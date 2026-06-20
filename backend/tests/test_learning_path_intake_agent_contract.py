from __future__ import annotations

import asyncio
from pathlib import Path

from langchain_core.messages import HumanMessage
from sqlmodel import Session

from app.database import build_engine, init_db, set_engine
from app.orchestration.agents.learning_path_intake import (
    is_intake_confirmation_query,
    is_intake_modification_query,
    latest_intake_from_state,
    run_learning_path_intake_agent,
)
from app.orchestration.agents.models import (
    LearningPathIntakeDraftOutput,
    LearningPathIntakeOutput,
)
from app.orchestration.agents.prompts import LEARNING_PATH_INTAKE_AGENT_SYSTEM_PROMPT
from app.services.conversation_session_service import (
    latest_learning_path_intake,
    load_or_create_session,
)


class _FakeIntakeLLM:
    def __init__(self, result: dict, *, validate_result: bool = True) -> None:
        self.result = result
        self.validate_result = validate_result
        self.schema: object | None = None
        self.calls: list[object] = []

    def with_structured_output(self, schema: object) -> "_FakeIntakeLLM":
        self.schema = schema
        return self

    async def ainvoke(
        self, messages: object
    ) -> LearningPathIntakeOutput | LearningPathIntakeDraftOutput | dict:
        self.calls.append(messages)
        if not self.validate_result:
            return self.result
        return self.schema.model_validate(self.result)


def _llm_intake_result(
    *, courses: list[dict[str, str]] | None = None, topic: str = "数据结构"
) -> dict:
    return {
        "type": "learning_path_intake",
        "status": "draft",
        "grade_year": "year_3",
        "grade_name": "大三",
        "learning_topic": topic,
        "courses": courses
        or [
            {
                "title": "LLM 定制复杂度与抽象数据类型",
                "purpose": "先理解数据结构的分析语言",
            },
            {"title": "LLM 定制线性表与栈队列", "purpose": "掌握线性结构实现"},
            {"title": "LLM 定制树结构与递归", "purpose": "建立递归结构理解"},
            {"title": "LLM 定制图结构项目", "purpose": "完成综合实践"},
        ],
        "recommendation_reasons": ["根据画像由 LLM 判断课程顺序"],
        "user_modification_summary": "",
        "risk_warnings": [],
        "requires_second_confirmation": False,
    }


def _profile() -> dict:
    return {
        "type": "basic_profile",
        "stage": "generated",
        "confirmed_info": {
            "current_grade": "大三",
            "major": "软件工程",
            "learning_stage": "刚入门",
            "has_clear_goal": "否",
            "learning_method_preference": "项目驱动学习",
            "learning_pace_preference": "每天少量",
            "content_preference": ["文档"],
            "need_guidance": "需要强引导",
            "knowledge_foundation": "没有基础",
            "strengths": "没有",
            "weaknesses": "缺少系统训练",
            "experience": "没有经验",
            "short_term_goal": "学习数据结构",
            "long_term_goal": "逐步形成数据结构方向的系统学习能力",
            "weekly_available_time": "每周 6-10 小时",
            "constraints": "平时学习节奏，避免过高强度",
        },
        "summary_text": "【基础学习画像总结】大三软件工程，目标是学习数据结构。",
    }


def test_intake_confirmation_query_accepts_natural_language() -> None:
    assert is_intake_confirmation_query("可以")
    assert is_intake_confirmation_query("就按这个来")
    assert is_intake_confirmation_query("听你的，可以开始")
    assert is_intake_confirmation_query("继续")
    assert not is_intake_confirmation_query("第二门课换成算法")


def test_intake_modification_query_accepts_course_change() -> None:
    assert is_intake_modification_query("第二门课换成算法")
    assert is_intake_modification_query("我想学前端")
    assert is_intake_modification_query("不想学这个")
    assert not is_intake_modification_query("就按这个来")


def test_intake_prompt_allows_required_statuses() -> None:
    assert "`draft`" in LEARNING_PATH_INTAKE_AGENT_SYSTEM_PROMPT
    assert "`confirmed`" in LEARNING_PATH_INTAKE_AGENT_SYSTEM_PROMPT
    assert "`risk_pending`" in LEARNING_PATH_INTAKE_AGENT_SYSTEM_PROMPT


def test_run_intake_agent_creates_data_structure_draft(tmp_path: Path) -> None:
    engine = build_engine(f"sqlite:///{tmp_path / 'intake-draft.db'}")
    set_engine(engine)
    init_db(engine)
    fake_llm = _FakeIntakeLLM(_llm_intake_result())

    with Session(engine) as session:
        load_or_create_session(session, "session-intake-draft", "user-1")

    result = asyncio.run(
        run_learning_path_intake_agent(
            {
                "user_id": "user-1",
                "session_id": "session-intake-draft",
                "query": "请根据我的基础画像生成学习路径。",
                "profile": _profile(),
                "messages": [
                    HumanMessage(
                        content="我现在大三、软件工程、想学习数据结构、目前不知道怎么学"
                    )
                ],
            },
            fake_llm,
        )
    )

    intake = result["learning_path_intake"]
    assert intake["type"] == "learning_path_intake"
    assert intake["status"] == "draft"
    assert intake["grade_year"] == "year_3"
    assert intake["learning_topic"] == "数据结构"
    assert 4 <= len(intake["courses"]) <= 10
    assert intake["courses"][0]["title"] == "LLM 定制复杂度与抽象数据类型"
    assert fake_llm.schema is LearningPathIntakeDraftOutput
    assert len(fake_llm.calls) == 1
    assert "AI 应用开发" not in result["response"]
    assert "LangChain" not in result["response"]
    assert "下一步是生成正式学习路径" in result["response"]
    assert "可以开始下一步吗" in result["response"]
    assert "直接回复“确认”" in result["response"]
    assert "把第2门换成" in result["response"]

    with Session(engine) as session:
        row = load_or_create_session(session, "session-intake-draft", "user-1")
        stored = latest_learning_path_intake(row.messages)

    assert stored == intake


def test_run_intake_agent_uses_llm_courses_for_natural_modification(
    tmp_path: Path,
) -> None:
    engine = build_engine(f"sqlite:///{tmp_path / 'intake-llm-modification.db'}")
    set_engine(engine)
    init_db(engine)

    courses = [
        {"title": "前端基础与浏览器工作流", "purpose": "建立前端入门基础"},
        {"title": "HTML CSS 与响应式页面", "purpose": "完成基础页面实践"},
        {"title": "JavaScript 交互基础", "purpose": "掌握页面交互"},
        {"title": "React 入门项目", "purpose": "完成组件化项目"},
    ]
    fake_llm = _FakeIntakeLLM(_llm_intake_result(courses=courses, topic="前端开发"))
    profile = _profile()
    profile["confirmed_info"]["short_term_goal"] = "学习前端"
    profile["summary_text"] = "【基础学习画像总结】大三软件工程，目标是学习前端。"

    result = asyncio.run(
        run_learning_path_intake_agent(
            {
                "user_id": "user-1",
                "session_id": "session-intake-llm-modification",
                "query": "我想学前端，课程更偏实践一点",
                "profile": profile,
                "messages": [],
            },
            fake_llm,
        )
    )

    intake = result["learning_path_intake"]
    assert intake["learning_topic"] == "前端开发"
    assert [course["title"] for course in intake["courses"]] == [
        course["title"] for course in courses
    ]
    assert len(fake_llm.calls) == 1


def test_run_intake_agent_normalizes_chinese_grade_year_from_llm(
    tmp_path: Path,
) -> None:
    engine = build_engine(f"sqlite:///{tmp_path / 'intake-chinese-grade-year.db'}")
    set_engine(engine)
    init_db(engine)

    llm_result = _llm_intake_result()
    llm_result["grade_year"] = "大三"
    fake_llm = _FakeIntakeLLM(llm_result, validate_result=False)

    result = asyncio.run(
        run_learning_path_intake_agent(
            {
                "user_id": "user-1",
                "session_id": "session-intake-chinese-grade-year",
                "query": "我现在应该干嘛？",
                "profile": _profile(),
                "messages": [],
            },
            fake_llm,
        )
    )

    intake = result["learning_path_intake"]
    assert intake["grade_year"] == "year_3"
    assert intake["grade_name"] == "大三"
    assert "error" not in result


def test_run_intake_agent_normalizes_numeric_grade_year_from_structured_llm(
    tmp_path: Path,
) -> None:
    engine = build_engine(f"sqlite:///{tmp_path / 'intake-numeric-grade-year.db'}")
    set_engine(engine)
    init_db(engine)

    profile = _profile()
    profile["confirmed_info"]["current_grade"] = "大二"
    profile["summary_text"] = "【基础学习画像总结】大二软件工程，目标是学习数据结构。"
    llm_result = _llm_intake_result()
    llm_result["grade_year"] = 2
    llm_result["grade_name"] = "大二"
    fake_llm = _FakeIntakeLLM(llm_result)

    result = asyncio.run(
        run_learning_path_intake_agent(
            {
                "user_id": "user-1",
                "session_id": "session-intake-numeric-grade-year",
                "query": "我现在应该干嘛？",
                "profile": profile,
                "messages": [],
            },
            fake_llm,
        )
    )

    intake = result["learning_path_intake"]
    assert intake["grade_year"] == "year_2"
    assert intake["grade_name"] == "大二"
    assert "error" not in result


def test_run_intake_agent_marks_existing_draft_confirmed(tmp_path: Path) -> None:
    engine = build_engine(f"sqlite:///{tmp_path / 'intake-confirm.db'}")
    set_engine(engine)
    init_db(engine)

    draft = {
        "type": "learning_path_intake",
        "status": "draft",
        "grade_year": "year_3",
        "grade_name": "大三",
        "learning_topic": "数据结构",
        "courses": [
            {"title": "数据结构入门与复杂度基础", "purpose": "建立基础"},
            {"title": "线性结构实践", "purpose": "练习线性结构"},
            {"title": "树与递归基础", "purpose": "理解递归结构"},
            {"title": "图与综合项目", "purpose": "完成综合应用"},
        ],
        "recommendation_reasons": ["目标是学习数据结构"],
        "user_modification_summary": "",
        "risk_warnings": [],
        "requires_second_confirmation": False,
    }
    state = {
        "user_id": "user-1",
        "session_id": "session-intake-confirm",
        "query": "就按这个来",
        "profile": _profile(),
        "learning_path_intake": draft,
        "messages": [],
    }

    result = asyncio.run(run_learning_path_intake_agent(state, object()))
    assert result["learning_path_intake"]["status"] == "confirmed"
    assert result["response"].startswith("好的")
    assert "下一步会生成正式学习路径" in result["response"]
    assert latest_intake_from_state(result)["status"] == "confirmed"


def test_run_intake_agent_confirms_risk_pending_and_clears_risk_fields(
    tmp_path: Path,
) -> None:
    engine = build_engine(f"sqlite:///{tmp_path / 'intake-risk-confirm.db'}")
    set_engine(engine)
    init_db(engine)

    risk_pending = {
        "type": "learning_path_intake",
        "status": "risk_pending",
        "grade_year": "year_3",
        "grade_name": "大三",
        "learning_topic": "数据结构",
        "courses": [
            {"title": "数据结构入门与复杂度基础", "purpose": "建立基础"},
            {"title": "线性结构实践", "purpose": "练习线性结构"},
            {"title": "树与递归基础", "purpose": "理解递归结构"},
            {"title": "图与综合项目", "purpose": "完成综合应用"},
        ],
        "recommendation_reasons": ["目标是学习数据结构"],
        "user_modification_summary": "想删掉已开始课程",
        "risk_warnings": ["替换/删除已开始学习的课程《旧课程》"],
        "requires_second_confirmation": True,
    }

    result = asyncio.run(
        run_learning_path_intake_agent(
            {
                "user_id": "user-1",
                "session_id": "session-intake-risk-confirm",
                "query": "确认",
                "profile": _profile(),
                "learning_path_intake": risk_pending,
                "messages": [],
            },
            object(),
        )
    )

    intake = result["learning_path_intake"]
    assert intake["status"] == "confirmed"
    assert intake["requires_second_confirmation"] is False
    assert intake["risk_warnings"] == []


def test_run_intake_agent_cancel_risk_pending_keeps_existing_path(
    tmp_path: Path,
) -> None:
    engine = build_engine(f"sqlite:///{tmp_path / 'intake-risk-cancel.db'}")
    set_engine(engine)
    init_db(engine)

    risk_pending = {
        "type": "learning_path_intake",
        "status": "risk_pending",
        "grade_year": "year_3",
        "grade_name": "大三",
        "learning_topic": "数据结构",
        "courses": [
            {"title": "数据结构入门与复杂度基础", "purpose": "建立基础"},
            {"title": "线性结构实践", "purpose": "练习线性结构"},
            {"title": "树与递归基础", "purpose": "理解递归结构"},
            {"title": "图与综合项目", "purpose": "完成综合应用"},
        ],
        "recommendation_reasons": ["目标是学习数据结构"],
        "user_modification_summary": "想删掉已开始课程",
        "risk_warnings": ["替换/删除已开始学习的课程《旧课程》"],
        "requires_second_confirmation": True,
    }

    result = asyncio.run(
        run_learning_path_intake_agent(
            {
                "user_id": "user-1",
                "session_id": "session-intake-risk-cancel",
                "query": "先不改",
                "profile": _profile(),
                "learning_path_intake": risk_pending,
                "messages": [],
            },
            object(),
        )
    )

    intake = result["learning_path_intake"]
    assert intake["status"] == "draft"
    assert intake["requires_second_confirmation"] is False
    assert intake["risk_warnings"] == []
    assert "保留原学习路径" in result["response"]
    assert "不做本次修改" in result["response"]


def test_run_intake_agent_detects_deletion_of_started_course_and_outlines(
    tmp_path: Path,
) -> None:
    from app.models import UserCourseKnowledgeOutline, UserYearLearningPath

    engine = build_engine(f"sqlite:///{tmp_path / 'intake-risk.db'}")
    set_engine(engine)
    init_db(engine)

    with Session(engine) as session:
        # Create user outline
        session.add(
            UserCourseKnowledgeOutline(
                user_uid="user-1",
                course_id="year_3_course_1",
                grade_year="year_3",
                course_name="树与递归基础",
                outline_data={},
            )
        )
        # Create year path with started course
        session.add(
            UserYearLearningPath(
                user_uid="user-1",
                grade_year="year_3",
                learning_topic="数据结构",
                path_data={
                    "schema_version": "learning_path.v2.course_node",
                    "current_learning_course": {
                        "grade_id": "year_3",
                        "course_node_id": "year_3_course_2",
                        "course_or_chapter_theme": "线性结构实践",
                        "course_goal": "掌握线性结构",
                        "time_arrangement": {
                            "semester_scope": "上学期",
                            "duration": "4周",
                            "pace_reason": "test",
                        },
                        "current_focus": "test",
                        "progress_state": "in_progress",
                        "next_action": "test",
                    },
                    "grade_plans": {
                        "year_3": {
                            "grade_id": "year_3",
                            "grade_name": "大三",
                            "grade_goal": "test",
                            "course_nodes": [
                                {
                                    "course_node_id": "year_3_course_2",
                                    "course_or_chapter_theme": "线性结构实践",
                                    "progress_state": "in_progress",
                                }
                            ],
                        }
                    },
                },
            )
        )
        session.commit()

    # Query with a modification query that doesn't include "线性结构实践" or "树与递归基础"
    # Query: "想学前端"
    profile = _profile()
    profile["confirmed_info"]["short_term_goal"] = "学习前端"
    profile["confirmed_info"]["long_term_goal"] = "系统学习前端"
    profile["summary_text"] = "【基础学习画像总结】大三软件工程，目标是学习前端。"
    fake_llm = _FakeIntakeLLM(
        _llm_intake_result(
            courses=[
                {"title": "前端基础与浏览器工作流", "purpose": "建立前端入门基础"},
                {"title": "HTML CSS 与响应式页面", "purpose": "完成基础页面实践"},
                {"title": "JavaScript 交互基础", "purpose": "掌握页面交互"},
                {"title": "React 入门项目", "purpose": "完成组件化项目"},
            ],
            topic="前端开发",
        )
    )
    result = asyncio.run(
        run_learning_path_intake_agent(
            {
                "user_id": "user-1",
                "session_id": "session-intake-risk",
                "query": "想学前端",
                "profile": profile,
                "messages": [],
            },
            fake_llm,
        )
    )

    intake = result["learning_path_intake"]
    assert intake["status"] == "risk_pending"
    assert intake["requires_second_confirmation"] is True
    assert any("树与递归基础" in w for w in intake["risk_warnings"])
    assert any("线性结构实践" in w for w in intake["risk_warnings"])
    assert "⚠️【风险提示】" in result["response"]
