<script setup lang="ts">
import { ref, reactive, nextTick, onMounted, onUnmounted } from "vue";
import {
  startSession,
  getSessionMessages,
  deleteSession,
  getSessionList,
} from "@/apis/frontEnd";
import { ElMessage } from "element-plus";
import {
  ChatRound,
  Clock,
  Delete,
  Plus,
  Promotion,
  Refresh,
} from "@element-plus/icons-vue";
import MarkdownRenderer from "@/components/common/MarkdownRenderer.vue";
import { ragChatStream } from "@/apis/agent";
import { analyzeEmotion } from "@/composables/useEmotionAnalysis";
import {
  getLocalMessages,
  mergeHistory,
  migrateLocalHistory,
  removeLocalHistory,
  saveLocalMessage,
} from "@/utils/localChatHistory";
import type {
  ChatMessage,
  EmotionGarden,
  MessageVerify,
  SessionHistoryItem,
} from "@/types";

const iconUrl1 = new URL("@/assets/images/robot-fill.png", import.meta.url)
  .href;
const iconUrl2 = new URL("@/assets/images/like.png", import.meta.url).href;
const iconUrl3 = new URL("@/assets/images/users.png", import.meta.url).href;
//对话区AI端头像（机器人.png，与侧边栏/后台同一张）
const aiAvatarUrl = new URL("@/assets/images/机器人.png", import.meta.url)
  .href;

const createDefaultEmotionGarden = (): EmotionGarden => ({
  primaryEmotion: "中性",
  emotionScore: 50,
  isNegative: false,
  summary: "选择一段历史会话后，这里会展示会话里的主要情绪倾向。",
  suggestion: "可以先从一句最想说的话开始，慢慢整理当前的感受。",
  riskLevel: "low",
  actionItems: ["记录此刻最明显的情绪", "做一次缓慢呼吸", "给自己留出几分钟安静时间"],
});

//新建会话
const creatNewFrontEndSession = () => {
  //创建一个新的会话对象
  const newSession = {
    sessionId: `temp_${Date.now()}`,
    status: "TEMP",
    sessionTitle: "新会话",
  };
  currentSession.value = newSession;
  message.value = [];
  emotionGarden.value = createDefaultEmotionGarden();
};

//定义一个当前会话对象
const currentSession = ref<SessionHistoryItem | null>(null);

//历史会话数据
const sessionHistory = ref<SessionHistoryItem[]>([]);

//定义对话信息，用来判断是否有历史会话，如果没有历史会话就显示欢迎语
const message = ref<ChatMessage[]>([]);

const userInput = ref("");

const isAiTyping = ref(false);

//RAG已整体迁到服务端（agent-server）：检索、引用、prompt组装都在 /agent/rag/chat
//一跳完成，浏览器端不再建库/不再直连LLM（原 useRag + 检索预算降级逻辑随之移除）

const isUserMessage = (msg: ChatMessage) => Number(msg.senderType) === 1;

//消息区DOM引用：用于新消息/流式输出时自动滚到底部
const chatMessagesRef = ref<HTMLElement | null>(null);
//自动滚底：force=新消息直接贴底；流式更新时只在用户本来就在底部附近才跟随，
//避免用户上翻阅读历史时被逐帧拽回底部
const scrollChatToBottom = (force = false) => {
  const el = chatMessagesRef.value;
  if (!el) return;
  const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 120;
  if (force || nearBottom) {
    el.scrollTop = el.scrollHeight;
  }
};

//消息时间显示：ISO字符串直接渲染像乱码（2026-08-20T13:51:23.456Z），转成本地友好格式
const formatMsgTime = (iso: string) => {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) {
    return iso;
  }
  const pad = (n: number) => String(n).padStart(2, "0");
  const hm = `${pad(d.getHours())}:${pad(d.getMinutes())}`;
  return d.toDateString() === new Date().toDateString()
    ? hm
    : `${d.getMonth() + 1}月${d.getDate()}日 ${hm}`;
};

//情绪花园数据
const emotionGarden = ref<EmotionGarden>(createDefaultEmotionGarden());

const isEmotionLoading = ref(false);

const formatDuration = (durationMinutes?: number) => {
  if (!durationMinutes || durationMinutes < 1) {
    return "刚刚";
  }

  if (durationMinutes < 60) {
    return `${durationMinutes}分钟`;
  }

  const hours = Math.floor(durationMinutes / 60);
  const minutes = durationMinutes % 60;
  return minutes > 0 ? `${hours}小时${minutes}分钟` : `${hours}小时`;
};

const normalizeScore = (score: unknown) => {
  const value = Number(score);
  if (Number.isNaN(value)) {
    return 50;
  }
  return Math.min(100, Math.max(0, Math.round(value)));
};

const getEmotionLevelText = (score: number) => {
  if (score >= 75) {
    return "强烈";
  }
  if (score >= 45) {
    return "中等";
  }
  return "轻微";
};

const getEmotionStatusText = () => {
  if (emotionGarden.value.riskLevel === "high") {
    return "需要关注";
  }
  if (emotionGarden.value.isNegative) {
    return "有些波动";
  }
  return "整体平稳";
};

const getEmotionDotCount = () => {
  return Math.max(1, Math.ceil(emotionGarden.value.emotionScore / 20));
};

const getRiskText = () => {
  if (emotionGarden.value.riskLevel === "high") {
    return "高风险";
  }
  if (emotionGarden.value.riskLevel === "medium") {
    return "中风险";
  }
  return "低风险";
};

const refreshCurrentEmotion = () => {
  //刷新按钮：消息都在本地（后端只存了首条初始消息），直接对当前对话跑本地分析
  if (!message.value.some((msg) => msg.content && !msg.isError)) {
    ElMessage.warning("当前会话还没有对话内容");
    return;
  }
  refreshEmotionFromConversation();
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
  //riskLevel后端返回数字0/1/2（原代码||判断里0恰好falsy才侥幸落回low），本地分析给字符串：统一转换
  const rawRisk = source.riskLevel ?? source.risk;
  const riskLevel = (
    (typeof rawRisk === "number" ? ["low", "medium", "high"][rawRisk] : rawRisk) ||
    "low"
  ) as "low" | "medium" | "high";

  return {
    primaryEmotion,
    emotionScore,
    isNegative,
    summary:
      source.summary ||
      source.analysis ||
      source.riskDescription ||
      `当前会话主要呈现${primaryEmotion}情绪，强度为${emotionScore}。`,
    suggestion:
      source.suggestion ||
      source.advice ||
      (isNegative
        ? "建议先降低当前压力强度，再继续梳理具体困扰。"
        : "当前状态相对稳定，可以继续保持温和表达。"),
    riskLevel,
    actionItems:
      source.actionItems ||
      source.improvementSuggestions ||
      source.actions ||
      source.suggestions ||
      ["记录触发情绪的事件", "做一次 4-6 呼吸练习", "必要时联系可信任的人"],
  };
};

const formatUserMessageContent = (content: string) => {
  return content
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;")
    .replace(/\n/g, "<br>");
};

const getErrorMessage = (error: any) => {
  if (typeof error === "string") {
    return error;
  }
  return (
    error?.msg ||
    error?.message ||
    error?.data?.msg ||
    error?.data?.message ||
    "AI回复失败，请重试"
  );
};

const normalizeMessages = (data: any): ChatMessage[] => {
  if (Array.isArray(data)) {
    return data;
  }
  if (Array.isArray(data?.data)) {
    return data.data;
  }
  if (Array.isArray(data?.records)) {
    return data.records;
  }
  if (Array.isArray(data?.data?.records)) {
    return data.data.records;
  }
  if (Array.isArray(data?.messages)) {
    return data.messages;
  }
  if (Array.isArray(data?.data?.messages)) {
    return data.data.messages;
  }
  if (Array.isArray(data?.list)) {
    return data.list;
  }
  if (Array.isArray(data?.data?.list)) {
    return data.data.list;
  }
  if (data?.id && data?.content) {
    return [data];
  }
  return [];
};

const sendMessage = async () => {
  console.log("发送消息");
  // 在这里添加发送消息的逻辑
  if (!userInput.value.trim()) {
    return;
  }

  if (isAiTyping.value) {
    ElMessage.warning("AI正在思考，请稍后再发送消息");
    return;
  }
  //定义一个变量接受输入框信息
  const inputMessage = userInput.value.trim();
  //发送信息后会话框的信息置空
  userInput.value = "";

  //用户消息先上屏，AI回复流式追加在其后
  const userMessage: ChatMessage = {
    id: `user_${Date.now()}`,
    senderType: 1,
    content: inputMessage,
    createdAt: new Date().toISOString(),
  };
  message.value.push(userMessage);
  scrollChatToBottom(true);
  //后端AI服务故障期间消息存不进服务端：先按当前会话key落本地
  //（temp会话等session/start成功后再把消息迁移到真实会话key下）
  saveLocalMessage(
    currentSession.value?.sessionId ?? currentSession.value?.id ?? "",
    userMessage,
  );

  //没有历史会话
  if (currentSession.value?.status === "TEMP") {
    //构建会话参数
    const sessionParams = {
      initialMessage: inputMessage,
      sessionTitle: currentSession.value?.sessionTitle || "新会话",
    };

    if (currentSession.value?.sessionTitle === "新会话") {
      sessionParams.sessionTitle = `AI助手-${new Date().toLocaleString()}`;
    } else {
      sessionParams.sessionTitle =
        currentSession.value?.sessionTitle || "新会话";
    }

    //首字优先：不等后端建会话（慢的时候要好几秒，是最拖首字的一环），
    //先用temp key立刻开流式；会话转正在后台进行，成功后迁移本地消息桶
    const tempSessionId = currentSession.value?.sessionId ?? "temp_unknown";
    startAiResponse(tempSessionId);

    //转正请求单飞：连发消息时避免重复建会话
    if (!sessionCreatePromise) {
      sessionCreatePromise = startSession(sessionParams)
        .then((res) => {
          const sessionData = {
            sessionId: res.sessionId,
            status: res.status,
            sessionTitle: sessionParams.sessionTitle,
          };
          //将当前会话对象更新为新创建的会话
          if (currentSession.value?.status === "TEMP") {
            Object.assign(currentSession.value, sessionData);
          } else {
            currentSession.value = sessionData;
          }
          //temp会话转正：把存在temp桶里的消息搬到真实会话桶（合并）
          if (tempSessionId && tempSessionId !== sessionData.sessionId) {
            migrateLocalHistory(tempSessionId, sessionData.sessionId);
          }
          getSessionHistory();
        })
        .catch((error) => {
          //建会话失败不再拦着AI回答：消息留在temp桶，下一条消息会再次尝试转正
          ElMessage.warning("会话同步失败，消息暂存本地");
          console.error("创建会话失败", error);
        })
        .finally(() => {
          sessionCreatePromise = null;
        });
    }
  } else {
    const sessionId =
      currentSession.value?.sessionId ?? currentSession.value?.id;
    if (!sessionId) {
      ElMessage.warning("会话ID不存在，无法发送消息");
      return;
    }
    startAiResponse(sessionId);
  }
};

//打字机动画的requestAnimationFrame句柄（模块级，供错误处理和组件卸载时中断）
let typewriterRAF: number | null = null;

//temp会话转正请求的单飞句柄：连发消息时不重复调session/start
let sessionCreatePromise: Promise<void> | null = null;

//打字机基础速度（字符/帧）和追平积压所需的帧数，可按观感调整
const TYPEWRITER_BASE_SPEED = 2;
const TYPEWRITER_CATCHUP_FRAMES = 30;

//停止打字机动画
const stopTypewriter = () => {
  if (typewriterRAF !== null) {
    cancelAnimationFrame(typewriterRAF);
    typewriterRAF = null;
  }
};

//AI自检徽章的展开状态：已展开明细的消息id集合（Set也要reactive包装才能驱动视图）
const expandedVerifyIds = reactive(new Set<string>());
const toggleVerifyDetail = (id: number | string) => {
  const key = String(id);
  if (expandedVerifyIds.has(key)) {
    expandedVerifyIds.delete(key);
  } else {
    expandedVerifyIds.add(key);
  }
};

//自检徽章文案与明细：pass一行全绿；warn/fail可展开看具体声明（只列非supported项）
const verifyIcon = (verdict: string) =>
  verdict === "fail" ? "✗" : verdict === "warn" ? "⚠" : "✓";
const verifyLabel = (v: MessageVerify) => {
  if (v.verdict === "fail") {
    return `AI 自检：${v.unsupported.length} 条声明与资料不符`;
  }
  if (v.verdict === "warn") {
    return `AI 自检：${v.beyond} 条为资料外建议`;
  }
  return `AI 自检：${v.supported} 条声明均有依据`;
};
const verifyDetailClaims = (v: MessageVerify) =>
  (v.claims ?? []).filter((c) => c.status !== "supported");
const hasVerifyDetail = (v: MessageVerify) => verifyDetailClaims(v).length > 0;

//System Prompt 与知识库上下文组装已迁到服务端 rag.py（RAG_CHAT_SYSTEM_PROMPT /
//build_rag_context，措辞逐字保留），前端只负责展示，需要对照措辞去服务端看

//流式对话方法：走服务端RAG（agent-server /rag/chat，SSE：citations→token→done）。
//历史：课程后端 /psychological-chat/stream 故障（HTTP 200后挂起不出数据）且无追加消息接口，
//先改前端直连GLM，RAG迁服务端后统一走 /agent/rag/chat；本地持久化见 localChatHistory.ts
const startAiResponse = async (sessionId: number | string) => {
  if (isAiTyping.value) {
    ElMessage.warning("AI正在思考，请稍后再发送消息");
    return;
  }

  isAiTyping.value = true;

  //必须用reactive包装：打字机循环直接修改aiMessage.content才能触发视图更新，
  //普通对象push进响应式数组后，闭包里持有的仍是原始对象，改它不会重新渲染
  const aiMessage = reactive<ChatMessage>({
    id: `ai_${Date.now()}`,
    senderType: 2,
    content: "",
    createdAt: new Date().toISOString(),
  });
  message.value.push(aiMessage);
  scrollChatToBottom(true);

  //完整文本缓冲区：SSE到达的内容先积累在这里，页面按打字机节奏逐帧展示
  let fullText = "";
  //已展示到第几个字符
  let shownCount = 0;
  //流是否已结束（done后等缓冲区播完再收尾）
  let streamFinished = false;
  let controller = new AbortController(); //用来终止fetch请求

  //流式结束后的收尾：停动画、补全文本、解锁输入、存档、刷新情绪分析、断开连接
  const finishStream = () => {
    stopTypewriter();
    aiMessage.content = fullText;
    isAiTyping.value = false;
    //性能埋点：完整一轮的产出速度（全文耗时与出字速率）
    console.info(
      `[性能] 全文完成：${fullText.length}字 / ${Math.round(performance.now() - perf.start)}ms`,
    );
    //AI回复落本地：落库取"当时"的会话id——temp会话可能在流式期间已被后台转正
    const currentId =
      currentSession.value?.sessionId ?? currentSession.value?.id ?? sessionId;
    saveLocalMessage(currentId, { ...aiMessage });
    //流式结束后跑一轮情绪分析（agent-server /agent/analyze；后端会话没有语料可分析）
    refreshEmotionFromConversation();
    controller.abort();
  };

  //流正常结束（done事件/[DONE]标记/连接关闭）：等缓冲区播完再收尾
  const markStreamFinished = () => {
    streamFinished = true;
    if (typewriterRAF === null && shownCount >= fullText.length) {
      finishStream();
    }
  };

  //打字机循环：每帧从缓冲区取一小段字符追加显示，速度随积压量自适应
  const playTypewriter = () => {
    typewriterRAF = requestAnimationFrame(() => {
      typewriterRAF = null;
      const backlog = fullText.length - shownCount;
      if (backlog > 0) {
        //基础速度保证平滑；积压越多追得越快，约TYPEWRITER_CATCHUP_FRAMES帧内追平
        const speed = Math.max(
          TYPEWRITER_BASE_SPEED,
          Math.ceil(backlog / TYPEWRITER_CATCHUP_FRAMES),
        );
        shownCount = Math.min(fullText.length, shownCount + speed);
        //刚好切在emoji等代理对中间时多带一个字符，避免出现乱码
        if (
          shownCount < fullText.length &&
          fullText.charCodeAt(shownCount) >= 0xdc00 &&
          fullText.charCodeAt(shownCount) <= 0xdfff
        ) {
          shownCount++;
        }
        aiMessage.content = fullText.slice(0, shownCount);
        //打字机逐帧出字时跟随滚底（用户上翻时自动让位）
        scrollChatToBottom();
      }

      if (shownCount < fullText.length) {
        playTypewriter();
      } else if (streamFinished) {
        finishStream();
      }
      //缓冲区暂时播完且流未结束：先停下，等下一批SSE数据到达后再重启
    });
  };

  //RAG已在服务端完成：citations事件到达即引用就绪（检索+网络往返一跳）。
  //性能埋点保留三段式——首字耗时 = 服务端RAG检索 + 模型首token
  const perf = { start: performance.now(), ragDone: 0, firstToken: 0 };
  const lastUserInput =
    [...message.value].reverse().find((m) => Number(m.senderType) === 1)
      ?.content || "";

  //携带最近10条对话作为上下文（刚发出的这条单独走 message 字段，不重复进history）
  const history = message.value
    .filter((msg) => !msg.isError && msg.content)
    .slice(0, -1)
    .slice(-10)
    .map((msg) => ({
      role: (Number(msg.senderType) === 1 ? "user" : "assistant") as
        | "user"
        | "assistant",
      content: String(msg.content),
    }));

  try {
    //服务端RAG对话（SSE）：citations先到（引用卡片数据），token字流接打字机
    await ragChatStream(
      { message: lastUserInput, history },
      {
        onCitations: (citations) => {
          perf.ragDone = performance.now();
          //引用卡片数据挂到AI消息上：回答完成后展示，并随消息一起本地持久化
          aiMessage.citations = citations.map((c) => ({
            index: c.index,
            articleId: c.articleId,
            articleTitle: c.articleTitle,
            heading: c.heading,
          }));
        },
        onVerify: (v) => {
          //自检结果挂到AI消息上（与citations同款：完成后展示、随消息一起本地持久化）
          aiMessage.verify = v;
        },
        onDelta: (delta) => {
          //首个delta到达 = 模型首字：只记一次，打印分段耗时拆解
          if (!perf.firstToken) {
            perf.firstToken = performance.now();
            //无引用的消息没有citations时刻：不分段，避免负数耗时
            if (!perf.ragDone) {
              perf.ragDone = perf.firstToken;
            }
            console.info(
              `[性能] 首字总耗时 ${Math.round(perf.firstToken - perf.start)}ms` +
                `（服务端RAG ${Math.round(perf.ragDone - perf.start)}ms + 模型首token ${Math.round(perf.firstToken - perf.ragDone)}ms）`,
            );
          }
          //新内容先进缓冲区，再（重新）启动打字机逐帧展示
          fullText += delta;
          if (typewriterRAF === null) {
            playTypewriter();
          }
        },
        onDone: markStreamFinished,
      },
      controller.signal,
    );
  } catch (error) {
    if (fullText) {
      //中断时已产出部分内容：按正常结束收尾，不弹错误
      markStreamFinished();
    } else {
      handleError(error);
      controller.abort();
    }
  }
};

//错误处理函数
const handleError = (error: any) => {
  //先停掉打字机动画，避免错误提示被流式文本继续覆盖
  stopTypewriter();
  const errorMessage = getErrorMessage(error);
  //当前会话的AI消息
  const aiMessage = message.value[message.value.length - 1];
  if (aiMessage) {
    aiMessage.content = errorMessage;
    aiMessage.isError = true;
  }
  isAiTyping.value = false;
  ElMessage.error(errorMessage);
  console.error("AI响应出错", error);
};

const handleKeyDown = (event: KeyboardEvent) => {
  if (event.isComposing || event.shiftKey) {
    return;
  }

  if (event.key === "Enter") {
    event.preventDefault();
    sendMessage();
  }
};

//历史会话列表
const getSessionHistory = async () => {
  const historyData = await getSessionMessages({
    pageNum: 1,
    pageSize: 10,
  });
  sessionHistory.value = Array.isArray(historyData)
    ? historyData
    : historyData?.records || [];
};

//每轮对话后本地分析情绪：聊天走GLM直连后消息只在本地，课程后端只存了
//session/start的首条消息、分析不出东西；这里拿当前会话最近10条消息跑
//非流式GLM分析，结果字段与后端emotion接口对齐，复用同一套宽容归一化
const refreshEmotionFromConversation = async () => {
  const recent = message.value
    .filter((msg) => !msg.isError && msg.content)
    .slice(-10)
    .map((msg) => ({
      role: (Number(msg.senderType) === 1 ? "user" : "assistant") as
        | "user"
        | "assistant",
      content: String(msg.content),
    }));
  isEmotionLoading.value = true;
  try {
    const result = await analyzeEmotion(recent);
    if (result) {
      emotionGarden.value = normalizeEmotionGarden(result);
    }
  } catch (error) {
    //情绪面板是辅助信息：分析失败保持花园现状，不打断对话
    console.warn("本地情绪分析失败，花园保持上一状态", error);
  } finally {
    isEmotionLoading.value = false;
  }
};

const getEmotionSessionId = (session: SessionHistoryItem) => {
  const rawId = session.sessionId ?? session.id;
  if (!rawId) {
    return "";
  }

  const idText = String(rawId);
  return /^\d+$/.test(idText) ? `session_${idText}` : idText;
};

//点击历史会话列表
const handleSessionLink = async (session: SessionHistoryItem) => {
  currentSession.value = session;
  const sessionId = session.id ?? session.sessionId;
  if (!sessionId) {
    ElMessage.warning("会话ID不存在，无法获取消息");
    return;
  }
  try {
    const sessionMessages = await getSessionList(sessionId);
    //服务端历史 + 本地历史合并：服务端只存了session/start的首条用户消息，
    //直连LLM期间的用户消息和AI回复都在本地（见 localChatHistory.ts）
    message.value = mergeHistory(
      normalizeMessages(sessionMessages),
      //v2存储层是IndexedDB异步读取，这里必须等结果再合并
      await getLocalMessages(sessionId),
    );
    console.log("历史会话消息", sessionMessages);
    //历史消息合并渲染完成后贴底，看到的是最近对话
    nextTick(() => scrollChatToBottom(true));

    //更新当前会话数据，保留接口返回的原始ID字段
    currentSession.value = {
      ...session,
      sessionId: getEmotionSessionId(session),
      status: session.status || "ACTIVE",
    };
  } catch (error) {
    ElMessage.error("获取历史消息失败");
    console.error("获取历史消息失败", error);
    return;
  }

  //历史会话：消息刚合并进 message，直接本地分析（后端同样只有首条初始消息）
  refreshEmotionFromConversation();
};

//删除历史会话
const deleteHistory = async (session: SessionHistoryItem) => {
  const deleteId = session.id ?? session.sessionId;
  if (!deleteId) {
    ElMessage.warning("会话ID不存在，无法删除");
    return;
  }

  try {
    await deleteSession(deleteId);
    //同步清理该会话的本地历史，避免残留
    removeLocalHistory(deleteId);
    ElMessage.success("删除会话成功");
    await getSessionHistory();

    const currentId =
      currentSession.value?.id ?? currentSession.value?.sessionId;
    const deletedId = session.id ?? session.sessionId;
    if (currentId === deletedId) {
      creatNewFrontEndSession();
    }
  } catch (error) {
    ElMessage.error("删除会话失败");
    console.error("删除会话失败", error);
  }
};

onMounted(() => {
  // 页面加载时，自动创建一个新的会话
  creatNewFrontEndSession();
  getSessionHistory();
  //RAG预热已不需要：知识库在服务端，由 agent-server 启动时的 lifespan 后台灌库
});

onUnmounted(() => {
  //组件卸载时停止打字机动画，避免残留帧继续改数据
  stopTypewriter();
});
</script>

<template>
  <div class="consultation-container">
    <div class="sidebar">
      <div class="ai-assistant-info">
        <div class="breathing-circle">
          <el-image
            :src="iconUrl1"
            style="width: 25px; height: 25px"
            alt="AI助手"
          />
        </div>
        <h3 class="assistant-name">Junnnneal AI助手</h3>
        <div class="online-status">
          <div class="status-dot"></div>
          在线服务中
        </div>
      </div>
      <!-- 情绪花园 -->
      <div class="emotion-garden">
        <div class="garden-header">
          <div class="garden-title">
            <el-icon><Promotion /></el-icon>
            情绪花园
          </div>
          <el-button
            text
            circle
            size="small"
            :loading="isEmotionLoading"
            title="刷新情绪分析"
            @click="refreshCurrentEmotion"
          >
            <el-icon><Refresh /></el-icon>
          </el-button>
        </div>

        <div class="emotion-overview">
          <div
            class="emotion-orbit"
            :class="{
              negative: emotionGarden.isNegative,
              high: emotionGarden.riskLevel === 'high',
            }"
          >
            <div class="emotion-score">{{ emotionGarden.emotionScore }}</div>
            <div class="emotion-unit">情绪强度</div>
          </div>
          <div class="emotion-copy">
            <div class="emotion-name">{{ emotionGarden.primaryEmotion }}</div>
            <div class="emotion-summary">{{ emotionGarden.summary }}</div>
          </div>
        </div>

        <div class="emotion-meter">
          <div
            class="meter-fill"
            :style="{ width: `${emotionGarden.emotionScore}%` }"
          ></div>
        </div>

        <div class="warm-tips">
          <div class="emotion-status-text">
            <span class="status-label">当前状态</span>
            <span
              class="status-emotion"
              :class="{ attention: emotionGarden.isNegative }"
            >
              {{ getEmotionStatusText() }}
            </span>
          </div>
          <div class="emotion-intensity">
            <div class="intensity-dots">
              <span
                v-for="dot in 5"
                :key="dot"
                class="dot"
                :class="{ active: dot <= getEmotionDotCount() }"
              ></span>
            </div>
            <span class="intensity-text">
              {{ getEmotionLevelText(emotionGarden.emotionScore) }}
            </span>
          </div>
          <div class="warm-suggestion">
            <div class="suggestion-icon">✦</div>
            <div class="suggestion-content">
              <div class="suggestion-title">温和建议</div>
              <div class="suggestion-text">{{ emotionGarden.suggestion }}</div>
            </div>
          </div>
          <div class="healing-actions">
            <div class="actions-title">下一步可以做</div>
            <div class="actions-list">
              <div
                class="action-item"
                v-for="item in emotionGarden.actionItems"
                :key="item"
              >
                <span class="action-icon">✓</span>
                <span class="action-text">{{ item }}</span>
              </div>
            </div>
          </div>
          <div
            class="risk-notice"
            v-if="emotionGarden.isNegative || emotionGarden.riskLevel !== 'low'"
          >
            <div class="notice-icon">!</div>
            <div class="notice-content">
              <div class="notice-title">{{ getRiskText() }}</div>
              <div class="notice-text">
                如果这种感受持续加重，建议联系可信任的人或寻求专业支持。
              </div>
            </div>
          </div>
        </div>
      </div>
      <!-- 历史会话列表 -->
      <div class="session-history">
        <h4 class="session-title">会话列表</h4>
        <div class="session-list">
          <div
            v-for="session in sessionHistory"
            :key="session.id || session.sessionId"
            class="session-item"
            @click="handleSessionLink(session)"
          >
            <div class="session-info">
              <div class="session-title">
                <span>{{ session.sessionTitle }}</span>
                <div class="session-meta">
                  <span class="session-time">{{ session.startedAt }}</span>
                </div>
                <div class="session-preview">
                  {{ session.lastMessageContent || "暂无消息" }}
                </div>
                <div class="session-stats">
                  <span
                    ><el-icon><ChatRound /></el-icon
                    >{{ session.messageCount || 0 }}</span
                  >
                  <span>
                    <el-icon><Clock /></el-icon>
                    {{ formatDuration(session.durationMinutes) }}
                  </span>
                </div>
              </div>
              <div class="session-actions">
                <el-button
                  type="danger"
                  text
                  size="mini"
                  @click.stop="deleteHistory(session)"
                  ><el-icon><Delete /></el-icon
                ></el-button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
    <div class="chat-main">
      <div class="chat-header">
        <div class="header-left">
          <div class="chat-avatar">
            <el-image
              :src="iconUrl2"
              style="width: 30px; height: 30px"
              alt="爱心"
            />
          </div>
          <div class="chat-info">
            <h2>心理健康AI助手</h2>
            <p>为你提供专业的心理咨询服务</p>
          </div>
        </div>
        <el-button
          circle
          size="small"
          @click="creatNewFrontEndSession"
          title="新建会话"
        >
          <el-icon><Plus /></el-icon>
        </el-button>
      </div>
      <!-- 聊天区域 -->
      <div class="chat-messages" ref="chatMessagesRef">
        <!-- 欢迎用语：常驻第一条，不随对话开始而消失 -->
        <div class="message-item ai-message">
          <div class="message-avatar">
            <el-image
              :src="aiAvatarUrl"
              style="width: 20px; height: 20px"
              alt="机器人"
            />
          </div>
          <div class="message-content">
            <div class="message-bubble">
              <p>
                你好，我是心理健康AI助手。请告诉我你的困扰，我会尽力为你提供帮助。
              </p>
            </div>
          </div>
        </div>
        <!-- 历史会话消息 -->
        <div
          class="message-item"
          v-for="msg in message"
          :key="msg.id"
          :class="isUserMessage(msg) ? 'user-message' : 'ai-message'"
        >
          <div class="message-avatar">
            <el-image
              v-if="isUserMessage(msg)"
              :src="iconUrl3"
              style="width: 18px; height: 18px"
              :alt="msg.senderTypeDesc"
            />
            <el-image
              v-else
              :src="aiAvatarUrl"
              style="width: 20px; height: 20px"
              :alt="msg.senderTypeDesc"
            />
          </div>
          <div class="message-content">
            <div class="message-bubble">
              <!-- ai正在思考中效果 -->
              <div
                v-if="msg.senderType === 2 && isAiTyping && !msg.content"
                class="typing-indicator"
              >
                <div class="typing-dot"></div>
                <div class="typing-dot"></div>
                <div class="typing-dot"></div>
              </div>
              <!-- ai部分的错误提示 -->
              <div v-else-if="msg.isError" class="error-message">
                <p>{{ msg.content }}</p>
              </div>
              <!-- ai正常返回的消息 -->
              <MarkdownRenderer
                v-else-if="msg.senderType === 2 && !msg.isError"
                :content="msg.content"
                :is-ai-message="true"
              ></MarkdownRenderer>
              <p
                v-else-if="msg.content"
                v-html="formatUserMessageContent(msg.content)"
              ></p>
              <!-- RAG引用来源卡片：回答完成后展示参考的知识库文章出处 -->
              <div
                v-if="msg.citations?.length && msg.content && !msg.isError"
                class="citations"
              >
                <div class="citations-title">📚 参考来源</div>
                <div
                  v-for="c in msg.citations"
                  :key="c.index"
                  class="citation-card"
                >
                  <span class="citation-index">[{{ c.index }}]</span>
                  <span class="citation-text">
                    {{ c.articleTitle }} · {{ c.heading }}
                  </span>
                </div>
              </div>
              <!-- AI自检徽章：回答完成后的幻觉自检结果（后端自检失败不发verify帧，此处不渲染） -->
              <div
                v-if="msg.verify && msg.content && !msg.isError"
                class="ai-verify"
                :class="`verify-${msg.verify.verdict}`"
              >
                <button
                  type="button"
                  class="verify-summary"
                  :class="{ expandable: hasVerifyDetail(msg.verify) }"
                  @click="hasVerifyDetail(msg.verify) && toggleVerifyDetail(msg.id)"
                >
                  <span class="verify-icon">{{
                    verifyIcon(msg.verify.verdict)
                  }}</span>
                  <span class="verify-label">{{
                    verifyLabel(msg.verify)
                  }}</span>
                  <span
                    v-if="hasVerifyDetail(msg.verify)"
                    class="verify-arrow"
                    >{{
                      expandedVerifyIds.has(String(msg.id)) ? "▴" : "▾"
                    }}</span
                  >
                </button>
                <div
                  v-if="expandedVerifyIds.has(String(msg.id))"
                  class="verify-details"
                >
                  <div
                    v-for="(c, i) in verifyDetailClaims(msg.verify)"
                    :key="i"
                    class="verify-claim"
                    :class="`claim-${c.status}`"
                  >
                    <span class="claim-mark">{{
                      c.status === "unsupported" ? "✗" : "⚠"
                    }}</span>
                    <span class="claim-text">{{ c.text }}</span>
                  </div>
                  <div
                    v-if="msg.verify.alignment != null"
                    class="verify-alignment"
                  >
                    与来源相似度 {{ msg.verify.alignment.toFixed(2) }}
                  </div>
                </div>
              </div>
            </div>
            <!-- 时间戳放在气泡外，紧贴气泡下方 -->
            <div class="message-time">
              {{
                msg.senderType === 2 && isAiTyping
                  ? "正在输入中..."
                  : formatMsgTime(msg.createdAt)
              }}
            </div>
          </div>
        </div>
      </div>

      <!-- 输入区域 -->
      <div class="chat-input">
        <div class="input-container">
          <el-input
            v-model="userInput"
            placeholder="请输入你想要分享的内容..."
            size="large"
            type="textarea"
            :rows="3"
            :disabled="isAiTyping"
            @keydown="handleKeyDown"
            class="message-input"
            clearable
          />
          <div class="input-footer">
            <span>按Enter发送，Shift+Enter换行</span>
            <span>{{ userInput.length }} / 500</span>
          </div>
        </div>
        <el-button
          type="primary"
          class="send-btn"
          circle
          title="发送消息"
          @click="sendMessage"
          :disabled="!userInput.trim() || userInput.length > 500"
        >
          <el-icon><Promotion /></el-icon>
        </el-button>
      </div>
    </div>
  </div>
</template>

<style scoped lang="scss">
.consultation-container {
  margin: 0 auto;
  width: 1200px;
  height: calc(100dvh - 40px);
  min-height: 680px;
  display: flex;
  align-items: stretch;
  gap: 20px;
  padding: 20px;
  .sidebar {
    width: 320px;
    flex-shrink: 0;
    overflow-y: auto;
    overflow-x: hidden;
    .ai-assistant-info {
      margin-bottom: 20px;
      background: linear-gradient(
        135deg,
        rgba(255, 255, 255, 0.9) 0%,
        rgba(255, 252, 248, 0.95) 100%
      );
      border-radius: 16px;
      padding: 16px;
      box-shadow:
        0 8px 32px rgba(251, 146, 60, 0.06),
        0 2px 8px rgba(0, 0, 0, 0.04);
      border: 1px solid rgba(251, 146, 60, 0.08);
      backdrop-filter: blur(10px);
      transition: transform 260ms cubic-bezier(0.32, 0.72, 0, 1), opacity 260ms cubic-bezier(0.32, 0.72, 0, 1);
      .breathing-circle {
        width: 60px;
        height: 60px;
        background: linear-gradient(135deg, #fb923c 0%, #f59e0b 100%);
        border-radius: 50%;
        display: flex;
        align-items: center;
        justify-content: center;
        margin: 0 auto 12px;
        animation: breathing 4s ease-in-out infinite;
        box-shadow: 0 6px 24px rgba(251, 146, 60, 0.25);
        position: relative;
      }
      .assistant-name {
        font-size: 16px;
        font-weight: 700;
        background: linear-gradient(135deg, #fb923c, #f59e0b);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        text-align: center;
        background-clip: text;
        margin: 0 0 12px;
      }
      .online-status {
        display: flex;
        align-items: center;
        justify-content: center;
        color: #059669;
        font-size: 12px;
        font-weight: 600;
        .status-dot {
          width: 8px;
          height: 8px;
          background: #059669;
          border-radius: 50%;
          margin-right: 8px;
          animation: pulse 2s infinite;
          box-shadow: 0 0 8px rgba(5, 150, 105, 0.4);
        }
      }
    }
    .session-history {
      background: white;
      border-radius: 16px;
      padding: 16px;
      box-shadow: 0 2px 12px rgba(0, 0, 0, 0.1);
      margin-bottom: 20px;
      min-height: 250px;
      display: flex;
      flex-direction: column;
      .section-title {
        font-size: 16px;
        font-weight: 600;
        color: #333;
        margin: 0 0 16px;
        display: flex;
        align-items: center;
        justify-content: space-between;
      }
      .session-list {
        overflow-y: auto;
        overflow-x: hidden;
        max-height: 200px;
        scrollbar-width: thin;
        scrollbar-color: rgba(64, 150, 255, 0.3) transparent;
        .session-item {
          position: relative;
          display: block;
          padding: 12px 14px;
          margin-bottom: 8px;
          border-radius: 12px;
          cursor: pointer;
          transition: transform 260ms cubic-bezier(0.32, 0.72, 0, 1), background-color 260ms cubic-bezier(0.32, 0.72, 0, 1), border-color 260ms cubic-bezier(0.32, 0.72, 0, 1);
          border: 2px solid transparent;
          &:hover {
            background: #f8f9ff;
            border-color: #e6f0ff;
          }
          &.active {
            background: #e6f0ff;
            border-color: #4096ff;
          }
          .session-info {
            display: grid;
            grid-template-columns: minmax(0, 1fr) 24px;
            align-items: start;
            column-gap: 8px;
            width: 100%;
            min-width: 0;
            .session-title {
              min-width: 0;
              font-weight: 500;
              font-size: 14px;
              color: #333;
              line-height: 1.45;
              margin-bottom: 0;
              overflow: visible;
              white-space: normal;
              > span {
                display: block;
                padding-right: 4px;
                color: #111827;
                font-weight: 700;
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
              }
              .session-meta {
                display: flex;
                align-items: center;
                gap: 8px;
                margin: 2px 0 6px;
                .session-time {
                  font-size: 12px;
                  color: #999;
                  line-height: 1;
                }
              }
              .session-preview {
                width: 100%;
                font-size: 12px;
                color: #666;
                margin-bottom: 6px;
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
              }
              .session-stats {
                display: flex;
                align-items: center;
                gap: 12px;
                span {
                  font-size: 12px;
                  color: #999;
                  display: flex;
                  align-items: center;
                  gap: 4px;
                  line-height: 1;
                  .el-icon {
                    width: 13px;
                    height: 13px;
                  }
                }
              }
            }
            .session-actions {
              position: static;
              display: flex;
              justify-content: center;
              width: 24px;
              .el-button {
                width: 24px;
                height: 24px;
                padding: 0;
                margin: 0;
              }
            }
          }
        }
        .no-sessions-text {
          text-align: center;
          font-size: 14px;
          color: #999;
        }
      }
    }
    .emotion-garden {
      background: linear-gradient(
        135deg,
        #fef9e7 0%,
        #fcf4e6 50%,
        #f6f0e8 100%
      );
      border-radius: 20px;
      padding: 16px;
      margin-bottom: 20px;
      box-shadow: 0 8px 32px rgba(252, 244, 230, 0.8);
      border: 1px solid rgba(255, 255, 255, 0.2);
      position: relative;
      overflow: hidden;
      min-height: 300px;

      .garden-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        margin-bottom: 20px;
        position: relative;
        z-index: 2;
        .garden-title {
          display: flex;
          align-items: center;
          gap: 8px;
          font-size: 16px;
          font-weight: 600;
          color: #8b4513;
        }
        .el-button {
          color: #a16207;
        }
      }
      .emotion-overview {
        display: flex;
        align-items: center;
        gap: 14px;
        margin-bottom: 16px;
        .emotion-orbit {
          width: 92px;
          height: 92px;
          border-radius: 50%;
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          flex-shrink: 0;
          color: #7c2d12;
          background:
            radial-gradient(circle at center, #fffaf0 58%, transparent 60%),
            conic-gradient(#22c55e 0%, #facc15 50%, #fb7185 100%);
          box-shadow:
            inset 0 0 0 1px rgba(255, 255, 255, 0.8),
            0 10px 28px rgba(251, 146, 60, 0.18);
          &.negative {
            background:
              radial-gradient(circle at center, #fffaf0 58%, transparent 60%),
              conic-gradient(#f59e0b 0%, #fb7185 72%, #ef4444 100%);
          }
          &.high {
            color: #991b1b;
            box-shadow:
              inset 0 0 0 1px rgba(255, 255, 255, 0.8),
              0 10px 28px rgba(239, 68, 68, 0.24);
          }
        }
        .emotion-score {
          font-size: 26px;
          font-weight: 700;
          line-height: 1;
        }
        .emotion-unit {
          margin-top: 4px;
          font-size: 11px;
          color: #9a6b34;
        }
        .emotion-copy {
          flex: 1;
          min-width: 0;
          text-align: left;
          .emotion-name {
            font-size: 18px;
            font-weight: 700;
            color: #78350f;
            margin-bottom: 6px;
          }
          .emotion-summary {
            font-size: 12px;
            color: #7c6f5b;
            line-height: 1.5;
          }
        }
      }
      .emotion-meter {
        height: 8px;
        border-radius: 999px;
        background: rgba(120, 113, 108, 0.12);
        overflow: hidden;
        margin-bottom: 16px;
        .meter-fill {
          height: 100%;
          border-radius: inherit;
          background: linear-gradient(90deg, #22c55e 0%, #facc15 48%, #fb7185 100%);
          transition: width 0.3s ease;
        }
      }
      .warm-tips {
        text-align: left;
        .emotion-status-text {
          margin-bottom: 12px;
          display: flex;
          align-items: center;
          justify-content: space-between;
          .status-label {
            font-size: 14px;
            color: #8b7355;
            margin-right: 8px;
          }
          .status-emotion {
            font-size: 16px;
            font-weight: 600;
            padding: 4px 12px;
            border-radius: 16px;
            display: inline-block;
            color: #047857;
            background: rgba(16, 185, 129, 0.12);
            &.attention {
              color: #be123c;
              background: rgba(251, 113, 133, 0.14);
            }
          }
        }
        .emotion-intensity {
          margin-bottom: 16px;
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 8px;
          .intensity-dots {
            display: flex;
            gap: 4px;
            .dot {
              width: 8px;
              height: 8px;
              border-radius: 50%;
              background: #e0e0e0;
              transition: transform 260ms cubic-bezier(0.32, 0.72, 0, 1), background-color 260ms cubic-bezier(0.32, 0.72, 0, 1);
              &.active {
                background: linear-gradient(135deg, #ff9a9e, #fecfef);
                transform: scale(1.2);
                box-shadow: 0 2px 8px rgba(255, 154, 158, 0.4);
              }
            }
          }
          .intensity-text {
            font-size: 12px;
            color: #8b7355;
            font-weight: 500;
          }
        }
        .warm-suggestion {
          background: linear-gradient(
            135deg,
            rgba(255, 255, 255, 0.95),
            rgba(255, 255, 255, 0.8)
          );
          border-radius: 16px;
          padding: 12px;
          margin-bottom: 16px;
          display: flex;
          align-items: flex-start;
          gap: 10px;
          border: 1px solid rgba(255, 255, 255, 0.6);
          box-shadow: 0 6px 20px rgba(0, 0, 0, 0.08);
          .suggestion-icon {
            font-size: 20px;
            flex-shrink: 0;
            margin-top: 2px;
          }
          .suggestion-content {
            text-align: left;
            flex: 1;
            .suggestion-title {
              font-size: 14px;
              font-weight: 600;
              color: #8b7355;
              margin-bottom: 6px;
            }
            .suggestion-text {
              font-size: 13px;
              color: #6b5b47;
              line-height: 1.5;
            }
          }
        }
        .healing-actions {
          margin-bottom: 16px;
          .actions-title {
            display: flex;
            align-items: center;
            justify-content: flex-start;
            gap: 8px;
            font-size: 14px;
            font-weight: 600;
            color: #8b7355;
            margin-bottom: 16px;
          }
          .actions-list {
            display: flex;
            flex-direction: column;
            gap: 10px;
            .action-item {
              background: linear-gradient(
                135deg,
                rgba(255, 255, 255, 0.9),
                rgba(255, 255, 255, 0.7)
              );
              border-radius: 12px;
              padding: 12px;
              display: flex;
              align-items: center;
              gap: 10px;
              border: 1px solid rgba(255, 255, 255, 0.5);
              box-shadow: 0 4px 12px rgba(0, 0, 0, 0.06);
              text-align: left;
              .action-icon {
                width: 18px;
                height: 18px;
                border-radius: 50%;
                display: flex;
                align-items: center;
                justify-content: center;
                font-size: 12px;
                color: #047857;
                background: rgba(16, 185, 129, 0.12);
                flex-shrink: 0;
              }
              .action-text {
                font-size: 12px;
                color: #6b5b47;
                line-height: 1.4;
                flex: 1;
              }
            }
          }
        }
        .risk-notice {
          background: linear-gradient(135deg, #fff9e6, #ffeaa7);
          border-radius: 16px;
          padding: 16px;
          display: flex;
          align-items: flex-start;
          gap: 12px;
          border: 1px solid rgba(255, 234, 167, 0.6);
          box-shadow: 0 6px 20px rgba(255, 234, 167, 0.3);
          .notice-icon {
            font-size: 20px;
            flex-shrink: 0;
            margin-top: 2px;
          }
          .notice-content {
            flex: 1;
            .notice-title {
              font-size: 14px;
              font-weight: 600;
              color: #d4840f;
              margin-bottom: 6px;
            }
            .notice-text {
              font-size: 13px;
              color: #b8740c;
              line-height: 1.5;
            }
          }
        }
      }
    }
  }
  .chat-main {
    background: linear-gradient(
      135deg,
      rgba(255, 255, 255, 0.95) 0%,
      rgba(255, 252, 250, 0.98) 100%
    );
    border-radius: 20px;
    box-shadow:
      0 12px 40px rgba(251, 146, 60, 0.08),
      0 4px 16px rgba(0, 0, 0, 0.04);
    border: 1px solid rgba(251, 146, 60, 0.1);
    backdrop-filter: blur(10px);
    display: flex;
    flex-direction: column;
    overflow: hidden;
    flex: 1;
    min-width: 0;
    min-height: 0;
    .chat-header {
      background: linear-gradient(135deg, #fb923c 0%, #f59e0b 100%);
      color: white;
      padding: 20px 24px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      position: relative;
      flex-shrink: 0;
      .header-left {
        display: flex;
        align-items: center;
        .chat-avatar {
          width: 48px;
          height: 48px;
          background: rgba(255, 255, 255, 0.25);
          border-radius: 50%;
          display: flex;
          align-items: center;
          justify-content: center;
          margin-right: 16px;
          box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
          position: relative;
          z-index: 1;
        }
        .chat-info {
          h2 {
            font-size: 20px;
            font-weight: 700;
            margin-bottom: 4px;
          }
          p {
            font-size: 14px;
          }
        }
      }
    }
    .chat-messages {
      flex: 1;
      overflow-y: auto;
      padding: 24px;
      display: flex;
      flex-direction: column;
      gap: 16px;
      background: linear-gradient(
        135deg,
        rgba(255, 255, 255, 0.02) 0%,
        rgba(255, 252, 248, 0.05) 100%
      );
      min-height: 0;
      scrollbar-width: thin;
      scrollbar-color: rgba(251, 146, 60, 0.3) transparent;
      .message-item {
        display: flex;
        align-items: flex-start;
        gap: 12px;
        .message-avatar {
          width: 32px;
          height: 32px;
          border-radius: 50%;
          display: flex;
          align-items: center;
          justify-content: center;
          font-size: 14px;
          color: white;
          flex-shrink: 0;
        }
        &.ai-message {
          .message-avatar {
            background: linear-gradient(135deg, #fb923c, #f59e0b);
            box-shadow: 0 4px 12px rgba(251, 146, 60, 0.3);
          }
        }
        &.user-message {
          .message-avatar {
            background: linear-gradient(135deg, #6b7280, #4b5563);
            box-shadow: 0 4px 12px rgba(107, 114, 128, 0.3);
          }
          //时间戳移出气泡后：用户消息的时间跟随气泡右侧对齐
          .message-content .message-time {
            text-align: right;
          }
        }
        .message-content {
          max-width: 70%;
          .message-bubble {
            background: linear-gradient(
              135deg,
              rgba(255, 255, 255, 0.9) 0%,
              rgba(255, 252, 248, 0.95) 100%
            );
            border-radius: 16px;
            padding: 12px 16px;
            position: relative;
            animation: fadeInUp 0.4s ease-out;
            border: 1px solid rgba(251, 146, 60, 0.1);
            box-shadow: 0 4px 16px rgba(251, 146, 60, 0.05);
            .typing-indicator {
              display: flex;
              gap: 4px;
              padding: 8px 0;
              .typing-dot {
                width: 8px;
                height: 8px;
                background: #ccc;
                border-radius: 50%;
                animation: typing 1.5s ease-in-out infinite;
                &:nth-child(2) {
                  animation-delay: 0.2s;
                }
                &:nth-child(3) {
                  animation-delay: 0.4s;
                }
              }
            }
            /* 错误消息样式 */
            .error-message {
              background: linear-gradient(135deg, #fef2f2 0%, #fecaca 100%);
              border: 1px solid #f87171;
              border-radius: 12px;
              padding: 12px 16px;
              color: #991b1b;
              font-weight: 500;
              display: flex;
              align-items: center;
              gap: 8px;
            }
            /* RAG引用来源卡片 */
            .citations {
              margin-top: 10px;
              padding-top: 8px;
              border-top: 1px dashed rgba(251, 146, 60, 0.35);
              .citations-title {
                font-size: 12px;
                color: #b45309;
                font-weight: 600;
                margin-bottom: 6px;
                text-align: left;
              }
              .citation-card {
                display: flex;
                align-items: baseline;
                gap: 6px;
                padding: 4px 8px;
                margin-bottom: 4px;
                border-radius: 8px;
                background: rgba(251, 146, 60, 0.07);
                .citation-index {
                  font-size: 11px;
                  color: #fb923c;
                  font-weight: 700;
                  flex-shrink: 0;
                }
                .citation-text {
                  font-size: 12px;
                  color: #92400e;
                  line-height: 1.4;
                  text-align: left;
                }
              }
            }
            /* AI自检徽章（生成后幻觉自检）：三档配色 pass绿 / warn黄 / fail红 */
            .ai-verify {
              margin-top: 8px;
              padding-top: 8px;
              border-top: 1px dashed rgba(251, 146, 60, 0.35);
              .verify-summary {
                display: flex;
                align-items: center;
                gap: 6px;
                width: 100%;
                padding: 4px 8px;
                border: none;
                border-radius: 8px;
                background: rgba(34, 197, 94, 0.08);
                font-family: inherit;
                font-size: 12px;
                color: #15803d;
                cursor: default;
                text-align: left;
                &.expandable {
                  cursor: pointer;
                }
                .verify-icon {
                  font-weight: 700;
                  flex-shrink: 0;
                }
                .verify-arrow {
                  margin-left: auto;
                  opacity: 0.7;
                }
              }
              &.verify-warn .verify-summary {
                background: #fef9ec;
                color: #a16207;
              }
              &.verify-fail .verify-summary {
                background: #fdf0ef;
                color: #b91c1c;
              }
              .verify-details {
                margin-top: 6px;
                .verify-claim {
                  display: flex;
                  align-items: baseline;
                  gap: 6px;
                  padding: 4px 8px;
                  margin-bottom: 4px;
                  border-radius: 8px;
                  font-size: 12px;
                  line-height: 1.4;
                  &.claim-unsupported {
                    background: #fdf0ef;
                    color: #991b1b;
                  }
                  &.claim-beyond {
                    background: #fef9ec;
                    color: #92400e;
                  }
                  .claim-mark {
                    font-weight: 700;
                    flex-shrink: 0;
                  }
                }
                .verify-alignment {
                  font-size: 11px;
                  color: #b08968;
                  text-align: left;
                }
              }
            }
          }
          .message-time {
            font-size: 12px;
            color: #999;
            margin-top: 4px;
          }
        }
      }
    }
    .chat-input {
      border-top: 1px solid rgba(251, 146, 60, 0.1);
      padding: 20px 24px 22px;
      display: flex;
      gap: 14px;
      align-items: flex-end;
      background: linear-gradient(
        135deg,
        rgba(255, 255, 255, 0.5) 0%,
        rgba(255, 252, 248, 0.7) 100%
      );
      backdrop-filter: blur(10px);
      flex-shrink: 0;
      .input-container {
        flex: 1;
        min-width: 0;
        display: flex;
        flex-direction: column;
        gap: 6px;
        :deep(.el-textarea__inner) {
          min-height: 72px !important;
          padding: 12px 14px;
          line-height: 1.55;
          border-radius: 6px;
          box-shadow: none;
          resize: none;
        }
        :deep(.el-textarea__inner:focus) {
          box-shadow: 0 0 0 1px #fb923c inset;
        }
      }
      .input-footer {
        display: flex;
        justify-content: space-between;
        align-items: center;
        font-size: 12px;
        color: #78716c;
        font-weight: 500;
        line-height: 1;
        min-height: 16px;
      }
      .send-btn {
        height: 60px;
        width: 60px;
        margin: 0 0 22px;
        flex-shrink: 0;
        border-radius: 16px;
        background: linear-gradient(
          135deg,
          #fb923c 0%,
          #f59e0b 100%
        ) !important;
        border: none !important;
        box-shadow: 0 6px 20px rgba(251, 146, 60, 0.25);
        transition: transform 260ms cubic-bezier(0.32, 0.72, 0, 1), background-color 260ms cubic-bezier(0.32, 0.72, 0, 1);
      }
    }
  }
}
</style>

<style scoped lang="scss">
/* Specificity bridge: keep the legacy nested markup while replacing its warm defaults. */
.consultation-container .sidebar .emotion-garden { background: #fff; box-shadow: 0 16px 36px rgba(157, 93, 38, 0.07); }
.consultation-container .sidebar .emotion-garden .emotion-overview .emotion-orbit { color: var(--ink); background: radial-gradient(circle at center, #fff 58%, transparent 60%), conic-gradient(var(--sage) 0 58%, #facc15 58% 78%, #fb7185 78% 100%); box-shadow: inset 0 0 0 1px rgba(251,146,60,.14), 0 10px 24px rgba(251,146,60,.12); }
.consultation-container .sidebar .emotion-garden .emotion-overview .emotion-copy .emotion-name { color: var(--ink); }
.consultation-container .sidebar .emotion-garden .emotion-overview .emotion-copy .emotion-summary { color: var(--muted); }
.consultation-container .sidebar .emotion-garden .emotion-meter .meter-fill { background: linear-gradient(90deg, #22c55e, #facc15 52%, #fb7185); }
.consultation-container .sidebar .emotion-garden .warm-tips .warm-suggestion,
.consultation-container .sidebar .emotion-garden .warm-tips .healing-actions .action-item { background: #fffdf7; border-color: rgba(251,146,60,.12); box-shadow: none; }
.consultation-container .sidebar .emotion-garden .warm-tips .suggestion-title,
.consultation-container .sidebar .emotion-garden .warm-tips .actions-title { color: var(--ink); }
.consultation-container .sidebar .emotion-garden .warm-tips .suggestion-text,
.consultation-container .sidebar .emotion-garden .warm-tips .action-text { color: var(--muted); }
.consultation-container .sidebar .emotion-garden .warm-tips .risk-notice { background: #fff9e6; border-color: rgba(255,234,167,.7); box-shadow: none; }

.consultation-container .chat-main .chat-messages .message-item .message-content .message-bubble { background: #fff; border-color: var(--line); box-shadow: 0 10px 24px rgba(157,93,38,.06); }
.consultation-container .chat-main .chat-messages .message-item.user-message .message-content .message-bubble { background: var(--sage); border-color: transparent; }
.consultation-container .chat-main .chat-input .input-container :deep(.el-textarea__inner) { border-color: var(--line); background: #fffdfb; }
.consultation-container .chat-main .chat-input .send-btn { background: var(--sage) !important; box-shadow: 0 12px 24px rgba(251,146,60,.2); }
</style>

<style scoped lang="scss">
/* Soft structuralism overlay for the existing consultation workspace. */
.consultation-container {
  --ink: #3f2932;
  --muted: #806873;
  --sage: #b24662;
  --sage-soft: #f8e9ee;
  --line: rgba(178, 70, 98, 0.16);
  width: 100%;
  max-width: none;
  height: auto;
  min-height: calc(100dvh - 70px);
  /*对话区不再被长侧栏拉伸：各自取自然高度，chat-main单独锁到视口高 */
  align-items: flex-start;
  /* Full-bleed background, centered content rail (like the emotion diary page). */
  padding: clamp(0.75rem, 2vw, 1.35rem)
    max(21.6px, calc((100% - 1360px) / 2 + 21.6px));
  gap: clamp(0.75rem, 2vw, 1.25rem);
  box-sizing: border-box;
  background:
    radial-gradient(circle at 12% 0%, rgba(226, 175, 190, 0.45), transparent 32%),
    #fdf8fa;
  color: var(--ink);
}

.consultation-container .sidebar {
  width: clamp(250px, 25vw, 320px);
  scrollbar-width: thin;
  scrollbar-color: rgba(178,70,98,.24) transparent;
  /*与chat-main同高、锁到视口底：侧栏内容多时内部滚动，不再把页面撑长 */
  height: calc(100dvh - 70px - 2 * clamp(0.75rem, 2vw, 1.35rem));
  overflow-y: auto;
}

.consultation-container .sidebar .ai-assistant-info,
.consultation-container .sidebar .emotion-garden,
.consultation-container .sidebar .session-history,
.consultation-container .chat-main {
  border: 1px solid var(--line);
  box-shadow: 0 16px 36px rgba(95, 42, 58, 0.08);
}

.consultation-container .sidebar .ai-assistant-info {
  padding: 1.35rem 1rem;
  border-radius: 1.15rem;
  background: rgba(255,255,255,.82);
  backdrop-filter: none;
}
.consultation-container .sidebar .ai-assistant-info .breathing-circle {
  width: 4.1rem;
  height: 4.1rem;
  margin-bottom: 0.8rem;
  background: var(--sage-soft);
  box-shadow: inset 0 0 0 1px rgba(178,70,98,.18), 0 14px 26px rgba(178,70,98,.16);
}
.consultation-container .sidebar .ai-assistant-info .assistant-name {
  color: var(--ink);
  background: none;
  -webkit-text-fill-color: initial;
  font-size: 1rem;
  letter-spacing: -0.02em;
}
.consultation-container .sidebar .ai-assistant-info .online-status { color: var(--sage); }
.consultation-container .sidebar .ai-assistant-info .online-status .status-dot { background: var(--sage); box-shadow: none; }

.consultation-container .sidebar .emotion-garden {
  padding: 1.15rem;
  border-radius: 1.15rem;
  background: #fff;
  box-shadow: 0 16px 36px rgba(95, 42, 58, 0.07);
}
.consultation-container .emotion-garden .garden-header { margin-bottom: 1.1rem; }
.consultation-container .emotion-garden .garden-title { color: var(--ink); font-size: .9rem; }
.consultation-container .emotion-garden .garden-title .el-icon { color: var(--sage); }
.consultation-container .emotion-garden .emotion-overview { gap: 0.8rem; }
.consultation-container .emotion-garden .emotion-orbit {
  width: 5.2rem;
  height: 5.2rem;
  color: var(--ink);
  background: radial-gradient(circle at center, #fff 58%, transparent 60%), conic-gradient(var(--sage) 0 58%, #facc15 58% 78%, #fb7185 78% 100%);
  box-shadow: inset 0 0 0 1px rgba(178,70,98,.14), 0 10px 24px rgba(178,70,98,.12);
}
.consultation-container .emotion-garden .emotion-score { font-size: 1.6rem; font-variant-numeric: tabular-nums; }
.consultation-container .emotion-garden .emotion-unit { color: var(--muted); }
.consultation-container .emotion-garden .emotion-copy .emotion-name { color: var(--ink); font-size: 1.05rem; }
.consultation-container .emotion-garden .emotion-copy .emotion-summary { color: var(--muted); }
.consultation-container .emotion-garden .emotion-meter { height: 0.42rem; background: #f4e3e9; }
.consultation-container .emotion-garden .emotion-meter .meter-fill { background: linear-gradient(90deg, #22c55e, #facc15 52%, #fb7185); }
.consultation-container .emotion-garden .warm-tips .status-label,
.consultation-container .emotion-garden .warm-tips .intensity-text { color: var(--muted); }
.consultation-container .emotion-garden .warm-tips .status-emotion { color: var(--sage); background: var(--sage-soft); }
.consultation-container .emotion-garden .warm-tips .status-emotion.attention { color: #a65347; background: #fff0ec; }
.consultation-container .emotion-garden .warm-tips .intensity-dots .dot { background: #ead9df; }
.consultation-container .emotion-garden .warm-tips .intensity-dots .dot.active { background: var(--sage); box-shadow: 0 2px 8px rgba(178,70,98,.22); }
.consultation-container .emotion-garden .warm-suggestion,
.consultation-container .emotion-garden .healing-actions .action-item { background: #fdf9fa; border: 1px solid rgba(178,70,98,.1); box-shadow: none; }
.consultation-container .emotion-garden .suggestion-icon { color: var(--sage); }
.consultation-container .emotion-garden .suggestion-title,
.consultation-container .emotion-garden .actions-title { color: var(--ink); }
.consultation-container .emotion-garden .suggestion-text,
.consultation-container .emotion-garden .action-text { color: var(--muted); }
.consultation-container .emotion-garden .action-icon { color: var(--sage); background: var(--sage-soft); }
.consultation-container .emotion-garden .risk-notice { background: #fff6ed; border-color: rgba(200,120,59,.22); box-shadow: none; }
.consultation-container .emotion-garden .notice-title { color: #a66231; }
.consultation-container .emotion-garden .notice-text { color: #986b4c; }

.consultation-container .sidebar .session-history {
  padding: 1rem;
  border-radius: 1.15rem;
  background: rgba(255,255,255,.82);
  box-shadow: 0 16px 36px rgba(95, 42, 58, 0.06);
}
.consultation-container .session-history .session-title { color: var(--ink); font-size: .9rem; }
.consultation-container .session-history .session-item { border: 1px solid transparent; border-radius: .8rem; transition: transform 240ms cubic-bezier(0.32,0.72,0,1), background-color 240ms cubic-bezier(0.32,0.72,0,1), border-color 240ms cubic-bezier(0.32,0.72,0,1); }
.consultation-container .session-history .session-item:hover { transform: translateX(3px); background: #f9eef2; border-color: var(--line); }
.consultation-container .session-history .session-title > span { color: var(--ink); }
.consultation-container .session-history .session-preview,
.consultation-container .session-history .session-time,
.consultation-container .session-history .session-stats span { color: var(--muted); }

.consultation-container .chat-main {
  border-radius: 1.35rem;
  background: #fff;
  backdrop-filter: none;
  /*高度锁定到视口底部（容器min-height 100dvh-70px 减上下padding）：
    输入框始终贴着页面底部，消息超出时由 .chat-messages 内部滚动 */
  height: calc(100dvh - 70px - 2 * clamp(0.75rem, 2vw, 1.35rem));
  flex-shrink: 0;
}
.consultation-container .chat-main .chat-header {
  padding: 1rem clamp(1rem, 3vw, 1.6rem);
  background: linear-gradient(135deg, #b24662 0%, #7f334a 100%);
  color: #fff;
  border-bottom: 1px solid var(--line);
}
.consultation-container .chat-main .chat-header .chat-avatar { width: 2.8rem; height: 2.8rem; margin-right: .8rem; background: var(--sage-soft); box-shadow: none; }
.consultation-container .chat-main .chat-header .chat-info h2 { color: #fff; font-size: 1.05rem; }
.consultation-container .chat-main .chat-header .chat-info p { color: rgba(255,255,255,.82); font-size: .76rem; }
.consultation-container .chat-main .chat-header > .el-button { color: #fff; border-color: rgba(255,255,255,.38); background: rgba(255,255,255,.14); }
.consultation-container .chat-main .chat-messages {
  padding: clamp(1rem, 3vw, 1.75rem);
  gap: 1.15rem;
  background: #fefafb;
  scrollbar-color: rgba(178,70,98,.22) transparent;
}
.consultation-container .chat-messages .message-avatar { border-radius: .7rem; background: var(--sage-soft) !important; box-shadow: none !important; }
.consultation-container .chat-messages .message-content { max-width: min(72%, 48rem); }
.consultation-container .chat-messages .message-bubble {
  border-radius: .35rem 1rem 1rem 1rem;
  padding: .85rem 1rem;
  background: #fff;
  border: 1px solid var(--line);
  box-shadow: 0 10px 24px rgba(95,42,58,.06);
  animation: consultation-in 420ms cubic-bezier(0.32,.72,0,1) both;
}
.consultation-container .chat-messages .user-message { flex-direction: row-reverse; }
.consultation-container .chat-messages .user-message .message-bubble { border-radius: 1rem .35rem 1rem 1rem; background: var(--sage); color: #fff; border-color: transparent; }
.consultation-container .chat-messages .message-time { color: #967b86; }
.consultation-container .chat-messages .citations { border-top-color: rgba(178,70,98,.2); }
.consultation-container .chat-messages .citation-card { background: #f9edf1; }
.consultation-container .chat-messages .citations-title { color: var(--sage); }
.consultation-container .chat-messages .ai-verify { border-top-color: rgba(178,70,98,.2); }
.consultation-container .chat-messages .citation-text { color: #68525c; }

.consultation-container .chat-main .chat-input {
  gap: .8rem;
  padding: .8rem clamp(1rem, 3vw, 1.6rem) 1rem;
  border-top-color: var(--line);
  background: #fff;
  backdrop-filter: none;
}
.consultation-container .chat-input .input-container :deep(.el-textarea__inner) { min-height: 4.4rem !important; border: 1px solid var(--line); border-radius: .85rem; background: #fdf9fa; color: var(--ink); transition: box-shadow 220ms cubic-bezier(.32,.72,0,1), border-color 220ms cubic-bezier(.32,.72,0,1); }
.consultation-container .chat-input .input-container :deep(.el-textarea__inner:focus) { border-color: rgba(178,70,98,.45); box-shadow: 0 0 0 3px rgba(178,70,98,.12) !important; }
.consultation-container .chat-input .input-footer { color: #806873; }
.consultation-container .chat-input .send-btn { width: 3.35rem; height: 3.35rem; margin-bottom: 1.35rem; border-radius: 1rem; background: var(--sage) !important; box-shadow: 0 12px 24px rgba(178,70,98,.2); transition: transform 240ms cubic-bezier(.32,.72,0,1), background-color 240ms cubic-bezier(.32,.72,0,1); }
.consultation-container .chat-input .send-btn:hover { background: #91384f !important; transform: translateY(-2px); }
.consultation-container .chat-input .send-btn:active { transform: scale(.97); }

@keyframes consultation-in { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }

@media (max-width: 920px) {
  .consultation-container { width: 100%; height: auto; min-height: calc(100dvh - 60px); flex-direction: column; }
  .consultation-container .sidebar { width: 100%; height: auto; max-height: none; overflow: visible; display: grid; grid-template-columns: repeat(2, minmax(0,1fr)); gap: .8rem; }
  .consultation-container .sidebar .ai-assistant-info { grid-column: 1 / -1; margin-bottom: 0; }
  .consultation-container .sidebar .emotion-garden, .consultation-container .sidebar .session-history { margin-bottom: 0; }
  .consultation-container .chat-main { min-height: 70dvh; }
}
@media (max-width: 600px) {
  .consultation-container { padding: .65rem; }
  .consultation-container .sidebar { display: flex; flex-direction: column; }
  .consultation-container .sidebar .ai-assistant-info { padding: 1rem; }
  .consultation-container .sidebar .emotion-garden { order: 2; }
  .consultation-container .sidebar .session-history { order: 3; }
  .consultation-container .chat-main .chat-header { padding: .8rem 1rem; }
  .consultation-container .chat-main .chat-messages { padding: .9rem; }
  .consultation-container .chat-messages .message-content { max-width: calc(100% - 2.75rem); }
  .consultation-container .chat-input { align-items: stretch; flex-wrap: wrap; }
  .consultation-container .chat-input .input-container { flex-basis: 100%; }
  .consultation-container .chat-input .send-btn { margin-left: auto; margin-bottom: 0; }
}
@media (prefers-reduced-motion: reduce) { .consultation-container .message-bubble, .consultation-container .breathing-circle, .consultation-container .status-dot { animation: none; } }
</style>
