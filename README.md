# 新生培训作业与校内赛系统

面向单校单组织的内部业务平台，用于学校邮箱自助注册、飞书培训文档只读同步与阅读、站内通知、培训作业提交、私密评语、校内赛组队与优秀作业展示。

阶段 1～6 已完成实现与隔离验收；飞书培训知识库只读快照、管理员手动同步、登录态阅读及参考仓库提交 `c28f8a0` 的同步契约已经完整上线。知识库阅读区现使用白色主题，桌面为左侧文档目录、中央正文和右侧本文目录；右侧本文目录随滚动高亮当前章节，成功打开文档后折叠系统主要导航且保持文档目录状态。2026-08-28 的隔离 Frontend 镜像 `sha256:2ad76bd…` 已上线，未触发新同步。2026-08-27 前台同步以 `succeeded` 完成 228 个目录节点、212 篇文档和 977 个成功媒体引用，耗时 `00:33:28.757715`，13 次允许的资源回退未阻断快照；旧 48 篇阶段性快照已被新成功快照自然替代。开发 Compose 继续通过 Nginx `5000` 端口提供局域网服务；生产现场仍需部署方补齐受信域名/证书、校园 SMTP、异机备份目标和独立告警接收方。

当前知识库发布候选通过 29 项后端知识库定向测试、完整后端 213 项测试、前端 20 个文件/77 项测试、Ruff、格式检查、严格 Mypy、ESLint、严格 TypeScript 和 Next.js 生产构建。Alembic 仍为 `20260827_0011`，本轮无迁移；阶段 6 的三浏览器 Playwright、隔离 HTTPS 及 npm/pip/Gitleaks/Trivy 零高危或零泄漏门继续有效。

## 核心边界

- 培训作业由个人提交，校内赛作品由团队队长提交。
- 只设学生和管理员两个角色，不提供分数、排名或公开评语。
- 新账号只接受 `@connect.hkust-gz.edu.cn`；邮箱前缀自动作为用户名，完成邮箱验证后可用用户名或完整邮箱登录。空系统首个完成验证的账号自动成为受最后管理员保护的管理员，其余账号直接激活为学生。
- 优秀作业只显示在对应作业中，不建立独立范本页面或赛事优秀成果入口。
- 除认证相关页面外，所有内容只对已登录用户开放。
- 现有战队官网与飞书知识库继续独立维护；本系统只由真实管理员手动触发飞书开放 API，同步最近成功的只读快照供登录用户阅读，不编辑或写回知识库，也不修改或依赖现有官网运行时。
- 同步顺序、块转换与失败语义固定参考提交 `c28f8a0`；阅读页按 ADR-034 使用白色主题、左文档目录、中央正文和右本文目录；右侧本文目录随滚动定位当前章节，成功打开文档后折叠系统主要导航且不改变文档目录状态，目录控件复用系统统一样式。本平台保留登录鉴权、`AppShell`、PostgreSQL/MinIO 快照、Worker 和管理员手动接口；部署方只需填写 App ID、App Secret 和 Wiki URL。
- 单个提交版本的附件总量不超过 2 GB，文件存储在 MinIO，元数据存储在 PostgreSQL。

## 技术栈

- 前端：Next.js App Router、TypeScript、Tailwind CSS
- 后端：FastAPI、SQLAlchemy、Alembic、PostgreSQL
- 存储与网关：MinIO、Nginx
- 部署：Docker Compose、校内服务器
- 消息：站内通知、SMTP、数据库 Outbox Worker

## 本地启动

需要 Docker Engine 与 Docker Compose v2。在项目根目录执行：

```powershell
Copy-Item .env.example .env
docker compose --env-file .env --file infra/compose/compose.yml up --build
```

Linux/macOS 使用：

```bash
cp .env.example .env
docker compose --env-file .env --file infra/compose/compose.yml up --build
```

模板默认启动后访问 `http://localhost:8080/login`。如需局域网开发验收，在 `.env` 中修改 `APP_HTTP_PORT`，并同步设置 `APP_BASE_URL`、`TRUSTED_HOSTS` 和 `MINIO_PUBLIC_BASE_URL`；不要暴露 PostgreSQL、MinIO Console、Frontend 或 Backend 端口。Nginx 是唯一主机入口；可通过 `/health/live`、`/health/ready` 和 `/health/worker` 检查后端、数据库与 Worker 状态。开发配置只使用 HTTP，生产环境必须按部署文档配置校内域名、HTTPS 和独立强密钥。

停止并保留数据卷：

```powershell
docker compose --env-file .env --file infra/compose/compose.yml down
```

本机单独运行质量门：

```powershell
Set-Location frontend
npm ci
npm run lint
npm run typecheck
npm test
npm run build

Set-Location ..\backend
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --require-hashes --requirement requirements-dev.lock
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\ruff.exe format --check .
.\.venv\Scripts\mypy.exe app tests
.\.venv\Scripts\pytest.exe
```

完整迁移前滚/回滚与 Compose 冒烟测试由 [.github/workflows/ci.yml](.github/workflows/ci.yml) 在真实 PostgreSQL、MinIO 和 Docker 环境执行。

## 生产部署与运维

生产部署使用 `.env.production.example`、`infra/compose/compose.production.yml` 和 `infra/nginx/nginx.production.conf`。必须填写固定镜像标签或 digest、校内 HTTPS 域名/证书、独立强密钥、SMTP 和 OpenPGP 接收方；生产只开放 Nginx 80/443，其他组件不映射主机端口。

- `infra/release/preflight.sh`：检查固定镜像、秘密文件、证书、拓扑和新鲜加密备份。
- `infra/release/deploy.sh` / `rollback.sh`：按备份门、迁移、健康等待、HTTPS 冒烟执行发布或仅镜像回滚。
- `infra/monitoring/check.sh` / `evaluate-alerts.sh`：生成不含个人信息的健康快照并评估证书、Worker、Outbox、备份、磁盘、5xx 和 P95 告警。
- `infra/backup/backup.sh`：每周 MinIO 完整基线、每日相对周基线的累计增量，并为每天生成 PostgreSQL 快照；所有可恢复归档离开宿主机前使用 OpenPGP 加密。
- `infra/backup/restore.sh`：只允许显式 `pnx-restore-*` 隔离项目，从周完整或“周基线 + 日增量”恢复并自动运行 Alembic/对象引用对账。
- `infra/backup/retention.sh`：默认 dry-run，保留 14 个每日、8 个每周，并保护仍被保留每日备份引用的周基线。

`BACKUP_STATE_DIR` 必须是与备份输出分离的本机 `0700` 目录；缺少有效周基线时每日备份会失败，不能绕过。完整部署、备份、故障演练、容量结果和外部现场材料见部署文档、容量报告与生产运维报告。

## Windows 裸预览

没有 Docker 时，可以只启动当前已实现的前后端骨架。分别打开两个 PowerShell 终端：

```powershell
Set-Location frontend
npm run dev -- --hostname 127.0.0.1 --port 3000
```

```powershell
Set-Location backend
.\.venv\Scripts\uvicorn.exe app.main:app --host 127.0.0.1 --port 8000 --no-access-log
```

登录页位于 `http://127.0.0.1:3000/login`，后端存活接口位于 `http://127.0.0.1:8000/api/v1/health/live`。未启动 PostgreSQL 时 `/api/v1/health/ready` 应安全返回 503 `DEPENDENCY_UNAVAILABLE`；Worker、MinIO、Nginx 和真实迁移不属于裸预览范围。

## 许可证

本项目采用 [MIT License](LICENSE)，版权归 HKUST(GZ) RoboMaster PNX Team 所有。

## 权威文档

1. [项目总览](.agents/docs/00-project-overview.md)
2. [产品需求](.agents/docs/01-product-requirements.md)
3. [信息架构](.agents/docs/02-information-architecture.md)
4. [设计系统](.agents/docs/03-design-system.md)
5. [页面规格](.agents/docs/04-page-specifications.md)
6. [系统架构](.agents/docs/05-system-architecture.md)
7. [API 规范](.agents/docs/06-api-specification.md)
8. [数据库结构](.agents/docs/07-database-schema.md)
9. [认证、安全与邮件](.agents/docs/08-auth-security-email.md)
10. [文件上传与存储](.agents/docs/09-file-upload-storage.md)
11. [部署与网络](.agents/docs/10-deployment-network.md)
12. [测试策略](.agents/docs/11-testing-strategy.md)
13. [编码规范](.agents/docs/12-coding-standards.md)
14. [Agent 工作流](.agents/docs/13-agent-workflow.md)
15. [路线图](.agents/docs/14-roadmap.md)
16. [架构决策](.agents/docs/15-decisions.md)
17. [变更记录](.agents/docs/16-changelog.md)
18. [容量与性能报告](.agents/docs/17-capacity-performance-report.md)
19. [生产运维与故障恢复报告](.agents/docs/18-production-operations-report.md)

开发或修改项目之前必须先阅读 [AGENTS.md](AGENTS.md) 和 [.agents/tasks/current-task.md](.agents/tasks/current-task.md)。
