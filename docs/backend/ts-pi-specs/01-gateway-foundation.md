# M1 开发文档：TS 编排网关骨架、跨服务协议与鉴权基础设施

> 文档日期：2026-11-27  
> 对应里程碑：M1（无前置依赖）  
> 上位文档：`docs/backend/ts-pi-agent-redesign.md`、`docs/backend/ts-pi-specs/00-roadmap-and-milestones.md`

---

## 1. 目标范围与前置依赖

### 1.1 目标范围
M1 搭建 OneTree 新一代 TypeScript AI 编排网关（`ai-gateway/`）的基础运行底座，打通 **前端 ↔ 代理层（Vite / Nginx）↔ TS 编排网关 ↔ Python 业务核心** 的双向通信、身份鉴权、链路追踪、SSE 协议适配与统一错误码契约，为 M2（个人 Pi 模型配置）及后续所有 Agent 迁移提供稳固基座。

### 1.2 不在 M1 范围内
- 不迁移任何业务 Agent 逻辑（对话仍由既有 Python 后端处理，直到 M4 切流）。
- 不新增业务数据库表（模型配置表属于 M2）。
- 不修改生产环境的实际线上配置（M1 仅完成模板与本地开发代理对齐，生产切换在 M9 统一验收）。

---

## 2. 现有源码盘点与必须兼容的边界约束

精读 M1 清单内全部源码后，识别出 **6 条必须严格兼容的既有约束与隐藏坑点**：

1. **本地开发直连 8000 绕过 Vite 代理的坑点**（`frontend/src/api/http.ts`）
   - 现状：`getBrowserApiBaseUrl()` 在 `localhost` / `127.0.0.1` 下直接拼接 `http://127.0.0.1:8000`，导致浏览器请求完全绕过了 `frontend/vite.config.ts` 中配置的 `/api` 代理。
   - 约束与改造：M1 必须修正本地开发环境的请求基址策略——在浏览器开发模式下默认走同源相对路径（由 Vite 5173 按路径分流至 Python 8000 与 TS 网关 8100），测试环境与显式 `VITE_API_BASE_URL` 保持原逻辑不受影响。
2. **JWT 鉴权与前端自动登出强契约**（`backend/app/core/security.py`、`frontend/src/api/http.ts`）
   - 现状：JWT 固定使用 `HS256`，签名密钥为 `JWT_SECRET`（开发环境默认值 `mutiagent-dev-secret-key-change-in-production`），载荷 `sub` 存 `user.uid`，有效期 2 小时。
   - 强契约：前端 `notifyAuthInvalidFromError()` 仅在 **HTTP 状态码为 401 且响应体 `detail` 严格等于 `"无效的认证凭证"`** 时，才派发 `mutiagent-auth-invalid` 事件触发退出登录。TS 网关 JWT 校验失败必须严格返回完全一致的状态码与文案。
   - 账号封禁态核验：Python 侧解码 JWT 后会查库确认用户存在（401 `"用户不存在"`）且 `is_active == True`（403 `"账号已被禁用"`）。TS 网关不直连数据库，必须在调用 Python 内部接口或专用身份核验接口时完成封禁态校验。
3. **请求 ID 透传与 JSON 访问日志规范**（`backend/app/core/observability.py`、`deploy/nginx/nginx.conf`）
   - 现状：全链路请求头统一为 `X-Request-ID`，合法格式为 `^[A-Za-z0-9._:-]{1,128}$`，缺失或非法时生成 32 位小写十六进制 UUID；Nginx 会隐藏上游重复头并统一回写 `$response_request_id`。
   - 约束：TS 网关必须实现完全一致的 `X-Request-ID` 解析与回写中间件，调用 Python 内部接口时原样透传该请求头，并输出同字段结构的 JSON 访问日志（`service` 标识为 `onetree-ai-gateway`）。
4. **Nginx 维护模式与 SSE 缓冲控制**（`deploy/nginx/conf.d/production.conf.template`、`backend/app/api/orchestration.py`）
   - 现状：Nginx 全局 `proxy_read_timeout` 为 300 秒，且所有 `/api` 路由均挂接 `$maintenance_marker` 503 维护拦截；SSE 禁用缓冲依赖上游响应头 `X-Accel-Buffering: no`。
   - 约束：TS 网关所有 SSE 路由必须固定返回 `Content-Type: text/event-stream; charset=utf-8`、`Cache-Control: no-cache`、`X-Accel-Buffering: no`；Nginx 后续新增指向 TS 网关的 `location` 必须保留相同的维护模式拦截与 `X-Request-ID` 透传。
5. **前端既有 SSE 事件协议强契约**（`frontend/src/api/orchestration.ts`）
   - 现状：前端 `parseSseChunk` 严格按 `\n\n` 分帧、解析 `event: <name>` 与 `data: <json>`，仅识别 11 种事件名：`session_started`、`supervisor_thinking`、`supervisor_plan`、`agent_calling`、`agent_progress`、`agent_result`、`text_chunk`、`data_update`、`message_completed`、`session_completed`、`error`。
   - 特殊映射：旧后端将 `text_chunk`、`supervisor_thinking`、`supervisor_plan` 包在 `event: message` 且 `payload.type` 填真实事件名，前端对此已做归一化。TS 网关 SSE 适配器需严格沿用该输出规范，确保前端零改动即可消费。
6. **会话持久化消息格式兼容**（`frontend/src/api/orchestration.ts`）
   - 现状：前端恢复历史会话时，按 `{ type: "human" | "ai", data: { content: "..." } }` 解析持久化消息数组。后续 M4 通过 Python 内部接口写入会话消息时，必须保持该存储结构不变。

---

## 3. 业务模块设计与核心流转

### 3.1 `ai-gateway/` 工程骨架与模块划分
TS 编排网关作为项目根目录下的独立 TypeScript 服务（要求 Node 22.19+，默认监听端口 `8100`），在 M1 阶段落成以下 6 个基础模块：

1. **配置加载与环境校验模块**
   - 统一读取并校验环境变量：`APP_ENV`、`PORT`（默认 `8100`）、`JWT_SECRET`、`PYTHON_BACKEND_URL`（默认指向本机 `8000` 端口）、`INTERNAL_API_TOKEN`、`ALLOWED_ORIGINS`。
   - 生产环境启动强校验：缺少 `JWT_SECRET`、`INTERNAL_API_TOKEN`、`PYTHON_BACKEND_URL`，或 `JWT_SECRET` 仍为开发默认值时，拒绝启动并明确报错（与 Python 侧 `config.py` 保持同等安全底线）。
2. **可观测性中间件（Request ID + 结构化日志）**
   - 请求进入时解析或生成 `X-Request-ID`，挂载到当前异步请求上下文（`AsyncLocalStorage`），并在响应头回写。
   - 请求结束时统一输出单行 JSON 访问日志，字段对齐 Python 后端：`timestamp`、`level`、`service`（`onetree-ai-gateway`）、`request_id`、`method`、`path`、`status_code`、`duration_ms`、`message`。
3. **对外用户鉴权中间件（JWT + 账号状态核验）**
   - 提取 `Authorization: Bearer <token>`，使用与 Python 后端一致的 `HS256` + `JWT_SECRET` 验签并提取 `sub`（`user_uid`）。
   - 验签失败或过期：直接返回 `401` + `{"detail": "无效的认证凭证"}`。
   - 验签通过后，通过内部后端客户端校验用户是否存在及 `is_active`（支持极短周期内存缓存或随业务上下文接口合并校验），封禁用户返回 `403` + `{"detail": "账号已被禁用"}`。
4. **Python 内部客户端（跨服务安全调用）**
   - 封装对 Python 后端 `/internal/*` 接口的统一 HTTP 调用层：自动注入内部鉴权头 `X-Internal-Token`、自动从异步上下文透传 `X-Request-ID`、统一超时控制与结构化错误映射。
   - 区分“业务错误（4xx，原样透传语义）”与“内部通信故障（超时/5xx，映射为可恢复网关错误）”。
5. **SSE 流式协议适配器**
   - 封装统一的 SSE 响应流构建器，固定写入防缓冲响应头，提供按既有 11 种事件名输出帧的标准方法（自动处理 `text_chunk` / `supervisor_thinking` / `supervisor_plan` 的 `event: message` 包装与心跳保活，防止长推理期间代理断流）。
6. **统一业务错误码体系**
   - 在保持既有 `detail` 字段完全兼容的前提下，扩展结构化错误字段 `error_code`（及可选引导字段 `action`），涵盖两类核心场景：
     - **HTTP JSON 错误**：保留 `detail` 供旧逻辑提示，新增 `error_code` 供前端精准分支处理。
     - **SSE `error` 事件**：保留 `message`、`recoverable`、`retryable`，新增 `error_code`、`provider`（如 OAuth 过期时指明哪个厂商）。

### 3.2 跨服务安全通信与双向鉴权机制

| 调用方向 | 路径前缀 | 鉴权方式 | 防护边界 |
|---|---|---|---|
| 前端 → TS 网关 | `/api/ai/*`（及后续切流的 `/api/chat/message`、`/api/branch/canopy/report/stream`、`/api/forest/ai/stream` 等） | `Authorization: Bearer <JWT>` | 校验签名、有效期与账号启用态 |
| TS 网关 → Python 后端 | `/internal/*` | `X-Internal-Token: <共享密钥>` | 常量时间比对；仅限内网/容器网络可达，Nginx 外网禁止转发 `/internal` |
| Python 后端 → TS 网关（M2 热失效、M8 知识库 AI） | `/internal/*` | `X-Internal-Token: <共享密钥>` | 同样使用常量时间比对；外网不可达 |

---

## 4. 跨服务接口、路由分流与错误码契约

### 4.1 M1 新增端点清单

| 服务 | 端点 | 用途 | 鉴权要求 |
|---|---|---|---|
| **TS 网关** | `GET /api/ai/health/live` | 网关存活探针，返回 `{"status": "ok"}` | 无 |
| **TS 网关** | `GET /api/ai/health/ready` | 网关就绪探针，探测 Python 内部连通性并返回依赖状态（异常返回 503） | 无 |
| **TS 网关** | `GET /api/ai/ping-auth`（M1 验收探针） | 验证 JWT 验签 + 调用 Python 内部用户核验 + 请求 ID 透传全链路 | Bearer JWT |
| **Python 后端** | `GET /internal/health` | 供 TS 网关就绪检查校验内部令牌与数据库连通性 | `X-Internal-Token` |
| **Python 后端** | `GET /internal/users/{user_uid}/auth-status` | 返回用户存在性、角色与 `is_active` 状态 | `X-Internal-Token` |

### 4.2 统一错误码契约（M1 落地定义，前端与双端共用）

| `error_code` | 典型 HTTP 状态码 | 业务含义 | 前端统一处理动作 |
|---|---|---|---|
| `AUTH_INVALID` | 401（`detail` 固定 `"无效的认证凭证"`） | JWT 无效或过期 | 触发既有自动登出事件 |
| `ACCOUNT_DISABLED` | 403 | 账号已被禁用 | 提示联系管理员 |
| `MODEL_NOT_CONFIGURED` | 428 / SSE `error` | 用户尚未配置可用的个人模型 | 弹出明确提示并提供一键跳转「模型配置」按钮 |
| `MODEL_OAUTH_EXPIRED` | 401 / SSE `error` | 个人绑定的某 Provider OAuth 授权失效 | 提示对应厂商授权过期，提供“重新登录”跳转 |
| `MODEL_CAPABILITY_MISMATCH` | 422 | 所选模型不满足场景能力要求（如无视觉能力） | 提示更换支持对应能力的模型 |
| `INTERNAL_SERVICE_UNAVAILABLE` | 503 | TS 网关与 Python 内部通信失败 | 提示服务暂时不可用，可重试 |

### 4.3 路由分流规划（Vite 本地代理 & Nginx 生产模板）

- **M1 立即生效的分流**：
  - `/api/ai/` 前缀（健康检查、后续 M2 模型配置运行时探针与 OAuth 回调）→ 转发至 TS 网关（本地 `8100` 端口，生产容器 `ai-gateway:8100`）。
  - 其余所有 `/api/` 路径 → 继续转发至 Python 后端（`8000` 端口），保证既有功能 100% 不受影响。
  - 显式拦截外网对 `/internal/` 的访问（Nginx 返回 404）。
- **后续里程碑渐进切流清单（预留路由，暂不切流）**：
  - M4 切流：`POST /api/chat/message`
  - M8 切流：`POST /api/forest/ai/stream`、`POST /api/branch/canopy/report/stream`

---

## 5. 风险点与回滚/灰度方案

1. **本地开发代理改动影响既有前端测试**
   - 风险：修改 `frontend/src/api/http.ts` 让浏览器开发态走同源代理时，可能影响 Vitest 单元测试或 Playwright 真实后端测试（端口 `8001`）。
   - 缓解：保留 `NODE_ENV === "test"` 与显式 `VITE_API_BASE_URL` 的最高优先级，仅将 `localhost / 127.0.0.1` 无显式环境变量时的默认回退改为同源相对路径 `""`。
2. **双服务 JWT 密钥或内部令牌不一致**
   - 风险：开发或部署时两边 `.env` 漏配导致鉴权大面积 401/403。
   - 缓解：在 `ai-gateway/.env.example` 与 `backend/.env.example` 明确对齐变量名；开发环境提供统一的开发默认内部令牌并打印警告，生产环境强制非空校验，缺配直接拒绝启动。
3. **无侵入灰度与一键回滚**
   - M1 仅承接新增的 `/api/ai/*` 路径，不触碰任何既有学生/管理端业务接口。如遇异常，停掉 `ai-gateway` 进程即可完全回退，对既有系统零影响。

---

## 6. M1 可执行验收清单

全部 8 项验收场景必须逐一通过并留存运行结果，方可视为 M1 达成：

| 编号 | 验收维度 | 具体验证步骤 | 预期达成结果 |
|---|---|---|---|
| **AC-1** | 网关独立启动与存活检查 | 启动 `ai-gateway`（`8100` 端口），请求 `GET /api/ai/health/live` | 返回 `200` 及 `{"status": "ok"}`；响应头包含合法 `X-Request-ID`；控制台输出标准 JSON 访问日志（`service = onetree-ai-gateway`）。 |
| **AC-2** | 就绪检查与依赖探测 | ① Python 后端正常运行时请求 `GET /api/ai/health/ready`<br>② 停止 Python 后端或配错内部令牌后再请求 | ① 返回 `200`，标注 `backend: "connected"`<br>② 返回 `503`，标注 `backend: "unavailable"`，不崩溃、不泄露敏感令牌。 |
| **AC-3** | Python 内部接口令牌防护 | ① 不带 `X-Internal-Token` 直接请求 Python `GET /internal/health`<br>② 带错误令牌请求<br>③ 带正确令牌请求 | ①、② 均被拒绝（`401` 或 `403`）<br>③ 返回 `200` 且日志记录对应 `X-Request-ID`。 |
| **AC-4** | Vite 代理分流与 JWT 鉴权 | 通过前端 `5173` 端口访问 `/api/ai/ping-auth`：<br>① 不带或带伪造/过期 JWT<br>② 带有效启用账号 JWT<br>③ 带已禁用账号 JWT | ① 返回 `401` 且 `detail` 严格等于 `"无效的认证凭证"`<br>② 返回 `200` 与当前 `user_uid` / `role`<br>③ 返回 `403` 且 `detail` 等于 `"账号已被禁用"`。 |
| **AC-5** | 跨服务 Request ID 全链路透传 | 发送请求携带自定义 `X-Request-ID: m1-trace-001` 访问 `/api/ai/ping-auth` | 响应头回传 `m1-trace-001`；`ai-gateway` 与 `mutiagent-backend` 双方 JSON 访问日志中均可检索到同一 `m1-trace-001`。 |
| **AC-6** | SSE 协议适配器兼容性 | 针对网关 SSE 适配器运行单元测试，覆盖 11 种事件名、防缓冲响应头与 `text_chunk`/`supervisor_thinking`/`supervisor_plan` 的 `event: message` 包装 | 输出帧可被前端 `orchestration.ts` 的 `parseSseChunk` 100% 无损解析。 |
| **AC-7** | 统一错误码前端识别 | 在前端 `http.ts` / `orchestration.ts` 单元测试中模拟返回 `MODEL_NOT_CONFIGURED` 与 `MODEL_OAUTH_EXPIRED`（含 HTTP 与 SSE 两种载体） | 前端错误解析工具可准确提取 `error_code` 与 `provider`，同时不破坏原有 `AUTH_INVALID` 自动登出逻辑。 |
| **AC-8** | 既有套件回归无破坏 | 运行 `ai-gateway` 单元测试与类型检查、`backend` 受影响测试、`frontend` 单元测试与 `npm run build` | 三端测试与构建全部通过，既有 `/api/*` 登录与业务流程不受任何影响。 |
