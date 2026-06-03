from __future__ import annotations

import json
from collections.abc import AsyncGenerator, Callable, Generator

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlmodel import Session

from app.core.security import create_get_current_user
from app.models import User, UserProfile
from app.orchestration.execution_registry import ExecutionState, registry
from app.orchestration.graph import get_orchestration_graph, stream_orchestration_events
from app.orchestration.state import OrchestrationState
from app.schemas import (
    AgentUserAnswer,
    SessionContinueRequest,
    SessionResponse,
    SessionStartRequest,
)

SessionDependency = Callable[[], Generator[Session, None, None]]


def _completed_user_profile(session: Session, user_uid: str) -> dict:
    profile = session.get(UserProfile, user_uid)
    if profile is None:
        return {}
    if profile.profile_data.get("type") != "basic_profile":
        return {}
    return profile.profile_data


def _graph_config(execution: ExecutionState) -> dict:
    return {"configurable": {"thread_id": execution.user_id}}


def _recover_or_get_execution(session_id: str, current_user: User) -> ExecutionState:
    execution = registry.get(session_id)
    if execution is None:
        return registry.create(current_user.uid)
    if execution.user_id != current_user.uid:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="对话不存在")
    return execution


def _sse(event: str, payload: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _session_answer_from_state(state: dict) -> AgentUserAnswer:
    answer = state.get("answer", {})
    if isinstance(answer, dict) and isinstance(answer.get("user_message"), str):
        return AgentUserAnswer(
            user_message=answer["user_message"],
            question_box=answer.get("question_box"),
        )
    response = state.get("response", "")
    return AgentUserAnswer(user_message=response or "")


def _session_response_from_state(execution: ExecutionState, state: dict) -> SessionResponse:
    session_id = str(state.get("session_id") or execution.execution_id)
    execution.execution_id = session_id
    execution.completed = True
    registry.save(execution)

    return SessionResponse(
        session_id=session_id,
        answer=_session_answer_from_state(state),
        agent_trace=state.get("agent_trace", []),
        completed=True,
        profile=state.get("profile"),
        learning_path=state.get("learning_path"),
        course_knowledge_outline=state.get("course_knowledge"),
    )


def _session_event_name(event_name: str) -> str:
    mapping = {
        "agent_started": "agent_step_started",
        "agent_completed": "agent_step_completed",
        "agent_failed": "agent_step_failed",
        "completed": "orchestration_completed",
        "error": "orchestration_failed",
        "orchestration_started": "orchestration_started",
        "context_loaded": "context_loaded",
        "tool_call_started": "tool_call_started",
        "tool_call_completed": "tool_call_completed",
        "thought_chunk": "thought_chunk",
        "message_started": "message_started",
        "text_chunk": "text_chunk",
        "data_schema_started": "data_schema_started",
        "data_chunk": "data_chunk",
        "data_completed": "data_completed",
    }
    return mapping.get(event_name, event_name)


def _prepare_state(
    payload_query: str,
    execution: ExecutionState,
    session: Session,
    current_user: User,
) -> dict:
    """Build the initial OrchestrationState update for a turn — shared by all 4 endpoints."""
    from langchain_core.messages import HumanMessage

    user_profile = _completed_user_profile(session, current_user.uid)
    
    state = {
        "query": payload_query,
        "user_id": current_user.uid,
        "session_id": execution.execution_id,
        "messages": [HumanMessage(content=payload_query)],
        "response": "",
        "answer": None,
        "question_box": None,
        "profile_completed": None,
        "error": None,
    }
    
    if user_profile:
        state["profile"] = user_profile
        
    return state


async def _stream_session_turn(
    execution: ExecutionState,
    state: OrchestrationState,
) -> AsyncGenerator[str, None]:
    """SSE generator — no longer holds a DB session during the entire stream."""
    try:
        async for event in stream_orchestration_events(state):
            event_name = _session_event_name(str(event.get("event", "")))
            payload = {k: v for k, v in event.items() if k not in ("state", "event")}

            if event_name in {"orchestration_completed", "orchestration_failed"}:
                final_state = event.get("state", state)
                session_response = _session_response_from_state(execution, final_state)
                payload.update(session_response.model_dump())

            yield _sse(event_name, payload)
    except Exception as exc:
        yield _sse("orchestration_failed", {"message": str(exc) or "对话请求失败，请稍后重试"})


def create_orchestration_router(session_dependency: SessionDependency) -> APIRouter:
    router = APIRouter(prefix="/api/orchestration", tags=["orchestration"])
    get_current_user = create_get_current_user(session_dependency)

    @router.post("/sessions/start", response_model=SessionResponse)
    async def start_session(
        payload: SessionStartRequest,
        current_user: User = Depends(get_current_user),
        session: Session = Depends(session_dependency),
    ) -> SessionResponse:
        execution = registry.create(current_user.uid)
        state = _prepare_state(payload.query, execution, session, current_user)

        graph = get_orchestration_graph()
        result_state = await graph.ainvoke(state, _graph_config(execution))

        if result_state.get("error"):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=result_state["error"],
            )
        return _session_response_from_state(execution, result_state)

    @router.post("/sessions/continue", response_model=SessionResponse)
    async def continue_session(
        payload: SessionContinueRequest,
        current_user: User = Depends(get_current_user),
        session: Session = Depends(session_dependency),
    ) -> SessionResponse:
        execution = _recover_or_get_execution(payload.session_id, current_user)
        state = _prepare_state(payload.query, execution, session, current_user)

        graph = get_orchestration_graph()
        result_state = await graph.ainvoke(state, _graph_config(execution))

        if result_state.get("error"):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=result_state["error"],
            )
        return _session_response_from_state(execution, result_state)

    @router.post("/sessions/start/stream")
    async def start_session_stream(
        payload: SessionStartRequest,
        current_user: User = Depends(get_current_user),
        session: Session = Depends(session_dependency),
    ) -> StreamingResponse:
        execution = registry.create(current_user.uid)
        state = _prepare_state(payload.query, execution, session, current_user)

        return StreamingResponse(
            _stream_session_turn(execution, state),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @router.post("/sessions/continue/stream")
    async def continue_session_stream(
        payload: SessionContinueRequest,
        current_user: User = Depends(get_current_user),
        session: Session = Depends(session_dependency),
    ) -> StreamingResponse:
        execution = _recover_or_get_execution(payload.session_id, current_user)
        state = _prepare_state(payload.query, execution, session, current_user)

        return StreamingResponse(
            _stream_session_turn(execution, state),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    return router
