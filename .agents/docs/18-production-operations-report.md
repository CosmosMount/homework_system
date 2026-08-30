# 生产运维与故障恢复验收报告

## 范围与结论

本报告记录阶段 6 在隔离 Docker Compose 项目中的生产配置、组件故障、加密备份、恢复、迁移、发布和安全验收，对应 NFR-001、NFR-007～NFR-012 和 NFR-T01、NFR-T07～NFR-T12。性能与容量数据单独见 `17-capacity-performance-report.md`。

验收结论：仓库已具备固定 Alpine 镜像、HTTPS 单入口、最小权限与资源限制、机器可读健康/告警、OpenPGP 加密备份、MinIO 每日真实增量、隔离链式恢复、只读引用对账及发布/回滚工具。依赖、秘密、镜像和生产配置安全门全部通过，空库迁移往返、三浏览器流程、正式发布脚本和局域网 5000 入口均完成验证。演练没有操作 `pnx-training`；生产域名、受信证书、校园 SMTP、异机加密备份目标和独立告警接收方仍须部署方提供，不能用本次临时 CA 和本机目录替代现场材料。

## 隔离环境

- 生产配置与故障项目：`pnx-stage6-config-ewchca`，临时域名 `stage6.local`，HTTPS 仅绑定 `127.0.0.1:58443`。
- 增量恢复项目：`pnx-restore-incremental-ewchca`，使用全新 PostgreSQL/MinIO 卷，不发布主机端口。
- 最终空库迁移项目：`pnx-stage6-final-migration`，使用全新 PostgreSQL 卷，不发布主机端口。
- 生产配置只允许 Nginx 发布 HTTP/HTTPS；Frontend、Backend、Worker、PostgreSQL、MinIO API 与 MinIO Console 均无主机端口。
- 临时证书、测试 GPG 密钥、随机应用秘密和虚构数据只存在于权限受限的 `/tmp` 演练目录，不进入仓库或报告。
- 验收结束后，`pnx-stage6-config-ewchca`、`pnx-restore-stage6-ewchca`、`pnx-restore-incremental-ewchca`、`pnx-stage6-e2e`、`pnx-stage6-performance` 和 `pnx-stage6-final-migration` 的容器、网络及 11 个数据卷均已删除。

## 五组件故障演练

演练时间为 2026-08-25。每次只停止一个目标容器，记录 HTTPS 与独立健康状态，目标完全恢复后才进入下一项。

| 故障组件 | 故障观测 | 用户影响 | 恢复结果 |
| --- | --- | --- | --- |
| Frontend | `/login` 为 `504`；Backend live/ready 与 Worker 均为 `200` | 页面不可加载；API 与异步任务仍可用 | 启动后容器健康，`/login` 恢复 `200` |
| Backend | `/login` 仍为 `200`；`/health/live`、`/health/ready` 为 `504`，经 Backend 暴露的 Worker 路径为 `502`；Worker 容器自身健康 | 已加载静态页面仍可显示，动态 API 全部不可用；Worker 继续运行 | 启动后 live/ready 均恢复 `200` |
| Worker | 停止后页面和 Backend ready 保持 `200`；最后心跳年龄 291 秒时仍为 `200`，321 秒时转为 `503 STALE_HEARTBEAT` | 同步业务可用；邮件、定时发布、阶段推进和清理延迟 | 启动后立即写入新心跳，端点与容器恢复健康 |
| PostgreSQL | `/login` 与 Backend live 为 `200`；Backend ready 和 Worker 健康立即为 `503`，错误只标记 PostgreSQL 不可用 | 动态业务与异步任务不可用，静态页面仍可加载 | 启动后 PostgreSQL、Backend ready 和 Worker 均恢复健康 |
| MinIO | 页面、Backend live/ready 与 Worker 均为 `200`；`/storage/minio/health/live` 超时且无 HTTP 响应 | 上传和下载不可用，普通数据库读取继续 | 启动后对象路径与 Backend ready 均为 `200` |

结论：健康入口能区分进程存活、数据库就绪、Worker 心跳和对象存储；故障边界与 `10-deployment-network.md` 一致。Worker 的 5 分钟心跳阈值属于明确容错窗口，不是即时容器探测的替代，机器检查同时读取容器状态。

## MinIO 每日增量设计

- 周备份生成完整对象负载、完整对象清单和当日 PostgreSQL 自定义格式快照。
- 日备份仍生成当日 PostgreSQL 快照，但 MinIO 只携带相对当前周基线的新增/变化对象与删除集合，同时保存当日完整对象清单。
- 日清单记录周备份 ID 和周对象清单 SHA-256。脚本还验证周加密归档、外部校验和与成功元数据；任一缺失即失败。
- 周基线清单状态只保存在与备份输出分离的宿主机本地 `0700` 目录。状态不含原文件名、用户、邮箱或内容，且不构成可独立恢复备份。
- 保留脚本默认 dry-run，并保护仍被保留日备份引用的周基线。
- 日恢复先验证和导入周完整基线，再校验基线桶、应用变化/新增与删除，最后以日完整清单和数据库文件记录执行两层对账。

该方案对应 ADR-019。每日是相对当前周完整基线的累计增量，因此任一日备份只依赖一个周备份，不会因删除较早日备份而断链。

## 真实备份与恢复结果

| 项目 | 结果 |
| --- | --- |
| 周完整备份 | `pnx-backup-20260825T004550Z-weekly`；1 个对象；对象负载 4,096 B；归档 27,803 B；耗时 4 秒 |
| 日增量备份 | `pnx-backup-20260825T004905Z-daily`；目标清单 2 个对象、4,128 B；实际增量仅 1 个对象、32 B；归档 23,418 B；耗时 4 秒 |
| 增量基线 | 日备份明确引用上述周备份；基线归档、外部 SHA-256、元数据和对象清单哈希全部验证 |
| 隔离恢复 | 目标 `pnx-restore-incremental-ewchca`；自动恢复周基线和日增量；2 个对象；RPO 31 秒；RTO 13 秒 |
| 恢复后对账 | 数据库文件 2、`available` 2、MinIO 对象 2；缺对象、大小不符、SHA-256 不符、未追踪对象均为 0 |
| 保留策略 | 真实目录 dry-run 成功；单元执行证明超过数量阈值但仍被保留日备份引用的周基线不会删除 |

演练数据全部虚构。RPO/RTO 远低于 24 小时/4 小时目标；现场结果仍受真实数据量、备份介质和网络影响，每学期必须在生产规模副本重跑。

## 标准备份流程

1. 确认 Worker 无异常积压、PostgreSQL/MinIO 健康、备份目标和本地状态目录空间充足。
2. 每周维护窗口设置 `BACKUP_KIND=weekly` 运行 `infra/backup/backup.sh`；成功后脚本才原子更新本地周基线状态。
3. 其他日期设置 `BACKUP_KIND=daily` 运行同一脚本；若没有有效周基线，先排查并执行周完整备份，不得绕过失败。
4. 检查外部 `.meta.json` 的 `status`、`object_backup_mode`、基线 ID、对象总量、实际负载量、删除量和耗时，再把 `.tar.gpg`、`.sha256`、`.meta.json` 成套发送到异机加密备份目标。
5. 运行 `infra/backup/retention.sh` dry-run 审查选集，确认后才设置 `RETENTION_APPLY=YES`；不得手工删除被引用周基线。

## 标准恢复流程

1. 创建全新、明确命名为 `pnx-restore-*` 的隔离 Compose 项目和空数据卷，使用相同或兼容固定镜像。
2. 设置目标 `.tar.gpg` 的绝对路径和同目录周基线归档；显式设置 `RESTORE_CONFIRM_PROJECT`，运行 `infra/backup/restore.sh`。
3. 脚本自动验证归档、解密、恢复数据库与对象、检查 Alembic head，并运行只读 `reconcile-storage`；任一步失败均不得把隔离环境切换为生产。
4. 启动完整隔离栈，使用虚构管理员验证登录、通知、提交、评语、优秀作业和下载；记录 RPO/RTO 与异常。
5. 生产灾难恢复需要单独的变更批准、流量切换和旧环境封存，不得把 `restore.sh` 直接指向现有生产项目。

## 容量与发布边界

- 100 会话读取 P95 为 341.754 ms、错误率 0%，满足 P95 小于 500 ms、错误率低于 1%；详细机器、数据集与上传结果见容量报告。
- Backend 使用 4 个 Uvicorn Worker；每进程 PostgreSQL 连接池为 `8+4`，Backend 生产上限为 4 CPU/1 GiB。
- 发布脚本要求固定镜像、有效加密备份门、迁移、健康等待和 HTTPS 冒烟；回滚只切换镜像，不盲目恢复旧数据库，也不自动执行 Alembic 降级。

## Connect 邮箱与初始管理员增量验收

2026-08-25 在阶段 6 发布候选之上完成认证引导更新。应用保持 `student`/`admin` 两角色，所谓“超级管理员”由空系统首个完成邮箱验证的 `admin` 和最后管理员保护共同表达。

- 隔离 PostgreSQL 完成 `base → 20260825_0006 → 20260825_0005 → 20260825_0006`；产生 Connect 账号后降级按设计拒绝并保持 0006。
- 两个真实并发邮箱验证请求均返回 200，数据库最终为一个 `active admin`、一个 `active student`、一条 `user.initial_admin_granted` 审计和两个已消费令牌，证明事务级 advisory lock 生效。
- 开发 `pnx-training` 已从 0005 升级为 0006 并重建应用入口；虚构 Connect 注册检查返回 201、旧域名返回 400，测试账号和未投递邮件任务已清理。

## 唯一账号管理员增量部署

- `20260825_0007` 已应用到开发 `pnx-training`；Backend、Worker、Frontend 和 Nginx 使用根目录 `.env` 重建，运行镜像 ID 与本次构建标签一致，六个常驻服务全部健康。
- `127.0.0.1:5000` 的 Nginx、Backend ready 和 Worker 健康返回 200；管理员新建作业、个人资料和登录人员页面匿名访问返回 307，管理员会话 API 返回 401 而不是 404。
- 部署前后用户聚合均为 21 行：5 个 `admin`、16 个 `student`。数据库不满足“用户表恰好一行”，因此迁移只推进 Alembic head，没有授予角色、撤销 Session 或写 `user.single_account_admin_granted`；未删除历史账号。

## 历史 Smoke 数据清理与唯一管理员

2026-08-25 经用户确认执行开发环境维护清理。目标账号在清理前未拥有通知、作业、赛事、队伍、提交或文件数据，因此没有删除目标账号业务内容，也没有把历史创建者伪造为该账号。

- PostgreSQL 17 自包含备份位于 `/tmp/pnx-training-before-smoke-account-removal-20260825.dump`，权限 `0600`，大小 146,558 B，SHA-256 为 `0bea209172cd12ca3a2d7b0d50c511d6e980edd9664351fd9a26c239e27a9fe0`；必须使用 PostgreSQL 17 的 `pg_restore`，宿主机旧版本不能解析 1.16 归档。
- MinIO 三对象副本位于 `/tmp/pnx-training-minio-before-smoke-account-removal-20260825`，权限已限制；三个对象共 826 B，逐项 SHA-256 已核对。两类 `/tmp` 材料是临时恢复副本，重启或系统清理前如需长期保留必须迁移到受控加密备份位置。
- Backend 与 Worker 停止后，单事务删除 20 个 Smoke 账号、4 条通知、4 个作业、2 个赛事、5 支队伍、2 个提交、3 个正式版本、2 条评语、6 条文件记录、24 条非目标 Outbox 和两个 Smoke 分类；正式版本不可删除触发器只在事务内临时关闭并在提交前恢复。
- 审计日志和认证安全事件保留，已删除操作者外键置空；`yzhang367@connect.hkust-gz.edu.cn` 提升为唯一的已验证 `active admin`，1 个尚未撤销的旧 Session 被撤销，并新增 `maintenance.smoke_accounts_deleted` 与 `user.role_change` 两条审计。
- 数据库提交后精确删除私有桶中的 3 个已备份对象。最终 Smoke 业务表和 MinIO 对象均为 0，目标账号 7 条历史验证邮件 Outbox 保留，非目标 Outbox 为 0；Alembic 保持 0007。
- Backend 与 Worker 重启后六个常驻服务全部健康；5000 端口 Nginx、Backend ready 和 Worker 为 200，管理员页面匿名访问为 307，最近五分钟日志无严重错误。角色变化已撤销旧 Session，用户必须重新登录。

恢复时不得直接覆盖当前运行环境：先停止应用写入，在显式隔离 PostgreSQL 17 环境使用该 dump 恢复并核对用户/业务表，再把对象副本恢复到隔离 MinIO，完成引用对账与登录冒烟后才评估切换。

## 最终发布、安全与可用性门

| 门 | 结果 |
| --- | --- |
| 应用质量 | 当前增量门通过 Ruff/136 文件格式、100 源文件严格 Mypy、130 个后端测试；ESLint、严格 TypeScript、36 个前端测试和 Next.js 生产构建均通过；阶段 6 浏览器与安全门继续见下列记录 |
| 浏览器 | Chromium、Firefox、WebKit 共 12 个只读核心流程通过，3 个注册写入按矩阵跳过；独立 Chromium 注册写入 1 项通过 |
| 依赖 | `npm audit --audit-level=high` 与 `pip-audit --requirement requirements.lock --disable-pip` 均为 0 已知漏洞 |
| 秘密 | Gitleaks 8.30.1 扫描 1 个 Git 提交/756,444 B 和 Git 跟踪及未忽略候选树 2,481,244 B，均为 0；脚本不再以历史扫描替代未提交候选树扫描 |
| SBOM/镜像 | Backend 95 个包、Frontend 90 个包；固定 digest Alpine 3.23.5 前后端镜像 HIGH/CRITICAL 均为 0 |
| 生产配置 | Trivy 配置扫描识别 20 个配置文件，HIGH/CRITICAL 误配置为 0；生产 Compose 仍只有 Nginx 两个公开映射 |
| 空库迁移 | 全新 PostgreSQL 17 卷已覆盖到 `20260825_0007` 的迁移测试，最终为单一 head；有 Connect 数据时 0006 危险降级保护通过，0007 downgrade 按安全设计保留已授予管理员 |
| 阶段 6 正式发布 | `pnx-release-20260825T013516Z`；当时迁移前后均为 `20260825_0005`，固定候选镜像和 HTTPS 四入口冒烟通过 |
| 认证更新部署 | 开发 `pnx-training` 当前为 `20260825_0007`；历史 Smoke 数据已清理，只保留一个已验证 `active admin`，Backend/Worker 重启并通过健康检查 |
| 开发入口 | `127.0.0.1:5000` 的登录/live/ready/worker 和 `10.4.150.222:5000/login` 均为 200；六个 `pnx-training` 服务健康且仅 Nginx 映射 5000 |

最初失败报告使用了构建时间早于 Dockerfile/锁文件修复的 Debian `stage6-local` 镜像，因此 Frontend 报告 49 个 HIGH/CRITICAL；没有忽略这些结果。重新从当前固定 digest Alpine Dockerfile 构建前后端候选，并用同一最新 Trivy 数据库严格重跑后得到上述 0 结果。安全脚本同时去除了工具容器的 `HOME=/tmp` 复用：Trivy 使用显式缓存目录，Syft 关闭更新检查，Playwright 的 npm/XDG 缓存分别设置。

阶段 6 候选树秘密扫描契约加入后的完整测试为 112 项；Connect 初始管理员增量完成时为 115 项，唯一账号管理员保证完成时完整 Backend 为 130 项。认证隔离项目、容器、网络和临时 PostgreSQL 卷在证据采集后已删除；开发 `pnx-training` 已完成 0007 迁移和应用服务重建。

## 外部现场验收项

以下材料不在仓库中，部署方提供后才能完成现场最终验收：

- 稳定校内 DNS 与受信 CA 证书，以及续期与 30 天告警通道。
- 校园 SMTP 凭证和真实投递测试账号。
- 与业务盘物理或故障域分离的异机加密备份目标、OpenPGP 恢复私钥托管和定期解密演练。
- 不依赖本系统邮件的独立告警接收方。
- 学校的数据保留、审计留存和灾难恢复审批制度。

## 新激活学生作业受众增量部署

2026-08-27 为解决作业发布后新注册学生无法进入固定受众的问题，新增并应用 `20260827_0010` 数据迁移。

- 迁移前 `assignment_audience_users` 数据备份位于 `/tmp/homework_system_assignment_audience_before_0010_20260827.sql`，权限 0600，大小 960 B，SHA-256 为 `7032fb9c8a20ef044276a943e2ccebcbd28758a0f3f10c14459bc4c84ab6a920`。
- 隔离 PostgreSQL 17 使用两个虚构账号和一个开放作业完成 `0009 → 0010 → 0009 → 0010`，受众数量为 `0 → 1 → 0 → 1`；临时容器已删除。
- 首次运行库迁移因新脚本文件权限为 0600，在读取脚本、开启迁移事务前退出；数据库仍为 0009。修正为标准 0644、重建 Backend 镜像后再次执行成功。
- 运行库最终为 `20260827_0010 (head)` 且 Alembic 无模型漂移；`xluo799@connect.hkust-gz.edu.cn` 已加入“电控第一次作业”正式受众，目标人数从 0 变为 1。
- Backend、Worker、Frontend 和 Nginx 已重建重启，六个常驻服务 healthy，`live`、`ready`、`worker`、`nginx-health` 均为 200。

## 飞书知识库 0011 运行态部署

2026-08-27 已将飞书知识库源码、迁移和前端路由部署到开发 Compose 运行态。

- 前后端固定镜像构建成功，Next.js 生产构建包含 `/knowledge` 与 `/admin/knowledge`；Backend、Worker、Frontend 完成容器替换。
- 首次迁移容器在导入知识库模型前退出：新目录/文件为 `0700/0600`，复制到镜像后属主为 root，非 root `appuser` 无法读取。数据库未开启迁移事务并完整保持 `0010`；将源码修正为标准 `0755/0644` 后重建，迁移容器以退出码 0 完成。
- 运行数据库为 `20260827_0011 (head)`；Backend、Worker、Frontend、PostgreSQL、MinIO、Nginx 六个常驻服务 healthy，`live`、`ready`、`worker` 与 `nginx-health` 均返回 200。
- 匿名访问 `/knowledge` 和 `/admin/knowledge` 分别由登录守卫返回 307，匿名访问 `/api/v1/knowledge` 返回 401，证明新路由已生效且未绕过鉴权。
- 飞书配置已对齐为 App ID、App Secret 和 Wiki URL 三项；生产通过 secret file 注入同一个 App Secret，不再要求独立 Space ID 或 Root Token。
- 真实只读诊断已成功取得 tenant token，并从 URL 自动解析整个空间后读取 227 个节点；过程中未记录或输出秘密、token、Space ID、对象键和飞书原始响应。
- 本轮四个健康端点再次返回 200；Docker socket 当时需要交互式 sudo，因此该初版部署阶段未重复读取容器列表。首次完整同步随后由前台接管命令完成，并已核对 `succeeded` 状态、目录正文和真实媒体下载。

## 飞书知识库首次前台初始化与参考对齐

2026-08-27 为缩短首次上线等待，先停止常驻 Worker，使用内部运维命令接管唯一活动运行；命令不创建第二条运行或第二套公开接口，并继续使用现有数据库、MinIO、脱敏日志和原子快照规则。

- 前台初始化在约 32 秒内生成首个阶段性回退快照：228 个目录节点、212 个 Docx 目标、48 篇可读正文和 0 个首轮媒体。
- 恢复 Worker 后，原 `sync_knowledge` Outbox 幂等收敛为 `sent`；`live`、`ready`、`worker` 和 `nginx-health` 四个健康端点均为 200。
- 该 48 篇快照当时用于保证学生入口先可读，不作为全部 212 个 Docx 的最终完整验收；现已被后续完整成功快照自然替代。
- 用户随后要求同步办法与知识库内容区排布固定对齐参考仓库提交 `c28f8a0`。目录、正文或标题错误必须使整次运行失败；图片/白板单项失败跳过块，附件失败保留整篇飞书原文入口。
- 当时的页面参考契约是文档目录、位于正文左侧的本文目录和正文，不存在顶部文档切换栏；移动端使用右下目录按钮和全屏目录。该历史页面顺序已于 2026-08-28 被 ADR-033 替代，同步契约继续有效。
- 对齐保留登录鉴权、`AppShell`、成功快照、MinIO、管理员手动接口和常规 Worker，不复制公开静态站点或硬编码租户资源。
- 该阶段的文档与实现调整不涉及数据库迁移；完整结果记录如下。

## 飞书知识库参考对齐完整上线

- 2026-08-27 前台完整同步以 `succeeded` 完成 228 个目录节点、212 篇文档和 977 个成功媒体引用，耗时 `00:33:28.757715`；13 次允许的资源回退未阻断快照。
- 旧 48 篇阶段性快照已被新成功快照自然替代；Worker 恢复后最新 `sync_knowledge` Outbox 为 `sent`、`attempt_count=1` 且无错误，管理员手动更新接口继续保留。
- 29 项后端知识库定向测试、完整后端 213 项测试、前端 20 个文件/76 项测试及全部静态检查和生产构建通过；Backend/Worker 镜像为 `sha256:f8c42b…`，Frontend 为 `sha256:e82d020…`。
- Backend、Worker、Frontend、PostgreSQL、MinIO、Nginx 六服务 healthy；`live`、`ready`、`worker`、`nginx-health` 均为 200，`/knowledge`、`/admin/knowledge` 匿名访问为 307，两个知识库 API 匿名访问为 401。
- Alembic 保持 `20260827_0011`，本轮无迁移；定向热修镜像未纳入并行账号清理代码，账号清理工作树保持原样。


## 2026-08-28：知识库白色主题前端部署

- 仅修改知识库阅读器、知识块渲染器和知识库前端测试：页面改为白色主题，桌面顺序为左侧文档目录、中央正文、右侧本文目录；成功打开文档后左目录自动收起，失败不改变当前文档和目录状态。
- 知识库定向 7 项测试、完整前端 20 个文件/76 项测试、ESLint、严格 TypeScript、工作树与隔离源码的 Next.js 生产构建均通过。
- 隔离构建从上一版已上线知识库源码基线开始，目录差异审计只有 `knowledge-reader.tsx`、`knowledge-blocks.tsx` 和 `knowledge-ui.test.tsx`，未纳入并行账号活跃度/清理改动。
- Frontend 已替换为 `sha256:1842c4d63afecf672d3310eb3a4db1d6b2ed40b604cad71749fe584999ee51dc`，Nginx 已重启；六个常驻服务均 healthy，`live`、`ready`、`worker`、`nginx-health` 均为 200。
- `/knowledge`、`/admin/knowledge` 匿名访问为 307，`/api/v1/knowledge`、`/api/v1/admin/knowledge` 匿名访问为 401；最新知识库运行仍为 `succeeded|212|977`，Outbox 仍为 `sent|1`，证明本轮未触发新同步。
- Backend、Worker、PostgreSQL、MinIO、管理员手动同步接口和 Alembic `20260827_0011` 均未修改；本轮无数据迁移。


## 2026-08-28：知识库主导航折叠与本文目录跟随部署

- 用户澄清后新增 ADR-034：成功打开当前或其他文档时折叠系统最左侧主要导航，文档目录保持用户自己的展开状态；加载失败不改变两者。
- 右侧本文目录使用 `sticky top-6`、最大视口高度和内部滚动，页面滚动时以 `aria-current="location"` 高亮当前章节；阅读器祖先改用不阻断 sticky 的横向 clip。
- 文档目录、搜索框、目录标题栏、目录行、展开/收起按钮和移动目录弹层统一使用系统全局设计令牌、圆角、边框、阴影、悬停和键盘焦点样式。
- 知识库定向 8 项测试、完整前端 20 文件/77 项测试、ESLint、严格 TypeScript、工作树和隔离源码 Next.js 生产构建通过。
- 隔离构建以已上线白色知识库源码为基线，差异审计仅有 `app-shell-navigation.tsx`、`app-shell-events.ts`、`knowledge-reader.tsx` 和 `knowledge-ui.test.tsx`；未纳入并行账号活跃度/清理代码。
- Frontend 已替换为 `sha256:2ad76bd178810d82cf1d0b7d2d3517fa891998d949977e5514ecaff51ac1ed39`，Nginx 已重启；六服务 healthy，`live`、`ready`、`worker`、`nginx-health` 均为 200。
- `/knowledge`、`/admin/knowledge` 匿名访问为 307，`/api/v1/knowledge`、`/api/v1/admin/knowledge` 匿名访问为 401；最新同步仍为 `succeeded|212|977`，Outbox 仍为 `sent|1`。
- Backend、Worker、PostgreSQL、MinIO、管理员手动同步接口和 Alembic `20260827_0011` 均未修改；本轮无迁移且未重新同步飞书。


## 2026-08-28：意向调查创建 500 修复部署

- Backend 日志定位为 `intention_options.survey_id` 外键失败：创建服务将父调查和选项同时加入 Session，ORM 实际先插入选项。失败事务已自动回滚，没有半成品调查。
- 服务层在加入父调查后显式 `flush()`，再加入选项并提交；父子记录仍处于一个原子事务，不改变 API、Schema、数据库结构或 Alembic 迁移。
- 意向调查定向 10 项、隔离源码完整后端测试、Ruff、146 个 Python 文件格式检查和 146 个源文件严格 Mypy 通过。真实运行 PostgreSQL 冒烟成功写入父调查和两个选项，随后回滚外层事务；测试调查和审计记录均为 0。
- 隔离构建基线为当前 HEAD，只叠加 `backend/app/intentions/service.py` 和 `backend/tests/test_intentions.py`，未纳入并行账号活跃度/清理改动。临时构建上下文已统一为非 root 用户可读权限，最终镜像正常读取应用和 Alembic 配置。
- Backend 与 Worker 已强制重建为同一镜像 `sha256:409a55ff76ad6d75e03c20c254f042f6424a60c99a649363ed3d06b8bc1b3d69`；Frontend、PostgreSQL、MinIO 和 Nginx 未重建。
- 六个常驻服务均 healthy，`live`、`ready`、`worker`、`nginx-health` 经 `127.0.0.1:5000` 均返回 200；容器内 `alembic current` 为 `20260827_0011 (head)`，部署后 Backend/Worker 最近日志无新外键、权限或启动异常。

## 2026-08-28：账号活跃度与多题实名问卷运行态部署

- 从已通过完整质量门的提交 `60b8fe9` 构建并部署固定标签：Backend/Worker `pnx-training-backend:questionnaire-account-20260828`（`sha256:8253599decbfb1e89dcb8a623d29f942ace011947f6b292588c0dfa5f4e45395`），Frontend `pnx-training-frontend:questionnaire-account-20260828`（`sha256:1252a6799ff1b034680317fafbaf4e9131ddea073ffd41628f9e0ac1e145a85b`）。两镜像均以 `appuser` 非 root 运行。
- 迁移前 PostgreSQL 17 自定义格式备份为 `/tmp/pnx-training-before-questionnaire-0013-20260828T132500Z.dump`，权限 `0600`、大小 4,141,766 B、SHA-256 `5a3c6354bb47f3f8f5d3bd2739c5bd69127462388c8945f6b75e34561c037e31`；已使用 PostgreSQL 17 `pg_restore --list` 校验。该 `/tmp` 文件是临时恢复材料，如需跨主机重启保留必须迁移到受控加密备份位置。
- 生产备份恢复到专用隔离 PostgreSQL 17 后，真实执行 `0011 → 0012 → 0013 → 0012 → 0013`；1 份旧调查、3 个选项、2 份回答和 2 条选择关系往返后数量一致，无孤立选项。隔离容器、匿名卷和网络已删除。
- 运行库在停止 Nginx、Frontend、Backend 和 Worker 后完成 `0011 → 0012 → 0013`；Alembic 为 `20260828_0013 (head)` 且 `alembic check` 无模型漂移。旧调查迁为 ID 与调查相同的兼容问题，标题一致；两份旧回答的 `submission_count` 范围为 1～6。迁移未执行任何账号删除。
- Worker 停止时超过 30 秒宽限期并以 137 退出；数据库连接随进程终止释放。新 Worker 启动后健康，无最近一小时 processing/retry Outbox，四个新应用服务最近十分钟日志无错误匹配。
- Backend、Worker、Frontend、PostgreSQL、MinIO、Nginx 六服务均 healthy；`live`、`ready`、`worker`、`nginx-health` 为 200。`/intentions`、`/admin/intentions`、`/admin/users` 匿名访问为 307，学生问卷、管理员问卷和实名名单 API 匿名访问为 401。运行 Frontend 编译包包含问卷管理、提交名单、提交次数与账号活跃度界面。
- 最近成功知识库快照保持 212 篇文档、986 个媒体引用，最新同步 Outbox 保持 `sent`、`attempt_count=1`；本次未触发飞书同步。现有 6 条验证邮件和 4 条历史知识库 `dead` Outbox 未被本次部署修改。
- 应用回滚可恢复先前镜像；`0013 → 0012` 会丢失多题标题和次数限制语义，若必须数据库降级应先停止写入并使用本次备份在隔离环境验证，禁止直接覆盖运行库。
## 2026-08-28：入口安全、高并发与 Docker 版本收敛

- 两套 Nginx 增加 limit_req_status 429；现有 Nginx 重启后 healthy。
- 多来源隔离登录 100/200/300 档全部 0 错误；100 Session/2,000 次读取 P95 331.674 ms、错误率 0%。单 IP 大量账号的 429 保留为预期防洪策略。
- PNX 端口映射仅 Nginx 0.0.0.0:5000；Compose 内 Backend、Frontend、PostgreSQL、MinIO 无宿主机端口映射。宿主机 5432/3000 属于另一个项目或宿主进程，本轮未修改。
- 匿名 API、Host/转发头、Origin/CSRF、非法方法、请求体上限、路径遍历和 source map 探测通过；Gitleaks 无泄漏。Trivy 发现 Backend Alpine 的 4 个 CVE，需后续升级基础镜像。
- 保留当前 questionnaire-account-20260828 与回滚候选 intention-fix-20260828、user-status-ui-20260828；删除已退出 PNX migrate 容器及其余旧 PNX 应用标签。运行卷、备份和六服务保留；隔离项目资源已删除。全局构建缓存未清理以免影响其他项目。

## 2026-08-28 问卷查看与草稿编辑部署

### 备份与构建

- 部署前从 `pnx-training-postgres-1` 生成 PostgreSQL 17 自定义格式备份 `/tmp/pnx-training-before-questionnaire-edit-20260828T145330Z.dump`，`pg_restore --list` 校验通过；大小 4,145,718 字节，权限 0600，SHA-256 为 `f089b9425488a48f4fa2d3b34744ab9423d86a00255b17c26c23caef373d08bf`。
- 完整质量门通过后构建 Backend/Worker `pnx-training-backend:questionnaire-edit-20260828`（`sha256:06eb68d3c5b2a0f6bbb0dd8d0add1c363d188d3ccd69ddf8f70f08437b07501c`）和 Frontend `pnx-training-frontend:questionnaire-edit-20260828`（`sha256:a5d9264abc6a944a5b0e6a0a7f3a743d02f7af20cb748a6e34ed8a8b5dbbce9a`）。
- `.env` 的 `APP_IMAGE_TAG` 固定为 `questionnaire-edit-20260828`；本轮没有数据库迁移，运行与源码 Alembic 都是 `20260828_0013`。

### 部署过程与恢复

- 第一次 Compose 调用未显式传 `--env-file .env`，Compose 按配置目录回退到 `dev` 并生成两个临时镜像；未写数据库。随即显式加载 `.env` 并按固定标签替换 Backend、Worker、Frontend、重启 Nginx。
- 首个固定 Backend 镜像中三个经补丁回退写入的 Python 文件权限为 0600，非 root 应用用户导入时报 `PermissionError`，入口健康端点短暂返回 502。将本轮源码统一恢复为 0644、重建同一固定标签并再次替换 Backend/Worker 后恢复；两个未使用的 `dev` 标签已删除。

### 最终验收

- Backend、Worker、Frontend、Nginx、PostgreSQL、MinIO 全部 healthy；`live`、`ready`、`worker`、`nginx-health` 均为 200。管理页面匿名访问 307，管理详情 GET 和 PATCH 匿名访问 401。
- 运行 Frontend 编译包包含“查看内容”“编辑问卷”“问卷修改已保存”；Backend OpenAPI 同一路径包含 GET/PATCH，最近一分钟新服务日志只有预期 200/401 请求，无错误。
- Alembic 为 `20260828_0013 (head)` 且 `alembic check` 无升级操作；部署前后问卷、题目、选项、回答、选择关系数量均为 `2/3/11/2/2`。
- 最近成功知识库同步仍为 `succeeded`、212 篇文档、986 个媒体；本轮没有调用飞书同步、账号删除、邮件发送或上传接口。

### 回滚

- 应用回滚只需把 `APP_IMAGE_TAG` 恢复为 `questionnaire-account-20260828` 并按同样方式重建 Backend、Worker、Frontend、重启 Nginx；本轮没有迁移需要降级。
- 若需数据级恢复，可使用已校验备份执行受控 `pg_restore`；备份当前位于 `/tmp`，需要长期保留时应转移到受控持久介质。

## 2026-08-29 反馈答疑部署

### 备份与迁移验证

- 部署前从 `pnx-training-postgres-1` 生成 PostgreSQL 17 自定义格式备份 `/tmp/pnx-training-before-help-requests-20260829T015203Z.dump`；`pg_restore --list` 共 277 项，文件大小 4,147,113 字节、权限 0600，SHA-256 为 `9bb10adf0edd852a9192f2eb9e65ba3c6a23ae908651192839089ab8369cd8a2`。该 `/tmp` 文件需迁移到受控持久介质才能跨主机重启长期保留。
- 将生产备份恢复到独立 PostgreSQL 17 容器后，使用候选 Backend 真实完成 `0013 → 0014 → 0013 → 0014`；`alembic check` 无模型漂移，新表 5 个检查约束、2 个用户外键及学生/管理员列表索引完整。
- 隔离往返前后用户、问卷/题目/选项/回答/选择关系、最近成功知识库文档/媒体计数均为 `6/2/3/11/2/2/212/986`；`help_requests` 初始为 0。隔离容器和网络已删除，未连接其他项目数据库。

### 构建与部署

- Backend 首个候选因新增源码目录为 0700、复制后属 root 所有，非 root `appuser` 在迁移事务前无法导入；生产库未受影响。将本次新增源码目录统一修正为 0755，并定向失效 runtime 缓存层后，非 root 导入与完整隔离迁移均通过。
- 最终 Backend/Worker 为 `pnx-training-backend:help-requests-20260829`（`sha256:c87408a3f807b211588b0d815c980a48a7e2ecd39be3ed611360cd1853ec07d0`），Frontend 为 `pnx-training-frontend:help-requests-20260829`（`sha256:a32c3c9c72a2a19dadaf9da536c9a174c520873075763c08709e80c901977020`）；两镜像均声明 `appuser`。
- 运行库在旧应用保持健康时事务升级 `0013 → 0014`，确认新表为空后把 `.env` 的 `APP_IMAGE_TAG` 固定为 `help-requests-20260829`，依次替换 Backend、Worker、Frontend，并重建 Nginx 刷新上游地址。

### 最终验收

- Backend、Worker、Frontend、PostgreSQL、MinIO、Nginx 六服务 healthy；`live`、`ready`、`worker`、`nginx-health` 均为 200。Alembic 为 `20260828_0014 (head)` 且无模型漂移。
- `/help`、学生详情、`/admin/help`、管理员详情匿名访问均为 307；运行 OpenAPI 包含 6 个反馈答疑操作，匿名 GET/POST/PUT 均为 401。
- 部署后 `help_requests=0`，用户 6、问卷 `2/3/11/2/2`、最近成功知识库 `succeeded/212/986` 保持不变；新服务日志只有预期 200/307/401，无启动、权限或事务异常。
- 本轮未触发飞书同步、邮件、账号删除或上传。应用回滚可把标签切回 `questionnaire-edit-20260828` 并保留向后兼容的 `0014`；工单产生后不得直接降级到 `0013`，因为 downgrade 会删除全部工单数据。

## 2026-08-29 已解答问题公开与分类提醒部署

### 构建与替换

- 完整质量门通过后构建 Backend/Worker `pnx-training-backend:help-public-20260829`（`sha256:942b9ee5e98d6658b4d870477eb1758562d3fd18bde1bf40f450d18629a54816`）和 Frontend `pnx-training-frontend:help-public-20260829`（`sha256:93feb800a8c6d17b3924c034424dec533efe6b88880dae7521256075b1f44239`），两者均声明 `appuser`。
- 构建前发现经补丁替代路径新增的公开页面目录为 0700、反馈答疑源码部分为 0600；在构建前统一恢复目录 0755、源码 0644，候选 Backend 以非 root 用户成功导入并生成八个反馈答疑操作。
- `.env` 的 `APP_IMAGE_TAG` 固定为 `help-public-20260829`；先替换 Backend/Worker 并等待健康，再替换 Frontend/Nginx。PostgreSQL、MinIO 未重启，旧 `help-requests-20260829` 镜像保留。

### 运行态验收

- Backend、Worker、Frontend、PostgreSQL、MinIO、Nginx 六服务 healthy；`live`、`ready`、`worker`、`nginx-health` 均返回 200，新应用服务近期日志无错误匹配。
- `/help`、`/help/public/{id}`、`/admin/help`、`/admin/help/{id}` 匿名访问为 307；两个公开 API 匿名访问为 401，说明页面和接口仍要求有效登录。
- 运行 Backend OpenAPI 含八个反馈答疑操作和两个公开路径；`PublicHelpRequestDetail` 只含工单 ID、类型、状态、标题、安全正文/答复、时间和 revision，不含提交者身份、通知 ID 或 Markdown 源文。
- Alembic 保持 `20260828_0014 (head)`，`alembic check` 无新升级操作。本轮不新增字段或迁移，没有执行数据库写入；运行库现有 1 条 `question/resolved` 工单，部署后按派生规则自动进入公开范围。
- 完整后端 Ruff、169 文件格式、120 源文件严格 Mypy、246 项 Pytest 通过；完整前端 ESLint、严格 TypeScript、21 文件/89 项 Vitest 与主机/容器生产构建通过。
- 本轮部署镜像同时包含已完成的学生提醒分类与徽标消除修复；该修复无迁移、无新依赖，权限和提醒幂等规则不变。
- 本轮未调用飞书同步、邮件、账号删除或上传接口。

### 回滚

- 应用回滚只需把 `APP_IMAGE_TAG` 恢复为 `help-requests-20260829`，按相同顺序替换 Backend/Worker、Frontend/Nginx；本轮没有数据库迁移需要降级，现有 `0014` 和工单数据应保留。
- 2026-08-29 收尾已在用户授权后撤销部署期间添加的 Docker socket `user:pnx:rw-` 临时 ACL；`getfacl -cp /var/run/docker.sock` 复核仅剩 owner、group、mask 与 other 基础条目，不再存在命名用户 `pnx` 权限。


## 2026-08-29 学生提醒共享页面 Frontend 增量部署

- 本轮只部署 `/profile`、`/sessions` 与 `/help/public/{request_id}` 的学生分类徽标取数补丁；源码已通过完整前端 22 个测试文件/90 项测试、ESLint、严格 TypeScript 和主机生产构建，容器内 Next.js 生产构建再次通过并包含三个目标路由。
- 构建前把新增通知组件目录/源码恢复为标准 `0755/0644`；Frontend 固定镜像为 `pnx-training-frontend:notification-badges-20260829`（`sha256:fd13387f14a56c518c9be2ef61860bf466ff0f7434cc340352d9875236836a86`），以 `appuser`（UID/GID 10001）运行。
- `.env` 的 `APP_IMAGE_TAG` 已固定为 `notification-badges-20260829`。Backend/Worker 容器继续运行 `help-public-20260829`，未重建或替换；原 Backend 镜像 `sha256:942b9ee5e98d…` 只增加同名固定别名，保证统一标签下 Compose 可复现。
- 仅强制重建 Frontend，待其 healthy 后重启 Nginx 刷新上游；PostgreSQL、MinIO、Backend 和 Worker 未重启。六服务最终均 healthy 且重启计数为 0。
- `live`、`ready`、`worker`、`nginx-health` 和登录页均为 200；`/profile`、`/sessions`、`/help/public/{id}` 匿名访问为 307，Dashboard API 匿名访问为 401；Frontend/Nginx 近十分钟无严重错误关键字。
- Alembic 保持 `20260828_0014 (head)`；本轮无迁移、数据库写入、飞书同步、邮件、账号删除或上传。应用回滚只需把统一标签恢复为 `help-public-20260829` 并按相同方式替换 Frontend、重启 Nginx。
- 用户完成撤销本次临时 Docker socket `user:pnx:rw-` ACL；`getfacl -cp /var/run/docker.sock` 复核仅剩基础 owner/group/mask/other 条目，socket 恢复为 `root:docker`、`0660`。

## 2026-08-29 统一发布点与 Docker 精确清理

### 发布点与备份

- 本轮将问卷管理详情/草稿编辑、反馈答疑/已解决问题公开、学生分类提醒及权威文档拆为五个本地提交：`5b642a2`、`84718d4`、`059d87a`、`c1e7259`、`634e01a`。未 push，也未创建外部 Release。
- 发布前 PostgreSQL 17 自定义格式备份为 `/tmp/pnx-training-before-release-634e01a-20260829T042700Z.dump`，大小 4,153,800 字节、权限 0600、SHA-256 `bb4ad5f713aa1d605e6cffac23903471d48a49dd66f1085bfb6660425cd78caa`；在 PostgreSQL 17 容器内执行 `pg_restore --list` 成功。
- `.env` 固定为 `APP_IMAGE_TAG=release-634e01a-20260829`。Backend/Worker 镜像为 `pnx-training-backend:release-634e01a-20260829`（`sha256:c7ccb9bd1249354d0ad5b059560bd90f34a69f6e22bd45058e6e65f132b8cea9`），Frontend 为 `pnx-training-frontend:release-634e01a-20260829`（`sha256:76266bc260527c7131af364c97ed2f801769b8a3ef5e111cb0dff642bf033c46`）。

### 质量门与部署过程

- Backend 通过 Ruff、169 个 Python 文件格式检查、120 个源文件严格 Mypy 和 246 项 Pytest；Frontend 通过 ESLint、严格 TypeScript、22 个文件/90 项 Vitest、主机和容器 Next.js 生产构建。
- Alembic 源码单一 head 与运行库均为 `20260828_0014`，`alembic check` 无模型漂移；候选 Backend 以 `appuser` 导入成功，OpenAPI 共 113 个路径。本轮没有新迁移。
- 按 Backend/Worker、Frontend/Nginx 顺序替换应用；PostgreSQL 与 MinIO 数据卷未重建。最终六服务 healthy，应用容器均为 `appuser`，重启次数为 0。
- `/login`、`/health/live`、`/health/ready`、`/health/worker`、`/nginx-health` 为 200；`/help`、`/admin/help`、`/admin/intentions`、`/profile`、`/sessions` 匿名访问为 307；公开答疑、管理答疑与 Dashboard API 匿名访问为 401，近期日志无严重错误匹配。
- 发布前后用户/问卷/问题/选项/回答/选择关系/工单/已解决公开问题/知识文档/媒体均为 `6/2/3/11/2/2/1/1/212/986`。本轮未触发邮件、飞书同步、账号删除、上传或其他业务写入。

### 清理范围与恢复边界

- 删除已退出的 `pnx-training-migrate-1`、10 个旧 PNX 应用标签和 9 个旧镜像 ID；清理后无 dangling 镜像，镜像占用由 7.76 GB 降至 7.05 GB。
- 当前仅保留 `release-634e01a-20260829` 和回滚候选 `notification-badges-20260829` 两组 PNX 应用镜像。回滚仅切换固定标签并按相同顺序替换应用，不降级 `0014` 数据库。
- 保留 `pnx-training_postgres_data`、`pnx-training_minio_data`、三个 PNX 网络、发布前备份、其他 `management-system` 项目、4 个来源不明匿名卷及全局 BuildKit 缓存；未执行全局 `docker system prune` 或全局卷/缓存清理。
- 备份位于 `/tmp`，只能作为本机短期恢复材料；需要跨主机重启或长期保留时，应转移到受控加密持久介质。

### 权限收尾

- Docker 操作临时授予 `/var/run/docker.sock` 命名 ACL `user:pnx:rw-`；非交互撤销因主机要求 sudo 密码未执行，随后由用户在主机终端完成交互式撤销。最终 `getfacl -cp` 只剩基础 owner/group/mask/other 条目，`stat` 为 `root:docker`、`0660`，部署权限已完全收敛。

## 2026-08-29 认证失败窗口修复部署

### 备份与构建

- 部署前从运行 PostgreSQL 17 生成自定义格式备份 `/tmp/pnx-training-before-auth-window-20260829T081859Z.dump`；同版本容器内 `pg_restore --list` 校验通过，宿主机文件大小 4,306,752 字节、权限 0600、SHA-256 为 `05f7ec8f7de2b6213461ca4133469f96ec624d276798b0ad6719ab53d3c8b46d`。容器内临时副本已删除，宿主机备份需迁往受控加密持久介质才能长期保留。
- 首个候选镜像因补丁后的 `backend/app/auth/service.py` 为 0600，非 root `appuser` 无法读取，未替换任何运行服务；恢复本任务源码/文档为标准 0644 后重建并以 `appuser` 完成模块导入和策略断言。
- 最终 Backend/Worker 镜像为 `pnx-training-backend:auth-window-20260829`（`sha256:716685804552957ea519dd0f063b93dbe46c10f9f420f12245797189bf355a84`）；当前 Frontend 镜像 `sha256:76266bc260527c7131af364c97ed2f801769b8a3ef5e111cb0dff642bf033c46` 仅增加同名标签别名，Frontend/Nginx 未重建或替换。`.env` 已固定 `APP_IMAGE_TAG=auth-window-20260829`。

### 运行态验收与数据保护

- 目标镜像 Alembic head 与运行库均为 `20260828_0014`，执行 `upgrade head` 无版本变化；本轮没有新增或执行数据迁移。
- Backend/Worker 强制替换后均以 `appuser` 运行、重启次数为 0 且 healthy；Frontend、Nginx、PostgreSQL、MinIO 持续 healthy。登录页、`live`、`ready`、`worker`、`nginx-health` 为 200，`/profile`、`/sessions` 匿名访问为 307，`/api/v1/auth/me` 匿名访问为 401。
- 运行 Backend 源码断言确认三个恢复入口不再调用历史计数，唯一 `_check_rate_limit` 调用使用 10 分钟窗口；近期日志没有启动、权限或事务异常，并记录到真实登录 200，证明新镜像已处理实际 Argon2id 登录请求。
- 备份时数据基线为用户 147（`active admin=4`、`active student=131`、`pending_email student=12`）和安全事件 987；最终为用户 148（`4/132/12`）和安全事件 997。按备份时间归因，实时外部流量新增 1 个账号并完成验证，同时产生 `login_failed=6`、`password_reset_request=1`、`registration=1`、`verification_resend=2`；部署过程没有调用这些写接口，未清理、回滚或篡改并发业务数据。
- 问卷/题目/选项/回答/选择关系保持 `3/5/21/80/158`，反馈答疑/已解决问题保持 `1/1`，知识库目录节点/媒体保持 `684/986`。本轮没有账号删除、安全事件清空、密码重置、批量重哈希、飞书同步或上传。

### 权限收尾与回滚

- Docker socket 临时命名 ACL `user:pnx:rw-` 已由用户交互式撤销；`getfacl -cp` 只剩基础 owner/group/mask/other 条目，socket 为 `root:docker`、`0660`，当前用户访问 Docker API 返回 permission denied。
- 应用回滚只需把统一标签恢复为 `release-634e01a-20260829` 并替换 Backend/Worker；数据库保持 `0014`，不得恢复部署前备份覆盖发布期间真实用户数据。

## 2026-08-29 管理员移除作业与通知部署

### 候选隔离与备份

- 本轮只发布管理员删除通知/作业、学生端归档过滤及对应前端入口。候选构建目录为 `/tmp/pnx-admin-content-removal-candidate.whyp7x`，并行修改的 `backend/app/auth/service.py` 直接替换为部署前运行容器版本；其 SHA-256 为 `c91a996d731f293172b9ac49e5c41a7a1a528da5a1b975f3b7e817f8822e9c42`，候选与工作树运行时代码仅该文件不同。
- 工作树完整质量门通过 Ruff、169 文件格式、153 个源文件严格 Mypy、264 项 Pytest、ESLint、严格 TypeScript、22 文件/95 项 Vitest 和 Next.js 生产构建。隔离候选另通过通知、作业、附件授权和 API 契约 38 项测试、125 个源文件静态检查；Backend 容器 OpenAPI 共 113 个路径并包含两个 DELETE/204 操作，Frontend 容器构建包含“删除通知/删除作业”。
- 部署前 PostgreSQL 17 自定义格式备份为 `/tmp/pnx-training-before-admin-content-removal-20260829T091428Z.dump`，同版本 `pg_restore --list` 校验共 314 项；文件大小 4,320,274 字节、权限 0600，SHA-256 为 `194a1cdd7c2330fc7dd7e0ef70cf7d68240c95761f2c7ad352b5579df4446629`。容器内临时副本已删除，宿主 `/tmp` 文件只适合作为本机短期恢复材料。

### 构建、替换与运行验收

- `.env` 已固定 `APP_IMAGE_TAG=admin-content-removal-20260829`。Backend/Worker 镜像为 `sha256:a9e4e73584e35588b537ea1f924c8888a4c73ddd4553ae88aa3ce4322b3f501e`，Frontend 为 `sha256:1ce818d5d2d65cde234e6ce698ca54685ad0def407a4337edad186a375954d5b`；应用容器均以 `appuser` 运行。
- 依次替换 Backend、Worker、Frontend、Nginx，PostgreSQL 和 MinIO 未重建。六服务均 healthy、重启次数为 0；`/login`、`/health/live`、`/health/ready`、`/health/worker`、`/nginx-health` 均为 200，管理员和学生通知/作业页面匿名为 307，两个 DELETE API 匿名为 401。
- 生产 Nginx 按设计不暴露 OpenAPI，外部请求返回 404；运行 Backend 内部 OpenAPI 已确认两个 DELETE 路径均声明 204。运行认证源码哈希仍为部署前版本，证明并行注册修复没有静默进入本次镜像。
- Alembic 保持 `20260828_0014 (head)`，本轮无迁移。部署前后问卷 `3/5/21/83/164`、反馈答疑 `1/1`、知识库 `succeeded/212/986`、Outbox `pending=1/processing=0/retry=0/dead=20`、归档通知/作业 `2/1` 和提交 `1/2` 均保持不变；用户由 150 增至 151 来自真实外部流量，部署命令没有调用业务写接口。
- 最近 15 分钟聚合到 6 次 `unhandled_exception`，均为部署前既有的重复注册邮箱唯一约束没有被旧认证源码映射；该风险正由工作树并行认证修复处理，本轮按范围没有部署该修复，也未发现管理员内容删除功能新增异常。

### 回滚与权限收尾

- 保留 Backend/Worker `auth-window-20260829` 与 Frontend `release-634e01a-20260829` 作为回滚候选。本轮数据库无迁移；若生产已执行删除，不应只回滚学生查询过滤，否则已归档内容可能重新出现在学生页面。
- 本轮临时 Docker socket 命名 ACL 必须在收尾时移除，并复核无 `user:pnx` 条目且 socket 为 `root:docker`、`0660`。

## 2026-08-29 注册唯一约束异常热修部署

### 隔离候选与备份

- 以当前运行的管理员内容删除 Backend `sha256:a9e4e73584e3…` 为基底构建 `pnx-training-backend:registration-constraint-20260829`；候选层链只新增 `/app/app/auth/service.py` 一个文件层，避免把并行账号删除开发改动带入生产。候选镜像为 `sha256:0972df29b3758acc4ef6750e248f59c8b905ec3bba44b4b4a6e0a4783e4d3e8b`。
- 认证文件在候选和运行容器中均为 `0644 appuser:appgroup`，SHA-256 为 `d25505a99c2b712e7078be61deae1522c40a62e9fec13a5184aafcd4c8580825`；嵌套 asyncpg 约束映射断言通过，未知约束仍按未预期错误处理。
- 部署前 PostgreSQL 17 自定义格式备份为 `/tmp/pnx-training-before-registration-constraint-20260829T103222Z.dump`，同版本 `pg_restore --list` 共 314 项；文件大小 4,328,438 字节、权限 0600、SHA-256 为 `b45dbbcc44c89576305511877687a2eae14c6b5f3f09fc76aaa2255dede5fc4a`。

### 替换与运行验收

- `.env` 固定 `APP_IMAGE_TAG=registration-constraint-20260829`；Backend/Worker 替换为新镜像并以 `appuser` 运行，重启次数为 0。Frontend 当前镜像 `sha256:1ce818d5d2d6…` 只增加同名标签别名，Frontend/Nginx 未替换。
- 候选执行 `alembic upgrade head` 后仍为 `20260828_0014 (head)`，没有结构或数据迁移。六服务全部 healthy；`/login`、`/health/live`、`/health/ready`、`/health/worker`、`/nginx-health` 均为 200。
- 运行断言确认嵌套 `constraint_name` 可识别，且管理员通知/作业两个 DELETE 路径仍存在于 OpenAPI；近期 Backend/Worker 日志没有 `unhandled_exception`、Traceback、权限或严重错误模式。
- 备份后首轮聚合为用户 154、安全事件 1,101、一次性令牌 219、Session 291；最终为用户 155、安全事件 1,103、一次性令牌 220、Session 291。备份时间后的聚合为 2 条 `registration`、1 个新验证令牌，变化来自持续外部注册流量；部署命令没有调用认证写接口，未删除、清空、重置、批量重哈希或回滚运行数据。

### 回滚与权限

- 应用回滚只需把固定标签恢复为 `admin-content-removal-20260829` 并替换 Backend/Worker；数据库没有迁移，不得用部署前备份覆盖期间真实注册数据。
- 普通用户执行 `setfacl -x u:pnx /var/run/docker.sock` 被宿主机拒绝，`sudo -n` 也因需要密码失败；当前临时 `user:pnx:rw-` ACL 尚在，必须由用户在宿主机终端交互式撤销后复核。

## 2026-08-29 飞书 LaTeX 公式隔离热修部署

### 候选隔离与备份

- Backend 候选以当前运行的 `registration-constraint-20260829`（`sha256:0972df29b375…`）为基底，镜像顶层只复制 `/app/app/knowledge/normalizer.py` 并恢复 `0644 appuser:appgroup`；运行认证文件继续保持 `d25505a99c2b712e7078be61deae1522c40a62e9fec13a5184aafcd4c8580825`，迁移目录不含并行账号删除的 `20260829_0015`。
- Frontend 从 Git 发布基线创建临时隔离上下文，只叠加已上线的通知/作业删除两个编辑器，以及公式所需的布局、知识块渲染、知识块类型、KaTeX 依赖/锁文件和公式测试，共 8 个差异文件；候选不含新增个人资料注销组件、`0015` 或新版账号删除确认字段。
- 隔离 Frontend 执行 `npm ci` 时审计 499 个包、0 漏洞，Next.js 生产构建和知识库 8 项组件测试通过；两个候选均以 `appuser` 运行，Backend 镜像内公式断言与 `20260828_0014 (head)` 源码检查通过。
- 部署前 PostgreSQL 17 自定义格式备份为 `/tmp/pnx-training-before-feishu-latex-20260829T112100Z.dump`，大小 4,330,074 字节、权限 0600、SHA-256 `b53cea2fd8927f4ce4f8aaca1b8a8bc759a1c508ac2db18208887f7a0c8b31a0`；同版本 `pg_restore --list` 校验通过。该文件是本机短期恢复材料，长期保留仍须迁移到受控加密介质。

### 替换与运行验收

- `.env` 已固定 `APP_IMAGE_TAG=feishu-latex-20260829`。Backend/Worker 运行镜像为 `sha256:5e7b335da4fcd0488939c9cd4476f798ecab1c303c6ebb3466bca84f49a61f95`，Frontend 为 `sha256:6076084d5de5aad1829d8cc5a663091b9fc4b2c8365f6c4446374638aef2acf7`。
- 使用 `--no-deps` 按 Backend/Worker、Frontend、Nginx 顺序强制替换并等待 healthy；没有创建 migrate 容器，PostgreSQL 与 MinIO 未重启。六服务最终 healthy、重启次数为 0，应用容器均为 `appuser`。
- 登录页、`live`、`ready`、`worker`、`nginx-health` 均为 200；`/knowledge` 与 `/admin/knowledge` 匿名访问为 307，两个知识库 API 匿名访问为 401。新服务日志只有预期健康和匿名守卫请求，无权限、事务、Traceback 或上游错误。
- 运行 Backend 的规范化器哈希为 `4014b6b181a8d51b85bc78300b268aea246c3a0be5d8322f2f6820731b61e0a3`，镜像内行内/独立公式断言通过；运行 Frontend 编译产物同时包含公式安全回退、KaTeX CSS 和既有“删除通知/删除作业”，且不含新版账号删除 `backup_confirmed` 字段。
- 运行 OpenAPI 仍为 113 个路径，保留通知/作业 DELETE，未出现并行开发的 `/api/v1/auth/account`；Alembic 保持 `20260828_0014 (head)`。
- 部署前后用户/问卷/问题/选项/回答/选择关系/工单/已解决问题/通知/作业/提交/版本计数均为 `155/3/5/21/84/166/1/1/2/1/1/2`；最近成功知识库保持 `succeeded/212/986`，最新 `sync_knowledge` Outbox 保持 `sent/1`，账号对象清理 Outbox 为 0。

### 回滚与剩余操作

- 旧 Backend/Worker `registration-constraint-20260829`（`sha256:0972df29b375…`）和 Frontend 基线（`sha256:1ce818d5d2d6…`）继续保留；应用回滚只切换固定标签并按相同顺序替换，不降级或恢复 `0014` 数据库。
- 本轮没有触发飞书同步、邮件、上传、认证或账号删除写接口。已有成功快照不会原地获得公式语义，必须由真实管理员手动同步一次，并在新运行 `succeeded` 后验收公式。
- 本次临时 Frontend 测试镜像和两个 `/tmp` 隔离构建目录已删除，运行/回滚镜像、数据卷和部署前备份保留。普通 `setfacl -x` 被拒绝且 `sudo -n` 要求密码，Docker socket 的 `user:pnx:rw-` 临时 ACL 仍需部署方在宿主机执行 `sudo setfacl -x u:pnx /var/run/docker.sock`，再用 `getfacl -cp` 确认只剩基础条目。

## 2026-08-29 管理员永久删除账号与用户自助注销部署

### 候选隔离

- 工作树同时包含已上线的通知/作业删除、注册修复、飞书公式、待部署账号删除和仍在开发的反馈答疑删除，未直接用整个工作树构建。Backend 以运行 `feishu-latex-20260829` 镜像为底，只叠加账号删除/迁移及部署中必要的备份修正；Frontend 从 Git 发布基线重建，只叠加已上线功能和账号删除白名单。
- 最终候选明确不含反馈答疑 DELETE；Backend OpenAPI 为 114 个路径，包含 `/api/v1/auth/account` 与管理员用户 DELETE/204，Frontend 编译产物保留 KaTeX、“删除通知”“删除作业”和账号注销界面。
- Backend/Frontend 候选均以 UID 10001 `appuser` 运行，账号删除、认证、迁移和备份关键文件为 `0644 appuser:appgroup`。前端隔离 `npm ci` 审计 499 个包、0 漏洞，Next.js 生产构建通过。
- 部署阶段新增备份/存储 9 项与迁移静态 6 项回归，Ruff、格式和相关严格 Mypy 通过；源码阶段既有后端定向 45 项与前端 23 文件/102 项质量门继续有效。

### 加密完整备份与恢复

- 维护窗口先停止 Nginx、Frontend、Backend、Worker，仅保留 healthy 的 PostgreSQL/MinIO；备份 ID 为 `pnx-backup-20260829T122839Z-weekly`，OpenPGP 接收方是本次隔离临时密钥环。
- 归档大小 1,979,581,142 字节、权限 0600、SHA-256 `a68bdd8a847a419a2d092730362a6277453bcb6cf67614c76a784d817bd85bdb`；PostgreSQL 自定义 dump 5,569,892 字节，PostgreSQL 17 `pg_restore --list` 为 314 项。
- MinIO 完整清单包含 2,885 个对象、2,038,164,595 字节。首次导出暴露备份路径只允许 `objects/` 而拒绝服务端 `knowledge/` 的缺陷；修正后仍只允许这两个固定前缀并继续拒绝绝对路径、空段和 `.`/`..`。
- 从全新 `pnx-restore-account-20260829` PostgreSQL/MinIO 卷恢复成功，RPO 1,177 秒、RTO 79 秒。对账把普通 `files` 与 `knowledge_assets` 合并为 1,010 个数据库引用，缺失/大小/SHA-256 不符均为 0；1,875 个旧知识库孤立对象保留并仅汇总告警。
- 恢复脚本只允许对账退出码 0/4 进入严格 JSON 检查；数据库引用异常仍硬失败，孤立对象不自动删除且最终摘要不输出对象键。备份、校验和、元数据、周基线状态和临时 GPG 密钥环保留在 `/tmp`，尚未形成异机持久副本。

### 隔离迁移往返

- 首次 `0014 → 0015` 在检查约束 DROP 阶段因 Alembic 命名约定二次展开失败，PostgreSQL 事务完整回滚，版本仍为 `0014`；生产库当时未迁移。
- 所有显式检查/外键名改用 `op.f(...)` 后，隔离副本完成 `0014 → 0015 → 0014 → 0015`。降级恢复原始不可变触发器，再升级恢复账号擦除受限例外。
- 0015 下全部 34 个 `users` 外键审计为 12 个 CASCADE、21 个 SET NULL、1 个队长 RESTRICT；相关可空性和四个检查约束符合设计。普通正式版本 DELETE 由隔离子事务确认仍被 SQLSTATE `55000` 拒绝。
- 往返前后核心计数保持 `155/3/5/21/84/166/1/1/4/1/1/2`，知识库保持 `succeeded/213/1006`，账号清理 Outbox 为 0；最终对象对账仍为 1,010 个引用全部匹配、1,875 个孤立对象告警。

### 生产迁移与运行验收

- 生产在备份和隔离往返全部通过后应用 `20260829_0015`；随后 `.env` 固定 `APP_IMAGE_TAG=account-deletion-20260829`，按 Backend/Worker、Frontend/Nginx 顺序替换，PostgreSQL/MinIO 容器和数据卷未重建。
- Backend/Worker 镜像为 `sha256:081be7ba08de49781ab40d3e3053c45910ca34078901935c28638135f8846c81`，Frontend 为 `sha256:d4b5172a1a780f2f4db63db2f65a80e881669c4ec7c3b0dc09632b3d620bd2f4`；应用均为 `appuser`，六服务 healthy、重启次数 0。
- `/login`、`live`、`ready`、`worker`、`nginx-health` 为 200；`/profile`、`/admin/users` 匿名原始响应为 307；本人和管理员账号 DELETE 匿名为 401。运行 OpenAPI 的本人必填字段为密码/确认邮箱，管理员另含原因/备份确认，均声明 204。
- 运行 Alembic 为 `20260829_0015 (head)`；生产 Schema 摘要与隔离一致，版本守卫含事务标记、父提交检查和 `55000`。部署前后核心业务计数不变，最新知识库为 `213/1006`，账号清理 Outbox 为 0。
- Backend/Worker/Frontend/Nginx 启动窗口对 Traceback、事务中止、权限拒绝、未捕获异常、对象键和 multipart 标识的聚合计数均为 0。本轮未携带认证调用删除 API，未触发真实账号删除、对象清理、飞书同步、认证或上传写入。

### 清理、回滚与剩余风险

- 隔离容器、网络、两个数据卷、明文解密临时目录、源码构建上下文和审计 SQL 已删除；生产/回滚镜像、生产卷及加密备份保留。
- 尚未执行任何真实账号删除时，可在确认数据未产生 SET NULL 去标识后降级到 `0014`；一旦执行删除应优先前滚修复，需恢复账号时只能使用删除前 PostgreSQL + MinIO 同点备份隔离恢复。当前 `/tmp` 备份和密钥环必须尽快迁移到受控独立介质并分离保存；Docker socket 临时 ACL 仍需收尾撤销。

## 2026-08-29 管理员删除反馈答疑部署

### 候选、备份与质量门

- 账号删除部署已先行完成，运行基线变为 `account-deletion-20260829` 与 `20260829_0015`。把运行 Backend 源码复制到临时目录逐文件比较后，工作区 Backend 仅 `help_requests/repository.py`、`router.py`、`service.py` 三个文件不同；候选没有回退账号删除、注册修复、通知/作业删除或公式能力。
- 候选 Backend OpenAPI 共 114 个路径，账号删除继续存在，答疑详情路径新增 DELETE/204 无正文，镜像仍含 `0015`；Frontend 编译产物同时包含答疑删除、账号删除、通知删除和公式安全回退。两个镜像均以 UID 10001 `appuser` 运行。
- 后端定向 27 项与完整 280 项 Pytest、Ruff、170 文件格式检查、153 源文件严格 Mypy 通过；前端完整 23 文件/102 项 Vitest、ESLint、严格 TypeScript 和主机/容器生产构建通过，容器 `npm ci` 审计 499 个包、0 漏洞。
- 部署前 PostgreSQL 17 自定义格式备份 `/tmp/pnx-training-before-help-delete-20260829T141903Z.dump` 为 5,571,302 字节、0600、SHA-256 `40cfce14391d4e135a3d30a6c786be81df494a69affe9a56dbceb445df49bbd0`，同版本 `pg_restore --list` 314 项通过；容器内临时副本已删除。

### 替换、异常恢复与运行验收

- `.env` 固定 `APP_IMAGE_TAG=help-delete-20260829`。Backend/Worker 镜像为 `sha256:1a2f7c6e3d7145653dcccb076c098fe544e854bcf29b6cede5ee9b5218fdc799`，Frontend 为 `sha256:2f7ef180f2c2da20eb39e6c723c45de5b8871e62b5e000bf5b53d60decd3b110`。
- 首次从仓库根调用 Compose 时没有显式 `--env-file .env`，工具把标签和飞书 URL 等变量按默认值解析，临时构建 `:dev` 并启动了配置不完整的 Backend/Worker。健康门检测到飞书 URL 为空后没有继续 Frontend；立即用显式 `--env-file .env` 和已验证固定镜像重建，Backend/Worker 恢复 healthy。该过程未运行 migrate，PostgreSQL、MinIO 及其卷未重建，聚合数据无变化。
- 随后替换 Frontend 并重建 Nginx 刷新上游。最终六服务 healthy、重启次数 0；Backend/Worker/Frontend 均为 `appuser`。登录、`live`、`ready`、`worker`、`nginx-health` 为 200，学生/管理员答疑页面匿名为 307，答疑 DELETE 匿名为 401 且返回统一 `AUTHENTICATION_REQUIRED`。
- 运行 OpenAPI 共 114 个路径，答疑 DELETE 声明无正文 204 且账号删除继续存在；Alembic 保持 `20260829_0015 (head)`。最终 Backend/Worker/Frontend 启动日志无 Traceback、事务、权限或未处理异常。
- 部署前后用户/问卷/问题/选项/回答/选择关系/工单/已解决问题/通知/作业/提交/版本/知识文档/知识媒体/账号清理 Outbox 保持 `155/3/5/21/85/169/1/1/2/1/1/2/897/1010/0`，最近成功知识库保持 `succeeded/213/1006`。

### 回滚与边界

- 本轮未携带认证调用真实答疑或账号 DELETE，未触发飞书同步、上传或其他业务写接口；答疑删除自身无数据库迁移、依赖或 Worker 变化。
- 应用回滚可把固定标签恢复为 `account-deletion-20260829` 并按 Backend/Worker、Frontend、Nginx 顺序替换，数据库保持 `0015`。若已执行答疑物理删除，应用回滚不能恢复工单，只能按删除前备份进行隔离恢复或采用明确的数据恢复流程。
- PostgreSQL 快照位于宿主机 `/tmp`，只适合作为本机短期材料；账号部署的完整加密 PostgreSQL + MinIO 备份及临时密钥环仍须迁移到受控独立介质并分离保存。Docker socket 临时 ACL 在全部部署验收后撤销并复核。

## 2026-08-30 管理员用户全量搜索与分页部署

### 候选隔离与质量门

- 共享工作树同时包含已上线账号/答疑删除、本次用户搜索和尚未部署的竞争赛队伍删除，未直接构建整个工作树。运行 `help-delete-20260829` Backend 与当前 users 模块逐文件哈希比较后，只有 `repository.py`、`router.py` 不同；精确 diff 只包含中文/英文角色状态搜索、LIKE 字面转义和页码上限。
- Backend 候选以运行镜像为底只覆盖上述两个文件。Frontend 从 Git HEAD 发布基线重建，叠加已上线通知/作业/答疑/账号删除、公式能力和本次三个搜索文件，明确排除竞争赛队伍详情与删除面板；生产构建通过，编译产物“搜索用户”与“下一页”存在，“删除队伍”匹配为 0。
- 无网络 Backend 候选静态 OpenAPI 为 114 个路径，`page.maximum=10000`，账号本人/管理员删除和答疑删除路径继续存在；Backend/Frontend 均为 UID 10001。Frontend 在无网络容器访问管理员页因无法解析 `backend` 返回预期隔离错误，接入只通 Backend 的 `app_net` 后无 Cookie 请求返回 307 `/login`。

### 加密部署前备份

- 复用 0700 的 `/tmp/pnx-account-deployment-backups`、独立 0700 状态目录、周基线清单和隔离 GPG 接收公钥，生成 `pnx-backup-20260829T155430Z-daily`。归档 5,679,123 字节、0600，SHA-256 `525a53cef7bb08676b31598e9978a67a45df1301ca558587591e8e57438c2e4b`。
- 备份包含 5,574,189 字节的完整 PostgreSQL 自定义格式 dump；MinIO 相对 `pnx-backup-20260829T122839Z-weekly` 为增量模式，库存保持 2,885 个对象/2,038,164,595 字节，payload 和删除对象均为 0。
- 外层校验和通过。首次把解密流提前截取单个 dump 时因 tar 结束读取使 GPG 收到 SIGPIPE、返回 141，不视为归档校验成功；随后在专用临时 0700 目录完整解密，内部 `SHA256SUMS` 与 PostgreSQL 17 `pg_restore --list` 通过，临时明文由 trap 删除。

### 定向替换

- `.env` 固定 `APP_IMAGE_TAG=admin-user-search-20260829`；Compose 解析确认 Backend/Worker/Migrate 指向新 Backend、Frontend 指向新 Frontend，PostgreSQL、MinIO、Nginx 固定镜像与内部数据网络不变。
- 按 `backend worker`、`frontend nginx` 两阶段执行显式 `--env-file .env --no-deps --force-recreate` 替换，阶段健康门均通过。没有调用发布脚本，因为该脚本会强制运行 migrate 并要求当前 HTTP 内网环境未配置的 TLS 证书；本次无迁移修复采用既有手工定向流程。
- Backend/Worker 镜像为 `sha256:8ce5a025653e05eeb2a42119cf0c20b4c258b76a82a39c8abeb24be607388880`，Frontend 为 `sha256:005345c40946bc33826565aebc8b441bc5f0600778384618042e6d885bec7be8`。PostgreSQL/MinIO 容器和卷未重建，未运行 migrate，数据库按部署前记录保持 `20260829_0015` 基线。

### 运行验收与数据边界

- 最终六服务 healthy、重启次数 0；Backend/Worker/Frontend 均为 `appuser`。`/login`、`/health/live`、`/health/ready`、`/health/worker`、`/nginx-health` 返回 200。
- `/admin/users` 无 Cookie 原始响应为 307 且 Location 为 `/login`；`/api/v1/admin/users` 无 Cookie 为 401。没有携带管理员 Session、Cookie 或其他认证材料，未读取用户列表，因此没有使用生产账号数据做功能测试。
- 运行镜像静态 OpenAPI 为 114 个路径，页码最大值 10000，账号本人/管理员删除与答疑删除路径继续存在；搜索与分页的业务正确性沿用部署前 Mock、组件、静态契约和生产构建质量门。
- Backend、Worker、Frontend、Nginx 启动窗口对 Traceback、严重错误、事务中止、权限拒绝、连接拒绝与未处理异常的聚合计数均为 0。本轮未调用账号/答疑删除、飞书同步、上传、认证或其他业务写接口。

### 回滚与剩余风险

- 回滚可把 `.env` 固定标签恢复为 `help-delete-20260829`，按 Backend/Worker、Frontend/Nginx 相同顺序替换；本次无 Schema 变化，不需要数据库降级。旧 Backend/Frontend 镜像继续保留。
- 周完整备份、每日增量备份、校验材料、状态清单和临时 GPG 密钥环仍位于同一宿主机 `/tmp`，只能作为短期恢复材料；必须迁移到受控独立介质并将加密归档与解密材料分离保存。
- Docker socket 仍有 `user:pnx:rw-` 临时命名 ACL。普通 `setfacl -x` 被宿主机拒绝，`sudo -n` 要求密码；需部署方交互执行 `sudo setfacl -x u:pnx /var/run/docker.sock`，再以 `getfacl -cp` 确认只剩基础 owner/group/mask/other 条目。

## 2026-08-30 管理员删除队伍部署

### 候选隔离与质量门

- 部署前运行容器仍为 `help-delete-20260829`。共享工作树另含管理员用户搜索/分页源码，未获本任务部署授权；Backend 以运行镜像为底只覆盖四个 competitions 文件，Frontend 恢复既有用户页后叠加已上线能力与队伍删除，避免范围串入。
- 源码阶段后端定向 16 项、完整 291 项、Ruff、170 文件格式和 120 源文件严格 Mypy 通过；原始前端 23 文件/104 项、ESLint、严格 TypeScript 和生产构建通过。隔离前端最终 23 文件/102 项、ESLint、严格 TypeScript 和 Docker 镜像内默认 Turbopack 生产构建通过。
- 镜像静态 OpenAPI 为 114 个路径；既有 `/api/v1/admin/teams/{team_id}` 路径新增 DELETE 方法，响应含 204/422。Backend 与 Frontend 镜像均以 `appuser` 运行。

### 部署前备份与定向替换

- PostgreSQL 17 快照 `/tmp/pnx-training-before-team-delete-20260829T161603Z.dump` 为 5,574,204 字节、0600，SHA-256 `1ebc990cbec3023a54a4fe6672a37d446af2608efb09dc5f4135786866b1a301`；同版本 `pg_restore --list` 303 个 TOC 条目通过。该文件只适合作为本机短期恢复材料。
- `.env` 固定 `APP_IMAGE_TAG=team-delete-20260830`。Backend/Worker 镜像 ID 为 `sha256:2d58004f482cefa3e01a3bd24877074fb72f496b8e9f3f067b484fcaf21efe97`，Frontend 为 `sha256:78fd991ced0d9fd308eba17c74cea4bd939fae78332d290aa1201610ee016015`。
- 先运行 Compose migrate 一次性服务，确认无 Schema 变更；随后按 Backend/Worker、Frontend、Nginx 顺序使用 `--no-deps --force-recreate` 替换。PostgreSQL、MinIO、卷和网络未重建。

### 运行验收与数据边界

- 六服务最终均 healthy、重启次数 0；Backend/Worker/Frontend 为 `appuser`。`/login`、`/api/v1/health/live`、`ready`、`worker` 与 `/nginx-health` 均为 200，Alembic 为 `20260829_0015 (head)`。
- 无 Cookie 的虚拟队伍 DELETE 返回 401。真实管理员队伍详情的 HTML 因 loading 边界先流式返回 200 骨架，响应内含 `NEXT_REDIRECT;replace;/login;307;` 和跳往 `/login` 的 meta refresh；后端 auth/me、管理员用户和队伍详情 API 全部 401，未泄露受保护内容。
- 部署前后聚合完全一致：用户 157、赛事 1、队伍 2、当前成员 2、团队提交 0、提交版本 2、答疑 0、知识文档 897、知识媒体 1010、账号清理 Outbox 0。启动窗口日志无 Traceback、事务中止、未处理异常或连接错误。
- 验收未携带管理员 Session/Cookie 调用任何真实 DELETE，未触发飞书同步、上传、认证、邮件或其他业务写入。隔离候选与本次 Turbopack 临时日志已精确清理；生产备份、当前/回滚镜像、卷与网络保留。

### 回滚与剩余风险

- 应用回滚可将标签恢复为 `help-delete-20260829` 并按 Backend/Worker、Frontend、Nginx 同序替换；本次无 Schema 变化，无需 Alembic 降级。已执行的物理删除不能由应用回滚恢复，只能按删除前备份采用明确恢复流程。
- Docker socket 仍有 `user:pnx:rw-` 临时 ACL；`sudo -n setfacl -x` 因需要密码失败。部署方须交互执行 `sudo setfacl -x u:pnx /var/run/docker.sock`，再用 `getfacl -cp` 与 `stat` 确认只剩基础 ACL 且为 `root:docker 0660`。

## 2026-08-30 队伍删除发布后的用户搜索回退纠正

### 根因证据

- 用户报告仍只显示 100 个后，当前 `.env` 与六服务已变为后续 `team-delete-20260830`，并非此前验收的 `admin-user-search-20260829`。队伍部署记录也明确候选从 `help-delete-20260829` 基线构建且排除用户搜索源码。
- 直接读取运行 Frontend 唯一 `admin/users` API chunk，函数签名只有 `activity,pageSize=100`，请求只包含 `page_size`，没有 `page/search`；运行 Backend users 模块哈希比较也显示 Repository/Router 回到旧版，其余 users 文件与工作树一致。
- 因而根因是后续发布的基线选择覆盖已上线搜索，不是 PostgreSQL 只有 100 个，也不是当前 Repository 的 `COUNT(*)` 或 LIKE 条件错误。该回归同时影响后端全量搜索和前端翻页。

### 合并候选与硬断言

- Backend 以当前 `team-delete-20260830` 为底，只覆盖当前 `users/repository.py` 与 `users/router.py`；候选静态 OpenAPI 114 个路径，`page.maximum=10000`，队伍、账号本人/管理员和答疑 DELETE 均存在，UID 为 10001。
- Frontend 从 Git HEAD 发布基线叠加全部已上线源码、账号注销、公式、队伍删除和用户搜索。临时上下文对每个白名单文件执行 `cmp`，并在构建前断言 `USER_PAGE_SIZE=20`、API `page/search`、搜索界面和 `deleteTeam`。
- 为排除旧 Turbopack chunk 复用，本轮使用 `docker build --no-cache`；`npm ci` 安装/审计 499 个包、0 漏洞，Next.js 编译与严格 TypeScript 通过。
- 构建后不依赖源码推断，直接扫描候选运行文件：唯一用户 API 实现包含 `page`、`page_size` 与 `search`，管理员路由含 `pageSize:20`；“搜索用户”“下一页”“删除队伍”均存在。接入只通 Backend 的应用网络后，无 Cookie 管理员页为 307 `/login`。

### 备份复核与定向纠正

- 没有再次读取当前生产数据库。只复核最近 `/tmp/pnx-training-before-team-delete-20260829T161603Z.dump`：5,574,204 字节、0600，SHA-256 `1ebc990cbec3023a54a4fe6672a37d446af2608efb09dc5f4135786866b1a301` 匹配，PostgreSQL 17 `pg_restore --list` 成功。
- `.env` 固定为 `team-user-search-20260830`。按 Backend/Worker、Frontend/Nginx 两阶段使用显式 `--env-file .env --no-deps --force-recreate` 定向替换；未运行 migrate，PostgreSQL/MinIO 容器、卷和网络未重建。
- Backend/Worker 镜像为 `sha256:0a3a88a7aeabed366b708695c867f0ee3bb6077bce05e441a8ed6fbc5041d2e3`，Frontend 为 `sha256:10552d3e6b750557e05d27527e06cac992091d7f80850f19c7a270a220d632f3`。最终运行 chunk 再次确认 `pageSize:20`、`page/search`、搜索界面和队伍删除同时存在。
- 六服务 healthy、重启 0；五个健康入口 200，`/admin/users` 匿名 307、用户 API 匿名 401。四个应用容器日志错误关键词聚合为 0；没有使用管理员 Session/Cookie、没有读取用户列表或调用任何业务写接口。

### 回滚与防复发

- 当前没有更早的单一镜像同时包含两项功能：回滚到 `team-delete-20260830` 会再次失去用户搜索，回滚到 `admin-user-search-20260829` 会失去队伍删除。应优先前滚修正 `team-user-search-20260830`，数据库无需降级。
- 后续从运行镜像制作隔离候选时，必须把所有已上线但尚未进入 Git HEAD 的能力列为显式保留清单，并对关键运行 chunk 做构建后断言；仅以“排除共享工作树其他任务”为边界会造成已上线能力回退。
- Docker socket 临时 ACL 与 `/tmp` 备份持久化风险未改变；全部 Docker 收尾后仍需交互式 sudo 撤销 ACL，并把备份迁移到受控独立介质。
