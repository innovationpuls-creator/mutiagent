# OneTree Docker 生产部署

本文档用于当前生产环境：Ubuntu Server 24.04 LTS x86_64、root、服务器公网 IP `1.12.69.26`、域名 `onetree.chat` 和 `www.onetree.chat`。

首次部署只有一个服务器命令。脚本会安装 Docker、配置国内回退源、导入现有数据库和教材、生成数据库/JWT 密钥、申请 HTTPS 证书，并检查服务、数据库和真实登录。

## 1. 部署前确认

执行部署前确认以下条件已经成立：

- `onetree.chat` 和 `www.onetree.chat` 的 A 记录都解析到 `1.12.69.26`。
- 腾讯云安全组允许公网访问 `80/tcp` 和 `443/tcp`。
- 域名实名认证已经完成；ICP备案状态按腾讯云要求处理。
- 本地 `backend/.env` 精确包含当前可用的 `DATABASE_URL`。
- 本地 PostgreSQL 18 的 `pg_dump`、`pg_restore` 和 `psql` 可用。

## 2. 本地导出数据库和教材

在本机项目根目录执行：

```bash
cd /Users/torch/torch/opt/mutiagent
./deploy/bin/export-local-data "$HOME/Desktop/onetree-migration.tar.gz"
./deploy/bin/verify-bundle "$HOME/Desktop/onetree-migration.tar.gz"
```

导出包包含当前数据库、`backend/.codex-artifacts/knowledge-base-uploads` 下的全部教材文件和 SHA-256 清单，不包含 LLM API Key、JWT 密钥或服务器数据库密码。

## 3. 上传迁移包

目标路径固定使用：

```text
/root/onetree-migration.tar.gz
```

OrcaTerm 可使用任一方式：

1. 将本地 `onetree-migration.tar.gz` 拖入终端窗口，上传后移动或重命名到上述路径。
2. 在 OrcaTerm 的文件管理/SFTP 面板上传到 `/root`。
3. 本地支持 SSH 时执行：

```bash
scp "$HOME/Desktop/onetree-migration.tar.gz" root@1.12.69.26:/root/onetree-migration.tar.gz
```

在服务器确认文件存在：

```bash
ls -lh /root/onetree-migration.tar.gz
```

## 4. 服务器一条命令部署

在服务器 root 终端完整执行这一行：

```bash
curl -fL --retry 5 --connect-timeout 10 https://raw.githubusercontent.com/innovationpuls-creator/mutiagent/main/deploy/bin/bootstrap -o /root/onetree-bootstrap && chmod 700 /root/onetree-bootstrap && /root/onetree-bootstrap
```

脚本依次询问六项内容：

1. `LLM API key`：实际使用的阿里百炼 API Key，输入时不回显。
2. `LLM model`：实际使用且已经验证可用的模型标识符。
3. `Let's Encrypt email`：证书到期通知邮箱。
4. `Migration bundle path`：填写 `/root/onetree-migration.tar.gz`。
5. `Smoke account`：填写用于部署检查的现有账号 `18771701100` 或 `18771701111`。
6. `Smoke password`：上一步账号的真实密码，输入时不回显。

数据库密码、JWT 密钥和维护检查 token 由脚本自动生成，不需要填写。生产配置保存到 `/opt/onetree/.env.production`，权限为 `0600`。

若 `/opt/onetree/bin/deploy` 已存在，说明首次部署已经完成，后续更新只使用该命令，不要重新导入迁移包。若首次部署中途失败且该命令尚不存在，重新执行同一条 bootstrap 命令；脚本会复用已生成的数据库和 JWT 密钥、停止未完成部署的业务容器，再从原迁移包安全重试。

成功后访问：

- `https://onetree.chat`
- `https://www.onetree.chat`
- `https://1.12.69.26`

## 5. 部署后检查

自动检查只覆盖服务、数据库、首页、HTTPS 和真实登录。完整学习流程继续人工测试。

```bash
docker compose --env-file /opt/onetree/.env.production -f /opt/onetree/deploy/compose.production.yml ps
curl -fsS https://onetree.chat/api/health/live
curl -fsS https://onetree.chat/api/health/ready
curl -I http://onetree.chat
curl -I https://onetree.chat
```

`http://onetree.chat` 应返回 HTTPS 跳转，live 和 ready 均应成功。

## 6. 后续一条命令更新

```bash
/opt/onetree/bin/deploy
```

该命令获取 `origin/main`、构建新镜像、进入维护状态、停止业务写入、创建数据库与教材备份、执行 Alembic migration，并在 smoke 成功后恢复流量。失败时保持维护状态并自动恢复旧提交、旧镜像；已经执行 migration 时同时恢复同一个备份。

## 7. 查看状态和最近 7 天日志

```bash
docker compose --env-file /opt/onetree/.env.production -f /opt/onetree/deploy/compose.production.yml ps
docker compose --env-file /opt/onetree/.env.production -f /opt/onetree/deploy/compose.production.yml logs --since 168h --tail 300
journalctl -u onetree-cert-renew.service --since "7 days ago" --no-pager
```

只查看单个服务时，在 `logs` 命令末尾添加精确服务名：`nginx`、`backend`、`worker`、`postgres` 或 `certbot`。

## 8. 比赛期间停止和重新启动

停止 Docker 服务：

```bash
systemctl stop docker.service docker.socket
```

重新启动：

```bash
systemctl start docker.service
docker compose --env-file /opt/onetree/.env.production -f /opt/onetree/deploy/compose.production.yml ps
```

不要执行 `docker compose down -v`，也不要删除 `postgres_data`、`textbook_uploads`、`letsencrypt` 或 `acme_webroot` volume。

## 9. HTTPS 证书和自动续期

续期定时器每天 `03:00` 和 `15:00` 检查一次：

```bash
systemctl status onetree-cert-renew.timer --no-pager
systemctl list-timers onetree-cert-renew.timer --all
```

手动触发一次续期和校验：

```bash
systemctl start onetree-cert-renew.service
systemctl status onetree-cert-renew.service --no-pager
journalctl -u onetree-cert-renew.service -n 200 --no-pager
```

单独校验证书：

```bash
cd /opt/onetree
./deploy/bin/cert-verify onetree-domain
./deploy/bin/cert-verify onetree-ip
```

脚本会检查完整证书链、SAN、私钥匹配、剩余有效期，以及 nginx 在线证书序列号。

## 10. 数据库 revision

```bash
docker compose --env-file /opt/onetree/.env.production -f /opt/onetree/deploy/compose.production.yml exec -T backend alembic current
```

生产数据库升级只通过 Alembic 和部署脚本执行，不在容器启动时建表或改表。

## 11. 备份、恢复和回滚

每次部署前会在 `/opt/onetree/backups` 创建数据库与教材完整快照，只保留最近 3 份完整备份。教材原文件保存在 Docker volume 中，备份轮转不会删除原文件。

列出备份 ID：

```bash
find /opt/onetree/backups -mindepth 1 -maxdepth 1 -type d -printf '%f\n' | sort -r
```

回滚命令契约为：

```text
/opt/onetree/bin/rollback <backup-id>
```

将 `<backup-id>` 替换为上一条命令列出的完整 ID。rollback 会校验清单、进入维护状态、停止写入、恢复对应数据库和教材、切回备份记录的 Git 提交，最后再次执行真实登录 smoke。

## 12. 磁盘检查

```bash
df -h / /opt/onetree
du -sh /opt/onetree/backups
docker system df
```

不要手工删除正在使用的 Docker volume。备份目录由发布脚本自动轮转为最近 3 份。

## 13. 常见故障定位

Docker 未启动：

```bash
systemctl status docker --no-pager
journalctl -u docker -n 200 --no-pager
```

域名或证书签发失败：

```bash
getent ahostsv4 onetree.chat
getent ahostsv4 www.onetree.chat
ufw status verbose
ss -lntp | grep -E ':(80|443)\b'
```

两个域名都必须显示 `1.12.69.26`，且服务器和腾讯云安全组都允许 `80/tcp`、`443/tcp`。

服务不健康或页面返回错误：

```bash
docker compose --env-file /opt/onetree/.env.production -f /opt/onetree/deploy/compose.production.yml ps
docker compose --env-file /opt/onetree/.env.production -f /opt/onetree/deploy/compose.production.yml logs --tail 300 nginx backend worker postgres
curl -i https://onetree.chat/api/health/ready
```

确认生产配置权限，不要输出文件内容：

```bash
stat -c '%a %U:%G %n' /opt/onetree/.env.production
```

正确结果是 root 持有且权限 `600`。
