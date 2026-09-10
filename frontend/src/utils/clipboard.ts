import { showToast } from "vant";

/** 剪贴板复制 + toast 反馈（移动端无感失败时给出可见提示） */
export async function copyContact(text: string, message: string) {
  try {
    await navigator.clipboard.writeText(text);
    showToast(message);
  } catch {
    showToast("复制失败，请手动复制");
  }
}
