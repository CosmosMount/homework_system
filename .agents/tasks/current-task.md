# 当前任务

## 标题

在 Docker 环境完成阶段 1 集成验收。

## 目标

运行已落地的 Compose 拓扑和 CI，确认固定镜像能够拉取、空 PostgreSQL 可迁移、Nginx 是唯一主机入口，且 Frontend、Backend、Worker、PostgreSQL 和 MinIO 健康检查全部通过。

## 已完成前置工作

- 前后端工程、Worker 心跳、Alembic、Dockerfile、Compose、Nginx、环境变量模板和 CI 已实现。
- 本机 Ruff、格式、Mypy、14 个 Pytest、ESLint、TypeScript、3 个 Vitest、Next.js 生产构建、`pip-audit` 和 `npm audit` 已通过。
- Compose/CI YAML 已解析，并通过仅 Nginx 暴露端口、internal 数据网络、Worker 出站网络、迁移依赖和开发秘密占位符的静态断言。
- Windows 裸启动已验证前端登录页、跳转、404、健康路由和后端存活、统一 404；PostgreSQL 未启动时就绪接口按预期返回安全 503。

## 待验证事项

- 在安装 Docker Compose v2 的主机执行 README 中的一条命令启动。
- 验证 Alembic 空库升级与降级、Nginx 配置语法和固定容器镜像实际可运行。
- 通过 `/login`、`/health/live`、`/health/ready`、`/health/worker` 冒烟路径。
- 在可用浏览器环境补做桌面/移动视觉检查；当前 Windows 浏览器沙箱无法建立自动化连接。
- 验证通过后将阶段 1 标记为全部验收完成，再为阶段 2 认证实现建立新计划。

## 相关文档

- `.agents/plans/plan_infrastructure_engineering_skeleton.md`
- `.agents/docs/10-deployment-network.md`
- `.agents/docs/11-testing-strategy.md`
- `.agents/docs/14-roadmap.md`
