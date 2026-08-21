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

//agent-server（LangGraph Agent）只在本机运行，线上未部署：
//提前说明比让访客发消息撞404后再看报错友好
const isProd = import.meta.env.PROD;

const SUGGESTIONS = [
  "我最近总是失眠，有什么科学的改善方法？",
  "帮我看看我最近的情绪状态怎么样",
  "帮我记一条情绪日记：今天有点焦虑，心情大概40分",
];

const summarizeArgs = (name: string, args: Record<string, unknown>): string => {
  const query = args.query ?? args.dominant_emotion ?? args.limit;
  return query !== undefined ? String(query) : "";
};

const scrollToBottom = async () => {
  await nextTick();
  const el = listRef.value;
  if (el) el.scrollTop = el.scrollHeight;
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
  const assistantMsg = reactive<ChatMsg>({ role: "assistant", content: "", segments: [] });
  messages.value.push(assistantMsg);
  streaming.value = true;
  scrollToBottom();

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

    <!-- 线上未部署Agent服务：进页面就说明，而不是等发消息撞404 -->
    <div v-if="isProd" class="prod-notice">
      线上演示说明：AI 健康管家由本地运行的 LangGraph Agent
      服务驱动，线上环境未部署该服务，发送消息会提示连接失败。
      完整体验请在本地项目启动 agent-server 后访问。
    </div>

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
                  <span class="thought-icon">{{ TOOL_META[seg.toolName]?.icon ?? "🛠" }}</span>
                  <span class="thought-label">
                    {{ TOOL_META[seg.toolName]?.label ?? seg.toolName }}
                  </span>
                  <span v-if="summarizeArgs(seg.toolName, seg.args)" class="thought-arg">
                    「{{ summarizeArgs(seg.toolName, seg.args) }}」
                  </span>
                  <span v-if="seg.running" class="spinner"></span>
                  <span v-else class="thought-done">✓</span>
                </div>
                <pre v-if="seg.result" class="thought-result">{{ seg.result }}</pre>
              </template>
              <!-- 回答段落 -->
              <pre v-else class="answer-text">{{ seg.text }}</pre>
            </div>
          </template>
          <pre v-else class="answer-text">{{ msg.content }}</pre>
          <div
            v-if="msg.role === 'assistant' && streaming && idx === messages.length - 1"
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
  display: flex;
  flex-direction: column;
  // 外层布局没有高度链，100%会塌：直接按视口算，扣掉导航栏(50px图+上下padding10px)
  height: calc(100vh - 70px);
  min-height: 560px;
  background: #fffaf0;
}

.butler-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 18px 28px;
  border-bottom: 1px solid #f3e3c9;

  h1 {
    margin: 0;
    font-size: 20px;
    color: #8b5e20;
  }
  p {
    margin: 4px 0 0;
    font-size: 13px;
    color: #b08d57;
  }
}

.agent-badge {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 14px;
  border-radius: 999px;
  background: #fff;
  border: 1px solid #f59e0b;
  font-size: 13px;
  color: #b45309;

  .dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: #22c55e;

    &.busy {
      background: #f59e0b;
      animation: pulse 0.9s infinite;
    }
  }
}

@keyframes pulse {
  50% {
    opacity: 0.3;
  }
}

.prod-notice {
  margin: 12px 28px 0;
  padding: 10px 14px;
  border-radius: 10px;
  border: 1px dashed #fb923c;
  background: #fff4e6;
  font-size: 13px;
  line-height: 1.6;
  color: #b45309;
}

.chat-list {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 24px 28px;
}

.empty-state {
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;

  .empty-icon {
    font-size: 52px;
  }
  h3 {
    margin: 0;
    color: #8b5e20;
  }
  p {
    margin: 0 0 16px;
    color: #b08d57;
    font-size: 14px;
  }
}

.suggestions {
  display: flex;
  flex-direction: column;
  gap: 10px;

  .suggestion-chip {
    padding: 10px 18px;
    border-radius: 999px;
    border: 1px solid #fb923c;
    background: #fff;
    color: #c2561a;
    font-size: 14px;
    cursor: pointer;
    transition: all 0.2s;

    &:hover {
      background: #fff4e6;
      transform: translateY(-1px);
    }
  }
}

.msg-row {
  display: flex;
  gap: 10px;
  margin-bottom: 18px;

  .avatar {
    flex-shrink: 0;
    width: 36px;
    height: 36px;
    border-radius: 50%;
    background: #fff;
    border: 1px solid #f0dcc0;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 18px;
  }

  &.user {
    flex-direction: row-reverse;

    .bubble {
      background: #fb923c;
      color: #fff;
      border-radius: 14px 2px 14px 14px;
    }
  }

  .bubble {
    max-width: 78%;
    padding: 12px 16px;
    border-radius: 2px 14px 14px 14px;
    background: #fff;
    border: 1px solid #f0dcc0;
    box-shadow: 0 1px 3px rgb(0 0 0 / 4%);

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
  font-size: 14px;
  line-height: 1.7;
  white-space: pre-wrap;
  word-break: break-word;
  color: #4b3a28;
}

.thought-card {
  margin-bottom: 10px;
  padding: 10px 12px;
  border-radius: 10px;
  background: #fff9e6;
  border: 1px dashed #facc15;

  &.running {
    border-style: solid;
    border-color: #fb923c;
    background: #fff4e6;
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
  color: #92600a;
  flex-wrap: wrap;

  .thought-arg {
    color: #c2561a;
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
  border: 2px solid #fb923c;
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
  background: rgb(251 191 36 / 8%);
  font-family: inherit;
  font-size: 12px;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-word;
  color: #8b7355;
}

.cursor {
  display: inline-block;
  color: #fb923c;
  animation: pulse 0.8s infinite;
}

.input-bar {
  display: flex;
  gap: 12px;
  padding: 14px 28px;
  border-top: 1px solid #f3e3c9;
  background: #fffdf7;
}
</style>
