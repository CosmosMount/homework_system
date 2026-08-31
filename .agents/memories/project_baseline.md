# 项目基线记忆

## 长期稳定事实

- 项目是单校、单组织的内部平台，不是多租户 SaaS、公开论坛或通用网盘。
- 用户角色只有学生和管理员；新账号使用 `@connect.hkust-gz.edu.cn` 注册，邮箱前缀派生为用户名，激活后可用用户名或完整邮箱登录。空系统首个完成验证的账号成为受最后管理员保护的管理员；历史数据库若用户表恰好一行且该账号已验证并处于 `active`，部署迁移或下次登录会把它持久化为管理员。其余账号直接激活为学生，不经过人工审核或强制初始分组。
- 注册、密码重置和管理员命令行创建账号统一使用 8～128 个 Unicode 字符密码策略；继续使用 Argon2id，并拒绝常见密码及与邮箱、学号高度相似的值。
- 应用层持久认证失败窗口只用于无效登录：按规范化邮箱 5 次、来源 IP 30 次统计 10 分钟，返回 `Retry-After: 600`；已验证 `active` 账号的正确密码先完成 Argon2id 校验并直接登录。注册、验证邮件重发和密码重置申请只记录安全分析事件，不读取历史事件形成持久等待；Nginx 瞬时入口限流继续保留。
- 登录默认使用浏览器会话 Cookie，服务端保持管理员 4 小时、学生 12 小时空闲与 14 天绝对期限；用户可主动选择最长 30 天的“记住登录状态”。系统不保存密码，持久 Session 必须同时持有高熵 Cookie 并匹配登录时精确来源 IP 的 HMAC；数据库不存精确 IP，相同 IP 不能单独认证。
- 现有官网与飞书培训知识库继续独立维护；本系统允许真实管理员手动触发飞书开放 API，将结构化正文和受控媒体同步为只读快照供登录用户阅读，但不编辑或写回飞书，不修改或依赖现有官网运行时，学生请求不实时访问飞书。
- 培训作业默认可向全体学生投放，也可按管理员维护的技术方向定向投放；届次设置已从产品入口移除，历史受众字段仅作兼容；个人提交作业，校内赛由团队队长提交。
- 作业发布时生成初始固定受众；后续普通学生首次激活时加入当时仍开放且匹配的作业，之后修改方向不重算历史归属。
- 提交允许保留多个不可变版本，私密评语只对相应个人或团队成员与管理员可见。
- 不提供分数、排名、自动评奖和公开评语；管理员可标记作业版本为优秀作业，它只在对应作业中向该作业受众显示，赛事版本不能标记。
- 架构固定为 Next.js + FastAPI + PostgreSQL + MinIO + Nginx + Docker Compose，部署在校内服务器。
- 单个提交版本的附件合计上限为 2 GB，使用预签名分片上传。
- 站内通知与 SMTP 邮件配合，邮件和定时发布由 PostgreSQL Outbox Worker 可靠执行，不引入 Redis。
- 反馈答疑采用登录态单工单模型：学生提交系统反馈或问题答疑并查看本人记录，真实管理员填写当前答复；已解答问题向有效登录用户匿名只读公开，开放问题和全部系统反馈仍私密。它不是匿名互联网论坛、即时聊天或多轮消息，也不支持评论、追问、附件、评分或邮件答复。

## 当前阶段

阶段 1～6 已完成实现与真实 Linux Docker/浏览器/运维验收，首版发布候选已经形成。系统源码具备认证与两角色授权、通知与工作台、作业/赛事、问卷、反馈答疑、飞书知识库只读同步与阅读，以及共享 MinIO 存储；管理员可维护资料和登录人员，并可在当前 Session 临时切换学生视图。

当前知识库发布候选通过 29 项后端知识库定向测试、完整后端 213 项测试、前端 20 个文件/76 项测试、Ruff、格式检查、严格 Mypy、ESLint、严格 TypeScript 和 Next.js 生产构建；此前容器构建、依赖审计、三浏览器、秘密扫描和镜像安全门继续有效。

生产资源边界下读取 P95 为 341.754 ms、错误率 0%；每日增量恢复 RPO 31 秒、RTO 13 秒且对象对账为 0。空库已完成 `base → 20260825_0006 → 20260825_0005 → 20260825_0006`，并发邮箱验证只产生一个初始管理员和一条授予审计；阶段 6 发布脚本记录 `pnx-release-20260825T013516Z` 并通过 HTTPS 冒烟，所有认证增量隔离资源也已清理。

开发 Compose 当前运行态为 `20260827_0011 (head)`，Frontend、Backend、Worker、PostgreSQL、MinIO 与 Nginx 均健康且只有 Nginx 映射 `0.0.0.0:5000`；Alembic 模型漂移检查没有待生成操作。数据库已清除历史 Stage 4/Stage 5/Codex Smoke 数据；当前有已验证 `active admin` `yzhang367@connect.hkust-gz.edu.cn` 与已验证 `active student` `xluo799@connect.hkust-gz.edu.cn`；角色变化已撤销全部旧 Session，用户需重新登录；两条维护审计保留。删除前 PostgreSQL 与 MinIO 恢复材料暂存于 `/tmp`，路径和校验值见 `.agents/plans/plan_remove_smoke_accounts.md` 与运维报告。统一前端 API Client 已兼容 `202` 等成功空响应，管理员新建作业、个人资料、登录人员和飞书知识库页面均已注册。
浏览器端作业/通知发布、正式版本和上传幂等操作已统一兼容普通局域网 HTTP：原生 `crypto.randomUUID()` 缺失时使用 Web Crypto `getRandomValues()` 生成 UUID v4。Frontend 新镜像和 Nginx 已重启，真实 Chromium 环境能力与回归测试一致。

飞书知识库参考提交 `c28f8a0` 对齐和真实完整上线已经完成。2026-08-27 前台同步以 `succeeded` 完成 228 个目录节点、212 篇文档和 977 个成功媒体引用，耗时 `00:33:28.757715`；日志中的 13 次允许资源回退未阻断快照，旧 48 篇阶段性快照已被新成功快照自然替代。Worker 恢复后最新 `sync_knowledge` Outbox 为 `sent`、`attempt_count=1` 且无错误。Backend/Worker 运行镜像为 `sha256:f8c42b…`，Frontend 为 `sha256:2ad76bd…`；知识库阅读区采用白色主题、左文档目录、中央正文和右本文目录，右侧本文目录随滚动高亮当前章节，成功打开文档后折叠系统主要导航且保持文档目录状态；六服务 healthy，四个健康端点为 200，知识库页面匿名 307、两个知识库 API 匿名 401。Alembic 仍为 `20260827_0011`，本轮无迁移。现场上线仍须部署方提供受信域名/证书、异机加密备份目标、独立告警接收方和学校数据留存/灾难恢复制度；多账号无管理员的异常历史库仍必须走受控恢复。


## 2026-08-27 增量记忆

- 管理员所有页面统一使用 `AdminPageHeader`，通知、作业、校内赛及详情页共享返回入口、标题层级和操作区。
- 赛事管理产品入口固定为“校内赛”：首页直接列出当前未归档赛事的队伍；首次配置路由只在没有当前赛事时可用。
- `CompetitionRepository` 使用事务级 advisory lock 配合未归档查询，`CompetitionService.create_competition` 在已有当前赛事时返回 `CAMPUS_COMPETITION_EXISTS`；归档历史赛事和赛题兼容数据不删除。
- 学生校内赛入口现为队伍中心，公开目录只列未满 `forming` 队伍的名称、状态和人数，支持搜索、分页、邀请码加入及本人主动自动分配。
- 新增登录态学生意向调查：管理员管理单选/多选、匿名汇总和本地二维码，学生只读取和修改本人回答；二维码 token 只存 SHA-256 且轮换后旧码失效。
- 2026-08-27 已重建 Backend/Worker/Frontend/Nginx；六服务健康，四个健康端点为 200，新增受保护页面/API 的匿名请求分别由登录守卫返回 307/401。
- 2026-08-27 密码下限已统一为 8 位并完成 Backend、Worker、Frontend、Nginx 重建重启；运行容器接受安全 8 位密码，注册和重置页面为 200，六服务保持健康。

- 2026-08-27 应用 `20260827_0010` 后，`xluo799@connect.hkust-gz.edu.cn` 已加入“电控第一次作业”正式受众，目标人数为 1；后续普通学生验证时会原子补录仍开放且匹配的作业。六服务 healthy、四个健康端点为 200、Alembic 无模型漂移。
- 0010 前受众表临时备份为 `/tmp/homework_system_assignment_audience_before_0010_20260827.sql`，权限 0600、大小 960 B、SHA-256 `7032fb9c8a20ef044276a943e2ccebcbd28758a0f3f10c14459bc4c84ab6a920`。
- 飞书知识库仓库实现已完成：管理员手动同步、Worker 只读快照、学生培训文档阅读、当前快照资源授权和结构化块渲染均已落地。
- 最终知识库质量门通过 29 项后端定向测试、完整后端 213 项测试、Ruff、格式检查、严格 Mypy，以及前端 20 个文件/76 项测试、ESLint、严格 TypeScript 和 Next.js 生产构建。
- 仓库与开发运行库 Alembic head 均为 `20260827_0011`；Backend、Worker、Frontend 已重建，迁移容器退出码为 0，六个常驻服务 healthy，四个健康端点为 200。
- 首次迁移容器因新知识库源码目录/文件为 `0700/0600` 且镜像复制后属主为 root，在导入模型前退出；数据库保持 `0010`。修正源码为标准 `0755/0644` 后重建并成功迁移，不存在半迁移数据。
- 飞书只读配置已对齐为 `FEISHU_APP_ID`、`FEISHU_APP_SECRET`（或 secret file）和 `FEISHU_WIKI_URL` 三项；空间 URL 自动解析数字 Space ID，文档 URL 自动解析节点 token，不再要求独立 Space ID/Root Token。
- 真实只读诊断已完成 tenant token 获取和整个空间节点读取，过程中未输出秘密、token、Space ID 或原始响应。
- 阶段性前台初始化曾生成 48 篇正文回退快照；最终完整同步已以 212 篇文档和 977 个成功媒体引用自然替代该快照。
- ADR-032 继续固定参考提交 `c28f8a0` 的目录/正文/标题 fail-fast 与媒体失败语义；ADR-033 保留白色主题和文档目录—正文—右侧本文目录顺序；ADR-034 规定成功打开文档后折叠系统主要导航且保持文档目录状态，并让右侧本文目录随滚动高亮当前章节。移动端右下按钮和全屏目录继续有效。
- 后端/前端知识库定向热修和运行镜像隔离了并行未完成的账号清理代码，账号清理工作树内容保持不变。


## 2026-08-28 增量记忆

- 知识库阅读区以 ADR-033 保留白色主题和文档目录—正文—本文目录顺序；ADR-034 已把自动折叠目标修正为系统主要导航，文档目录保持用户状态，加载失败不改变两者；右侧本文目录 sticky 跟随并高亮当前章节。
- 最新定向 8 项知识库前端测试、完整 20 文件/77 项测试、ESLint、严格 TypeScript 和工作树/隔离源码 Next.js 生产构建通过。
- 最新隔离镜像差异仅含共享主导航、折叠事件、知识库阅读器和测试 4 个文件；Frontend 运行镜像为 `sha256:2ad76bd…`，六服务 healthy，四个健康端点为 200，页面/API 匿名守卫为 307/401。
- 最新同步仍为 `succeeded`、212 篇文档、977 个媒体引用，最新知识库 Outbox 仍为 `sent`、`attempt_count=1`；未触发新同步、未迁移数据库，管理员手动接口和 Worker 保持不变。
- 管理员创建带选项的意向调查曾因 ORM 先插入 `intention_options` 而触发外键 500；`IntentionService.create()` 现先 `flush()` 父调查，再在同一事务写入选项，失败继续整体回滚。
- 该修复通过意向定向 10 项、隔离源码完整后端测试、Ruff、146 文件格式检查、146 个源文件严格 Mypy 及真实 PostgreSQL 回滚冒烟；没有测试数据残留，也不涉及 API、Schema 或迁移。
- Backend/Worker 当前运行同一隔离修复镜像 `sha256:409a55ff…`，并行账号活跃度/清理改动未纳入；六服务 healthy，四个健康端点为 200，Alembic 保持 `20260827_0011 (head)`。
- “意向调查”源码已升级为用户界面“问卷”：支持 1～30 道必答单选/多选题、每人 1～100 次或不限的提交上限、本人最新答案/累计次数、管理员分题统计和仅真实管理员可读的实名最新答案名单；兼容保留 `/intentions` 路径和二维码登录回跳。
- 新迁移 `20260828_0013` 接在工作树已有账号活跃度 `20260827_0012` 后，把旧调查迁为一个兼容问题、保留选项/回答并以 revision 初始化提交次数，旧调查默认不限；降级按题序展平且会丢失题目/次数语义，生产回滚前必须备份。
- 问卷改造初轮完整后端 218 项、前端 20 文件/79 项、ESLint、严格 TypeScript 和生产构建通过；定向 Ruff、格式与 7 文件严格 Mypy 通过，双向离线 PostgreSQL DDL 可生成。该初轮当时尚未部署，Docker socket 权限也未生效；完整后端静态门当时另被既有账号清理改动的未定义 `payload` 阻塞，后续均已处理。
- 管理员用户页旧版以 `FormData(form)` 读取提交按钮值，导致角色、禁用和恢复按钮不发请求；现已改为从 `SubmitEvent.submitter` 识别实际按钮，并补充角色提升回归。
- Frontend 当前运行隔离热修镜像 `sha256:f9cc2771…`，未纳入工作树账号清理和问卷改造；Backend/Worker 仍为 `sha256:409a55ff…`。
- 六服务 healthy，四个健康端点为 200，Nginx 继续映射 `0.0.0.0:5000`，管理员页面匿名守卫为 307；Alembic 保持 `20260827_0011 (head)`。
- 上线后真实管理员页面的两次角色变更及禁用/恢复请求均返回 200，证明按钮到后端的完整写链路已经恢复。
- 本次角色按钮修复不涉及 API、数据库、迁移或用户角色数据变更。
- 管理员用户卡片的账号状态已从英文枚举改为“正常 / 待验证 / 已禁用”中文胶囊，使用浅色语义背景、边框、圆点和文字；角色使用蓝灰胶囊，超期提示为“X 天未登录”，中文角色/状态可搜索。
- 本轮工作树完整前端 20 文件/80 项、隔离基线 20 文件/72 项、最终定向回归、ESLint、严格 TypeScript 和生产构建通过。
- Frontend 当前运行隔离镜像 `sha256:4ebd888c…`，未纳入工作树账号清理和问卷改造；六服务 healthy，四个健康端点 200，Nginx 保持 5000 端口。
- 本次纯前端状态 UI 调整不涉及 API、权限、数据库、迁移或用户数据。
- 账号活跃度/受保护清理、多题实名问卷和对应前端已分别提交为 `b328035`、`2468f05`、`86a90c4`；账号服务错位的 `payload` 引用已修复，邮箱变更 Session 锁回到 `patch_user()`。
- 最终工作树通过 Ruff、161 文件格式检查、146 个源文件严格 Mypy、218 项后端测试，以及 ESLint、严格 TypeScript、20 文件/80 项前端测试和 Next.js 生产构建；Alembic 单一源码 head 为 `20260828_0013`。
- 2026-08-28 对现有 5000 入口完成 100 并发、5,000 次无写入混合探测：错误率 0%，总体 P95 286.163 ms、吞吐 1,226.374 req/s；探测后四个健康端点均为 200，无遗留压测进程。
- Docker 授权后在独立 `pnx-loginburst-20260828a` 空库应用到 `20260828_0013` 并生成 300 个虚构学生容量数据。100 个账号从同一出口同时经 Nginx 登录时仅 21 个成功、79 个被 Nginx `auth_limit` 以 503 拒绝；日志确认请求未到 Backend，根因是全认证路径共享 `5r/s`、`burst=20` 的 IP 粗限流。
- 绕过 Nginx 只验证同一隔离 Backend 时，第 101～200 个虚构账号 100/100 登录成功，总耗时 5.293 秒、登录 P95 5.235 秒，数据库产生 100 个独立 Session；说明应用与数据库能完成突发，但当前入口不能满足校园 NAT 下 100 个账号同时登录，且登录等待明显高于普通读取 NFR。该入口策略尚未修改，需在不削弱应用层账号/IP 失败限流的前提下单独整改并让粗限流返回 429。
- 本轮隔离 Compose、卷、网络、专用镜像和 0600 临时密码目录均已清理；20 路 multipart、正式 100 Session 业务读取和 `0011 ↔ 0012 ↔ 0013` 真实 PostgreSQL 往返仍未执行。
- 隔离压测步骤没有部署新提交、应用迁移、执行账号删除或向现有 5000 写入压测数据；其后独立功能部署已更新运行基线，见下节。

## 2026-08-28 部署后基线

- 运行 Compose 已部署提交 `60b8fe9`：Backend/Worker 镜像 `sha256:8253599…`，Frontend 镜像 `sha256:1252a679…`，固定标签均为 `questionnaire-account-20260828`。
- 运行数据库 Alembic 为 `20260828_0013 (head)` 且无模型漂移；`0012` 和 `0013` 已同时应用，没有执行账号删除。迁移前 PostgreSQL 17 备份位于 `/tmp/pnx-training-before-questionnaire-0013-20260828T132500Z.dump`，SHA-256 为 `5a3c6354…e31`。
- 生产备份的隔离副本已完成 `0011 → 0012 → 0013 → 0012 → 0013` 真实往返；旧调查迁为 1 个兼容问题，3 个选项、2 份回答和 2 条选择关系保持完整。
- 六个常驻服务 healthy，四个健康端点为 200；问卷、管理员问卷与用户页面匿名守卫为 307，问卷和实名名单 API 匿名访问为 401。
- 最近成功知识库快照保持 212 篇文档、986 个媒体引用，最新同步 Outbox 保持 `sent/1`，本次没有触发飞书同步。
## 2026-08-28 高并发与入口安全基线

- Nginx 开发/生产认证限流使用 limit_req_status 429，仍按真实来源使用 5r/s + burst=20；客户端不能通过转发头改写来源。单 IP 大量账号命中 429 属于预期防护。
- 隔离多来源登录 100/200/300 账号均 0 错误；100 Session/2,000 次登录后读取错误率 0%，P95 331.674 ms。Argon2 登录突发最慢分片 P95 为 3.53～8.90 秒，属于 CPU 排队观测。
- 本机入口安全探测通过匿名鉴权、Host/转发头、Origin/CSRF、方法、请求体、路径遍历和 source map 边界；Gitleaks 0 泄漏。Trivy 发现 Backend Alpine 的 4 个 CVE，基础镜像升级待排期。
- 当前 PNX 只保留 questionnaire-account-20260828 当前镜像和 intention-fix-20260828/user-status-ui-20260828 回滚候选；运行卷、备份和六服务均保留。

## 2026-08-28 问卷查看与草稿编辑运行基线

- 当前 Backend/Worker 镜像为 `pnx-training-backend:questionnaire-edit-20260828`（`sha256:06eb68d3c5b2…`），Frontend 为 `pnx-training-frontend:questionnaire-edit-20260828`（`sha256:a5d9264abc6a…`）；Nginx 主机端口仍为 5000，六服务 healthy。
- 管理员可读取任意状态问卷完整内容；仅 `draft` 可按 revision 修改标题、说明、时间窗口、提交次数和题目/选项结构，其他状态只读。学生和管理员学生视图没有管理详情/修改权限。
- Alembic 保持 `20260828_0013 (head)` 且无模型漂移，本轮不新增迁移。运行数据为 2 份问卷、3 道题、11 个选项、2 份回答、2 条选择关系。
- 部署前备份为 `/tmp/pnx-training-before-questionnaire-edit-20260828T145330Z.dump`，4,145,718 字节、0600，SHA-256 `f089b9425488a48f4fa2d3b34744ab9423d86a00255b17c26c23caef373d08bf`。
- 最近成功知识库快照仍为 212 篇文档、986 个媒体，未触发飞书同步。首次部署权限故障已通过恢复源码 0644、重建镜像解决；未使用的临时 `dev` 标签已删除。

## 2026-08-29 反馈答疑运行基线

- 新增 `HELP-001～HELP-006` 私密工单域、学生/管理员四个页面、六个受保护 API、`help_requests` 表和 `20260828_0014` 单一源码 head；学生本人 404、管理员学生视图、revision、Markdown 清洗、通知和脱敏审计边界已实现。
- 管理员答复在锁行和 revision 校验后，同一事务写状态、当前答复、审计与 `help_request_resolved:{request_id}:{revision}` 站内通知；通知只含安全标题和 `/help/{request_id}`，不含正文且不创建邮件 Outbox。
- 2026-08-29 正式修订新增 `HELP-007`：仅已解决问题提供登录态匿名公开列表/详情，查询不连接用户表且响应无提交者身份；不新增字段或迁移，系统反馈和开放问题继续私密。
- 完整质量门通过：Ruff、169 文件格式检查、120 个源文件严格 Mypy、246 项后端测试；ESLint、严格 TypeScript、21 文件/89 项前端测试和 Next.js 生产构建。
- 当前 Backend/Worker 为 `pnx-training-backend:help-public-20260829`（`sha256:942b9ee5e98d…`），Frontend 为 `pnx-training-frontend:help-public-20260829`（`sha256:93feb800a8c6…`），均以 `appuser` 运行；`.env` 已固定该标签。
- 运行库为 `20260828_0014 (head)` 且无模型漂移；迁移前备份 `/tmp/pnx-training-before-help-requests-20260829T015203Z.dump` 为 4,147,113 字节、0600，SHA-256 `9bb10adf0edd852a9192f2eb9e65ba3c6a23ae908651192839089ab8369cd8a2`。
- 生产副本隔离完成 `0013 → 0014 → 0013 → 0014`；用户 6、问卷 `2/3/11/2/2` 和知识库 `212/986` 前后不变，隔离容器和网络已清理。
- 六服务 healthy，四健康端点为 200；公开页面匿名 307、两个公开 API 匿名 401，运行 OpenAPI 含八个反馈答疑操作；本轮未触发邮件、飞书同步、账号删除或上传。
- 运行库现有 1 条 `question/resolved` 工单，未由本轮修改，已按派生规则进入登录态匿名公开范围；本轮不新增迁移，Alembic 仍为 `20260828_0014 (head)` 且无模型漂移。

- 2026-08-29 学生提醒改为按公告、作业、校内赛和反馈答疑目标分类显示；已归档公告从查询侧立即排除，新归档事务同时写已读，本人工单解决提醒在详情通过单条已读接口消除。本轮无迁移、无新依赖，已随 `help-public-20260829` 部署。
- 2026-08-29 已在用户授权后撤销本次部署添加的 Docker socket `user:pnx:rw-` 临时 ACL；`getfacl -cp /var/run/docker.sock` 复核仅剩基础 owner/group/mask/other 条目，部署权限已收敛。


## 2026-08-29 学生提醒共享页面部署后基线

- 当前 Frontend 为 `pnx-training-frontend:notification-badges-20260829`（`sha256:fd13387f14a5…`），以 `appuser` 运行；个人资料、登录设备和公开答疑详情均保持学生分类徽标，不再进入页面后暂时归零。
- Backend/Worker 容器仍为 `pnx-training-backend:help-public-20260829`（`sha256:942b9ee5e98d…`），同一镜像已增加 `notification-badges-20260829` 别名；`.env` 使用该统一固定标签。
- 六服务 healthy，四健康端点与登录页 200，三个目标页面匿名守卫 307，Dashboard API 匿名访问 401；Alembic 保持 `20260828_0014 (head)`，本轮无迁移或业务数据写入。
- 本次部署使用的 Docker socket `user:pnx:rw-` 临时 ACL 已由用户撤销；复核仅剩基础 ACL，socket 为 `root:docker`、`0660`。

## 2026-08-29 统一发布与 Docker 清理后基线

- 当前固定发布标签为 `release-634e01a-20260829`；Backend/Worker 镜像 ID 为 `sha256:c7ccb9bd1249354d0ad5b059560bd90f34a69f6e22bd45058e6e65f132b8cea9`，Frontend 镜像 ID 为 `sha256:76266bc260527c7131af364c97ed2f801769b8a3ef5e111cb0dff642bf033c46`，应用容器均以 `appuser` 运行。
- 六服务 healthy 且重启次数为 0；登录页和全部健康端点为 200，受保护页面/API 的匿名 307/401 守卫保持有效。Alembic 与运行库为单一 `20260828_0014 (head)`，无模型漂移或新迁移。
- 发布前后业务计数保持 `6/2/3/11/2/2/1/1/212/986`，依次对应用户、问卷、问题、选项、回答、选择关系、工单、已解决公开问题、知识文档和媒体；未触发飞书同步、邮件、账号删除或上传。
- 发布前备份 `/tmp/pnx-training-before-release-634e01a-20260829T042700Z.dump` 已通过 PostgreSQL 17 `pg_restore --list` 校验，大小 4,153,800 字节、0600、SHA-256 `bb4ad5f713aa1d605e6cffac23903471d48a49dd66f1085bfb6660425cd78caa`；长期保留仍需迁出 `/tmp`。
- Docker 仅保留当前发布与 `notification-badges-20260829` 回滚镜像，以及运行卷、三个 PNX 网络、其他项目、4 个来源不明匿名卷和全局构建缓存；已删除 1 个旧迁移容器、10 个旧应用标签和 9 个旧镜像 ID，无 dangling 镜像，未全局 prune。
- `/var/run/docker.sock` 的临时命名 ACL `user:pnx:rw-` 已由用户撤销；最终只剩基础 owner/group/mask/other 条目，所有者/权限为 `root:docker`、`0660`，本轮 Docker 权限已完全收敛。

## 2026-08-29 认证失败窗口部署后基线

- 当前 Backend/Worker 为 `pnx-training-backend:auth-window-20260829`（`sha256:716685804552…`），以 `appuser` 运行且 healthy；Frontend 继续使用原镜像 `sha256:76266bc26052…` 并增加同名标签别名，`.env` 固定到 `auth-window-20260829`。
- 六服务 healthy，登录页和四个健康端点为 200，认证页面/API 匿名守卫保持 307/401；运行库为 `20260828_0014 (head)`，本轮无迁移。
- 部署前 PostgreSQL 17 备份为 `/tmp/pnx-training-before-auth-window-20260829T081859Z.dump`，大小 4,306,752 字节、0600、SHA-256 `05f7ec8f7de2b6213461ca4133469f96ec624d276798b0ad6719ab53d3c8b46d`。
- 发布期间真实用户并发完成注册、验证和登录；部署没有调用认证写接口或回滚这些数据。Docker socket 临时 ACL 已撤销并恢复为 `root:docker`、`0660`，当前用户不再具有 Docker API 访问权限。

## 2026-08-29 管理员内容删除部署后基线

- 当前 Backend/Worker 与 Frontend 固定标签均为 `admin-content-removal-20260829`，镜像分别为 `sha256:a9e4e73584e3…` 与 `sha256:1ce818d5d2d6…`；应用容器以 `appuser` 运行，六服务 healthy、重启次数为 0。
- 管理员可以二次确认删除通知或作业：未发布内容受审计物理删除，已发布内容归档并立即退出学生列表、详情、优秀作业及附件签名路径；提交、评语、受众、提醒、文件元数据与审计历史保留。
- 登录页和 `live/ready/worker/nginx-health` 均为 200，管理/学生通知和作业页面匿名为 307，两个 DELETE API 匿名为 401；运行 Backend OpenAPI 含两个 DELETE/204 路径。
- Alembic 保持 `20260828_0014 (head)`，PostgreSQL、MinIO 未重建且无迁移。部署前备份 `/tmp/pnx-training-before-admin-content-removal-20260829T091428Z.dump` 为 4,320,274 字节、0600，SHA-256 `194a1cdd7c2330fc7dd7e0ef70cf7d68240c95761f2c7ad352b5579df4446629`，只适合作为本机短期恢复材料。

## 2026-08-29 注册唯一约束热修后基线

- 当前 Backend/Worker 固定标签为 `registration-constraint-20260829`，镜像 ID `sha256:0972df29b3758acc4ef6750e248f59c8b905ec3bba44b4b4a6e0a4783e4d3e8b`；Frontend 继续运行 `sha256:1ce818d5d2d6…`，只增加同名标签别名，Frontend/Nginx 未替换。
- Backend/Worker 以 `appuser` 运行、重启次数为 0；六服务 healthy，登录页和 `live/ready/worker/nginx-health` 均为 200。运行认证文件为 0644，哈希 `d25505a99c2b712e7078be61deae1522c40a62e9fec13a5184aafcd4c8580825`。
- 重复邮箱/学号的 asyncpg 嵌套唯一约束已在 Service 层映射为字段级 400；管理员通知/作业 DELETE 路径继续存在。Alembic 保持 `20260828_0014 (head)`，无迁移。
- 部署前 PostgreSQL 17 备份 `/tmp/pnx-training-before-registration-constraint-20260829T103222Z.dump` 为 4,328,438 字节、0600、SHA-256 `b45dbbcc44c89576305511877687a2eae14c6b5f3f09fc76aaa2255dede5fc4a`，已通过同版本 314 项校验，只适合作为本机短期恢复材料。
- 部署命令未调用认证写接口；部署窗口的用户/安全事件/令牌变化来自持续外部注册流量，未删除或回滚真实业务数据。
- Docker socket 的临时 `user:pnx:rw-` ACL 尚待用户以交互式 sudo 撤销；应用服务已完成部署和验收，不依赖该 ACL 继续运行。

## 2026-08-29 账号永久删除源码候选基线

- 已完成管理员永久删除非本人账号与用户自助注销源码，两条路径均要求有效 Session、CSRF、当前密码和目标邮箱确认并保护最后一个激活管理员；管理员另需内部原因与备份确认。个人数据物理删除，共享平台/团队记录保留并去除归属。
- 新源码 Alembic 单一 head 为 `20260829_0015`，包含个人 `CASCADE`、共享 `SET NULL`、队长预处理和正式版本触发器的事务级受限例外；运行环境仍保持此前已部署的 `20260828_0014`，本轮未应用、检查或降级 `0015`。
- 账号对象由可靠 Outbox 在 Worker 中先终止 multipart 再幂等删除；Worker 暂停不回滚数据库删除，对象不再授权并在恢复后继续清理。执行过删除后只能从删除前 PostgreSQL + MinIO 同点备份隔离恢复，不能由应用撤销。
- 本轮只执行不接触基础设施的纯 Mock/静态质量门：后端定向 45 项、Ruff、格式、120 源文件严格 Mypy，前端最终 23 文件/102 项 Vitest、ESLint、严格 TypeScript 和生产构建通过。未连接或修改当前 PostgreSQL/MinIO，未调用 5000 写接口、真实删除或备份脚本；生产启用前仍必须新建并验证同点加密完整备份。

## 2026-08-29 飞书 LaTeX 公式部署后基线

- 飞书知识库规范化器已保留富文本行内 `equation` 语义，并支持 `block_type=16` 独立公式块；阅读器使用本地 `katex@0.16.22` 分别排版行内与独立公式，坏公式安全回退为源文。
- KaTeX 禁用 trust，限制宏展开和尺寸，HTML 扩展为硬错误；不接受飞书任意 HTML。30 项后端知识库测试、受影响后端静态门、前端完整 23 文件/99 项测试、ESLint、严格 TypeScript 和生产构建通过。
- 当前固定标签为 `feishu-latex-20260829`；Backend/Worker 镜像 ID 为 `sha256:5e7b335da4fc…`，Frontend 为 `sha256:6076084d5de5…`，六服务 healthy、重启次数 0，登录页与四健康端点 200，知识库页面/API 匿名守卫为 307/401。
- Alembic 保持 `20260828_0014 (head)` 且未启动 migrate；部署前后核心业务计数不变，最近成功知识库仍为 212 篇文档、986 个媒体，最新同步 Outbox 仍为 `sent/1`，本轮未触发飞书、邮件、上传或账号删除写入。
- 部署前 PostgreSQL 17 备份 `/tmp/pnx-training-before-feishu-latex-20260829T112100Z.dump` 为 4,330,074 字节、0600，SHA-256 `b53cea2fd8927f4ce4f8aaca1b8a8bc759a1c508ac2db18208887f7a0c8b31a0`。现有快照不会原地获得公式语义，仍需真实管理员手动同步一次。
- 临时 Frontend 测试镜像与隔离构建目录已清理；Docker socket 的 `user:pnx:rw-` 临时 ACL 因宿主机要求交互式 sudo 尚待部署方撤销，应用运行不依赖该 ACL。

## 2026-08-29 反馈答疑删除源码候选基线

- 真实管理员可通过 CSRF 保护的 DELETE/204 物理删除任意系统反馈或问题答疑；事务锁定工单、把相关未读解决提醒标为已读、写脱敏审计后删除，学生本人、管理员与登录态公开读取随即不可见。
- 管理员详情提供区分类型的危险按钮与二次确认；学生、管理员学生视图和匿名请求分别受服务端授权与认证守卫限制。无软删除字段、状态、迁移、依赖或 Worker 变更。
- 后端定向 27 项和完整 280 项 Pytest、Ruff/格式，前端完整 23 文件/102 项 Vitest、ESLint、严格 TypeScript 与生产构建通过；当时完整后端 Mypy 的 6 项失败位于并行账号删除测试，不在本候选改动中，现已在账号删除部署收尾修正并通过 153 个源文件严格 Mypy。
- 候选尚未部署，未连接或修改当前 PostgreSQL/MinIO，未调用运行环境 DELETE；当前运行态仍是既有 `feishu-latex-20260829` 应用与 `20260828_0014` 数据库基线。

## 2026-08-29 账号永久删除部署后基线

- 当前固定标签为 `account-deletion-20260829`；Backend/Worker 镜像 ID 为 `sha256:081be7ba08de49781ab40d3e3053c45910ca34078901935c28638135f8846c81`，Frontend 为 `sha256:d4b5172a1a780f2f4db63db2f65a80e881669c4ec7c3b0dc09632b3d620bd2f4`，应用均以 `appuser` 运行。
- 运行数据库为 `20260829_0015 (head)`；34 个指向 `users` 的外键为 12 个 CASCADE、21 个 SET NULL 和 1 个由 Service 预处理的队长 RESTRICT。版本触发器只在账号擦除事务且父提交不存在时允许级联，普通 DELETE 保持 `55000`。
- 六服务 healthy、重启次数 0；登录和四健康端点 200，`/profile`、`/admin/users` 匿名 307，管理员/本人删除 API 匿名 401。OpenAPI 共 114 个路径，包含两条账号 DELETE/204 且不含仍在开发的反馈答疑 DELETE。
- 部署前后用户/问卷/问题/选项/回答/选择关系/工单/已解决问题/通知/作业/提交/版本保持 `155/3/5/21/84/166/1/1/4/1/1/2`；最近成功知识库为 `succeeded/213/1006`，账号对象清理 Outbox 为 0，部署没有调用真实账号删除或飞书同步。
- 加密完整备份 `pnx-backup-20260829T122839Z-weekly` 位于 `/tmp/pnx-account-deployment-backups/`，归档 SHA-256 为 `a68bdd8a847a419a2d092730362a6277453bcb6cf67614c76a784d817bd85bdb`；PostgreSQL 17 目录 314 项、2,885 个对象、从空环境恢复和 `0014 ↔ 0015` 往返通过。
- 对账确认 1,010 个数据库引用对象无缺失、大小或哈希不符；1,875 个历史知识库孤立对象保留并报告，不自动删除。隔离容器、网络和卷已清理。
- 最终纯 Fake 回归显式覆盖 `knowledge/` 完整备份恢复与 `knowledge_assets` 已跟踪对账；相关 66 项 Pytest、全量 Ruff/格式和 153 个源文件严格 Mypy 通过。
- 加密归档、校验材料和临时 GPG 密钥环仍同在本机 `/tmp`，尚未形成异机持久副本，必须迁移到受控独立介质并分离保存归档与解密材料；Docker socket 临时 `user:pnx:rw-` ACL 仍待撤销并复核为基础 `root:docker`、`0660` 权限。

## 2026-08-29 反馈答疑删除部署后基线

- 当前固定标签为 `help-delete-20260829`；Backend/Worker 镜像 ID 为 `sha256:1a2f7c6e3d7145653dcccb076c098fe544e854bcf29b6cede5ee9b5218fdc799`，Frontend 为 `sha256:2f7ef180f2c2da20eb39e6c723c45de5b8871e62b5e000bf5b53d60decd3b110`，应用均为 `appuser`。
- 真实管理员可通过 CSRF 保护的 DELETE/204 物理删除任意系统反馈或问题答疑；事务锁定工单、把相关未读解决提醒标为已读、写脱敏审计后删除，学生本人、管理员与登录态公开读取随即不可见。
- 六服务 healthy、重启次数 0；登录和四健康端点 200，答疑页面匿名 307、DELETE 匿名 401。OpenAPI 共 114 个路径，保留两条账号 DELETE 并新增答疑 DELETE/204 无正文。
- Alembic 保持 `20260829_0015 (head)`；本轮无迁移。部署前后聚合保持 `155/3/5/21/85/169/1/1/2/1/1/2/897/1010/0`，最新知识库为 `succeeded/213/1006`，账号对象清理 Outbox 为 0。
- 部署前 PostgreSQL 17 快照 `/tmp/pnx-training-before-help-delete-20260829T141903Z.dump` 为 5,571,302 字节、0600、SHA-256 `40cfce14391d4e135a3d30a6c786be81df494a69affe9a56dbceb445df49bbd0`，314 项目录校验通过；它只适合作为本机短期恢复材料。
- 本轮未调用带认证的答疑或账号 DELETE，未触发飞书同步、上传或其他业务写入。首次 Compose 漏载根环境文件的容器未通过健康门，显式 `--env-file .env` 重建后恢复，数据库与 MinIO 未重建且数据聚合不变。
- 后端完整 280 项、Ruff/格式/153 源文件严格 Mypy，前端完整 23 文件/102 项、ESLint、严格 TypeScript 和主机/容器生产构建通过。

## 2026-08-29 管理员用户全量搜索源码候选基线

- 管理员 `/admin/users` 已从“固定加载前 100 条再本地过滤”改为后端全库搜索与固定每页 20 条分页；空搜索可逐页查看全部账号，页面展示当前页、总页数和准确匹配总数。页码限制为 1～10000，越界 URL 回到实际末页。
- `search`、`activity` 与 `page` 写入 URL 并在适用操作间保留；搜索覆盖姓名、邮箱、学号、中文/英文角色及状态，SQL LIKE 的 `%`、`_` 和反斜杠按普通文本转义。用户写入成功后按同一查询刷新，删除造成末页收缩时回退，避免筛选残留和 OFFSET 跳项。
- `GET /admin/users` 继续要求真实管理员权限，响应字段、角色/状态修改、禁用/恢复及已上线的两条账号 DELETE、高风险确认和最后管理员保护均未改变；本任务不新增数据库字段、索引或 Alembic 迁移。
- Backend 定向 33 项和本任务相关 Ruff/格式/严格 Mypy 通过；共享工作树完整复核另有 289 项通过、2 项范围外竞争赛测试失败。Frontend 定向 10 项与完整 23 文件/103 项、ESLint、严格 TypeScript 和生产构建通过。
- 验证只使用 Mock、静态 OpenAPI 和本地构建，未连接、读取或修改当前 PostgreSQL/MinIO，未调用运行环境 API。该候选尚未部署，当前运行态继续保持既有 `help-delete-20260829` 应用与 `20260829_0015 (head)` 数据库基线。

## 2026-08-29 管理员删除队伍源码候选基线

- 真实管理员可在队伍详情填写内部原因并二次确认删除。后端以队伍行锁、当前成员行锁、CSRF 与真实管理员依赖为边界：无团队提交时物理删除，有历史团队提交时释放全部当前成员并保留 `dissolved` 壳及不可变提交、评语和附件。
- 两种删除模式都从学生入口、常规管理员队伍列表和直接详情隐藏，并释放一赛一队占用；审计只记录目标 UUID、原状态、`physical/dissolved_retained` 模式、安全计数和内部原因，不包含成员身份、邀请码、正文、附件名或对象键。
- 本功能复用既有表、状态、外键和审计，无 Alembic 迁移或新依赖。后端定向 16 项与完整 291 项、Ruff、170 文件格式及 120 源文件严格 Mypy 通过；前端定向 9 项与完整 23 文件/104 项、ESLint、严格 TypeScript 和 Next.js 生产构建通过。
- 验证未连接当前 PostgreSQL/MinIO、未调用真实 DELETE、未访问 Docker socket，也未运行备份、镜像构建或部署命令。候选尚未部署，运行态继续保持 `help-delete-20260829` 与 `20260829_0015 (head)`。

## 2026-08-30 管理员用户全量搜索部署后基线

- 当前固定标签为 `admin-user-search-20260829`；Backend/Worker 镜像 ID 为 `sha256:8ce5a025653e05eeb2a42119cf0c20b4c258b76a82a39c8abeb24be607388880`，Frontend 为 `sha256:005345c40946bc33826565aebc8b441bc5f0600778384618042e6d885bec7be8`，应用均以 `appuser` 运行。
- 管理员用户页使用服务端全量搜索与固定每页 20 条分页，支持姓名、邮箱、学号、中文/英文角色和状态；URL 保留 `search/activity/page`，页码限制 1～10000，写后刷新和末页收缩回退已上线。
- 六服务 healthy、重启次数 0；登录与四个健康端点 200，`/admin/users` 匿名 307、用户列表 API 匿名 401。静态 OpenAPI 共 114 个路径，账号删除、管理员删除和答疑删除能力均保留。
- 部署前 OpenPGP 每日备份 `pnx-backup-20260829T155430Z-daily` 为 5,679,123 字节、0600，SHA-256 `525a53cef7bb08676b31598e9978a67a45df1301ca558587591e8e57438c2e4b`；完整 PostgreSQL dump 5,574,189 字节，通过内部校验和 PostgreSQL 17 目录检查。MinIO 相对周基线无对象变化。
- 本轮未运行 migrate，PostgreSQL/MinIO 容器与卷未重建；数据库按部署前记录保持 `20260829_0015` 基线。验收未使用管理员登录态、未读取用户列表、未调用任何业务写接口，四个应用容器日志错误关键词聚合为 0。
- 回滚镜像 `help-delete-20260829` 继续保留；应用回滚不需要数据库降级。完整周备份、每日增量归档与临时 GPG 密钥环均在本机 `/tmp`，必须迁移到受控独立介质并分离保存。

## 2026-08-30 管理员删除队伍部署后基线

- 当前固定标签为 `team-delete-20260830`；Backend/Worker 镜像 ID 为 `sha256:2d58004f482cefa3e01a3bd24877074fb72f496b8e9f3f067b484fcaf21efe97`，Frontend 为 `sha256:78fd991ced0d9fd308eba17c74cea4bd939fae78332d290aa1201610ee016015`，应用均以 `appuser` 运行。
- 本候选以 `help-delete-20260829` 运行基线只叠加队伍删除，明确未带入共享工作树中的管理员用户搜索/分页源码。真实管理员现在可按无提交物理删除、有提交保留 `dissolved` 壳的语义删除队伍。
- 六服务 healthy、重启 0；五个健康入口 200，匿名队伍 DELETE 401。管理员队伍 HTML 流响应为 200 骨架但携带 `/login` 的 307 redirect digest，受保护 API 为 401 且不返回业务数据。
- Alembic 为 `20260829_0015 (head)`；本轮无新迁移。PostgreSQL/MinIO 容器和卷未重建，部署前后 `157/1/2/2/0/2/0/897/1010/0` 聚合依次对应用户、赛事、队伍、当前成员、团队提交、版本、答疑、知识文档、知识媒体和账号清理 Outbox。
- 部署前 PostgreSQL 快照为 `/tmp/pnx-training-before-team-delete-20260829T161603Z.dump`，大小 5,574,204 字节、0600、SHA-256 `1ebc990cbec3023a54a4fe6672a37d446af2608efb09dc5f4135786866b1a301`，PostgreSQL 17 目录校验通过。
- 本轮未调用带认证的真实 DELETE 或其他业务写接口；隔离候选已清理。回滚使用 `help-delete-20260829` 且无需数据库降级。
- Docker socket 临时 `user:pnx:rw-` ACL 仍存在；非交互 sudo 要求密码，需部署方交互撤销并复核为基础 `root:docker 0660`。

## 2026-08-30 队伍删除与用户搜索合并部署后基线

- 当前固定标签为 `team-user-search-20260830`；Backend/Worker 镜像 ID 为 `sha256:0a3a88a7aeabed366b708695c867f0ee3bb6077bce05e441a8ed6fbc5041d2e3`，Frontend 为 `sha256:10552d3e6b750557e05d27527e06cac992091d7f80850f19c7a270a220d632f3`，应用均为 `appuser`。
- `team-delete-20260830` 曾从旧基线排除用户搜索，导致运行 Backend users 文件回退、Frontend API chunk 只传 `page_size=100`；这是用户仍只显示 100 个的根因。当前合并镜像已纠正，不是数据库计数问题。
- 运行 Frontend 编译 chunk 明确包含 `pageSize:20`、`page/search`、搜索/分页界面与队伍删除；Backend 静态 OpenAPI 为 114 个路径，`page.maximum=10000`，队伍、账号和答疑删除路径均保留。
- 六服务 healthy、重启 0；登录与四健康端点 200，管理员用户页匿名 307、用户 API 匿名 401。Backend、Worker、Frontend、Nginx 错误关键词聚合均为 0。
- 纠正发布未运行 migrate，PostgreSQL/MinIO 容器和数据卷未重建；数据库保持既有 `20260829_0015` 基线。最近队伍发布前数据库备份的 0600、SHA-256 与 PostgreSQL 17 目录已重新校验。
- 验收未使用管理员 Session/Cookie、未读取用户列表、未调用删除、同步、上传、认证或其他业务写接口。Docker socket 临时 ACL 与本机 `/tmp` 备份持久化风险仍待部署方收尾。

## 2026-08-30 持久登录与同源 IP 绑定源码候选基线

- 登录页、API 与 Session 服务已实现默认关闭的 `remember_me`：普通登录为浏览器会话 Cookie；主动记住时 Session/CSRF Cookie、空闲期和绝对期最长 30 天，并在个人/管理员会话列表显示 `remembered`。
- 持久会话以原始 Session token 为 HMAC key 绑定 Nginx 覆盖转发头后的规范化精确来源 IP；数据库仅保存 64 位 `ip_binding_hash` 和既有网段摘要。不同 IP 会立即撤销，相同 IP 无 Cookie 仍为 401，不存在 IP-only 用户查询或认证路径。
- 新迁移 `20260830_0016` 只为 `sessions` 增加可空列，历史 Session 保持 `NULL`。后端定向 70 项、完整 299 项、Ruff、171 文件格式、153 源文件严格 Mypy，以及前端 23 文件/105 项 Vitest、ESLint、严格 TypeScript 和生产构建均通过。
- 本候选没有连接、迁移或修改当前 PostgreSQL/MinIO，没有构建或部署 Docker。运行应用继续为 `team-user-search-20260830`，数据库继续为 `20260829_0015`；部署前必须应用 `0016`，产生持久会话后回滚旧应用会停止绑定校验，应优先前滚。

## 2026-08-30 持久登录与同源 IP 绑定部署后基线

- 当前固定标签为 `persistent-login-20260830`；Backend/Worker 镜像 ID 为 `sha256:6851f9892b16bfb6f2b4436dceba8b58b93651163882226770fc5339b91e6dc3`，Frontend 为 `sha256:96544dc22467f4ba4b74d236d9474bc1bfeb50b133c89cb695aa9cc3bf72424b`，应用均为 `appuser`。
- 生产 Alembic 为 `20260830_0016 (head)`；`sessions.ip_binding_hash` 是可空 `varchar(64)`，历史 Session 保持 NULL。隔离 `0015 ↔ 0016` 往返和生产 `0015 → 0016` 均通过，`alembic check` 无漂移。
- 六服务 healthy、重启 0；登录和四健康端点 200，匿名会话管理页/API 为 307/401。运行 OpenAPI 共 114 条路径，`remember_me` 默认 false，Session `remembered` 为 boolean。
- 部署前 OpenPGP 每日备份 `pnx-backup-20260830T045545Z-daily` 为 5,682,620 字节，完整 PostgreSQL dump 为 5,578,815 字节；外层/内部校验和 299 项目录通过，MinIO 2,885 个对象无本次 payload 或删除变化。
- 生产全表行数聚合哈希迁移前后均为 `6a44c75dea0d9e822c8ea06169f8c76d6a529a249ad1e33644dad20d53274c05`；PostgreSQL/MinIO 容器与卷未重建，隔离和 migrate 临时资源已清理。
- 验收未使用真实账号、Session 或 Cookie，也未调用登录、删除、同步、上传或其他业务写接口；六服务新验收窗口无异常日志。
- 旧 `team-user-search-20260830` 镜像保留，但旧 Backend 会忽略 IP 绑定列；产生持久会话后应用回滚前应先撤销绑定 Session，正常处置优先前滚。
- 加密归档与临时 GPG 私钥仍同机位于 `/tmp`，必须迁移并分离保存；Docker socket `user:pnx:rw-` ACL 因交互式 sudo 密码要求尚未撤销。

## 2026-08-30 持久登录跳转热修复后基线

- 当前固定标签为 `persistent-login-ip-forwarding-20260830`；Frontend 镜像 ID 为 `sha256:77dbfdec8659b82308eb159f2e48cdb2cb217974731eb4e080d4b83ffda90734`，Backend/Worker 继续运行既有 `sha256:6851f9892b16bfb6f2b4436dceba8b58b93651163882226770fc5339b91e6dc3`，应用均为 `appuser`。
- Next.js Server Component 直连 Backend 时会同时转发当前 Cookie 与 Nginx 覆盖清洗的单值来源 IP；缺失时不伪造。Nginx 继续覆盖客户端 `X-Forwarded-For`，Frontend 不发布宿主端口。
- 六服务 healthy、重启 0；五健康入口 200，匿名会话页/API 为 307/401。生产 Alembic 保持 `20260830_0016 (head)`，本轮未迁移，PostgreSQL/MinIO 容器与卷未重建。
- Frontend 完整 24 文件/107 项 Vitest、ESLint、严格 TypeScript、主机及镜像内生产构建通过；隔离假 Backend 与运行编译产物验证可信来源 IP 透传，新日志窗口无异常。
- 已被旧错误路径撤销的持久 Session 不会自动恢复，用户需重新勾选登录一次。`/tmp` 备份/私钥和 Docker socket ACL 遗留风险不变。

## 2026-08-30 学生知识库飞书入口关闭部署基线

- `/knowledge` 已按有效视图区分来源链接：真实学生和管理员学生视图不显示标题原文入口、未映射飞书文档链接或附件失败回退；真实管理员普通视图保留排障入口。
- 当前成功快照内显式文档 mention 继续站内切换；已本地化块附件和富文本内嵌文件继续通过 `/api/v1/knowledge/assets/{id}/content` 鉴权下载，失败附件在学生侧显示“暂不可下载”。
- 新增 ADR-046，更新 KB-002、KB-003、KB-005、KB-007、KB-008 相关页面/API/安全/测试说明；同步层既有来源与回退元数据保持兼容。
- 部署时发现 `/knowledge` 鉴权与其他受保护读取并发导致匿名登录回跳竞速，已调整为先执行 `requireUser("/knowledge")`，并新增鉴权前不得发起其他读取的回归。
- 最终知识库定向 2 文件/12 项、完整前端 25 文件/111 项 Vitest、ESLint、严格 TypeScript 和镜像内 Next.js 生产构建通过。
- 当前固定标签为 `knowledge-student-links-20260830`，Frontend 镜像为 `sha256:a67211cda8d65afeb34bbdde630609cd7c50aff974cc99ddbb9f6852ac26c652`；只替换 Frontend 并刷新 Nginx。Backend/Worker、PostgreSQL、MinIO 容器未替换，Alembic 保持 `20260830_0016 (head)`。
- 部署前后聚合保持 `users=158|knowledge_documents=1110|knowledge_assets=1027|account_cleanup=0`，最近同步保持 `succeeded|213|1020`、Outbox 保持 `sent|1`；未运行 migrate、未触发飞书同步或业务写入。


## 2026-08-30 问卷重新开启源码候选基线

- 真实管理员可把 `closed` 问卷重新开启并再次关闭；关闭卡片同时保留归档入口，`archived` 仍为终态。学生和管理员学生视图没有状态管理权限。
- 重新开启保留问题/选项、二维码 token、历史最新答案、累计提交次数、原时间窗口和提交上限；学生读取/提交继续同时校验 `open`、时间窗口与剩余次数。审计使用 `intention.reopen` 并只记录来源/目标状态。
- 本轮复用现有状态列与 `POST /admin/intentions/{survey_id}/open`，不新增 API Schema、数据库字段、Alembic 迁移或依赖。
- 问卷定向后端/API 34 项、前端 2 文件/10 项，完整后端 299 项、Ruff、153 文件格式、120 源文件严格 Mypy，完整前端 25 文件/112 项、ESLint、严格 TypeScript 和生产构建均通过。
- 源码候选阶段未连接或修改运行 PostgreSQL/MinIO，也未调用运行问卷状态接口；后续运行态部署结果如下。

## 2026-08-30 问卷重新开启部署后基线

- 当前固定标签为 `questionnaire-reopen-20260830`；Backend/Worker 镜像为 `sha256:f613c227e74b67b8c3f1257cb7dca2b2d80b2273168bad13df80ba923331e016`，Frontend 为 `sha256:35bed3d14aef08f213df7b14510c2623af5944d3639a3e2788175944a6d7bb75`，应用均以 `appuser` 运行。
- 六服务 healthy、重启 0，五个健康入口为 200；问卷页面匿名为 307，问卷管理与学生 API 匿名为 401。运行 Backend/Frontend 标记确认重新开启能力及持久登录、来源 IP 转发、用户搜索、删除、知识库附件和 KaTeX 等既有能力同时存在。
- 未运行 migrate，Alembic 保持 `20260830_0016 (head)`；PostgreSQL/MinIO 容器 ID 为 `bfa750f66ab0…`、`331150f34f37…`，未重建容器、卷或网络。
- 部署前后 `users=158`，问卷五表 `3/5/21/91/181`、状态 `archived:2,open:1`，知识库 `1110/1027`、账号清理 Outbox `0`、最近同步 `succeeded|213|1020` 与同步 Outbox `sent|1` 均不变。
- 验收未携带认证信息调用真实问卷写接口，未触发飞书同步或其他业务写入；部署窗口四个应用服务日志无异常。最新 5,682,620 字节加密备份的 0600 与 SHA-256 校验仍有效，`/tmp` 与 Docker socket ACL 遗留风险不变。

## 2026-08-30 问卷三种范围邮件源码基线（未部署）

- 当前工作树已实现真实管理员在开放填写窗口内选择手动成员、一个激活技术组或全部激活学生发送问卷邮件。技术组/全部范围由后端在发送时查询权威激活学生，三种范围同一 revision/成员只入队一次，重新开启后可再次显式发送；邮件只含称呼、标题和站内链接。
- 功能复用既有 `outbox_jobs`、Worker、8 次退避、dead 列表和人工重试，无新依赖或迁移；运行环境仍保持上一节 `questionnaire-reopen-20260830` 部署基线，本轮没有调用真实 SMTP 或写入运行数据库。
- 后端意向/API 契约定向 48 项、完整 315 项、Ruff 及 171 文件格式检查、120 个源文件严格 Mypy 通过；前端问卷定向 12 项、完整 25 文件/115 项、ESLint、严格 TypeScript 和生产构建通过。

## 2026-08-30 问卷三种范围邮件部署后基线

- 当前固定标签为 `questionnaire-email-scopes-20260830`；Backend/Worker 镜像为 `sha256:af1d520399115abad815f84100c5e34c961a29003087d3088eccf54eb7106cbd`，Frontend 为 `sha256:8d4ba40349833834a713a6af4b5ea90c572343dd26e6ab58a9d78aeef75e75fe`，应用均以 `appuser` 运行。
- 六服务 healthy、重启 0，五个健康入口为 200；问卷页面匿名为 307，管理/学生问卷 API 与匿名邮件 POST 为 401。运行 OpenAPI 为 115 条路径且 `recipient_scope` 枚举为 `manual/direction/all`，Frontend 产物包含三范围及全部既有能力标记。
- 未运行 migrate，Alembic 保持 `20260830_0016 (head)`；PostgreSQL/MinIO 容器 ID 仍为 `bfa750f66ab0…`、`331150f34f37…`，未重建容器、卷或网络。
- 部署前后 `users=160`、问卷五表 `3/5/21/92/183`、状态 `archived:2,open:1`、知识库 `1110/1027`、最近同步 `succeeded|213|1020` 和 Outbox 聚合均不变；`intention_open_email` 与 `delete_account_object` 均为 0。
- 验收未携带管理员登录态或调用真实业务写接口，未触发 SMTP/飞书；自 `2026-08-30T14:56:57Z` 起四个应用容器错误关键词匹配为 0。最近加密备份与新增 6,838,808 字节 PostgreSQL 17 快照均已校验；同机 `/tmp` 恢复材料和 Docker socket ACL 遗留风险不变。

## 2026-08-31 管理端删除可见性源码候选基线（未部署）

- 通知/作业已用 `deleted_at` 区分手工归档和已删除归档：常规管理列表/详情排除删除标记，手工归档仍可读取并继续删除；已发布删除与手工归档首次删除均写脱敏审计，重复 DELETE 幂等。
- 新迁移 `20260831_0017` 从成功 archive 模式删除审计回填历史通知/作业，约束删除标记只能用于 `archived`；提醒、邮件、受众快照、提交、不可变版本、评语、优秀标记、附件与审计继续保留。
- 通知归档页只显示“删除通知”，删除成功返回管理列表；作业归档删除入口保持。完整后端 320 项、Ruff/格式、严格 Mypy，以及完整前端 25 文件/116 项、ESLint、严格 TypeScript 和生产构建通过。
- 独立 PostgreSQL 的 `0016 → 0017 → 0016 → 0017` 往返与历史回填区分通过，临时容器已清理。源码阶段未连接或修改生产 PostgreSQL/MinIO、未调用真实 DELETE；后续部署结果如下。

## 2026-08-31 管理端删除可见性部署后基线

- 当前固定标签为 `admin-content-visibility-20260831`；Backend/Worker 镜像为 `sha256:589290276cd2ab01b283dc227e3effffe9548df4235a8965fa2c2f3c97145772`，Frontend 为 `sha256:8d5ea4a60f04cbf7be44b22b438a1a5c60aef40a0ebf37cf6786ceec2fca116b`，应用均以 `appuser` 运行。
- 生产 Alembic 为 `20260831_0017 (head)`；两表可空 `deleted_at` 与“非空必须归档”检查有效。生产历史内容删除审计为 0，故两条归档通知和一条归档作业仍保持手工归档语义、可进入管理详情继续删除。
- 六服务 healthy、重启 0；登录及正式健康入口为 200，管理页面匿名 307、管理 API 和虚假 UUID DELETE 匿名 401。运行 OpenAPI 115 条路径，删除过滤/幂等和 Frontend 新旧能力标记齐全。
- PostgreSQL/MinIO 容器 ID 与卷未变化；核心业务聚合保持一致。问卷窗口内有正常外部提交及成功审计，部署未携带认证信息调用真实 DELETE 或其他业务写接口；四个新应用容器严重错误关键词为 0。
- 部署前加密备份 `pnx-backup-20260831T054111Z-daily` 为 99,897,873 字节、0600，SHA-256 `06f7a4657cf53cabdb7c18fe59d1b16974b0d9ad8a31aa0701afc8fa1b1f525b`，PostgreSQL 17 目录和 MinIO 摘要校验通过。备份/私钥同机 `/tmp` 与 Docker socket ACL 仍待部署方收口。

## 2026-08-31 培训知识库阅读与目录文件源码基线（未部署）

- ADR-049 部分替代 ADR-034 的目录树内部状态：无当前文档时仅展示根层条目且根文件夹保持收起，显式进入文档后祖先链自动展开并滚动定位，切换后旧自动路径收缩，历史返回首页后恢复根层收起视图；目录栏整体开合、系统主导航成功折叠、右侧本文目录 sticky 高亮和移动端目录不变。
- 飞书目录 `obj_type=file` 独立文件通过 `knowledge_nodes.asset_id` 复用既有附件校验、MinIO 与 `/knowledge/assets/{id}/content`；授权同时接受最新成功快照的文档资源关联和独立文件节点关联，失败节点不生成飞书下载链接。
- 图片点击在当前页可访问模态预览，连续图片按容器宽度自动并排/换行；没有新增依赖。
- 源码 Alembic head 为 `20260831_0018`，生产仍为 `20260831_0017`。旧成功快照不会原地获得独立文件资源；部署迁移后须由真实管理员手动成功同步。downgrade 会把 `file` 转回 `unsupported`、删除节点资源关联但保留 MinIO 对象。
- 完整后端 322 项、Ruff、173 文件格式、153 源文件严格 Mypy，完整前端 25 文件/118 项、ESLint、严格 TypeScript和 Next.js 生产构建通过；未连接运行 PostgreSQL/MinIO，未迁移、同步或部署。

## 2026-08-31 培训知识库阅读与目录文件部署后基线

- 当前固定标签为 `knowledge-directory-media-20260831`；Backend/Worker 镜像为 `sha256:77f58286fe7434a970d9656f8a5801ce470af628745e992f513dffb69cb2796f`，Frontend 为 `sha256:f523e338e44c0788fb61c1f8378f73940f1bdc00d907a8a1ef770dfbe3883e65`，应用均以 `appuser` 运行。Backend 源码/迁移在镜像内为只读可遍历，常驻用户和备份宿主降权 UID 均可导入。
- 生产 Alembic 为 `20260831_0018 (head)`；112 个历史 `unsupported:file` 节点已转为 `file:file`，目前 `asset_id` 全为空，可空 UUID 列、资源外键和索引有效。旧应用不识别 `file`，回滚必须先受控降级到 `0017`，不能只换旧镜像。
- 六服务 healthy、重启 0；登录和四个健康入口、Frontend 内部健康均为 200。知识库页面匿名为 307 且保留 `next=/knowledge`，目录 API 和虚假资源下载匿名为 401；PostgreSQL/MinIO 容器与卷未重建。
- 运行 Frontend 产物包含目录活动项跟随、图片页内浮层/关闭、不可下载状态、缩放光标与 `flex-wrap`；运行 Backend OpenAPI 为 115 条路径并包含 `file` 和受保护资源下载。
- 迁移前后全表行数哈希均为 `65b142a35e7e3a73dc49743a8978943d4910544312bde9951c0b3148ff4a585f`；知识库文档/资源/节点保持 1327/1064/1603，Outbox `dead/pending/sent=23/1/400`，部署未使用真实登录态、未触发飞书同步或其他业务写入，四个应用容器严重错误关键词为 0。
- 部署前加密备份 `pnx-backup-20260831T073443Z-daily` 为 99,901,190 字节、0600、SHA-256 `a337e786920638b30224317155f76029f69afd25717df61b26e705d3167c3a00`；完整解密、内部校验、PostgreSQL 17 的 314 项目录和 MinIO 摘要通过。
- 目录文件下载仍需真实管理员在 `/admin/knowledge` 手动完成一次成功同步；失败同步不覆盖旧快照。备份/临时私钥同机 `/tmp` 与 Docker socket `user:pnx:rw-` ACL 仍待部署方迁移和交互撤销。

## 2026-08-31 知识库默认根层视图前端热修基线

- 无有效 `?doc` 的知识库首页不再自动读取第一篇文档，正文显示选文档空状态，目录只展示根层条目且所有根文件夹保持收起；显式打开文档时只展开祖先链并滚动定位，切换后旧路径收缩，历史返回首页后清空正文并恢复根层收起视图。
- 页面/组件定向 16 项与完整前端 25 文件/120 项 Vitest、ESLint、严格 TypeScript、主机及镜像内生产构建通过；镜像依赖审计 0 漏洞，隔离候选以 `appuser` 运行且 `/health=200`。
- 当前固定标签为 `knowledge-root-view-20260831`。Frontend 镜像为 `sha256:9a76b96ca85d67a0364cf939fd5528bbfb42b6d4633d143b75a61ad2443b811f`；Backend/Worker 继续运行 `sha256:77f58286fe7434a970d9656f8a5801ce470af628745e992f513dffb69cb2796f`，同名 Backend 标签只作别名。仅 Frontend/Nginx 被替换，Backend、Worker、PostgreSQL、MinIO 容器 ID 保持不变。
- 六服务 healthy、重启 0，登录和五个健康入口为 200；知识库页面/API/虚假资源下载匿名为 307/401/401，Alembic 保持 `20260831_0018 (head)`。本热修无数据迁移、飞书同步或业务写入，目录独立文件下载、图片页内浮层和连续图片自适应布局不变。
- 最近加密备份 `pnx-backup-20260831T073443Z-daily` 的 0600、99,901,190 字节和 SHA-256 `a337e786920638b30224317155f76029f69afd25717df61b26e705d3167c3a00` 已再次复核；同机 `/tmp` 恢复材料与 Docker socket 临时 ACL 风险仍待部署方收口。

## 2026-08-31 知识库目录文件端点与图片序列修复部署后基线

- 当前固定标签为 `knowledge-file-gallery-fix-20260831`；Backend/Worker 镜像为 `sha256:2b1c9079e5dc9f2079acdb063cd7a0e2d88c52c68be045a346f180054d692141`，Frontend 为 `sha256:a5ad5927756819aeedbe4931b4921a60831d11fcaced9ea9530ded90f04446d3`，应用以 `appuser` 运行。
- 飞书正文图片/附件继续走 Drive `medias`，目录 `obj_type=file` 改为 Drive `files`；两者仍进入同一 350 ms 节流、安全检测、MinIO 与受保护授权链路。画廊跨空段落和纯媒体容器分组，可见内容仍是边界。
- 六服务 healthy、重启 0，登录与五个健康入口为 200，知识库页面/API/虚假资源下载匿名为 307/401/401；Alembic 保持 `20260831_0018 (head)`，PostgreSQL/MinIO 容器和卷未重建。
- 部署前后聚合为 `users/runs/nodes/documents/assets/outbox=169/12/1836/1544/1064/430`。当前最新成功快照仍为旧代码生成的 217 篇/1,057 资源，16 个文件节点全部无关联；必须由真实管理员再手动成功同步完成最终验收。
- 新备份 `pnx-backup-20260831T102419Z-daily` 为 101,156,599 字节、0600、SHA-256 `e3a7ddf3ca640f8d825c3d763a0db938b3264fca21fced5894c216d8da8a1468`，外层/解密/内部/PostgreSQL 17 恢复目录验证通过。同机 `/tmp` 恢复材料与 Docker socket `user:pnx:rw-` ACL 风险不变。
