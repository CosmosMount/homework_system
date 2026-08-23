# 新生培训作业与校内赛系统

面向单校单组织的内部业务平台，用于学校邮箱自助注册、站内通知、培训作业提交、私密评语、校内赛组队与优秀作业展示。

阶段 1 工程骨架已经建立：前端、后端、数据库迁移、Worker、Nginx、Docker Compose 和 CI 均已落盘。当前登录页是明确标注“认证尚未接入”的界面骨架；注册、登录、通知、作业和赛事等业务能力按路线图后续阶段实现。

## 核心边界

- 培训作业由个人提交，校内赛作品由团队队长提交。
- 只设学生和管理员两个角色，不提供分数、排名或公开评语。
- 学生验证 `@hkust-gz.edu.cn` 邮箱后直接激活，无需管理员审批或初始分组。
- 优秀作业只显示在对应作业中，不建立独立范本页面或赛事优秀成果入口。
- 除认证相关页面外，所有内容只对已登录用户开放。
- 现有战队官网与培训知识库保持独立；本系统不复制培训内容，也不修改或调用现有站点。
- 单个提交版本的附件总量不超过 2 GB，文件存储在 MinIO，元数据存储在 PostgreSQL。

## 计划技术栈

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

启动完成后访问 `http://localhost:8080/login`。Nginx 是唯一主机入口；可通过 `/health/live`、`/health/ready` 和 `/health/worker` 检查后端、数据库与 Worker 状态。开发配置只使用 HTTP，生产环境必须按部署文档配置校内域名、HTTPS 和独立强密钥。

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

开发或修改项目之前必须先阅读 [AGENTS.md](AGENTS.md) 和 [.agents/tasks/current-task.md](.agents/tasks/current-task.md)。
