import { describe, expect, it, vi } from "vitest";
import { usePagedList } from "@/composables/usePagedList";

interface Row {
  id: number;
  label: string;
}

const row = (id: number): Row => ({ id, label: `row-${id}` });

/** 固定页数据的 fetcher：pages[i] 为第 i+1 页返回的条目，total 可选。 */
function mockFetcher(pages: Row[][], total?: number) {
  const calls: number[] = [];
  const fetcher = vi.fn(async (page: number) => {
    calls.push(page);
    return { items: pages[page - 1] ?? [], total };
  });
  return { fetcher, calls };
}

describe("usePagedList load", () => {
  it("拉取第一页并整体替换列表，total 来自后端", async () => {
    const { fetcher } = mockFetcher([[row(1), row(2)]], 5);
    const list = usePagedList<Row>(fetcher, { pageSize: 2 });

    await list.load();

    expect(fetcher).toHaveBeenCalledWith(1, 2);
    expect(list.items.value.map((r) => r.id)).toEqual([1, 2]);
    expect(list.total.value).toBe(5);
    expect(list.loading.value).toBe(false);
    expect(list.hasMore.value).toBe(true);
  });

  it("请求失败时异常上抛且 loading 复位", async () => {
    const fetcher = vi.fn(async () => {
      throw new Error("boom");
    });
    const list = usePagedList<Row>(fetcher);

    await expect(list.load()).rejects.toThrow("boom");
    expect(list.loading.value).toBe(false);
  });

  it("重新 load 回到第一页并替换旧内容", async () => {
    const { fetcher } = mockFetcher([[row(1), row(2)], [row(3)]], 3);
    const list = usePagedList<Row>(fetcher, { pageSize: 2 });

    await list.load();
    await list.loadMore();
    await list.load();

    expect(fetcher.mock.calls.map((c) => c[0])).toEqual([1, 2, 1]);
    expect(list.items.value.map((r) => r.id)).toEqual([1, 2]);
  });
});

describe("usePagedList loadMore", () => {
  it("追加下一页并按 id 去重", async () => {
    const { fetcher } = mockFetcher([[row(1), row(2)], [row(2), row(3)]], 3);
    const list = usePagedList<Row>(fetcher, { pageSize: 2 });

    await list.load();
    await list.loadMore();

    expect(list.items.value.map((r) => r.id)).toEqual([1, 2, 3]);
    expect(list.hasMore.value).toBe(false);
  });

  it("hasMore 为 false 时不再发请求", async () => {
    const { fetcher } = mockFetcher([[row(1)]], 1);
    const list = usePagedList<Row>(fetcher, { pageSize: 2 });

    await list.load();
    await list.loadMore();

    expect(fetcher).toHaveBeenCalledTimes(1);
  });

  it("加载中重复调用合并为一次请求", async () => {
    let release!: () => void;
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    const fetcher = vi.fn(async (page: number) => {
      if (page === 2) {
        await gate;
      }
      return { items: [row(page)], total: 2 };
    });
    const list = usePagedList<Row>(fetcher, { pageSize: 1 });
    await list.load();

    const pending = list.loadMore();
    await list.loadMore();
    release();
    await pending;

    expect(fetcher).toHaveBeenCalledTimes(2);
    expect(list.items.value.map((r) => r.id)).toEqual([1, 2]);
  });
});

describe("usePagedList hasMore 推断与 reset", () => {
  it("无 total 时按「末页不满」推断", async () => {
    const { fetcher } = mockFetcher([[row(1), row(2)], [row(3)]]);
    const list = usePagedList<Row>(fetcher, { pageSize: 2 });

    await list.load();
    expect(list.hasMore.value).toBe(true);

    await list.loadMore();
    expect(list.hasMore.value).toBe(false);
  });

  it("reset 清空列表回到初始态", async () => {
    const { fetcher } = mockFetcher([[row(1), row(2)]], 2);
    const list = usePagedList<Row>(fetcher, { pageSize: 2 });

    await list.load();
    list.reset();

    expect(list.items.value).toEqual([]);
    expect(list.total.value).toBe(0);
    expect(list.hasMore.value).toBe(false);

    await list.load();
    expect(list.items.value).toHaveLength(2);
    expect(fetcher).toHaveBeenLastCalledWith(1, 2);
  });

  it("支持自定义 keyOf 去重", async () => {
    const fetcher = vi.fn(async (page: number) => ({
      items: [{ id: page, label: "a" }, { id: page + 10, label: "b" }],
    }));
    const list = usePagedList<{ id: number; label: string }>(fetcher, {
      pageSize: 2,
      keyOf: (item) => item.label,
    });

    await list.load();
    await list.loadMore();

    expect(list.items.value.map((r) => r.label)).toEqual(["a", "b"]);
  });
});
