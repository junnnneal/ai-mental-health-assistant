<script setup lang="ts">
import { computed } from "vue";
import { useRouter } from "vue-router";
import type { RouteMenu } from "@/types";
import { useAdminStore } from "@/stores/adminStore";

const adminStore = useAdminStore();
const isCollapsed = computed(() => adminStore.isCollapsed);

const logoImg = new URL("@/assets/images/机器人.png", import.meta.url).href;

const router = useRouter();
//点击跳转路由
const selectMeun = (path: string) => {
  const currentRoute = router.options.routes[0];
  if (currentRoute?.path) {
    router.push(`${currentRoute.path}/${path}`);
  }
};

//断言加as unkown做中转
const menuItems = computed<RouteMenu[]>(
  () => (router.options.routes[0]?.children ?? []) as unknown as RouteMenu[],
);
const handleOpen = (key: string) => {};
const handleClose = (key: string) => {};
</script>

<template>
  <!-- 侧边栏容器，根据折叠状态动态切换宽度 -->
  <el-aside :width="isCollapsed ? '64px' : '264px'">
    <!-- 菜单组件 -->
    <el-menu
      :collapse="isCollapsed"
      :collapse-transition="false"
      default-active="2"
      @open="handleOpen"
      @close="handleClose"
      class="meun-style"
    >
      <div class="brand">
        <el-image
          style="width: 50px; height: 50px; margin-right: 10px"
          :src="logoImg"
          alt="logo"
        />
        <div v-show="!isCollapsed" class="info-card">
          <h1 class="brand-title">心理健康AI助手</h1>
          <p class="brand-subtitle">管理后台</p>
        </div>
      </div>
      <!-- 菜单部分 -->
      <el-menu-item
        v-for="item in menuItems"
        :key="item.path"
        :index="item.path"
        @click="selectMeun(item.path)"
      >
        <el-icon><component :is="item.meta.icon" /></el-icon>
        <span>{{ item.meta.title }}</span>
      </el-menu-item>
    </el-menu>
  </el-aside>
</template>

<style lang="scss" scoped>
.meun-style {
  height: 100%;
  .brand {
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 10px;
    background-color: #fff;
    border-bottom: 1px solid #e5e7eb;
    .info-card {
      .brand-title {
        font-size: 20px;
        font-weight: bold;
        margin-bottom: 5px;
        color: #1f2937;
      }
      .brand-subtitle {
        font-size: 14px;
        color: #6b7280;
      }
    }
  }
}
</style>
