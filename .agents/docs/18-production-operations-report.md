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
