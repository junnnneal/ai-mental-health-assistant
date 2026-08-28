"""
BM25 词法检索（混合检索第三路）：补稠密向量在精确词面匹配上的短板。

为什么加：embedding 粗排是语义召回，专有名词/术语/精确字面（"惊恐发作""CBT-I"）
可能整体排不进余弦 top-10——精排只能重排已召回的候选，捞不回没进池子的块
（100 题评测里 R@10=0 的粗排缺口就是这类）。BM25 是稀疏词法检索，与稠密向量互补：
两路各捞 top-N → 去重并集进 cross-encoder 精排 → 三路排名 RRF 等权融合（见 rag.py）。

实现说明：
- 纯 Python Okapi BM25（k1=1.5 b=0.75，IDF 用 +1 平滑避免负贡献），655 块规模毫秒级，
  不引外部服务（ES/Milvus 稀疏）是刻意的：这个体量上纯内存倒排就是最优解；
- 中文分词：jieba 可用则用之；装不上（Render 内存紧张/装包失败）自动退化为
  CJK 字符二元组 + ASCII 整词（Elasticsearch CJK 分析器同款策略）——与 vector_store
  双后端同一哲学：删掉 requirements 里的 jieba 一行即降级，业务代码零改动；
- 索引与向量库同生命周期：按种子语料 sha256 指纹惰性构建，语料变了自动重建。
  构建只做本地文本处理（分词+词频统计），不打任何 API；
- 任何失败返回 []：词法路是增强项，绝不拖垮检索主链路（降级=两路融合照常）。
"""
import math
import os
import re
import threading
from collections import Counter
from typing import Optional

import config

try:
    import jieba
except ImportError:  # 降级路径：CJK 二元组分词，见模块 docstring
    jieba = None

K1 = 1.5   # Okapi 标准值：词频饱和速度
B = 0.75   # 文档长度归一化强度

_CJK_RUN = re.compile(r"[一-鿿]+")
_ASCII_WORD = re.compile(r"[A-Za-z0-9]+(?:[-'.][A-Za-z0-9]+)*")
_HAS_CONTENT = re.compile(r"[一-鿿A-Za-z0-9]")

_jieba_ready = False


def _tokenize_char(text: str) -> list[str]:
    """CJK 二元组 + ASCII 整词（小写）。跨词边界的二元组是噪声，但 IDF 会压掉
    绝大多数（高频虚词 df≈N → idf 趋零；生僻跨界对的干扰交给下游精排闸门兜底）——
    词法路的职责是召回，不是精准。"""
    toks: list[str] = []
    for run in _CJK_RUN.findall(text):
        toks.extend(run[i:i + 2] for i in range(len(run) - 1))
    toks.extend(w.lower() for w in _ASCII_WORD.findall(text))
    return toks


def tokenize(text: str) -> list[str]:
    """查询与文档共用同一分词器（BM25 的硬前提）。"""
    if jieba is None or os.getenv("BM25_TOKENIZER", "").lower() == "char":
        return _tokenize_char(text)
    global _jieba_ready
    if not _jieba_ready:
        jieba.initialize()  # 首次加载词典 ~1s，之后纯查表
        _jieba_ready = True
    return [t.lower() for t in jieba.lcut(text) if _HAS_CONTENT.search(t)]


def tokenizer_name() -> str:
    if jieba is None or os.getenv("BM25_TOKENIZER", "").lower() == "char":
        return "char-bigram"
    return "jieba"


class _BM25Index:
    """倒排统计 + Okapi 打分。语料百级，直接每查询全量扫文档打分（毫秒级），
    不必建 posting list——规模上万再换。"""

    def __init__(self, chunks: list[dict]):
        self.docs = {c["id"]: c for c in chunks}
        self.order = [c["id"] for c in chunks]
        # 索引文本带标题语境：标题词是用户词面命中的高发区，与 embed_text 前缀同理
        self.tf: dict[str, Counter] = {}
        self.len: dict[str, int] = {}
        df: Counter = Counter()
        for c in chunks:
            toks = tokenize(f"{c['articleTitle']} {c['heading']} {c['text']}")
            self.tf[c["id"]] = Counter(toks)
            self.len[c["id"]] = len(toks)
            df.update(set(toks))
        self.N = len(chunks)
        self.avgdl = (sum(self.len.values()) / self.N) if self.N else 0.0
        self.idf = {t: math.log(1.0 + (self.N - n + 0.5) / (n + 0.5)) for t, n in df.items()}

    def search(self, query: str, top_n: int) -> list[tuple[dict, float]]:
        q = tokenize(query)
        if not q or not self.N:
            return []
        scores: list[tuple[str, float]] = []
        for did in self.order:
            tf, dl = self.tf[did], self.len[did]
            s = 0.0
            for t in q:
                f = tf.get(t)
                if not f:
                    continue
                s += self.idf[t] * f * (K1 + 1) / (f + K1 * (1 - B + B * dl / self.avgdl))
            if s > 0:
                scores.append((did, s))
        scores.sort(key=lambda x: -x[1])
        return [(self.docs[d], round(s, 4)) for d, s in scores[:top_n]]


_index: Optional[_BM25Index] = None
_index_fp: Optional[str] = None
_lock = threading.Lock()


def _build() -> _BM25Index:
    # 延迟导入 knowledge_base：它在模块级 import rag，rag 又 import 本模块，
    # 成环只能在函数内解开
    from knowledge_base import _chunk_article, _load_seed_articles, _seed_fingerprint
    chunks = [
        {"id": c["id"], "articleId": c["articleId"], "articleTitle": c["articleTitle"],
         "heading": c["heading"], "text": c["text"]}
        for art in _load_seed_articles() for c in _chunk_article(art)
    ]
    if not chunks:
        raise RuntimeError("种子语料为 0 块")
    print(f"[BM25] 构建索引：{len(chunks)} 块（tokenizer={tokenizer_name()}）")
    return _BM25Index(chunks)


def get_index() -> Optional[_BM25Index]:
    """惰性单例：语料指纹变了自动重建（与向量库 ensure_built 同一套指纹）。"""
    global _index, _index_fp
    from knowledge_base import _seed_fingerprint
    fp = _seed_fingerprint()
    if _index is not None and _index_fp == fp:
        return _index
    with _lock:
        if _index is None or _index_fp != fp:  # 双检：等待锁期间可能已被建好
            try:
                _index = _build()
                _index_fp = fp
            except Exception as e:  # noqa: BLE001 —— 词法路挂了不能影响向量检索
                print(f"[BM25] 索引构建失败，词法路本轮关闭（重启后重试）：{e}")
                return None
    return _index


def search(query: str, top_n: int) -> list[tuple[dict, float]]:
    """BM25 top_n 检索：[(chunk_dict, bm25分)] 按分降序。任何失败返回 []。"""
    if top_n <= 0 or not (query or "").strip():
        return []
    try:
        idx = get_index()
        if idx is None:
            return []
        return idx.search(query, top_n)
    except Exception as e:  # noqa: BLE001 —— 增强项绝不拖垮主链路
        print(f"[BM25] 检索失败，本条跳过词法路：{e}")
        return []
