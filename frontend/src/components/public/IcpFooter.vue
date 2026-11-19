<script setup lang="ts">
/**
 * ICP 备案页脚（工信部要求网站底部标注备案号并链接工信部官网）。
 * 备案号常量在 constants/site.ts——页脚组件与 lite 地图浮层共同消费。
 */
import { SITE_ICP_NUMBER, SITE_ICP_URL } from "@/constants/site";

withDefaults(defineProps<{ showTerms?: boolean }>(), { showTerms: false });
</script>

<template>
  <div class="py-4 text-center text-[11px] leading-4 text-muted">
    <a
      class="text-muted underline-offset-2 hover:text-secondary"
      :href="SITE_ICP_URL"
      target="_blank"
      rel="noopener noreferrer"
    >{{ SITE_ICP_NUMBER }}</a>
    <template v-if="showTerms">
      <span class="mx-1">·</span>
      <a class="text-muted hover:text-secondary" href="/terms">《用户协议》</a>
      <span class="mx-1">·</span>
      <a class="text-muted hover:text-secondary" href="/privacy">《隐私政策》</a>
    </template>
  </div>
</template>
