<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { nationwideRegions } from "@/data/regions";

/**
 * 城市选择弹层（自 Board.vue 拆出，P1-1）：
 * 省份 → 城市两级选择 + 搜索；城市选项由父级聚合（静态省份表 + 订单地址归并）。
 */
const props = defineProps<{
  show: boolean;
  city: string;
  options: string[];
}>();

const emit = defineEmits<{
  (e: "update:show", value: boolean): void;
  (e: "update:city", value: string): void;
}>();

const citySearch = ref("");
const selectedProvince = ref("");

// 打开时重置搜索，并按当前选中城市预选省份
watch(
  () => props.show,
  (visible) => {
    if (visible) {
      citySearch.value = "";
      selectedProvince.value = nationwideRegions.find((region) => region.cities.includes(props.city))?.name || "";
    }
  }
);

const provinceOptions = computed(() => nationwideRegions.map((region) => region.name));

const selectedProvinceCities = computed(() => {
  return nationwideRegions.find((region) => region.name === selectedProvince.value)?.cities || [];
});

const visibleCityOptions = computed(() => {
  const keyword = normalizeText(citySearch.value);
  if (!keyword) return selectedProvinceCities.value;
  return selectedProvinceCities.value.filter((city) => normalizeText(formatCityName(city)).includes(keyword));
});

function normalizeText(value: unknown) {
  return String(value || "").replace(/\s+/g, "").toLowerCase();
}

function formatCityName(city: string) {
  return city.replace(/市$/, "");
}

function formatProvinceName(province: string) {
  return province.replace(/壮族自治区|回族自治区|维吾尔自治区|自治区|特别行政区|省|市$/, "");
}

function selectProvince(province: string) {
  selectedProvince.value = province;
  citySearch.value = "";
}

function selectCity(city: string) {
  emit("update:city", city);
  emit("update:show", false);
}
</script>

<template>
  <van-popup :show="show" round position="bottom" @update:show="(value: boolean) => emit('update:show', value)">
    <div class="max-h-[78vh] overflow-y-auto p-4">
      <div class="mb-3 text-base font-semibold text-slate-950">选择城市</div>
      <button
        class="mb-3 rounded-lg px-3 py-2 text-sm font-medium"
        :class="city === 'all' ? 'bg-blue-600 text-white' : 'bg-slate-100 text-slate-700'"
        @click="selectCity('all')"
      >
        全部城市
      </button>

      <template v-if="selectedProvince">
        <div class="mb-2 text-xs font-medium text-slate-500">{{ selectedProvince }} · 选择城市</div>
        <van-field v-model="citySearch" class="mb-3 rounded-lg bg-slate-50" placeholder="搜索城市" clearable />
        <button class="mb-3 rounded-lg bg-slate-100 px-3 py-2 text-sm font-medium text-slate-700" @click="selectProvince('')">
          更换省份
        </button>
        <div class="flex flex-wrap gap-2">
          <button
            v-for="option in visibleCityOptions"
            :key="option"
            class="rounded-lg px-3 py-2 text-sm font-medium"
            :class="option === city ? 'bg-blue-600 text-white' : 'bg-slate-100 text-slate-700'"
            @click="selectCity(option)"
          >
            {{ formatCityName(option) }}
          </button>
        </div>
        <div v-if="visibleCityOptions.length === 0" class="mt-3 text-xs text-slate-400">
          没有匹配的城市
        </div>
      </template>
      <template v-else>
        <div class="mb-2 text-xs font-medium text-slate-500">先选择省份</div>
        <div class="grid grid-cols-4 gap-2">
          <button
            v-for="province in provinceOptions"
            :key="province"
            class="min-w-0 rounded-lg bg-slate-100 px-1.5 py-2 text-sm font-medium text-slate-700"
            @click="selectProvince(province)"
          >
            {{ formatProvinceName(province) }}
          </button>
        </div>
      </template>
    </div>
  </van-popup>
</template>
