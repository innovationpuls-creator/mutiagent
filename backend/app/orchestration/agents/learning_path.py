from __future__ import annotations

import asyncio
import copy
import json
import logging

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import ToolMessage
from langchain_core.prompts import ChatPromptTemplate

from app.orchestration.grade_contract import (
    grade_year_from_current_grade,
    is_supported_current_grade,
    unsupported_current_grade_error,
)
from app.orchestration.agents.learning_path_intake import latest_intake_from_state
from app.orchestration.agents.profile import is_complete_profile_data
from app.orchestration.agents.models import LearningPathIntakeOutput, LearningPathPlanOutput
from app.orchestration.agents.prompts import LEARNING_PATH_AGENT_SYSTEM_PROMPT
from app.orchestration.agents.utils import extract_last_tool_call_args, extract_last_tool_call_id
from app.orchestration.state import OrchestrationState

logger = logging.getLogger(__name__)

DEFAULT_PATH_COMMANDS = ("默认", "直接", "随便帮我填", "不确定的你随便帮我填", "帮我生成")
DEFAULT_TOPIC = "学习路径"
MIN_LEARNING_PATH_COURSES = 4
MAX_LEARNING_PATH_COURSES = 10
LEARNING_PATH_STRUCTURED_TIMEOUT_SECONDS = 120.0
LEARNING_PATH_RETRY_ERROR = "学习路径生成失败，请重试生成学习路径。"


def _allows_default_path(text: str) -> bool:
    return any(command in text for command in DEFAULT_PATH_COMMANDS)


def _grade_year_from_profile(profile: dict) -> str:
    confirmed = profile.get("confirmed_info", {}) if isinstance(profile, dict) else {}
    return grade_year_from_current_grade(confirmed.get("current_grade"))


def _topic_from_profile(profile: dict) -> str:
    confirmed = profile.get("confirmed_info", {}) if isinstance(profile, dict) else {}
    content_preference = confirmed.get("content_preference", [])
    content_text = " ".join(str(item) for item in content_preference) if isinstance(content_preference, list) else ""
    text_candidates = [
        str(confirmed.get("short_term_goal", "")),
        str(confirmed.get("long_term_goal", "")),
        content_text,
        str(profile.get("summary_text", "")) if isinstance(profile, dict) else "",
        str(profile.get("text", "")) if isinstance(profile, dict) else "",
    ]
    combined = "\n".join(text_candidates).lower()
    if "vibecoding" in combined:
        return "vibecoding"
    if "agent" in combined or "智能体" in combined:
        return "AI Agent 开发与部署"
    if "前端" in combined:
        return "前端开发"
    if "后端" in combined:
        return "后端开发"
    if "ai" in combined:
        return "AI 应用开发"
    return DEFAULT_TOPIC


def _confirmed_intake_from_state(state: OrchestrationState | dict) -> tuple[dict | None, str]:
    raw_intake = latest_intake_from_state(state)
    if not isinstance(raw_intake, dict) or raw_intake.get("status") != "confirmed":
        return None, "请先确认课程草案，再生成正式学习路径。"

    try:
        intake = LearningPathIntakeOutput.model_validate(raw_intake)
    except Exception as exc:
        logger.warning("LearningPathAgent confirmed intake validation failed: %s: %s", type(exc).__name__, exc)
        return None, "课程草案不完整，请先重新生成并确认课程草案。"
    return intake.model_dump(), ""


def _intake_course_lines(intake: dict) -> list[str]:
    courses = intake.get("courses", [])
    if not isinstance(courses, list):
        return []
    lines: list[str] = []
    for index, course in enumerate(courses, start=1):
        if not isinstance(course, dict):
            continue
        title = str(course.get("title", "")).strip()
        purpose = str(course.get("purpose", "")).strip()
        if title and purpose:
            lines.append(f"{index}. {title}：{purpose}")
        elif title:
            lines.append(f"{index}. {title}")
    return lines


def _validate_learning_path_contract(path_data: dict) -> str:
    if path_data.get("schema_version") != "learning_path.v2.course_node":
        return "学习路径 schema_version 不正确。"
    current = path_data.get("current_learning_course")
    if not isinstance(current, dict):
        return "学习路径缺少 current_learning_course。"
    progress_state = current.get("progress_state")
    if progress_state not in {"in_progress", "completed"}:
        return "current_learning_course.progress_state 必须是 in_progress 或 completed。"
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
    normalized_course_nodes = [course for course in course_nodes if isinstance(course, dict)]
    if not MIN_LEARNING_PATH_COURSES <= len(normalized_course_nodes) <= MAX_LEARNING_PATH_COURSES:
        return "当前学年课程数量必须在 4 到 10 门之间。"
    if not any(
        course.get("course_node_id") == course_id
        for course in normalized_course_nodes
    ):
        return "current_learning_course.course_node_id 无法定位。"
    return ""


def _path_courses(path_data: dict, grade_year: str) -> list[dict]:
    grade_plans = path_data.get("grade_plans")
    if not isinstance(grade_plans, dict):
        return []
    grade_plan = grade_plans.get(grade_year)
    if not isinstance(grade_plan, dict):
        return []
    course_nodes = grade_plan.get("course_nodes")
    if not isinstance(course_nodes, list):
        return []
    return [course for course in course_nodes if isinstance(course, dict)]


def _persist_learning_path(user_id: str, grade_year: str, learning_topic: str, path_dict: dict) -> None:
    from sqlmodel import Session

    from app.database import get_engine
    from app.services.course_knowledge_service import delete_user_course_outlines_by_grade_year
    from app.services.learning_path_service import upsert_year_learning_path

    try:
        with Session(get_engine()) as db_session:
            upsert_year_learning_path(db_session, user_id, grade_year, learning_topic, path_dict)
            delete_user_course_outlines_by_grade_year(db_session, user_id, grade_year)
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
    semester_scope: str = "上学期",
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
        "time_arrangement": _time_arrangement(duration, pace_reason, semester_scope),
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


def _current_course_from_node(
    course: dict,
    *,
    progress_state: str = "in_progress",
    current_focus: str | None = None,
    next_action: str | None = None,
) -> dict:
    return {
        "grade_id": course["grade_id"],
        "course_node_id": course["course_node_id"],
        "course_or_chapter_theme": course["course_or_chapter_theme"],
        "course_goal": course["course_goal"],
        "time_arrangement": course["time_arrangement"],
        "current_focus": current_focus or f"正在学习 {course['course_or_chapter_theme']}",
        "progress_state": progress_state,
        "next_action": next_action or "开始第一章需求拆解",
    }


def _learning_path_response_text(path_data: dict) -> str:
    current_learning_course = path_data.get("current_learning_course")
    if not isinstance(current_learning_course, dict):
        return "学习路径已生成。"

    theme = current_learning_course.get("course_or_chapter_theme")
    next_action = current_learning_course.get("next_action")
    clauses = ["学习路径已生成"]
    if isinstance(theme, str) and theme.strip():
        clauses.append(f"当前建议先学习《{theme.strip()}》")
    if isinstance(next_action, str) and next_action.strip():
        clauses.append(f"下一步：{next_action.strip()}")
    return "，".join(clauses) + "。"


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


def _format_progress_snapshots(progress_snapshots: list[dict[str, object]]) -> str:
    if not progress_snapshots:
        return "已有学习路径完成度摘要：无历史数据。"

    lines = ["已有学习路径完成度摘要："]
    for snapshot in progress_snapshots:
        grade_year = str(snapshot.get("grade_year", "")).strip()
        total_courses = int(snapshot.get("total_courses", 0) or 0)
        completed_courses = int(snapshot.get("completed_courses", 0) or 0)
        line = f"{grade_year}：共 {total_courses} 门课程，已完成 {completed_courses} 门"

        current_course_id = str(snapshot.get("current_course_id", "")).strip()
        current_progress_state = str(snapshot.get("current_progress_state", "")).strip()
        next_course_id = str(snapshot.get("next_course_id", "")).strip()
        extras: list[str] = []
        if current_course_id:
            extras.append(f"当前课程 {current_course_id}")
        if current_progress_state:
            extras.append(f"当前状态 {current_progress_state}")
        if next_course_id:
            extras.append(f"下一门 {next_course_id}")
        if extras:
            line = f"{line}，{'，'.join(extras)}"
        lines.append(line)
    return "\n".join(lines)


def _build_analysis_input(
    profile: dict,
    grade_year: str,
    learning_topic: str,
    requirements: str,
    progress_snapshots: list[dict[str, object]],
    intake: dict,
) -> str:
    intake_course_lines = "\n".join(_intake_course_lines(intake))
    return (
        f"请为 {grade_year} 生成「{learning_topic}」的学习路径。\n\n"
        "输出前先完成以下分析：\n"
        "1. 判断用户当前阶段、目标导向、时间约束与关键短板。\n"
        "2. 判断当前年级最应该先开始的课程，以及为什么先学它。\n"
        "3. 判断课程之间的依赖、阶段拆分、实践闭环与验收标准。\n"
        "4. 如果输入里已经有历史学习路径与完成度，必须在此基础上延续当前进度，不要重新从第一门课开始。\n"
        "5. 再把分析结果映射到轻量规划骨架，输出 4-10 门课程的 course_specs；"
        "课程数量必须与已确认课程草案一致，课程顺序必须与已确认课程草案一致。"
        "不要输出完整知识图谱或章节明细。\n\n"
        "已确认课程草案是正式学习路径的边界，不能扩展到用户没有确认的方向：\n"
        f"{json.dumps(intake, ensure_ascii=False, indent=2)}\n"
        f"已确认课程顺序：\n{intake_course_lines}\n\n"
        f"用户画像关键信息：{json.dumps(profile, ensure_ascii=False, indent=2)}\n"
        f"当前目标年级：{grade_year}\n"
        f"学习主题：{learning_topic}\n"
        f"具体要求：{requirements or '无'}\n"
        f"{_format_progress_snapshots(progress_snapshots)}"
    )


def _course_spec(
    *,
    course_node_id: str,
    theme: str,
    semester_scope: str,
    duration: str,
    pace_reason: str,
    goal: str,
    stage_titles: list[str],
    key_points: list[str],
    difficult_points: list[str],
    acceptance_criteria: list[str],
    difficulty_level: str,
) -> dict:
    return {
        "course_node_id": course_node_id,
        "theme": theme,
        "semester_scope": semester_scope,
        "duration": duration,
        "pace_reason": pace_reason,
        "goal": goal,
        "stage_titles": stage_titles,
        "key_points": key_points,
        "difficult_points": difficult_points,
        "acceptance_criteria": acceptance_criteria,
        "difficulty_level": difficulty_level,
    }


def _normalize_goal_type(value: str) -> str:
    normalized = value.strip()
    if normalized in {"考试", "课程学习", "项目实践", "能力提升", "就业准备", "其他"}:
        return normalized

    lowered = normalized.lower()
    if "exam" in lowered or "考试" in normalized:
        return "考试"
    if "course" in lowered or "课程" in normalized:
        return "课程学习"
    if "project" in lowered or "项目" in normalized:
        return "项目实践"
    if "career" in lowered or "job" in lowered or "求职" in normalized or "就业" in normalized:
        return "就业准备"
    if "ability" in lowered or "skill" in lowered or "能力" in normalized:
        return "能力提升"
    return "其他"


def _normalize_semester_scope(value: str, *, course_index: int, total_courses: int) -> str:
    normalized = value.strip()
    for scope in ("上学期", "下学期", "寒假", "暑假", "全年级内弹性安排"):
        if scope in normalized:
            return scope
    if "上" in normalized and "学期" in normalized:
        return "上学期"
    if "下" in normalized and "学期" in normalized:
        return "下学期"
    if "寒" in normalized:
        return "寒假"
    if "暑" in normalized:
        return "暑假"
    return "上学期" if course_index < total_courses else "下学期"


def _normalize_difficulty_level(value: str) -> str:
    normalized = value.strip()
    if normalized in {"入门", "基础", "中级", "高级"}:
        return normalized

    lowered = normalized.lower()
    if "begin" in lowered or "starter" in lowered or "入门" in normalized:
        return "入门"
    if "basic" in lowered or "foundation" in lowered or "基础" in normalized:
        return "基础"
    if "high" in lowered or "advanced" in lowered or "高级" in normalized:
        return "高级"
    if "medium" in lowered or "intermediate" in lowered or "中级" in normalized:
        return "中级"
    return "中级"


def _normalize_grade_goal(value: str, *, grade_year: str, default_grade_goal: str) -> str:
    normalized = value.strip()
    if not normalized:
        return default_grade_goal
    lowered = normalized.lower()
    if lowered == grade_year.lower() or lowered.startswith("year_"):
        return default_grade_goal
    return normalized


def _grade_course_specs(grade_year: str, topic: str, pace_reason: str) -> tuple[str, str, list[dict], list[dict]]:
    if grade_year == "year_1":
        specs = [
            _course_spec(
                course_node_id="year_1_course_1",
                theme="编程与算法基础",
                semester_scope="上学期",
                duration="6 周",
                pace_reason="先打稳编程语法与算法思维",
                goal="完成 Python 基础语法、流程控制与基础算法训练",
                stage_titles=["语法入门", "数据结构启蒙", "算法思维训练"],
                key_points=["Python 基础语法", "流程控制", "算法思维"],
                difficult_points=["抽象建模", "复杂度理解"],
                acceptance_criteria=["能独立完成基础算法练习并解释思路"],
                difficulty_level="基础",
            ),
            _course_spec(
                course_node_id="year_1_course_2",
                theme="数据结构与算法实战",
                semester_scope="上学期",
                duration="6 周",
                pace_reason="把基础语法推进到可解决问题的水平",
                goal="围绕常见题型掌握数组、链表、栈队列与搜索排序",
                stage_titles=["线性结构实践", "搜索与排序", "题型拆解复盘"],
                key_points=["数组与链表", "栈与队列", "搜索与排序"],
                difficult_points=["边界条件分析", "调试思路"],
                acceptance_criteria=["能独立完成一组结构化算法练习题"],
                difficulty_level="基础",
            ),
            _course_spec(
                course_node_id="year_1_course_3",
                theme="Git 协作与调试基础",
                semester_scope="下学期",
                duration="4 周",
                pace_reason="尽早建立工程协作与排错习惯",
                goal="掌握 Git 基础协作、日志定位与常见调试方法",
                stage_titles=["Git 提交流程", "日志与断点调试", "协作复盘"],
                key_points=["Git 基础命令", "断点调试", "问题复盘"],
                difficult_points=["冲突处理", "问题定位路径"],
                acceptance_criteria=["能独立完成一次带日志的代码调试与提交协作"],
                difficulty_level="基础",
            ),
        ]
        return "大一", "夯实编程与工程基础", specs, []

    if grade_year == "year_2":
        specs = [
            _course_spec(
                course_node_id="year_2_course_1",
                theme="Web 前端与交互基础",
                semester_scope="上学期",
                duration="6 周",
                pace_reason="先补足用户界面与交互表达能力",
                goal="完成一个具备基础状态管理与交互逻辑的前端页面",
                stage_titles=["组件拆分", "状态与事件", "交互联调"],
                key_points=["组件设计", "状态管理", "交互联调"],
                difficult_points=["状态同步", "页面调试"],
                acceptance_criteria=["能独立完成一个有状态的交互页面"],
                difficulty_level="基础",
            ),
            _course_spec(
                course_node_id="year_2_course_2",
                theme="后端接口与数据库建模",
                semester_scope="上学期",
                duration="6 周",
                pace_reason="建立服务端接口与数据结构意识",
                goal="掌握 REST 接口设计、数据库建模与基本持久化能力",
                stage_titles=["接口设计", "数据库建模", "服务端联调"],
                key_points=["REST 接口", "数据库建模", "ORM 基础"],
                difficult_points=["关系设计", "数据一致性"],
                acceptance_criteria=["能完成一个带数据库的后端接口服务"],
                difficulty_level="基础",
            ),
            _course_spec(
                course_node_id="year_2_course_3",
                theme="全栈工程化与部署入门",
                semester_scope="下学期",
                duration="5 周",
                pace_reason="把前后端能力收束为可运行项目",
                goal="掌握环境配置、联调、部署与基础监控意识",
                stage_titles=["环境配置", "全栈联调", "部署复盘"],
                key_points=["环境配置", "全栈联调", "部署入门"],
                difficult_points=["跨端排错", "环境一致性"],
                acceptance_criteria=["能把一个全栈项目运行并部署到可访问环境"],
                difficulty_level="基础",
            ),
        ]
        relations = [
            _knowledge_relation(
                from_node_id="year_1_course_3",
                to_node_id="year_2_course_1",
                relation_type="prerequisite",
                description="先具备基础协作与调试能力，再进入 Web 工程化主线。",
            )
        ]
        return "大二", "建立全栈工程能力", specs, relations

    if grade_year == "year_4":
        specs = [
            _course_spec(
                course_node_id="year_4_course_1",
                theme="就业级作品集与迭代优化",
                semester_scope="上学期",
                duration="6 周",
                pace_reason="先把项目沉淀为可展示的就业级作品",
                goal="完成作品集整理、性能优化和面试讲解准备",
                stage_titles=["项目复盘", "优化迭代", "作品集整理"],
                key_points=["项目复盘", "性能优化", "作品集包装"],
                difficult_points=["方案取舍", "表达与复盘"],
                acceptance_criteria=["形成可展示的就业级项目作品集"],
                difficulty_level="中级",
            ),
            _course_spec(
                course_node_id="year_4_course_2",
                theme=f"{topic}综合项目孵化",
                semester_scope="上学期",
                duration="6 周",
                pace_reason="把既有能力沉淀成完整毕业项目",
                goal=f"围绕 {topic} 形成可展示的综合项目方案与技术路线",
                stage_titles=["选题聚焦", "架构方案", "阶段演示"],
                key_points=["选题定位", "架构取舍", "里程碑规划"],
                difficult_points=["范围收敛", "方案表达"],
                acceptance_criteria=["完成一个可演示的毕业项目方案与第一版实现"],
                difficulty_level="中级",
            ),
            _course_spec(
                course_node_id="year_4_course_3",
                theme=f"{topic}求职展示与面试复盘",
                semester_scope="下学期",
                duration="4 周",
                pace_reason="收束为求职表达与面试准备",
                goal="完成项目讲解稿、问答清单与个人复盘素材",
                stage_titles=["项目讲解", "问答清单", "面试复盘"],
                key_points=["项目表达", "面试问答", "复盘能力"],
                difficult_points=["重点取舍", "高压表达"],
                acceptance_criteria=["能独立完成一次完整项目讲解与面试复盘"],
                difficulty_level="中级",
            ),
        ]
        relations = [
            _knowledge_relation(
                from_node_id="year_3_course_3",
                to_node_id="year_4_course_1",
                relation_type="prerequisite",
                description="先完成项目级部署与监控实践，再沉淀毕业作品与求职表达。",
            )
        ]
        return "大四", "沉淀就业级项目作品集", specs, relations

    specs = [
        _course_spec(
            course_node_id="year_3_course_1",
            theme=f"{topic}基础能力搭建",
            semester_scope="上学期",
            duration="6 周",
            pace_reason=pace_reason,
            goal=f"完成 {topic} 所需的核心接口、工具链与最小功能闭环",
            stage_titles=["需求拆解", "接口接入", "最小闭环演示"],
            key_points=["OpenAI-compatible API 调用", "Prompt 设计", "前后端联调"],
            difficult_points=["异步调用稳定性", "错误处理与重试"],
            acceptance_criteria=["完成一个可运行的 AI 功能模块并接入 Web 应用"],
            difficulty_level="中级",
        ),
        _course_spec(
            course_node_id="year_3_course_2",
            theme=f"{topic}项目实战",
            semester_scope="上学期",
            duration="8 周",
            pace_reason=pace_reason,
            goal=f"围绕 {topic} 完成一个具备真实交互与部署能力的课程级项目",
            stage_titles=["架构设计", "多智能体联调", "部署验收"],
            key_points=["LangGraph 编排", "SSE 流式交互", "部署与监控"],
            difficult_points=["多智能体状态管理", "线上稳定性"],
            acceptance_criteria=["项目支持真实用户流程与部署演示"],
            difficulty_level="中级",
        ),
        _course_spec(
            course_node_id="year_3_course_3",
            theme=f"{topic}工程化服务编排与部署监控",
            semester_scope="下学期",
            duration="6 周",
            pace_reason=pace_reason,
            goal=f"围绕 {topic} 补强工程化服务编排、部署与线上监控能力",
            stage_titles=["服务编排", "部署方案", "监控复盘"],
            key_points=["服务编排", "部署与发布", "监控告警"],
            difficult_points=["状态一致性", "线上问题定位"],
            acceptance_criteria=["完成一个支持基础监控与部署复盘的工程化项目版本"],
            difficulty_level="中级",
        ),
    ]
    relations = [
        _knowledge_relation(
            from_node_id="year_2_course_3",
            to_node_id="year_3_course_1",
            relation_type="prerequisite",
            description="先具备全栈联调与部署入门能力，再进入 AI 功能闭环搭建。",
        )
    ]
    return "大三", f"完成 {topic} 项目闭环", specs, relations


def _build_learning_path_from_course_specs(
    profile: dict,
    *,
    grade_year: str,
    learning_topic: str,
    grade_goal: str,
    goal_type: str,
    desired_outcome: str,
    four_year_outcome: str,
    current_focus: str,
    next_action: str,
    course_specs: list[dict],
) -> dict:
    confirmed = profile.get("confirmed_info", {}) if isinstance(profile, dict) else {}
    major = str(confirmed.get("major") or "")
    current_grade = str(confirmed.get("current_grade") or "")
    weekly_time = str(confirmed.get("weekly_available_time") or "")
    constraints = str(confirmed.get("constraints") or "")
    weaknesses_text = str(confirmed.get("weaknesses") or "")
    weaknesses = [item for item in weaknesses_text.split("、") if item]
    knowledge_foundation = str(confirmed.get("knowledge_foundation") or "")
    mastered_content = [knowledge_foundation] if knowledge_foundation else []
    pace_reason = f"围绕{constraints}安排" if constraints else "根据后续补充的时间与约束调整"
    topic = learning_topic or DEFAULT_TOPIC
    resource_directions: list[dict] = []
    grade_name, default_grade_goal, _default_specs, leading_relations = _grade_course_specs(grade_year, topic, pace_reason)

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

    grade_courses: list[dict] = []
    global_relations = list(leading_relations)
    ordered_node_ids: list[str] = []
    previous_course_id = ""
    for index, spec in enumerate(course_specs, start=1):
        resource_ids = build_course_resources(
            spec["course_node_id"],
            spec["theme"],
            spec["key_points"][:2],
            spec["difficulty_level"],
        )
        chapter_nodes, core_knowledge_points, knowledge_relations = _build_course_structure(
            course_node_id=spec["course_node_id"],
            theme=spec["theme"],
            stage_titles=spec["stage_titles"],
            key_points=spec["key_points"],
            difficult_points=spec["difficult_points"],
            acceptance_criteria=spec["acceptance_criteria"],
            resource_direction_ids=resource_ids,
        )
        prerequisite_node_ids = [previous_course_id] if previous_course_id else []
        grade_courses.append(
            _course_node(
                course_node_id=spec["course_node_id"],
                grade_id=grade_year,
                theme=spec["theme"],
                semester_scope=_normalize_semester_scope(
                    str(spec.get("semester_scope") or ""),
                    course_index=index,
                    total_courses=len(course_specs),
                ),
                duration=spec["duration"],
                pace_reason=spec["pace_reason"],
                goal=spec["goal"],
                key_points=spec["key_points"],
                difficult_points=spec["difficult_points"],
                learning_sequence=spec["stage_titles"],
                acceptance_criteria=spec["acceptance_criteria"],
                prerequisite_node_ids=prerequisite_node_ids,
                chapter_nodes=chapter_nodes,
                core_knowledge_points=core_knowledge_points,
                knowledge_relations=knowledge_relations,
                downstream_resource_direction_ids=resource_ids,
            )
        )
        if previous_course_id:
            global_relations.append(
                _knowledge_relation(
                    from_node_id=previous_course_id,
                    to_node_id=spec["course_node_id"],
                    relation_type="extends",
                    description=f"先完成 {previous_course_id}，再进入 {spec['theme']}。",
                )
            )
        previous_course_id = spec["course_node_id"]
        ordered_node_ids.append(spec["course_node_id"])

    grade_plans = {
        grade_year: {
            "grade_id": grade_year,
            "grade_name": grade_name,
            "grade_goal": grade_goal or default_grade_goal,
            "course_nodes": grade_courses,
        }
    }
    if not grade_courses:
        raise ValueError("学习路径 course_specs 为空，无法展开为完整路径。")
    current_course = grade_courses[0]
    normalized_current_focus = current_focus.strip() if isinstance(current_focus, str) and current_focus.strip() else f"正在学习 {current_course['course_or_chapter_theme']}"
    normalized_next_action = next_action.strip() if isinstance(next_action, str) and next_action.strip() else "开始第一章需求拆解"
    current_learning_course = _current_course_from_node(
        current_course,
        current_focus=normalized_current_focus,
        next_action=normalized_next_action,
    )

    return {
        "schema_version": "learning_path.v2.course_node",
        "learning_goal": {
            "target_course_or_skill": topic,
            "goal_type": _normalize_goal_type(goal_type),
            "desired_outcome": desired_outcome,
            "four_year_outcome": four_year_outcome,
        },
        "learner_baseline": {
            "current_grade": current_grade,
            "major": major,
            "mastered_content": mastered_content,
            "weaknesses": weaknesses,
            "constraints": [constraints] if constraints else [],
            "weekly_available_time": weekly_time,
        },
        "planning_rules": {
            "node_unit": "course_node",
            "grade_boundary_rule": "一个学年生成一张学习路径表，按课程节点递进",
            "sequence_rule": "同一年级内先完成前置课程，再推进后续课程",
            "resource_rule": "按课程节点生成资源与后续练习",
        },
        "grade_plans": grade_plans,
        "knowledge_graph": {
            "global_relations": global_relations,
            "critical_paths": [
                _critical_path(
                    f"{grade_year}_learning_path",
                    f"围绕{topic}形成 {grade_name} 当前学年的主路径",
                    ordered_node_ids,
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
        "current_learning_courses": [current_learning_course],
        "current_learning_course": current_learning_course,
    }


def _build_local_learning_path(
    profile: dict,
    *,
    grade_year: str,
    learning_topic: str,
) -> dict:
    confirmed = profile.get("confirmed_info", {}) if isinstance(profile, dict) else {}
    constraints = str(confirmed.get("constraints") or "")
    pace_reason = f"围绕{constraints}安排" if constraints else "根据后续补充的时间与约束调整"
    topic = learning_topic or DEFAULT_TOPIC
    _grade_name, grade_goal, course_specs, _leading_relations = _grade_course_specs(grade_year, topic, pace_reason)

    return _build_learning_path_from_course_specs(
        profile,
        grade_year=grade_year,
        learning_topic=topic,
        grade_goal=grade_goal,
        goal_type="项目实践",
        desired_outcome=f"完成一个围绕 {topic} 的课程级项目",
        four_year_outcome="形成就业级项目作品集",
        current_focus="",
        next_action="",
        course_specs=course_specs,
    )


def _load_existing_year_learning_paths(state: OrchestrationState) -> dict[str, dict]:
    existing_paths = state.get("year_learning_paths")
    if isinstance(existing_paths, dict):
        return existing_paths

    user_id = str(state.get("user_id", "")).strip()
    if not user_id:
        return {}

    from sqlmodel import Session

    from app.database import get_engine
    from app.services.learning_path_service import get_all_year_learning_paths

    try:
        with Session(get_engine()) as db_session:
            return get_all_year_learning_paths(db_session, user_id)
    except Exception as exc:
        logger.warning("Failed to load existing learning paths for user %s: %s", user_id, exc)
        return {}


def _progress_snapshot_for_grade(
    progress_snapshots: list[dict[str, object]],
    grade_year: str,
) -> dict[str, object] | None:
    for snapshot in progress_snapshots:
        if str(snapshot.get("grade_year", "")).strip() == grade_year:
            return snapshot
    return None


def _scope_learning_path_to_grade_year(path_dict: dict, grade_year: str) -> dict:
    scoped_path = copy.deepcopy(path_dict)
    grade_plans = scoped_path.get("grade_plans")
    if not isinstance(grade_plans, dict) or grade_year not in grade_plans:
        return scoped_path

    scoped_path["grade_plans"] = {grade_year: grade_plans[grade_year]}
    courses = _path_courses(scoped_path, grade_year)
    if not courses:
        return scoped_path

    current = scoped_path.get("current_learning_course")
    if not isinstance(current, dict) or current.get("grade_id") != grade_year:
        current = _current_course_from_node(courses[0])
        scoped_path["current_learning_course"] = current

    current_courses = scoped_path.get("current_learning_courses")
    if not isinstance(current_courses, list) or not current_courses:
        scoped_path["current_learning_courses"] = [scoped_path["current_learning_course"]]
    else:
        scoped_path["current_learning_courses"] = [scoped_path["current_learning_course"]]
    return scoped_path


def _apply_existing_progress_to_path(
    path_dict: dict,
    grade_year: str,
    progress_snapshot: dict[str, object] | None,
) -> dict:
    if progress_snapshot is None:
        return path_dict

    courses = _path_courses(path_dict, grade_year)
    if not courses:
        return path_dict

    total_courses = len(courses)
    completed_courses = int(progress_snapshot.get("completed_courses", 0) or 0)
    next_course_id = str(progress_snapshot.get("next_course_id", "")).strip()

    if completed_courses >= total_courses:
        completed_course = _current_course_from_node(
            courses[-1],
            progress_state="completed",
            current_focus="当前阶段课程已全部完成",
            next_action="当前年级课程已完成",
        )
        path_dict["current_learning_course"] = completed_course
        path_dict["current_learning_courses"] = [completed_course]
        return path_dict

    if next_course_id:
        next_course = next(
            (
                course
                for course in courses
                if isinstance(course, dict) and course.get("course_node_id") == next_course_id
            ),
            None,
        )
        if isinstance(next_course, dict):
            current_course = _current_course_from_node(
                next_course,
                current_focus=f"基于已完成进度，继续推进 {next_course['course_or_chapter_theme']}",
                next_action="延续当前完成度，从这一门课继续推进",
            )
            path_dict["current_learning_course"] = current_course
            path_dict["current_learning_courses"] = [current_course]
            return path_dict

    next_index = max(0, min(completed_courses, total_courses - 1))
    current_course = _current_course_from_node(
        courses[next_index],
        current_focus=f"基于已完成进度，继续推进 {courses[next_index]['course_or_chapter_theme']}",
        next_action="延续当前完成度，从这一门课继续推进",
    )
    path_dict["current_learning_course"] = current_course
    path_dict["current_learning_courses"] = [current_course]
    return path_dict


def _build_learning_path_from_plan(
    profile: dict,
    *,
    grade_year: str,
    learning_topic: str,
    plan_data: dict,
    intake_courses: list[dict] | None = None,
) -> dict:
    if plan_data.get("schema_version") == "learning_path.v2.course_node":
        return _scope_learning_path_to_grade_year(plan_data, grade_year)

    confirmed = profile.get("confirmed_info", {}) if isinstance(profile, dict) else {}
    constraints = str(confirmed.get("constraints") or "")
    pace_reason = f"围绕{constraints}安排" if constraints else "根据后续补充的时间与约束调整"
    _grade_name, default_grade_goal, _default_specs, _leading_relations = _grade_course_specs(
        grade_year,
        learning_topic or DEFAULT_TOPIC,
        pace_reason,
    )

    raw_course_specs = plan_data.get("course_specs")
    if not isinstance(raw_course_specs, list):
        raise ValueError("学习路径规划结果缺少 course_specs。")
    if not MIN_LEARNING_PATH_COURSES <= len(raw_course_specs) <= MAX_LEARNING_PATH_COURSES:
        raise ValueError("学习路径 course_specs 数量必须在 4 到 10 门之间。")

    expected_courses = intake_courses if isinstance(intake_courses, list) else []
    if expected_courses and len(raw_course_specs) != len(expected_courses):
        raise ValueError("学习路径 course_specs 数量必须与已确认课程草案一致。")

    course_specs: list[dict] = []
    for index, spec in enumerate(raw_course_specs, start=1):
        if not isinstance(spec, dict):
            continue
        intake_course = expected_courses[index - 1] if index <= len(expected_courses) else {}
        intake_title = str(intake_course.get("title", "")).strip() if isinstance(intake_course, dict) else ""
        intake_purpose = str(intake_course.get("purpose", "")).strip() if isinstance(intake_course, dict) else ""
        spec_goal = str(spec.get("goal") or "").strip()
        course_specs.append(
            {
                "course_node_id": f"{grade_year}_course_{index}",
                "theme": intake_title or str(spec.get("theme") or "").strip(),
                "semester_scope": str(spec.get("semester_scope") or "").strip(),
                "duration": str(spec.get("duration") or "").strip(),
                "pace_reason": str(spec.get("pace_reason") or "").strip(),
                "goal": spec_goal or intake_purpose,
                "stage_titles": [str(item).strip() for item in spec.get("stage_titles", []) if str(item).strip()],
                "key_points": [str(item).strip() for item in spec.get("key_points", []) if str(item).strip()],
                "difficult_points": [str(item).strip() for item in spec.get("difficult_points", []) if str(item).strip()],
                "acceptance_criteria": [str(item).strip() for item in spec.get("acceptance_criteria", []) if str(item).strip()],
                "difficulty_level": _normalize_difficulty_level(str(spec.get("difficulty_level") or "中级")),
            }
        )

    return _build_learning_path_from_course_specs(
        profile,
        grade_year=grade_year,
        learning_topic=learning_topic,
        grade_goal=_normalize_grade_goal(
            str(plan_data.get("grade_goal") or ""),
            grade_year=grade_year,
            default_grade_goal=default_grade_goal,
        ),
        goal_type=str(plan_data.get("goal_type") or "项目实践").strip() or "项目实践",
        desired_outcome=str(plan_data.get("desired_outcome") or f"完成一个围绕 {learning_topic} 的课程级项目").strip(),
        four_year_outcome=str(plan_data.get("four_year_outcome") or "形成就业级项目作品集").strip(),
        current_focus=str(plan_data.get("current_focus") or "").strip(),
        next_action=str(plan_data.get("next_action") or "").strip(),
        course_specs=course_specs,
    )


async def run_learning_path_agent(state: OrchestrationState, llm: BaseChatModel) -> dict:
    """Generate a simplified learning path for a single grade year."""
    tool_args = extract_last_tool_call_args(state)

    profile = state.get("profile")
    confirmed = profile.get("confirmed_info", {}) if isinstance(profile, dict) else {}
    current_grade = confirmed.get("current_grade") if isinstance(confirmed, dict) else ""
    if isinstance(current_grade, str) and current_grade.strip() and not is_supported_current_grade(current_grade):
        return {"error": unsupported_current_grade_error(current_grade), "hard_error": True}
    if not is_complete_profile_data(profile):
        return {"error": "请先完成基础画像再生成学习路径。", "hard_error": True}

    intake, intake_error = _confirmed_intake_from_state(state)
    if intake_error:
        return {"error": intake_error, "hard_error": True}

    grade_year = str(intake.get("grade_year", "")).strip()
    if not grade_year:
        return {"error": "课程草案中缺少可识别的年级，无法生成学习路径。", "hard_error": True}

    query = str(state.get("query", "")).strip()
    resolved_topic = str(intake.get("learning_topic", "")).strip()
    if not resolved_topic:
        return {"error": "课程草案中缺少学习主题，无法生成学习路径。", "hard_error": True}

    existing_year_learning_paths = _load_existing_year_learning_paths(state)
    from app.services.learning_path_service import get_learning_path_progress_snapshots

    progress_snapshots = get_learning_path_progress_snapshots(existing_year_learning_paths)
    target_progress_snapshot = _progress_snapshot_for_grade(progress_snapshots, grade_year)

    input_text = _build_analysis_input(
        profile,
        grade_year,
        resolved_topic,
        str(tool_args.get("specific_requirements", "")),
        progress_snapshots,
        intake,
    )

    try:
        structured_llm = llm.with_structured_output(LearningPathPlanOutput)
        prompt = ChatPromptTemplate.from_messages([
            ("system", LEARNING_PATH_AGENT_SYSTEM_PROMPT),
            ("human", "{query}"),
        ])
        chain = prompt | structured_llm
        result: LearningPathPlanOutput = await asyncio.wait_for(
            chain.ainvoke({"query": input_text}),
            timeout=LEARNING_PATH_STRUCTURED_TIMEOUT_SECONDS,
        )
    except Exception as exc:
        logger.warning("LearningPathAgent structured output failed: %s: %s", type(exc).__name__, exc)
        return {"error": f"{LEARNING_PATH_RETRY_ERROR} ({type(exc).__name__}: {exc})", "hard_error": True}

    try:
        path_dict = _build_learning_path_from_plan(
            profile,
            grade_year=grade_year,
            learning_topic=resolved_topic,
            plan_data=result.model_dump(),
            intake_courses=intake.get("courses", []),
        )
    except Exception as exc:
        logger.warning("LearningPathAgent plan expansion failed: %s: %s", type(exc).__name__, exc)
        return {"error": f"{LEARNING_PATH_RETRY_ERROR} (plan: {type(exc).__name__}: {exc})", "hard_error": True}
    path_dict = _apply_existing_progress_to_path(path_dict, grade_year, target_progress_snapshot)
    contract_error = _validate_learning_path_contract(path_dict)
    if contract_error:
        logger.warning("LearningPathAgent contract validation failed: %s", contract_error)
        return {"error": f"{LEARNING_PATH_RETRY_ERROR} (contract: {contract_error})", "hard_error": True}
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
            result["course_knowledge"] = None
            result["response"] = _learning_path_response_text(agent_result["year_learning_path"])
        if agent_result.get("error") is not None:
            result["response"] = agent_result["error"]
        return result

    return learning_path_agent_node
