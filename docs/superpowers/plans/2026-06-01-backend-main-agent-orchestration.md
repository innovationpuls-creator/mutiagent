# Backend Main Agent Orchestration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the old chatflow route-first orchestration with a main-agent-led session API that can call intent, profile, and learning path agents, persist agent conversations, save learning paths, stream trace events, and render results in the existing frontend chat UI.

**Architecture:** Add explicit backend contracts for main-agent control JSON and learning path JSON, store Dify conversation IDs in a generic `useragentconversation` table, and execute validated agent plans through small orchestration modules. Keep the existing profile agent output contract intact, add a one-call learning path flow, then update the frontend to consume `/api/orchestration/sessions/*` and render agent traces plus learning path cards.

**Tech Stack:** FastAPI, SQLModel, Pydantic, LangGraph-compatible orchestration modules, Dify Chatflow API, pytest, React 18, TypeScript, Vite, styled-components, Vitest.

---

## File Structure

Backend files to modify:

- `backend/app/models.py`: add `UserAgentConversation` and `UserLearningPath`.
- `backend/app/schemas.py`: add session API schemas, main-agent response schemas, trace schemas, and learning path read schemas.
- `backend/app/orchestration/dify_client.py`: load `DIFY_CHAT_API_KEY` and `DIFY_LEARNING_PATH_AGENT_API_KEY`; support Dify `inputs`.
- `backend/app/orchestration/state.py`: replace the old profile-only state fields with session-oriented state fields.
- `backend/app/orchestration/graph.py`: keep this file as the orchestration entry point, delegating parsing and execution to focused modules.
- `backend/app/api/orchestration.py`: replace old chatflow route handlers with new sessions route handlers and streaming route handlers.
- `backend/app/main.py`: include the learning path router.

Backend files to create:

- `backend/app/orchestration/response_parser.py`: parse Dify `answer` JSON.
- `backend/app/orchestration/agent_plan.py`: Pydantic models and validation for main-agent control JSON and learning path JSON.
- `backend/app/orchestration/agent_executor.py`: execute validated main-agent call plans.
- `backend/app/services/agent_conversation_service.py`: persist Dify conversation IDs by `user_uid + agent_key`.
- `backend/app/services/learning_path_service.py`: persist and read latest learning path.
- `backend/app/api/learning_path.py`: expose `GET /api/learning-path/me`.
- `backend/tests/test_agent_plan.py`: contract tests for main-agent and learning path JSON validation.
- `backend/tests/test_agent_conversation_service.py`: persistence tests for generic agent conversations.
- `backend/tests/test_learning_path_service.py`: persistence tests for learning paths.
- `backend/tests/test_sessions_api.py`: API and streaming tests for session orchestration.

Frontend files to modify:

- `frontend/src/types/chat.ts`: add main-agent message, learning path result, session answer, and trace event types.
- `frontend/src/api/orchestration.ts`: switch to `/api/orchestration/sessions/*` and parse new stream events.
- `frontend/src/onboarding/chatReducer.ts`: store learning path results on assistant messages.
- `frontend/src/components/onboarding/AiGreetingInput.tsx`: map new stream events to existing chat flow and right-side agent panel.
- `frontend/src/components/onboarding/AssistantMessage.tsx`: render main-agent `question_box` when present.

Frontend files to create:

- `frontend/src/api/learningPath.ts`: read latest learning path.
- `frontend/src/components/learning/LearningPathCard.tsx`: render structured learning path output.
- `frontend/src/components/learning/LearningPathCard.test.tsx`: verify all four sections render.
- `frontend/src/api/orchestration.session.test.ts`: verify new session API request and stream parsing behavior.

---

### Task 1: Backend Models And Persistence Services

**Files:**
- Modify: `backend/app/models.py`
- Create: `backend/app/services/agent_conversation_service.py`
- Create: `backend/app/services/learning_path_service.py`
- Test: `backend/tests/test_agent_conversation_service.py`
- Test: `backend/tests/test_learning_path_service.py`

- [ ] **Step 1: Write failing tests for generic agent conversation persistence**

Create `backend/tests/test_agent_conversation_service.py`:

```python
from __future__ import annotations

from pathlib import Path

from sqlmodel import Session, SQLModel, create_engine

from app.models import User
from app.services.agent_conversation_service import get_agent_conversation_id, upsert_agent_conversation


def build_session(tmp_path: Path) -> Session:
    engine = create_engine(f"sqlite:///{tmp_path / 'agent-conversation.db'}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    session = Session(engine)
    session.add(User(uid="user-1", username="测试用户", identifier="agent-conversation@example.com"))
    session.commit()
    return session


def test_upsert_agent_conversation_creates_and_updates_by_agent_key(tmp_path: Path) -> None:
    session = build_session(tmp_path)

    created = upsert_agent_conversation(
        session=session,
        user_uid="user-1",
        agent_key="main_agent",
        conversation_id="main-conv-1",
    )
    updated = upsert_agent_conversation(
        session=session,
        user_uid="user-1",
        agent_key="main_agent",
        conversation_id="main-conv-2",
    )

    assert created.user_uid == "user-1"
    assert updated.conversation_id == "main-conv-2"
    assert get_agent_conversation_id(session, "user-1", "main_agent") == "main-conv-2"
    assert get_agent_conversation_id(session, "user-1", "profile_agent") == ""
```

- [ ] **Step 2: Run the failing conversation service test**

Run:

```bash
cd backend
uv run pytest tests/test_agent_conversation_service.py -v
```

Expected: FAIL with `ModuleNotFoundError` for `app.services.agent_conversation_service` or missing `UserAgentConversation`.

- [ ] **Step 3: Write failing tests for learning path persistence**

Create `backend/tests/test_learning_path_service.py`:

```python
from __future__ import annotations

from pathlib import Path

from sqlmodel import Session, SQLModel, create_engine

from app.models import User
from app.services.learning_path_service import get_user_learning_path, upsert_user_learning_path


def build_session(tmp_path: Path) -> Session:
    engine = create_engine(f"sqlite:///{tmp_path / 'learning-path.db'}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    session = Session(engine)
    session.add(User(uid="user-1", username="路径用户", identifier="learning-path@example.com"))
    session.commit()
    return session


def test_upsert_user_learning_path_saves_latest_path_data(tmp_path: Path) -> None:
    session = build_session(tmp_path)
    first = {"learning_goal": {"target_course_or_skill": "Python"}}
    second = {"learning_goal": {"target_course_or_skill": "数据结构"}}

    upsert_user_learning_path(session, "user-1", first)
    saved = upsert_user_learning_path(session, "user-1", second)
    loaded = get_user_learning_path(session, "user-1")

    assert saved.path_data == second
    assert loaded is not None
    assert loaded.path_data["learning_goal"]["target_course_or_skill"] == "数据结构"
```

- [ ] **Step 4: Run the failing learning path service test**

Run:

```bash
cd backend
uv run pytest tests/test_learning_path_service.py -v
```

Expected: FAIL with `ModuleNotFoundError` for `app.services.learning_path_service` or missing `UserLearningPath`.

- [ ] **Step 5: Add SQLModel models**

Modify `backend/app/models.py` by adding these classes after `UserDifyConversation`:

```python
class UserAgentConversation(SQLModel, table=True):
    user_uid: str = Field(foreign_key="user.uid", primary_key=True)
    agent_key: str = Field(primary_key=True, max_length=64)
    conversation_id: str = Field(default="")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class UserLearningPath(SQLModel, table=True):
    user_uid: str = Field(foreign_key="user.uid", primary_key=True)
    path_data: dict = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
```

- [ ] **Step 6: Implement agent conversation service**

Create `backend/app/services/agent_conversation_service.py`:

```python
from __future__ import annotations

from datetime import datetime, timezone

from sqlmodel import Session

from app.models import UserAgentConversation


def get_agent_conversation_id(session: Session, user_uid: str, agent_key: str) -> str:
    stored = session.get(UserAgentConversation, (user_uid, agent_key))
    if stored is None:
        return ""
    return stored.conversation_id


def upsert_agent_conversation(
    session: Session,
    user_uid: str,
    agent_key: str,
    conversation_id: str,
) -> UserAgentConversation:
    stored = session.get(UserAgentConversation, (user_uid, agent_key))
    now = datetime.now(timezone.utc)
    if stored is None:
        stored = UserAgentConversation(
            user_uid=user_uid,
            agent_key=agent_key,
            conversation_id=conversation_id,
            created_at=now,
            updated_at=now,
        )
    else:
        stored.conversation_id = conversation_id
        stored.updated_at = now

    session.add(stored)
    session.commit()
    session.refresh(stored)
    return stored
```

- [ ] **Step 7: Implement learning path service**

Create `backend/app/services/learning_path_service.py`:

```python
from __future__ import annotations

from datetime import datetime, timezone

from sqlmodel import Session

from app.models import UserLearningPath


def get_user_learning_path(session: Session, user_uid: str) -> UserLearningPath | None:
    return session.get(UserLearningPath, user_uid)


def upsert_user_learning_path(session: Session, user_uid: str, path_data: dict) -> UserLearningPath:
    stored = session.get(UserLearningPath, user_uid)
    now = datetime.now(timezone.utc)
    if stored is None:
        stored = UserLearningPath(
            user_uid=user_uid,
            path_data=path_data,
            created_at=now,
            updated_at=now,
        )
    else:
        stored.path_data = path_data
        stored.updated_at = now

    session.add(stored)
    session.commit()
    session.refresh(stored)
    return stored
```

- [ ] **Step 8: Run persistence tests**

Run:

```bash
cd backend
uv run pytest tests/test_agent_conversation_service.py tests/test_learning_path_service.py -v
```

Expected: PASS for both test files.

- [ ] **Step 9: Commit persistence layer**

```bash
git add backend/app/models.py backend/app/services/agent_conversation_service.py backend/app/services/learning_path_service.py backend/tests/test_agent_conversation_service.py backend/tests/test_learning_path_service.py
git commit -m "feat: add agent conversation and learning path persistence"
```

---

### Task 2: Backend Agent Contracts And Parsers

**Files:**
- Create: `backend/app/orchestration/response_parser.py`
- Create: `backend/app/orchestration/agent_plan.py`
- Modify: `backend/app/orchestration/dify_client.py`
- Test: `backend/tests/test_agent_plan.py`

- [ ] **Step 1: Write failing contract tests**

Create `backend/tests/test_agent_plan.py`:

```python
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.orchestration.agent_plan import (
    AgentCall,
    LearningPathResult,
    MainAgentResult,
    validate_call_graph,
)
from app.orchestration.response_parser import parse_json_answer


def test_parse_json_answer_accepts_plain_json() -> None:
    result = parse_json_answer({"answer": "{\"response\":{\"user_message\":\"你好\",\"question_box\":null},\"control\":{\"action\":\"reply_only\",\"calls\":[]}}"})

    assert result["response"]["user_message"] == "你好"


def test_main_agent_result_requires_known_agent_key() -> None:
    with pytest.raises(ValidationError):
        MainAgentResult.model_validate(
            {
                "response": {"user_message": "处理中", "question_box": None},
                "control": {
                    "action": "call_agents",
                    "calls": [
                        {
                            "call_id": "bad_call",
                            "agent_key": "unknown_agent",
                            "label": "未知",
                            "depends_on": [],
                            "parallel_group": None,
                            "agent_input": {},
                        }
                    ],
                },
            }
        )


def test_validate_call_graph_rejects_missing_dependency() -> None:
    call = AgentCall(
        call_id="learning_path",
        agent_key="learning_path_agent",
        label="学习路径",
        depends_on=["profile_missing"],
        parallel_group=None,
        agent_input={},
    )

    with pytest.raises(ValueError, match="depends_on references unknown call_id"):
        validate_call_graph([call])


def test_learning_path_result_requires_four_sections() -> None:
    result = LearningPathResult.model_validate(
        {
            "learning_goal": {
                "target_course_or_skill": "数据结构",
                "target_completion_time": "大二结束前",
                "goal_type": "课程学习",
                "desired_outcome": "能完成课程项目",
            },
            "gap_analysis": {
                "current_mastered_content": ["Python 基础"],
                "current_weaknesses": ["算法复杂度"],
                "required_capabilities": ["线性表", "树", "图"],
                "main_gaps": ["缺少系统刷题"],
            },
            "foundation_path": {
                "stages": [
                    {
                        "stage_id": "year_1",
                        "stage_name": "大一基础",
                        "learning_goal": "打牢编程基础",
                        "learning_content": ["Python", "C 语言"],
                        "learning_tasks": ["完成 20 个基础练习"],
                        "recommended_methods": ["课程学习"],
                        "completion_standard": ["能独立写小程序"],
                    }
                ]
            },
            "generated_path": {
                "overall_goal": "形成数据结构学习路径",
                "stage_routes": [{"stage_id": "year_1", "route_summary": "先补编程基础"}],
                "schedule": [{"period": "大一上", "focus": "编程基础", "milestone": "完成基础项目"}],
                "task_checklist": ["每周练习 3 次"],
                "recommended_resource_types": ["教材", "题库"],
                "stage_acceptance_criteria": [{"stage_id": "year_1", "criteria": ["完成项目"]}],
                "next_actions": ["本周开始复习数组和链表"],
            },
        }
    )

    assert result.learning_goal.target_course_or_skill == "数据结构"
```

- [ ] **Step 2: Run contract tests and confirm failure**

Run:

```bash
cd backend
uv run pytest tests/test_agent_plan.py -v
```

Expected: FAIL with missing `agent_plan` and `response_parser` modules.

- [ ] **Step 3: Implement JSON response parser**

Create `backend/app/orchestration/response_parser.py`:

```python
from __future__ import annotations

import json
import re


class DifyAnswerParseError(ValueError):
    pass


def parse_json_answer(raw: dict) -> dict:
    raw_answer = raw.get("answer", "")
    if not isinstance(raw_answer, str):
        raise DifyAnswerParseError("Dify answer must be a string")

    cleaned = raw_answer.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", cleaned, flags=re.DOTALL)
    if fenced:
        cleaned = fenced.group(1).strip()

    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise DifyAnswerParseError("Dify answer is not valid JSON") from exc

    if not isinstance(parsed, dict):
        raise DifyAnswerParseError("Dify answer JSON must be an object")
    return parsed
```

- [ ] **Step 4: Implement agent plan and learning path models**

Create `backend/app/orchestration/agent_plan.py`:

```python
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


AgentKey = Literal["intent_recognition_agent", "profile_agent", "learning_path_agent"]
AgentAction = Literal["reply_only", "call_agents", "final_answer"]
GoalType = Literal["考试", "课程学习", "项目实践", "能力提升", "就业准备", "其他"]


class QuestionBox(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str
    options: list[str]


class MainAgentResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_message: str = Field(min_length=1)
    question_box: QuestionBox | None


class AgentCall(BaseModel):
    model_config = ConfigDict(extra="forbid")

    call_id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    agent_key: AgentKey
    label: str = Field(min_length=1)
    depends_on: list[str] = Field(default_factory=list)
    parallel_group: str | None
    agent_input: dict


class MainAgentControl(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: AgentAction
    calls: list[AgentCall]

    @field_validator("calls")
    @classmethod
    def validate_calls_for_action(cls, calls: list[AgentCall], info: object) -> list[AgentCall]:
        data = getattr(info, "data", {})
        action = data.get("action")
        if action in {"reply_only", "final_answer"} and calls:
            raise ValueError("calls must be empty when action is reply_only or final_answer")
        if action == "call_agents" and not calls:
            raise ValueError("calls must not be empty when action is call_agents")
        return calls


class MainAgentResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    response: MainAgentResponse
    control: MainAgentControl


def validate_call_graph(calls: list[AgentCall]) -> None:
    ids = {call.call_id for call in calls}
    if len(ids) != len(calls):
        raise ValueError("call_id values must be unique")
    for call in calls:
        for dependency in call.depends_on:
            if dependency not in ids:
                raise ValueError("depends_on references unknown call_id")
            if dependency == call.call_id:
                raise ValueError("depends_on must not reference the same call_id")


class LearningGoal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_course_or_skill: str = Field(min_length=1)
    target_completion_time: str = Field(min_length=1)
    goal_type: GoalType
    desired_outcome: str = Field(min_length=1)


class GapAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_mastered_content: list[str] = Field(min_length=1)
    current_weaknesses: list[str] = Field(min_length=1)
    required_capabilities: list[str] = Field(min_length=1)
    main_gaps: list[str] = Field(min_length=1)


class FoundationStage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stage_id: str = Field(min_length=1)
    stage_name: str = Field(min_length=1)
    learning_goal: str = Field(min_length=1)
    learning_content: list[str] = Field(min_length=1)
    learning_tasks: list[str] = Field(min_length=1)
    recommended_methods: list[str] = Field(min_length=1)
    completion_standard: list[str] = Field(min_length=1)


class FoundationPath(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stages: list[FoundationStage] = Field(min_length=1)


class StageRoute(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stage_id: str = Field(min_length=1)
    route_summary: str = Field(min_length=1)


class ScheduleItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    period: str = Field(min_length=1)
    focus: str = Field(min_length=1)
    milestone: str = Field(min_length=1)


class StageAcceptanceCriteria(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stage_id: str = Field(min_length=1)
    criteria: list[str] = Field(min_length=1)


class GeneratedPath(BaseModel):
    model_config = ConfigDict(extra="forbid")

    overall_goal: str = Field(min_length=1)
    stage_routes: list[StageRoute] = Field(min_length=1)
    schedule: list[ScheduleItem] = Field(min_length=1)
    task_checklist: list[str] = Field(min_length=1)
    recommended_resource_types: list[str] = Field(min_length=1)
    stage_acceptance_criteria: list[StageAcceptanceCriteria] = Field(min_length=1)
    next_actions: list[str] = Field(min_length=1)


class LearningPathResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    learning_goal: LearningGoal
    gap_analysis: GapAnalysis
    foundation_path: FoundationPath
    generated_path: GeneratedPath
```

- [ ] **Step 5: Extend Dify client with new environment keys and inputs**

Modify `backend/app/orchestration/dify_client.py`:

```python
DIFY_CHAT_API_KEY = os.getenv("DIFY_CHAT_API_KEY", "")
DIFY_LEARNING_PATH_AGENT_API_KEY = os.getenv("DIFY_LEARNING_PATH_AGENT_API_KEY", "")
```

Change `chat_blocking` signature and payload:

```python
    async def chat_blocking(
        self,
        query: str,
        user_id: str,
        conversation_id: str = "",
        inputs: dict | None = None,
    ) -> DifyResponse:
        url = f"{self._base_url}/chat-messages"
        payload = {
            "inputs": inputs or {},
            "query": query,
            "response_mode": "blocking",
            "conversation_id": conversation_id,
            "user": user_id,
        }
```

Change `chat_streaming` signature and payload in the same way if the existing implementation continues to expose streaming Dify calls.

- [ ] **Step 6: Run contract tests**

Run:

```bash
cd backend
uv run pytest tests/test_agent_plan.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit backend contracts**

```bash
git add backend/app/orchestration/response_parser.py backend/app/orchestration/agent_plan.py backend/app/orchestration/dify_client.py backend/tests/test_agent_plan.py
git commit -m "feat: add main agent orchestration contracts"
```

---

### Task 3: Backend Agent Executor

**Files:**
- Create: `backend/app/orchestration/agent_executor.py`
- Modify: `backend/app/orchestration/state.py`
- Test: `backend/tests/test_agent_executor.py`

- [ ] **Step 1: Write failing executor tests**

Create `backend/tests/test_agent_executor.py`:

```python
from __future__ import annotations

import asyncio

import pytest
from sqlmodel import Session, SQLModel, create_engine

from app.models import User, UserProfile
from app.orchestration.agent_executor import AgentExecutor, AgentExecutionError
from app.orchestration.dify_client import DifyResponse


class FakeDifyClient:
    def __init__(self, answer: str, conversation_id: str) -> None:
        self.answer = answer
        self.conversation_id = conversation_id
        self.calls: list[dict] = []

    async def chat_blocking(self, query: str, user_id: str, conversation_id: str = "", inputs: dict | None = None) -> DifyResponse:
        self.calls.append({"query": query, "user_id": user_id, "conversation_id": conversation_id, "inputs": inputs or {}})
        return DifyResponse(
            answer=self.answer,
            conversation_id=self.conversation_id,
            task_id="task-1",
            message_id="message-1",
            raw={"answer": self.answer, "conversation_id": self.conversation_id},
        )


def build_session() -> Session:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    session = Session(engine)
    session.add(User(uid="user-1", username="执行用户", identifier="executor@example.com"))
    session.commit()
    return session


def test_learning_path_requires_completed_profile() -> None:
    session = build_session()
    executor = AgentExecutor(
        session=session,
        user_uid="user-1",
        clients={
            "learning_path_agent": FakeDifyClient("{}", "learning-conv"),
        },
    )

    with pytest.raises(AgentExecutionError, match="基础画像"):
        asyncio.run(executor.execute_learning_path({"target": "数据结构"}))


def test_learning_path_passes_profile_and_request_inputs() -> None:
    session = build_session()
    session.add(
        UserProfile(
            user_uid="user-1",
            profile_data={"type": "basic_profile", "stage": "generated", "text": "画像"},
            profile_text="画像",
        )
    )
    session.commit()
    learning_path = (
        '{"learning_goal":{"target_course_or_skill":"数据结构","target_completion_time":"大二结束前",'
        '"goal_type":"课程学习","desired_outcome":"完成课程项目"},'
        '"gap_analysis":{"current_mastered_content":["Python"],"current_weaknesses":["复杂度"],'
        '"required_capabilities":["树"],"main_gaps":["练习少"]},'
        '"foundation_path":{"stages":[{"stage_id":"year_1","stage_name":"大一基础","learning_goal":"补基础",'
        '"learning_content":["编程"],"learning_tasks":["练习"],"recommended_methods":["课程"],'
        '"completion_standard":["项目"]}]},'
        '"generated_path":{"overall_goal":"学会数据结构","stage_routes":[{"stage_id":"year_1","route_summary":"补基础"}],'
        '"schedule":[{"period":"大一上","focus":"编程","milestone":"项目"}],"task_checklist":["练习"],'
        '"recommended_resource_types":["教材"],"stage_acceptance_criteria":[{"stage_id":"year_1","criteria":["项目"]}],'
        '"next_actions":["学习数组"]}}'
    )
    client = FakeDifyClient(learning_path, "learning-conv")
    executor = AgentExecutor(session=session, user_uid="user-1", clients={"learning_path_agent": client})

    result = asyncio.run(executor.execute_learning_path({"target_course_or_skill": "数据结构"}))

    assert result["learning_goal"]["target_course_or_skill"] == "数据结构"
    assert client.calls[0]["inputs"]["user_profile"]["type"] == "basic_profile"
    assert client.calls[0]["inputs"]["learning_path_request"]["target_course_or_skill"] == "数据结构"
```

- [ ] **Step 2: Run executor tests and confirm failure**

Run:

```bash
cd backend
uv run pytest tests/test_agent_executor.py -v
```

Expected: FAIL with missing `agent_executor`.

- [ ] **Step 3: Implement session state**

Replace `backend/app/orchestration/state.py` with:

```python
from __future__ import annotations

from typing import TypedDict


class OrchestrationState(TypedDict):
    query: str
    user_id: str
    session_id: str
    mode: str
    main_raw: dict
    main_result: dict
    agent_results: dict
    answer: dict
    profile: dict | None
    learning_path: dict | None
    completed: bool
    error: str
```

- [ ] **Step 4: Implement agent executor**

Create `backend/app/orchestration/agent_executor.py`:

```python
from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator

from sqlmodel import Session

from app.models import UserProfile
from app.orchestration.agent_plan import AgentCall, LearningPathResult
from app.orchestration.dify_client import (
    DIFY_INTENT_RECOGNITION_API_KEY,
    DIFY_LEARNING_PATH_AGENT_API_KEY,
    DIFY_PROFILE_AGENT_API_KEY,
    DifyClient,
)
from app.orchestration.response_parser import parse_json_answer
from app.services.agent_conversation_service import get_agent_conversation_id, upsert_agent_conversation
from app.services.learning_path_service import upsert_user_learning_path
from app.services.profile_service import upsert_user_profile


class AgentExecutionError(RuntimeError):
    pass


class AgentExecutor:
    def __init__(self, session: Session, user_uid: str, clients: dict[str, DifyClient] | None = None) -> None:
        self.session = session
        self.user_uid = user_uid
        self.clients = clients or {
            "intent_recognition_agent": DifyClient(api_key=DIFY_INTENT_RECOGNITION_API_KEY),
            "profile_agent": DifyClient(api_key=DIFY_PROFILE_AGENT_API_KEY),
            "learning_path_agent": DifyClient(api_key=DIFY_LEARNING_PATH_AGENT_API_KEY),
        }

    async def execute_call(self, call: AgentCall) -> dict:
        if call.agent_key == "intent_recognition_agent":
            return await self.execute_intent(call.agent_input)
        if call.agent_key == "profile_agent":
            return await self.execute_profile(call.agent_input)
        if call.agent_key == "learning_path_agent":
            return await self.execute_learning_path(call.agent_input)
        raise AgentExecutionError(f"Unsupported agent_key: {call.agent_key}")

    async def execute_intent(self, agent_input: dict) -> dict:
        client = self.clients["intent_recognition_agent"]
        conversation_id = get_agent_conversation_id(self.session, self.user_uid, "intent_recognition_agent")
        response = await client.chat_blocking(
            query=str(agent_input.get("query", "")),
            user_id=self.user_uid,
            conversation_id=conversation_id,
            inputs=agent_input,
        )
        upsert_agent_conversation(self.session, self.user_uid, "intent_recognition_agent", response.conversation_id)
        return {"answer": response.answer, "raw": response.raw}

    async def execute_profile(self, agent_input: dict) -> dict:
        client = self.clients["profile_agent"]
        conversation_id = get_agent_conversation_id(self.session, self.user_uid, "profile_agent")
        response = await client.chat_blocking(
            query=str(agent_input.get("query", "")),
            user_id=self.user_uid,
            conversation_id=conversation_id,
            inputs={},
        )
        upsert_agent_conversation(self.session, self.user_uid, "profile_agent", response.conversation_id)
        parsed = parse_json_answer(response.raw)
        if parsed.get("type") == "basic_profile" and parsed.get("stage") == "generated":
            upsert_user_profile(self.session, self.user_uid, parsed)
        return parsed

    async def execute_learning_path(self, agent_input: dict) -> dict:
        profile = self.session.get(UserProfile, self.user_uid)
        if profile is None:
            raise AgentExecutionError("请先完成基础画像，再生成学习路径。")
        if profile.profile_data.get("type") != "basic_profile" or profile.profile_data.get("stage") != "generated":
            raise AgentExecutionError("请先完成基础画像，再生成学习路径。")

        client = self.clients["learning_path_agent"]
        conversation_id = get_agent_conversation_id(self.session, self.user_uid, "learning_path_agent")
        response = await client.chat_blocking(
            query="生成学习路径",
            user_id=self.user_uid,
            conversation_id=conversation_id,
            inputs={
                "user_profile": profile.profile_data,
                "learning_path_request": agent_input,
            },
        )
        upsert_agent_conversation(self.session, self.user_uid, "learning_path_agent", response.conversation_id)
        parsed = parse_json_answer(response.raw)
        result = LearningPathResult.model_validate(parsed).model_dump()
        upsert_user_learning_path(self.session, self.user_uid, result)
        return result

    async def execute_calls(self, calls: list[AgentCall]) -> dict[str, dict]:
        results: dict[str, dict] = {}
        pending = {call.call_id: call for call in calls}
        while pending:
            ready = [
                call for call in pending.values()
                if all(dependency in results for dependency in call.depends_on)
            ]
            if not ready:
                raise AgentExecutionError("Agent call graph has unresolved dependencies")
            batch = await asyncio.gather(*(self.execute_call(call) for call in ready))
            for call, result in zip(ready, batch, strict=True):
                results[call.call_id] = result
                pending.pop(call.call_id)
        return results
```

- [ ] **Step 5: Run executor tests**

Run:

```bash
cd backend
uv run pytest tests/test_agent_executor.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit executor**

```bash
git add backend/app/orchestration/state.py backend/app/orchestration/agent_executor.py backend/tests/test_agent_executor.py
git commit -m "feat: execute validated agent calls"
```

---

### Task 4: Backend Session API And Streaming Events

**Files:**
- Modify: `backend/app/schemas.py`
- Modify: `backend/app/api/orchestration.py`
- Create: `backend/app/api/learning_path.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_sessions_api.py`

- [ ] **Step 1: Write failing sessions API tests**

Create `backend/tests/test_sessions_api.py`:

```python
from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from sqlmodel import Session, create_engine

from app.api import orchestration as orchestration_api
from app.main import create_app
from app.models import UserLearningPath


class ReplyOnlyGraph:
    async def ainvoke(self, state: dict, config: dict) -> dict:
        return {
            **state,
            "session_id": "session-1",
            "answer": {"user_message": "你好，我可以帮你规划学习。", "question_box": None},
            "agent_results": {},
            "profile": None,
            "learning_path": None,
            "completed": False,
            "error": "",
        }


def register(client: TestClient) -> tuple[str, str]:
    response = client.post(
        "/api/auth/register",
        json={
            "username": "会话用户",
            "identifier": "sessions@example.com",
            "password": "test-password-123",
            "confirm_password": "test-password-123",
        },
    )
    body = response.json()
    return body["access_token"], body["user"]["uid"]


def test_start_session_returns_main_agent_answer(tmp_path: Path, monkeypatch) -> None:
    database_url = f"sqlite:///{tmp_path / 'sessions.db'}"
    monkeypatch.setattr(orchestration_api, "graph", ReplyOnlyGraph())
    client = TestClient(create_app(database_url=database_url))
    token, _ = register(client)

    response = client.post(
        "/api/orchestration/sessions/start",
        headers={"Authorization": f"Bearer {token}"},
        json={"query": "你好"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["session_id"] == "session-1"
    assert body["answer"]["user_message"] == "你好，我可以帮你规划学习。"
    assert body["learning_path"] is None


def test_get_learning_path_me_returns_saved_path(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'learning-path-api.db'}"
    client = TestClient(create_app(database_url=database_url))
    token, uid = register(client)
    engine = create_engine(database_url, connect_args={"check_same_thread": False})
    with Session(engine) as session:
        session.add(UserLearningPath(user_uid=uid, path_data={"learning_goal": {"target_course_or_skill": "Python"}}))
        session.commit()

    response = client.get("/api/learning-path/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.json()["learning_path"]["learning_goal"]["target_course_or_skill"] == "Python"


def test_get_learning_path_me_returns_404_without_path(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'learning-path-api-404.db'}"
    client = TestClient(create_app(database_url=database_url))
    token, _ = register(client)

    response = client.get("/api/learning-path/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 404
    assert "还没有生成学习路径" in response.json()["detail"]
```

- [ ] **Step 2: Run sessions API tests and confirm failure**

Run:

```bash
cd backend
uv run pytest tests/test_sessions_api.py -v
```

Expected: FAIL because `/api/orchestration/sessions/start` and `/api/learning-path/me` do not exist.

- [ ] **Step 3: Add new response schemas**

Append to `backend/app/schemas.py`:

```python
class SessionStartRequest(BaseModel):
    query: str = Field(min_length=1, max_length=4000)


class SessionContinueRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=80)
    query: str = Field(min_length=1, max_length=4000)


class AgentQuestionBox(BaseModel):
    question: str
    options: list[str]


class AgentUserAnswer(BaseModel):
    user_message: str
    question_box: AgentQuestionBox | None = None


class AgentTraceStep(BaseModel):
    step_id: str
    agent_key: str
    label: str
    phase: str
    status: str
    message: str
    depends_on: list[str] = Field(default_factory=list)
    parallel_group: str | None = None


class SessionResponse(BaseModel):
    session_id: str
    answer: AgentUserAnswer
    agent_trace: list[AgentTraceStep] = Field(default_factory=list)
    completed: bool
    profile: dict | None = None
    learning_path: dict | None = None


class LearningPathReadResponse(BaseModel):
    learning_path: dict
    updated_at: datetime
```

- [ ] **Step 4: Rework orchestration API with session endpoints**

Modify `backend/app/api/orchestration.py` so `create_orchestration_router` exposes:

```python
@router.post("/sessions/start", response_model=SessionResponse)
async def start_session(
    payload: SessionStartRequest,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(session_dependency),
) -> SessionResponse:
    execution = registry.create(current_user.uid)
    state = await graph.ainvoke(
        _initial_state(payload.query, current_user.uid, execution.execution_id),
        _graph_config(execution),
    )
    if state.get("error"):
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=state["error"])
    return SessionResponse(
        session_id=state["session_id"],
        answer=state["answer"],
        agent_trace=state.get("agent_trace", []),
        completed=state.get("completed", False),
        profile=state.get("profile"),
        learning_path=state.get("learning_path"),
    )
```

Also add:

```python
@router.post("/sessions/continue", response_model=SessionResponse)
async def continue_session(
    payload: SessionContinueRequest,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(session_dependency),
) -> SessionResponse:
    execution = registry.get(payload.session_id)
    if execution is None or execution.user_id != current_user.uid:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="对话不存在")
    state = await graph.ainvoke(
        _initial_state(payload.query, current_user.uid, execution.execution_id),
        _graph_config(execution),
    )
    if state.get("error"):
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=state["error"])
    return SessionResponse(
        session_id=state["session_id"],
        answer=state["answer"],
        agent_trace=state.get("agent_trace", []),
        completed=state.get("completed", False),
        profile=state.get("profile"),
        learning_path=state.get("learning_path"),
    )
```

Keep the old route functions only if the implementation needs a temporary transition inside the same file. Do not expose them as the primary frontend path.

- [ ] **Step 5: Implement learning path read router**

Create `backend/app/api/learning_path.py`:

```python
from __future__ import annotations

from collections.abc import Callable, Generator

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from app.core.security import create_get_current_user
from app.models import User
from app.schemas import LearningPathReadResponse
from app.services.learning_path_service import get_user_learning_path

SessionDependency = Callable[[], Generator[Session, None, None]]


def create_learning_path_router(session_dependency: SessionDependency) -> APIRouter:
    router = APIRouter(prefix="/api/learning-path", tags=["learning-path"])
    get_current_user = create_get_current_user(session_dependency)

    @router.get("/me", response_model=LearningPathReadResponse)
    def read_my_learning_path(
        current_user: User = Depends(get_current_user),
        session: Session = Depends(session_dependency),
    ) -> LearningPathReadResponse:
        stored = get_user_learning_path(session, current_user.uid)
        if stored is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="还没有生成学习路径",
            )
        return LearningPathReadResponse(learning_path=stored.path_data, updated_at=stored.updated_at)

    return router
```

- [ ] **Step 6: Include learning path router**

Modify `backend/app/main.py`:

```python
from app.api.learning_path import create_learning_path_router
```

Inside `create_app` after profile router:

```python
    app.include_router(create_learning_path_router(create_session_dependency(engine)))
```

- [ ] **Step 7: Implement streaming endpoints**

Add streaming route handlers in `backend/app/api/orchestration.py`:

```python
@router.post("/sessions/start/stream")
async def start_session_stream(
    payload: SessionStartRequest,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(session_dependency),
) -> StreamingResponse:
    execution = registry.create(current_user.uid)
    state = _initial_state(payload.query, current_user.uid, execution.execution_id)
    return StreamingResponse(
        _stream_session_turn(execution, state, session),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
```

Add the matching continue stream route. `_stream_session_turn` must emit `agent_step_started`, `agent_step_completed`, `agent_step_failed`, `orchestration_completed`, and `orchestration_failed` events.

- [ ] **Step 8: Run API tests**

Run:

```bash
cd backend
uv run pytest tests/test_sessions_api.py -v
```

Expected: PASS.

- [ ] **Step 9: Run backend regression tests**

Run:

```bash
cd backend
uv run pytest -v
```

Expected: PASS. If old chatflow tests fail because old routes were intentionally replaced, update those tests to assert the new `/api/orchestration/sessions/*` behavior.

- [ ] **Step 10: Commit API layer**

```bash
git add backend/app/schemas.py backend/app/api/orchestration.py backend/app/api/learning_path.py backend/app/main.py backend/tests/test_sessions_api.py
git commit -m "feat: add main agent session APIs"
```

---

### Task 5: LangGraph Main-Agent Flow

**Files:**
- Modify: `backend/app/orchestration/graph.py`
- Test: `backend/tests/test_orchestration_graph.py`

- [ ] **Step 1: Replace old graph tests with main-agent flow tests**

Modify `backend/tests/test_orchestration_graph.py` to include:

```python
def test_graph_returns_reply_only_main_agent_answer() -> None:
    main = FakeDifyClient(
        [
            (
                '{"response":{"user_message":"你好，我会先了解你的目标。","question_box":null},'
                '"control":{"action":"reply_only","calls":[]}}'
            )
        ]
    )
    graph = create_orchestration_graph(main_client=main)
    result = asyncio.run(graph.ainvoke(make_state("你好"), {"configurable": {"thread_id": "graph-main-1"}}))

    assert result["answer"]["user_message"] == "你好，我会先了解你的目标。"
    assert result["completed"] is False
```

Add a second test for invalid JSON:

```python
def test_graph_sets_error_when_main_agent_json_is_invalid() -> None:
    main = FakeDifyClient(["不是 JSON"])
    graph = create_orchestration_graph(main_client=main)
    result = asyncio.run(graph.ainvoke(make_state("你好"), {"configurable": {"thread_id": "graph-main-2"}}))

    assert "valid JSON" in result["error"]
```

- [ ] **Step 2: Run graph tests and confirm failure**

Run:

```bash
cd backend
uv run pytest tests/test_orchestration_graph.py -v
```

Expected: FAIL because `create_orchestration_graph` does not accept `main_client`.

- [ ] **Step 3: Implement main-agent graph flow**

Modify `backend/app/orchestration/graph.py` to:

- Instantiate `DifyClient(api_key=DIFY_CHAT_API_KEY)` as `main_client`.
- Call main agent with persisted `main_agent` conversation ID.
- Parse with `parse_json_answer`.
- Validate with `MainAgentResult.model_validate`.
- If `reply_only`, set `answer` to `result.response.model_dump()`.
- If `call_agents`, call `AgentExecutor.execute_calls`.
- After downstream results, call main agent again with `inputs={"agent_results": results}` and `query="请基于 agent 结果生成最终回复"`.
- Set `learning_path` when downstream results include `learning_path_agent`.
- Set `profile` when downstream results include `profile_agent` completion.

- [ ] **Step 4: Run graph tests**

Run:

```bash
cd backend
uv run pytest tests/test_orchestration_graph.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit graph flow**

```bash
git add backend/app/orchestration/graph.py backend/tests/test_orchestration_graph.py
git commit -m "feat: route sessions through main agent graph"
```

---

### Task 6: Frontend API Types And Stream Parser

**Files:**
- Modify: `frontend/src/types/chat.ts`
- Modify: `frontend/src/api/orchestration.ts`
- Create: `frontend/src/api/learningPath.ts`
- Test: `frontend/src/api/orchestration.session.test.ts`

- [ ] **Step 1: Write frontend API tests**

Create `frontend/src/api/orchestration.session.test.ts`:

```typescript
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { startSession } from './orchestration';

describe('session orchestration API', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('posts to the new session start endpoint', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        session_id: 'session-1',
        answer: { user_message: '你好', question_box: null },
        agent_trace: [],
        completed: false,
        profile: null,
        learning_path: null,
      }),
    });
    vi.stubGlobal('fetch', fetchMock);

    const result = await startSession('token-1', '你好');

    expect(fetchMock).toHaveBeenCalledWith(
      'http://127.0.0.1:8000/api/orchestration/sessions/start',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ query: '你好' }),
      }),
    );
    expect(result.sessionId).toBe('session-1');
    expect(result.answer.userMessage).toBe('你好');
  });
});
```

- [ ] **Step 2: Run frontend API test and confirm failure**

Run:

```bash
cd frontend
npm run test -- src/api/orchestration.session.test.ts
```

Expected: FAIL because `startSession` does not exist.

- [ ] **Step 3: Extend chat types**

Modify `frontend/src/types/chat.ts`:

```typescript
export interface AgentUserAnswer {
  userMessage: string;
  questionBox: QuestionBox | null;
}

export interface LearningPathResult {
  learning_goal: {
    target_course_or_skill: string;
    target_completion_time: string;
    goal_type: '考试' | '课程学习' | '项目实践' | '能力提升' | '就业准备' | '其他';
    desired_outcome: string;
  };
  gap_analysis: {
    current_mastered_content: string[];
    current_weaknesses: string[];
    required_capabilities: string[];
    main_gaps: string[];
  };
  foundation_path: {
    stages: Array<{
      stage_id: string;
      stage_name: string;
      learning_goal: string;
      learning_content: string[];
      learning_tasks: string[];
      recommended_methods: string[];
      completion_standard: string[];
    }>;
  };
  generated_path: {
    overall_goal: string;
    stage_routes: Array<{ stage_id: string; route_summary: string }>;
    schedule: Array<{ period: string; focus: string; milestone: string }>;
    task_checklist: string[];
    recommended_resource_types: string[];
    stage_acceptance_criteria: Array<{ stage_id: string; criteria: string[] }>;
    next_actions: string[];
  };
}
```

Extend `ChatMessage`:

```typescript
  agentAnswer?: AgentUserAnswer | null;
  learningPath?: LearningPathResult | null;
```

- [ ] **Step 4: Replace orchestration API client paths**

Modify `frontend/src/api/orchestration.ts` to export:

```typescript
export interface SessionTurn {
  sessionId: string;
  answer: AgentUserAnswer;
  completed: boolean;
  profile: SessionMessage | null;
  learningPath: LearningPathResult | null;
}

export async function startSession(token: string, query: string): Promise<SessionTurn> {
  const payload = await requestOrchestration<SessionResponse>(
    '/api/orchestration/sessions/start',
    token,
    { query },
  );
  return normalizeSessionResponse(payload);
}

export async function continueSession(token: string, sessionId: string, query: string): Promise<SessionTurn> {
  const payload = await requestOrchestration<SessionResponse>(
    '/api/orchestration/sessions/continue',
    token,
    { session_id: sessionId, query },
  );
  return normalizeSessionResponse(payload);
}
```

Keep compatibility exports only if existing callers still import old names during the same task:

```typescript
export const startChatflow = startSession;
export const continueChatflow = continueSession;
```

- [ ] **Step 5: Add learning path read client**

Create `frontend/src/api/learningPath.ts`:

```typescript
import type { LearningPathResult } from '../types/chat';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000';

export interface LearningPathRead {
  learningPath: LearningPathResult;
  updatedAt: string;
}

export async function getMyLearningPath(token: string): Promise<LearningPathRead> {
  const response = await fetch(`${API_BASE_URL}/api/learning-path/me`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!response.ok) {
    throw new Error('还没有生成学习路径');
  }
  const payload = await response.json() as { learning_path: LearningPathResult; updated_at: string };
  return { learningPath: payload.learning_path, updatedAt: payload.updated_at };
}
```

- [ ] **Step 6: Run frontend API tests**

Run:

```bash
cd frontend
npm run test -- src/api/orchestration.session.test.ts
```

Expected: PASS.

- [ ] **Step 7: Commit frontend API changes**

```bash
git add frontend/src/types/chat.ts frontend/src/api/orchestration.ts frontend/src/api/learningPath.ts frontend/src/api/orchestration.session.test.ts
git commit -m "feat: add session orchestration frontend API"
```

---

### Task 7: Frontend Learning Path Rendering And Agent Trace

**Files:**
- Create: `frontend/src/components/learning/LearningPathCard.tsx`
- Create: `frontend/src/components/learning/LearningPathCard.test.tsx`
- Modify: `frontend/src/onboarding/chatReducer.ts`
- Modify: `frontend/src/components/onboarding/AiGreetingInput.tsx`
- Modify: `frontend/src/components/onboarding/AssistantMessage.tsx`

- [ ] **Step 1: Write LearningPathCard test**

Create `frontend/src/components/learning/LearningPathCard.test.tsx`:

```typescript
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { LearningPathCard } from './LearningPathCard';
import type { LearningPathResult } from '../../types/chat';

const path: LearningPathResult = {
  learning_goal: {
    target_course_or_skill: '数据结构',
    target_completion_time: '大二结束前',
    goal_type: '课程学习',
    desired_outcome: '完成课程项目',
  },
  gap_analysis: {
    current_mastered_content: ['Python 基础'],
    current_weaknesses: ['算法复杂度'],
    required_capabilities: ['树', '图'],
    main_gaps: ['练习不足'],
  },
  foundation_path: {
    stages: [{
      stage_id: 'year_1',
      stage_name: '大一基础',
      learning_goal: '打牢基础',
      learning_content: ['编程语言'],
      learning_tasks: ['完成练习'],
      recommended_methods: ['课程学习'],
      completion_standard: ['完成小项目'],
    }],
  },
  generated_path: {
    overall_goal: '形成完整数据结构能力',
    stage_routes: [{ stage_id: 'year_1', route_summary: '先补编程基础' }],
    schedule: [{ period: '大一上', focus: '编程基础', milestone: '完成项目' }],
    task_checklist: ['每周练习'],
    recommended_resource_types: ['教材', '题库'],
    stage_acceptance_criteria: [{ stage_id: 'year_1', criteria: ['完成项目'] }],
    next_actions: ['学习数组和链表'],
  },
};

describe('LearningPathCard', () => {
  it('renders all learning path sections', () => {
    render(<LearningPathCard path={path} />);

    expect(screen.getByText('明确学习目标')).toBeInTheDocument();
    expect(screen.getByText('分析当前差距')).toBeInTheDocument();
    expect(screen.getByText('规划基础学习路径')).toBeInTheDocument();
    expect(screen.getByText('生成学习路径')).toBeInTheDocument();
    expect(screen.getByText('数据结构')).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run LearningPathCard test and confirm failure**

Run:

```bash
cd frontend
npm run test -- src/components/learning/LearningPathCard.test.tsx
```

Expected: FAIL because `LearningPathCard` does not exist.

- [ ] **Step 3: Implement LearningPathCard**

Create `frontend/src/components/learning/LearningPathCard.tsx`:

```tsx
import styled from 'styled-components';
import type { LearningPathResult } from '../../types/chat';

interface LearningPathCardProps {
  path: LearningPathResult;
}

function ListBlock({ items }: { items: string[] }) {
  return (
    <ul>
      {items.map((item) => <li key={item}>{item}</li>)}
    </ul>
  );
}

export function LearningPathCard({ path }: LearningPathCardProps) {
  return (
    <Card>
      <section>
        <h3>明确学习目标</h3>
        <dl>
          <div><dt>目标课程或技能</dt><dd>{path.learning_goal.target_course_or_skill}</dd></div>
          <div><dt>目标完成时间</dt><dd>{path.learning_goal.target_completion_time}</dd></div>
          <div><dt>学习目标类型</dt><dd>{path.learning_goal.goal_type}</dd></div>
          <div><dt>最终效果</dt><dd>{path.learning_goal.desired_outcome}</dd></div>
        </dl>
      </section>

      <section>
        <h3>分析当前差距</h3>
        <h4>当前已掌握内容</h4>
        <ListBlock items={path.gap_analysis.current_mastered_content} />
        <h4>当前薄弱环节</h4>
        <ListBlock items={path.gap_analysis.current_weaknesses} />
        <h4>目标所需能力</h4>
        <ListBlock items={path.gap_analysis.required_capabilities} />
        <h4>主要差距</h4>
        <ListBlock items={path.gap_analysis.main_gaps} />
      </section>

      <section>
        <h3>规划基础学习路径</h3>
        {path.foundation_path.stages.map((stage) => (
          <article key={stage.stage_id}>
            <h4>{stage.stage_name}</h4>
            <p>{stage.learning_goal}</p>
            <ListBlock items={stage.learning_content} />
            <ListBlock items={stage.learning_tasks} />
            <ListBlock items={stage.recommended_methods} />
            <ListBlock items={stage.completion_standard} />
          </article>
        ))}
      </section>

      <section>
        <h3>生成学习路径</h3>
        <p>{path.generated_path.overall_goal}</p>
        <ListBlock items={path.generated_path.task_checklist} />
        <ListBlock items={path.generated_path.recommended_resource_types} />
        <ListBlock items={path.generated_path.next_actions} />
      </section>
    </Card>
  );
}

const Card = styled.article`
  inline-size: min(100%, var(--container-default));
  display: grid;
  gap: var(--space-20);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  background: var(--color-surface-raised);
  box-shadow: var(--shadow-md);
  padding: var(--space-24);
  color: var(--color-text-primary);

  section {
    display: grid;
    gap: var(--space-12);
  }

  h3,
  h4,
  p,
  ul,
  dl {
    margin: 0;
  }

  h3 {
    font-size: var(--text-h5);
    font-weight: var(--font-weight-medium);
  }

  h4,
  dt {
    font-size: var(--text-body-sm);
    color: var(--color-text-secondary);
    font-weight: var(--font-weight-medium);
  }

  dl {
    display: grid;
    gap: var(--space-8);
  }

  dl div {
    display: grid;
    gap: var(--space-4);
  }

  ul {
    padding-inline-start: var(--space-20);
  }
`;
```

- [ ] **Step 4: Update reducer done action to store main answer and learning path**

Modify `frontend/src/onboarding/chatReducer.ts`:

```typescript
| {
    type: 'RUN_DONE';
    content: string;
    sessionMessage: ChatMessage['sessionMessage'];
    sessionId?: string;
    agentAnswer?: ChatMessage['agentAnswer'];
    learningPath?: ChatMessage['learningPath'];
  }
```

Inside `RUN_DONE` updater:

```typescript
          agentAnswer: action.agentAnswer ?? null,
          learningPath: action.learningPath ?? null,
```

- [ ] **Step 5: Update AiGreetingInput to use session API and new events**

Modify imports:

```typescript
import { streamSession, type SessionAgentEvent } from '../../api/orchestration';
import { LearningPathCard } from '../learning/LearningPathCard';
```

Map new event names:

```typescript
if (event.event === 'agent_step_started') {
  dispatch({ type: 'STREAMING_STARTED' });
  dispatch({
    type: 'STEP',
    step: {
      stepId: event.step_id,
      kind: 'agent',
      status: 'running',
      title: event.label,
      summary: event.message,
      agent: event.agent_key,
    },
  });
}
```

Handle final event:

```typescript
if (event.event === 'orchestration_completed') {
  executionIdRef.current = event.session_id ?? null;
  finalSessionId = event.session_id ?? undefined;
  dispatch({
    type: 'RUN_DONE',
    content: event.answer?.user_message ?? '',
    sessionMessage: event.profile,
    agentAnswer: event.answer,
    learningPath: event.learning_path ?? null,
    sessionId: event.session_id ?? undefined,
  });
}
```

Render learning path before normal assistant message:

```tsx
if (message.learningPath) {
  return <LearningPathCard key={message.id} path={message.learningPath} />;
}
```

- [ ] **Step 6: Run LearningPathCard tests**

Run:

```bash
cd frontend
npm run test -- src/components/learning/LearningPathCard.test.tsx
```

Expected: PASS.

- [ ] **Step 7: Run frontend unit tests**

Run:

```bash
cd frontend
npm run test
```

Expected: PASS.

- [ ] **Step 8: Commit frontend rendering**

```bash
git add frontend/src/components/learning/LearningPathCard.tsx frontend/src/components/learning/LearningPathCard.test.tsx frontend/src/onboarding/chatReducer.ts frontend/src/components/onboarding/AiGreetingInput.tsx frontend/src/components/onboarding/AssistantMessage.tsx
git commit -m "feat: render main agent sessions and learning paths"
```

---

### Task 8: End-To-End Verification And Cleanup

**Files:**
- Modify tests discovered by the commands below only when they still assert old `/api/orchestration/chatflow/*` behavior.
- No new production file is introduced in this task.

- [ ] **Step 1: Run all backend tests**

Run:

```bash
cd backend
uv run pytest -v
```

Expected: PASS.

- [ ] **Step 2: Run frontend tests**

Run:

```bash
cd frontend
npm run test
```

Expected: PASS.

- [ ] **Step 3: Run frontend build**

Run:

```bash
cd frontend
npm run build
```

Expected: PASS and Vite build completes without TypeScript errors.

- [ ] **Step 4: Start backend server for manual smoke test**

Run:

```bash
cd backend
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Expected: server starts and logs FastAPI startup without import errors.

- [ ] **Step 5: Start frontend server**

Run in another terminal:

```bash
cd frontend
npm run dev
```

Expected: Vite prints a local URL on `127.0.0.1`.

- [ ] **Step 6: Manual smoke test in browser**

Use the app UI:

1. Log in with a test user.
2. Open the AI widget.
3. Send a normal greeting and confirm main agent response renders.
4. Ask to complete profile and confirm profile collection still renders with `ChatCard`.
5. Ask for learning path after profile completion and confirm the right-side trace shows main agent judgment, downstream agent execution, and main agent summary.
6. Confirm the learning path card renders the four sections.

- [ ] **Step 7: Verify learning path read endpoint**

Run:

```bash
curl -H "Authorization: Bearer <token>" http://127.0.0.1:8000/api/learning-path/me
```

Expected: JSON contains `learning_path` and `updated_at`.

- [ ] **Step 8: Commit verification fixes**

If any verification-only fixes were needed:

```bash
git add <changed-files>
git commit -m "fix: stabilize main agent orchestration flow"
```

If no files changed, do not create a commit.

---

## Self Review

Spec coverage:

- Main-agent-led orchestration is covered by Tasks 2, 3, 4, and 5.
- Generic Dify conversation persistence is covered by Task 1.
- Learning path storage and read API are covered by Tasks 1 and 4.
- Main agent and learning path Dify JSON contracts are covered by Task 2.
- Streaming and visible agent trace are covered by Tasks 4 and 7.
- Frontend learning path rendering is covered by Task 7.
- Regression and manual verification are covered by Task 8.

Red-flag scan:

- This plan contains no unfinished markers or unspecified file paths.
- Every implementation task names exact files and verification commands.

Type consistency:

- Backend uses `session_id`, `answer`, `agent_trace`, `profile`, and `learning_path` consistently across schemas, API, and frontend normalization.
- Agent keys are fixed as `main_agent`, `intent_recognition_agent`, `profile_agent`, and `learning_path_agent`.
- Learning path Dify input keys are fixed as `user_profile` and `learning_path_request`.
