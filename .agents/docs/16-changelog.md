# 项目变更记录

本文件记录面向项目能力、架构和运维的重要变化，不逐条复制 Git 提交。

## 2026-08-23

### Added

- 建立新生培训作业与校内赛系统的中文权威文档基线。
- 定义 `@hkust-gz.edu.cn` 邮箱注册、验证后直接激活、两角色权限和服务端 Session。
- 定义定向通知、站内未读、SMTP 提醒和 PostgreSQL Outbox Worker。
- 定义固定受众快照、个人作业、多版本提交、个人延期和私密评语。
- 定义赛事报名、自助建队、邀请码、队长、人数约束、队伍锁定和团队提交。
- 定义作业内优秀作业的标记/取消、作业受众可见和源文件删除保护。
- 定义 MinIO 私有桶、16 MiB 分片、2 GiB 版本上限、哈希校验、断点续传和孤立对象清理。
- 定义 Next.js、FastAPI、PostgreSQL、MinIO、Nginx 和 Docker Compose 的校内部署架构。
- 建立需求编号、页面路由、API、数据库、测试矩阵、工程规范、Agent 流程、路线图和 ADR。
- 建立 Next.js 16 严格 TypeScript 前端、PNX 深色登录骨架、前端健康路由和 Vitest 测试。
- 建立 FastAPI 分层后端、统一错误、请求 ID、结构化日志、异步数据库会话、健康 API 与 Worker 心跳。
- 新增可回滚的首条 Alembic 迁移，仅创建 `worker_heartbeats` 运维表，不提前创建认证或业务表。
- 新增多阶段 Dockerfile、固定镜像版本、Nginx 同源路由、Compose 网络/数据卷/健康依赖和 GitHub Actions 质量门。

### Security

- 明确 Argon2id、一次性令牌哈希、Session 撤销、CSRF、登录限流和 Markdown 清洗要求。
- 明确 PostgreSQL、MinIO 管理端口和秘密不得向用户网络或仓库暴露。
- 明确私密评语、其他学生提交和非本作业受众的优秀作业不得通过页面、API、邮件或日志泄露。
- 记录首版不内置恶意软件扫描的剩余风险与文件执行/预览限制。

### Operations

- 定义每日/每周备份、每学期恢复演练、RPO 24 小时和 RTO 4 小时目标。
- 定义 Worker 心跳、Outbox 积压、证书、磁盘、MinIO 容量和备份状态告警。
- 实现 `app_net`、internal `data_net` 和仅供 Worker 主动发送 SMTP 的 `worker_egress_net`；主机只映射开发 Nginx 端口。
- CI 覆盖前后端质量门、依赖漏洞检查、真实 PostgreSQL 迁移前滚/回滚和完整 Compose 健康冒烟。

### Changed

- 删除管理员注册批准/拒绝和强制初始分组；邮箱验证成功后直接激活，届次与方向改为登录后可选分类。
- 删除独立优秀范本列表、详情、管理页面、状态机和赛事来源，改为对应作业详情中的“优秀作业”。
- 用 `assignment_excellent_submissions` 关联替代独立范本数据表，并同步 API、权限和测试。

### Fixed

- Windows 裸测发现 PostgreSQL 主机无法解析时就绪接口返回 500；健康服务现将套接字/DNS 错误映射为统一的 503 `DEPENDENCY_UNAVAILABLE`，并补充数据库就绪与 Worker 健康回归测试。

### Notes

- 阶段 1 只实现工程与运维骨架；登录页不会伪造认证成功，AUTH、NEWS、HW、SUB、COMP、TEAM、SHOW、FILE 和 MAIL 业务仍按路线图后续实现。
- 当前主机没有 Docker，Compose 和真实 PostgreSQL 冒烟由 CI 定义但尚未在本机执行；前后端独立质量门与依赖审计已通过。
- Windows 裸启动已验证前端页面/跳转/404/健康和后端存活/安全依赖失败；自动浏览器视觉检查受本机浏览器沙箱限制，需在 Linux/Docker 验收或可用浏览器环境补做。
- 现有战队官网和飞书培训知识库保持独立，未作修改或运行时集成。
