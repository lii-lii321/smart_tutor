<script setup lang="ts">
/**
 * ICP 备案页脚（工信部要求网站底部标注备案号并链接工信部官网）。
 * 公安备案通过后在同区追加公安备案号（2026-12-19 前办理，编号待用户提供）。
 * 备案号改动只动这一处常量。
 */
const ICP_NUMBER = "蜀ICP备2026072597号-1";

withDefaults(defineProps<{ showTerms?: boolean }>(), { showTerms: false });
</script>

<template>
  <div class="py-4 text-center text-[11px] leading-4 text-muted">
    <a
      class="text-muted underline-offset-2 hover:text-secondary"
      href="https://beian.miit.gov.cn/"
      target="_blank"
      rel="noopener noreferrer"
    >{{ ICP_NUMBER }}</a>
    <template v-if="showTerms">
      <span class="mx-1">·</span>
      <a class="text-muted hover:text-secondary" href="/terms">《用户协议》</a>
      <span class="mx-1">·</span>
      <a class="text-muted hover:text-secondary" href="/privacy">《隐私政策》</a>
    </template>
  </div>
</template>
