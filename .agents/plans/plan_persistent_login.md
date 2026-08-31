# 持久登录与同源 IP 绑定实施计划

## 状态

已完成并部署，部署后登录跳转回归已热修复（2026-08-30）。

## 背景与问题本质

用户希望登录页提供“记住密码”，并在同一 IP 下避免频繁重复登录。现有实现不会保存明文密码，但所有登录都会把 Session 与 CSRF Cookie 固定持久化 14 天；服务端又按管理员 4 小时、学生 12 小时空闲过期，因此浏览器关闭后仍可能保留无效 Cookie，且没有显式的用户选择或来源 IP 绑定。

本任务把产品用语收敛为“记住登录状态”：浏览器和服务端仍不保存明文密码，只有用户主动勾选时才创建持久 Cookie 和长空闲 Session。来源 IP 不能单独代表账号，因为校园 NAT、宿舍和实验室网络可能让多人共享出口；免登录必须同时持有高熵 HttpOnly Session Cookie，并通过精确来源 IP 的会话级 HMAC 绑定。数据库只保留 HMAC 与既有 IP 网段摘要，不保存完整 IP。

## 影响需求与范围

- 新增 AUTH-013：可选记住登录、普通浏览器会话 Cookie、持久会话最长 30 天、精确来源 IP HMAC 绑定、网络变化立即撤销，以及 IP 不得单独认证。
- 继续满足 AUTH-004、AUTH-006、AUTH-009、NFR-001～NFR-002、NFR-006、NFR-008、NFR-012。
- 修改登录页面与请求体、Session Cookie/CSRF Cookie 生命周期、认证依赖、Session 服务与会话列表。
- 为 `sessions` 增加可空 `ip_binding_hash`，新增可回滚 Alembic `20260830_0016`；空值代表普通/历史会话，非空代表已记住且绑定来源 IP 的会话。
- 更新产品需求、页面、架构、API、数据库、安全、部署、测试、ADR、变更记录、当前任务、完成记录和项目基线。

## 现有结构与可复用能力

- 复用高熵 Session Cookie、数据库令牌哈希、CSRF 双提交校验、Session 撤销、密码重置和账号状态复核。
- 复用 Nginx 覆盖外部 `X-Forwarded-For` 为 `$remote_addr` 的可信代理边界，以及后端 `client_ip`/`request_ip_prefix` 解析。
- 复用 `Router → Service → Repository` 分层；Router 只映射 Cookie，Service 决定会话类型、期限和 IP 绑定，Repository 继续负责 Session 持久化。
- 复用登录页 `FormData`、统一 API Client、Session 列表与现有认证回归测试。

## 安全与产品取舍

1. 不实现密码 Cookie、localStorage 密码、可逆密码或浏览器指纹登录；密码仍只在登录请求内存中短暂存在并由 Argon2id 校验。
2. 不允许“只要 IP 相同就自动识别账号”。免登录必须同时满足持有有效 Session Cookie、账号仍为 `active`、Session 未撤销/过期、且精确来源 IP 绑定 HMAC 匹配。
3. 普通登录使用无 `Max-Age` 的浏览器会话 Cookie，服务端继续使用管理员 4 小时、学生 12 小时空闲期和 14 天绝对期。
4. 用户主动勾选后，Session 与 CSRF Cookie 持久化最多 30 天；服务端空闲期与绝对期均不超过 30 天。IP 变化时立即撤销该 Session，用户需重新输入密码。
5. `ip_binding_hash = HMAC-SHA256(raw_session_token, canonical_client_ip)`；原始 Session token 和精确 IP 均不入库，数据库泄露时不能仅凭低熵 IP 离线枚举绑定值。Cookie 轮换密钥和 CSRF 规则保持不变。
6. 历史 Session 的 `ip_binding_hash` 为 `NULL`，继续按旧期限工作，不在迁移时批量撤销或伪造为已记住会话。

## 实施步骤

1. 新增后端和前端失败测试：登录请求默认 `remember_me=false`，勾选时请求为 true；普通 Cookie 无持久期限，记住会话 Cookie 为 30 天。
2. 增加 Session 迁移和 ORM 字段；升级只添加可空列，降级只删除该列，不修改用户、密码、现有 Session 到期时间或安全事件。
3. Service 创建会话时按 `remember_me` 选择期限，并仅对记住会话生成精确 IP HMAC；认证时对非空绑定进行常量时间校验，失败则撤销会话并返回统一重新登录错误。
4. 认证依赖把可信精确来源 IP 传入 Service；Router 按会话类型设置 Session/CSRF Cookie，CSRF 轮换不能把普通 Cookie 意外变为持久 Cookie。
5. 登录页新增默认不勾选的“记住登录状态”复选框，明确“仅私人设备、当前网络、最多 30 天、不保存密码”；会话列表标识持久登录状态。
6. 同步 AUTH-013、API、数据库、安全、页面、架构、部署、测试与 ADR-045，记录共享 IP 不可作为唯一凭证的拒绝方案。
7. 运行认证/安全/API/迁移后端定向测试、前端登录定向测试、Ruff、格式、严格 Mypy、ESLint、严格 TypeScript；再运行完整后端/前端测试和生产构建。
8. 核对 Alembic 单一 head、Git 差异和无秘密输出；更新任务完成记录、变更记录和项目基线。本任务不擅自连接或迁移当前运行 PostgreSQL，不构建/部署镜像，除非用户另行授权部署。

## 验证方式

- API 契约：`remember_me` 为可选布尔值且默认 false；旧客户端不传字段仍能登录。
- 普通登录：Session 记录无 IP 绑定，Cookie 无 `Max-Age/Expires`，浏览器关闭后不再保留；服务端既有 4/12 小时空闲与 14 天绝对期不变。
- 记住登录：Session 记录只有 64 位 HMAC、不含精确 IP；Cookie 最长 30 天；同一精确来源 IP 和有效 Cookie可持续使用，来源 IP 变化立即撤销。
- 安全反例：没有 Cookie 即使 IP 相同也返回 401；复制 Cookie 到不同 IP 返回 401；禁用、密码重置、主动撤销、绝对过期继续失效。
- 前端：复选框默认关闭、勾选值正确进入 JSON、页面明确不保存密码；错误请求不把密码或登录标识写入持久存储。
- 迁移：`0015 → 0016 → 0015 → 0016` 静态/真实隔离往返按环境能力验证；降级只移除绑定字段。

## 实际验证结果

- 后端认证、安全、API 与迁移定向 70 项、完整 299 项 Pytest、Ruff、171 文件格式检查和 153 源文件严格 Mypy 全部通过。
- 前端完整 23 文件/105 项 Vitest、ESLint、严格 TypeScript 与 Next.js 生产构建全部通过。
- Alembic 静态契约确认 `20260830_0016` 为单一 head；从部署前加密备份恢复的隔离 PostgreSQL 完成 `0015 → 0016 → 0015 → 0016`，字段两次升级后均为可空 `varchar(64)`，降级后完全移除，`alembic check` 无漂移。
- 候选 Backend 因宿主机 umask 使新增源码为 0600，首次非 root 导入被健康门阻断；`backend/Dockerfile` 改为由 `appuser:appgroup` 拥有复制的应用与迁移后重新构建，UID 10001 导入、迁移头和 114 条 OpenAPI 路径均通过。
- 部署前加密备份 `pnx-backup-20260830T045545Z-daily` 的外层 SHA-256、完整解密、内部校验、Manifest 与 PostgreSQL 17 目录均通过；MinIO 2,885 个对象相对周基线无 payload 或删除变化。
- 生产迁移和 Backend/Worker、Frontend/Nginx 两阶段定向替换完成；六服务 healthy、重启 0，Alembic 为 `20260830_0016 (head)` 且无漂移，全表行数聚合哈希前后均为 `6a44c75dea0d9e822c8ea06169f8c76d6a529a249ad1e33644dad20d53274c05`。

## 风险与控制

- **共享出口误认证**：IP 只作为 Cookie 的附加绑定，绝不用于寻找用户或创建 Session。
- **网络切换导致重新登录**：这是精确 IP 绑定的预期安全结果；界面明确只有当前网络可免登录，移动网络或 VPN 切换后需重新认证。
- **长期 Cookie 被盗**：使用 `Secure`、`HttpOnly`、`SameSite=Lax`、同源 CSRF、30 天上限、精确 IP HMAC、账号状态复核和会话撤销共同限制风险。
- **历史兼容**：新列可空且旧请求默认不记住；不改变既有 Session token 哈希、Cookie 名或登录成功响应结构。
- **应用回滚放宽绑定**：旧应用可读取原 Session token，但不会校验新列；若已经产生持久会话，回滚前应先撤销 `ip_binding_hash IS NOT NULL` 的会话，正常故障处理优先前滚。

## 回滚方式

- 应用回滚到旧版本后，普通和记住会话仍是可识别的原 Session token；旧应用不会执行 IP 绑定校验，但会继续遵守记录内的到期时间。若安全要求禁止短暂放宽，应先撤销 `ip_binding_hash IS NOT NULL` 的会话再回滚应用。
- 数据库可从 `20260830_0016` 降级到 `20260829_0015`，仅删除 `sessions.ip_binding_hash`；不会删除账号、密码、Session 或其他业务数据。
- 前滚优先：若已产生记住会话，建议修复应用并保留绑定列，而不是降级后失去额外 IP 校验。

## 部署执行计划

1. 只读确认工作树范围、当前固定镜像、六服务健康、运行 Alembic `0015`、MinIO 健康、磁盘空间与 Docker 权限；不输出环境秘密。
2. 使用现有 OpenPGP 周基线生成部署前每日加密备份，验证外层 SHA-256、元数据、完整解密内部校验和与 PostgreSQL 17 目录；备份失败则停止部署。
3. 以完整当前源码构建固定标签 `persistent-login-20260830` 的 Backend 与 Frontend，检查镜像非 root、迁移单一 head、OpenAPI 契约、管理员用户搜索、队伍删除、账号/答疑删除与持久登录前端产物均存在。
4. 在隔离 PostgreSQL 副本完成 `0015 → 0016 → 0015 → 0016` 往返并核对新列，随后对生产运行库执行向后兼容的 `0016` 升级；不重建 PostgreSQL/MinIO。
5. 先替换 Backend/Worker并等待健康，再替换 Frontend/Nginx；固定 `.env` 标签并保留 `team-user-search-20260830` 回滚镜像。
6. 验收六服务健康、重启次数、五个健康入口、匿名页面/API 守卫、运行 OpenAPI、Alembic head、镜像用户、启动日志与安全响应头；不使用真实 Session、不调用登录或业务写接口。
7. 更新运维报告、变更记录、完成记录、项目基线、当前任务和本计划；记录备份、镜像、迁移、回滚与遗留外部介质/Docker ACL 风险。

## 部署实际结果

- `.env` 已固定为 `persistent-login-20260830`；Backend/Worker 镜像为 `sha256:6851f9892b16bfb6f2b4436dceba8b58b93651163882226770fc5339b91e6dc3`，Frontend 为 `sha256:96544dc22467f4ba4b74d236d9474bc1bfeb50b133c89cb695aa9cc3bf72424b`，旧合并镜像继续保留用于应用回滚。
- 生产 PostgreSQL/MinIO 容器 ID 与部署前一致，数据卷未重建；只执行一次 `0015 → 0016` 事务迁移，一次性 migrate 容器与隔离容器、网络、卷、明文临时目录均已删除。
- `/login`、三个 API 健康端点与 `/nginx-health` 均为 200；`/admin/sessions` 无 Cookie 为 307 `/login`，`/api/v1/auth/me` 无 Cookie 为 401，登录页存在“记住登录状态”。
- 新 Backend 运行 OpenAPI 中 `remember_me` 默认 false、类型为 boolean，Session `remembered` 为 boolean，共 114 条路径；六服务新验收窗口无 Traceback、事务、权限或连接错误。
- 本次没有使用生产账号、Session 或 Cookie，没有调用登录、删除、同步、上传或其他业务写接口。加密归档与临时 GPG 私钥仍同宿主机保存在 `/tmp`，Docker socket ACL 因交互式 sudo 密码要求尚未撤销。

## 部署后登录跳转回归修复

- 现象：用户勾选“记住登录状态”后登录响应成功，但跳转仍回到登录页；不勾选时可正常进入。
- 根因：浏览器登录 POST 经 Nginx 直达 Backend，持久 Session 绑定真实来源 IP；跳转后 Next.js Server Component 从 Frontend 容器直连 Backend，只转发 Cookie 而未转发 Nginx 已覆盖的来源 IP，导致首次 `/auth/me` 把容器 IP 误判为换网并撤销 Session。
- 修复：Frontend 服务端 API 同时读取入站 `x-forwarded-for` 与 Cookie，并把该单值来源 IP 头传给内部 Backend；Nginx 继续覆盖客户端伪造头，Frontend 不发布宿主端口，安全边界不放宽。
- 验证：增加 Server API 回归测试，断言 Cookie 与来源 IP 同时转发、缺失来源 IP 时不伪造；Frontend 定向 2 文件/11 项、完整 24 文件/107 项 Vitest、ESLint、严格 TypeScript、主机 Next.js 生产构建和 Docker 镜像内生产构建全部通过。隔离假 Backend 依次收到 `/auth/me` 与 `/dashboard` 的同一假 Cookie 和 `198.51.100.42`，临时容器与网络已清理。
- 部署：`.env` 固定为 `persistent-login-ip-forwarding-20260830`；新 Frontend 镜像为 `sha256:77dbfdec8659b82308eb159f2e48cdb2cb217974731eb4e080d4b83ffda90734`。本次仅替换 Frontend/Nginx，Backend/Worker 继续使用相同的 `sha256:6851f9892b16bfb6f2b4436dceba8b58b93651163882226770fc5339b91e6dc3`，未运行 migrate，PostgreSQL/MinIO 未重建。
- 验收：六服务 healthy、重启 0；`/login`、live、ready、worker 与 `/nginx-health` 为 200，`/admin/sessions` 匿名为 307，`/api/v1/auth/me` 匿名为 401；运行 Frontend 编译产物含 `x-forwarded-for`，新日志窗口无 Traceback、权限、连接、事务或外键异常。
- 兼容：回归期间已被不同来源地址误判并撤销的旧持久 Session 不会被热修复复活，用户需要重新勾选登录一次；之后同一有效 Cookie 与同一来源 IP 可正常进入。
