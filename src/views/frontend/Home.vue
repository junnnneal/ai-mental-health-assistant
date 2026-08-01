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
  background: linear-gradient(
      90deg,
      rgb(74, 156, 140) 0%,
      rgb(61, 138, 122) 100%
    )
    rgba(74, 156, 140, 0.95);
  color: white;
  padding: 5rem 0;
  height: calc(100vh - 285px);
  display: flex;
  align-items: center;
  justify-content: center;
  .content {
    display: flex;
    justify-content: center;
    align-items: center;
    gap: 30px;
    .text {
      width: 500px;
      .title {
        font-size: 45px;
        font-weight: bold;
        // line-height: 1.2;
        margin-bottom: 15px;
        .highlight-text {
          color: #ffd700;
        }
      }
      .hero-actions {
        margin-top: 30px;

        .outline-button {
          background-color: transparent;
          border-color: #fff;
          color: #fff;

          &:hover,
          &:focus {
            background-color: rgba(255, 255, 255, 0.12);
            border-color: #fff;
            color: #fff;
          }
        }
      }
    }
    .robot {
      display: flex;
      justify-content: center;
      align-items: center;
      width: 260px;
      height: 260px;
      border-radius: 50%;
      border: 2px solid rgba(255, 255, 255, 0.2);
      background: linear-gradient(
        135deg,
        rgba(255, 255, 255, 0.15) 0%,
        rgba(255, 255, 255, 0.05) 100%
      );
      box-shadow:
        0 15px 35px rgba(0, 0, 0, 0.1),
        inset 0 1px 0 rgba(255, 255, 255, 0.3);
    }
  }
}
</style>
