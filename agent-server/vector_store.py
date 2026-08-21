"""
向量存储层：对应架构图里的 vector_stores.py + chroma_db/。

设计成「接口 + 双后端」：
- ChromaStore：chromadb PersistentClient 持久化 + cosine 空间，主后端；
- JsonStore：vectors.json 落盘 + 纯Python余弦暴力检索，回退后端。
  chromadb 在 Python 3.13 / Render 512MB 环境下有不确定性（旧版装不上、内存紧张），
  回退只改环境变量 KB_BACKEND=json 或 import 失败自动降级，业务代码零改动。
  语料只有百来个块，暴力余弦毫秒级，检索质量与 ANN 无差别。

业务层只依赖 VectorStore 接口，统一返回：
  [{id, articleId, articleTitle, heading, text, score}]
score 语义与前端手写余弦一致（越大越相似，1 为上限）。
"""
import json
import math
import os
from typing import Optional, Protocol

import config

COLLECTION = "psych_kb"


def _cosine(a: list[float], b: list[float]) -> float:
    """纯Python余弦：回退后端用（迁自 tools.py 原实现）"""
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb or 1)


class VectorStore(Protocol):
    backend_name: str

    def count(self) -> int: ...
    def upsert(self, ids: list[str], vectors: list[list[float]],
               metadatas: list[dict], documents: list[str]) -> None: ...
    def query(self, vector: list[float], top_k: int) -> list[dict]: ...
    def clear(self) -> None: ...
    def fingerprint(self) -> Optional[str]: ...
    def set_fingerprint(self, fp: str) -> None: ...


class ChromaStore:
    """chromadb 持久化后端：数据落 CHROMA_DIR，进程重启后无需重新 embedding"""

    backend_name = "chroma"

    def __init__(self):
        # chromadb 延迟到构造时才 import：不用 chroma 时（回退模式下）不占内存
        import chromadb
        from chromadb.config import Settings

        self._client = chromadb.PersistentClient(
            path=config.CHROMA_DIR,
            settings=Settings(anonymized_telemetry=False),  # 关遥测，省一次外呼
        )
        self._col = self._client.get_or_create_collection(
            name=COLLECTION,
            metadata={"hnsw:space": "cosine"},  # 距离空间必须是余弦，和打分语义对齐
        )

    def count(self) -> int:
        return self._col.count()

    def upsert(self, ids, vectors, metadatas, documents) -> None:
        self._col.upsert(ids=ids, embeddings=vectors,
                         metadatas=metadatas, documents=documents)

    def query(self, vector, top_k) -> list[dict]:
        if self._col.count() == 0:
            return []
        res = self._col.query(
            query_embeddings=[vector],
            n_results=min(top_k, self._col.count()),
            include=["metadatas", "documents", "distances"],
        )
        out = []
        # chroma 按入参维度返回嵌套列表（我们只查一条，取第一层）
        for cid, meta, doc, dist in zip(
            res["ids"][0], res["metadatas"][0], res["documents"][0], res["distances"][0]
        ):
            meta = meta or {}
            # cosine distance = 1 - 相似度：换算回与前端一致的分数语义
            out.append({
                "id": cid,
                "articleId": meta.get("articleId", ""),
                "articleTitle": meta.get("articleTitle", ""),
                "heading": meta.get("heading", ""),
                "text": doc or "",
                "score": round(1 - dist, 4),
            })
        return out

    def clear(self) -> None:
        # 删集合重建比逐条 delete 干净：metadata 里的指纹也一并清掉
        self._client.delete_collection(COLLECTION)
        self._col = self._client.get_or_create_collection(
            name=COLLECTION, metadata={"hnsw:space": "cosine"}
        )

    def fingerprint(self) -> Optional[str]:
        return (self._col.metadata or {}).get("fingerprint")

    def set_fingerprint(self, fp: str) -> None:
        # chroma 1.5+ 禁止 modify 时携带 hnsw:space（即使值没变也算"改距离函数"报错）；
        # 只传 fingerprint 即可——距离函数在创建集合时已固化，metadata 里丢掉不影响检索
        self._col.modify(metadata={"fingerprint": fp})


class JsonStore:
    """文件后端：单 JSON 文件 + 暴力余弦。chromadb 不可用时的保险丝"""

    backend_name = "json"

    def __init__(self):
        self._path = os.path.join(config.CHROMA_DIR, "vectors.json")
        os.makedirs(config.CHROMA_DIR, exist_ok=True)
        self._data = {"fingerprint": None, "items": []}
        if os.path.exists(self._path):
            try:
                with open(self._path, encoding="utf-8") as f:
                    self._data = json.load(f)
            except Exception:
                pass  # 文件损坏当作空库，重新灌

    def _save(self) -> None:
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False)

    def count(self) -> int:
        return len(self._data["items"])

    def upsert(self, ids, vectors, metadatas, documents) -> None:
        by_id = {it["id"]: it for it in self._data["items"]}
        for cid, vec, meta, doc in zip(ids, vectors, metadatas, documents):
            by_id[cid] = {"id": cid, "vector": vec, "meta": meta, "doc": doc}
        self._data["items"] = list(by_id.values())
        self._save()

    def query(self, vector, top_k) -> list[dict]:
        ranked = sorted(
            ((_cosine(vector, it["vector"]), it) for it in self._data["items"]),
            key=lambda x: x[0], reverse=True,
        )[:top_k]
        return [{
            "id": it["id"],
            "articleId": it["meta"].get("articleId", ""),
            "articleTitle": it["meta"].get("articleTitle", ""),
            "heading": it["meta"].get("heading", ""),
            "text": it["doc"],
            "score": round(s, 4),
        } for s, it in ranked]

    def clear(self) -> None:
        self._data = {"fingerprint": None, "items": []}
        self._save()

    def fingerprint(self) -> Optional[str]:
        return self._data.get("fingerprint")

    def set_fingerprint(self, fp: str) -> None:
        self._data["fingerprint"] = fp
        self._save()


_store: Optional[VectorStore] = None


def get_vector_store() -> VectorStore:
    """单例工厂：优先 chroma；KB_BACKEND=json 显式回退，或 chromadb 装不上/初始化失败自动降级"""
    global _store
    if _store is not None:
        return _store
    if config.KB_BACKEND == "chroma":
        try:
            _store = ChromaStore()
            print(f"[向量库] 使用 chromadb 后端（目录 {config.CHROMA_DIR}）")
            return _store
        except Exception as e:  # noqa: BLE001 —— 降级不能炸启动，只打日志
            print(f"[向量库] chromadb 初始化失败，降级 json 后端：{e}")
    _store = JsonStore()
    print(f"[向量库] 使用 json 回退后端（{config.CHROMA_DIR}/vectors.json）")
    return _store
