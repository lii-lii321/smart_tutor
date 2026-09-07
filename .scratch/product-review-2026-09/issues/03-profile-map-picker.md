# 03 个人中心常驻地地图选点

Status: ready-for-agent

## 现状

个人中心"编辑资料"已支持常驻地文本（服务端高德地理编码）与坐标直传，
但前端只提供文本输入；文本歧义（重名小区/跨城区域）时编码可能偏差。

## 建议

编辑资料弹层加"在地图上选点"入口：复用 `utils/amap.ts` 的 `loadAMap`，
内嵌迷你地图 + 中心点取坐标（或 `locateCurrentPosition` 一键定位），
把 lng/lat 随 `PATCH /auth/teacher/profile` 一并提交。

Blocked by: —
