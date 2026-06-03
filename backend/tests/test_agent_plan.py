from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.orchestration.agent_plan import (
    AgentCall,
    CourseKnowledgeOutlineResult,
    LearningPathResult,
    MainAgentResult,
    normalize_learning_path_result_payload,
    validate_call_graph,
)

def test_main_agent_result_requires_known_agent_key() -> None:
    with pytest.raises(ValidationError):
        MainAgentResult.model_validate(
            {
                "response": {"user_message": "处理中", "question_box": None},
                "control": {
                    "action": "call_agents",
                    "calls": [
                        {
                            "call_id": "bad_call",
                            "agent_key": "unknown_agent",
                            "label": "未知",
                            "depends_on": [],
                            "parallel_group": None,
                            "agent_input": {},
                        }
                    ],
                },
            }
        )


def test_main_agent_result_accepts_course_knowledge_agent_key() -> None:
    result = MainAgentResult.model_validate(
        {
            "response": {"user_message": "我会生成当前课程章节。", "question_box": None},
            "control": {
                "action": "call_agents",
                "calls": [
                    {
                        "call_id": "course_knowledge",
                        "agent_key": "course_knowledge_agent",
                        "label": "课程知识点规划智能体",
                        "depends_on": [],
                        "parallel_group": None,
                        "agent_input": {},
                    }
                ],
            },
        }
    )

    assert result.control.calls[0].agent_key == "course_knowledge_agent"


def test_validate_call_graph_rejects_missing_dependency() -> None:
    call = AgentCall(
        call_id="learning_path",
        agent_key="learning_path_agent",
        label="学习路径",
        depends_on=["profile_missing"],
        parallel_group=None,
        agent_input={},
    )

    with pytest.raises(ValueError, match="depends_on references unknown call_id"):
        validate_call_graph([call])


def build_learning_path_result() -> dict:
    return {
        "schema_version": "learning_path.v2.course_node",
        "learning_goal": {
            "target_course_or_skill": "计算机专业能力",
            "goal_type": "就业准备",
            "desired_outcome": "具备独立完成后端项目与面试表达的能力",
            "four_year_outcome": "形成从基础编程到工程实践的完整能力链路",
        },
        "learner_baseline": {
            "current_grade": "准大一",
            "major": "计算机科学与技术",
            "mastered_content": ["Python 基础语法"],
            "weaknesses": ["算法复杂度理解不稳定"],
            "constraints": ["每周学习时间有限"],
            "weekly_available_time": "每周 8 小时",
        },
        "planning_rules": {
            "node_unit": "course_node",
            "grade_boundary_rule": "每个 course_node 必须只属于一个 grade_id，不能跨年级安排；跨年级内容必须拆成多个 course_node。",
            "sequence_rule": "先完成编程基础，再进入数据结构、工程实践和项目综合。",
            "resource_rule": "每个课程节点必须提供后续资源生成方向。",
        },
        "grade_plans": {
            "year_1": {
                "grade_id": "year_1",
                "grade_name": "大一",
                "grade_goal": "打牢编程与数学基础",
                "course_nodes": [
                    {
                        "course_node_id": "year_1_course_1",
                        "grade_id": "year_1",
                        "course_or_chapter_theme": "程序设计基础",
                        "time_arrangement": {
                            "semester_scope": "上学期",
                            "duration": "3 个月",
                            "pace_reason": "先建立基础语法与调试习惯",
                        },
                        "course_goal": "能独立完成小型命令行程序",
                        "prerequisite_node_ids": [],
                        "chapter_nodes": [
                            {
                                "chapter_node_id": "year_1_course_1_chapter_1",
                                "chapter_theme": "变量、流程控制与函数",
                                "knowledge_hierarchy": [
                                    {
                                        "hierarchy_id": "hier_year_1_course_1",
                                        "parent_hierarchy_id": None,
                                        "hierarchy_level": "课程",
                                        "title": "程序设计基础",
                                        "summary": "建立编程表达能力",
                                        "knowledge_point_ids": ["kp_programming_basic"],
                                    }
                                ],
                                "core_knowledge_point_ids": ["kp_programming_basic"],
                                "key_points": ["函数拆分", "调试习惯"],
                                "difficult_points": ["循环边界", "状态变化追踪"],
                                "prerequisite_node_ids": [],
                                "learning_sequence": ["变量", "条件", "循环", "函数"],
                                "knowledge_relations": [
                                    {
                                        "from_node_id": "kp_programming_basic",
                                        "to_node_id": "year_1_course_1_chapter_1",
                                        "relation_type": "contains",
                                        "description": "章节包含基础编程知识点",
                                    }
                                ],
                                "downstream_resource_direction_ids": ["resource_programming_basic_doc"],
                            }
                        ],
                        "core_knowledge_points": [
                            {
                                "knowledge_point_id": "kp_programming_basic",
                                "name": "基础编程表达",
                                "parent_knowledge_point_id": None,
                                "level": "基础",
                                "description": "使用变量、分支、循环和函数表达解题过程",
                                "mastery_standard": "能独立写出带函数拆分的小程序",
                            }
                        ],
                        "key_points": ["基础语法", "函数拆分", "调试"],
                        "difficult_points": ["边界条件", "变量状态"],
                        "learning_sequence": ["year_1_course_1_chapter_1"],
                        "knowledge_relations": [
                            {
                                "from_node_id": "year_1_course_1_chapter_1",
                                "to_node_id": "year_1_course_1",
                                "relation_type": "contains",
                                "description": "课程节点包含章节节点",
                            }
                        ],
                        "downstream_resource_direction_ids": ["resource_programming_basic_doc"],
                        "acceptance_criteria": ["完成 3 个基础编程项目"],
                    }
                ],
            },
            "year_2": {
                "grade_id": "year_2",
                "grade_name": "大二",
                "grade_goal": "进入数据结构与数据库",
                "course_nodes": [
                    {
                        "course_node_id": "year_2_course_1",
                        "grade_id": "year_2",
                        "course_or_chapter_theme": "数据结构",
                        "time_arrangement": {
                            "semester_scope": "上学期",
                            "duration": "4 个月",
                            "pace_reason": "需要连续练习抽象结构与复杂度分析",
                        },
                        "course_goal": "掌握线性表、树和图的基础应用",
                        "prerequisite_node_ids": ["year_1_course_1"],
                        "chapter_nodes": [
                            {
                                "chapter_node_id": "year_2_course_1_chapter_1",
                                "chapter_theme": "线性表与复杂度",
                                "knowledge_hierarchy": [
                                    {
                                        "hierarchy_id": "hier_year_2_course_1",
                                        "parent_hierarchy_id": None,
                                        "hierarchy_level": "课程",
                                        "title": "数据结构",
                                        "summary": "用结构化方式组织和处理数据",
                                        "knowledge_point_ids": ["kp_linear_list"],
                                    }
                                ],
                                "core_knowledge_point_ids": ["kp_linear_list"],
                                "key_points": ["数组", "链表", "复杂度"],
                                "difficult_points": ["指针关系", "复杂度推导"],
                                "prerequisite_node_ids": ["year_1_course_1_chapter_1"],
                                "learning_sequence": ["数组", "链表", "复杂度"],
                                "knowledge_relations": [
                                    {
                                        "from_node_id": "year_1_course_1",
                                        "to_node_id": "year_2_course_1_chapter_1",
                                        "relation_type": "prerequisite",
                                        "description": "程序设计基础是线性表实现的先修内容",
                                    }
                                ],
                                "downstream_resource_direction_ids": ["resource_linear_list_question_bank"],
                            }
                        ],
                        "core_knowledge_points": [
                            {
                                "knowledge_point_id": "kp_linear_list",
                                "name": "线性表",
                                "parent_knowledge_point_id": None,
                                "level": "核心",
                                "description": "数组和链表的结构、操作与复杂度",
                                "mastery_standard": "能实现并分析常见线性表操作",
                            }
                        ],
                        "key_points": ["抽象结构", "复杂度", "实现能力"],
                        "difficult_points": ["指针操作", "边界条件"],
                        "learning_sequence": ["year_2_course_1_chapter_1"],
                        "knowledge_relations": [
                            {
                                "from_node_id": "year_1_course_1",
                                "to_node_id": "year_2_course_1",
                                "relation_type": "prerequisite",
                                "description": "数据结构依赖程序设计基础",
                            }
                        ],
                        "downstream_resource_direction_ids": ["resource_linear_list_question_bank"],
                        "acceptance_criteria": ["完成线性表实现与复杂度分析"],
                    }
                ],
            },
            "year_3": {
                "grade_id": "year_3",
                "grade_name": "大三",
                "grade_goal": "完成后端工程实践",
                "course_nodes": [
                    {
                        "course_node_id": "year_3_course_1",
                        "grade_id": "year_3",
                        "course_or_chapter_theme": "后端项目实践",
                        "time_arrangement": {
                            "semester_scope": "下学期",
                            "duration": "2 个月",
                            "pace_reason": "集中完成完整项目闭环",
                        },
                        "course_goal": "完成可部署的后端服务",
                        "prerequisite_node_ids": ["year_2_course_1"],
                        "chapter_nodes": [
                            {
                                "chapter_node_id": "year_3_course_1_chapter_1",
                                "chapter_theme": "接口、数据库与鉴权",
                                "knowledge_hierarchy": [
                                    {
                                        "hierarchy_id": "hier_year_3_course_1",
                                        "parent_hierarchy_id": None,
                                        "hierarchy_level": "课程",
                                        "title": "后端项目实践",
                                        "summary": "把数据结构与数据库能力转化为工程项目",
                                        "knowledge_point_ids": ["kp_backend_api"],
                                    }
                                ],
                                "core_knowledge_point_ids": ["kp_backend_api"],
                                "key_points": ["API 设计", "数据库建模", "鉴权"],
                                "difficult_points": ["边界设计", "事务一致性"],
                                "prerequisite_node_ids": ["year_2_course_1"],
                                "learning_sequence": ["接口设计", "数据库", "鉴权"],
                                "knowledge_relations": [
                                    {
                                        "from_node_id": "year_2_course_1",
                                        "to_node_id": "year_3_course_1_chapter_1",
                                        "relation_type": "applies_to",
                                        "description": "数据结构能力用于接口数据建模",
                                    }
                                ],
                                "downstream_resource_direction_ids": ["resource_backend_code_example"],
                            }
                        ],
                        "core_knowledge_points": [
                            {
                                "knowledge_point_id": "kp_backend_api",
                                "name": "后端 API 设计",
                                "parent_knowledge_point_id": None,
                                "level": "应用",
                                "description": "设计可维护的接口、数据模型和鉴权流程",
                                "mastery_standard": "能独立完成一个带鉴权的 CRUD 服务",
                            }
                        ],
                        "key_points": ["接口契约", "数据库", "鉴权"],
                        "difficult_points": ["错误处理", "服务边界"],
                        "learning_sequence": ["year_3_course_1_chapter_1"],
                        "knowledge_relations": [
                            {
                                "from_node_id": "year_2_course_1",
                                "to_node_id": "year_3_course_1",
                                "relation_type": "applies_to",
                                "description": "工程实践应用前置课程能力",
                            }
                        ],
                        "downstream_resource_direction_ids": ["resource_backend_code_example"],
                        "acceptance_criteria": ["完成一个可部署后端项目"],
                    }
                ],
            },
            "year_4": {
                "grade_id": "year_4",
                "grade_name": "大四",
                "grade_goal": "作品集与就业准备",
                "course_nodes": [
                    {
                        "course_node_id": "year_4_course_1",
                        "grade_id": "year_4",
                        "course_or_chapter_theme": "项目复盘与面试表达",
                        "time_arrangement": {
                            "semester_scope": "上学期",
                            "duration": "1 个月",
                            "pace_reason": "把已有项目转化为可展示成果",
                        },
                        "course_goal": "形成作品集和面试叙述",
                        "prerequisite_node_ids": ["year_3_course_1"],
                        "chapter_nodes": [
                            {
                                "chapter_node_id": "year_4_course_1_chapter_1",
                                "chapter_theme": "项目复盘",
                                "knowledge_hierarchy": [
                                    {
                                        "hierarchy_id": "hier_year_4_course_1",
                                        "parent_hierarchy_id": None,
                                        "hierarchy_level": "课程",
                                        "title": "项目复盘与面试表达",
                                        "summary": "把工程项目整理成就业材料",
                                        "knowledge_point_ids": ["kp_project_review"],
                                    }
                                ],
                                "core_knowledge_point_ids": ["kp_project_review"],
                                "key_points": ["问题背景", "技术取舍", "结果表达"],
                                "difficult_points": ["取舍表达", "量化成果"],
                                "prerequisite_node_ids": ["year_3_course_1"],
                                "learning_sequence": ["项目背景", "技术方案", "复盘表达"],
                                "knowledge_relations": [
                                    {
                                        "from_node_id": "year_3_course_1",
                                        "to_node_id": "year_4_course_1_chapter_1",
                                        "relation_type": "resource_basis_for",
                                        "description": "后端项目是复盘材料的基础",
                                    }
                                ],
                                "downstream_resource_direction_ids": ["resource_project_video_script"],
                            }
                        ],
                        "core_knowledge_points": [
                            {
                                "knowledge_point_id": "kp_project_review",
                                "name": "项目复盘表达",
                                "parent_knowledge_point_id": None,
                                "level": "应用",
                                "description": "把项目目标、技术方案和结果整理成面试表达",
                                "mastery_standard": "能用 3 分钟讲清一个项目",
                            }
                        ],
                        "key_points": ["作品集", "面试表达", "复盘"],
                        "difficult_points": ["简洁表达", "突出贡献"],
                        "learning_sequence": ["year_4_course_1_chapter_1"],
                        "knowledge_relations": [
                            {
                                "from_node_id": "year_3_course_1",
                                "to_node_id": "year_4_course_1",
                                "relation_type": "resource_basis_for",
                                "description": "已有项目支撑就业材料生成",
                            }
                        ],
                        "downstream_resource_direction_ids": ["resource_project_video_script"],
                        "acceptance_criteria": ["完成作品集文档和项目讲解稿"],
                    }
                ],
            },
        },
        "knowledge_graph": {
            "global_relations": [
                {
                    "from_node_id": "year_1_course_1",
                    "to_node_id": "year_2_course_1",
                    "relation_type": "prerequisite",
                    "description": "程序设计基础是数据结构学习的先修课程节点",
                }
            ],
            "critical_paths": [
                {
                    "path_id": "backend_employment_path",
                    "purpose": "形成后端就业能力",
                    "ordered_node_ids": ["year_1_course_1", "year_2_course_1", "year_3_course_1", "year_4_course_1"],
                }
            ],
        },
        "resource_generation_contract": {
            "downstream_agents": [
                "learning_resource_agent",
                "question_bank_agent",
                "document_agent",
                "code_example_agent",
                "video_script_agent",
                "dynamic_update_agent",
            ],
            "resource_directions": [
                {
                    "resource_direction_id": "resource_programming_basic_doc",
                    "target_node_ids": ["year_1_course_1"],
                    "resource_type": "文档",
                    "generation_goal": "生成程序设计基础讲义",
                    "content_requirements": ["包含概念解释", "包含练习入口"],
                    "difficulty_level": "入门",
                }
            ],
        },
        "dynamic_update_contract": {
            "trackable_metrics": ["课程节点完成率", "章节验收通过率"],
            "update_triggers": ["连续两周未完成计划", "章节测验低于 70 分"],
            "adjustment_strategy": "只调整同一年级内未完成的 course_node，不把节点移动到其他年级。",
        },
    }


def test_learning_path_result_accepts_course_node_schema() -> None:
    result = LearningPathResult.model_validate(
        build_learning_path_result()
    )

    assert result.schema_version == "learning_path.v2.course_node"
    assert result.grade_plans.year_1.course_nodes[0].course_node_id == "year_1_course_1"
    assert result.grade_plans.year_4.course_nodes[0].time_arrangement.duration == "1 个月"


def build_course_knowledge_outline_result() -> dict:
    return {
        "schema_version": "course_knowledge_outline.v1",
        "course_node_id": "year_1_course_1",
        "course_name": "程序设计基础",
        "grade_id": "year_1",
        "personalization_summary": "围绕用户已有 Python 基础和循环边界薄弱点定制章节。",
        "sections": [
            {
                "section_id": "1",
                "parent_section_id": None,
                "depth": 1,
                "title": "第 1 章 用程序表达问题",
                "order_index": 1,
            },
            {
                "section_id": "1.1",
                "parent_section_id": "1",
                "depth": 2,
                "title": "1.1 变量、输入输出与调试习惯",
                "order_index": 2,
            },
            {
                "section_id": "1.2",
                "parent_section_id": "1",
                "depth": 2,
                "title": "1.2 分支、循环边界与状态追踪",
                "order_index": 3,
            },
        ],
        "learning_sequence": ["1", "1.1", "1.2"],
        "markmap_source": "# 程序设计基础\n## 第 1 章 用程序表达问题\n### 1.1 变量、输入输出与调试习惯\n### 1.2 分支、循环边界与状态追踪",
    }


def test_course_knowledge_outline_result_accepts_flat_sections() -> None:
    result = CourseKnowledgeOutlineResult.model_validate(build_course_knowledge_outline_result())

    assert result.schema_version == "course_knowledge_outline.v1"
    assert result.sections[1].parent_section_id == "1"


def test_course_knowledge_outline_result_rejects_unknown_learning_sequence() -> None:
    data = build_course_knowledge_outline_result()
    data["learning_sequence"] = ["1", "9.9"]

    with pytest.raises(ValidationError, match="learning_sequence"):
        CourseKnowledgeOutlineResult.model_validate(data)


def test_learning_path_result_rejects_course_node_crossing_grade_boundary() -> None:
    data = build_learning_path_result()
    data["grade_plans"]["year_1"]["course_nodes"][0]["grade_id"] = "year_2"

    with pytest.raises(ValidationError, match="course_node grade_id must match parent grade_id"):
        LearningPathResult.model_validate(data)


def test_normalize_learning_path_result_payload_repairs_deep_empty_lists_and_level_alias() -> None:
    data = build_learning_path_result()
    year_2_node = dict(data["grade_plans"]["year_2"]["course_nodes"][0])
    year_2_node["course_node_id"] = "year_2_course_2"
    year_2_node["course_or_chapter_theme"] = "数据库系统"
    year_2_node["chapter_nodes"] = []
    year_2_node["knowledge_relations"] = []
    data["grade_plans"]["year_2"]["course_nodes"].append(year_2_node)
    data["grade_plans"]["year_3"]["course_nodes"][0]["chapter_nodes"] = []
    data["grade_plans"]["year_3"]["course_nodes"][0]["knowledge_relations"] = []
    data["grade_plans"]["year_4"]["course_nodes"][0]["chapter_nodes"] = []
    data["grade_plans"]["year_4"]["course_nodes"][0]["knowledge_relations"] = []
    data["grade_plans"]["year_4"]["course_nodes"][0]["core_knowledge_points"][0]["level"] = "高级"

    normalized = normalize_learning_path_result_payload(data)
    result = LearningPathResult.model_validate(normalized)

    repaired_year_2_node = result.grade_plans.year_2.course_nodes[1]
    repaired_year_3_node = result.grade_plans.year_3.course_nodes[0]
    repaired_year_4_node = result.grade_plans.year_4.course_nodes[0]
    assert repaired_year_2_node.chapter_nodes[0].chapter_node_id == "year_2_course_2_chapter_1"
    assert repaired_year_2_node.knowledge_relations[0].relation_type == "contains"
    assert repaired_year_3_node.chapter_nodes[0].chapter_node_id == "year_3_course_1_chapter_1"
    assert repaired_year_4_node.core_knowledge_points[0].level == "进阶"


def test_normalize_learning_path_result_payload_repairs_empty_course_node_core_fields() -> None:
    data = build_learning_path_result()
    year_2_node = dict(data["grade_plans"]["year_2"]["course_nodes"][0])
    year_2_node["course_node_id"] = "year_2_course_2"
    year_2_node["course_or_chapter_theme"] = "数据库系统"
    year_2_node["chapter_nodes"] = []
    year_2_node["core_knowledge_points"] = []
    year_2_node["knowledge_relations"] = []
    data["grade_plans"]["year_2"]["course_nodes"].append(year_2_node)

    for grade_id, node_index in [("year_3", 0), ("year_4", 0)]:
        course_node = data["grade_plans"][grade_id]["course_nodes"][node_index]
        course_node["chapter_nodes"] = []
        course_node["core_knowledge_points"] = []
        course_node["knowledge_relations"] = []

    normalized = normalize_learning_path_result_payload(data)
    result = LearningPathResult.model_validate(normalized)

    repaired_year_2_node = result.grade_plans.year_2.course_nodes[1]
    repaired_year_3_node = result.grade_plans.year_3.course_nodes[0]
    repaired_year_4_node = result.grade_plans.year_4.course_nodes[0]
    assert repaired_year_2_node.core_knowledge_points[0].knowledge_point_id == "kp_year_2_course_2"
    assert repaired_year_2_node.chapter_nodes[0].core_knowledge_point_ids == ["kp_year_2_course_2"]
    assert repaired_year_2_node.knowledge_relations[0].from_node_id == "year_2_course_2_chapter_1"
    assert repaired_year_3_node.core_knowledge_points[0].knowledge_point_id == "kp_year_3_course_1"
    assert repaired_year_3_node.chapter_nodes[0].chapter_node_id == "year_3_course_1_chapter_1"
    assert repaired_year_4_node.core_knowledge_points[0].knowledge_point_id == "kp_year_4_course_1"
    assert repaired_year_4_node.knowledge_relations[0].to_node_id == "year_4_course_1"


def test_question_box_option_accepts_string() -> None:
    from app.orchestration.agent_plan import QuestionBoxOption
    
    option = QuestionBoxOption.model_validate("生成「FastAPI + AI ...战」的教学资源")
    assert option.label == "生成「FastAPI + AI ...战」的教学资源"
    assert option.value == "生成「FastAPI + AI ...战」的教学资源"
    assert option.description == ""
    assert option.target_fields == ["query"]
    assert option.fills == {"query": "生成「FastAPI + AI ...战」的教学资源"}
