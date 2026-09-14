<script setup lang="ts">
/**
 * 编辑个人资料弹层（自 Profile.vue 拆出）：基础资料 + 常驻地定位（逆地理编码到城市·区粒度）。
 * 打开时从 auth store 回填，保存后回写 store。
 */
import { ref, watch } from "vue";
import { getApiErrorMessage } from "@/utils/apiError";
import { useAuthStore } from "@/stores/auth";
import { authApi } from "@/api/auth";
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
});

async function locateHomeArea() {
  if (locating.value) return;
  locating.value = true;
  try {
    const AMap = await loadAMap();
    const [lng, lat] = await locateCurrentPosition(AMap);
    profileCoords.value = { lng, lat };
    // 逆地理编码取"城市·区"粒度文本，避免暴露精确住址
    await new Promise<void>((resolve) => {
      const geocoder = new AMap.Geocoder();
      geocoder.getAddress([lng, lat], (status, result) => {
        if (status === "complete" && result?.regeocode) {
          const comp = result.regeocode.addressComponent || {};
          const city = String(comp.city || comp.province || "").replace(/市$/, "");
          const district = comp.district || "";
          profileForm.value.home_area = district ? `${city}·${district}` : String(result.regeocode.formattedAddress || "");
        }
        resolve();
      });
    });
    showToast("已定位当前位置");
  } catch {
    showToast("定位失败，请允许浏览器使用位置信息");
  } finally {
    locating.value = false;
  }
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
