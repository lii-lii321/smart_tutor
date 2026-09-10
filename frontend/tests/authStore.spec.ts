import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useAuthStore } from "@/stores/auth";

const { meMock } = vi.hoisted(() => ({ meMock: vi.fn() }));

vi.mock("@/api/auth", () => ({
  authApi: { me: meMock },
}));

beforeEach(() => {
  setActivePinia(createPinia());
  meMock.mockReset();
  localStorage.clear();
});

describe("auth store fetchMe", () => {
  it("60s TTL 内重复调用不重复请求", async () => {
    const store = useAuthStore();
    store.setAuth("token-1", "teacher");
    meMock.mockResolvedValue({ role: "teacher", teacher: { id: 1, name: "张三" } });

    const first = await store.fetchMe();
    const second = await store.fetchMe();

    expect(meMock).toHaveBeenCalledTimes(1);
    expect(second).toEqual(first);
    expect(second?.role).toBe("teacher");
  });

  it("并发调用合并为一次请求（in-flight 去重）", async () => {
    const store = useAuthStore();
    store.setAuth("token-1", "teacher");
    meMock.mockResolvedValue({ role: "teacher" });

    await Promise.all([store.fetchMe(), store.fetchMe(), store.fetchMe()]);

    expect(meMock).toHaveBeenCalledTimes(1);
  });

  it("失败不缓存：reject 后下次调用重新请求", async () => {
    const store = useAuthStore();
    store.setAuth("token-1", "teacher");
    meMock.mockRejectedValueOnce(new Error("network down"));

    await expect(store.fetchMe()).rejects.toThrow("network down");

    meMock.mockResolvedValue({ role: "teacher" });
    await store.fetchMe();

    expect(meMock).toHaveBeenCalledTimes(2);
  });

  it("force 跳过缓存强制请求", async () => {
    const store = useAuthStore();
    store.setAuth("token-1", "teacher");
    meMock.mockResolvedValue({ role: "teacher" });

    await store.fetchMe();
    await store.fetchMe(true);

    expect(meMock).toHaveBeenCalledTimes(2);
  });
});

describe("auth store logout", () => {
  it("清空内存状态与 localStorage", () => {
    const store = useAuthStore();
    store.setAuth("token-1", "tenant_admin");

    store.logout();

    expect(store.token).toBe("");
    expect(store.role).toBe("");
    expect(store.isLoggedIn).toBe(false);
    expect(localStorage.getItem("token")).toBeNull();
    expect(localStorage.getItem("role")).toBeNull();
    expect(localStorage.getItem("tenant")).toBeNull();
  });

  it("登出后 fetchMe 直接返回 null，不再发请求", async () => {
    const store = useAuthStore();
    store.setAuth("token-1", "teacher");
    store.logout();

    await expect(store.fetchMe()).resolves.toBeNull();
    expect(meMock).not.toHaveBeenCalled();
  });
});
