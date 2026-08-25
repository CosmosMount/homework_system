# API 规范

## 通用约定

- 基础路径：`/api/v1`。
- 传输：生产环境只允许 HTTPS；请求与响应默认 `application/json`，对象分片直接上传到预签名 MinIO URL。
- 命名：JSON 字段使用 `snake_case`，资源 ID 使用 UUID 字符串，时间使用带时区 ISO 8601。
- 身份：浏览器携带服务端 Session Cookie。所有非安全方法必须同时携带 `X-CSRF-Token`。
- 幂等：创建正式版本、完成上传、发布和邮件重发接受 `Idempotency-Key`；同一用户、端点和键重复请求返回第一次的结果。
- 并发：可编辑管理资源包含 `revision`；`PATCH` 必须提交读取到的 `revision`，过期版本返回 409。
- 分页：`page` 从 1 开始，`page_size` 默认 20、最大 100；响应为 `{items, page, page_size, total}`。
- 排序：只接受各端点声明的字段，格式为 `sort=-published_at,title`，减号表示倒序。
- 未授权返回 401；已登录但无操作权限返回 403；对学生不可见的业务资源返回 404。

成功响应直接返回资源或分页结构，不再包裹 `data`。删除或无正文操作返回 `204 No Content`。

## 错误结构

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "请求参数不符合要求。",
    "request_id": "0196d1a0-4b8e-7c7a-a5cf-3d26b577d7d8",
    "details": [
      {"field": "email", "reason": "INVALID_CAMPUS_EMAIL"}
    ]
  }
}
```

| HTTP | 通用错误码 | 含义 |
| ---: | --- | --- |
| 400 | `INVALID_REQUEST`、`VALIDATION_ERROR` | 语法或字段错误 |
| 401 | `AUTHENTICATION_REQUIRED`、`INVALID_CREDENTIALS` | 未登录或登录失败 |
| 403 | `FORBIDDEN`、`CSRF_FAILED`、`TEAM_CAPTAIN_REQUIRED` | 无操作权限 |
| 404 | `RESOURCE_NOT_FOUND` | 不存在或对当前学生不可见 |
| 409 | `STATE_CONFLICT`、`REVISION_CONFLICT`、`ALREADY_IN_COMPETITION_TEAM`、`IDEMPOTENCY_CONFLICT` | 状态或并发冲突 |
| 410 | `TOKEN_EXPIRED`、`TOKEN_ALREADY_USED`、`UPLOAD_EXPIRED` | 一次性资源失效 |
| 413 | `SUBMISSION_SIZE_EXCEEDED` | 版本附件合计超过限制 |
| 415 | `FILE_TYPE_NOT_ALLOWED` | 文件类型不允许 |
| 422 | `BUSINESS_RULE_VIOLATION` | 字段有效但违反业务规则 |
| 429 | `RATE_LIMITED` | 触发限流，响应含 `Retry-After` |
| 500 | `INTERNAL_ERROR` | 未预期错误，必须返回请求 ID |
| 503 | `DEPENDENCY_UNAVAILABLE` | 必要依赖暂时不可用 |

## 公共认证接口

### `POST /auth/register`

访问：未登录。对应 AUTH-001、AUTH-002、AUTH-010。

`email` 必须规范化后精确以 `@connect.hkust-gz.edu.cn` 结尾；旧域名、子域名、相似域名或通过该字符串作为局部内容的请求均被拒绝。

```json
{
  "full_name": "张三",
  "student_number": "12345678",
  "email": "student@connect.hkust-gz.edu.cn",
  "password": "user-supplied-password"
}
```

返回 `201`：

```json
{
  "user_id": "uuid",
  "status": "pending_email",
  "verification_expires_at": "2026-08-24T10:00:00+08:00"
}
```

错误：`INVALID_CAMPUS_EMAIL`、`EMAIL_ALREADY_REGISTERED`、`STUDENT_NUMBER_ALREADY_REGISTERED`、`WEAK_PASSWORD`、`RATE_LIMITED`。

### 邮箱验证

| 方法与路径 | 请求 | 结果 | 需求 |
| --- | --- | --- | --- |
| `POST /auth/email-verifications/resend` | `{email}` | 统一返回 202 | AUTH-002、AUTH-009 |
| `POST /auth/email-verifications/confirm` | `{token}` | `{status: active}`；空系统首个验证账号成为管理员，其余为学生 | AUTH-002～AUTH-003、AUTH-008 |

令牌无效返回 `400 INVALID_TOKEN`，过期或已使用返回 410。重发接口不暴露邮箱是否注册。

### Session

| 方法与路径 | 请求/响应 | 需求 |
| --- | --- | --- |
| `POST /auth/login` | `{identifier,password}` → `{user}` 并设置 Session Cookie；暂时兼容旧 `{email,password}` 请求 | AUTH-004、AUTH-006、AUTH-009 |
| `POST /auth/logout` | 撤销当前 Session，返回 204 | AUTH-006 |
| `GET /auth/me` | 当前用户、可空届次/方向、角色、状态 | AUTH-004、AUTH-007 |
| `GET /auth/csrf` | `{csrf_token}` 并刷新 CSRF Cookie | NFR-002 |
| `GET /auth/sessions` | 当前用户的 Session 列表 | AUTH-006 |
| `DELETE /auth/sessions/{session_id}` | 撤销指定本人 Session | AUTH-006 |
| `GET /auth/admin/sessions` | 管理员查看当前所有活跃登录会话的脱敏用户与设备摘要 | AUTH-007、AUTH-008、NFR-006 |

`identifier` 可以是 Connect 邮箱前缀用户名或完整邮箱；用户名先补全为当前 Connect 域名，完整邮箱按原域名规范化，因此旧域名存量账号仍须输入完整邮箱。用户名和对应 Connect 完整邮箱映射到同一账号及同一邮箱限流维度。兼容字段 `email` 只用于旧客户端请求解析，新 OpenAPI 契约和前端统一使用 `identifier`。

登录对账号不存在、密码错误、`pending_email` 和 `disabled` 统一返回 401 `INVALID_CREDENTIALS`，响应状态、文案和主体不暴露账号是否存在或当前状态。成功登录唯一的已验证 active student 时，服务端在事务锁内把其持久化为 admin、撤销旧 Session、写审计，再返回管理员用户并创建新的 4 小时空闲 Session；多账号用户不触发该修正。系统不存在注册审批状态；用户在注册成功页或统一重发验证接口继续邮箱验证流程。

### 密码重置

| 方法与路径 | 请求 | 结果 | 需求 |
| --- | --- | --- | --- |
| `POST /auth/password-resets/request` | `{email}` | 统一返回 202 | AUTH-005、AUTH-009 |
| `POST /auth/password-resets/confirm` | `{token,new_password}` | 返回 204，撤销其他 Session | AUTH-005 |

## 工作台与站内通知

### `GET /dashboard`

返回当前用户、未读数、最近 5 条通知、最近 5 个作业和进行中赛事/队伍。每个集合只含当前用户可见资源；优秀作业不出现在工作台，只在对应作业内读取。对应 NEWS-005、HW-006、TEAM-006、SHOW-002。

### 站内通知接口

| 方法与路径 | 行为 | 需求 |
| --- | --- | --- |
| `GET /notifications?status=unread` | 分页返回当前用户提醒 | NEWS-005 |
| `POST /notifications/{notification_id}/read` | 标记单条已读 | NEWS-005 |
| `POST /notifications/read-all` | `{before, type?}` 范围内全部已读 | NEWS-005 |

通知结构包含 `id`、`type`、`title`、`target_url`、`created_at`、`read_at`，不得包含私密评语正文。

## 通知内容接口

### 学生读取

| 方法与路径 | 查询/结果 | 需求 |
| --- | --- | --- |
| `GET /announcements` | `query,unread,page,page_size`；只返回当前受众、已发布且未归档项 | NEWS-003～NEWS-005、NEWS-008 |
| `GET /announcements/{announcement_id}` | 返回清洗后的正文、附件和更新时间 | NEWS-001、NEWS-007～NEWS-008 |

### 管理接口

| 方法与路径 | 行为 | 需求 |
| --- | --- | --- |
| `GET /admin/announcements` | 按状态、受众、日期搜索全部通知 | NEWS-001～NEWS-007 |
| `POST /admin/announcements` | 创建草稿 | NEWS-001～NEWS-003 |
| `GET /admin/announcements/{id}` | 读取草稿和预计受众数 | NEWS-002 |
| `PATCH /admin/announcements/{id}` | 按 `revision` 修改内容、受众、计划和附件 | NEWS-001～NEWS-004、NEWS-007 |
| `POST /admin/announcements/{id}/publish` | 立即发布或确认定时计划 | NEWS-003、NEWS-005～NEWS-006 |
| `POST /admin/announcements/{id}/archive` | 归档 | NEWS-003 |
| `POST /admin/announcements/{id}/send-update` | 为当前受众创建一次更新提醒 Outbox | NEWS-007、MAIL-002～MAIL-005 |

创建/修改主体：

```json
{
  "title": "第一次培训作业说明",
  "summary": "本周提交要求",
  "body_markdown": "## 内容\n...",
  "audience": {
    "all_students": false,
    "cohort_ids": ["uuid"],
    "direction_ids": ["uuid"],
    "match": "intersection"
  },
  "attachment_file_ids": ["uuid"],
  "publish_at": "2026-09-01T20:00:00+08:00",
  "pinned_until": null,
  "send_email": true,
  "revision": 3
}
```

创建时不传 `revision`。受众必须满足：`all_students=true` 时其他集合为空；否则至少选择一个届次或方向。`match=intersection` 表示同时满足非空维度。

## 作业接口

### 学生读取与提交

| 方法与路径 | 行为 | 需求 |
| --- | --- | --- |
| `GET /assignments` | `status,query,page,page_size`；返回本人受众作业与最新提交摘要 | HW-002、HW-003、HW-006 |
| `GET /assignments/{assignment_id}` | 返回要求、外链、有效截止、附件规则、本人提交摘要和优秀作业摘要 | HW-001、HW-004、HW-006、SHOW-002 |
| `POST /assignments/{assignment_id}/submission-versions` | 创建本人正式版本 | SUB-001～SUB-005、FILE-001 |
| `GET /assignments/{assignment_id}/submission` | 返回本人提交聚合、版本和评语 | SUB-003、SUB-005～SUB-007 |
| `GET /assignments/{assignment_id}/excellent-submissions` | 返回该作业已标记的优秀版本摘要 | SHOW-001～SHOW-005 |
| `GET /assignments/{assignment_id}/excellent-submissions/{version_id}` | 返回优秀版本正文、链接、附件和作者姓名，不含评语 | SHOW-002～SHOW-005 |

正式版本请求必须带 `Idempotency-Key`：

```json
{
  "text_markdown": "本次实现说明",
  "external_url": "https://example.invalid/repository",
  "file_ids": ["uuid", "uuid"]
}
```

返回 `201`：`{submission_id, version_id, version_number, submitted_at, total_file_bytes}`。超过有效截止返回 `409 ASSIGNMENT_CLOSED`，未完成文件返回 `409 FILE_NOT_AVAILABLE`。

### 管理接口

| 方法与路径 | 行为 | 需求 |
| --- | --- | --- |
| `GET /admin/assignments` | 搜索全部作业及提交统计 | HW-005 |
| `POST /admin/assignments` | 创建草稿 | HW-001～HW-003 |
| `GET /admin/assignments/{id}` | 读取配置、受众预估/快照和统计 | HW-002、HW-005 |
| `PATCH /admin/assignments/{id}` | 修改允许字段 | HW-007 |
| `POST /admin/assignments/{id}/publish` | 固化受众快照并发布 | HW-002～HW-003 |
| `POST /admin/assignments/{id}/close` | 提前关闭 | HW-003 |
| `POST /admin/assignments/{id}/archive` | 归档 | HW-003 |
| `PUT /admin/assignments/{id}/extensions/{user_id}` | `{extended_deadline,reason}` | HW-004 |
| `DELETE /admin/assignments/{id}/extensions/{user_id}` | 截止前移除尚未使用的延期 | HW-004 |
| `GET /admin/assignments/{id}/submissions` | 按届次、方向、提交/反馈状态列出目标学生 | HW-005 |
| `POST /admin/assignments/{id}/excellent-submissions/{version_id}` | 把本作业版本标记为优秀作业 | SHOW-001～SHOW-003 |
| `DELETE /admin/assignments/{id}/excellent-submissions/{version_id}` | 取消优秀标记 | SHOW-004 |

作业草稿主体包含 `title`、`description_markdown`、`training_url`、`submission_instructions`、`audience`、`allowed_extensions`、`max_total_bytes`、`publish_at`、`deadline` 和 `revision`。`max_total_bytes` 最大为 2147483648。

## 通用提交与评语接口

| 方法与路径 | 访问 | 行为 | 需求 |
| --- | --- | --- | --- |
| `GET /submissions/{submission_id}` | 所有者/团队成员/管理员 | 返回聚合和版本摘要 | SUB-003、SUB-005 |
| `GET /submissions/{submission_id}/versions/{version_id}` | 同上 | 返回不可变版本和当前用户可见评语 | SUB-003、SUB-006 |
| `PUT /admin/submissions/{submission_id}/versions/{version_id}/feedback` | 管理员 | `{body_markdown,revision?}` 创建或修订私密评语 | SUB-006、COMP-005 |

评语响应含 `id`、`body_html`、`created_by`、`created_at`、`updated_at`、`revision`，不含评分字段。

## 赛事接口

### 学生赛事读取与报名

| 方法与路径 | 行为 | 需求 |
| --- | --- | --- |
| `GET /competitions` | 按阶段搜索可见赛事并返回本人状态 | COMP-001～COMP-003 |
| `GET /competitions/{competition_id}` | 返回赛事、时间轴、赛题、报名和队伍摘要 | COMP-001～COMP-004 |
| `POST /competitions/{competition_id}/registration` | 登记本人参赛 | COMP-003 |
| `DELETE /competitions/{competition_id}/registration` | 报名期撤回；已入队时禁止 | COMP-003、TEAM-002 |

### 队伍接口

| 方法与路径 | 请求/行为 | 需求 |
| --- | --- | --- |
| `GET /competitions/{competition_id}/my-team` | 返回本人队伍、成员与权限 | TEAM-001～TEAM-006 |
| `POST /competitions/{competition_id}/teams` | `{name}` 创建队伍并成为队长 | TEAM-001 |
| `POST /competitions/{competition_id}/teams/join` | `{invite_code}` 加入队伍 | TEAM-001～TEAM-004 |
| `POST /teams/{team_id}/invite-code/rotate` | 队长轮换邀请码，明文只返回一次 | TEAM-003 |
| `DELETE /teams/{team_id}/members/{user_id}` | 队长移除成员或成员退出本人 | TEAM-003 |
| `POST /teams/{team_id}/captain-transfer` | `{new_captain_user_id}` | TEAM-003 |
| `POST /teams/{team_id}/dissolve` | 解散仅剩或已清空成员的形成中队伍 | TEAM-003 |

### 赛题提交

| 方法与路径 | 行为 | 需求 |
| --- | --- | --- |
| `GET /competitions/{competition_id}/tasks/{task_id}` | 返回赛题、有效截止、团队提交摘要 | COMP-004、TEAM-006 |
| `POST /competitions/{competition_id}/tasks/{task_id}/submission-versions` | 当前队长创建团队正式版本 | TEAM-006～TEAM-007、SUB-001～SUB-003 |
| `GET /competitions/{competition_id}/tasks/{task_id}/submission` | 当前团队成员查看版本和评语 | TEAM-006、COMP-005 |

版本请求与作业版本结构相同。队伍非 `locked`、人数无效、被取消资格或不在提交期均返回具体 409 错误。

### 管理赛事接口

| 方法与路径 | 行为 | 需求 |
| --- | --- | --- |
| `GET /admin/competitions` | 搜索全部赛事和阶段统计 | COMP-001～COMP-006 |
| `POST /admin/competitions` | 创建赛事草稿 | COMP-001～COMP-002 |
| `GET /admin/competitions/{id}` | 读取赛事、报名、队伍和提交汇总 | COMP-001～COMP-006 |
| `PATCH /admin/competitions/{id}` | 修改尚未生效或允许延后的字段 | COMP-001～COMP-004 |
| `POST /admin/competitions/{id}/publish` | 发布并按时间进入正确阶段 | COMP-002 |
| `POST /admin/competitions/{id}/close-registration` | 提前关报名并锁队 | COMP-002、TEAM-004～TEAM-005 |
| `POST /admin/competitions/{id}/close-submissions` | 提前关提交 | COMP-002 |
| `POST /admin/competitions/{id}/archive` | 归档 | COMP-006 |
| `POST /admin/competitions/{id}/tasks` | 创建赛题草稿 | COMP-004 |
| `PATCH /admin/competition-tasks/{task_id}` | 修改赛题 | COMP-004 |
| `GET /admin/competitions/{id}/teams` | 筛选队伍、人数和提交状态 | TEAM-004～TEAM-006 |
| `POST /admin/teams/{team_id}/members` | `{user_id,reason}` 补录 | TEAM-005 |
| `GET /admin/competitions/{id}/registrations` | 返回个人报名记录、状态、当前队伍和管理员可见的取消资格原因 | COMP-003 |
| `POST /admin/competitions/{id}/registrations/{user_id}/disqualify` | `{reason}` 取消个人资格并在仍有有效队伍时同步取消整队资格 | COMP-003、TEAM-006 |
| `GET /admin/teams/{team_id}` | 返回队伍成员、权限字段和各赛题提交/最新版本摘要 | TEAM-004～TEAM-006、SUB-005 |
| `DELETE /admin/teams/{team_id}/members/{user_id}` | `{reason}` 管理员移除 | TEAM-005 |
| `POST /admin/teams/{team_id}/captain-transfer` | `{new_captain_user_id,reason}` | TEAM-005 |
| `POST /admin/teams/{team_id}/waive-min-size` | `{reason}` 人数豁免 | TEAM-004 |
| `POST /admin/teams/{team_id}/disqualify` | `{reason}` 取消资格 | COMP-003、TEAM-006 |

赛事时间必须满足：`registration_start < registration_end <= submission_start < submission_end`。赛题截止处于提交窗口内。
个人取消资格原因只返回管理员和对应学生本人；联动队伍的 `disqualification_reason` 使用不含个人原因的固定通用说明。管理员补录使 `invalid` 队伍达到最低人数时恢复 `locked`；从 `locked` 队伍移除成员后低于最低人数且没有豁免时转为 `invalid`。所有上述纠错请求必须提供非空原因并写审计。


## 优秀作业接口

优秀作业接口全部嵌套在作业资源下，不提供 `/showcases` 或赛事来源。标记请求无正文；服务端必须验证版本属于指定作业、不是赛事提交且尚未标记。读取权限复用作业受众快照，响应展示提交者姓名和该版本的文本、链接、附件，不返回评语、内部提交聚合 ID 或其他版本。

## 上传与下载接口

### 初始化 `POST /uploads/init`

对应 FILE-001～FILE-004。请求：

```json
{
  "purpose": "assignment_submission",
  "context_id": "assignment-or-task-uuid",
  "file_name": "project.zip",
  "size_bytes": 734003200,
  "media_type": "application/zip",
  "sha256": "64-lowercase-hex"
}
```

返回 `201`：

```json
{
  "upload_id": "uuid",
  "status": "initialized",
  "part_size_bytes": 16777216,
  "part_count": 44,
  "uploaded_parts": [],
  "expires_at": "2026-08-24T10:00:00+08:00"
}
```

`purpose` 为 `announcement_attachment`、`assignment_submission` 或 `competition_submission`。服务端按上下文验证权限、截止、扩展名和总量。

### 分片与完成

| 方法与路径 | 请求/结果 | 需求 |
| --- | --- | --- |
| `POST /uploads/{upload_id}/parts/presign` | `{part_numbers:[1,2]}` → 每片短时 URL 与必需校验头 | FILE-002、FILE-005 |
| `GET /uploads/{upload_id}` | 状态、已完成分片、过期时间 | FILE-002、FILE-006 |
| `POST /uploads/{upload_id}/complete` | `{parts:[{part_number,etag,checksum_sha256}],sha256}` → 可引用文件 | FILE-003～FILE-004 |
| `DELETE /uploads/{upload_id}` | 终止会话并异步清理对象 | FILE-002、FILE-006 |
| `POST /files/{file_id}/download-url` | 授权后返回 5 分钟预签名 URL | FILE-005 |

每次预签名最多申请 10 个分片；分片 URL 有效期 15 分钟。完成接口必须带幂等键。

## 管理用户与基础数据

| 方法与路径 | 行为 | 需求 |
| --- | --- | --- |
| `GET /admin/users` | 按状态、可选届次/方向和角色搜索账号 | AUTH-007～AUTH-008 |
| `POST /admin/users/{id}/disable` | `{reason}` 并撤销 Session | AUTH-007 |
| `POST /admin/users/{id}/restore` | `{reason}` | AUTH-007 |
| `PATCH /admin/users/{id}` | 调整姓名、学号、邮箱、可空届次/方向 | AUTH-007、AUTH-010 |
| `POST /admin/users/{id}/role` | `{role,reason}`，禁止撤销最后一个管理员 | AUTH-008 |
| `GET/POST /admin/cohorts` | 列表/创建可选届次 | AUTH-007 |
| `PATCH /admin/cohorts/{id}` | 修改名称或启用状态 | AUTH-007 |
| `GET/POST /admin/directions` | 列表/创建可选方向 | AUTH-007 |
| `PATCH /admin/directions/{id}` | 修改名称或启用状态 | AUTH-007 |

## 邮件与审计管理

| 方法与路径 | 行为 | 需求 |
| --- | --- | --- |
| `GET /admin/mail-outbox` | 按状态、事件类型、时间搜索；接收方脱敏 | MAIL-002～MAIL-004 |
| `POST /admin/mail-outbox/{id}/retry` | 最终失败项人工重试，使用原幂等键 | MAIL-003～MAIL-005 |
| `GET /admin/audit-logs` | 按操作者、动作、资源、请求 ID、时间搜索 | NFR-006 |

邮件正文和一次性令牌不通过管理 API 返回。审计 API 只读。

## 健康接口

| 路径 | 用途 | 响应 |
| --- | --- | --- |
| `GET /health/live` | 进程存活 | 进程可响应即 200 |
| `GET /health/ready` | 接流量条件 | 配置有效且 PostgreSQL 可用时 200 |
| `GET /health/worker` | Worker 心跳，由内网监控访问 | 最近心跳、Outbox 延迟摘要 |

健康接口不得返回版本秘密、连接串、凭证或用户数据。
