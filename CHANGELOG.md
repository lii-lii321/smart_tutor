# 更新记录

本项目按"阶段交付"推进，每个阶段在仓库留痕。日期为 2026 年。

## [0.9.0] - 业务闭环补强（触达/信任凭证/上线前置）

> 方向切换：工程质量线饱和后转向功能与业务设计（用户拍板）。
> 四项按业务杠杆排序交付。

### 上线前置包

- `scripts/generate_secrets.py`：一键生成 4 个必填生产密钥（DB×2/JWT/OWNER
  访问码），可读访问码去歧义字符，3 组属性测试
- Caddy 自动 HTTPS：`deploy/Caddyfile` + `docker-compose.https.yml` override
  （Let's Encrypt 自动签发续期，HSTS/安全头收口在 TLS 入口）
- DEPLOY_CHECKLIST 新增 §7 密钥轮换操作单（每个密钥在哪轮换/如何生效/影响面）

### 触达通道基础设施（站内信之外的推送）

- `outbound_messages` 队列表（迁移 e8a4c6d2b9f7）：与站内信**同事务**排队，
  业务回滚不发假通知；scheduler 异步投递（独立锁/异常域），失败留痕
  重试 3 次耗尽转 dead
- 通道：企业微信群机器人 / 通用 Webhook（令牌头）/ 日志兜底（未配置无感）；
  短信/订阅消息按 Channel 形态补实现即可复用投递与重试
- 关键事件接线：教员流转通知单点（`_notify_teacher`）+ B 端收到新投递/
  成交待退定金/教员取消 + 订单临期提醒
- 通道测试 7 例（httpx MockTransport）：同事务回滚、重试语义、报文格式、批内隔离

### 教员公开成绩单（中介转发给家长的信任凭证）

- `GET /public/teacher/{id}/scorecard`（无需登录）：脱敏口径与橱窗同纪律——
  姓名只露姓氏、不露联系方式/坐标，只公开成交数/违约数/评价均分与最近 20 条评语；
  封禁教员 404 与不存在同响应
- 前端 `/public/teacher/:id/scorecard` 只读页 + 系统分享/复制链接
- 分享入口：教员评价弹层（有评价才显示）+ 中介成交投递卡（新窗口打开）
- 测试 4 例锁定脱敏与聚合口径

### 收款凭证半线上化

- `financial_records.receipt_path`（迁移 f2b7e3a9c5d8）：转账截图挂流水，
  凭证随流水保留（对账红线不删）
- `services/receipts.py`：魔数校验（不信任扩展名）、≤5MB、随机文件名、
  路径穿越防护；compose 挂卷 `receipt_data` 持久化
- 上传（B 端租户隔离）/ 读取（本租户 B 端·归属教员·超管三向鉴权，越权 404），
  图片经鉴权端点下发不暴露静态路径；响应只带 has_receipt 标记
- 财务页每笔流水"传凭证/看凭证"操作；新依赖 python-multipart

**基线：pytest 213 passed（+18）/ ruff 0 / mypy 0 / vitest 59 / build 绿 / alembic 双迁移零漂移**

## [0.8.3] - 门禁收紧与工程化补全

### 类型门禁升级

- **mypy strict_optional=true**：DB 层可空列（status/weekly_frequency/deposit_amount 等）
  此前可静默流入非空注解函数，23 处流转全部显式化——订单状态流转前经
  `_current_status` 收窄（遗留 NULL 行 409 拒绝而非静默放行）、费率精算入参按
  写入默认值收窄、可空金额列展示 `_money(None)→0.0`、简历创建 teacher_id 缺失 403
- 实测抓出 FastAPI 限制：特殊参数 `response: Response | None` 注解会被拒
  （Invalid args for response field），保留 `= None` + type: ignore 并注释归因

### utcnow 统一收敛

- `datetime.utcnow()` 82 处（34 文件）收敛到 `utils/clock.utcnow`：
  取值语义不变（naive UTC），消除 Python 3.12+ DeprecationWarning；
  刻意不用 ruff UP017 建议的 `datetime.UTC` 别名（3.11+），保住 3.10 解释器下限；
  alembic 历史迁移不动

### 工程化补全

- **husky pre-commit**：提交前 ruff 全库 + 前端 eslint（秒级），`prepare` 脚本使
  npm install 自动激活
- **组件级测试起步**：vitest.config 补 @vitejs/plugin-vue；ApplicationCard
  状态→动作按钮矩阵 13 例锁定（vitest 46 → 59 例）
- Settings.vue 我的教员改增量加载（每页 50），myTeachers API 增可选分页参数
  （缺省 0 保持全量兼容，后端 SQL 分页已就绪）
- e2e.yml 增每日北京时间凌晨 5:30 定时回归；package.json 增独立 `typecheck` 脚本

## [0.8.2] - 类型基建与前端去重（审查遗留项收官）

### 类型基建（mypy 从噪音到信号）

- **models 迁 SQLAlchemy 2.0 Mapped[]/mapped_column 声明**：legacy Column 在类层面的
  静态类型是 Column[X]，实例属性的真实类型无法表达，mypy 226 个错误约 95% 是噪音；
  迁移后 DDL 元数据逐列不变（alembic check 零漂移 + 195 用例实证），mypy 0 错误基线
  成立并接入 CI 阻断
- 动态反查 relationship 统一 write_only（2.0 推荐，代码零直接使用）；
  TeacherResume.applications 补 passive_deletes=True，删除简历前显式置空投递的
  resume_id（原 dynamic 隐式行为，DB FK 无 ON DELETE 动作）
- **修复 mypy 揪出的资金精度问题**：转自带价时 float 0.0 写 DECIMAL 费率列、
  教员报价 float 直接入库——一律 Decimal 化（精算纪律对齐）；模型 deposit_amount
  默认值同步 Decimal
- rowcount 九处经 utils/db.py 统一解包；internal_stats 显式构造嵌套模型；
  批量解析响应显式 model_validate（边界校验成文）；财务 CSV 流式导出补
  FastAPI 版本依赖注释

### CI 门禁

- 覆盖率门禁：fail_under=88（实测基线 90%，3810 语句，留 2pt 缓冲），pytest-cov
  此前在依赖里但 CI 从未运行
- mypy 步骤阻断（pyproject 配置五目标，strict_optional=false 宽松起步，
  DB 可空列 Optional 收窄留作专项）

### 前端去重

- 通知列表抽共享 `NotificationList`：教员端弹窗与 B 端仪表盘此前各维护约 120 行
  管理逻辑，差异收敛为 scope prop + 文案；净删约 110 行
- MyApplications 与 ApplicationsReview 右栏投递列表复用 usePagedList：
  跨页重复条目去重与翻页死端保护统一生效

## [0.8.1] - 审查跟进整改（并发安全/口径收敛/CI 门禁）

> 触发：0.8.0 后的第二次全面审查（后端/前端/测试与基础设施三路并行），
> 按严重度逐项消号；全部工作分主题批次提交并推送（`PLAN:audit` 延续系列）。

### 并发与资金正确性

- **cancel_application 锁序修复（高）**：教员取消投递原是先锁投递行再锁订单行，
  与 B 端资金端点的全局锁序（order → application）相反，MySQL 下并发即成环
  （InnoDB 1213，资金接口随机 500）。现改为无锁定位 → 锁订单 → 锁投递，
  与 `_get_managed_application` 同范式
- teacher_match 候选池按 `Teacher.id` 排序、简历回退排序补 id 决胜——消除 MySQL
  无 ORDER BY 返回顺序不定导致的中介视角"推荐结果每次都不一样"

### 后端口径

- `mark_all_read` / `tenant_mark_all_read` 补 `deleted_at` 过滤：一键已读不再把已软删
  通知打上 `read_at`（软删行不可见的不变量在写路径同样成立）
- `create_tenant` / `blacklist_teacher` 查重补唯一约束兜底：并发下 IntegrityError 转 409
  而非裸 500（照 apply_order 既有范式）
- `highlights/experience/strengths` 补 `max_length`（2000/5000/2000）：Text 列可写且进入
  推荐评分正则，无上限单请求可塞 MB 级文本

### 前端口径

- 新增 `utils/fee.ts` 单一费率源：BatchImport 与 OrderDetail 两处费率副本收敛接入，
  修复 OrderDetail 预览漏寒暑假 2.5 倍分支、deposit 硬编码的口径漂移
- `geo.searchPois` 去掉"成都"硬编码：城市参数可空，ProfileEditPopup 从常驻地前缀推导
  （外地中介教员不再搜到成都的结果）
- 新增 `constants/orderStatus.ts`：订单状态文案/徽标唯一口径，Dashboard 与 OrdersList
  两处已分叉的映射收敛（"已完成"统一为"已成交"）
- `format.ts` 新增 `todayStr` 本地日期：财务筛选与 4 处导出文件名弃用 `toISOString`
  （东八区 0-8 点 UTC 口径错一天）

### CI 与测试

- **MySQL 方言业务验证转正（阻断）**：conftest 支持 `TEST_DATABASE_URL`（MySQL 下每用例
  drop_all+create_all 隔离），CI mysql job 新增 `test_money_flow` 业务子集——资金流此前
  只在 SQLite 方言验证，本地已对 mysql:8.4 容器实测全绿
- pip-audit / npm audit 由"记录用"改为高危阻断（实测当前零漏洞）
- 192 → **195 用例**：一键已读跳过软删行（两端）、大文本入参上限校验
- compose 五服务全部加资源上限（2C4G 目标机防 MySQL OOM 连坐）；redis 补 maxmemory LRU

## [0.8.0] - 全面审查整改（上线就绪批次）

> 触发：2026-09-13 全项目四维审查（业务后端/前端/测试/部署运维），
> 按 P0→P2 分六阶段整改，本条目为整改汇总（对应 `PLAN:audit` 系列提交）。

### 资金正确性（最高优先）

- **成交资金守卫（P1-1）**：成交时已付定金的兄弟投递自动登记 `refund_out` 流水并通知双方，
  消除"定金在台账上凭空消失"的黑洞；试课中的兄弟投递（不变量破坏）拒绝成交整体回滚
- **定金时点费率快照（P1-2）**：`applications` 新增 `fee_total/fee_deposit/fee_balance`
  （alembic `f8a3c1e5d7b9`），confirm-deposit 写入快照，尾款/退款/没收一律读快照——
  教员付定金后中介改价不再追溯；重新投递清空上一轮快照
- **财务口径单点下发（P1-3）**：投递响应新增 `fee` 字段（快照口径），前端审核页删除复刻的
  费率表/定金硬编码，改费率从此单点生效

### 安全与隐私

- parser 日志先过 `mask_contact_info` 再落盘（此前 AI 输出含家长手机号原文直接进日志）；
  重试收窄为仅网络/JSON 错误（确定性校验失败不再白烧 AI 调用费）
- `teacher-register` 补限流（唯一裸奔的微信外呼入口）；投递报价加 `le=999999.99` 上限
  （DECIMAL 溢出 500 → 参数层 422）；自带价订单导入金额服务端置零（不信任客户端）
- token 吊销比较改 `<=`：封堵同秒改密不吊销的秒级缺口
- 越权修复：超管移出黑名单恒 404（`tenant_id IS NULL`）→ 需显式 `tenant_id` 定位

### API 一致性

- 状态机收敛：`archived → recruiting` 进入白名单，批量重开与单发 republish 同口径
  （资金守卫 + 投递清理不变，completed 仍为终态）
- 查询优化：订单 count 全列子查询 → 同条件直查；LIKE 全部 `autoescape`（`%%%` 不再全表扫描）；
  batch-status 的 Redis 同步按状态聚合一次；全部写路径 Redis 操作移到 DB commit 之后
  （回滚不留幽灵订单坐标）
- 投递/试课失败入参从裸 query 改 Pydantic body（`ApplyOrderRequest`/`TrialFailedRequest`）

### 性能

- batch-parse 多段 AI 解析并发化（信号量限 3）；高德地理编码 `gather` 并发 + 连接池复用
- **修复 Redis GEO 读路径从未生效的隐藏 bug**：`GEOPOS` 返回 `[(lng,lat)]` 被按扁平坐标访问，
  真实 Redis 下必然 IndexError 后被降级兜底掩盖（fakeredis 测试暴露 + 真实 Redis 复现实锤），
  橱窗地图从此真正走 GEO 索引

### 前端工程化

- ESLint(flat) + Prettier + openapi-typescript 类型生成工具链（`npm run lint` / `gen:api`，
  CI 接入 lint）；AMap 全面类型化（官方 jsapi-types + 插件补齐声明），eslint 警告 44 → 0
- 组件拆分：Profile.vue 795→127（6 个弹层组件）、ApplicationsReview.vue 779→323
  （卡片/退费精算/评价三组件）；修复取消确认弹窗误弹"操作失败"的存量 UX bug；
  order store loading 按操作域拆分；AMap REST key 分离变量

### 测试

- 151 → **161 用例**：fee 快照 9 例、安全守卫 5 例、状态机一致性 6 例、fakeredis Redis 真实路径 6 例、
  横向越权参数化矩阵 10 例、通知/简历/橱窗形状 7 例、auth/tenants 边缘 10 例
- **覆盖率测量修正**：`concurrency=greenlet`（SQLAlchemy asyncio 经 greenlet 驱动，此前路由层
  在 DB await 后整段漏计）——真实总覆盖 57% → **87%**（notifications 100%、resumes/public 98%、
  auth 91%、applications 90%、tenants 90%）
- 用例顺序依赖修复：限流进程内计数每用例清空；owner-login 改读生效配置

### 部署与运维

- `.dockerignore` 补全（`dev.db.backup*`/`logs`/`*.log` 等曾会随 `COPY . .` 进生产镜像）+ 修正
  `.playwright-mcp` 笔误——本地敏感数据入库镜像的通道已封死（Docker 实测验证）
- 上线预检脚本 `scripts/preflight.py`（生产红线/DB 迁移到位/Redis/第三方 Key/日志目录，
  只读体检，已实测抓出迁移戳漂移）
- compose 内置 `db-backup` 服务：每日 mysqldump 到宿主机 `./backups`（保留 14 天可调）；
  MySQL root 密码与业务密码强制分离
- 全部 5 个服务带 healthcheck（scheduler 按心跳文件判假死）；nginx 公开/认证接口每 IP 限流 +
  `server_tokens off`
- DEPLOY.md 增补发版标准序列（备份→构建→迁移→预检→验证）与三层回滚手册；
  env 样例补齐 6 个缺失字段；`alembic downgrade` 的 MySQL FK 索引权衡文档化

## [0.7.3] - 联系触达与资料完善

- 教员资料可编辑：新增 `PATCH /auth/teacher/profile`（姓名/性别/微信/院校/专业/年级/亮点/常驻地），
  个人中心"编辑资料"弹层；常驻地文本无坐标时服务端高德地理编码，距离维度推荐真正生效
- 联系方式触达闭环：B 端投递列表下发教员手机号/微信号（一键复制，中介可直接线下收定金）；
  橱窗与登录响应下发中介微信，教员端橱窗工具栏与帮助中心可复制联系
- 教员取消投递（含退定金取消）即时写入 B 端站内通知
- 教员端邀请码解析统一（路由 > 登录中介 > 最近浏览 > 演示默认），移除全部硬编码演示码
- 老板端教员管理接入搜索/封禁筛选/分页加载更多；经营看板补封禁数
- B 端订单导出携带当前搜索关键字，导出与所见一致
- 性能：中介"我的教员"N+1 修复（批量信用聚合，抽至 `services/credit.py`）；
  财务汇总改 SQL 聚合；通知一键已读改单条 UPDATE
- 安全：新设密码（注册/改密/老板指定）强制同时包含字母和数字；登录不校验避免锁死老用户
- 数据：`teachers.home_area` 列 + 财务/评价表高频查询索引（alembic `c2a7e9b4d1f3`，
  DEV 老库自动补丁同步）
- 测试：新增简历库、资料编辑/联系方式/取消通知/密码复杂度回归，共 64 用例

## [0.7.2] - 产品化打磨与部署自检

- UI 统一：全部 emoji 标题/头像替换为 van-icon（-o 线性体系）；新增 favicon 与品牌标题
- 404 独立页面；中介通知"去处理"直达订单；通知角标每 60s 静默刷新
- 教员被中介拉黑后推荐区显示明确拦截原因；结算单记录带订单编号
- 新增 `scripts/smoke_test.py`：部署后一条命令全链路自检（21 项断言）
- 修复 dev 补丁缺陷：notifications 老表 teacher_id NOT NULL 未放宽导致
  B 端通知写入静默回滚（SQLite 重建表迁移约束）

## [0.7.0] - 中介级教员管理

- 新增 `tenant_teacher_blacklist`：中介可拉黑不负责任的教员（仅限本租户），
  拉黑即自动拒绝其待审投递并通知教员；投递/推荐链路 403 拦截，移出即恢复
- 中介设置页新增"我的教员"管理区（投递次数/成交/违约/评分/黑名单状态）
- 投递审核详情弹窗支持快捷拉黑

## [0.6.0] - 评价体系、信用、结算单、B 端通知、经营看板

- 成交评价：中介对成交教员 1-5 星 + 评语（一单一评可修改），教员可查看并收到通知；
  推荐历史分接入评价均分
- 教员信用画像：投递列表批量聚合成交数/违约数/评价均分
- 教员结算单：`/financial-records/mine` 费用汇总与全部流水，个人中心"我的费用"
- B 端通知：教员投递通知中介、订单临期（24h 窗口）自动提醒；工作台铃铛 + 未读角标
- 老板经营看板：平台规模/资金总览/历史口径投递漏斗/中介排行（GMV）

## [0.5.1] - 全流程实测修复

- 简历设为默认/编辑 500（onupdate 属性过期 → MissingGreenlet），flush 后 refresh
- 路由转场动画在部分 WebView 卡死导致"URL 变了页面不渲染"，移除转场；toast 过渡禁用
- Redis 不可用时橱窗请求 2-3s → 客户端单例池 + 0.5s 快速失败
- 个人中心弹层支持点遮罩关闭；自带价订单橱窗不再展示误导性 ¥0

## [0.5.0] - CI、token 立即失效、Redis 限流、Docker 部署

- GitHub Actions：push/PR 自动跑后端测试与前端构建
- 改密/重置后已签发 JWT 立即失效（token_valid_after + iat 比对，UTC 语义）
- 登录/AI 解析限流改 Redis 固定窗口，故障降级进程内
- Dockerfile ×2 + docker-compose（MySQL/Redis/api/web）+ DEPLOY.md

## [0.4.0] - 业务功能充实

- 教员站内通知（投递全流程）+ 未读角标；教员封禁（平台级）；被拒教员可重新投递
- 财务流水类型/日期筛选 + CSV 导出（BOM 中文表头）

## [0.3.0] - 资金与状态机守卫（止血批次）

- 投递流程全端点订单状态前置校验 + 行锁，杜绝已完成订单复活二次收款
- 重开订单强制资金处置；net_amount 去除 forfeit 双算；退款封顶实收；零退款补记没收
- 成交自动关闭兄弟投递；自动归档跳过有已收款投递的订单

## [0.2.0] - 密码认证体系

- 教员手机号+密码、中介邀请码+密码（bcrypt）；登录限流；错误统一化防枚举
- 老板创建中介返回一次性初始密码、可重置；自助改密接口
- Alembic 迁移链建立，生产建表唯一途径

## [0.1.0] - 项目骨架

- FastAPI 异步后端 + Vue3 H5，订单/投递/财务/推荐/解析/地理编码
- 多租户隔离、JWT、高德地图橱窗、DeepSeek 批量解析
