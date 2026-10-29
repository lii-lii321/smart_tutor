import { showToast } from "vant";

/**
 * 剪贴板写入：HTTPS 环境走 Clipboard API；HTTP（如备案前的裸 IP 访问）没有
 * navigator.clipboard，回退 execCommand（隐藏 textarea 选中复制，全浏览器可用）。
 * 返回是否成功，调用方可自行决定失败文案。
 */
export async function copyToClipboard(text: string): Promise<boolean> {
  if (window.isSecureContext && navigator.clipboard) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch {
      // 权限拒绝等场景继续走回退，不直接判失败
    }
  }
  try {
    const textarea = document.createElement("textarea");
    textarea.value = text;
    textarea.setAttribute("readonly", "");
    textarea.style.position = "fixed";
    textarea.style.opacity = "0";
    document.body.appendChild(textarea);
    textarea.select();
    const ok = document.execCommand("copy");
    document.body.removeChild(textarea);
    return ok;
  } catch {
    return false;
  }
}

/** 剪贴板复制 + toast 反馈（移动端无感失败时给出可见提示） */
export async function copyContact(text: string, message: string) {
  showToast((await copyToClipboard(text)) ? message : "复制失败，请手动复制");
}
