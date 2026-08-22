<script setup>
import { ref, onMounted } from "vue";
import { useRouter } from "vue-router";
import { ElMessageBox, ElMessage } from "element-plus";
import { logout as logoutApi } from "@/apis/admin";
const router = useRouter();
const iconUrl = new URL("@/assets/images/机器人.png", import.meta.url).href;
const isLoggedIn = ref(false);

const handleLogout = () => {
  //退出二次确认：与后台 NavBar 同款，取消则不发起退出请求
  ElMessageBox.confirm("确定退出登录吗？", "提示", {
    confirmButtonText: "确定",
    cancelButtonText: "取消",
    type: "warning",
  }).then(() => {
    logoutApi().then(() => {
      localStorage.removeItem("token");
      localStorage.removeItem("userInfo");
      isLoggedIn.value = false;
      router.push("/");
      ElMessage.success("退出登录成功");
    });
  });
};

onMounted(() => {
  isLoggedIn.value = localStorage.getItem("token") !== null;
});
</script>

<template>
  <div class="frontend-layout">
    <div class="navbar-container">
      <div class="brand-section">
        <el-image
          :src="iconUrl"
          alt="心理AI助手"
          style="width: 50px; height: 50px"
        >
        </el-image>
        <h1 class="brand-name">心理健康AI助手</h1>
      </div>
      <div class="nav-section">
        <router-link to="/" class="nav-link">首页</router-link>
        <router-link to="/consultation" class="nav-link" v-if="isLoggedIn"
          >AI咨询</router-link
        >
        <router-link to="/health-butler" class="nav-link" v-if="isLoggedIn"
          >AI健康管家</router-link
        >
        <router-link to="/emotion-diary" class="nav-link" v-if="isLoggedIn"
          >情绪日记</router-link
        >
        <router-link to="/knowledge" class="nav-link">知识库</router-link>
        <el-button class="logout-btn" v-if="isLoggedIn" @click="handleLogout"
          >退出登录</el-button
        >
        <template v-else>
          <router-link to="/auth/login" class="nav-link">登录</router-link>
          <router-link to="/auth/register" class="nav-link">
            <el-button type="primary">注册</el-button>
          </router-link>
        </template>
      </div>
    </div>
    <div class="main-content"></div>
    <router-view></router-view>
    <div class="footer-container">
      <div class="footer-bottom">
        <p>&copy; 2026 心理健康AI助手. 保留所有权利.</p>
      </div>
    </div>
  </div>
</template>

<style scoped lang="scss">
.frontend-layout {
  background-color: #fff;
  .navbar-container {
    max-width: 1200px;
    height: 100%;
    margin: 0 auto;
    padding: 10px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    .brand-section {
      display: flex;
      align-items: center;
      .brand-name {
        margin-left: 10px;
        font-size: 24px;
        font-weight: 600;
        color: #333;
      }
    }
    .nav-section {
      display: flex;
      align-items: center;
      gap: 40px;
      .nav-link {
        color: #4b5563;
        font-size: 16px;
        font-weight: 500;
        &:hover {
          color: #4a90e2;
        }
      }
    }
  }

  @media (max-width: 760px) {
    .navbar-container {
      min-height: 58px;
      height: auto;
      padding: 8px 14px;
      gap: 14px;

      .brand-section {
        min-width: 0;

        :deep(.el-image) {
          width: 36px !important;
          height: 36px !important;
          flex: 0 0 auto;
        }

        .brand-name {
          max-width: 120px;
          margin-left: 7px;
          color: #29313a;
          font-size: 16px;
          line-height: 1.2;
          text-wrap: balance;
        }
      }

      .nav-section {
        min-width: 0;
        flex: 1;
        justify-content: flex-end;
        gap: 10px;
        overflow-x: auto;
        scrollbar-width: none;

        &::-webkit-scrollbar {
          display: none;
        }

        .nav-link {
          flex: 0 0 auto;
          font-size: 13px;
          white-space: nowrap;
        }

        :deep(.el-button) {
          height: 34px;
          padding: 0 11px;
          font-size: 13px;
        }
      }
    }
  }

  @media (max-width: 430px) {
    .navbar-container {
      .brand-name {
        max-width: 76px;
        font-size: 14px;
      }

      .nav-section {
        gap: 7px;
        justify-content: flex-start;

        .nav-link {
          font-size: 12px;
        }

        :deep(.el-button) {
          padding: 0 8px;
        }
      }
    }
  }

  .footer-container {
    background: #1f2937;
    color: white;
    padding: 15px 0;
    margin-top: auto;
    .footer-bottom {
      max-width: 1200px;
      margin: 0 auto;
      padding: 0 10px;
      text-align: center;
    }
  }
}
</style>
