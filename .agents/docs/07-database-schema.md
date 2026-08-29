# 数据库结构

## 通用规则

- PostgreSQL 是唯一关系数据源；附件二进制只存 MinIO。
- 业务实体主键统一使用应用生成的 UUIDv7 和 PostgreSQL `uuid` 类型，便于按时间局部排序；只允许运维单例表使用文档明确的自然键。
- 时间统一使用 `TIMESTAMPTZ`；可变表包含 `created_at`、`updated_at` 和整数 `revision`。
- 邮箱在写入前规范化为小写并存入 `email_normalized`，以唯一索引比较；原始显示值存 `email`。
- 不采用全局通用软删除。用户和业务内容通过状态保留；可清理文件使用 `deleted_at`。正式版本、评语和审计日志不物理删除。
- 外键默认 `RESTRICT`；只对纯关联表使用 `CASCADE`。历史资源不得因删除基础配置而失去引用。
- 枚举通过 PostgreSQL enum 或受约束文本实现；迁移必须支持新增值的前滚策略。

## 枚举

| 枚举 | 值 |
| --- | --- |
| `user_role` | `student`, `admin` |
| `user_status` | `pending_email`, `active`, `disabled` |
| `announcement_status` | `draft`, `scheduled`, `published`, `archived` |
| `assignment_status` | `draft`, `published`, `closed`, `archived` |
| `competition_status` | `draft`, `registration_open`, `registration_closed`, `submission_open`, `submission_closed`, `archived` |
| `registration_status` | `registered`, `withdrawn`, `disqualified` |
| `team_status` | `forming`, `locked`, `invalid`, `dissolved`, `disqualified`, `archived` |
| `upload_status` | `initialized`, `uploading`, `verifying`, `available`, `rejected`, `aborted`, `expired` |
| `outbox_status` | `pending`, `processing`, `retry`, `sent`, `dead` |
| `audience_match` | `union`, `intersection` |
| `help_request_type` | `system_feedback`, `question` |
| `help_request_status` | `open`, `resolved` |

## 实体关系

```mermaid
erDiagram
    COHORTS ||--o{ USERS : assigns
    DIRECTIONS ||--o{ USERS : assigns
    USERS ||--o{ SESSIONS : owns
    USERS ||--o{ STUDENT_NOTIFICATIONS : receives
    USERS ||--o{ HELP_REQUESTS : submits
    ANNOUNCEMENTS }o--o{ COHORTS : targets
    ANNOUNCEMENTS }o--o{ DIRECTIONS : targets
    ASSIGNMENTS }o--o{ USERS : snapshots
    ASSIGNMENTS ||--o{ ASSIGNMENT_EXTENSIONS : grants
    COMPETITIONS ||--o{ COMPETITION_REGISTRATIONS : accepts
    COMPETITIONS ||--o{ COMPETITION_TASKS : contains
    COMPETITIONS ||--o{ TEAMS : contains
    TEAMS ||--o{ TEAM_MEMBERS : has
    USERS ||--o{ INTENTION_RESPONSES : submits
    INTENTION_SURVEYS ||--o{ INTENTION_OPTIONS : defines
    INTENTION_SURVEYS ||--o{ INTENTION_RESPONSES : receives
    INTENTION_RESPONSES ||--o{ INTENTION_RESPONSE_OPTIONS : selects
    INTENTION_OPTIONS ||--o{ INTENTION_RESPONSE_OPTIONS : selected_by
    ASSIGNMENTS ||--o{ SUBMISSIONS : receives
    COMPETITION_TASKS ||--o{ SUBMISSIONS : receives
    USERS ||--o{ SUBMISSIONS : owns_assignment
    TEAMS ||--o{ SUBMISSIONS : owns_competition
    SUBMISSIONS ||--o{ SUBMISSION_VERSIONS : versions
    SUBMISSION_VERSIONS ||--o| FEEDBACK : receives
    SUBMISSION_VERSIONS }o--o{ FILES : attaches
    ASSIGNMENTS ||--o{ ASSIGNMENT_EXCELLENT_SUBMISSIONS : highlights
    SUBMISSION_VERSIONS ||--o| ASSIGNMENT_EXCELLENT_SUBMISSIONS : selected
    UPLOAD_SESSIONS ||--o{ UPLOAD_PARTS : tracks
    FILES ||--o| UPLOAD_SESSIONS : produces
    USERS ||--o{ AUDIT_LOGS : acts
```

## 身份与基础数据

### `cohorts`

`id`, `code`, `name`, `start_year`, `is_active`, `created_at`, `updated_at`, `revision`。

- `code` 全局唯一且不可复用；历史引用存在时只能停用。
- 届次设置已从产品入口移除；表结构和数据保留，用于历史通知/作业受众、快照及旧 API 兼容，不在本次变更中物理删除。

### `directions`

`id`, `code`, `name`, `description`, `is_active`, `created_at`, `updated_at`, `revision`。

- `code` 全局唯一；用于机械、电控、视觉等技术方向。

### `users`

`id`, `email`, `email_normalized`, `student_number`, `full_name`, `password_hash`, `role`, `status`, `cohort_id`, `direction_id`, `email_verified_at`, `disabled_at`, `disabled_by`, `disabled_reason`, `password_changed_at`, `created_at`, `updated_at`, `revision`。

约束：

- `email_normalized` 和 `student_number` 分别唯一。
- Connect 用户名由 `email_normalized` 的 local-part 派生，不新增用户名列、独立唯一约束或可编辑用户名；旧域名存量账号不启用前缀登录。
- 数据库 CHECK 允许 `@hkust-gz.edu.cn` 存量行与 `@connect.hkust-gz.edu.cn` 新行共存；公开注册和管理员邮箱修改的 Service 只允许 Connect 域名。
- 任一 `active` 账号必须具有 `email_verified_at`；`cohort_id` 和 `direction_id` 均可空且不参与登录条件。新产品只维护 `direction_id`，`cohort_id` 仅保留历史兼容。
- 公开注册先创建 `pending_email student`；验证事务在固定 advisory lock 内确认没有任何 `active` 用户时把首个账号设为 `admin`，其余账号保持 `student`。同一事务锁也用于登录时确认不存在其他用户行；唯一的已验证 `active student` 必须提升为 `admin`、增加 revision、撤销旧 Session 并写审计。
- `password_hash` 只存 Argon2id 编码结果。
- 角色变更和状态变更均写 `audit_logs`。

索引：`(status, created_at)`、`(cohort_id, direction_id, status)`、`(role, status)`。届次索引暂保留，供历史受众查询使用。

### `sessions`

`id`, `user_id`, `token_hash`, `csrf_secret_hash`, `created_at`, `last_seen_at`, `idle_expires_at`, `absolute_expires_at`, `revoked_at`, `student_view`, `ip_prefix`, `user_agent_summary`。

- `token_hash` 唯一；只存随机 Session 令牌的哈希。
- 读取使用 `token_hash` 索引，并过滤未撤销和未过期记录。
- 用户禁用、密码重置和角色敏感变更时批量撤销。
- `student_view` 为非空布尔值，默认 `false`，只表示当前 Session 的临时有效角色，不修改 `users.role`；管理员切换开关时写入 `audit_logs`。真实角色变更必须撤销该用户全部 Session，因此降级后不能由本人恢复管理员视图。

### `one_time_tokens`

`id`, `user_id`, `purpose`, `token_hash`, `expires_at`, `used_at`, `created_at`。

- `purpose` 仅为 `email_verification` 或 `password_reset`。
- `token_hash` 唯一；新令牌创建时使同用户同用途的旧令牌失效。

### `auth_security_events`

`id`, `event_type`, `email_normalized`, `user_id`, `ip_prefix`, `occurred_at`, `metadata`。

- 用于登录限流与安全分析；用户名和对应 Connect 完整邮箱都先写成同一个规范化完整邮箱，`metadata` 禁止密码、Cookie 和一次性令牌。
- 索引 `(email_normalized, occurred_at)` 和 `(ip_prefix, occurred_at)`。

## 通知与站内提醒

### `announcements`

`id`, `title`, `summary`, `body_markdown`, `body_html`, `status`, `all_students`, `audience_match`, `publish_at`, `published_at`, `pinned_until`, `send_email`, `created_by`, `updated_by`, `archived_at`, `created_at`, `updated_at`, `revision`。

- `body_html` 是经统一策略清洗后的缓存。
- `all_students=true` 时不得存在届次/方向关联。新建产品流程只写方向关联；历史届次关联继续保留。
- `scheduled` 必须有未来 `publish_at`；`published` 必须有 `published_at`。

### `announcement_cohorts`、`announcement_directions`

分别包含 `(announcement_id, cohort_id)` 和 `(announcement_id, direction_id)` 复合主键。用于配置受众；发布时另外生成逐用户通知记录作为发送快照。新建通知不再写入 `announcement_cohorts`，历史关联只读兼容。

### `announcement_files`

`announcement_id`, `file_id`, `display_order`。复合唯一约束保证同一附件不重复绑定。

### `student_notifications`

`id`, `user_id`, `notification_type`, `event_key`, `title`, `target_type`, `target_id`, `target_url`, `created_at`, `read_at`。

- `(user_id, event_key)` 唯一，保证重试不生成重复提醒。
- 索引 `(user_id, read_at, created_at DESC)`。
- 工作台按 `target_type/target_url` 把未读提醒归入公告、作业、校内赛和反馈答疑；公告分类只统计仍为 `published` 的目标，历史遗留的归档公告提醒不进入有效未读数。
- 公告归档在同一事务把该公告当前未读提醒写入 `read_at`；学生读取公告或本人工单详情后仍通过既有受 CSRF 保护的单条已读接口更新，不通过 GET 隐式写入。

## 反馈答疑

### `help_requests`

`id`, `request_type`, `status`, `title`, `content_markdown`, `content_html`, `resolution_markdown`, `resolution_html`, `created_by`, `resolved_by`, `resolved_at`, `created_at`, `updated_at`, `revision`。

- `request_type` 只允许 `system_feedback`、`question`，`status` 只允许 `open`、`resolved`；标题去除首尾空白后长度为 1～200，学生正文为 1～20,000 字符。
- `content_html` 和非空的 `resolution_html` 都由统一安全 Markdown 渲染器生成；数据库保存当前答复，不建立公开评论或多轮消息表。
- `created_by` 和 `resolved_by` 均以 `RESTRICT` 引用 `users`。`open` 必须没有答复者、答复时间或答复正文；`resolved` 必须同时具有非空答复、答复者和答复时间。
- 学生列表索引 `(created_by, created_at DESC, id DESC)`；管理员筛选索引 `(status, request_type, created_at DESC, id DESC)`。
- 管理员首次答复或修订答复时锁定本行、校验 `revision`，并在同一事务写 `audit_logs` 和 `student_notifications`；通知事件键为 `help_request_resolved:{request_id}:{revision}`，只包含安全标题和本人详情链接。
- 不新增 `is_public` 字段或迁移；登录态公开查询固定选择 `request_type='question' AND status='resolved'`，复用管理员筛选索引且不连接 `users`。因此开放问题和全部系统反馈始终私密，问题首次解决即公开，答复修订直接反映最新版本。

## 作业与受众快照

### `assignments`

`id`, `title`, `description_markdown`, `description_html`, `training_url`, `submission_instructions`, `status`, `all_students`, `audience_match`, `allowed_extensions`, `max_total_bytes`, `publish_at`, `published_at`, `deadline`, `created_by`, `updated_by`, `closed_at`, `archived_at`, `created_at`, `updated_at`, `revision`。

- `allowed_extensions` 存规范化小写数组，并由服务层保证是全局白名单子集。
- `max_total_bytes` 满足 `1 <= value <= 2147483648`。
- `deadline > publish_at`。

### `assignment_cohorts`、`assignment_directions`

保存发布前的受众配置，结构与通知关联表相同。新建作业不再写入 `assignment_cohorts`，历史关联只读兼容。

### `assignment_audience_users`

`assignment_id`, `user_id`, `cohort_id_at_publish`, `direction_id_at_publish`, `created_at`，复合主键 `(assignment_id, user_id)`。

- 发布事务生成初始固定受众；后续账号首次激活为普通学生时，同一激活事务为仍处于 `published`、未过公共截止且匹配的作业追加该学生。
- `cohort_id_at_publish` 和 `direction_id_at_publish` 对激活后补录行记录补录当时分类；届次字段仅历史兼容。学生后续调整方向不修改此表。

### `assignment_extensions`

`assignment_id`, `user_id`, `extended_deadline`, `reason`, `granted_by`, `created_at`, `updated_at`, `revision`。

- 复合唯一 `(assignment_id, user_id)`。
- `extended_deadline` 必须晚于作业公共截止时间。

## 赛事、报名与队伍

### `competitions`

`id`, `name`, `description_markdown`, `description_html`, `rules_url`, `status`, `registration_start`, `registration_end`, `submission_start`, `submission_end`, `min_team_size`, `max_team_size`, `created_by`, `updated_by`, `published_at`, `archived_at`, `created_at`, `updated_at`, `revision`。

约束：

- `registration_start < registration_end <= submission_start < submission_end`。
- `1 <= min_team_size <= max_team_size <= 20`。
- 状态只允许按规定方向推进。

### `competition_registrations`

`id`, `competition_id`, `user_id`, `status`, `registered_at`, `withdrawn_at`, `disqualified_at`, `disqualified_by`, `disqualification_reason`, `created_at`, `updated_at`, `revision`。

- `(competition_id, user_id)` 唯一；重新报名复用记录并校验状态。
- 索引 `(competition_id, status)`。

### `competition_tasks`（历史兼容）

`id`, `competition_id`, `title`, `description_markdown`, `description_html`, `resource_url`, `allowed_extensions`, `max_total_bytes`, `deadline`, `display_order`, `created_at`, `updated_at`, `revision`。

- `deadline` 位于历史赛事提交窗口内；新赛事不创建该实体。
- `(competition_id, display_order)` 唯一。

### `teams`

`id`, `competition_id`, `name`, `status`, `captain_user_id`, `invite_code_hash`, `invite_code_rotated_at`, `min_size_waived_at`, `min_size_waived_by`, `waiver_reason`, `disqualified_at`, `disqualified_by`, `disqualification_reason`, `created_at`, `updated_at`, `locked_at`, `dissolved_at`, `revision`。

- `(competition_id, lower(name))` 对未解散队伍唯一。
- `captain_user_id` 必须是当前有效成员，由 Service 事务保证。
- 邀请码只保存慢哈希或带服务端 pepper 的 HMAC，不保存明文。公开目录只从该表和有效成员计数生成，不连接用户身份字段；自动分配锁定赛事及所有候选 `forming` 队伍并优先选择未满且人数较少者。

### `team_members`

`id`, `team_id`, `competition_id`, `user_id`, `joined_at`, `left_at`, `added_by_admin`, `admin_reason`。

- 部分唯一索引 `(competition_id, user_id) WHERE left_at IS NULL` 保证一赛一队。
- 唯一 `(team_id, user_id, joined_at)` 保留重新加入历史。
- Service 验证 `competition_id` 与 `teams.competition_id` 一致。
- 索引 `(team_id, left_at)`。

## 学生问卷

### `intention_surveys`

`id`, `title`, `description_markdown`, `description_html`, `status`, `max_submissions`, `starts_at`, `ends_at`, `public_token_hash`, `created_by`, `updated_by`, `created_at`, `updated_at`, `revision`。

- `status` 只允许 `draft`、`open`、`closed`、`archived`，Service 只允许顺序推进。
- 标题去除首尾空白后长度为 1～200；开始和结束时间同时存在时必须 `starts_at < ends_at`。
- `description_html` 由统一安全 Markdown 渲染器生成；`public_token_hash` 是唯一 64 位 SHA-256 十六进制值，不保存二维码明文 token。
- `max_submissions` 为 1～100 的正整数或 `NULL`（不限次数）；索引 `(status, starts_at, ends_at)` 支持学生开放问卷查询。

### `intention_questions`

`id`, `survey_id`, `prompt`, `allow_multiple`, `display_order`。

- 问卷删除时级联删除问题；`prompt` 去空白后长度 1～200，`display_order >= 0`。
- `(survey_id, display_order)` 唯一；每题独立使用 `allow_multiple` 表达单选或多选。

### `intention_options`

`id`, `question_id`, `label`, `display_order`。

- `question_id` 删除时级联删除选项；`label` 去空白后非空，`display_order >= 0`。
- `(question_id, display_order)` 唯一；Service 额外按去空白后的大小写折叠标签拒绝同题重复选项。

### `intention_responses`

`id`, `survey_id`, `user_id`, `free_text`, `submission_count`, `submitted_at`, `created_at`, `updated_at`, `revision`。

- `(survey_id, user_id)` 唯一，保证同一学生只保留一份最新回答；每次成功覆盖时原子增加正整数 `submission_count`、更新时间和 revision，不保留被覆盖的答案历史。
- `user_id` 使用 `RESTRICT`，调查删除时级联删除回答；正式产品通过归档保留调查，不提供删除 API。

### `intention_response_options`

`response_id`, `option_id`，复合主键 `(response_id, option_id)`。

- 回答删除时级联删除选择；选项仍被引用时 `RESTRICT`。
- Service 在写入前锁定问卷和本人回答，验证全部问题、问题归属、选项归属及每题选择数量，并在同一事务校验/增加提交次数；数据库唯一约束处理并发首次填写。
- 管理员统计只聚合回答数和分题选项选择数；实名名单通过受管理员保护的查询连接 `users`，批量装载最新选择，只返回需求允许字段。

## 提交、版本和评语

### `submissions`

`id`, `assignment_id`, `competition_task_id`, `owner_user_id`, `owner_team_id`, `latest_version_id`, `created_at`, `updated_at`。

核心检查约束：

```sql
CHECK (
  (assignment_id IS NOT NULL AND competition_task_id IS NULL
   AND owner_user_id IS NOT NULL AND owner_team_id IS NULL)
  OR
  (assignment_id IS NULL AND competition_task_id IS NOT NULL
   AND owner_user_id IS NULL AND owner_team_id IS NOT NULL)
)
```

- 部分唯一 `(assignment_id, owner_user_id) WHERE assignment_id IS NOT NULL`。
- 部分唯一 `(competition_task_id, owner_team_id) WHERE competition_task_id IS NOT NULL`。
- `latest_version_id` 在创建版本事务结束前指向同一提交的版本；使用延迟外键或迁移后追加外键解决建表循环。

### `submission_versions`

`id`, `submission_id`, `version_number`, `submitted_by`, `text_markdown`, `text_html`, `external_url`, `total_file_bytes`, `idempotency_key`, `submitted_at`。

- `(submission_id, version_number)` 唯一，`version_number >= 1`。
- `(submitted_by, idempotency_key)` 唯一。
- `text_markdown`、`external_url` 和附件至少一种存在，由 Service 验证。
- 行创建后禁止 `UPDATE` 和 `DELETE`；必要纠错创建新版本。

### `version_files`

`version_id`, `file_id`, `display_order`，复合主键 `(version_id, file_id)`。

- 同一文件只允许绑定一个正式版本或一个通知，避免跨用户引用。
- 绑定事务再次验证文件所有者、状态和合计大小。

### `feedback`

`id`, `version_id`, `body_markdown`, `body_html`, `created_by`, `created_at`, `updated_at`, `revision`。

- `version_id` 唯一，一版最多一条当前评语。
- 修订差异写入审计，表中保留当前版本；不提供评分字段。

## 优秀作业

### `assignment_excellent_submissions`

`assignment_id`, `version_id`, `marked_by`, `marked_at`，复合主键 `(assignment_id, version_id)`。

- `version_id` 另设唯一约束，避免同一版本被重复标记。
- Service 必须验证该版本的 `submission.assignment_id` 等于记录的 `assignment_id`，并拒绝 `competition_task_id` 非空的赛事版本。
- 该表存在即表示优秀标记生效；取消标记删除关联行，不删除源提交版本、附件或审计日志。
- 作业受众从源版本读取全部文本、链接和附件，并通过 `submitted_by` 关联用户姓名；`feedback` 永不参与优秀作业响应。
- 关联存在期间，源版本和其 `version_files` 禁止进入合规删除流程。

## 文件和上传

### `files`

`id`, `owner_user_id`, `purpose`, `object_key`, `original_name`, `extension`, `declared_media_type`, `detected_media_type`, `size_bytes`, `sha256`, `status`, `created_at`, `available_at`, `deleted_at`。

- `object_key` 唯一且不可由客户端指定。
- `sha256` 为 64 位小写十六进制；`size_bytes >= 0`。
- 索引 `(owner_user_id, status, created_at)`、`(status, created_at)`。

### `upload_sessions`

`id`, `file_id`, `user_id`, `purpose`, `context_type`, `context_id`, `minio_upload_id`, `part_size_bytes`, `part_count`, `expected_size_bytes`, `expected_sha256`, `status`, `last_activity_at`, `expires_at`, `idempotency_key`, `created_at`, `completed_at`, `failure_code`。

- `(user_id, idempotency_key)` 唯一。
- `expires_at` 默认最后活动时间后 24 小时。
- `minio_upload_id` 视为敏感内部标识，不通过日志输出。

### `upload_parts`

`upload_session_id`, `part_number`, `etag`, `checksum_sha256`, `size_bytes`, `completed_at`，复合主键 `(upload_session_id, part_number)`。

- `1 <= part_number <= upload_sessions.part_count`。

## Outbox、幂等与审计

### `worker_heartbeats`

`worker_name`, `started_at`, `last_heartbeat_at`, `updated_at`。

- `worker_name` 是长度不超过 100 的自然主键；首版默认值为 `primary`，用于区分未来并行 Worker，而不是业务租户。
- Worker 启动后立即写入并按配置周期原子更新；API 只返回名称、启动时间、最近心跳和安全的心跳年龄。
- 索引 `last_heartbeat_at` 支持 NFR-008 的陈旧心跳检查和独立告警。
- 该表由首条 Alembic 迁移 `20260823_0001` 创建，可完整降级删除；它是阶段 1 唯一已创建的数据库表。

### `outbox_jobs`

`id`, `job_type`, `event_key`, `payload`, `secret_payload_ciphertext`, `status`, `available_at`, `attempt_count`, `max_attempts`, `locked_by`, `locked_at`, `last_error_code`, `last_error_summary`, `created_at`, `sent_at`。

- `event_key` 唯一，是 MAIL-005 的幂等依据。
- `payload` 只含完成任务所需的资源 ID和非秘密模板变量，不保存密码、Cookie 或明文一次性令牌。
- `secret_payload_ciphertext` 可空，只用于保存经独立 Outbox 密钥认证加密的投递秘密；不得通过管理 API、日志或审计返回。
- 领取索引 `(status, available_at)`；Worker 使用 `FOR UPDATE SKIP LOCKED`。
- 邮件管理 API 只查询 `job_type` 为邮件的记录并对接收方脱敏。

### `idempotency_records`

`id`, `user_id`, `endpoint_key`, `idempotency_key`, `request_hash`, `response_status`, `response_body`, `resource_id`, `expires_at`, `created_at`。

- `(user_id, endpoint_key, idempotency_key)` 唯一。
- 同键不同 `request_hash` 返回 `IDEMPOTENCY_CONFLICT`。

### `audit_logs`

`id`, `actor_user_id`, `action`, `target_type`, `target_id`, `request_id`, `ip_prefix`, `result`, `change_summary`, `created_at`。

- 只追加，不更新、不通过产品接口删除。
- `change_summary` 是脱敏 JSONB，只保存变更字段和安全摘要。
- 索引 `(actor_user_id, created_at DESC)`、`(target_type, target_id, created_at DESC)`、`request_id`。

## 需求与实体映射

| 需求域 | 核心表 |
| --- | --- |
| AUTH | `users`, `sessions`, `one_time_tokens`, `auth_security_events`, `directions`；`cohorts` 仅历史兼容 |
| NEWS、MAIL | `announcements`, 受众关联表, `student_notifications`, `outbox_jobs` |
| HW | `assignments`, 受众配置与快照, `assignment_extensions` |
| COMP、TEAM | `competitions`, `competition_registrations`, `teams`, `team_members`；`competition_tasks` 仅保留历史兼容数据 |
| SUB | `submissions`, `submission_versions`, `version_files`, `feedback` |
| INT | `intention_surveys`, `intention_questions`, `intention_options`, `intention_responses`, `intention_response_options` |
| HELP | `help_requests`, `student_notifications`, `audit_logs` |
| SHOW | `assignment_excellent_submissions`、作业与版本外键、源附件删除保护 |
| FILE | `files`, `upload_sessions`, `upload_parts` |
| NFR-006 | `audit_logs` |
| NFR-008 | `worker_heartbeats` |

## 迁移规则

1. 每次结构变化只提交一条职责明确的 Alembic 迁移链，不手工修改生产表。
2. 大表新增非空字段采用“可空字段 → 回填 → 约束”三阶段，避免长时间锁表。
3. 删除列或枚举值采用至少一个版本的弃用窗口，先停止读取和写入，再迁移数据，最后移除。
4. 生产迁移前完成 PostgreSQL 备份；不可逆迁移必须给出经过测试的前滚恢复方案。
5. 迁移测试从空库升级到最新，也从上一个发布版本升级到最新，并验证全部检查、唯一和外键约束。
6. 数据修正迁移 `20260825_0007` 不改变结构，只在用户表恰好一行且该行是已验证 `active student` 时提升为管理员、撤销旧 Session 并追加审计；降级保留已授予角色，避免系统重新失去管理员。
7. 认证增量迁移 `20260826_0008` 为 `sessions.student_view` 增加可回滚的非空布尔列，默认关闭；降级仅删除该列，不恢复已撤销 Session 或审计记录。
8. 意向调查迁移 `20260827_0009` 创建上述四张表、外键、唯一约束和状态/时间检查；downgrade 按响应选项、回答、选项、调查顺序删除，可完成 `0008 → 0009 → 0008 → 0009` 往返。
9. 作业受众数据迁移 `20260827_0010` 为现有 active student 补录仍开放且匹配的作业，使用专用 `created_at` 标记；downgrade 只删除该标记行，可完成 `0009 → 0010 → 0009 → 0010` 往返。
10. 问卷升级迁移 `20260828_0013` 接在账号活跃度 `0012` 后：为每份旧调查创建 ID 等于原调查 ID 的兼容问题，把旧选项迁到 `question_id`，以原回答 revision 初始化 `submission_count`，旧调查 `max_submissions=NULL` 保持不限。downgrade 按题序展平选项并保留选择关系，但旧结构无法保留问题标题和次数限制语义，生产降级前必须备份；验证 `0012 → 0013 → 0012 → 0013`。
11. 反馈答疑迁移 `20260828_0014` 接在 `0013` 后，只创建 `help_requests` 表、检查约束、外键和查询索引，不回填或修改现有业务数据。downgrade 删除整张表并丢失已产生的工单与答复，生产降级前必须备份；验证 `0013 → 0014 → 0013 → 0014` 并保持单一 head。
12. 已解答问题公开读取仅改变查询和响应，不改变 `0014` 表结构，不新增 Alembic revision；应用回滚不需要数据库降级。

## 飞书知识库快照

### `knowledge_sync_runs`

`id`, `status`, `source_url`, `triggered_by`, `started_at`, `finished_at`, `document_count`, `asset_count`, `error_code`, `error_summary`, `created_at`。状态只允许 `pending/running/succeeded/failed`；部分唯一常量索引保证进行中状态合计最多一条。最新 `succeeded.finished_at` 即学生当前快照，不维护额外单例指针。

### `knowledge_nodes` 与 `knowledge_documents`

- 节点按 `sync_run_id` 保存父节点、飞书节点/对象标识、类型、标题、深度、顺序和安全原文 URL；同一运行的节点 token 唯一。
- 文档一对一关联节点，按运行保存外部文档标识、标题、原文 URL、规范化块 `JSONB` 和顺序；同一运行的文档标识唯一。
- 失败运行可保留诊断状态，但从不被学生读取；同一运行重试前级联清空部分节点/文档再重建。
- 对齐参考同步后，只有目录遍历和全部目标 Docx 的 blocks、标题及引用均完成的运行才能标为 `succeeded`；目录子树或单篇正文不得被静默跳过并形成新的部分成功快照。

### `knowledge_assets` 与 `knowledge_document_assets`

- 媒体全局按 `(external_asset_token, asset_kind)` 复用，保存服务端对象键、安全文件名、媒体类型、大小、SHA-256、可选宽高和最后发现时间；文件内容只在 MinIO。
- 文档媒体关联记录 `usage_type` 与顺序。资源 API 必须通过“最新成功运行 → 文档 → 关联 → 媒体”联查授权。

迁移 `20260827_0011` 创建上述五表、外键、检查、唯一和查询索引；downgrade 逆序删除关联、文档、媒体、节点和运行表，不删除 MinIO 对象，避免数据库回滚造成不可恢复文件丢失。

参考仓库对齐和首次上线前台初始化不改变上述表、约束或迁移，本轮不新增数据库迁移。
