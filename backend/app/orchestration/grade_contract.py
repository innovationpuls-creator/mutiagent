from __future__ import annotations

UNDERGRAD_GRADE_YEAR_MAP = {
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


def grade_year_from_current_grade(current_grade: object) -> str:
    grade_text = str(current_grade or "").strip()
    if not grade_text:
        return ""
    for label, grade_year in UNDERGRAD_GRADE_YEAR_MAP.items():
        if label in grade_text:
            return grade_year
    return ""


def is_supported_current_grade(current_grade: object) -> bool:
    return grade_year_from_current_grade(current_grade) != ""


def unsupported_current_grade_error(current_grade: object) -> str:
    grade_text = str(current_grade or "").strip()
    if grade_text:
        return (
            "当前学习路径只支持大一到大四。"
            f"你当前提供的年级是「{grade_text}」，请先确认对应的本科年级。"
        )
    return "当前学习路径只支持大一到大四，请先确认你的本科年级。"


REQUIRED_CONFIRMED_INFO_KEYS = frozenset(
    {
        "current_grade",
        "major",
        "learning_stage",
        "has_clear_goal",
        "learning_method_preference",
        "learning_pace_preference",
        "content_preference",
        "need_guidance",
        "knowledge_foundation",
        "strengths",
        "weaknesses",
        "experience",
        "short_term_goal",
        "long_term_goal",
        "weekly_available_time",
        "constraints",
    }
)


def is_complete_profile_data(profile: dict | None) -> bool:
    """A finished basic profile: every required field plus a supported grade."""
    if not isinstance(profile, dict) or profile.get("type") != "basic_profile":
        return False
    confirmed_info = profile.get("confirmed_info")
    if not isinstance(confirmed_info, dict):
        return False
    return REQUIRED_CONFIRMED_INFO_KEYS.issubset(
        confirmed_info.keys()
    ) and is_supported_current_grade(confirmed_info.get("current_grade"))
