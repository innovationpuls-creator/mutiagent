# Production Security and Observability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 FastAPI 生产启动具有强配置校验、精确 CORS、无默认 demo 账号、真实健康检查和可关联请求日志。

**Architecture:** 新增集中配置模块并显式注入应用与 JWT；将健康路由和观测中间件从 `main.py` 拆分。保留显式测试/开发建表 helper，生产 `create_app` 不再依赖它，最终 DDL 切断在数据库子计划完成。

**Tech Stack:** Python 3.12, FastAPI, SQLModel, Pydantic, stdlib logging, pytest.

## Global Constraints

- 生产必填键：`APP_ENV`, `DATABASE_URL`, `JWT_SECRET`, `LLM_API_KEY`, `LLM_MODEL`, `ALLOWED_ORIGINS`。
- `LLM_BASE_URL` 精确值为 `https://dashscope.aliyuncs.com/compatible-mode/v1`。
- 生产 `JWT_SECRET` 不得等于 `mutiagent-dev-secret-key-change-in-production`。
- 生产 CORS 只接受 `ALLOWED_ORIGINS` 中逐项解析出的完整 origin。
- 结构化日志不得记录 Authorization、密码、JWT、LLM API Key、数据库密码或请求正文。

---

### Task 1: 集中生产配置与 JWT 注入

**Files:**
- Create: `backend/app/core/config.py`
- Modify: `backend/app/core/security.py`
- Test: `backend/tests/test_production_config.py`
- Test: `backend/tests/test_auth_api.py`

**Interfaces:**
- Produces: `AppSettings`, `load_settings(environ: Mapping[str, str] | None = None) -> AppSettings`。
- Produces: `configure_jwt(secret: str) -> None`，供 `create_app` 在路由创建前调用。

- [ ] **Step 1: 写配置失败红测**

```python
@pytest.mark.parametrize(
    "missing_key",
    ["DATABASE_URL", "JWT_SECRET", "LLM_API_KEY", "LLM_MODEL", "ALLOWED_ORIGINS"],
)
def test_production_rejects_missing_required_settings(missing_key: str) -> None:
    environ = valid_production_environ()
    environ.pop(missing_key)
    with pytest.raises(ValueError, match=missing_key):
        load_settings(environ)

def test_production_rejects_default_jwt_secret() -> None:
    environ = valid_production_environ()
    environ["JWT_SECRET"] = "mutiagent-dev-secret-key-change-in-production"
    with pytest.raises(ValueError, match="JWT_SECRET"):
        load_settings(environ)
```

- [ ] **Step 2: 运行红测**

Run: `cd backend && uv run pytest tests/test_production_config.py -q`
Expected: FAIL，因为 `app.core.config` 尚不存在。

- [ ] **Step 3: 实现最小配置模型**

`AppSettings` 必须保存精确环境、数据库 URL、JWT secret、LLM 配置与 `tuple[str, ...]` origins；`load_settings` 必须按逗号拆分 `ALLOWED_ORIGINS`、去空白、拒绝空项，并在 production 校验全部必填项。

- [ ] **Step 4: 改造 JWT 使用运行时显式 secret**

删除模块级默认 `SECRET_KEY`。`configure_jwt` 只接受非空字符串；`create_access_token` 和 `decode_access_token` 在未配置时抛出启动配置错误，而不是使用后备值。

- [ ] **Step 5: 运行配置与认证测试**

Run: `cd backend && uv run pytest tests/test_production_config.py tests/test_auth_api.py -q`
Expected: PASS。

- [ ] **Step 6: Ruff 与提交**

Run: `cd backend && uv run ruff check --fix app/core/config.py app/core/security.py tests/test_production_config.py tests/test_auth_api.py && uv run ruff format app/core/config.py app/core/security.py tests/test_production_config.py tests/test_auth_api.py`

Commit: `git commit -m "fix: enforce production security settings"`

### Task 2: 精确 CORS 与生产 demo seed 隔离

**Files:**
- Modify: `backend/app/main.py`
- Modify: `backend/app/database.py`
- Modify: `backend/tests/test_cors_api.py`
- Modify: `backend/tests/test_auth_api.py`
- Modify: `backend/tests/test_cultivation_program_api.py`

**Interfaces:**
- Consumes: `load_settings`, `configure_jwt`。
- Produces: `create_app(database_url: str | None = None, settings: AppSettings | None = None, initialize_database: bool = False) -> FastAPI`。

- [ ] **Step 1: 写生产 CORS 红测**

```python
def test_production_cors_allows_configured_origin(client: TestClient) -> None:
    response = client.options("/api/health/live", headers=preflight("https://onetree.chat"))
    assert response.headers["access-control-allow-origin"] == "https://onetree.chat"

def test_production_cors_rejects_unconfigured_origin(client: TestClient) -> None:
    response = client.options("/api/health/live", headers=preflight("https://app.example.com"))
    assert "access-control-allow-origin" not in response.headers
```

- [ ] **Step 2: 写 seed 隔离红测**

`test_production_startup_does_not_create_demo_user` 创建空测试 schema，启动 production app 后精确查询 `User.identifier == "demo@mutiagent.local"` 并断言不存在。`test_development_seed_creates_demo_user_only_when_explicitly_enabled` 只在显式开发 helper 中断言存在。

- [ ] **Step 3: 运行红测**

Run: `cd backend && uv run pytest tests/test_cors_api.py tests/test_auth_api.py -q`
Expected: FAIL，因为当前放行所有公网 HTTPS origin 且启动创建 demo 用户。

- [ ] **Step 4: 实现 allowlist 与显式初始化**

移除 `_build_cors_origin_regex` 的公网通配行为。`CORSMiddleware.allow_origins` 只使用 settings origins。把 schema 初始化与 seed 留在显式 `initialize_development_database` helper；生产 `create_app` 不 seed。修改依赖 demo 登录的测试，使测试自己创建所需用户。

- [ ] **Step 5: 运行定向测试与 Ruff**

Run: `cd backend && uv run pytest tests/test_cors_api.py tests/test_auth_api.py tests/test_cultivation_program_api.py -q`
Expected: PASS。

Commit: `git commit -m "fix: isolate production startup data"`

### Task 3: Request ID 与结构化访问日志

**Files:**
- Create: `backend/app/core/observability.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_request_id.py`

**Interfaces:**
- Produces: `RequestIdMiddleware`。
- Produces: `configure_json_logging(service_name: str) -> None`。
- Header contract: `X-Request-ID`。

- [ ] **Step 1: 写 request ID 红测**

```python
def test_response_reuses_valid_incoming_request_id(client: TestClient) -> None:
    response = client.get("/api/health/live", headers={"X-Request-ID": "req-123"})
    assert response.headers["X-Request-ID"] == "req-123"

def test_response_replaces_invalid_request_id(client: TestClient) -> None:
    response = client.get("/api/health/live", headers={"X-Request-ID": "bad value\n"})
    assert response.headers["X-Request-ID"] != "bad value\n"
```

另写日志捕获测试，断言 method/path/status_code/duration/request_id 存在，且日志不包含 Authorization 和请求密码。

- [ ] **Step 2: 运行红测**

Run: `cd backend && uv run pytest tests/test_request_id.py -q`
Expected: FAIL，因为响应没有 `X-Request-ID`。

- [ ] **Step 3: 实现中间件与 JSON formatter**

只接受长度 1..128 且字符属于 `[A-Za-z0-9._:-]` 的入站 ID；否则生成 UUID4 hex。使用 `contextvars.ContextVar` 关联日志，不读取或记录请求正文。

- [ ] **Step 4: 运行测试、Ruff、提交**

Run: `cd backend && uv run pytest tests/test_request_id.py -q`
Expected: PASS。

Commit: `git commit -m "feat: add request tracing logs"`

### Task 4: 真实 liveness 与 readiness

**Files:**
- Create: `backend/app/api/health.py`
- Modify: `backend/app/main.py`
- Modify: `backend/app/schemas.py`
- Test: `backend/tests/test_health_api.py`

**Interfaces:**
- Produces: `create_health_router(engine: Engine) -> APIRouter`。
- Routes: `/api/health/live`, `/api/health/ready`, `/api/health`。

- [ ] **Step 1: 写健康红测**

```python
def test_liveness_does_not_query_database(client_with_broken_engine: TestClient) -> None:
    assert client_with_broken_engine.get("/api/health/live").status_code == 200

def test_readiness_fails_when_database_is_unavailable(client_with_broken_engine: TestClient) -> None:
    response = client_with_broken_engine.get("/api/health/ready")
    assert response.status_code == 503
    assert response.json()["database"] == "unavailable"
```

增加可用数据库时 `SELECT 1` 成功测试，以及 legacy `/api/health` 返回真实 readiness 的测试。Alembic head 校验在数据库子计划 Task 2 补齐。

- [ ] **Step 2: 运行红测**

Run: `cd backend && uv run pytest tests/test_health_api.py -q`
Expected: FAIL，因为路由不存在且 legacy health 固定成功。

- [ ] **Step 3: 实现独立 health router**

readiness 使用新 Session/connection 执行 `SELECT 1`，捕获 SQLAlchemy 异常并返回 503；liveness 不访问数据库。

- [ ] **Step 4: 生成 API 类型**

Run: `cd frontend && npm run gen:api && npx biome check --write openapi.json src/types/api.ts`
Expected: API 文件更新且 Biome 无错误。

- [ ] **Step 5: 测试、Ruff、提交**

Run: `cd backend && uv run pytest tests/test_health_api.py tests/test_cors_api.py tests/test_request_id.py -q`
Expected: PASS。

Commit: `git commit -m "feat: add real service health checks"`

### Task 5: Phase 1 回归门禁

**Files:**
- Modify only if failures trace directly to Phase 1 behavior.

- [ ] **Step 1: 运行后端定向回归**

Run: `cd backend && uv run pytest tests/test_production_config.py tests/test_auth_api.py tests/test_cors_api.py tests/test_request_id.py tests/test_health_api.py tests/test_cultivation_program_api.py -q`
Expected: PASS，0 failures。

- [ ] **Step 2: 运行格式检查**

Run: `cd backend && uv run ruff check app tests && uv run ruff format --check app tests`
Expected: exit 0。

- [ ] **Step 3: 前端契约检查**

Run: `cd frontend && npm test -- --run && npm run build`
Expected: 0 failures，build exit 0。
