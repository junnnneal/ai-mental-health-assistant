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
.backend-layout {
  height: 100vh;
  //el-header 是NavBar父亲，NavBar继承el-header的高度
  .el-header {
    height: 76px !important;
  }
  //两层 el-container 都撑满：内层是"头部+主区"纵向flex，el-main 靠 flex:1 分到剩余高度，
  //成为唯一滚动容器（此前 height:100% 同时打在外层container和el-main上，多出76px导致整列溢出）
  .el-container {
    height: 100%;
  }
  //去掉 element-plus 默认20px内边距，白底才能铺满主区边缘
  .el-main {
    padding: 0;
    overflow-y: auto;
  }
  .content-container {
    padding: 20px;
    background-color: #fff;
    //至少铺满可视高度，内容更高时白底跟着长高，滚动时始终完整覆盖
    min-height: 100%;
    box-sizing: border-box;
  }
}
</style>
