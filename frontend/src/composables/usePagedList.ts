import { computed, ref, shallowRef } from "vue";

/** fetcher 返回的分页结果；total 缺省时 hasMore 按「末页不满」推断。 */
export interface PagedResult<T> {
  items: T[];
  total?: number;
}

export interface UsePagedListOptions<T> {
  pageSize?: number;
  /** 去重键；缺省取 item.id。 */
  keyOf?: (item: T) => string | number;
}

/**
 * 「加载更多」式列表的统一状态机：loading/loadingMore/page/known 去重收敛到一处，
 * 视图只保留 fetcher 适配与自己的特有逻辑。
 * load/loadMore 的异常原样抛给调用方（toast 文案由视图决定）。
 */
export function usePagedList<T>(
  fetcher: (page: number, pageSize: number) => Promise<PagedResult<T>>,
  opts?: UsePagedListOptions<T>
) {
  const pageSize = opts?.pageSize ?? 20;
  const keyOf = opts?.keyOf ?? defaultKeyOf;

  // shallowRef：列表始终整体替换，无需对条目做深层响应式代理（也规避泛型 T 的 unwrap 类型问题）
  const items = shallowRef<T[]>([]);
  const total = ref(0);
  const loading = ref(false);
  const loadingMore = ref(false);
  const page = ref(1);
  // total 是否由后端提供；缺省时 hasMore 按「末页不满」推断
  // （必须是 ref：computed 的 hasMore 依赖它们，普通变量不会触发重算）
  const totalFromServer = ref(false);
  const lastPageCount = ref(0);
  // 翻页死端：整页返回但去重后零新增（后端分页异常），置位后停止翻页避免无限空转
  const dedupExhausted = ref(false);

  const hasMore = computed(() => {
    if (dedupExhausted.value) {
      return false;
    }
    if (totalFromServer.value) {
      return items.value.length < total.value;
    }
    return lastPageCount.value >= pageSize;
  });

  function apply(result: PagedResult<T>, replace: boolean) {
    const incoming = result.items || [];
    const existing = replace ? new Set<string | number>() : new Set(items.value.map((item) => keyOf(item)));
    const fresh = incoming.filter((item) => !existing.has(keyOf(item)));
    items.value = replace ? fresh : [...items.value, ...fresh];
    totalFromServer.value = result.total != null;
    total.value = result.total ?? items.value.length;
    lastPageCount.value = incoming.length;
    dedupExhausted.value = !replace && incoming.length > 0 && fresh.length === 0;
  }

  /** 回到第一页并整体替换列表。 */
  async function load() {
    loading.value = true;
    page.value = 1;
    try {
      apply(await fetcher(1, pageSize), true);
    } finally {
      loading.value = false;
    }
  }

  /** 追加下一页，已见过的条目（按 keyOf）去重；无更多或加载中时直接跳过。 */
  async function loadMore() {
    if (loadingMore.value || !hasMore.value) return;
    loadingMore.value = true;
    try {
      const next = page.value + 1;
      apply(await fetcher(next, pageSize), false);
      page.value = next;
    } finally {
      loadingMore.value = false;
    }
  }

  /** 清空列表回到初始态（不发起请求）。 */
  function reset() {
    items.value = [];
    total.value = 0;
    page.value = 1;
    totalFromServer.value = false;
    lastPageCount.value = 0;
    dedupExhausted.value = false;
  }

  return { items, total, loading, loadingMore, hasMore, load, loadMore, reset };
}

function defaultKeyOf<T>(item: T): string | number {
  return (item as unknown as { id: string | number }).id;
}
