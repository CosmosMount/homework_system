# 认证与基础数据实施计划

## 问题背景

阶段 1 已完成工程骨架和 Docker 集成验收，但系统仍只有禁用登录骨架与 `worker_heartbeats` 表。用户已授权继续实现完整首版；按路线图必须先完成阶段 2，建立所有后续通知、作业、上传和赛事都依赖的身份、Session、基础分类、审计与可靠邮件底座，验收通过后才能进入阶段 3。

本阶段对应 AUTH-001～AUTH-010、MAIL-001～MAIL-005 中的认证邮件能力，以及 NFR-002、NFR-005～NFR-006、NFR-008～NFR-009、NFR-012。不得提前实现通知、作业、上传或赛事业务。

## 需求本质与必要性

- 学校邮箱验证成功后账号必须直接激活，不存在注册审批或强制初始分组。
- Session、CSRF、账号状态和角色授权必须由后端强制；前端隐藏入口不构成安全控制。
- 邮箱验证与密码重置令牌只能使用一次，数据库只保存哈希，异步邮件投递不得在 Outbox 中保存明文令牌。
- 管理员禁用、角色/邮箱变更、密码重置必须即时撤销相关 Session，并对高风险操作审计。
- 阶段 3 之后依赖通用 Outbox、审计、用户与受众分类；若此阶段缺少数据库约束和可靠事务，后续模块会重复实现并产生权限漂移。

## 现有结构与可复用能力

- 复用 FastAPI 应用工厂、统一错误结构、请求 ID、结构化日志和 `Router → Service → Repository` 分层。
- 复用异步 SQLAlchemy Session、Alembic 命名规范、PostgreSQL 17、Worker 主循环和健康心跳。
- 复用 Next.js App Router、严格 TypeScript、PNX 深色设计令牌、认证页外壳和前端测试配置。
- 复用 Nginx 同源 `/api/v1` 路由、请求 ID、认证路径限速和 Compose 单一入口。
- 复用既有 Docker、CI、迁移前滚/回滚和局域网 5000 端口运行环境。

## 安全与架构取舍

1. 密码使用 Argon2id，新增维护状态明确的密码哈希依赖；参数通过目标主机基准确认单次校验约 200～500 ms。
2. Session 与 CSRF 令牌使用密码学随机值，数据库保存带独立 pepper 的 HMAC-SHA-256；Session 当前/前一密钥支持无中断轮换。
3. 生产固定使用 `__Host-pnx_session`、`__Host-pnx_csrf` 和 `Secure`。本地 HTTP 开发只能使用无 `__Host-` 前缀的开发 Cookie 名称，配置在生产模式下若未启用 Secure 必须启动失败。
4. 邮箱验证/重置的明文随机令牌只在创建事务内短暂存在；写入 Outbox 前使用独立 `OUTBOX_ENCRYPTION_KEY` 进行认证加密，数据库中的一次性令牌仍只保存 SHA-256 哈希。Worker 解密仅用于构造目标邮件，日志与管理 API 永不返回明文或密文载荷。
5. 认证邮件通过通用 PostgreSQL Outbox 与 Worker 发送；SMTP 暂不可用不回滚注册或密码重置申请，最多 8 次指数退避后进入 `dead`。
6. 开发环境当前没有真实 SMTP 凭证，自动测试使用受控假 SMTP/适配器验证投递内容；局域网真实邮件验收需要后续注入校园 SMTP 配置，不新增公开邮件捕获页面或令牌旁路。

## 数据库与迁移

新增一条可回滚的阶段 2 Alembic 迁移，创建：

- `cohorts`、`directions`；
- `users`、`sessions`、`one_time_tokens`、`auth_security_events`；
- `outbox_jobs`、`audit_logs`。

约束包括邮箱/学号唯一、两角色/三账号状态、已激活账号邮箱验证时间、令牌用途、Session 唯一哈希、Outbox 事件幂等键、分类编码唯一、必要检查约束和查询索引。迁移 `downgrade` 按外键逆序删除本阶段对象，不修改阶段 1 心跳表。

## 后端实现

1. 新增 UUIDv7、时钟、令牌/HMAC、认证加密、IP 前缀、用户代理摘要和事务辅助能力，只实现本阶段真实需要的共享函数。
2. 建立 `auth`、`users`、`audit`、`notifications/outbox` 模块的 ORM、schema、Repository、Service 与 Router。
3. 实现注册、验证重发/确认、登录、退出、`/auth/me`、CSRF、Session 列表/撤销、密码重置申请/确认。
4. 实现 Session/角色依赖、账号每请求状态复核、Origin/Referer 和 CSRF 校验、登录/注册/重发/重置限流及统一枚举安全错误。
5. 实现管理员用户查询、禁用/恢复、资料/邮箱/可选分类修改、角色调整、最后管理员保护，以及届次/方向 CRUD。
6. 实现交互式 `python -m app.cli create-admin`，密码不进入命令行参数或 shell 历史。
7. 扩展 Worker：保留心跳并领取认证邮件 Outbox，执行 SMTP 发送、锁租约、指数退避、最终失败和幂等状态更新。

## 前端实现

1. 将禁用登录骨架替换为真实登录表单，并新增注册、邮箱验证、忘记密码、重置密码页面。
2. 建立集中 API Client、统一错误解析和 CSRF 获取/提交逻辑，不在页面散落原始响应判断。
3. 建立认证后学生/管理员最小布局、根路径按角色跳转、个人资料与 Session 管理页面。
4. 建立管理员用户、届次与方向页面，覆盖禁用、恢复、角色与可选分类维护；高风险动作要求原因和确认。
5. 所有表单提供字段错误、加载、防重复提交、键盘焦点、移动端布局和安全失败状态；不提前伪造通知/作业/赛事数据。

## API、权限与部署影响

- API 严格使用 `06-api-specification.md` 已定义的 `/auth/*`、`/admin/users/*`、`/admin/cohorts*` 和 `/admin/directions*`，不新增业务捷径。
- 除公共认证端点与健康端点外，新增接口默认要求有效 Session；管理接口额外要求 `admin`。
- 增加 Cookie 安全、Outbox 加密和认证/SMTP 配置变量；`.env.example` 只给说明性开发值，生产验证拒绝弱密钥和非 Secure Cookie。
- Compose 保持只有 Nginx 暴露主机端口；PostgreSQL、Worker 和任何投递秘密不新增外部入口。

## 测试与验收

### 后端

- 单元测试覆盖校园邮箱精确匹配、密码规则/Argon2id、令牌哈希与单次消费、Session 过期/撤销、CSRF、Origin、限流、最后管理员保护和 Outbox 退避。
- PostgreSQL 集成测试覆盖邮箱/学号并发唯一、账号状态、无分类激活登录、Session 撤销、角色/邮箱变更审计、`SKIP LOCKED` 领取和迁移约束。
- API 契约覆盖 AUTH-T01～AUTH-T11、SEC-T01、SEC-T03 的允许/拒绝两侧，不在日志、响应或管理查询中出现密码、Cookie、令牌或投递密文。
- Alembic 从阶段 1 升级到阶段 2、降级回阶段 1、再升级；验证单一 head 和实际 PostgreSQL 约束。

### 前端与端到端

- ESLint、严格 TypeScript、Vitest 和生产构建通过。
- 组件测试覆盖登录、注册、验证、重置、Session 撤销和管理员用户操作的加载、字段错误与无障碍语义。
- 在真实 Compose 中创建首个管理员，完成管理员登录、学生注册、验证后直接激活、无分类登录、禁用即时失效、密码重置和 Session 撤销流程。
- 在 360、768、1280、1440 px 检查核心认证与管理页面，验证键盘焦点和 AA 对比；不使用真实学生资料。

## 文档与完成条件

- 先新增本阶段必要 ADR，解释开发 Cookie 与 Outbox 投递秘密加密；同步 API、数据库、安全、部署、测试和变更记录。
- 更新 `current-task.md` 指向本计划；阶段验收完成后移入 `completed.md` 并更新路线图与项目记忆。
- AUTH-T01～AUTH-T11、SEC-T01、SEC-T03、迁移往返、完整 Compose 和浏览器核心流程全部通过后，才能为阶段 3 建立新计划。

## 明确不实施

- 不实现通知内容、作业、优秀作业、上传、赛事、队伍或提交业务。
- 不增加 OAuth、校园 SSO、MFA、长期 JWT、Redis/Celery、第三角色或注册审批。
- 不建立开发令牌公开接口、公开邮件查看页、真实学生测试数据或前端授权替代逻辑。
