from __future__ import annotations

import asyncio
from pathlib import Path

from langchain_core.messages import HumanMessage
from sqlmodel import Session, select

from app.database import build_engine, init_db, set_engine
from app.models import KnowledgeGap, User
from app.orchestration.agents.learning_path_intake import (
    _bind_fallback_course_sources,
    _build_intake_generation_input,
    _courses_for_topic,
    _require_intake_courses_from_knowledge_context,
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
from tests.fixtures.knowledge_base import enabled_source, published_textbook, section
from tests.postgres import postgresql_test_url


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


def _intake_course(title: str, purpose: str, section_id: str) -> dict:
    return {
        "title": title,
        "purpose": purpose,
        "source_textbook_id": "textbook-data-structures",
        "source_textbook_title": "数据结构教材",
        "source_outline_section_ids": [section_id],
    }


def _llm_intake_result(
    *, courses: list[dict] | None = None, topic: str = "数据结构"
) -> dict:
    return {
        "type": "learning_path_intake",
        "status": "draft",
        "grade_year": "year_3",
        "grade_name": "大三",
        "learning_topic": topic,
        "courses": courses
        or [
            _intake_course(
                "LLM 定制复杂度与抽象数据类型",
                "先理解数据结构的分析语言",
                "1.1",
            ),
            _intake_course("LLM 定制线性表与栈队列", "掌握线性结构实现", "2.1"),
            _intake_course("LLM 定制树结构与递归", "建立递归结构理解", "3.1"),
            _intake_course("LLM 定制图结构项目", "完成综合实践", "4.1"),
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


def _seed_published_textbook_context(
    session: Session,
    *,
    topic: str = "数据结构",
    textbook_id: str = "textbook-data-structures",
    title: str = "数据结构教材",
) -> None:
    source_id = f"source-{textbook_id}"
    session.add(enabled_source(source_id=source_id))
    textbook = published_textbook(
        textbook_id=textbook_id,
        source_id=source_id,
        title=title,
    )
    textbook.description = f"覆盖{topic}、线性结构、树、图。"
    textbook.tags = [topic, "线性结构", "树", "图"]
    textbook.outline = {
        "sections": [
            {"section_id": "1.1", "title": f"{topic}基础"},
            {"section_id": "2.1", "title": "线性结构"},
            {"section_id": "3.1", "title": "树结构"},
            {"section_id": "4.1", "title": "图结构"},
        ]
    }
    session.add(textbook)
    session.add(
        section(
            textbook_id=textbook_id,
            section_content_id=f"section-{textbook_id}-body",
            section_id="1.1",
            title=f"{topic}基础",
            content_zh="这段教材正文不能进入课程草案输入。",
        )
    )
    session.commit()


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


def test_intake_generation_input_declares_downstream_order_and_resource_boundary() -> (
    None
):
    generation_input = _build_intake_generation_input(
        {
            "year_learning_paths": {},
        },
        "我想学习数据结构",
        _profile(),
        None,
        {
            "textbooks": [
                {
                    "textbook_id": "textbook-data-structures",
                    "title": "数据结构教材",
                    "sections": [
                        {"section_id": "1.1", "title": "复杂度分析"},
                        {"section_id": "2.1", "title": "单链表"},
                    ],
                }
            ],
            "gap_id": None,
        },
    )

    assert "课程顺序会被正式学习路径智能体严格继承" in generation_input
    assert (
        "source_outline_section_ids 会继续传递给大纲、Markdown、视频和动画智能体"
        in generation_input
    )
    assert "每门课程的 purpose 必须说明教材小节覆盖的具体学习边界" in generation_input


def test_run_intake_agent_creates_data_structure_draft(tmp_path: Path) -> None:
    engine = build_engine(postgresql_test_url(tmp_path, "intake-draft"))
    set_engine(engine)
    init_db(engine)
    fake_llm = _FakeIntakeLLM(_llm_intake_result())

    with Session(engine) as session:
        session.add(
            User(uid="user-1", username="课程用户", identifier="course@example.com")
        )
        _seed_published_textbook_context(session)
        load_or_create_session(session, "session-intake-draft", "user-1")

    result = asyncio.run(
        run_learning_path_intake_agent(
            {
                "user_id": "user-1",
                "session_id": "session-intake-draft",
                "query": "进入学习路径草案智能体",
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
    assert 4 <= len(intake["courses"]) <= 8
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


def test_run_intake_agent_injects_published_textbook_context_without_body(
    tmp_path: Path,
) -> None:
    engine = build_engine(postgresql_test_url(tmp_path, "intake-kb-context"))
    set_engine(engine)
    init_db(engine)
    fake_llm = _FakeIntakeLLM(_llm_intake_result())

    with Session(engine) as session:
        session.add(
            User(uid="user-1", username="课程用户", identifier="course@example.com")
        )
        _seed_published_textbook_context(
            session,
            topic="数据结构",
            textbook_id="textbook-data-structures",
            title="数据结构教材",
        )
        load_or_create_session(session, "session-intake-kb-context", "user-1")

    result = asyncio.run(
        run_learning_path_intake_agent(
            {
                "user_id": "user-1",
                "session_id": "session-intake-kb-context",
                "query": "进入学习路径草案智能体",
                "profile": _profile(),
                "messages": [],
            },
            fake_llm,
        )
    )

    assert "error" not in result
    assert len(fake_llm.calls) == 1
    human_message = fake_llm.calls[0][1]
    assert "已发布知识库教材上下文" in human_message.content
    assert "textbook-data-structures" in human_message.content
    assert "数据结构基础" in human_message.content
    assert "这段教材正文不能进入课程草案输入" not in human_message.content
    assert "content_zh" not in human_message.content


def test_fallback_data_structure_courses_bind_matching_outline_sections() -> None:
    knowledge_context = {
        "textbooks": [
            {
                "textbook_id": "textbook-data-structures",
                "title": "数据结构教材",
                "outline_summary": [
                    {"section_id": "1.1", "title": "复杂度分析与抽象数据类型"},
                    {"section_id": "2.1", "title": "数组、链表、栈与队列"},
                    {"section_id": "3.1", "title": "树结构与递归遍历"},
                    {"section_id": "4.1", "title": "查找、排序与哈希"},
                    {"section_id": "5.1", "title": "图结构与综合项目"},
                ],
            }
        ],
        "gap_id": None,
    }

    courses = _bind_fallback_course_sources(
        _courses_for_topic("数据结构"),
        {},
        "year_3",
        knowledge_context,
    )

    assert courses[0]["source_outline_section_ids"] == ["1.1"]
    assert courses[1]["source_outline_section_ids"] == ["2.1"]
    assert courses[2]["source_outline_section_ids"] == ["3.1"]
    assert courses[3]["source_outline_section_ids"] == ["4.1"]
    assert courses[4]["source_outline_section_ids"] == ["5.1"]


def test_intake_normalization_rejects_unknown_outline_sections() -> None:
    knowledge_context = {
        "textbooks": [
            {
                "textbook_id": "textbook-data-structures",
                "title": "数据结构教材",
                "outline_summary": [
                    {"section_id": "1.1", "title": "复杂度分析"},
                    {"section_id": "2.1", "title": "线性结构"},
                ],
            }
        ],
        "gap_id": None,
    }
    intake = _llm_intake_result(
        courses=[
            _intake_course("错误小节绑定", "验证不存在的小节会被拒绝", "9.9"),
            _intake_course("线性表", "继续学习线性结构", "2.1"),
            _intake_course("树结构", "学习树", "2.1"),
            _intake_course("图结构", "学习图", "2.1"),
        ]
    )

    try:
        _require_intake_courses_from_knowledge_context(intake, knowledge_context)
    except ValueError as exc:
        assert str(exc) == "课程草案教材小节不在已发布知识库上下文中。"
    else:
        raise AssertionError("课程草案必须拒绝不存在的教材小节绑定。")


def test_run_intake_agent_returns_gap_without_draft_when_no_published_textbook(
    tmp_path: Path,
) -> None:
    engine = build_engine(postgresql_test_url(tmp_path, "intake-kb-gap"))
    set_engine(engine)
    init_db(engine)
    fake_llm = _FakeIntakeLLM(_llm_intake_result())

    result = asyncio.run(
        run_learning_path_intake_agent(
            {
                "user_id": "user-1",
                "session_id": "session-intake-kb-gap",
                "query": "进入学习路径草案智能体",
                "profile": _profile(),
                "messages": [],
            },
            fake_llm,
        )
    )

    assert "learning_path_intake" not in result
    assert result["gap_id"]
    assert result["error"] == (
        "知识库暂无覆盖「数据结构」的已发布教材，已加入管理员待办。"
    )
    assert fake_llm.calls == []
    with Session(engine) as session:
        gap = session.exec(
            select(KnowledgeGap).where(KnowledgeGap.gap_id == result["gap_id"])
        ).one()
    assert gap.normalized_topic == "数据结构"


def test_run_intake_agent_uses_llm_courses_for_natural_modification(
    tmp_path: Path,
) -> None:
    engine = build_engine(postgresql_test_url(tmp_path, "intake-llm-modification"))
    set_engine(engine)
    init_db(engine)
    with Session(engine) as session:
        _seed_published_textbook_context(session, topic="前端开发")

    courses = [
        _intake_course("前端基础与浏览器工作流", "建立前端入门基础", "1.1"),
        _intake_course("HTML CSS 与响应式页面", "完成基础页面实践", "2.1"),
        _intake_course("JavaScript 交互基础", "掌握页面交互", "3.1"),
        _intake_course("React 入门项目", "完成组件化项目", "4.1"),
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
    engine = build_engine(postgresql_test_url(tmp_path, "intake-chinese-grade-year"))
    set_engine(engine)
    init_db(engine)
    with Session(engine) as session:
        _seed_published_textbook_context(session)

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
    engine = build_engine(postgresql_test_url(tmp_path, "intake-numeric-grade-year"))
    set_engine(engine)
    init_db(engine)
    with Session(engine) as session:
        _seed_published_textbook_context(session)

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
    engine = build_engine(postgresql_test_url(tmp_path, "intake-confirm"))
    set_engine(engine)
    init_db(engine)

    draft = {
        "type": "learning_path_intake",
        "status": "draft",
        "grade_year": "year_3",
        "grade_name": "大三",
        "learning_topic": "数据结构",
        "courses": [
            _intake_course("数据结构入门与复杂度基础", "建立基础", "1.1"),
            _intake_course("线性结构实践", "练习线性结构", "2.1"),
            _intake_course("树与递归基础", "理解递归结构", "3.1"),
            _intake_course("图与综合项目", "完成综合应用", "4.1"),
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
    engine = build_engine(postgresql_test_url(tmp_path, "intake-risk-confirm"))
    set_engine(engine)
    init_db(engine)

    risk_pending = {
        "type": "learning_path_intake",
        "status": "risk_pending",
        "grade_year": "year_3",
        "grade_name": "大三",
        "learning_topic": "数据结构",
        "courses": [
            _intake_course("数据结构入门与复杂度基础", "建立基础", "1.1"),
            _intake_course("线性结构实践", "练习线性结构", "2.1"),
            _intake_course("树与递归基础", "理解递归结构", "3.1"),
            _intake_course("图与综合项目", "完成综合应用", "4.1"),
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
    engine = build_engine(postgresql_test_url(tmp_path, "intake-risk-cancel"))
    set_engine(engine)
    init_db(engine)

    risk_pending = {
        "type": "learning_path_intake",
        "status": "risk_pending",
        "grade_year": "year_3",
        "grade_name": "大三",
        "learning_topic": "数据结构",
        "courses": [
            _intake_course("数据结构入门与复杂度基础", "建立基础", "1.1"),
            _intake_course("线性结构实践", "练习线性结构", "2.1"),
            _intake_course("树与递归基础", "理解递归结构", "3.1"),
            _intake_course("图与综合项目", "完成综合应用", "4.1"),
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

    engine = build_engine(postgresql_test_url(tmp_path, "intake-risk"))
    set_engine(engine)
    init_db(engine)

    with Session(engine) as session:
        session.add(
            User(uid="user-1", username="课程用户", identifier="course@example.com")
        )
        _seed_published_textbook_context(session, topic="前端开发")
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

    # Query with a modification query that excludes started course names.
    # Query: "想学前端"
    profile = _profile()
    profile["confirmed_info"]["short_term_goal"] = "学习前端"
    profile["confirmed_info"]["long_term_goal"] = "系统学习前端"
    profile["summary_text"] = "【基础学习画像总结】大三软件工程，目标是学习前端。"
    fake_llm = _FakeIntakeLLM(
        _llm_intake_result(
            courses=[
                _intake_course("前端基础与浏览器工作流", "建立前端入门基础", "1.1"),
                _intake_course("HTML CSS 与响应式页面", "完成基础页面实践", "2.1"),
                _intake_course("JavaScript 交互基础", "掌握页面交互", "3.1"),
                _intake_course("React 入门项目", "完成组件化项目", "4.1"),
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
