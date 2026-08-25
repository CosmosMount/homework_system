# Agent 工作规则

## 项目目标

建设一个单校单组织的新生培训作业与校内赛内部平台。系统负责动态业务流程，不负责维护培训知识库，也不承担公开官网功能。

## 必读顺序

修改任何内容前依次阅读：

1. `.agents/memories/project_baseline.md`
2. `.agents/docs/00-project-overview.md`
3. `.agents/docs/01-product-requirements.md`
4. 与任务相关的页面、架构、API、数据库或安全文档
5. `.agents/tasks/current-task.md`
6. `.agents/plans/` 下对应的唯一正式计划

## 文件管理

- 根目录只保留项目源码、配置和 `README.md`、`AGENTS.md` 等标准入口文件。
- Agent 生成的任务计划统一放入 `.agents/plans/`，命名为 `plan_<object_name>.md`，每个任务只能有一个正式版本。
- Agent 生成的详细项目文档统一放入 `.agents/docs/`，不得在其他位置创建备份。
- 当前任务、待办和已完成记录放入 `.agents/tasks/`；阶段性项目记忆放入 `.agents/memories/`。
- 计划、设计说明、调试记录、技术分析和记忆均使用中文。

## 目录职责

- `frontend/`：Next.js 页面、组件、浏览器交互和 API 客户端，不直接访问数据库或 MinIO 管理接口。
- `backend/`：FastAPI、认证授权、业务服务、仓储、Worker 和数据库迁移。
- `infra/`：Docker Compose、Nginx、健康检查、部署和备份脚本。
- `.agents/docs/`：产品与技术设计的权威来源。
- `.agents/tasks/`：当前开发状态，不得替代正式需求文档。

## 不可破坏的产品约束

- 只设 `student` 与 `admin` 两个角色；前端隐藏不是授权机制，后端每个受保护接口都必须鉴权。
- 作业只能由个人提交，赛事作品只能由队伍提交，且只有队长能够创建正式赛事提交版本。
- 不引入评分、排名、自动评奖或公开评语。
- 公开注册只接受 `@connect.hkust-gz.edu.cn`；空系统首个完成验证的账号成为受最后管理员保护的 `admin`，其余账号直接激活为 `student`，不设置注册审核或强制初始分组。
- 优秀作业只能来自作业提交，只显示在对应作业中，不建立独立范本或赛事展示模块。
- 不复制现有培训知识库，不修改或依赖现有官网运行时。
- 文件内容不得存入 PostgreSQL；MinIO 对象键必须由服务端生成。
- 不存储明文密码，不渲染未经清洗的 Markdown HTML，不公开 PostgreSQL 和 MinIO 管理端口。

## 修改前

- 分析需求本质、现有模块职责、可复用能力和受影响的需求编号。
- 非简单任务必须先创建中文计划，说明背景、必要性、影响和验证方式。
- API 变更先核对 `06-api-specification.md`；数据库变更必须设计可回滚迁移并核对 `07-database-schema.md`。
- 不为假设性未来需求新增抽象、依赖、服务或重复封装。

## 实现要求

- 仅修改完成当前目标所需的模块，不进行无关重构。
- API Router 只处理协议转换；Service 承担业务规则；Repository 负责持久化。
- 复杂流程拆分为职责单一的函数，禁止在路由或数据库层混入跨层逻辑。
- 外部输入必须验证，错误必须使用统一错误码，不得静默吞掉异常或记录密钥、密码、令牌和 Cookie。

## 修改后

- 运行与风险匹配的单元、集成和端到端测试。
- 更新受影响的需求、页面、API、数据库、测试、决策和变更记录。
- 更新 `.agents/tasks/current-task.md`，并将完成项移动到 `.agents/tasks/completed.md`。
- 复查新增实现是否使旧逻辑冗余；确认后再安全删除，禁止保留重复路径。
- 最终说明修改文件、验证结果、遗留风险和是否涉及数据迁移。
