# TS 编排网关重构：进度记录

> 约定：只记录**重要完成节点**（里程碑启动、模块落地、验收项实测通过/失败、阻塞与决策）。每个节点附日期、证据（命令与结果）与未完成/未验证项。
> 总纲：`00-roadmap-and-milestones.md`；当前里程碑文档：`01-gateway-foundation.md`。

## 执行模式（用户 2026-11-27 指定）
目标：M2 起逐个推进至 M9，每个里程碑按「源码精读 → 对照 0X 文档实现 → 逐项验收 → 写本文档 → 自动 git commit（不 push、不开 PR）」闭环；遇到不确定的事停下询问；不得越过用户的「停下」指令；失败如实记录。

## M1：TS 网关骨架、跨服务协议与鉴权基础设施

状态：**已完成并提交**（AC-8 中 nginx docker 实机段本机未能执行）

### 已确认的决策（2026-11-27）
| 决策 | 结论 |
|---|---|
| 网关框架 | Hono（`@hono/node-server`），JWT 用 `jose` |
| Nginx 模板 | M1 内修改：`/api/ai/` → `ai-gateway:8100`（resolver + 变量惰性解析，网关未部署时 nginx 仍可启动）、`/internal/` 返回 404 |
| Python 生产环境缺 `INTERNAL_API_TOKEN` | 不阻止启动，`/internal/*` 一律 403 拒绝（fail closed）；M9 再改为必填 |
| 验证数据隔离 | 联调使用独立 Postgres schema，不写用户本机开发库的业务数据 |

### 完成节点
| 日期 | 节点 | 证据 | 备注 |
|---|---|---|---|
| 2026-11-27 | 只读检查完成：两份规格、总纲 `ts-pi-agent-redesign.md` 与 M1 必读源码已读 | — | 本机有 Postgres(5432)，无 docker/nginx |
| 2026-11-27 | `ai-gateway/` 源码与单测落地（配置、请求 ID/JSON 日志、错误码、JWT 鉴权、内部令牌、Python 客户端、SSE 适配器） | `npx tsc --noEmit` 通过；`npx vitest run` 5 个文件 30 个测试全部通过 | 已在 AC-1~5 真实联调中验证 |
| 2026-11-27 | SSE 黄金夹具 `ai-gateway/test/fixtures/sse-contract.txt` 生成，网关侧逐字节比对通过 | 同上 | 前端侧解析测试已通过（AC-6） |
| 2026-11-27 | Python `/internal/health`、`/internal/users/{uid}/auth-status` 与令牌防护落地 | `ruff check`、`ruff format --check` 通过；`pytest` 6 个相关文件 47 个测试通过 | 全量 backend pytest 936 通过 |
| 2026-11-27 | Nginx `production.conf.template` 增加 `/api/ai/` 与 `/internal/`；`test_nginx_config.sh` 增加断言 | 脚本静态断言段通过；docker 段因本机无 docker 无法执行 | **未在真实 nginx 中验证** |
| 2026-11-27 | 前端：错误码解析（HTTP/SSE）、`parseSseChunk` 导出、Vite `/api/ai` 分流、开发态改走同源相对路径 | 代码已写、diff 已审阅；e2e 路由匹配 `**/api/**` 不受影响 | `biome`/`vitest` 288/`tsc -b`/`npm run build` 全部通过 |

### 验收清单实测结果（2026-11-27）
联调环境：Python 后端 8000（独立 schema `m1_acceptance`，测完已删除）+ ai-gateway 8100（`tsx`）+ Vite 5173。

| 编号 | 结果 | 实测证据 |
|---|---|---|
| AC-1 | 通过 | `GET :8100/api/ai/health/live` → 200 `{"status":"ok"}`，响应头 `x-request-id` 为 32 位 hex；网关输出 JSON 访问日志，`service=onetree-ai-gateway` |
| AC-2 | 通过 | 后端正常：200 `{"status":"ok","backend":"connected"}`；网关配错内部令牌：503 `{"status":"error","backend":"unavailable"}`；停掉后端：同样 503；网关进程未崩溃，日志与响应均不含令牌 |
| AC-3 | 通过 | Python `/internal/health`：无令牌 401「缺少内部令牌」、错令牌 403「内部令牌无效」、正确令牌 200；后端 JSON 日志分别记录 `ac3-a/b/c` 请求 ID |
| AC-4 | 通过 | 经 Vite `:5173/api/ai/ping-auth`：无令牌、伪造密钥、过期令牌均 401 且 `detail` 为「无效的认证凭证」；有效账号 200 返回 `user_uid`/`role=student`；禁用账号 403「账号已被禁用」 |
| AC-5 | 通过 | 请求带 `X-Request-ID: m1-trace-001`：响应头回传同值；网关日志（`/api/ai/ping-auth`）与 `mutiagent-backend` 日志（`/internal/users/.../auth-status`）均含 `m1-trace-001` |
| AC-6 | 通过 | `ai-gateway` 单测覆盖 11 种事件名、防缓冲响应头、`event: message` 包装、心跳；黄金夹具逐字节一致；前端 `orchestration.sse-contract.test.ts` 用真实 `parseSseChunk` 解析同一夹具通过 |
| AC-7 | 通过 | 前端 `errorCodes.test.ts`：HTTP 428 `MODEL_NOT_CONFIGURED`、401 `MODEL_OAUTH_EXPIRED`（含 `provider`）及 SSE `error` 事件均可提取；仅 401+`无效的认证凭证` 触发自动登出 |
| AC-8 | 部分通过 | ai-gateway：`tsc --noEmit`、`npm run build`、`vitest` 30/30 通过；backend：`ruff check`/`format --check` 通过，全量 `pytest` 936 通过；frontend：`biome` 无错误（118 条为既有警告）、`vitest` 51 文件 288 通过、`tsc -b` + `npm run build` 通过。**未执行**：`deploy/tests/test_nginx_config.sh` 的 docker/nginx 实机段（本机无 docker），仅静态断言段通过；Playwright e2e 未运行（e2e 路由匹配 `**/api/**`，分析上不受影响） |

### 已知遗留 / 风险
- Nginx 新增的 `/api/ai/`、`/internal/` 配置未经真实 nginx 加载校验，建议在有 docker 的环境跑 `deploy/tests/test_nginx_config.sh`。
- 生产 compose 尚无 `ai-gateway` 服务、生产环境未配置 `INTERNAL_API_TOKEN`（均按计划留到 M9）。
- 网关 `/api/ai/ping-auth` 每次请求都调用 Python 校验用户状态，未加缓存（M1 刻意从简）。
