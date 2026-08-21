# AI心理健康情绪陪伴助手项目梳理

## 1. 项目介绍与技术栈

### 项目介绍

AI心理健康情绪陪伴助手是一个基于 Vue3 的前后台分离心理健康平台，前台面向用户提供 AI 心理咨询、情绪日记和心理知识库，后台面向管理员提供数据看板、咨询记录、情绪日志和知识文章管理。

项目围绕“实时对话 + 情绪分析 + 内容运营 + 数据可视化”展开，既有用户侧的陪伴式交互，也有管理侧的运营数据闭环。

### 技术栈

- 前端框架：Vue3、Composition API、TypeScript
- 构建工具：Vite
- 路由与状态：Vue Router、Pinia
- UI 组件库：Element Plus、@element-plus/icons-vue
- 网络请求：Axios、Vite Proxy
- AI 流式通信：@microsoft/fetch-event-source、SSE
- 数据可视化：ECharts
- 内容编辑与渲染：wangEditor、Markdown/HTML 渲染
- 样式方案：SCSS、响应式布局
- 工程化：vue-tsc 类型检查、npm-run-all2 构建脚本

## 2. 项目亮点与核心代码

### 亮点一：基于 SSE 实现 AI 回复流式输出

用户发送消息后，前端通过 `fetchEventSource` 建立 `text/event-stream` 流式连接，AI 回复按片段追加到最后一条 AI 消息中。相比普通 HTTP 请求一次性返回，流式输出能显著降低用户等待感，更贴近真实 AI 对话产品体验。

核心代码来源：`src/views/frontend/Consultation.vue`

```ts
const startAiResponse = (sessionId: number | string, userInput: string) => {
  if (isAiTyping.value) {
    ElMessage.warning("AI 正在思考，请稍后再发送消息");
    return;
  }

  isAiTyping.value = true;
  message.value.push({
    id: `ai_${Date.now()}`,
    senderType: 2,
    content: "",
    createdAt: new Date().toISOString(),
  });

  const controller = new AbortController();

  fetchEventSource("/api/psychological-chat/stream", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      token: localStorage.getItem("token") || "",
      Accept: "text/event-stream",
    },
    body: JSON.stringify({ sessionId, userInput }),
    signal: controller.signal,
    onmessage(event) {
      const aiMessage = message.value[message.value.length - 1];

      if (event.event === "done") {
        isAiTyping.value = false;
        loadSessionEmotion(sessionId);
        controller.abort();
        return;
      }

      const payload = JSON.parse(event.data.trim());
      if (String(payload.code) === "200" && payload.data?.content) {
        aiMessage.content += payload.data.content;
      }
    },
    onerror(error) {
      handleError(error);
      controller.abort();
    },
  });
};
```

可以写进简历的表达：

- 基于 SSE + `fetchEventSource` 实现 AI 咨询回复的流式渲染，通过消息占位、分片追加、完成事件监听和异常中断处理，提升对话实时性与交互稳定性。

### 亮点二：会话情绪分析数据归一化，增强接口兼容性

情绪分析接口返回字段可能存在不同命名方式，项目中对 `emotionScore / score / intensity`、`primaryEmotion / emotion / emotionName` 等字段做统一归一化，同时增加默认值、分数边界裁剪和风险等级兜底，避免后端字段变化导致前端页面崩溃。

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

文章弹窗中使用：

```vue
<RichTextEditor
  v-model="formData.content"
  placeholder="请输入文章内容"
  :maxCharCount="5000"
  @change="handleContentChange"
  @created="handleEditorCreate"
  min-height="400px"
/>
```

可以写进简历的表达：

- 使用 wangEditor 封装后台文章富文本编辑器，支持文章正文可视化编辑、内容回显、字数统计和表单双向绑定，提升知识库内容运营效率。

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

const handleUploadRequest = async (options: any) => {
  const file = options.file;
  businessId.value = businessId.value || crypto.randomUUID();
  const fileRes = await uploadFile(file, { id: businessId.value });
  imgUrl.value = `${fileBaseURL}${fileRes.filePath}`;
  formData.value.coverImage = fileRes.filePath;
};

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

背景：对话改走 GLM 直连后，课程后端没有"追加消息"接口，聊天记录由前端负责持久化，加载历史会话时再与服务端消息合并。最初用 localStorage 实现，但它是同步 IO 且只有约 5MB 配额，长会话（含 RAG 引用卡片）既卡主线程又容易被浏览器静默丢弃写入。于是把存储层升级为 IndexedDB：

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

// 会话key归一化：同一会话在页面里可能是 123 / "session_123" / "temp_123"，
// 统一去掉前缀，保证不同来源的id寻址到同一个存储桶
const getSessionKey = (sessionId: number | string) => {
  return String(sessionId ?? "").replace(/^session_/, "") || "unknown";
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

// 模块加载即完成存量迁移，业务侧无感
openDb()
  .then(migrateLegacyLocalStorage)
  .catch(() => {
    // IndexedDB不可用（隐私模式等）：读写接口各自降级返回空，不阻塞聊天
  });
```

降级策略：IndexedDB 不可用（如 Safari 隐私模式）时读写各自返回空值并 `console.warn`，聊天主流程不受影响；单键迁移失败则保留旧键下次重试。登录态 `token/userInfo` 这类几百字节、需要同步读取的数据仍留在 localStorage，两个方案按场景分工。

同一套方案还复用在 RAG 向量缓存（`src/rag/vectorStore.ts`）：文章分块向量首次计算后落 IndexedDB，之后检索直接读本地缓存，不再请求 embedding 接口，并以"文章集合指纹"作为版本号实现知识库变化后自动全量重建。

可以写进简历的表达：

- 设计并实现基于 IndexedDB 的本地会话历史存储层：自增主键保序、用户+会话桶键索引实现多账号会话隔离与按会话查询，单会话容量上限自动裁剪，内置 localStorage 存量数据自动迁移与隐私模式降级，解决长会话同步阻塞与 5MB 配额溢出问题，存储升级对用户无感。

## 3. 可优化部分与方向

1. 类型安全可以继续加强：目前不少接口返回和页面数据使用 `any`，建议为文章、分页、看板、会话、情绪分析等接口定义明确的响应类型，并让 API 函数使用泛型返回。

2. SSE 生命周期可以更完整：当前在单次请求完成时会 `abort`，建议把 `AbortController` 提升为组件级变量，在 `onBeforeUnmount` 或切换会话时主动中断旧连接，避免离开页面后仍接收消息。

3. Markdown 与富文本安全需要增强：项目里存在 `v-html`，虽然对部分内容做了转义，但建议使用成熟 Markdown 解析库配合 DOMPurify 白名单过滤，后台富文本保存/展示也要做 XSS 防护。

4. 路由权限可以配置化：当前通过 `to.path.startsWith("/back")` 和 `userType` 判断，建议在路由 `meta` 中加入 `requiresAuth`、`roles`，让权限规则更集中。

5. ECharts 可补充销毁和自适应：建议在 `onBeforeUnmount` 中统一 `dispose` 图表实例，并监听窗口 resize 或使用 ResizeObserver 调用 `chart.resize()`。

6. 接口环境配置可以优化：`vite.config.ts` 中代理地址写死为服务器 IP，建议改为 `.env.development`、`.env.production` 中的 `VITE_API_BASE_URL`。

7. 用户体验可以继续打磨：会话列表、文章列表、图表区域可补充骨架屏、空状态、重试按钮；知识库搜索可增加防抖，减少频繁筛选或请求。

8. 代码结构可以抽离组合式函数：如 `useChatStream`、`useEmotionGarden`、`useDashboardCharts`，降低单文件组件体积，方便测试和维护。

9. 登录态存储可以更安全：token 存在 `localStorage` 容易受 XSS 影响，正式项目可考虑 HttpOnly Cookie、短 token + refresh token、接口 401 统一刷新。

10. 工程质量可以补测试：为请求封装、路由守卫、数据归一化、表单提交等逻辑补充 Vitest 单元测试，关键页面补充 Playwright E2E。

## 4. 面试官可能追问与参考答案

### Q1：你为什么用 SSE 实现 AI 回复，而不是普通 HTTP 或 WebSocket？

答：普通 HTTP 需要等后端生成完整回答后一次性返回，用户等待感强；SSE 支持服务端持续向客户端推送文本片段，很适合 AI 这种单向流式输出场景。WebSocket 是双向长连接，适合 IM、协同编辑等强双向场景，本项目主要是用户发起请求、服务端持续返回回答，SSE 更轻量。

对应八股：SSE 基于 HTTP，响应头通常是 `text/event-stream`，浏览器保持连接持续接收事件；WebSocket 是独立的双向协议，需要握手升级，适合高频双向通信。

### Q2：流式消息过程中怎么避免用户重复发送？

答：项目中使用 `isAiTyping` 作为发送锁，AI 回复未完成时再次发送会直接提示。收到 `done` 事件、连接关闭或异常时再把 `isAiTyping` 置回 `false`。

对应八股：前端并发控制常见方式包括 loading 锁、按钮禁用、请求取消、防抖节流、接口幂等。

### Q3：`AbortController` 在这个项目里起什么作用？

答：它用于主动终止流式请求。比如收到 `done` 事件、后端返回 error 或解析异常时调用 `controller.abort()`，避免连接继续占用资源。

对应八股：`AbortController` 可以给 fetch 请求传入 `signal`，调用 `abort()` 后请求会被取消，常用于搜索切换、页面卸载、重复请求取消。

### Q4：你如何处理后端情绪分析字段不稳定的问题？

答：我做了 `normalizeEmotionGarden`，对多个可能字段名做兜底，比如情绪分数可能来自 `emotionScore`、`score`、`intensity`，情绪名称可能来自 `primaryEmotion`、`emotion`、`emotionName`，同时对分数做 0 到 100 的边界处理。

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

答：我会优先做三件事：第一，把接口 `any` 改成明确类型；第二，增强 SSE 和 ECharts 的卸载清理；第三，处理 `v-html` 的 XSS 安全。它们分别对应稳定性、可维护性和安全性，是面试官比较容易认可的优化方向。

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

修复放在存储层：`saveLocalMessage` 入库前 `JSON.parse(JSON.stringify(msg))` 剥成纯对象，对所有调用方（含会话转正时的消息迁移重放）统一生效。消息体全是 JSON 安全字段（createdAt 是 ISO 字符串），往返无损。

面试时可以强调的点是**定位方法**：不是盲改代码，而是先按"哪类消息丢、哪类不丢"分类缩小范围（用户消息在、AI 消息丢、带引用的丢得更彻底），每一类对应一条代码路径，交集直接指向"citations + 响应式代理"的组合。

对应八股：

- 结构化克隆算法：IndexedDB、postMessage 传值用的序列化机制，支持普通对象、数组、Date、Blob、Map/Set 等；不支持函数、Symbol、DOM 节点、Proxy——遇到不可克隆的值直接抛 DataCloneError
- Vue3 响应式原理：`reactive()` 基于 Proxy，get 陷阱里嵌套对象会被递归包装成代理，所以**展开运算符浅拷贝只能剥掉顶层代理**，嵌套对象要深拷贝或 JSON 序列化才能穿透
- `JSON.parse(JSON.stringify())` 的局限：Date 变字符串、undefined/函数/Symbol 丢失、循环引用报错；本项目消息体是纯 JSON 字段所以无损，更通用的做法是递归 `toRaw` 或深拷贝工具

## 5. 可直接放到简历里的版本

### Codex 辅助开发表述

可以写成：

借助 Codex 完成项目基础工程搭建，包括 Vue3 + TypeScript 项目骨架、前后台路由结构、Pinia 状态管理、Axios 请求封装等基础配置，减少重复初始化成本，提升开发效率。

更简洁一点：

借助 Codex 完成项目骨架、路由、Pinia 和 Axios 等基础工程配置，提高前期开发效率。

面试时可以这样解释：

我不是直接让 Codex 一次性生成整个项目，而是把它当作工程初始化和代码辅助工具。前期我先确定项目模块和技术栈，然后让 Codex 帮我生成基础目录、路由配置、Pinia 状态管理和 Axios 请求封装。之后核心业务，比如 SSE 流式对话、情绪分析面板、文章管理和数据看板，是我结合接口和页面需求逐步实现和调整的。

对应开发流程：

1. 明确项目需求与技术栈：确定使用 Vue3、TypeScript、Vite、Element Plus、Pinia、Vue Router、Axios 等技术。
2. 让 Codex 辅助生成基础目录：拆分 `views/frontend`、`views/backend`、`components/layouts`、`apis`、`stores`、`utils` 等模块。
3. 让 Codex 辅助配置路由：生成用户端、管理端、登录注册模块，并通过动态导入实现路由懒加载。
4. 让 Codex 辅助配置 Pinia：封装后台侧边栏折叠状态等全局状态。
5. 让 Codex 辅助封装 Axios：统一处理 `baseURL`、请求超时、Token 自动携带、登录过期跳转等逻辑。
6. 自己结合接口和业务继续完善核心页面：实现 AI 咨询、SSE 流式回复、情绪日记、知识库和后台数据看板。
7. 最后借助 Codex 检查代码结构、类型问题、接口封装一致性和可优化点。

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

基于 Vue3 + TypeScript 开发的 AI 心理健康情绪陪伴平台，包含用户端 AI 心理咨询、情绪日记、心理知识库，以及管理端数据看板、咨询记录和文章运营模块。项目通过 SSE 实现 AI 回复流式输出，并结合情绪分析、富文本内容管理和 ECharts 数据可视化形成完整业务闭环。

技术栈：

Vue3、TypeScript、Vite、Vue Router、Pinia、Element Plus、Axios、SSE、ECharts、wangEditor、SCSS。

项目亮点：

- 基于 SSE + `fetchEventSource` 实现 AI 咨询回复的流式渲染，通过消息占位、分片追加、完成事件监听和异常中断处理，提升对话实时性与交互稳定性。
- 封装情绪分析结果归一化逻辑，对接口字段差异、异常分数、空数据和风险等级进行兜底处理，提升 AI 情绪面板在异常数据下的稳定性。
- 基于 Axios 拦截器封装统一请求层，实现 Token 自动注入、业务数据拆包、登录失效重定向和泛型响应类型约束，降低接口调用重复代码。
- 设计前后台双 Layout 路由架构，结合 Vue Router 前置守卫实现基于用户角色的页面级权限控制，并使用动态导入优化首屏加载体积。
- 使用 ECharts 构建后台运营看板，展示情绪趋势、咨询活动、用户活跃等指标，并通过实例销毁避免重复渲染问题。
- 封装配置化表格搜索组件和文章编辑弹窗，集成动态组件、富文本编辑、封面上传、编辑回显和标签格式转换，提高后台内容管理模块复用性。
- 设计并实现基于 IndexedDB 的本地会话历史存储层，通过自增主键保序、桶键索引隔离多账号会话、容量上限自动裁剪和 localStorage 存量自动迁移，解决长会话同步阻塞与配额溢出问题。
