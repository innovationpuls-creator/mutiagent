# OneTree Docker 最小生产基线设计

## 1. 目标

把 OneTree 从本地开发运行方式改造成可在单台公网 Linux 服务器安全部署、升级、诊断和恢复的生产系统。

完成后的系统必须满足：

- 数据库升级或应用发布失败时，可以恢复到发布前状态。
- 当前本地 PostgreSQL 全量数据和教材上传文件可以迁移到服务器。
- 容器更新不会删除数据库、教材文件、证书或部署备份。
- 危险的默认认证、跨域和演示账号配置不能进入生产环境。
- 每次提交自动验证后端、前端、API 契约和 Docker 构建。
- 每次部署后自动验证服务、数据库、HTTPS 和真实登录。
- 线上请求和故障可以通过 `request_id`、结构化日志和健康检查定位。
- 首次部署和后续更新都有一条命令入口，并提供完整中文部署文档。

## 2. 已确认的部署环境

- 操作系统：Ubuntu Server 24.04 LTS 64 位。
- CPU 架构：x86_64。
- 服务器资源：4 核 CPU、4 GB 内存、40 GB SSD。
- 服务器位于中国大陆广州并具有固定公网 IPv4。
- 服务器使用 root 账号通过 TAT/OrcaTerm 管理。
- 端口 `80` 和 `443` 可以开放。
- Docker 尚未安装，由首次部署脚本安装 Docker Engine 和 Docker Compose 插件。
- 部署源：公开 GitHub 仓库 `https://github.com/innovationpuls-creator/mutiagent.git` 的 `main` 分支。
- 生产域名：`onetree.chat` 和 `www.onetree.chat`。
- 域名注册人为个人，网站名称为“一棵树学习空间”。
- 网站用于比赛期间供少量参与者使用；新用户注册保持开放。
- 比赛结束后由管理员手动停止 Docker 服务，不增加自动下线功能。

## 3. 运维边界

- PostgreSQL 与前后端运行在同一台服务器。
- 不使用外部托管数据库、对象存储或外部告警渠道。
- 不做定时异地备份。
- 每次部署前必须生成本机数据库与教材文件备份，只保留最近 3 份。
- 管理员上传的教材原文件永久保留；备份轮转不能删除原文件。
- 本地日志保留 7 天。
- 部署更新允许几十秒维护时间。
- 自动部署后只验证服务、数据库和真实登录；完整学习流程由用户人工测试。

## 4. 容器架构

生产 Compose 项目包含以下服务：

### 4.1 `nginx`

- 唯一公网入口。
- 绑定主机端口 `80` 和 `443`。
- 提供前端静态产物。
- 将 `/api` 请求反向代理到 `backend`。
- 提供 ACME HTTP-01 challenge 目录。
- HTTP 请求自动跳转到 HTTPS。
- 为登录和注册接口实施请求频率限制。
- 设置基础安全响应头和上传大小限制。
- 维护期间返回明确的维护页面。

### 4.2 `backend`

- 运行 FastAPI。
- 仅加入 Docker 内部网络，不发布主机端口。
- 通过内部服务名连接 PostgreSQL。
- 不在应用启动时创建、修改或删除数据库表。
- 提供 liveness、readiness 和登录烟雾测试接口所需能力。

### 4.3 `worker`

- 使用与 `backend` 相同的应用镜像。
- 独立执行教材解析、翻译和其他长时间任务。
- 任务状态持久化在 PostgreSQL。
- HTTP 请求只负责创建任务，不直接承担最长可达数百秒的任务执行。
- worker 重启后能够继续处理数据库中未完成的任务。

### 4.4 `postgres`

- 运行 PostgreSQL 15，与项目 README 声明的主版本一致。
- 只加入 Docker 内部网络，不发布 `5432` 到主机。
- 数据目录使用命名 volume。
- 配置健康检查。

### 4.5 `certbot`

- 使用 Certbot 5.4 或更高版本。
- 通过 webroot HTTP-01 方式申请和续期证书。
- 证书目录和 ACME 账户目录使用持久化 volume。

### 4.6 一次性任务

- `migrate`：执行 Alembic 数据库迁移。
- `smoke`：执行服务、数据库、HTTPS 和真实登录检查。
- `backup`：生成部署前数据库与教材快照。
- `restore`：从指定部署快照恢复数据库与教材文件。

## 5. 持久化数据

必须创建并保护以下持久化存储：

- PostgreSQL 数据 volume。
- 教材上传文件 volume，对应当前 `backend/.codex-artifacts/knowledge-base-uploads`。
- Let’s Encrypt 证书与 ACME 账户 volume。
- 部署备份目录。
- 持久化 systemd journal，统一接收 Docker 容器日志。

普通部署、停止和启动命令不得调用 `docker compose down -v`，也不得删除任何上述 volume。

## 6. 首次数据迁移

### 6.1 本地导出

本地导出脚本必须：

1. 从当前项目配置读取准确的数据库连接，不推断数据库名、用户或端口。
2. 使用 PostgreSQL 自带工具生成可校验的全量数据库 dump。
3. 打包当前教材上传目录的全部文件。
4. 生成包含文件大小与 SHA-256 的清单。
5. 生成单一迁移包，供用户通过 OrcaTerm 拖拽或 SFTP 上传到服务器 `/root`。

迁移包不包含 LLM API Key、JWT 密钥或服务器生成的 PostgreSQL 密码。

### 6.2 服务器导入

首次部署脚本必须：

1. 校验迁移包清单与 SHA-256。
2. 创建 PostgreSQL volume 和教材 volume。
3. 恢复数据库 dump。
4. 恢复全部教材文件并保持原文件名和层级。
5. 执行 Alembic 版本检查与必要迁移。
6. 验证管理员账号以及 `18771701100`、`18771701111` 记录仍存在。
7. 使用用户提供的真实登录凭证执行登录烟雾测试。

脚本不得在仓库或日志中记录用户密码。

## 7. 数据库版本管理与恢复

- 引入 Alembic 作为唯一生产数据库迁移入口。
- 为当前生产模型建立明确的初始基线版本。
- 将现有 `schema_upgrades.py` 中仍需保留的升级操作转换为有版本号的迁移。
- FastAPI 启动不得执行 `SQLModel.metadata.create_all`、手写 schema upgrade 或删表操作。
- 部署脚本必须在迁移前进入维护状态并生成数据库与教材备份。
- Alembic 迁移成功后才能启动新版本应用。
- 迁移失败时停止发布并保持旧版本不可写，随后恢复部署前数据库备份和旧应用版本。
- 新版本健康检查或登录烟雾测试失败时，恢复旧容器；如果本次迁移已经改变数据库，同时恢复部署前数据库与教材快照。
- 每份备份必须包含时间、Git commit、Alembic revision、数据库 dump、教材快照和 SHA-256 清单。
- 轮转逻辑只保留最近 3 份完整备份。

## 8. 生产安全配置

### 8.1 自动生成的密钥

首次部署交互式脚本只要求用户填写：

- `LLM_API_KEY`
- `LLM_MODEL`
- `LETSENCRYPT_EMAIL`
- 首次部署时的迁移包路径
- 用于登录烟雾测试的现有账号和密码

脚本自动生成：

- PostgreSQL 强随机密码。
- JWT HS256 强随机签名密钥。

`LLM_BASE_URL` 固定为：

`https://dashscope.aliyuncs.com/compatible-mode/v1`

生产 secrets 文件：

- 由 root 创建。
- 权限为 `0600`。
- 不进入 Git。
- 不打印到部署日志。

### 8.2 后端强校验

- 生产环境缺少 `JWT_SECRET`、`DATABASE_URL`、`LLM_API_KEY`、`LLM_MODEL` 或允许来源配置时必须拒绝启动。
- 生产环境禁止使用固定 JWT 后备值。
- 生产环境禁止自动创建固定 demo 账号。
- 开发和测试环境仍可使用显式的开发配置，但行为必须由准确的环境值控制。

### 8.3 网络边界

- UFW 只开放 `80/tcp` 和 `443/tcp`。
- PostgreSQL 与 FastAPI 不绑定公网端口。
- CORS 仅允许 `https://onetree.chat`、`https://www.onetree.chat` 和明确配置的公网 IP HTTPS origin。
- nginx 对登录和注册路由设置独立限流区。
- 上传请求设置与项目需求一致的明确最大体积。

## 9. HTTPS 证书自动化

### 9.1 管理对象

必须同时管理：

- `onetree.chat` 与 `www.onetree.chat` 的域名证书。
- 服务器固定公网 IPv4 的可信 IP 证书。

域名正常上线后仍保留公网 IP HTTPS 访问与 IP 证书续期。

### 9.2 首次签发

1. nginx 先使用仅支持 HTTP challenge 的 bootstrap 配置启动。
2. 部署脚本验证端口 `80`、`443`、域名解析和 Certbot 版本。
3. 先使用 Let’s Encrypt staging 环境验证签发链路。
4. staging 成功后申请正式域名证书。
5. 使用 Certbot `shortlived` profile 和 `--ip-address` 申请正式 IP 证书。
6. 校验证书链、SAN、私钥匹配关系和有效期。
7. 校验成功后原子切换 nginx 正式 HTTPS 配置。

### 9.3 续期

部署脚本创建：

- `onetree-cert-renew.service`
- `onetree-cert-renew.timer`

定时器每天运行两次：

1. 执行 `certbot renew`。
2. 对续期后的域名和 IP 证书执行链、SAN、私钥和有效期检查。
3. 只有校验成功才执行 nginx reload。
4. reload 失败时保持当前 nginx 进程和旧证书继续服务。
5. 失败写入 systemd journal 和部署日志，后续定时任务继续重试。

### 9.4 HTTPS 验证

每日自动验证：

- 域名证书剩余有效期。
- IP 证书剩余有效期。
- TLS 握手。
- SAN 匹配。
- HTTP 到 HTTPS 跳转。
- nginx 当前加载证书的序列号与磁盘证书一致。

不接入外部通知渠道，只在本地日志记录结果。

## 10. 健康检查与日志

### 10.1 健康接口

- `/api/health/live`：只证明 FastAPI 进程可响应。
- `/api/health/ready`：执行真实 PostgreSQL 查询，并检查应用所需 schema revision。
- 原有 `/api/health` 不再固定返回数据库已连接；它应兼容地返回真实 readiness 结果或被明确弃用。

### 10.2 请求追踪

- nginx 接收或生成 `X-Request-ID` 并传递给 FastAPI。
- FastAPI 中间件验证或生成 request ID。
- 响应头返回同一个 `X-Request-ID`。
- 结构化日志至少包含时间、级别、服务、request ID、方法、路径、状态码和耗时。
- 后台任务日志包含 job ID、任务类型、状态和关联 request ID。
- 日志不得记录密码、JWT、LLM API Key、数据库密码或教材正文。

### 10.3 运行策略

- 应用容器使用 `restart: unless-stopped`。
- Docker 使用 `journald` logging driver；systemd journal 设置 `MaxRetentionSec=7day` 和 `SystemMaxUse=2G`，保证日志最多保留 7 天且不会无限占用 40 GB 磁盘。
- 不接入短信、邮件、企业微信或其他主动告警。

## 11. CI 质量门禁

GitHub Actions 必须在 pull request 和 `main` push 上执行：

### 11.1 后端

- `uv run ruff check`
- `uv run ruff format --check`
- 使用独立 PostgreSQL service container 运行全量 `uv run pytest`
- 验证 Alembic 可以从空数据库升级到 head。
- 验证当前 schema 可以被 Alembic 识别为 head。

### 11.2 前端

- `npx biome check`
- `npm test`
- `npm run build`
- 重新执行 `npm run gen:api` 后验证 `frontend/openapi.json` 与 `frontend/src/types/api.ts` 没有 Git diff。

### 11.3 容器与烟雾测试

- 构建所有生产镜像。
- 启动生产等价 Compose 测试栈。
- 验证 liveness、readiness、前端首页和登录。
- CI 不调用真实 LLM API，不执行完整学习路径生成。

必须修复当前后端全量测试创建过多 PostgreSQL schema 并触发 `max_locks_per_transaction` 耗尽的问题，使全量 CI 可以稳定结束。

## 12. 部署流程

### 12.1 首次部署

服务器执行一条 bootstrap 命令，随后进入交互式引导。bootstrap 负责：

1. 验证 Ubuntu 24.04 x86_64 和 root 权限。
2. 安装 Docker Engine、Docker Compose、Git、curl、openssl 和必要系统工具。
3. 创建 4 GB swap 并持久化到 `/etc/fstab`。
4. 配置 UFW，只开放 `80`、`443`。
5. 克隆公开仓库 `main` 到 `/opt/onetree`。
6. 生成生产 secrets。
7. 校验并导入 `/root` 下的迁移包。
8. 创建部署前基线备份。
9. 构建镜像、迁移数据库、启动服务。
10. 申请证书并切换 HTTPS。
11. 执行服务、数据库、HTTPS 和真实登录烟雾测试。
12. 输出最终访问地址和常用运维命令。

### 12.2 后续更新

固定命令 `/opt/onetree/bin/deploy`：

1. 获取 `origin/main` 最新提交。
2. 记录当前 Git commit、镜像和 Alembic revision。
3. 生成部署前完整备份。
4. 构建新镜像。
5. 切换维护页并停止写入。
6. 执行 Alembic migration。
7. 启动新版本。
8. 执行服务、数据库、HTTPS 和真实登录烟雾测试。
9. 成功后恢复正常流量并轮转旧备份。
10. 失败时执行回滚并返回非零退出码。

### 12.3 回滚

提供明确的 `/opt/onetree/bin/rollback <backup-id>` 命令。回滚必须：

- 验证备份清单。
- 进入维护状态。
- 停止应用写入。
- 恢复指定数据库 dump 和教材快照。
- 恢复对应 Git commit 和镜像。
- 启动旧版本并执行 readiness 与登录检查。
- 验证成功后才恢复流量。

## 13. 部署文档

中文部署文档必须覆盖：

- 域名、ICP备案和 DNS 前置条件。
- 本地数据导出。
- OrcaTerm 拖拽、SFTP 和 scp 三种迁移包上传方式。
- 首次一条命令部署。
- 交互式配置字段。
- 后续一条命令更新。
- 查看服务状态和 7 天日志。
- 手动停止与重新启动比赛网站。
- 查看证书签发与续期状态。
- 手动触发证书续期测试。
- 查看当前数据库 revision。
- 数据库和教材恢复。
- 指定备份回滚。
- 磁盘空间检查与备份轮转。
- 常见故障及准确诊断命令。
- 备案成功后在页面底部展示备案号并链接工信部备案网站。

## 14. 验收标准

只有以下证据全部成立才视为达到最小生产基线：

1. 干净 Ubuntu 24.04 x86_64 服务器可以从一条 bootstrap 命令完成部署。
2. 当前本地数据库和教材文件迁移后，管理员和指定现有账号记录存在且真实登录成功。
3. PostgreSQL、FastAPI 端口无法从公网直接访问。
4. 域名和固定公网 IP 均可通过可信 HTTPS 访问。
5. HTTP 自动跳转 HTTPS。
6. 手动运行证书续期测试成功，nginx 无中断 reload。
7. FastAPI 在生产密钥缺失或使用禁止的默认值时拒绝启动。
8. 生产环境不会自动创建 demo 账号。
9. readiness 在数据库断开时失败，在数据库恢复后成功。
10. 请求响应和日志包含同一 request ID，且日志不包含 secrets。
11. 模拟迁移失败时旧数据保持可恢复，发布返回失败。
12. 模拟新版本健康检查失败时自动恢复旧容器和部署前数据。
13. Docker 容器重建后数据库、教材、证书和备份仍存在。
14. 全量 CI 后端、前端、API drift、Docker build 和烟雾测试全部通过。
15. 完整中文部署、更新、停止、日志、续期和恢复文档可按步骤执行。
