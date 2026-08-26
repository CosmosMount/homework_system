# 当前任务

## 状态

已完成：Markdown 展示统一、蓝白圆角主题换肤、纯白背景与共享布局视觉细化、管理员命令栏统一、侧边栏导航及 CI 类型检查修复。

## 完成内容

- 管理员作业编辑页保留 Markdown 源文本框，保存后的说明通过与用户详情相同的安全 HTML 渲染展示，不暴露内部实现标签。
- 全局切换为蓝白配色，使用纯白页面背景、浅蓝交互表面、蓝色主操作、蓝灰边框、圆角控件/容器和柔和层次阴影。
- 富文本预览补充标题、列表、链接、表格、代码块和引用样式，继续通过 `SafeHtml` 呈现，不新增前端 Markdown 解析器。
- 增加管理员页面回归测试，覆盖预览结构、作业入口、个人资料保存和登录人员视图。

## 验证结果

- 前端 14 个测试文件、43 项测试通过；ESLint、严格 TypeScript 和 Next.js 生产构建通过。
- Frontend 已重建并替换，Nginx 已重启；`/health/live`、`/health/ready`、`/health/worker` 和 `/nginx-health` 均返回 200。
- 匿名访问 `/api/v1/auth/admin/sessions` 返回 401；本次未修改业务 API、权限、数据库或迁移。

## 本次追加：按钮视觉优化

- 主操作按钮改为浅蓝底深蓝字，统一圆角、阴影和悬停反馈；保留深蓝状态标签以维持对比度。
- 学生端筛选/上传，以及管理员新建通知、新建作业、新建赛事入口接入共享按钮样式。
- 管理员创建入口增加加号图标和清晰的按钮语义。
- 管理员通知、作业和赛事列表页统一复用紧凑命令栏，创建链接使用浅蓝 `h-9`/`rounded-lg` 按钮样式，表单主按钮保持原有尺寸。
- 修复 `test_auth_login.py` 的 `AuthenticatedContext` 测试类型标注，以及 `test_notifications.py` 的 `RecordingSender` 属性推断；不改变运行时逻辑。

## 本轮验证结果

- 后端定向认证/通知测试 14 项、严格 Mypy（127 个源文件）、Ruff 检查与格式检查通过。
- 前端 14 个测试文件 42 项测试、ESLint、严格 TypeScript 和 Next.js 生产构建通过。

## 本次追加：侧边栏与统一 Markdown 展示

- 顶部横向导航改为响应式侧边栏：桌面端可折叠，移动端使用抽屉入口；管理员和学生共享布局组件并保持各自的权限入口。
- Markdown 源文本仅在编辑表单中可见；通知、作业、赛事和提交详情统一展示服务端清洗后的安全 HTML，管理员编辑区与学生详情复用同一渲染组件。
- 删除编辑区中的内部实现标签和预览标题，保留必要的“保存后可查看内容”状态提示。

## 本轮验证结果

- 前端 14 个测试文件、43 项测试通过；ESLint、严格 TypeScript 和 Next.js 生产构建通过。

## 本次追加：作业源码默认收起

- 管理员作业编辑页对已有安全 HTML 的作业先展示渲染结果，Markdown 源文改为通过“编辑 Markdown 源文”按需展开；新建或尚未生成 HTML 的草稿仍默认显示编辑框。
- 用户详情页和管理员已保存内容继续复用同一 `RenderedMarkdown`/`SafeHtml` 渲染路径，未修改 API、权限或数据结构。

## 本轮验证结果

- 管理员界面回归测试 7 项、完整前端 14 个测试文件 43 项测试、ESLint、严格 TypeScript 和 Next.js 生产构建均通过。
- Frontend 镜像已重建并替换，Frontend 与 Nginx 已重启；Backend、Worker、PostgreSQL、MinIO 保持健康。
- `/health/live`、`/health/ready`、`/health/worker`、`/nginx-health` 均返回 200；匿名访问 `/admin/assignments/new` 正确重定向到 `/login`。

## 本次追加：纯白背景与整体 UI 优化

- 页面根背景和 HTML 根节点改为纯白，移除网格/径向渐变，避免影响通知、作业与 Markdown 阅读。
- 调整蓝灰色令牌、浅蓝主按钮、输入焦点环、卡片阴影、侧栏和认证页圆角，统一页面层级并保持管理员与学生共用布局。
- 参考 `../management_system` 的轻边框、白色表面和紧凑层次，不修改业务 API、权限、数据库或 Markdown 清洗。

## 本轮验证结果

- 前端 14 个测试文件、47 项测试、ESLint、严格 TypeScript 和 Next.js 生产构建通过。
- Frontend 已重建并替换，Frontend/Nginx 已重启；六个 Compose 服务健康，/health/live、/health/ready、/health/worker、/nginx-health 和 5000 端口登录页均返回 200。


## 本次追加：共享布局与视觉层次细化

- 共享侧栏改用首字母圆角导航图标与 active 卡片状态，底部增加姓名和有效角色身份卡；退出、学生视图、个人资料和登录设备入口统一触控尺寸与交互反馈。
- 认证页增加白色圆角表单卡片和 PNX 品牌标识；面板、输入控件、标题排版与滚动条细节统一为纯白背景下的蓝白视觉层次。
- 不修改 API、权限、数据库、Markdown 清洗或业务状态机。

## 本轮验证结果

- 前端 14 个测试文件、47 项测试、ESLint、严格 TypeScript 和 Next.js 生产构建通过。
- Frontend/Nginx 已重建重启；Backend、Worker、PostgreSQL、MinIO、Frontend 和 Nginx 六个 Compose 服务健康，健康端点与 5000 端口登录页均返回 200。

## 正式计划

- .agents/plans/plan_markdown_preview_blue_white_theme.md
- .agents/plans/plan_button_visual_polish.md
- .agents/plans/plan_sidebar_markdown_rendering.md
- .agents/plans/plan_assignment_editor_visibility.md
- .agents/plans/plan_admin_student_view.md
- .agents/plans/plan_ui_visual_refinement.md

## 本次追加：赛事公告与组队简化

- 新赛事仅保留校内赛公告、报名、建队和邀请码组队；管理员与学生页面移除赛题创建、编辑、列表和提交入口。
- 发布赛事不再要求至少存在一个赛题；保留历史赛题表和 API 作为兼容路径，不做数据库迁移或删除。
- 新增后端无赛题发布测试和学生公告型赛事详情回归测试；同步产品、页面、API、架构、数据库、测试、决策和变更文档。

## 验证结果

- 后端完整测试 130 项、Ruff、格式检查、严格 Mypy（127 个源文件）通过。
- 前端完整测试 14 个文件/45 项、ESLint、严格 TypeScript、Next.js 生产构建通过。
- Backend、Worker、Frontend 已重建并重启，Nginx 随后重启；`/health/live`、`/health/ready`、`/health/worker`、`/nginx-health` 均返回 200。
- 5000 端口匿名赛事与管理员入口均正确进入登录守卫；旧赛题路径不暴露受保护内容。

## 状态

已完成：校内赛赛事已收敛为公告、报名和组队流程。

## 本次追加：管理员临时学生视图

- 管理员可在当前 Session 通过侧栏切换为学生视图并操作学生工作台；关闭后回到管理员工作台，真实 `users.role` 不变。
- 学生视图使用 `sessions.student_view` 和有效角色授权；管理 API（含登录人员、用户、通知、作业、赛事管理）由后端拒绝，学生通知/作业/赛事/个人提交/上传按学生权限执行。
- 其他管理员将账号真实降为 `student` 时撤销该用户全部 Session，本人重新登录后不能通过学生视图按钮恢复管理员权限。
- 新增 `20260826_0008` 可回滚迁移、认证/用户管理和前端侧栏回归测试，并同步需求、页面、架构、API、数据库、测试、决策和变更文档。

## 当前状态

已完成：实现、定向与完整质量门、迁移应用、镜像重建、服务重启和 5000 端口健康验收均通过。

## 本次追加：管理员学生视图作业受众预览

- 修复管理员开启学生视图后作业列表为空：发布时受众快照只包含普通学生，唯一管理员不会被写入快照。
- 学生视图现按管理员账号当前届次/方向在服务端临时预览已发布作业；普通学生仍使用固定快照。提交、上传、优秀作业及附件下载共用该预览授权。
- 预览不写入受众快照、站内通知、邮件或统计数据。

## 本轮验证结果

- 后端 135 项测试、Ruff、格式检查和严格 Mypy 通过；新增作业受众预览回归。
- 运行数据库确认唯一管理员、已发布作业及受众快照数量；待重建镜像后再做运行态 API 验收。
