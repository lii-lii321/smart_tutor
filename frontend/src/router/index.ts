import { createRouter, createWebHistory, RouteRecordRaw } from "vue-router";
import { showToast } from "vant";
import { useAuthStore } from "@/stores/auth";
import { getApiErrorStatus } from "@/utils/apiError";
import { resolveInviteCode } from "@/utils/inviteCode";

/** 按目标角色选登录入口：三角色三个独立产品入口 */
function loginRouteFor(role: unknown, redirect: string) {
  if (role === "tenant_admin") {
    return { path: "/admin/login", query: { redirect } };
  }
  if (role === "super_admin") {
    return { path: "/owner/login", query: { redirect } };
  }
  return { path: "/teacher/login", query: { redirect } };
}

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
    props: { role: "teacher" as const },
    meta: { title: "教员登录", guest: true },
    // 旧链接兼容：三 tab 时代分享出的 /teacher/login?tab=admin|owner 永久迁到独立入口
    beforeEnter: (to) => {
      const tab = to.query.tab;
      if (tab === "admin" || tab === "owner") {
        const { tab: _tab, ...rest } = to.query;
        return { path: tab === "admin" ? "/admin/login" : "/owner/login", query: rest };
      }
    },
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
  {
    // 公开成绩单：无需登录（中介转发给家长的信任凭证）
    path: "/public/teacher/:id/scorecard",
    name: "TeacherScorecard",
    component: () => import("@/views/public/TeacherScorecard.vue"),
    meta: { title: "教员成绩单" },
  },
  {
    // 法务文档：用户协议 / 隐私政策（公开可访问）
    path: "/terms",
    name: "TermsOfService",
    component: () => import("@/views/public/LegalPage.vue"),
    props: { doc: "terms" as const },
    meta: { title: "用户协议" },
  },
  {
    path: "/privacy",
    name: "PrivacyPolicy",
    component: () => import("@/views/public/LegalPage.vue"),
    props: { doc: "privacy" as const },
    meta: { title: "隐私政策" },
  },

  // ── B 端（中介后台） ──
  {
    path: "/admin",
    redirect: "/admin/dashboard",
  },
  {
    // 中介独立登录入口（不再重定向到教员登录页的角色标签）
    path: "/admin/login",
    name: "AdminLogin",
    component: () => import("@/views/teacher/Login.vue"),
    props: { role: "admin" as const },
    meta: { title: "中介登录", guest: true },
  },
  {
    // 老板独立登录入口：不在任何页面挂链接，仅直达 URL 访问
    path: "/owner/login",
    name: "OwnerLogin",
    component: () => import("@/views/teacher/Login.vue"),
    props: { role: "owner" as const },
    meta: { title: "平台管理登录", guest: true },
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
    return next(loginRouteFor(to.meta.role, to.fullPath));
  }

  // 有本地 token 也不代表会话仍然有效，进入受保护页面向后端确认。
  // 仅 401 才是会话失效：网络抖动/服务端异常不推翻本地登录态（fetchMe 失败不缓存，下次导航自动重试）
  if (to.meta.auth && auth.token) {
    try {
      await auth.fetchMe();
    } catch (e) {
      if (getApiErrorStatus(e) === 401) {
        auth.logout();
        return next(loginRouteFor(to.meta.role, to.fullPath));
      }
      showToast("网络异常，部分数据可能加载失败");
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

  // 角色检查：走错端不踢出会话，送回该角色自己的首页
  if (to.meta.role && auth.role !== to.meta.role && auth.role !== "super_admin") {
    const home = auth.role === "tenant_admin"
      ? "/admin/dashboard"
      : auth.role === "super_admin"
        ? "/owner/tenants"
        : "/";
    showToast("您没有访问该页面的权限，已返回首页");
    return next(home);
  }

  next();
});

// 发版后旧页面懒加载已删除的 chunk 会直接白屏：兜底整页刷新加载新版本
router.onError((error, to) => {
  const message = String((error as { message?: string })?.message || "");
  if (message.includes("Failed to fetch dynamically imported module") || message.includes("Importing a module script failed")) {
    window.location.href = to.fullPath;
  }
});

export default router;
