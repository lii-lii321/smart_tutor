import { describe, expect, it } from "vitest";
import { getApiErrorMessage, getApiErrorStatus } from "@/utils/apiError";

/** axios.isAxiosError 只依据 isAxiosError 标记，无需真请求。 */
function axiosError(extra: Record<string, unknown>): Error {
  return Object.assign(new Error("Request failed"), { isAxiosError: true, config: {} }, extra);
}

describe("getApiErrorMessage", () => {
  it("字符串 detail 直接透出（后端业务提示）", () => {
    const e = axiosError({ response: { status: 400, data: { detail: "余额尚未结清" } } });
    expect(getApiErrorMessage(e)).toBe("余额尚未结清");
  });

  it("422 数组 detail 拼接 loc（去掉 body 前缀）与 msg", () => {
    const e = axiosError({
      response: {
        status: 422,
        data: {
          detail: [
            { loc: ["body", "price"], msg: "field required" },
            { loc: ["body"], msg: "两次输入不一致" },
          ],
        },
      },
    });
    expect(getApiErrorMessage(e)).toBe("price: field required；两次输入不一致");
  });

  it("无 response（断网/超时）给网络提示", () => {
    const e = axiosError({});
    expect(getApiErrorMessage(e)).toBe("网络异常，请检查网络后重试");
  });

  it("普通 Error 透出 message", () => {
    expect(getApiErrorMessage(new Error("保存失败"))).toBe("保存失败");
  });

  it("其余回退兜底文案（含 Request failed 的 axios 默认消息）", () => {
    expect(getApiErrorMessage("boom")).toBe("操作失败，请稍后重试");
    expect(getApiErrorMessage("boom", "自定义兜底")).toBe("自定义兜底");
    expect(getApiErrorMessage(new Error("Request failed with status code 500"))).toBe(
      "操作失败，请稍后重试"
    );
  });
});

describe("getApiErrorStatus", () => {
  it("axios 错误取 HTTP 状态码", () => {
    const e = axiosError({ response: { status: 403, data: {} } });
    expect(getApiErrorStatus(e)).toBe(403);
  });

  it("无 response 的 axios 错误与普通 Error 返回 null", () => {
    expect(getApiErrorStatus(axiosError({}))).toBeNull();
    expect(getApiErrorStatus(new Error("boom"))).toBeNull();
  });
});
