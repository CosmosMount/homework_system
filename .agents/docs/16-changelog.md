# 项目变更记录

本文件记录面向项目能力、架构和运维的重要变化，不逐条复制 Git 提交。

## 2026-08-30

### 持久登录与同源 IP 绑定源码完成（尚未部署）

- 登录页新增默认关闭的“记住登录状态”，只提交 `remember_me` 选择，不保存密码；普通登录改为浏览器会话 Session/CSRF Cookie，服务端既有管理员 4 小时、学生 12 小时空闲和 14 天绝对期限保持不变。
- 主动记住时 Cookie 与服务端 Session 最长 30 天，以原始高熵 Session token 为 HMAC key 绑定 Nginx 可信代理边界提供的精确来源 IP。数据库不存精确 IP；后续请求必须同时持有 Cookie 且 IP 匹配，IP 变化立即撤销，相同 IP 无 Cookie 仍返回 401。
- 登录 API 新增默认 `false` 的 `remember_me`，个人与管理员会话响应新增 `remembered`；可回滚迁移 `20260830_0016` 只增加可空 `sessions.ip_binding_hash`。登录人员页面会标识已记住会话。
- 后端认证/安全/API/迁移定向 70 项、完整 299 项、Ruff、171 文件格式检查和 153 源文件严格 Mypy 通过；前端完整 23 文件/105 项 Vitest、ESLint、严格 TypeScript 和 Next.js 生产构建通过。
- 本功能只完成源码、迁移与文档，没有连接、迁移或修改当前 PostgreSQL/MinIO，也没有构建或部署 Docker。运行应用仍为 `team-user-search-20260830`，运行库仍为 `20260829_0015`；部署时必须先应用 `0016`，已有持久会话后回滚旧应用会停止 IP 绑定校验，应优先前滚。

## 2026-08-29

### 管理员删除队伍源码完成（尚未部署）

- 新增真实管理员 `DELETE /admin/teams/{team_id}` 与队伍详情独立危险区；请求要求 CSRF、去空白后的非空内部原因和前端二次确认，成功返回 204 并返回校内赛管理页。
- 删除事务先锁定队伍、当前成员并统计团队提交引用：无历史提交时物理删除队伍与成员关联；有历史提交时释放全部当前成员、清空队长与当前取消资格元数据、转为 `dissolved`，保留队伍壳、成员历史、不可变版本、评语和附件。两种模式均退出学生端、常规管理员列表和直接详情并写脱敏审计。
- 复用既有状态、外键与审计，无 Alembic 迁移或新依赖。后端定向 16 项与完整 291 项、Ruff、170 文件格式、120 源文件严格 Mypy 通过；前端定向 9 项与完整 23 文件/104 项、ESLint、严格 TypeScript 和 Next.js 生产构建通过。
- 本功能尚未部署；验证未连接当前 PostgreSQL/MinIO、未调用真实 DELETE、未访问 Docker socket，也未运行备份、镜像构建或部署命令。

### 源码阶段记录（随后已部署）

- 完成真实管理员永久删除非本人账号与用户自助注销源码：新增受 CSRF 保护的 `DELETE /admin/users/{user_id}` 和 `DELETE /auth/account`，要求当前密码、目标邮箱确认、最后管理员保护与脱敏审计；管理员另须填写非空白原因并确认 PostgreSQL + MinIO 备份可恢复。
- 新增 `20260829_0015`，把个人数据外键改为 `CASCADE`、共享创建者/操作者/上传者改为可空 `SET NULL`；队长删除前转移或解散队伍，锁定队伍人数不足时失效。正式版本触发器仅对 `pnx.account_erasure=on` 且父提交已删除的账号擦除事务放行级联 DELETE。
- 个人作业附件和未绑定上传通过可靠 `delete_account_object` Outbox 清理，Worker 先终止 multipart 再幂等删除；通知和团队版本共享附件继续保留。邮件任务清除收件人/姓名/秘密，认证安全事件去除账号与邮箱关联。
- 纯 Mock/静态后端定向 45 项、Ruff、格式、120 个源文件严格 Mypy，以及前端最终 23 文件/102 项 Vitest、ESLint、严格 TypeScript 和生产构建通过；迁移静态契约保持单一源码 head。
- 在该源码完成阶段，功能尚未部署，`0015` 尚未执行；当时未连接、迁移、测试或修改当前 PostgreSQL/MinIO，未调用真实删除接口或 5000 写接口，也未运行会读取当前数据的备份脚本。随后已在加密完整备份和隔离恢复/迁移往返通过后部署，结果见本文件后续“部署管理员永久删除账号与用户自助注销”章节。

### 管理员用户全量搜索源码完成（随后已部署）

- 修复管理员用户页只请求前 100 个账号并在浏览器本地搜索的问题；此前已有的中文角色/状态搜索也只过滤已加载第一页。本候选改为服务端全库搜索和每页 20 条分页，空搜索可以逐页查看全部账号，并显示当前页、总页数和匹配总数。页码限制为 1～10000，越界 URL 带原筛选回到实际末页。
- 搜索、活跃度筛选与页码统一写入 URL，翻页保留筛选；服务端搜索覆盖姓名、邮箱、学号、中文/英文角色及状态，并把 `%`、`_` 和反斜杠作为普通文本处理。资料、角色、状态或删除成功后按同一查询刷新，删除导致末页收缩时回退，避免 OFFSET 跳项。
- 既有真实管理员鉴权、账号响应字段、已上线账号删除保护和全部用户写操作保持不变。本修复无迁移；Backend 定向 33 项及相关静态门通过，共享工作树其余 289 项后端测试通过，2 项范围外竞争赛测试因赋值前读取 `team` 失败；Frontend 23 文件/103 项、ESLint、严格 TypeScript 和生产构建通过。验证未连接、读取或修改当前 PostgreSQL/MinIO，也未调用运行环境 API。

### Deployed

- 部署 Backend/Worker `pnx-training-backend:help-requests-20260829` 与 Frontend `pnx-training-frontend:help-requests-20260829`，两者均以 `appuser` 运行；Compose 固定标签已同步更新。
- PostgreSQL 运行库从 `20260828_0013` 迁移到 `20260828_0014`，仅新增私密反馈答疑表、约束、外键与索引；初始工单数为 0。
- 部署 Backend/Worker `pnx-training-backend:help-public-20260829`（`sha256:942b9ee5e98d…`）与 Frontend `pnx-training-frontend:help-public-20260829`（`sha256:93feb800a8c6…`），包含已解答问题公开答疑和学生分类提醒；旧应用镜像保留用于回滚。
- 本次只替换应用服务，PostgreSQL 保持 `20260828_0014`，未执行迁移或业务写入。
- 学生提醒共享页面补丁部署为 Frontend `pnx-training-frontend:notification-badges-20260829`（`sha256:fd13387f14a5…`）；Backend/Worker 容器不变，原 Backend 镜像只增加同名固定别名，`.env` 已固定到新统一标签。
- 认证失败窗口修复已部署为 Backend/Worker `pnx-training-backend:auth-window-20260829`（`sha256:716685804552…`），均以 `appuser` 运行且重启次数为 0；当前 Frontend 镜像只增加同名固定别名，未重建或替换，`.env` 已固定到新标签。
- 管理员内容删除已部署为 Backend/Worker 与 Frontend 固定标签 `admin-content-removal-20260829`；应用镜像分别为 `sha256:a9e4e73584e3…` 与 `sha256:1ce818d5d2d6…`，PostgreSQL、MinIO 未重建。
- 注册唯一约束热修已部署为 Backend/Worker `pnx-training-backend:registration-constraint-20260829`（`sha256:0972df29b375…`）；镜像以当前管理员内容删除版本为基底只覆盖认证服务文件。Frontend/Nginx 未替换，现有 Frontend 镜像只增加同名标签别名，`.env` 已固定到新标签。

### Validation

- PostgreSQL 17 备份校验和生产副本隔离 `0013 → 0014 → 0013 → 0014` 往返通过，Alembic 无模型漂移，旧用户、问卷 `2/3/11/2/2` 和知识库 `212/986` 数据保持不变。
- 六服务 healthy，四个健康端点返回 200；四个反馈答疑页面匿名访问返回 307，OpenAPI 六个操作均存在且匿名访问返回 401。
- 部署后日志无启动、权限或事务异常；未触发飞书同步、邮件、账号删除或上传。
- 完整后端 246 项、Ruff、169 文件格式和 120 源文件严格 Mypy 通过；完整前端 21 文件/89 项、ESLint、严格 TypeScript 和生产构建通过。
- 六服务 healthy，四健康端点 200；公开页面匿名 307、公开 API 匿名 401，运行 OpenAPI 含八个反馈答疑操作且公开响应无提交者/通知/Markdown 源文字段。
- Alembic `20260828_0014 (head)` 且无模型漂移；运行库现有 1 条 `question/resolved`，未由本轮修改并自动进入公开范围。
- 新应用服务近期日志无启动、权限或事务错误；未触发飞书同步、邮件、账号删除或上传。
- 学生提醒共享页面增量通过 22 个前端测试文件/90 项测试、ESLint、严格 TypeScript、主机与容器生产构建；部署后六服务 healthy、四健康端点 200，`/profile`、`/sessions`、`/help/public/{id}` 匿名访问 307，Dashboard API 匿名访问 401。
- 本次部署临时 Docker socket 命名 ACL 已由用户撤销，复核恢复为 `root:docker`、`0660` 基础权限。
- 认证失败窗口与密码校验修复通过 44 项认证/密码安全定向测试和完整 254 项后端测试；Ruff、169 个 Python 文件格式检查及 120 个源文件严格 Mypy 通过。
- Alembic 保持 `20260828_0014 (head)`，迁移目录无差异；测试证明当前 Argon2id 参数无需升级时密码哈希原值不变。
- 部署前 PostgreSQL 17 自定义格式备份 `/tmp/pnx-training-before-auth-window-20260829T081859Z.dump` 已在同版本容器内通过 `pg_restore --list`，大小 4,306,752 字节、权限 0600、SHA-256 `05f7ec8f7de2b6213461ca4133469f96ec624d276798b0ad6719ab53d3c8b46d`。
- 部署后六服务 healthy；登录页、`live`、`ready`、`worker` 与 Nginx 健康端点均为 200，`/profile`、`/sessions` 匿名访问为 307，`/api/v1/auth/me` 匿名访问为 401；运行 Backend 已确认只保留一个 10 分钟应用层失败窗口，近期真实登录返回 200。
- Alembic 保持 `20260828_0014 (head)`。发布期间真实外部流量新增并验证 1 个账号，同时产生 6 条登录失败、1 条密码重置申请、1 条注册和 2 条重发验证事件；问卷 `3/5/21/80/158`、反馈答疑 `1/1`、知识库目录节点/媒体 `684/986` 前后不变。部署没有调用认证写接口，未删除或回滚并发业务数据。
- Docker socket 临时 `user:pnx:rw-` ACL 已由用户撤销；复核只剩基础 ACL，socket 恢复为 `root:docker`、`0660`，当前用户访问 Docker API 返回 permission denied。
- 管理员内容删除最终工作树通过 Ruff、169 文件格式、153 个源文件严格 Mypy、264 项 Pytest、ESLint、严格 TypeScript、22 文件/95 项 Vitest 和 Next.js 生产构建；隔离部署候选另通过 38 项后端定向测试、125 个源文件静态检查及容器构建。
- 部署前 PostgreSQL 17 备份 `/tmp/pnx-training-before-admin-content-removal-20260829T091428Z.dump` 通过 314 项 `pg_restore --list` 校验，大小 4,320,274 字节、权限 0600、SHA-256 `194a1cdd7c2330fc7dd7e0ef70cf7d68240c95761f2c7ad352b5579df4446629`。
- 六服务 healthy 且重启次数为 0；登录页和四个健康端点为 200，管理/学生页面匿名为 307，两个 DELETE API 匿名为 401，运行 Backend OpenAPI 含两个 DELETE/204 操作。Alembic 保持 `20260828_0014 (head)`，本轮无迁移。
- 部署候选明确排除并行注册唯一约束修复，运行认证源码与部署前一致。最近 15 分钟聚合的 6 次未处理异常仍来自该既有重复注册问题，不属于管理员内容删除回归；工作树修复及其完整 264 项测试保持未部署状态。
- 注册热修部署前 PostgreSQL 17 备份 `/tmp/pnx-training-before-registration-constraint-20260829T103222Z.dump` 通过同版本 314 项 `pg_restore --list` 校验，大小 4,328,438 字节、权限 0600、SHA-256 `b45dbbcc44c89576305511877687a2eae14c6b5f3f09fc76aaa2255dede5fc4a`。
- 候选镜像层链确认完整继承当前管理员内容删除 Backend，仅新增一个 `0644 appuser:appgroup` 认证文件层；运行认证文件 SHA-256 为 `d25505a99c2b712e7078be61deae1522c40a62e9fec13a5184aafcd4c8580825`，嵌套约束映射和既有两个 DELETE OpenAPI 路径断言通过。
- Backend/Worker 以 `appuser` 运行、重启次数为 0 且 healthy；Frontend、Nginx、PostgreSQL、MinIO 未替换并持续 healthy。登录页、`live`、`ready`、`worker`、`nginx-health` 均为 200，近期 Backend/Worker 日志无未处理异常、Traceback、权限或严重错误模式。
- Alembic 保持 `20260828_0014 (head)`，无迁移。部署窗口持续外部流量使用户净增 1、注册事件净增 2、验证令牌净增 1；部署命令未调用认证写接口，也未删除、重置或回滚用户、密码、安全事件、令牌或 Session。
- Docker socket 临时 `user:pnx:rw-` ACL 仍待用户在宿主机交互式撤销；普通 `setfacl` 被拒绝，`sudo -n` 要求密码。应用部署与健康不受此权限收尾影响。

### Changed

- 新增 `DELETE /admin/announcements/{id}` 与 `DELETE /admin/assignments/{id}`：未发布通知/作业物理删除并取消活动定时发布，已发布内容转为归档，重复删除已归档资源幂等成功。
- 管理员通知和作业编辑页以二次确认的“删除通知 / 删除作业”替代并列归档入口；删除成功返回管理列表，取消确认不发送请求。
- 已归档通知和作业立即退出学生列表、详情及作业内优秀作业入口，优秀作业附件签名同步收紧；受众快照、正式提交、评语、优秀标记、提醒、附件元数据与审计记录继续保留。
- 旧归档 API 保持兼容；删除接口继续使用真实管理员、CSRF、行锁、统一错误与脱敏审计，不新增数据库字段、迁移或依赖。
- 已确认问题答疑在管理员解答后向有效登录用户匿名公开；开放问题和全部系统反馈继续仅本人和管理员可见。
- 新增登录态公开答疑列表/详情 API 与学生公开详情页面，公开响应不包含提问者 UUID、姓名、学号、邮箱或 Markdown 源文。
- 公开可见性固定由 `question + resolved` 派生，不新增数据库字段、迁移、手动开关、评论、追问、附件、点赞或评分。
- ADR-037 部分替代 ADR-036 的“全部私密”范围，原本人权限、管理员处理事务、revision、通知和审计规则保持不变。

### Fixed

- 修复应用层登录失败冷却在账号查询和 Argon2id 校验前直接拒绝请求的问题；已验证 `active` 账号输入正确密码时立即登录，不再被既有失败事件施加持久等待。
- 删除注册、验证邮件重发和密码重置申请的 1 小时应用层持久失败窗口；这些入口继续写安全事件并保留 Nginx 瞬时入口保护。
- 无效密码、未知账号、待验证和禁用账号仍使用统一错误，按规范化邮箱和来源 IP 保留 10 分钟失败窗口，返回 `Retry-After: 600`；Nginx 瞬时入口限流、dummy Argon2id 和透明参数升级边界保持不变。
- 修复 SQLAlchemy/asyncpg 嵌套包装导致注册唯一约束名无法识别的问题；重复邮箱和重复学号现在都会回滚注册事务，并返回既有 `400 VALIDATION_ERROR` 字段错误，而不是通用未预期 500。前端对应输入框显示“该邮箱已注册”或“该学号已注册”。
- 唯一约束识别只遍历异常因果链上的结构化 `constraint_name`，不解析数据库错误文本；未知约束继续作为未预期异常上抛，避免错误分类。
- 本修复不新增迁移，不删除、清空、重置或批量重算用户及密码数据。
- 修复学生侧把全部站内未读集中显示在“通知”入口的问题：工作台新增公告、作业、校内赛和反馈答疑分类计数，侧栏只在提醒实际目标入口显示徽标。
- 公告归档事务同步把该公告未读提醒标记为已读，分类查询也排除历史遗留归档公告提醒；公告或本人工单详情通过既有 CSRF 写接口自动同步已读，其他业务提醒不受影响。
- 本轮不新增数据库迁移、依赖或第二套通知中心，保留兼容总数与提醒幂等事件键。

## 2026-08-28

### Added

- 新增私密“反馈答疑”工单域：学生可提交系统反馈或问题答疑并查看本人记录，真实管理员可筛选全部工单、填写或修订处理结果。
- 新增学生 `/help`、`/help/[requestId]` 与管理员 `/admin/help`、`/admin/help/[requestId]` 页面，以及六个受保护 API；共享侧栏按有效角色显示对应入口。
- 新增 `20260828_0014` 迁移和 `help_requests` 表，包含类型/状态/答复一致性检查、用户外键、本人列表与管理员筛选索引；降级会删除全部工单数据，生产执行前必须备份。

### Security

- 学生查询在仓储层绑定本人 UUID，他人记录与不存在统一 404；普通管理员视图不能调用学生接口，管理员学生视图只按本人学生路径使用，管理接口只允许真实管理员。
- 学生正文与管理员答复统一由服务端 Markdown 允许列表清洗；通知和审计不保存问题或答复正文，也不发送邮件。
- 管理员答复先锁定工单并校验 revision，在同一事务提交状态、答复、脱敏审计与幂等站内通知；过期 revision 返回 `REVISION_CONFLICT`。

### Testing

- 反馈答疑定向后端 24 项（含领域、OpenAPI 与迁移契约）和前端 5 项交互回归通过；覆盖两种类型、本人 404、学生视图、Markdown、管理员筛选、答复修订、重复提交与通知/审计事务。
- 完整后端 Ruff、169 个文件格式检查、153 个源文件严格 Mypy、242 项 Pytest 通过；完整前端 21 个文件/87 项 Vitest、ESLint、严格 TypeScript 和 Next.js 生产构建通过。
- Alembic 源码保持单一 `20260828_0014` head。当前环境 Docker socket 拒绝访问且没有本地 PostgreSQL 服务端，因此未执行 `0013 → 0014 → 0013 → 0014` 真实往返，也未迁移现有运行库。
- 在独立空库和 300 个虚构学生容量数据上执行 100 账号同出口同时登录：当前 Nginx 只放行 21 个，79 个由 `auth_limit` 直接返回 503；Backend 未收到这些拒绝请求，成功请求均产生唯一 Session。
- 绕过 Nginx 的隔离对照中，第 101～200 个虚构账号 100/100 登录成功，总耗时 5.293 秒、P95 5.235 秒，数据库为 100 个 Session/100 个独立用户，服务保持健康。
- 测试项目、卷、网络、专用镜像和临时密码文件已清理；隔离压测步骤没有修改现有 5000 运行实例、真实账号或业务数据，随后功能部署单独记录在本日 Deployed 小节。

### Known issues

- `infra/nginx/nginx.conf` 与生产配置把所有认证请求共用 `5r/s`、`burst=20` 的来源 IP 桶，会误伤校园 NAT 下的集中正常登录，并让 Nginx 默认返回 503 而非限流契约的 429。需单独拆分登录突发保护、保留应用层账号/IP 失败限制并增加配置契约与端到端负载回归。

## 2026-08-27

### Added
- 新增可回滚数据迁移 `20260827_0010`，为现有 active student 补录仍开放且匹配的作业受众快照。
- 学生 `/competitions` 收敛为单一校内赛队伍中心，增加队伍名称搜索、分页和不含成员/邀请码的公开摘要。
- 新增主动自动分配：仅报名期已报名且无队伍学生可用，优先加入人数较少的未满成形队伍，无候选时自动建队并一次返回邀请码；事务锁和一赛一队唯一索引共同处理并发。
- 新增独立学生意向调查域：管理员创建单选/多选调查、开放/关闭/归档和查看匿名汇总；学生登录后填写或修改本人回答。
- 新增管理员本地二维码生成与移动端填写入口；二维码 token 只存 SHA-256，轮换后旧码失效，扫码登录后安全返回原调查。
- 新增可回滚迁移 `20260827_0009`，包含 `intention_surveys`、`intention_options`、`intention_responses` 和 `intention_response_options` 四张表。

### Changed
- 后续账号验证为普通学生时，在激活事务内加入当时仍开放且匹配的作业正式快照；之后调整方向仍不重算历史归属。
- 注册、密码重置和管理员命令行创建账号的密码长度统一为 8～128 个字符，前端提示与浏览器约束同步为 8 位下限。
- 学生与管理员侧栏增加“意向调查”入口；管理员意向页面继续复用统一 `AdminPageHeader`、蓝白圆角表面和响应式表单。
- 校内赛卡片只展示队伍名称、状态与人数；自动分配新队伍邀请码和管理员二维码 token 只在当前响应中短暂展示。

### Security
- 八位下限继续保留 Argon2id、128 位上限、常见密码拒绝以及邮箱/学号相似性检查，并补充常见八位弱密码。
- 意向个人回答仅本人可读，管理员接口只返回有效学生数、填写人数/比例和各选项汇总，不返回姓名、学号或补充说明。
- 二维码不是匿名凭证；调查页面和 API 仍要求 Session、CSRF、有效角色和开放状态。登录 `next` 只接受同源绝对路径，拒绝外部 URL、协议相对 URL 和登录递归。
- 二维码由前端本地 `qrcode` 库生成，不向第三方发送填写 URL 或 token。

### Testing
- 新增新学生激活补录、初始管理员跳过、开放/匹配/已有快照 SQL 条件和 0010 单头迁移回归；隔离数据库完成 `0009 → 0010 → 0009 → 0010`。
- 新增 7、8、128、129 位密码策略边界及注册/重置表单八位约束回归。
- 新增队伍目录隐私/搜索/分页、邀请码资格与容量、最小队伍优先、自动建队、状态拒绝和并发冲突回归。
- 新增意向 Schema、Markdown 清洗、状态机、首次/修改回答、单选限制、关闭拒绝、零分母统计、二维码哈希轮换和旧码失效回归。
- 新增学生队伍中心、自动分配、意向单选/多选、管理员创建/状态/统计/二维码，以及扫码登录安全回跳前端回归。

### Operations
- 新学生作业可见性增量通过 Ruff、146 个 Python 文件格式检查、134 个源文件严格 Mypy、164 项后端测试、ESLint、严格 TypeScript、18 个前端测试文件/63 项测试及主机/容器 Next.js 构建；运行库升级到 `20260827_0010`，目标学生已进入“电控第一次作业”正式快照，六服务 healthy、四个健康端点为 200、Alembic 无漂移。
- 首次运行迁移在读取 0600 的新脚本前退出，数据库仍完整停留 0009；修正仓库文件为 0644 并重建后成功升级，无半迁移数据。部署前受众表备份位于 `/tmp/homework_system_assignment_audience_before_0010_20260827.sql`。
- 八位密码策略增量通过 Ruff、134 个 Python 文件格式检查、134 个源文件严格 Mypy、163 项后端测试、ESLint、严格 TypeScript、18 个前端测试文件/63 项测试及主机/容器 Next.js 生产构建。Backend、Worker、Frontend 和 Nginx 已重建重启，六个服务 healthy，四个健康端点及注册/重置页面为 200。
- 完整质量门通过：Ruff、145 个 Python 文件格式、134 个源文件严格 Mypy、159 项后端测试；ESLint、严格 TypeScript、18 个前端测试文件/62 项测试及 Next.js 主机/容器生产构建。
- `npm audit --audit-level=high` 与 Python 锁定依赖审计均为 0 个已知漏洞；Alembic `check` 无模型漂移。
- 应用迁移已到 `20260827_0009 (head)`；Backend、Worker、Frontend、Nginx 已重建重启，六个 Compose 服务 healthy，四个健康端点为 200，新增页面/API 的匿名守卫为 307/401。

## 2026-08-26

### Changed
- 移除管理员届次设置、用户资料届次字段以及通知/作业新建表单的届次选择；当前产品分类收敛为技术方向，新建请求始终发送空 `cohort_ids`。
- 保留 `cohorts` 表、旧管理 API 和历史受众关联，编辑历史资源时原样兼容，不执行数据删除或数据库迁移。
- 共享侧栏、品牌、身份卡和视图操作改用统一的内联 SVG 原子图标，移除首字母与中文单字占位，不新增第三方图标依赖。
- 页面根背景统一为纯白，移除网格和径向渐变；保留浅蓝 hover、提示和主按钮表面以维持交互层次。
- 调整蓝灰文字、边框、阴影与浅蓝按钮令牌，认证页、侧栏、管理员页头、卡片和表单控件统一使用圆角与低对比度层次。
- 共享侧栏改用首字母圆角导航图标和 active 卡片状态，底部增加姓名/有效角色身份卡；退出、学生视图和个人入口统一触控尺寸与 hover 反馈。
- 认证页增加白色表单卡片与 PNX 品牌标识，内容面板和输入控件统一使用白底蓝灰层次。
- 管理员可在当前 Session 开启或关闭学生视图：后端以 `student_view` 区分有效角色，学生业务按学生权限执行，所有管理员 API 在该视图返回 403；侧栏提供“查看学生视图/返回管理员视图”入口。
- 其他管理员将账号真实角色降为 `student` 时撤销该用户全部 Session，学生视图不能恢复管理员权限；新增可回滚迁移 `20260826_0008`、认证/用户管理回归及侧栏切换回归。
- 校内赛产品范围收敛为“公告 + 报名组队”：新赛事不设置赛题或作品提交，管理员与学生端均移除赛题入口；旧赛题表和 API 仅作为历史数据兼容路径保留。
- 赛事发布不再要求至少一个赛题；补充无赛题发布、公告展示和组队入口回归测试。
- 管理员通知、作业和赛事列表页参考 `management_system` 的 `PageCommandBar`，统一使用紧凑页头与浅蓝创建按钮；新增 `AdminPageHeader`，不改变业务路由或权限。
- 新增 `commandButtonClassName` 和 `commandLinkClassName`，创建入口统一为 `h-9`、`rounded-lg`、浅蓝底深蓝字，表单主按钮保持既有样式。
- 登录后页面改用共享响应式侧边栏；桌面端可折叠，移动端可打开抽屉，管理员和学生沿用各自入口并显示当前 active 状态。
- 已保存作业编辑页默认展示与学生详情一致的 Markdown 渲染结果，源文本编辑器改为按需展开；新建作业仍直接显示源文本输入，不改变提交与发布接口。

### Fixed
- 修复 Dashboard 作业聚合漏传管理员学生视图的临时受众参数；已发布但不在普通学生快照中的作业现在会出现在工作台“近期作业”。
- 修复 CI 严格 Mypy 对 `list_admin_sessions` 测试上下文的 `SimpleNamespace` 类型错误，以及通知测试中 `MailSender.calls` 属性推断的两个错误；修复范围仅限测试类型标注。
- Markdown 编辑表单保留源文本输入，其他页面统一通过 `SafeHtml` 展示服务端安全 HTML；移除预览标题、清洗标记等内部实现文案，管理员编辑区与用户详情复用同一渲染路径。

### Operations
- 管理员学生视图增量通过后端 134 项测试、Ruff、严格 Mypy，前端 47 项测试、ESLint、严格 TypeScript 和 Next.js 生产构建；应用 `20260826_0008` 迁移后重建 Backend/Worker/Frontend/Nginx。
- 六个 Compose 服务健康，Alembic 当前为 `20260826_0008 (head)`；5000 端口 `/health/live`、`/health/ready`、`/health/worker`、`/nginx-health` 返回 200，匿名管理员会话 API 返回 401，业务页面由登录守卫返回 307。
- 后端认证/通知定向测试 14 项、Ruff 检查/格式检查、严格 Mypy 127 个源文件通过；前端 14 个测试文件 42 项测试、ESLint、严格 TypeScript 和 Next.js 生产构建通过。
- 未修改 API 契约、权限规则、数据库结构、迁移或运行时业务逻辑。
- 前端 14 个测试文件 43 项测试、ESLint、严格 TypeScript 和 Next.js 生产构建通过。

## 2026-08-25

### Added
- 主操作按钮改为浅蓝底深蓝字，统一圆角、阴影和悬停反馈；学生端筛选/上传及管理员新建通知、新建作业、新建赛事入口复用共享按钮样式，并增加加号图标。
- 管理员作业编辑页新增“Markdown 渲染预览”，复用服务端清洗后的 HTML 结构展示标题、列表、代码块等内容，未保存内容仍明确以编辑区为准。
- 全局视觉换肤为蓝白主色、蓝色主操作、浅蓝背景和蓝灰边框；基础控件与内容容器统一增加圆角和低对比度层次阴影。

- 新增唯一账号管理员保证：历史数据库只有一个已验证 `active student` 时，部署迁移或下次成功登录会在事务锁内把真实角色持久化为 `admin`，撤销旧 Session 并写独立审计；待验证、禁用和多账号数据库不提升。
- 新增 `20260825_0007` 数据修正迁移与 ADR-022；迁移不改表结构，降级保留已授予管理员，避免回滚后重新失去管理入口。
- Connect 邮箱 local-part 自动作为派生用户名；激活账号支持用户名或完整邮箱登录，旧域名存量账号继续使用完整邮箱。
- 登录 API 新增 `identifier` 主字段并兼容旧 `email` 请求；注册成功页展示用户名和邮箱验证前不可登录提示。
- 新注册及管理员邮箱修改切换为精确 `@connect.hkust-gz.edu.cn`，空系统首个完成邮箱验证的账号在事务锁内唯一成为受最后管理员保护的 `admin`，后续账号保持 `student`。
- 新增 `20260825_0006` 邮箱约束迁移、初始管理员授予审计与 ADR-020；旧域名存量账号继续可用但应用层不再接受旧域名新写入，交互式管理员命令降为受控恢复工具。
- 完成阶段 6 生产运维加固：固定镜像生产 Compose、HTTPS Nginx、`*_FILE` secret、最小权限/只读根文件系统/资源限制、机器健康快照与独立告警、发布/回滚、安全扫描和 Playwright/容量工具。
- 新增 OpenPGP 备份工具链、对象清单 v2、MinIO 周完整与每日累计增量、保留依赖保护、显式隔离恢复和默认只读的数据库/对象存储引用对账。
- 新增容量与性能报告、生产运维与故障恢复报告，以及 ADR-019“MinIO 每日累计增量基于当前周完整备份”。
- 完成阶段 5 校内赛闭环：六阶段赛事、个人报名/撤回/取消资格、多赛题、邀请码组队、一赛一队、队长转让、锁队/失效/豁免、当前队长团队正式版本和当前成员私密评语。
- 新增管理员赛事、赛题、个人报名和队伍工作台，支持带原因补录/移除、队长修正、人数豁免、个人/整队取消资格和各赛题提交摘要；赛事版本不提供优秀作业操作。
- 将共享提交和 MinIO multipart 扩展到 `competition_submission`，新增可回滚 `20260825_0005` 迁移、团队所有者二选一约束、一赛一队部分唯一索引、队长成员一致性与赛题截止约束。
- 完成阶段 4 作业闭环：固定逐学生受众快照、公共截止与个人延期、草稿/定时发布/关闭/归档、个人不可变版本、管理员统计、私密评语 revision 和作业内优秀版本。
- 将通用 MinIO multipart 扩展到 `assignment_submission`，在初始化与正式绑定时复核角色、受众、截止、扩展名、总量、所有者、上下文、状态和占用；下载授权覆盖本人、管理员及作业受众可见的优秀源版本。
- 新增可回滚的 `20260824_0004` 迁移、学生与管理员作业页面、提交审阅页、真实工作台作业数据、动态加载态，以及阶段 4 后端与前端回归测试。

### Security

- 唯一账号修正复用初始管理员固定 PostgreSQL advisory lock，并在锁内重新锁定用户行、复核不存在其他账号；角色 revision、Session 撤销和授予审计同事务提交。
- 邮箱验证和密码重置邮件在解密载荷、连接 SMTP 前复核事件关联令牌；已使用、过期、用途不符或被替代的任务以脱敏 `dead/TOKEN_SUPERSEDED` 终止，避免 SMTP 恢复后投递失效链接。
- 初始管理员判定使用固定 PostgreSQL 事务级 advisory lock，并与激活、角色授予和 `user.initial_admin_granted` 审计同事务提交；不增加 `super_admin` 第三角色。
- 用户名与对应 Connect 完整邮箱统一规范化为同一限流键；待验证账号使用任一登录标识仍返回统一认证失败，不能绕过邮箱验证。
- 生产配置拒绝 HTTP、弱秘密、错误校园域名和不安全 Cookie；只允许 Nginx 发布 HTTP/HTTPS，PostgreSQL、MinIO 管理端口、Frontend 与 Backend 不公开。
- 前后端发布候选改用固定 digest 的 Alpine 3.23.5 最小运行时；最新 Trivy 数据库下两个镜像和生产配置的 HIGH/CRITICAL 均为 0，npm/pip 依赖审计为 0。
- 固定 Gitleaks 8.30.1 同时扫描 Git 历史和 `git ls-files --cached --others --exclude-standard` 候选树，避免未提交阶段成果逃逸；两类扫描泄漏均为 0。
- 所有可恢复备份离开宿主机前使用 OpenPGP 加密；本地周基线状态必须与备份输出分离且权限为 `0700`，恢复只接受显式 `pnx-restore-*` 空环境并校验外部/内部哈希。
- 邀请码只保存带服务端 pepper 的 HMAC，明文仅在创建/轮换响应出现一次且不写审计；当前成员/历史成员、其他队伍和非队长权限分别返回允许结果、404 或 `TEAM_CAPTAIN_REQUIRED`。
- 个人取消资格原因只向本人和管理员返回，仍在队内时整队联动取消资格但队友只获得固定通用原因；管理员纠错原因全部进入审计。

### Fixed
- 修复普通局域网 HTTP 非安全上下文中 `crypto.randomUUID()` 不存在，导致作业/通知发布、正式版本和上传幂等请求在发出前失败的问题；浏览器端统一优先使用原生 UUID，缺失时以 Web Crypto `getRandomValues()` 生成 UUID v4，不使用低熵随机降级。
- 管理员新增全体活跃登录人员视图，后端仅返回脱敏用户、设备、IP 网段和活动时间；个人资料页支持管理员维护自己的姓名、学号和校园邮箱，继续复用 revision、审计与邮箱重新验证规则。
- 修正 `20260825_0007` 新文件权限为 `0644`，确保 Backend 镜像中的非 root 运行用户可读取 Alembic 迁移。

- 修复宿主机 SMTP 配置更新后运行中 Worker 仍持有旧环境、验证邮件持续退避的问题；在不发信预检通过后仅重建 Worker，并受控恢复最新有效验证任务。
- 修复统一前端 API Client 把 `202 Accepted` 空响应强制解析为 JSON 的问题；重发验证和密码重置申请现可正确显示统一成功提示，`204` 与非空 JSON 成功响应保持兼容。
- 根据真实待验证账号反馈，将误导性的“用户名、邮箱或密码错误”改为包含邮箱验证排查项的统一失败提示，并在登录页增加常驻验证说明与重发入口；不暴露具体账号状态。
- 消除作业列表提交/最新版本/反馈和赛事列表报名/队伍状态的热点 N+1；工作台跳过无用分页 count 并保留进行中赛事数据。
- 修复最终镜像扫描使用旧 Debian `stage6-local` 标签导致 49 个陈旧 HIGH/CRITICAL 的问题；重建当前 Alpine 候选后严格重跑，不增加忽略规则。
- 安全工具和 Playwright 容器不再复用 `HOME=/tmp`；分别使用显式 Trivy 缓存、Syft 更新开关、npm/XDG 缓存，并增加阶段 6 契约测试。
- 修复容量种子将允许扩展名写成 `.txt/.pdf/.zip` 的问题，统一为规范化的 `txt/pdf/zip` 并增加不变量测试。
- 修复管理员从已锁定队伍移除成员后人数跌破最低要求仍保持 `locked` 的问题；成员增删统一推进 team revision，移除后无豁免则转为 `invalid`，补录达标或豁免可恢复。
- 补齐管理员个人资料编辑与登录人员入口；作业管理和新建作业入口继续由现有管理员页面与后端鉴权提供。
- 赛事归档只将 `locked` 队伍转为 `archived`，保留 `invalid` 与 `disqualified` 的历史资格结论；管理员队伍详情补齐赛题提交摘要。
- 修复学生导航中作业链接的 JSX 分支位置，并让管理员概览展示真实作业总数和未来 72 小时截止数量。
- 通用上传器保留浏览器 `PUT` 分片语义；真实验收中发现的首轮 MinIO 403 来自冒烟命令误用 POST，修正命令后 SigV4/Nginx/MinIO 链路通过。

### Operations
- 局域网 HTTP 幂等键兼容增量通过 14 个前端测试文件、40 项测试、ESLint、严格 TypeScript 及主机/容器生产构建；Frontend 已用新镜像替换并重启，Nginx 已重启，六服务健康。真实 Chromium 确认局域网地址 `isSecureContext=false`、`randomUUID=undefined`、`getRandomValues=function`，5000 端口作业编辑页为 200、发布 API 匿名探测为 401 而非 404。

- 经用户确认，在删除前生成并验证 PostgreSQL 17 自包含备份与 MinIO 三对象副本；维护窗口内单事务清理 20 个 Stage 4/Stage 5/Codex Smoke 账号及其全部业务树、24 条非目标 Outbox 和两个 Smoke 分类，随后删除已备份的 3 个 MinIO 对象。
- `yzhang367@connect.hkust-gz.edu.cn` 已持久化为唯一的已验证 `active admin`，旧 Session 全部撤销并写入两条维护审计；历史审计保留，已删除操作者外键按设计置空。
- 清理后通知、作业、赛事、队伍、提交、版本、评语、文件和 MinIO 对象均为 0；目标账号的 7 条历史验证邮件 Outbox 保留，非目标 Outbox 为 0。Alembic 保持 `20260825_0007`，六服务健康且 5000 健康链路为 200。
- 开发 `pnx-training` 已升级到 `20260825_0007`；Backend、Worker、Frontend 和 Nginx 使用根目录 `.env` 重建，六个常驻服务健康且仅 Nginx 映射 `0.0.0.0:5000`。运行镜像 ID 与新构建标签一致，Nginx/Backend ready/Worker 为 200，管理员页面守卫为 307，管理员会话 API 匿名访问为 401。
- 部署聚合检查发现当前数据库有 21 个账号（5 个 `admin`、16 个 `student`），所以 `0007` 按设计只推进迁移版本，没有改变角色、Session 或审计；未删除历史账号。
- 唯一账号增量通过 Ruff、136 个 Python 文件格式检查、100 个应用源文件严格 Mypy、130 个后端测试、ESLint、严格 TypeScript、36 个前端测试和 Next.js 生产构建。
- SMTP 连接、STARTTLS 和认证预检成功且未执行 `MAIL FROM/RCPT/DATA`；新 Worker 已加载最新 SMTP 环境。本次窗口只投递 1 条最新有效邮箱验证任务，15 条失效验证/重置任务全部转为 `dead/TOKEN_SUPERSEDED`，未创建额外邮件任务。
- 邮件恢复增量通过通知定向 8 项测试、Ruff、127 个 Python 文件格式、100 源文件严格 Mypy 和完整 127 项后端测试；六个常驻服务健康，仅 Nginx 映射 `0.0.0.0:5000`，Nginx/API 健康返回 200。
- 管理员权限补全增量通过 Ruff、135 个 Python 文件格式检查、100 个应用源文件严格 Mypy、128 个后端测试、ESLint、严格 TypeScript 和 36 个前端测试；`5000` 端口的 Backend live/ready、Worker、MinIO 与三项目标页面/API 注册复验通过，本次无数据库迁移。
- 本次仅重建并替换 Frontend；六个常驻服务健康，本机与局域网 `5000` 重发验证页面均为 200。回归与运行验收没有调用重发/重置 API，没有发送测试邮件。
- Backend、Worker、Frontend 已用新镜像重建；migrate 退出 0，六服务健康且仅 Nginx 映射 `0.0.0.0:5000`。隔离激活账号经局域网分别使用用户名和完整邮箱登录均为 200、返回同一用户，账号、Session、审计和临时秘密已清理。
- 部署方已确认校园 SMTP 配置完成；本次未通过真实邮件投递验证，既有待验证账号和 Outbox 状态未重新确认。
- 全新 PostgreSQL 17 空库完成 `base → 20260825_0006 → 20260825_0005 → 20260825_0006`；两个真实并发验证请求均返回 200，最终恰好一个管理员、一个学生、一条授予审计和两个已消费令牌；有 Connect 账号时危险降级明确失败并回滚。
- 现有 `pnx-training` 从 `20260825_0005` 升级到 `20260825_0006` 并重建 Backend、Worker、Frontend、Nginx；migrate 退出 0，六服务健康，仅 Nginx 映射 `0.0.0.0:5000`，本机和局域网登录页均为 200，真实旧域名注册返回 400、Connect 注册返回 201，虚构待验证账号及邮件任务随后精确清理。
- 最终通过 Ruff、132 文件格式、125 源文件严格 Mypy、112 个后端测试、ESLint、严格 TypeScript、30 个前端测试和 Next.js 生产构建；Playwright 三浏览器只读流程与 Chromium 注册写入通过。
- 全新空 PostgreSQL 卷完成 `base → 20260825_0005 → base → 20260825_0005`；发布 `pnx-release-20260825T013516Z` 迁移前后均为 head，固定 Alpine 镜像 HTTPS 冒烟通过。
- `127.0.0.1:5000` 与 `10.4.150.222:5000` 登录/健康入口复验为 200；六个阶段 6 隔离项目和 11 个临时数据卷已清理，`pnx-training` 未重启且六服务继续健康。
- 生产资源边界下 100 会话 2,000 次读取错误率 0%、P95 341.754 ms；20×100 MiB multipart 全部成功，近 2 GiB 单文件 127 片零错误。Backend 最终为 4 个 Uvicorn Worker、每进程数据库池 `8+4`、4 CPU/1 GiB。
- 完成 Frontend、Backend、Worker、PostgreSQL、MinIO 逐项故障注入与恢复；Worker 在停止后 321 秒准确转为 stale，其他组件的用户影响和 live/ready/独立存储状态符合设计。
- 真实生成周完整 `pnx-backup-20260825T004550Z-weekly` 和只携带 1 个/32 B 变化对象的日增量 `pnx-backup-20260825T004905Z-daily`；空项目链式恢复 RPO 31 秒、RTO 13 秒，数据库 2 条文件记录与 MinIO 2 个对象全量对账一致。
- 完成 `20260825_0005 → 20260824_0004 → 20260825_0005` 真实 PostgreSQL 迁移往返，最终为单一 `20260825_0005 (head)`；Ruff/格式、严格 Mypy、68 个后端测试、ESLint、严格 TypeScript、27 个前端测试和生产构建通过。
- 通过 `10.4.150.222:5000` 完成报名组队、并发一赛一队、Worker 锁队、管理员纠错/取消资格、MinIO 团队 multipart、成员/历史成员隐私、评语、下载、审计和归档冒烟；8 个临时账号全部禁用。
- 六个常驻 Compose 服务健康，只有 Nginx 映射 `0.0.0.0:5000`；开发库保留明确命名的 Stage 5 Smoke 赛事、队伍、提交和审计记录供追溯。
- 完成 `20260824_0003 → 20260824_0004 → 20260824_0003 → 20260824_0004` 真实 PostgreSQL 迁移往返，最终为单一 `20260824_0004 (head)`。
- Ruff、格式、严格 Mypy、59 个后端测试、ESLint、严格 TypeScript、20 个前端测试和 Next.js 生产构建全部通过；前后端镜像重建成功。
- 通过 `10.4.150.222:5000` 完成真实账号、CSRF、受众、多版本幂等、MinIO 上传/恢复/校验/下载、越权 404、评语隐私、优秀标记、延期、关闭拒绝和 Worker 自动状态推进。
- 六个常驻 Compose 服务健康，本项目仍只有 Nginx 映射 `0.0.0.0:5000`；冒烟学生账号已禁用、作业已归档。

## 2026-08-24

### Added

- 实现安全 Markdown 通知、全体/届次/方向并集与交集受众、草稿/定时/发布/置顶/归档状态，以及学生工作台、通知列表/详情和站内未读。
- 实现通知首次发布与更新提醒的逐学生站内记录、邮件 Outbox、定时发布 Worker 幂等和 SMTP 故障隔离；新增管理员通知、邮件任务、审计与概览页面。
- 实现通知附件所需的通用 MinIO multipart 基础能力：服务端对象键、预签名分片、恢复、连续分片校验、流式完整 SHA-256、文件签名检测、授权下载和终态/孤立对象清理。
- 新增可回滚的 `20260824_0003` 通知、站内提醒和上传迁移，以及阶段 4“作业、上传与私密评语”的实施准备。
- 实现学校邮箱注册与验证后直接激活、Argon2id、登录/退出、服务端 Session、CSRF、Session 管理、密码重置和认证限流。
- 实现管理员用户、角色、禁用/恢复、邮箱/资料/可选分类管理，届次/方向 CRUD、最后管理员保护、只读审计和交互式首个管理员命令。
- 实现认证邮件 Outbox、SMTP 双格式模板、锁租约、指数退避、dead 状态、错误脱敏、人工重试及 Worker 心跳并行运行。
- 实现真实认证页面、个人资料/Session、管理员用户与分类页面，以及集中浏览器 API/CSRF Client 和服务端鉴权 DAL。
- 新增可回滚的 `20260824_0002` 认证与基础数据迁移，以及阶段 3“通知与工作台”唯一正式计划。

### Security

- 一次性令牌数据库只存 SHA-256，Outbox 投递秘密使用独立 AES-GCM 密钥认证加密；管理 API、审计和错误摘要不返回明文或密文载荷。
- 生产配置强制 Secure `__Host-` Cookie 与强密钥，本地 HTTP 使用隔离 Cookie 名；Origin/Referer、CSRF、账号状态和角色均由后端强制。
- 最后一个激活管理员的禁用或降级请求返回 409，并在同一事务写入 denied 审计；禁用、重置、邮箱和角色敏感变化立即撤销 Session。

### Fixed

- 为 Nginx `map` 中两个包含 `{n}` 量词的请求 ID 正则补充引号，修复 Nginx 1.31 启动时 `unexpected "{"` 并持续重启的问题。

### Operations

- 在 Linux Docker 29.6.0、Docker Compose v5.1.4 环境完成固定前后端镜像构建；因主机既有 Docker Hub 镜像代理返回缺失 layer，使用可达代理拉取后按官方名称本地标记，未修改仓库镜像来源。
- 在空 PostgreSQL 17 数据卷完成 Alembic `upgrade head → downgrade base → upgrade head`，最终版本为 `20260823_0001 (head)`。
- 通过 `nginx -t`、登录页、存活、就绪、Worker 心跳、合法/非法请求 ID、最近严重错误日志和 Compose 端口隔离检查；Frontend、Backend、Worker、PostgreSQL、MinIO 与 Nginx 全部健康。
- 本机忽略的 `.env` 使用随机开发凭证和 `0600` 权限，只将 Nginx 发布到 `0.0.0.0:5000`；已通过 `127.0.0.1:5000` 与 `10.4.150.222:5000` 请求验证。

### Notes

- 宿主机另有不属于本项目的 Next.js 进程监听 3000，以及 `management-system-postgres-1` 发布 5432；本次未修改或停止这些外部服务。

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

## 2026-08-26

### Fixed

- 修复管理员切换学生视图后看不到已发布作业的问题：唯一管理员可能不在发布时生成的普通学生受众快照中，学生视图现按该账号当前技术方向执行服务端临时受众预览；历史届次资源仍按固定快照兼容读取，预览不改变受众、通知、邮件或统计数据。

## 2026-08-27

### Changed
- 通知、作业、校内赛及其它管理员页面统一复用 `AdminPageHeader`，返回入口、标题层级、说明和操作区使用同一布局。
- 管理员赛事入口改名为“校内赛”，首页只展示当前未归档校内赛和队伍列表，移除“新建赛事”操作；首次配置路由仅在没有当前赛事时可用。
- 保留归档赛事、历史赛题和旧 API 兼容，不删除数据库数据；服务层阻止已有未归档赛事时创建第二条赛事。

### Fixed
- 增加前后端回归，覆盖管理员校内赛队伍列表、无创建入口和重复校内赛 `409` 冲突。

## 2026-08-27：飞书培训知识库同步与阅读

### Added

- 新增 `KB-001～KB-008`：登录态培训文档阅读器支持目录树、标题搜索、URL 选文档、内部文档跳转、本文目录、移动抽屉及结构化块渲染。
- 新增管理员 `/admin/knowledge` 手动异步同步、脱敏运行状态和学生当前快照展示；同步写入 Outbox 并只由 Worker 访问飞书。
- 新增可回滚 `20260827_0011` 五表迁移，知识块存 JSONB，安全图片/白板/附件存 MinIO，资源下载验证当前成功快照引用。

### Security

- 飞书 API 固定 HTTPS 主机且拒绝重定向，凭证仅从环境/secret file 注入；链接、响应大小、分页、文件名、扩展名、媒体魔数和对象授权均受控。
- 不渲染飞书任意 HTML，不下发 tenant token、媒体 token、对象键或原始错误正文；失败同步不覆盖成功快照。

### Changed

- ADR-031 定向替代 ADR-002 的“完全不复制/同步飞书”部分；仍不修改、写回或依赖现有官网运行时，不增加公开知识库。
- 飞书部署配置与参考仓库统一为 `FEISHU_APP_ID`、`FEISHU_APP_SECRET`（或生产 secret file）和 `FEISHU_WIKI_URL`；URL 自动解析整个空间或单篇新版文档，不再要求独立 Space ID/Root Token。

### Validation

- 初版后端 179 项测试、Ruff、157 个 Python 文件格式检查和 144 个源文件严格 Mypy 通过。
- 初版前端 19 个测试文件/67 项测试、ESLint、严格 TypeScript 与 Next.js 生产构建通过；`/knowledge` 和 `/admin/knowledge` 均进入生产路由。
- 开发/生产 Compose 配置解析、Alembic 单 head、`0010 → 0011` 前滚 SQL 和 `0011 → 0010` 回滚 SQL 通过；部分唯一索引生成正确的 PostgreSQL 条件唯一索引。
- 三项真实配置的只读诊断成功：取得 tenant token 并读取整个空间 227 个目录节点，未输出凭证、token、Space ID 或飞书原始响应。

### Deployment

- 已完成 Backend、Worker、Frontend 镜像构建与容器替换；`20260827_0011` 迁移容器 `Exited (0)`，运行库为单一 head，六个常驻服务 healthy，四个健康端点均为 200。
- 首次迁移容器在导入模型前因新知识库源码 `0700/0600` 权限与镜像 root 属主组合而退出，数据库完整停留 `0010`；修正源码为标准 `0755/0644` 后重建成功，无半迁移数据。
- `/knowledge` 与 `/admin/knowledge` 匿名访问分别 307 到登录守卫，`/api/v1/knowledge` 匿名访问为 401。该初版部署阶段尚未执行首次完整同步；后续参考对齐运行已完成正文块、真实媒体和成功快照验收。

## 2026-08-27：飞书同步与知识库内容区参考对齐

### Changed

- 新增 ADR-032，以参考仓库提交 `c28f8a0` 固定同步顺序、块转换语义和内容区排布，替代自定义正文并发、单篇/子树跳过和自行设计的内容区布局。
- 桌面内容区当时固定为文档目录、位于正文左侧的本文目录和正文；删除“顶部文档切换栏”假设。移动端固定为右下目录按钮和包含搜索、文档树、本文目录的全屏目录。该历史页面顺序已由 2026-08-28 的 ADR-033 替代，同步契约继续有效。
- 保留本平台登录鉴权、`AppShell`、成功快照、PostgreSQL、MinIO、常规 Worker 和管理员 `POST /admin/knowledge/sync`，不复制参考官网公开静态运行时。

### Operations

- 早期前台初始化曾生成 228 个目录节点、212 个 Docx 目标、48 篇可读正文和 0 个首轮媒体的阶段性回退快照；该快照后续已被完整成功快照自然替代。
- 参考契约完整运行以 `succeeded` 完成 228 个目录节点、212 篇文档和 977 个成功媒体引用，耗时 `00:33:28.757715`；13 次允许的 asset fallback 未阻断快照。
- 恢复 Worker 后最新 `sync_knowledge` Outbox 为 `sent`、`attempt_count=1` 且无错误；管理员 `POST /admin/knowledge/sync` 继续作为后续更新入口。
- 部署方仍只填写 App ID、App Secret 和 Wiki URL；不新增参考仓库可选的 `FEISHU_DOCUMENT_ID`。

### Validation

- 测试契约新增 50 条目录分页、串行 DFS、500 条 blocks 分页、blocks→metadata 顺序、内联附件、350 ms 图片/附件队列、白板 PNG Accept 和精确媒体失败行为。
- 29 项后端知识库定向测试、完整后端 213 项测试、前端 20 个测试文件/76 项测试、Ruff、格式检查、严格 Mypy、ESLint、严格 TypeScript 和 Next.js 生产构建全部通过。
- Backend/Worker 镜像为 `sha256:f8c42b…`，Frontend 为 `sha256:e82d020…`；六服务 healthy，`live`、`ready`、`worker`、`nginx-health` 均为 200。
- `/knowledge`、`/admin/knowledge` 匿名访问均为 307，两个知识库 API 匿名访问均为 401；Alembic 保持 `20260827_0011`，本轮文档与实现对齐不涉及数据库迁移。


## 2026-08-28：知识库白色阅读主题与右侧本文目录

### Changed

- 新增 ADR-033：知识库阅读区改为白色主题；桌面顺序调整为左侧文档目录、正文、右侧本文目录。
- 成功打开当前或其他文档后左侧文档目录自动收起并保留展开按钮；单篇加载失败继续保留当前文档和目录状态，移动端全屏目录行为不变。
- ADR-032 的同步顺序、块转换、失败语义、管理员手动接口、Worker、成功快照和媒体授权继续有效；本轮无数据库迁移且不重新同步飞书。

### Validation

- 知识库定向 7 项组件测试、完整前端 20 个测试文件/76 项测试、ESLint、严格 TypeScript 和 Next.js 生产构建通过。
- 从已上线知识库隔离源码基线构建，差异仅为阅读器、块渲染器和知识库测试 3 个文件；镜像 `sha256:1842c4d…` 已替换 Frontend，Nginx 已重启，六服务 healthy，四个健康端点为 200，页面/API 匿名守卫保持 307/401。


## 2026-08-28：知识库主导航折叠、本文目录跟随与控件统一

### Changed

- 新增 ADR-034，澄清成功打开文档后收起的是系统最左侧主要导航；文档目录继续保持用户自己的展开/折叠状态，加载失败不改变两者。
- 右侧本文目录改为视口吸附、长目录内部滚动，并随页面滚动以 `aria-current="location"` 高亮当前章节；移除会阻断 sticky 的祖先 overflow。
- 文档目录、搜索框、目录标题栏、目录行、展开/收起按钮和移动端目录弹层改用系统全局令牌、圆角、边框、阴影、悬停与焦点样式。

### Validation

- 知识库定向 8 项测试、完整前端 20 个测试文件/77 项测试、ESLint、严格 TypeScript 和 Next.js 生产构建通过。
- 本轮只涉及 Frontend，不触发飞书同步，不修改管理员手动接口、Worker、Backend 或数据库。
- 隔离构建差异只有共享主导航、主导航折叠事件、知识库阅读器和知识库测试；Frontend `sha256:2ad76bd…` 已上线，六服务 healthy，四个健康端点 200，页面/API 匿名守卫 307/401。


## 2026-08-28：意向调查创建外键顺序修复

### Fixed

- 修复管理员创建带选项的意向调查返回 500：父调查加入 Session 后先执行 `flush()`，再写入选项，避免 `intention_options.survey_id` 在父记录落库前触发外键约束。
- 父调查和全部选项仍处于同一事务，任一步失败都会整体回滚；不增加重复写入路径，不改变 API、Schema、数据库结构或迁移。

### Testing

- 创建回归新增 `survey → flush → option → option → commit` 严格顺序断言；意向调查定向 10 项、隔离源码完整后端测试、Ruff、146 个 Python 文件格式检查和 146 个源文件严格 Mypy 通过。
- 使用真实运行 PostgreSQL 完成多选调查与两个选项的事务冒烟，随后回滚外层事务；调查与审计测试记录均为 0，无数据残留。

### Operations

- 从当前 HEAD 隔离叠加本次两个代码文件构建，未纳入并行账号活跃度/清理改动；Backend 和 Worker 已统一部署镜像 `sha256:409a55ff76ad6d75e03c20c254f042f6424a60c99a649363ed3d06b8bc1b3d69`。
- 六个 Compose 服务均 healthy，`live`、`ready`、`worker`、`nginx-health` 均为 200；Alembic 为 `20260827_0011 (head)`，最近 Backend/Worker 日志无新异常。


## 2026-08-28：意向调查升级为多题实名问卷

### Added

- 问卷支持 1～30 道必答单选/多选题，管理员可动态增加/删除“第一志愿、第二志愿”等题目，并把每人提交上限设为 1～100 次或不限。
- 新增仅真实管理员可访问的实名提交名单，展示姓名、学号、学校邮箱、最新分题答案、补充说明、累计提交次数和最后提交时间；原统计升级为按题目分组。
- 新增可回滚 `20260828_0013`：创建 `intention_questions`，增加 `max_submissions`/`submission_count`，把旧单题调查、选项和回答原位迁移为兼容问卷。

### Changed

- 学生与管理员界面统一称“问卷”；兼容保留 `/intentions` 路由和内部表前缀，旧二维码与站内链接不失效。
- 每次成功提交覆盖本人最新答案并消耗一次提交次数；达到上限后学生表单只读，服务端返回 `INTENTION_SUBMISSION_LIMIT_REACHED`。
- ADR-035 部分替代 ADR-028 的单题、无限改答和仅匿名汇总决策；二维码哈希、登录要求、状态机和本人读取边界继续有效。

### Security

- 学生接口仍只返回本人最新答案；实名名单路由复用真实管理员守卫，管理员学生视图也不能读取。
- 问卷答案和补充说明不得进入日志、分析或审计详情；提交审计只保留问卷 UUID 和累计次数。

### Validation

- 完整后端 218 项、完整前端 20 文件/79 项测试通过；前端 ESLint、严格 TypeScript 和 Next.js 生产构建通过，问卷定向 Ruff、格式检查和 7 个源/测试文件严格 Mypy 通过。
- `0012 → 0013` 与 `0013 → 0012` 离线 PostgreSQL DDL 成功生成；初轮交付时 Docker socket 权限尚未生效，运行库应用和真实 PostgreSQL 往返随后单独完成。
- 完整后端 Ruff/Mypy 被工作树既有账号清理改动的 `backend/app/users/service.py:215` 未定义 `payload` 阻塞，完整格式检查只额外命中同组既有未格式化文件；本轮未改动该逻辑。

## 2026-08-28：管理员角色按钮无请求修复

### Fixed

- 修复用户管理页通过 `FormData(form)` 读取提交按钮值导致角色、禁用和恢复分支全部静默跳过的问题。
- 现在从原生 `SubmitEvent.submitter` 读取实际点击按钮；高风险原因仍由表单字段读取，后端 CSRF、管理员鉴权、审计和最后管理员保护保持不变。

### Testing

- 新增“设为管理员”回归，断言点击后调用 `POST /admin/users/{id}/role`，请求体为目标角色与操作原因，成功响应后界面更新为管理员。
- 工作树账号管理定向 7 项、完整前端 20 文件/79 项、ESLint、严格 TypeScript、Next.js 生产构建通过。
- 从干净运行基线隔离生成的热修源码通过完整前端 19 文件/71 项、ESLint、严格 TypeScript 和容器生产构建。

### Operations

- Frontend 已替换为只含本次修复的隔离镜像 `sha256:f9cc27716b81325ee43ae144c235f8be7c33f18ba89e3d5f8c20c120b7900132`；并行账号清理和问卷改造未纳入运行镜像。
- Nginx 继续映射主机 5000 端口；六个常驻服务 healthy，`live`、`ready`、`worker`、`nginx-health` 均为 200，`/admin/users` 匿名访问为 307。
- 上线后的真实管理员页面已完成两次角色变更、一次禁用和一次恢复，四次对应 API 写请求均返回 200。
- Alembic 保持 `20260827_0011 (head)`；本次未修改 Backend、Worker、API、数据库、迁移或现有用户数据。

## 2026-08-28：账号状态标签 UI 优化

### Changed

- 管理员用户卡片不再展示 `active`、`pending_email`、`disabled` 英文数据库枚举，分别改为“正常”“待验证”“已禁用”。
- 状态标签采用圆角胶囊、浅色语义背景、边框、状态圆点与中文文字；角色标签采用独立低饱和蓝灰样式，避免与账号状态争夺层级。
- 超过十天未进入提示改为带时钟图标的“X 天未登录”；搜索支持中文角色和账号状态名称。

### Testing

- 新增三种状态中文呈现、胶囊样式、英文枚举不渲染和“已禁用”中文搜索回归。
- 工作树账号管理定向 8 项、完整前端 20 文件/80 项、ESLint、严格 TypeScript 和 Next.js 生产构建通过。
- 隔离运行基线完整前端 20 文件/72 项、最终定向回归、ESLint、严格 TypeScript 与容器生产构建通过。

### Operations

- 从干净运行基线叠加角色按钮修复与本轮状态 UI 构建，未纳入并行账号清理和问卷改造；Frontend 运行镜像为 `sha256:4ebd888cf8df782f971356c79650ee866235f92021f193c4fad40ab55d63c4e1`。
- 运行生产包已确认包含新的“待验证”文案；六服务 healthy，`live`、`ready`、`worker`、`nginx-health` 均为 200，Nginx 继续映射主机 5000 端口，`/admin/users` 匿名访问为 307。
- Alembic 保持 `20260827_0011 (head)`；未修改 Backend、Worker、API、权限、数据库、迁移或用户数据。

## 2026-08-28：分提交整理、完整质量门与并发探测

### Fixed

- 修复账号清理工作树中 `restore_user()` 误引用不存在的 `payload`；邮箱变更前的 Session 锁恢复到 `patch_user()`，不改变账号清理产品规则。
- 按后端账号、后端问卷、前端交互和权威记录拆分提交，保持 Alembic `0011 → 0012 → 0013` 单一迁移链。

### Commits

- `b328035 feat(accounts): track inactivity and protect cleanup`
- `2468f05 feat(questionnaires): support multi-question submissions`
- `86a90c4 feat(frontend): add account activity and questionnaire flows`

### Validation

- Ruff、161 文件格式检查、146 个源文件严格 Mypy、218 项完整后端测试通过；Alembic 单一源码 head 为 `20260828_0013`。
- 前端 ESLint、严格 TypeScript、20 个测试文件/80 项测试和 Next.js 生产构建通过。
- 100 并发、10 轮、5,000 次无写入混合探测错误率 0%，持续 4.077 秒、吞吐 1,226.374 req/s，总体 P95 286.163 ms；探测后 `live`、`ready`、`worker` 和 `nginx-health` 均为 200。

### Limits

- Docker 授权前未执行 300 账号/100 独立登录 Session 的正式 NFR-T03 场景、20 路 multipart 或 `0011 ↔ 0012 ↔ 0013` 真实 PostgreSQL 往返；后续已补充 100 账号登录突发诊断和迁移往返，但正式业务读取与 multipart 仍未由这些结果替代。
- 运行 Compose 仍为 `20260827_0011` 的隔离热修版本；未部署本批提交、未应用迁移、未执行账号删除，也未写入容量数据。

## 2026-08-28：账号活跃度与多题实名问卷部署

### Deployed

- Backend/Worker 已切换到 `sha256:8253599…`，Frontend 已切换到 `sha256:1252a679…`；本地 Compose 固定标签为 `questionnaire-account-20260828`。
- PostgreSQL 已从 `20260827_0011` 升级到 `20260828_0013`，同时应用账号活动字段/受众外键 `0012` 与多题问卷 `0013`；没有自动删除账号。
- 旧单题调查已迁为一题问卷，原 3 个选项、2 份回答和 2 条选择关系保留；管理员实名名单、分题统计和提交次数限制进入运行态。

### Validation

- PostgreSQL 17 迁移前备份完成并校验；生产副本隔离往返 `0011 → 0012 → 0013 → 0012 → 0013` 通过，Alembic 无模型漂移。
- 六服务 healthy，四个健康端点 200，页面匿名守卫 307，学生/管理员问卷及实名名单 API 匿名访问 401；新服务最近日志无错误。
- 最近知识库快照保持 212 篇文档和 986 个媒体引用，最新同步 Outbox 仍为 `sent/1`，未触发飞书同步。
## 2026-08-28：高并发、局域网安全与 Docker 版本收敛

- Nginx 认证限流拒绝从默认 503 改为 429；保留真实来源 IP 的 5r/s、burst 20 和后端账号/IP 失败登录限制。
- 新增 infra/performance/login_burst.py，read_load.py 支持独立 Origin；多来源隔离登录 100/200/300 账号均 0 错误，100 Session/2,000 次读取 P95 331.674 ms、错误率 0%。
- 本机入口安全探测、Gitleaks 通过；Trivy 发现 Backend Alpine 的 4 个上游 CVE，记录为后续基础镜像升级项。
- 删除 PNX 已退出迁移容器和旧应用镜像标签，保留当前/回滚镜像、运行卷和备份；未执行全局 Docker prune。

## 2026-08-28：问卷内容查看、草稿编辑与部署

### Added

- 新增 `GET /admin/intentions/{survey_id}`，真实管理员可查看任意状态问卷的说明、时间窗口、提交限制、revision 及完整问题/选项，不返回个人答案。
- 管理页新增“查看内容”；草稿新增完整编辑表单，可修改标题、Markdown 说明、时间窗口、提交上限和题目结构，保存后立即刷新可见内容。

### Changed

- `PATCH /admin/intentions/{survey_id}` 仅接受 `draft` 与匹配 revision，在同一事务删除旧问题并重建有序问题/选项；成功返回刷新后的完整详情。开放、关闭、归档问卷继续只读。
- 完整管理详情和修改继续使用真实管理员依赖，学生及管理员学生视图均为 403；审计不记录问卷回答或二维码 token。

### Validation and deployment

- 完整后端 230 项、前端 20 文件/82 项及全部静态质量门、Next.js 生产构建通过；无数据库迁移，Alembic 保持 `20260828_0013`。
- Backend/Worker 部署为 `sha256:06eb68d3…`，Frontend 部署为 `sha256:a5d9264a…`，固定标签均为 `questionnaire-edit-20260828`；六服务 healthy，四健康端点 200。
- 部署前备份 `/tmp/pnx-training-before-questionnaire-edit-20260828T145330Z.dump` 为 PostgreSQL 17 自定义格式，大小 4,145,718 字节、权限 0600、SHA-256 `f089b9425488a48f4fa2d3b34744ab9423d86a00255b17c26c23caef373d08bf`。
- 问卷数据关系和知识库最近成功快照保持不变，未触发飞书同步。首次 Compose 未显式加载 `.env` 生成的未使用 `dev` 标签已删除；首次固定镜像的源码权限问题已恢复为 0644、重建并完成最终健康验收。

## 2026-08-29：分批提交、统一发布与 Docker 精确清理

### Commits

- `5b642a2 feat(questionnaires): add admin detail and draft editing`
- `84718d4 feat(notifications): categorize student unread badges`
- `059d87a feat(help): add private requests and resolved answers`
- `c1e7259 docs: align questionnaire help and notification contracts`
- `634e01a docs(ops): record questionnaire help and badge deployments`

### Release and validation

- Backend 通过 Ruff、169 个 Python 文件格式检查、120 个源文件严格 Mypy、246 项 Pytest；Frontend 通过 ESLint、严格 TypeScript、22 个文件/90 项 Vitest以及主机和容器内 Next.js 生产构建。
- Alembic 源码只有 `20260828_0014` 一个 head，运行库为 `20260828_0014 (head)`，`alembic check` 无模型漂移；候选 Backend 以 `appuser` 导入成功，OpenAPI 共 113 个路径。
- 发布前备份 `/tmp/pnx-training-before-release-634e01a-20260829T042700Z.dump` 为 PostgreSQL 17 自定义格式，大小 4,153,800 字节、权限 0600、SHA-256 `bb4ad5f713aa1d605e6cffac23903471d48a49dd66f1085bfb6660425cd78caa`，容器内 `pg_restore --list` 校验通过。
- `.env` 固定 `APP_IMAGE_TAG=release-634e01a-20260829`；Backend/Worker 使用 `sha256:c7ccb9bd1249354d0ad5b059560bd90f34a69f6e22bd45058e6e65f132b8cea9`，Frontend 使用 `sha256:76266bc260527c7131af364c97ed2f801769b8a3ef5e111cb0dff642bf033c46`，应用容器均为 `appuser`。
- 按 Backend/Worker、Frontend/Nginx 顺序替换后六服务 healthy、重启次数为 0；登录页、四个健康端点和 Nginx 健康端点为 200，受保护页面匿名访问为 307，公开答疑、管理答疑和 Dashboard API 匿名访问为 401，近期日志无严重错误匹配。
- 发布前后用户/问卷/问题/选项/回答/选择关系/工单/已解决公开问题/知识文档/媒体计数均为 `6/2/3/11/2/2/1/1/212/986`；未触发邮件、飞书同步、账号删除或上传。

### Cleanup and limits

- 删除 1 个旧 `pnx-training-migrate-1` 容器、10 个旧 PNX 应用标签和 9 个旧镜像 ID；无 dangling 镜像，镜像占用由 7.76 GB 降至 7.05 GB。
- 仅保留当前 `release-634e01a-20260829` 与回滚 `notification-badges-20260829` 两组 PNX 应用镜像；保留 PostgreSQL/MinIO 运行卷、三个 PNX 网络、发布前备份、其他 `management-system` 项目、4 个来源不明匿名卷和全局 BuildKit 缓存，未执行全局 prune。
- 本轮无新迁移或业务写入；提交仅在本地，未 push、未创建外部 Release。`/tmp` 备份如需跨主机重启长期保留，仍须转移到受控持久介质。
- Docker 操作期间临时添加的 socket 命名 ACL `user:pnx:rw-` 已由用户通过交互式 sudo 撤销；最终复核只剩基础 owner/group/mask/other 条目，socket 为 `root:docker`、`0660`，权限收尾完成。

## 2026-08-29：修复飞书同步 LaTeX 公式解析

### Fixed

- 飞书普通富文本中的 `equation.content` 不再降为无类型字符串，`block_type=16` 独立公式块不再被未知容器路径丢弃；同步后的 JSONB 分别保留行内公式标记和独立 `equation` 块。
- 知识库阅读器使用本地 KaTeX 区分行内与独立公式，支持反斜杠命令、上下标、积分、分式和根式；语法错误回退显示可读 LaTeX 源文，不中断整篇文档。

### Security

- KaTeX 设置 `trust=false`、宏展开与尺寸上限，并把 HTML 扩展作为硬错误；飞书不受信 HTML 不进入公式渲染，插入 DOM 的标记只来自受限的本地 KaTeX 生成器。

### Validation

- 30 项后端知识库测试、受影响后端文件 Ruff/格式/严格 Mypy、前端知识库 8 项、完整 23 文件/99 项 Vitest、ESLint、严格 TypeScript 与 Next.js 生产构建通过；新增 `katex@0.16.22` 安装审计为 0 漏洞。
- 隔离 Frontend 候选再次通过知识库 8 项测试、Next.js 生产构建和 0 漏洞安装审计；Backend 候选在镜像内通过公式规范化断言，保留注册唯一约束修复哈希且 Alembic 源码仍为 `20260828_0014`。

### Deployed

- 固定标签 `feishu-latex-20260829` 已上线：Backend/Worker 镜像为 `sha256:5e7b335da4fc…`，Frontend 为 `sha256:6076084d5de5…`，应用容器均以 `appuser` 运行。
- 六服务 healthy、重启次数 0；登录页和四健康端点为 200，知识库页面匿名 307、两个知识库 API 匿名 401，启动窗口日志无权限、事务或上游异常。
- Alembic 保持 `20260828_0014 (head)`，未启动 migrate；部署前后业务计数保持 `155/3/5/21/84/166/1/1/2/1/1/2`，最近成功知识库保持 `succeeded/212/986`，最新同步 Outbox 保持 `sent/1`。
- 部署前 PostgreSQL 17 备份为 `/tmp/pnx-training-before-feishu-latex-20260829T112100Z.dump`，大小 4,330,074 字节、0600，SHA-256 `b53cea2fd8927f4ce4f8aaca1b8a8bc759a1c508ac2db18208887f7a0c8b31a0`，同版本 `pg_restore --list` 校验通过。
- 本轮无 API、鉴权、Schema 或迁移变化，未触发真实飞书同步、邮件、上传或账号删除。旧成功快照不会原地改写，仍需真实管理员手动同步一次。
- 本次临时 Frontend 测试镜像与隔离目录已删除，运行/回滚镜像和备份保留；Docker socket 的 `user:pnx:rw-` ACL 因宿主机要求交互式 sudo 尚未撤销，需部署方执行 `sudo setfacl -x u:pnx /var/run/docker.sock` 后复核。

## 2026-08-29：部署管理员永久删除账号与用户自助注销

### Added

- 上线 `DELETE /admin/users/{user_id}` 与 `DELETE /auth/account`；两条路径均重新验证当前密码和确认邮箱，管理员路径另要求内部原因与 PostgreSQL + MinIO 备份确认，成功返回 204。
- 账号个人数据在 PostgreSQL 单事务级联清理，共享平台/团队记录使用 SET NULL 去除归属；个人对象通过可靠 `delete_account_object` Outbox 在 Worker 中终止 multipart 后幂等删除。

### Fixed

- `20260829_0015` 的显式检查/外键名称统一使用 `op.f(...)`，避免 Alembic 命名约定二次展开；首次隔离失败升级由事务完整回滚，修正后完成 `0014 → 0015 → 0014 → 0015`。
- 对象完整备份允许服务端生成的 `objects/` 与 `knowledge/` 两类前缀；存储对账把 `knowledge_assets` 纳入数据库引用集合。恢复仍硬拒绝引用缺失、大小或 SHA-256 不符，只对孤立对象计数告警且绝不自动删除。

### Backup and validation

- OpenPGP 周完整备份 `pnx-backup-20260829T122839Z-weekly` 为 1,979,581,142 字节、0600，SHA-256 `a68bdd8a847a419a2d092730362a6277453bcb6cf67614c76a784d817bd85bdb`；PostgreSQL dump 5,569,892 字节并通过 314 项 `pg_restore --list`，MinIO 清单为 2,885 个对象/2,038,164,595 字节。
- 从空隔离环境恢复成功，RTO 79 秒；1,010 个数据库引用对象无缺失/大小/哈希不符，1,875 个历史孤立知识库对象保留并报告。普通正式版本 DELETE 仍返回 SQLSTATE `55000`。

### Deployed and remaining risks

- 固定标签 `account-deletion-20260829` 已上线；Backend/Worker 镜像为 `sha256:081be7ba08de49781ab40d3e3053c45910ca34078901935c28638135f8846c81`，Frontend 为 `sha256:d4b5172a1a780f2f4db63db2f65a80e881669c4ec7c3b0dc09632b3d620bd2f4`，应用均以 `appuser` 运行。
- 生产 Alembic 为 `20260829_0015 (head)`；六服务 healthy、重启次数 0，登录和四健康端点为 200，`/profile`、`/admin/users` 匿名为 307，两条账号 DELETE API 匿名为 401。
- 部署前后用户/问卷/问题/选项/回答/选择关系/工单/已解决问题/通知/作业/提交/版本保持 `155/3/5/21/84/166/1/1/4/1/1/2`，最近成功知识库为 `succeeded/213/1006`。部署没有携带认证信息调用真实账号 DELETE，账号清理 Outbox 为 0。
- 加密归档、校验材料和临时 GPG 密钥环仍位于本机 `/tmp`，不等同于异机持久备份，必须迁移到受控独立介质并将归档与解密材料分离保存；Docker socket 临时 `user:pnx:rw-` ACL 仍待撤销和复核。

## 2026-08-29：部署管理员删除反馈答疑

### Added

- 新增真实管理员 `DELETE /admin/help-requests/{request_id}`；系统反馈和问题答疑不受 open/resolved 状态限制，行锁事务物理删除并返回无正文 204。
- 删除前把目标工单未读解决提醒标为已读，保留历史已读提醒和只追加审计；审计不记录标题、正文、答复或学生身份。管理员详情新增区分类型的二次确认入口。

### Validation and backup

- 后端定向 27 项与完整 280 项 Pytest、Ruff、170 文件格式和 153 源文件严格 Mypy 通过；前端 23 文件/102 项 Vitest、ESLint、严格 TypeScript、主机及容器生产构建通过，容器依赖安装审计 0 漏洞。
- 部署前 PostgreSQL 17 自定义格式快照 `/tmp/pnx-training-before-help-delete-20260829T141903Z.dump` 为 5,571,302 字节、0600、SHA-256 `40cfce14391d4e135a3d30a6c786be81df494a69affe9a56dbceb445df49bbd0`，`pg_restore --list` 314 项通过。

### Deployed

- 固定标签 `help-delete-20260829` 已上线；Backend/Worker 镜像为 `sha256:1a2f7c6e3d7145653dcccb076c098fe544e854bcf29b6cede5ee9b5218fdc799`，Frontend 为 `sha256:2f7ef180f2c2da20eb39e6c723c45de5b8871e62b5e000bf5b53d60decd3b110`，应用均以 `appuser` 运行。
- 六服务 healthy、重启次数 0；登录和四健康端点 200，学生/管理员答疑页面匿名 307，答疑 DELETE 匿名 401。运行 OpenAPI 共 114 个路径，同时保留账号删除并新增答疑 DELETE/204 无正文。
- Alembic 保持 `20260829_0015 (head)`，本轮无迁移；部署前后聚合保持 `155/3/5/21/85/169/1/1/2/1/1/2/897/1010/0`，最近知识库为 `succeeded/213/1006`，账号对象清理 Outbox 为 0。
- 首次替换命令未显式传入根 `.env`，Compose 临时解析为 `:dev` 且飞书 URL 为空；未通过健康门、未继续 Frontend，随后以 `--env-file .env` 立即重建 Backend/Worker 并恢复健康。PostgreSQL/MinIO 未重建，数据聚合无变化。
- 本轮未携带认证调用真实答疑或账号 DELETE，未触发飞书同步、上传或其他业务写接口；应用回滚可切回 `account-deletion-20260829` 且数据库保持 `0015`，已经物理删除的工单不能由应用回滚恢复。

## 2026-08-30：部署管理员用户全量搜索与分页修复

### Fixed

- 管理员用户页不再只加载前 100 个账号后本地搜索，改为受管理员鉴权的服务端全量搜索和固定每页 20 条分页；空搜索可逐页查看全部账号。
- 搜索覆盖姓名、邮箱、学号、中文/英文角色与状态，`%`、`_` 和反斜杠按普通文本处理；`search/activity/page` 保留在 URL，越界页回到实际末页。
- 用户资料、角色、状态或删除写入成功后按相同服务端查询刷新，避免筛选残留、分页 OFFSET 跳项和末页收缩错误；既有账号删除确认、审计及最后管理员保护不变。

### Backup and isolation

- 发布前生成 OpenPGP 加密备份 `pnx-backup-20260829T155430Z-daily`：归档 5,679,123 字节、0600，SHA-256 为 `525a53cef7bb08676b31598e9978a67a45df1301ca558587591e8e57438c2e4b`；完整 PostgreSQL dump 为 5,574,189 字节，外层/内部校验与 PostgreSQL 17 `pg_restore --list` 通过。
- MinIO 采用相对 `pnx-backup-20260829T122839Z-weekly` 的增量清单，2,885 个对象无新增、修改或删除；完整周备份、每日归档、状态清单和临时 GPG 密钥环均保留。
- Backend 以运行 `help-delete-20260829` 镜像为底只叠加两个 users 文件；Frontend 从 Git 发布基线叠加已上线能力与本次搜索文件，编译产物明确不含仍未部署的“删除队伍”。

### Deployed and safety validation

- 固定标签 `admin-user-search-20260829` 已上线；Backend/Worker 镜像为 `sha256:8ce5a025653e05eeb2a42119cf0c20b4c258b76a82a39c8abeb24be607388880`，Frontend 为 `sha256:005345c40946bc33826565aebc8b441bc5f0600778384618042e6d885bec7be8`，应用容器均以 `appuser` 运行。
- 六服务 healthy、重启 0；登录与四健康端点 200，管理员用户页匿名 307、用户列表 API 匿名 401。运行静态 OpenAPI 共 114 个路径，页码最大值 10000，既有账号/答疑删除接口继续存在。
- 部署未运行 migrate，PostgreSQL/MinIO 容器和数据卷未重建；没有使用管理员 Session、Cookie 或真实账号读取用户列表，也未调用删除、同步、上传、认证或其他业务写接口。四个应用容器启动日志错误关键词计数均为 0。
- 回滚只需恢复 `help-delete-20260829` 固定标签并定向替换四个应用服务，数据库保持既有 `20260829_0015` 基线；本机 `/tmp` 备份仍须迁移至受控独立介质。

## 2026-08-30：部署管理员删除队伍

- 以运行中的 `help-delete-20260829` 为基线构造隔离候选，只叠加队伍删除；明确排除共享工作树中的管理员用户搜索/分页源码。隔离前端 23 文件/102 项、ESLint、严格 TypeScript 和镜像内默认生产构建通过。
- 部署前 PostgreSQL 快照 `/tmp/pnx-training-before-team-delete-20260829T161603Z.dump` 为 5,574,204 字节、0600，SHA-256 `1ebc990cbec3023a54a4fe6672a37d446af2608efb09dc5f4135786866b1a301`，PostgreSQL 17 目录校验通过。
- 固定标签 `team-delete-20260830` 已上线；Backend/Worker 镜像为 `sha256:2d58004f482cefa3e01a3bd24877074fb72f496b8e9f3f067b484fcaf21efe97`，Frontend 为 `sha256:78fd991ced0d9fd308eba17c74cea4bd939fae78332d290aa1201610ee016015`，应用均为 `appuser`。
- 发布运行无变更 migrate 并按 Backend/Worker、Frontend、Nginx 顺序替换；PostgreSQL/MinIO 容器和数据卷未重建，Alembic 保持 `20260829_0015 (head)`。
- 六服务 healthy、重启 0；登录与四健康端点 200，匿名队伍 DELETE 401。OpenAPI 在既有队伍路径新增 DELETE/204；部署前后十项业务聚合完全一致，应用日志无异常。
- 验收未携带认证调用真实 DELETE，未触发飞书同步、上传或邮件写入。临时隔离候选已清理，备份与当前/回滚镜像保留。
- Docker socket 临时 `user:pnx:rw-` ACL 撤销尝试因 `sudo -n` 需要密码失败，仍需部署方交互执行 `sudo setfacl -x u:pnx /var/run/docker.sock` 并复核基础 ACL。

## 2026-08-30：纠正队伍删除发布造成的用户搜索回退

### Fixed

- 后续 `team-delete-20260830` 从旧 `help-delete-20260829` 基线构建并明确排除用户搜索，覆盖了已上线的 Backend 搜索和 Frontend 分页；运行 chunk 因此恢复为 `pageSize=100` 且不传 `page/search`，直接造成管理员仍只能查看/搜索前 100 个账号。
- 新合并候选以队伍删除 Backend 为底叠加两个 users 文件，并无缓存重建同时包含全部已上线功能、队伍删除与用户搜索的 Frontend；不回滚任何删除、公式、通知或作业能力。

### Validation and deployed

- 构建上下文逐文件 `cmp`，页大小、查询参数、搜索界面和队伍删除源码断言通过；`npm ci` 审计 499 个包、0 漏洞，Next.js 生产构建成功。
- 候选及最终运行编译 chunk 均确认 `pageSize:20`、`page/search`、“搜索用户”“下一页”“删除队伍”同时存在；Backend 静态 OpenAPI 为 114 个路径并保留队伍/账号/答疑 DELETE。
- 固定标签 `team-user-search-20260830` 已上线；Backend/Worker 镜像为 `sha256:0a3a88a7aeabed366b708695c867f0ee3bb6077bce05e441a8ed6fbc5041d2e3`，Frontend 为 `sha256:10552d3e6b750557e05d27527e06cac992091d7f80850f19c7a270a220d632f3`。六服务 healthy、重启 0，五个健康入口 200，匿名管理员用户页/API 为 307/401。
- 本次未运行 migrate，PostgreSQL/MinIO 与数据卷未重建；只复核既有队伍部署前备份文件的权限、SHA-256 和目录，没有再次读取生产业务数据。未使用管理员登录态、未读取用户列表、未调用业务写接口，应用日志错误关键词为 0。

## 2026-08-30：部署持久登录与同源 IP 绑定

### Added

- 上线默认关闭的“记住登录状态”：普通登录使用浏览器会话 Cookie，主动勾选后 Session/CSRF Cookie 最长 30 天，并要求有效高熵 Cookie 与登录时精确来源 IP 的 HMAC 绑定同时匹配；不保存密码或精确 IP。
- `sessions.ip_binding_hash` 通过可回滚 `20260830_0016` 上线，历史 Session 保持 NULL；会话列表公开 `remembered` 状态。Backend Dockerfile 复制应用与迁移时改由 `appuser:appgroup` 持有，避免宿主机 umask 让非 root 镜像不可读。

### Backup and migration

- OpenPGP 每日备份 `pnx-backup-20260830T045545Z-daily` 为 5,682,620 字节，PostgreSQL dump 为 5,578,815 字节；外层/内部校验、Manifest 和 PostgreSQL 17 的 299 项目录均通过。MinIO 2,885 个对象相对周基线无 payload 或删除变化。
- 全新隔离 PostgreSQL 完成 `0015 → 0016 → 0015 → 0016`，字段类型、可空性、降级移除及 `alembic check` 均通过；业务表行数聚合哈希前后一致，临时容器、网络、卷和明文目录已清理。
- 生产只执行一次 `0015 → 0016`，全表行数聚合哈希保持 `6a44c75dea0d9e822c8ea06169f8c76d6a529a249ad1e33644dad20d53274c05`；PostgreSQL/MinIO 容器与数据卷未重建。

### Deployed and validation

- 固定标签 `persistent-login-20260830` 已上线；Backend/Worker 镜像为 `sha256:6851f9892b16bfb6f2b4436dceba8b58b93651163882226770fc5339b91e6dc3`，Frontend 为 `sha256:96544dc22467f4ba4b74d236d9474bc1bfeb50b133c89cb695aa9cc3bf72424b`，应用均以 `appuser` 运行。
- 六服务 healthy、重启 0；五个健康入口为 200，匿名会话管理页/API 为 307/401。运行 OpenAPI 的 `remember_me` 默认 false，Session 含 boolean `remembered`，Alembic 为 `20260830_0016 (head)` 且无漂移。
- 部署未使用生产账号、Session 或 Cookie，也未调用登录、删除、同步、上传或其他业务写接口；新验收窗口日志无事务、权限、连接或未处理异常。
- 旧合并镜像保留用于应用回滚，但旧 Backend 不执行 IP 绑定校验，应优先前滚或先撤销持久 Session。加密备份与临时私钥仍需迁往独立介质；Docker socket ACL 因交互式 sudo 要求尚未撤销。

## 2026-08-30：修复持久登录跳转后立即失效

### Fixed

- 登录 POST 经 Nginx 直达 Backend 并绑定真实来源 IP，而跳转后的 Next.js Server Component 原先只转发 Cookie，Backend 看到 Frontend 容器 IP 后把持久 Session 误判为换网并立即撤销；这也是“不勾选可进入、勾选仍停留登录页”的根因。
- 服务端 API Client 现同时转发当前 Cookie 与 Nginx 已覆盖的单值 `X-Forwarded-For`，缺失来源头时不自行伪造。Nginx 仍覆盖客户端伪造头，Frontend 不发布宿主端口，认证安全边界未放宽。

### Validation and deployed

- 新增服务端转发回归；定向 2 文件/11 项与完整 24 文件/107 项 Vitest、ESLint、严格 TypeScript、主机及镜像内 Next.js 生产构建全部通过。隔离假 Backend 确认 `/auth/me`、`/dashboard` 收到同一假 Cookie 与来源 IP，临时资源已清理。
- `.env` 固定 `persistent-login-ip-forwarding-20260830`，Frontend 镜像更新为 `sha256:77dbfdec8659b82308eb159f2e48cdb2cb217974731eb4e080d4b83ffda90734`；仅替换 Frontend/Nginx，Backend/Worker 仍为 `sha256:6851f9892b16bfb6f2b4436dceba8b58b93651163882226770fc5339b91e6dc3`。本轮无迁移，PostgreSQL/MinIO 未重建。
- 六服务 healthy、重启 0，五健康入口 200，匿名会话页/API 为 307/401，运行 Frontend 产物包含 `x-forwarded-for`，新日志窗口无异常。此前已被误判撤销的持久 Session 需要用户重新勾选登录一次。

## 2026-08-30：关闭学生知识库飞书原文入口并保留附件下载

### Changed

- 新增 ADR-046；`/knowledge` 以当前 Session 的有效视图区分飞书来源入口。真实学生与管理员学生视图不再显示标题下的“在飞书中打开原文”，真实管理员普通视图保留排障入口。
- 学生侧未映射飞书文档 URL 只显示文本，显式映射到当前成功快照的内部文档 mention 继续在阅读器内切换；普通 HTTPS 资料链接不变。
- 已本地化块附件和富文本内嵌文件继续链接登录态 `/api/v1/knowledge/assets/{id}/content`。只有飞书回退而没有 `asset_id` 的附件在学生侧显示“暂不可下载”，不再生成“在飞书查看”链接。

### Validation and deployed

- 部署验收发现 `/knowledge` 的鉴权与其他受保护读取曾由 `Promise.all` 并发发起，匿名请求可能被非页面目标的 401/重定向抢先处理；现改为先完成 `requireUser("/knowledge")`，再读取目录、当前文档和通知，并新增 Server Component 回归保证鉴权完成前不发起其他读取。
- 最终知识库定向 2 文件/12 项、完整前端 25 文件/111 项 Vitest、ESLint、严格 TypeScript 和镜像内 Next.js 生产构建全部通过；最终候选以非 root `appuser` 运行、健康检查通过，匿名 `/knowledge` 稳定 307 到 `/login?next=%2Fknowledge`。
- `.env` 已固定为 `knowledge-student-links-20260830`，Frontend 镜像为 `sha256:a67211cda8d65afeb34bbdde630609cd7c50aff974cc99ddbb9f6852ac26c652`；只定向替换 Frontend 并刷新 Nginx。Backend/Worker 继续使用既有 `sha256:6851f989…`，PostgreSQL、MinIO 与数据卷未重建。
- Alembic 保持 `20260830_0016 (head)`；部署前后聚合均为 `users=158`、`knowledge_documents=1110`、`knowledge_assets=1027`、`account_cleanup=0`，最近同步保持 `succeeded|213|1020`，同步 Outbox 保持 `sent|1`。本轮未运行 migrate、未触发飞书同步或业务写入。


## 2026-08-30：允许已关闭问卷重新开启

### Changed

- 问卷状态机新增 `closed → open`；重新开启后可再次关闭，`archived` 仍为不可恢复终态。真实管理员在关闭问卷卡片可选择“重新开启”或“归档问卷”。
- 重新开启只更新状态、更新者、时间与 revision，保留题目/选项、二维码 token、历史最新答案、累计提交次数、原时间窗口和提交上限。原窗口已结束或本人次数已用尽时，重新开启不会绕过既有学生提交限制。
- 后端复用既有 `POST /admin/intentions/{survey_id}/open`，关闭后重新开启写独立 `intention.reopen` 审计与 `from_status/to_status` 摘要；真实管理员、CSRF、行锁和 409 状态冲突边界不变。新增 ADR-047，本轮无 API Schema 或数据库迁移。

### Validation and deployed

- 问卷定向后端/API 34 项、前端 2 文件/10 项通过；完整后端 299 项、Ruff、153 文件格式、120 源文件严格 Mypy，以及完整前端 25 文件/112 项 Vitest、ESLint、严格 TypeScript 和 Next.js 生产构建全部通过。
- 固定标签 `questionnaire-reopen-20260830` 已部署；Backend/Worker 镜像为 `sha256:f613c227e74b67b8c3f1257cb7dca2b2d80b2273168bad13df80ba923331e016`，Frontend 为 `sha256:35bed3d14aef08f213df7b14510c2623af5944d3639a3e2788175944a6d7bb75`，应用均以 `appuser` 运行。
- 六服务 healthy、重启 0，五健康入口为 200；问卷页面/API 匿名守卫为 307/401。运行标记确认问卷重新开启与持久登录、IP 转发、用户搜索、删除、知识库附件和 KaTeX 等既有能力同时保留。
- 未运行 migrate，Alembic 保持 `20260830_0016 (head)`；PostgreSQL/MinIO 未重建。部署前后用户、问卷五表、问卷状态、知识库、账号清理和同步聚合完全一致，未携带认证调用真实问卷写接口，也未触发飞书同步或其他业务写入。
- 新日志窗口无 Traceback、权限、连接、事务、外键或未处理异常。最近加密每日备份仍为 5,682,620 字节、0600 且 SHA-256 校验有效；同机 `/tmp` 恢复材料与 Docker socket 临时 ACL 风险不变。

## 2026-08-30：问卷支持按手动成员、技术组或全部激活学生发送邮件

### Changed

- 开放问卷邮件通知区提供三种互斥范围：通过既有用户搜索手动选择最多 100 名激活学生、选择一个激活技术组，或选择全部激活学生。前端按范围只提交成员 UUID、技术组 UUID 或 `all` 标识，并展示新增任务与同开放周期已存在数量；未满足当前范围输入时按钮禁用。
- `POST /admin/intentions/{survey_id}/email-notifications` 请求 Schema 以 `recipient_scope`、`recipient_user_ids` 和 `direction_id` 表达互斥范围。Service 在问卷行锁事务中校验状态与窗口；手动模式整体复核成员，技术组/全部模式由 Repository 查询发送瞬间的权威激活学生集合，停用/不存在技术组和空集合整体拒绝。
- 三种范围统一按 `survey revision + member` 唯一事件键避免重复入队，范围重叠不会重复发送；Outbox 与包含范围、可选技术组和计数的脱敏审计同事务提交。关闭后重新开启 revision 改变，管理员可再次显式发送；邮件只含称呼、标题和站内填写链接，不含答案、补充说明、二维码 token 或管理员信息。

### Validation

- 后端意向/API 契约定向 48 项、完整 315 项、Ruff 及 171 文件格式检查、120 个源文件严格 Mypy 全部通过。
- 前端问卷定向 12 项、完整 25 文件/115 项 Vitest、ESLint、严格 TypeScript 和 Next.js 生产构建通过。
- 自动测试使用替身且未连接或调用真实 SMTP；未连接运行 PostgreSQL/MinIO、未创建邮件任务、未运行 migrate、未构建或部署 Docker。本功能无数据库迁移。

### Deployed

- 固定标签 `questionnaire-email-scopes-20260830` 已部署；Backend/Worker 为 `sha256:af1d520399115abad815f84100c5e34c961a29003087d3088eccf54eb7106cbd`，Frontend 为 `sha256:8d4ba40349833834a713a6af4b5ea90c572343dd26e6ab58a9d78aeef75e75fe`。六服务 healthy、重启 0，五健康入口为 200，问卷页面/API 匿名守卫为 307/401。
- 运行 OpenAPI 为 115 条路径且包含 `manual/direction/all`；Frontend 编译产物保留三范围与既有上线能力。未运行 migrate，Alembic 保持 `20260830_0016 (head)`，PostgreSQL/MinIO 未重建。
- 部署前后 `users=160`、问卷五表 `3/5/21/92/183`、状态 `archived:2,open:1`、知识库 `1110/1027`、最近同步与 Outbox 聚合一致；匿名邮件 POST 为 401，未触发 SMTP、飞书或其他业务写入，部署窗口日志无异常。

## 2026-08-31：修复通知/作业删除后仍出现在管理页面

### Changed

- `announcements` 与 `assignments` 新增局部删除标记；手工 `archived` 继续在管理端留存，执行 DELETE 的归档记录退出常规管理列表和详情。
- 已发布内容删除同步写归档状态与删除标记；手工归档通知/作业首次 DELETE 写标记、revision 和审计，已有标记的重复 DELETE 保持 204 且不重复审计。
- 通知归档页恢复“删除通知”危险操作，同时继续隐藏保存、发布和更新提醒；确认文案说明删除后同时退出学生和管理页面。

### Migration and validation

- 新增 `20260831_0017_admin_content_deleted_visibility.py`，从成功 archive 模式删除审计回填历史标记，并以检查约束限制非空标记只能用于归档状态；downgrade 先删约束再删列。
- 完整后端 320 项、Ruff/格式 172 文件、严格 Mypy 153 个源文件；完整前端 25 文件/116 项、ESLint、严格 TypeScript 和生产构建通过。
- 独立 PostgreSQL 的 `0016 → 0017 → 0016 → 0017` 往返通过：通知/作业各 1 条删除审计记录被回填，各 1 条手工归档记录保持空值，第二次升级结果一致；临时容器已删除。
- 源码候选阶段未连接或修改生产 PostgreSQL/MinIO，未调用运行环境 DELETE；随后已完成下述生产部署。

### Deployed

- 部署前加密每日备份 `pnx-backup-20260831T054111Z-daily` 为 99,897,873 字节、0600，SHA-256 `06f7a4657cf53cabdb7c18fe59d1b16974b0d9ad8a31aa0701afc8fa1b1f525b`；数据库 dump 8,157,669 字节、PostgreSQL 17 目录 314 项，MinIO 清单 2,939 个对象且增量删除 0。
- 固定标签 `admin-content-visibility-20260831` 已部署；Backend/Worker 镜像为 `sha256:589290276cd2ab01b283dc227e3effffe9548df4235a8965fa2c2f3c97145772`，Frontend 为 `sha256:8d5ea4a60f04cbf7be44b22b438a1a5c60aef40a0ebf37cf6786ceec2fca116b`。生产 Alembic 为 `20260831_0017 (head)`，历史回填为 0。
- 六服务 healthy、重启 0；PostgreSQL/MinIO 容器未重建。运行 OpenAPI 115 条路径、管理页面匿名 307、管理 API 和虚假 UUID DELETE 匿名 401；部署未携带认证信息调用真实 DELETE，四个应用容器严重错误关键词为 0。
- 核心业务聚合保持一致；问卷在部署窗口有正常外部提交及对应成功审计。临时镜像已清理；Docker socket 临时 ACL 因交互式 sudo 要求仍待部署方撤销。

## 2026-08-31：培训知识库目录跟随、独立文件下载与图片阅读完成并部署

### Changed

- 无当前文档时目录只展示根层条目且根文件夹保持收起；进入、切换或通过浏览器历史恢复有效文档时自动展开当前祖先链、滚动定位活动项，并收缩离开的旧路径。目录栏整体开合和系统主导航折叠边界保持不变。
- 飞书目录 `obj_type=file` 独立文件复用附件安全校验、MinIO 和 `/knowledge/assets/{id}/content`；当前快照资源授权同时接受文档关联与独立文件节点关联，失败节点不暴露飞书链接。
- 图片点击改为当前页可访问模态浮层，支持 Escape、遮罩、关闭按钮和焦点回归；连续图片按容器宽度自动并排、空间不足时换行。
- 新增 `20260831_0018_knowledge_directory_files.py` 和 ADR-049；downgrade 自动把 `file` 转回 `unsupported` 后删除节点资源关联，不删除 MinIO 对象。

### Validation and rollout boundary

- 后端知识库/迁移定向 40 项及完整 322 项 Pytest、Ruff、173 文件格式、153 源文件严格 Mypy通过；前端知识库定向 13 项及完整 25 文件/118 项 Vitest、ESLint、严格 TypeScript 和 Next.js 16.3.2 生产构建通过。
- 源码阶段未连接或修改运行 PostgreSQL/MinIO，未执行迁移、真实飞书同步、Docker 构建或部署；随后已完成下述部署。

### Deployed

- 新建加密同点备份 `pnx-backup-20260831T073443Z-daily`：归档 99,901,190 字节、0600、SHA-256 `a337e786920638b30224317155f76029f69afd25717df61b26e705d3167c3a00`；数据库 dump 8,160,511 字节、PostgreSQL 17 目录 314 项，MinIO 清单 2,939 个对象/2,130,171,406 字节，增量 54 个/92,006,811 字节且删除 0。
- 固定标签 `knowledge-directory-media-20260831` 已部署；Backend/Worker 镜像为 `sha256:77f58286fe7434a970d9656f8a5801ce470af628745e992f513dffb69cb2796f`，Frontend 为 `sha256:f523e338e44c0788fb61c1f8378f73940f1bdc00d907a8a1ef770dfbe3883e65`，应用均以 `appuser` 运行。Backend 源码在镜像内为只读可遍历，备份脚本的宿主降权 UID 也能安全导入。
- 生产已从 `20260831_0017` 升级为 `20260831_0018 (head)`；112 个历史 `unsupported:file` 节点转为 `file:file` 且 `asset_id=NULL`，可空 UUID 列、FK 和索引有效。迁移前后全表行数哈希保持 `65b142a35e7e3a73dc49743a8978943d4910544312bde9951c0b3148ff4a585f`。
- 六服务 healthy、重启 0；五个健康入口为 200，知识库页面/API/虚假资源下载匿名为 307/401/401，运行产物包含目录跟随、图片浮层、下载状态和 `flex-wrap`，四个应用容器严重错误关键词为 0。PostgreSQL/MinIO 容器未重建，未触发真实飞书同步；仍须真实管理员手动成功同步一次，目录文件才会获得下载资源。

## 2026-08-31：知识库默认根层视图截图验收热修

### Changed

- 无有效 `?doc` 的 `/knowledge` 不再自动选择或读取第一篇文档；正文显示“从目录选择一篇培训文档”，左栏只展示根层条目，根文件夹显示向右箭头且不展示子项。
- 显式点击目录/搜索/内部链接或历史恢复有效文档时只展开当前祖先链并滚动定位；切换文档收缩旧路径，历史返回无文档首页时清空当前文档与自动展开集合。目录栏整体开合、目录文件下载、图片页内浮层和画廊布局不变。
- KB-002、页面说明、设计系统、KB-T06、ADR-049、正式计划、基线和任务记录统一纠正“展示根层”与“展开根文件夹”的歧义。

### Validation and deployed

- 知识库页面/组件定向 2 文件/16 项与完整前端 25 文件/120 项 Vitest、ESLint、严格 TypeScript、主机及镜像内 Next.js 生产构建全部通过；无缓存镜像依赖审计 0 漏洞，隔离候选 `appuser` 与 `/health=200` 通过。
- 固定标签 `knowledge-root-view-20260831` 已仅替换 Frontend/Nginx；Frontend 镜像为 `sha256:9a76b96ca85d67a0364cf939fd5528bbfb42b6d4633d143b75a61ad2443b811f`。Backend/Worker、PostgreSQL、MinIO 容器 ID 保持不变，Alembic 保持 `20260831_0018 (head)`。
- 六服务 healthy、重启 0，登录和五健康入口为 200；知识库页面/API/虚假资源下载匿名为 307/401/401，运行产物与新日志窗口通过。未运行 migrate、未触发飞书同步或业务写入。

## 2026-08-31：修复同步后目录文件不可下载与图片未并排

### Fixed

- 生产证据确认最新同步已经成功，根因不是未同步：16 个目录文件错误复用了正文媒体的 `/drive/v1/medias/{token}/download`。目录独立文件现改用 `/drive/v1/files/{token}/download`，正文图片/附件端点保持不变，安全校验、MinIO、登录态授权和失败降级继续复用。
- 图片画廊现跨过空段落并展开只承载媒体的结构容器；同一视觉序列在容器足够宽时并排、空间不足时换行，可见文字、标题和列表仍终止分组，不重排正文语义。

### Validation and deployed

- 后端知识库定向 31 项、完整 322 项、Ruff/格式和受影响 4 文件严格 Mypy通过；前端知识库 2 文件/17 项、完整 25 文件/121 项、ESLint、严格 TypeScript、主机与镜像内生产构建通过。
- 新 OpenPGP 每日备份 `pnx-backup-20260831T102419Z-daily` 为 101,156,599 字节、0600，SHA-256 `e3a7ddf3ca640f8d825c3d763a0db938b3264fca21fced5894c216d8da8a1468`；外层、完整解密、内部逐文件和 PostgreSQL 17 恢复目录验证通过。
- 固定标签 `knowledge-file-gallery-fix-20260831` 已两阶段上线；Backend/Worker 为 `sha256:2b1c9079e5dc9f2079acdb063cd7a0e2d88c52c68be045a346f180054d692141`，Frontend 为 `sha256:a5ad5927756819aeedbe4931b4921a60831d11fcaced9ea9530ded90f04446d3`。六服务 healthy、重启 0，Alembic 保持 `20260831_0018 (head)`，PostgreSQL/MinIO 未重建。
- 部署前后聚合保持 `users=169|runs=12|nodes=1836|documents=1544|assets=1064|outbox=430`；当前快照仍是旧代码生成的 217 篇/1,057 资源，16 个目录文件尚未原地改写。须真实管理员在新版本上再次手动成功同步后，才能验收新的节点资源关联。
