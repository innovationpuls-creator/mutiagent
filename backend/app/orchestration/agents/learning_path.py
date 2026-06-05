from __future__ import annotations

import json
import logging

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import ToolMessage
from langchain_core.prompts import ChatPromptTemplate

from app.orchestration.agents.models import YearLearningPathOutput
from app.orchestration.agents.prompts import LEARNING_PATH_AGENT_SYSTEM_PROMPT
from app.orchestration.agents.utils import extract_last_tool_call_args, extract_last_tool_call_id
from app.orchestration.state import OrchestrationState

logger = logging.getLogger(__name__)

DEFAULT_PATH_COMMANDS = ("默认", "直接", "随便帮我填", "不确定的你随便帮我填", "帮我生成")
GRADE_YEAR_MAP = {
    "大一": "year_1",
    "大1": "year_1",
    "一年级": "year_1",
    "大二": "year_2",
    "大2": "year_2",
    "二年级": "year_2",
    "大三": "year_3",
    "大3": "year_3",
    "三年级": "year_3",
    "大四": "year_4",
    "大4": "year_4",
    "四年级": "year_4",
}
DEFAULT_TOPIC = "AI 应用开发"


def _allows_default_path(text: str) -> bool:
    return any(command in text for command in DEFAULT_PATH_COMMANDS)


def _grade_year_from_profile(profile: dict) -> str:
    confirmed = profile.get("confirmed_info", {}) if isinstance(profile, dict) else {}
    current_grade = str(confirmed.get("current_grade", ""))
    for label, grade_year in GRADE_YEAR_MAP.items():
        if label in current_grade:
            return grade_year
    return ""


def _topic_from_profile(profile: dict) -> str:
    confirmed = profile.get("confirmed_info", {}) if isinstance(profile, dict) else {}
    text_candidates = [
        str(confirmed.get("short_term_goal", "")),
        str(confirmed.get("long_term_goal", "")),
        str(profile.get("summary_text", "")) if isinstance(profile, dict) else "",
        str(profile.get("text", "")) if isinstance(profile, dict) else "",
    ]
    combined = "\n".join(text_candidates).lower()
    if "前端" in combined:
        return "前端开发"
    if "后端" in combined:
        return "后端开发"
    if "ai" in combined:
        return DEFAULT_TOPIC
    return DEFAULT_TOPIC


def _validate_learning_path_contract(path_data: dict) -> str:
    if path_data.get("schema_version") != "learning_path.v2.course_node":
        return "学习路径 schema_version 不正确。"
    current = path_data.get("current_learning_course")
    if not isinstance(current, dict):
        return "学习路径缺少 current_learning_course。"
    grade_id = current.get("grade_id")
    course_id = current.get("course_node_id")
    grade_plans = path_data.get("grade_plans")
    if not isinstance(grade_plans, dict):
        return "current_learning_course.grade_id 无法定位。"
    grade_plan = grade_plans.get(grade_id)
    if not isinstance(grade_plan, dict):
        return "current_learning_course.grade_id 无法定位。"
    course_nodes = grade_plan.get("course_nodes")
    if not isinstance(course_nodes, list):
        return "current_learning_course.course_node_id 无法定位。"
    if not any(
        isinstance(course, dict) and course.get("course_node_id") == course_id
        for course in course_nodes
    ):
        return "current_learning_course.course_node_id 无法定位。"
    return ""


def _persist_learning_path(user_id: str, grade_year: str, learning_topic: str, path_dict: dict) -> None:
    from sqlmodel import Session

    from app.database import get_engine
    from app.services.learning_path_service import upsert_year_learning_path

    try:
        with Session(get_engine()) as db_session:
            upsert_year_learning_path(db_session, user_id, grade_year, learning_topic, path_dict)
        logger.info("LearningPath persisted for user %s, year %s", user_id, grade_year)
    except Exception as exc:
        logger.error("Failed to persist learning_path for user %s: %s", user_id, exc)


def _time_arrangement(duration: str, pace_reason: str, semester_scope: str = "上学期") -> dict:
    return {
        "semester_scope": semester_scope,
        "duration": duration,
        "pace_reason": pace_reason,
    }


def _knowledge_point(
    *,
    knowledge_point_id: str,
    name: str,
    level: str,
    description: str,
    mastery_standard: str,
    parent_knowledge_point_id: str | None = None,
) -> dict:
    return {
        "knowledge_point_id": knowledge_point_id,
        "name": name,
        "parent_knowledge_point_id": parent_knowledge_point_id,
        "level": level,
        "description": description,
        "mastery_standard": mastery_standard,
    }


def _knowledge_hierarchy(
    *,
    hierarchy_id: str,
    hierarchy_level: str,
    title: str,
    summary: str,
    knowledge_point_ids: list[str],
    parent_hierarchy_id: str | None = None,
) -> dict:
    return {
        "hierarchy_id": hierarchy_id,
        "parent_hierarchy_id": parent_hierarchy_id,
        "hierarchy_level": hierarchy_level,
        "title": title,
        "summary": summary,
        "knowledge_point_ids": knowledge_point_ids,
    }


def _knowledge_relation(
    *,
    from_node_id: str,
    to_node_id: str,
    relation_type: str,
    description: str,
) -> dict:
    return {
        "from_node_id": from_node_id,
        "to_node_id": to_node_id,
        "relation_type": relation_type,
        "description": description,
    }


def _chapter_node(
    *,
    chapter_node_id: str,
    chapter_theme: str,
    knowledge_hierarchy: list[dict],
    core_knowledge_point_ids: list[str],
    key_points: list[str],
    difficult_points: list[str],
    prerequisite_node_ids: list[str],
    learning_sequence: list[str],
    knowledge_relations: list[dict],
    downstream_resource_direction_ids: list[str],
) -> dict:
    return {
        "chapter_node_id": chapter_node_id,
        "chapter_theme": chapter_theme,
        "knowledge_hierarchy": knowledge_hierarchy,
        "core_knowledge_point_ids": core_knowledge_point_ids,
        "key_points": key_points,
        "difficult_points": difficult_points,
        "prerequisite_node_ids": prerequisite_node_ids,
        "learning_sequence": learning_sequence,
        "knowledge_relations": knowledge_relations,
        "downstream_resource_direction_ids": downstream_resource_direction_ids,
    }


def _resource_direction(
    *,
    resource_direction_id: str,
    target_node_ids: list[str],
    resource_type: str,
    generation_goal: str,
    content_requirements: list[str],
    difficulty_level: str,
) -> dict:
    return {
        "resource_direction_id": resource_direction_id,
        "target_node_ids": target_node_ids,
        "resource_type": resource_type,
        "generation_goal": generation_goal,
        "content_requirements": content_requirements,
        "difficulty_level": difficulty_level,
    }


def _critical_path(path_id: str, purpose: str, ordered_node_ids: list[str]) -> dict:
    return {
        "path_id": path_id,
        "purpose": purpose,
        "ordered_node_ids": ordered_node_ids,
    }


def _course_node(
    *,
    course_node_id: str,
    grade_id: str,
    theme: str,
    duration: str,
    pace_reason: str,
    goal: str,
    key_points: list[str],
    difficult_points: list[str],
    learning_sequence: list[str],
    acceptance_criteria: list[str],
    prerequisite_node_ids: list[str],
    chapter_nodes: list[dict],
    core_knowledge_points: list[dict],
    knowledge_relations: list[dict],
    downstream_resource_direction_ids: list[str],
) -> dict:
    return {
        "course_node_id": course_node_id,
        "grade_id": grade_id,
        "course_or_chapter_theme": theme,
        "time_arrangement": _time_arrangement(duration, pace_reason),
        "course_goal": goal,
        "prerequisite_node_ids": prerequisite_node_ids,
        "chapter_nodes": chapter_nodes,
        "core_knowledge_points": core_knowledge_points,
        "key_points": key_points,
        "difficult_points": difficult_points,
        "learning_sequence": learning_sequence,
        "knowledge_relations": knowledge_relations,
        "downstream_resource_direction_ids": downstream_resource_direction_ids,
        "acceptance_criteria": acceptance_criteria,
    }


def _current_course_from_node(course: dict) -> dict:
    return {
        "grade_id": course["grade_id"],
        "course_node_id": course["course_node_id"],
        "course_or_chapter_theme": course["course_or_chapter_theme"],
        "course_goal": course["course_goal"],
        "time_arrangement": course["time_arrangement"],
        "current_focus": f"正在学习 {course['course_or_chapter_theme']}",
        "progress_state": "not_started",
        "next_action": "开始第一章需求拆解",
    }


def _build_course_structure(
    *,
    course_node_id: str,
    theme: str,
    stage_titles: list[str],
    key_points: list[str],
    difficult_points: list[str],
    acceptance_criteria: list[str],
    resource_direction_ids: list[str],
) -> tuple[list[dict], list[dict], list[dict]]:
    knowledge_points = [
        _knowledge_point(
            knowledge_point_id=f"{course_node_id}_kp_{index + 1}",
            name=point,
            level="核心" if index == 0 else "应用",
            description=f"围绕{theme}需要稳定掌握的关键能力：{point}",
            mastery_standard=f"能够把{point}用于{theme}当前阶段任务。",
        )
        for index, point in enumerate(key_points)
    ]
    knowledge_points.extend(
        [
            _knowledge_point(
                knowledge_point_id=f"{course_node_id}_difficulty_{index + 1}",
                name=point,
                level="进阶",
                description=f"{theme}中的重点难点：{point}",
                mastery_standard=f"能够独立定位并处理与{point}相关的问题。",
            )
            for index, point in enumerate(difficult_points)
        ]
    )

    point_ids = [item["knowledge_point_id"] for item in knowledge_points[: max(1, min(2, len(knowledge_points)))]]
    chapter_nodes: list[dict] = []
    knowledge_relations: list[dict] = []

    for index, stage_title in enumerate(stage_titles, start=1):
        chapter_node_id = f"{course_node_id}_chapter_{index}"
        chapter_key_points = [stage_title]
        if index - 1 < len(key_points):
            chapter_key_points.append(key_points[index - 1])

        stage_hierarchy_id = f"{chapter_node_id}_hier_stage"
        task_hierarchy_id = f"{chapter_node_id}_hier_task"
        chapter_nodes.append(
            _chapter_node(
                chapter_node_id=chapter_node_id,
                chapter_theme=stage_title,
                knowledge_hierarchy=[
                    _knowledge_hierarchy(
                        hierarchy_id=stage_hierarchy_id,
                        hierarchy_level="章节",
                        title=stage_title,
                        summary=f"围绕{stage_title}推进{theme}的主线任务。",
                        knowledge_point_ids=point_ids,
                    ),
                    _knowledge_hierarchy(
                        hierarchy_id=task_hierarchy_id,
                        parent_hierarchy_id=stage_hierarchy_id,
                        hierarchy_level="主题",
                        title=f"{stage_title}阶段任务",
                        summary=f"把{stage_title}拆成可执行任务，并对齐验收要求。",
                        knowledge_point_ids=point_ids,
                    ),
                ],
                core_knowledge_point_ids=point_ids,
                key_points=chapter_key_points,
                difficult_points=difficult_points[:2],
                prerequisite_node_ids=[chapter_nodes[-1]["chapter_node_id"]] if chapter_nodes else [],
                learning_sequence=[stage_hierarchy_id, task_hierarchy_id],
                knowledge_relations=[
                    _knowledge_relation(
                        from_node_id=course_node_id,
                        to_node_id=chapter_node_id,
                        relation_type="contains",
                        description=f"{theme}课程包含章节 {stage_title}。",
                    )
                ],
                downstream_resource_direction_ids=resource_direction_ids,
            )
        )
        knowledge_relations.append(
            _knowledge_relation(
                from_node_id=chapter_node_id,
                to_node_id=course_node_id,
                relation_type="contains",
                description=f"章节 {stage_title} 属于课程 {theme}。",
            )
        )
        if index > 1:
            knowledge_relations.append(
                _knowledge_relation(
                    from_node_id=f"{course_node_id}_chapter_{index - 1}",
                    to_node_id=chapter_node_id,
                    relation_type="prerequisite",
                    description=f"先完成上一阶段，再进入 {stage_title}。",
                )
            )

    if acceptance_criteria:
        knowledge_relations.append(
            _knowledge_relation(
                from_node_id=course_node_id,
                to_node_id=f"{course_node_id}_acceptance",
                relation_type="applies_to",
                description=f"{theme}最终以验收标准收束：{'；'.join(acceptance_criteria)}",
            )
        )

    return chapter_nodes, knowledge_points, knowledge_relations


def _build_analysis_input(profile: dict, grade_year: str, learning_topic: str, requirements: str) -> str:
    return (
        f"请为 {grade_year} 生成「{learning_topic}」的学习路径。\n\n"
        "输出前先完成以下分析：\n"
        "1. 判断用户当前阶段、目标导向、时间约束与关键短板。\n"
        "2. 判断当前年级最应该先开始的课程，以及为什么先学它。\n"
        "3. 判断课程之间的依赖、阶段拆分、实践闭环与验收标准。\n"
        "4. 再把分析结果映射到结构化学习路径。\n\n"
        f"用户画像关键信息：{json.dumps(profile, ensure_ascii=False, indent=2)}\n"
        f"当前目标年级：{grade_year}\n"
        f"学习主题：{learning_topic}\n"
        f"具体要求：{requirements or '无'}"
    )


def _build_local_learning_path(profile: dict, *, grade_year: str, learning_topic: str) -> dict:
    confirmed = profile.get("confirmed_info", {}) if isinstance(profile, dict) else {}
    major = str(confirmed.get("major") or "软件工程")
    current_grade = str(confirmed.get("current_grade") or "大三")
    weekly_time = str(confirmed.get("weekly_available_time") or "每周 6-10 小时")
    constraints = str(confirmed.get("constraints") or "平时学习节奏")
    weaknesses_text = str(confirmed.get("weaknesses") or "大型项目实战经验、数据库设计能力、英文阅读速度")
    weaknesses = [item for item in weaknesses_text.split("、") if item]
    mastered_content = [f"{major}基础"]
    pace_reason = f"围绕{constraints}安排"
    topic = learning_topic or "AI 应用开发"
    resource_directions: list[dict] = []

    def build_course_resources(course_node_id: str, theme: str, focus: list[str], difficulty_level: str) -> list[str]:
        resource_id = f"{course_node_id}_resource"
        resource_directions.append(
            _resource_direction(
                resource_direction_id=resource_id,
                target_node_ids=[course_node_id],
                resource_type="文档",
                generation_goal=f"围绕{theme}生成阶段讲义与任务清单",
                content_requirements=focus + ["包含阶段验收标准", "包含复盘问题"],
                difficulty_level=difficulty_level,
            )
        )
        return [resource_id]

    year_1_resource_ids = build_course_resources("year_1_course_1", "编程与算法基础", ["基础语法", "数据结构"], "基础")
    year_2_resource_ids = build_course_resources("year_2_course_1", "工程化 Web 开发基础", ["接口设计", "数据库设计"], "基础")
    year_3_course_1_resource_ids = build_course_resources(
        "year_3_course_1",
        f"{topic}基础能力搭建",
        ["OpenAI-compatible API 调用", "Prompt 设计"],
        "中级",
    )
    year_3_course_2_resource_ids = build_course_resources(
        "year_3_course_2",
        f"{topic}项目实战",
        ["LangGraph 编排", "SSE 流式交互"],
        "中级",
    )
    year_4_resource_ids = build_course_resources(
        "year_4_course_1",
        "就业级作品集与迭代优化",
        ["项目复盘", "作品集包装"],
        "中级",
    )

    year_1_structure = _build_course_structure(
        course_node_id="year_1_course_1",
        theme="编程与算法基础",
        stage_titles=["语法入门", "数据结构实践", "算法题巩固"],
        key_points=["Python 基础语法", "数据结构", "算法思维"],
        difficult_points=["抽象建模", "复杂度分析"],
        acceptance_criteria=["能够独立完成基础算法练习"],
        resource_direction_ids=year_1_resource_ids,
    )
    year_2_structure = _build_course_structure(
        course_node_id="year_2_course_1",
        theme="工程化 Web 开发基础",
        stage_titles=["接口设计", "数据库建模", "全栈联调"],
        key_points=["HTTP 接口", "数据库设计", "前后端协作"],
        difficult_points=["状态管理", "数据建模"],
        acceptance_criteria=["完成一个基础 Web 应用并上线"],
        resource_direction_ids=year_2_resource_ids,
    )
    year_3_course_1_structure = _build_course_structure(
        course_node_id="year_3_course_1",
        theme=f"{topic}基础能力搭建",
        stage_titles=["需求拆解", "接口接入", "最小闭环演示"],
        key_points=["OpenAI-compatible API 调用", "Prompt 设计", "前后端联调"],
        difficult_points=["异步调用稳定性", "错误处理与重试"],
        acceptance_criteria=["完成一个可运行的 AI 功能模块并接入 Web 应用"],
        resource_direction_ids=year_3_course_1_resource_ids,
    )
    year_3_course_2_structure = _build_course_structure(
        course_node_id="year_3_course_2",
        theme=f"{topic}项目实战",
        stage_titles=["架构设计", "多智能体联调", "部署验收"],
        key_points=["LangGraph 编排", "SSE 流式交互", "部署与监控"],
        difficult_points=["多智能体状态管理", "线上稳定性"],
        acceptance_criteria=["项目支持真实用户流程与部署演示"],
        resource_direction_ids=year_3_course_2_resource_ids,
    )
    year_4_structure = _build_course_structure(
        course_node_id="year_4_course_1",
        theme="就业级作品集与迭代优化",
        stage_titles=["项目复盘", "优化迭代", "作品集整理"],
        key_points=["项目复盘", "性能优化", "作品集包装"],
        difficult_points=["方案取舍", "表达与复盘"],
        acceptance_criteria=["形成可展示的就业级项目作品集"],
        resource_direction_ids=year_4_resource_ids,
    )

    year_1 = _course_node(
        course_node_id="year_1_course_1",
        grade_id="year_1",
        theme="编程与算法基础",
        duration="8 周",
        pace_reason="以课程基础打底",
        goal="完成 Python、数据结构与算法基础训练",
        key_points=["Python 基础语法", "数据结构", "算法思维"],
        difficult_points=["抽象建模", "复杂度分析"],
        learning_sequence=["语法入门", "数据结构实践", "算法题巩固"],
        acceptance_criteria=["能够独立完成基础算法练习"],
        prerequisite_node_ids=[],
        chapter_nodes=year_1_structure[0],
        core_knowledge_points=year_1_structure[1],
        knowledge_relations=year_1_structure[2],
        downstream_resource_direction_ids=year_1_resource_ids,
    )
    year_2 = _course_node(
        course_node_id="year_2_course_1",
        grade_id="year_2",
        theme="工程化 Web 开发基础",
        duration="8 周",
        pace_reason="先建立前后端工程能力",
        goal="掌握前后端协作、数据库与接口开发基础",
        key_points=["HTTP 接口", "数据库设计", "前后端协作"],
        difficult_points=["状态管理", "数据建模"],
        learning_sequence=["接口设计", "数据库建模", "全栈联调"],
        acceptance_criteria=["完成一个基础 Web 应用并上线"],
        prerequisite_node_ids=["year_1_course_1"],
        chapter_nodes=year_2_structure[0],
        core_knowledge_points=year_2_structure[1],
        knowledge_relations=year_2_structure[2],
        downstream_resource_direction_ids=year_2_resource_ids,
    )
    year_3_courses = [
        _course_node(
            course_node_id="year_3_course_1",
            grade_id="year_3",
            theme=f"{topic}基础能力搭建",
            duration="6 周",
            pace_reason=pace_reason,
            goal=f"完成 {topic} 所需的核心接口、工具链与最小功能闭环",
            key_points=["OpenAI-compatible API 调用", "Prompt 设计", "前后端联调"],
            difficult_points=["异步调用稳定性", "错误处理与重试"],
            learning_sequence=["需求拆解", "接口接入", "最小闭环演示"],
            acceptance_criteria=["完成一个可运行的 AI 功能模块并接入 Web 应用"],
            prerequisite_node_ids=["year_2_course_1"],
            chapter_nodes=year_3_course_1_structure[0],
            core_knowledge_points=year_3_course_1_structure[1],
            knowledge_relations=year_3_course_1_structure[2],
            downstream_resource_direction_ids=year_3_course_1_resource_ids,
        ),
        _course_node(
            course_node_id="year_3_course_2",
            grade_id="year_3",
            theme=f"{topic}项目实战",
            duration="8 周",
            pace_reason=pace_reason,
            goal=f"围绕 {topic} 完成一个具备真实交互与部署能力的课程级项目",
            key_points=["LangGraph 编排", "SSE 流式交互", "部署与监控"],
            difficult_points=["多智能体状态管理", "线上稳定性"],
            learning_sequence=["架构设计", "多智能体联调", "部署验收"],
            acceptance_criteria=["项目支持真实用户流程与部署演示"],
            prerequisite_node_ids=["year_3_course_1"],
            chapter_nodes=year_3_course_2_structure[0],
            core_knowledge_points=year_3_course_2_structure[1],
            knowledge_relations=year_3_course_2_structure[2],
            downstream_resource_direction_ids=year_3_course_2_resource_ids,
        ),
    ]
    year_4 = _course_node(
        course_node_id="year_4_course_1",
        grade_id="year_4",
        theme="就业级作品集与迭代优化",
        duration="10 周",
        pace_reason="把项目沉淀为作品集",
        goal="完成作品集整理、性能优化和面试讲解准备",
        key_points=["项目复盘", "性能优化", "作品集包装"],
        difficult_points=["方案取舍", "表达与复盘"],
        learning_sequence=["项目复盘", "优化迭代", "作品集整理"],
        acceptance_criteria=["形成可展示的就业级项目作品集"],
        prerequisite_node_ids=["year_3_course_2"],
        chapter_nodes=year_4_structure[0],
        core_knowledge_points=year_4_structure[1],
        knowledge_relations=year_4_structure[2],
        downstream_resource_direction_ids=year_4_resource_ids,
    )

    all_grade_plans = {
        "year_1": {
            "grade_id": "year_1",
            "grade_name": "大一",
            "grade_goal": "夯实编程与算法基础",
            "course_nodes": [year_1],
        },
        "year_2": {
            "grade_id": "year_2",
            "grade_name": "大二",
            "grade_goal": "建立全栈工程能力",
            "course_nodes": [year_2],
        },
        "year_3": {
            "grade_id": "year_3",
            "grade_name": "大三",
            "grade_goal": f"完成 {topic} 项目闭环",
            "course_nodes": year_3_courses,
        },
        "year_4": {
            "grade_id": "year_4",
            "grade_name": "大四",
            "grade_goal": "沉淀就业级项目作品集",
            "course_nodes": [year_4],
        },
    }
    
    grade_plans = {
        grade_year: all_grade_plans[grade_year]
    } if grade_year in all_grade_plans else {}

    current_course = next(
        (
            course
            for course in grade_plans.get(grade_year, {}).get("course_nodes", [])
            if isinstance(course, dict)
        ),
        year_3_courses[0],
    )

    return {
        "schema_version": "learning_path.v2.course_node",
        "learning_goal": {
            "target_course_or_skill": topic,
            "goal_type": "项目实践",
            "desired_outcome": f"完成一个围绕 {topic} 的课程级项目",
            "four_year_outcome": "形成就业级项目作品集",
        },
        "learner_baseline": {
            "current_grade": current_grade,
            "major": major,
            "mastered_content": mastered_content,
            "weaknesses": weaknesses or ["大型项目实战经验"],
            "constraints": [constraints],
            "weekly_available_time": weekly_time,
        },
        "planning_rules": {
            "node_unit": "course_node",
            "grade_boundary_rule": "按年级递进，先基础后项目",
            "sequence_rule": "先完成基础能力搭建，再进入项目实战与部署验收",
            "resource_rule": "按课程节点生成资源与后续练习",
        },
        "grade_plans": grade_plans,
        "knowledge_graph": {
            "global_relations": [
                _knowledge_relation(
                    from_node_id="year_1_course_1",
                    to_node_id="year_2_course_1",
                    relation_type="prerequisite",
                    description="先打稳编程与算法基础，再进入工程化 Web 开发。",
                ),
                _knowledge_relation(
                    from_node_id="year_2_course_1",
                    to_node_id="year_3_course_1",
                    relation_type="prerequisite",
                    description="先具备前后端联调能力，再进入 AI 功能闭环搭建。",
                ),
                _knowledge_relation(
                    from_node_id="year_3_course_1",
                    to_node_id="year_3_course_2",
                    relation_type="extends",
                    description="先完成最小闭环，再扩展到多智能体项目实战。",
                ),
            ],
            "critical_paths": [
                _critical_path(
                    "ai_application_path",
                    f"围绕{topic}形成从基础到项目落地的主路径",
                    [
                        "year_1_course_1",
                        "year_2_course_1",
                        "year_3_course_1",
                        "year_3_course_2",
                        "year_4_course_1",
                    ],
                )
            ],
        },
        "resource_generation_contract": {
            "downstream_agents": ["learning_resource_agent"],
            "resource_directions": resource_directions,
        },
        "dynamic_update_contract": {
            "trackable_metrics": ["题目得分", "项目里程碑完成度"],
            "update_triggers": ["score > 70", "milestone completed"],
            "adjustment_strategy": "通过后推进下一门课程，未通过则补强薄弱点",
        },
        "current_learning_courses": [_current_course_from_node(current_course)],
        "current_learning_course": _current_course_from_node(current_course),
    }


async def run_learning_path_agent(state: OrchestrationState, llm: BaseChatModel) -> dict:
    """Generate a simplified learning path for a single grade year."""
    tool_args = extract_last_tool_call_args(state)
    grade_year = tool_args.get("grade_year", "")
    learning_topic = tool_args.get("learning_topic", "")

    profile = state.get("profile")
    if (
        not isinstance(profile, dict)
        or profile.get("type") != "basic_profile"
        or not isinstance(profile.get("confirmed_info"), dict)
    ):
        return {"error": "请先完成基础画像再生成学习路径。", "hard_error": True}

    grade_year = grade_year or _grade_year_from_profile(profile)
    if not grade_year:
        return {"error": "画像中缺少可识别的年级，无法生成学习路径。", "hard_error": True}

    query = str(state.get("query", "")).strip()
    resolved_topic = learning_topic.strip() if isinstance(learning_topic, str) else ""
    if not resolved_topic or _allows_default_path(query):
        resolved_topic = _topic_from_profile(profile)

    input_text = _build_analysis_input(
        profile,
        grade_year,
        resolved_topic,
        str(tool_args.get("specific_requirements", "")),
    )

    try:
        structured_llm = llm.with_structured_output(YearLearningPathOutput)
        prompt = ChatPromptTemplate.from_messages([
            ("system", LEARNING_PATH_AGENT_SYSTEM_PROMPT),
            ("human", "{query}"),
        ])
        chain = prompt | structured_llm
        result: YearLearningPathOutput = await chain.ainvoke({"query": input_text})
    except Exception as exc:
        logger.warning("LearningPathAgent structured output failed: %s", exc)
        path_dict = _build_local_learning_path(profile, grade_year=grade_year, learning_topic=resolved_topic)
        _persist_learning_path(state["user_id"], grade_year, resolved_topic, path_dict)
        return {"year_learning_path": path_dict, "grade_year": grade_year}

    path_dict = result.model_dump()
    contract_error = _validate_learning_path_contract(path_dict)
    if contract_error:
        logger.warning("LearningPathAgent contract validation failed: %s", contract_error)
        fallback_path = _build_local_learning_path(profile, grade_year=grade_year, learning_topic=resolved_topic)
        _persist_learning_path(state["user_id"], grade_year, resolved_topic, fallback_path)
        return {"year_learning_path": fallback_path, "grade_year": grade_year}
    _persist_learning_path(state["user_id"], grade_year, resolved_topic, path_dict)

    return {"year_learning_path": path_dict, "grade_year": grade_year}


def create_learning_path_agent_node(llm: BaseChatModel):
    async def learning_path_agent_node(state: OrchestrationState) -> dict:
        agent_result = await run_learning_path_agent(state, llm)

        tool_call_id = extract_last_tool_call_id(state)
        tool_message = ToolMessage(
            content=json.dumps(agent_result, ensure_ascii=False),
            tool_call_id=tool_call_id or "unknown",
        )

        result = {"messages": [tool_message]}
        if agent_result.get("year_learning_path") is not None:
            merged_paths = dict(state.get("year_learning_paths") or {})
            merged_paths[result_grade_year := agent_result.get("grade_year", "")] = agent_result["year_learning_path"]
            result["year_learning_path"] = agent_result["year_learning_path"]
            result["year_learning_paths"] = merged_paths
            result["grade_year"] = result_grade_year
            result["latest_grade_year"] = result_grade_year
            # Clear the previous worker's natural-language response so the final
            # session summary is derived from the refreshed learning path.
            result["response"] = ""
        if agent_result.get("error") is not None:
            result["response"] = agent_result["error"]
        return result

    return learning_path_agent_node
