from __future__ import annotations

from app.orchestration.agents.prompts import (
    COURSE_KNOWLEDGE_AGENT_SYSTEM_PROMPT,
    LEARNING_PATH_AGENT_SYSTEM_PROMPT,
    LEARNING_PATH_INTAKE_AGENT_SYSTEM_PROMPT,
    SECTION_MARKDOWN_AGENT_SYSTEM_PROMPT,
    SUPERVISOR_BASE_PROMPT,
)


def _assert_contains(prompt: str, phrase: str) -> None:
    assert phrase in prompt


def test_supervisor_prompt_keeps_uncovered_topics_in_admin_gap_flow() -> None:
    _assert_contains(
        SUPERVISOR_BASE_PROMPT,
        "未覆盖内容不生成教学内容，必须进入管理员待办清单",
    )
    _assert_contains(
        SUPERVISOR_BASE_PROMPT,
        "只有已发布知识库教材可以进入学生端生成流程",
    )


def test_learning_path_intake_prompt_requires_published_textbook_context() -> None:
    _assert_contains(
        LEARNING_PATH_INTAKE_AGENT_SYSTEM_PROMPT,
        "课程草案只能从已发布知识库教材上下文生成",
    )
    _assert_contains(
        LEARNING_PATH_INTAKE_AGENT_SYSTEM_PROMPT,
        "每门课程必须绑定 "
        "source_textbook_id、source_textbook_title、source_outline_section_ids",
    )
    _assert_contains(
        LEARNING_PATH_INTAKE_AGENT_SYSTEM_PROMPT,
        "不得自行新增未发布教材或未绑定章节",
    )
    _assert_contains(
        LEARNING_PATH_INTAKE_AGENT_SYSTEM_PROMPT,
        "课程顺序会被正式学习路径智能体严格继承",
    )
    _assert_contains(
        LEARNING_PATH_INTAKE_AGENT_SYSTEM_PROMPT,
        "每门课程的目的必须说明后续大纲与 Markdown 资源生成边界",
    )


def test_learning_path_prompt_preserves_confirmed_source_bindings() -> None:
    _assert_contains(
        LEARNING_PATH_AGENT_SYSTEM_PROMPT,
        "正式学习路径必须以已确认课程草案为唯一课程边界",
    )
    _assert_contains(
        LEARNING_PATH_AGENT_SYSTEM_PROMPT,
        "不得替换或新增课程草案中的教材来源绑定",
    )
    _assert_contains(
        LEARNING_PATH_AGENT_SYSTEM_PROMPT,
        "未绑定 source_textbook_id 的课程不得进入正式学习路径",
    )
    _assert_contains(
        LEARNING_PATH_AGENT_SYSTEM_PROMPT,
        "resource_generation_contract 必须声明下游顺序",
    )
    _assert_contains(
        LEARNING_PATH_AGENT_SYSTEM_PROMPT,
        "course_knowledge_agent -> section_markdown_agent -> "
        "section_video_search_agent -> section_html_animation_agent",
    )


def test_course_knowledge_prompt_requires_bound_textbook_sections() -> None:
    _assert_contains(
        COURSE_KNOWLEDGE_AGENT_SYSTEM_PROMPT,
        "章节目录只能基于课程节点绑定的教材小节生成",
    )
    _assert_contains(
        COURSE_KNOWLEDGE_AGENT_SYSTEM_PROMPT,
        "sections[] 的 source_* 字段必须来自绑定教材小节",
    )
    _assert_contains(COURSE_KNOWLEDGE_AGENT_SYSTEM_PROMPT, "不得新增未绑定教材小节")
    _assert_contains(
        COURSE_KNOWLEDGE_AGENT_SYSTEM_PROMPT,
        "每个二级小节必须为后续 Markdown 教学、视频检索和 HTML 动画提供具体知识点",
    )
    _assert_contains(
        COURSE_KNOWLEDGE_AGENT_SYSTEM_PROMPT,
        "不得把小节写成总体性、模糊的资源主题",
    )


def test_section_markdown_prompt_requires_textbook_evidence_pack() -> None:
    _assert_contains(
        SECTION_MARKDOWN_AGENT_SYSTEM_PROMPT,
        "教材证据包是唯一正文事实来源",
    )
    _assert_contains(
        SECTION_MARKDOWN_AGENT_SYSTEM_PROMPT,
        "没有教材证据包时不得生成正文教学内容",
    )
    _assert_contains(
        SECTION_MARKDOWN_AGENT_SYSTEM_PROMPT,
        "不得脱离 evidence_text 自行补充事实",
    )
