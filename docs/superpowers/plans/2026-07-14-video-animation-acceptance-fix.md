# 视频检索与 HTML 动画验收修复 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让生产环境的视频检索和 HTML 动画只在真实资源、真实结构和可见渲染均通过检查时返回成功，并能定位平台失败原因。

**Architecture:** 保留现有 Bilibili/YouTube 并行检索和章节级 45 秒超时，在平台边界增加统一诊断日志；视频仍以真实视频页为唯一成功条件。动画在后端统一清洗、拒绝编码残片并复用确定性结构动画重建，最终由同一质量门决定是否持久化为可用资源。

**Tech Stack:** FastAPI/Python 3.12、asyncio、httpx、Pydantic、pytest、Ruff、React 18 iframe `srcDoc`。

---

## 文件边界

- 修改 `backend/app/orchestration/agents/course_resources/bilibili.py`：记录 Bilibili HTTP/解析阶段结果，不改变真实页面校验规则。
- 修改 `backend/app/orchestration/agents/course_resources/video.py`：记录 YouTube 请求/解析阶段结果，并保留真实 URL 质量门。
- 修改 `backend/app/orchestration/agents/course_resources/animation.py`：拒绝 `&oklch(...)` 等编码残片，强化结构质量检查，必要时使用确定性动画重建。
- 修改 `backend/app/orchestration/agents/course_resources/common.py`：仅在需要共享动画非法文本模式时添加精确常量。
- 修改 `backend/tests/test_course_resource_agent_contract.py`：先添加失败测试，再覆盖平台诊断、动画清洗、确定性重建和失败状态。
- 不修改 `frontend/src/pages/leaf/LeafContent.tsx`：当前 iframe 沙箱和失败卡片边界已经正确，问题发生在后端 HTML 输入；本计划用后端 HTML 输入契约覆盖 iframe 的可见污染。

### Task 1: 为视频平台边界补齐可诊断证据

**Files:**
- Modify: `backend/app/orchestration/agents/course_resources/bilibili.py` 的 `_search_bilibili_video_page_results`
- Modify: `backend/app/orchestration/agents/course_resources/video.py` 的 `_search_youtube_video_results`
- Test: `backend/tests/test_course_resource_agent_contract.py`

- [ ] **Step 1: 写失败测试，锁定平台请求和解析日志**

在现有视频搜索测试附近添加两个测试：

```python
import httpx

from app.orchestration.agents.course_resources import animation as animation_module
from app.orchestration.agents.course_resources import video as video_module


def test_search_platform_logs_http_failure_type(monkeypatch, caplog):
    class FailingClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def get(self, *_args, **_kwargs):
            raise httpx.ConnectError("dns failure")

    monkeypatch.setattr(video_module.httpx, "AsyncClient", lambda **_kwargs: FailingClient())
    results = asyncio.run(video_module._search_youtube_video_results("算法效率"))
    assert results == []
    assert "YouTube search request failed" in caplog.text
    assert "ConnectError" in caplog.text
```

同时为 Bilibili 响应正文不含 BV 号添加测试，断言日志包含 `result_count=0` 和解析阶段。

- [ ] **Step 2: 运行定向测试确认先失败**

Run:

```bash
cd backend && uv run pytest tests/test_course_resource_agent_contract.py -k 'youtube_search_request or bilibili_search_parse' -q
```

Expected: FAIL，因为当前日志文案没有异常类型，也没有平台解析结果数。

- [ ] **Step 3: 实现最小日志改动**

在两个平台函数中分别记录：

```python
logger.warning(
    "YouTube search request failed query=%s error_type=%s error=%s",
    query,
    type(exc).__name__,
    exc,
)
```

请求成功后记录 HTTP 状态；解析前后记录 `raw_result_count` 和 `parsed_result_count`。Bilibili 不得因无 BV 号构造搜索页成功结果。

- [ ] **Step 4: 运行定向测试确认通过**

Run:

```bash
cd backend && uv run pytest tests/test_course_resource_agent_contract.py -k 'youtube_search_request or bilibili_search_parse' -q
```

Expected: PASS。

- [ ] **Step 5: 提交视频诊断改动**

```bash
git add backend/app/orchestration/agents/course_resources/bilibili.py backend/app/orchestration/agents/course_resources/video.py backend/tests/test_course_resource_agent_contract.py
git commit -m "fix: diagnose video platform search failures"
```

### Task 2: 拒绝非法动画 HTML，并在失败时重建确定性结构动画

**Files:**
- Modify: `backend/app/orchestration/agents/course_resources/animation.py` 的 `_normalize_animation_html`、`_normalize_animations`、`_normalized_animation_quality_issue`
- Modify: `backend/app/orchestration/agents/course_resources/common.py`（仅当共享非法颜色模式需要抽取时）
- Test: `backend/tests/test_course_resource_agent_contract.py`

- [ ] **Step 1: 写失败测试，复现生产截图中的非法文本**

添加测试：

```python
from app.orchestration.agents.course_resources import animation as animation_module


def test_normalize_animation_html_rejects_encoded_color_text():
    html_text = '<section class="section-animation"><div>&oklch(72% 0.08 240); 主题</div></section>'
    normalized = animation_module._normalize_animation_html(
        html_text, _linked_list_animation_brief()
    )
    assert normalized == ""
```

再添加结构测试，要求缺失实体、关系或 timeline 时 `_normalized_animation_quality_issue` 返回具体错误，不得返回 `None`。

- [ ] **Step 2: 运行测试确认先失败**

Run:

```bash
cd backend && uv run pytest tests/test_course_resource_agent_contract.py -k 'encoded_color_text or animation_structure' -q
```

Expected: FAIL，因为当前实现保留 `&oklch(...)`，且部分结构只依赖字符串存在性。

- [ ] **Step 3: 实现动画输入边界**

在动画 HTML 规范化边界增加精确拒绝规则：

```python
_ENCODED_COLOR_TEXT_PATTERN = re.compile(
    r"&(?:oklch|rgba?|hsla?)\s*\([^)]*\)", re.IGNORECASE
)
```

匹配到该模式时返回空 HTML，使当前流程进入质量失败处理；不得把非法文本替换成可用动画。

将结构检查改为同时要求：

- `section-animation` 根节点；
- brief 中每个 entity 的 `data-entity-id` 或可见 label；
- brief 中每条 relation 的来源和目标以及连线元素；
- brief 中每个 timeline step 的 `data-timeline` 或 `data-step`；
- 中文上下文、UTF-8 声明、OKLCH/CSS 变量颜色和 reduced-motion 降级。

- [ ] **Step 4: 为非法模型输出接入确定性重建测试**

构造模型返回包含 `&oklch(...)` 的动画数据，调用 `run_section_html_animation_agent`，断言最终结果中的 HTML 不含 `&oklch`，并包含 `data-entity-id`、`data-timeline`、关系连线和 `prefers-reduced-motion`。若确定性结果也不满足质量门，断言返回失败而不是 `available`。

- [ ] **Step 5: 实现最小重建路径**

在每次模型输出通过 `_normalize_animations` 后执行质量检查；质量问题存在时，先调用现有 `_deterministic_animation_data(animation_briefs, section)`，再对重建结果运行同一 `_normalized_animation_quality_issue`。只有重建结果无质量问题才写入 `section_html_animations`；否则保留现有失败返回。

- [ ] **Step 6: 运行动画定向测试确认通过**

```bash
cd backend && uv run pytest tests/test_course_resource_agent_contract.py -k 'animation' -q
```

Expected: 所有动画契约测试 PASS，并且生产截图中的 `&oklch(...)` 回归测试 PASS。

- [ ] **Step 7: 提交动画改动**

```bash
git add backend/app/orchestration/agents/course_resources/animation.py backend/app/orchestration/agents/course_resources/common.py backend/tests/test_course_resource_agent_contract.py
git commit -m "fix: reject malformed animation html"
```

### Task 3: 全量验证与生产验收

**Files:**
- Modify: 无；只验证 Task 1 和 Task 2 的提交

- [ ] **Step 1: 执行 Ruff 自动清理和格式化**

```bash
cd backend
uv run ruff check --fix app/orchestration/agents/course_resources/bilibili.py app/orchestration/agents/course_resources/video.py app/orchestration/agents/course_resources/animation.py tests/test_course_resource_agent_contract.py
uv run ruff format app/orchestration/agents/course_resources/bilibili.py app/orchestration/agents/course_resources/video.py app/orchestration/agents/course_resources/animation.py tests/test_course_resource_agent_contract.py
```

- [ ] **Step 2: 运行后端验证**

```bash
cd backend && uv run pytest tests/test_course_resource_agent_contract.py -q
cd backend && uv run pytest
```

Expected: 两条命令均 PASS。

- [ ] **Step 3: 检查工作区和差异**

```bash
git diff --check
git status --short
```

只允许出现本计划涉及的源代码、测试和提交文档；保留用户已有的 `docs/report-data-inventory.md`，删除本次产生且不再需要的临时验证文件。

- [ ] **Step 4: 部署到腾讯云**

在服务器执行已确认的部署命令：

```bash
cd /opt/onetree
/opt/onetree/bin/deploy
```

部署完成必须看到 `smoke checks passed` 和 `deploy completed`，并确认 compose 中 `backend`、`worker`、`nginx`、`postgres` 均为运行或健康状态。

- [ ] **Step 5: 生产回归**

重新发送 1.1 章节生成请求，同时读取 backend 日志，必须能看到平台请求/解析阶段日志、明确的 YouTube 异常类型以及 Bilibili 结果数量。页面验收标准：

- 视频：至少一个真实可打开的视频页面通过校验才显示可用；否则显示准确失败原因，不显示搜索页成功卡片。
- 动画：iframe 内不出现 `&oklch(...)`、CSS 代码残片或纯文字卡片；必须出现 brief 对应实体、关系线和步骤交互。

- [ ] **Step 6: 提交最终验证记录**

```bash
git diff --check
git log -3 --oneline
```

在交付说明中列出测试结果、生产部署提交、backend 日志证据和页面验收结果；未满足任一条时不得声明验收通过。
