from __future__ import annotations

import asyncio

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
                call
                for call in pending.values()
                if all(dependency in results for dependency in call.depends_on)
            ]
            if not ready:
                raise AgentExecutionError("Agent call graph has unresolved dependencies")
            batch = await asyncio.gather(*(self.execute_call(call) for call in ready))
            for call, result in zip(ready, batch, strict=True):
                results[call.call_id] = result
                pending.pop(call.call_id)
        return results
