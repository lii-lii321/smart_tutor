import { useRouter } from "vue-router";

/** 返回键跟随来路：站内跳入就 back，一层一层退回（从审核页跳入就退回审核页）；
 *  直链/新标签进入（无历史）才兜底到语义父级。
 *  OrderWorkspace 的 goBack 模式（4a72d0f）提炼推广到全部 B 端页面。 */
export function useSmartBack(fallback: string) {
  const router = useRouter();
  function goBack() {
    if (window.history.state && window.history.state.back) router.back();
    else router.push(fallback);
  }
  return { goBack };
}
