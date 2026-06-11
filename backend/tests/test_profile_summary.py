from app.orchestration.agents.course_resources import _profile_summary_for_prompt


def test_empty_profile_returns_empty():
    assert _profile_summary_for_prompt(None) == ""
    assert _profile_summary_for_prompt({}) == ""


def test_partial_profile_returns_subset():
    profile = {
        "weaknesses": "数据结构",
        "learning_method_preference": "项目驱动学习",
    }
    result = _profile_summary_for_prompt(profile)
    assert "薄弱方向：数据结构" in result
    assert "学习方式偏好：项目驱动学习" in result
    assert "擅长方向" not in result


def test_full_profile_returns_all_dimensions():
    profile = {
        "weaknesses": "算法",
        "strengths": "前端开发",
        "learning_method_preference": "系统课程学习",
        "content_preference": ["文档", "视频"],
        "knowledge_foundation": "Python基础",
        "learning_pace_preference": "每天少量",
        "short_term_goal": "掌握数据结构",
    }
    result = _profile_summary_for_prompt(profile)
    assert "【用户画像摘要】" in result
    assert "内容形式偏好：文档、视频" in result
    assert "- " in result
