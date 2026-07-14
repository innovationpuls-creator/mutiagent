# Task 1 报告：视频平台边界诊断证据

## 状态与范围

- 开始时 HEAD：`a79aebbcb2122cd3c1d48e922016d16efdaf84ef`
- 修改范围：
  - `backend/app/orchestration/agents/course_resources/bilibili.py`
  - `backend/app/orchestration/agents/course_resources/video.py`
  - `backend/tests/test_course_resource_agent_contract.py`
- 未触碰既有工作区改动：`docs/report-data-inventory.md`、`.DS_Store`、`docs/.DS_Store`

## TDD 证据

先添加两个失败测试并运行：

```bash
cd backend && uv run pytest tests/test_course_resource_agent_contract.py -k 'youtube_search_request or bilibili_search_parse' -q
```

结果：`2 failed, 108 deselected`。

失败原因与目标一致：YouTube 原日志没有 `YouTube search request failed` 和异常类型；Bilibili 没有解析阶段结果数日志。

## 实现

- YouTube 请求异常日志增加 `error_type=%s`，使用 `type(exc).__name__`，并保留查询和异常文本。
- Bilibili 请求异常日志增加请求失败文案、查询、异常类型和异常文本。
- 两个平台在请求成功后记录 HTTP 状态码。
- 两个平台在解析前记录 `raw_result_count`，解析后记录 `parsed_result_count`。
- Bilibili 页面正文没有 BV 号时保持返回空列表，不构造搜索页 URL 作为视频结果。

## 验证

定向测试：

```bash
cd backend && uv run pytest tests/test_course_resource_agent_contract.py -k 'youtube_search_request or bilibili_search_parse' -q
```

结果：`2 passed, 108 deselected`。

覆盖测试：

```bash
cd backend && uv run pytest tests/test_course_resource_agent_contract.py -q
```

结果：`110 passed`。

Ruff：

```bash
cd backend && uv run ruff check --fix app/orchestration/agents/course_resources/bilibili.py app/orchestration/agents/course_resources/video.py tests/test_course_resource_agent_contract.py
cd backend && uv run ruff format app/orchestration/agents/course_resources/bilibili.py app/orchestration/agents/course_resources/video.py tests/test_course_resource_agent_contract.py
cd backend && uv run ruff check app/orchestration/agents/course_resources/bilibili.py app/orchestration/agents/course_resources/video.py tests/test_course_resource_agent_contract.py
cd backend && uv run ruff format --check app/orchestration/agents/course_resources/bilibili.py app/orchestration/agents/course_resources/video.py tests/test_course_resource_agent_contract.py
```

结果：规则检查通过；格式检查通过；格式化命令完成 1 个文件格式化，其他文件保持不变。

其他自检：`git diff --check` 通过。

## Important 修复记录：YouTube JSON 解析失败日志

- 新增回归测试：HTTP 200 响应正文匹配 `ytInitialData`，但 JSON 无法解析时，断言日志包含 `parsed_result_count=0`。
- TDD 红灯：

  ```bash
  cd backend && uv run pytest tests/test_course_resource_agent_contract.py::test_youtube_search_parse_logs_zero_results_on_invalid_initial_data -q
  ```

  结果：`1 failed`，失败原因是 JSON 解析异常分支缺少 `parsed_result_count=0`。
- 最小修复：YouTube `json.loads` 异常日志增加 `parsed_result_count=0`，未改变其他视频筛选行为。
- 验证：精确回归测试 `1 passed`；覆盖测试 `111 passed`；Ruff 检查与格式检查通过；`git diff --check` 通过。

## 复审修复记录：存量 Bilibili 搜索页与解析计数断言

- P1：新增 `test_existing_video_value_rejects_bilibili_search_page_url`。红灯命令：

  ```bash
  cd backend && uv run pytest tests/test_course_resource_agent_contract.py -k 'bilibili_search_parse_logs_zero_results_without_bv_id or existing_video_value_rejects_bilibili_search_page_url' -q
  ```

  结果：`1 failed, 1 passed, 110 deselected`。失败证明 `_existing_video_value` 会把 `https://search.bilibili.com/video?...` 复用为已有视频。
- 最小修复：`_normalized_video_quality_issue` 在 HTTP(S) 校验后拒绝 `search.bilibili.com`，使搜索页不能作为真实视频 URL；真实 Bilibili 视频页的既有 BV 校验路径未改动。
- P2：Bilibili 无 BV 号测试将宽泛的 `result_count=0` 子串改为完整字段 `parsed_result_count=0`。该字段在现有日志中已经存在，因此该项测试在红灯运行中通过，表明修改收紧了断言而非修复生产行为。
- 定向验证：`2 passed, 110 deselected`。
- 覆盖验证：`112 passed`。
- Ruff：`uv run ruff check --fix ...`、`uv run ruff format ...`、`uv run ruff check ...` 与 `uv run ruff format --check ...` 均通过。
- `git diff --check` 通过。

## Important 修复记录：Bilibili 精确视频 URL 合同

- 新增参数化回归测试，拒绝下列 `source=Bilibili` URL：
  - `https://www.bilibili.com`
  - `https://www.bilibili.com/search?keyword=AI`
  - `bilibili.com/video/BV1xx411x7xx`
  - `https://evilbilibili.com/video/BV1xx411x7xx`
- 同时新增真实 URL 形态通过测试：`https://www.bilibili.com/video/BV1xx411x7xx`。
- TDD 红灯：

  ```bash
  cd backend && uv run pytest tests/test_course_resource_agent_contract.py -k 'requires_exact_bilibili_video_url or accepts_exact_bilibili_video_url_shape' -q
  ```

  结果：`4 failed, 1 passed, 112 deselected`。四类无效 URL 未被精确 Bilibili 合同拒绝。
- 最小修复：BV 提取仅接受 `https`、`www.bilibili.com` 和完整 `/video/BV...` 路径；`source=Bilibili` 的质量门要求该精确形态；异步质量门只为已确认的 Bilibili 视频执行 Bilibili 元数据校验，其他平台不再经由 Bilibili `status=skip` 分支。
- 精确验证：`6 passed, 111 deselected`，包含既有 YouTube watch URL 回归。
- 覆盖验证发现两条存量“已验证视频”夹具的 BV 号不完整；已改为完整 BV 号，并为这两条完整路径显式 mock Bilibili 元数据成功响应，避免网络依赖。两个受影响 nodeid：`2 passed`。
- 最终验证：`uv run pytest tests/test_course_resource_agent_contract.py -q` 为 `117 passed`；Ruff 规则检查和格式检查通过；`git diff --check` 通过。

## 复审修复记录：Bilibili URL 边界与 source 绕过

- 新增失败测试覆盖：
  - `source=YouTube` 搭配 `https://evilbilibili.com/video/BV1xx411x7xx`。
  - Bilibili URL 的 query、fragment、username/password 和非默认端口。
  - 保留 `https://www.bilibili.com/video/BV1xx411x7xx` 正常通过测试。
- TDD 红灯：

  ```bash
  cd backend && uv run pytest tests/test_course_resource_agent_contract.py -k 'requires_exact_bilibili_video_url or does_not_allow_source_to_bypass_bilibili_url or accepts_exact_bilibili_video_url_shape or video_quality_gate_accepts_youtube_watch_url' -q
  ```

  结果：`5 failed, 5 passed, 112 deselected`。新增的四类 URL 边界和 source 绕过均被当前实现错误放行。
- 最小修复：`_bilibili_bvid_from_url` 现在只接受 `scheme=https`、`hostname=www.bilibili.com`、无凭据、无 query/fragment、无显式端口或默认端口 `443`，以及完整 `/video/BV...` 路径；质量门拒绝 `source=YouTube` 的非 YouTube watch 地址，未改变 YouTube watch URL 的既有通过逻辑。
- TDD 绿灯：同一命令结果为 `10 passed, 112 deselected`。
- 定向验证：

  ```bash
  cd backend && uv run pytest tests/test_course_resource_agent_contract.py -k 'video_quality or find_verified_video_from_search_uses_youtube_when_bilibili_has_no_verified_match' -q
  ```

  结果：`24 passed, 98 deselected`。
- 完整验证：`cd backend && uv run pytest tests/test_course_resource_agent_contract.py -q`，结果：`122 passed in 17.77s`。
- Ruff 与差异检查：`uv run ruff check --fix`、`uv run ruff format`、`uv run ruff check`、`uv run ruff format --check` 均通过；两个生产文件格式化后保持不变；`git diff --check` 通过。
- TDD 测试检查点：`cb92a6f test: cover exact bilibili video URL boundaries`。
- 实现提交：`b2a3628 fix: harden bilibili video URL validation`。
- 本次改动文件：`backend/app/orchestration/agents/course_resources/bilibili.py`、`backend/app/orchestration/agents/course_resources/video.py`、`backend/tests/test_course_resource_agent_contract.py`。
