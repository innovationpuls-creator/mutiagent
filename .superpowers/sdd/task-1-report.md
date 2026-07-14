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
