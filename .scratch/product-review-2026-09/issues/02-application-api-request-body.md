# 02 投递接口 query 传参改请求体

Status: ready-for-agent

## 现状

- `POST /applications/` 的 order_id/proposed_price/resume_id 走 query params
- `POST /applications/{id}/trial-failed` 的 refund_amount/trial_paid_by_parent/is_teacher_violated 同理

报价、简历 ID 出现在 URL query 中（访问日志/代理日志可见）；
`ApplicationRequest` schema 已在本次批次删除。

## 建议

定义 `ApplicationCreateRequest` / `TrialFailedRequest` 请求体模型，
前端 `frontend/src/api/applications.ts` 同步从 params 改 data，一并更新相关测试。

Blocked by: —
