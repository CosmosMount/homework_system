# 管理员查看人员组别分布计划

## 状态

已完成并部署（2026-09-14 16:28，北京时间）。

## 背景与必要性

管理员用户页已经支持按单个技术组筛选账号，但只能看到当前筛选结果和分页人数，无法一次判断各技术组人员分布以及仍未设置技术组的人数。直接从当前 20 条分页结果统计会产生错误结论，也不利于管理员识别分组缺口。

本功能在现有 `/admin/users` 管理上下文中增加只读分布概览。统计口径固定为当前 `active student`：排除待验证、已禁用账号和管理员，避免把不可参与学生业务的账号混入技术组人员配置；包含全部现有技术组（含已停用但仍可能被历史用户引用的组）以及“未设置技术组”。统计读取完整用户集合，不受用户列表搜索、活跃度、技术组筛选和分页影响。

## 实现范围

- Backend 在 `users` Repository 使用聚合查询计算每个现有技术组的 active student 人数，并单独计算未设置技术组和总人数。
- Service 负责把聚合结果转换为稳定响应；Router 新增真实管理员只读端点，只做协议转换并复用 `AdminContextDependency`。
- Frontend Server API 增加响应类型和读取函数；管理员用户页与方向列表、用户分页并行读取分布。
- 页面在用户筛选与账号卡片之前展示总人数、已分组、未分组以及逐技术组人数/占比；明确说明统计不受下方筛选影响，停用组保留标识。
- 不新增写操作、审计事件、依赖、数据库字段、索引或 Alembic 迁移。

## 受影响需求与文档

- 需求：AUTH-007、NFR-002、NFR-003、NFR-004。
- 页面：`/admin/users` 人员技术组分布、空状态和响应式展示。
- API：新增 `GET /admin/users/direction-distribution` 管理员只读契约。
- 数据：复用 `users.role/status/direction_id`、`directions` 及现有外键/索引。
- 测试：Backend Repository/Service/OpenAPI，Frontend 页面读取与人数/占比/停用组展示。

## 安全与数据约束

- 端点仅允许真实管理员且未开启学生视图；未登录、学生和管理员学生视图不得读取聚合结果。
- 响应只包含技术组 ID、编码、名称、启用状态和聚合人数，不返回用户身份、邮箱、学号或名单。
- 分布按全量 active student 计算，不接受浏览器传入用户集合，也不从分页响应派生。
- 只读查询不连接 MinIO，不修改 PostgreSQL，不产生审计或 Outbox。

## 验证方式

- Repository 回归覆盖多个技术组、零人技术组、停用技术组、未设置技术组，并确认只统计 `active student`。
- Service 回归断言总人数、已分组/未分组关系和稳定响应映射。
- OpenAPI 回归断言新端点和响应字段；鉴权沿用路由级真实管理员依赖。
- Frontend 回归断言页面并行读取分布、显示全量统计、百分比、未分组和停用标识，并证明下方筛选参数只影响用户分页请求。
- 运行相关 Pytest、Vitest、Ruff、格式、严格 Mypy、ESLint、严格 TypeScript、Next.js 生产构建和 `git diff --check`。

## 数据迁移与发布

- 不涉及数据迁移；无需修改或运行 Alembic。
- 部署使用当前线上提交 `59cabd7` 加本功能 8 个运行时代码文件的隔离候选，不直接构建脏工作区；不调用带认证业务写接口。

## 完成结果

- 新增 `GET /admin/users/direction-distribution`，复用真实管理员上下文并返回全部正常学生的总数、已分组/未分组人数，以及所有现有技术组（含零人和停用组）的人数。
- `/admin/users` 在筛选列表之前展示响应式统计卡片和比例条；统计独立读取，不受搜索、活跃度、技术组筛选或分页参数影响。
- 后端定向 40 项、前端定向 10 项、前端完整 27 文件/166 项通过；Ruff、格式检查、后端应用源码严格 Mypy、本任务相关后端源码与测试严格 Mypy、ESLint 和 `git diff --check` 通过。
- 全量后端 Pytest 在约 13% 处因既有 ASGI 测试环境无输出停滞而中断；加入额外方向 API 测试后仍在相同位置停滞，本任务定向回归全部通过。包含全部测试的严格 Mypy 仍有 12 项既有错误，均位于未修改的 `tests/test_inactive_account_cleanup.py`。
- 默认 Turbopack 构建受沙箱内部端口绑定限制；Webpack 在临时关闭嵌套 TypeScript CLI 后完成生产构建，临时配置已撤销。最终复跑 `npm run typecheck` 被未修改的 `app/login/page.tsx` 既有可选页面参数签名阻断，本任务定向前端测试通过。

## 部署结果

- 新加密每日增量备份 `pnx-backup-20260914T081810Z-daily` 已生成，并在全新 `pnx-restore-admin-user-distribution-20260914` 隔离项目完成空卷恢复；RPO 54 秒、RTO 187 秒，1,659 个对象的缺失、大小、SHA-256 和未跟踪差异均为 0，恢复资源已清理。
- 干净隔离候选的 Frontend 正式 `next build` 完整通过编译、TypeScript、页面数据收集和静态页面生成。固定标签 `admin-user-distribution-20260914` 的 Backend/Worker 镜像为 `sha256:200fcf645a5286a8b9df12d0c625851d269f19bfd1bac1403ac218901e5d941c`，Frontend 为 `sha256:6a319b8f612db7373770343dea0837b27056bd657dbaef7e8b50a7ef2a75f1d0`。
- 幂等 migrate 成功，Alembic 保持 `20260910_0025 (head)`；先切换 Backend/Worker，再切换 Frontend并两次校验、热重载 Nginx。PostgreSQL、MinIO 与 Nginx 容器未重建，旧 `account-auto-cleanup-20260911` 镜像保留用于应用回滚。
- 六服务 healthy、重启 0；登录与三项健康检查为 200，管理员用户页匿名为 307，新 API 匿名为 401，运行 OpenAPI 和 Frontend 编译产物均包含新能力。发布前后用户/正常学生/已分组学生/技术组/活动 Outbox 保持 `191/171/154/6/2`，稳定期 Nginx 5xx 和应用错误日志均为 0。
- 验收未使用管理员 Session、未调用业务写接口、未触发飞书同步或邮件，也未重建数据容器或数据卷。加密备份及解密材料仍在同一宿主机临时目录，须由部署方迁往独立受控介质并分离保存。
