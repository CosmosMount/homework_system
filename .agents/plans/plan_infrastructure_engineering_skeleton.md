# 基础设施与工程骨架实施计划

## 问题背景

权威中文设计基线已经完成，但仓库尚无前端、后端、迁移、容器或测试代码。若直接进入认证业务，统一配置、错误响应、请求追踪、数据库事务、健康检查和部署网络会在各模块中重复出现，造成后续实现漂移。本任务按路线图阶段 1 先建立可运行、可测试的工程底座。

## 现有结构与可复用能力

- 当前只有 README、AGENTS 和 `.agents/` 权威文档，没有业务源码、依赖锁文件或运行时配置。
- 技术栈已由 ADR-003、ADR-005～ADR-007 固定为 Next.js、FastAPI、PostgreSQL、MinIO、Nginx、Docker Compose 和数据库 Worker。
- API 已规定 `/api/v1`、统一错误结构、请求 ID 及存活/就绪/Worker 健康接口。
- 部署文档已规定 Nginx 为唯一浏览器入口，PostgreSQL 与 MinIO 管理端口不得暴露。
- 本阶段不实现注册、Session、通知、作业、上传或赛事业务；这些能力继续按路线图后续阶段交付。

## 计划修改

1. 建立 `frontend/` Next.js App Router 工程，开启 TypeScript 严格模式、ESLint、Vitest 和 Tailwind CSS，落地 PNX 深色设计令牌、认证页视觉骨架、根路径跳转和前端健康接口。
2. 建立 `backend/` FastAPI 工程，按 `api → service → repository` 的长期边界预留模块目录，但只实现当前必要的配置、应用工厂、统一领域错误、请求 ID、中间件、结构化日志和健康检查。
3. 使用 SQLAlchemy 异步会话和 Alembic 建立数据库底座；首条迁移只创建阶段 1 必需的 `worker_heartbeats` 表，不提前创建阶段 2 之后的业务表。
4. 建立独立 Worker 入口，定期通过 Repository 更新数据库心跳；API 的 Worker 健康接口只返回安全摘要。
5. 建立 Backend 与 Frontend 多阶段 Dockerfile、Nginx 同源路由、Compose 服务、健康检查、数据卷和网络隔离。
6. 为 Worker 增加独立 `worker_egress_net`，使数据网络保持 internal 的同时允许后续连接校园 SMTP；同步修正部署文档的网络描述。
7. 建立 `.env.example`、开发命令、后端 Ruff/Pyright/Pytest、前端 lint/type/test/build 和 GitHub Actions 质量门。
8. 更新 README、数据库结构、部署说明、测试策略、路线图状态、任务、变更记录和项目记忆。

## 涉及模块

- `frontend/`：应用布局、设计令牌、登录页骨架、健康 Route Handler、前端测试与构建配置。
- `backend/`：配置、日志、中间件、错误映射、数据库会话、健康 Router、Worker 与 Alembic。
- `infra/`：Compose、Nginx、容器入口和网络。
- `.github/workflows/`：阶段 1 质量门。
- `.agents/docs/`：数据库心跳、Worker 出站网络、阶段验收与变更记录。

## API、数据库、权限与迁移影响

- 新增既有规范中的 `GET /health/live`、`GET /health/ready`、`GET /health/worker`，不新增业务 API。
- 新增 `worker_heartbeats` 表，包含 Worker 名称、启动时间、最近心跳时间和更新时间；通过 Alembic 可升级和降级。
- 健康接口不读取用户数据、不返回连接串或凭证；就绪失败使用统一安全错误摘要。
- 页面骨架不伪造登录状态，不开放尚未实现的学生或管理员业务页面。

## 部署影响

- 本地与校内部署均由 Nginx 提供唯一浏览器入口；Frontend、Backend、PostgreSQL、MinIO 和 Worker 不映射主机端口。
- `data_net` 保持内部网络；Worker 额外挂载仅用于出站的 `worker_egress_net`，不接受主机入站流量。
- `.env.example` 只提供非生产示例和变量说明，生产密钥必须另行注入。

## 测试与验收

- 后端运行 Ruff、Pyright、Pytest，覆盖请求 ID、统一错误、存活、数据库就绪和 Worker 心跳状态。
- 前端运行 ESLint、TypeScript、Vitest 和生产构建，覆盖根路径跳转、登录骨架和健康响应。
- Alembic 从空库升级到最新并可降级；在真实 PostgreSQL 环境验证迁移。
- Compose 配置可解析，服务只有 Nginx 映射主机端口，PostgreSQL 与 MinIO Console 不暴露。
- 启动后通过 Nginx 访问页面、`/api/v1/health/live`、`/api/v1/health/ready` 和前端静态资源。
- 若当前主机缺少 Docker，只完成静态配置、独立前后端测试与构建，并在交付中明确 Compose 运行验证仍需 Docker 环境。

## 不实施的内容

- 不实现 AUTH、NEWS、HW、SUB、COMP、TEAM、SHOW、FILE、MAIL 的业务流程。
- 不创建对应业务表、演示账号、虚假通知、作业或赛事数据。
- 不引入 Redis、微服务、公开对象桶、长期 JWT 或额外状态管理库。

## 完成标准

- 工程目录、锁文件、迁移、容器和 CI 配置齐全，后续认证阶段可在现有底座上直接扩展。
- 本机可执行的 lint、类型、单元测试和生产构建全部通过。
- 文档、任务与项目记忆准确反映已实现范围、验证结果和 Docker 环境限制。

## 执行结果（2026-08-23）

- 计划内工程文件均已实现，且没有创建认证、通知、作业、赛事、上传等超出阶段 1 的业务表或接口。
- 本机通过 Ruff、格式、Mypy、12 个 Pytest、ESLint、严格 TypeScript、3 个 Vitest、Next.js 生产构建、`pip-audit` 和 `npm audit`。
- Compose 与 CI YAML 已解析，网络、端口、健康依赖、环境变量和 Nginx 路由通过静态交叉断言。
- 当前主机无 Docker；真实镜像构建、Nginx `-t`、空 PostgreSQL 迁移前滚/回滚及完整 Compose 冒烟已配置在 CI，仍需在 Docker 环境实际运行。

## 追加执行结果（2026-08-24）

- 已在 Linux Docker 29.6.0、Docker Compose v5.1.4 环境构建固定前后端镜像并启动完整拓扑，弥补 2026-08-23 Windows 主机无法执行的验收项。
- 空 PostgreSQL 17 数据卷完成 `upgrade head → downgrade base → upgrade head`，最终 Alembic 版本为 `20260823_0001 (head)`。
- 真实 `nginx -t` 发现两个请求 ID 正则的 `{n}` 量词未加引号，已修复；合法请求 ID 保留、非法值替换和 Nginx 健康探针均通过。
- Frontend、Backend、Worker、PostgreSQL、MinIO 和 Nginx 全部健康；迁移服务以 0 退出，`/login`、三类健康接口和局域网 `0.0.0.0:5000` 入口均通过。
- 只有 Nginx 映射本项目主机端口，阶段 1 集成验收完成。
