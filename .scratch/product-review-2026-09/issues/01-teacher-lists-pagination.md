# 01 教员侧核心列表补分页

Status: ready-for-agent

## 现状

- `GET /applications/mine`（我的投递）全量返回
- `GET /notifications/mine`、`/tenant-mine` 仅 limit<=100，无翻页
- `GET /financial-records/mine`（我的费用）全量返回

活跃教员一年后投递/通知/流水上千条，H5 首屏载荷线性膨胀。

## 建议

三个接口补 `page/page_size/total`，前端仿 OrdersList 的"加载更多"模式；
通知可顺带引入"进入页面即自动标记可见条目已读"。

Blocked by: —
