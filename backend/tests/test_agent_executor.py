from __future__ import annotations

import asyncio

import pytest
from sqlmodel import Session, SQLModel, create_engine

from app.models import User, UserProfile
from app.orchestration.agent_executor import AgentExecutionError, AgentExecutor
from app.orchestration.dify_client import DifyResponse


class FakeDifyClient:
    def __init__(self, answer: str, conversation_id: str) -> None:
        self.answer = answer
        self.conversation_id = conversation_id
        self.calls: list[dict] = []

    async def chat_blocking(
        self,
        query: str,
        user_id: str,
        conversation_id: str = "",
        inputs: dict | None = None,
    ) -> DifyResponse:
        self.calls.append(
            {
                "query": query,
                "user_id": user_id,
                "conversation_id": conversation_id,
                "inputs": inputs or {},
            }
        )
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
