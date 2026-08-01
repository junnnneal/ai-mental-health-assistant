<script setup lang="ts">
import { Back } from "@element-plus/icons-vue";
import { ref } from "vue";
import type { FormInstance } from "element-plus";
import { login } from "@/apis/admin";
import type { LoginResult } from "@/types";
import { useRouter } from "vue-router";

const router = useRouter();
const formData = ref({
  username: "",
  password: "",
});

const rules = ref({
  username: [{ required: true, message: "请输入用户名", trigger: "blur" }],
  password: [{ required: true, message: "请输入密码", trigger: "blur" }],
});

const formRef = ref<FormInstance>();

const handleBackHome = () => {
  router.push("/");
};

const submitForm = async (formEl: FormInstance | undefined) => {
  if (!formEl) return;
  await formEl.validate((vaild) => {
    if (vaild) {
      login(formData.value).then((data: LoginResult) => {
        //判断token是否存在
        if (!data.token) {
          return console.error("登录失败");
        }
        //登录成功，将token存储到localStorage，userInfo存储到localStorage
        localStorage.setItem("token", data.token);
        localStorage.setItem("userInfo", JSON.stringify(data.userInfo));

        //根据用户角色跳转不同的页面
        if (data.userInfo.userType === 2) {
          router.push("/back/dashboard");
        } else {
          router.push("/");
        }
      });
    }
  });
};
</script>

<template>
  <div class="container">
    <div class="title">
      <div class="back-home" @click="handleBackHome">
        <el-icon><Back /></el-icon>
        <span>返回首页</span>
      </div>
      <div class="title-text">
        <h2>登录你的账户</h2>
        <p>请输入你的登录信息</p>
      </div>
    </div>
    <div class="form-container">
      <el-form
        ref="formRef"
        :model="formData"
        :rules="rules"
        label-position="top"
      >
        <el-form-item label="用户名和邮箱" prop="username">
          <el-input
            v-model="formData.username"
            size="large"
            placeholder="请输入用户名或邮箱"
          ></el-input>
        </el-form-item>
        <el-form-item label="密码" prop="password">
          <el-input
            v-model="formData.password"
            size="large"
            placeholder="请输入密码"
            type="password"
            show-password
          ></el-input>
        </el-form-item>
        <el-button
          type="primary"
          size="large"
          class="btn"
          @click="submitForm(formRef)"
          >登录</el-button
        >
      </el-form>
      <div class="footer">
        <p>还没有账户？<router-link to="/auth/register">去注册</router-link></p>
      </div>
    </div>
  </div>
</template>

<style scoped lang="scss">
.container {
  width: 384px;
  .title {
    .back-home {
      margin-bottom: 60px;
      display: inline-flex;
      align-items: center;
      gap: 6px;
      color: #4b5563;
      cursor: pointer;
      user-select: none;

      &:hover {
        color: #409eff;
      }
    }
    .title-text {
      text-align: center;
      h2 {
        font-size: 36px;
        margin-bottom: 10px;
      }
      p {
        font-size: 18px;
        color: #6b7280;
      }
    }
  }
}
.form-container {
  margin-top: 30px;
  .btn {
    width: 100%;
    margin-top: 40px;
  }
  .footer {
    text-align: center;
    padding: 30px;
  }
}
</style>
