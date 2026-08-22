<script setup lang="ts">
import { nextTick, reactive, ref } from "vue";
import { ElMessage } from "element-plus";
import { Promotion, VideoPause } from "@element-plus/icons-vue";

/**
 * AI健康管家：不只是聊天，而是把 LangGraph Agent 的决策过程可视化。
 * 后端 astream_events 翻译出的 SSE 协议：
 *   token      → 正在生成的回答字流（打字机）
 *   tool_start → Agent 决定调用某个工具（渲染成"思考步骤"卡片）
 *   tool_end   → 工具返回结果，填进对应卡片
 *   done/error → 结束
 */

interface ThoughtSegment {
  kind: "thought";
  toolName: string;
  args: Record<string, unknown>;
  result?: string;
  running: boolean;
}
interface AnswerSegment {
  kind: "answer";
  text: string;
}
type Segment = ThoughtSegment | AnswerSegment;

interface ChatMsg {
  role: "user" | "assistant";
  content: string;
  segments?: Segment[];
  isError?: boolean;
}

// 工具元信息：SSE里的工具名 → 用户能看懂的步骤名与参数摘要
const TOOL_META: Record<string, { icon: string; label: string }> = {
  search_knowledge: { icon: "🔍", label: "检索心理健康知识库" },
  get_emotion_analysis: { icon: "📊", label: "分析最近的咨询情绪" },
  get_recent_sessions: { icon: "📋", label: "查询咨询历史" },
  save_emotion_diary: { icon: "📝", label: "写入情绪日记" },
};

const messages = ref<ChatMsg[]>([]);
const userInput = ref("");
const streaming = ref(false);
const listRef = ref<HTMLElement>();
let abortController: AbortController | null = null;
//线上已通过 Render 部署 agent-server + Netlify agent.mjs 转发，/agent/chat 可用

const SUGGESTIONS = [
  "我最近总是失眠，有什么科学的改善方法？",
  "帮我看看我最近的情绪状态怎么样",
  "帮我记一条情绪日记：今天有点焦虑，心情大概40分",
];

const summarizeArgs = (name: string, args: Record<string, unknown>): string => {
  const query = args.query ?? args.dominant_emotion ?? args.limit;
  return query !== undefined ? String(query) : "";
};

//自动滚底：force=新消息直接贴底；流式更新只在用户本来就在底部附近才跟随，
//避免上翻阅读思考过程时被逐块SSE拽回底部
const scrollToBottom = async (force = false) => {
  await nextTick();
  const el = listRef.value;
  if (!el) return;
  const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 120;
  if (force || nearBottom) el.scrollTop = el.scrollHeight;
};

const currentAssistant = (): ChatMsg | null => {
  const last = messages.value[messages.value.length - 1];
  return last?.role === "assistant" ? last : null;
};

const handleSseEvent = (msg: ChatMsg, data: Record<string, unknown>) => {
  const segments = msg.segments ?? (msg.segments = []);
  switch (data.type) {
    case "tool_start": {
      segments.push({
        kind: "thought",
        toolName: String(data.name ?? ""),
        args: (data.args as Record<string, unknown>) ?? {},
        running: true,
      });
      break;
    }
    case "tool_end": {
      // 关掉最近一个同名且还在执行中的步骤卡片
      for (let i = segments.length - 1; i >= 0; i--) {
        const seg = segments[i];
        if (!seg || seg.kind !== "thought") continue;
        if (seg.running && seg.toolName === data.name) {
          seg.result = String(data.result ?? "");
          seg.running = false;
          break;
        }
      }
      break;
    }
    case "token": {
      // 字流永远落在末尾：末尾是思考卡片就新开一段回答
      const last = segments[segments.length - 1];
      if (last?.kind === "answer") last.text += String(data.text ?? "");
      else segments.push({ kind: "answer", text: String(data.text ?? "") });
      msg.content = segments
        .filter((s): s is AnswerSegment => s.kind === "answer")
        .map((s) => s.text)
        .join("");
      break;
    }
  }
};

const send = async (text?: string) => {
  const content = (text ?? userInput.value).trim();
  if (!content || streaming.value) return;
  userInput.value = "";
  messages.value.push({ role: "user", content });
  //必须用reactive包装：SSE回调直接改segments才会触发视图更新，
  //普通对象push进响应式数组后闭包持有的仍是原始对象，改它不重渲染——
  //症状就是整段答案在流结束时一次性出现（不是流式）
  const assistantMsg = reactive<ChatMsg>({
    role: "assistant",
    content: "",
    segments: [],
  });
  messages.value.push(assistantMsg);
  streaming.value = true;
  scrollToBottom(true);

  // 带上最近10轮对话（只要正文，思考过程不回传）
  const history = messages.value
    .slice(0, -2)
    .filter((m) => m.content && !m.isError)
    .slice(-10)
    .map((m) => ({ role: m.role, content: m.content }));

  abortController = new AbortController();
  try {
    const res = await fetch("/agent/chat", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        token: localStorage.getItem("token") ?? "",
      },
      body: JSON.stringify({ message: content, history }),
      signal: abortController.signal,
    });
    if (!res.ok || !res.body) throw new Error(`HTTP ${res.status}`);

    // 原生流式解析SSE：buffer暂存半行，按\n切割逐条处理
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let finished = false;
    while (!finished) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() ?? "";
      for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed.startsWith("data:")) continue;
        try {
          const data = JSON.parse(trimmed.slice(5).trim());
          if (data.type === "done") finished = true;
          else if (data.type === "error") {
            assistantMsg.isError = true;
            assistantMsg.content = String(data.message ?? "Agent 执行出错");
          } else handleSseEvent(assistantMsg, data);
        } catch {
          // 半包JSON下一轮拼接，忽略
        }
        scrollToBottom();
      }
    }
    if (!assistantMsg.content && !assistantMsg.isError) {
      assistantMsg.isError = true;
      assistantMsg.content = "回复为空，请重试";
    }
  } catch (e) {
    if ((e as Error).name !== "AbortError") {
      assistantMsg.isError = true;
      assistantMsg.content = "Agent 服务连接失败，请确认本地服务已启动";
      ElMessage.error("AI健康管家服务暂不可用");
    }
  } finally {
    streaming.value = false;
    abortController = null;
    scrollToBottom();
  }
};

const stop = () => {
  abortController?.abort();
};
</script>

<template>
  <div class="butler-page">
    <header class="butler-header">
      <div class="header-info">
        <h1>AI 健康管家</h1>
        <p>不只是回答——你能看到它每一步在查什么、做什么决定</p>
      </div>
      <div class="agent-badge">
        <span class="dot" :class="{ busy: streaming }"></span>
        {{ streaming ? "思考中…" : "Agent 就绪" }}
      </div>
    </header>

    <div class="chat-list" ref="listRef">
      <div v-if="messages.length === 0" class="empty-state">
        <div class="empty-icon">🧠</div>
        <h3>我是你的 AI 健康管家</h3>
        <p>我可以检索心理知识库、分析你的咨询情绪、帮你记录心情日记</p>
        <div class="suggestions">
          <button
            v-for="s in SUGGESTIONS"
            :key="s"
            class="suggestion-chip"
            @click="send(s)"
          >
            {{ s }}
          </button>
        </div>
      </div>

      <div
        v-for="(msg, idx) in messages"
        :key="idx"
        class="msg-row"
        :class="msg.role"
      >
        <div class="avatar">{{ msg.role === "user" ? "🙂" : "🤖" }}</div>
        <div class="bubble" :class="{ error: msg.isError }">
          <template v-if="msg.role === 'assistant' && msg.segments?.length">
            <!-- 思考步骤卡片：Agent 的工具调用过程 -->
            <div
              v-for="(seg, si) in msg.segments"
              :key="si"
              :class="[
                seg.kind === 'thought' ? 'thought-card' : 'answer-seg',
                { running: seg.kind === 'thought' && seg.running },
              ]"
            >
              <template v-if="seg.kind === 'thought'">
                <div class="thought-head">
                  <span class="thought-icon">{{
                    TOOL_META[seg.toolName]?.icon ?? "🛠"
                  }}</span>
                  <span class="thought-label">
                    {{ TOOL_META[seg.toolName]?.label ?? seg.toolName }}
                  </span>
                  <span
                    v-if="summarizeArgs(seg.toolName, seg.args)"
                    class="thought-arg"
                  >
                    「{{ summarizeArgs(seg.toolName, seg.args) }}」
                  </span>
                  <span v-if="seg.running" class="spinner"></span>
                  <span v-else class="thought-done">✓</span>
                </div>
                <pre v-if="seg.result" class="thought-result">{{
                  seg.result
                }}</pre>
              </template>
              <!-- 回答段落 -->
              <pre v-else class="answer-text">{{ seg.text }}</pre>
            </div>
          </template>
          <pre v-else class="answer-text">{{ msg.content }}</pre>
          <div
            v-if="
              msg.role === 'assistant' &&
              streaming &&
              idx === messages.length - 1
            "
            class="cursor"
          >
            ▌
          </div>
        </div>
      </div>
    </div>

    <footer class="input-bar">
      <el-input
        v-model="userInput"
        placeholder="说说你的困扰，或让管家帮你查一查、记一记…"
        :disabled="streaming"
        @keyup.enter="send()"
        clearable
      />
      <el-button
        v-if="streaming"
        type="warning"
        :icon="VideoPause"
        round
        @click="stop"
      >
        停止
      </el-button>
      <el-button
        v-else
        type="primary"
        :icon="Promotion"
        round
        :disabled="!userInput.trim()"
        @click="send()"
      >
        发送
      </el-button>
    </footer>
  </div>
</template>

<style scoped lang="scss">
.butler-page {
  --ink: #3d2e27;
  --muted: #846a5d;
  --line: rgba(173, 87, 42, 0.2);
  --surface: #ffffff;
  --wash: #fdf7f3;
  display: flex;
  flex-direction: column;
  /*锁死高度而非min-height：chat-list 才会成为内部滚动容器，
    流式时 scrollToBottom 才真正生效；页脚保持在页面最底 */
  height: calc(100dvh - 70px);
  background:
    radial-gradient(
      circle at 88% 4%,
      rgba(225, 180, 149, 0.42),
      transparent 32%
    ),
    var(--wash);
  color: var(--ink);
}

.butler-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: clamp(1rem, 3vw, 1.7rem) 170.5px;
  border-bottom: 1px solid var(--line);
  background: rgba(255, 255, 255, 0.72);

  h1 {
    margin: 0;
    font-size: clamp(1.2rem, 2vw, 1.65rem);
    letter-spacing: -0.03em;
    color: var(--ink);
  }
  p {
    max-width: 52ch;
    margin: 0.35rem 0 0;
    font-size: 0.8rem;
    color: var(--muted);
  }
}

.agent-badge {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 0.45rem 0.75rem;
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.82);
  border: 1px solid var(--line);
  font-size: 0.76rem;
  color: #93451f;
  font-weight: 650;

  .dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: #22c55e;

    &.busy {
      background: #ba632e;
      animation: pulse 0.9s infinite;
    }
  }
}

@keyframes pulse {
  50% {
    opacity: 0.3;
  }
}

.chat-list {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  width: min(920px, calc(100% - 2rem));
  margin: 0 auto;
  padding: clamp(1.3rem, 4vw, 2.5rem) 0;
}

.empty-state {
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 0.7rem;
  padding: 2rem 1rem;
  text-align: center;

  .empty-icon {
    display: grid;
    place-items: center;
    width: 4.4rem;
    height: 4.4rem;
    margin-bottom: 0.6rem;
    border-radius: 1.35rem;
    background: #f7e8de;
    color: #9f4b25;
    font-size: 2.2rem;
    filter: saturate(0.7);
  }
  h3 {
    margin: 0;
    color: var(--ink);
    letter-spacing: -0.025em;
  }
  p {
    max-width: 36rem;
    margin: 0 0 1.1rem;
    color: var(--muted);
    font-size: 0.9rem;
    line-height: 1.65;
  }
}

.suggestions {
  display: flex;
  flex-direction: column;
  gap: 0.65rem;

  .suggestion-chip {
    width: min(100%, 34rem);
    padding: 0.75rem 1rem;
    border-radius: 0.9rem;
    border: 1px solid var(--line);
    background: rgba(255, 255, 255, 0.86);
    color: #9f4b25;
    font-size: 0.82rem;
    text-align: left;
    cursor: pointer;
    transition:
      transform 240ms cubic-bezier(0.32, 0.72, 0, 1),
      background-color 240ms cubic-bezier(0.32, 0.72, 0, 1),
      border-color 240ms cubic-bezier(0.32, 0.72, 0, 1);

    &:hover {
      background: #fff;
      border-color: rgba(183, 89, 44, 0.55);
      transform: translateX(4px);
    }
    &:focus-visible {
      outline: 3px solid rgba(183, 89, 44, 0.25);
      outline-offset: 2px;
    }
  }
}

.msg-row {
  display: flex;
  gap: 0.75rem;
  margin-bottom: 1.15rem;
  animation: message-in 420ms cubic-bezier(0.32, 0.72, 0, 1) both;

  .avatar {
    flex-shrink: 0;
    width: 2.2rem;
    height: 2.2rem;
    border-radius: 0.8rem;
    background: #f8ebe3;
    border: 1px solid rgba(183, 89, 44, 0.16);
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 1rem;
  }

  &.user {
    flex-direction: row-reverse;

    .bubble {
      background: #b7592c;
      color: #fff;
      border-radius: 1rem 0.3rem 1rem 1rem;
    }
  }

  .bubble {
    max-width: min(78%, 46rem);
    padding: 0.9rem 1.05rem;
    border-radius: 0.3rem 1rem 1rem 1rem;
    background: var(--surface);
    border: 1px solid #ead4c7;
    box-shadow: 0 12px 28px rgba(92, 48, 29, 0.07);

    &.error {
      border-color: #fca5a5;
      background: #fef2f2;

      .answer-text {
        color: #991b1b;
      }
    }
  }
}

.answer-text {
  margin: 0;
  font-family: inherit;
  font-size: 0.9rem;
  line-height: 1.75;
  white-space: pre-wrap;
  word-break: break-word;
  color: #3d2e27;
}

.thought-card {
  margin-bottom: 10px;
  padding: 0.7rem 0.8rem;
  border-radius: 0.8rem;
  background: var(--surface);
  border: 1px dashed #cf8a62;

  &.running {
    border-style: solid;
    border-color: #b7592c;
    background: #f8ebe3;
  }
}

.answer-seg {
  margin-bottom: 10px;
}

.thought-head {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: #80513a;
  flex-wrap: wrap;

  .thought-arg {
    color: #9f4b25;
  }

  .thought-done {
    margin-left: auto;
    color: #059669;
  }
}

.spinner {
  margin-left: auto;
  width: 12px;
  height: 12px;
  border: 2px solid #b7592c;
  border-top-color: transparent;
  border-radius: 50%;
  animation: spin 0.7s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

.thought-result {
  margin: 8px 0 0;
  max-height: 120px;
  overflow-y: auto;
  padding: 8px;
  border-radius: 6px;
  background: rgb(183 89 44 / 8%);
  font-family: inherit;
  font-size: 12px;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-word;
  color: #7b6559;
}

.cursor {
  display: inline-block;
  color: #b7592c;
  animation: pulse 0.8s infinite;
}

.input-bar {
  display: flex;
  gap: 0.75rem;
  padding: 0.9rem 170.5px 1.1rem;
  border-top: 1px solid var(--line);
  background: rgba(255, 255, 255, 0.84);
  :deep(.el-input) {
    flex: 1;
  }
  :deep(.el-input__wrapper) {
    min-height: 2.9rem;
    border-radius: 0.85rem;
    background: #fff;
    box-shadow: 0 0 0 1px rgba(183, 89, 44, 0.16) inset;
    transition: box-shadow 220ms cubic-bezier(0.32, 0.72, 0, 1);
    &.is-focus {
      box-shadow: 0 0 0 2px rgba(183, 89, 44, 0.34) inset;
    }
  }
  :deep(.el-button) {
    min-height: 2.9rem;
    padding: 0 1.1rem;
    border-radius: 0.85rem;
    background: #b7592c;
    border: 0;
    transition:
      transform 220ms cubic-bezier(0.32, 0.72, 0, 1),
      background-color 220ms cubic-bezier(0.32, 0.72, 0, 1);
    &:hover {
      background: #94431f;
      transform: translateY(-1px);
    }
    &:active {
      transform: scale(0.98);
    }
  }
}

@keyframes message-in {
  from {
    opacity: 0;
    transform: translateY(10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

@media (max-width: 680px) {
  .butler-page {
    min-height: calc(100dvh - 60px);
  }
  .butler-header {
    align-items: flex-start;
    gap: 0.75rem;
    padding-inline: 1rem;
  }
  .agent-badge {
    flex-shrink: 0;
  }
  .chat-list {
    width: min(100% - 1.2rem, 920px);
    padding-top: 1rem;
  }
  .msg-row .bubble {
    max-width: calc(100vw - 5.2rem);
  }
  .input-bar {
    align-items: stretch;
    flex-wrap: wrap;
    padding: 0.7rem;
  }
  .input-bar :deep(.el-input) {
    width: 100%;
    flex-basis: 100%;
  }
  .input-bar :deep(.el-button) {
    margin-left: auto;
  }
}

@media (prefers-reduced-motion: reduce) {
  .msg-row,
  .agent-badge .dot {
    animation: none;
  }
}
</style>
