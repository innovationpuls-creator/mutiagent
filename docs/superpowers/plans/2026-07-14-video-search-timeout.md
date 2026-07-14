# Video Search Timeout Optimization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bound chapter video search latency and return explicit unavailable results when external video search does not finish within the per-section budget.

**Architecture:** Keep the existing Bilibili/YouTube search and quality rules. Add a section-level timeout around each section search task, preserve the existing semaphore, and convert timeout exceptions into the same persisted `unavailable` result shape used by quality failures.

**Tech Stack:** Python 3, asyncio, httpx, pytest, Ruff, SQLModel persistence.

---

### Task 1: Add the timeout contract test

**Files:**
- Modify: `backend/tests/test_course_resource_agent_contract.py` near the existing `run_section_video_search_agent` tests
- Modify: `backend/app/orchestration/agents/course_resources/common.py` only after the test is red

- [ ] **Step 1: Write the failing test**

Add a test that patches `_find_verified_video_from_search` to block on an `asyncio.Event`, sets the section budget to a small value, invokes `run_section_video_search_agent`, and asserts the section result is `status == "unavailable"` with a timeout failure reason instead of propagating `asyncio.TimeoutError`.

- [ ] **Step 2: Run the exact test to verify it fails**

Run: `cd backend && uv run pytest tests/test_course_resource_agent_contract.py::<exact_new_test_name> -q`

Expected: FAIL because the current implementation awaits `_find_verified_video_from_search` without a section-level timeout.

### Task 2: Implement bounded per-section video search

**Files:**
- Modify: `backend/app/orchestration/agents/course_resources/common.py:34-38`
- Modify: `backend/app/orchestration/agents/course_resources/video.py:1371-1449`
- Test: `backend/tests/test_course_resource_agent_contract.py`

- [ ] **Step 1: Add the exact section budget constant**

Add a named constant beside the existing video timeout constants, with the test-defined small value patched by `monkeypatch` during the contract test. Keep the production value below the Nginx `proxy_read_timeout` after the existing 3-section concurrency is applied.

- [ ] **Step 2: Wrap each section search in `asyncio.wait_for`**

Inside `generate_video_links`, wrap the existing two-attempt verification loop with `asyncio.wait_for(..., timeout=_VIDEO_SECTION_TIMEOUT_SECONDS)`. Catch `asyncio.TimeoutError`, log the exact section ID and elapsed budget, and return the existing unavailable payload with a timeout-specific `failure_reason`.

- [ ] **Step 3: Keep section failures isolated**

Do not cancel the outer `asyncio.gather`. Each `_limited_video` task must resolve to its own `(section_id, video_value)` tuple, including timeout results, so successful sections still persist their links.

- [ ] **Step 4: Run the exact test to verify it passes**

Run: `cd backend && uv run pytest tests/test_course_resource_agent_contract.py::<exact_new_test_name> -q`

Expected: PASS.

### Task 3: Add observability and regression coverage

**Files:**
- Modify: `backend/app/orchestration/agents/course_resources/video.py`
- Test: `backend/tests/test_course_resource_agent_contract.py`

- [ ] **Step 1: Add tests for timeout logging fields and successful sections**

Use `caplog` and two sections: make one section time out and one return a valid video. Assert the timeout log contains the exact section ID and that the successful section remains `available`.

- [ ] **Step 2: Run the focused video-search contract tests**

Run: `cd backend && uv run pytest tests/test_course_resource_agent_contract.py -k 'video_search_agent or verified_search or video_timeout' -q`

Expected: all selected tests pass.

- [ ] **Step 3: Run Ruff on modified Python files**

Run: `cd backend && uv run ruff check --fix app/orchestration/agents/course_resources/common.py app/orchestration/agents/course_resources/video.py tests/test_course_resource_agent_contract.py && uv run ruff format app/orchestration/agents/course_resources/common.py app/orchestration/agents/course_resources/video.py tests/test_course_resource_agent_contract.py`

Expected: exit code 0 with no remaining Ruff errors.

### Task 4: Verify the complete backend contract

**Files:**
- Verify: `backend/app/orchestration/agents/course_resources/common.py`
- Verify: `backend/app/orchestration/agents/course_resources/video.py`
- Verify: `backend/tests/test_course_resource_agent_contract.py`

- [ ] **Step 1: Run the resource-agent contract test file**

Run: `cd backend && uv run pytest tests/test_course_resource_agent_contract.py -q`

Expected: exit code 0 and zero failures.

- [ ] **Step 2: Inspect the final diff**

Run: `git diff --check && git diff -- backend/app/orchestration/agents/course_resources/common.py backend/app/orchestration/agents/course_resources/video.py backend/tests/test_course_resource_agent_contract.py`

Expected: only timeout-boundary, timeout-observability, and regression-test changes are present; the pre-existing untracked `docs/report-data-inventory.md` remains untouched.
