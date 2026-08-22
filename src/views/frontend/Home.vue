<script setup lang="ts">
import { ElMessage } from "element-plus";
import { useRouter } from "vue-router";

const iconUrl = new URL("@/assets/images/robot-fill.png", import.meta.url).href;
const router = useRouter();

const checkLogin = () => {
  const token = localStorage.getItem("token");
  if (!token) {
    ElMessage.error("请先登录");
    return false;
  }
  return true;
};

const handleStartConsultation = () => {
  if (!checkLogin()) return;
  router.push("/consultation");
};

const handleGoDiary = () => {
  if (!checkLogin()) return;
  router.push("/emotion-diary");
};

const handleHeroActionsClick = (event: MouseEvent) => {
  const container = event.currentTarget as HTMLElement;
  const target = event.target as HTMLElement | null;
  const button = target?.closest("button");
  if (!button || !container.contains(button)) return;

  const buttons = Array.from(container.querySelectorAll("button"));
  const buttonIndex = buttons.indexOf(button);

  if (buttonIndex === 0) {
    handleStartConsultation();
  }

  if (buttonIndex === 1) {
    handleGoDiary();
  }
};
</script>

<template>
  <div class="home-container">
    <div class="content">
      <div class="text">
        <h2 class="title">
          一次温暖的对话<br />
          <span class="highlight-text">化孤独为慰藉</span>
        </h2>
        <p class="description">
          与心理AI助手进行深度对话，让孤独的心灵找到慰藉。
        </p>
        <div class="hero-actions" @click="handleHeroActionsClick">
          <el-button type="primary" size="large">开始倾诉，获得陪伴</el-button>
          <el-button class="outline-button" size="large"
            >记录心情，释放情绪
          </el-button>
        </div>
      </div>
      <div class="robot">
        <el-image
          :src="iconUrl"
          alt="心理AI助手"
          style="width: 150px; height: 150px"
        ></el-image>
      </div>
    </div>
  </div>
</template>

<style scoped lang="scss">
.home-container {
  --ink: #ffffff;
  --muted: rgba(255, 255, 255, 0.8);
  --sage: #4a9c8c;
  --paper: #3d8a7a;
  position: relative;
  isolation: isolate;
  overflow: hidden;
  min-height: calc(100dvh - 285px);
  padding: clamp(3rem, 8vw, 7rem) clamp(1.25rem, 6vw, 6rem) clamp(4rem, 9vw, 8rem);
  background:
    radial-gradient(circle at 78% 18%, rgba(102, 186, 163, 0.72), transparent 34%),
    radial-gradient(circle at 12% 92%, rgba(44, 113, 99, 0.64), transparent 36%),
    linear-gradient(115deg, #4a9c8c 0%, #3d8a7a 100%);
  color: var(--ink);
  display: flex;
  align-items: center;
  justify-content: center;
  &::before {
    content: "";
    position: absolute;
    inset: 0;
    z-index: -1;
    opacity: 0.26;
    pointer-events: none;
    background-image: radial-gradient(rgba(255, 255, 255, 0.18) 0.55px, transparent 0.55px);
    background-size: 6px 6px;
    mask-image: linear-gradient(135deg, black, transparent 72%);
  }
  .content {
    width: min(1120px, 100%);
    display: grid;
    grid-template-columns: minmax(0, 1.1fr) minmax(280px, 0.9fr);
    justify-content: space-between;
    align-items: center;
    gap: clamp(2rem, 8vw, 8rem);
    .text {
      max-width: 630px;
      animation: home-rise 760ms cubic-bezier(0.32, 0.72, 0, 1) both;
      .title {
        max-width: 11ch;
        margin: 0 0 1.25rem;
        font-size: clamp(2.7rem, 5.4vw, 5.25rem);
        font-weight: 750;
        letter-spacing: -0.06em;
        line-height: 0.98;
        text-wrap: balance;
        .highlight-text {
          display: inline-block;
          color: #ffd700;
        }
      }
      .description {
        max-width: 34rem;
        margin: 0;
        color: var(--muted);
        font-size: clamp(1rem, 1.3vw, 1.2rem);
        line-height: 1.75;
      }
      .hero-actions {
        display: flex;
        flex-wrap: wrap;
        gap: 12px;
        margin-top: 2.25rem;

        :deep(.el-button) {
          min-height: 48px;
          margin: 0;
          padding: 0 1.35rem;
          border-radius: 999px;
          font-weight: 650;
          letter-spacing: 0.01em;
          transition: transform 260ms cubic-bezier(0.32, 0.72, 0, 1), box-shadow 260ms cubic-bezier(0.32, 0.72, 0, 1), background-color 260ms cubic-bezier(0.32, 0.72, 0, 1);
          &:hover { transform: translateY(-2px); }
          &:active { transform: translateY(1px) scale(0.98); }
          &:focus-visible { outline: 3px solid rgba(47, 129, 120, 0.28); outline-offset: 3px; }
        }
        :deep(.el-button--primary) {
          border: 0;
          background: #2f8178;
          box-shadow: 0 14px 28px rgba(21, 76, 65, 0.26);
          &:hover { background: #256d66; box-shadow: 0 18px 32px rgba(21, 76, 65, 0.34); }
        }
        .outline-button {
          background: rgba(255, 255, 255, 0.42);
          border: 1px solid rgba(255, 255, 255, 0.48);
          color: #fff;

          &:hover,
          &:focus {
            background-color: rgba(255, 255, 255, 0.14);
            border-color: #fff;
            color: #fff;
          }
        }
      }
    }
    .robot {
      position: relative;
      display: flex;
      justify-content: center;
      align-items: center;
      width: min(390px, 78vw);
      aspect-ratio: 1;
      justify-self: end;
      border-radius: 38% 62% 58% 42% / 43% 40% 60% 57%;
      background: linear-gradient(145deg, rgba(255,255,255,.2), rgba(255,255,255,.06));
      box-shadow: 24px 28px 70px rgba(21, 76, 65, 0.28), inset 0 1px 0 rgba(255,255,255,.32);
      animation: home-float 7200ms ease-in-out infinite;
      &::after {
        content: "陪你把今天说清楚";
        position: absolute;
        right: -1.5rem;
        bottom: 2.25rem;
        padding: 0.7rem 0.95rem;
        border-radius: 12px 12px 4px 12px;
        background: rgba(255,255,255,.94);
        color: #3d7168;
        font-size: 0.78rem;
        box-shadow: 0 12px 30px rgba(44, 91, 81, 0.12);
      }
      :deep(.el-image) { width: 48% !important; height: 48% !important; filter: drop-shadow(0 18px 24px rgba(21, 76, 65, .24)); }
    }
  }
}

@keyframes home-rise { from { opacity: 0; transform: translateY(22px); } to { opacity: 1; transform: translateY(0); } }
@keyframes home-float { 0%, 100% { transform: translateY(0) rotate(-3deg); } 50% { transform: translateY(-12px) rotate(2deg); } }

@media (max-width: 760px) {
  .home-container { min-height: calc(100dvh - 120px); padding: 3rem 1.25rem 4rem; align-items: flex-start; }
  .home-container .content { grid-template-columns: 1fr; gap: 2.5rem; }
  .home-container .content .text { max-width: none; }
  .home-container .content .text .title { max-width: 12ch; font-size: clamp(2.8rem, 13vw, 4.2rem); }
  .home-container .content .text .hero-actions :deep(.el-button) { flex: 1 1 100%; }
  .home-container .content .robot { width: min(280px, 74vw); justify-self: center; }
  .home-container .content .robot::after { right: -0.5rem; bottom: 1.25rem; }
}

@media (prefers-reduced-motion: reduce) {
  .home-container .content .text, .home-container .content .robot { animation: none; }
}
</style>
