import { createRouter, createWebHistory } from "vue-router";
import type { RouteRecordRaw } from "vue-router";

const routes: RouteRecordRaw[] = [
  {
    path: "/back",
    name: "backend",
    component: () => import("@/components/layouts/BackendLayout.vue"),
    //重定向
    redirect: "/back/dashboard",
    children: [
      {
        path: "dashboard",
        name: "dashboard",
        component: () => import("@/views/backend/DashBoard.vue"),
        meta: { title: "数据分析", icon: "PieChart" },
      },
      {
        path: "knowledge",
        name: "backend-knowledge",
        component: () => import("@/views/backend/Knowledge.vue"),
        meta: { title: "知识文章", icon: "ChatLineSquare" },
      },
      {
        path: "consultations",
        name: "consultations",
        component: () => import("@/views/backend/Consultations.vue"),
        meta: { title: "咨询记录", icon: "Message" },
      },
      {
        path: "emotional",
        name: "emotional",
        component: () => import("@/views/backend/Emotional.vue"),
        meta: { title: "情感分析", icon: "User" },
      },
    ],
  },
  {
    path: "/",
    name: "frontend",
    component: () => import("@/components/layouts/FrontendLayout.vue"),
    children: [
      {
        path: "",
        name: "home",
        component: () => import("@/views/frontend/Home.vue"),
        meta: { title: "首页" },
      },
      {
        path: "consultation",
        name: "consultation",
        component: () => import("@/views/frontend/Consultation.vue"),
        meta: { title: "AI咨询" },
      },
      {
        path: "emotion-diary",
        name: "emotion-diary",
        component: () => import("@/views/frontend/EmotionDiary.vue"),
        meta: { title: "情绪日记" },
      },
      {
        path: "knowledge",
        name: "frontend-knowledge",
        component: () => import("@/views/frontend/FrontendKnowledge.vue"),
        meta: { title: "知识库" },
      },
    ],
  },
  {
    path: "/auth",
    name: "auth",
    component: () => import("@/components/layouts/AuthLayout.vue"),
    children: [
      {
        path: "login",
        name: "login",
        component: () => import("@/views/auth/Login.vue"),
        meta: { title: "登录" },
      },
      {
        path: "register",
        name: "register",
        component: () => import("@/views/auth/Register.vue"),
        meta: { title: "注册" },
      },
    ],
  },
];

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes,

  scrollBehavior() {
    return {
      top: 0,
    };
  },
});

//路由前置守卫
router.beforeEach((to, from, next) => {
  const token = localStorage.getItem("token");
  const userInfo = JSON.parse(localStorage.getItem("userInfo") || "{}");

  if (!token) {
    if (to.path.startsWith("/back")) {
      next("/auth/login");
    } else {
      next();
    }
    return;
  }
  //后台用户
  if (userInfo.userType === 2) {
    if (to.path.startsWith("/back")) {
      next();
    } else {
      next("/back/dashboard");
    }
    return;
  }
  //前台用户
  if (userInfo.userType === 1) {
    if (to.path.startsWith("/back") || to.path.startsWith("/auth")) {
      next("/");
    } else {
      next();
    }
    return;
  }

  next("/auth/login");
});

export default router;
