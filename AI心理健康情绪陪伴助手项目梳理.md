# AI心理健康情绪陪伴助手项目梳理

## 1. 项目介绍与技术栈

### 项目介绍

AI心理健康情绪陪伴助手是一个「Vue3 前端 + Python 服务端」的心理健康平台：前台面向用户提供 AI 心理咨询（服务端 RAG 检索增强 + 流式打字机 + 引用溯源）、AI 健康管家（LangGraph ReAct Agent，工具调用过程可视化）、情绪日记和情绪花园；后台面向管理员提供数据看板、咨询记录、情绪日志和知识文章管理。

项目已上线：前端与代理层部署在 Netlify（https://ai-mental.netlify.app），AI 服务（RAG + Agent）部署在 Render（Python FastAPI + Chroma 向量库），所有密钥只存在平台环境变量，前端零密钥、零 AI 逻辑。

### 技术栈

- 前端框架：Vue3、Composition API、TypeScript
- 构建工具：Vite
- 路由与状态：Vue Router、Pinia
- UI 组件库：Element Plus、@element-plus/icons-vue
- 网络请求：Axios、原生 fetch（SSE 流式解析）
- AI 服务端：Python 3.13、FastAPI、LangGraph、LangChain、ChromaDB、httpx、uvicorn
- AI 能力：智谱 GLM-4-Flash（对话）、embedding-2（向量化）、RAG 检索增强、ReAct Agent
- 数据可视化：ECharts
- 内容编辑与渲染：wangEditor、Markdown/HTML 渲染
- 本地存储：IndexedDB（会话历史）、localStorage（登录态）
- 部署：Netlify（静态站 + Functions 代理）、Render（FastAPI 服务）
- 样式方案：SCSS、响应式布局
- 工程化：vue-tsc 类型检查、pip 钉版本依赖

## 2. 项目亮点与核心代码

### 亮点一：SSE 流式渲染全链路——原生 fetch 解析 + rAF 自适应打字机 + 引用前置

咨询页对话走服务端 RAG（`/agent/rag/chat`，SSE 协议：`citations → token → done`）。前端用原生 fetch 的 ReadableStream 解析 SSE（不依赖第三方 SSE 库），字流先进缓冲区，再由 requestAnimationFrame 打字机按「基础速度 + 积压自适应」逐帧上屏；检索结果由服务端作为**首事件**前置下发，回答还没开始引用卡片就能渲染。

核心代码来源：`src/views/frontend/Consultation.vue`、`src/apis/agent.ts`

```ts
// ragChatStream 内的 SSE 解析：buffer 暂存半行，按 \n 切割逐条处理
// （网络分片可能把一条 SSE 事件切成两半，半行留到下一批数据拼完）
const reader = res.body.getReader();
const decoder = new TextDecoder();
let buffer = "";
for (;;) {
  const { done, value } = await reader.read();
  if (done) break;
  buffer += decoder.decode(value, { stream: true });
  const lines = buffer.split("\n");
  buffer = lines.pop() ?? ""; // 最后一段可能是半行，留到下一轮
  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed.startsWith("data:")) continue;
    const data = JSON.parse(trimmed.slice(5).trim());
    if (data.type === "citations") callbacks.onCitations(data.citations ?? []);
    else if (data.type === "token") callbacks.onDelta(String(data.text ?? ""));
    else if (data.type === "done") { callbacks.onDone(); return; }
  }
}
```

```ts
// 打字机循环：每帧从缓冲区取一小段字符追加显示，速度随积压量自适应
const playTypewriter = () => {
  typewriterRAF = requestAnimationFrame(() => {
    typewriterRAF = null;
    const backlog = fullText.length - shownCount;
    if (backlog > 0) {
      // 基础速度保证平滑；积压越多追得越快，约 TYPEWRITER_CATCHUP_FRAMES 帧内追平
      const speed = Math.max(
        TYPEWRITER_BASE_SPEED,
        Math.ceil(backlog / TYPEWRITER_CATCHUP_FRAMES),
      );
      shownCount = Math.min(fullText.length, shownCount + speed);
      // 刚好切在 emoji 等代理对中间时多带一个字符，避免出现乱码
      if (
        shownCount < fullText.length &&
        fullText.charCodeAt(shownCount) >= 0xdc00 &&
        fullText.charCodeAt(shownCount) <= 0xdfff
      ) {
        shownCount++;
      }
      aiMessage.content = fullText.slice(0, shownCount);
    }
    if (shownCount < fullText.length) {
      playTypewriter();
    } else if (streamFinished) {
      finishStream();
    }
    // 缓冲区暂时播完且流未结束：先停下，等下一批 SSE 数据到达后再重启
  });
};
```

可以写进简历的表达：

- 实现 AI 回复流式渲染全链路：原生 fetch 解析 SSE（半行缓冲拼接防网络分片）、rAF 打字机按积压量自适应出字速度（含代理对完整切割）、done 后等缓冲播完再收尾，配合服务端 citations 首事件前置，实现「引用卡片先出、回答逐字流出」的实时对话体验。

### 亮点二：会话情绪分析数据归一化，增强接口兼容性

情绪分析结果来自 LLM 结构化输出，字段可能存在不同命名方式，项目中对 `emotionScore / score / intensity`、`primaryEmotion / emotion / emotionName` 等字段做统一归一化，同时增加默认值、分数边界裁剪和风险等级兜底，避免字段变化导致前端页面崩溃。

核心代码来源：`src/views/frontend/Consultation.vue`

```ts
const normalizeScore = (score: unknown) => {
  const value = Number(score);
  if (Number.isNaN(value)) return 50;
  return Math.min(100, Math.max(0, Math.round(value)));
};

const normalizeEmotionGarden = (data: any): EmotionGarden => {
  const source = data?.data || data || {};
  const emotionScore = normalizeScore(
    source.emotionScore ?? source.score ?? source.intensity,
  );
  const primaryEmotion =
    source.primaryEmotion || source.emotion || source.emotionName || "中性";
  const isNegative =
    Boolean(source.isNegative) ||
    ["焦虑", "悲伤", "愤怒", "恐惧", "压力", "低落"].some((name) =>
      String(primaryEmotion).includes(name),
    );

  return {
    primaryEmotion,
    emotionScore,
    isNegative,
    summary: source.summary || source.analysis || `当前主要情绪为 ${primaryEmotion}`,
    suggestion: source.suggestion || source.advice || "建议先记录情绪触发因素",
    riskLevel: source.riskLevel || source.risk || "low",
    actionItems: source.actionItems || source.actions || source.suggestions || [],
  };
};
```

可以写进简历的表达：

- 封装情绪分析结果归一化逻辑，对接口字段差异、异常分数、空数据和风险等级进行兜底处理，提升 AI 情绪面板在异常数据下的稳定性。

### 亮点三：Axios 二次封装，统一 Token 注入与登录过期处理

项目统一封装请求实例，自动携带 token，并在响应拦截器中统一拆包业务数据、处理登录过期、清理本地身份信息并跳转登录页，减少页面内重复判断。

核心代码来源：`src/utils/request.ts`

```ts
const instance = axios.create({
  baseURL: "/api",
  timeout: 5000,
});

instance.interceptors.request.use((config) => {
  const token = localStorage.getItem("token");
  if (token) {
    config.headers["token"] = token;
  }
  return config;
});

instance.interceptors.response.use((response) => {
  const { data, config } = response;
  if (data.code == 200) {
    return data.data;
  }
  if (data.code == -1) {
    if (!config.url?.includes("/login")) {
      localStorage.removeItem("token");
      localStorage.removeItem("userInfo");
      router.push("/auth/login");
    }
    return Promise.reject(data.msg || "登录过期");
  }
  return Promise.reject(data.msg || "网络请求失败");
});

const request = <T = any>(config: AxiosRequestConfig): Promise<T> => {
  return instance(config) as Promise<T>;
};
```

可以写进简历的表达：

- 基于 Axios 拦截器封装统一请求层，实现 Token 自动注入、业务数据拆包、登录失效重定向和泛型响应类型约束，降低接口调用重复代码。

### 亮点四：前后台路由拆分与角色访问控制

路由中将前台、后台、登录注册页面拆成不同 Layout，并使用动态导入实现路由级懒加载。前置守卫根据 token 和 `userType` 控制访问范围，防止普通用户进入后台、管理员误入前台。

核心代码来源：`src/router/index.ts`

```ts
const routes: RouteRecordRaw[] = [
  {
    path: "/back",
    component: () => import("@/components/layouts/BackendLayout.vue"),
    children: [
      { path: "dashboard", component: () => import("@/views/backend/DashBoard.vue") },
      { path: "knowledge", component: () => import("@/views/backend/Knowledge.vue") },
    ],
  },
  {
    path: "/",
    component: () => import("@/components/layouts/FrontendLayout.vue"),
    children: [
      { path: "", component: () => import("@/views/frontend/Home.vue") },
      { path: "consultation", component: () => import("@/views/frontend/Consultation.vue") },
    ],
  },
];

router.beforeEach((to, from, next) => {
  const token = localStorage.getItem("token");
  const userInfo = JSON.parse(localStorage.getItem("userInfo") || "{}");

  if (!token && to.path.startsWith("/back")) {
    next("/auth/login");
    return;
  }

  if (userInfo.userType === 2) {
    next(to.path.startsWith("/back") ? undefined : "/back/dashboard");
    return;
  }

  if (userInfo.userType === 1) {
    next(to.path.startsWith("/back") || to.path.startsWith("/auth") ? "/" : undefined);
    return;
  }

  next("/auth/login");
});
```

可以写进简历的表达：

- 设计前后台双 Layout 路由架构，结合 Vue Router 前置守卫实现基于用户角色的页面级权限控制，并使用动态导入优化首屏加载体积。

### 亮点五：ECharts 数据看板，覆盖情绪趋势、咨询活跃和用户活跃度

后台看板通过接口获取综合分析数据后初始化多个图表，并在重复初始化前销毁旧实例，避免重复挂载造成图表错乱或内存泄漏。

核心代码来源：`src/views/backend/DashBoard.vue`

```ts
let emotionChart: any = null;

const initEmotionChart = () => {
  if (!emotionChartRef.value) return;
  if (emotionChart) {
    emotionChart.dispose();
  }

  const emotionData = aiData.value.emotionTrend;
  emotionChart = echarts.init(emotionChartRef.value);

  emotionChart.setOption({
    tooltip: { trigger: "axis" },
    legend: { data: ["平均情绪评分", "记录数量"] },
    xAxis: {
      type: "category",
      data: emotionData.map((item: any) => item.date),
    },
    yAxis: [{ type: "value" }, { type: "value" }],
    series: [
      {
        name: "平均情绪评分",
        type: "line",
        data: emotionData.map((item: any) => item.avgMoodScore),
        smooth: true,
      },
      {
        name: "记录数量",
        type: "line",
        data: emotionData.map((item: any) => item.recordCount),
        smooth: true,
      },
    ],
  });
};
```

可以写进简历的表达：

- 使用 ECharts 构建后台运营看板，封装多图表初始化逻辑，展示情绪趋势、咨询活动、用户活跃等指标，并通过实例销毁避免重复渲染问题。

### 亮点六：配置化表格搜索组件，提高后台列表复用性

后台文章列表的搜索区域不是写死的，而是通过 `formItem` 配置动态渲染输入框、选择器等控件，父组件只需要传入字段配置并监听 `search` 事件即可复用。

核心代码来源：`src/components/backend/TableSearch.vue`

```vue
<script setup lang="ts">
const props = defineProps<{
  formItem?: FormItemConfig[];
}>();

const formItemAttr = computed(() =>
  (props.formItem || []).map((item) => ({
    ...item,
    col: { xs: 24, sm: 12, md: 8, lg: 6, xl: 4 },
  })),
);

const isComp = (comp: string) => {
  return {
    input: "el-input",
    select: "el-select",
  }[comp];
};
</script>

<template>
  <template v-for="item in formItemAttr" :key="item.prop">
    <component
      :is="isComp(item.comp)"
      v-model="formData[item.prop]"
      :placeholder="item.placeholder"
    />
  </template>
</template>
```

可以写进简历的表达：

- 封装配置化表格搜索组件，基于动态组件和字段配置渲染查询表单，提升后台多列表场景下的组件复用性和维护效率。

### 亮点七：富文本文章管理，支持编辑回显、封面上传和标签转换

后台文章弹窗整合 wangEditor 富文本组件、Element Plus 表单校验、封面上传和新增/编辑复用逻辑。编辑文章时通过 `watch` 回填数据，提交时将标签数组转换成后端需要的字符串。

wangEditor 是项目中使用的富文本编辑器库，主要作用是让后台管理员在新增或编辑知识文章时，可以像写文档一样编辑正文内容，例如加粗、斜体、标题、列表、引用、链接、字体颜色等。它不是普通的 `textarea`，而是可视化文章内容编辑器。

在本项目中的位置：

- 依赖位置：`package.json`
- 封装组件：`src/components/backend/RichTextEditor.vue`
- 使用位置：`src/components/backend/ArticleDialog.vue`

依赖代码：

```json
"@wangeditor/editor": "^5.1.23",
"@wangeditor/editor-for-vue": "^5.1.12"
```

富文本组件封装代码：

```ts
import "@wangeditor/editor/dist/css/style.css";
import {
  Editor as WangEditor,
  Toolbar as WangToolbar,
} from "@wangeditor/editor-for-vue";
```

```vue
<WangToolbar
  :editor="editorRef"
  :defaultConfig="toolbarConfig"
  mode="default"
/>

<WangEditor
  v-model="content"
  :defaultConfig="editorConfig"
  mode="default"
  @onCreated="handleEditorCreated"
  @onChange="handleEditorChange"
/>
```

核心代码来源：`src/components/backend/ArticleDialog.vue`

```ts
const dialogVisible = computed({
  get: () => props.modelValue,
  set: (val) => emit("update:modelValue", val),
});

const isEdit = computed(() => !!props.article?.id);

watch(() => props.article, (newVal) => {
  if (newVal) {
    formData.value = { ...newVal };
    businessId.value = newVal.id;
    imgUrl.value = newVal.coverImage ? `${fileBaseURL}${newVal.coverImage}` : "";
  }
});

const handleSubmit = () => {
  const { tagArray, ...rest } = formData.value;
  const submitData = { ...rest, tags: tagArray.join(",") };
  const request = isEdit.value
    ? updateArticle(props.article.id, submitData)
    : createArticle(submitData);
};
```

可以写进简历的表达：

- 封装文章新增/编辑弹窗，集成 wangEditor、封面上传、表单校验、编辑回显和标签格式转换，实现后台内容运营的完整闭环。

### 亮点八：基于 IndexedDB 的本地会话历史存储层，含 localStorage 存量自动迁移

背景：课程后端没有"追加消息"接口，AI 对话消息由前端负责持久化，加载历史会话时再与服务端消息合并。最初用 localStorage 实现，但它是同步 IO 且只有约 5MB 配额，长会话（含 RAG 引用卡片）既卡主线程又容易被浏览器静默丢弃写入。于是把存储层升级为 IndexedDB：

1. **异步不阻塞**：全异步 API，读写大会话不再卡 UI
2. **容量充裕**：配额从约 5MB 提升到数百 MB
3. **对象直存**：结构化克隆直接存取 `citations` 等嵌套对象，无需整体 JSON 序列化
4. **单条追加**：存一条消息只需一次 `add`，不用"整串读→拼接→整串写回"；自增主键天然保序
5. **无感迁移**：首次打开自动把 localStorage 存量数据迁入并清理旧键，用户零感知

表结构设计：存储桶键 = 用户 id + 会话 key（同一浏览器区分多账号的会话记录），桶键建索引实现按会话查询，单会话保留最近 200 条、超限自动裁剪最早的记录。对外接口与 v1 完全同名，业务侧只需同步改异步。

核心代码来源：`src/utils/localChatHistory.ts`

```ts
// 连接单例：首次建库/升版时建表——自增主键保序，桶键索引用于按会话查询
let dbPromise: Promise<IDBDatabase> | null = null;

const openDb = (): Promise<IDBDatabase> => {
  if (dbPromise) return dbPromise;
  dbPromise = new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VERSION);
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

// 存储桶键 = 用户id + 会话key，与v1的localStorage键尾同构（迁移零转换）
const bucketKey = (sessionId: number | string) =>
  `${getUserId()}_${getSessionKey(sessionId)}`;
```

```ts
/** 追加一条消息到本地历史（错误提示不入库；存储失败不影响聊天主流程） */
export const saveLocalMessage = async (
  sessionId: number | string,
  msg: ChatMessage,
) => {
  if (msg.isError) return;
  try {
    const bucket = bucketKey(sessionId);
    //入参可能是Vue响应式代理（嵌套的citations经get陷阱读出仍是Proxy），
    //Proxy不可结构化克隆，直接add会抛DataCloneError；JSON往返剥成纯对象
    const plainMsg = JSON.parse(JSON.stringify(msg)) as ChatMessage;
    const store = await objectStore("readwrite");
    await reqAsPromise(store.add({ ...plainMsg, bucket }));
    // 桶内超限裁剪：删最早的（seq最小）记录
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
```

降级策略：IndexedDB 不可用（如 Safari 隐私模式）时读写各自返回空值并 `console.warn`，聊天主流程不受影响；单键迁移失败则保留旧键下次重试。登录态 `token/userInfo` 这类几百字节、需要同步读取的数据仍留在 localStorage，两个方案按场景分工。

可以写进简历的表达：

- 设计并实现基于 IndexedDB 的本地会话历史存储层：自增主键保序、用户+会话桶键索引实现多账号会话隔离与按会话查询，单会话容量上限自动裁剪，内置 localStorage 存量数据自动迁移与隐私模式降级，解决长会话同步阻塞与 5MB 配额溢出问题，存储升级对用户无感。

### 亮点九：服务端 RAG 知识库——Chroma 向量库 + 语料指纹增量重建 + 双后端保险丝

咨询页与 Agent 共用的知识库运行在 Python 服务端：30 篇文章按 `<h3>` 语义小节分块（122 块），调用 embedding-2 向量化（分块文本带「【分类】标题 - 小节名」前缀提升命中率），写入 Chroma 持久化向量库（cosine 空间），用户提问时检索 top-3 注入 system prompt。知识库通过**语料 sha256 指纹**判断是否需要重建（改了 data/*.json 自动重灌，没改则秒过），并发调用用**单飞任务**防重复构建。

核心代码来源：`agent-server/knowledge_base.py`、`agent-server/vector_store.py`

```python
# 语料指纹 = 全部种子文件内容的 sha256。文件增删改都会让指纹变化触发重建
def _seed_fingerprint() -> str:
    h = hashlib.sha256()
    for path in _seed_files():
        h.update(os.path.basename(path).encode("utf-8"))
        with open(path, "rb") as f:
            h.update(f.read())
    return h.hexdigest()

async def ensure_built() -> int:
    """知识库就绪入口：指纹匹配且非空直接返回；否则触发单飞构建并等待。"""
    global _build_task
    store = get_vector_store()
    fp = _seed_fingerprint()
    if store.count() > 0 and store.fingerprint() == fp:
        return store.count()
    if _build_task is None or _build_task.done():
        _build_task = asyncio.create_task(_do_build())
    # shield：某个等待方被取消（如 /rag/chat 的3s软超时）不能连带取消构建本身
    return await asyncio.shield(_build_task)
```

```python
class ChromaStore:
    """chromadb 持久化后端：数据落盘，进程重启后无需重新 embedding"""

    def __init__(self):
        import chromadb  # 延迟导入：回退模式下不占内存
        self._client = chromadb.PersistentClient(
            path=config.CHROMA_DIR,
            settings=Settings(anonymized_telemetry=False),
        )
        self._col = self._client.get_or_create_collection(
            name=COLLECTION,
            metadata={"hnsw:space": "cosine"},  # 距离空间必须是余弦
        )

    def query(self, vector, top_k) -> list[dict]:
        res = self._col.query(
            query_embeddings=[vector],
            n_results=min(top_k, self._col.count()),
            include=["metadatas", "documents", "distances"],
        )
        out = []
        for cid, meta, doc, dist in zip(...):
            # cosine distance = 1 - 相似度：换算回"越大越相似"的分数语义
            out.append({..., "score": round(1 - dist, 4)})
        return out
```

向量层设计成「接口 + 双后端」：业务代码只依赖 `VectorStore` Protocol，chromadb 在 Python 3.13 / 512MB 内存环境出问题时，一个环境变量（或 import 失败自动）切换到 JsonStore（vectors.json + 纯 Python 余弦暴力检索），语料只有百来块、暴力计算毫秒级，检索质量无差别——这是部署在免费云环境前的工程保险丝。

可以写进简历的表达：

- 构建服务端 RAG 知识库 pipeline：文章按 h3 语义分块（上下文前缀增强向量语义）、embedding 批量向量化入 Chroma（cosine），sha256 语料指纹实现增量重建、单飞任务 + asyncio.shield 防并发重复构建与误取消；向量层以 Protocol 接口 + 纯 Python 余弦回退双后端设计，保证云环境依赖异常时零改动降级。

### 亮点十：LangGraph ReAct Agent + 工具调用过程可视化

「AI 健康管家」是服务端 ReAct Agent：LLM 自主决定调用 4 个工具——知识库 RAG 检索、情绪分析查询、咨询历史查询、情绪日记写入；用户 token 经 ContextVar 做请求级隔离透传，每个请求的所有工具调用都以该用户身份访问后端。Agent 执行过程通过 `astream_events` 翻译成自定义 SSE 协议（token / tool_start / tool_end / done / error），前端把每次工具调用渲染成「思考步骤卡片」，Agent 查了什么、做了什么决定全程可见。

核心代码来源：`agent-server/main.py`、`agent-server/tools.py`

```python
async for ev in agent.astream_events({"messages": msgs}, version="v2"):
    kind = ev["event"]
    if kind == "on_chat_model_stream":        # → 打字机字流
        delta = _content_text(ev["data"]["chunk"].content)
        if delta:
            yield _sse({"type": "token", "text": delta})
    elif kind == "on_tool_start":             # → 思考步骤卡片（执行中）
        yield _sse({"type": "tool_start", "name": ev["name"],
                    "args": ev["data"].get("input") or {}})
    elif kind == "on_tool_end":               # → 卡片填入结果
        out = ev["data"].get("output")
        result = getattr(out, "content", out)  # ToolMessage取content本体
        yield _sse({"type": "tool_end", "name": ev["name"],
                    "result": str(result)[:500]})
yield _sse({"type": "done"})
```

```python
# 用户token透传：本轮Agent内所有工具调用都以该用户身份访问后端
# async并发下全局变量会串号，ContextVar绑定上下文、每请求隔离
user_token: ContextVar[str] = ContextVar("user_token", default="")

@tool
async def search_knowledge(query: str, top_k: int = 3) -> str:
    """在心理健康知识库中检索与问题最相关的文章小节。……"""
    try:
        await knowledge_base.ensure_built()
    except Exception as e:
        return _reply({"error": f"知识库暂不可用：{e}，请直接凭常识回答"})
    results = await rag.retrieve(query, top_k)
    ...
```

前端数据模型：助手消息是 **segments 数组**——`thought`（工具卡片）与 `answer`（字流段落）交替，天然表达 ReAct 的「思考→工具→再思考→回答」；前端只依赖自定义 SSE 协议不依赖 LangGraph，换掉框架前端零改动。

可以写进简历的表达：

- 基于 LangGraph 搭建服务端 ReAct Agent（FastAPI + astream_events 流式）：LLM 自主调度 RAG 检索、情绪分析、历史查询、日记写入 4 个工具，用户 token 以 ContextVar 做请求级隔离透传；自定义 SSE 事件协议驱动前端「思考步骤卡片 + 打字机回答」的过程可视化。

### 亮点十一：Netlify + Render 双平台部署，密钥全部服务端隔离

生产架构：浏览器 → Netlify（静态站 + `agent.mjs` 边缘函数）→ Render（FastAPI + Chroma，密钥与 GLM 调用都在这层）。前端只认同源的 `/agent/*` 路径——本地开发由 vite 代理转发到 localhost:8000，生产由 Netlify 函数转发到 Render，前端代码零差异、天然无 CORS 问题。代理函数带防滥用护栏：Origin 校验（浏览器不可伪造）、256KB 请求体上限、请求头白名单（只透传 token / authorization / x-admin-token），SSE 响应流式透传不落地不缓冲。

核心代码来源：`netlify/functions/agent.mjs`

```js
// Origin只在存在时校验：浏览器请求必带且不可伪造；非浏览器客户端由服务端鉴权兜底
const origin = req.headers.get("origin");
const ownOrigins = [process.env.URL, process.env.DEPLOY_PRIME_URL].filter(Boolean);
if (origin && ownOrigins.length > 0 && !ownOrigins.includes(origin)) {
  return jsonError(403, "跨站调用被拒绝");
}

const headers = {};
for (const name of ALLOWED_HEADERS) {  // content-type/accept/token/authorization/x-admin-token
  const v = req.headers.get(name);
  if (v) headers[name] = v;
}

const upstream = await fetch(`${upstreamBase}/${sub}${search}`, {
  method: req.method, headers, body: bodyText,
});
// SSE 流式透传：响应体不解析直接返回，打字机/思考卡片体验与本地一致
return new Response(upstream.body, {
  status: upstream.status,
  headers: { "content-type": upstream.headers.get("content-type") || "application/json",
             "cache-control": "no-cache" },
});
```

免费资源治理：Render 免费版 15 分钟无流量休眠，用 UptimeRobot 每 10 分钟 ping `/health` 保活；磁盘是 ephemeral 的，服务重启由 lifespan 自动按指纹重建 Chroma（30 篇分钟内）；`/kb/rebuild` 管理端点用 `secrets.compare_digest` 校验独立管理令牌。

可以写进简历的表达：

- 设计并落地双平台部署架构：Netlify 承载静态站与边缘函数代理（Origin 校验、请求体上限、请求头白名单、SSE 流式透传），Render 承载 FastAPI + Chroma，密钥全部收敛在服务端环境变量；针对免费层限制设计保活、磁盘重建与内存回退方案，前端本地/生产共用同一 `/agent` 路径实现环境零差异。

## 3. 可优化部分与方向

1. 类型安全可以继续加强：目前不少接口返回和页面数据使用 `any`，建议为文章、分页、看板、会话、情绪分析等接口定义明确的响应类型，并让 API 函数使用泛型返回。

2. SSE 生命周期可以更完整：当前在单次请求完成时会 `abort`，建议把 `AbortController` 提升为组件级变量，在 `onBeforeUnmount` 或切换会话时主动中断旧连接，避免离开页面后仍接收消息。

3. Markdown 与富文本安全需要增强：项目里存在 `v-html`，虽然对部分内容做了转义，但建议使用成熟 Markdown 解析库配合 DOMPurify 白名单过滤，后台富文本保存/展示也要做 XSS 防护。

4. 路由权限可以配置化：当前通过 `to.path.startsWith("/back")` 和 `userType` 判断，建议在路由 `meta` 中加入 `requiresAuth`、`roles`，让权限规则更集中。

5. ECharts 可补充销毁和自适应：建议在 `onBeforeUnmount` 中统一 `dispose` 图表实例，并监听窗口 resize 或使用 ResizeObserver 调用 `chart.resize()`。

6. 前端接口环境配置可以优化：`vite.config.ts` 中代理地址写死为服务器 IP，建议改为 `.env.development`、`.env.production` 中的 `VITE_API_BASE_URL`（agent-server 侧已全部环境变量化，可作为参照）。

7. 用户体验可以继续打磨：会话列表、文章列表、图表区域可补充骨架屏、空状态、重试按钮；知识库搜索可增加防抖，减少频繁筛选或请求。

8. 代码结构可以抽离组合式函数：如 `useChatStream`、`useEmotionGarden`、`useDashboardCharts`，降低单文件组件体积，方便测试和维护。

9. 登录态存储可以更安全：token 存在 `localStorage` 容易受 XSS 影响，正式项目可考虑 HttpOnly Cookie、短 token + refresh token、接口 401 统一刷新。

10. 工程质量可以补测试：为请求封装、路由守卫、数据归一化、表单提交等逻辑补充 Vitest 单元测试，关键页面补充 Playwright E2E。

11. 对话的服务端持久化：AI 对话消息目前只存浏览器 IndexedDB（后端无追加消息接口），管理后台看不到；agent-server 可加一层 SQLite 存消息，后台咨询记录模块即恢复完整。

12. RAG 质量与安全治理：检索质量目前靠人工抽检，可建评测集量化 hit-rate / MRR，规模上来后加 rerank；`/rag/chat` 公网无鉴权，可加速率限制防滥用。

## 4. 面试官可能追问与参考答案

### Q1：你为什么用 SSE 实现 AI 回复，而不是普通 HTTP 或 WebSocket？

答：普通 HTTP 需要等后端生成完整回答后一次性返回，用户等待感强；SSE 支持服务端持续向客户端推送文本片段，很适合 AI 这种单向流式输出场景。WebSocket 是双向长连接，适合 IM、协同编辑等强双向场景，本项目主要是用户发起请求、服务端持续返回回答，SSE 更轻量。项目里 SSE 由自建的 Python 服务产生（FastAPI StreamingResponse），经 Netlify 代理函数流式透传到浏览器，全程不缓冲。

对应八股：SSE 基于 HTTP，响应头通常是 `text/event-stream`，浏览器保持连接持续接收事件；WebSocket 是独立的双向协议，需要握手升级，适合高频双向通信。

### Q2：流式消息过程中怎么避免用户重复发送？

答：项目中使用 `isAiTyping` 作为发送锁，AI 回复未完成时再次发送会直接提示。收到 `done` 事件、连接关闭或异常时再把 `isAiTyping` 置回 `false`。

对应八股：前端并发控制常见方式包括 loading 锁、按钮禁用、请求取消、防抖节流、接口幂等。

### Q3：`AbortController` 在这个项目里起什么作用？

答：它用于主动终止流式请求。比如收到 `done` 事件、后端返回 error 或解析异常时调用 `controller.abort()`，避免连接继续占用资源。

对应八股：`AbortController` 可以给 fetch 请求传入 `signal`，调用 `abort()` 后请求会被取消，常用于搜索切换、页面卸载、重复请求取消。

### Q4：你如何处理后端情绪分析字段不稳定的问题？

答：我做了 `normalizeEmotionGarden`，对多个可能字段名做兜底，比如情绪分数可能来自 `emotionScore`、`score`、`intensity`，情绪名称可能来自 `primaryEmotion`、`emotion`、`emotionName`，同时对分数做 0 到 100 的边界处理。情绪分析本身由服务端 LLM 产出结构化 JSON（异常返回 `result=null` 不抛 5xx），前端归一化做第二层兜底。

对应八股：前端要避免直接信任接口结构，适合在 adapter/normalizer 层完成数据清洗、默认值、类型转换和异常兜底。

### Q5：Axios 封装的价值是什么？

答：统一处理 baseURL、超时、token 注入、响应拆包和登录过期跳转。这样页面里只关心业务数据，不需要每个接口都重复写 token 和错误处理。

对应八股：Axios 请求拦截器在请求发出前执行，响应拦截器在 then/catch 前执行，适合统一鉴权、错误处理、loading、数据转换。

### Q6：路由守卫如何实现前后台权限隔离？

答：进入路由前读取本地 token 和 userInfo。没有 token 访问后台会跳登录；管理员 `userType === 2` 只能进入后台，访问前台会跳到后台首页；普通用户 `userType === 1` 访问后台或登录页会跳到前台首页。

对应八股：Vue Router 的 `beforeEach` 是全局前置守卫，可以通过 `to`、`from`、`next` 或返回值控制跳转；更推荐把权限写到 `route.meta`。

### Q7：ECharts 为什么要在重新初始化前 `dispose`？

答：同一个 DOM 上重复 `echarts.init` 可能产生多个实例，导致图表重叠、事件重复绑定或内存泄漏。先 `dispose` 旧实例再创建新实例，可以保证状态干净。

对应八股：第三方库创建的实例通常不完全受 Vue 自动管理，组件卸载时需要手动清理定时器、事件监听、图表实例、长连接等资源。

### Q8：配置化搜索表单的优点是什么？

答：后台列表通常都有查询表单，字段不同但结构相似。把字段名、控件类型、占位符、选项做成配置，组件内部用动态组件渲染，可以减少重复模板代码，新增搜索项只需要改配置。

对应八股：Vue 动态组件使用 `<component :is="xxx" />`，可以根据变量渲染不同组件；props 是单向数据流，不能直接修改，所以项目里用 computed 派生新配置。

### Q9：Vue3 组件的 `v-model` 本质是什么？

答：默认是父组件传 `modelValue`，子组件通过 `emit("update:modelValue", value)` 通知父组件更新。项目中的文章弹窗和富文本编辑器都用了 computed 的 get/set 来封装双向绑定。

对应八股：Vue3 支持多个 `v-model`，如 `v-model:title` 对应 `title` 和 `update:title`；本质仍然是 props + emit。

### Q10：`v-html` 有什么风险？你怎么处理？

答：`v-html` 会把字符串当 HTML 插入 DOM，如果内容来自用户输入或不可信接口，就可能出现 XSS。项目里用户消息做了 HTML 字符转义，Markdown 渲染也先替换 `<`、`>`；更完善的方案是 DOMPurify 白名单过滤。

对应八股：XSS 是攻击者注入脚本并在用户浏览器执行，常见防护包括输入校验、输出转义、CSP、HttpOnly Cookie、HTML Sanitizer。

### Q11：这个项目里 Composition API 的优势体现在哪里？

答：像 AI 对话状态、情绪分析状态、表单状态、图表实例都用 `ref/reactive/computed` 组织，逻辑更容易按功能聚合。后续还可以继续抽成 `useChatStream`、`useDashboardCharts` 这种组合式函数，提高复用和可测试性。

对应八股：`ref` 适合基本类型和需要整体替换的数据，模板中自动解包；`reactive` 适合对象；`computed` 有缓存，依赖不变不会重新计算。

### Q12：如果让你继续优化这个项目，你会优先做什么？

答：分两端说。前端：把接口 `any` 改成明确类型、补 SSE 和 ECharts 的卸载清理、处理 `v-html` 的 XSS 安全；服务端：给对话加服务端持久化（后台能看到 AI 咨询记录）、给 RAG 建检索质量评测集。分别对应稳定性、可维护性、安全性和可评估性。

对应八股：项目优化要从用户体验、稳定性、安全性、性能、可维护性几个角度展开，最好能结合具体代码说清楚收益。

### Q13：本地存储为什么选 IndexedDB 而不是 localStorage？

答：三个原因。一是 localStorage 是同步 IO，会话变长后每次读写都要整体 `JSON.parse/stringify`，会阻塞主线程；二是它只有约 5MB 配额，超限时浏览器会静默丢弃写入，聊天记录加引用卡片很容易触顶；三是它只能存字符串、只能整串读写，而 IndexedDB 支持对象直存（结构化克隆）、索引查询和单条追加，正好匹配"按会话存消息"的场景。同时做了分层：登录 token 这类几百字节、路由守卫里需要同步读取的数据仍留在 localStorage，两个方案按场景分工。升级时还做了 localStorage 存量自动迁移，用户无感。

对应八股：IndexedDB 是浏览器内置的异步 NoSQL 数据库，容量通常数百 MB 起；核心概念有数据库（database）、对象仓库（objectStore）、事务（transaction）、索引（index）；所有读写都包在事务里，具备原子性；用结构化克隆算法存对象和二进制，不需要 JSON 序列化；原生 API 是回调式的，实践中通常包一层 Promise 或用 idb 这类库。

### Q14：项目里遇到过什么比较难的 bug？怎么定位的？

答：RAG 升级上线后用户反馈"最新开的对话不保留历史记录"。定位过程：先查存储层写入链路没发现问题，怀疑是会话同步（temp 转正）丢了消息；最后靠控制台报错锁定——`DataCloneError: Failed to execute 'add' on 'IDBObjectStore'`。完整因果链是三个"各自正确"的设计组合出来的：

1. AI 消息为了打字机动画必须用 `reactive()` 包装，否则流式修改 content 不触发视图更新
2. RAG 命中后往消息上挂 `citations` 引用数组（产品需求，引用卡要随消息持久化）
3. 落库时 `{ ...aiMessage }` 浅拷贝：顶层成了普通对象，但嵌套的 `citations` 经 Vue 代理的 get 陷阱读出来**仍然是 Proxy**；IndexedDB 的 `add()` 走结构化克隆，而 Proxy 不可克隆，直接抛错

这个 bug 的迷惑性在于**按消息类型选择性触发**：用户消息（普通对象常量）能存、不带引用的 AI 回复（顶层全是原始类型）也能存，只有带引用卡的 AI 回复全部落库失败——表现出来就像"随机丢历史"，而且恰好只影响升级后的新对话（旧数据是 localStorage 时代 JSON.stringify 存的，序列化会穿透代理，天然没这个问题）。

修复放在存储层：`saveLocalMessage` 入库前 `JSON.parse(JSON.stringify(msg))` 剥成纯对象，对所有调用方（含会话转正时的消息迁移重放）统一生效。

面试时可以强调的点是**定位方法**：不是盲改代码，而是先按"哪类消息丢、哪类不丢"分类缩小范围，每一类对应一条代码路径，交集直接指向"citations + 响应式代理"的组合。

对应八股：

- 结构化克隆算法：IndexedDB、postMessage 传值用的序列化机制，支持普通对象、数组、Date、Blob、Map/Set 等；不支持函数、Symbol、DOM 节点、Proxy——遇到不可克隆的值直接抛 DataCloneError
- Vue3 响应式原理：`reactive()` 基于 Proxy，get 陷阱里嵌套对象会被递归包装成代理，所以**展开运算符浅拷贝只能剥掉顶层代理**，嵌套对象要深拷贝或 JSON 序列化才能穿透
- `JSON.parse(JSON.stringify())` 的局限：Date 变字符串、undefined/函数/Symbol 丢失、循环引用报错；本项目消息体是纯 JSON 字段所以无损，更通用的做法是递归 `toRaw` 或深拷贝工具

### Q15：RAG 为什么放在服务端而不是浏览器端？

答：这个项目实际经历过两个阶段。第一版 RAG 在浏览器端（向量存 IndexedDB），能跑但上线后暴露三个硬伤：①健康管家 Agent 必须访问需登录态的用户数据（情绪分析、日记），浏览器端做不了；②密钥只能藏在代理层后面，能力和成本都受限；③每个访客要各自在浏览器建一遍向量库（首次 10~30 秒）。所以整体迁到服务端：知识库只在服务进程内一份、密钥只在服务端环境变量、Agent 与咨询页共用同一个向量库。迁移时定了条纪律——**prompt 和上下文组装逐字搬运、模型输入保持不变**——保证线上回答风格零漂移，出问题也好对比排查。

对应八股：RAG（Retrieval-Augmented Generation）= 先检索相关资料注入上下文、再让 LLM 作答，缓解幻觉、可溯源；浏览器端 vs 服务端的取舍维度 = 密钥安全、语料共享、计算位置、首字延迟、离线能力。

### Q16：向量库为什么选 Chroma？检索是怎么工作的？

答：Chroma 是轻量级向量数据库：嵌入式（不需要独立部署数据库服务）、PersistentClient 直接落盘、支持 cosine 距离空间，和 FastAPI 单服务架构最匹配。入库时把每个文章小节的 1024 维向量连同元数据（文章标题/小节名）一起 upsert；检索时把用户问题也向量化，Chroma 返回距离最近的 top-k，我做了分数语义换算——cosine distance = 1 − 相似度，取 `1 - dist` 换算回"越大越相似"，与之前手写余弦打分一致，引用卡片上的分数才有统一语义。另外因为 chromadb 在 Python 3.13 / 512MB 环境有不确定性，向量层设计了 Protocol 接口 + 纯 Python 余弦的 JsonStore 回退后端，语料只有百来块、暴力检索毫秒级，回退后功能无损。

对应八股：向量检索 = 文本 embedding 成高维向量后按距离找最近邻；cosine 只看方向不看模长，适合文本语义；HNSW 是分层可导航小世界图，近似检索用 O(logN) 换少量召回损失——百级语料暴力精确检索就够，ANN 是规模上来后的事（这个取舍讲清楚比堆名词加分）。

### Q17：Embedding 是什么？你的分块策略是怎样的？

答：embedding 模型把文本映射成语义空间里的稠密向量（本项目用智谱 embedding-2，1024 维），语义相近的文本向量方向相近。分块按文章的 `<h3>` 小节切——小节是天然语义边界；每个块的向量化文本不是裸正文，而是加「【分类】标题 - 小节名」前缀，因为小节正文脱离标题语义不完整（光一句"固定起床时间比固定入睡时间重要"不一定能检索关联到"失眠"）。低于 20 字的碎块直接丢弃。实测"最近总是失眠睡不着"能精准命中 CBT-I 的三条规则。

对应八股：embedding / 双塔模型、余弦相似度、top-k 检索、分块策略（固定长度 vs 语义边界）对检索命中率的影响、批量向量化接口的批次限制。

### Q18：ReAct Agent 是什么？工具是怎么被 LLM 调用的？

答：ReAct = Reason + Act 循环：LLM 输出"调用哪个工具 + 参数"→ 执行工具 → 结果回给 LLM → 继续推理，直到能给出最终回答。LangGraph 的 `create_react_agent` 把这个循环封装成状态图，工具的 docstring 就是 LLM 看的"工具说明书"（什么时候调、参数含义）。我的 4 个工具：知识库检索（走同一套 RAG 链路）、情绪分析查询、咨询历史查询、日记写入；后三个要用户 token，用 ContextVar 从请求头透传进工具——async 并发下全局变量会让多用户 token 互相覆盖，ContextVar 绑定上下文每请求隔离。Agent 过程用 `astream_events` 流出 token / 工具事件，翻译成自定义 SSE 协议给前端做思考卡片可视化。

对应八股：Function Calling 协议（模型输出结构化调用意图而非自然语言）、Agent 循环与终止条件、递归上限（GraphRecursionError 兜底）、流式事件粒度。

### Q19：为什么部署要 Netlify + Render 两个平台？代理函数做了什么？

答：分工是「Netlify 管入口、Render 管算力」：Netlify 承载静态站和边缘函数，国内访问友好、免费额度稳定；Render 跑 Python AI 服务（FastAPI + Chroma），免费版 750 小时/月刚好覆盖单服务全月。`agent.mjs` 把 `/agent/*` 转发到 Render：Origin 校验防跨站滥用（浏览器不可伪造，无 Origin 的客户端由服务端自身鉴权兜底）、256KB 请求体上限、请求头白名单只透传三类身份头。好处有三个：浏览器只认同源域名（无 CORS）、密钥全部收敛在 Render 环境变量、前端本地（vite 代理）与生产（函数转发）走同一个 `/agent` 路径，前端代码零差异。

对应八股：反向代理、CORS 与同源策略、环境变量与密钥管理（密钥永不出现在前端 bundle）、SSE 透传时为什么不能缓冲（流式体验依赖分片直达）。

### Q20：免费云资源有什么坑？你怎么应对的？

答：四个坑四套预案：①15 分钟无流量休眠——UptimeRobot 每 10 分钟 ping `/health` 保活，冷启动基本消失；②磁盘 ephemeral、重启丢数据——Chroma 库由服务启动时 lifespan 后台重建，语料指纹判断要不要重灌（30 篇约分钟级），且种子语料随代码部署不依赖外部存活；③512MB 内存紧张——chromadb 关遥测 + 延迟导入，真超标可用 `KB_BACKEND=json` 切纯 Python 余弦回退（百级语料功能无损）；④撞上冷启动时检索可能未就绪——`/rag/chat` 对知识库就绪做 3 秒软超时，超时降级为无引用回答，绝不拖首字。

对应八股：无状态服务设计、健康检查端点、冷启动、超时与降级策略（可用性优先于功能完整性）。

## 5. 可直接放到简历里的版本

### Codex 辅助开发表述

可以写成：

借助 Codex 完成项目基础工程搭建，包括 Vue3 + TypeScript 项目骨架、前后台路由结构、Pinia 状态管理、Axios 请求封装等基础配置，减少重复初始化成本，提升开发效率。

更简洁一点：

借助 Codex 完成项目骨架、路由、Pinia 和 Axios 等基础工程配置，提高前期开发效率。

面试时可以这样解释：

我不是直接让 Codex 一次性生成整个项目，而是把它当作工程初始化和代码辅助工具。前期我先确定项目模块和技术栈，然后让 Codex 帮我生成基础目录、路由配置、Pinia 状态管理和 Axios 请求封装。之后核心业务，比如 SSE 流式对话、服务端 RAG、LangGraph Agent、部署上线，是我结合接口和页面需求逐步实现和调整的。

对应开发流程：

1. 明确项目需求与技术栈：确定使用 Vue3、TypeScript、Vite、Element Plus、Pinia、Vue Router、Axios 等技术。
2. 让 Codex 辅助生成基础目录：拆分 `views/frontend`、`views/backend`、`components/layouts`、`apis`、`stores`、`utils` 等模块。
3. 让 Codex 辅助配置路由：生成用户端、管理端、登录注册模块，并通过动态导入实现路由懒加载。
4. 让 Codex 辅助配置 Pinia：封装后台侧边栏折叠状态等全局状态。
5. 让 Codex 辅助封装 Axios：统一处理 `baseURL`、请求超时、Token 自动携带、登录过期跳转等逻辑。
6. 自己结合接口和业务继续完善核心功能：AI 咨询（服务端 RAG + 流式）、AI 健康管家（LangGraph Agent）、情绪分析、知识库和后台数据看板。
7. 自己完成 Python 服务端（FastAPI + Chroma + LangGraph）与 Netlify / Render 双平台部署。
8. 最后借助 Codex 检查代码结构、类型问题、接口封装一致性和可优化点。

可以配合的代码示例：

```ts
// 路由懒加载
{
  path: "consultation",
  name: "consultation",
  component: () => import("@/views/frontend/Consultation.vue"),
  meta: { title: "AI咨询" },
}
```

```ts
// Pinia 状态管理
export const useAdminStore = defineStore("admin", () => {
  const isCollapsed = ref(false);

  const toggleAdmin = () => {
    isCollapsed.value = !isCollapsed.value;
  };

  return {
    isCollapsed,
    toggleAdmin,
  };
});
```

项目介绍：

基于 Vue3 + TypeScript 前端与 Python FastAPI 服务端开发的 AI 心理健康陪伴平台（已上线）：用户侧提供 AI 心理咨询（服务端 RAG 检索增强、SSE 流式打字机、引用溯源卡片）、AI 健康管家（LangGraph ReAct Agent，工具调用过程可视化）、情绪日记与情绪花园；管理侧提供数据看板、咨询记录和文章运营。生产架构为 Netlify（静态站 + 边缘函数代理）+ Render（FastAPI + Chroma 向量库），密钥全部收敛在服务端环境变量。

技术栈：

前端：Vue3、TypeScript、Vite、Vue Router、Pinia、Element Plus、Axios、ECharts、IndexedDB、SSE；服务端：Python、FastAPI、LangGraph、LangChain、ChromaDB、智谱 GLM / embedding-2；部署：Netlify Functions、Render。

项目亮点：

- 构建服务端 RAG 检索增强链路：知识库文章按 h3 语义分块（上下文前缀增强向量语义），embedding-2 向量化入 Chroma（cosine），sha256 语料指纹增量重建 + 单飞任务防并发重复构建；检索 top-3 注入 system prompt，SSE 首事件前置下发 citations，AI 回复带可溯源的参考来源卡片。
- 基于 LangGraph 搭建服务端 ReAct Agent（FastAPI + astream_events 流式）：LLM 自主调度 RAG 检索、情绪分析、历史查询、日记写入 4 个工具，用户 token 以 ContextVar 做请求级隔离透传；自定义 SSE 事件协议驱动前端「思考步骤卡片 + 打字机」的过程可视化。
- 设计并落地双平台部署架构：Netlify 边缘函数代理（Origin 校验、请求头白名单、SSE 流式透传）转发至 Render 上的 FastAPI + Chroma 服务，密钥零出前端；针对免费层限制实现保活、指纹自动重建与内存回退方案。
- 实现 AI 回复流式渲染全链路：原生 fetch 解析 SSE（半行缓冲防网络分片）、rAF 打字机按积压量自适应出字速度，配合服务端 citations 前置，对话实时性与平滑度兼得。
- 设计并实现基于 IndexedDB 的本地会话历史存储层：桶键索引隔离多账号会话、自增主键保序、容量自动裁剪、localStorage 存量自动迁移与隐私模式降级，解决长会话同步阻塞与配额溢出问题。
- 设计前后台双 Layout 路由架构，结合 Vue Router 前置守卫实现角色级页面权限控制；基于 Axios 拦截器封装统一请求层（Token 注入、业务拆包、登录失效重定向）。
