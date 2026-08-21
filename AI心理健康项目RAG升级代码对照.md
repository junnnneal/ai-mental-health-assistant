INFO: Started server process [157776]
INFO: Waiting for application startup.
INFO: Application startup complete.
INFO: Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
INFO: 127.0.0.1:56114 - "GET /health HTTP/1.1" 200 OK
INFO: 127.0.0.1:62050 - "POST /chat HTTP/1.1" 500 Internal Server Error
ERROR: Exception in ASGI application
Traceback (most recent call last):
File "C:\Users\24744\Desktop\AI+VUE3项目\AI_project\agent-server\.venv\Lib\site-packages\uvicorn\protocols\http\httptools_impl.py", line 422, in run_asgi
result = await app( # type: ignore[func-returns-value]
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
self.scope, self.receive, self.send
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
)
^
File "C:\Users\24744\Desktop\AI+VUE3项目\AI_project\agent-server\.venv\Lib\site-packages\uvicorn\middleware\proxy_headers.py", line 63, in **call**
return await self.app(scope, receive, send)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
File "C:\Users\24744\Desktop\AI+VUE3项目\AI_project\agent-server\.venv\Lib\site-packages\fastapi\applications.py", line 1163, in **call**
await super().**call**(scope, receive, send)
File "C:\Users\24744\Desktop\AI+VUE3项目\AI_project\agent-server\.venv\Lib\site-packages\starlette\applications.py", line 96, in **call**
await self.middleware_stack(scope, receive, send)
File "C:\Users\24744\Desktop\AI+VUE3项目\AI_project\agent-server\.venv\Lib\site-packages\starlette\middleware\errors.py", line 186, in **call**
raise exc
File "C:\Users\24744\Desktop\AI+VUE3项目\AI_project\agent-server\.venv\Lib\site-packages\starlette\middleware\errors.py", line 164, in **call**
await self.app(scope, receive, \_send)
File "C:\Users\24744\Desktop\AI+VUE3项目\AI_project\agent-server\.venv\Lib\site-packages\starlette\middleware\cors.py", line 88, in **call**
await self.app(scope, receive, send)
File "C:\Users\24744\Desktop\AI+VUE3项目\AI_project\agent-server\.venv\Lib\site-packages\starlette\middleware\exceptions.py", line 63, in **call**
await wrap_app_handling_exceptions(self.app, conn)(scope, receive, send)
File "C:\Users\24744\Desktop\AI+VUE3项目\AI_project\agent-server\.venv\Lib\site-packages\starlette_exception_handler.py", line 53, in wrapped_app
raise exc
File "C:\Users\24744\Desktop\AI+VUE3项目\AI_project\agent-server\.venv\Lib\site-packages\starlette_exception_handler.py", line 42, in wrapped_app
await app(scope, receive, sender)
File "C:\Users\24744\Desktop\AI+VUE3项目\AI_project\agent-server\.venv\Lib\site-packages\fastapi\middleware\asyncexitstack.py", line 18, in **call**
await self.app(scope, receive, send)
File "C:\Users\24744\Desktop\AI+VUE3项目\AI_project\agent-server\.venv\Lib\site-packages\starlette\routing.py", line 670, in **call**
await self.middleware_stack(scope, receive, send)
File "C:\Users\24744\Desktop\AI+VUE3项目\AI_project\agent-server\.venv\Lib\site-packages\fastapi\routing.py", line 2734, in app
await route.handle(scope, receive, send)
File "C:\Users\24744\Desktop\AI+VUE3项目\AI_project\agent-server\.venv\Lib\site-packages\fastapi\routing.py", line 1281, in handle
await super().handle(scope, receive, send)
File "C:\Users\24744\Desktop\AI+VUE3项目\AI_project\agent-server\.venv\Lib\site-packages\starlette\routing.py", line 280, in handle
await self.app(scope, receive, send)
File "C:\Users\24744\Desktop\AI+VUE3项目\AI_project\agent-server\.venv\Lib\site-packages\fastapi\routing.py", line 158, in app
await wrap_app_handling_exceptions(app, request)(scope, receive, send)
File "C:\Users\24744\Desktop\AI+VUE3项目\AI_project\agent-server\.venv\Lib\site-packages\starlette_exception_handler.py", line 53, in wrapped_app
raise exc
File "C:\Users\24744\Desktop\AI+VUE3项目\AI_project\agent-server\.venv\Lib\site-packages\starlette_exception_handler.py", line 42, in wrapped_app
await app(scope, receive, sender)
File "C:\Users\24744\Desktop\AI+VUE3项目\AI_project\agent-server\.venv\Lib\site-packages\fastapi\routing.py", line 144, in app
response = await f(request)
^^^^^^^^^^^^^^^^
File "C:\Users\24744\Desktop\AI+VUE3项目\AI_project\agent-server\.venv\Lib\site-packages\fastapi\routing.py", line 706, in app
raw_response = await run_endpoint_function(
^^^^^^^^^^^^^^^^^^^^^^^^^^^^
...<3 lines>...
)
^
File "C:\Users\24744\Desktop\AI+VUE3项目\AI_project\agent-server\.venv\Lib\site-packages\fastapi\routing.py", line 352, in run_endpoint_function
return await dependant.call(\*\*values)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
File "C:\Users\24744\Desktop\AI+VUE3项目\AI_project\agent-server\main.py", line 38, in chat
body = await request.json()
^^^^^^^^^^^^^^^^^^^^
File "C:\Users\24744\Desktop\AI+VUE3项目\AI_project\agent-server\.venv\Lib\site-packages\starlette\requests.py", line 265, in json
self.\_json = json.loads(body)
~~~~~~~~~~^^^^^^
File "C:\Users\24744\AppData\Local\Programs\Python\Python313\Lib\json\_\_init\_\_.py", line 341, in loads
s = s.decode(detect_encoding(s), 'surrogatepass')
UnicodeDecodeError: 'utf-8' codec can't decode byte 0xce in position 12: invalid continuation byte
},
});
await api(`/knowledge/article/${id}/status`, { method: "PUT", body: { status: 1 } });

````

**面试要点**：
- 后端 `code` 字段返回的是**字符串 `"200"`**（原项目 request.ts 用 `==` 宽松比较的原因），脚本用 `Number(json.code) !== 200` 兼容两种形态
- Windows 下 Node 在 HTTP 连接未关闭时调用 `process.exit()` 会触发 libuv 断言崩溃（`Assertion failed: UV_HANDLE_CLOSING`），改用 `process.exitCode = 1` 自然退出
- 脚本工程化细节：单篇失败不中断、幂等可重跑、轻限流（300ms/篇）

---

## 模块二：AI 对话保存问题——诊断与本地持久化

### 2.1 诊断过程（这段"破案"本身就是面试素材）

**现象**：AI 对话一直显示"繁忙"；换成 LLM 直连后，回复刷新就丢。

**用实验逐层定位**：

```text
实验1  POST /psychological-chat/stream → HTTP 200，120ms 后连接 terminated
       ↳ 所谓"一直繁忙"= 接口秒断，fetchEventSource 在后台自动无限重试的表象

实验2  stream 前后各查一次消息库 → 条数不变
       ↳ stream 挂了连用户消息都不落库（后端设计：它本该负责存后续消息+AI回复）

实验3  OPTIONS /sessions/{id}/messages → Allow: GET,HEAD,OPTIONS（没有POST！）
       对照 OPTIONS /session/start     → Allow: POST,OPTIONS（真实可靠）
       ↳ 后端唯一能写入的接口只有 session/start（仅存首条用户消息）
````

**关键技巧**：`OPTIONS` 请求的 `Allow` 响应头会让路由"自白"支持哪些 HTTP 方法——比猜测参数名/路径可靠得多（参数矩阵试了 10 种全返回同一个兜底"系统错误"，无法区分"参数错"和"路由不存在"）。

### 2.2 本地持久化方案（`src/utils/localChatHistory.ts`）

**干了什么**：后端不可改的约束下，对话消息由前端按 `用户ID+会话ID` 落 localStorage，加载历史时与服务端数据合并，实现刷新/重进后对话完整恢复。

**会话 key 归一化**——同一会话在页面里有三种 id 形态，必须收敛到同一个存储桶：

```ts
//会话key归一化：同一会话在页面里可能是 123 / "session_123" / "temp_123" 三种形态，
//统一去掉 session_ 前缀，保证不同来源的id寻址到同一个存储桶
const getSessionKey = (sessionId: number | string) => {
  return String(sessionId ?? "").replace(/^session_/, "") || "unknown";
};

const storageKey = (sessionId: number | string) =>
  `${KEY_PREFIX}_${getUserId()}_${getSessionKey(sessionId)}`;
```

**追加消息**（错误提示不入库，容量异常不影响聊天主流程）：

```ts
export const saveLocalMessage = (
  sessionId: number | string,
  msg: ChatMessage,
) => {
  if (msg.isError) {
    return;
  }
  try {
    const list = getLocalMessages(sessionId);
    list.push(msg);
    localStorage.setItem(
      storageKey(sessionId),
      JSON.stringify(list.slice(-MAX_MESSAGES)), // 单会话上限200条，防撑爆
    );
  } catch (error) {
    console.warn("本地会话历史保存失败", error);
  }
};
```

**服务端 + 本地历史合并**（服务端只存了首条用户消息，去重后拼接刚好是完整时间线）：

```ts
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
```

**接入点**（`Consultation.vue`）——三个生命周期全覆盖：

```ts
//① 用户消息上屏时同步落本地（temp会话先落temp桶）
saveLocalMessage(currentSession.value?.sessionId ?? "", userMessage);

//② temp会话转正（session/start成功）：把temp桶的消息迁移到真实会话桶
if (tempSessionId && tempSessionId !== sessionData.sessionId) {
  migrateLocalHistory(tempSessionId, sessionData.sessionId);
}

//③ AI回复流式结束收尾时落本地（引用卡片随消息一起持久化）
const finishStream = () => {
  stopTypewriter();
  aiMessage.content = fullText;
  isAiTyping.value = false;
  saveLocalMessage(sessionId, { ...aiMessage });
  loadSessionEmotion(sessionId);
  controller.abort();
};

//④ 加载历史会话：服务端 + 本地合并
message.value = mergeHistory(
  normalizeMessages(sessionMessages),
  getLocalMessages(sessionId),
);

//⑤ 删除会话：同步清理本地桶
await deleteSession(deleteId);
removeLocalHistory(deleteId);
```

**面试要点**：

- 方案的诚实边界（主动讲，加分）：跨设备不同步、管理后台看不到、明文存储、5MB 上限——并给出升级路径（后端加写入接口后，`saveLocalMessage` 一行换成调接口，合并逻辑保留当离线兜底）
- 挂死的后端通道整个删除，GLM 直连成为唯一通道，代码反而简化（去掉了双通道切换的代次守卫）

---

### 2.3 存储层升级：localStorage → IndexedDB（当天深夜）

**干了什么**：把对话本地持久化从 localStorage 整体迁移到 IndexedDB 异步存储层，对外接口同名（读/存/迁移/删/合并）、同步变异步，并自动完成 localStorage 存量数据的一次性迁移，用户无感。

**升级动机**：① localStorage 同步 IO 阻塞主线程，大会话 JSON.parse 会卡顿；② ~5MB 配额易触顶；③ IndexedDB 结构化克隆，citations 等嵌套对象免序列化；④ 容量配额大一个数量级以上。

**核心设计——桶模型 + 自增主键保序**：

```ts
// 存储记录 = 消息体 + 桶键（用户id_会话key，与v1键尾同构，迁移零转换）
interface StoredMessage extends ChatMessage { bucket: string }

// 建库：自增主键天然按写入顺序排列，桶键建索引用于按会话查询
req.onupgradeneeded = () => {
  const store = db.createObjectStore(STORE, { keyPath: "seq", autoIncrement: true });
  store.createIndex("bucket", "bucket", { unique: false });
};

// v1存量迁移：扫 local_chat_history_* 键 → 剥前缀即桶键 → 逐条写入 → 删旧键
// 单键失败跳过且键保留，下次进来自动重试（幂等）
const migrateLegacyLocalStorage = async () => {
  for (let i = 0; i < localStorage.length; i++) {
    const key = localStorage.key(i) ?? "";
    if (!key.startsWith(`${LEGACY_PREFIX}_`)) continue;
    const bucket = key.slice(LEGACY_PREFIX.length + 1);
    const list = JSON.parse(localStorage.getItem(key) || "[]");
    // ...写入后 localStorage.removeItem(key); i--;
  }
};
```

**面试要点**：

- **为什么不用 localStorage 了**：同步阻塞 + 5MB 配额 + 整体 JSON 序列化；IndexedDB 全异步、配额大、结构化克隆存对象。
- **怎么做到无感迁移**：新桶键与旧键尾同构（`userId_sessionKey`），模块加载时扫旧键迁移、迁完即删、失败保留重试——幂等设计。
- **为什么接口要异步化**：IndexedDB 是异步 API；`getLocalMessages` 变 `Promise` 后，唯一的调用点改动就是加一个 `await`（合并历史前等结果）。
- **边界处理**：IndexedDB 不可用（隐私模式）时读写各自降级返回空/警告，绝不阻塞聊天主流程；单桶超 200 条裁最旧（seq 最小）记录。
- 诚实边界（被追问时主动说）：IndexedDB 仍是浏览器本地存储，清站点数据会丢、不能跨设备——它优化的是**容量与性能**，不是**持久性**；持久性要靠服务端（SQLite/MySQL）。

## 模块三：LLM 统一客户端（`src/apis/llm.ts`）

**干了什么**：把对话（流式/非流式）和 embedding 向量化统一到一个客户端，全部走 vite `/llm` 代理（key 在 Node 侧注入，前端不暴露）。用原生 fetch + ReadableStream 解析 SSE，**摆脱了 @microsoft/fetch-event-source 依赖**。

**SSE 流式解析**——核心是处理网络分片（事件可能被切断在半行）：

```ts
const reader = res.body!.getReader();
const decoder = new TextDecoder();
//SSE事件可能被网络分片切断：半行留在buffer等下一批数据拼完
let buffer = "";
for (;;) {
  const { done, value } = await reader.read();
  if (done) break;
  buffer += decoder.decode(value, { stream: true });
  const lines = buffer.split("\n");
  buffer = lines.pop() ?? ""; // 最后一段可能是半行，留到下一轮
  for (const line of lines) {
    const data = line.replace(/^data:/, "").trim();
    if (!data) continue;
    if (data === "[DONE]") {
      // OpenAI兼容流式的结束标记
      callbacks.onDone();
      return;
    }
    try {
      const payload = JSON.parse(data);
      const delta = payload?.choices?.[0]?.delta?.content;
      if (delta) callbacks.onDelta(delta);
    } catch {
      /* 不完整的JSON行：跳过，等buffer拼齐 */
    }
  }
}
callbacks.onDone();
```

**embedding 批量向量化**——按 index 还原顺序，不依赖接口返回顺序：

```ts
export const embedding = async (input: string[]): Promise<number[][]> => {
  const res = await fetch(EMBED_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ model: "embedding-2", input }),
  });
  if (!res.ok) throw new Error(`embedding接口异常：${res.status}`);
  const json = await res.json();
  const list = (json?.data || []) as { index: number; embedding: number[] }[];
  const out: number[][] = new Array(input.length);
  list.forEach((d) => {
    out[d.index] = d.embedding;
  });
  return out;
};
```

---

## 模块四：RAG 三件套

### 4.1 分块器（`src/rag/chunker.ts`）

**干了什么**：拉全量已发布文章（列表接口不带正文，需逐篇拉详情），按 `<h3>` 小节切块。

```ts
//在前瞻断言处切割，保留<h3>在块内
const sections = html
  .split(/(?=<h3>)/)
  .map((s) => s.trim())
  .filter(Boolean);

return sections
  .map((section, i) => {
    const heading =
      (section.match(/<h3>(.*?)<\/h3>/) || [])[1] || article.title;
    const text = section.replace(/<[^>]+>/g, "").trim(); // 剥离HTML标签
    return {
      id: `${article.id}_${i}`,
      heading,
      text,
      //向量化文本带"分类+文章标题+小节名"上下文前缀，检索更准
      embedText: `【${article.categoryName}】${article.title} - ${heading}\n${text}`,
    };
  })
  .filter((chunk) => chunk.text.length >= 20); // 过滤太短的碎块
```

**为什么要加上下文前缀**：小节正文脱离标题后语义不完整（比如光一句"固定起床时间比固定入睡时间重要"向量检索不一定会关联到"失眠"），前缀让每个块的向量自带主题信息。实测三个典型问题全部精准命中。

### 4.2 向量缓存（`src/rag/vectorStore.ts`）

**干了什么**：向量存 IndexedDB（localStorage 放不下 122 块×1024 维浮点），带版本指纹失效机制。

```ts
//版本指纹 = 文章集合(id+更新时间+标题)，知识库内容变化后自动全量重建
const fingerprint = (articles: any[]) =>
  articles.map((a) => `${a.id}:${a.updatedAt ?? ""}:${a.title}`).join("|");
```

```ts
//批量写入：单事务多次put，整批成功才落定（IndexedDB事务原子性）
export const putChunks = async (chunks: KnowledgeChunk[]) => {
  const db = await openDb();
  return new Promise<void>((resolve, reject) => {
    const tx = db.transaction(STORE_CHUNKS, "readwrite");
    chunks.forEach((chunk) => tx.objectStore(STORE_CHUNKS).put(chunk));
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
};
```

### 4.3 检索器（`src/rag/retriever.ts`）

**干了什么**：构建去重（单飞）→ query 向量化 → 全量余弦相似度 → top-k。

**构建单飞**——多个并发调用共享同一个构建 Promise，不重复建库：

```ts
let building: Promise<KnowledgeChunk[]> | null = null;

export const ensureVectorStore = async (): Promise<KnowledgeChunk[]> => {
  if (building) return building; // 已在构建：共享同一个Promise
  building = (async () => {
    const { articles, chunks } = await buildAllChunks();
    const fp = fingerprint(articles);
    if ((await getMeta("fingerprint")) === fp) {
      const cached = await getAllChunks();
      if (cached.length > 0) return cached; // 缓存命中：零embedding请求
    }
    await clearChunks();
    const BATCH_SIZE = 10; // embedding批量上限内留余量
    for (let i = 0; i < chunks.length; i += BATCH_SIZE) {
      const batch = chunks.slice(i, i + BATCH_SIZE);
      const vectors = await embedding(batch.map((c) => c.embedText));
      batch.forEach((chunk, j) => {
        chunk.embedding = vectors[j];
      });
    }
    await putChunks(chunks);
    await setMeta("fingerprint", fp);
    return chunks;
  })();
  try {
    return await building;
  } finally {
    building = null; // 失败后允许下次重试
  }
};
```

**余弦相似度检索**：

```ts
const cosineSimilarity = (a: number[], b: number[]) => {
  let dot = 0,
    normA = 0,
    normB = 0;
  for (let i = 0; i < a.length; i++) {
    const av = a[i] ?? 0,
      bv = b[i] ?? 0;
    dot += av * bv;
    normA += av * av;
    normB += bv * bv;
  }
  return dot / (Math.sqrt(normA) * Math.sqrt(normB) || 1);
};

export const retrieve = async (query: string, topK = 3) => {
  const chunks = await ensureVectorStore();
  const [queryVector] = await embedding([query]);
  return chunks
    .filter((chunk) => chunk.embedding)
    .map((chunk) => ({
      ...chunk,
      score: cosineSimilarity(queryVector, chunk.embedding!),
    }))
    .sort((a, b) => b.score - a.score)
    .slice(0, topK);
};
```

> **为什么不用向量数据库**：122 块 × 1024 维的全量暴力计算是毫秒级，浏览器端单机场景上 ANN 索引（HNSW 等）是过度设计——面试讲清这个取舍比堆技术名词加分。

**端到端检索质量实测**（35 篇真实文章 → 122 块 → embedding-2）：

```text
「最近总是失眠睡不着怎么办」
  [1] 0.6564 失眠认知行为疗法 · 规则二：睡不着就离开床
  [2] 0.5878 失眠认知行为疗法 · 规则一：固定起床时间
  [3] 0.5696 失眠认知行为疗法 · 规则三：白天不补觉、下午不碰咖啡因

「工作压力太大感觉快撑不住了」
  [1] 0.6241 职场压力管理 · 建立恢复节奏的三个层次
  [2] 0.6216 职业倦怠 · 止损三步

「怎么跟父母沟通他们总管我」
  [1] 0.4479 和家人设立边界 · 边界的正确姿势
  [2] 0.4386 亲密关系中的沟通 · 非暴力沟通四步法
```

---

## 模块五：RAG 接入咨询页

### 5.1 检索 + 注入 Prompt（`Consultation.vue` 的 `startAiResponse`）

```ts
//RAG检索：拿用户最新输入去知识库向量库找相关资料（失败降级为空，对话不受影响）
const lastUserInput =
  [...message.value].reverse().find((m) => Number(m.senderType) === 1)
    ?.content || "";
const references = lastUserInput ? await ragSearch(lastUserInput, 3) : [];

//引用卡片数据挂到AI消息上：回答完成后展示，并随消息一起本地持久化
if (references.length) {
  aiMessage.citations = references.map((r, i) => ({
    index: i + 1,
    articleId: r.articleId,
    articleTitle: r.articleTitle,
    heading: r.heading,
  }));
}

//检索到的资料注入system prompt，要求模型标注来源序号，回答可溯源
const ragContext = references.length
  ? [
      "以下是知识库中与用户问题相关的资料，回答时可参考，并在使用处标注来源序号（如[1][2]）；若资料与问题无关请忽略，不要编造引用：",
      ...references.map(
        (r, i) =>
          `[${i + 1}] 《${r.articleTitle}》—— ${r.heading}\n${r.text.slice(0, 300)}`,
      ),
    ].join("\n\n")
  : "";

await chatCompletionStream(
  [
    {
      role: "system",
      content: [GLM_SYSTEM_PROMPT, ragContext].filter(Boolean).join("\n\n"),
    },
    ...history, // 最近10条对话，保持上下文记忆
  ],
  {
    onDelta: (delta) => {
      fullText += delta; // 进缓冲区，打字机逐帧展示
      if (typewriterRAF === null) playTypewriter();
    },
    onDone: markStreamFinished,
  },
  controller.signal,
);
```

### 5.2 降级封装（`src/composables/useRag.ts`）

```ts
export const useRag = () => {
  const isRetrieving = ref(false);
  const ragError = ref("");

  const search = async (query: string, topK = 3): Promise<RetrievedChunk[]> => {
    isRetrieving.value = true;
    try {
      return await retrieve(query, topK);
    } catch (error) {
      //降级：知识库/向量接口不可用时，退回无引用的纯LLM回答
      ragError.value = "知识库检索不可用";
      return [];
    } finally {
      isRetrieving.value = false;
    }
  };

  return { isRetrieving, ragError, search };
};
```

### 5.3 引用来源卡片（模板）

```html
<!-- RAG引用来源卡片：回答完成后展示参考的知识库文章出处 -->
<div
  v-if="msg.citations?.length && msg.content && !msg.isError"
  class="citations"
>
  <div class="citations-title">📚 参考来源</div>
  <div v-for="c in msg.citations" :key="c.index" class="citation-card">
    <span class="citation-index">[{{ c.index }}]</span>
    <span class="citation-text">{{ c.articleTitle }} · {{ c.heading }}</span>
  </div>
</div>
```

---

## 模块六：LangGraph Agent 服务 + 过程可视化（当天晚间）

### 6.1 干了什么

用 **Python FastAPI + LangGraph** 搭了一个服务端 ReAct Agent（`agent-server/`），LLM 自主决定调用 4 个工具：知识库 RAG 检索（服务端向量化）、情绪分析查询、咨询历史查询、情绪日记写入。后端用 `astream_events` 把 Agent 的执行过程翻译成 SSE 事件流，前端「AI健康管家」页面不只展示回答，还把**每次工具调用渲染成"思考步骤"卡片**——用户能看见 Agent 在查什么、做什么决定。

### 6.2 用户身份透传：ContextVar（`agent-server/tools.py`）

每个请求的 Agent 可能发起多次工具调用，都要以"当前用户"身份访问后端接口。用 `ContextVar` 在请求处理器里写入 token，工具执行时自动读取——async 上下文安全，多用户并发不串号：

```python
# 当前请求的用户token（FastAPI请求处理器写入）
user_token: ContextVar[str] = ContextVar("user_token", default="")

def _headers() -> dict:
    return {"token": user_token.get(), "Content-Type": "application/json"}

@tool
async def get_emotion_analysis() -> str:
    """获取当前用户最近一次AI咨询会话的情绪分析结果……"""
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(
            f"{BACKEND_BASE}/psychological-chat/sessions",
            params={"pageNum": 1, "pageSize": 1},
            headers=_headers(),          # ← token 从请求头一路透传到这里
        )
        ...
```

### 6.3 服务端 RAG 工具（与前端 RAG 同款分块逻辑）

知识库在**服务进程内**构建：拉全量文章 → 按 `<h3>` 分块 → `embedding-2` 批量向量化（10条/批，按 index 还原顺序）→ 内存缓存，余弦 top-k：

```python
@tool
async def search_knowledge(query: str, top_k: int = 3) -> str:
    """在心理健康知识库中检索与问题最相关的文章小节。……"""
    if not _knowledge_base:
        if await _build_knowledge_base() == 0:
            return _reply({"error": "知识库构建失败或为空，请直接凭常识回答"})
    async with httpx.AsyncClient(timeout=30) as client:
        qv = (await _embed_texts([query], client))[0]
    ranked = sorted(
        ((_cosine(qv, c["embedding"]), c) for c in _knowledge_base),
        key=lambda x: x[0], reverse=True,
    )[:top_k]
    return _reply([...])   # JSON字符串，LLM好解析，前端好展示
```

### 6.4 ReAct 循环组装（`agent-server/graph.py`）

GLM 走 OpenAI 兼容协议，换个 `base_url` 就接进 LangChain 生态：

```python
llm = ChatOpenAI(
    model="glm-4-flash-250414",  # 固定版本号：别名排队TTFT抖动0.4~1.8s，固定版稳定200ms级
    base_url="https://open.bigmodel.cn/api/paas/v4",
    api_key=os.getenv("GLM_API_KEY", ""),
    temperature=0.7,
    streaming=True,  # 必须开，否则 astream_events 拿不到 token 级事件
)

agent = create_react_agent(llm, AGENT_TOOLS, prompt=SYSTEM_PROMPT)
```

系统提示词里定义了"什么情况调哪个工具"（专业问题→先检索并注明来源；记录心情→写日记，参数从对话自然提取不反复反问）+ 安全底线（危机信号→热线 400-161-9995，不做诊断）。

### 6.5 SSE 事件协议翻译（`agent-server/main.py`）

`astream_events(version="v2")` 吐出的是 LangGraph 内部事件，翻译成前端能直接消费的 5 种事件：

```python
async for ev in agent.astream_events({"messages": msgs}, version="v2"):
    kind = ev["event"]
    if kind == "on_chat_model_stream":        # → 打字机字流
        delta = ev["data"]["chunk"].content
        if isinstance(delta, list):           # 兼容分块列表返回
            delta = "".join(p.get("text", "") for p in delta if isinstance(p, dict))
        if delta:
            yield _sse({"type": "token", "text": delta})
    elif kind == "on_tool_start":             # → 思考步骤卡片（执行中）
        yield _sse({"type": "tool_start", "name": ev["name"], "args": ev["data"].get("input") or {}})
    elif kind == "on_tool_end":               # → 卡片填入结果
        out = ev["data"].get("output")
        result = getattr(out, "content", out)  # ToolMessage取content本体
        yield _sse({"type": "tool_end", "name": ev["name"], "result": str(result)[:500]})
yield _sse({"type": "done"})
```

### 6.6 前端过程可视化（`src/views/frontend/HealthButler.vue`）

核心数据模型：助手消息不是一坨文本，而是 **segments 数组**——`thought`（工具调用卡片）与 `answer`（字流段落）交替，天然表达 ReAct 的"思考→工具→再思考→回答"：

```ts
const handleSseEvent = (msg: ChatMsg, data: Record<string, unknown>) => {
  const segments = msg.segments ?? (msg.segments = []);
  switch (data.type) {
    case "tool_start":
      segments.push({ kind: "thought", toolName: String(data.name ?? ""),
                      args: (data.args as Record<string, unknown>) ?? {}, running: true });
      break;
    case "tool_end":
      // 关掉最近一个同名且还在执行中的步骤卡片
      for (let i = segments.length - 1; i >= 0; i--) {
        const seg = segments[i];
        if (!seg || seg.kind !== "thought") continue;
        if (seg.running && seg.toolName === data.name) {
          seg.result = String(data.result ?? ""); seg.running = false; break;
        }
      }
      break;
    case "token":
      // 字流永远落在末尾：末尾是思考卡片就新开一段回答
      const last = segments[segments.length - 1];
      if (last?.kind === "answer") last.text += String(data.text ?? "");
      else segments.push({ kind: "answer", text: String(data.text ?? "") });
      break;
  }
};
```

工具名 → 用户可读的步骤标签（`TOOL_META`），SSE 解析复用咨询页同款"buffer 暂存半行 + 按 `\n` 切割"模式；请求带最近 10 轮正文（思考过程不回传，控制上下文成本）。

### 6.7 验证结果

- curl 直连 8000 与经 vite `/agent` 代理两级均通；
- 失眠问题 → Agent 自主调用 `search_knowledge`，命中 CBT-I 三条规则（0.64/0.63/0.60），回答流式输出并注明出处；
- 情绪状态问题 → `get_emotion_analysis` 以登录用户身份调后端拿到真实情绪数据（token 透传链路验证）；
- `npm run type-check` 干净。

### 6.8 面试要点

- **ReAct 是什么**：Reason + Act 循环——LLM 输出"调用哪个工具+参数"→ 执行工具 → 结果回给 LLM → 继续推理，直到能给出最终回答；`create_react_agent` 把这个循环封装成图，工具的 docstring 就是 LLM 的"工具说明书"。
- **为什么 Agent 的 RAG 放服务端**：咨询页 RAG 在浏览器（IndexedDB 缓存、零服务器成本）；Agent 的工具要访问需鉴权的用户数据（情绪分析/日记），必须在服务端，向量库进程内缓存。同一套分块逻辑两处复用。
- **SSE 事件协议设计**：把框架内部事件流翻译成稳定的自定义协议（token/tool_start/tool_end/done/error），前端只依赖协议不依赖框架——换掉 LangGraph 前端零改动。
- **ContextVar vs 全局变量**：async 并发下全局变量会让多用户 token 互相覆盖，ContextVar 绑定上下文，每请求隔离。

---

## 简历亮点（一句话版）

**① LangGraph Agent + 过程可视化（主推）**

> 基于 LangGraph 搭建服务端 ReAct Agent（FastAPI + astream_events 流式）：LLM 自主调度 4 个工具——服务端 RAG 知识检索、情绪分析查询、咨询历史查询、情绪日记写入，用户 token 以 ContextVar 做请求级隔离透传；自定义 SSE 事件协议（token / 工具开始 / 工具结束）驱动前端"思考步骤卡片 + 打字机回答"的过程可视化，Agent 每一步查了什么、做了什么决定全程可见。

**② RAG 检索增强**

> 自研浏览器端 RAG 链路：将知识库文章按语义小节分块后调用 Embedding API 向量化，以 IndexedDB 缓存向量并按内容指纹自动失效，用户提问时余弦相似度取 Top-3 注入 System Prompt，AI 回答附带可溯源的参考来源卡片；实测典型心理问题检索全部精准命中，冷启动仅首次建库约 15 秒，之后毫秒级检索。

**③ 对话本地持久化兜底（体现工程判断）**

> 在后端 AI 服务故障且无消息写入接口的约束下（用 OPTIONS 探测证实路由仅支持 GET），设计前端对话持久化方案：消息按 用户+会话 落 localStorage、temp 会话转正自动迁移、加载历史与服务端数据合并去重，刷新/重进后对话完整恢复，并预留后端恢复后的一行切换点。

**备选小亮点**

> 用原生 fetch 的 ReadableStream 解析 SSE 流式响应并统一封装 LLM 客户端（对话/向量化），摆脱第三方 SSE 库依赖，配合 rAF 缓冲自适应打字机实现平滑流式渲染。

> 编写 30 篇结构化心理科普语料与幂等批量导入脚本（分类映射/标题查重/自动发布），一次导入即产出 122 个可检索知识块，为 RAG 提供真实语料地基。

---

## 今日踩坑速查

| 坑                   | 现象                                      | 解法                               |
| -------------------- | ----------------------------------------- | ---------------------------------- |
| 后端 code 是字符串   | `"200" !== 200` 判断失败                  | `Number(json.code) !== 200`        |
| Windows libuv 断言   | 连接未关时 `process.exit()` 崩溃          | 改 `process.exitCode = 1` 自然退出 |
| "一直繁忙"假象       | stream 秒断 + fetchEventSource 自动重试   | 删除死通道，GLM 直连               |
| 路由存在性判断       | 参数错误和路由不存在返回同一个兜底错误    | `OPTIONS` 看 `Allow` 响应头        |
| 会话 id 三种形态     | 123 / "session_123" / "temp_123" 各存各的 | key 归一化剥前缀                   |
| 小节脱离标题语义不全 | 检索命中率下降                            | embedText 加"分类+标题+小节"前缀   |
| Windows curl 发中文  | FastAPI `UnicodeDecodeError: 0xce`       | 控制台按 GBK 编码 `-d`，改 `--data-binary @utf8文件` |
| astream_events 不出 token | 只看到整段完成事件，前端打字机不动    | `ChatOpenAI(streaming=True)` 必须开 |
| glm-4-flash 首字忽快忽慢 | 同一prompt TTFT 0.4~1.8s 随机 | 别名会漂移，钉死固定版本号 `glm-4-flash-250414`（稳定200ms级） |
| 首字慢误判为RAG拖累 | 实测RAG只占~170ms | 真凶：`await session/start` 阻塞（改并行）+ 模型别名排队（换版本）。定位靠分段埋点，别猜 |
