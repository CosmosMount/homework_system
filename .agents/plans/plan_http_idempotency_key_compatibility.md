# 局域网 HTTP 幂等键兼容修复计划

## 问题背景与本质原因

- 管理员在作业编辑页点击“发布 / 安排发布”后只看到“操作失败，请稍后重试”，后端没有收到对应发布请求。
- 作业草稿的创建与保存请求均成功，发布接口和后端受众快照逻辑可用；失败发生在浏览器构造请求头阶段。
- 多个客户端组件直接调用 `crypto.randomUUID()` 生成 `Idempotency-Key`。该方法只在安全上下文（HTTPS 或 localhost）中保证可用，当前局域网 HTTP 验收地址不提供它，因此调用会在请求发出前抛出异常。

## 现有结构与可复用能力

- `frontend/lib/` 已承载共享的浏览器端基础能力，适合增加单一幂等键生成函数。
- 后端发布接口、CSRF 客户端、幂等约束和统一错误处理无需改变。
- 浏览器 Web Crypto 的 `getRandomValues()` 可在当前目标浏览器的非安全上下文中生成高熵随机字节，并可按 UUID v4 位布局编码。

## 必要修改

1. 在 `frontend/lib/` 增加共享幂等键生成工具：优先使用 `crypto.randomUUID()`，缺失时使用 `crypto.getRandomValues()` 生成符合 UUID v4 结构的键；不使用 `Math.random()` 降级。
2. 作业发布、通知发布/更新提醒、个人/团队正式版本提交、上传初始化与上传完成统一使用该工具。
3. 增加管理员作业发布回归测试，模拟 `crypto.randomUUID` 不存在，证明保存后仍会发送带合法 `Idempotency-Key` 的发布请求。
4. 增加工具级测试，固定随机字节验证 UUID v4 版本位、变体位和格式，并保留原生 `randomUUID()` 优先路径。

## 影响与不修改范围

- 对应需求为 HW-002、HW-003，并同时消除 NEWS-003、SUB-002、FILE-002～FILE-004 的同类客户端故障风险。
- 不改变 API 路径、请求/响应结构、权限、后端业务规则或数据库结构，不需要 Alembic 迁移。
- 服务端 `frontend/proxy.ts` 的 CSP nonce 运行于 Node.js 安全运行时，不属于局域网浏览器兼容问题，本任务不改动。
- 若 Web Crypto 整体不可用，工具显式失败，不以低熵伪随机数伪造幂等键；项目支持的现代浏览器均提供 `getRandomValues()`。

## 验证与上线

1. 运行新增回归及完整 Frontend Vitest。
2. 运行 ESLint、严格 TypeScript 和 Next.js 生产构建。
3. 重新构建并替换 Frontend 容器，确认六个常驻服务健康。
4. 通过局域网 HTTP 验收作业发布：发布请求到达后端且草稿进入预期的 `published` 或定时状态，不再出现仅保存成功但发布请求缺失的情况。
5. 更新测试策略、变更记录、当前任务、完成记录和项目基线。

## 实施结果

- 已新增共享幂等键工具，并替换作业/通知发布、正式版本和上传流程中的浏览器直接 `randomUUID()` 调用；服务端 CSP nonce 保持不变。
- 原生 UUID、`getRandomValues()` UUID v4 降级、拒绝低熵随机及管理员作业发布回归均通过。
- 完整前端结果为 14 个测试文件、40 项测试、ESLint、严格 TypeScript、主机与容器生产构建通过。
- Frontend 已重新构建、替换并健康，Nginx 已重启；六个常驻服务健康，5000 端口作业编辑页和发布 API 路由正常。
- 真实局域网 Chromium 验证 `isSecureContext=false`、`randomUUID=undefined`、`getRandomValues=function`，与修复针对的运行条件一致。
- 无 API、权限、后端、数据库或迁移变更；测试和匿名运行探测未修改目标作业状态。

