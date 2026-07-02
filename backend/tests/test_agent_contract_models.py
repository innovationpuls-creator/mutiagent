from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.orchestration.agents.models import (
    ConfirmedInfoOutput,
    CourseKnowledgeOutput,
    CourseNodeOutput,
    CurrentLearningCourse,
    LearningPathCourseSpecOutput,
    LearningPathIntakeCourseOutput,
    LearningPathResultOutput,
    ProfileSessionOutput,
    QuestionFormOutput,
    SectionAnimationBriefOutput,
    SectionHtmlAnimationOutput,
    SectionItem,
    SectionMarkdownOutput,
    SectionVideoSearchOutput,
)


def _confirmed_info() -> dict:
    return {
        "current_grade": "大三",
        "major": "软件工程",
        "learning_stage": "有基础",
        "has_clear_goal": "大致有方向",
        "learning_method_preference": "项目驱动学习",
        "learning_pace_preference": "按项目里程碑推进",
        "content_preference": ["代码实践", "项目案例", "AI 对话调试"],
        "need_guidance": "需要轻量提醒",
        "knowledge_foundation": "已具备软件工程基础，AI 基础由系统补全为入门到基础",
        "strengths": "工程实现与课程学习能力",
        "weaknesses": "大型项目实战经验、数据库设计能力、英文阅读速度",
        "experience": "平时学习，项目经验由系统补全为待强化",
        "short_term_goal": (
            "在 3 个月内独立开发一个具备完整前后端功能的 Web 应用，并部署上线"
        ),
        "long_term_goal": "形成 AI 应用开发能力",
        "weekly_available_time": "每周 6-10 小时",
        "constraints": "平时学习节奏，避免过高强度",
    }


def _course_node(course_id: str, grade_id: str = "year_3") -> dict:
    return {
        "course_node_id": course_id,
        "grade_id": grade_id,
        "course_or_chapter_theme": "AI 应用开发项目课",
        "source_textbook_id": "textbook-ai-web",
        "source_textbook_title": "AI 应用开发项目教程",
        "source_outline_section_ids": ["1.1", "1.2", "1.3"],
        "course_stage_plan": ["需求拆解", "接口联调", "部署验收"],
        "time_arrangement": {
            "semester_scope": "上学期",
            "duration": "6 周",
            "pace_reason": "围绕平时学习节奏安排",
        },
        "course_goal": "完成一个 AI 功能模块并接入 Web 应用",
        "prerequisite_node_ids": [],
        "chapter_nodes": [],
        "core_knowledge_points": [],
        "key_points": ["AI API 调用", "前后端集成"],
        "difficult_points": ["工程化部署"],
        "learning_sequence": ["需求拆解", "接口联调", "部署验收"],
        "knowledge_relations": [],
        "downstream_resource_direction_ids": [],
        "acceptance_criteria": ["能独立演示完整功能"],
    }


def _section_item() -> dict:
    return {
        "section_id": "1.1",
        "parent_section_id": "1",
        "depth": 2,
        "title": "学习目标",
        "order_index": 1,
        "description": "明确本节学习目标。",
        "key_knowledge_points": ["功能边界", "验收标准"],
        "source_textbook_id": "textbook-ai-web",
        "source_textbook_title": "AI 应用开发项目教程",
        "source_section_ids": ["1.1", "1.2"],
        "source_section_titles": ["功能边界", "验收标准"],
        "source_content_chars": 3600,
    }


def _complete_markdown() -> str:
    return "\n\n".join(
        [
            "# 1.1 学习目标",
            "## 学习目标\n明确输入、输出和验收标准。",
            "<!-- video:id=video_1 -->",
            "## 核心概念\n功能边界与验收标准。",
            "## 步骤讲解\n先确认目标，再拆任务。",
            "<!-- animation:id=anim_1 -->",
            "## 练习任务\n写一张任务卡。",
            "## 检查标准\n能给出可验收产出。",
            "## 来源\n- 《AI 应用开发项目教程》：功能边界；验收标准",
        ]
    )


def _learning_path() -> dict:
    grade_plans = {
        "year_1": {
            "grade_id": "year_1",
            "grade_name": "大一",
            "grade_goal": "夯实编程基础",
            "course_nodes": [_course_node("year_1_course_1", "year_1")],
        },
        "year_2": {
            "grade_id": "year_2",
            "grade_name": "大二",
            "grade_goal": "建立工程基础",
            "course_nodes": [_course_node("year_2_course_1", "year_2")],
        },
        "year_3": {
            "grade_id": "year_3",
            "grade_name": "大三",
            "grade_goal": "完成 AI Web 项目",
            "course_nodes": [
                _course_node("year_3_course_1", "year_3"),
                _course_node("year_3_course_2", "year_3"),
            ],
        },
        "year_4": {
            "grade_id": "year_4",
            "grade_name": "大四",
            "grade_goal": "就业作品集",
            "course_nodes": [_course_node("year_4_course_1", "year_4")],
        },
    }
    return {
        "schema_version": "learning_path.v2.course_node",
        "learning_goal": {
            "target_course_or_skill": "AI 应用开发",
            "goal_type": "项目实践",
            "desired_outcome": "独立完成 AI Web 应用",
            "four_year_outcome": "形成就业级项目作品集",
        },
        "learner_baseline": {
            "current_grade": "大三",
            "major": "软件工程",
            "mastered_content": ["软件工程基础"],
            "weaknesses": ["数据库设计能力"],
            "constraints": ["平时学习"],
            "weekly_available_time": "每周 6-10 小时",
        },
        "planning_rules": {
            "node_unit": "course_node",
            "grade_boundary_rule": "按年级递进",
            "sequence_rule": "先基础后项目",
            "resource_rule": "按课程节点生成资源",
        },
        "grade_plans": grade_plans,
        "knowledge_graph": {"global_relations": [], "critical_paths": []},
        "resource_generation_contract": {
            "downstream_agents": ["learning_resource_agent"],
            "resource_directions": [],
        },
        "dynamic_update_contract": {
            "trackable_metrics": ["题目得分"],
            "update_triggers": ["score > 70"],
            "adjustment_strategy": "通过后推进课程",
        },
        "current_learning_course": {
            "grade_id": "year_3",
            "course_node_id": "year_3_course_1",
            "course_or_chapter_theme": "AI 应用开发项目课",
            "course_goal": "完成一个 AI 功能模块并接入 Web 应用",
            "time_arrangement": {
                "semester_scope": "上学期",
                "duration": "6 周",
                "pace_reason": "围绕平时学习节奏安排",
            },
            "current_focus": "正在学习 AI 应用开发项目课",
            "progress_state": "in_progress",
            "next_action": "开始第一章需求拆解",
        },
    }


def test_profile_session_output_requires_complete_confirmed_info() -> None:
    profile = ProfileSessionOutput(
        type="basic_profile",
        stage="generated",
        question_mode="question_box",
        confirmed_info=ConfirmedInfoOutput(**_confirmed_info()),
        defaulted_fields=["learning_stage"],
        question_md="画像已生成，是否进入学习路径草案智能体？",
        question_box={"question": "下一步做什么？", "options": []},
        text="【基础学习画像总结】大三软件工程 AI 方向。",
    )

    assert profile.type == "basic_profile"
    assert profile.confirmed_info.current_grade == "大三"
    assert profile.confirmed_info.content_preference == [
        "代码实践",
        "项目案例",
        "AI 对话调试",
    ]


def test_confirmed_info_normalizes_list_style_scalar_fields_from_llm() -> None:
    payload = _confirmed_info()
    payload["content_preference"] = "代码实践"
    payload["strengths"] = ["执行力强", "有课程项目经验"]
    payload["weaknesses"] = ["部署经验不足", "工程稳定性经验不足"]
    payload["constraints"] = ["平时课程比较满", "只能周末集中学习"]

    confirmed = ConfirmedInfoOutput(**payload)

    assert confirmed.content_preference == ["代码实践"]
    assert confirmed.strengths == "执行力强、有课程项目经验"
    assert confirmed.weaknesses == "部署经验不足、工程稳定性经验不足"
    assert confirmed.constraints == "平时课程比较满、只能周末集中学习"


def test_profile_session_output_defaults_sparse_question_box_options_from_llm() -> None:
    profile = ProfileSessionOutput(
        type="basic_profile",
        stage="generated",
        question_mode="question_box",
        confirmed_info=ConfirmedInfoOutput(**_confirmed_info()),
        defaulted_fields=[],
        question_md="画像已生成，是否进入学习路径草案智能体？",
        question_box={
            "question": "画像已生成，下一步要进入学习路径草案智能体吗？",
            "options": [
                {"label": "进入学习路径草案智能体", "value": "continue_path"},
                {"label": "修改画像方向", "value": "modify_profile"},
            ],
        },
        text="【基础学习画像总结】大三软件工程 AI 方向。",
    )

    assert profile.question_box.options[0].description == ""
    assert profile.question_box.options[0].target_fields == []
    assert profile.question_box.options[0].fills == {}


def test_learning_path_requires_current_learning_course() -> None:
    path = LearningPathResultOutput(**_learning_path())

    assert path.schema_version == "learning_path.v2.course_node"
    assert isinstance(path.current_learning_course, CurrentLearningCourse)
    assert path.current_learning_course.course_node_id == "year_3_course_1"
    assert path.current_learning_courses[0].course_node_id == "year_3_course_1"


def test_learning_path_rejects_missing_current_learning_course() -> None:
    payload = _learning_path()
    payload.pop("current_learning_course")

    with pytest.raises(ValidationError):
        LearningPathResultOutput(**payload)


def test_learning_path_normalizes_missing_current_learning_courses() -> None:
    path = LearningPathResultOutput(**_learning_path())

    assert len(path.current_learning_courses) == 1
    assert (
        path.current_learning_courses[0].course_node_id
        == path.current_learning_course.course_node_id
    )


def test_learning_path_rejects_invalid_current_learning_course_progress_state() -> None:
    payload = _learning_path()
    payload["current_learning_course"]["progress_state"] = "unknown"

    with pytest.raises(ValidationError):
        LearningPathResultOutput(**payload)


def test_learning_path_rejects_current_learning_course_not_started_state() -> None:
    payload = _learning_path()
    payload["current_learning_course"]["progress_state"] = "not_started"

    with pytest.raises(ValidationError):
        LearningPathResultOutput(**payload)


def test_learning_path_intake_course_requires_source_binding() -> None:
    course = LearningPathIntakeCourseOutput(
        title="AI 应用开发项目课",
        purpose="围绕项目实践建立完整开发闭环",
        source_textbook_id="textbook-ai-web",
        source_textbook_title="AI 应用开发项目教程",
        source_outline_section_ids=["1.1", "1.2"],
    )

    assert course.source_textbook_id == "textbook-ai-web"
    assert course.source_outline_section_ids == ["1.1", "1.2"]

    with pytest.raises(ValidationError):
        LearningPathIntakeCourseOutput(
            title="AI 应用开发项目课",
            purpose="围绕项目实践建立完整开发闭环",
        )


def test_learning_path_intake_course_rejects_empty_and_extra_textbook_fields() -> None:
    with pytest.raises(ValidationError):
        LearningPathIntakeCourseOutput(
            title="AI 应用开发项目课",
            purpose="围绕项目实践建立完整开发闭环",
            source_textbook_id="",
            source_textbook_title="AI 应用开发项目教程",
            source_outline_section_ids=["1.1"],
        )

    with pytest.raises(ValidationError):
        LearningPathIntakeCourseOutput(
            title="AI 应用开发项目课",
            purpose="围绕项目实践建立完整开发闭环",
            source_textbook_id="textbook-ai-web",
            source_textbook_title="AI 应用开发项目教程",
            source_outline_section_ids=["1.1"],
            source_textbook_isbn="978-7-0000-0000-0",
        )


def test_learning_path_intake_course_rejects_more_than_seven_source_sections() -> None:
    with pytest.raises(ValidationError):
        LearningPathIntakeCourseOutput(
            title="AI 应用开发项目课",
            purpose="围绕项目实践建立完整开发闭环",
            source_textbook_id="textbook-ai-web",
            source_textbook_title="AI 应用开发项目教程",
            source_outline_section_ids=[
                "1.1",
                "1.2",
                "1.3",
                "1.4",
                "1.5",
                "1.6",
                "1.7",
                "1.8",
            ],
        )


def test_course_node_requires_source_binding_and_stage_plan() -> None:
    node = CourseNodeOutput(**_course_node("year_3_course_1"))

    assert node.source_textbook_title == "AI 应用开发项目教程"
    assert node.course_stage_plan == ["需求拆解", "接口联调", "部署验收"]

    payload = _course_node("year_3_course_1")
    payload.pop("source_textbook_id")

    with pytest.raises(ValidationError):
        CourseNodeOutput(**payload)


def test_course_node_rejects_empty_binding_and_more_than_seven_sources() -> None:
    empty_payload = _course_node("year_3_course_1")
    empty_payload["source_textbook_title"] = ""

    with pytest.raises(ValidationError):
        CourseNodeOutput(**empty_payload)

    oversized_payload = _course_node("year_3_course_1")
    oversized_payload["source_outline_section_ids"] = [
        "1.1",
        "1.2",
        "1.3",
        "1.4",
        "1.5",
        "1.6",
        "1.7",
        "1.8",
    ]

    with pytest.raises(ValidationError):
        CourseNodeOutput(**oversized_payload)


def test_course_node_rejects_extra_textbook_fields() -> None:
    payload = _course_node("year_3_course_1")
    payload["source_textbook_isbn"] = "978-7-0000-0000-0"

    with pytest.raises(ValidationError):
        CourseNodeOutput(**payload)


def test_learning_path_course_spec_normalizes_string_list_fields_from_llm() -> None:
    spec = LearningPathCourseSpecOutput(
        theme="AI Agent 最小可用闭环搭建",
        semester_scope="上学期",
        duration="4周",
        pace_reason="先完成最小闭环再扩展",
        goal="完成一个可运行的 Agent 闭环原型",
        stage_titles="需求拆解、状态管理、部署验收",
        key_points="Agent 状态、工具调用、结果验证",
        difficult_points="部署链路打通；稳定性排查",
        acceptance_criteria="本地运行无崩溃，覆盖核心路径，具备边界条件测试用例。",
        difficulty_level="中级",
    )

    assert spec.stage_titles == ["需求拆解", "状态管理", "部署验收"]
    assert spec.key_points == ["Agent 状态", "工具调用", "结果验证"]
    assert spec.difficult_points == ["部署链路打通", "稳定性排查"]
    assert spec.acceptance_criteria == [
        "本地运行无崩溃",
        "覆盖核心路径",
        "具备边界条件测试用例。",
    ]


def test_course_knowledge_section_requires_source_binding() -> None:
    output = CourseKnowledgeOutput(
        course_id="year_3_course_1",
        course_name="AI 应用开发项目课",
        grade_year="大三",
        personalization_summary="围绕平时学习节奏安排。",
        sections=[SectionItem(**_section_item())],
        learning_sequence=["先明确目标", "再完成练习"],
        total_estimated_hours="6 小时",
    )

    assert output.sections[0].source_section_ids == ["1.1", "1.2"]
    assert output.sections[0].source_content_chars == 3600

    payload = _section_item()
    payload.pop("source_section_ids")

    with pytest.raises(ValidationError):
        SectionItem(**payload)


def test_section_rejects_empty_binding_and_extra_textbook_fields() -> None:
    empty_payload = _section_item()
    empty_payload["source_textbook_id"] = ""

    with pytest.raises(ValidationError):
        SectionItem(**empty_payload)

    extra_payload = _section_item()
    extra_payload["source_textbook_isbn"] = "978-7-0000-0000-0"

    with pytest.raises(ValidationError):
        SectionItem(**extra_payload)


def test_course_knowledge_section_rejects_more_than_seven_source_sections() -> None:
    payload = _section_item()
    payload["source_section_ids"] = [
        "1.1",
        "1.2",
        "1.3",
        "1.4",
        "1.5",
        "1.6",
        "1.7",
        "1.8",
    ]

    with pytest.raises(ValidationError):
        SectionItem(**payload)


def test_section_markdown_normalizes_string_visual_elements_from_llm() -> None:
    output = SectionMarkdownOutput(
        section_id="1.1",
        parent_section_id="1",
        title="学习目标",
        markdown=_complete_markdown(),
        video_briefs=[
            {
                "video_id": "video_1",
                "title": "学习目标导入视频",
                "purpose": "帮助学习者理解功能边界与验收标准",
            }
        ],
        animation_briefs=[
            {
                "animation_id": "anim_1",
                "title": "目标动画",
                "concept": "展示学习目标如何落到验收标准",
                "visual_elements": "目标卡片、任务卡片、验收标准卡片",
                "motion": "依次淡入",
                "space": "正文宽度",
                "placement_hint": "练习任务之后",
            }
        ],
    )

    assert output.animation_briefs[0].visual_elements == [
        "目标卡片、任务卡片、验收标准卡片"
    ]


def test_section_markdown_rejects_missing_source_footer() -> None:
    with pytest.raises(ValidationError):
        SectionMarkdownOutput(
            section_id="1.1",
            parent_section_id="1",
            title="学习目标",
            markdown="\n\n".join(
                [
                    "# 1.1 学习目标",
                    "## 学习目标\n明确输入、输出和验收标准。",
                    "<!-- video:id=video_1 -->",
                    "## 核心概念\n功能边界与验收标准。",
                    "## 步骤讲解\n先确认目标，再拆任务。",
                    "<!-- animation:id=anim_1 -->",
                    "## 练习任务\n写一张任务卡。",
                    "## 检查标准\n能给出可验收产出。",
                ]
            ),
            video_briefs=[
                {
                    "video_id": "video_1",
                    "title": "学习目标导入视频",
                    "purpose": "帮助学习者理解功能边界与验收标准",
                }
            ],
            animation_briefs=[
                {
                    "animation_id": "anim_1",
                    "title": "目标动画",
                    "concept": "展示学习目标如何落到验收标准",
                    "visual_elements": ["目标卡片", "任务卡片", "验收标准卡片"],
                    "motion": "依次淡入",
                    "space": "正文宽度",
                    "placement_hint": "练习任务之后",
                }
            ],
        )


def test_section_markdown_rejects_empty_source_footer() -> None:
    with pytest.raises(ValidationError):
        SectionMarkdownOutput(
            section_id="1.1",
            parent_section_id="1",
            title="学习目标",
            markdown=_complete_markdown().replace(
                "## 来源\n- 《AI 应用开发项目教程》：功能边界；验收标准",
                "## 来源\n  ",
            ),
            video_briefs=[
                {
                    "video_id": "video_1",
                    "title": "学习目标导入视频",
                    "purpose": "帮助学习者理解功能边界与验收标准",
                }
            ],
            animation_briefs=[
                {
                    "animation_id": "anim_1",
                    "title": "目标动画",
                    "concept": "展示学习目标如何落到验收标准",
                    "visual_elements": ["目标卡片", "任务卡片", "验收标准卡片"],
                    "motion": "依次淡入",
                    "space": "正文宽度",
                    "placement_hint": "练习任务之后",
                }
            ],
        )


def test_section_markdown_rejects_non_terminal_source_footer() -> None:
    with pytest.raises(ValidationError):
        SectionMarkdownOutput(
            section_id="1.1",
            parent_section_id="1",
            title="学习目标",
            markdown=_complete_markdown()
            + "\n\n## 检查标准\n来源段后不允许继续追加二级标题。",
            video_briefs=[
                {
                    "video_id": "video_1",
                    "title": "学习目标导入视频",
                    "purpose": "帮助学习者理解功能边界与验收标准",
                }
            ],
            animation_briefs=[
                {
                    "animation_id": "anim_1",
                    "title": "目标动画",
                    "concept": "展示学习目标如何落到验收标准",
                    "visual_elements": ["目标卡片", "任务卡片", "验收标准卡片"],
                    "motion": "依次淡入",
                    "space": "正文宽度",
                    "placement_hint": "练习任务之后",
                }
            ],
        )


def test_section_markdown_rejects_repeated_source_footer() -> None:
    markdown = _complete_markdown().replace(
        "## 来源\n- 《AI 应用开发项目教程》：功能边界；验收标准",
        (
            "## 来源\n- 《AI 应用开发项目教程》：功能边界；验收标准"
            "\n\n## 检查标准\n来源段后不允许继续追加二级标题。"
            "\n\n## 来源\n- 重复来源"
        ),
    )

    with pytest.raises(ValidationError):
        SectionMarkdownOutput(
            section_id="1.1",
            parent_section_id="1",
            title="学习目标",
            markdown=markdown,
            video_briefs=[
                {
                    "video_id": "video_1",
                    "title": "学习目标导入视频",
                    "purpose": "帮助学习者理解功能边界与验收标准",
                }
            ],
            animation_briefs=[
                {
                    "animation_id": "anim_1",
                    "title": "目标动画",
                    "concept": "展示学习目标如何落到验收标准",
                    "visual_elements": ["目标卡片", "任务卡片", "验收标准卡片"],
                    "motion": "依次淡入",
                    "space": "正文宽度",
                    "placement_hint": "练习任务之后",
                }
            ],
        )


def test_section_markdown_rejects_missing_resource_briefs() -> None:
    with pytest.raises(ValidationError):
        SectionMarkdownOutput(
            section_id="1.1",
            parent_section_id="1",
            title="学习目标",
            markdown="# 1.1 学习目标\n\n## 学习目标\n目标说明。",
            video_briefs=[],
            animation_briefs=[],
        )


def test_section_markdown_rejects_low_quality_fallback_markers() -> None:
    with pytest.raises(ValidationError):
        SectionMarkdownOutput(
            section_id="1.1",
            parent_section_id="1",
            title="学习目标",
            markdown="\n\n".join(
                [
                    "# 1.1 学习目标",
                    "## 学习目标\n目标说明。",
                    "<!-- video:id=video_1 -->",
                    (
                        "## 核心概念\nKey Concept\n"
                        "This section explores foundational concepts."
                    ),
                    "## 步骤讲解\n先确认目标，再拆任务。",
                    "<!-- animation:id=anim_1 -->",
                    "## 练习任务\n写一张任务卡。",
                    "## 检查标准\n能给出可验收产出。",
                ]
            ),
            video_briefs=[
                {
                    "video_id": "video_1",
                    "title": "学习目标导入视频",
                    "purpose": "帮助学习者理解功能边界与验收标准",
                }
            ],
            animation_briefs=[
                {
                    "animation_id": "anim_1",
                    "title": "目标动画",
                    "concept": "展示学习目标如何落到验收标准",
                    "visual_elements": ["目标卡片", "任务卡片", "验收标准卡片"],
                    "motion": "依次淡入",
                    "space": "正文宽度",
                    "placement_hint": "练习任务之后",
                }
            ],
        )


def test_section_markdown_rejects_missing_teaching_headings() -> None:
    with pytest.raises(ValidationError):
        SectionMarkdownOutput(
            section_id="1.1",
            parent_section_id="1",
            title="学习目标",
            markdown="\n\n".join(
                [
                    "# 1.1 学习目标",
                    "## 学习目标\n目标说明。",
                    "<!-- video:id=video_1 -->",
                    "## 核心概念\n功能边界与验收标准。",
                    "## 步骤讲解\n先确认目标，再拆任务。",
                    "<!-- animation:id=anim_1 -->",
                ]
            ),
            video_briefs=[
                {
                    "video_id": "video_1",
                    "title": "学习目标导入视频",
                    "purpose": "帮助学习者理解功能边界与验收标准",
                }
            ],
            animation_briefs=[
                {
                    "animation_id": "anim_1",
                    "title": "目标动画",
                    "concept": "展示学习目标如何落到验收标准",
                    "visual_elements": ["目标卡片", "任务卡片", "验收标准卡片"],
                    "motion": "依次淡入",
                    "space": "正文宽度",
                    "placement_hint": "练习任务之后",
                }
            ],
        )


def test_section_markdown_rejects_placeholder_id_mismatch() -> None:
    with pytest.raises(ValidationError):
        SectionMarkdownOutput(
            section_id="1.1",
            parent_section_id="1",
            title="学习目标",
            markdown="\n\n".join(
                [
                    "# 1.1 学习目标",
                    "## 学习目标\n明确输入、输出和验收标准。",
                    "<!-- video:id=wrong_video -->",
                    "## 核心概念\n功能边界与验收标准。",
                    "## 步骤讲解\n先确认目标，再拆任务。",
                    "<!-- animation:id=anim_1 -->",
                    "## 练习任务\n写一张任务卡。",
                    "## 检查标准\n能给出可验收产出。",
                ]
            ),
            video_briefs=[
                {
                    "video_id": "video_1",
                    "title": "学习目标导入视频",
                    "purpose": "帮助学习者理解功能边界与验收标准",
                }
            ],
            animation_briefs=[
                {
                    "animation_id": "anim_1",
                    "title": "目标动画",
                    "concept": "展示学习目标如何落到验收标准",
                    "visual_elements": ["目标卡片", "任务卡片", "验收标准卡片"],
                    "motion": "依次淡入",
                    "space": "正文宽度",
                    "placement_hint": "练习任务之后",
                }
            ],
        )


def test_section_animation_brief_normalizes_visual_elements_and_motion_steps() -> None:
    output = SectionAnimationBriefOutput(
        animation_id="anim_1",
        title="接口调用流程动画",
        concept="展示输入如何经过校验后进入异步 LLM 调用",
        visual_elements=[
            {"element": "User Input Card", "content": "{ query: '...' }"},
            {"element": "Validation Box", "content": "Check Syntax (Sync)"},
            {"element": "LLM Cloud Icon", "content": "Generate Answer (Async)"},
        ],
        motion=[
            "Data packet moves from User Input Card to Validation Box.",
            "Then it waits at the LLM Cloud Icon before returning the answer.",
        ],
        space="正文宽度",
        placement_hint="步骤讲解之后",
    )

    assert output.visual_elements == [
        "User Input Card：{ query: '...' }",
        "Validation Box：Check Syntax (Sync)",
        "LLM Cloud Icon：Generate Answer (Async)",
    ]
    assert output.motion == (
        "Data packet moves from User Input Card to Validation Box.\n"
        "Then it waits at the LLM Cloud Icon before returning the answer."
    )


def test_section_animation_brief_normalizes_structured_space() -> None:
    output = SectionAnimationBriefOutput(
        animation_id="anim_1",
        title="检查点流程动画",
        concept="展示运行证据如何被保存",
        visual_elements=["用户输入", "Agent", "日志"],
        motion="节点依次淡入",
        space={"width": "600px", "height": "400px"},
        placement_hint={"after": "练习任务"},
    )

    assert output.space == '{"width": "600px", "height": "400px"}'
    assert output.placement_hint == '{"after": "练习任务"}'


def test_section_video_search_allows_missing_top_level_query_fields_from_llm() -> None:
    output = SectionVideoSearchOutput(
        videos=[
            {
                "brief_id": "video_1",
                "title": "需求拆解视频",
                "url": "https://www.bilibili.com/video/example",
                "cover_url": "",
                "source": "Bilibili",
            }
        ]
    )

    assert output.section_id == ""
    assert output.query == ""
    assert output.videos[0].brief_id == "video_1"


def test_section_html_animation_allows_missing_top_level_and_item_title_from_llm() -> (
    None
):
    output = SectionHtmlAnimationOutput(
        animations=[
            {
                "animation_id": "anim_1",
                "html": (
                    '<div class="section-animation"><style></style><p>目标</p></div>'
                ),
            }
        ]
    )

    assert output.section_id == ""
    assert output.animations[0].title == ""
    assert "section-animation" in output.animations[0].html


def test_profile_session_output_supports_question_form() -> None:
    question_data = {
        "field_name": "major",
        "label": "所学专业",
        "description": "输入你的专业名称",
        "input_type": "free_text",
        "required": True,
        "options": [],
    }

    form_data = {
        "title": "专业基本信息",
        "description": "请提供您的专业信息以帮助我们定制学习计划",
        "stage": "basic_info",
        "questions": [question_data],
        "submit_label": "确认提交",
    }

    profile = ProfileSessionOutput(
        type="basic_profile",
        stage="basic_info",
        question_mode="question_box",
        confirmed_info=ConfirmedInfoOutput(**_confirmed_info()),
        defaulted_fields=[],
        question_md="请填写表单",
        question_box={"question": "表单", "options": []},
        question_form=QuestionFormOutput(**form_data),
        text="请填写以下表单：",
    )

    assert profile.question_form is not None
    assert profile.question_form.title == "专业基本信息"
    assert profile.question_form.submit_label == "确认提交"
    assert len(profile.question_form.questions) == 1
    assert profile.question_form.questions[0].field_name == "major"
    assert profile.question_form.questions[0].required is True
    assert profile.question_form.questions[0].options == []
