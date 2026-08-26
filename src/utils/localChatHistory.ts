import type { ChatMessage } from "@/types";

/**
 * 本地会话历史存储 v2：IndexedDB 异步存储层
 *
 * 背景：后端 /psychological-chat/stream 的AI服务故障且无"追加消息"接口，
 * 直连LLM的对话消息由前端持久化，加载历史会话时与服务端消息合并。
 *
 * 从 localStorage 升级到 IndexedDB 的动机：
 * 1. localStorage 是同步IO，大会话 JSON.parse/stringify 会阻塞主线程；IndexedDB 全异步
 * 2. localStorage 约5MB配额，长会话（含引用卡片）容易触顶被浏览器静默丢弃
 * 3. IndexedDB 结构化克隆：citations 等嵌套对象直接存取，无需整体JSON序列化
 * 4. 首次打开自动把 localStorage 存量数据迁入，用户无感升级
 *
 * 对外接口与 v1 完全同名（读/存/迁移/删/合并），仅由同步改为异步。
 */

const DB_NAME = "chat_history_db";
const DB_VERSION = 1;
const STORE = "messages";
//v1 localStorage 键前缀（存量迁移用）
const LEGACY_PREFIX = "local_chat_history";
//单会话最多保留的消息条数，防长会话无限膨胀
const MAX_MESSAGES = 200;

//当前登录用户id：同一浏览器里区分不同账号的会话记录
const getUserId = () => {
  try {
    const info = JSON.parse(localStorage.getItem("userInfo") || "{}");
    return info.userId ?? info.id ?? "guest";
  } catch {
    return "guest";
  }
};

//会话key归一化：同一会话在页面里可能是 123 / "session_123" / "temp_123" 三种形态，
//统一去掉 session_ 前缀，保证不同来源的id寻址到同一个存储桶
const getSessionKey = (sessionId: number | string) => {
  return String(sessionId ?? "").replace(/^session_/, "") || "unknown";
};

//存储桶键 = 用户id + 会话key，与v1的localStorage键尾保持同构（迁移零转换）
const bucketKey = (sessionId: number | string) =>
  `${getUserId()}_${getSessionKey(sessionId)}`;

/** 存储记录：消息体 + 桶键（seq自增主键由IndexedDB生成，天然保序） */
interface StoredMessage extends ChatMessage {
  // IndexedDB 的内部自增主键，不属于业务消息；读取后不能带回再次 add
  seq?: number;
  bucket: string;
}

// ---- IndexedDB 基础设施：连接单例 + 请求Promise化 ----

let dbPromise: Promise<IDBDatabase> | null = null;

const openDb = (): Promise<IDBDatabase> => {
  if (dbPromise) {
    return dbPromise;
  }
  dbPromise = new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VERSION);
    //首次建库/升版时建表：自增主键保序，桶键建索引用于按会话查询
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains(STORE)) {
        const store = db.createObjectStore(STORE, {
          keyPath: "seq",
          autoIncrement: true,
        });
        store.createIndex("bucket", "bucket", { unique: false });
      }
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
  return dbPromise;
};

const objectStore = async (mode: IDBTransactionMode) => {
  const db = await openDb();
  return db.transaction(STORE, mode).objectStore(STORE);
};

const reqAsPromise = <T>(req: IDBRequest<T>): Promise<T> =>
  new Promise((resolve, reject) => {
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });

// ---- v1存量迁移：localStorage → IndexedDB，跑一次即清 ----

const migrateLegacyLocalStorage = async () => {
  let moved = 0;
  for (let i = 0; i < localStorage.length; i++) {
    const key = localStorage.key(i) ?? "";
    if (!key.startsWith(`${LEGACY_PREFIX}_`)) {
      continue;
    }
    try {
      //旧键 local_chat_history_{userId}_{sessionKey} 剥前缀后正好是新桶键
      const bucket = key.slice(LEGACY_PREFIX.length + 1);
      const list = JSON.parse(localStorage.getItem(key) || "[]");
      if (Array.isArray(list) && list.length) {
        const store = await objectStore("readwrite");
        for (const msg of list) {
          // 旧数据可能已经带有 seq。迁移时必须让 IndexedDB 重新生成主键，
          // 否则重复迁移/已有记录会触发 ConstraintError。
          const { seq: _seq, ...messageWithoutSeq } = msg as StoredMessage;
          store.add({ ...messageWithoutSeq, bucket });
        }
        moved += list.length;
      }
      localStorage.removeItem(key);
      i--; //removeItem后后面的键整体前移一位
    } catch {
      //单键迁移失败跳过，下次进来重试（键还在）
    }
  }
  if (moved > 0) {
    console.log(`[历史] localStorage 存量 ${moved} 条已迁入 IndexedDB`);
  }
};

//模块加载即完成迁移，业务侧无感
openDb()
  .then(migrateLegacyLocalStorage)
  .catch(() => {
    //IndexedDB不可用（隐私模式等）：读写接口各自降级返回空，不阻塞聊天
  });

// ---- 对外接口（与v1同名，异步化） ----

/** 读取某个会话的本地历史（失败返回空数组，不影响对话展示） */
export const getLocalMessages = async (
  sessionId: number | string,
): Promise<ChatMessage[]> => {
  try {
    const store = await objectStore("readonly");
    const records = (await reqAsPromise(
      store.index("bucket").getAll(bucketKey(sessionId)),
    )) as StoredMessage[];
    //剥掉存储字段，只留消息体；seq自增天然按写入顺序排列
    // seq 只是 IndexedDB 内部主键，不能暴露给业务层，否则消息再次保存时
    // store.add() 会尝试复用旧主键并报 Key already exists。
    return records.map(({ bucket: _bucket, seq: _seq, ...msg }) => msg);
  } catch {
    return [];
  }
};

/** 追加一条消息到本地历史（错误提示不入库；存储失败不影响聊天主流程） */
export const saveLocalMessage = async (
  sessionId: number | string,
  msg: ChatMessage,
) => {
  if (msg.isError) {
    return;
  }
  try {
    const bucket = bucketKey(sessionId);
    //入参可能是Vue响应式代理：aiMessage由reactive()包装，浅拷贝后嵌套的citations
    //经get陷阱读出仍是Proxy，而Proxy不可结构化克隆，直接add会抛DataCloneError
    //（表现为带引用的AI回复全部落库失败）。JSON往返剥成纯对象再入库；
    //消息体全是JSON安全字段（createdAt为ISO字符串），往返无损。
    const plainMsg = JSON.parse(JSON.stringify(msg)) as StoredMessage;
    // 无论消息来自页面新建、历史回显还是迁移，都只允许 IndexedDB 生成 seq。
    const { seq: _seq, ...messageWithoutSeq } = plainMsg;
    const store = await objectStore("readwrite");
    await reqAsPromise(store.add({ ...messageWithoutSeq, bucket }));
    //桶内超限裁剪：删最早的（seq最小）记录
    const keys = (await reqAsPromise(
      store.index("bucket").getAllKeys(bucket),
    )) as IDBValidKey[];
    if (keys.length > MAX_MESSAGES) {
      for (const key of keys.slice(0, keys.length - MAX_MESSAGES)) {
        store.delete(key);
      }
    }
  } catch (error) {
    console.warn("本地会话历史保存失败", error);
  }
};

/** 清空某个会话桶 */
const clearBucket = async (sessionId: number | string) => {
  const store = await objectStore("readwrite");
  const keys = (await reqAsPromise(
    store.index("bucket").getAllKeys(bucketKey(sessionId)),
  )) as IDBValidKey[];
  for (const key of keys) {
    store.delete(key);
  }
};

/** temp会话转正（后端session/start拿到真实id）时，把temp桶消息并入真实桶 */
export const migrateLocalHistory = async (
  fromId: number | string,
  toId: number | string,
) => {
  try {
    const [from, to] = await Promise.all([
      getLocalMessages(fromId),
      getLocalMessages(toId),
    ]);
    if (!from.length) {
      return;
    }
    //去重规则与mergeHistory一致：发送方+正文相同视为已存在
    const seen = new Set(
      to.map((msg) => `${Number(msg.senderType)}|${msg.content}`),
    );
    for (const msg of from) {
      if (!seen.has(`${Number(msg.senderType)}|${msg.content}`)) {
        await saveLocalMessage(toId, msg);
      }
    }
    await clearBucket(fromId);
  } catch (error) {
    console.warn("本地会话历史迁移失败", error);
  }
};

/** 删除会话时同步清理本地历史 */
export const removeLocalHistory = async (sessionId: number | string) => {
  try {
    await clearBucket(sessionId);
  } catch (error) {
    console.warn("本地会话历史清理失败", error);
  }
};

/**
 * 服务端历史与本地历史合并
 * 服务端只存了session/start的首条用户消息且在前，本地消息去重后按原顺序追加在后，
 * 拼起来正好是完整的对话时间线
 */
export const mergeHistory = (
  serverMessages: ChatMessage[],
  localMessages: ChatMessage[],
): ChatMessage[] => {
  const seen = new Set(
    serverMessages.map((msg) => `${Number(msg.senderType)}|${msg.content}`),
  );
  const extra = localMessages.filter(
    (msg) => !seen.has(`${Number(msg.senderType)}|${msg.content}`),
  );
  return [...serverMessages, ...extra];
};
