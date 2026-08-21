# AI心理健康项目 RAG 升级代码对照（服务端架构版）

按时间线梳理本项目 AI 能力的三次演进，核心代码与决策依据对照。2026-08 更新：RAG 已整体迁到服务端（Python FastAPI + Chroma）并部署上线，本文档为当前架构的权威版本。

## 0. 演进时间线（先讲清「为什么变成现在这样」）

| 阶段 | 触发问题 | 方案 | 结果 |
| --- | --- | --- | --- |
| ① 后端 AI 通道 | 课程后端 `/psychological-chat/stream` HTTP 200 后挂死不出数据（"一直繁忙"），且后端无追加消息接口 | OPTIONS 探测证实路由能力 → 删死通道，改浏览器直连 GLM + 前端本地持久化 | 对话可用，消息存浏览器 |
| ② 浏览器端 RAG | 直连模型无专业知识、回答不可溯源 | 前端建 RAG：拉文章 → h3 分块 → embedding 向量化 → IndexedDB 缓存向量 → 余弦 top-3 注入 prompt | 检索精准、带引用卡片；但向量库在每个访客浏览器各建一份（首次 10~30s） |
| ③ 服务端 RAG + Agent（现在） | ②上线即受限：健康管家 Agent 要访问需登录态的用户数据，浏览器做不了；密钥只能藏代理层；向量库无法共享 | RAG 整体迁服务端（五模块 + Chroma），LangGraph Agent 同链路复用；Netlify + Render 双平台部署 | 前端零密钥零 AI 逻辑，咨询页/情绪分析/健康管家全部线上可用 |

**迁移纪律（这是本次重构最重要的工程决策）**：prompt、上下文组装、分块逻辑全部**逐字搬运**，以「迁移前后模型输入不变」为行为基准——线上回答风格零漂移，出问题可以逐字 diff 排查，而不是「重构完回答变味了不知道哪改坏的」。

---

## 1. 语料与批量导入

30 篇结构化心理科普文章（`scripts/seed-articles/articles-{1,2}.json`），带分类与 h3 分节结构，是 RAG 的语料地基。导入走幂等脚本 `scripts/import-articles.mjs`：

```js
//复刻 src/utils/request.ts 的请求约定：token 放请求头，响应体 { code, msg, data }
async function api(path, { method = "GET", body } = {}) {
  const res = await fetch(`${API_BASE}${path}`, {
    method,
    headers: { "Content-Type": "application/json", token: TOKEN },
    body: body ? JSON.stringify(body) : undefined,
  });
  const json = await res.json().catch(() => ({ code: res.status, msg: "响应不是 JSON" }));
  //后端 code 可能是字符串 "200" 或数字 200（原项目 request.ts 也是用 == 宽松比较）
  if (Number(json.code) !== 200) {
    throw new Error(`${method} ${path} → code=${json.code} msg=${json.msg ?? ...}`);
  }
  return json.data;
}

//语料分类 → 后台已有分类的映射（后台分类固定 4 个，无创建接口）
const CATEGORY_MAP = {
  "情绪管理": "情绪管理",
  "压力应对": "压力缓解",
  "人际沟通": "人际关系",
  "睡眠健康": "心理健康基础",
  "自我成长": "心理健康基础",
  "心理科普": "心理健康基础",
};
```

**面试要点**：

- 后端 `code` 字段返回的是**字符串 `"200"`**，脚本用 `Number(json.code) !== 200` 兼容两种形态
- 工程化细节：先拉分类树校验映射（缺分类提前中止）、按标题查重（可安全重跑）、创建后自动发布（status=1）、单篇失败不中断、轻限流（300ms/篇）、`--dry-run` 演练模式
- 服务端架构落地后，同一份语料又复制为 `agent-server/data/*.json` 作为内置种子（见 §4.4）——一份语料，两处消费（后台文章库展示 + 服务端 RAG 入库）

---

## 2. 对话保存问题：诊断与本地持久化

### 2.1 诊断过程（这段"破案"本身就是面试素材）

**现象**：AI 对话一直显示"繁忙"。

**用实验逐层定位**：

```text
实验1  POST /psychological-chat/stream → HTTP 200，120ms 后连接 terminated
       ↳ 所谓"一直繁忙"= 接口秒断，fetchEventSource 在后台自动无限重试的表象

实验2  stream 前后各查一次消息库 → 条数不变
       ↳ stream 挂了连用户消息都不落库（后端设计：它本该负责存后续消息+AI回复）

实验3  OPTIONS /sessions/{id}/messages → Allow: GET,HEAD,OPTIONS（没有POST！）
       对照 OPTIONS /session/start     → Allow: POST,OPTIONS（真实可靠）
       ↳ 后端唯一能写入的接口只有 session/start（仅存首条用户消息）
```

**关键技巧**：`OPTIONS` 请求的 `Allow` 响应头会让路由"自白"支持哪些 HTTP 方法——比猜测参数名/路径可靠得多（参数矩阵试了 10 种全返回同一个兜底"系统错误"，无法区分"参数错"和"路由不存在"）。

### 2.2 本地持久化：IndexedDB 桶模型（`src/utils/localChatHistory.ts`）

后端不可改的约束下，对话消息由前端按 `用户ID+会话ID` 落本地，加载历史时与服务端数据合并。localStorage 方案（同步 IO 卡主线程、~5MB 配额易触顶、只能整串读写）升级为 IndexedDB：

```ts
// 建库：自增主键天然按写入顺序排列，桶键建索引用于按会话查询
req.onupgradeneeded = () => {
  const store = db.createObjectStore(STORE, { keyPath: "seq", autoIncrement: true });
  store.createIndex("bucket", "bucket", { unique: false });
};

// 会话key归一化：同一会话在页面里可能是 123 / "session_123" / "temp_123"，
// 统一去掉前缀，保证不同来源的id寻址到同一个存储桶
const getSessionKey = (sessionId: number | string) =>
  String(sessionId ?? "").replace(/^session_/, "") || "unknown";

// 存储桶键 = 用户id + 会话key，与v1的localStorage键尾同构（迁移零转换）
const bucketKey = (sessionId: number | string) =>
  `${getUserId()}_${getSessionKey(sessionId)}`;
```

```ts
/** 追加一条消息到本地历史（错误提示不入库；存储失败不影响聊天主流程） */
export const saveLocalMessage = async (sessionId, msg: ChatMessage) => {
  if (msg.isError) return;
  try {
    const bucket = bucketKey(sessionId);
    //入参可能是Vue响应式代理（嵌套的citations经get陷阱读出仍是Proxy），
    //Proxy不可结构化克隆，直接add会抛DataCloneError；JSON往返剥成纯对象
    const plainMsg = JSON.parse(JSON.stringify(msg)) as ChatMessage;
    const store = await objectStore("readwrite");
    await reqAsPromise(store.add({ ...plainMsg, bucket }));
    // 桶内超限裁剪：删最早的（seq最小）记录，单会话上限200条
  } catch (error) {
    console.warn("本地会话历史保存失败", error);
  }
};
```

接入点全覆盖五个生命周期：①用户消息上屏落本地（temp 会话先落 temp 桶）→ ②temp 转正时迁移桶 → ③AI 回复流式结束落本地（引用卡片随消息持久化）→ ④加载历史时服务端+本地合并去重 → ⑤删会话同步清理桶。

**面试要点**：

- **DataCloneError 破案**（详见《项目梳理》Q14）：`reactive()` 消息 + 挂 citations + 浅拷贝落库，三者组合导致「只有带引用卡的 AI 回复」落库失败，表象是"新对话随机丢历史"；修复在存储层 JSON 往返剥代理，对所有调用方统一生效
- 方案的诚实边界（主动讲，加分）：跨设备不同步、管理后台看不到、清站点数据会丢——它优化的是**容量与性能**，不是**持久性**
- v1 localStorage 存量自动迁移（键尾同构 + 迁完即删 + 失败保留重试 = 幂等），用户无感

---

## 3. 第一版：浏览器端 RAG（演进记录，已被服务端取代）

> 这一段保留作为演进素材：分块逻辑与检索质量结论**原样活在现在的服务端代码里**（`knowledge_base.py::_chunk_article`），只是运行时从浏览器换到了服务进程。

当时的链路：拉全量已发布文章 → h3 分块（embedText 带「【分类】标题 - 小节」前缀）→ embedding-2 向量化 → 向量存 IndexedDB（带内容指纹失效）→ 用户提问时全量余弦 top-3 → 注入 system prompt。

**分块为什么要加上下文前缀**：小节正文脱离标题后语义不完整（光一句"固定起床时间比固定入睡时间重要"不一定能检索关联到"失眠"），前缀让每个块的向量自带主题信息。

**端到端检索质量实测**（30 篇 → 122 块 → embedding-2，数据至今有效——服务端同一套分块）：

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

**为什么最终迁走（决策记录）**：①健康管家 Agent 的工具要访问需登录态的用户数据（情绪分析/日记），浏览器端做不了，导致核心功能只能"仅本地"；②密钥只能藏在代理层后面，能力与成本受限；③每个访客各自在浏览器建库（首次 10~30 秒、IndexedDB 清了重来）。权衡后放弃浏览器方案（代码保留作回滚路径），全面迁服务端——**技术方案要服从产品形态**，这个取舍本身就是面试好素材。

---

## 4. 服务端 RAG：五模块架构（当前核心）

对应标准 RAG 架构分层（config / knowledge_base / vector_stores / rag），目录 `agent-server/`：

```
data/*.json ──▶ knowledge_base.py ──▶ rag.py(embedding) ──▶ vector_store.py(Chroma)
 种子文章      入库编排(分块/指纹)      智谱 embedding-2        持久化+cosine检索
                                             │
main.py ◀────────────────────────────────────┘
 ├─ POST /rag/chat   咨询页：检索→citations事件→LLM流式（SSE）
 ├─ POST /chat       健康管家：LangGraph ReAct，token/tool_start/tool_end/done/error
 ├─ POST /analyze    情绪分析（非流式，异常返 result=null）
 ├─ POST /kb/rebuild 强制重建知识库（x-admin-token 校验 ADMIN_TOKEN）
 └─ GET  /health     健康检查 + 知识库状态（chunks/building/backend）
```

### 4.1 config.py——配置集中（全部环境变量化）

此前 GLM 地址、模型名、CORS 散落在三个文件硬编码；现在一份清单管本地 `.env` 和 Render 环境变量：

```python
GLM_API_KEY = os.getenv("GLM_API_KEY", "")
GLM_BASE_URL = os.getenv("GLM_BASE_URL", "https://open.bigmodel.cn/api/paas/v4")
CHAT_MODEL = os.getenv("CHAT_MODEL", "glm-4-flash-250414")  # 固定版本号：别名排队抖动大
EMBED_MODEL = os.getenv("EMBED_MODEL", "embedding-2")

CORS_ORIGINS = [o.strip() for o in os.getenv(
    "CORS_ORIGINS", "http://localhost:5173,http://localhost:5174").split(",") if o.strip()]

ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "")   # 空 = 管理端点禁用
CHROMA_DIR = os.getenv("CHROMA_DIR", "./chroma_data")
KB_SEED_DIR = os.getenv("KB_SEED_DIR", "./data")
KB_BACKEND = os.getenv("KB_BACKEND", "chroma")  # chroma | json 回退开关
RAG_TOP_K = int(os.getenv("RAG_TOP_K", "3"))
```

### 4.2 llm.py——ChatOpenAI 工厂

三个用途三个实例，一个构造点，换模型/地址只改环境变量：

```python
def make_llm(temperature: Optional[float] = None, streaming: bool = False) -> ChatOpenAI:
    kwargs = {}
    if temperature is not None:
        kwargs["temperature"] = temperature
    if streaming:
        kwargs["streaming"] = True   # astream_events 拿 token 级事件必须开
    return ChatOpenAI(model=CHAT_MODEL, base_url=GLM_BASE_URL, api_key=GLM_API_KEY, **kwargs)

rag_llm = make_llm()                        # 咨询页：不传温度（对齐前端直连现行为）
analyze_llm = make_llm(temperature=0.2)     # 情绪分析：要稳定的结构化 JSON
agent_llm = make_llm(temperature=0.7, streaming=True)  # ReAct：对流式事件敏感
```

### 4.3 vector_store.py——VectorStore 接口 + 双后端

业务层只依赖 Protocol 接口，chromadb 出问题时零改动降级：

```python
class VectorStore(Protocol):
    backend_name: str
    def count(self) -> int: ...
    def upsert(self, ids, vectors, metadatas, documents) -> None: ...
    def query(self, vector: list[float], top_k: int) -> list[dict]: ...
    def clear(self) -> None: ...
    def fingerprint(self) -> Optional[str]: ...
    def set_fingerprint(self, fp: str) -> None: ...
```

Chroma 主后端的关键细节：

```python
class ChromaStore:
    def __init__(self):
        import chromadb  # 延迟导入：回退模式下不占内存
        from chromadb.config import Settings
        self._client = chromadb.PersistentClient(
            path=config.CHROMA_DIR,
            settings=Settings(anonymized_telemetry=False),  # 关遥测省一次外呼
        )
        self._col = self._client.get_or_create_collection(
            name=COLLECTION,
            metadata={"hnsw:space": "cosine"},  # 距离空间创建时固化
        )

    def query(self, vector, top_k) -> list[dict]:
        res = self._col.query(
            query_embeddings=[vector],
            n_results=min(top_k, self._col.count()),
            include=["metadatas", "documents", "distances"],
        )
        out = []
        # chroma 按入参维度返回嵌套列表（只查一条，取第一层）
        for cid, meta, doc, dist in zip(
            res["ids"][0], res["metadatas"][0], res["documents"][0], res["distances"][0]
        ):
            out.append({
                "id": cid, "articleId": meta.get("articleId", ""),
                "articleTitle": meta.get("articleTitle", ""),
                "heading": meta.get("heading", ""),
                "text": doc or "",
                "score": round(1 - dist, 4),  # cosine distance=1-相似度，换算回统一语义
            })
        return out

    def set_fingerprint(self, fp: str) -> None:
        # chroma 1.5+ 禁止 modify 时携带 hnsw:space（即使值没变也算"改距离函数"报错）；
        # 只传 fingerprint——距离函数创建时已固化，metadata 里丢掉不影响检索
        self._col.modify(metadata={"fingerprint": fp})
```

JsonStore 回退后端：`vectors.json` 落盘 + 纯 Python 余弦暴力检索（语料百来块，毫秒级，检索质量与 ANN 无差别）。单例工厂决定用哪个：

```python
def get_vector_store() -> VectorStore:
    """优先 chroma；KB_BACKEND=json 显式回退，或 chromadb 装不上/初始化失败自动降级"""
    global _store
    if _store is not None:
        return _store
    if config.KB_BACKEND == "chroma":
        try:
            _store = ChromaStore()
            return _store
        except Exception as e:  # 降级不能炸启动，只打日志
            print(f"[向量库] chromadb 初始化失败，降级 json 后端：{e}")
    _store = JsonStore()
    return _store
```

### 4.4 knowledge_base.py——入库编排

三个入口：启动自动判空灌库（lifespan）、改数据后指纹失配自动重建、管理端点手动重建。

**为什么用内置种子而不再拉后端文章**：①后端文章库会被同学清掉（发生过），内置源不依赖外部存活；②后端接口要用户 token，服务启动时没有可用身份。种子生成稳定 id，保证重启重建后已持久化的引用卡片 articleId 不漂移：

```python
# 种子文件没有 id 字段，用 seed:{文件名}:{序号} 生成稳定 id：
# 重启/重建后引用卡片里持久化的 articleId 不会漂移
articles.append({
    "id": f"seed:{stem}:{i}",
    "title": str(a.get("title") or ""),
    "categoryName": str(a.get("category") or ""),
    "content": str(a.get("content") or ""),
})
```

**分块**（逻辑与浏览器时代逐字一致）：

```python
def _chunk_article(article: dict) -> list[dict]:
    """<h3> 小节是天然语义边界；纯文本不足20字的碎块丢弃；
    向量化文本带 【分类】标题 - 小节 前缀提升检索命中率。"""
    chunks = []
    for sec in filter(None, (s.strip() for s in re.split(r"(?=<h3>)", html))):
        m = re.search(r"<h3>(.*?)</h3>", sec)
        heading = m.group(1) if m else title
        text = re.sub(r"<[^>]+>", "", sec).strip()
        if len(text) < 20:
            continue
        chunks.append({
            "id": f"{article['id']}_{len(chunks)}",   # 与前端 KnowledgeChunk.id 同构
            ...
            "embed_text": f"【{category}】{title} - {heading}\n{text}",
        })
    return chunks
```

**就绪入口：指纹 + 单飞 + shield + 锁**，四层并发防护：

```python
async def ensure_built() -> int:
    """指纹匹配且非空直接返回；否则触发单飞构建并等待。"""
    global _build_task
    store = get_vector_store()
    fp = _seed_fingerprint()          # 全部种子文件内容的 sha256
    if store.count() > 0 and store.fingerprint() == fp:
        return store.count()          # 指纹命中：零 embedding 请求
    if _build_task is None or _build_task.done():
        _build_task = asyncio.create_task(_do_build())
    # shield：某个等待方被取消（如 /rag/chat 的3s软超时）不能连带取消构建本身
    return await asyncio.shield(_build_task)

async def _do_build() -> int:
    async with _build_lock:           # 与 rebuild 并发时串行，避免交叉写库
        # 拿到锁后再查一次：可能别人已经建完
        if store.count() > 0 and store.fingerprint() == fp:
            return store.count()
        return await _ingest(store)   # 清库→分块→分批向量化→upsert→记指纹
```

为什么每层都要：并发调用 `ensure_built` 共享同一个 Task（单飞，不重复建库）；等待方超时被取消不能杀掉构建（shield，别的请求还在等）；`rebuild` 强制重建与常规构建要串行（锁，防交叉写脏数据）。

### 4.5 rag.py——向量化 + 检索 + prompt

措辞纪律的落点：咨询页 system prompt 与上下文组装从前端**逐字迁移**（迁移前后模型输入一致 = 行为基准）：

```python
# 咨询页人设（原 Consultation.vue 的 GLM_SYSTEM_PROMPT，逐字迁移）
RAG_CHAT_SYSTEM_PROMPT = "\n".join([
    "你是Junnnneal AI助手，一位温暖、专业的心理健康陪伴助手。",
    "请先用温和共情的语气回应对方的情绪，再给出具体、可操作的建议；回复保持简洁，一般不超过300字。",
    "如果用户表现出明显的自伤或危机倾向，请优先建议拨打心理援助热线（如希望24热线400-161-9995）或联系信任的人。",
])

def build_rag_context(citations: list[dict]) -> str:
    """检索结果注入 system prompt（原前端 ragContext 组装，逐字复刻）。正文截300字。"""
    if not citations:
        return ""
    return "\n\n".join(
        ["以下是知识库中与用户问题相关的资料，回答时自然地参考；与问题无关的请忽略，不要在回答里标注来源序号（如[1][2]）：",
         *[f"[{i + 1}] 《{c['articleTitle']}》—— {c['heading']}\n{c['text'][:300]}"
           for i, c in enumerate(citations)]])
```

检索永不抛异常——检索失败 ≠ 对话失败：

```python
async def retrieve(query: str, top_k: int | None = None) -> list[dict]:
    """任何失败都返回 []（调用方降级为无引用对话），检索绝不能拖垮聊天主链路。"""
    query = (query or "").strip()
    if not query:
        return []
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            qv = (await embed_texts([query], client))[0]
        if not qv:
            return []
        results = get_vector_store().query(qv, top_k or config.RAG_TOP_K)
    except Exception as e:
        print(f"[RAG] 检索失败，本条消息降级为无引用：{e}")
        return []
    for i, item in enumerate(results):
        item["index"] = i + 1
    return results
```

---

## 5. 接口层：main.py

### 5.1 lifespan 启动预热

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(_warmup_kb())   # 后台灌库，不阻塞服务就绪
    yield
    task.cancel()
```

启动即后台灌库（指纹命中时跳过）；失败只打日志，首次检索时自动重试。Render 重启（ephemeral 磁盘被清）后靠它分钟内恢复向量库。

### 5.2 POST /rag/chat——SSE 契约

| 事件 | 载荷 | 时机 |
| --- | --- | --- |
| `citations` | `{"type":"citations","citations":[{index,articleId,articleTitle,heading,score}]}` | **首事件**，检索后 LLM 开流前；无命中整帧省略 |
| `token` | `{"type":"token","text":"…"}` | `rag_llm.astream()` 每个 delta |
| `done` / `error` | 同 /chat | 结束/任何异常不断流 |

```python
async def event_stream():
    try:
        # 知识库就绪等待3s软超时：冷启动撞上灌库时降级为无引用回答，绝不拖首字
        try:
            await asyncio.wait_for(knowledge_base.ensure_built(), timeout=3)
        except Exception:
            print("[RAG] 知识库3秒内未就绪，本条消息降级为无引用对话")

        citations = await rag.retrieve(message)
        if citations:
            # 引用卡片数据前置下发：回答还没开始就能渲染来源
            yield _sse({"type": "citations", "citations": [...]})

        system_content = "\n\n".join(
            x for x in [rag.RAG_CHAT_SYSTEM_PROMPT, rag.build_rag_context(citations)] if x)
        msgs = [SystemMessage(content=system_content), *_history_messages(history, message)]

        async for chunk in rag_llm.astream(msgs):
            delta = _content_text(chunk.content)
            if delta:
                yield _sse({"type": "token", "text": delta})
        yield _sse({"type": "done"})
    except Exception as e:  # SSE 里任何异常都要吐给前端而不是断流
        yield _sse({"type": "error", "message": f"RAG 对话出错：{e}"})
```

设计点：①citations 前置——用户在模型出字前就能看到「参考来源」卡片，感知等待变短；②不走 ReAct 图（咨询页要稳定低延迟，检索一次注入即可），Agent 那套多轮工具循环留给健康管家；③不需要用户 token。

### 5.3 POST /analyze——情绪分析（逐字迁移自前端 useEmotionAnalysis）

system prompt 要求只输出一个 JSON 对象；每条消息截 500 字（分析看情绪倾向不需要全文，控 token 与耗时）；宽松解析取第一个 `{` 到最后一个 `}` 兜底；**任何内部异常返回 `{"result": null}` 不抛 5xx**——情绪面板缺一轮数据无伤大雅：

```python
raw = await analyze_llm.ainvoke([
    SystemMessage(content=ANALYZE_SYSTEM_PROMPT),
    HumanMessage(content=f"对话记录：\n{transcript}"),
])
return {"result": _parse_json_loose(_content_text(raw.content))}
```

### 5.4 管理与健康检查

```python
@app.post("/kb/rebuild")
async def kb_rebuild(request: Request):
    """管理令牌未配置或校验不过一律403。"""
    if not config.ADMIN_TOKEN:
        return JSONResponse({"error": "ADMIN_TOKEN 未配置，端点禁用"}, status_code=403)
    token = request.headers.get("x-admin-token") or ""
    if not secrets.compare_digest(token, config.ADMIN_TOKEN):  # 恒定时间比较防时序侧信道
        return JSONResponse({"error": "管理令牌错误"}, status_code=403)
    asyncio.create_task(_bg())   # 后台执行，立即返回
    return {"started": True}

@app.get("/health")  # 保活 ping 也打这里
async def health():
    return {"status": "ok",
            "kb": {"chunks": ..., "building": ..., "backend": get_vector_store().backend_name}}
```

---

## 6. LangGraph Agent：AI健康管家

### 6.1 ReAct 组装（graph.py）

GLM 走 OpenAI 兼容协议，换个 `base_url` 接进 LangChain 生态：

```python
agent_llm = make_llm(temperature=0.7, streaming=True)  # 必须开，否则 astream_events 拿不到 token 级事件

agent = create_react_agent(agent_llm, AGENT_TOOLS, prompt=SYSTEM_PROMPT)
```

系统提示词定义「什么情况调哪个工具」（专业问题→先检索并注明来源；记心情→写日记，参数自然提取不反复反问）+ 安全底线（危机信号→热线 400-161-9995，不做诊断）。

### 6.2 工具层（tools.py）：ContextVar 透传 + RAG 新链路

每个请求的 Agent 可能发起多次工具调用，都要以"当前用户"身份访问后端。`ContextVar` 在请求处理器写入 token、工具执行时自动读取——async 上下文安全，多用户并发不串号：

```python
user_token: ContextVar[str] = ContextVar("user_token", default="")

@tool
async def get_emotion_analysis() -> str:
    """获取当前用户最近一次AI咨询会话的情绪分析结果……"""
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(f"{BACKEND_BASE}/psychological-chat/sessions",
                             params={"pageNum": 1, "pageSize": 1},
                             headers=_headers())   # ← token 从请求头一路透传到这里
```

`search_knowledge` 改走新链路，返回结构与拆分前完全一致（Agent 解析行为零变化）：

```python
@tool
async def search_knowledge(query: str, top_k: int = 3) -> str:
    """在心理健康知识库中检索与问题最相关的文章小节。……"""
    try:
        await knowledge_base.ensure_built()   # 通常启动时后台已灌完，这里兜底
    except Exception as e:
        return _reply({"error": f"知识库暂不可用：{e}，请直接凭常识回答"})
    results = await rag.retrieve(query, top_k)
    if not results:
        return _reply({"info": "知识库中没有检索到相关内容，请直接凭常识回答"})
    return _reply([{"title": c["articleTitle"], "heading": c["heading"],
                    "summary": c["text"][:200], "score": c["score"]} for c in results])
```

另两个工具：`get_recent_sessions`（咨询历史列表）、`save_emotion_diary`（写情绪日记，参数从对话自然提取）。工具返回统一 JSON 字符串——LLM 好解析，前端好展示；`_json()` 安全解析后端响应，token 过期返回空体也不炸整条 SSE 流。

### 6.3 SSE 事件协议翻译（main.py /chat）

`astream_events(version="v2")` 吐出的是 LangGraph 内部事件，翻译成前端能直接消费的 5 种事件（代码见《项目梳理》亮点十）。**前端只依赖协议不依赖框架**——换掉 LangGraph 前端零改动。

### 6.4 前端过程可视化（HealthButler.vue）

助手消息是 **segments 数组**——`thought`（工具调用卡片）与 `answer`（字流段落）交替，天然表达 ReAct 的「思考→工具→再思考→回答」；`tool_end` 从后往前找最近一个同名且 running 的卡片回填结果；工具名经 `TOOL_META` 映射成用户可读的步骤标签（🔍 检索心理健康知识库 / 📊 分析最近的咨询情绪…）。

---

## 7. 前端切换：零差异接进服务端

### 7.1 src/apis/agent.ts——统一客户端

```ts
export const ragChatStream = async (
  payload: AgentChatPayload,
  callbacks: { onCitations; onDelta; onDone },
  signal?: AbortSignal,
) => {
  const res = await fetch("/agent/rag/chat", { method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload), signal });
  ...
  // 原生流式解析SSE：buffer暂存半行，按\n切割逐条处理（与 HealthButler.vue 同款）
  for (const line of lines) {
    if (data.type === "citations") callbacks.onCitations(data.citations ?? []);
    else if (data.type === "token") callbacks.onDelta(String(data.text ?? ""));
    else if (data.type === "done") { callbacks.onDone(); return; }
    else if (data.type === "error") throw new Error(String(data.message ?? "RAG 对话出错"));
  }
};
```

`/agent` 路径的妙处：开发环境 vite 代理转发 localhost:8000，生产环境 Netlify 函数转发 Render——**前端代码零差异**。

### 7.2 Consultation.vue 接线

前端删掉了整个浏览器 RAG（检索、降级预算、prompt 组装、embedding 调用），`startAiResponse` 收敛为：组 history → `ragChatStream` → citations 挂消息、delta 进打字机缓冲。rAF 打字机、TEMP 会话转正、本地持久化、情绪刷新全部不动。

```ts
//携带最近10条对话作为上下文（刚发出的这条单独走 message 字段，不重复进history）
const history = message.value
  .filter((msg) => !msg.isError && msg.content)
  .slice(0, -1)
  .slice(-10)
  .map(...);

await ragChatStream(
  { message: lastUserInput, history },
  {
    onCitations: (citations) => {
      //引用卡片数据挂到AI消息上：回答完成后展示，并随消息一起本地持久化
      aiMessage.citations = citations.map(...);
    },
    onDelta: (delta) => { fullText += delta; if (typewriterRAF === null) playTypewriter(); },
    onDone: markStreamFinished,
  },
  controller.signal,
);
```

### 7.3 useEmotionAnalysis 薄化

签名不变（全项目唯一引用方零改动），内部换 `analyzeEmotionRemote`；system prompt、500 字截断、宽松解析都在服务端 main.py。

---

## 8. 部署上线：Netlify + Render 双平台

### 8.1 架构

```
浏览器（https://ai-mental.netlify.app）
 ├─ 静态资源 ──────────── Netlify CDN
 ├─ /api/*   ──redirect──▶ 课程后端 159.75.169.224:1235
 ├─ /llm/*   ──llm.mjs───▶ 智谱 GLM（保留作回滚路径）
 └─ /agent/* ──agent.mjs─▶ Render（AGENT_URL 环境变量）
                           └─ FastAPI + Chroma + GLM 密钥全在这层
```

本地开发：vite 把 `/agent` 代理到 localhost:8000——与生产同路径。

### 8.2 Render 配置（免费版）

- Root Directory `agent-server`；Build `pip install -r requirements.txt`；Start `uvicorn main:app --host 0.0.0.0 --port $PORT`
- 环境变量：`PYTHON_VERSION=3.13.4`、`GLM_API_KEY`、`BACKEND_BASE`、`CORS_ORIGINS`、`ADMIN_TOKEN`
- 免费层约束与对策：15 分钟无流量休眠→UptimeRobot 每 10 分钟 ping `/health`；磁盘 ephemeral→lifespan 指纹自动重建；512MB 内存紧→`KB_BACKEND=json` 回退

### 8.3 netlify/functions/agent.mjs——代理与护栏

```js
export default async (req) => {
  const upstreamBase = process.env.AGENT_URL;   // 未配置直接 500 明确报错
  ...
  // Origin只在存在时校验：浏览器请求必带且不可伪造；非浏览器客户端由服务端鉴权兜底
  const origin = req.headers.get("origin");
  const ownOrigins = [process.env.URL, process.env.DEPLOY_PRIME_URL].filter(Boolean);
  if (origin && ownOrigins.length > 0 && !ownOrigins.includes(origin)) {
    return jsonError(403, "跨站调用被拒绝");
  }
  // 请求体上限 256KB；请求头白名单：content-type/accept/token/authorization/x-admin-token

  const upstream = await fetch(`${upstreamBase}/${sub}${search}`, { method, headers, body });
  // SSE 流式透传：响应体不解析直接返回，打字机/思考卡片体验与本地一致
  return new Response(upstream.body, { status: upstream.status, headers: {...} });
};

export const config = { path: "/agent/:path*" };  // 函数内声明路由，netlify.toml 不用改
```

**Netlify Functions 踩坑（生产 /llm 404 的教训）**：函数入口文件必须**平铺在 functions/ 目录**（或子目录内叫 index.mjs），Next.js 风格的 `llm/[[path]].mjs` 会被打包器直接无视；且设了自定义 `config.path` 后默认地址 `/.netlify/functions/xxx` 失效，netlify.toml 里不能再配同名 redirect（会重写向死地址）。

**流式边界**：Netlify 函数流式响应上限 60s——`/rag/chat` 5~15s 安全；`/chat`（ReAct 多轮工具）最坏贴近上限，超时表现为流提前结束而非报错（已有 300 字约束 + 结果截断缓解）。

### 8.4 上线验证（全链路 curl 实测）

- Render 直连：`/health` 返回 chroma 后端 122 块；`/rag/chat` SSE citations→token→done；`/analyze` 返回情绪 JSON；`/kb/rebuild` 错 token 403 / 对 token `{"started":true}`
- 经 Netlify：`/agent/health` 透传正常；`/agent/rag/chat` 带 Origin 请求出完整 SSE 流；恶意 Origin 403；静态首页正常
- 本地↔生产行为一致（同 prompt 同分块，迁移基准达成）

---

## 9. 简历亮点（一句话版）

**① 服务端 RAG + LangGraph Agent 全链路（主推）**

> 独立完成 AI 能力服务端化：FastAPI 五模块架构（config / llm 工厂 / knowledge_base 入库编排 / Chroma 向量库 / rag 检索），知识库 30 篇文章按 h3 语义分块（122 块）经 embedding-2 向量化入 Chroma（cosine），sha256 语料指纹增量重建 + 单飞任务 + asyncio.shield 防并发重复构建与误取消；咨询页 RAG 检索 top-3 注入 prompt（SSE citations 前置下发 + 流式打字机 + 引用溯源卡片），LangGraph ReAct Agent 自主调度 4 个工具（RAG 检索/情绪分析/历史查询/日记写入），token 以 ContextVar 请求级隔离透传，工具调用过程前端可视化；迁移以「模型输入逐字不变」为行为基准，线上回答风格零漂移。

**② 双平台部署与免费资源治理**

> 设计 Netlify（静态站 + 边缘函数代理：Origin 校验、请求头白名单、256KB 上限、SSE 流式透传）+ Render（FastAPI + Chroma，密钥全部环境变量）双平台架构，前端零密钥零 CORS；针对免费层限制实现 UptimeRobot 保活、磁盘 ephemeral 指纹自动重建、内存回退双后端（VectorStore Protocol + 纯 Python 余弦），前端本地/生产共用 /agent 路径实现环境零差异。

**③ 对话本地持久化兜底（体现工程判断）**

> 在后端 AI 服务故障且无消息写入接口的约束下（用 OPTIONS 探测证实路由仅支持 GET），设计 IndexedDB 存储层：用户+会话桶键索引隔离、自增主键保序、200 条自动裁剪、localStorage 存量幂等迁移、隐私模式降级；定位并修复 reactive 代理不可结构化克隆导致的 DataCloneError「随机丢历史」问题。

**备选小亮点**

> 原生 fetch 的 ReadableStream 解析 SSE（半行缓冲防网络分片）+ rAF 打字机按积压量自适应出字速度（含代理对完整切割），摆脱第三方 SSE 库依赖。

> 编写 30 篇结构化心理科普语料与幂等批量导入脚本（分类映射/标题查重/自动发布/dry-run），一份语料两处消费（后台展示 + RAG 入库）。

---

## 10. 今日踩坑速查

| 坑 | 现象 | 解法 |
| --- | --- | --- |
| 后端 code 是字符串 | `"200" !== 200` 判断失败 | `Number(json.code) !== 200` |
| "一直繁忙"假象 | stream 秒断 + fetchEventSource 自动重试 | OPTIONS 看 `Allow` 头证实，删死通道 |
| 会话 id 三种形态 | 123 / "session_123" / "temp_123" 各存各的 | key 归一化剥前缀 |
| 小节脱离标题语义不全 | 检索命中率下降 | embedText 加「分类+标题+小节」前缀 |
| glm-4-flash 首字忽快忽慢 | 同一 prompt TTFT 0.4~1.8s 随机 | 别名会漂移，钉死 `glm-4-flash-250414` |
| 首字慢误判为 RAG 拖累 | 实测 RAG 只占 ~170ms | 真凶：`await session/start` 阻塞（改并行）+ 别名排队。定位靠分段埋点，别猜 |
| astream_events 不出 token | 只看到整段完成事件，打字机不动 | `ChatOpenAI(streaming=True)` 必须开 |
| Windows curl 发中文 | FastAPI `UnicodeDecodeError: 0xce` | 控制台按 GBK 编码 `-d`，改 `--data-binary @utf8文件` |
| Py3.13 装 chromadb | 旧版 chroma-hnswlib 编译失败 | 钉 `chromadb>=1.1,<2`（Rust 内核才有 wheel） |
| chroma modify 带 hnsw:space | ValueError "Changing the distance function"（值没变也报） | modify 只传 fingerprint；距离函数创建时已固化 |
| chroma 拒绝空 metadata | upsert 报 "Expected metadata to be a non-empty dict" | 每条 metadata 必须非空 |
| 端口 8000 被旧进程占 | 新代码 404 / 返回旧行为 | netstat 查 PID → taskkill，再起服务 |
| Netlify 函数不生效 | 自定义目录结构被无视，/llm 404 | 入口平铺 functions/ 目录；`config.path` 函数内声明；netlify.toml 不配同名 redirect |
| SSE 经代理卡成整段 | 缓冲导致打字机不动 | agent.mjs 流式透传不落地；服务端 `X-Accel-Buffering: no` |
| Netlify 函数 60s 上限 | 长回复流提前结束（非报错） | /rag/chat 5~15s 安全；/chat ReAct 最坏贴近，加 300 字约束与截断 |
| Windows libuv 断言 | 连接未关时 `process.exit()` 崩溃 | 改 `process.exitCode = 1` 自然退出 |
