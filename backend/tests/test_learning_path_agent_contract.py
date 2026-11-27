"""Contract tests for the learning path agent."""

# ruff: noqa: E501

from __future__ import annotations

from app.orchestration.agents.learning_path import (
    _build_learning_path_from_plan,
    _validate_learning_path_contract,
)


def _complete_profile(
    summary_text: str = "【基础学习画像总结】大3软件工程，当前以AI 应用开发为主线。",
) -> dict:
    return {
        "type": "basic_profile",
        "stage": "generated",
        "question_mode": "question_box",
        "confirmed_info": {
            "current_grade": "大3",
            "major": "软件工程",
            "learning_stage": "有基础",
            "has_clear_goal": "大致有方向",
            "learning_method_preference": "项目驱动学习",
            "learning_pace_preference": "按项目里程碑推进",
            "content_preference": ["代码实践", "项目案例", "AI 对话调试"],
            "need_guidance": "需要轻量提醒",
            "knowledge_foundation": "已具备软件工程基础，AI 应用开发方向可从入门到基础逐步补全",
            "strengths": "工程实现与课程学习能力",
            "weaknesses": "大型项目实战经验、数据库设计能力、英文阅读速度",
            "experience": "平时学习",
            "short_term_goal": "围绕AI 应用开发完成一个可运行的课程级项目",
            "long_term_goal": "形成AI 应用开发方向的应用开发能力",
            "weekly_available_time": "每周 6-10 小时",
            "constraints": "平时学习节奏，避免过高强度",
        },
        "defaulted_fields": [],
        "question_md": "画像已生成，是否进入学习路径草案智能体？",
        "question_box": {
            "question": "画像已生成，下一步要进入学习路径草案智能体吗？",
            "options": [],
        },
        "text": summary_text,
        "summary_text": summary_text,
    }


def _confirmed_intake(
    *,
    grade_year: str = "year_3",
    grade_name: str = "大三",
    learning_topic: str = "数据结构",
    course_titles: list[str] | None = None,
) -> dict:
    titles = course_titles or [
        "数据结构入门与复杂度基础",
        "线性结构实践",
        "树与递归基础",
        "查找排序与哈希",
        "图结构与综合项目",
    ]
    return {
        "type": "learning_path_intake",
        "status": "confirmed",
        "grade_year": grade_year,
        "grade_name": grade_name,
        "learning_topic": learning_topic,
        "courses": [
            {
                "title": title,
                "purpose": f"完成 {title} 的关键训练",
                "source_textbook_id": f"textbook-{index}",
                "source_textbook_title": f"{learning_topic}教材 {index}",
                "source_outline_section_ids": [
                    f"textbook-{index}-section-1",
                    f"textbook-{index}-section-2",
                ],
            }
            for index, title in enumerate(titles, start=1)
        ],
        "recommendation_reasons": [f"目标是学习{learning_topic}"],
        "user_modification_summary": "",
        "risk_warnings": [],
        "requires_second_confirmation": False,
    }


AI_COURSE_TITLES = [
    "AI Agent 最小可用闭环搭建",
    "AI Agent 多节点编排与联调",
    "AI Agent 工程化调试与评测",
    "AI Agent 部署上线与稳定性复盘",
]


def _llm_learning_path_payload() -> dict:
    return {
        "schema_version": "learning_path.v2.course_node",
        "learning_goal": {
            "target_course_or_skill": "AI 应用开发",
            "goal_type": "项目实践",
            "desired_outcome": "独立完成一个 AI 应用项目",
            "four_year_outcome": "形成就业级项目作品集",
        },
        "learner_baseline": {
            "current_grade": "大三",
            "major": "软件工程",
            "mastered_content": ["软件工程基础"],
            "weaknesses": ["多智能体编排经验"],
            "constraints": ["平时学习节奏"],
            "weekly_available_time": "每周 6-10 小时",
        },
        "planning_rules": {
            "node_unit": "course_node",
            "grade_boundary_rule": "按年级递进",
            "sequence_rule": "先基础后项目，先单体闭环后多智能体协作",
            "resource_rule": "按课程节点生成资源",
        },
        "grade_plans": {
            "year_1": {
                "grade_id": "year_1",
                "grade_name": "大一",
                "grade_goal": "夯实基础",
                "course_nodes": [
                    {
                        "course_node_id": "year_1_course_1",
                        "grade_id": "year_1",
                        "course_or_chapter_theme": "编程与算法基础",
                        "time_arrangement": {
                            "semester_scope": "上学期",
                            "duration": "8 周",
                            "pace_reason": "先打基础",
                        },
                        "course_goal": "完成编程基础训练",
                        "prerequisite_node_ids": [],
                        "chapter_nodes": [],
                        "core_knowledge_points": [],
                        "key_points": ["Python 基础"],
                        "difficult_points": ["抽象建模"],
                        "learning_sequence": ["语法", "数据结构", "算法"],
                        "knowledge_relations": [],
                        "downstream_resource_direction_ids": [],
                        "acceptance_criteria": ["完成基础练习"],
                    }
                ],
            },
            "year_2": {
                "grade_id": "year_2",
                "grade_name": "大二",
                "grade_goal": "建立工程能力",
                "course_nodes": [
                    {
                        "course_node_id": "year_2_course_1",
                        "grade_id": "year_2",
                        "course_or_chapter_theme": "工程化 Web 开发基础",
                        "time_arrangement": {
                            "semester_scope": "上学期",
                            "duration": "8 周",
                            "pace_reason": "建立前后端协作能力",
                        },
                        "course_goal": "完成基础 Web 应用",
                        "prerequisite_node_ids": ["year_1_course_1"],
                        "chapter_nodes": [],
                        "core_knowledge_points": [],
                        "key_points": ["接口设计"],
                        "difficult_points": ["数据建模"],
                        "learning_sequence": ["接口", "数据库", "联调"],
                        "knowledge_relations": [],
                        "downstream_resource_direction_ids": [],
                        "acceptance_criteria": ["完成一个基础 Web 应用"],
                    }
                ],
            },
            "year_3": {
                "grade_id": "year_3",
                "grade_name": "大三",
                "grade_goal": "完成 AI 项目闭环",
                "course_nodes": [
                    {
                        "course_node_id": "year_3_course_1",
                        "grade_id": "year_3",
                        "course_or_chapter_theme": "AI 应用开发基础能力搭建",
                        "time_arrangement": {
                            "semester_scope": "上学期",
                            "duration": "6 周",
                            "pace_reason": "围绕平时学习节奏安排",
                        },
                        "course_goal": "完成最小功能闭环",
                        "prerequisite_node_ids": ["year_2_course_1"],
                        "chapter_nodes": [],
                        "core_knowledge_points": [],
                        "key_points": ["Prompt 设计", "前后端联调"],
                        "difficult_points": ["错误处理与重试"],
                        "learning_sequence": ["需求拆解", "接口接入", "最小闭环演示"],
                        "knowledge_relations": [],
                        "downstream_resource_direction_ids": [],
                        "acceptance_criteria": [
                            "完成一个可运行的 AI 功能模块并接入 Web 应用"
                        ],
                    },
                    {
                        "course_node_id": "year_3_course_2",
                        "grade_id": "year_3",
                        "course_or_chapter_theme": "AI 应用开发项目实战",
                        "time_arrangement": {
                            "semester_scope": "下学期",
                            "duration": "8 周",
                            "pace_reason": "在基础闭环后进入复杂项目",
                        },
                        "course_goal": "完成课程级项目",
                        "prerequisite_node_ids": ["year_3_course_1"],
                        "chapter_nodes": [],
                        "core_knowledge_points": [],
                        "key_points": ["LangGraph 编排", "SSE 流式交互"],
                        "difficult_points": ["线上稳定性"],
                        "learning_sequence": ["架构设计", "多智能体联调", "部署验收"],
                        "knowledge_relations": [],
                        "downstream_resource_direction_ids": [],
                        "acceptance_criteria": ["支持真实用户流程与部署演示"],
                    },
                ],
            },
            "year_4": {
                "grade_id": "year_4",
                "grade_name": "大四",
                "grade_goal": "沉淀作品集",
                "course_nodes": [
                    {
                        "course_node_id": "year_4_course_1",
                        "grade_id": "year_4",
                        "course_or_chapter_theme": "就业级作品集与迭代优化",
                        "time_arrangement": {
                            "semester_scope": "上学期",
                            "duration": "10 周",
                            "pace_reason": "围绕求职展示打磨",
                        },
                        "course_goal": "形成作品集",
                        "prerequisite_node_ids": ["year_3_course_2"],
                        "chapter_nodes": [],
                        "core_knowledge_points": [],
                        "key_points": ["项目复盘"],
                        "difficult_points": ["方案表达"],
                        "learning_sequence": ["项目复盘", "优化迭代", "作品集整理"],
                        "knowledge_relations": [],
                        "downstream_resource_direction_ids": [],
                        "acceptance_criteria": ["形成就业级项目作品集"],
                    }
                ],
            },
        },
        "knowledge_graph": {"global_relations": [], "critical_paths": []},
        "resource_generation_contract": {
            "downstream_agents": ["learning_resource_agent"],
            "resource_directions": [],
        },
        "dynamic_update_contract": {
            "trackable_metrics": ["项目里程碑完成度"],
            "update_triggers": ["里程碑完成"],
            "adjustment_strategy": "根据验收结果调整课程推进节奏",
        },
        "current_learning_course": {
            "grade_id": "year_3",
            "course_node_id": "year_3_course_1",
            "course_or_chapter_theme": "AI 应用开发基础能力搭建",
            "course_goal": "完成最小功能闭环",
            "time_arrangement": {
                "semester_scope": "上学期",
                "duration": "6 周",
                "pace_reason": "围绕平时学习节奏安排",
            },
            "current_focus": "优先搭建最小闭环并补齐错误处理能力",
            "progress_state": "in_progress",
            "next_action": "先完成需求拆解并确认验收边界",
        },
    }


def _llm_learning_path_plan_payload(
    course_themes: list[str],
    *,
    goal_type: str = "项目实践",
    grade_goal: str = "完成 AI 项目闭环",
    desired_outcome: str = "完成一个可上线并可演示的 AI Agent 项目",
    four_year_outcome: str = "形成就业级项目作品集",
    current_focus: str = "先聚焦最小可用闭环与部署稳定性",
    next_action: str = "先完成第一门课的需求拆解与验收边界确认",
) -> dict:
    return {
        "goal_type": goal_type,
        "grade_goal": grade_goal,
        "desired_outcome": desired_outcome,
        "four_year_outcome": four_year_outcome,
        "current_focus": current_focus,
        "next_action": next_action,
        "course_specs": [
            {
                "theme": theme,
                "semester_scope": "上学期" if index < len(course_themes) else "下学期",
                "duration": "6 周" if index != 2 else "8 周",
                "pace_reason": "围绕周末集中与上线目标安排",
                "goal": f"完成 {theme} 对应的关键训练",
                "stage_titles": [
                    f"{theme}需求拆解",
                    f"{theme}实现联调",
                    f"{theme}验收复盘",
                ],
                "key_points": [
                    f"{theme}能力点 1",
                    f"{theme}能力点 2",
                    f"{theme}能力点 3",
                ],
                "difficult_points": [f"{theme}部署稳定性", f"{theme}调试与回归"],
                "acceptance_criteria": [f"完成 {theme} 的阶段验收并可演示"],
                "difficulty_level": "中级",
            }
            for index, theme in enumerate(course_themes, start=1)
        ],
    }


def _single_year_learning_path_payload(
    grade_year: str,
    grade_name: str,
    grade_goal: str,
    course_themes: list[str],
    *,
    topic: str = "AI 应用开发",
) -> dict:
    course_nodes: list[dict] = []
    for index, theme in enumerate(course_themes, start=1):
        course_nodes.append(
            {
                "course_node_id": f"{grade_year}_course_{index}",
                "grade_id": grade_year,
                "course_or_chapter_theme": theme,
                "time_arrangement": {
                    "semester_scope": "上学期"
                    if index < len(course_themes)
                    else "下学期",
                    "duration": "6 周",
                    "pace_reason": "围绕当前阶段学习目标逐步推进",
                },
                "course_goal": f"完成 {theme} 对应的核心训练",
                "prerequisite_node_ids": [f"{grade_year}_course_{index - 1}"]
                if index > 1
                else [],
                "chapter_nodes": [
                    {
                        "chapter_node_id": f"{grade_year}_course_{index}_chapter_1",
                        "chapter_theme": f"{theme} 拆解",
                        "knowledge_hierarchy": [],
                        "core_knowledge_point_ids": [],
                        "key_points": [f"{theme} 重点"],
                        "difficult_points": [f"{theme} 难点"],
                        "prerequisite_node_ids": [],
                        "learning_sequence": [f"{theme} 学习顺序"],
                        "knowledge_relations": [],
                        "downstream_resource_direction_ids": [
                            f"{grade_year}_course_{index}_resource"
                        ],
                    }
                ],
                "core_knowledge_points": [
                    {
                        "knowledge_point_id": f"{grade_year}_course_{index}_kp_1",
                        "name": f"{theme} 核心知识",
                        "parent_knowledge_point_id": None,
                        "level": "核心",
                        "description": f"{theme} 的关键知识点",
                        "mastery_standard": f"能把 {theme} 用到项目任务里",
                    }
                ],
                "key_points": [f"{theme} 重点"],
                "difficult_points": [f"{theme} 难点"],
                "learning_sequence": [f"{theme} 学习顺序"],
                "knowledge_relations": [],
                "downstream_resource_direction_ids": [
                    f"{grade_year}_course_{index}_resource"
                ],
                "acceptance_criteria": [f"完成 {theme} 的阶段验收"],
            }
        )

    current_course = course_nodes[0]
    return {
        "schema_version": "learning_path.v2.course_node",
        "learning_goal": {
            "target_course_or_skill": topic,
            "goal_type": "项目实践",
            "desired_outcome": f"围绕 {topic} 完成目标学年学习闭环",
            "four_year_outcome": "形成就业级项目作品集",
        },
        "learner_baseline": {
            "current_grade": grade_name,
            "major": "软件工程",
            "mastered_content": ["软件工程基础"],
            "weaknesses": ["工程化能力"],
            "constraints": ["平时学习节奏"],
            "weekly_available_time": "每周 6-10 小时",
        },
        "planning_rules": {
            "node_unit": "course_node",
            "grade_boundary_rule": "按年级递进",
            "sequence_rule": "同一年级内按课程顺序递进",
            "resource_rule": "按课程节点生成资源",
        },
        "grade_plans": {
            grade_year: {
                "grade_id": grade_year,
                "grade_name": grade_name,
                "grade_goal": grade_goal,
                "course_nodes": course_nodes,
            }
        },
        "knowledge_graph": {
            "global_relations": [],
            "critical_paths": [
                {
                    "path_id": f"{grade_year}_critical_path",
                    "purpose": f"{grade_name}主学习路径",
                    "ordered_node_ids": [
                        course["course_node_id"] for course in course_nodes
                    ],
                }
            ],
        },
        "resource_generation_contract": {
            "downstream_agents": ["learning_resource_agent"],
            "resource_directions": [
                {
                    "resource_direction_id": f"{course['course_node_id']}_resource",
                    "target_node_ids": [course["course_node_id"]],
                    "resource_type": "文档",
                    "generation_goal": f"围绕 {course['course_or_chapter_theme']} 生成资源",
                    "content_requirements": ["包含阶段任务", "包含验收标准"],
                    "difficulty_level": "中级"
                    if grade_year in {"year_3", "year_4"}
                    else "基础",
                }
                for course in course_nodes
            ],
        },
        "dynamic_update_contract": {
            "trackable_metrics": ["项目里程碑完成度"],
            "update_triggers": ["milestone completed"],
            "adjustment_strategy": "结合已完成课程数调整后续课程重点",
        },
        "current_learning_course": {
            "grade_id": grade_year,
            "course_node_id": current_course["course_node_id"],
            "course_or_chapter_theme": current_course["course_or_chapter_theme"],
            "course_goal": current_course["course_goal"],
            "time_arrangement": current_course["time_arrangement"],
            "current_focus": f"优先完成 {current_course['course_or_chapter_theme']}",
            "progress_state": "in_progress",
            "next_action": "先完成第一阶段任务拆解",
        },
    }


def test_validate_learning_path_contract_rejects_missing_current_course() -> None:
    result = _validate_learning_path_contract(
        {"schema_version": "learning_path.v2.course_node", "grade_plans": {}}
    )

    assert result == "学习路径缺少 current_learning_course。"


def test_validate_learning_path_contract_rejects_current_course_that_is_not_active_or_completed() -> (
    None
):
    payload = _llm_learning_path_payload()
    payload["current_learning_course"]["progress_state"] = "not_started"

    result = _validate_learning_path_contract(payload)

    assert (
        result
        == "current_learning_course.progress_state 必须是 in_progress 或 completed。"
    )


def test_validate_learning_path_contract_rejects_grade_with_less_than_three_courses() -> (
    None
):
    payload = _single_year_learning_path_payload(
        "year_3",
        "大三",
        "完成 AI 项目闭环",
        ["AI 应用开发基础能力搭建", "AI 应用开发项目实战"],
    )

    result = _validate_learning_path_contract(payload)

    assert result == "当前学年课程数量必须在 4 到 8 门之间。"


def test_build_learning_path_from_plan_preserves_confirmed_course_source_binding() -> (
    None
):
    intake = _confirmed_intake(
        learning_topic="AI 应用开发",
        course_titles=AI_COURSE_TITLES,
    )
    plan_data = _llm_learning_path_plan_payload(
        [
            "模型返回标题 1",
            "模型返回标题 2",
            "模型返回标题 3",
            "模型返回标题 4",
        ]
    )

    path = _build_learning_path_from_plan(
        _complete_profile(),
        grade_year="year_3",
        learning_topic="AI 应用开发",
        plan_data=plan_data,
        intake_courses=intake["courses"],
    )

    course_nodes = path["grade_plans"]["year_3"]["course_nodes"]
    for index, course_node in enumerate(course_nodes):
        intake_course = intake["courses"][index]
        assert course_node["course_or_chapter_theme"] == intake_course["title"]
        assert course_node["source_textbook_id"] == intake_course["source_textbook_id"]
        assert (
            course_node["source_textbook_title"]
            == intake_course["source_textbook_title"]
        )
        assert (
            course_node["source_outline_section_ids"]
            == intake_course["source_outline_section_ids"]
        )
        assert (
            course_node["course_stage_plan"]
            == plan_data["course_specs"][index]["stage_titles"]
        )


def test_build_learning_path_from_full_path_uses_intake_source_binding() -> None:
    intake = _confirmed_intake(
        learning_topic="AI 应用开发",
        course_titles=AI_COURSE_TITLES,
    )
    plan_data = _single_year_learning_path_payload(
        "year_3",
        "大三",
        "完成 AI 项目闭环",
        [
            "模型返回标题 1",
            "模型返回标题 2",
            "模型返回标题 3",
            "模型返回标题 4",
        ],
    )
    for index, course_node in enumerate(
        plan_data["grade_plans"]["year_3"]["course_nodes"],
        start=1,
    ):
        course_node["source_textbook_id"] = f"model-textbook-{index}"
        course_node["source_textbook_title"] = f"模型教材 {index}"
        course_node["source_outline_section_ids"] = [f"model-section-{index}"]
        course_node["course_stage_plan"] = [f"模型阶段 {index}"]

    path = _build_learning_path_from_plan(
        _complete_profile(),
        grade_year="year_3",
        learning_topic="AI 应用开发",
        plan_data=plan_data,
        intake_courses=intake["courses"],
    )

    course_nodes = path["grade_plans"]["year_3"]["course_nodes"]
    for index, course_node in enumerate(course_nodes):
        intake_course = intake["courses"][index]
        assert course_node["course_or_chapter_theme"] == intake_course["title"]
        assert course_node["source_textbook_id"] == intake_course["source_textbook_id"]
        assert (
            course_node["source_textbook_title"]
            == intake_course["source_textbook_title"]
        )
        assert (
            course_node["source_outline_section_ids"]
            == intake_course["source_outline_section_ids"]
        )


def test_data_structure_learning_path_uses_confirmed_textbook_sections_over_model_sources() -> (
    None
):
    intake = _confirmed_intake(
        learning_topic="数据结构",
        course_titles=[
            "复杂度分析与线性结构基础",
            "树与递归基础",
            "查找排序与哈希",
            "图结构与综合项目",
        ],
    )
    intake["courses"][0]["source_textbook_id"] = "textbook-data-structures"
    intake["courses"][0]["source_textbook_title"] = "数据结构教程"
    intake["courses"][0]["source_outline_section_ids"] = ["1.1", "1.2"]

    plan_data = _single_year_learning_path_payload(
        "year_3",
        "大三",
        "完成数据结构基础训练",
        [
            "模型改写的复杂度课程",
            "模型改写的树课程",
            "模型改写的排序课程",
            "模型改写的图课程",
        ],
    )
    first_course = plan_data["grade_plans"]["year_3"]["course_nodes"][0]
    first_course["source_textbook_id"] = "model-textbook"
    first_course["source_textbook_title"] = "模型替换教材"
    first_course["source_outline_section_ids"] = ["9.9"]

    path = _build_learning_path_from_plan(
        _complete_profile(),
        grade_year="year_3",
        learning_topic="数据结构",
        plan_data=plan_data,
        intake_courses=intake["courses"],
    )

    first_node = path["grade_plans"]["year_3"]["course_nodes"][0]
    assert first_node["course_or_chapter_theme"] == "复杂度分析与线性结构基础"
    assert first_node["source_textbook_id"] == "textbook-data-structures"
    assert first_node["source_textbook_title"] == "数据结构教程"
    assert first_node["source_outline_section_ids"] == ["1.1", "1.2"]
