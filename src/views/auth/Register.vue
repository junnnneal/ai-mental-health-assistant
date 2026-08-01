<script setup lang="ts">
import { ref, onMounted } from "vue";
import { register } from "@/apis/frontEnd";
import { ElMessage } from "element-plus";
import type { FormInstance, FormRules } from "element-plus";
import { useRouter } from "vue-router";

const router = useRouter();

const formData = ref({
  username: "",
  email: "",
  nickname: "",
  phone: "",
  password: "",
  confirmPassword: "",
  gender: 0,
  userType: 1, // 1表示普通用户，2表示心理咨询师
});

const rules: FormRules = {
  username: [
    { required: true, message: "请输入用户名", trigger: "blur" },
    {
      min: 3,
      max: 20,
      message: "用户名长度在3到20个字符之间",
      trigger: "blur",
    },
  ],
  email: [
    { required: true, message: "请输入邮箱", trigger: "blur" },
    {
      type: "email",
      message: "请输入有效的邮箱地址",
      trigger: ["blur", "change"],
    },
  ],
  password: [
    { required: true, message: "请输入密码", trigger: "blur" },
    { min: 6, max: 20, message: "密码长度在6到20个字符之间", trigger: "blur" },
  ],
  confirmPassword: [
    { required: true, message: "请再次输入密码", trigger: "blur" },
    {
      validator: (_rule, value: string, callback) => {
        if (!value) {
          callback();
        } else if (value !== formData.value.password) {
          callback(new Error("两次输入的密码不一致"));
        } else {
          callback();
        }
      },
      trigger: "blur",
    },
  ],
};

//表单提交
const submitFormRef = ref<FormInstance>();

const submitForm = async (formEl: FormInstance | undefined) => {
  if (!formEl) return;
  formEl.validate(async (valid: boolean) => {
    if (!valid) return;

    register(formData.value)
      .then(() => {
        ElMessage.success("注册成功");
        // 注册成功后，跳转到登录页面
        router.push("/auth/login");
      })
      .catch((err) => {
        console.error("注册失败", err);
      });
  });
};
</script>

<template>
  <div class="container">
    <div class="title">
      <div class="title-text">
        <h2>创建您的账户</h2>
        <p>填写注册信息</p>
      </div>
    </div>
    <div class="form-container">
      <el-form
        ref="submitFormRef"
        :model="formData"
        :rules="rules"
        label-position="top"
      >
        <el-form-item label="用户名" prop="username" for="register-username">
          <el-input
            id="register-username"
            v-model="formData.username"
            placeholder="请输入用户名"
            size="large"
          ></el-input>
        </el-form-item>
        <el-form-item label="邮箱" prop="email" for="register-email">
          <el-input
            id="register-email"
            v-model="formData.email"
            placeholder="请输入邮箱"
            size="large"
          ></el-input>
        </el-form-item>
        <el-form-item label="昵称" prop="nickname" for="register-nickname">
          <el-input
            id="register-nickname"
            v-model="formData.nickname"
            placeholder="请输入昵称(选填)"
            size="large"
          ></el-input>
        </el-form-item>
        <el-form-item label="手机号" prop="phone" for="register-phone">
          <el-input
            id="register-phone"
            v-model="formData.phone"
            placeholder="请输入手机号(选填)"
            size="large"
          ></el-input>
        </el-form-item>
        <el-form-item label="性别" prop="gender" for="">
          <el-radio-group
            v-model="formData.gender"
            size="large"
            aria-label="性别"
            name="gender"
          >
            <el-radio :value="1">男</el-radio>
            <el-radio :value="2">女</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="密码" prop="password" for="register-password">
          <el-input
            id="register-password"
            v-model="formData.password"
            type="password"
            placeholder="请输入密码"
            size="large"
          ></el-input>
        </el-form-item>
        <el-form-item
          label="确认密码"
          prop="confirmPassword"
          for="register-confirm-password"
        >
          <el-input
            id="register-confirm-password"
            v-model="formData.confirmPassword"
            type="password"
            placeholder="请再次输入密码"
            size="large"
          ></el-input>
        </el-form-item>
        <el-button
          class="btn"
          type="primary"
          size="large"
          @click="submitForm(submitFormRef)"
        >
          注册
        </el-button>
      </el-form>
      <div class="footer">
        已有账户？<router-link to="/auth/login">立即登录</router-link>
      </div>
    </div>
  </div>
</template>

<style scoped lang="scss">
.container {
  width: 384px;
  .flex-box {
    display: flex;
    align-items: center;
  }
  .title {
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
  .form-container {
    margin-top: 30px;
    .btn {
      margin-top: 40px;
      width: 100%;
    }
    .footer {
      padding: 30px;
      text-align: center;
    }
  }
}
</style>
