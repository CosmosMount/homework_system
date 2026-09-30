# 允许备用域名访问但保留主链接

## 背景

当前运行实例的 `APP_BASE_URL` 仍是主链接 `http://10.4.150.222:5000`。新增备用域名后，后端虽然接受了该 Host，但 Origin 校验仍只接受 `APP_BASE_URL`，导致从 `https://pnx-tutorial.demonmaster.cn` 登录返回 `CSRF_FAILED`。

## 目标与影响

- 增加显式的可信 CSRF Origin 配置，允许管理员指定备用 HTTPS 域名。
- 保持 `APP_BASE_URL` 不变，邮件和系统生成链接继续使用主链接。
- 继续执行精确 Origin 匹配，不放宽为任意来源或通配符。

## 实现范围

- Settings 增加 `CSRF_TRUSTED_ORIGINS` 解析与格式校验，并将其与 `APP_BASE_URL` 合并为同源校验白名单。
- Docker Compose 和环境示例透传该变量；当前 `.env` 只加入 `https://pnx-tutorial.demonmaster.cn`。
- 增加配置契约测试，更新部署网络文档。

## 验证

- 运行配置与定向后端测试。
- 重建 Backend、Worker，检查健康状态。
- 使用备用域名携带 `Origin` 请求登录接口，确认不再返回 `CSRF_FAILED`，错误账号应返回正常认证错误。
