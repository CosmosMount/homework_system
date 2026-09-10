# 通知正文图片与邮件内嵌图片实施计划

## 背景与必要性

当前通知 Markdown 仅支持文本结构，通知附件中的图片只能在附件区预览；通知邮件虽然已经直接渲染入队时的 Markdown 正文快照，但不能显示正文图片。管理员需要在正文指定位置展示已上传图片，并让邮件客户端无需访问对象存储外链即可看到同一图片。

本任务对应 NEWS-001、NEWS-006～NEWS-007、FILE-005～FILE-007、MAIL-001～MAIL-005 与 NFR-011。图片必须继续来自当前通知的安全附件，不开放任意远程图片 URL，不把文件内容、对象键或永久访问地址写入 PostgreSQL。

## 方案

1. 定义 `![说明](announcement-image:<file_uuid>)` 专用 Markdown 引用。统一解析器只把该协议且 UUID 合法的图片渲染为 `img`，普通远程图片、`data:`、`javascript:`、SVG 与原始 HTML继续禁用。
2. 通知保存时在 Service 层校验每个引用均属于请求中的当前通知附件，文件状态可用，服务端探测类型为 PNG/JPEG/GIF/WebP；最多 10 个不重复正文图片，单张不超过 5 MiB、合计不超过 20 MiB。被正文引用的附件不能从同次保存请求解除绑定。
3. 数据库继续只保存 Markdown、清洗后的专用 URI HTML、文件 UUID 关联和元数据，不新增表或迁移。API 返回正文时把专用 URI映射为登录态 `/api/v1/files/{file_id}/content`；该 GET 入口复用业务关联授权并 307 到 5 分钟 inline 签名地址。
4. 通知邮件 Outbox 增加正文图片文件 UUID 快照，不保存对象键或字节。Worker 按通知上传上下文、可用状态、服务端媒体类型和大小上限复核后，从 MinIO 有界读取；HTML 使用稳定 CID，SMTP 组装 `multipart/related`，纯文本保留图片说明。旧 Outbox 没有图片字段时保持兼容。
5. 管理端附件列表返回安全附件元数据，合规图片提供“插入正文”操作，按光标位置写入专用 Markdown；保存后预览复用登录态内容入口。

## 影响范围

- Backend：Markdown 清洗、通知 Service/Schema/Router、上传内容入口、对象存储有界读取、邮件渲染与 Outbox Worker。
- Frontend：通知 API 类型、管理员通知编辑器、通知正文样式。
- 文档：产品需求、页面、架构、API、文件安全、邮件、安全、测试、决策、变更、运维记录、任务和阶段记忆。
- 数据库：无结构或数据迁移；既有通知和旧邮件任务保持兼容。

## 验证方式

1. Backend 单元/集成：合法图片引用、重复引用、跨通知/未绑定/非图片/危险类型/超限、解除绑定保护、学生与管理员内容授权、旧任务兼容、CID HTML 与 MIME related、对象读取失败和坏载荷重试语义。
2. Frontend：图片附件插入 Markdown、保存载荷、已有附件回显与安全预览；完整 Vitest、ESLint、严格 TypeScript 和生产构建。
3. 全量 Backend Pytest、Ruff、格式、严格 Mypy 与 `git diff --check`。
4. 部署使用显式 `.env` 和正式 Compose 文件构建固定标签，先 Backend/Worker 后 Frontend/Nginx；核对 Alembic 无变化、六服务健康、重启计数、匿名内容入口 401、运行源码标记、日志 5xx/异常和部署前后业务聚合。保留部署前镜像回滚标签，不发送真实通知邮件、不修改真实通知数据。

