from __future__ import annotations

import json
from collections.abc import AsyncGenerator, Callable, Generator

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlmodel import Session

from app.core.security import create_get_current_user
from app.models import User
from app.orchestration.execution_registry import ExecutionState, registry
from app.orchestration.graph import create_orchestration_graph, stream_orchestration_events
from app.orchestration.state import OrchestrationState
from app.schemas import (
    ChatflowContinueRequest,
    ChatflowContinueResponse,
    ChatflowResponse,
    ChatflowStartRequest,
    SessionContinueRequest,
    SessionResponse,
    SessionStartRequest,
)
from app.services.dify_conversation_service import get_user_dify_conversation, upsert_user_dify_conversation
from app.services.profile_service import upsert_user_profile

SessionDependency = Callable[[], Generator[Session, None, None]]

graph = create_orchestration_graph()


def _initial_state(
    query: str,
    user_id: str,
    session_id: str = "",
    conversation_id: str = "",
    intent_conversation_id: str = "",
) -> OrchestrationState:
    return {
        "query": query,
        "user_id": user_id,
        "session_id": session_id,
        "mode": "session",
        "main_raw": {},
        "main_result": {},
        "agent_results": {},
        "answer": {},
        "agent_trace": [],
        "profile": None,
        "learning_path": None,
        "completed": False,
        "conversation_id": conversation_id,
        "intent_conversation_id": intent_conversation_id,
        "intent_raw": {},
        "intent": "",
        "route_status": "",
        "dify_raw": {},
        "answer_json": {},
        "phase": "collecting",
        "error": "",
    }


def _graph_config(execution: ExecutionState) -> dict:
    return {"configurable": {"thread_id": execution.user_id}}


def _reject_unsupported_route(state: OrchestrationState) -> None:
    if state.get("phase") == "unsupported":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=state.get("error") or "当前仅支持基础画像对话。",
        )


def _sync_execution(execution: ExecutionState, state: OrchestrationState) -> None:
    execution.conversation_id = state.get("conversation_id", "")
    execution.intent_conversation_id = state.get("intent_conversation_id", "")
    execution.completed = state.get("phase") == "completed"
    execution.final_result = state.get("answer_json") if execution.completed else None
    registry.save(execution)


def _restore_saved_conversations(session: Session, execution: ExecutionState) -> None:
    stored = get_user_dify_conversation(session, execution.user_id)
    if stored is None:
        return
    execution.intent_conversation_id = stored.intent_conversation_id
    execution.conversation_id = stored.profile_conversation_id


def _persist_conversations(session: Session, execution: ExecutionState) -> None:
    upsert_user_dify_conversation(
        session=session,
        user_uid=execution.user_id,
        intent_conversation_id=execution.intent_conversation_id,
        profile_conversation_id=execution.conversation_id,
    )


def _sse(event: str, payload: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _session_answer_from_state(state: dict) -> dict:
    answer = state.get("answer", {})
    if isinstance(answer, dict) and isinstance(answer.get("user_message"), str):
        return answer

    answer_json = state.get("answer_json", {})
    if isinstance(answer_json, dict):
        return {
            "user_message": str(answer_json.get("text", "")),
            "question_box": answer_json.get("question_box"),
        }

    return {"user_message": "", "question_box": None}


def _session_response_from_state(execution: ExecutionState, state: dict) -> SessionResponse:
    session_id = str(state.get("session_id") or execution.execution_id)
    execution.execution_id = session_id
    execution.completed = bool(state.get("completed", False))
    registry.save(execution)

    return SessionResponse(
        session_id=session_id,
        answer=_session_answer_from_state(state),
        agent_trace=state.get("agent_trace", []),
        completed=bool(state.get("completed", False)),
        profile=state.get("profile"),
        learning_path=state.get("learning_path"),
    )


def _session_event_name(event_name: str) -> str:
    if event_name == "agent_started":
        return "agent_step_started"
    if event_name == "agent_completed":
        return "agent_step_completed"
    if event_name == "agent_failed":
        return "agent_step_failed"
    if event_name == "completed":
        return "orchestration_completed"
    if event_name == "error":
        return "orchestration_failed"
    return event_name


async def _stream_session_turn(
    execution: ExecutionState,
    state: OrchestrationState,
    session: Session,
) -> AsyncGenerator[str, None]:
    try:
        async for event in stream_orchestration_events(state):
            event_name = _session_event_name(str(event.get("event", "agent_step_completed")))
            payload = {key: value for key, value in event.items() if key != "state"}

            if event_name in {"orchestration_completed", "orchestration_failed"}:
                final_state = event.get("state", state)
                session_response = _session_response_from_state(execution, final_state)
                payload.update(session_response.model_dump())

            yield _sse(event_name, payload)
    except Exception as exc:
        yield _sse("orchestration_failed", {"message": str(exc) or "对话请求失败，请稍后重试"})


async def _stream_chatflow_turn(
    execution: ExecutionState,
    state: OrchestrationState,
    session: Session,
) -> AsyncGenerator[str, None]:
    try:
        async for event in stream_orchestration_events(state):
            event_name = str(event.get("event", "message"))
            payload = {key: value for key, value in event.items() if key != "state"}

            if event_name == "completed":
                final_state = event.get("state", state)
                _sync_execution(execution, final_state)
                _persist_conversations(session, execution)

                if execution.completed and execution.final_result:
                    upsert_user_profile(session, execution.user_id, execution.final_result)

                payload.update(
                    {
                        "execution_id": execution.execution_id,
                        "conversation_id": execution.conversation_id,
                        "answer": final_state.get("answer_json", {}),
                        "completed": execution.completed,
                        "final_result": execution.final_result,
                    }
                )

            yield _sse(event_name, payload)
    except Exception as exc:
        yield _sse("error", {"message": str(exc) or "对话请求失败，请稍后重试"})


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
        state = await graph.ainvoke(
            _initial_state(payload.query, current_user.uid, execution.execution_id),
            _graph_config(execution),
        )
        if state.get("error"):
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=state["error"])
        return _session_response_from_state(execution, state)

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
        return _session_response_from_state(execution, state)

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

    @router.post("/sessions/continue/stream")
    async def continue_session_stream(
        payload: SessionContinueRequest,
        current_user: User = Depends(get_current_user),
        session: Session = Depends(session_dependency),
    ) -> StreamingResponse:
        execution = registry.get(payload.session_id)
        if execution is None or execution.user_id != current_user.uid:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="对话不存在")

        state = _initial_state(payload.query, current_user.uid, execution.execution_id)

        return StreamingResponse(
            _stream_session_turn(execution, state, session),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @router.post("/chatflow/start", response_model=ChatflowResponse)
    async def start_chatflow(
        payload: ChatflowStartRequest,
        current_user: User = Depends(get_current_user),
        session: Session = Depends(session_dependency),
    ) -> ChatflowResponse:
        execution = registry.create(current_user.uid)
        _restore_saved_conversations(session, execution)
        state = await graph.ainvoke(
            _initial_state(
                query=payload.query,
                user_id=current_user.uid,
                conversation_id=execution.conversation_id,
                intent_conversation_id=execution.intent_conversation_id,
            ),
            _graph_config(execution),
        )
        _reject_unsupported_route(state)
        _sync_execution(execution, state)
        _persist_conversations(session, execution)

        if execution.completed and execution.final_result:
            upsert_user_profile(session, current_user.uid, execution.final_result)

        return ChatflowResponse(
            execution_id=execution.execution_id,
            conversation_id=execution.conversation_id,
            answer=state.get("answer_json", {}),
            completed=execution.completed,
            final_result=execution.final_result,
        )

    @router.post("/chatflow/start/stream")
    async def start_chatflow_stream(
        payload: ChatflowStartRequest,
        current_user: User = Depends(get_current_user),
        session: Session = Depends(session_dependency),
    ) -> StreamingResponse:
        execution = registry.create(current_user.uid)
        _restore_saved_conversations(session, execution)
        state = _initial_state(
            query=payload.query,
            user_id=current_user.uid,
            conversation_id=execution.conversation_id,
            intent_conversation_id=execution.intent_conversation_id,
        )

        return StreamingResponse(
            _stream_chatflow_turn(execution, state, session),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @router.post("/chatflow/continue", response_model=ChatflowContinueResponse)
    async def continue_chatflow(
        payload: ChatflowContinueRequest,
        current_user: User = Depends(get_current_user),
        session: Session = Depends(session_dependency),
    ) -> ChatflowContinueResponse:
        execution = registry.get(payload.execution_id)
        if execution is None or execution.user_id != current_user.uid:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="对话不存在")
        if execution.completed:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="对话已完成")

        state = await graph.ainvoke(
            _initial_state(
                query=payload.query,
                user_id=current_user.uid,
                conversation_id=execution.conversation_id,
                intent_conversation_id=execution.intent_conversation_id,
            ),
            _graph_config(execution),
        )
        _reject_unsupported_route(state)
        _sync_execution(execution, state)
        _persist_conversations(session, execution)

        if execution.completed and execution.final_result:
            upsert_user_profile(session, current_user.uid, execution.final_result)

        return ChatflowContinueResponse(
            answer=state.get("answer_json", {}),
            completed=execution.completed,
            conversation_id=execution.conversation_id,
            final_result=execution.final_result,
        )

    @router.post("/chatflow/continue/stream")
    async def continue_chatflow_stream(
        payload: ChatflowContinueRequest,
        current_user: User = Depends(get_current_user),
        session: Session = Depends(session_dependency),
    ) -> StreamingResponse:
        execution = registry.get(payload.execution_id)
        if execution is None or execution.user_id != current_user.uid:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="对话不存在")
        if execution.completed:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="对话已完成")

        state = _initial_state(
            query=payload.query,
            user_id=current_user.uid,
            conversation_id=execution.conversation_id,
            intent_conversation_id=execution.intent_conversation_id,
        )

        return StreamingResponse(
            _stream_chatflow_turn(execution, state, session),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    return router
