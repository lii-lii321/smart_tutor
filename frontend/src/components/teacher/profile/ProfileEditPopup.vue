<script setup lang="ts">
/**
 * 编辑个人资料弹层（自 Profile.vue 拆出）：基础资料 + 常驻地定位（逆地理编码到城市·区粒度）。
 * 打开时从 auth store 回填，保存后回写 store。
 */
import { computed, ref, watch } from "vue";
import { getApiErrorMessage } from "@/utils/apiError";
import { useAuthStore } from "@/stores/auth";
import { authApi } from "@/api/auth";
import { geoApi, type NearbyPoi } from "@/api/geo";
import { loadAMap, locateCurrentPosition } from "@/utils/amap";
import { showToast } from "vant";

const show = defineModel<boolean>("show", { default: false });

const auth = useAuthStore();

const profileSaving = ref(false);
const profileForm = ref({
  name: "",
  gender: "male" as "male" | "female",
  wechat_id: "",
  school: "",
  major: "",
  grade: "",
  highlights: "",
  home_area: "",
});
const profileCoords = ref<{ lng: number; lat: number } | null>(null);
const locating = ref(false);
// 地点候选：定位后为附近地点；桌面 IP 定位误差可达数十公里，
// 关键字搜索（如"西南石油大学"）才是准确的选点方式
const nearbyPois = ref<NearbyPoi[]>([]);
const nearbyLoading = ref(false);
const selectedPoi = ref<NearbyPoi | null>(null);
const locatedPrefix = ref("");
const searchKeyword = ref("");
const searching = ref(false);
const hasSearched = ref(false);
const poiSource = ref<"nearby" | "search">("nearby");
const listTitle = computed(() =>
  poiSource.value === "search"
    ? "搜索结果（点选填入常驻地）"
    : "附近地点（点选更精确；不在附近就用上方搜索）"
);

watch(show, (visible) => {
  if (!visible) return;
  const t = auth.teacher;
  profileForm.value = {
    name: t?.name || "",
    gender: t?.gender === "female" ? "female" : "male",
    wechat_id: t?.wechat_id || "",
    school: t?.school || "",
    major: t?.major || "",
    grade: t?.grade || "",
    highlights: t?.highlights || "",
    home_area: t?.home_area || "",
  };
  profileCoords.value =
    t?.lng != null && t?.lat != null ? { lng: Number(t.lng), lat: Number(t.lat) } : null;
  nearbyPois.value = [];
  selectedPoi.value = null;
  locatedPrefix.value = "";
  searchKeyword.value = "";
  hasSearched.value = false;
  poiSource.value = "nearby";
});

async function locateHomeArea() {
  if (locating.value) return;
  locating.value = true;
  nearbyPois.value = [];
  selectedPoi.value = null;
  poiSource.value = "nearby";
  try {
    const AMap = await loadAMap();
    const [lng, lat] = await locateCurrentPosition(AMap);
    profileCoords.value = { lng, lat };
    // 逆地理/附近 POI 走后端 REST（Web服务 Key）：浏览器 JSAPI 的服务调用
    // 需要另一种 key 类型 + 安全密钥，现有 key 只能走 REST
    const areaText = await geoApi.reverseArea(lng, lat);
    if (areaText) {
      profileForm.value.home_area = areaText;
      locatedPrefix.value = areaText;
    }
    showToast(areaText ? "已定位，可从下方选择更精确的位置" : "已使用定位坐标");
    // 附近可选地点是增强能力：拉不到就让用户保留区级文本
    nearbyLoading.value = true;
    nearbyPois.value = await geoApi.nearbyPois(lng, lat);
  } catch {
    showToast("定位失败，请允许浏览器使用位置信息");
  } finally {
    locating.value = false;
    nearbyLoading.value = false;
  }
}

async function doSearchPois() {
  const keyword = searchKeyword.value.trim();
  if (!keyword || searching.value) return;
  searching.value = true;
  selectedPoi.value = null;
  nearbyPois.value = [];
  try {
    // 城市相关性：从已有常驻地的"城市"前缀推导（如"成都·武侯区"→"成都"），
    // 不再默认成都——外地中介的教员搜"××大学"应命中本地结果
    const city = (profileForm.value.home_area || "").split("·")[0]?.trim();
    nearbyPois.value = await geoApi.searchPois(keyword, city || undefined);
    poiSource.value = "search";
    hasSearched.value = true;
  } catch {
    showToast("搜索失败，请稍后重试");
  } finally {
    searching.value = false;
  }
}

function selectPoi(poi: NearbyPoi) {
  selectedPoi.value = poi;
  profileCoords.value = { lng: poi.lng, lat: poi.lat };
  // 优先用 POI 自带的省市区（搜索结果可能远离定位点），退化到定位前缀
  const prefix = poi.area || locatedPrefix.value;
  profileForm.value.home_area = prefix ? `${prefix}·${poi.name}` : poi.name;
}

async function saveProfile() {
  if (!profileForm.value.name.trim() || !profileForm.value.school.trim() || !profileForm.value.wechat_id.trim()) {
    showToast("姓名、院校和微信号为必填");
    return;
  }
  profileSaving.value = true;
  try {
    const updated = await authApi.updateTeacherProfile({
      name: profileForm.value.name.trim(),
      gender: profileForm.value.gender,
      wechat_id: profileForm.value.wechat_id.trim(),
      school: profileForm.value.school.trim(),
      major: profileForm.value.major.trim() || undefined,
      grade: profileForm.value.grade.trim() || undefined,
      highlights: profileForm.value.highlights.trim() || undefined,
      home_area: profileForm.value.home_area.trim() || undefined,
      ...(profileCoords.value
        ? { lng: profileCoords.value.lng, lat: profileCoords.value.lat }
        : {}),
    });
    auth.setTeacher(updated);
    show.value = false;
    showToast("资料已更新");
  } catch (e) {
    showToast(getApiErrorMessage(e, "保存失败"));
  } finally {
    profileSaving.value = false;
  }
}
</script>

<template>
  <van-popup v-model:show="show" round position="bottom" close-on-click-overlay>
    <div class="max-h-[82vh] overflow-y-auto p-4">
      <div class="mb-1 text-base font-semibold text-slate-950">编辑个人资料</div>
      <div class="mb-3 text-xs leading-5 text-slate-400">
        填写常驻地后，推荐排序会优先考虑订单与你的距离。
      </div>

      <van-field v-model="profileForm.name" label="姓名" placeholder="真实姓名" required maxlength="20" />
      <van-field label="性别">
        <template #input>
          <van-radio-group v-model="profileForm.gender" direction="horizontal">
            <van-radio name="male">男</van-radio>
            <van-radio name="female">女</van-radio>
          </van-radio-group>
        </template>
      </van-field>
      <van-field v-model="profileForm.wechat_id" label="微信号" placeholder="家长/中介联系用" required maxlength="50" />
      <van-field v-model="profileForm.school" label="院校" placeholder="就读/毕业院校" required maxlength="50" />
      <van-field v-model="profileForm.major" label="专业" placeholder="选填" maxlength="50" />
      <van-field v-model="profileForm.grade" label="年级" placeholder="如：研二 / 大四" maxlength="20" />
      <van-field
        v-model="profileForm.highlights"
        label="个人亮点"
        type="textarea"
        rows="2"
        autosize
        maxlength="200"
        placeholder="如：耐心细致，擅长口语启蒙"
      />
      <van-field
        v-model="profileForm.home_area"
        label="常驻地"
        placeholder="如：成都·武侯区"
        maxlength="100"
      >
        <template #button>
          <button
            class="flex shrink-0 items-center gap-0.5 text-xs font-medium text-blue-600 disabled:opacity-50"
            :disabled="locating"
            @click="locateHomeArea"
          >
            <van-icon name="location-o" />
            {{ locating ? "定位中..." : "定位" }}
          </button>
        </template>
      </van-field>
      <div v-if="profileCoords" class="px-4 pb-1 text-xs text-emerald-600">
        ✓ 已使用定位坐标，推荐将按此计算距离
        <span v-if="selectedPoi">（{{ selectedPoi.name }}）</span>
      </div>

      <!-- 地点候选面板：关键字搜索 + 定位后的附近地点，点选填入常驻地 -->
      <div class="mb-1 mx-1 rounded-xl border border-slate-100 bg-white">
        <div class="flex items-center gap-2 px-3 pt-2">
          <input
            v-model="searchKeyword"
            class="min-w-0 flex-1 rounded-lg border border-slate-200 px-2 py-1.5 text-sm outline-none focus:border-blue-400"
            placeholder="按名称搜地点，如：西南石油大学"
            maxlength="50"
            @keyup.enter="doSearchPois"
          />
          <button
            class="shrink-0 rounded-lg bg-slate-100 px-3 py-1.5 text-xs font-medium text-slate-700 disabled:opacity-50"
            :disabled="searching || !searchKeyword.trim()"
            @click="doSearchPois"
          >
            {{ searching ? "搜索中..." : "搜索地点" }}
          </button>
        </div>
        <div class="px-3 pt-1.5 pb-1 text-xs text-slate-400">{{ listTitle }}</div>
        <div v-if="nearbyLoading || searching" class="px-3 pb-2 text-xs text-slate-400">
          {{ searching ? "搜索中..." : "正在搜索附近地点..." }}
        </div>
        <div v-else-if="nearbyPois.length > 0" class="max-h-44 overflow-y-auto pb-1">
          <button
            v-for="(poi, index) in nearbyPois"
            :key="`${poi.name}-${index}`"
            class="flex w-full items-center justify-between gap-2 px-3 py-2 text-left active:bg-slate-50"
            @click="selectPoi(poi)"
          >
            <span class="min-w-0">
              <span class="block truncate text-sm text-slate-800">{{ poi.name }}</span>
              <span v-if="poi.address" class="block truncate text-xs text-slate-400">{{ poi.address }}</span>
            </span>
            <van-icon
              v-if="selectedPoi === poi"
              name="success"
              color="#2563eb"
            />
          </button>
        </div>
        <div v-else-if="hasSearched" class="px-3 pb-2 text-xs text-slate-400">
          没有找到相关地点，换个关键词试试
        </div>
      </div>

      <button
        class="mt-3 w-full rounded-xl bg-blue-600 py-3 text-sm font-semibold text-white disabled:opacity-50"
        :disabled="profileSaving"
        @click="saveProfile"
      >
        {{ profileSaving ? "保存中..." : "保存资料" }}
      </button>
    </div>
  </van-popup>
</template>
