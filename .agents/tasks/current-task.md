# 当前任务

## 2026-10-25 分步提交与推送

当前修改已按后端、队伍前端、物资前端与文档四组整理，验证结果移入 `completed.md`，唯一计划为 `.agents/plans/plan_commit_push_20261025.md`。推送目标为 `origin/main`，本次不涉及部署或新增迁移。

## 物资标签二维码优先（2026-10-25）

源码、验证与生产部署已完成，详情移入 `completed.md`，唯一计划为 `.agents/plans/plan_material_label_layout.md`。Frontend 热修标签 `materials-print-session-20261025`，已修复真实 UUID 密度与同页重复配对；六服务健康，待 D110 实物定位与扫码验收，无新增数据库迁移。

## 物资批量排序修复（2026-10-25）

源码、隔离验证与生产部署完成，结果移入 `completed.md`；唯一计划为 `.agents/plans/plan_material_ordering.md`。固定标签 `materials-order-label-20261025`，现有 80 件物资排序已在恢复副本验证；无新增数据库迁移。

## 队长联系方式与配额显示修复（2026-10-19）

源码、隔离 PostgreSQL 验证和生产部署均已完成，详细结果已移入 `completed.md`；唯一正式计划为 `.agents/plans/plan_team_contact_and_quota_display.md`。生产固定标签 `team-contact-composition-20261019`，数据库为 `20261019_0032`，六服务健康。待现场确认真实学生浏览器填写微信及查看队长联系方式；备份与解密私钥仍需异机分离保存。

## 组队方向配额调整（2026-10-19）

源码、隔离 PostgreSQL 并发验证及生产部署均已完成，结果移入 `completed.md`；唯一正式计划为 `.agents/plans/plan_team_composition_update.md`。生产固定标签 `team-composition-20261019`，数据库保持 `20261013_0031`，无迁移，六服务健康；真实学生浏览器组队操作仍待现场验收。

## 物资管理（2026-10-16）

源码与生产部署均已完成，详细结果移入 `completed.md`；唯一正式计划为 `.agents/plans/plan_material_management.md`。生产固定标签 `materials-20261016`、数据库 `20261013_0031`，六服务健康。待现场验证事项：受信 HTTPS 入口下的 D110 实物打印与在校实物扫码；当前 HTTP 入口不提供 Web Serial 安全上下文。

## 飞书培训综述图表与双语润色（2026-10-07）

已在原中英文独立 LaTeX 源文件中加入系统闭环图、视觉处理链图和培训阶段表，并润色各方向的课程说明与实践建议。两版各保留五个显式分页和相同的 37 个飞书来源链接；结构静态检查通过。内置编译器因平台标准目录错误无法编译，隔离容器的软件源也不可用；新版 PDF 与实测六页排版仍待验证，旧 PDF 仅对应 2026-09-25 版本。正式计划继续使用 `.agents/plans/plan_training_illustration.md`；无业务代码、数据迁移或飞书同步。

## 校内赛队伍改名、申请与换队（2026-10-03）

源码与生产部署均已完成，详细结果移入 `completed.md`；唯一正式计划为 `.agents/plans/plan_team_change_and_applications.md`。固定标签 `team-applications-20261003`，生产数据库为 `20261003_0030`，六服务健康。加密备份已从空卷恢复并对账 2,291 个对象；未发送真实申请邮件。现有组队开放开关保持开启。

## 备用域名登录来源修复（2026-09-30）

已将 `pnx-tutorial.demonmaster.cn` 加入当前 Docker Compose 的 `TRUSTED_HOSTS` 与 `CSRF_TRUSTED_ORIGINS`，保持 `APP_BASE_URL=http://10.4.150.222:5000` 主链接不变。后端新增显式备用 Origin 白名单并完成镜像重建；Backend、Worker healthy。备用域名登录携带正确 Origin 时已通过来源校验，错误账号返回正常 `INVALID_CREDENTIALS`，不再返回 `CSRF_FAILED`。正式计划为 `.agents/plans/plan_trusted_csrf_origins.md`。

## 工作区提交整理（2026-09-30）

既有改动已按知识库、业务后端、业务前端和文档记录整理；详细验证及提交说明移入 `completed.md`，唯一计划为 `.agents/plans/plan_commit_cleanup_20260930.md`。本次仅本地提交，未推送或执行部署、数据迁移。

## 作业与通知统一邮件提醒（2026-09-30）

源码与部署均已完成，记录已移入 `completed.md`，正式计划为 `.agents/plans/plan_assignment_notification_email_reminder.md`。固定标签 `email-reminder-20260930`，数据库保持 `20260927_0029`。Docker 生产构建、前端完整 179 项、后端定向 106 项、静态检查、备份空卷恢复和隔离 PostgreSQL 入队验证通过；六服务健康，无迁移，未发送真实邮件。

## 已关闭作业重新打开（2026-09-28）

源码与生产部署已完成，正式计划为 `.agents/plans/plan_assignment_reopen.md`；完整记录已移入 `completed.md`。生产标签为 `assignment-reopen-20260928`，数据库保持 `20260927_0029`。

## 作业截止时间移除（2026-09-27）

源码、迁移、验证及生产部署已完成，详情已移入 `completed.md`；正式计划为 `.agents/plans/plan_assignment_remove_deadlines.md`。生产运行标签为 `assignment-no-deadline-20260927`，数据库为 `20260927_0029`。历史修正截止任务仅作阶段记录。

## 作业修正截止及学生完成状态（2026-09-27）

源码、隔离验证及生产部署均已完成，记录已移入 `completed.md`；唯一计划为 `.agents/plans/plan_assignment_review_deadline.md`。生产数据库为 `20260927_0028`。

学生状态标签字体微调此前已完成并部署，上一 Frontend/Compose 标签为 `assignment-status-font-20260927`；Backend/Worker 仍运行原 `review-deadline-completion-20260927` 镜像，数据库仍为 `20260927_0028`。

学生列表公共截止、个人延期和修正截止字体已继续统一并部署；当前 Frontend/Compose 固定标签为 `assignment-deadline-font-20260927`，Backend/Worker 镜像及数据库版本不变。完成记录已移入 `completed.md`。

2026-09-25 独立交付的飞书培训综述已扩写为中、英文各六页的独立 LaTeX 文稿与 PDF，完成情况记录于 `completed.md`；对应唯一计划为 `.agents/plans/plan_training_illustration.md`。该交付不改变下方平台开发任务状态。

# 当前任务：站内内容引用知识库文档（2026-09-21）

- 正式计划：`.agents/plans/plan_internal_knowledge_references.md`。
- 已完成公告正文、作业说明、作业私密评语的统一知识库文档选择器；引用使用稳定 `source_token`，知识库页面兼容 `source` 与既有 `doc` 参数，公告邮件自动补全绝对链接。
- 已补充前后端针对性测试并通过；无 API、数据库字段、迁移、依赖或飞书写回。
- 2026-09-22 已部署标签 `knowledge-references-20260922`：Backend/Worker `sha256:021445cc5c7325fbe0b809662d979f6d97d473d7be1e5de8951fcc4e69e930c9`，Frontend `sha256:aa343aac5818205d1f8be7b593fe8fc7b5d60d2c65c6b17bad2a67d1066951fd`；数据库保持 `20260921_0027 (head)`，仅执行幂等迁移检查，PostgreSQL/MinIO 未重建。
- 部署后六服务 healthy、重启 0；`/login`、`/health/live`、`/health/ready`、`/health/worker` 返回 200，匿名 `/knowledge` 为 307、`/api/v1/knowledge` 为 401，近期错误日志无异常。代码提交 `2e2757d`、`0a659c1`，文档提交 `d422d83`。

## 置顶、当前设备与品牌字标视觉优化（2026-09-18）

本轮沿用 `.agents/plans/plan_ui_visual_refinement.md` 和既有 SVG 图标体系，仅调整前端表现层：置顶状态补充图钉图标与胶囊标签；当前设备补充显示器图标与绿色语义状态；共享侧栏、移动端抽屉及认证壳层的 PNX / TRAINING HUB 调整为分层字标。无 API、权限、数据库、迁移或新依赖变化。

已部署：前端定向测试 31 项、ESLint 和严格 TypeScript 通过；容器内 Next.js 生产构建通过。Frontend 镜像 `ui-visual-refinement-20260918` 与 Nginx 已替换，Frontend/Nginx healthy，`/login`、`/health/live`、`/health/ready`、`/health/worker` 均返回 200；旧 Frontend 镜像保留为 `ui-visual-refinement-rollback-20260918`。无 API、权限、数据库、迁移或新依赖变化。

## CI 后端测试收集修复（2026-09-17）

GitHub Actions 后端任务已改为在既有 `backend/` 工作目录执行 `python -m pytest`，修复 Python 3.12 下直接调用 `pytest` 控制台脚本时项目根目录未进入模块搜索路径、全部测试在收集阶段报 `ModuleNotFoundError: app` 的问题。该修复不改业务代码、依赖、API、数据库或迁移；属于单行 CI 入口修复，无需新增正式计划。

## 作业私密评语图片（2026-09-16）

源码与部署已完成。唯一正式计划为 `.agents/plans/plan_assignment_feedback_images.md`，决策为 ADR-072 及放宽大小边界的 ADR-073。固定标签 `assignment-feedback-images-20260916` 已上线，真实管理员可为具体作业版本上传并随评语保存最多 10 张安全图片；学生本人和真实管理员可在网页评语区直接查看及下载，邮件、提醒和审计不暴露私密内容。生产数据库已应用 `20260916_0026`。

2026-09-16 用户进一步确认放宽图片大小：当前限额为单张 10 MiB、每条评语合计 50 MiB，数量 10 张与图片类型不变；ADR-073 取代 ADR-072 中的旧大小边界。通知正文图片限额不变。

相关后端 74 项、前端 167 项、Ruff/格式、相关严格 Mypy、ESLint、Alembic 单 head、`0025 ↔ 0026` 离线 SQL 与差异空白检查通过；限额放宽后已再次通过后端定向回归、129 个相关 Python 源文件严格 Mypy、前端完整 27 文件/167 项、Ruff/193 文件格式及 ESLint。部署门进一步把 Next.js/ESLint 配置升级到 16.3.5、Sharp 升级到 0.35.4，生产依赖审计为 0 漏洞，严格 TypeScript 与镜像内生产构建通过。新加密备份已从空卷恢复 1,736 个对象并零差异对账，隔离副本完成真实 `0025 → 0026 → 0025 → 0026`；生产六服务 healthy、重启 0，稳定期无应用严重错误或 Nginx 5xx。完整后端套件仍保留此前既有 ASGI 环境长时等待记录，未据此宣称全量通过。

## 知识库正文完整性与样式修复（2026-09-14）

已部署为 `knowledge-content-fidelity-20260914`，唯一计划仍为 `.agents/plans/plan_feishu_knowledge_sync.md`。标题子树递归展示、标题/正文 Emoji、未知富文本安全降级、正文树缺失引用 fail-fast、提示块完整色号和内部样式已覆盖定向与镜像内运行验收；无迁移、新依赖或真实飞书同步。新加密备份已空卷恢复 1,683 个对象且零差异，六服务 healthy、重启 0，数据库保持 `20260910_0025`。已有成功快照已获得前端展示修复；同步侧增强需真实管理员下一次手动成功同步后作用于新快照。

## 知识库视频播放交付（2026-09-10）

正文 MP4/WebM 已部署为 `knowledge-video-20260910`，2026-09-10 19:21:25（北京时间）完成切换。六服务 healthy、重启 0，数据库保持 `20260910_0025`；完整隔离候选后端 489 项通过/1 跳过、前端 165 项通过，构建和静态检查通过，新备份空卷恢复 1,455 个对象零差异。真实视频 Range/206、inline 与默认 attachment、匿名鉴权均通过；切换后稳定期无 5xx。唯一计划为 `.agents/plans/plan_feishu_knowledge_sync.md`，完成记录已更新。浏览器编码/全屏/签名过期重试需人工确认；同机备份仍须异机保管。本次明确排除十五天账号自动擦除及相关提示，下面其他任务仍未发布，不得将工作区整体直接构建上线。

## 当前状态

2026-09-14 管理员人员技术组分布已部署为 `admin-user-distribution-20260914`：数据库保持 `20260910_0025`，六服务 healthy、重启 0；新备份完成空卷恢复和 1,659 个对象零差异对账。完成记录与唯一计划已更新，未调用带认证业务写接口。

2026-09-11 十五天自动账号清理部署和旧 Docker 清理已完成，完成项移入 `completed.md`，唯一计划 `plan_account_activity_cleanup.md`。当前标签 `account-auto-cleanup-20260911` 完整包含知识库视频功能，18:08:55（北京时间）切换完成；六服务健康、重启 0，无迁移，205 账号/19 激活管理员/0 超期候选，未实际删除账号。用户明确要求跳过备份，35 个旧标签/18 个唯一镜像及 1 个无挂载已退出迁移容器已删；不再能直接使用旧本地镜像回滚，现有备份和数据卷保持。后端 522 通过/1 跳过、前端 166 通过，静态/构建和运行验收通过。上方视频部署段为历史阶段记录，其“排除自动擦除”不再代表当前部署。

2026-09-10 “学生自助方向权限与人数分布”已完成部署，标签 `team-direction-composition-20260910`，数据库 `20260910_0025`；六服务 healthy、重启 0，数据及持久卷保持，两个开关仍关闭。已补齐线上“嵌入式-控制/嵌入式-硬件”名称；备份恢复、迁移往返与匿名验收通过。切换期间 4 次短暂 5xx，切换完成后稳定期无 5xx。完成项已移入 `completed.md`，唯一计划不变。

原有修改已提交 `4fd1d3b`，本功能及部署记录新增修改尚未提交。管理员可按需在校内赛队伍管理页开启学生自助改方向；仍需部署方补齐异机备份/私钥分离存储和既有 HTTP 环境的 HTTPS 改造。

2026-09-08 “新入技术组学生历史作业可见性”已完成部署：生产迁移 `0023 → 0024` 新增 3 条匹配历史作业受众；新加密备份已从空卷恢复 1,419 个对象，隔离迁移幂等与升降级往返通过。随后接续的 `announcement-inline-images-20260908` 已确认完整包含本修复；当前六服务 healthy、重启 0，PostgreSQL/MinIO 未重建，未使用真实登录态或调用业务写接口。

2026-09-08 “作业提交完成确认与三栏总览”已完成并部署：源码基于 `cb551f5`，发布门补充提交为 `f145ec8`；后端完整 422 项、Ruff、180 文件格式、155 文件严格 Mypy，前端 26 文件/156 项、ESLint、严格 TypeScript 和生产构建通过。新备份 `pnx-backup-20260908T045305Z-daily` 已从空卷恢复 1,384 个对象并零差异对账，隔离副本完成 `0022 ↔ 0023` 往返和模型漂移检查。固定标签 `assignment-completion-20260908` 已按 Backend/Worker、Frontend/Nginx 两阶段上线，生产为 `20260908_0023 (head)`，六服务 healthy、重启 0；PostgreSQL/MinIO 未重建，验收未携带管理员 Session 或调用真实完成确认写接口。

2026-09-08 已完成生产 MinIO 未引用对象与冗余备份收敛：删除 1,875 个超过 7 天且不在普通文件/知识库资产引用集合中的历史 `knowledge/` 对象，释放 1,336,875,776 字节；清理后 1,384 个对象与 1,384 个有效引用完全一致。新每日备份 `pnx-backup-20260908T032301Z-daily` 已从空卷恢复且未引用对象为 0；仅保留其依赖的周基线与该最新每日增量，旧每日备份及测试伪备份已删除。生产六服务保持 healthy。

2026-09-08 “管理员控制学生组队开放、简介按技术组筛选”已完成源码、分步提交、完整质量门与生产部署，完成记录已移入 `.agents/tasks/completed.md`。`20260908_0022` 默认关闭学生组队；关闭时个人简介填写、浏览、搜索和技术组筛选继续可用，学生组队写接口由后端强制阻断。固定标签 `team-participation-controls-20260908` 已两阶段上线，六服务 healthy、重启 0，生产为 `20260908_0022 (head)`；PostgreSQL/MinIO 容器和数据卷未重建，验收未使用真实登录态或产生业务写入。


2026-09-06 “反馈答疑管理员蓝点、普通业务附件页内预览与个人作业返回上下文”已完成实现、完整质量门、无缓存候选构建、加密备份空卷恢复、两阶段部署和稳定期验收，完成记录已移入 `.agents/tasks/completed.md`。当前标签为 `help-preview-navigation-20260906`，六服务 healthy、重启 0，Alembic 保持 `20260904_0020 (head)`；PostgreSQL/MinIO 未重建，关键业务聚合无变化。本次源码、基础设施和中文文档已按逻辑分步提交，未推送；远端写权限问题仍需仓库所有者提供 HTTPS 凭据或授权 SSH 公钥后处理。

2026-09-05 已完成“作业允许一次选择并上传多张图片”源码候选，唯一正式计划为 `.agents/plans/plan_assignment_multiple_images.md`，ADR-060 已接受。作业上传器按当前版本剩余的 100 个附件和总字节额度预检批次，再按选择顺序逐文件复用既有安全 multipart 会话；成功项进入待提交清单，失败项及后续队列可继续，通知上传保持单文件。前端定向 8 项、完整 25 文件/141 项、ESLint、严格 TypeScript和 Next.js 16.3.2 构建，后端定向 4 项、完整 382 项、Ruff、155 文件格式检查和严格 Mypy 全部通过。无 API 形状、依赖、数据库或迁移变化，尚未构建镜像或部署。

2026-09-05 已完成并部署“发布作业后允许修改”，唯一正式计划为 `.agents/plans/plan_published_assignment_editing.md`。隔离候选未纳入管理员学生视图恢复、独立队伍等并行改动，通过后端 396 项、前端 25 文件/139 项、全部静态/构建、安全与恢复门。固定标签 `published-assignment-editing-20260905` 已两阶段上线，Backend/Worker 为 `sha256:83fce481995c…`、Frontend 为 `sha256:e7d2f455da9b…`；六服务 healthy、重启 0，Alembic 保持 `20260904_0019 (head)`。新备份 `pnx-backup-20260905T105700Z-daily` 已从空卷恢复并对账 3,141 个对象，应用回滚标签已固定。健康、匿名权限、运行产物、核心聚合及稳定期日志均通过；未携带管理员 Session、未调用真实作业 PATCH，本轮无数据迁移，PostgreSQL/MinIO 未重建。

部署后真实管理员手动触发的飞书知识库同步已在第 2 次尝试成功，最新快照为 216 篇文档、1,241 个资源；长任务期间 Worker 因循环心跳陈旧短暂 unhealthy，但进程未重启且任务持续推进，完成后已恢复 healthy。该健康误报限制已加入 `.agents/tasks/backlog.md`。

2026-09-05 已完成“管理员作业发布权限一致性修复”源码，唯一正式计划为 `.agents/plans/plan_admin_assignment_publish_permissions.md`。只读日志与脱敏 Session 聚合确认失败账号均为 `active admin`，实际阻塞来自同一 Session 在其他标签切入 `student_view=true` 后陈旧管理页继续提交。作业管理组件现于首次 `FORBIDDEN` 后调用受 CSRF 保护的关闭学生视图接口，并在后端确认真实角色仍为 `admin` 后只重试原请求一次；创建、保存、发布、关闭、删除和个人延期统一覆盖，普通学生或已降级账号仍被拒绝。管理员权限定向 16 项、完整前端 25 文件/137 项、ESLint、严格 TypeScript和 Next.js 16.3.2 生产构建通过。本轮无 API 或数据库变更、无迁移，未调用运行环境真实管理写接口，尚未构建镜像或部署。

2026-09-04 已完成“保留校内赛页面并改为独立队伍中心”源码候选，唯一正式计划为 `.agents/plans/plan_standalone_teams.md`，ADR-059 已接受。当前页面不展示赛事实体，激活学生无需管理员先创建赛事即可直接创建队伍、凭邀请码加入或主动自动分配；旧队伍由 `20260904_0020` 隔离到 legacy 表，新产品队伍表从空表开始，历史赛事提交和对象不删除。Backend 只注册 `/teams*` 与 `/admin/teams*`，所有当前正式版本均为个人作业版本；旧前端赛事详情只兼容重定向。后端 378 项、Ruff、177 文件格式和 155 文件严格 Mypy，前端 25 文件/135 项、ESLint、严格 TypeScript、Next.js 16.3.2 构建，隔离 PostgreSQL `0019 → 0020 → 0019 → 0020` 与 OpenAPI 路径断言全部通过。本轮未连接或迁移运行 PostgreSQL/MinIO，未构建或部署 Docker；上线前必须先完成数据库与对象存储同点备份。

2026-09-04 已完成并部署“问卷查看内容、编辑问卷与全部操作桌面同行”热修。上一轮仅让主操作容器单行，详情组件仍主动另起一行；现已把所有当前命令合并进唯一操作组，桌面 `lg` 起整体和按钮文字均不换行，移动端仍可换行。代码提交 `fd9311f`；前端问卷定向 27/27、完整 25 文件/138 项、ESLint、严格 TypeScript、Next.js 16.3.2 构建和 `git diff --check` 通过。固定标签 `questionnaire-actions-row-20260904` 已只替换 Frontend/Nginx，Frontend 为 `sha256:3ba9fa4315a59833d093f6c992d8248a1ba3aa599108dce62091e2fe214e2650`，Backend/Worker 保持 `sha256:d668cd915766892fbb059ebce9e7118262cbe6db68d6d86c3ad491aef22a3bc6`；六服务 healthy、重启 0，Alembic 保持 `20260904_0019 (head)`。未使用管理员 Session、未执行业务写入或迁移，知识库图片说明继续排除。

2026-09-04 已完成并部署“管理员永久删除问卷与桌面操作按钮单行”。任意状态问卷可由真实管理员二次确认永久删除；成功后立即移除卡片及缓存，活动邮件与问卷数据按事务规则清理。移动端操作区保留换行，桌面 `lg` 起全部当前按钮保持同一行且文字不换行。固定标签 `questionnaire-delete-layout-20260904` 已两阶段无构建上线，Backend/Worker 为 `sha256:d668cd915766892fbb059ebce9e7118262cbe6db68d6d86c3ad491aef22a3bc6`，Frontend 为 `sha256:41ea6351cbf52c0dbae3e8358e85497b6d690682fad8742e1c1358321ac63fe8`；六服务 healthy、重启 0，`20260904_0019` 无漂移，PostgreSQL/MinIO 未重建。新备份已空卷恢复 3,115 个对象且引用差异为 0；验收未调用真实 DELETE 或其他业务写接口。知识库图片说明仍未部署。

2026-09-04 已完成并部署“问卷开放后可修改非答案结构”，唯一正式计划为 `.agents/plans/plan_student_teams_auto_assignment_intentions.md`，ADR-057 已接受。`draft` 保持完整编辑，`open/closed` 可修改标题、说明、题目文字、提交上限、时间窗口和填写范围，但题量、题型及选项数量/文字/顺序冻结；`archived` 只读。合法修改保留问题/选项 UUID、回答、累计次数和二维码 token，受限范围每次保存复核启用组，revision/结构/受众/提交失败均整体回滚。后端定向 82 项、完整 384 项及全部静态门，前端定向 23 项、完整 25 文件/134 项、生产构建及全部静态门通过。新备份完成空卷恢复和 3,115 个对象对账；生产实际缺失的现有 `0018 → 0019` 已执行一次，12 份旧问卷默认全体，模型无漂移。固定标签 `questionnaire-live-edit-20260904` 已两阶段上线，Backend/Worker `sha256:5f2a114b…`、Frontend `sha256:cc1e3a67…`；六服务 healthy、重启 0，匿名权限、聚合和日志验收通过。知识库图片说明未进入候选；兼容回滚镜像保留 0019，不降级数据库。

2026-09-04 已完成“问卷支持分技术组填写”源码候选，继续使用唯一正式计划 `.agents/plans/plan_student_teams_auto_assignment_intentions.md`，ADR-056 已接受。问卷草稿可选择全部学生或 1～50 个启用技术组，首次开放后冻结受众；学生列表、详情、二维码和提交均按当前 `users.direction_id` 后端鉴权，非目标学生统一 404。统计分母及邮件全部范围按当前目标激活学生计算，手动成员和技术组邮件不能越过问卷受众；迁移 `20260904_0019` 让旧问卷默认面向全体。后端定向 84 项、完整 376 项、Ruff、175 文件格式和 154 文件严格 Mypy；前端定向 21 项、完整 25 文件/132 项、ESLint、严格 TypeScript、生产构建、`0018 → 0019 → 0018` 离线 DDL 与 `git diff --check` 全部通过。本轮未连接或迁移运行 PostgreSQL/MinIO，未创建真实邮件任务，也未构建或部署 Docker。

2026-09-04 已完成“飞书知识库图片文字说明保留与网页展示”源码候选，继续使用唯一正式计划 `.agents/plans/plan_feishu_knowledge_sync.md`，ADR-055 已接受。Backend 从 `image.caption.content` 生成清洗、限长的可选纯文本 `caption`；Frontend 在单图和画廊的对应图片下方显示 `figcaption`，同时用于图片与预览可访问名称，无说明时回退文件名，白板行为不变。后端知识库 15 项、全量 Ruff 规则、目标格式和相关 Mypy，前端知识库 17 项、全量 ESLint、严格 TypeScript、生产构建及 `git diff --check` 全部通过。本轮无数据库迁移或新依赖，未连接运行 PostgreSQL/MinIO、未触发飞书同步，也未构建或部署 Docker；部署后仍须真实管理员手动成功同步一次。

2026-09-04 已完成并部署“仅标题为意向选择的问卷可按第一志愿配置方向”。前端只在标题去除首尾空白后精确等于“意向选择”时渲染入口，Backend 在读取题目、方向、回答、用户或写审计前独立复核，其他标题返回 `422 INVALID_INTENTION_DIRECTION_SURVEY`。固定标签 `questionnaire-title-gate-20260904` 已两阶段上线，Backend/Worker 镜像为 `sha256:680fb42e542616179e5e4066966dc1968da6d87b13347a31aee8897f2100617e`，Frontend 为 `sha256:f2b8df9bfc2717160aa92850bd260353bbed3fe7f0b13b13a9a34a7a23d76831`；六服务 healthy、重启 0。未运行迁移，PostgreSQL/MinIO 容器未重建，部署前后业务聚合一致；验收未携带管理员 Session、未执行真实批量配置，既有 143 条用户方向审计和 1 条汇总审计保持不变。

2026-09-03 已完成并部署“按所有人的第一志愿配置技术方向”。固定标签 `questionnaire-first-choice-20260903` 已两阶段上线，Backend/Worker 镜像为 `sha256:baed161838bed54fd6002439dd0c5facd7362cef90479a1f19a448d94a42edb6`，Frontend 为 `sha256:2da9cf011f66c3e3bfe2edd5f2ef98bd875a9e8ca12119017cf21d6cbca74507`；六服务 healthy、重启 0，运行 OpenAPI 为 116 条路径，新端点与前端产物均已确认。部署未运行迁移，PostgreSQL/MinIO 容器和卷未重建，`20260831_0018 (head)` 保持且 Alembic 无模型漂移；未携带管理员 Session、未执行真实批量方向配置，方向配置审计仍为 0、既有作业受众为 116。新加密备份 `pnx-backup-20260903T144234Z-daily` 已完成从空环境恢复、3,115 个对象对账和清理，统一回滚标签为 `first-choice-rollback-20260903`。发布门发现并修正 `0018` 既有索引在 ORM 元数据中的漏声明，不涉及数据库 DDL。

2026-09-03 已完成“按所有人的第一志愿配置技术方向”源码候选，继续使用唯一正式计划 `.agents/plans/plan_student_teams_auto_assignment_intentions.md`，ADR-053 已接受。真实管理员可在问卷卡片中把第一道单选题全部选项显式映射到启用方向，确认后以最新回答覆盖当前 `active student` 的方向；相同方向不增加 revision，其他账号和未提交者不变。逐用户与汇总审计不含答案或选项 ID，问卷、提交次数、Session 和既有作业固定受众不变。后端定向 57 项、完整 357 项、Ruff、174 文件格式和 154 文件严格 Mypy；前端问卷定向 15 项、完整 25 文件/125 项、ESLint、严格 TypeScript 与生产构建全部通过。本功能无数据库迁移，未连接运行 PostgreSQL/MinIO、未调用真实写接口，也未构建或部署 Docker。

2026-09-01 已完成并部署“飞书知识库增加 `.exe` 支持”。正式计划继续使用唯一的 `.agents/plans/plan_feishu_knowledge_sync.md`，ADR-052 已接受。仅知识库快照文件使用专用入口：支持五种 PE 架构与 PE32/PE32+ 合法配对，拒绝伪装双扩展、伪造 MZ、越界头、DLL 和无执行标志；普通作业、赛事、通知等上传仍拒绝 EXE。下载强制 attachment、octet-stream 和 nosniff。定向 47 项、完整后端 348 项、Ruff、174 文件格式、154 个 `app + tests` 严格 Mypy、`git diff --check`、只读候选断言和真实 MinIO 响应头冒烟通过。新备份 `pnx-backup-20260901T073356Z-daily` 完整验证；固定标签 `knowledge-exe-20260901` 已只替换 Backend/Worker，镜像为 `sha256:e96142385c75ca08589c9fb993d06094a121725986492af00913b708eeaa33c3`。六服务 healthy、重启 0，Alembic 保持 `20260831_0018 (head)`，知识库聚合和同步状态不变，未触发飞书同步。仍须真实管理员手动成功同步，才能验收飞书中的实际 EXE 获得内部资源关联。

2026-09-01 已完成并部署“飞书知识库文件上限提升至 1 GiB 且保持有界内存”。正式计划继续使用唯一的 `.agents/plans/plan_feishu_knowledge_sync.md`，ADR-051 已接受。块附件、富文本内嵌附件、正文 Drive 文件和目录独立文件使用 `FEISHU_KNOWLEDGE_MAX_FILE_BYTES=1073741824`，图片/白板仍使用 50 MiB；飞书响应按声明/累计双限流式读取，Service 只嗅探 64 KiB 首块，MinIO 固定 16 MiB multipart、每片 SHA-256 并增量计算完整摘要，异常关闭响应并尽力 abort。定向 40 项、完整后端 331 项、Ruff、174 文件格式、120 源文件严格 Mypy、`git diff --check` 和真实 MinIO 小型冒烟通过。新备份 `pnx-backup-20260901T021328Z-daily` 完整验证通过；固定标签 `knowledge-file-1gib-20260901` 已只替换 Backend/Worker，镜像为 `sha256:0757eb16493e0fbd1c5292ba9cd78db5ca81ee8b0800cf50b7bd6cc5e03b2f4f`。六服务 healthy、重启 0，Alembic 保持 `20260831_0018 (head)`，聚合保持 `170/15/2535/2195/1111/434`，未触发飞书同步。仍须真实管理员再次手动成功同步，才能验收 50 MiB～1 GiB 合规文件；当前宿主实际使用的 `compose.yml` 没有 Worker 内存 cap，生产模板 768 MiB 边界不变。

2026-09-01 已完成并部署“正文附件明确失败原因、飞书 Drive 文件引用不再显示纯文字”，正式计划继续使用唯一的 `.agents/plans/plan_feishu_knowledge_sync.md`。用户反馈同步后无变化，生产只读核对确认北京时间 09:06～09:10 的 `succeeded/217/1102` 仍由旧 `knowledge-file-gallery-fix-20260831` Worker 生成；源码此前尚未部署。同步器现严格识别受信租户 `/file/{token}` 的 mention/富文本链接，Drive 文件走 `files`，正文块与内嵌附件继续走 `medias`；成功资源复用现有文档关联和登录态下载，失败只形成 `type_not_allowed/too_large/unavailable`。前端显示受保护下载控件或“文件类型不支持 / 文件超过同步上限 / 暂不可下载”，学生视图不生成飞书失败链接，管理员普通视图保留排障入口。保持现有类型白名单、EXE 拦截和默认 50 MiB，无迁移、无新依赖。新备份 `pnx-backup-20260901T012444Z-daily` 完整验证通过；固定标签 `knowledge-inline-files-20260901` 已两阶段上线，Backend/Worker 为 `sha256:ca23fa69c76468c96f1cf065f98e4d3b6a25ed8fbdc4d1b29c6ce8e7f18e9d10`，Frontend 为 `sha256:98a00ead7518a601160f211faf667f8c4dd2d494f3f48e0b6cb485b17f724b34`。六服务 healthy、重启 0，Alembic 保持 `20260831_0018 (head)`，PostgreSQL/MinIO 容器和卷未重建，部署前后聚合保持 `170/14/2302/1978/1109/433`。发布未代替管理员触发同步；须真实管理员在新 Worker 上再次手动成功同步后完成业务验收。

2026-08-31 已完成仓库 MIT License 与分步提交治理：用户确认版权主体为 `HKUST(GZ) RoboMaster PNX Team`，根目录新增标准 MIT `LICENSE`，README 增加许可证入口；既有改动已拆为持久登录、问卷范围邮件、管理端删除可见性、知识库目录文件与响应式媒体、项目记录五个提交，许可证及治理记录作为第六个独立提交。本轮无业务、API、数据库或部署变化，不涉及数据迁移。

2026-08-31 已修复并部署“成功同步后目录文件仍不可下载、真实图片序列未并排”。生产只读证据确认 17:04 最新同步为 `succeeded/217/1057`，但 16 个 `file` 节点全部无资源；同一令牌的 `medias` 端点被飞书拒绝而 `files` 端点可读取，因此目录独立文件现显式使用 Drive `files`，正文媒体继续使用 `medias`。前端画廊现跨过空段落并展开纯媒体容器，可见内容仍终止分组。后端定向 31 项、完整 322 项、Ruff/格式、受影响 4 文件严格 Mypy；前端定向 2 文件/17 项、完整 25 文件/121 项、ESLint、严格 TypeScript、主机与镜像内生产构建全部通过。固定标签 `knowledge-file-gallery-fix-20260831` 已两阶段上线，Backend/Worker 为 `sha256:2b1c9079e5dc9f2079acdb063cd7a0e2d88c52c68be045a346f180054d692141`，Frontend 为 `sha256:a5ad5927756819aeedbe4931b4921a60831d11fcaced9ea9530ded90f04446d3`；六服务 healthy、重启 0，Alembic 保持 `20260831_0018 (head)`，PostgreSQL/MinIO 未重建。新加密备份 `pnx-backup-20260831T102419Z-daily` 完整验证通过。当前 16 个文件仍属于旧代码生成的成功快照，须真实管理员在新版本上再次手动同步后验收资源关联。

2026-08-31 已按用户截图完成并部署知识库默认根层视图热修：无有效 `?doc` 时不再自动读取第一篇文档，只展示根层条目且所有根文件夹保持收起；显式进入文档后只展开当前祖先链，浏览器历史退出文档后清空正文并恢复根层收起视图。知识库定向 2 文件/16 项、完整前端 25 文件/120 项 Vitest、ESLint、严格 TypeScript、主机与镜像内 Next.js 生产构建全部通过。固定标签为 `knowledge-root-view-20260831`，Frontend 镜像 `sha256:9a76b96ca85d67a0364cf939fd5528bbfb42b6d4633d143b75a61ad2443b811f` 已仅替换 Frontend/Nginx；Backend 新标签只是现有 `sha256:77f58286fe7434a970d9656f8a5801ce470af628745e992f513dffb69cb2796f` 的别名，Backend/Worker、PostgreSQL、MinIO 容器 ID 保持不变。六服务 healthy、重启 0，Alembic 保持 `20260831_0018 (head)`，知识库页面/API/虚假资源下载匿名为 307/401/401，发布窗口日志无异常。本热修无迁移、无飞书同步或业务写入。

2026-08-31 已完成并部署培训知识库“目录根层默认、当前文档路径跟随与旧路径收缩、目录独立文件受保护下载、图片当前页浮层及连续图片自适应并排”，正式计划继续使用唯一的 `.agents/plans/plan_feishu_knowledge_sync.md`。固定标签为 `knowledge-directory-media-20260831`，Backend/Worker 镜像 `sha256:77f58286fe7434a970d9656f8a5801ce470af628745e992f513dffb69cb2796f`、Frontend 镜像 `sha256:f523e338e44c0788fb61c1f8378f73940f1bdc00d907a8a1ef770dfbe3883e65` 已两阶段上线；生产 Alembic 为 `20260831_0018 (head)`，112 个历史目录文件已转为 `file:file` 且等待下次成功同步关联资源。六服务 healthy、重启 0，PostgreSQL/MinIO 未重建，迁移前后全表行数哈希一致，运行产物、匿名权限和日志验收通过。加密同点备份 `pnx-backup-20260831T073443Z-daily` 已完整校验；本次未触发飞书同步，仍须真实管理员在 `/admin/knowledge` 手动成功同步一次。

2026-08-31 已完成并部署“通知/作业删除后退出常规管理页面，并允许手工归档通知继续删除”，正式计划继续使用唯一的 `.agents/plans/plan_admin_content_removal.md`。固定标签为 `admin-content-visibility-20260831`，Backend/Worker 镜像 `sha256:589290276cd2ab01b283dc227e3effffe9548df4235a8965fa2c2f3c97145772`、Frontend 镜像 `sha256:8d5ea4a60f04cbf7be44b22b438a1a5c60aef40a0ebf37cf6786ceec2fca116b` 已两阶段上线；生产 Alembic 为 `20260831_0017 (head)`，两列与两项检查约束有效。六服务 healthy、重启 0，PostgreSQL/MinIO 未重建；未调用真实业务 DELETE，运行 OpenAPI、匿名权限、业务聚合和日志验收通过。Docker socket 临时 ACL 仍需部署方交互式 sudo 撤销。

2026-08-30 已完成并部署“问卷按手动成员、技术组或全部激活学生发送邮件”，正式计划继续使用唯一的 `.agents/plans/plan_student_teams_auto_assignment_intentions.md`。固定标签为 `questionnaire-email-scopes-20260830`，Backend/Worker 镜像 `sha256:af1d520399115abad815f84100c5e34c961a29003087d3088eccf54eb7106cbd`、Frontend 镜像 `sha256:8d4ba40349833834a713a6af4b5ea90c572343dd26e6ab58a9d78aeef75e75fe` 已两阶段上线；六服务 healthy、重启 0，运行 OpenAPI 为 115 条路径且包含 `manual/direction/all`。未运行 migrate，PostgreSQL/MinIO 未重建，部署前后用户、问卷五表、状态、知识库和 Outbox 聚合一致；匿名邮件 POST 为 401，未触发真实 SMTP、飞书同步或其他业务写入，部署窗口日志无异常。

2026-08-30 已完成并部署已关闭问卷重新开启，正式计划继续使用唯一的 `.agents/plans/plan_student_teams_auto_assignment_intentions.md`。固定标签为 `questionnaire-reopen-20260830`，Backend/Worker 镜像 `sha256:f613c227e74b67b8c3f1257cb7dca2b2d80b2273168bad13df80ba923331e016`、Frontend 镜像 `sha256:35bed3d14aef08f213df7b14510c2623af5944d3639a3e2788175944a6d7bb75` 已两阶段上线；六服务 healthy、重启 0，未运行 migrate，PostgreSQL/MinIO 未重建。部署前后用户、问卷五表、问卷状态、知识库和 Outbox 聚合一致；验收未调用真实问卷状态接口、未触发飞书同步或其他业务写入，部署窗口日志无异常。

2026-08-30 已完成并部署学生知识库飞书原文入口关闭，正式计划继续使用唯一的 `.agents/plans/plan_feishu_knowledge_sync.md`。真实学生与管理员学生视图不再显示标题原文、未映射飞书文档或附件失败回退链接；当前快照内部文档跳转和 `/api/v1/knowledge/assets/{id}/content` 附件下载保持可用，真实管理员普通视图保留排障入口。部署时同时修复 `/knowledge` 匿名登录回跳竞速；最终知识库定向 2 文件/12 项、完整前端 25 文件/111 项 Vitest、ESLint、严格 TypeScript 和镜像内生产构建通过。该阶段 Frontend 固定标签为 `knowledge-student-links-20260830`、镜像为 `sha256:a67211cda8d65afeb34bbdde630609cd7c50aff974cc99ddbb9f6852ac26c652`；未运行 migrate，未替换 Backend/Worker/PostgreSQL/MinIO，未触发飞书同步或业务写入。

2026-08-30 已完成持久登录部署后跳转回归热修复，正式计划为 `.agents/plans/plan_persistent_login.md`。Next.js 服务端 API 现同时向内部 Backend 转发 Cookie 与 Nginx 已覆盖的单值来源 IP，缺失时不伪造；Frontend/Nginx 已定向替换为 `persistent-login-ip-forwarding-20260830`，未运行 migrate、未替换 Backend/Worker、未重建 PostgreSQL/MinIO。六服务 healthy、重启 0；回归期间已撤销的持久 Session 需用户重新勾选登录一次。

2026-08-30 已完成并部署管理员删除队伍，正式计划继续使用唯一的 `.agents/plans/plan_competitions_teams.md`。原 `team-delete-20260830` 候选以 `help-delete-20260829` 为基线并明确排除用户搜索源码，随后覆盖了已上线搜索修复；现已改用合并固定标签 `team-user-search-20260830`，同时保留队伍删除和管理员全量用户搜索。部署前 PostgreSQL 17 快照已复核，纠正发布未运行 migrate、未重建 PostgreSQL/MinIO，六服务 healthy、重启 0，未携带认证调用真实 DELETE 或读取用户列表。

2026-08-30 已完成并重新部署管理员用户全量搜索与分页修复，正式计划为 `.agents/plans/plan_admin_user_search.md`。根因不是数据库只有 100 个，而是后续 `team-delete-20260830` Frontend/Backend 从旧基线构建，把用户 API 回退为只传 `page_size=100`。当前 `team-user-search-20260830` 以队伍删除镜像为基线合并 users 两个后端文件，并无缓存重建包含全部已上线功能的 Frontend；运行编译 chunk 已确认 `pageSize:20` 且传递 `page/search`。六服务 healthy、匿名管理员页/API 为 307/401；未使用管理员登录态、未读取用户列表、未调用业务写接口。

2026-08-29 已完成并部署管理员永久删除账号与用户自助注销，正式计划为 `.agents/plans/plan_account_deletion.md`。固定标签为 `account-deletion-20260829`，运行库为 `20260829_0015 (head)`；加密完整备份、从空环境恢复和 `0014 ↔ 0015` 往返均通过，生产验收未调用真实账号删除接口，账号清理 Outbox 仍为 0。详细结果已移入完成记录、变更记录与生产运维报告。

2026-08-29 已完成并部署真实管理员删除反馈答疑，正式计划继续使用唯一的 `.agents/plans/plan_feedback_help_requests.md`。固定标签为 `help-delete-20260829`，删除会物理移除工单并同步退出学生本人/公开读取，相关未读提醒标为已读并保留脱敏审计；运行验收未调用带认证的真实 DELETE，本轮无迁移。

本次答疑删除候选以已上线账号删除为基线，继续保留通知/作业删除、注册唯一约束修复、飞书 KaTeX 公式和账号删除能力；运行 OpenAPI 同时包含账号与答疑 DELETE，Alembic 保持 `20260829_0015 (head)`，最近成功知识库快照为 213 篇文档、1006 个媒体。

部署备份和临时 GPG 密钥环目前位于本机 `/tmp`，需要迁移到受控独立介质并分离保存。Docker socket 临时 `user:pnx:rw-` ACL 已尝试撤销，但普通用户无权限且 `sudo -n` 要求密码；仍需部署方交互执行 `sudo setfacl -x u:pnx /var/run/docker.sock` 并复核基础 ACL。
