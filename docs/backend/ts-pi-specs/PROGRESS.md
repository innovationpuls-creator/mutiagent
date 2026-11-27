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
