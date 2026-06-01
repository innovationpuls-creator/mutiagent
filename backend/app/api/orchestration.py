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
from app.schemas import ChatflowContinueRequest, ChatflowContinueResponse, ChatflowResponse, ChatflowStartRequest
from app.services.dify_conversation_service import get_user_dify_conversation, upsert_user_dify_conversation
from app.services.profile_service import upsert_user_profile

SessionDependency = Callable[[], Generator[Session, None, None]]

graph = create_orchestration_graph()


def _initial_state(
    query: str,
    user_id: str,
    conversation_id: str = "",
    intent_conversation_id: str = "",
) -> OrchestrationState:
    return {
        "query": query,
        "user_id": user_id,
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
