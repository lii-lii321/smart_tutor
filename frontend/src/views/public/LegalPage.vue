<script setup lang="ts">
import { computed } from "vue";
import { useRoute, useRouter } from "vue-router";

const route = useRoute();
const router = useRouter();

const props = defineProps<{ doc?: "terms" | "privacy" }>();

const doc = computed(() => (props.doc === "privacy" || route.name === "PrivacyPolicy" ? "privacy" : "terms"));

const UPDATED = "2026-09-25";

interface LegalSection {
  heading: string;
  paragraphs: string[];
}

const TERMS: LegalSection[] = [
  {
    heading: "一、协议范围",
    paragraphs: [
      "欢迎使用智派家教（以下简称「本平台」）。本协议是您与平台运营方之间就使用本平台服务所订立的约定，适用于教员、中介机构（合作方）及其他访问者。",
      "您注册、登录或使用本平台，即表示已阅读并同意本协议。",
    ],
  },
  {
    heading: "二、平台定位",
    paragraphs: [
      "本平台为家教信息服务撮合平台，为中介机构与教员之间提供订单发布、投递、状态管理与信息流转工具。",
      "本平台不是教员的雇主或用工方，亦不是教学服务的直接提供方。教学服务的质量、安全与履行由教员与中介机构自行协商确定并承担责任。",
    ],
  },
  {
    heading: "三、账号与邀请码",
    paragraphs: [
      "教员凭手机号与中介邀请码注册登录；中介机构凭平台发放的邀请码与密码进入管理后台。账号仅限本人使用，请妥善保管登录凭证。",
      "存在违规行为（虚假简历、失约、骚扰家长或中介、绕开平台私下交易造成纠纷等）的账号，平台或所属中介可采取限制、封禁等措施。",
    ],
  },
  {
    heading: "四、信息费与资金",
    paragraphs: [
      "教员通过平台获取订单需向中介机构支付信息费，费用标准（定金与尾款）在订单卡片中明示。信息费由教员与中介机构线下自行结算，平台不代收、不托管、不参与分成。",
      "定金、尾款的退还规则以订单页面及中介机构公示的规则为准。因教学服务发生的纠纷，请首先与对接中介机构协商解决。",
    ],
  },
  {
    heading: "五、教员行为规范",
    paragraphs: [
      "您承诺提交的简历、院校背景、课酬期望等信息真实、准确；确认接单后按时履约；试课与授课期间遵守家庭隐私与安全规范。",
      "因提供虚假信息或违反行为规范导致的后果由您自行承担。",
    ],
  },
  {
    heading: "六、服务变更与终止",
    paragraphs: [
      "平台可能因业务调整变更或中断部分功能，将在页面内公告。若您不同意变更后的协议，可停止使用并申请注销账号。",
    ],
  },
  {
    heading: "七、联系我们",
    paragraphs: [
      "对本协议或平台服务有任何疑问，请通过页面上展示的中介联系微信，或平台公告渠道与我们联系。",
    ],
  },
];

const PRIVACY: LegalSection[] = [
  {
    heading: "一、我们收集的信息",
    paragraphs: [
      "教员账号信息：手机号、姓名、就读/毕业院校、专业、年级、简历内容（科目、经历、优势）与期望课酬。",
      "位置信息：仅当您主动授权时用于计算您与订单的距离（用于智能推荐），不用于持续追踪。",
      "订单信息由中介机构录入：包括授课区域（模糊地址）、课酬、时间要求；家长联系方式（精确地址、电话）仅中介机构可见，不向教员端展示。",
    ],
  },
  {
    heading: "二、信息的使用",
    paragraphs: [
      "用于账号识别与登录、订单匹配与智能推荐、投递流程管理、消息通知与必要的平台运营统计。",
      "平台不会将您的个人信息出售给任何第三方。",
    ],
  },
  {
    heading: "三、AI 与第三方服务",
    paragraphs: [
      "订单文本解析：中介录入的原始聊天文本会经过联系方式脱敏处理后，调用 AI 服务（DeepSeek）进行结构化解析，解析结果仅用于生成订单。",
      "地理编码：模糊地址通过高德地图服务转换为坐标用于地图展示与距离计算。",
      "错误监控：前端与后端接入 Sentry 进行异常上报，已关闭个人信息采集（send_default_pii=false）。",
      "上述服务商均仅获得完成对应功能所必需的最小信息。",
    ],
  },
  {
    heading: "四、存储与安全",
    paragraphs: [
      "家长联系方式仅中介机构可见，不向教员端展示；教员端订单信息默认脱敏（地址模糊化、电话掩码、坐标降精度）。",
      "敏感操作（联系方式查看、资金确认）记录操作审计日志，可追溯操作人与来源 IP。",
      "数据传输使用 HTTPS 加密；数据库备份仅保存在部署服务器本地。",
    ],
  },
  {
    heading: "五、您的权利",
    paragraphs: [
      "您可在个人中心查看、更正您的简历与资料，或申请注销账号。",
      "注销后，您的登录凭证立即失效；简历与投递记录将按平台留存策略删除或匿名化处理。",
    ],
  },
  {
    heading: "六、未成年人保护",
    paragraphs: [
      "本平台面向成年教员与机构用户。涉及未成年人学员的教学信息由中介机构录入与管理，平台提示相关方对未成年人信息承担更高的保护义务。",
    ],
  },
  {
    heading: "七、政策更新与联系方式",
    paragraphs: [
      "本政策可能不时更新，更新后在页面内公告。",
      "如对本政策有任何疑问、意见或请求（查询、更正、删除您的个人信息），请通过页面上展示的中介联系微信或平台公告渠道与我们联系。",
    ],
  },
];

const sections = computed(() => (doc.value === "privacy" ? PRIVACY : TERMS));
const title = computed(() => (doc.value === "privacy" ? "隐私政策" : "用户协议"));
</script>

<template>
  <div class="min-h-screen bg-page pb-16">
    <van-nav-bar :title="title" left-arrow @click-left="router.back()" />

    <div class="mx-auto max-w-2xl px-4 py-5">
      <div class="mb-4 text-xs text-muted">
        更新日期：{{ UPDATED }}
        <template v-if="doc === 'terms'">
          ·
          <router-link class="text-brand-700" to="/privacy">查看《隐私政策》</router-link>
        </template>
        <template v-else>
          ·
          <router-link class="text-brand-700" to="/terms">查看《用户协议》</router-link>
        </template>
      </div>

      <article class="space-y-5">
        <section
          v-for="section in sections"
          :key="section.heading"
          class="rounded-2xl border border-default bg-surface p-4 shadow-card"
        >
          <h2 class="text-sm font-bold text-ink">{{ section.heading }}</h2>
          <p
            v-for="(paragraph, i) in section.paragraphs"
            :key="i"
            class="mt-2 text-[13px] leading-6 text-secondary"
          >
            {{ paragraph }}
          </p>
        </section>
      </article>
    </div>
  </div>
</template>
