# Aliyun Bilibili Video Search Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace only the video Agent search transport with auditable DashScope native Bilibili search sources.

**Architecture:** Add one focused DashScope search-source adapter and call it from the existing verified video search path. Preserve existing Bilibili URL and metadata verification plus chapter hard-failure behavior; do not alter global LLM factories or other agents.

**Tech Stack:** Python 3.11+, asyncio, DashScope SDK 1.26.2, pytest, Ruff.

---

### Task 1: DashScope-native Bilibili source search

**Files:**
- Create: `backend/app/orchestration/agents/course_resources/aliyun_bilibili_search.py`
- Modify: `backend/app/orchestration/agents/course_resources/video.py`
- Modify: `backend/app/orchestration/agents/course_resources/__init__.py`
- Test: `backend/tests/test_course_resource_agent_contract.py`

- [ ] **Step 1: Write failing adapter-contract tests**

Add tests that monkeypatch `dashscope.Generation.call` and assert the adapter passes the existing `LLM_API_KEY` and `LLM_MODEL`, uses `enable_search=True`, `result_format="message"`, and sends exact `forced_search`, `turbo`, `enable_source`, `assigned_site_list`, and `prompt_intervene` fields. Assert parsing uses `output.search_info.search_results` and emits only the exact `title`, `url`, `site_name`, and `index` source values.

- [ ] **Step 2: Run adapter tests and verify RED**

Run:

```bash
cd backend
uv run pytest tests/test_course_resource_agent_contract.py -k 'aliyun_bilibili_search' -q
```

Expected: tests fail because the adapter does not exist.

- [ ] **Step 3: Implement the minimal adapter**

Implement an async function that builds the exact approved request and calls `dashscope.Generation.call` through `asyncio.to_thread`. Read only `response.output.search_info["search_results"]`; return an empty list for non-OK responses, missing `search_info`, or malformed result items. Do not parse URLs from response text.

- [ ] **Step 4: Write failing video-Agent integration tests**

Add tests proving `_find_verified_video_from_search` obtains sources from the adapter rather than `_search_bilibili_video_results`/`_search_youtube_video_results`, rejects non-exact Bilibili URLs, verifies exact URLs with `_verify_bilibili_video_metadata`, preserves source ordering, and returns no video when DashScope returns no auditable sources.

- [ ] **Step 5: Run integration tests and verify RED**

Run the exact new node IDs with `uv run pytest ... -q`; expected failure must show the old scraper path was called or the new adapter path was not called.

- [ ] **Step 6: Replace only the search transport**

Update the verified search function to construct the semantic search scope from exact `outline`, `section`, and `video_briefs` fields and call the adapter. Preserve `_normalized_video_quality_issue_async`, exact Bilibili URL validation, metadata verification, result normalization, persistence, concurrency limits, and whole-chapter hard failure. Remove only imports/helpers made unused by this transport replacement.

- [ ] **Step 7: Run focused tests and verify GREEN**

Run:

```bash
cd backend
uv run pytest tests/test_course_resource_agent_contract.py -k 'video or aliyun_bilibili_search' -q
```

Expected: all selected tests pass.

- [ ] **Step 8: Format and run full backend contract regression**

Run:

```bash
cd backend
uv run ruff check --fix app/orchestration/agents/course_resources tests/test_course_resource_agent_contract.py
uv run ruff format app/orchestration/agents/course_resources tests/test_course_resource_agent_contract.py
uv run pytest tests/test_course_resource_agent_contract.py tests/test_agent_prompt_contracts.py tests/test_agent_contract_models.py tests/test_orchestration_contract_guards.py tests/test_orchestration_llm.py -q
```

Expected: Ruff clean and all tests pass.

- [ ] **Step 9: Report without committing**

Return changed files, RED/GREEN commands and counts, remaining concerns, and `git diff --check` result. Do not commit, push, deploy, or modify files outside the listed scope.
