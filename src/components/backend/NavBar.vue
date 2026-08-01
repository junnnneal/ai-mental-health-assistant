<script setup lang="ts">
import { Expand, ArrowDown } from "@element-plus/icons-vue";
import { useAdminStore } from "@/stores/adminStore";
import {useRouter,useRoute} from "vue-router";
import {ElMessageBox,ElMessage} from "element-plus";
import {logout} from "@/apis/admin";

const adminStore = useAdminStore();
const router = useRouter();
const route = useRoute();

const avatarImg = new URL("@/assets/images/user.jpg", import.meta.url).href;

const handleCommand = (command: string) => {
  if(command === 'logout') {
    ElMessageBox.confirm('确定退出登录吗？', '提示', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning'
    }).then(() => {
      logout().then(() => {
        // 清除本地存储中的token
        localStorage.removeItem('token');
        localStorage.removeItem('userInfo');
        // 跳转到登录页
        router.push('/auth/login');
        ElMessage.success('退出登录成功');
      });
    });
  }
};
</script>

<template>
  <div class="navbar">
    <div class="flex-box">
      <el-button @click="adminStore.toggleAdmin">
        <el-icon><Expand /></el-icon>
      </el-button>
      <p class="page-title">{{ route.meta.title }}</p>
    </div>
    <div class="flex-box">
      <el-dropdown @command="handleCommand">
        <div class="flex-box">
          <el-avatar :src="avatarImg" />
          <p class="user-name">admin</p>
          <el-icon><ArrowDown /></el-icon>
        </div>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item command="logout" >退出登录</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
    </div>
  </div>
</template>

<style lang="scss" scoped>
.navbar {
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 15px;
  background: white;
  box-shadow: 0 1px 4px rgba(0, 21, 41, 0.08);
  border-bottom: 1px solid #e5e7eb;
  .flex-box {
    display: flex;
    align-items: center;
    justify-content: center;
    .page-title {
      margin-left: 20px;
      font-size: 26px;
      font-weight: bold;
      color: #1f2937;
    }
    .user-name {
      margin: 0 5px;
      font-weight: bold;
    }
  }
}
</style>
