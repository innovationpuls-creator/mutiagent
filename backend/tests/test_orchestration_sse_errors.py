from __future__ import annotations

import asyncio
import json

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.orchestration.graph import (
    _event_for_agent_error,
    _is_hard_agent_error,
    route_after_worker,
    stream_orchestration_events,
)


def test_is_hard_agent_error_detects_hard_error_payload() -> None:
    assert (
        _is_hard_agent_error(
            {"error": "学习路径缺少 current_learning_course。", "hard_error": True}
        )
        is True
    )
    assert _is_hard_agent_error({"error": "可恢复提示"}) is False


def test_event_for_agent_error_marks_learning_path_retryable() -> None:
    event = _event_for_agent_error("learning_path_agent", "学习路径生成失败")

    assert event["event"] == "error"
    assert event["retryable"] is True
    assert event["retryAction"] == "retry_learning_path"
    assert event["recoverable"] is True


def test_stream_orchestration_events_stops_after_hard_agent_error(monkeypatch) -> None:
    class StubGraph:
        async def astream_events(self, state, version):
            yield {"event": "on_chain_start", "name": "learning_path_agent"}
            yield {
                "event": "on_chain_end",
                "name": "learning_path_agent",
                "data": {
                    "output": {
                        "messages": [
                            ToolMessage(
                                content=json.dumps(
                                    {
                                        "error": "学习路径生成失败",
                                        "hard_error": True,
                                    },
                                    ensure_ascii=False,
                                ),
                                tool_call_id="tool-1",
                            )
                        ]
                    }
                },
            }
            yield {
                "event": "on_chain_end",
                "name": "LangGraph",
                "data": {"output": {"response": "不应到达这里"}},
            }

    monkeypatch.setattr(
        "app.orchestration.graph.build_orchestration_graph",
        lambda: StubGraph(),
    )

    async def collect_events() -> list[dict]:
        return [
            event
            async for event in stream_orchestration_events(
                {
                    "session_id": "session-1",
                    "query": "继续生成学习路径",
                    "messages": [],
                }
            )
        ]

    events = asyncio.run(collect_events())

    assert {"event": "session_completed", "session_id": "session-1"} not in events
    assert not any(event["event"] == "message_completed" for event in events)

    result_event = next(
        event
        for event in events
        if event["event"] == "agent_result" and event["agent"] == "learning_path_agent"
    )
    assert result_event["stepId"] == "learning_path_agent-result"
    assert result_event["kind"] == "agent"
    assert result_event["success"] is False
    assert result_event["error"] == "学习路径生成失败"

    error_event = next(event for event in events if event["event"] == "error")
    assert error_event["retryable"] is True
    assert error_event["retryAction"] == "retry_learning_path"


def test_stream_orchestration_events_starts_with_intent_routing(monkeypatch) -> None:
    class StubGraph:
        async def astream_events(self, state, version):
            if False:
                yield {}

    monkeypatch.setattr(
        "app.orchestration.graph.build_orchestration_graph",
        lambda: StubGraph(),
    )

    async def collect_events() -> list[dict]:
        return [
            event
            async for event in stream_orchestration_events(
                {
                    "session_id": "session-preload",
                    "query": "你好",
                    "messages": [],
                    "profile": {"type": "basic_profile"},
                    "year_learning_paths": {"year_3": {"grade_name": "大三"}},
                    "course_knowledge": {"course_name": "AI 应用开发"},
                }
            )
        ]

    events = asyncio.run(collect_events())
    assert events[0] == {
        "event": "agent_calling",
        "stepId": "intent-routing",
        "kind": "route",
        "agent": "intent_agent",
        "label": "意图识别智能体",
        "message": "正在判断本轮要调用的智能体",
    }


def test_stream_orchestration_events_emits_idle_status_while_waiting(
    monkeypatch,
) -> None:
    class StubGraph:
        async def astream_events(self, state, version):
            await asyncio.sleep(0.01)
            yield {
                "event": "on_chain_end",
                "name": "LangGraph",
                "data": {"output": {"response": "处理完成"}},
            }

    monkeypatch.setattr(
        "app.orchestration.graph.build_orchestration_graph",
        lambda: StubGraph(),
    )

    async def collect_events() -> list[dict]:
        return [
            event
            async for event in stream_orchestration_events(
                {
                    "session_id": "session-idle",
                    "query": "给我看看这个课的大纲",
                    "messages": [],
                },
                idle_timeout_seconds=0.001,
            )
        ]

    events = asyncio.run(collect_events())

    assert any(
        event["event"] == "supervisor_thinking"
        and event["message"] == "仍在处理，请稍等一下..."
        for event in events
    )
    assert any(
        event["event"] == "message_completed" and event["full_text"] == "处理完成"
        for event in events
    )


def test_session_completed_reports_final_structured_state(monkeypatch) -> None:
    complete_profile = {
        "type": "basic_profile",
        "summary_text": "大三软件工程学生，目标是完成 AI 应用开发项目。",
        "confirmed_info": {
            "current_grade": "大三",
            "major": "软件工程",
            "learning_stage": "项目实践",
            "has_clear_goal": "是",
            "learning_method_preference": "项目驱动学习",
            "learning_pace_preference": "按项目里程碑推进",
            "content_preference": ["代码实践", "项目案例"],
            "need_guidance": "需要轻量提醒",
            "knowledge_foundation": "有 Python 和前端基础",
            "strengths": "能完成小型功能",
            "weaknesses": "异步工程经验不足",
            "experience": "做过课程项目",
            "short_term_goal": "完成 AI 功能模块",
            "long_term_goal": "成为全栈 AI 开发者",
            "weekly_available_time": "每周 8 小时",
            "constraints": "时间有限",
        },
    }

    class StubGraph:
        async def astream_events(self, state, version):
            yield {"event": "on_chain_start", "name": "supervisor"}
            yield {
                "event": "on_chain_end",
                "name": "LangGraph",
                "data": {
                    "output": {
                        "response": "你好，我在这里帮你规划学习。",
                        "profile": complete_profile,
                        "year_learning_paths": {"year_3": {"grade_name": "大三"}},
                        "course_knowledge": {"course_name": "AI 应用开发基础能力搭建"},
                    }
                },
            }

    monkeypatch.setattr(
        "app.orchestration.graph.build_orchestration_graph",
        lambda: StubGraph(),
    )

    async def collect_events() -> list[dict]:
        return [
            event
            async for event in stream_orchestration_events(
                {
                    "session_id": "session-history-only",
                    "query": "你好",
                    "messages": [],
                    "profile": complete_profile,
                    "year_learning_paths": {"year_3": {"grade_name": "大三"}},
                    "course_knowledge": {"course_name": "AI 应用开发基础能力搭建"},
                }
            )
        ]

    events = asyncio.run(collect_events())
    completed = next(event for event in events if event["event"] == "session_completed")

    assert completed["session_id"] == "session-history-only"
    assert completed["has_profile"] is True
    assert completed["has_paths"] is True
    assert completed["has_outline"] is True


def test_session_completed_marks_unsupported_postgraduate_basic_profile_as_incomplete(
    monkeypatch,
) -> None:
    unsupported_profile = {
        "type": "basic_profile",
        "summary_text": "当前学习路径只支持大一到大四。你当前提供的年级是「研一」，请先确认对应的本科年级。",
        "confirmed_info": {
            "current_grade": "研一",
            "major": "软件工程",
            "learning_stage": "项目实践",
            "has_clear_goal": "是",
            "learning_method_preference": "项目驱动学习",
            "learning_pace_preference": "按项目里程碑推进",
            "content_preference": ["代码实践", "项目案例"],
            "need_guidance": "需要轻量提醒",
            "knowledge_foundation": "有 Python 和前端基础",
            "strengths": "能完成小型功能",
            "weaknesses": "异步工程经验不足",
            "experience": "做过课程项目",
            "short_term_goal": "完成 AI 功能模块",
            "long_term_goal": "成为全栈 AI 开发者",
            "weekly_available_time": "每周 8 小时",
            "constraints": "时间有限",
        },
    }

    class StubGraph:
        async def astream_events(self, state, version):
            yield {"event": "on_chain_start", "name": "supervisor"}
            yield {
                "event": "on_chain_end",
                "name": "LangGraph",
                "data": {
                    "output": {
                        "response": unsupported_profile["summary_text"],
                        "profile": unsupported_profile,
                        "year_learning_paths": {"year_3": {"grade_name": "大三"}},
                        "course_knowledge": {"course_name": "AI 应用开发基础能力搭建"},
                    }
                },
            }

    monkeypatch.setattr(
        "app.orchestration.graph.build_orchestration_graph",
        lambda: StubGraph(),
    )

    async def collect_events() -> list[dict]:
        return [
            event
            async for event in stream_orchestration_events(
                {
                    "session_id": "session-unsupported-grade",
                    "query": "继续",
                    "messages": [],
                    "profile": unsupported_profile,
                    "year_learning_paths": {"year_3": {"grade_name": "大三"}},
                    "course_knowledge": {"course_name": "AI 应用开发基础能力搭建"},
                }
            )
        ]

    events = asyncio.run(collect_events())
    completed = next(event for event in events if event["event"] == "session_completed")

    assert completed["session_id"] == "session-unsupported-grade"
    assert completed["has_profile"] is False
    assert completed["has_paths"] is True
    assert completed["has_outline"] is True


def test_session_completed_marks_collecting_profile_as_incomplete(monkeypatch) -> None:
    collecting_profile = {
        "type": "collecting",
        "stage": "basic_info",
        "question_mode": "question_md",
        "confirmed_info": {
            "current_grade": "大三",
            "major": "",
            "learning_stage": "",
            "has_clear_goal": "",
            "learning_method_preference": "",
            "learning_pace_preference": "",
            "content_preference": [],
            "need_guidance": "",
            "knowledge_foundation": "",
            "strengths": "",
            "weaknesses": "",
            "experience": "",
            "short_term_goal": "",
            "long_term_goal": "",
            "weekly_available_time": "",
            "constraints": "",
        },
        "defaulted_fields": [],
        "question_md": "为了生成基础画像，请先告诉我你的专业。",
        "question_box": {"question": "", "options": []},
        "text": "为了生成基础画像，请先告诉我你的专业。",
    }

    class StubGraph:
        async def astream_events(self, state, version):
            yield {"event": "on_chain_start", "name": "profile_agent"}
            yield {
                "event": "on_chain_end",
                "name": "profile_agent",
                "data": {
                    "output": {
                        "profile": collecting_profile,
                        "messages": [],
                    }
                },
            }
            yield {
                "event": "on_chain_end",
                "name": "LangGraph",
                "data": {
                    "output": {
                        "profile": collecting_profile,
                        "response": collecting_profile["text"],
                    }
                },
            }

    monkeypatch.setattr(
        "app.orchestration.graph.build_orchestration_graph",
        lambda: StubGraph(),
    )

    async def collect_events() -> list[dict]:
        return [
            event
            async for event in stream_orchestration_events(
                {
                    "session_id": "session-collecting",
                    "query": "我现在大三，你看看我的个人画像，你推荐什么？",
                    "messages": [],
                }
            )
        ]

    events = asyncio.run(collect_events())
    completed = next(event for event in events if event["event"] == "session_completed")

    assert completed["session_id"] == "session-collecting"
    assert completed["has_profile"] is False
    assert completed["has_paths"] is False
    assert completed["has_outline"] is False


def test_stream_orchestration_events_emits_worker_calling_for_forced_route(
    monkeypatch,
) -> None:
    class StubGraph:
        async def astream_events(self, state, version):
            yield {"event": "on_chain_start", "name": "learning_path_agent"}
            yield {
                "event": "on_chain_end",
                "name": "learning_path_agent",
                "data": {
                    "output": {
                        "messages": [
                            ToolMessage(
                                content=json.dumps(
                                    {
                                        "year_learning_path": {
                                            "current_learning_course": {
                                                "course_node_id": "year_3_course_1",
                                            }
                                        },
                                        "grade_year": "year_3",
                                    },
                                    ensure_ascii=False,
                                ),
                                tool_call_id="tool-1",
                            )
                        ],
                        "year_learning_paths": {
                            "year_3": {
                                "current_learning_course": {
                                    "course_node_id": "year_3_course_1",
                                }
                            }
                        },
                    }
                },
            }
            yield {
                "event": "on_chain_end",
                "name": "LangGraph",
                "data": {"output": {"year_learning_paths": {"year_3": {}}}},
            }

    monkeypatch.setattr(
        "app.orchestration.graph.build_orchestration_graph",
        lambda: StubGraph(),
    )

    async def collect_events() -> list[dict]:
        return [
            event
            async for event in stream_orchestration_events(
                {
                    "session_id": "session-forced-learning-path",
                    "query": "直接帮我生成学习路径",
                    "messages": [],
                }
            )
        ]

    events = asyncio.run(collect_events())

    calling_event = next(
        event
        for event in events
        if event["event"] == "agent_calling"
        and event.get("agent") == "learning_path_agent"
    )
    assert calling_event["label"] == "学习路径智能体"


def test_stream_orchestration_events_emits_supervisor_plan_before_worker_run(
    monkeypatch,
) -> None:
    class StubChunk:
        def __init__(self, content: str, tool_call_chunks: list[dict]) -> None:
            self.content = content
            self.tool_call_chunks = tool_call_chunks

    class StubGraph:
        async def astream_events(self, state, version):
            yield {
                "event": "on_chat_model_stream",
                "name": "supervisor",
                "data": {
                    "chunk": StubChunk(
                        "",
                        [
                            {
                                "name": "learning_path_agent",
                                "args": '{"grade_year":"year_3","learning_topic":"AI 应用开发"}',
                            }
                        ],
                    )
                },
            }
            yield {
                "event": "on_chain_end",
                "name": "LangGraph",
                "data": {"output": {"response": "学习路径已生成。"}},
            }

    monkeypatch.setattr(
        "app.orchestration.graph.build_orchestration_graph",
        lambda: StubGraph(),
    )

    async def collect_events() -> list[dict]:
        return [
            event
            async for event in stream_orchestration_events(
                {
                    "session_id": "session-supervisor-plan",
                    "query": "帮我规划 AI 应用开发学习路径",
                    "messages": [],
                }
            )
        ]

    events = asyncio.run(collect_events())

    plan_event = next(event for event in events if event["event"] == "supervisor_plan")
    assert plan_event["agent"] == "learning_path_agent"
    assert plan_event["label"] == "学习路径智能体"
    assert plan_event["reason"] == "调用 学习路径智能体"

    calling_event = next(
        event
        for event in events
        if event["event"] == "agent_calling"
        and event.get("agent") == "learning_path_agent"
        and event.get("args")
    )
    assert calling_event["label"] == "学习路径智能体"
    assert (
        calling_event["args"]
        == '{"grade_year":"year_3","learning_topic":"AI 应用开发"}'
    )


def test_stream_orchestration_events_keeps_soft_worker_failure_in_agent_result(
    monkeypatch,
) -> None:
    class StubGraph:
        async def astream_events(self, state, version):
            yield {"event": "on_chain_start", "name": "profile_agent"}
            yield {
                "event": "on_chain_end",
                "name": "profile_agent",
                "data": {
                    "output": {
                        "messages": [
                            ToolMessage(
                                content=json.dumps(
                                    {
                                        "error": "画像生成失败：结构化输出异常",
                                    },
                                    ensure_ascii=False,
                                ),
                                tool_call_id="tool-1",
                            )
                        ],
                        "response": "画像生成失败：结构化输出异常",
                    }
                },
            }
            yield {
                "event": "on_chain_end",
                "name": "LangGraph",
                "data": {
                    "output": {
                        "response": "画像生成失败：结构化输出异常",
                    }
                },
            }

    monkeypatch.setattr(
        "app.orchestration.graph.build_orchestration_graph",
        lambda: StubGraph(),
    )

    async def collect_events() -> list[dict]:
        return [
            event
            async for event in stream_orchestration_events(
                {
                    "session_id": "session-soft-worker-error",
                    "query": "继续补全我的画像",
                    "messages": [],
                }
            )
        ]

    events = asyncio.run(collect_events())

    result_event = next(
        event
        for event in events
        if event["event"] == "agent_result" and event["agent"] == "profile_agent"
    )
    assert result_event["success"] is False
    assert result_event["error"] == "画像生成失败：结构化输出异常"

    assert not any(event["event"] == "error" for event in events)

    completed_event = next(
        event for event in events if event["event"] == "message_completed"
    )
    assert completed_event["full_text"] == "画像生成失败：结构化输出异常"


def test_route_after_worker_ends_after_initial_profile_generation_to_wait_for_user_confirmation() -> (
    None
):
    assert (
        route_after_worker(
            {
                "profile": {
                    "type": "basic_profile",
                    "summary_text": "大三软件工程学生，继续强化 AI 应用开发。",
                    "confirmed_info": {
                        "current_grade": "大三",
                        "major": "软件工程",
                        "learning_stage": "项目实践",
                        "has_clear_goal": "是",
                        "learning_method_preference": "项目驱动",
                        "learning_pace_preference": "周末集中",
                        "content_preference": ["实践"],
                        "need_guidance": "需要",
                        "knowledge_foundation": "有 Python 基础",
                        "strengths": "执行力强",
                        "weaknesses": "部署经验不足",
                        "experience": "做过课程项目",
                        "short_term_goal": "更新项目方向",
                        "long_term_goal": "完成 AI 应用开发项目",
                        "weekly_available_time": "每周 8 小时",
                        "constraints": "周末集中",
                    },
                },
                "messages": [
                    HumanMessage(content="大三，软件工程，AI，周末集中"),
                    AIMessage(
                        content="",
                        tool_calls=[
                            {
                                "name": "profile_agent",
                                "args": {
                                    "conversation_summary": "大三，软件工程，AI，周末集中"
                                },
                                "id": "force_profile_agent",
                            }
                        ],
                    ),
                    ToolMessage(
                        content="{}",
                        tool_call_id="force_profile_agent",
                    ),
                ],
            }
        )
        == "supervisor"
    )


def test_route_after_worker_returns_supervisor_for_completed_tasks_profile_followup() -> (
    None
):
    assert (
        route_after_worker(
            {
                "profile": {
                    "type": "basic_profile",
                    "summary_text": "大三软件工程学生，继续强化 AI 应用开发。",
                    "confirmed_info": {
                        "current_grade": "大三",
                        "major": "软件工程",
                        "learning_stage": "项目实践",
                        "has_clear_goal": "是",
                        "learning_method_preference": "项目驱动",
                        "learning_pace_preference": "周末集中",
                        "content_preference": ["实践"],
                        "need_guidance": "需要",
                        "knowledge_foundation": "有 Python 基础",
                        "strengths": "执行力强",
                        "weaknesses": "部署经验不足",
                        "experience": "做过课程项目",
                        "short_term_goal": "更新项目方向",
                        "long_term_goal": "完成 AI 应用开发项目",
                        "weekly_available_time": "每周 8 小时",
                        "constraints": "周末集中",
                    },
                },
                "messages": [
                    AIMessage(
                        content="当前所有任务已经完成。如果你想继续下一阶段，我可以先帮你更新个人画像，再重新生成学习路径。"
                    ),
                    HumanMessage(content="大三，软件工程，AI，周末集中"),
                    AIMessage(
                        content="",
                        tool_calls=[
                            {
                                "name": "profile_agent",
                                "args": {
                                    "conversation_summary": "大三，软件工程，AI，周末集中"
                                },
                                "id": "force_profile_agent",
                            }
                        ],
                    ),
                    ToolMessage(
                        content="{}",
                        tool_call_id="force_profile_agent",
                    ),
                ],
            }
        )
        == "supervisor"
    )


def test_route_after_course_knowledge_resource_request_returns_supervisor() -> None:
    assert (
        route_after_worker(
            {
                "query": "生成当前课程教学内容",
                "course_knowledge": {
                    "course_id": "year_3_course_1",
                    "sections": [
                        {"section_id": "1", "parent_section_id": None, "depth": 1}
                    ],
                },
                "messages": [
                    HumanMessage(content="生成当前课程教学内容"),
                    AIMessage(
                        content="",
                        tool_calls=[
                            {
                                "name": "course_knowledge_agent",
                                "args": {"course_id": "year_3_course_1"},
                                "id": "force_course_knowledge_agent",
                            }
                        ],
                    ),
                    ToolMessage(
                        content='{"course_id": "year_3_course_1"}',
                        tool_call_id="force_course_knowledge_agent",
                    ),
                ],
            }
        )
        == "supervisor"
    )


def test_route_after_course_knowledge_detailed_content_returns_supervisor() -> None:
    assert (
        route_after_worker(
            {
                "query": "帮我重新生成构建本地知识库问答系统 (RAG基础)的详细内容",
                "course_knowledge": {
                    "course_id": "year_3_course_1",
                    "sections": [
                        {"section_id": "1", "parent_section_id": None, "depth": 1}
                    ],
                },
                "messages": [
                    HumanMessage(
                        content="帮我重新生成构建本地知识库问答系统 (RAG基础)的详细内容"
                    ),
                    AIMessage(
                        content="",
                        tool_calls=[
                            {
                                "name": "course_knowledge_agent",
                                "args": {"course_id": "year_3_course_1"},
                                "id": "force_course_knowledge_agent",
                            }
                        ],
                    ),
                    ToolMessage(
                        content='{"course_id": "year_3_course_1"}',
                        tool_call_id="force_course_knowledge_agent",
                    ),
                ],
            }
        )
        == "supervisor"
    )


def test_route_after_worker_ends_without_followup() -> None:
    assert route_after_worker({}) == "__end__"
