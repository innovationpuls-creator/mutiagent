from __future__ import annotations

from datetime import datetime, timezone

from sqlmodel import Session, select

from app.models import CourseResourceQuality


def _score_outline_completeness(outline_data: dict) -> tuple[int, list[str]]:
    """Score based on whether outline sections have composed content."""
    suggestions: list[str] = []
    sections = outline_data.get("sections", [])
    if not isinstance(sections, list) or not sections:
        return 0, ["课程大纲为空"]

    total = 0
    with_content = 0
    for section in sections:
        if not isinstance(section, dict):
            continue
        if section.get("parent_section_id") is not None:
            continue
        total += 1
        composed = section.get("composed_markdown")
        if isinstance(composed, str) and composed.strip():
            with_content += 1

    if total == 0:
        return 0, ["未找到顶层章节"]

    ratio = with_content / total
    score = round(ratio * 100)

    if score < 100:
        missing = total - with_content
        suggestions.append(f"还有 {missing} 个章节未生成内容")

    return score, suggestions


def _score_difficulty_fit(outline_data: dict, profile_data: dict | None) -> tuple[int, list[str]]:
    """Score based on difficulty match with user profile."""
    suggestions: list[str] = []

    if not profile_data or not isinstance(profile_data, dict):
        return 60, ["画像数据不完整，无法评估难度适配度"]

    stage = profile_data.get("learning_stage", "")
    pace = profile_data.get("learning_pace_preference", "")

    sections = outline_data.get("sections", [])
    if not isinstance(sections, list):
        return 50, ["大纲结构异常"]

    total_sections = len([
        s for s in sections
        if isinstance(s, dict) and s.get("parent_section_id") is None
    ])

    base_score = 70
    if isinstance(stage, str):
        if "刚入门" in stage and total_sections > 12:
            base_score -= 15
            suggestions.append("初学者课程章节数较多，建议精简")
        elif "项目实践" in stage and total_sections < 5:
            base_score -= 10
            suggestions.append("项目实践阶段章节数较少，建议增加实战内容")

    if isinstance(pace, str):
        if "每天少量" in pace and total_sections > 10:
            base_score -= 10
            suggestions.append("学习节奏较慢但章节较多，建议分阶段安排")

    score = max(0, min(100, base_score))
    return score, suggestions


def _score_accuracy(outline_data: dict) -> tuple[int, list[str]]:
    """Score based on structural quality markers."""
    suggestions: list[str] = []
    sections = outline_data.get("sections", [])
    if not isinstance(sections, list):
        return 0, ["大纲结构异常"]

    top_level = [
        s for s in sections
        if isinstance(s, dict) and s.get("parent_section_id") is None
    ]
    if not top_level:
        return 0, ["未找到章节"]

    has_subsections = any(
        s.get("parent_section_id") is not None
        for s in sections
        if isinstance(s, dict)
    )

    score = 60
    if has_subsections:
        score += 20
    if outline_data.get("learning_sequence"):
        score += 10
    if outline_data.get("personalization_summary"):
        score += 10

    if not has_subsections:
        suggestions.append("章节缺少子节划分")
    if not outline_data.get("learning_sequence"):
        suggestions.append("缺少推荐学习步骤")

    return min(100, score), suggestions


def score_course_resources(
    session: Session,
    user_uid: str,
    course_node_id: str,
    outline_data: dict,
    profile_data: dict | None,
) -> dict:
    """Compute quality scores for a course and persist them."""
    accuracy, acc_suggestions = _score_accuracy(outline_data)
    difficulty_fit, diff_suggestions = _score_difficulty_fit(outline_data, profile_data)
    completeness, comp_suggestions = _score_outline_completeness(outline_data)
    overall = round((accuracy + difficulty_fit + completeness) / 3)

    all_suggestions = acc_suggestions + diff_suggestions + comp_suggestions

    existing = session.get(CourseResourceQuality, (user_uid, course_node_id))
    now = datetime.now(timezone.utc)
    if existing:
        existing.accuracy_score = accuracy
        existing.difficulty_fit_score = difficulty_fit
        existing.completeness_score = completeness
        existing.overall_score = overall
        existing.suggestions = all_suggestions
        existing.scored_at = now
        existing.updated_at = now
    else:
        session.add(CourseResourceQuality(
            user_uid=user_uid,
            course_node_id=course_node_id,
            accuracy_score=accuracy,
            difficulty_fit_score=difficulty_fit,
            completeness_score=completeness,
            overall_score=overall,
            suggestions=all_suggestions,
            scored_at=now,
        ))

    session.commit()

    return {
        "accuracy": accuracy,
        "difficulty_fit": difficulty_fit,
        "completeness": completeness,
        "overall": overall,
        "suggestions": all_suggestions,
    }


def get_quality_scores_for_user(
    session: Session,
    user_uid: str,
) -> dict[str, dict]:
    """Return quality scores for all courses of a user, keyed by course_node_id."""
    rows = list(
        session.exec(
            select(CourseResourceQuality).where(CourseResourceQuality.user_uid == user_uid)
        ).all()
    )
    result: dict[str, dict] = {}
    for row in rows:
        result[row.course_node_id] = {
            "accuracy": row.accuracy_score,
            "difficulty_fit": row.difficulty_fit_score,
            "completeness": row.completeness_score,
            "overall": row.overall_score,
            "suggestions": row.suggestions if isinstance(row.suggestions, list) else [],
            "scored_at": row.scored_at.isoformat() if row.scored_at else None,
        }
    return result
