"""
知识库入库编排：种子文章加载 → 分块 → 向量化 → 写入向量库。
对应架构图里的 knowledge_base.py（原图是上传文件触发，这里改为
「启动时自动判空灌库 + 改数据后指纹失配自动重建 + 管理端点手动重建」三种入口）。

知识源用内置 data/*.json 种子而不是课程后端：
- 后端文章库会被同学清掉（发生过），内置源不依赖外部存活；
- 后端接口要用户 token，服务启动时没有可用身份。
"""
import asyncio
import hashlib
import json
import os
import re
from typing import Optional

import httpx

import config
from rag import embed_texts
from vector_store import get_vector_store

# 入库互斥锁：ensure_built 与 rebuild 并发时串行执行，避免交叉写库
_build_lock = asyncio.Lock()
# 单飞任务：并发调用 ensure_built 共享同一次构建（对齐前端 retriever.ts 的单飞模式）
_build_task: Optional[asyncio.Task] = None


def _seed_files() -> list[str]:
    """种子 JSON 按文件名排序：顺序稳定，指纹才稳定"""
    d = config.KB_SEED_DIR
    return sorted(
        os.path.join(d, f) for f in os.listdir(d) if f.endswith(".json")
    ) if os.path.isdir(d) else []


def _seed_fingerprint() -> str:
    """语料指纹 = 全部种子文件内容的 sha256。文件增删改都会让指纹变化触发重建"""
    h = hashlib.sha256()
    for path in _seed_files():
        h.update(os.path.basename(path).encode("utf-8"))
        with open(path, "rb") as f:
            h.update(f.read())
    return h.hexdigest()


def _load_seed_articles() -> list[dict]:
    """读 data/*.json → 统一成 {id, title, categoryName, content} 结构。
    种子文件没有 id 字段，用 seed:{文件名}:{序号} 生成稳定 id：
    重启/重建后引用卡片里持久化的 articleId 不会漂移。"""
    articles = []
    for path in _seed_files():
        stem = os.path.splitext(os.path.basename(path))[0]
        with open(path, encoding="utf-8") as f:
            items = json.load(f)
        for i, a in enumerate(items):
            articles.append({
                "id": f"seed:{stem}:{i}",
                "title": str(a.get("title") or ""),
                "categoryName": str(a.get("category") or ""),
                "content": str(a.get("content") or ""),
            })
    return articles


def _chunk_article(article: dict) -> list[dict]:
    """单篇分块（原 tools.py:105-120 逻辑原样迁移，与前端 chunker.ts 同款）：
    <h3> 小节是天然语义边界；纯文本不足20字的碎块丢弃；
    向量化文本带 【分类】标题 - 小节 前缀提升检索命中率。"""
    html = article.get("content") or ""
    title = article.get("title") or ""
    category = article.get("categoryName") or ""
    chunks = []
    for sec in filter(None, (s.strip() for s in re.split(r"(?=<h3>)", html))):
        m = re.search(r"<h3>(.*?)</h3>", sec)
        heading = m.group(1) if m else title
        text = re.sub(r"<[^>]+>", "", sec).strip()
        if len(text) < 20:
            continue
        chunks.append({
            # 与前端 KnowledgeChunk.id 同构：{文章id}_{小节序号}
            "id": f"{article['id']}_{len(chunks)}",
            "articleId": article["id"],
            "articleTitle": title,
            "heading": heading,
            "text": text,
            "embed_text": f"【{category}】{title} - {heading}\n{text}",
        })
    return chunks


async def _ingest(store) -> int:
    """清库 → 全量分块 → 分批向量化 → 写入 → 记指纹"""
    fp = _seed_fingerprint()
    store.clear()
    chunks = []
    for article in _load_seed_articles():
        chunks.extend(_chunk_article(article))
    if not chunks:
        print("[知识库] 种子语料为 0 块，检查 data/*.json 是否存在")
        return 0
    async with httpx.AsyncClient(timeout=60) as client:
        vectors = await embed_texts([c["embed_text"] for c in chunks], client)
    valid = [(c, v) for c, v in zip(chunks, vectors) if v]
    if len(valid) < len(chunks):
        # 缺块绝不入库、绝不记指纹：部分库+匹配指纹 = 永不自愈的静默缺块
        # （线上事故根因：embedding 掉条被过滤后照常 set_fingerprint，655 块只剩 610）。
        # 抛错让指纹保持失配，下一次 ensure_built / 重启自动整库重试——全有或全无。
        raise RuntimeError(
            f"向量化不完整：{len(valid)}/{len(chunks)} 块，放弃本次入库（不记指纹，下次自动重试）")
    store.upsert(
        ids=[c["id"] for c, _ in valid],
        vectors=[v for _, v in valid],
        metadatas=[
            {
                "articleId": c["articleId"],
                "articleTitle": c["articleTitle"],
                "heading": c["heading"],
            }
            for c, _ in valid
        ],
        documents=[c["text"] for c, _ in valid],
    )
    store.set_fingerprint(fp)
    print(f"[知识库] 入库完成：{len(valid)} 个知识块（指纹 {fp[:8]}…）")
    return len(valid)


async def ensure_built() -> int:
    """知识库就绪入口：指纹匹配且非空直接返回；否则触发单飞构建并等待。
    失败会抛出（调用方自行降级），下一次调用自动重试。"""
    global _build_task
    store = get_vector_store()
    fp = _seed_fingerprint()
    if store.count() > 0 and store.fingerprint() == fp:
        return store.count()
    if _build_task is None or _build_task.done():
        _build_task = asyncio.create_task(_do_build())
    # shield：某个等待方被取消（如 /rag/chat 的3s软超时）不能连带取消构建本身
    return await asyncio.shield(_build_task)


async def _do_build() -> int:
    async with _build_lock:
        store = get_vector_store()
        fp = _seed_fingerprint()
        # 拿到锁后再查一次：可能别人（rebuild/前一个任务）已经建完
        if store.count() > 0 and store.fingerprint() == fp:
            return store.count()
        return await _ingest(store)


async def rebuild() -> int:
    """强制重建（管理端点 /kb/rebuild 用）：无视指纹直接清库重灌。
    挂到 _build_task 上让 /health 的 building 位对手动重建也可见
    （否则重建失败/进行中都显示 building:false，线上排障被误导过）。"""
    global _build_task
    _build_task = asyncio.current_task()
    try:
        async with _build_lock:
            return await _ingest(get_vector_store())
    finally:
        _build_task = None


def is_building() -> bool:
    return _build_task is not None and not _build_task.done()


def chunk_count() -> int:
    try:
        return get_vector_store().count()
    except Exception:
        return 0
