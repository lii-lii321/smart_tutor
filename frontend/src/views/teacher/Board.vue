<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import client from "@/api/client";
import { useAuthStore } from "@/stores/auth";

interface OrderBrief {
  id: number;
  grade_subject: string;
  price_total: string;
  base_price: number;
  weekly_frequency: number;
  fuzzy_address: string;
  subway_remark?: string | null;
  lng: number;
  lat: number;
  calculated_info_fee: number;
  deposit_amount: number;
  balance_amount: number;
  needs_manual_price: boolean;
  created_at?: string | null;
}

interface ResumeSnapshot {
  id: number;
  teacher_id: number;
  title: string;
  teaching_subjects: string;
  teaching_grades: string;
  experience: string;
  strengths?: string | null;
  availability?: string | null;
  expected_rate?: string | null;
  is_default: boolean;
}

interface ScoreBreakdown {
  distance: number;
  subject: number;
  grade: number;
  school: number;
  price: number;
  history: number;
}

interface RecommendationItem extends OrderBrief {
  status: string;
  total_score: number;
  score_breakdown: ScoreBreakdown;
  reasons: string[];
  distance_km?: number | null;
  already_applied: boolean;
  application_id?: number | null;
  application_status?: string | null;
  matched_subject?: string | null;
  matched_grade?: string | null;
  best_resume?: ResumeSnapshot | null;
}

interface PublicBoardResponse {
  tenant_name: string;
  invite_code: string;
  orders: OrderBrief[];
}

interface RecommendationResponse {
  tenant_name: string;
  invite_code: string;
  count: number;
  items: RecommendationItem[];
}

const route = useRoute();
const router = useRouter();
const auth = useAuthStore();

const tenantName = ref("");
const inviteCode = computed(() => String(route.params.inviteCode || ""));
const publicOrders = ref<OrderBrief[]>([]);
const recommendations = ref<RecommendationItem[]>([]);
const loading = ref(true);
const recLoading = ref(false);
const error = ref("");

const stats = computed(() => ({
  total: publicOrders.value.length,
  recommended: recommendations.value.length,
}));

onMounted(async () => {
  await loadBoard();
  if (auth.isTeacher) {
    await loadRecommendations();
  }
});

async function loadBoard() {
  loading.value = true;
  error.value = "";
  try {
    const res = await client.get<PublicBoardResponse>(`/public/agent/${inviteCode.value}/board`);
    tenantName.value = res.data.tenant_name;
    publicOrders.value = res.data.orders || [];
  } catch (err: any) {
    error.value = err?.response?.data?.detail || "看板加载失败";
  } finally {
    loading.value = false;
  }
}

async function loadRecommendations() {
  recLoading.value = true;
  try {
    await auth.fetchMe().catch(() => null);
    const res = await client.get<RecommendationResponse>(`/public/agent/${inviteCode.value}/recommendations`, {
      params: { limit: 12 },
    });
    recommendations.value = res.data.items || [];
    if (!tenantName.value) {
      tenantName.value = res.data.tenant_name;
    }
  } catch {
    recommendations.value = [];
  } finally {
    recLoading.value = false;
  }
}

function scoreWidth(score: number) {
  return `${Math.max(0, Math.min(100, score))}%`;
}

function formatDistance(item: RecommendationItem) {
  if (typeof item.distance_km !== "number") return "距离待完善";
  if (item.distance_km < 1) return `${Math.round(item.distance_km * 1000)} 米`;
  return `${item.distance_km.toFixed(1)} km`;
}

function openOrder(orderId: number) {
  router.push(`/teacher/orders/${orderId}`);
}

function loginPath() {
  router.push(`/teacher/login?invite_code=${encodeURIComponent(inviteCode.value)}`);
}
</script>

<template>
  <div class="board-page">
    <header class="hero">
      <div>
        <p class="eyebrow">教员橱窗</p>
        <h1>{{ tenantName || inviteCode }}</h1>
        <p class="subtle">公开订单 + 个性化推荐</p>
      </div>
      <div class="hero-meta">
        <span>公开单 {{ stats.total }}</span>
        <span v-if="stats.recommended">推荐单 {{ stats.recommended }}</span>
      </div>
    </header>

    <section class="panel" v-if="auth.isTeacher">
      <div class="panel-head">
        <div>
          <h2>智能推荐</h2>
          <p>按学校、专业、年级、科目、位置、报价和历史投递综合排序。</p>
        </div>
        <button class="ghost-btn" @click="loadRecommendations" :disabled="recLoading">刷新</button>
      </div>

      <div v-if="recLoading" class="empty">正在计算推荐分...</div>
      <div v-else-if="recommendations.length" class="card-list">
        <article v-for="item in recommendations" :key="item.id" class="rec-card">
          <div class="rec-top">
            <div>
              <h3>{{ item.grade_subject }}</h3>
              <p>{{ item.fuzzy_address }} · {{ formatDistance(item) }}</p>
            </div>
            <div class="score-pill">{{ item.total_score }} 分</div>
          </div>

          <div class="score-grid">
            <div v-for="entry in [
              ['距离', item.score_breakdown.distance],
              ['科目', item.score_breakdown.subject],
              ['年级', item.score_breakdown.grade],
              ['院校', item.score_breakdown.school],
              ['课酬', item.score_breakdown.price],
              ['历史', item.score_breakdown.history],
            ]" :key="entry[0]" class="score-row">
              <span>{{ entry[0] }}</span>
              <div class="bar"><div class="fill" :style="{ width: scoreWidth(Number(entry[1])) }"></div></div>
              <strong>{{ entry[1] }}</strong>
            </div>
          </div>

          <ul class="reason-list">
            <li v-for="reason in item.reasons" :key="reason">{{ reason }}</li>
          </ul>

          <div class="resume-box" v-if="item.best_resume">
            <p>匹配简历：{{ item.best_resume.title }}</p>
            <small>{{ item.best_resume.teaching_subjects }} · {{ item.best_resume.teaching_grades }}</small>
          </div>

          <div class="actions">
            <span class="tag" v-if="item.already_applied">已投递</span>
            <span class="tag muted" v-else>可直接投递</span>
            <button class="primary-btn" @click="openOrder(item.id)">查看订单</button>
          </div>
        </article>
      </div>
      <div v-else class="empty">暂无匹配推荐，先把教员资料补完整。</div>
    </section>

    <section class="panel" v-else>
      <div class="panel-head">
        <div>
          <h2>登录后可看推荐</h2>
          <p>登录后系统会按你的学校、专业、年级、位置和历史投递自动排序。</p>
        </div>
        <button class="primary-btn" @click="loginPath">去登录</button>
      </div>
    </section>

    <section class="panel">
      <div class="panel-head">
        <div>
          <h2>公开订单</h2>
          <p>当前中介正在招聘的单子。</p>
        </div>
      </div>

      <div v-if="loading" class="empty">正在加载订单...</div>
      <div v-else-if="error" class="empty error">{{ error }}</div>
      <div v-else-if="publicOrders.length" class="card-list">
        <article v-for="item in publicOrders" :key="item.id" class="order-card">
          <div class="rec-top">
            <div>
              <h3>{{ item.grade_subject }}</h3>
              <p>{{ item.fuzzy_address }}</p>
            </div>
            <div class="meta-price">¥{{ item.base_price.toFixed(0) }}</div>
          </div>
          <div class="order-meta">
            <span>信息费 ¥{{ item.calculated_info_fee.toFixed(0) }}</span>
            <span>定金 ¥{{ item.deposit_amount.toFixed(0) }}</span>
            <span>尾款 ¥{{ item.balance_amount.toFixed(0) }}</span>
          </div>
        </article>
      </div>
      <div v-else class="empty">暂无公开订单。</div>
    </section>
  </div>
</template>

<style scoped>
.board-page {
  min-height: 100vh;
  background: #f8fafc;
  color: #0f172a;
  padding: 16px;
  box-sizing: border-box;
  font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}

.hero,
.panel {
  background: #fff;
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  padding: 16px;
  margin-bottom: 16px;
}

.hero {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
}

.eyebrow {
  margin: 0 0 6px;
  color: #1a365d;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0;
}

h1,
h2,
h3,
p {
  margin: 0;
}

h1 {
  font-size: 24px;
  line-height: 1.2;
}

h2 {
  font-size: 18px;
  margin-bottom: 4px;
}

.subtle,
.panel-head p,
.rec-top p,
.resume-box small,
.order-meta,
.empty {
  color: #475569;
  font-size: 13px;
  line-height: 1.5;
}

.hero-meta {
  display: flex;
  flex-direction: column;
  gap: 6px;
  color: #1e293b;
  font-size: 13px;
  text-align: right;
  padding-top: 4px;
}

.panel-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
  margin-bottom: 12px;
}

.card-list {
  display: grid;
  gap: 12px;
}

.rec-card,
.order-card {
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  padding: 14px;
  background: #fff;
}

.rec-top {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 12px;
}

.score-pill,
.meta-price {
  background: #1a365d;
  color: #fff;
  border-radius: 999px;
  padding: 6px 10px;
  font-size: 13px;
  font-weight: 700;
  white-space: nowrap;
}

.score-grid {
  display: grid;
  gap: 8px;
  margin-bottom: 12px;
}

.score-row {
  display: grid;
  grid-template-columns: 34px 1fr 30px;
  gap: 8px;
  align-items: center;
  font-size: 12px;
  color: #334155;
}

.bar {
  height: 8px;
  background: #e2e8f0;
  border-radius: 999px;
  overflow: hidden;
}

.fill {
  height: 100%;
  background: #2563eb;
  border-radius: inherit;
}

.reason-list {
  margin: 0 0 12px;
  padding-left: 18px;
  color: #334155;
  font-size: 13px;
}

.resume-box {
  border: 1px solid #dbeafe;
  background: #eff6ff;
  border-radius: 10px;
  padding: 10px 12px;
  margin-bottom: 12px;
}

.actions {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
}

.order-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.tag {
  color: #1a365d;
  background: #dbeafe;
  border-radius: 999px;
  padding: 4px 10px;
  font-size: 12px;
}

.tag.muted {
  background: #f1f5f9;
  color: #334155;
}

.primary-btn,
.ghost-btn {
  border-radius: 8px;
  border: 1px solid #2563eb;
  padding: 8px 12px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
}

.primary-btn {
  background: #2563eb;
  color: #fff;
}

.ghost-btn {
  background: #fff;
  color: #2563eb;
}

.empty {
  padding: 14px 0 4px;
}

.empty.error {
  color: #b91c1c;
}

@media (max-width: 640px) {
  .hero,
  .panel-head,
  .actions {
    flex-direction: column;
  }

  .hero-meta {
    text-align: left;
  }
}
</style>
