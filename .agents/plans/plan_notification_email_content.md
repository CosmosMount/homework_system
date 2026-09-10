# 通知邮件正文渲染实施计划

## 背景与必要性

当前通知在站内保存原始 Markdown 与服务端清洗后的 HTML，但发布邮件和更新提醒邮件只显示标题、摘要与站内链接。用户需要在邮件客户端中直接阅读通知正文，同时继续通过站内登录态访问附件和完整业务上下文。

本任务对应 NEWS-001、NEWS-006～NEWS-007、MAIL-001～MAIL-005 与 NFR-011，不改变通知受众、发布事务、邮件可靠投递或附件授权边界。

## 现有能力与影响范围

- 复用 `app.core.markdown.render_markdown` 的 CommonMark 渲染与 HTML 允许列表清洗，不建立第二套邮件 Markdown 解析器。
- 发布与显式更新提醒继续由 `AnnouncementService` 按接收人创建唯一 Outbox；邮件正文取入队时的通知 Markdown 快照，避免投递延迟期间内容变化导致事件语义漂移。
- HTML 邮件展示清洗后的通知正文，纯文本邮件展示 Markdown 原文；标题、摘要、称呼和链接继续按各自上下文转义或校验。
- 附件不嵌入邮件，不生成 MinIO 地址或永久下载链接；用户仍需登录站内查看附件。
- 兼容部署前已经入队且没有正文快照的通知邮件：继续发送原标题、摘要与链接模板，不因升级进入 dead。

## 实施步骤

1. 扩展通知发布邮件与更新邮件 Outbox 普通载荷，加入入队时的 `body_markdown` 快照。
2. 邮件模板使用统一 Markdown 清洗器生成 HTML 正文，并在纯文本替代部分加入 Markdown 正文；保留站内详情与附件入口。
3. 增加发布/更新载荷、正文格式渲染、XSS/危险链接清洗、附件地址缺失及旧任务兼容测试。
4. 同步产品需求、邮件安全设计、测试策略、变更记录、当前任务与完成记录。

## 验证方式

- 运行通知邮件定向 Pytest，覆盖普通发布和更新提醒两种任务。
- 运行受影响文件 Ruff、格式检查和 Mypy；风险允许时运行完整后端测试。
- 运行 `git diff --check` 并复核普通 Outbox 管理 API 不返回 payload。

## 明确不实施

- 不在邮件中嵌入附件、预签名地址、对象键或其他受登录态保护的数据。
- 不修改 API、数据库表、Alembic 迁移、Frontend 或 SMTP 重试策略。
- 不把私密评语、反馈答疑正文或问卷答案加入邮件。

## 完成结果

2026-09-08 已完成源码与文档。通知发布和更新提醒 Outbox 均保存入队时 Markdown 正文快照；HTML 邮件发送前再次使用统一清洗器渲染，纯文本替代部分包含同一 Markdown，旧无正文任务继续按原模板投递。定向通知测试 17 项、完整后端 424 项、Ruff、180 文件格式检查、155 个源文件严格 Mypy 与 `git diff --check` 全部通过。本轮未连接 SMTP、PostgreSQL 或 MinIO，未构建镜像或部署，不涉及 API、数据库或数据迁移。

## 部署步骤

1. 复核当前六服务健康、运行 Backend/Worker 镜像、Alembic head、最新已验证备份和部署前业务聚合。
2. 构建固定标签 `notification-email-content-20260908` 的 Backend 镜像，并在隔离容器中验证通知邮件载荷和安全正文渲染标记。
3. 固定当前 Backend 镜像为回滚标签，只替换 Backend/Worker；不运行迁移，不替换 Frontend/Nginx/PostgreSQL/MinIO。
4. 验证六服务健康、HTTP 健康入口、运行源码标记、Alembic head、业务聚合、Outbox 状态与发布窗口日志；不携带管理员 Session，不创建或投递真实通知邮件。

## 部署结果

2026-09-08 固定标签 `notification-email-content-20260908` 已只替换 Backend/Worker，镜像为 `sha256:d6dca2dc1778d19b496dc4c726b693a7f2cc650cd6bdba4d46f7c83a58a6ab34`；Nginx 仅重启以刷新上游，Frontend/PostgreSQL/MinIO 容器未替换。当前 Frontend `sha256:80dc5b64e94e…` 另加同名发布别名，保证单一 `APP_IMAGE_TAG` 后续可重建。六服务 healthy、重启 0，四个健康入口与登录页通过，匿名通知 API 为 401，运行源码标记有效，Alembic 保持 `20260908_0023 (head)`，用户/通知/Outbox 聚合保持 `196/4/960`。稳定期 Backend/Worker 异常关键词与 Nginx 5xx 均为 0。

首次替换命令未显式传入 `--env-file .env`，Compose 短暂创建了本地 `dev` Backend/Worker，Worker 因缺少正式环境配置重启；约一分钟内已用正式环境文件和固定标签纠正，Nginx 日志没有 5xx，数据库聚合无变化。误生成的 `dev` 标签已删除。回滚标签 `notification-email-content-rollback-20260908` 指向部署前 Backend 镜像 `sha256:41e4bf16bb57eceff8a0a2e9817b5c9bde08a5e5d02ccb47a8dfe85a6bd8a022`。本轮未运行迁移、未调用真实通知写入或发送测试邮件。
