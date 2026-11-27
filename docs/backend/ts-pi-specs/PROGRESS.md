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

## M2：个人 Pi 模型配置后端、加密存储与 Provider 运行时

状态：**已完成并提交**（AC-1~7 在真实 Postgres + Python + 网关上联调通过；OAuth 厂商为 mock，见「未验证项」）

### 已确认的决策 / 与文档的偏差（2026-11-27）
| 项 | 结论 |
|---|---|
| OAuth 方案 | 经用户确认：**复用 Pi 自带登录流程**（`models.login`）。网关发起并返回 `auth_url`/`device_code`，前端粘贴授权码提交 `/complete`；Pi 的本地回调服务仅在浏览器与网关同机时生效。`state` 为网关随机一次性值，绑定 `user_uid`，10 分钟过期。**偏差**：未实现文档中的网关自生成 state/PKCE 与 `GET /api/ai/oauth/callback`；新增 `GET /api/ai/oauth/{provider}/status`。 |
| 续期并发 | 进程内 per(user,provider) 互斥 + Python 行锁 compare-and-swap（refresh token 指纹）；冲突时采用库中已更新的凭据 |
| 加密 | Fernet，密钥由 `MODEL_SECRET_ENCRYPTION_KEY` 派生；生产环境缺密钥**在使用时返回 503（fail closed）**，开发环境使用默认密钥并告警 |
| 能力标签 | Pi 目录无「工具调用」标志，内置模型一律按 `tools=true`；自定义模型使用用户填写的标签 |
| 回退链 | 429 / 5xx / 超时 / 网络错误 → 切下一个候选；OAuth 失败 → `MODEL_OAUTH_EXPIRED`（含 provider）；其他 4xx → 502 不回退。存在回退链时默认 `maxRetries=0` 以快速切换 |
| 内置 Provider | 不允许添加自定义模型（422）；自定义模型仅属于自定义 Provider |
| 迁移 | `0007` 的外键仅在 `user` 表存在时创建（兼容 `test_forest_submission_recovery` 的残缺库迁移用例） |

### 完成节点
| 日期 | 节点 | 证据 |
|---|---|---|
| 2026-11-27 | Python：4 张表 + 迁移 `0007`、`crypto`（加密/掩码）、`model_config_service`、`/api/model-config` 全套接口、`/internal/users/{uid}/model-runtime-config`、`oauth-refresh-lock`、`oauth-credential`、`model-usage` | `ruff check` / `format --check` 通过；`tests/test_model_config_api.py` 17 个、迁移用例通过 |
| 2026-11-27 | 网关：Pi 用户级 `Models` 构建（禁用网关环境变量取密钥）、场景解析、`ModelRuntime`（60s 缓存+失效、回退链、异步用量上报）、探针、OAuth 会话、`/api/ai/models/{catalog,probe,scene-check}`、`/api/ai/oauth/*`、`/internal/cache/invalidate-user-model-config`、`/internal/models/capabilities` | `tsc --noEmit`、`npm run build` 通过；`vitest` 7 文件 45 个全部通过（含 mock 上游与 mock OAuth 厂商） |
| 2026-11-27 | 修复：`0007` 外键导致 `test_recovery_migration_preserves_unknown_historical_version` 失败 | 全量 `pytest` 953 通过（需加载主仓库 `backend/.env` 的 LLM 变量，否则 `test_forest_api` 的 LLM 用例因无凭据失败，属环境问题与本里程碑无关） |

### 验收清单实测结果（2026-11-27）
联调环境：Python 后端 8000（独立 schema `m2_acceptance`，测完已删除）+ ai-gateway 8100（tsx 测试入口，注入 mock OAuth 厂商与「直接调用场景」的验收专用路由）+ mock OpenAI 兼容上游 9100（`/p429`、`/p500` 恒返回对应状态，`/ok` 成功并记录请求头）。脚本为 scratchpad 内一次性验收脚本，不入库。

| 编号 | 结果 | 实测证据 |
|---|---|---|
| AC-1 | 通过 | 迁移至 `0007`，4 张表齐全；库内 `secret_encrypted`/`headers_encrypted` 为 Fernet 密文（`gAAAA…`），不含明文 Key 与自定义头值；`GET /api/model-config` 仅返回掩码 `••••1234`，请求头值返回 `••••` |
| AC-2 | 通过 | 自定义 OpenAI 兼容 Provider + 自定义模型（Compat `maxTokensField=max_tokens`）：上游实收 `X-Relay-Tenant: acme-42`、`Authorization: Bearer …1234`，请求体含 `max_tokens`、不含 `max_completion_tokens` |
| AC-3 | 通过 | 把非视觉模型绑定到 `quiz_vision`：422 + `error_code=MODEL_CAPABILITY_MISMATCH`；换成视觉模型后保存 200 |
| AC-4 | 通过（mock 厂商） | ① 手动粘贴授权码：start 返回 `auth_url`，他人用 state 完成 → 400，本人完成 → 200 并加密落库（`oauth_status=authorized`），重放 → 400；② Token 过期后 5 个并发请求全部成功，**上游刷新仅 1 次**，库中过期时间已更新。**自动回调模式**未实测（依赖 Pi 本地回调服务与真实厂商，见未验证项） |
| AC-5 | 通过 | 非视觉模型：text/tools=ok、vision=skipped；视觉模型：三项 ok；均返回 `first_token_ms`；无效 Key：text=failed，原因「认证失败（401）…」，tools/vision 跳过，响应不含 Key |
| AC-6 | 通过 | ① 主模型 429、500 均无缝切到备用并成功（attempts 记录 `HTTP_429`/`HTTP_500` → 成功）；② `PATCH /api/model-config/quick-switch` 后未重启立即生效（relay → backup）；③ `/api/model-config/usage`：12 次请求、1400 tokens、成本 0.00126 USD，流水含失败行及错误码、耗时 |
| AC-7 | 通过 | 新账号 scene-check 与运行时均 428 + `MODEL_NOT_CONFIGURED`（`action=open_model_settings`），验证时进程环境含全局 `OPENAI_API_KEY` 亦不回退 |

### 未验证项 / 已知遗留
- **真实厂商 OAuth（Claude/ChatGPT/Copilot 等）**未实测：本机无厂商账号，OAuth 全链路使用 mock 厂商（登录、续期、CAS 均为真实代码路径）。自动回调模式与真实授权页跳转需有账号的环境验证。
- `GET /api/ai/models/catalog` 在联调中未单独对真实 Pi 内置目录断言字段，单测断言了 provider 数 > 5 与能力字段。
- 前端 OpenAPI 客户端未重新生成，模型配置页面属 M8；本里程碑未改前端。
- 网关尚未接入任何业务场景（M3 起）；`/_accept/complete` 仅存在于一次性验收入口，未进入代码库。

## M3：双端「模型配置」页面与工作区快捷切换器（前端）

状态：**已完成并提交**（AC-1~6 通过；真实触发引导的链路依赖 M4+，见「未验证项」）

### 实现要点与偏差（2026-11-27）
| 项 | 结论 |
|---|---|
| 页面复用 | 学生 `/settings/models`（`MainLayout` 内）与管理员 `/admin/models`（`AdminLayout` 菜单第 5 项）共用同一个 `ModelConfigPage`；数据按登录用户隔离；管理员高级模式额外显示「教材翻译」「公开教材搜书」 |
| 学生入口 | 个人下拉菜单中禁用的「偏好设置 · 暂不可用」替换为「模型配置」，未配置时菜单项与头像带红点（`needsSetup`） |
| 状态同步 | 新增 `ModelConfigContext`（登录后并行拉取 `/api/model-config` 与网关目录，供切换器/红点/引导共享）；无 Provider 时回落到默认值，对既有页面与测试无影响；对非法返回体做了形状校验 |
| 快捷切换器 | `ModelQuickSwitcher` 挂在全局 AI 对话面板输入区上方与 Forest 答疑栏；切换调用 `PATCH /api/model-config/quick-switch`（Python 侧同时让网关缓存失效） |
| 引导 | `ModelGuidanceCard`：`MODEL_NOT_CONFIGURED` → 直达模型配置页；`MODEL_OAUTH_EXPIRED` → 点名厂商并跳 `?reauth=<provider>` 自动弹出 OAuth 登录；挂接 AI 对话面板（`SessionStreamError`）与 Forest 答疑（`ForestSubmissionError` 新增 `errorCode/provider`） |
| 偏差 1 | 「自定义模型」仅能加在**自定义 Provider** 下（M2 决策：内置厂商模型来自 Pi 目录） |
| 偏差 2 | 温度/超时/重试/Prompt 缓存为**全局运行参数**（后端 `runtime_options` 为用户级，不是每场景一份）；回退链、模型、思考深度为每场景独立 |
| 偏差 3 | 回退链排序用「上移/移除」按钮而非拖拽 |
| 偏差 4 | OAuth 弹窗沿用 M2 的 Pi 登录流：展示授权链接 + 粘贴授权码/回调 URL，同时轮询状态以兼容自动回调；设备码厂商展示验证码 |
| 偏差 5 | 分段控件使用 `aria-pressed` 按钮组（`role="toolbar"`），以通过 biome a11y 规则 |
| API 类型 | `npm run gen:api` 已重新生成 `openapi.json`、`src/types/api.ts`（`api.ts` 仅新增 665 行；`openapi.json` 因格式化差异产生大 diff）；再次运行无新增差异 |

### 完成节点
| 日期 | 节点 | 证据 |
|---|---|---|
| 2026-11-27 | 新增 `api/modelConfig.ts`、`ModelConfigContext`、`ModelQuickSwitcher`、`ModelGuidanceCard`、设置页（Provider/自定义模型+Compat/OAuth 弹窗/场景槽位/探针/用量）、路由与菜单入口 | `tsc -b` 通过；`biome` 0 错误（新增文件仅有与既有基线同类的告警） |
| 2026-11-27 | 前端测试 | `vitest` 55 文件 **321** 个通过（M2 末为 288；新增 33，含 AI 对话面板两条引导用例） |

### 验收清单实测结果（2026-11-27）
联调环境：独立 schema `m3_acceptance`（测完已删除）+ Python 8000 + 网关 8100（真实 `server.ts`）+ mock OpenAI 兼容上游 9100 + Vite 5173；用内置浏览器驱动真实页面。

| 编号 | 结果 | 实测证据 |
|---|---|---|
| AC-1 | 通过 | 管理员菜单出现「模型配置 → /admin/models」且高亮；学生个人菜单进入 `/settings/models`；管理员账号初始为「未配置模型」，看不到学生保存的中转站（互不干扰）；管理员高级模式场景含「教材翻译」「公开教材搜书」，学生测试断言不含（单测 + 浏览器） |
| AC-2 | 通过 | 极简模式保存主力/视觉模型与「高」思考深度，刷新后回显一致（浏览器 + 单测）；高级模式视觉槽位中非视觉模型置灰并标注「（不支持图片输入）」（单测断言 `disabled` 与文案）；视觉模型下拉仅含视觉模型 |
| AC-3 | 通过（mock OAuth） | 新增自定义 Provider（Base URL 校验、Key 掩码回显不预填明文）、自定义模型含能力标签/参考单价/Compat（`supportsDeveloperRole=false`、`maxTokensField` 等）提交体正确，非法 Compat JSON 被前端拦截；探针经真实网关→mock 上游显示「文本 ✔ 94 ms / 工具调用 ✔ / 视觉理解 未声明」，失败时展示明确原因；OAuth 弹窗（授权链接、粘贴回调 URL 提取 `code`、轮询、Esc 关闭）单测通过。**真实厂商 OAuth 未实测** |
| AC-4 | 通过 | 全局 AI 对话面板中点击切换思考深度与模型：界面立即更新，`GET /api/model-config` 确认持久化为 `relay-vl` + `low`；Forest 答疑栏复用同一组件（单测）；刷新后保持 |
| AC-5 | 通过（请求层模拟） | 对话面板收到 428 `MODEL_NOT_CONFIGURED` 时弹出引导卡并链接 `/settings/models`（浏览器注入 428 + 单测）；`MODEL_OAUTH_EXPIRED` 点名厂商、链接 `?reauth=…`、且不触发自动登出（单测）；管理员链接指向 `/admin/models`。**说明**：现网对话仍走 Python 旧编排（M4 才切到网关），真实触发 428 要等 M4+ |
| AC-6 | 通过 | `npm run gen:api` 重跑无新增差异；`npm test` 321 通过；`npm run build` 成功；375/768/1280 三个视口无横向溢出（`scrollWidth == 视口宽`）；抽屉在 <640px 为底部弹层、768px 侧抽屉；Esc 关闭；`prefers-reduced-motion` 下取消过渡（页面本身无 framer-motion 动画）；修复了过程中发现的复选框被拉伸问题 |

### 未验证项 / 已知遗留
- Playwright e2e 未运行（新增的登录后拉取模型配置请求在 e2e 的 `**/api/**` 路由 mock 下返回形状不符时已被忽略，分析上不影响）。
- 管理端知识库「翻译/搜书」的引导挂接留到 M8（该链路本里程碑仍走旧后端）。
- 真实厂商 OAuth（含自动回调）、`prefers-reduced-motion` 的浏览器实机切换未单独实测。

## M4：主对话图骨架、入口分流、Supervisor 路由与画像采集

状态：**已完成并提交**（AC-1~7 通过；模型侧均为脚本化 mock 上游，见「未验证项」）

### 实现要点与偏差（2026-11-27）
| 项 | 结论 |
|---|---|
| 切流 | `POST /api/chat/message` 由网关接管（同路径、同鉴权、同 SSE 协议）：Vite 代理 `^/api/(ai(/\|$)\|chat/message(\?\|$))` 与 Nginx `location = /api/chat/message` 指向 `ai-gateway:8100`；`/api/chat/start`、`GET /api/chat/sessions/{id}` 仍在 Python。会话不存在/越权仍是 HTTP 404（流开始前预检），401/422 与旧路由语义一致 |
| 主图 | `@langchain/langgraph` `StateGraph`：`entry → supervisor → profile_agent \| legacy_bridge \| finalize`；节点流转全部用 `Command({goto, update})`；事件统一经 `config.writer` 写出，由路由转成 SSE 帧。`@langchain/langgraph@1.7.5`、`@earendil-works/pi-agent-core@1.6.1` |
| 入口分流 | 仅两种显式协议直通旧流水线：消息含 `[LEAF_RESOURCE_GENERATION]`、或 `session_state.pending_leaf_regeneration` 存在（旧会话里的 `[LEAF_REGEN_PENDING]` 标记由 Python 在读取时转成该字段）。**三个关键词拦截器不再经过主路径** |
| 3 阶段门禁 | `gatedToolNames()` 为纯函数：A 无完整画像（仅 `delegate_profile_agent`）；B 有画像无路径（+`delegate_learning_path_intake`、`get_student_progress_summary`）；C 有路径（+`get_learning_path`、`get_course_outline`、`delegate_course_knowledge`，有大纲再加 `delegate_course_resources`）。`collecting` 画像即使残留路径数据也不解锁后续阶段。模型即使幻觉调用未下发的工具，也只会得到「工具不存在」错误，不会越权 |
| 画像 Agent | `pi-agent-core` `Agent` + 两个工具 `ask_profile_question` / `save_student_profile`。落库对象全部由 `profileContract.ts` 确定性拼装（16 字段、`question_box`、`defaulted_fields`、`text`/`summary_text` 一致），模型只提供业务字段；单测里复刻了前端 `pickProfile` 校验 |
| 校验与自纠 | 保存时校验：年级 ∈ 大一~大四、16 字段非空非「未知」、核心字段（年级/专业/学习阶段/近期目标/每周时间/学习方式）不得标为默认、`use_defaults` 必须由学生本轮明确要求（`allowsDefaultFill`）；失败返回 `isError` 并由 Pi 循环自纠，**最多 2 次**，超出后走确定性兜底卡片（不报错、不落库非法年级）。`ask_profile_question` 若带入非法年级，会把年级清空并强制改为年级追问卡 |
| 会话状态 | 迁移 `0008_conversation_session_state`（JSONB，非空，默认 `{}`）；读取时「显式 `session_state` 优先，否则回退旧约定」（`learning_path_intake` 取最近一条、`pending_leaf_regeneration` 从最近 AI 文本标记解析），旧会话无需迁移数据。M4 只写入 `pending_profile_followup`；`learning_path_intake` / `pending_leaf_regeneration` 的显式写入分别留给 M5 / M7 |
| 内部接口 | `GET /internal/chat/sessions/{id}/context`（归属校验、历史去除结构化条目、未消化薄弱点拼接保留）、`POST …/turn`（先完整写入，失败则仅存用户消息；可带 `session_state` 补丁，`null` 删键）、`PUT /internal/students/{uid}/profile`（保留“改画像即清大纲”不变量）、`GET …/learning-overview`；另加过渡接口 `POST …/legacy-stream` |
| 持久化顺序 | `finalize` 节点先 `persistTurn` 再发 `message_completed` / `session_completed`；整体写入失败时只发 `error`，并兜底只存用户消息（不写空助手消息）。实测：收到 `message_completed` 的瞬间，库里已有 2 条消息 |
| 未配置模型 | 在 supervisor 之前解析「对话与画像」槽位；未配置则发 SSE `error`（`MODEL_NOT_CONFIGURED`，`action=open_model_settings`），**什么都不写**（包括用户消息，避免重试后重复），不请求上游 |
| 模型运行时 | `ModelRuntime.agentStream()`：为 Agent 提供按场景候选链回退的 `streamFn`——仅在**尚未输出任何内容**时回退（避免用户看到半截答案接另一个模型）；每次尝试都上报用量；OAuth 失败转 `MODEL_OAUTH_EXPIRED`。Agent 循环硬上限 8 轮 |
| 偏差 1 | Pi 1.6.1 自带 `@earendil-works/pi-schema`（`obj/str/arr/opt…`）作为工具参数 Schema（M1 已依赖），**未引入** `@sinclair/typebox`；能力等价 |
| 偏差 2 | **过渡桥接（M5–M7 前）**：尚未迁移的委派（`delegate_learning_path_intake` / `delegate_course_knowledge` / `delegate_course_resources`）与显式资源协议，把整轮交给 Python 旧流水线（`legacy-stream`，网关原样转发 SSE 帧、本轮不再自己落库）。这些轮次仍使用服务端全局 LLM 配置，**不走个人模型、不会返回 428**；旧流水线里的关键词拦截器也只在这些轮次内可达，待 M9 随旧代码一并删除 |
| 偏差 3 | 画像采集用「单问题卡片」（`question_box`，字段标准选项来自预设，模型不得自编）；旧版分阶段 `question_form`（多题表单）不再产出，`question_form` 恒为 `null`（前端契约未强制该字段） |
| 偏差 4 | 画像首次完成后自动流转到课程草案智能体（文档 3.3 末句）依赖 M5，未启用；完成卡片的「进入学习路径草案智能体」按钮仍由前端触发下一轮 |
| 偏差 5 | Python 旧 `POST /api/chat/message` 与 `ChatContextLoader`/各 Handler 暂留（桥接复用），M9 清理 |
| 其他 | 图片附件仅在所选模型声明支持图片输入时才传给模型；`deploy` 侧新增 Nginx 精确匹配 location |

### 完成节点
| 日期 | 节点 | 证据 |
|---|---|---|
| 2026-11-27 | Python：迁移 0008 + 4 个内部接口 + 桥接接口 + 上下文/落库服务 | `ruff check`/`format` 通过；新增 `tests/test_internal_chat_api.py` 12 项；迁移 head 断言更新并校验列非空默认 `{}` |
| 2026-11-27 | 网关：`src/chat/{profileContract,agentRunner,profileAgent,supervisor,graph,routes}.ts`、`ModelRuntime.agentStream`、`BackendClient` 扩展 | `tsc --noEmit` 与 `npm run build` 通过；`vitest` 9 文件 **73** 个通过（M3 末 40；新增 `chat.test.ts` 22、`profileContract.test.ts` 6 等） |
| 2026-11-27 | 切流配置 | Vite 代理；Nginx 模板与 `test_nginx_config.sh` 断言已更新（见「未验证项」） |
| 2026-11-27 | 全量回归 | 后端 `pytest` **965** 通过（含主仓 LLM 环境变量）；前端 `vitest` 55 文件 **321** 通过；`biome`（vite.config.ts）通过 |

### 验收清单实测结果（2026-11-27）
联调环境：独立 schema `m4_acceptance`（`alembic upgrade head` 实跑 0008，测完已删除）+ Python 8000 + 网关 8100（真实 `server.ts`）+ **脚本化 mock OpenAI 兼容上游** 9100（按队列返回文本或指定工具调用，并记录每次请求的工具清单）+ Vite 5173 + 内置浏览器。每个账号经真实 `/api/model-config` 配置了指向 mock 的个人模型。

| 编号 | 结果 | 实测证据 |
|---|---|---|
| AC-1 | 通过 | 无画像新账号发“直接帮我生成大纲和学习路径”：上游收到的工具清单 **仅** `['delegate_profile_agent']`；单测另验证幻觉调用越阶段工具只得到错误结果，不触发桥接 |
| AC-2 | 通过 | 3 轮采集（“我大三”→“软件工程”→补齐）：第 1 轮 `collecting`，第 2 轮合并出 年级=大三/专业=软件工程 并带「找工作/考研/提升能力…」选项卡，第 3 轮落库 `basic_profile`（16 字段、`stage=generated`、`message_completed.full_text == summary_text`、`session_state` 追问标记被清除）。**浏览器**：单选卡片正常渲染（“已确认 年级 大三 / 专业 软件工程”+ 选项按钮「有基础」等）；整页刷新后首页仍显示画像完成度 12%、软件工程/大三与待回答的问题；最终轮生成「画像完成 · 进入学习路径草案智能体」卡片 |
| AC-3 | 通过 | “我研二，软件工程，想学 AI”：库内 `current_grade` 为空（未落非法年级）、专业保留、卡片文案点名「研二」并提示只支持大一到大四、选项为 大一~大四+其他，SSE 无 `error`；另测“保存时年级=研二 → 被工具拒绝 → 模型改调追问”：上游共 3 次调用、最终 `collecting`、无报错；单测覆盖“连续 3 次非法保存后确定性兜底” |
| AC-4 | 通过 | “直接按默认帮我生成画像”：2 次模型调用（委派+保存）完成落库，`defaulted_fields` = 次要字段 8 项（`has_clear_goal`、`learning_pace_preference`、`content_preference`、`need_guidance`、`strengths`、`weaknesses`、`long_term_goal`、`constraints`），核心字段（专业等）不在其中；单测另验证“学生没要求默认却传 `use_defaults`”与“核心字段标记为默认”均被拒绝 |
| AC-5 | 通过 | 已有路径+大纲的账号问“下个月我主要要学哪几门课？”：下发工具含 `get_learning_path`、`delegate_course_resources`；模型调用只读工具后，**库内真实路径文本**作为工具结果回到模型，SSE 推送 `data_update(learning_path_loaded, years=[year_3])`；进度工具同样验证。无任何关键词表参与。**说明**：由 mock 模型被脚本化为“调用该工具”，验证的是门禁、取数与回传链路，不评价真实模型的判断力 |
| AC-6 | 通过 | 读库时点：收到 `message_completed` 的瞬间 `GET /api/chat/sessions/{id}` 已含 2 条消息；刷新带 `session_id` 的页面，历史用户消息与「画像完成」结构化卡片挂在对应助手消息下；单测验证整体写入失败时无完成事件且仅兜底用户消息 |
| AC-7 | 通过 | 旧形态会话（`session_state` 默认 `{}`，`messages` 内夹带 `learning_path_intake`）继续对话 200、消息 5 条且 intake 保留、给模型的历史不含 intake（4 条=系统+历史 2+本轮 1）；新会话 200；Python 单测覆盖“显式 `session_state` 优先于旧约定”“旧 `[LEAF_REGEN_PENDING]` 标记转显式字段” |
| 附加 | 通过 | 显式 `[LEAF_RESOURCE_GENERATION]` 走桥接（上游模型 0 次调用、SSE 来自 Python 旧流水线）；未知会话 404、无令牌 401（`AUTH_INVALID`）；未配置模型账号：只得到 `MODEL_NOT_CONFIGURED` 错误事件、模型 0 次调用、库内 0 行；`chat_profile` 用量已按次写入 `user_model_usage_log`；首选模型 503 时回退到备用模型（单测） |

### 未验证项 / 已知遗留
- **真实模型**：所有对话轮次的“模型”均为脚本化 mock（验证了工具门禁、校验自纠、落库契约与流式链路），**未**用真实厂商模型评估提示词质量、工具调用遵循度与多轮采集体验；真实模型下的自纠次数/兜底触发率需要后续观察。
- **Nginx**：本机无 Docker，`nginx -t` 与容器级用例未跑；`test_nginx_config.sh` 中的静态 Python 断言（含新增 `location = /api/chat/message`）已通过。
- **桥接路径**：只验证了“显式协议→旧流水线→SSE 原样转发”，未用真实 LLM 跑完整的课程草案/大纲/资源生成（这些在 M5–M7 迁移时重测）。
- 回退只在“尚未输出任何内容”时发生，流到一半的上游失败不会换模型（有意设计）。
- Playwright e2e 未运行；浏览器里的 Vite HMR WebSocket 报错来自内置浏览器环境，与功能无关。

## M5：课程草案确认与按年学习路径生成

状态：**已完成并提交**（AC-1~6 通过；模型侧均为脚本化 mock 上游，见「未验证项」）

### 已确认的决策 / 与文档的偏差（2026-11-27）
| 项 | 结论 |
|---|---|
| 节点与流转 | 主图新增 `intake_agent`（课程草案）与 `learning_path_agent`（按年路径）。`delegate_learning_path_intake` 不再走旧流水线桥接，改为 `Command({goto: "intake_agent"})`；草案 `confirmed` 时 `Command({goto: "learning_path_agent"})` 同一次 SSE 内无缝跳转，其余状态 `goto: "finalize"`。桥接现只剩 `delegate_course_knowledge` / `delegate_course_resources` / 显式资源协议（M6/M7 移除） |
| 四态 | `none → draft → risk_pending → confirmed`，存 `session_state.learning_path_intake`（M4 已有的显式字段，读取时仍兼容旧会话“夹在 messages 里的 intake”）。**路径生成成功后清除该字段**（`null` 删键），避免遗留的 `confirmed` 在后续无关对话里被“可以”之类的回复误触发重新生成；生成失败时保留 `confirmed`，重试只需重跑路径节点 |
| 工具按状态下发 | `propose_or_revise_draft`（所有状态）；`confirm_draft`（draft / risk_pending / confirmed）；`cancel_risk_revision`（仅 risk_pending）；追问直接文字回答，不调用工具、不改状态。主管提示词在存在草案时强制把“确认/修改/取消/追问”都委派给草案智能体。**中文确认/取消/修改关键词表已不在 TS 路径中** |
| 教材检索 | `propose_or_revise_draft` 两步：先只带 `learning_topic`（可选 `search_topic`）→ 工具内部调 `POST /internal/knowledge-base/textbook-context-for-intake` 取目录摘要返回给模型；再带 `courses` 提交。无匹配教材时由程序确定性回复（修改场景：“原有的课程草稿已为你保留，可继续调整或直接确认原草稿”；首次：引导换方向），登记 `KnowledgeGap`（Python 侧按 `normalized_topic` 去重）并发 `data_update(knowledge_gap_recorded, gap_id)`，**不覆盖/清空草案** |
| 来源绑定校验 | 纯函数 `validateDraftCourses`：4–8 门、教材 ID 必须在本轮检索目录内、小节 ID 必须属于该教材（1–7 个）。**不再有字符打分兜底**；错误项逐条作为工具错误回给模型，同轮自纠最多 2 次（`MAX_INTAKE_CORRECTIONS`），超出则不落库、回复失败提示并保留原草案。修改草案时“与现有草案完全相同的绑定”被信任（避免改一门课就要重新检索所有教材） |
| 风险检测 | 纯函数 `detectRisks`：对比 Python `GET /internal/students/{uid}/protected-courses`（已有大纲或已开始/已完成课程），新草案丢掉任何一门 → 强制 `risk_pending`、`requires_second_confirmation=true`、列出 `risk_warnings`。`cancel_risk_revision` 与旧实现一致：回到普通草稿（保留修改后的课程）、清空风险，**不改正式路径**（正式路径只在 confirm 后才写） |
| 偏差 1：契约装配保留在 Python | 文档把“路径图谱与契约装配器 / 进度延续器”放在 TS。我**没有**在 TS 重写这约 800 行已被大量测试覆盖的确定性逻辑，而是把现有纯函数 (`_build_learning_path_from_plan` / `_apply_existing_progress_to_path` / `_validate_learning_path_contract`) 包成内部接口 `POST /internal/students/{uid}/learning-paths/{grade_year}/assemble`（无 LLM、无副作用）。理由：避免两份实现漂移、契约只有一处事实来源；模型侧（轻量规划 + 自纠）仍完全在 TS。该模块 M9 清理旧 agents 目录时随之搬迁为独立服务模块 |
| 偏差 2：新增内部接口 | 文档列 4 个，另加 `assemble`（上条）。`PUT /internal/students/{uid}/learning-paths/{grade_year}` 在单事务内 `upsert_year_learning_path` + `delete_user_course_outlines_by_grade_year`，异常回滚 |
| 路径节点 | 模型只通过工具 `submit_learning_path_plan` 提交轻量规划（学年目标/类型/成果/当前聚焦/下一步 + 与草案一一对应的 `course_specs`）；TS 先本地校验（数量=草案课程数、阶段≥3、知识点≥3、重难点/验收≥1），再调 `assemble`（后端 422 的原因同样回给模型），**共 1 次自纠**（`MAX_PLAN_CORRECTIONS`）。成功后 `saveYearLearningPath` → 摘要文本以“学习路径已生成”开头（前端结构化卡片按此前缀挂载）→ 再 `persistTurn` |
| 失败处理 | 路径节点两次失败：先落库本轮（用户消息 + 失败提示、草案保持 `confirmed`），再发 SSE `error`（`agent=learning_path_agent`、`retryable=true`、`retryAction="retry_learning_path"`，与旧版前端重试按钮契约一致），不发 `message_completed`。草案节点失败只回复文字、不改状态 |
| 模型场景 | 草案/路径节点使用 `path_outline` 槽位（对话主管与画像仍用 `chat_profile`）；未配置时按 M2 的“极简模式默认主力模型”回退 |
| 其他 | 路径节点提示词带各年级进度快照（`GET …/progress-snapshots`），延续逻辑由后端装配器完成；会话 `has_paths` 在本轮生成后立即为 true |

### 完成节点
| 日期 | 节点 | 证据 |
|---|---|---|
| 2026-11-27 | Python：`learning_path_runtime_service.py` + 5 个内部接口（教材上下文/受保护课程/进度快照/装配/单事务保存） | `ruff check`/`format` 通过；新增 `tests/test_internal_learning_path_api.py` 5 项（鉴权、缺口登记、装配+保存+进度延续、数量不一致 422、保存仅清该年级大纲）。顺带把 M4 的迁移列断言收紧到 `current_schema()`（此前依赖库里没有别的 schema） |
| 2026-11-27 | 网关：`intakeContract.ts`（纯函数）、`intakeAgent.ts`、`pathAgent.ts`、图节点与流转、`BackendClient` 扩展、主管提示词/工具委派更新 | `tsc --noEmit` 与 `npm run build` 通过；`vitest` 10 文件 **86** 个通过（M4 末 73；新增 `intake.test.ts` 13，并把 M4 的“桥接”用例改为仍未迁移的 `delegate_course_knowledge`） |
| 2026-11-27 | 全量回归 | 后端 `pytest` **970** 通过；`ruff check`/`format --check` 通过；前端无改动（M4 的 321 项测试未重跑） |

### 验收清单实测结果（2026-11-27）
联调环境：独立 schema `m5_acceptance`（`alembic upgrade head` 实跑，测完已删除）+ Python 8000 + 网关 8100（真实 `server.ts`）+ 脚本化 mock OpenAI 兼容上游 9100 + Vite 5173 + 内置浏览器；数据库里种入真实已发布教材《数据结构教材》（8 个小节）。每个账号经真实 `/api/model-config` 配置指向 mock 的个人模型，画像经内部接口落库。

| 编号 | 结果 | 实测证据 |
|---|---|---|
| AC-1 | 通过 | 先生成草案（4 门课，全部绑定 `tb-ds`），再问“第 2 门课会不会太难？为什么排在这里？”：回复直接讲解；草案 JSON 与提问前**逐字相同**、状态仍 `draft`、`useryearlearningpath` 0 行；该轮草案智能体拿到的工具是 `confirm_draft`+`propose_or_revise_draft`（无取消）。单测另验证按状态的工具集合 |
| AC-2 | 通过 | 模型第 2 次提交把第 2 门课的小节写成伪造的 `ds-999`：后端 mock 日志里回给模型的工具结果为“第 2 门课《线性结构实践》引用了教材「数据结构教材」中不存在的小节 ID：ds-999。小节 ID 必须逐字复制目录中的 section_id。”，第 3 次提交改成真实 `ds-2`，同一个请求内完成（共 4 次模型调用、无 `error` 事件）；落库小节 `[[ds-1],[ds-2],[ds-3],[ds-4]]`。单测另验证“超出 2 次自纠预算 → 不落库、回复失败提示” |
| AC-3 | 通过 | 已有草案后说“把第 3 门换成量子力学”（知识库无该教材）：`knowledgegap` **0 → 1 行**（`gap-…|量子力学`），草案 JSON 前后逐字相同，回复为“…已加入管理员待办。你原有的课程草稿已为你保留，可以继续调整，或者直接确认原草稿。”，并发出 `data_update(knowledge_gap_recorded, gap_id)`。（同一库里第二次重跑得到同一 `gap_id`、行数仍 1——Python 侧按 `normalized_topic` 去重，符合预期） |
| AC-4 | 通过 | 账号有课程《操作系统概论》的大纲；新草案没有该课 → `risk_pending`、`risk_warnings=["替换/删除已有课程大纲的课程《操作系统概论》"]`、`requires_second_confirmation=true`；回复“先不改”→ 工具集合含 `cancel_risk_revision`，状态回到 `draft`、警告清空、`useryearlearningpath` 仍 0 行；再次修改回到 `risk_pending`；回复“确认覆盖”→ `confirm_draft` → 同轮生成路径：年级路径 1 行、该年级大纲 0 行 |
| AC-5 | 通过 | 回复“可以，按这个生成吧”：同一次 SSE 内事件顺序为 `…supervisor_plan(learning_path_intake) → agent_calling/agent_result(learning_path_intake) → agent_calling(learning_path_agent) → agent_result(learning_path_agent) → message_completed → session_completed(has_paths=true)`；库里路径 `schema_version=learning_path.v2.course_node`，含 `grade_plans/knowledge_graph(critical_paths)/resource_generation_contract/dynamic_update_contract/current_learning_course(s)`，节点含 `chapter_nodes/course_node_id/source_*`；课程顺序与草案一致、教材绑定逐门一致；预置的该年级大纲被清空；回复以“学习路径已生成”开头；`GET /api/chat/sessions/{id}` 返回 `year_learning_paths=[year_3]`；`learning_path_intake` 键已清除。**浏览器**：`/branch` 页面渲染该路径（“这一学年共 4 门课程”、4 张课程卡） |
| AC-6 | 通过 | 把第 1 门课置为已完成后刷新同年级路径：进度快照 `completed_courses=1,next=year_3_course_2`；路径智能体提示词里带有“year_3：共 4 门课程，已完成 1 门”；刷新后 `current_learning_course=year_3_course_2（线性结构实践）`、状态 `in_progress`；浏览器 `/branch`：第 1 门“已完成”、第 2 门“当前焦点”、第 3 门“未开放”。Python 单测另覆盖装配器的进度延续 |
| 附加 | 通过 | 路径规划被后端拒绝两次：`error{agent=learning_path_agent, retryable=true, retryAction="retry_learning_path"}`，`useryearlearningpath` 0 行，草案仍为 `confirmed`，本轮 4 条消息已落库；用量按场景写入（`chat_profile` 与 `path_outline` 分别计次） |

### 未验证项 / 已知遗留
- **真实模型**：全部为脚本化 mock，验证的是工具门禁、校验自纠、契约装配、落库与流式链路，**未**评估真实模型选课质量、对 4–8 门数量/绑定规则的遵循度，也没测真实模型在“先检索目录再提交”两步工具协议下的表现。
- 路径节点的“模型自纠”只覆盖了数量不符与后端 422 两类；真实模型可能出现的其它字段漂移（例如 `difficulty_level` 同义词）由后端装配器已有的规范化兜底，未做针对性真实验证。
- 旧 Python 的 `learning_path_intake.py` / `learning_path.py` 及其关键词拦截器仍在仓库中（旧流水线 `legacy-stream` 对 M6/M7 的委派仍会加载它们），按计划在 M9 统一清理；装配函数目前是从旧模块里 import 的私有函数。
- “画像首次完成后自动流转到课程草案”（M4 遗留）：仍由前端“进入学习路径草案智能体”按钮触发下一轮，主管在 B 阶段会委派草案智能体；未做同轮自动衔接。
- Nginx/Docker 与 Playwright e2e 未运行（同 M4）。

## M6：课程大纲智能体与教材章节拆分

状态：**已完成并提交**（AC-1~6 通过；模型侧均为脚本化 mock 上游，见「未验证项」）

### 已确认的决策 / 与文档的偏差（2026-11-27）
| 项 | 结论 |
|---|---|
| 节点与流转 | 主图新增 `outline_agent`。`delegate_course_knowledge` 不再走旧流水线桥接，改为带 `course_ref`（课程名称/ID；`__all_current_grade__` 表示本年级全部课程；留空为当前课程）的 `Command({goto: "outline_agent"})`，处理完直接 `finalize`。桥接现只剩 `delegate_course_resources` 与显式资源协议（M7 移除） |
| 偏差 1：确定性部分留在 Python | 同 M5 原则：骨架构建、教材可见性门禁、文案合规校验、指纹校验与批量保存全部在 Python（`app/services/outline_service.py`，复用旧 `course_knowledge.py` 里已被测试覆盖的私有函数），经 3 个内部接口暴露：`POST /internal/students/{uid}/outline-source-context`、`…/course-outlines/compose`（校验模型命名并装配大纲，422 附中文原因）、`…/course-outlines/batch`（指纹不符 409）。模型侧（命名、并发调度、自纠、进度与部分成功）全部在 TS（`outlineAgent.ts`） |
| 超长小节自动拆分 | 教材小节正文 >8000 字时拆成多个学生端小节：目标 4000–7000 字/段、硬上限 8000，优先在段落末断开，其次句末，最后才硬切（尾段仍超限则递归再拆）。每段带 `source_chunk_index` / `source_chunk_total` / `source_char_range=[起,止)`，`source_content_chars` 为该段字数。为此 `SectionItem` 新增 3 个可选字段（`extra="forbid"`，必须声明）。章节 ID 仍为 "1"、"1.1"、"1.2"… |
| 模型只做命名 | 工具 `submit_outline_naming`：`personalization_summary` + 每个 section 的 `title/description/key_knowledge_points`。提示词里给出各 section 的教材来源标题与是否被拆分（“教材小节被拆成 N 个部分，这是第 K 部分”）。后端合规校验 = 旧版英文标题/内部字段检测 + 新增 `sec_*` 正则；不合规的具体原因回给模型，**同工具内自纠 1 次**（`MAX_NAMING_CORRECTIONS`），仍不合规则该课程记为失败 |
| 并发与进度 | 全年级模式 `mapWithConcurrency`，默认并发 2（`concurrency` 参数可调到 3）；每门课完成/失败后发一条 `agent_progress`（“已完成《X》大纲（2/5）”）。大纲按路径顺序排序后一次 `batch` 保存（单事务，失败整体回滚） |
| 部分成功 | 成功的课程保存；回复追加“以下课程大纲生成失败：《X》。…可以说“单独补生成《X》大纲”来重试”，`agent_result.success` 仍为 true（摘要写明“N 门失败”）。全部失败则不保存、回复失败提示。仅 `MODEL_OAUTH_EXPIRED` 会整体上抛（所有课程都会同样失败） |
| 脏写保护 | `source-context` 返回该年级课程身份指纹（sha256），`batch` 在学生锁内逐条比对，不符 → 409，TS 回复“学习路径在生成期间已更新，本次大纲未保存，请重新生成课程大纲。”，不落任何大纲 |
| 教材可见性门禁 | `source-context` 阶段就校验绑定教材已发布，否则 422（“《X》绑定的教材当前不可用（已下架或未发布），暂时无法生成课程大纲。”）；TS 把它直接作为回复、**不调用任何命名模型**，不发 `error` |
| 回复文案 | 单课程以“课程大纲已生成：《课程名》”开头（前端卡片按此前缀挂载），全年级为“本年级 N 门课程的章节大纲已生成。”，后接“运用了…教材及内容”清单（取学生端中文章节标题，最多 8 个）。发 `data_update(course_knowledge_generated)`，会话 `has_outline` 本轮即为 true |
| 模型场景 | 沿用 `path_outline` 槽位 |

### 完成节点
| 日期 | 节点 | 证据 |
|---|---|---|
| 2026-11-27 | Python：`outline_service.py`、`SectionItem` 拆分字段、3 个内部接口 | `ruff check`/`format` 通过；新增 `tests/test_internal_outline_api.py` 7 项（拆分算法含无断点 20000 字、鉴权、13000 字小节拆成 2 段且范围连续、按名称/默认选课、英文标题/`sec_1_1`/缺小节被拒、批量保存+指纹 409、教材下架 422）。测试里连跑 3 次确认无随机性 |
| 2026-11-27 | 网关：`outlineAgent.ts`、图节点 `outline_agent`、主管 `course_ref` 委派、`BackendClient`/FakeBackend 扩展 | `tsc --noEmit` 与 `npm run build` 通过；`vitest` 11 文件 **98** 个通过（M5 末 86；新增 `outline.test.ts` 12，并把 M4 的“桥接”用例改为 `delegate_course_resources`） |
| 2026-11-27 | 全量回归 | 后端 `pytest` **977** 通过（M5 末 970 + 新增 7；全量跑时用了 `-p no:logging`，9 个依赖 caplog 的用例因此报错，去掉该参数单独重跑全部通过）；`ruff check`/`format --check` 通过；前端无改动 |

### 验收清单实测结果（2026-11-27）
联调环境：独立 schema `m6_acceptance`（`alembic upgrade head` 实跑，测完已删除）+ Python 8000 + 网关 8100（真实 `server.ts`）+ 脚本化 mock 上游 9100（命名请求固定延迟 1.5 s，按课程名触发“纠错/失败”行为）。5 本已发布教材，第 1 本两个小节各 13000 字；每个账号经内部接口装配并保存 5 门课程的年级路径，经真实 `/api/model-config` 指向 mock。

| 编号 | 结果 | 实测证据 |
|---|---|---|
| AC-1 | 通过 | 13000 字小节落库为 2 段：`source_char_range=[0,6314]` 与 `[6314,13000]`（连续、覆盖全文），`source_content_chars=6314/6686`（均 ≤8000），`source_chunk_index=[1,2]`、`source_chunk_total=2`，标题“第1.1部分的中文讲解/第1.2部分…”；教材两个小节各拆一次共 4 段，章节 ID 为 1、1.1、1.2、2、2.1、2.2。经学生端 `GET /api/chat/sessions/{id}` 读取到同一份大纲（6 个小节、4 个带拆分元数据）。（脚本自带的断言按“只拆 1 个小节”写成 2 段，因种子数据拆了 2 个小节而误报 FAIL，已核对数据本身满足验收标准） |
| AC-2 | 通过 | mock 第一次提交的标题为“Complexity Analysis & sec_1_1”：回给模型的工具结果为“章节命名未通过，请修正后重新提交：章节 1 的可见文案包含教材内部编号（如 sec_1_1）…”，第 2 次提交中文标题通过；该课程共 2 次命名调用、无 `error` 事件，落库标题全为中文且不含 `sec_`/英文。单测另覆盖“英文标题”单独被拦截及“超出 1 次自纠 → 失败不保存” |
| AC-3 | 通过 | 5 门课全年级模式：库里 5 条大纲；SSE 里 5 条 `agent_progress`（“已完成《…》大纲（1/5）”…“（5/5）”）；总耗时 **4.6 s**，对比串行仅模型延迟就需 7.5 s（5×1.5 s）；5 次命名调用在 3.0 s 窗口内陆续发起（并发 2：3 个批次）；回复以“本年级 5 门课程的章节大纲已生成。”开头 |
| AC-4 | 通过 | 第 5 门课命名始终英文：库里只有 1–4 门的 4 条大纲（学生端读取正常）；进度含“《图结构失败课》大纲生成失败（5/5）”；回复结尾“以下课程大纲生成失败：《图结构失败课》。已生成的大纲不受影响，你可以说“单独补生成《图结构失败课》大纲”来重试。”；无 `error` 事件 |
| AC-5 | 通过 | 生成进行中（约 2.5 s 时）经内部接口修改该年级课程目标（指纹改变）：保存被拒，库里大纲 **0 行**，回复“学习路径在生成期间已更新，本次大纲未保存，请重新生成课程大纲。”，仍正常 `session_completed`。Python 单测另验证 409 与该文案 |
| AC-6 | 通过 | 把教材置为 `archived` 后请求当前课程大纲：模型调用共 **1 次**（仅主管路由）、命名调用 0 次、大纲 0 行，回复“《数据结构入门与复杂度基础》绑定的教材当前不可用（已下架或未发布），暂时无法生成课程大纲。”，无 `error` 事件 |

### 未验证项 / 已知遗留
- **真实模型**：全部为脚本化 mock，验证的是工具门禁、合规校验与自纠、并发调度、拆分、保存与流式链路，**未**评估真实模型的中文命名质量、对“不得出现英文教材标题/`sec_*`”的遵循度，以及拆分段之间标题递进是否自然。
- “单独补生成《XXX》大纲”只验证了文案与 `course_ref=课程名` 的选课路径（后端按名称选课有单测），**未**用 mock 脚本真实跑一遍“失败后补生成成功”的第二轮对话。
- 文档里“学生直接要求生成教学内容但还没有大纲 → `Command` 跳到 M7 资源子图”未做：M7 尚未开发，当前该请求仍由主管按门禁回答（无大纲时没有 `delegate_course_resources` 工具）；待 M7 衔接。
- 全年级并发默认 2，未做并发 3 的压测；`mapWithConcurrency` 有单测（峰值=2、耗时明显低于串行）。
- 旧 Python `course_knowledge.py` 仍在仓库中（`legacy-stream` 对资源协议的桥接仍会加载整个旧编排），其私有函数被 `outline_service.py` 直接 import，按计划在 M9 清理时迁成独立服务模块。
- Nginx/Docker 与 Playwright e2e 未运行；前端无改动，未在浏览器里重新渲染拆分后的大纲卡片（仅验证了学生端 API 返回）。

## M7：小节多模态教学资源生成子图

状态：**已完成并提交**（AC-1~6 通过；模型侧为脚本化 mock 上游，真实视频检索未跑，见「未验证项」）

### 已确认的决策 / 与文档的偏差（2026-11-27）
| 项 | 结论 |
|---|---|
| 节点与流转 | 主图新增 `resource_agent`，**移除 `legacy_bridge`**。叶子页按钮（`[LEAF_RESOURCE_GENERATION]`）在 `entry` 解析后直达 `resource_agent`（不经 Supervisor）；自然语言走 Supervisor 的 `delegate_course_resources(chapter_section_id?)` 再进入同一节点。 |
| 偏差 1：确定性逻辑留在 Python | 与 M5/M6 一致。教材证据、提示词、校验、检查点落库、章节锁、评分均在 `app/services/resource_service.py`，经 `/internal/students/{uid}/courses/{cid}/…` 暴露（prepare / markdown prompt+validate / video search / animation prompt+validate / `PUT sections/{sid}/resources` / finish）。TS 只做模型循环、并发、进度事件。文档里“prepare 返回教材切片”改为“Python 直接生成带证据的提示词”。 |
| 单小节流水线 | markdown →（video ∥ animation，`Promise.allSettled`）→ compose，每阶段完成即落库；章节内小节并发默认 2（可配到 3）。第一个小节 compose 后即可在叶子页读到，不必等整章。 |
| 自纠 | `submit_section_markdown` 经后端校验，最多 2 次同对话内修正；`submit_section_animations` 1 次修正后回退确定性模板动画。 |
| 偏差 2：视频逐小节降级 | 旧逻辑“至少一半小节有视频否则整章报错”改为**每小节独立降级**：搜不到合格视频 → `status:"unavailable"`、事件 `video_unavailable:true`、compose 里写 `video` 块 `unavailable`，不阻断、不报错。 |
| 偏差 3：严格 Markdown 校验 | 旧脚手架会把垃圾输出补全成“合格”文档，故 `validate_markdown` 先对**原始模型输出**做正文检查，再走脚手架与质量检查。 |
| 检查点真正落库 | 旧实现只在内存里存检查点；现存 `section_resource_checkpoints[sec][phase]`（及 `section_resource_errors`），重跑时已完成阶段直接复用（`mode≠regenerate`）。结构变更时这两个键随其它生成物一并清空。 |
| 偏差 4：部分失败可续跑 | `generate` 仅在**整章所有小节都已 compose** 时才进入“请先告知侧重点”；部分小节失败后再点按钮是续跑。（验收中发现原先 `any` 判定会让失败的章节无法续跑，已改为 `all` 并改了单测。） |
| 重新生成侧重点 | 存 `session_state.pending_leaf_regeneration {course_node_id, chapter_section_id, requested_at}`，不再用 `[LEAF_REGEN_PENDING]` 隐藏标签；用户下一条消息直接进 `resource_agent`（`mode=regenerate`，消息作 focus），完成后置 `null` 清除。 |
| 章节锁 | `finish` 在 TS `finally` 中必调；锁加 30 分钟 TTL，网关崩溃不会永久锁章。重复点击返回“这一章正在生成。”。 |
| 超长拆分小节取证 | `get_textbook_evidence_pack(..., char_range)`：M6 拆出的小节只取各自 `source_char_range` 切片，修复了 >8000 字证据包超限。 |
| 前端事件契约 | 事件顶层带 `course_id / chapter_section_id / section_id / kind(course_resource_section|course_resource_chapter) / phase / status / stepId / success`；最终 `agent_result success=true, status="completed"` 触发叶子页刷新。前端**无改动**。 |
| 失败泛化 | `ChatFailure{agent,label,message,retryAction?,extra?}`；`finalize` 先落库再发 `error`。路径智能体同步改用。 |

### 完成节点
- Python：`resource_service.py`、`/internal` 8 个端点、锁 TTL、证据切片；`tests/test_internal_resources_api.py` 8 个用例。
- TS：`backendClient` 8 个方法、`resourceAgent.ts`、`supervisor.ts`/`graph.ts` 改造（`legacy_bridge` 删除）、`test/resource.test.ts` 15 个用例；三个过时的 legacy 路由测试已改写。
- 全量：后端 **984 passed**（ruff check/format 干净）；网关 `tsc --noEmit`、`npm run build` 通过，vitest **112 passed**。

### 验收清单实测结果
真实 Python 后端 + 真实网关 + 脚本化 mock 模型，独立 Postgres schema `m7_acceptance`（用后已删除），5 本教材、第一章拆成 3 个叶子小节（1.1/1.2/1.3）。

| AC | 结果 | 证据 |
|---|---|---|
| AC-1 | 通过 | 按钮路径：无 `supervisor_plan`，库里 `section_composed_markdowns = [1.1,1.2,1.3]`，compose 事件 `{course_id: year_3_course_1, chapter_section_id: 1, section_id: 1.1, kind: course_resource_section, phase: compose, status: completed, success: true}`，终稿“本章教学内容已生成。”；自然语言路径：`supervisor_plan agent=course_resources`，结果同为 3 个小节。 |
| AC-2 | 通过 | 1.1 的 video 窗口 [0.03s..0.04s] 与 animation 窗口 [0.03s..0.05s] 重叠；mock 把 1.2 延迟 4 s，1.1 compose 事件在 +0.05 s、库里 1.1 已可见（+0.27 s），整个请求 +4.11 s 才结束。 |
| AC-3 | 通过（变体） | 第 1.2 节 **markdown 阶段**失败（模型只回“只有一句话”）：1.1/1.3 已 compose，1.2 记录 `section_resource_errors{phase: markdown}`、checkpoint=failed；重跑时模型仅被调用 1.2（3 次），1.1/1.3 的 markdown 事件为“文案已有检查点，直接复用”，最终 3 节齐全、错误清除。文档原场景是**动画阶段**失败：该路径由 vitest（resource.test.ts）覆盖，未在 live 里复现。 |
| AC-4 | 通过（降级路径）| 实机：本环境检索不到合格视频 → 3 节 `video.status=unavailable`，compose 含 `video:unavailable` 块，事件“该小节暂未找到合适教学视频，已平稳跳过”，无 `error`，终稿“本章教学内容已生成。”，请求不失败。“找到视频”路径：后端单测 `test_video_found_is_saved_as_available_and_composed`（打桩 Bilibili 检索）+ 网关 vitest；**未做真实检索**（见下）。 |
| AC-5 | 通过 | 已生成章节再点“重新生成”：回复“重新生成本章前，请告诉我下一版需要侧重哪里。”，模型调用 **0 次**，回复与历史里**无** `LEAF_REGEN_PENDING`，`session_state.pending_leaf_regeneration = {course_node_id, chapter_section_id: 1, requested_at}`；下一条“多讲一些复杂度的例题”：无 supervisor 调用，该 focus 出现在小节提示词里，pending 键清除，1.1 的 `generated_at` 更新。 |
| AC-6 | 通过 | (a) 第一次运行中（1.2 延迟）另一会话再点：`error {message:"这一章正在生成。", kind: course_resource_chapter}`，第一次不受影响并完成；(b) 全部小节失败：`error` 事件后立即重试成功；(c) 客户端中途断开：网关继续跑完（先落库），立即新请求被拒“这一章正在生成。”，跑完后下一次请求正常执行——锁已释放。 |

### 未验证项 / 已知遗留
- **真实模型**：全部为脚本化 mock。模型自写的动画能否通过 Python 严格校验未在 live 里执行（live 走了模板回退；通过校验的路径由单测/vitest 覆盖）。
- **真实视频检索**：旧检索仅有 DashScope 联网搜 Bilibili（需 `LLM_API_KEY`），本次未使用该付费密钥，故“真的找到视频”只用桩验证；降级是真实走通的。
- **客户端断开不中止运行**：网关当前不因 SSE 断开而取消生成（与 persist-first 一致，结果仍落库，锁在运行结束后释放）；若要“断开即取消”需另加 abort 传播，本里程碑未做。
- 文档里“LEAF 隐藏标签”已不被网关使用，但 `chat_context_service` 仍会从旧 `[LEAF_REGEN_PENDING]` 标记构造 pending，`rule_engine` 旧解析器、`legacy-stream` 路由、`progress.bridged`/`raw` chunk 与 `openLegacyStream` 仍在，留给 M9 清理。
- 前端未在浏览器里复验叶子页刷新（前端无改动，仅验证事件字段契约）；Nginx/Docker 与 Playwright e2e 未运行。

## M8：章节测验、视觉判分、Forest AI、成长报告与知识库 AI 收口

状态：**已完成并提交**（AC-1~5 通过；模型侧为脚本化 mock 上游，见「未验证项」）

### 已确认的决策 / 与文档的偏差（2026-11-27）
| 项 | 结论 |
|---|---|
| 总体切分 | 与 M5–M7 一致：确定性逻辑（数据读取、四条防幻觉校验、事务与恢复）留在 Python；所有模型调用在 TS 网关。Python→网关新增通用调用 `call_gateway_ai / acall_gateway_ai`（内部令牌，网关 HTTP 错误保留 `status/detail/error_code`）。 |
| 出题 `/internal/ai/quiz/generate` | Python 新增 `POST /internal/students/{uid}/quiz-material`（实为 `forest_ai_service.quiz_generation_material`，供 Forest 路由内部调用）汇总**全部二级小节**的「练习任务/检查标准」（取自 M7 的小节 markdown）与知识点清单。TS `submit_quiz` 工具 + 确定性校验（3 题型齐全、总分严格 100、单选选项/`correct_option_id` 合法、`knowledge_point_ids` ⊆ 本章清单），原地自修 1 次，仍失败 → HTTP 502「出题失败」。**`build_fallback_quiz_questions` 假题逻辑整体删除**；失败不落库、`regenerate` 失败不动旧题。 |
| 判分 `/internal/ai/quiz/grade` | 单选纯规则（不调模型）；代码题走文本模型；图片题有真实图片 → `quiz_vision` 槽位的视觉模型（模型不支持图片 → 422 `MODEL_CAPABILITY_MISMATCH`；未配置 → 428 `MODEL_NOT_CONFIGURED`，提交不落库、本机草稿可原样重试）；仅文字描述则降级按文字评分（评语里说明未见图片）。三题并发，总分由程序累加，`passed = score > 70`。事务/幂等/恢复快照逻辑未动。 |
| 场景槽位 | 出题与代码判分用 `course_resources` 槽位（文本）；仅在**真有图片**时用 `quiz_vision`；Forest AI 带图时 `quiz_vision`，否则 `course_resources`（避免没配视觉模型的学生连纯文字答疑都被挡住）。 |
| Forest AI | 网关接管 `POST /api/forest/ai/stream`（Vite 代理 + Nginx `location =` 已切），事件仍为 `forest_ai_text_chunk / forest_ai_completed / forest_error{message,error_code?}`。**苏格拉底模式由服务端判定**：Python `GET /internal/forest/chapters/{course}/{chapter}/material?user_uid&quiz_id` 返回 `submitted`（该测验是否已有判分尝试），客户端伪造 `grading_result` 无效；无 `quiz_id` 才回落到客户端上下文。挂载只读工具 `read_chapter_learning_material`。 |
| 偏差：教材原文 | 材料接口只返回本章各小节**讲解正文**（单小节 6000 字、总计 24000 字截断），未附加绑定教材原文片段；多轮追问仅靠请求里的当前题目上下文（请求体本无历史字段）。 |
| 成长报告 | 网关接管 `POST /api/branch/canopy/report/stream`（路由同上）。Python 提供 `report-context`、`report-evidence`、`report-validate`；Agent 三个只读工具 `read_quiz/read_chapter/read_textbook`，**程序硬限 6 次**，超出作为工具错误回传；`submit_growth_report` 内调用 Python 的**同一套四条校验**（证据 ID 真实且教材须已读、无测验时 strengths 必须为空且优势须引 quiz、建议课程 ID 真实、事实分析数字须有出处），失败回传原地修正（≤2 次），通过后由 Python 组装 `GrowthReport`（只附带实际引用的 evidence）。Python 旧 `/canopy/report/stream` 路由与 `stream_growth_report/generate_narrative` 删除。 |
| 知识库 AI | 迁移 `0009_kb_job_triggered_by`（`KnowledgeBaseIngestionJob.triggered_by_uid`，可空）；管理员触发的整理/确认/上传/搜书都写入或携带 `admin.uid`。`/internal/ai/kb/translate-chunk`、`/internal/ai/kb/search-textbook-sources` 在 `kb_translate/kb_search` 槽位用**该管理员本人**的模型，用量记在其名下；未配置 → 428，SSE `error` 带 `error_code`。URL 合法性/可解析性核验仍在 Python。 |
| 删除 | Python 的 `generate_quiz_questions / grade_quiz_answers / stream_forest_ai_response / build_fallback_quiz_questions`（`forest.py` 保留同名**网关代理封装**，便于测试打桩）、`get_translation_llm / get_search_worker_llm` 在知识库服务中的使用。 |

### 完成节点
- Python：`ai_gateway_client.call_gateway_ai`、迁移 0009、`forest_ai_service.py`（出题材料/章节材料/报告上下文·证据·校验）、`/internal` 5 个新接口、`forest.py` 改走网关、KB 服务与路由透传管理员 uid；删除旧 LLM 路径；改写 4 个旧测试文件，新增 `tests/test_forest_gateway_ai.py`（3 个）。
- TS：`src/ai/{quiz,kb,forestAi,growthReport,routes}.ts`、`backendClient` 4 个新方法、`app.ts` 挂载 `/internal/ai/*` 与两条公开流；`test/m8.test.ts`（19 个）。
- 切流：`frontend/vite.config.ts` 代理正则与 `production.conf.template` 两个 `location =`（`proxy_buffering off`）+ `test_nginx_config.sh` 静态断言。
- 全量：后端 **983 passed**（ruff 干净）；网关 `tsc --noEmit`、`npm run build` 通过，vitest **131 passed**。

### 验收清单实测结果
真实 Python 后端 + 真实网关 + 脚本化 mock 模型，独立 schema `m8_acceptance`（用后已删除）；章节内容由 M7 流程真实生成。

| AC | 结果 | 证据 |
|---|---|---|
| AC-1 | 通过 | 出题：单选/代码/图片各 1 道，分值 30+40+30=100，提示词里带有各叶子小节「练习任务」；模型回 110 分 → HTTP 502「出题失败…（三题分值之和必须严格等于 100（当前 110））」，库里 0 条测验；`regenerate` 失败后旧题 `quiz_version` 不变。 |
| AC-2 | 通过 | 纯文字作答：{q1:30, q2:35, q3:25}=90 且等于三题之和，模型判分调用仅 2 次（单选未调模型）；断流恢复 GET 返回同一 attempt；同一 `client_submission_id` 重放 0 次新模型调用。有视觉模型的学生提交真实 PNG：该次调用 `model=relay-vision` 且带图，评语含图片内容，总分 60=0+35+25。无视觉模型提交真图：SSE `error` 428「尚未配置可用的个人模型…」，尝试 0 条落库。 |
| AC-3 | 通过 | 提交前：系统提示为苏格拉底模式（含“严禁直接给出…”），回复走 `forest_ai_text_chunk` → `forest_ai_completed`；判分后（客户端传 `grading_result=null`）服务端识别已提交，提示词切到完整解析、不含苏格拉底指令。 |
| AC-4 | 通过 | 无测验账号：模型先编造一条引用 `quiz:fake` 的优势 → Python 校验拒绝 → 修正后 `strengths=[]` 完成（共 2 次提交）。有测验账号：阶段 collecting→analyzing→writing；脚本让模型发 8 次读取，网关只放行 6 次（其余作为工具错误），共 10 次模型请求；含无来源数字 999 的首份报告被拒、修正版通过；报告里全部 evidence ID 都在目录内、优势引用 quiz 证据。 |
| AC-5 | 通过 | 已配置的管理员：搜书经网关走其个人模型（`source_search_completed`，候选 URL 仍由 Python 核验，本机无网络出口故 `result_count=0`）；分段翻译返回中文；用量表里该管理员名下有 `kb_search`、`kb_translate`。未配置的管理员：agent 流 `error_code=MODEL_NOT_CONFIGURED`，翻译抛“尚未配置可用的个人模型…”，且没有发生任何模型调用。 |

### 未验证项 / 已知遗留
- **真实模型**：全部为脚本化 mock。苏格拉底“不剧透”是否被真实模型遵守、视觉模型是否真能读懂截图、报告写作质量均未评估；live 验证的是提示词/模式切换、工具与校验链路、计费与错误传播。
- **成长报告前端 `parseReport`** 与展开依据/跳转课程的 UI 未在浏览器验证（前端无改动，仅验证 SSE 事件与 Python `GrowthReport` 模型校验）。
- **OpenAPI 类型**：删除 Python 的 `/api/branch/canopy/report/stream`（`GrowthReport` 模型原仅由该路由暴露）后，重新生成 `frontend/src/types/api.d.ts` 可能丢失 `GrowthReport` 等类型；当前提交的 `api.d.ts` 未动，M9 清理时需处理。
- **知识库翻译**：现有入库流程并没有调用 `translate_section_content_to_zh`（它是未接入的辅助函数），本次只把它改成走管理员个人模型并经单测/live 验证，没有新增“入库时自动翻译”。`triggered_by_uid` 已落库并随 worker 的 job 可读。
- 出题 live 时所选章节没有 `knowledge_point_ids` 清单，ID 子集校验在 live 里是空集合成立，真实校验由 vitest 与 `validateQuiz` 单测覆盖。
- 管理端知识库页的“引导直达模型配置”仅由后端/SSE 返回 `error_code=MODEL_NOT_CONFIGURED`，前端页面未改、未在浏览器复验。
- Nginx 容器级用例（需要 Docker）本机未跑，仅静态断言通过；`GET /internal/forest/.../material` 未附教材原文（见偏差）。

## M9：旧架构清退、生产部署适配与全链路回归验收

状态：**已完成并提交**（AC-1~7 全部通过；真实模型输出与真实视频检索见「未验证项」）

### 已确认的决策 / 与文档的偏差（2026-11-27）
| 项 | 结论 |
|---|---|
| 旧编排清退 | 删除 `app/orchestration/{graph,llm,events,guards,rule_engine,default_fill,observability,…}`、`agents/{supervisor,profile,learning_path_intake,utils}` 与 `api/chat_handlers.py`；`/internal/.../legacy-stream` 与 `/api/orchestration/*` 中除 `/start`、`/sessions/{id}` 外的路由全部移除。`pyproject.toml`/`uv.lock` 去掉全部 `langchain*`/`langgraph*`。 |
| 偏差：`app/orchestration/` 保留 | 作为**纯函数辅助包**保留（`contracts`、`grade_contract`、`prompt_budget`、`recovery`、`state`、`agents/{course_knowledge,learning_path,models,prompts,quiz,course_resources/*}`），其中不含任何模型调用/langchain 依赖，仍被 `/internal` 确定性接口复用。 |
| 偏差：保留 `dashscope` | B 站视频检索仍在 Python（M7 约定），因此保留 `dashscope` 依赖；平台 `LLM_API_KEY`/`LLM_MODEL` 在生产变为**可选**（缺失时视频逐小节降级），bootstrap 仍会提示填写。 |
| 消息存储 | 会话消息仍是旧 langchain 字典形态 `{"type":"human"\|"ai","data":{…}}`，由 `chat_context_service` 以纯 dict 读写；旧会话数据无需迁移（AC-4 已验证）。 |
| 生产配置校验 | `core/config.py` 生产环境强制 `INTERNAL_API_TOKEN`、`MODEL_SECRET_ENCRYPTION_KEY`、`AI_GATEWAY_URL`，缺失即拒绝启动。 |
| 网关 Lint | 采用 Biome（`ai-gateway/biome.json`，关闭 `noExplicitAny`/`noNonNullAssertion`），新增 `npm run lint`。 |
| 部署面 | 新增 `ai-gateway/Dockerfile`（多阶段、非 root、HEALTHCHECK）；`compose.production.yml`/`compose.ci.yml` 加 `ai-gateway` 服务；`env.production.example`、`bootstrap`、`deploy`、`smoke`、两份 Nginx 模板（`/api/ai/`、`/api/chat/message`、`/api/forest/ai/stream` 转发网关，`/internal/` 对外 404/封闭）同步。 |
| OpenAPI | 报告类型随旧路由删除移出 schema，改为前端本地类型（`src/api/growthReport.ts`），`gen:api` 无漂移。 |
| 顺带修复 | `knowledge_base_service._source_textbook_ids` 不递归列表内的嵌套教材 ID，已补递归并加测试。 |

### 完成节点
- 后端：删除上述旧编排模块与对应测试；`chat_context_service` 内联旧 `rule_engine` 的纯解析（`parse_leaf_regeneration_pending_marker` 等）；`grade_contract` 新增 `is_complete_profile_data`；`state.py` 简化为 `dict`。
- 网关：删除 `backendClient`/`chat/routes`/`chat/types`/`graph` 中旧桥接死代码与 `test/chat.test.ts`；修 Lint 全部问题；新增 Dockerfile、Biome。
- 部署：见上；`deploy/tests/*` 静态断言同步。
- 文档（AC-7）：`docs/backend/agent逻辑.md`、`backend-tech-stack.md`、`docs/project-overview.md`、`docs/database/数据库表结构.md`、`docs/deployment/docker-production.md`（网关服务、必需环境变量、故障定位）。

### 验收清单实测结果
| 编号 | 结果 | 证据 |
|---|---|---|
| AC-1 | 通过 | 依赖清单与 `app/` 内 `grep -ri "langchain\|langgraph"` 无命中；在**不含 langchain 的干净 venv**（`uv sync --frozen --extra test`）中全量 `pytest -q`：**514 passed**；`ruff check app tests`、`ruff format --check` 通过。测试数从 984 降到 514 是因为删除了旧编排的测试（对应能力已迁到 TS 网关，由其 131 项测试覆盖），**不宣称等价覆盖**。 |
| AC-2 | 通过 | `tsc --noEmit`、`npm run lint`（Biome，0 错误/0 警告）、`npm run build` 通过，vitest **131 passed**。 |
| AC-3 | 通过 | `gen:api` 无漂移、`tsc`、vitest **321 passed**、`npm run build`、Biome 通过（既有 131 条 Biome warning 为基线，未新增）。 |
| AC-4 | 通过 | 独立 schema 中：①`alembic upgrade head` 全新库成功（`test_alembic_migrations` 亦过）；②升到 0006 后插入历史用户/画像/会话/KB 任务数据，并还原成 0007 之前的结构，再 `upgrade head` → 0009，历史行全部完整（会话 `session_state` 回填 `{}`、旧消息结构可读、KB 任务 `triggered_by_uid` 为空）；③再执行 `downgrade` 到 0006 与重新 `upgrade head` 均无报错、数据保留。注意 0001 使用 `metadata.create_all`，所以“滚动升级”实际是在 0007–0009 三个增量迁移上演练。 |
| AC-5 | 通过 | **浏览器走查（后补，Vite 5173 + 干净后端 + 真实网关 + 脚本化 mock 上游）**：①新学生在登录页登录 → 进入萌芽首页，对话框模型切换器显示“未配置模型” → 发送消息得到红色错误条“尚未配置可用的个人模型，请先前往[模型配置]完成设置”及“去配置模型”卡片（链接到 `/settings/models`）→ 在页面里新增自定义 Provider（Key 仅回显 `••••0001`）+ 新增模型 `relay-main` → 点“测试连接”探针：文本 ✔ 93 ms、工具调用 ✗（mock 不支持）、视觉未声明 → 选主力模型并“保存配置”（提示下一轮对话立即生效）→ 返回对话，切换器显示 `relay-main`，发送“我大三”后经 Supervisor → 画像智能体，页面出现“基础信息/年级=大三 已确认/采集中”卡片，进度条“生成完成·8 个步骤”。网络面板中登录后所有 `/api/*` 均 200（仅登录页预取的 2 个 401 属未登录状态）、后端日志 0 个 500、`user_model_usage_log` 写入 `chat_profile` 记录。另注：该输入框按 Enter 不发送，需点发送按钮（沿用既有行为，非 M9 改动）。**脚本部分**： | 独立 schema `m9_acceptance` + 干净 venv 后端 + 真实网关 `server.ts` + 脚本化 mock 上游，重跑 M4–M8 全部验收脚本：M4 AC-1~7 全过；M5 AC-1~6 全过；M6 AC-2~6 通过，AC-1 脚本断言“只拆 1 段”与种子（两小节各 13000 字）不符而误报 FAIL，实际 4 段（`[0,6314]`/`[6314,13000]` ×2）满足标准，与 M6 记录一致；M7 阶段 A/B/C 全过（视频检索未配置 → 逐节“暂无视频”降级且 composed 不受影响）；M8 AC-1~5 全过。全程后端日志 **0 个 500/Traceback**，各场景用量日志入库（如 chat_profile 10 行）。 |
| AC-6 | 通过 | 后补：启动本机 Docker Desktop 后，按 CI 流程实跑：`compose config` OK → `build`（backend/ai-gateway/nginx 镜像）OK → `up postgres` + `run migrate` OK → `up --wait backend worker nginx` 全部 healthy（含 ai-gateway healthy）→ `run --rm smoke` 输出 “CI smoke checks passed” → 经 nginx 访问 `/internal/health` 得 **404**、`/api/ai/health/live` 得 200；网关 `/ready` 200。另在有 Docker 条件下重跑 `test_compose_config`、`test_bootstrap`、`test_nginx_config`（含 nginx 容器 `nginx -t`）、`test_smoke`、`test_deploy_rollback`、`test_deployment_docs` 全过；`test_nginx_config.sh` 因 compose 现要求 `INTERNAL_API_TOKEN`/`MODEL_SECRET_ENCRYPTION_KEY` 而补了测试环境变量。测试栈已 `down -v` 清除。网关生产产物另做过 `node dist/server.js` 实跑。 |
| AC-7 | 通过 | 四份文档已按最终代码核对更新；`deploy` 文档同步。 |

### 未验证项 / 已知遗留
- 未覆盖：真实服务器（腾讯云）上的域名/IP 证书与外网访问，仅在本机 CI 配置（bootstrap 模式 Nginx）下验证。
- AC-5 的浏览器走查仅覆盖到阶段 ①②（登录、拦截、配置、探针、画像采集首轮）；阶段 ③~⑧ 的 UI 点击未重做，由 API/SSE 级脚本覆盖（M3–M8 各自也做过相应页面验证）。
- **所有模型行为均为脚本化 mock，真实模型输出质量、真实 B 站/YouTube 检索未验证**；任何真实上游问题需用真实配置再测。
- Python 测试数量下降（984→514）为主动删除旧编排测试所致，覆盖由网关测试承接，但并非逐项对应。
- 前端 131 条 Biome 基线 warning 未处理。
