# Quiz Feedback Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement a complete feedback evaluation loop for the Forest Quiz Page, updating the canopy metrics and growth tree on quiz submission, and adapting downstream AI resource generation based on quiz weaknesses.

**Architecture:** Extend backend grading stream to emit canopy overview and unlocked chapters/courses. Inject unconsumed weaknesses into profile weaknesses dynamically. Create a glassmorphic celebration overlay in React using Framer Motion to visualize growth tree development.

**Tech Stack:** FastAPI, SQLModel, React 18, Tailwind CSS, Framer Motion, LXGW WenKai, OKLCH, pytest.

---

### Task 1: Backend Weakness Resolution in `forest_service.py`

**Files:**
- Modify: `backend/app/services/forest_service.py`
- Test: `backend/tests/test_forest_api.py`

- [ ] **Step 1: Write the failing test for weakness resolution**
  Create/append `test_weakness_name_resolution` in `backend/tests/test_forest_api.py` to assert that when a weakness is analyzed, its knowledge point name is correctly resolved from either outline key knowledge points or learning path core knowledge points.

  ```python
  def test_weakness_name_resolution(tmp_path: Path) -> None:
      database_url = f"sqlite:///{tmp_path / 'forest-weakness-res.db'}"
      TestClient(create_app(database_url=database_url))
      user_uid = _seed_forest_data(database_url)
      engine = create_engine(database_url, connect_args={"check_same_thread": False})
      
      # Prepare quiz with a specific knowledge point ID "验收标准"
      questions = [{
          "question_id": "q1",
          "type": "single_choice",
          "prompt": "题目",
          "options": [],
          "points": 100,
          "knowledge_point_ids": ["验收标准"]
      }]
      grading_result = {
          "score": 50,
          "passed": False,
          "question_results": [{"question_id": "q1", "score": 0, "max_score": 100}],
          "summary": "不正确"
      }
      
      with Session(engine) as session:
          quiz = generate_or_read_quiz(session, user_uid, "year_3_course_2", "1", questions, regenerate=False)
          attempt, weaknesses = submit_quiz_attempt(
              session, user_uid, quiz.quiz_id, {"q1": "B"}, grading_result
          )
          
          # Assert that the weakness name matches "验收标准" resolved from mock outline sections
          assert len(weaknesses) == 1
          assert weaknesses[0].knowledge_point_id == "验收标准"
          assert weaknesses[0].knowledge_point_name == "验收标准"
  ```

- [ ] **Step 2: Run test to verify it fails**
  Run: `uv run pytest tests/test_forest_api.py::test_weakness_name_resolution -v`
  Expected: FAIL (assertion error: `knowledge_point_name == ""` or similar, since name is currently empty).

- [ ] **Step 3: Write minimal implementation in `forest_service.py`**
  Add `_resolve_knowledge_point_name` above `_analyze_weakness` and call it in `_analyze_weakness` to assign `knowledge_point_name`:

  ```python
  def _resolve_knowledge_point_name(
      session: Session,
      user_uid: str,
      course_node_id: str,
      chapter_id: str,
      kp_id: str,
  ) -> str:
      # 1. Try to find in course outline sections' key_knowledge_points
      outline = get_user_course_knowledge_outline(session, user_uid, course_node_id)
      if isinstance(outline, dict):
          sections = outline.get("sections", [])
          for sec in sections:
              if isinstance(sec, dict):
                  if sec.get("section_id") == chapter_id or not chapter_id:
                      kps = sec.get("key_knowledge_points", [])
                      if isinstance(kps, list):
                          for kp in kps:
                              if isinstance(kp, str) and (kp == kp_id or kp.lower() in kp_id.lower() or kp_id.lower() in kp.lower()):
                                  return kp

      # 2. Try to find in learning path core_knowledge_points
      year_paths = get_all_year_learning_paths(session, user_uid)
      found = _find_course(year_paths, course_node_id)
      if found is not None:
          _, _, course = found
          core_kps = course.get("core_knowledge_points", [])
          if isinstance(core_kps, list):
              for kp in core_kps:
                  if isinstance(kp, dict):
                      kpid = kp.get("knowledge_point_id", "")
                      kpname = kp.get("name", "")
                      if kpid == kp_id:
                          return kpname
                      if kpname and (kpname.lower() in kp_id.lower() or kp_id.lower() in kpname.lower()):
                          return kpname

      return kp_id
  ```

  And update `_analyze_weakness` to assign:
  ```python
  kp_name = _resolve_knowledge_point_name(session, user_uid, course_node_id, chapter_id, kp_id)
  ```

- [ ] **Step 4: Run test to verify it passes**
  Run: `uv run pytest tests/test_forest_api.py::test_weakness_name_resolution -v`
  Expected: PASS.

- [ ] **Step 5: Commit**
  Run:
  ```bash
  git add backend/app/services/forest_service.py backend/tests/test_forest_api.py
  git commit -m "feat: add weakness knowledge point name resolution"
  ```

---

### Task 2: Done Event Enhancements in `/attempts/stream` API

**Files:**
- Modify: `backend/app/api/forest.py`
- Test: `backend/tests/test_forest_api.py`

- [ ] **Step 1: Write the failing test for attempts stream done event**
  Create/append `test_submit_forest_quiz_attempt_stream_api_done_data` in `backend/tests/test_forest_api.py` to assert that the streaming `/quizzes/{quiz_id}/attempts/stream` endpoint returns `canopy_overview`, `next_unlocked_chapter_id`, and `next_course_id` inside the `done` event.

  ```python
  def test_submit_forest_quiz_attempt_stream_api_done_data(tmp_path: Path) -> None:
      database_url = f"sqlite:///{tmp_path / 'forest-attempt-stream-test.db'}"
      client = TestClient(create_app(database_url=database_url))
      user_uid = _seed_forest_data(database_url)
      engine = create_engine(database_url, connect_args={"check_same_thread": False})
      questions = [{"question_id": "q1", "type": "single_choice", "prompt": "题目", "options": [], "points": 100}]

      with Session(engine) as session:
          quiz = generate_or_read_quiz(session, user_uid, "year_3_course_2", "1", questions, regenerate=False)

      async def fake_grade_answers(*_args, **_kwargs):
          return {"score": 71, "passed": True, "question_results": [], "summary": "通过"}

      with patch("app.api.forest.grade_quiz_answers", fake_grade_answers):
          response = client.post(
              f"/api/forest/quizzes/{quiz.quiz_id}/attempts/stream",
              json={"answers": {"q1": "A"}},
              headers=_auth_headers(user_uid),
          )

      assert response.status_code == 200
      assert "event: done" in response.text
      assert "canopy_overview" in response.text
      assert "next_unlocked_chapter_id" in response.text
  ```

- [ ] **Step 2: Run test to verify it fails**
  Run: `uv run pytest tests/test_forest_api.py::test_submit_forest_quiz_attempt_stream_api_done_data -v`
  Expected: FAIL (assertion error: `canopy_overview` not found in response text).

- [ ] **Step 3: Modify `_extract_knowledge_point_ids` and done event in `forest.py`**
  Extend `_extract_knowledge_point_ids` to include key knowledge points:
  ```python
  kp_ids.extend(chapter.get("key_knowledge_points", []))
  ```

  And update `submit_quiz_attempt_stream` to import services, fetch canopy, calculate next unlocked items, and format the done SSE event payload:
  ```python
  from app.services.learning_path_service import get_canopy_overview, get_year_learning_path
  from app.services.forest_service import _chapter_ids_for_course, _next_chapter_id

  canopy = get_canopy_overview(session, current_user.uid)
  grade_year, chapter_ids = _chapter_ids_for_course(session, current_user.uid, quiz.course_node_id)
  next_chapter_id = _next_chapter_id(chapter_ids, quiz.chapter_id)

  next_unlocked_chapter_id = next_chapter_id if attempt.passed else None
  next_course_id = None
  if attempt.passed and not next_chapter_id:
      updated_path = get_year_learning_path(session, current_user.uid, grade_year)
      if updated_path:
          current_course = updated_path.get("current_learning_course", {})
          if current_course and current_course.get("course_node_id") != quiz.course_node_id:
              next_course_id = current_course.get("course_node_id")
  ```

- [ ] **Step 4: Run test to verify it passes**
  Run: `uv run pytest tests/test_forest_api.py::test_submit_forest_quiz_attempt_stream_api_done_data -v`
  Expected: PASS.

- [ ] **Step 5: Commit**
  Run:
  ```bash
  git add backend/app/api/forest.py backend/tests/test_forest_api.py
  git commit -m "feat: add canopy overview and unlocked markers to quiz attempts stream done event"
  ```

---

### Task 3: Weakness Injection in Chat stream in `orchestration.py`

**Files:**
- Modify: `backend/app/api/orchestration.py`
- Test: `backend/tests/test_forest_api.py`

- [ ] **Step 1: Write the failing test for weakness injection**
  Append `test_weakness_feedback_loop` to `backend/tests/test_forest_api.py`. Submit an attempt that fails a question with a weakness, verify it is created, then mock a profile loading scenario or assert that unconsumed weaknesses are correctly added when getting profile.

  ```python
  # (Test will be written in test_forest_api.py)
  # Assert unconsumed weaknesses are formatted into profile weaknesses.
  ```

- [ ] **Step 2: Run test to verify it fails**
  Run: `uv run pytest tests/test_forest_api.py::test_weakness_feedback_loop -v`
  Expected: FAIL.

- [ ] **Step 3: Implement weakness injection in `_stream_chat_events` in `orchestration.py`**
  After loading the user profile:
  ```python
  if profile and isinstance(profile, dict):
      from app.models import ChapterWeakness
      from sqlmodel import select
      stmt = select(ChapterWeakness).where(
          ChapterWeakness.user_uid == user_uid,
          ChapterWeakness.consumed == False
      )
      unconsumed_weaknesses = db_session.exec(stmt).all()
      if unconsumed_weaknesses:
          weak_names = []
          for w in unconsumed_weaknesses:
              if w.knowledge_point_name and w.knowledge_point_name not in weak_names:
                  weak_names.append(w.knowledge_point_name)
          if weak_names:
              existing_weaknesses = profile.get("weaknesses", "")
              if existing_weaknesses:
                  if isinstance(existing_weaknesses, list):
                      profile["weaknesses"] = list(set(existing_weaknesses + weak_names))
                  else:
                      existing_list = [item.strip() for item in str(existing_weaknesses).split("、") if item.strip()]
                      combined = list(set(existing_list + weak_names))
                      profile["weaknesses"] = "、".join(combined)
              else:
                  profile["weaknesses"] = "、".join(weak_names)
  ```

- [ ] **Step 4: Run test to verify it passes**
  Run: `uv run pytest tests/test_forest_api.py::test_weakness_feedback_loop -v`
  Expected: PASS.

- [ ] **Step 5: Commit**
  Run:
  ```bash
  git add backend/app/api/orchestration.py
  git commit -m "feat: inject unconsumed weaknesses into profile weaknesses during chat stream"
  ```

---

### Task 4: Weakness Consumption in `course_resources.py`

**Files:**
- Modify: `backend/app/orchestration/agents/course_resources.py`
- Test: `backend/tests/test_forest_api.py`

- [ ] **Step 1: Write verification step in `test_weakness_feedback_loop`**
  Verify that after calling `_persist_outline(user_uid, outline_data)`, all unconsumed weaknesses for the course are marked as consumed (`consumed = True`).

- [ ] **Step 2: Run test to verify it fails**
  Run: `uv run pytest tests/test_forest_api.py::test_weakness_feedback_loop -v`
  Expected: FAIL on the final assertion where it checks if weakness consumed is True.

- [ ] **Step 3: Implement weakness consumption in `_persist_outline`**
  Update `_persist_outline` in `backend/app/orchestration/agents/course_resources.py`:
  ```python
  def _persist_outline(user_id: str, outline: dict) -> None:
      with Session(get_engine()) as db_session:
          upsert_user_course_knowledge_outline(db_session, user_id, outline)
          course_id = outline.get("course_id", "")
          if course_id:
              from app.models import ChapterWeakness
              from sqlmodel import select
              stmt = select(ChapterWeakness).where(
                  ChapterWeakness.user_uid == user_id,
                  ChapterWeakness.course_node_id == course_id,
                  ChapterWeakness.consumed == False
              )
              unconsumed = db_session.exec(stmt).all()
              for w in unconsumed:
                  w.consumed = True
                  db_session.add(w)
              db_session.commit()
  ```

- [ ] **Step 4: Run test to verify it passes**
  Run: `uv run pytest tests/test_forest_api.py::test_weakness_feedback_loop -v`
  Expected: PASS.

- [ ] **Step 5: Commit**
  Run:
  ```bash
  git add backend/app/orchestration/agents/course_resources.py
  git commit -m "feat: consume weaknesses on successful resource outline persistence"
  ```

---

### Task 5: Frontend Glassmorphic `ForestQuizOverlay` Component

**Files:**
- Create: `frontend/src/components/forest/ForestQuizOverlay.tsx`
- Test: `frontend/src/components/forest/__tests__/ForestQuizOverlay.test.tsx`

- [ ] **Step 1: Write the frontend component tests**
  Create a test checking that when passed a mock `attempt` and `canopy_overview` data:
  - It renders the correct score and pass/fail state.
  - It displays the correct growth tree SVGs based on `growth_stage`.
  - It has "返回雨林" and "解锁下一章" CTA buttons.
  - It displays any weaknesses analyzed.

- [ ] **Step 2: Verify test fails**
  Run: `npm run test ForestQuizOverlay.test.tsx`
  Expected: FAIL (File or component does not exist).

- [ ] **Step 3: Write the component `ForestQuizOverlay.tsx`**
  Implement the overlay using OKLCH and LXGW WenKai typography (no Bold weight).
  Add spring scale animation to the Growth Tree SVG. Include prefers-reduced-motion check to fallback cleanly.

- [ ] **Step 4: Run tests and verify they pass**
  Run: `npm run test ForestQuizOverlay.test.tsx`
  Expected: PASS.

- [ ] **Step 5: Commit**
  Run:
  ```bash
  git add frontend/src/components/forest/ForestQuizOverlay.tsx
  git commit -m "feat: add glassmorphic ForestQuizOverlay component with growth tree animations"
  ```

---

### Task 6: Frontend Streaming Submission in `ForestQuizPage.tsx`

**Files:**
- Modify: `frontend/src/pages/forest/ForestQuizPage.tsx`

- [ ] **Step 1: Update page submission logic**
  Replace standard POST submission with event-stream handling of `/attempts/stream`.
  Track streaming status (`grading` -> `analyzing` -> `unlocking` -> `done`).
  Render status messages dynamically.

- [ ] **Step 2: Render `ForestQuizOverlay`**
  Upon receiving `done` event, set `isOverlayOpen` to true and pass attempt and canopy data to `ForestQuizOverlay`.

- [ ] **Step 3: Run page level tests and manual tests**
  Verify the quiz submission flow doesn't break existing page structures.

- [ ] **Step 4: Commit**
  Run:
  ```bash
  git add frontend/src/pages/forest/ForestQuizPage.tsx
  git commit -m "feat: integrate attempts streaming submission and overlay modal in ForestQuizPage"
  ```
