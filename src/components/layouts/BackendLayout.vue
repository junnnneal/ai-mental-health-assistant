<script setup lang="ts">
import SideBar from "@/components/backend/SideBar.vue";
import NavBar from "@/components/backend/NavBar.vue";
</script>

<template>
  <div class="backend-layout">
    <el-container class="main-container">
      <SideBar />
      <el-container>
        <el-header>
          <NavBar />
        </el-header>
        <el-main class="main-container">
          <router-view class="content-container"></router-view>
        </el-main>
      </el-container>
    </el-container>
  </div>
</template>

<style lang="scss" scoped>
.content-container {
  height: calc(100% - 74px);
}
</style>
<style lang="scss" scoped>
.backend-layout {
  height: 100vh;
  //el-header 是NavBar父亲，NavBar继承el-header的高度
  .el-header {
    height: 76px !important;
  }
  .main-container {
    height: 100%;
    .content-container {
      padding: 20px;
      background-color: #fff;
      min-height: calc(100% - 74px);
    }
  }
}
</style>
