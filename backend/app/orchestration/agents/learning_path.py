from __future__ import annotations

import copy

DEFAULT_TOPIC = "学习路径"
MIN_LEARNING_PATH_COURSES = 4
MAX_LEARNING_PATH_COURSES = 8


def _validate_learning_path_contract(path_data: dict) -> str:
    if path_data.get("schema_version") != "learning_path.v2.course_node":
        return "学习路径 schema_version 不正确。"
    current = path_data.get("current_learning_course")
    if not isinstance(current, dict):
        return "学习路径缺少 current_learning_course。"
    progress_state = current.get("progress_state")
    if progress_state not in {"in_progress", "completed"}:
        return (
            "current_learning_course.progress_state 必须是 in_progress 或 completed。"
        )
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
    normalized_course_nodes = [
        course for course in course_nodes if isinstance(course, dict)
    ]
    if (
        not MIN_LEARNING_PATH_COURSES
        <= len(normalized_course_nodes)
        <= MAX_LEARNING_PATH_COURSES
    ):
        return "当前学年课程数量必须在 4 到 8 门之间。"
    if not any(
        course.get("course_node_id") == course_id for course in normalized_course_nodes
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


def _time_arrangement(
    duration: str, pace_reason: str, semester_scope: str = "上学期"
) -> dict:
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
    source_textbook_id: str,
    source_textbook_title: str,
    source_outline_section_ids: list[str],
    course_stage_plan: list[str],
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
        "source_textbook_id": source_textbook_id,
        "source_textbook_title": source_textbook_title,
        "source_outline_section_ids": source_outline_section_ids,
        "course_stage_plan": course_stage_plan,
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
        "current_focus": current_focus
        or f"正在学习 {course['course_or_chapter_theme']}",
        "progress_state": progress_state,
        "next_action": next_action or "开始第一章需求拆解",
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

    point_ids = [
        item["knowledge_point_id"]
        for item in knowledge_points[: max(1, min(2, len(knowledge_points)))]
    ]
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
                prerequisite_node_ids=[chapter_nodes[-1]["chapter_node_id"]]
                if chapter_nodes
                else [],
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
    if (
        "career" in lowered
        or "job" in lowered
        or "求职" in normalized
        or "就业" in normalized
    ):
        return "就业准备"
    if "ability" in lowered or "skill" in lowered or "能力" in normalized:
        return "能力提升"
    return "其他"


def _normalize_semester_scope(
    value: str, *, course_index: int, total_courses: int
) -> str:
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


def _normalize_grade_goal(
    value: str, *, grade_year: str, default_grade_goal: str
) -> str:
    normalized = value.strip()
    if not normalized:
        return default_grade_goal
    lowered = normalized.lower()
    if lowered == grade_year.lower() or lowered.startswith("year_"):
        return default_grade_goal
    return normalized


_GRADE_NAMES = {"year_1": "大一", "year_2": "大二", "year_3": "大三", "year_4": "大四"}


def _grade_defaults(grade_year: str, topic: str) -> tuple[str, str]:
    """Display name and fallback goal of a grade (the plan comes from the agent)."""
    return _GRADE_NAMES.get(grade_year, grade_year), f"围绕{topic}完成本学年学习"


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
    topic = learning_topic or DEFAULT_TOPIC
    resource_directions: list[dict] = []
    grade_name, default_grade_goal = _grade_defaults(grade_year, topic)

    def build_course_resources(
        course_node_id: str, theme: str, focus: list[str], difficulty_level: str
    ) -> list[str]:
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
    global_relations: list[dict] = []
    ordered_node_ids: list[str] = []
    previous_course_id = ""
    for index, spec in enumerate(course_specs, start=1):
        resource_ids = build_course_resources(
            spec["course_node_id"],
            spec["theme"],
            spec["key_points"][:2],
            spec["difficulty_level"],
        )
        chapter_nodes, core_knowledge_points, knowledge_relations = (
            _build_course_structure(
                course_node_id=spec["course_node_id"],
                theme=spec["theme"],
                stage_titles=spec["stage_titles"],
                key_points=spec["key_points"],
                difficult_points=spec["difficult_points"],
                acceptance_criteria=spec["acceptance_criteria"],
                resource_direction_ids=resource_ids,
            )
        )
        prerequisite_node_ids = [previous_course_id] if previous_course_id else []
        grade_courses.append(
            _course_node(
                course_node_id=spec["course_node_id"],
                grade_id=grade_year,
                theme=spec["theme"],
                source_textbook_id=spec["source_textbook_id"],
                source_textbook_title=spec["source_textbook_title"],
                source_outline_section_ids=spec["source_outline_section_ids"],
                course_stage_plan=spec["course_stage_plan"],
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
                    description=(
                        f"先完成 {previous_course_id}，再进入 {spec['theme']}。"
                    ),
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
    normalized_current_focus = (
        current_focus.strip()
        if isinstance(current_focus, str) and current_focus.strip()
        else f"正在学习 {current_course['course_or_chapter_theme']}"
    )
    normalized_next_action = (
        next_action.strip()
        if isinstance(next_action, str) and next_action.strip()
        else "开始第一章需求拆解"
    )
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
            "downstream_agents": [
                "course_knowledge_agent",
                "section_markdown_agent",
                "section_video_search_agent",
                "section_html_animation_agent",
            ],
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
        scoped_path["current_learning_courses"] = [
            scoped_path["current_learning_course"]
        ]
    else:
        scoped_path["current_learning_courses"] = [
            scoped_path["current_learning_course"]
        ]
    return scoped_path


def _bind_confirmed_course_sources(
    path_dict: dict, grade_year: str, intake_courses: list[dict] | None
) -> dict:
    courses = _path_courses(path_dict, grade_year)
    expected_courses = intake_courses if isinstance(intake_courses, list) else []
    if not courses or not expected_courses:
        return path_dict
    if len(courses) != len(expected_courses):
        raise ValueError("学习路径 course_nodes 数量必须与已确认课程草案一致。")

    for index, course_node in enumerate(courses):
        intake_course = expected_courses[index]
        course_node["course_or_chapter_theme"] = str(intake_course["title"]).strip()
        course_node["source_textbook_id"] = str(
            intake_course["source_textbook_id"]
        ).strip()
        course_node["source_textbook_title"] = str(
            intake_course["source_textbook_title"]
        ).strip()
        course_node["source_outline_section_ids"] = intake_course[
            "source_outline_section_ids"
        ]
        course_node["course_stage_plan"] = [
            str(item).strip()
            for item in course_node.get("course_stage_plan", [])
            if str(item).strip()
        ] or [
            str(item).strip()
            for item in course_node.get("learning_sequence", [])
            if str(item).strip()
        ]
    return path_dict


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
                if isinstance(course, dict)
                and course.get("course_node_id") == next_course_id
            ),
            None,
        )
        if isinstance(next_course, dict):
            current_course = _current_course_from_node(
                next_course,
                current_focus=(
                    f"基于已完成进度，继续推进 {next_course['course_or_chapter_theme']}"
                ),
                next_action="延续当前完成度，从这一门课继续推进",
            )
            path_dict["current_learning_course"] = current_course
            path_dict["current_learning_courses"] = [current_course]
            return path_dict

    next_index = max(0, min(completed_courses, total_courses - 1))
    current_course = _current_course_from_node(
        courses[next_index],
        current_focus=(
            f"基于已完成进度，继续推进 {courses[next_index]['course_or_chapter_theme']}"
        ),
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
        scoped_path = _scope_learning_path_to_grade_year(plan_data, grade_year)
        return _bind_confirmed_course_sources(scoped_path, grade_year, intake_courses)

    _grade_name, default_grade_goal = _grade_defaults(
        grade_year, learning_topic or DEFAULT_TOPIC
    )

    raw_course_specs = plan_data.get("course_specs")
    if not isinstance(raw_course_specs, list):
        raise ValueError("学习路径规划结果缺少 course_specs。")
    if (
        not MIN_LEARNING_PATH_COURSES
        <= len(raw_course_specs)
        <= MAX_LEARNING_PATH_COURSES
    ):
        raise ValueError("学习路径 course_specs 数量必须在 4 到 8 门之间。")

    expected_courses = intake_courses if isinstance(intake_courses, list) else []
    if expected_courses and len(raw_course_specs) != len(expected_courses):
        raise ValueError("学习路径 course_specs 数量必须与已确认课程草案一致。")

    course_specs: list[dict] = []
    for index, spec in enumerate(raw_course_specs, start=1):
        if not isinstance(spec, dict):
            continue
        intake_course = (
            expected_courses[index - 1] if index <= len(expected_courses) else {}
        )
        intake_title = (
            str(intake_course["title"]).strip()
            if isinstance(intake_course, dict)
            else ""
        )
        intake_purpose = (
            str(intake_course["purpose"]).strip()
            if isinstance(intake_course, dict)
            else ""
        )
        spec_goal = str(spec.get("goal") or "").strip()
        course_specs.append(
            {
                "course_node_id": f"{grade_year}_course_{index}",
                "theme": intake_title or str(spec.get("theme") or "").strip(),
                "source_textbook_id": str(intake_course["source_textbook_id"]).strip(),
                "source_textbook_title": str(
                    intake_course["source_textbook_title"]
                ).strip(),
                "source_outline_section_ids": intake_course[
                    "source_outline_section_ids"
                ],
                "semester_scope": str(spec.get("semester_scope") or "").strip(),
                "duration": str(spec.get("duration") or "").strip(),
                "pace_reason": str(spec.get("pace_reason") or "").strip(),
                "goal": spec_goal or intake_purpose,
                "stage_titles": [
                    str(item).strip()
                    for item in spec.get("stage_titles", [])
                    if str(item).strip()
                ],
                "key_points": [
                    str(item).strip()
                    for item in spec.get("key_points", [])
                    if str(item).strip()
                ],
                "difficult_points": [
                    str(item).strip()
                    for item in spec.get("difficult_points", [])
                    if str(item).strip()
                ],
                "acceptance_criteria": [
                    str(item).strip()
                    for item in spec.get("acceptance_criteria", [])
                    if str(item).strip()
                ],
                "course_stage_plan": [
                    str(item).strip()
                    for item in spec.get("stage_titles", [])
                    if str(item).strip()
                ],
                "difficulty_level": _normalize_difficulty_level(
                    str(spec.get("difficulty_level") or "中级")
                ),
            }
        )

    path_dict = _build_learning_path_from_course_specs(
        profile,
        grade_year=grade_year,
        learning_topic=learning_topic,
        grade_goal=_normalize_grade_goal(
            str(plan_data.get("grade_goal") or ""),
            grade_year=grade_year,
            default_grade_goal=default_grade_goal,
        ),
        goal_type=str(plan_data.get("goal_type") or "项目实践").strip() or "项目实践",
        desired_outcome=str(
            plan_data.get("desired_outcome")
            or f"完成一个围绕 {learning_topic} 的课程级项目"
        ).strip(),
        four_year_outcome=str(
            plan_data.get("four_year_outcome") or "形成就业级项目作品集"
        ).strip(),
        current_focus=str(plan_data.get("current_focus") or "").strip(),
        next_action=str(plan_data.get("next_action") or "").strip(),
        course_specs=course_specs,
    )
    return _bind_confirmed_course_sources(path_dict, grade_year, intake_courses)
