import { createRouter, createWebHistory, RouteRecordRaw } from "vue-router";
import { useAuthStore } from "@/stores/auth";
import { resolveInviteCode } from "@/utils/inviteCode";

const routes: RouteRecordRaw[] = [
  // ── C 端（教员 H5） ──
  {
    // 落地页跟随最近使用的中介橱窗，而不是固定跳演示邀请码
    path: "/",
    redirect: () => `/teacher/board/${resolveInviteCode()}`,
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
    meta: { title: "订单详情", auth: true, role: "teacher" },
  },
  {
    path: "/teacher/applications",
    name: "MyApplications",
    component: () => import("@/views/teacher/MyApplications.vue"),
    meta: { title: "我的投递", auth: true, role: "teacher" },
  },
  {
    path: "/teacher/profile",
    name: "TeacherProfile",
    component: () => import("@/views/teacher/Profile.vue"),
    meta: { title: "个人中心", auth: true, role: "teacher" },
  },
  {
    path: "/teacher/help",
    name: "TeacherHelpCenter",
    component: () => import("@/views/teacher/HelpCenter.vue"),
    meta: { title: "帮助中心", auth: true, role: "teacher" },
  },

  // ── B 端（中介后台） ──
  {
    path: "/admin",
    redirect: "/admin/dashboard",
  },
  {
    // 统一认证入口：中介/老板登录都由 teacher/login 页的角色标签承接
    path: "/admin/login",
    redirect: (to) => ({ path: "/teacher/login", query: { ...to.query, tab: "admin" } }),
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
    path: "/admin/map",
    name: "AdminMap",
    component: () => import("@/views/admin/MapBoard.vue"),
    meta: { title: "地图看单", auth: true, role: "tenant_admin" },
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
  {
    path: "/:pathMatch(.*)*",
    name: "NotFound",
    component: () => import("@/views/NotFound.vue"),
    meta: { title: "页面不存在" },
  },
];

const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior: () => ({ top: 0 }),
});

// 路由守卫
router.beforeEach(async (to, _from, next) => {
  const auth = useAuthStore();

  // 设置页面标题
  document.title = (to.meta.title as string) || "智派";

  // 需要认证
  if (to.meta.auth && !auth.token) {
    const loginPath =
      to.meta.role === "tenant_admin" ? "/admin/login" : "/teacher/login";
    return next({ path: loginPath, query: { redirect: to.fullPath } });
  }

  // 有本地 token 也不代表会话仍然有效，进入受保护页面前向后端确认。
  if (to.meta.auth && auth.token) {
    try {
      await auth.fetchMe();
    } catch {
      auth.logout();
      const loginPath =
        to.meta.role === "tenant_admin" ? "/admin/login" : "/teacher/login";
      return next({ path: loginPath, query: { redirect: to.fullPath } });
    }
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
    const targetRole = String(to.meta.role);
    const loginPath = targetRole === "tenant_admin" ? "/admin/login" : "/teacher/login";
    auth.logout();
    return next({ path: loginPath, query: { redirect: to.fullPath } });
  }

  next();
});

export default router;
