import { reactive } from "vue";

/**
 * 全局底部确认弹层（替代 vant 居中双按钮 showConfirmDialog）：
 * 确认/取消按钮上下堆叠、全宽大按钮、颜色分离——杜绝移动端并排按钮的误触。
 * 用法：
 *   const ok = await appConfirm({ title: "确认？", message: "...", confirmText: "确认", danger: true });
 *   if (!ok) return;
 */
export interface AppConfirmOptions {
  title?: string;
  message: string;
  confirmText?: string;
  /** 危险操作（删除/没收/注销等不可逆动作）确认按钮显示为红色 */
  danger?: boolean;
}

export const appConfirmState = reactive({
  visible: false,
  title: "",
  message: "",
  confirmText: "确认",
  danger: false,
});

let resolver: ((ok: boolean) => void) | null = null;

export function appConfirm(options: AppConfirmOptions): Promise<boolean> {
  // 已有未决弹窗时按取消结算，防止连点叠层导致 resolve 丢失
  if (resolver) resolver(false);
  appConfirmState.title = options.title ?? "确认操作";
  appConfirmState.message = options.message;
  appConfirmState.confirmText = options.confirmText ?? "确认";
  appConfirmState.danger = options.danger ?? false;
  appConfirmState.visible = true;
  return new Promise<boolean>((resolve) => {
    resolver = resolve;
  });
}

export function settleAppConfirm(ok: boolean) {
  appConfirmState.visible = false;
  resolver?.(ok);
  resolver = null;
}
