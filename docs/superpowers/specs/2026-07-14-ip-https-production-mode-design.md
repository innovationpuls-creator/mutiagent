# IP HTTPS 生产模式设计

## 背景

服务器位于中国大陆，`onetree.chat` 和 `www.onetree.chat` 尚未完成 ICP 备案。腾讯云当前拦截域名 HTTP 请求，Let's Encrypt 的域名 HTTP-01 校验无法到达 OneTree Nginx。

本阶段只保证公网 IP `1.12.69.26` 的 HTTPS 可用。备案通过后，再恢复现有的域名与 IP 双证书生产模式。

## 目标

- 一键部署只申请 Let's Encrypt 短期 IP 证书 `onetree-ip`。
- 部署完成后通过 `https://1.12.69.26` 访问 OneTree。
- systemd 定时任务自动续期并验证 IP 证书。
- 自动验收只检查服务、数据库和登录。
- 保留现有数据库、账户、管理员、用户和管理员上传的教材文件。
- 保留现有域名双证书能力，备案通过后可以切回。

## 非目标

- 本阶段不保证 `onetree.chat` 或 `www.onetree.chat` 可用。
- 不修改业务前端、业务后端、数据库结构或用户数据。
- 不增加备份策略、使用上限或额外的 Docker 停止功能。

## 设计

### Nginx 模式

新增精确模式名 `production-ip`，对应独立模板 `deploy/nginx/conf.d/production-ip.conf.template`。

该模板包含：

- 端口 80 上的 IP ACME HTTP-01 路径。
- 其余 IP HTTP 请求重定向到 `https://1.12.69.26`。
- 端口 443 只加载 `/etc/letsencrypt/live/onetree-ip/fullchain.pem` 和 `privkey.pem`。
- 与现有生产模板相同的安全响应头、接口限流、维护模式和反向代理规则。
- 域名请求不作为当前生产入口。

Compose 的 Nginx 启动校验明确允许 `bootstrap`、`production-ip` 和 `production` 三个值，不接受其他值。

### 证书申请

`deploy/bin/cert-issue` 接收精确参数 `ip` 或 `all`：

- `ip`：只执行 `onetree-ip` 的 staging dry-run、正式签发和证书验证。
- `all`：保持现有域名与 IP 双证书流程，供备案通过后使用。
- 未提供参数时按 `all` 处理，保持现有脚本兼容性。

Bootstrap 在当前一键部署流程中显式执行 `cert-issue ip`。证书成功后，将 `.env.production` 的 `NGINX_CONFIG_MODE` 写为 `production-ip`，重建 Nginx，然后运行 smoke 检查。

### 自动续期

`deploy/bin/cert-renew` 从 `.env.production` 读取 `NGINX_CONFIG_MODE`：

- `production-ip`：续期后只验证 `onetree-ip`，重载 Nginx，并核对线上 IP 证书序列号。
- `production`：保持现有逻辑，同时验证域名和 IP 证书。
- 其他值：立即失败，不重载 Nginx。

现有 systemd service 和每天两次的 timer 不改变。

### 失败处理

- IP 证书签发或验证失败时，不切换到 `production-ip`。
- Nginx 配置检查失败时，不执行重载。
- 证书续期或验证失败时，定时任务返回失败并保留当前正在服务的配置。
- 所有失败路径都不删除数据库卷、教材卷或已有账户。

## 测试与验收

自动测试覆盖：

- `cert-issue ip` 不发起域名证书请求。
- `cert-issue all` 保持双证书行为。
- `cert-renew` 在两种生产模式下只验证对应证书。
- `production-ip` Nginx 模板只引用 `onetree-ip`。
- Compose 接受 `production-ip`，拒绝其他未知模式。
- Bootstrap 依次执行 IP 证书签发、切换 `production-ip`、Nginx 重建和 smoke 检查。

服务器验收标准：

- PostgreSQL、backend、worker、certbot、nginx 均为 healthy。
- `https://1.12.69.26` 返回前端页面。
- `/api/health/live` 和 `/api/health/ready` 成功。
- 指定账户登录成功，且 `/api/auth/me` 成功。
- `onetree-cert-renew.timer` 已启用。
- `cert-verify onetree-ip` 成功。
