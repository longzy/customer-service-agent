# 安全策略

## 支持的版本

项目处于 M1 阶段，只维护 `main` 分支的最新提交。

## 报告漏洞

请不要在公开 Issue 中披露漏洞细节。将复现步骤、影响范围与建议修复发送给仓库 owner（见 [CODEOWNERS](.github/CODEOWNERS)），并在 48 小时内确认收到。

## 安全基线

完整规则见 [工程标准第 4 节](docs/process/standards.md)。摘要：

- 身份与租户只从认证上下文获取，请求正文出现身份字段即拒绝。
- 非本机环境的会话 Cookie 必须 `Secure` + `HttpOnly` + `SameSite=Lax`，并使用 `__Host-` 前缀。
- 写操作必须有 CSRF 策略；管理端点独立鉴权且默认不挂载。
- 密钥只存在于环境变量；仓库与 CI 开启 secret scanning 与 push protection。
- 日志、审计与评测夹具不得包含密钥、令牌、完整支付信息与超范围个人信息。
- 依赖审计与 SAST 无高危才可合并。

## 本地开发注意

- `.env` 不入库；请从 `.env.example` 复制并填入本地密钥。
- 测试账号登录只在 `ENVIRONMENT=development` 或 `test` 下启用。
- Mock OMS 与 `/_admin` 故障注入接口仅用于开发与测试，不得暴露到共享环境。
