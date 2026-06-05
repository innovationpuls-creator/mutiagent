from __future__ import annotations

from collections.abc import Callable, Generator

from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.core.security import create_get_current_user
from app.models import User, UserProfile
from app.services.course_knowledge_service import get_user_course_knowledge_outline
from app.services.learning_path_service import (
    find_current_course,
    get_all_year_learning_paths,
    get_latest_grade_year,
    iter_year_learning_paths,
)

SessionDependency = Callable[[], Generator[Session, None, None]]

PROFILE_FIELDS = {
    "current_grade": "currentGrade",
    "major": "major",
    "learning_stage": "learningStage",
    "has_clear_goal": "hasClearGoal",
    "learning_method_preference": "learningMethodPreference",
    "learning_pace_preference": "learningPacePreference",
    "content_preference": "contentPreference",
    "need_guidance": "needGuidance",
    "knowledge_foundation": "knowledgeFoundation",
    "strengths": "strengths",
    "weaknesses": "weaknesses",
    "experience": "experience",
    "short_term_goal": "shortTermGoal",
    "long_term_goal": "longTermGoal",
    "weekly_available_time": "weeklyAvailableTime",
    "constraints": "constraints",
}

DEFAULT_PROFILE = {
    "currentGrade": "暂未确认",
    "major": "暂未确认",
    "learningStage": "暂未确认",
    "hasClearGoal": "暂未确认",
    "learningMethodPreference": "暂未确认",
    "learningPacePreference": "暂未确认",
    "contentPreference": [],
    "needGuidance": "暂未确认",
    "knowledgeFoundation": "暂未确认",
    "strengths": "暂未确认",
    "weaknesses": "暂未确认",
    "experience": "暂未确认",
    "shortTermGoal": "暂未确认",
    "longTermGoal": "暂未确认",
    "weeklyAvailableTime": "暂未确认",
    "constraints": "暂未确认",
}


def _camelize_confirmed_info(profile_data: dict) -> dict:
    confirmed = profile_data.get("confirmed_info", {})
    if not isinstance(confirmed, dict):
        return DEFAULT_PROFILE.copy()

    result = DEFAULT_PROFILE.copy()
    for source_key, target_key in PROFILE_FIELDS.items():
        value = confirmed.get(source_key)
        if source_key == "content_preference":
            result[target_key] = value if isinstance(value, list) else []
        elif isinstance(value, str) and value.strip():
            result[target_key] = value
    return result


def _profile_completeness(profile: dict) -> int:
    total = len(PROFILE_FIELDS)
    filled = 0
    for key, value in profile.items():
        if isinstance(value, list):
            filled += 1 if value else 0
        elif isinstance(value, str) and value != "暂未确认":
            filled += 1
    return round((filled / total) * 100)


def _summary_from_profile(profile_data: dict, profile: dict) -> str:
    text = profile_data.get("text")
    if isinstance(text, str) and text.strip():
        first_paragraph = text.strip().split("\n\n", 1)[0]
        return first_paragraph.replace("【用户基础信息】", "").strip() or text.strip()

    major = profile.get("major", "你的专业方向")
    stage = profile.get("learningStage", "当前阶段")
    return f"你正在围绕{major}建立基础画像，当前阶段是{stage}。继续完成画像后，会生成更具体的学习建议。"


def _compact(value: object, fallback: str, limit: int = 48) -> str:
    if isinstance(value, list):
        text = "、".join(str(item) for item in value if item)
    else:
        text = str(value or "")
    text = " ".join(text.split())
    if not text or text == "暂未确认":
        return fallback
    return text if len(text) <= limit else f"{text[:limit]}..."


def _today_learning_from_path(
    session: Session,
    user_uid: str,
    year_learning_paths: dict[str, dict] | None,
    latest_grade_year: str = "",
) -> dict | None:
    if not year_learning_paths:
        return None
    for path in iter_year_learning_paths(year_learning_paths, latest_grade_year):
        try:
            current_course = find_current_course(path)
        except ValueError:
            continue
        current = path["current_learning_course"]
        grade_plan = path.get("grade_plans", {}).get(current.get("grade_id"), {})
        course_nodes = grade_plan.get("course_nodes", [])
        current_index = next(
            (
                index
                for index, course in enumerate(course_nodes)
                if course.get("course_node_id") == current.get("course_node_id")
            ),
            -1,
        )
        following = course_nodes[current_index + 1 :] if current_index >= 0 else []
        course_id = current.get("course_node_id")
        current_course_outline = None
        if isinstance(course_id, str) and course_id:
            current_course_outline = get_user_course_knowledge_outline(session, user_uid, course_id)
        return {
            "title": current["course_or_chapter_theme"],
            "description": (
                f"{current['course_goal']} 当前重点：{current['current_focus']} "
                f"下一步：{current['next_action']}"
            ),
            "source": "学习路径智能体",
            "currentLearningCourse": current,
            "currentCourseDetail": current_course,
            "currentCourseOutline": current_course_outline,
            "followingCourses": following,
        }
    return None


def _dashboard_from_profile(
    session: Session,
    user_uid: str,
    stored: UserProfile | None,
    year_learning_paths: dict[str, dict] | None = None,
    latest_grade_year: str = "",
) -> dict:
    today_from_path = _today_learning_from_path(
        session,
        user_uid,
        year_learning_paths,
        latest_grade_year,
    )
    if stored is None:
        return {
            "profile": DEFAULT_PROFILE,
            "profileCompleteness": 0,
            "profileSummaryText": "还没有生成基础画像。完成 AI 对话后，这里会展示你的真实画像摘要。",
            "todayLearning": today_from_path or {
                "title": "先完成基础画像",
                "description": "回答关于年级、专业、学习偏好和目标的几个问题后，我会把结果保存到你的画像里。",
                "source": "等待画像生成",
                "currentLearningCourse": None,
                "currentCourseDetail": None,
                "currentCourseOutline": None,
                "followingCourses": [],
            },
            "recommendations": [],
        }

    profile_data = stored.profile_data if isinstance(stored.profile_data, dict) else {}
    profile = _camelize_confirmed_info(profile_data)
    if profile_data.get("type") == "collecting":
        return {
            "profile": profile,
            "profileCompleteness": _profile_completeness(profile),
            "profileSummaryText": _summary_from_profile(profile_data, profile),
            "todayLearning": today_from_path or {
                "title": "先完成基础画像",
                "description": "你还有几项关键信息待确认。继续完成画像后，我会把今日学习建议和推荐内容补全到这里。",
                "source": "等待画像生成",
                "currentLearningCourse": None,
                "currentCourseDetail": None,
                "currentCourseOutline": None,
                "followingCourses": [],
            },
            "recommendations": [],
        }

    short_goal = _compact(profile.get("shortTermGoal"), "围绕近期目标拆解学习任务")
    weakness = _compact(profile.get("weaknesses"), "根据画像补齐能力短板")
    content_preference = _compact(profile.get("contentPreference"), "根据偏好推荐学习资源")
    return {
        "profile": profile,
        "profileCompleteness": _profile_completeness(profile),
        "profileSummaryText": _summary_from_profile(stored.profile_data, profile),
        "todayLearning": today_from_path or {
            "title": "基于画像规划下一步",
            "description": f"优先处理「{short_goal}」，同时把「{weakness}」作为本阶段强化重点。",
            "source": "基础画像 Agent",
            "currentLearningCourse": None,
            "currentCourseDetail": None,
            "currentCourseOutline": None,
            "followingCourses": [],
        },
        "recommendations": [
            {
                "id": "rec-profile-goal",
                "title": "学习目标拆解",
                "duration": _compact(profile.get("weeklyAvailableTime"), "待定", 16),
                "description": short_goal,
                "accent": "sage",
            },
            {
                "id": "rec-profile-weakness",
                "title": "薄弱点强化",
                "duration": "个性化",
                "description": weakness,
                "accent": "lavender",
            },
            {
                "id": "rec-profile-content",
                "title": "内容形式匹配",
                "duration": "自适应",
                "description": content_preference,
                "accent": "peach",
            },
        ],
    }


def create_profile_router(session_dependency: SessionDependency) -> APIRouter:
    router = APIRouter(prefix="/api/profile", tags=["profile"])
    get_current_user = create_get_current_user(session_dependency)

    @router.get("/dashboard")
    async def get_dashboard(
        current_user: User = Depends(get_current_user),
        session: Session = Depends(session_dependency),
    ) -> dict:
        stored = session.get(UserProfile, current_user.uid)
        year_learning_paths = get_all_year_learning_paths(session, current_user.uid)
        latest_grade_year = get_latest_grade_year(session, current_user.uid)
        return _dashboard_from_profile(
            session,
            current_user.uid,
            stored,
            year_learning_paths,
            latest_grade_year,
        )

    return router
