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

`email` 必须规范化后精确以 `@connect.hkust-gz.edu.cn` 结尾；旧域名、子域名、相似域名或通过该字符串作为局部内容的请求均被拒绝。`password` 必须为 8～128 个 Unicode 字符，并通过常见密码和身份相似性检查。

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

错误：`INVALID_CAMPUS_EMAIL`、`EMAIL_ALREADY_REGISTERED`、`STUDENT_NUMBER_ALREADY_REGISTERED`、`WEAK_PASSWORD`。邮箱或学号重复统一返回 `400 VALIDATION_ERROR`，并在 `details` 中分别使用 `email` 或 `student_number` 字段；应用预检和数据库唯一约束最终拒绝必须保持相同对外契约，不得退化为 500。

### 邮箱验证

| 方法与路径 | 请求 | 结果 | 需求 |
| --- | --- | --- | --- |
| `POST /auth/email-verifications/resend` | `{email}` | 统一返回 202 | AUTH-002、AUTH-009 |
| `POST /auth/email-verifications/confirm` | `{token}` | `{status: active}`；空系统首个验证账号成为管理员，其余为学生并原子补入当时仍开放且匹配的作业受众快照 | AUTH-002～AUTH-003、AUTH-008 |

令牌无效返回 `400 INVALID_TOKEN`，过期或已使用返回 410。重发接口不暴露邮箱是否注册；注册和重发验证均不使用应用层持久失败窗口，但仍可能受 Nginx 瞬时入口限流。

### Session

| 方法与路径 | 请求/响应 | 需求 |
| --- | --- | --- |
| `POST /auth/login` | `{identifier,password,remember_me=false}` → `{user}` 并设置 Session/CSRF Cookie；暂时兼容旧 `{email,password}` 请求 | AUTH-004、AUTH-006、AUTH-009、AUTH-013 |
| `POST /auth/logout` | 撤销当前 Session，返回 204 | AUTH-006 |
| `DELETE /auth/account` | `{current_password,confirmation_email}`；重新认证并永久删除本人账号/个人数据，成功清 Session 与 CSRF Cookie，返回 204 | AUTH-012 |
| `GET /auth/me` | 当前用户、可空技术方向、真实角色、状态和当前 Session 的 `student_view` 标记；届次字段仅为历史兼容 | AUTH-004、AUTH-007 |
| `GET /auth/csrf` | `{csrf_token}` 并刷新 CSRF Cookie | NFR-002 |
| `GET /auth/sessions` | 当前用户的 Session 列表，包含 `remembered`、IP 网段与到期时间，不含 token 或精确 IP | AUTH-006、AUTH-013 |
| `DELETE /auth/sessions/{session_id}` | 撤销指定本人 Session | AUTH-006 |
| `GET /auth/admin/sessions` | 管理员查看当前所有活跃登录会话的脱敏用户、`remembered` 与设备摘要 | AUTH-007～AUTH-008、AUTH-013、NFR-006 |
| `POST /auth/student-view` | 当前真实角色为 `admin` 时把当前 Session 标记为学生视图，返回 `user` 且 `student_view: true` | AUTH-011 |
| `DELETE /auth/student-view` | 清除当前 Session 的学生视图标记，返回 `user` 且 `student_view: false` | AUTH-011 |

`identifier` 可以是 Connect 邮箱前缀用户名或完整邮箱；用户名先补全为当前 Connect 域名，完整邮箱按原域名规范化，因此旧域名存量账号仍须输入完整邮箱。用户名和对应 Connect 完整邮箱映射到同一账号及同一邮箱限流维度。兼容字段 `email` 只用于旧客户端请求解析，新 OpenAPI 契约和前端统一使用 `identifier`。
`remember_me` 是可选布尔值，省略时为 `false`。普通登录返回无 `Max-Age/Expires` 的浏览器会话 Cookie，服务端仍使用管理员 4 小时/学生 12 小时空闲及 14 天绝对期；`true` 时 Session 与 CSRF Cookie 的 `Max-Age` 为不超过 30 天，Session 记录的空闲/绝对期限同样不超过 30 天，并保存由原始 Session token 与可信精确来源 IP 计算的 64 位 HMAC。后续请求 IP 绑定不匹配时撤销 Session 并返回 `401 AUTHENTICATION_REQUIRED`；仅有相同 IP 而无 Cookie 仍返回 401。成功响应、日志、会话列表与 OpenAPI 均不返回密码、Session token、绑定 HMAC 或精确 IP。
`DELETE /auth/account` 只接受当前有效账号本人；`confirmation_email` 去除首尾空白并规范化后必须与当前账号完全一致，错误密码返回 `401 INVALID_CREDENTIALS`，邮箱不一致返回带 `confirmation_email/ACCOUNT_EMAIL_MISMATCH` 的 `400 VALIDATION_ERROR`，最后一名激活管理员返回 `409 STATE_CONFLICT`。成功前不会清 Cookie；数据库事务失败时账号保持，成功后不返回删除计数、邮箱或对象信息。备份确认不由普通用户填写，但页面必须披露不可撤销和备份保留期边界。


`GET /auth/me` 和登录响应中的 `user` 始终返回真实 `role`；管理员学生视图通过 `student_view: true` 表示当前 Session 的有效角色为学生。学生视图请求管理员接口（包括 `/admin/*` 与管理员会话列表）返回 403；学生通知、作业、独立队伍、个人提交和上传接口按有效角色执行，关闭后恢复管理员权限。

登录先查询规范化账号并执行真实或 dummy Argon2id 校验。账号不存在、密码错误、`pending_email` 和 `disabled` 统一返回 401 `INVALID_CREDENTIALS`，10 分钟内达到规范化邮箱 5 次或来源 IP 30 次阈值时统一返回 429 `RATE_LIMITED` 和 `Retry-After: 600`；响应状态、文案和主体不暴露账号是否存在或当前状态。已验证 `active` 账号的正确密码不受既有失败事件持久冷却阻断。成功登录唯一的已验证 active student 时，服务端在事务锁内把其持久化为 admin、撤销旧 Session、写审计，再返回管理员用户并创建新的 4 小时空闲 Session；多账号用户不触发该修正。系统不存在注册审批状态；用户在注册成功页或统一重发验证接口继续邮箱验证流程。

### 密码重置

| 方法与路径 | 请求 | 结果 | 需求 |
| --- | --- | --- | --- |
| `POST /auth/password-resets/request` | `{email}` | 统一返回 202 | AUTH-005、AUTH-009 |
| `POST /auth/password-resets/confirm` | `{token,new_password}`，`new_password` 使用与注册相同的 8～128 字符策略 | 返回 204，撤销其他 Session | AUTH-005 |

密码重置申请不使用应用层持久失败窗口，始终保持统一 202；仍记录不含敏感字段的安全事件，并可能受 Nginx 瞬时入口限流。

## 工作台与站内通知

### `GET /dashboard`

返回当前用户、有效未读总数 `unread_count`、按 `announcements/assignments/teams/help_requests` 分类的 `unread_counts`、最近 5 条通知、最近 5 个作业和本人当前队伍。已归档公告提醒不进入总数或分类计数。每个集合只含当前用户可见资源；优秀作业不出现在工作台，只在对应作业内读取。对应 NEWS-005、HW-006、TEAM-006、SHOW-002。

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
| `GET /announcements/{announcement_id}` | 只返回当前受众的已发布通知正文、附件和更新时间；归档通知与不可见资源统一 404 | NEWS-001、NEWS-007～NEWS-009 |

### 管理接口

| 方法与路径 | 行为 | 需求 |
| --- | --- | --- |
| `GET /admin/announcements` | 按状态、受众、日期搜索未删除通知；手工归档仍返回，已删除归档不返回 | NEWS-001～NEWS-007、NEWS-009 |
| `POST /admin/announcements` | 创建草稿 | NEWS-001～NEWS-003 |
| `GET /admin/announcements/{id}` | 读取未删除通知、预计受众数和手工归档留存记录；已删除归档统一 404 | NEWS-002、NEWS-009 |
| `PATCH /admin/announcements/{id}` | 按 `revision` 修改内容、受众、计划和附件 | NEWS-001～NEWS-004、NEWS-007 |
| `DELETE /admin/announcements/{id}` | 未发布通知取消活动定时任务并物理删除；已发布或手工归档通知归档标记删除；返回 204 | NEWS-003、NEWS-009、NFR-006 |
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

上方示例保留 `cohort_ids` 仅用于说明历史兼容字段；新产品页面不会生成非空届次 ID。

创建时不传 `revision`。产品端受众必须满足：`all_students=true` 时其他集合为空；否则至少选择一个技术方向。`match=intersection` 表示同时满足所选方向。请求中的 `cohort_ids` 仅为历史客户端/资源兼容字段，新建页面始终发送空数组。

删除接口以独立删除标记区分手工归档和已删除归档。物理删除只适用于 `draft/scheduled`，并解除 `announcement_files` 绑定；文件对象不在请求中同步删除，继续由孤立对象 Worker 处理。`published` 删除转为归档并写删除标记，手工 `archived` 首次 DELETE 补写标记；常规管理列表/详情只返回未删除内容，重复 DELETE 对已有标记幂等 204。归档删除把未读公告提醒标为已读并保留提醒/邮件历史，学生随后读取统一 404。

## 作业接口

### 学生读取与提交

| 方法与路径 | 行为 | 需求 |
| --- | --- | --- |
| `GET /assignments` | `status,query,page,page_size`；普通学生只返回正式受众快照（发布时成员及激活时开放作业补录）中未归档的作业与最新提交摘要；管理员当前 Session 开启学生视图时，按该账号技术方向对新规则作业执行只读受众预览，不写入或改变快照，历史届次受众仍按原快照兼容 | HW-002、HW-003、HW-006、HW-008、AUTH-011 |
| `GET /assignments/{assignment_id}` | 返回未归档作业的要求、外链、有效截止、附件规则、本人提交摘要和优秀作业摘要；归档作业 404，管理员当前 Session 开启学生视图时仍按学生规则读取 | HW-001、HW-004、HW-006、HW-008、SHOW-002、AUTH-011 |
| `POST /assignments/{assignment_id}/submission-versions` | 创建本人正式版本；管理员当前 Session 开启学生视图时允许以自身账号创建个人版本，普通管理员视图仍禁止代交 | SUB-001～SUB-005、FILE-001、AUTH-011 |
| `GET /assignments/{assignment_id}/submission` | 返回本人提交聚合、版本和评语 | SUB-003、SUB-005～SUB-007 |
| `GET /assignments/{assignment_id}/excellent-submissions` | 返回该作业已标记的优秀版本摘要；学生视图管理员按临时受众预览规则读取 | SHOW-001～SHOW-005、AUTH-011 |
| `GET /assignments/{assignment_id}/excellent-submissions/{version_id}` | 返回优秀版本正文、链接、附件和作者姓名，不含评语；学生视图管理员按临时受众预览规则读取 | SHOW-002～SHOW-005、AUTH-011 |

正式版本请求必须带 `Idempotency-Key`：

```json
{
  "text_markdown": "本次实现说明",
  "external_url": "https://example.invalid/repository",
  "file_ids": ["uuid", "uuid"]
}
```

返回 `201`：`{submission_id, version_id, version_number, submitted_at, total_file_bytes}`。`file_ids` 最多包含 100 个不重复 UUID；浏览器可一次选择多张图片或其他允许类型附件，但每个文件仍分别经过现有 `/uploads*` 会话，正式版本只在用户确认时一次绑定全部可用文件。超过有效截止返回 `409 ASSIGNMENT_CLOSED`，未完成文件返回 `409 FILE_NOT_AVAILABLE`。

### 管理接口

| 方法与路径 | 行为 | 需求 |
| --- | --- | --- |
| `GET /admin/assignments` | 搜索未删除作业及提交统计；手工归档仍返回，已删除归档不返回 | HW-005、HW-008 |
| `POST /admin/assignments` | 创建草稿 | HW-001～HW-003 |
| `GET /admin/assignments/{id}` | 读取未删除作业配置、受众预估/快照和统计；已删除归档统一 404 | HW-002、HW-005、HW-008 |
| `PATCH /admin/assignments/{id}` | 按 `revision` 修改作业；草稿可修改完整配置，`published/closed` 允许标题、说明、培训资料链接、提交说明、受众和公共截止变化。受众变化按当前激活学生原子替换权威快照；发布时间与附件规则必须原值回传。截止前移不得早于最后正式提交；自动关闭作业把截止延至未来时重新开放，提前关闭作业保持关闭 | HW-002～HW-003、HW-007、NFR-006 |
| `DELETE /admin/assignments/{id}` | 草稿取消活动定时任务并物理删除；已发布、已关闭或手工归档作业归档标记删除；返回 204 | HW-003、HW-008、NFR-006 |
| `POST /admin/assignments/{id}/publish` | 固化受众快照并发布 | HW-002～HW-003 |
| `POST /admin/assignments/{id}/close` | 提前关闭 | HW-003 |
| `POST /admin/assignments/{id}/archive` | 归档 | HW-003 |
| `PUT /admin/assignments/{id}/extensions/{user_id}` | `{extended_deadline,reason}` | HW-004 |
| `DELETE /admin/assignments/{id}/extensions/{user_id}` | 截止前移除尚未使用的延期 | HW-004 |
| `GET /admin/assignments/{id}/submissions` | 按方向、提交/反馈状态分页列出“当前受众并集历史提交者”；每项返回 `in_current_audience`，统计口径只计算当前受众，历史届次快照仍可读取 | HW-005 |
| `POST /admin/assignments/{id}/excellent-submissions/{version_id}` | 把本作业版本标记为优秀作业 | SHOW-001～SHOW-003 |
| `DELETE /admin/assignments/{id}/excellent-submissions/{version_id}` | 取消优秀标记 | SHOW-004 |

作业草稿主体包含 `title`、`description_markdown`、`training_url`、`submission_instructions`、`audience`、`allowed_extensions`、`max_total_bytes`、`publish_at`、`deadline` 和 `revision`。`max_total_bytes` 最大为 2147483648。

作业删除以独立删除标记区分手工归档和已删除归档。物理删除只适用于尚无学生生命周期的 `draft`；`published/closed` 删除必须转为 `archived` 并写删除标记，手工 `archived` 首次 DELETE 补写标记；常规管理列表/详情只返回未删除内容，重复 DELETE 对已有标记幂等 204。归档删除不得删除固定受众、提交、版本、评语、优秀标记和附件；学生列表、详情、优秀作业读取以及优秀附件重新签名均排除归档作业，提交所有者的历史版本仍按不可变记录保留。

## 个人作业提交与评语接口

| 方法与路径 | 访问 | 行为 | 需求 |
| --- | --- | --- | --- |
| `GET /submissions/{submission_id}` | 所有者/管理员 | 返回个人作业聚合和版本摘要 | SUB-003、SUB-005 |
| `GET /submissions/{submission_id}/versions/{version_id}` | 所有者/管理员 | 返回不可变版本和当前用户可见评语 | SUB-003、SUB-006 |
| `PUT /admin/submissions/{submission_id}/versions/{version_id}/feedback` | 管理员 | `{body_markdown,revision?}` 创建或修订私密评语，并同事务创建站内提醒与唯一评语邮件 Outbox | SUB-006、MAIL-001～MAIL-005 |

评语响应含 `id`、`body_html`、`created_by`、`created_at`、`updated_at`、`revision`，不含评分字段。邮件仅含学生称呼、作业标题和 `/assignments/{assignment_id}/submissions/{submission_id}` 站内链接，不含评语正文。

## 独立队伍接口

“校内赛”是前端导航名称，不对应赛事实体 API。以下接口均以有效 Session 为前提；学生写操作还要求同源与 CSRF。

### 学生队伍接口

| 方法与路径 | 请求/行为 | 需求 |
| --- | --- | --- |
| GET /team-settings | active student 读取当前 `is_team_open`、更新时间和 revision | TEAM-014 |
| GET /team-profiles | 支持 `direction_id`；返回简介分页、启用技术组选项和 `team_open` | TEAM-010、TEAM-014 |
| GET /admin/team-settings | 真实管理员读取唯一学生组队开关 | TEAM-014 |
| PATCH /admin/team-settings | is_team_open、revision；同源、CSRF、乐观锁与脱敏审计 | TEAM-014 |

| GET /teams | query、page、page_size；返回 forming 队伍的名称、状态、当前/最大人数和 can_join，不返回成员或邀请码 | TEAM-006 |
| GET /teams/me | 返回本人当前队伍、成员、成员技术方向/已提交简介和 can_manage；无队伍返回 null | TEAM-003、TEAM-006、TEAM-010、TEAM-013 |
| GET /team-profiles | query、page、page_size；返回 active student 自愿发布的姓名、技术方向、纯文本简介、更新时间和当前账号邀请状态 | TEAM-010～TEAM-011 |
| GET /team-profiles/me | 返回本人已发布简介或 null | TEAM-010 |
| PUT /team-profiles/me | introduction、revision；创建时 revision 为 null，更新时必须匹配当前版本 | TEAM-010、TEAM-013 |
| GET /team-invitations | 当前无队伍受邀者读取发给本人的 pending 邀请 | TEAM-012 |
| POST /team-invitations | invitee_user_id；未满队伍的任一当前成员发出邀请，同队同目标重复 pending 幂等返回现有邀请 | TEAM-011、TEAM-013 |
| POST /team-invitations/{invitation_id}/accept | 受邀者接受后加入队伍并取消本人其他 pending 邀请，返回本人队伍 | TEAM-012 |
| POST /team-invitations/{invitation_id}/decline | 受邀者拒绝邀请，返回统一成功响应 | TEAM-012 |
| POST /teams | name；直接创建队伍并成为队长，201 响应中的 invite_code 只出现一次 | TEAM-001～TEAM-002 |
| POST /teams/join | invite_code；加入未满 forming 队伍 | TEAM-001～TEAM-004 |
| POST /teams/auto-assign | 无正文；优先加入人数最少的未满 forming 队伍，否则自动建队 | TEAM-002、TEAM-004～TEAM-005 |
| POST /teams/{team_id}/invite-code/rotate | 队长轮换邀请码，明文只返回一次 | TEAM-003 |
| DELETE /teams/{team_id}/members/{user_id} | 队长移除非队长成员，或非队长退出本人 | TEAM-003 |
| POST /teams/{team_id}/captain-transfer | new_captain_user_id | TEAM-003 |
| POST /teams/{team_id}/dissolve | 仅剩队长一人时解散 | TEAM-003、TEAM-007 |

创建、加入和自动分配只允许有效角色为 student 的 active 账号。已有当前队伍返回 409 ALREADY_IN_TEAM；队伍已满返回 409 TEAM_FULL；并发分配冲突返回 409 TEAM_MEMBERSHIP_CONFLICT；无效邀请码返回 400 INVITE_CODE_INVALID。邀请码尝试按账号和来源网段限流，超限返回 429 RATE_LIMITED 和 Retry-After。非队长管理返回 403 TEAM_CAPTAIN_REQUIRED，队长直接退出返回 409 CAPTAIN_TRANSFER_REQUIRED，非单人队伍解散返回 409 TEAM_NOT_EMPTY。

组队简介 `introduction` 去空白后为 1～2,000 字符纯文本，不接收 HTML 字段；目录不返回邮箱、学号、邀请码或 Session 信息。发出邀请时目标必须是另一名已提交简介、当前无队伍的 active student，发送者只需是关联队伍当前成员而不要求为队长。接受时重新锁定并校验邀请仍为 pending、队伍仍 `forming` 且未满、本人仍无队伍；已处理邀请返回 `409 INVITATION_NOT_PENDING`，队伍不可用、已在队伍、队伍已满和并发成员冲突分别返回稳定 409。邀请不发送邮件、不自动加入，也不包含邀请码。

### 管理员队伍接口

| 方法与路径 | 请求/行为 | 需求 |
| --- | --- | --- |
| GET /admin/teams | query、page、page_size；分页返回当前独立队伍 | TEAM-008 |
| GET /admin/teams/{team_id} | 返回成员和队伍详情 | TEAM-008 |
| POST /admin/teams/{team_id}/members | user_id、reason；补录 active student | TEAM-004、TEAM-008 |
| DELETE /admin/teams/{team_id}/members/{user_id} | reason；管理员移除非队长成员 | TEAM-008 |
| POST /admin/teams/{team_id}/captain-transfer | new_captain_user_id、reason | TEAM-008 |
| DELETE /admin/teams/{team_id} | reason；物理删除队伍并级联成员关系，返回 204 | TEAM-008 |

管理员接口必须由真实 admin 且未开启学生视图调用；所有写操作要求 CSRF。reason 去空白后必须为 1～2,000 字符并写脱敏审计；删除二次确认属于前端防误触，不能代替后端授权。独立队伍不统计或读取历史团队提交，删除不会触碰 legacy 赛事、版本、评语、附件或 MinIO 对象。

### Legacy 数据边界

COMP-001～COMP-006 已退出当前产品。后端不注册 /competitions*、/admin/competitions* 或赛事赛题提交 API；旧赛事、报名、赛题、原队伍和历史赛事提交只由 0020 迁移后的 legacy 数据结构保留。前端旧详情路径仅重定向到 /competitions 队伍中心，不读取这些记录。

## 学生问卷接口

### 学生读取与回答

| 方法与路径 | 行为 | 需求 |
| --- | --- | --- |
| `GET /intentions` | 返回当前 `open`、处于填写窗口内且面向全部学生或命中本人当前技术组的问卷摘要、题目数、提交上限及本人已提交次数 | INT-002～INT-004、INT-009 |
| `GET /intentions/{survey_id}` | 返回清洗说明、多道题目/选项、提交上限和本人最新回答；可选 `token` 不匹配或本人不属于当前填写范围时返回 404 | INT-001～INT-004、INT-006、INT-009 |
| `PUT /intentions/{survey_id}/response` | `{answers:[{question_id,selected_option_ids}],free_text?}` 在本人当前属于填写范围时覆盖最新回答并原子增加一次提交次数 | INT-002～INT-004、INT-009 |

学生接口按有效角色鉴权；普通管理员视图不能代填，管理员学生视图可以按本人账号和当前 `users.direction_id` 填写。问卷关闭、未开始或已过结束时间时，读取不可见，写入返回 `409 INTENTION_CLOSED`；问卷受众不匹配时列表不返回，详情、带二维码 token 的详情和提交统一返回 404；达到上限返回 `409 INTENTION_SUBMISSION_LIMIT_REACHED`。缺少题目、重复题目、单选数量错误、问题不属于问卷、选项不属于对应问题或重复选项均被拒绝。

### 管理接口

| 方法与路径 | 行为 | 需求 |
| --- | --- | --- |
| `GET /admin/intentions` | 返回全部问卷及 `{audience:{all_students,direction_ids}}`、题目数、提交人数和每人提交上限，不含个人回答 | INT-001～INT-005、INT-009 |
| `GET /admin/intentions/{survey_id}` | 返回任意状态问卷的管理摘要、填写范围、revision、完整问题与选项，不含个人回答 | INT-001～INT-002、INT-009 |
| `POST /admin/intentions` | 使用 `{title,description_markdown,questions,max_submissions?,starts_at?,ends_at?,audience:{all_students,direction_ids}}` 创建 `draft` 多题问卷并清洗 Markdown；`max_submissions=null` 表示不限，省略 `audience` 兼容为全部学生 | INT-001～INT-003、INT-009 |
| `PATCH /admin/intentions/{survey_id}` | 按 `revision` 原子修改非归档问卷并返回刷新后的完整内容；`draft` 可整体替换题目/选项，`open/closed` 只原位更新标题、说明、题目文字、提交上限、时间窗口和填写范围，题量/题型/选项变化返回 `409 INTENTION_ANSWER_STRUCTURE_IMMUTABLE`，归档返回 `409 INTENTION_ARCHIVED`，revision 冲突返回 409 | INT-001～INT-003、INT-009 |
| `DELETE /admin/intentions/{survey_id}` | 二次确认后永久删除任意状态问卷、全部题目/选项/回答/受众并取消未完成问卷邮件；成功返回 204 | INT-010、NFR-006 |
| `POST /admin/intentions/{survey_id}/{action}` | `action` 为 `open`、`closed` 或 `archived`；`open` 可用于首次开放 `draft` 或按原受众重新开启 `closed`，草稿首次开放会复核目标技术组仍启用；`closed` 关闭当前开放问卷，`archived` 只归档已关闭问卷 | INT-002、INT-009 |
| `GET /admin/intentions/{survey_id}/stats` | 返回当前目标激活学生数、提交人数/比例和每道题各选项人数/比例 | INT-005、INT-009 |
| `GET /admin/intentions/{survey_id}/responses` | 返回实名提交名单：身份、最新分题答案、补充说明、累计提交次数和最后提交时间 | INT-005 |
| `POST /admin/intentions/{survey_id}/qr-token` | 轮换二维码 token 并返回 `{survey_id,token,fill_url,generated_at}` | INT-006 |
| `POST /admin/intentions/{survey_id}/email-notifications` | 必填 `Idempotency-Key`；请求为 `{recipient_scope:"manual",recipient_user_ids:[uuid,...]}`、`{recipient_scope:"direction",direction_ids:[uuid,...]}` 或 `{recipient_scope:"all"}`，返回 `{survey_id,requested_count,queued_count,already_queued_count}`；旧 `direction_id` 暂作滚动发布兼容输入 | INT-007、MAIL-001～MAIL-005 |
| `POST /admin/intentions/{survey_id}/apply-first-choice-directions` | 请求为 `{question_id,option_mappings:[{option_id,direction_id}],confirm_overwrite:true}`，返回 `{survey_id,question_id,eligible_response_count,updated_count,unchanged_count,skipped_response_count}` | INT-008 |

`audience.all_students=true` 时 `direction_ids` 必须为空；`all_students=false` 时必须提供 1～50 个不重复 UUID，且创建、每次非归档编辑和首次开放都整体确认目标组仍启用，否则返回 `400 INVALID_INTENTION_AUDIENCE`。状态允许 `draft → open → closed`、`closed → open` 和 `closed → archived`；`archived` 为终态，其他状态组合返回 `409 STATE_CONFLICT`。修改接口锁定问卷并先检查 revision；`open/closed` 请求仍提交完整问题结构用于比较，但只能改变题目文字，题目数量及顺序、`allow_multiple`、选项数量/文字/顺序必须和数据库一致，且不删除问题、选项、回答或 token。重新开启只改变状态、更新者、更新时间和 revision，保留当前内容、填写范围、既有回答/累计次数、二维码 token、时间窗口和提交上限，并写 `intention.reopen` 脱敏审计。管理详情和修改接口必须使用真实管理员依赖，学生和管理员学生视图均返回 403；详情不含个人答案。统计接口不含个人信息且分母按当前填写范围内的激活学生计算；实名名单接口同样只允许真实管理员，名单只返回当前最新答案，不返回被覆盖的历史内容。二维码 token 使用高熵随机值，数据库只保存 SHA-256；每次生成使旧 token 失效，`closed`/`archived` 问卷拒绝生成，填写地址仍由 Session、角色、开放窗口和当前技术组受众保护；关闭前已有 token 在重新开启且当前时间窗口有效时可继续定位问卷。

删除接口只允许真实管理员并要求 CSRF，不要求问卷处于特定状态或提交 revision。Service 锁定问卷后，在同一事务删除该问卷仍为 `pending/processing/retry` 的 `intention_open_email`、全部回答选择和问卷根记录；受众、题目、选项及回答通过现有级联清理，已应用到 `users.direction_id` 的第一志愿结果不回滚。成功只返回 204 并写不含问卷/答案正文的 `intention.delete` 审计；不存在或已删除资源返回 `404 RESOURCE_NOT_FOUND`，失败整体回滚。删除提交后，管理/学生列表和所有直接读取、二维码、提交、统计及名单接口均因物理不存在而不再返回该问卷。

第一志愿方向端点只允许真实管理员并要求 CSRF，`confirm_overwrite` 只能为 `true`。服务端以 `display_order,id` 确认第一题且要求单选，请求选项集合必须与第一题全部选项完全一致，全部目标方向必须仍启用；错误分别返回 `422 INVALID_INTENTION_FIRST_CHOICE`、`422 INTENTION_FIRST_CHOICE_MUST_BE_SINGLE`、`400 INVALID_INTENTION_DIRECTION_MAPPING`。事务只更新当前有最新回答的 `active student`，相同方向不增加 revision；没有可更新回答者返回 `422 NO_INTENTION_DIRECTION_RESPONSES`。成功结果中的跳过数量为全部回答者减去符合条件回答者；操作不受问卷状态限制，但开放问卷后续改答不会自动同步。事务失败整体回滚，不修改问卷、回答、提交次数、二维码、Session 或既有作业受众快照。
该端点仅适用于标题去除首尾空白后精确等于“意向选择”的问卷；其他标题、附加前后缀或近似文案返回 `422 INVALID_INTENTION_DIRECTION_SURVEY`。标题校验发生在题目、方向、回答和用户锁查询之前，拒绝时不得改方向或写成功审计。

邮件端点只允许真实管理员并要求 CSRF，三种范围互斥：`manual` 要求 1～100 个不重复成员 UUID 且不得带技术组，`direction` 要求 1～100 个不重复技术组 UUID 且不得带成员，`all` 不得带成员或技术组。旧客户端可暂时只提交一个 `direction_id`，但不得与 `direction_ids` 同时存在。请求不得包含邮箱；手动模式由服务端整体重新校验全部账号仍为问卷受众内的已验证激活学生，任一无效或越界返回 `400 INVALID_INTENTION_EMAIL_RECIPIENTS`；技术组模式要求所选组是问卷目标技术组的子集，再整体复核全部技术组当前激活，任一越界或无效返回 `400 INVALID_INTENTION_EMAIL_DIRECTION`；技术组成员按并集合并，`all` 只解析问卷全部目标激活学生。最终集合为空返回 `400 NO_INTENTION_EMAIL_RECIPIENTS`，以上错误均不写部分任务。问卷不是当前可填写的 `open` 状态时返回 `409 INTENTION_CLOSED`。同一 revision 下同一成员的既有事件返回 `already_queued_count` 而不重复入队；关闭后重新开启 revision 增加，可由管理员再次显式选择发送。

## 优秀作业接口

优秀作业接口全部嵌套在作业资源下，不提供 `/showcases` 或赛事来源。标记请求无正文；服务端必须验证版本属于指定作业、属于个人作业且尚未标记。普通学生读取权限复用作业受众快照；管理员当前 Session 开启学生视图时按当前作业受众配置临时预览。响应展示提交者姓名和该版本的文本、链接、附件，不返回评语、内部提交聚合 ID 或其他版本。

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

`purpose` 只接受 `announcement_attachment` 或 `assignment_submission`。数据库检查约束继续允许 `competition_submission` 仅为保存 legacy 文件元数据，公共请求 Schema 与 Service 必须拒绝该值。服务端按上下文验证权限、截止、扩展名和总量。

### 分片与完成

| 方法与路径 | 请求/结果 | 需求 |
| --- | --- | --- |
| `POST /uploads/{upload_id}/parts/presign` | `{part_numbers:[1,2]}` → 每片短时 URL 与必需校验头 | FILE-002、FILE-005 |
| `GET /uploads/{upload_id}` | 状态、已完成分片、过期时间 | FILE-002、FILE-006 |
| `POST /uploads/{upload_id}/complete` | `{parts:[{part_number,etag,checksum_sha256}],sha256}` → 可引用文件 | FILE-003～FILE-004 |
| `DELETE /uploads/{upload_id}` | 终止会话并异步清理对象 | FILE-002、FILE-006 |
| `POST /files/{file_id}/download-url` | 授权后返回 5 分钟预签名 URL | FILE-005 |
| `POST /files/{file_id}/preview-url` | 复用下载的完整业务授权；仅安全可预览类型返回 5 分钟 inline URL | FILE-005、FILE-007 |

每次预签名最多申请 10 个分片；分片 URL 有效期 15 分钟。完成接口必须带幂等键。

## 管理用户与基础数据

| 方法与路径 | 行为 | 需求 |
| --- | --- | --- |
| `GET /admin/users` | `search,status,role,direction_id,activity,page,page_size`；`page` 为 1～10000、`page_size` 为 1～100；在分页前按姓名、学校邮箱、学号及中文/英文角色和状态搜索全部账号，返回准确 `total`；历史 `cohort_id` 查询参数保留兼容 | AUTH-007～AUTH-008 |
| `POST /admin/users/{id}/disable` | `{reason}` 并撤销 Session | AUTH-007 |
| `POST /admin/users/{id}/restore` | `{reason}` | AUTH-007 |
| `PATCH /admin/users/{id}` | 调整姓名、学号、邮箱和可空技术方向；历史 `cohort_id` 字段保留兼容 | AUTH-007、AUTH-010 |
| `POST /admin/users/{id}/role` | `{role,reason}`，禁止撤销最后一个管理员 | AUTH-008 |
| `DELETE /admin/users/{id}` | `{reason,current_password,confirmation_email,backup_confirmed}`；删除任意非当前账号及个人数据，返回 204 | AUTH-012、NFR-006～NFR-009 |
| `GET/POST /admin/cohorts` | 历史兼容的届次列表/创建接口，不再作为产品入口 | AUTH-007 |
| `PATCH /admin/cohorts/{id}` | 历史兼容接口，修改名称或启用状态；不由新前端调用 | AUTH-007 |
| `GET/POST /admin/directions` | 列表/创建可选方向 | AUTH-007 |
| `PATCH /admin/directions/{id}` | 修改名称或启用状态 | AUTH-007 |

`GET /admin/users` 的 `search` 去除首尾空白后最长 200 字符；空字符串等同未搜索。姓名、邮箱和学号使用大小写不敏感包含匹配，`%`、`_` 与反斜杠按普通文本转义；“管理员 / 学生 / 正常 / 待验证 / 已禁用”及对应英文枚举映射到角色或状态条件。`direction_id` 在分页前精确筛选一个技术组。过滤后的 `total` 与 `items` 使用同一条件，前端固定每页 20 条并通过 URL 保留 `direction_id`、`search`、`activity` 和 `page`；请求页超过 `total` 推导的末页时，页面规范化跳转到末页，API 本身继续返回明确分页响应。

管理员删除请求示例：

```json
{
  "reason": "账号所有者提出永久删除申请",
  "current_password": "administrator-current-password",
  "confirmation_email": "target@connect.hkust-gz.edu.cn",
  "backup_confirmed": true
}
```

`reason` 去空白后为 3～500 字符，`current_password` 最长 128 字符；`confirmation_email` 规范化后必须与目标账号一致，`backup_confirmed` 必须为 `true`。真实管理员且未开启学生视图才可调用，管理接口删除当前操作者返回 `409 STATE_CONFLICT` 并引导使用本人注销；错误密码为 `401 INVALID_CREDENTIALS`，邮箱/原因/备份确认为字段级 `400 VALIDATION_ERROR`，最后一名激活管理员为 409。近期、待验证与禁用目标不再因活跃度被拒绝。

成功 `204` 表示 PostgreSQL 中账号与个人数据已经提交删除、共享记录已去除归属、个人对象清理任务已可靠入队，不表示所有 MinIO 副本已经在响应前删除。响应和管理邮件任务列表不返回密码、确认邮箱、个人正文、对象键或 multipart ID；对象 Worker 最终失败通过运维积压/告警处理。共享记录响应中的 `created_by`、`submitted_by`、`granted_by`、`resolved_by` 等操作者 UUID 在账号擦除后允许为 `null`。

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

## 飞书培训知识库接口

| 方法与路径 | 行为 | 权限/需求 |
| --- | --- | --- |
| `GET /knowledge` | 返回最新成功快照元数据、目录节点和文档摘要；目录节点含 `document/folder/file/unsupported` 类型以及可空 `asset_id/file_size/mime_type`，无快照返回 `snapshot:null` 与空数组 | 登录，KB-001～KB-002、KB-005～KB-007 |
| `GET /knowledge/documents/{document_id}` | 只在最新成功快照中按内部 UUID 返回标题、原文 URL、同步时间和结构化块 | 登录，KB-002～KB-003、KB-005 |
| `GET /knowledge/assets/{asset_id}/content` | 验证资源被最新成功快照的文档资源关联或独立文件节点引用后，图片/白板跳转短时 inline URL，正文附件和目录文件跳转 attachment URL；知识库 PE 文件额外把签名响应强制为 `Content-Type: application/octet-stream` | 登录，KB-006～KB-008 |
| `GET /admin/knowledge` | 返回 `configured`、学生当前快照和最近运行的脱敏状态 | 真实管理员，KB-004～KB-005、KB-008 |
| `POST /admin/knowledge/sync` | CSRF 校验后创建同步运行、审计和 Outbox，返回 `202 {run}` | 真实管理员，KB-004～KB-005 |

目录和文档响应不返回飞书 app secret、tenant token、MinIO 对象键或飞书错误正文。目录独立文件只返回内部资源 UUID、安全标题、大小和媒体类型，不返回永久地址。文档既有结构化块 JSON 可包含图片块的可选纯文本 `caption`、`type=equation` 的独立公式块，以及富文本 segment 的 `equation=true` 行内公式标记；图片说明来自飞书 `image.caption.content`，移除空字符、限制 20,000 字符，纯空白时省略，不接受 HTML。LaTeX 只作为文本内容返回，不接受 HTML。文件型富文本 segment 使用 `file=true`，并可返回可空 `asset_id`、`file_name`、`file_size`、`mime_type` 和 `unavailable_reason`；块附件也可返回同一失败原因。`unavailable_reason` 只允许 `type_not_allowed`、`too_large`、`unavailable`，不得返回上游错误正文。媒体路径只接受内部 UUID，不接受对象键或任意 URL。

`source_url`、块内既有 `fallback_url` 与文件 segment 的安全 HTTPS `href` 继续作为快照来源/兼容元数据返回；真实学生和管理员学生视图不得把它们渲染为飞书原文或文件失败回退链接。成功本地化附件、富文本内嵌文件与 Drive 文件引用都通过 `GET /knowledge/assets/{asset_id}/content` 授权下载，并通过当前成功快照的文档资源关系取得授权。

稳定错误：未配置为 `503 KNOWLEDGE_SYNC_NOT_CONFIGURED`；已有进行中运行为 `409 KNOWLEDGE_SYNC_IN_PROGRESS`；文档或媒体不属于当前快照统一为 `404 RESOURCE_NOT_FOUND`；MinIO 签名失败为 `503 DEPENDENCY_UNAVAILABLE`。管理员学生视图调用管理接口返回 `403 FORBIDDEN`。

参考仓库提交 `c28f8a0` 的同步顺序和页面排布对齐属于 Service、Worker 与前端内部实现，不新增公开 API。首次上线前台初始化是仅接管唯一活动运行的内部运维命令；管理员 `POST /admin/knowledge/sync` 保持为后续更新的唯一产品写入口。

## 反馈答疑接口

全部反馈答疑接口要求有效 Session；本人接口按有效学生角色授权，公开答疑接口允许任一有效登录角色，管理接口只允许真实管理员且未开启学生视图。对应 HELP-001～HELP-008。

### 登录态匿名公开答疑

| 方法与路径 | 行为 | 需求 |
| --- | --- | --- |
| `GET /help-requests/public` | `page,page_size`；只分页返回已解决问题的匿名摘要 | HELP-007 |
| `GET /help-requests/public/{request_id}` | 只返回已解决问题的安全正文和最新答复；开放问题、系统反馈与不存在统一 404 | HELP-007 |

公开列表不查询 `users` 并复用不含提交者字段的 `HelpRequestPage`；详情使用独立最小响应 `PublicHelpRequestDetail`，不含提交者、通知 ID 或 Markdown 源文字段。匿名请求返回 401；公开可见性固定由 `request_type=question AND status=resolved` 派生，不接受类型、状态或作者筛选参数。

### 学生创建与读取

| 方法与路径 | 行为 | 需求 |
| --- | --- | --- |
| `GET /help-requests` | `type,status,page,page_size`；只分页返回本人创建的工单 | HELP-002 |
| `POST /help-requests` | 创建“系统反馈”或“问题答疑”工单，返回 `201` 详情 | HELP-001～HELP-002 |
| `GET /help-requests/{request_id}` | 只返回本人工单、安全正文、管理员处理结果和该工单当前未读提醒 ID；他人与不存在统一 404 | HELP-002 |

创建主体：

```json
{"request_type":"system_feedback","title":"移动端按钮无法使用","content_markdown":"## 复现步骤\\n..."}
```

`request_type` 只能为 `system_feedback` 或 `question`；标题 1～200 字符，详情 1～20,000 字符，均在去除首尾空白后校验。普通管理员视图调用学生接口返回 403；管理员学生视图按本人账号创建和读取。

### 管理员查看与处理

| 方法与路径 | 行为 | 需求 |
| --- | --- | --- |
| `GET /admin/help-requests` | `type,status,query,page,page_size`；返回全部工单和提交学生安全身份摘要 | HELP-003 |
| `GET /admin/help-requests/unread-count` | 只返回当前管理员本人 `help_request_created` 未读数量 `{count}`；静态路由先于 UUID 详情注册 | HELP-003、NEWS-005 |
| `GET /admin/help-requests/{request_id}` | 返回学生姓名、学号、学校邮箱、完整工单、当前答复和当前管理员本人对此工单的未读提醒 ID | HELP-003 |
| `PUT /admin/help-requests/{request_id}/resolution` | `{resolution_markdown,revision}`；首次答复或修订答复，原子写状态、审计和站内通知 | HELP-004～HELP-005 |
| `DELETE /admin/help-requests/{request_id}` | 锁定后物理删除工单、使相关未读解决提醒失效并写脱敏审计，返回 204 | HELP-008 |

答复请求：

```json
{"resolution_markdown":"已修复移动端按钮，请刷新后重试。","revision":1}
```

本人详情额外包含只属于当前学生、当前工单的未读解决提醒 `notification_ids`；管理员详情则只包含当前管理员、当前工单、`notification_type=help_request_created` 的未读 `notification_ids`，两者都用于调用既有单条已读接口且不返回通知事件键。学生创建工单时同事务为全部当前有效管理员生成固定脱敏标题的创建提醒；首次解决使该工单全部管理员未读创建提醒失效，修订不重复处理。管理员成功响应还包含 `request_type`、`status`、安全正文/答复、提交学生摘要、`resolved_by`、`resolved_at`、时间和 `revision`，不返回日志、通知内部事件键或其他学生工单。删除请求无主体，成功响应无正文；物理删除前把同一 `target_type=help_request,target_id=request_id` 的全部未读提醒标为已读，历史已读提醒继续保留。空答复返回 `400 VALIDATION_ERROR`，过期 revision 返回 `409 REVISION_CONFLICT`，不可见资源返回 `404 RESOURCE_NOT_FOUND`；学生和管理员学生视图调用管理接口返回 `403 FORBIDDEN`。

`POST /files/{file_id}/preview-url` 与下载端点使用相同 Session、CSRF 和业务关联授权，成功响应字段与下载一致。只有服务端 `detected_media_type` 与扩展名匹配的 PDF、PNG/JPEG/GIF/WebP、MP4/WebM，或已检测为 `text/plain` 的安全文本扩展名可预览；文本签名响应强制 `text/plain; charset=utf-8`。HTML、SVG、Office、压缩包、可执行文件、未知或不匹配类型返回 `415 FILE_PREVIEW_NOT_SUPPORTED`，授权失败仍按既有 404，不得借 415 探测不可见文件。
