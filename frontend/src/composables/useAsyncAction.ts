import { ref, type Ref } from "vue";

/**
 * 统一的双击防重包装：in-flight 期间忽略重复触发，防止双击连发两次请求
 * （重置密码双击会重置两次、开关类操作双击会状态翻转两次）。
 * 返回 [包装后的函数, 忙碌标记]，模板用 :disabled="busy" 消费。
 */
export function useAsyncAction<Args extends unknown[]>(
  action: (...args: Args) => Promise<unknown>
): [(...args: Args) => Promise<void>, Ref<boolean>] {
  const busy = ref(false);

  async function run(...args: Args): Promise<void> {
    if (busy.value) return;
    busy.value = true;
    try {
      await action(...args);
    } finally {
      busy.value = false;
    }
  }

  return [run, busy];
}
