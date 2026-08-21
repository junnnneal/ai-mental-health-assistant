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
        <el-image class="logo" :src="logoImg" alt="logo" />
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
    //图标固定贴左7px：(64-50)/2=7，折叠时正好在64px侧栏居中，
    //展开/折叠位置完全不动（不能整体居中，否则两种状态下图标会左右跳）
    justify-content: flex-start;
    padding: 0 7px;
    //与顶栏 el-header 同高（含边线box-sizing），两条底边线才能对齐
    height: 76px;
    box-sizing: border-box;
    background-color: #fff;
    border-bottom: 1px solid #e5e7eb;
    .logo {
      width: 50px;
      height: 50px;
      //折叠态侧栏只剩64px，flex默认收缩会把图标压扁，禁止缩
      flex-shrink: 0;
    }
    .info-card {
      margin-left: 10px;
      white-space: nowrap;
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
