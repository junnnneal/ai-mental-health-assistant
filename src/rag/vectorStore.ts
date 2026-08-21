import type { KnowledgeChunk } from "./types";

/**
 * 向量库的IndexedDB缓存层
 * 首次检索：文章分块 → 批量embedding → 落库（约35篇×4块，一次性成本）
 * 之后：直接读本地缓存，不再请求embedding接口
 * 版本指纹 = 文章集合(id+updatedAt+title)，知识库内容变化后自动全量重建
 */

const DB_NAME = "rag_vector_store";
const DB_VERSION = 1;
const STORE_CHUNKS = "chunks";
const STORE_META = "meta";

//打开（或初始化）向量库
const openDb = () =>
  new Promise<IDBDatabase>((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VERSION);
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains(STORE_CHUNKS)) {
        db.createObjectStore(STORE_CHUNKS, { keyPath: "id" });
      }
      if (!db.objectStoreNames.contains(STORE_META)) {
        db.createObjectStore(STORE_META);
      }
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });

//读meta（如版本指纹），库不可用时返回null（隐私模式等场景降级）
export const getMeta = async (key: string): Promise<unknown> => {
  try {
    const db = await openDb();
    return await new Promise((resolve, reject) => {
      const req = db.transaction(STORE_META).objectStore(STORE_META).get(key);
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error);
    });
  } catch {
    return null;
  }
};

export const setMeta = async (key: string, value: unknown) => {
  const db = await openDb();
  return new Promise<void>((resolve, reject) => {
    const req = db
      .transaction(STORE_META, "readwrite")
      .objectStore(STORE_META)
      .put(value, key);
    req.onsuccess = () => resolve();
    req.onerror = () => reject(req.error);
  });
};

//读全部知识块（含向量）
export const getAllChunks = async (): Promise<KnowledgeChunk[]> => {
  const db = await openDb();
  return new Promise((resolve, reject) => {
    const req = db.transaction(STORE_CHUNKS).objectStore(STORE_CHUNKS).getAll();
    req.onsuccess = () => resolve((req.result || []) as KnowledgeChunk[]);
    req.onerror = () => reject(req.error);
  });
};

//批量写入知识块：单事务多次put，整批成功才落定
export const putChunks = async (chunks: KnowledgeChunk[]) => {
  const db = await openDb();
  return new Promise<void>((resolve, reject) => {
    const tx = db.transaction(STORE_CHUNKS, "readwrite");
    const store = tx.objectStore(STORE_CHUNKS);
    chunks.forEach((chunk) => store.put(chunk));
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
};

export const clearChunks = async () => {
  const db = await openDb();
  return new Promise<void>((resolve, reject) => {
    const req = db
      .transaction(STORE_CHUNKS, "readwrite")
      .objectStore(STORE_CHUNKS)
      .clear();
    req.onsuccess = () => resolve();
    req.onerror = () => reject(req.error);
  });
};
