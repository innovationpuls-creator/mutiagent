# M2 开发文档：全员个人 Pi 模型配置后端与运行时

> 文档日期：2026-11-27  
> 对应里程碑：M2（前置依赖：M1）  
> 上位文档：`docs/backend/ts-pi-agent-redesign.md`、`docs/backend/ts-pi-specs/00-roadmap-and-milestones.md`

---

## 1. 目标范围与前置依赖

### 1.1 目标范围
落地 OneTree **“一视同仁，人人用自己的 AI”** 的个人模型配置后端持久化、加解密安全、OAuth 授权与续期闭环、Pi 多模型运行时装配、故障回退链、连通性探针与用量统计体系，为 M3（前端页面）及 M4–M8（全部业务 Agent）提供统一模型底座。

### 1.2 核心设计原则
- **单一租户配置模型**：学生与管理员使用完全一致的个人配置结构，不设系统兜底模型或代付额度。
- **Pi 能力零阉割**：完整覆盖 Pi 的内置目录、自定义 Provider 与模型、协议兼容项（Compat）、6 档思考深度、Prompt 缓存、多模态视觉标签、Web 端 OAuth 与用量统计。
- **密钥永不出库明文给前端**：所有 API Key、OAuth Access Token、Refresh Token 在 Python 侧应用层加密存储，前端仅见脱敏掩码与状态；仅在 `/internal/*` 通道向 TS 网关下发解密后凭据。

---

## 2. 现有源码盘点与约束

1. **数据库迁移基线**（`backend/migrations/versions/`）：当前最新迁移为 `0006_admin_program_drop_embed.py`。M2 必须新增 `0007_personal_pi_model_config.py`，并保持对 PostgreSQL 18 JSONB 与现有表命名/索引风格一致。
2. **既有并发锁约定**（`backend/app/services/student_lock.py`）：现有短事务采用对 `User` 行加 `FOR UPDATE` 串行化。M2 的 OAuth 并发刷新需按「用户 + Provider」维度加行锁，避免多小节并发生成时同时刷新导致 Refresh Token 互相顶掉失效。
3. **旧 LLM 单例限制**（`backend/app/orchestration/llm.py`）：旧版全局共享 5 个 `ChatOpenAI` 单例且写死 `LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL`。M2 起在 TS 网关完全改为**按 `user_uid` + 业务场景槽位动态解析**，旧环境变量不再作为用户默认模型。
4. **OpenAPI 生成机制**（`backend/app/export_openapi.py`）：Python 侧新增的对外配置读写接口必须带完整 Pydantic Schema，以便前端 `npm run gen:api` 自动同步类型。

---

## 3. 业务模块设计与核心流转

### 3.1 Python 侧：配置持久化与凭据安全模块
1. **应用层加解密服务**
   - 从环境变量 `MODEL_SECRET_ENCRYPTION_KEY` 读取对称加密主密钥（生产环境强制非空校验，开发环境提供可区分警告）；负责 API Key、OAuth Access Token、Refresh Token、敏感自定义请求头的加密入库与解密读取。
   - 对外响应统一生成脱敏掩码（例如保留末 4 位）与配置状态标记，绝不返回明文。
2. **个人配置 CRUD 与防呆校验服务**
   - 管理用户的内置/自定义 Provider、自定义模型列表及场景槽位映射。
   - **能力防呆校验**：保存场景槽位时强制核验——绑定至「测验图片判分 / Forest 多模态答疑」的模型必须具备视觉能力标签；绑定至需要工具调用的槽位（对话、草案、成长报告）的模型必须具备工具能力标签；不满足则拒绝保存并返回 `MODEL_CAPABILITY_MISMATCH`（422）。
   - **热失效通知**：任意保存/删除/OAuth 更新提交数据库后，异步或同步调用 TS 网关内部接口失效该 `user_uid` 的运行时缓存（通知失败记录告警并依赖短 TTL 自动过期，不阻断保存）。
3. **OAuth 并发续期锁服务**
   - 当 TS 网关发现某用户某 Provider 的 Access Token 临近过期或已过期，调用 Python 内部续期协调接口（或由 Python 加行锁后调用 TS 网关执行上游换取再落库）：先对 `UserModelProvider` 目标行加 `FOR UPDATE`，若其他并发请求已完成刷新则直接返回最新 Token，否则执行单次刷新并落库。
4. **个人用量统计聚合服务**
   - 接收 TS 网关上报的每次调用明细（场景、Provider、模型、输入/输出/缓存命中/推理 Token、估算费用、耗时、是否成功），按天与按业务场景提供聚合查询接口。

### 3.2 TS 网关侧：Pi 运行时与多用户装配模块
1. **目录与自定义注册中心**
   - 暴露 Pi 内置 Provider 与模型目录（附带上下文窗口、最大输出、视觉/工具/思考能力、参考单价、是否支持 OAuth）。
   - 为每个用户合并“Pi 内置目录 + 用户自定义 Provider 与模型”，完整支持 4 种协议族（OpenAI Chat Completions / OpenAI Responses / Anthropic Messages / Google Native）、Base URL、自定义请求头及 **Pi Compat 兼容项**（推理字段格式、系统/开发者角色兼容、Token 上限字段名等）。
2. **按请求模型解析器与短周期缓存**
   - 按 `user_uid` 缓存该用户的生效配置（TTL 60 秒，支持内部热失效接口即时清除）。
   - 解析顺序：检查高级模式指定场景槽位 → 回退至极简模式（视觉场景取“默认视觉模型”，其余场景取“默认主力模型”）→ 均未配置时立即抛出 `MODEL_NOT_CONFIGURED`（428 / SSE `error`）。
   - 解析出最终主模型、6 档思考深度（`off` / `minimal` / `low` / `medium` / `high` / `xhigh`）、温度、最大输出、超时、重试次数、Prompt 缓存策略以及备用回退链。
3. **高可用回退链执行器（Fallback Chain）**
   - 调用主模型遇到限流（429）、超时或 5xx 异常时，按用户配置的回退链顺序自动切换备用模型继续执行；遇到 OAuth 授权失效且刷新失败时，立即中止并返回 `MODEL_OAUTH_EXPIRED`（附带 `provider` 标识）。
   - 每次调用结束后（无论成功或回退成功），统一将 Pi 返回的精确 Token 与估算费用异步上报至 Python 用量流水表。
4. **一期 Web 端双模式 OAuth 授权引擎**
   - **发起授权**：前端请求某支持 OAuth 的 Provider 登录，TS 网关生成带防伪 `state`（绑定 `user_uid`、`provider_id`、有效期 10 分钟）的授权链接与 PKCE 参数。
   - **双模式完成**：
     - 模式 A（自动回调）：支持 Web 回调的厂商跳回网关回调端点，校验 `state` 后换取 Token 并加密落库。
     - 模式 B（手动粘贴兜底）：仅允许本机回调的厂商，前端展示授权页链接与“粘贴回调 URL / 授权码”输入框，提交至 TS 网关完成换取与落库。
5. **三项能力连通性探针**
   - 接受用户指定的 Provider + 模型配置（支持保存前临时参数测试或已保存配置测试），依次执行极简探针并记录首字延迟：
     - **基础文本探针**：极简对话返回，验证认证与网络连通；
     - **工具调用探针**：挂 1 个极简只读工具，验证原生 Tool Calling 兼容；
     - **视觉探针**（模型声明支持视觉时执行）：附带一张极小内置测试图，验证多模态图片输入可用。

---

## 4. 数据库表设计与跨服务接口契约

### 4.1 新增 4 张 PostgreSQL 数据表（Alembic `0007_personal_pi_model_config.py`）

| 表名 | 主键 / 唯一约束 | 核心字段 |
|---|---|---|
| `user_model_provider` | `(user_uid, provider_id)` 唯一 | `id`、`user_uid`、`provider_id`、`display_name`、`is_builtin`、`protocol`、`base_url`、`headers_encrypted`、`auth_type`（`api_key` / `oauth`）、`secret_encrypted`、`oauth_refresh_encrypted`、`oauth_expires_at`、`oauth_account_label`、`enabled`、`updated_at` |
| `user_custom_model` | `(user_uid, provider_id, model_id)` 唯一 | `id`、`user_uid`、`provider_id`、`model_id`、`display_name`、`context_window`、`max_tokens`、`supports_vision`、`supports_tools`、`supports_reasoning`、`compat_config`（JSONB）、`pricing`（JSONB）、`enabled`、`updated_at` |
| `user_model_preferences` | `user_uid` 主键 | `user_uid`、`config_mode`（`simple` / `advanced`）、`default_model_ref`（JSONB：`provider_id` + `model_id`）、`default_vision_model_ref`（JSONB）、`default_thinking_level`、`runtime_options`（JSONB：温度、超时、重试、Prompt 缓存）、`slot_bindings`（JSONB：各业务场景槽位的主模型、思考深度、回退链列表）、`updated_at` |
| `user_model_usage_log` | `usage_id` 主键，索引 `(user_uid, created_at)` 与 `(user_uid, scene)` | `usage_id`、`user_uid`、`request_id`、`scene`、`provider_id`、`model_id`、`thinking_level`、`input_tokens`、`output_tokens`、`cache_read_tokens`、`cache_write_tokens`、`reasoning_tokens`、`estimated_cost_usd`、`latency_ms`、`success`、`error_code`、`created_at` |

### 4.2 对外接口与内部接口清单

- **对外配置接口（Python 负责持久化读写，TS 网关负责目录/探针/OAuth）**：
  - `GET /api/ai/models/catalog`（TS 网关）：返回 Pi 内置 Provider 与模型元数据目录。
  - `GET /api/model-config` / `PUT /api/model-config/providers/{provider_id}` / `DELETE /api/model-config/providers/{provider_id}`（Python）：个人 Provider 与加密凭据管理（返回脱敏视图）。
  - `PUT /api/model-config/custom-models` / `DELETE /api/model-config/custom-models/{id}`（Python）：自定义模型与 Compat 管理。
  - `PUT /api/model-config/preferences` / `PATCH /api/model-config/quick-switch`（Python）：完整槽位偏好保存与快捷切换（当前模型 + 思考深度）。
  - `GET /api/model-config/usage`（Python）：个人按天/按场景用量与费用聚合。
  - `POST /api/ai/models/probe`（TS 网关）：三项能力连通性探针。
  - `POST /api/ai/oauth/{provider_id}/start`、`GET /api/ai/oauth/callback`、`POST /api/ai/oauth/{provider_id}/complete`（TS 网关）：双模式 OAuth 授权闭环。
- **内部跨服务接口（需 `X-Internal-Token`）**：
  - Python 暴露：`GET /internal/users/{uid}/model-runtime-config`（返回解密凭据与槽位配置）、`POST /internal/users/{uid}/providers/{provider_id}/oauth-refresh-lock`（行锁保护续期）、`POST /internal/users/{uid}/model-usage`（写入用量流水）。
  - TS 网关暴露：`POST /internal/cache/invalidate-user-model-config`（即时清除某用户运行时缓存）。

---

## 5. 风险点与缓解策略

1. **OAuth 回调跨域与防伪**：`state` 严格绑定 `user_uid` 并设置 10 分钟一次性消费，防止 CSRF 与跨账号串写；仅支持本机回调的厂商通过手动粘贴兜底确保 100% 可用。
2. **自定义中转站协议怪异**：通过直接透传 Pi 的 `Compat` 配置字段，让用户可在界面微调推理字段与角色映射，无需改代码适配每个中转站。
3. **用量上报不能阻塞主对话**：用量写入采用异步非阻塞上报，失败仅打结构化告警日志，不影响学生正常回复。

---

## 6. M2 可执行验收清单

| 编号 | 验收维度 | 具体验证步骤 | 预期达成结果 |
|---|---|---|---|
| **AC-1** | 迁移与加密存储 | 在独立测试库执行 Alembic 迁移至 `0007`；保存含 API Key 与自定义请求头的 Provider，直查数据库并调用 `GET /api/model-config` | 4 张表创建成功；数据库字段为密文不可逆明文读取；对外接口仅返回脱敏掩码。 |
| **AC-2** | 自定义模型与 Compat | 新增自定义 OpenAI 兼容端点及自定义模型（填写 Compat 参数与视觉/工具标签），调用目录与解析接口 | 运行时正确合并内置与自定义模型，且 Compat 与自定义请求头实际透传到上游请求。 |
| **AC-3** | 能力防呆校验 | 尝试将 `supports_vision = false` 的模型绑定到「测验图片判分」槽位 | 服务端拒绝并返回 `422` + `error_code = MODEL_CAPABILITY_MISMATCH`。 |
| **AC-4** | Web OAuth 双模式与并发锁 | ① 走自动回调与手动粘贴授权码完成授权<br>② 模拟 5 个并发请求同时遇到过期 Token | ① 两种模式均成功加密落库并标记已授权<br>② 仅触发 1 次上游刷新请求，5 个请求全部成功，无 Refresh Token 失效。 |
| **AC-5** | 三项连通性探针 | 对支持视觉与不支持视觉的模型分别调用 `/api/ai/models/probe` | 准确返回文本、工具调用、视觉三项状态与首字延迟；无效 Key 返回清晰原因。 |
| **AC-6** | 回退链、热失效与用量 | ① 配置主模型（模拟 429/500）+ 备用模型，发起一次调用<br>② 修改思考深度或切换模型后不重启服务立即再调用<br>③ 查询 `/api/model-config/usage` | ① 自动无缝切至备用模型返回成功<br>② 缓存即时失效，新配置立刻生效<br>③ 用量表准确记录 Token、估算费用与耗时。 |
| **AC-7** | 未配置用户统一拦阻 | 使用尚未配置任何模型的新账号请求模型解析 | 返回标准 `MODEL_NOT_CONFIGURED` 错误码，不回退任何全局环境变量密钥。 |
