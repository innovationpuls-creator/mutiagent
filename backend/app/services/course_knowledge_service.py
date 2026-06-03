from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterator

from sqlmodel import Session

from app.models import UserCourseKnowledgeOutline
from app.orchestration.agent_plan import GRADE_PLAN_KEYS


def get_user_course_knowledge_outline(
    session: Session,
    user_uid: str,
    course_node_id: str,
) -> UserCourseKnowledgeOutline | None:
    return session.get(UserCourseKnowledgeOutline, (user_uid, course_node_id))


def upsert_user_course_knowledge_outline(
    session: Session,
    user_uid: str,
    outline_data: dict,
) -> UserCourseKnowledgeOutline:
    course_node_id = str(outline_data.get("course_node_id") or "")
    if not course_node_id:
        raise ValueError("course_node_id is required")

    now = datetime.now(timezone.utc)
    stored = session.get(UserCourseKnowledgeOutline, (user_uid, course_node_id))
    if stored is None:
        stored = UserCourseKnowledgeOutline(
            user_uid=user_uid,
            course_node_id=course_node_id,
            grade_id=str(outline_data.get("grade_id") or ""),
            course_name=str(outline_data.get("course_name") or ""),
            outline_data=outline_data,
            created_at=now,
            updated_at=now,
        )
    else:
        stored.grade_id = str(outline_data.get("grade_id") or "")
        stored.course_name = str(outline_data.get("course_name") or "")
        stored.outline_data = outline_data
        stored.updated_at = now

    session.add(stored)
    session.commit()
    session.refresh(stored)
    return stored


def iter_course_nodes(path_data: dict) -> Iterator[dict]:
    grade_plans = path_data.get("grade_plans")
    if not isinstance(grade_plans, dict):
        return

    for grade_id in GRADE_PLAN_KEYS:
        grade_plan = grade_plans.get(grade_id)
        if not isinstance(grade_plan, dict):
            continue
        course_nodes = grade_plan.get("course_nodes")
        if not isinstance(course_nodes, list):
            continue
        for course_node in course_nodes:
            if isinstance(course_node, dict):
                yield course_node


def find_course_node(path_data: dict, course_node_id: str) -> dict | None:
    for course_node in iter_course_nodes(path_data):
        if course_node.get("course_node_id") == course_node_id:
            return course_node
    return None


def resolve_current_course_node(path_data: dict) -> dict:
    knowledge_graph = path_data.get("knowledge_graph")
    critical_paths = knowledge_graph.get("critical_paths") if isinstance(knowledge_graph, dict) else None
    if isinstance(critical_paths, list):
        for path_item in critical_paths:
            if not isinstance(path_item, dict):
                continue
            ordered_node_ids = path_item.get("ordered_node_ids")
            if not isinstance(ordered_node_ids, list):
                continue
            for node_id in ordered_node_ids:
                if not isinstance(node_id, str):
                    continue
                course_node = find_course_node(path_data, node_id)
                if course_node is not None:
                    return course_node

    for course_node in iter_course_nodes(path_data):
        return course_node

    raise ValueError("学习路径中没有可用的课程节点。")
