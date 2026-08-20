import { createRouter, createWebHistory, RouteRecordRaw } from "vue-router";
import { useAuthStore } from "@/stores/auth";

const routes: RouteRecordRaw[] = [
  // ── C 端（教员 H5） ──
  {
    path: "/",
    redirect: "/teacher/board/tx886",
  },
  {
    path: "/teacher/board/:inviteCode",
    name: "TeacherBoard",
    component: () => import("@/views/teacher/Board.vue"),
    meta: { title: "橱窗地图", transition: "fade" },
  },
  {
    path: "/teacher/login",
    name: "TeacherLogin",
    component: () => import("@/views/teacher/Login.vue"),
    meta: { title: "教员登录", guest: true },
  },
  {
    path: "/teacher/register",
    name: "TeacherRegister",
    component: () => import("@/views/teacher/Register.vue"),
    meta: { title: "教员注册", guest: true },
  },
  {
    path: "/teacher/orders/:id",
    name: "OrderDetail",
    component: () => import("@/views/teacher/OrderDetail.vue"),
    meta: { title: "订单详情", auth: true },
  },
  {
    path: "/teacher/applications",
    name: "MyApplications",
    component: () => import("@/views/teacher/MyApplications.vue"),
    meta: { title: "我的投递", auth: true },
  },
  {
    path: "/teacher/profile",
    name: "TeacherProfile",
    component: () => import("@/views/teacher/Profile.vue"),
    meta: { title: "个人中心", auth: true },
  },

  // ── B 端（中介后台） ──
  {
    path: "/admin",
    redirect: "/admin/dashboard",
  },
  {
    path: "/admin/login",
    name: "AdminLogin",
    component: () => import("@/views/admin/Login.vue"),
    meta: { title: "中介登录", guest: true },
  },
  {
    path: "/admin/dashboard",
    name: "Dashboard",
    component: () => import("@/views/admin/Dashboard.vue"),
    meta: { title: "仪表盘", auth: true, role: "tenant_admin" },
  },
  {
    path: "/admin/batch-import",
    name: "BatchImport",
    component: () => import("@/views/admin/BatchImport.vue"),
    meta: { title: "批量导入", auth: true, role: "tenant_admin" },
  },
  {
    path: "/admin/orders",
    name: "OrdersList",
    component: () => import("@/views/admin/OrdersList.vue"),
    meta: { title: "订单管理", auth: true, role: "tenant_admin" },
  },
  {
    path: "/admin/applications",
    name: "ApplicationsReview",
    component: () => import("@/views/admin/ApplicationsReview.vue"),
    meta: { title: "投递审核", auth: true, role: "tenant_admin" },
  },
  {
    path: "/admin/settings",
    name: "AdminSettings",
    component: () => import("@/views/admin/Settings.vue"),
    meta: { title: "设置", auth: true, role: "tenant_admin" },
  },
  {
    path: "/admin/financial-records",
    name: "FinancialRecords",
    component: () => import("@/views/admin/FinancialRecords.vue"),
    meta: { title: "财务流水", auth: true, role: "tenant_admin" },
  },
  {
    path: "/owner/tenants",
    name: "OwnerTenants",
    component: () => import("@/views/admin/Tenants.vue"),
    meta: { title: "中介管理", auth: true, role: "super_admin" },
  },
];

const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior: () => ({ top: 0 }),
});

// 路由守卫
router.beforeEach((to, _from, next) => {
  const auth = useAuthStore();

  // 设置页面标题
  document.title = (to.meta.title as string) || "智派";

  // 需要认证
  if (to.meta.auth && !auth.token) {
    const loginPath =
      to.meta.role === "tenant_admin" ? "/admin/login" : "/teacher/login";
    return next(loginPath);
  }

  // 已登录则跳过访客页
  if (to.meta.guest && auth.token) {
    if (auth.role === "super_admin") {
      return next("/owner/tenants");
    }
    if (auth.role === "tenant_admin") {
      return next("/admin/dashboard");
    }
    return next("/");
  }

  // 角色检查
  if (to.meta.role && auth.role !== to.meta.role && auth.role !== "super_admin") {
    return next("/");
  }

  next();
});

export default router;
