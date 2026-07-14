"""Contract tests for the course resource agent."""

# ruff: noqa: E501,E402

from __future__ import annotations

import json
import logging
from pathlib import Path

import httpx
import pytest

from app.orchestration.agents.course_resources import (
    _ANIMATION_TIMEOUT_SECONDS,
    _MARKDOWN_TIMEOUT_SECONDS,
    _RESOURCE_TIMEOUT_SECONDS,
    _VIDEO_TIMEOUT_SECONDS,
    _animation_input,
    _compose_section_content,
    _fallback_cover_data_url,
    _find_verified_video_from_search,
    _invoke_resource_chain,
    _markdown_input,
    _markdown_quality_issue,
    _merge_course_resource_data,
    _normalized_animation_quality_issue,
    _normalized_video_quality_issue,
    _normalized_video_quality_issue_async,
    _profile_learning_context_text,
    _section_body_from_expansion_text,
    _section_by_id,
    _target_sections_for_scope,
    _video_input,
    _video_search_queries,
)
from app.orchestration.agents.course_resources import animation as animation_module
from app.orchestration.agents.course_resources import bilibili as bilibili_module
from app.orchestration.agents.course_resources import video as video_module
from app.orchestration.agents.course_resources.common import (
    SECTION_MARKDOWN_EXPANSION_SYSTEM_PROMPT,
    _resource_query_with_prompt_budget,
    _section_markdown_data_from_plain_text,
)
from tests.postgres import postgresql_test_url


def _outline() -> dict:
    return {
        "course_id": "year_3_course_1",
        "course_name": "AI 应用开发",
        "grade_year": "year_3",
        "personalization_summary": "先完成需求拆解，再进入接口接入。",
        "sections": [
            {
                "section_id": "1",
                "parent_section_id": None,
                "depth": 1,
                "title": "需求拆解",
                "order_index": 1,
                "description": "确认功能边界与验收标准。",
                "key_knowledge_points": ["功能边界", "验收标准"],
            },
            {
                "section_id": "1.1",
                "parent_section_id": "1",
                "depth": 2,
                "title": "学习目标",
                "order_index": 2,
                "description": "明确本节学习目标。",
                "key_knowledge_points": ["功能边界"],
            },
            {
                "section_id": "1.2",
                "parent_section_id": "1",
                "depth": 2,
                "title": "任务拆解",
                "order_index": 3,
                "description": "把目标拆成任务。",
                "key_knowledge_points": ["任务拆分"],
            },
            {
                "section_id": "1.3",
                "parent_section_id": "1",
                "depth": 2,
                "title": "检查点",
                "order_index": 4,
                "description": "确认完成标准。",
                "key_knowledge_points": ["验收标准"],
            },
            {
                "section_id": "2",
                "parent_section_id": None,
                "depth": 1,
                "title": "接口接入",
                "order_index": 5,
                "description": "接入 LLM API。",
                "key_knowledge_points": ["API 调用"],
            },
            {
                "section_id": "2.1",
                "parent_section_id": "2",
                "depth": 2,
                "title": "学习目标",
                "order_index": 6,
                "description": "掌握接口接入目标。",
                "key_knowledge_points": ["API 调用"],
            },
        ],
        "learning_sequence": ["第一章：需求拆解", "第二章：接口接入"],
        "total_estimated_hours": "8 小时",
    }


def test_markdown_expansion_prompt_allows_english_evidence_but_requires_chinese_output() -> (
    None
):
    assert "英文" in SECTION_MARKDOWN_EXPANSION_SYSTEM_PROMPT
    assert "evidence_text" in SECTION_MARKDOWN_EXPANSION_SYSTEM_PROMPT
    assert "中文" in SECTION_MARKDOWN_EXPANSION_SYSTEM_PROMPT


def test_markdown_quality_requires_source_footer_when_section_has_textbook_binding() -> (
    None
):
    section = {
        "section_id": "1.1",
        "title": "复杂度分析",
        "description": "判断算法开销。",
        "key_knowledge_points": ["时间复杂度"],
        "source_textbook_id": "textbook-data-structures",
        "source_textbook_title": "数据结构教程",
        "source_section_ids": ["1.1"],
        "source_section_titles": ["复杂度分析"],
    }
    markdown = _complete_section_markdown("1.1", "复杂度分析").replace(
        "\n\n## 来源\n- 《AI 应用开发项目教程》：1.1 复杂度分析。", ""
    )

    issue = _markdown_quality_issue(
        markdown,
        section,
        [
            {
                "video_id": "video_1",
                "title": "复杂度分析视频",
                "purpose": "辅助理解时间复杂度。",
            }
        ],
        [
            {
                "animation_id": "anim_1",
                "title": "时间复杂度曲线动画",
                "concept": "展示输入规模增长时操作次数如何变化。",
                "visual_elements": ["输入规模", "操作次数", "增长趋势"],
            }
        ],
    )

    assert issue == "Markdown 缺少教材来源。"


def test_generated_markdown_briefs_use_specific_data_structure_visual_plan() -> None:
    from app.orchestration.agents.course_resources.common import (
        _generated_markdown_seed_data,
    )

    section = {
        "section_id": "2.3",
        "title": "单链表",
        "description": "讲解节点通过指针串联的线性结构。",
        "key_knowledge_points": ["节点", "指针", "插入删除"],
        "source_section_titles": ["链表的存储结构"],
    }

    seed_data = _generated_markdown_seed_data(section)

    video_brief = seed_data["video_briefs"][0]
    animation_brief = seed_data["animation_briefs"][0]
    assert "单链表" in video_brief["title"]
    assert "节点" in video_brief["purpose"]
    assert "指针" in video_brief["purpose"]
    assert animation_brief["title"] == "单链表节点指针串联动画"
    assert animation_brief["visual_elements"] == [
        "头指针",
        "节点(data,next)",
        "next 指针",
        "尾节点 None",
    ]
    assert "节点通过 next 指针串联" in animation_brief["concept"]


def test_course_resource_llm_timeouts_are_three_minutes() -> None:
    assert _RESOURCE_TIMEOUT_SECONDS == 180.0
    assert _MARKDOWN_TIMEOUT_SECONDS == 180.0
    assert _VIDEO_TIMEOUT_SECONDS == 180.0
    assert _ANIMATION_TIMEOUT_SECONDS == 180.0


def test_markdown_input_includes_textbook_evidence_pack(tmp_path) -> None:
    from sqlmodel import Session

    from app.database import build_engine, init_db, set_engine
    from app.models import User
    from tests.fixtures.knowledge_base import enabled_source, published_textbook
    from tests.fixtures.knowledge_base import section as k_section

    engine = build_engine(postgresql_test_url(tmp_path, "markdown-input-evidence"))
    set_engine(engine)
    init_db(engine)
    with Session(engine) as session:
        session.add(
            User(uid="user-1", username="课程用户", identifier="course@example.com")
        )
        session.add(enabled_source(source_id="source-ai-web"))
        textbook = published_textbook(
            textbook_id="textbook-ai-web",
            source_id="source-ai-web",
            title="AI 应用开发项目教程",
        )
        textbook.outline = {
            "sections": [
                {"section_id": "1.1", "title": "功能边界"},
                {"section_id": "1.2", "title": "验收标准"},
            ]
        }
        session.add(textbook)
        session.add(
            k_section(
                textbook_id="textbook-ai-web",
                section_content_id="markdown-input-section-1-1",
                section_id="1.1",
                title="功能边界",
                content_zh="功能边界正文来自知识库。",
                order_index=1,
            )
        )
        session.add(
            k_section(
                textbook_id="textbook-ai-web",
                section_content_id="markdown-input-section-1-2",
                section_id="1.2",
                title="验收标准",
                content_zh="验收标准正文来自知识库。",
                order_index=2,
            )
        )
        session.commit()

    outline = _outline()
    outline["source_textbook_id"] = "textbook-ai-web"
    outline["source_textbook_title"] = "AI 应用开发项目教程"
    outline["source_outline_section_ids"] = ["1.1", "1.2"]
    outline["source_section_ids"] = ["1.1", "1.2"]
    outline["source_section_titles"] = ["功能边界", "验收标准"]
    outline["source_content_chars"] = 3600
    outline["sections"][1]["source_textbook_id"] = "textbook-ai-web"
    outline["sections"][1]["source_textbook_title"] = "AI 应用开发项目教程"
    outline["sections"][1]["source_section_ids"] = ["1.1", "1.2"]
    outline["sections"][1]["source_section_titles"] = ["功能边界", "验收标准"]
    outline["sections"][1]["source_content_chars"] = 3600

    section = _section_by_id(outline, "1.1")
    assert section is not None
    payload = _markdown_input(
        {"profile": _profile(), "year_learning_paths": _year_learning_paths()},
        outline,
        section,
    )

    assert '"source_textbook_id"' in payload
    assert '"textbook_evidence_pack"' in payload
    assert '"source_section_ids"' in payload
    assert '"source_section_titles"' in payload
    assert '"source_content_chars"' in payload
    assert "功能边界正文来自知识库" in payload
    assert "验收标准正文来自知识库" in payload


def test_section_markdown_system_prompt_matches_full_document_generation() -> None:
    assert "完整 Markdown 文档" in SECTION_MARKDOWN_EXPANSION_SYSTEM_PROMPT
    assert "禁止输出完整 Markdown 文档" not in SECTION_MARKDOWN_EXPANSION_SYSTEM_PROMPT
    assert "禁止输出 `#` 或 `##` 标题" not in SECTION_MARKDOWN_EXPANSION_SYSTEM_PROMPT
    assert "禁止输出视频或动画占位符" not in SECTION_MARKDOWN_EXPANSION_SYSTEM_PROMPT


def test_invoke_resource_chain_parses_chat_message_content_before_model_dump() -> None:
    from app.orchestration.agents.models import SectionHtmlAnimationOutput

    class MessageLike:
        content = json.dumps(
            {
                "section_id": "1.1",
                "animations": [
                    {
                        "animation_id": "anim_1",
                        "title": "动画",
                        "html": '<section class="section-animation">动画内容</section>',
                    }
                ],
            },
            ensure_ascii=False,
        )

        def model_dump(self):
            return {"content": self.content, "type": "ai", "usage_metadata": {}}

    class Chain:
        async def ainvoke(self, _payload):
            return MessageLike()

    query = "请生成动画。\n\n输入：" + json.dumps(
        {
            "target_section": {"section_id": "1.1"},
            "animation_briefs": [
                {
                    "animation_id": "anim_1",
                    "title": "动画",
                    "concept": "动画内容",
                    "visual_elements": ["动画内容"],
                }
            ],
        },
        ensure_ascii=False,
    )

    result = asyncio.run(
        _invoke_resource_chain(Chain(), query, SectionHtmlAnimationOutput)
    )

    assert result["section_id"] == "1.1"
    assert result["animations"][0]["animation_id"] == "anim_1"


def test_youtube_search_request_logs_http_failure_type(monkeypatch, caplog) -> None:
    class FailingClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def get(self, *_args, **_kwargs):
            raise httpx.ConnectError("dns failure")

    monkeypatch.setattr(
        video_module.httpx, "AsyncClient", lambda **_kwargs: FailingClient()
    )

    results = asyncio.run(video_module._search_youtube_video_results("算法效率"))

    assert results == []
    assert "YouTube search request failed" in caplog.text
    assert "ConnectError" in caplog.text


def test_youtube_search_parse_logs_zero_results_on_invalid_initial_data(
    monkeypatch, caplog
) -> None:
    caplog.set_level(logging.WARNING)

    class InvalidSearchResponse:
        status_code = 200
        text = "<script>var ytInitialData = {invalid json};</script>"

        def raise_for_status(self):
            return None

    class SearchClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def get(self, *_args, **_kwargs):
            return InvalidSearchResponse()

    monkeypatch.setattr(
        video_module.httpx, "AsyncClient", lambda **_kwargs: SearchClient()
    )

    results = asyncio.run(video_module._search_youtube_video_results("算法效率"))

    assert results == []
    assert "YouTube search parse" in caplog.text
    assert "parsed_result_count=0" in caplog.text


def test_bilibili_search_parse_logs_zero_results_without_bv_id(
    monkeypatch, caplog
) -> None:
    caplog.set_level(logging.WARNING)

    class EmptySearchResponse:
        status_code = 200
        text = "搜索结果正文不含视频标识"

        def raise_for_status(self):
            return None

    class SearchClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def get(self, *_args, **_kwargs):
            return EmptySearchResponse()

    monkeypatch.setattr(
        bilibili_module.httpx, "AsyncClient", lambda **_kwargs: SearchClient()
    )

    results = asyncio.run(
        bilibili_module._search_bilibili_video_page_results("算法效率", {})
    )

    assert results == []
    assert "Bilibili search parse" in caplog.text
    assert "parsed_result_count=0" in caplog.text


def _profile() -> dict:
    return {
        "type": "basic_profile",
        "confirmed_info": {
            "current_grade": "大三",
            "major": "软件工程",
            "learning_stage": "项目实践",
            "learning_method_preference": "项目驱动学习",
            "content_preference": ["视频", "文档", "代码实践"],
            "weekly_available_time": "每天 12 小时项目驱动",
            "constraints": "需要先补齐需求边界表达",
        },
        "text": "画像强调项目驱动、视频文档结合，并需要补齐需求边界表达。",
    }


def _year_learning_paths() -> dict:
    return {
        "year_3": {
            "schema_version": "learning_path.v2.course_node",
            "current_learning_course": {
                "grade_id": "year_3",
                "course_node_id": "year_3_course_1",
                "course_or_chapter_theme": "AI 应用开发",
                "course_goal": "完成作品级 Agent 项目闭环",
                "current_focus": "先把需求拆解落实为可验收产出",
                "progress_state": "in_progress",
                "next_action": "完成第一章需求拆解",
            },
            "resource_generation_contract": {
                "resource_directions": [
                    {
                        "resource_direction_id": "year_3_course_1_resource",
                        "target_node_ids": ["year_3_course_1"],
                        "resource_type": "文档",
                        "generation_goal": "围绕作品级 Agent 项目闭环生成教学资源",
                        "content_requirements": [
                            "绑定章节大纲",
                            "引用学习者画像",
                            "补充视频和动画",
                        ],
                        "difficulty_level": "中级",
                    }
                ]
            },
        }
    }


def test_target_sections_for_chapter_scope_expands_child_sections() -> None:
    targets = _target_sections_for_scope(_outline(), "1", "chapter_sections")

    assert [section["section_id"] for section in targets] == ["1.1", "1.2", "1.3"]


def test_target_sections_for_chapter_scope_accepts_leaf_section_reference() -> None:
    targets = _target_sections_for_scope(_outline(), "2.1", "chapter_sections")

    assert [section["section_id"] for section in targets] == ["2.1"]


def test_target_sections_for_chapter_scope_accepts_english_chapter_title_reference() -> (
    None
):
    outline = _outline()
    outline["sections"][4]["title"] = "Embedding Generation & Storage"
    targets = _target_sections_for_scope(
        outline,
        "Please generate chapter 2 Embedding Generation & Storage.",
        "chapter_sections",
    )

    assert [section["section_id"] for section in targets] == ["2.1"]


def test_target_sections_default_first_chapter_uses_child_sections_not_parent() -> None:
    targets = _target_sections_for_scope(_outline(), "", "default_first_chapter")

    assert [section["section_id"] for section in targets] == ["1.1", "1.2", "1.3"]


def test_target_sections_rejects_course_scope_generation() -> None:
    with pytest.raises(ValueError, match="一次只能生成一章"):
        _target_sections_for_scope(_outline(), "", "course_sections")


def test_resource_agent_inputs_keep_only_current_chapter_context() -> None:
    outline = _outline()
    outline["section_markdowns"] = {
        "1.1": {
            "section_id": "1.1",
            "parent_section_id": "1",
            "title": "学习目标",
            "markdown": _complete_section_markdown("1.1", "学习目标"),
            "video_briefs": [
                {
                    "video_id": "video_1",
                    "title": "学习目标导入视频",
                    "purpose": "帮助学习者把学习目标落到可验收产出",
                }
            ],
            "animation_briefs": [
                {
                    "animation_id": "anim_1",
                    "title": "学习目标流程动画",
                    "concept": "展示学习目标如何转成任务、资源和检查标准",
                    "visual_elements": ["学习目标", "练习任务", "检查标准"],
                    "motion": "三个节点依次淡入",
                    "space": "正文宽度的 100%，高度 320px。",
                    "placement_hint": "练习任务之后",
                }
            ],
        },
        "2.1": {
            "section_id": "2.1",
            "parent_section_id": "2",
            "title": "学习目标",
            "markdown": "# 接口接入",
            "video_briefs": [],
            "animation_briefs": [],
        },
    }
    year_learning_paths = _year_learning_paths()
    year_learning_paths["year_3"]["resource_generation_contract"][
        "resource_directions"
    ].append(
        {
            "resource_direction_id": "year_3_course_2_resource",
            "target_node_ids": ["year_3_course_2"],
            "resource_type": "文档",
            "generation_goal": "围绕 AI Agent 项目实战生成教学资源",
            "content_requirements": ["绑定第二门课大纲"],
            "difficulty_level": "高级",
        }
    )
    state = {
        "profile": _profile(),
        "year_learning_paths": year_learning_paths,
    }
    section = _section_by_id(outline, "1.1")
    assert section is not None

    queries = [
        _markdown_input(state, outline, section),
        _video_input(state, outline, section),
        _animation_input(state, outline, section),
    ]
    payloads = [_payload_from_query(query) for query in queries]

    for query, payload in zip(queries, payloads, strict=True):
        assert "接口接入" not in query
        assert "第二章：接口接入" not in query
        assert "2.1" not in query
        assert [
            item["section_id"] for item in payload["course_knowledge"]["sections"]
        ] == ["1", "1.2", "1.3"]
        assert payload["course_knowledge"]["learning_sequence"] == ["第一章：需求拆解"]
        assert payload["parent_section"]["section_id"] == "1"
        assert payload["target_section"]["section_id"] == "1.1"
        assert (
            "course_node_id"
            not in payload["year_learning_paths"]["current_learning_course"]
        )
        directions = payload["year_learning_paths"]["resource_generation_contract"][
            "resource_directions"
        ]
        assert [item["resource_direction_id"] for item in directions] == [
            "year_3_course_1_resource"
        ]
        assert "year_3_course_2_resource" not in query

    assert payloads[0]["course_knowledge"]["existing_section_markdowns_ids"] == ["1.1"]
    assert payloads[1]["section_markdowns"].keys() == {"1.1"}


def test_merge_course_resource_data_preserves_outline_fields() -> None:
    outline = _outline()
    merged = _merge_course_resource_data(
        outline,
        "section_markdowns",
        {
            "1.1": {
                "section_id": "1.1",
                "parent_section_id": "1",
                "title": "学习目标",
                "markdown": "# 学习目标",
                "animation_briefs": [],
                "generated_at": "2026-06-06T00:00:00Z",
            }
        },
    )

    assert merged["course_id"] == "year_3_course_1"
    assert merged["sections"] == outline["sections"]
    assert merged["section_markdowns"]["1.1"]["markdown"] == "# 学习目标"


def test_fallback_cover_data_url_is_stable_svg_data_url() -> None:
    value = _fallback_cover_data_url("学习目标")

    assert value.startswith("data:image/svg+xml;utf8,")
    assert "学习目标" in value


def test_video_quality_accepts_exact_bilibili_page_without_title_relevance() -> None:
    outline = {
        "course_id": "year_3_course_1",
        "course_name": "AI 应用基础架构：向量数据库与非结构化数据处理",
        "grade_year": "year_3",
        "sections": [
            {
                "section_id": "1",
                "parent_section_id": None,
                "depth": 1,
                "title": "环境搭建与 Embedding 原理验证",
                "order_index": 1,
                "description": "围绕向量数据库环境搭建与 Embedding 原理验证展开。",
                "key_knowledge_points": ["Embedding 模型的选择与维度映射原理"],
            },
            {
                "section_id": "1.3",
                "parent_section_id": "1",
                "depth": 2,
                "title": "检查点",
                "order_index": 2,
                "description": "确认是否真正掌握环境搭建与 Embedding 原理验证。",
                "key_knowledge_points": [
                    "文本分块粒度与上下文丢失的平衡调试",
                    "提交一个 Python 脚本，输入任意 PDF 文件，输出 Top-3 最相关的文本片段及其相似度分数",
                ],
            },
        ],
    }
    section = _section_by_id(outline, "1.3")

    assert section is not None

    issue = _normalized_video_quality_issue(
        [
            {
                "brief_id": "video_1",
                "title": "我永远也无法达成通过第一个检查点的真实",
                "url": "https://www.bilibili.com/video/BV1LjEP6XEeb",
                "source": "Bilibili",
            }
        ],
        [
            {
                "video_id": "video_1",
                "title": "检查点验证视频",
                "purpose": "帮助学习者确认环境搭建与 Embedding 原理验证的小节检查标准。",
            }
        ],
        section,
        outline,
    )

    assert issue is None


def test_video_quality_accepts_exact_bilibili_page_without_brief_relevance() -> None:
    outline = {
        "course_id": "year_3_course_1",
        "course_name": "AI 应用开发基础能力搭建",
        "grade_year": "year_3",
        "sections": [
            {
                "section_id": "1",
                "parent_section_id": None,
                "depth": 1,
                "title": "需求拆解",
                "order_index": 1,
                "description": "围绕需求拆解推进课程主线。",
                "key_knowledge_points": ["OpenAI-compatible API 调用"],
            },
            {
                "section_id": "1.3",
                "parent_section_id": "1",
                "depth": 2,
                "title": "检查点",
                "order_index": 4,
                "description": "确认需求拆解是否真正学会。",
                "key_knowledge_points": ["异步调用稳定性", "验收标准"],
            },
        ],
    }
    section = _section_by_id(outline, "1.3")

    assert section is not None

    issue = _normalized_video_quality_issue(
        [
            {
                "brief_id": "video_1",
                "title": "AI Agent智能体搭建自动生成测试用例智能体教程，全流程AI驱动软件测试落地方案，轻松掌握必备AI技能",
                "url": "https://www.bilibili.com/video/BV1EtVm6iEzF",
                "source": "Bilibili",
            }
        ],
        [
            {
                "video_id": "video_1",
                "title": "异步编程中的稳定性陷阱与最佳实践",
                "purpose": "通过可视化演示，解释为什么在 AI 应用中使用异步调用至关重要，并直观展示常见错误（如阻塞事件循环）导致的后果，帮助学习者建立正确的异步思维模型。",
            }
        ],
        section,
        outline,
    )

    assert issue is None


def test_video_quality_accepts_exact_youtube_page_without_brief_relevance() -> None:
    outline = {
        "course_id": "year_3_course_1",
        "course_name": "AI 应用开发基础能力搭建",
        "grade_year": "year_3",
        "sections": [
            {
                "section_id": "1",
                "parent_section_id": None,
                "depth": 1,
                "title": "需求拆解",
                "order_index": 1,
                "description": "围绕需求拆解推进课程主线。",
                "key_knowledge_points": ["OpenAI-compatible API 调用"],
            },
            {
                "section_id": "1.1",
                "parent_section_id": "1",
                "depth": 2,
                "title": "学习目标",
                "order_index": 2,
                "description": "明确本节学习目标。",
                "key_knowledge_points": ["需求拆解", "OpenAI-compatible API 调用"],
            },
        ],
    }
    section = _section_by_id(outline, "1.1")

    assert section is not None

    issue = _normalized_video_quality_issue(
        [
            {
                "brief_id": "video_1",
                "title": "OpenAI 调用API Key中转站I如何操作 GPTech API全教程 #雲闪世界 #Gemini",
                "url": "https://www.youtube.com/watch?v=kYNGidyh4jI",
                "source": "YouTube",
            }
        ],
        [
            {
                "video_id": "video_1",
                "title": "OpenAI API 调用全流程演示",
                "purpose": "通过屏幕录制展示从获取 API Key 到成功运行第一行代码的全过程，重点演示环境变量配置和 SDK 初始化，解决初学者在环境搭建阶段的常见痛点。",
            }
        ],
        section,
        outline,
    )

    assert issue is None


def test_video_quality_allows_python_openai_tutorial_when_brief_emphasizes_sdk_setup() -> (
    None
):
    outline = {
        "course_id": "year_3_course_1",
        "course_name": "AI 应用开发基础能力搭建",
        "grade_year": "year_3",
        "sections": [
            {
                "section_id": "1",
                "parent_section_id": None,
                "depth": 1,
                "title": "需求拆解",
                "order_index": 1,
                "description": "围绕需求拆解推进课程主线。",
                "key_knowledge_points": ["OpenAI-compatible API 调用"],
            },
            {
                "section_id": "1.1",
                "parent_section_id": "1",
                "depth": 2,
                "title": "学习目标",
                "order_index": 2,
                "description": "明确本节学习目标。",
                "key_knowledge_points": ["需求拆解", "OpenAI-compatible API 调用"],
            },
        ],
    }
    section = _section_by_id(outline, "1.1")

    assert section is not None

    issue = _normalized_video_quality_issue(
        [
            {
                "brief_id": "video_1",
                "title": "How to Use OpenAI API with Python | 2026 Latest Tutorial",
                "url": "https://www.youtube.com/watch?v=dummy-openai-python",
                "source": "YouTube",
            }
        ],
        [
            {
                "video_id": "video_1",
                "title": "OpenAI API 调用全流程演示",
                "purpose": "通过屏幕录制展示从获取 API Key 到成功运行第一行代码的全过程，重点演示环境变量配置和 SDK 初始化，解决初学者在环境搭建阶段的常见痛点。",
            }
        ],
        section,
        outline,
    )

    assert issue is None


def test_video_quality_allows_asyncio_event_loop_tutorial_for_async_stability_checkpoint() -> (
    None
):
    outline = {
        "course_id": "year_3_course_1",
        "course_name": "AI 应用开发基础能力搭建",
        "grade_year": "year_3",
        "sections": [
            {
                "section_id": "1",
                "parent_section_id": None,
                "depth": 1,
                "title": "需求拆解",
                "order_index": 1,
                "description": "围绕需求拆解推进课程主线。",
                "key_knowledge_points": ["OpenAI-compatible API 调用"],
            },
            {
                "section_id": "1.3",
                "parent_section_id": "1",
                "depth": 2,
                "title": "检查点",
                "order_index": 4,
                "description": "确认需求拆解是否真正学会。",
                "key_knowledge_points": ["异步调用稳定性", "验收标准"],
            },
        ],
    }
    section = _section_by_id(outline, "1.3")

    assert section is not None

    issue = _normalized_video_quality_issue(
        [
            {
                "brief_id": "video_1",
                "title": "Python asyncio: the event loop secret nobody explains",
                "url": "https://www.youtube.com/watch?v=dummy-asyncio-loop",
                "source": "YouTube",
            }
        ],
        [
            {
                "video_id": "video_1",
                "title": "异步编程中的稳定性陷阱与最佳实践",
                "purpose": "通过可视化演示，解释为什么在 AI 应用中使用异步调用至关重要，并直观展示常见错误（如阻塞事件循环）导致的后果，帮助学习者建立正确的异步思维模型。",
            }
        ],
        section,
        outline,
    )

    assert issue is None


def test_video_quality_allows_checkpoint_title_that_strongly_matches_video_brief() -> (
    None
):
    outline = {
        "course_id": "year_3_course_1",
        "course_name": "RAG Core: Embeddings & Vector Search Engine",
        "grade_year": "year_3",
        "sections": [
            {
                "section_id": "1",
                "parent_section_id": None,
                "depth": 1,
                "title": "Data Ingestion & Chunking Strategy",
                "order_index": 1,
                "description": "围绕数据摄取与分块策略展开。",
                "key_knowledge_points": [
                    "Text splitting strategies (recursive character vs semantic)"
                ],
            },
            {
                "section_id": "1.3",
                "parent_section_id": "1",
                "depth": 2,
                "title": "检查点",
                "order_index": 3,
                "description": "确认这一章是否真正学会。",
                "key_knowledge_points": [
                    "Debugging dimension mismatches between query and document embeddings",
                    "A Python script that loads a PDF/Text file, chunks it, generates embeddings, and stores them in a local Vector DB.",
                ],
            },
        ],
    }
    section = _section_by_id(outline, "1.3")

    assert section is not None

    issue = _normalized_video_quality_issue(
        [
            {
                "brief_id": "video_1",
                "title": "RAG 调试实战：维度不匹配错误排查",
                "url": "https://www.bilibili.com/video/BV1abcde1234",
                "source": "Bilibili",
            }
        ],
        [
            {
                "video_id": "video_1",
                "title": "RAG 调试实战：维度不匹配错误排查",
                "purpose": "通过屏幕录制演示，展示当 Query 和 Document 向量维度不一致时，Python 控制台的具体报错信息，并逐步演示如何定位和修复该问题。",
            }
        ],
        section,
        outline,
    )

    assert issue is None


def test_video_quality_allows_similar_topic_title_without_exact_brief_name() -> None:
    outline = _outline()
    outline["course_name"] = "构建本地知识库问答系统 (RAG基础)"
    section = {
        "section_id": "1.2",
        "parent_section_id": "1",
        "depth": 2,
        "title": "语义分块策略设计",
        "order_index": 3,
        "description": "设计适合 RAG 的 chunking 策略。",
        "key_knowledge_points": [
            "文本分块",
            "chunk_size",
            "chunk_overlap",
            "上下文保留",
        ],
    }
    issue = _normalized_video_quality_issue(
        [
            {
                "brief_id": "video_1",
                "title": "RAG 文档切分 Chunking、chunk_size 与 overlap 实战教程",
                "url": "https://www.youtube.com/watch?v=dummy-rag-chunking",
                "cover_url": "",
                "source": "example.com",
            }
        ],
        [
            {
                "video_id": "video_1",
                "title": "语义分块策略设计教学视频",
                "purpose": "帮助学习者理解文本分块参数如何影响检索上下文。",
            }
        ],
        section,
        outline,
    )

    assert issue is None


def test_video_quality_allows_bilibili_search_placeholder_until_metadata_validation(
    monkeypatch,
) -> None:
    outline = {
        "course_id": "year_3_course_1",
        "course_name": "AI 应用基础架构：向量数据库与非结构化数据处理",
        "grade_year": "year_3",
        "sections": [
            {
                "section_id": "1",
                "parent_section_id": None,
                "depth": 1,
                "title": "环境搭建与 Embedding 原理验证",
                "order_index": 1,
                "description": "围绕向量数据库环境搭建与 Embedding 原理验证展开。",
                "key_knowledge_points": ["Embedding 模型的选择与维度映射原理"],
            },
            {
                "section_id": "1.1",
                "parent_section_id": "1",
                "depth": 2,
                "title": "学习目标",
                "order_index": 2,
                "description": "明确环境搭建与 Embedding 原理验证的学习目标。",
                "key_knowledge_points": ["向量数据库", "Embedding", "语义检索"],
            },
        ],
    }
    section = _section_by_id(outline, "1.1")

    assert section is not None

    import app.orchestration.agents.course_resources as module

    async def metadata_ok(_url: str) -> dict:
        return {
            "status": "ok",
            "text": "最强Embedding大模型？Qwen3 Embedding模型部署教程，向量数据库与语义检索实战",
            "title": "最强Embedding大模型？Qwen3 Embedding模型部署教程",
        }

    monkeypatch.setattr(module, "_verify_bilibili_video_metadata", metadata_ok)

    issue = asyncio.run(
        _normalized_video_quality_issue_async(
            [
                {
                    "brief_id": "video_1",
                    "title": "Bilibili 搜索结果 BV1pGM2zgEHM",
                    "url": "https://www.bilibili.com/video/BV1pGM2zgEHM",
                    "cover_url": "",
                    "source": "Bilibili",
                }
            ],
            [
                {
                    "video_id": "video_1",
                    "title": "学习目标导入视频",
                    "purpose": "帮助学习者理解向量数据库、Embedding 与语义检索之间的关系。",
                }
            ],
            section,
            outline,
        )
    )

    assert issue is None


def test_video_quality_accepts_reachable_bilibili_metadata_without_topic_relevance(
    monkeypatch,
) -> None:
    outline = {
        "course_id": "year_3_course_1",
        "course_name": "AI 应用基础架构：向量数据库与非结构化数据处理",
        "grade_year": "year_3",
        "sections": [
            {
                "section_id": "1",
                "parent_section_id": None,
                "depth": 1,
                "title": "环境搭建与 Embedding 原理验证",
                "order_index": 1,
                "description": "围绕向量数据库环境搭建与 Embedding 原理验证展开。",
                "key_knowledge_points": ["Embedding 模型的选择与维度映射原理"],
            },
            {
                "section_id": "1.2",
                "parent_section_id": "1",
                "depth": 2,
                "title": "任务拆解",
                "order_index": 2,
                "description": "把环境搭建与 Embedding 验证拆成可执行任务。",
                "key_knowledge_points": ["向量数据库", "Embedding", "RAG"],
            },
        ],
    }
    section = _section_by_id(outline, "1.2")

    assert section is not None

    import app.orchestration.agents.course_resources as module

    async def metadata_generic_task(_url: str) -> dict:
        return {
            "status": "ok",
            "text": "第二课:做一个日报周报助手，学会任务拆解的底层能力。课程讲任务拆解、输入处理输出。",
            "title": "第二课:做一个日报周报助手，学会任务拆解的底层能力",
        }

    monkeypatch.setattr(
        module, "_verify_bilibili_video_metadata", metadata_generic_task
    )

    issue = asyncio.run(
        _normalized_video_quality_issue_async(
            [
                {
                    "brief_id": "video_1",
                    "title": "Bilibili 搜索结果 BV15YQeBJESB",
                    "url": "https://www.bilibili.com/video/BV15YQeBJESB",
                    "cover_url": "",
                    "source": "Bilibili",
                }
            ],
            [
                {
                    "video_id": "video_1",
                    "title": "RAG 架构全景与 Embedding 在其中的角色",
                    "purpose": "帮助学习者理解环境搭建与 Embedding 验证在 RAG 链路中的位置。",
                }
            ],
            section,
            outline,
        )
    )

    assert issue is None


def test_video_quality_allows_related_rag_chunking_metadata_without_exact_brief_terms(
    monkeypatch,
) -> None:
    outline = {
        "course_id": "year_3_course_1",
        "course_name": "构建本地知识库问答系统 (RAG基础)",
        "grade_year": "year_3",
        "sections": [
            {
                "section_id": "1",
                "parent_section_id": None,
                "depth": 1,
                "title": "非结构化文档解析与智能分块",
                "order_index": 1,
                "description": "围绕 RAG 的文档解析、文本分块与向量化准备展开。",
                "key_knowledge_points": ["PDF 文档解析", "文本分块", "向量化准备"],
            },
            {
                "section_id": "1.1",
                "parent_section_id": "1",
                "depth": 2,
                "title": "文档解析到分块的处理链路",
                "order_index": 2,
                "description": "理解原始文档如何变成可检索片段。",
                "key_knowledge_points": [
                    "非结构化文档解析",
                    "chunk_size",
                    "chunk_overlap",
                ],
            },
        ],
    }
    section = _section_by_id(outline, "1.1")

    assert section is not None

    import app.orchestration.agents.course_resources as module

    async def metadata_related_rag_chunking(_url: str) -> dict:
        return {
            "status": "ok",
            "text": "RAG 本地知识库实战：文档解析、文本切分、chunk_size、overlap 与向量检索完整流程",
            "title": "RAG 本地知识库文档切分与向量检索实战",
        }

    monkeypatch.setattr(
        module, "_verify_bilibili_video_metadata", metadata_related_rag_chunking
    )

    issue = asyncio.run(
        _normalized_video_quality_issue_async(
            [
                {
                    "brief_id": "video_1",
                    "title": "Bilibili 搜索结果 BV1ragchunk1",
                    "url": "https://www.bilibili.com/video/BV1ragchunk1",
                    "cover_url": "",
                    "source": "Bilibili",
                }
            ],
            [
                {
                    "video_id": "video_1",
                    "title": "PDF Loader Splitter Embedder 串联演示",
                    "purpose": "展示 PDF 文件如何流经 Loader、Splitter、Embedder 并进入 Vector DB。",
                }
            ],
            section,
            outline,
        )
    )

    assert issue is None


def test_video_search_queries_compact_dimension_mismatch_checkpoint_terms() -> None:
    outline = {
        "course_id": "year_3_course_1",
        "course_name": "RAG Core: Embeddings & Vector Search Engine",
        "grade_year": "year_3",
        "sections": [
            {
                "section_id": "1",
                "parent_section_id": None,
                "depth": 1,
                "title": "Data Ingestion & Chunking Strategy",
                "order_index": 1,
                "description": "围绕数据摄取与分块策略展开。",
                "key_knowledge_points": [
                    "Text splitting strategies (recursive character vs semantic)"
                ],
            },
            {
                "section_id": "1.3",
                "parent_section_id": "1",
                "depth": 2,
                "title": "检查点",
                "order_index": 3,
                "description": "确认这一章是否真正学会。",
                "key_knowledge_points": [
                    "Debugging dimension mismatches between query and document embeddings",
                    "A Python script that loads a PDF/Text file, chunks it, generates embeddings, and stores them in a local Vector DB.",
                ],
            },
        ],
    }
    section = _section_by_id(outline, "1.3")

    assert section is not None

    queries = _video_search_queries(
        [
            {
                "video_id": "video_1",
                "title": "RAG 调试实战：维度不匹配错误排查",
                "purpose": "通过屏幕录制演示，展示当 Query 和 Document 向量维度不一致时，Python 控制台的具体报错信息（如 ValueError: Dimension mismatch），并逐步演示如何通过打印 shape 和统一模型实例来定位和修复该问题。",
            }
        ],
        section,
        outline,
    )

    assert "RAG embedding dimension mismatch error tutorial" in queries[:3]
    assert "vector dimension mismatch embedding error" in queries
    assert all(
        "A Python script that loads a PDF/Text file, chunks it, generates embeddings, and stores them in a local Vector DB."
        not in query
        for query in queries
    )
    assert all(len(query) <= 120 for query in queries)


def test_video_search_queries_include_pdf_vector_store_focus_for_pipeline_section() -> (
    None
):
    outline = {
        "course_id": "year_3_course_1",
        "course_name": "RAG Core: Embeddings & Vector Search Engine",
        "grade_year": "year_3",
        "sections": [
            {
                "section_id": "1",
                "parent_section_id": None,
                "depth": 1,
                "title": "Data Ingestion & Chunking Strategy",
                "order_index": 1,
                "description": "围绕数据摄取与分块策略展开。",
                "key_knowledge_points": [
                    "Text splitting strategies (recursive character vs semantic)"
                ],
            },
            {
                "section_id": "1.2",
                "parent_section_id": "1",
                "depth": 2,
                "title": "任务拆解",
                "order_index": 2,
                "description": "把这一章拆成任务。",
                "key_knowledge_points": [
                    "Data Ingestion & Chunking Strategy",
                    "Text splitting strategies (recursive character vs semantic)",
                ],
            },
        ],
    }
    section = _section_by_id(outline, "1.2")

    assert section is not None

    queries = _video_search_queries(
        [
            {
                "video_id": "video_1",
                "title": "RAG 数据管道全景图：从 PDF 到 Vector Store",
                "purpose": "视频将动态展示数据从静态文件流经 Loader、Splitter、Embedder 最终进入 Vector DB 的全过程。",
            }
        ],
        section,
        outline,
    )

    assert "RAG PDF to vector store tutorial" in queries[:4]
    assert "RAG loader splitter embedder vector database" in queries


def test_video_search_queries_include_query_function_focus_for_checkpoint_section() -> (
    None
):
    outline = {
        "course_id": "year_3_course_1",
        "course_name": "RAG Core: Embeddings & Vector Search Engine",
        "grade_year": "year_3",
        "sections": [
            {
                "section_id": "2",
                "parent_section_id": None,
                "depth": 1,
                "title": "Embedding Generation & Storage",
                "order_index": 5,
                "description": "围绕 Embedding Generation & Storage 展开。",
                "key_knowledge_points": [
                    "Using HuggingFace/SentenceTransformers for local embeddings"
                ],
            },
            {
                "section_id": "2.3",
                "parent_section_id": "2",
                "depth": 2,
                "title": "检查点",
                "order_index": 8,
                "description": "确认这一章是否真正学会。",
                "key_knowledge_points": [
                    "Handling large files without memory overflow during chunking",
                    "A query function that returns top-3 most similar chunks for a given question string.",
                ],
            },
        ],
    }
    section = _section_by_id(outline, "2.3")

    assert section is not None

    queries = _video_search_queries(
        [
            {
                "video_id": "video_1",
                "title": "RAG 内存优化与检索调试实战演示",
                "purpose": "通过屏幕录制演示如何使用 tracemalloc 检测内存泄漏，以及如何解读向量检索的相似度分数。",
            }
        ],
        section,
        outline,
    )

    assert any("query function" in query.lower() for query in queries)
    assert any("top k chunks" in query.lower() for query in queries)


def test_video_search_queries_prioritize_env_and_sdk_terms_for_openai_setup() -> None:
    outline = {
        "course_id": "year_3_course_1",
        "course_name": "AI 应用开发基础能力搭建",
        "grade_year": "year_3",
        "sections": [
            {
                "section_id": "1",
                "parent_section_id": None,
                "depth": 1,
                "title": "需求拆解",
                "order_index": 1,
                "description": "围绕需求拆解推进课程主线。",
                "key_knowledge_points": ["OpenAI-compatible API 调用"],
            },
            {
                "section_id": "1.1",
                "parent_section_id": "1",
                "depth": 2,
                "title": "学习目标",
                "order_index": 2,
                "description": "明确本节学习目标。",
                "key_knowledge_points": ["需求拆解", "OpenAI-compatible API 调用"],
            },
        ],
    }
    section = _section_by_id(outline, "1.1")

    assert section is not None

    queries = _video_search_queries(
        [
            {
                "video_id": "video_1",
                "title": "OpenAI API 调用全流程演示",
                "purpose": "通过屏幕录制展示从获取 API Key 到成功运行第一行代码的全过程，重点演示环境变量配置和 SDK 初始化，解决初学者在环境搭建阶段的常见痛点。",
            }
        ],
        section,
        outline,
    )

    assert "Python OpenAI 环境变量配置 SDK初始化 教程" in queries
    assert "Python OpenAI API 环境变量 初始化 教程" in queries


def test_video_search_queries_prioritize_asyncio_blocking_terms_for_checkpoint() -> (
    None
):
    outline = {
        "course_id": "year_3_course_1",
        "course_name": "AI 应用开发基础能力搭建",
        "grade_year": "year_3",
        "sections": [
            {
                "section_id": "1",
                "parent_section_id": None,
                "depth": 1,
                "title": "需求拆解",
                "order_index": 1,
                "description": "围绕需求拆解推进课程主线。",
                "key_knowledge_points": ["OpenAI-compatible API 调用"],
            },
            {
                "section_id": "1.3",
                "parent_section_id": "1",
                "depth": 2,
                "title": "检查点",
                "order_index": 4,
                "description": "确认需求拆解是否真正学会。",
                "key_knowledge_points": ["异步调用稳定性", "验收标准"],
            },
        ],
    }
    section = _section_by_id(outline, "1.3")

    assert section is not None

    queries = _video_search_queries(
        [
            {
                "video_id": "video_1",
                "title": "异步编程中的稳定性陷阱与最佳实践",
                "purpose": "通过可视化演示，解释为什么在 AI 应用中使用异步调用至关重要，并直观展示常见错误（如阻塞事件循环）导致的后果，帮助学习者建立正确的异步思维模型。",
            }
        ],
        section,
        outline,
    )

    assert "Python asyncio 阻塞事件循环 最佳实践 教程" in queries
    assert "Python 异步编程 阻塞事件循环 稳定性 教程" in queries


def test_find_verified_video_from_search_uses_first_reachable_video(
    monkeypatch,
) -> None:
    outline = {
        "course_id": "year_3_course_1",
        "course_name": "AI 应用基础架构：向量数据库与非结构化数据处理",
        "grade_year": "year_3",
        "sections": [
            {
                "section_id": "1",
                "parent_section_id": None,
                "depth": 1,
                "title": "环境搭建与 Embedding 原理验证",
                "order_index": 1,
                "description": "围绕向量数据库环境搭建与 Embedding 原理验证展开。",
                "key_knowledge_points": ["Embedding 模型的选择与维度映射原理"],
            },
            {
                "section_id": "1.2",
                "parent_section_id": "1",
                "depth": 2,
                "title": "任务拆解",
                "order_index": 2,
                "description": "把环境搭建与 Embedding 验证拆成可执行任务。",
                "key_knowledge_points": ["向量数据库", "Embedding", "RAG"],
            },
        ],
    }
    section = _section_by_id(outline, "1.2")

    assert section is not None

    briefs = [
        {
            "video_id": "video_1",
            "title": "RAG 架构全景与 Embedding 在其中的角色",
            "purpose": "帮助学习者理解环境搭建与 Embedding 验证在 RAG 链路中的位置。",
        }
    ]

    import app.orchestration.agents.course_resources as module

    async def fake_search(_query: str) -> list[dict]:
        return [
            {
                "title": "Pinecone向量数据库入门 - OpenAI Embedding向量数据存储",
                "url": "https://www.bilibili.com/video/BV1Pinecone1",
                "cover_url": "",
                "source": "Bilibili",
            },
            {
                "title": "RAG 架构全景与 Embedding 在其中的角色 LangChain 教程",
                "url": "https://www.bilibili.com/video/BV1RagGuide2",
                "cover_url": "",
                "source": "Bilibili",
            },
        ]

    async def fake_verify(url: str) -> dict:
        if url == "https://www.bilibili.com/video/BV1Pinecone1":
            return {
                "status": "ok",
                "text": "Pinecone向量数据库入门 OpenAI Embedding 向量数据存储 教程",
                "title": "Pinecone向量数据库入门 - OpenAI Embedding向量数据存储",
            }
        if url == "https://www.bilibili.com/video/BV1RagGuide2":
            return {
                "status": "ok",
                "text": "RAG 架构全景与 Embedding 在其中的角色 LangChain 教程 环境搭建",
                "title": "RAG 架构全景与 Embedding 在其中的角色 LangChain 教程",
            }
        raise AssertionError(f"unexpected url: {url}")

    async def fake_youtube_search(_query: str) -> list[dict]:
        return []

    monkeypatch.setattr(module, "_search_bilibili_video_results", fake_search)
    monkeypatch.setattr(module, "_search_youtube_video_results", fake_youtube_search)
    monkeypatch.setattr(module, "_verify_bilibili_video_metadata", fake_verify)

    verified = asyncio.run(_find_verified_video_from_search(briefs, section, outline))

    assert len(verified) == 1
    assert verified[0]["brief_id"] == "video_1"
    assert verified[0]["url"] == "https://www.bilibili.com/video/BV1Pinecone1"


def test_find_verified_video_from_search_stops_after_first_reachable_video(
    monkeypatch,
) -> None:
    outline = {
        "course_id": "year_3_course_1",
        "course_name": "AI 应用基础架构：向量数据库与非结构化数据处理",
        "grade_year": "year_3",
        "sections": [
            {
                "section_id": "1",
                "parent_section_id": None,
                "depth": 1,
                "title": "环境搭建与 Embedding 原理验证",
                "order_index": 1,
                "description": "围绕向量数据库环境搭建与 Embedding 原理验证展开。",
                "key_knowledge_points": ["Embedding 模型的选择与维度映射原理"],
            },
            {
                "section_id": "1.2",
                "parent_section_id": "1",
                "depth": 2,
                "title": "任务拆解",
                "order_index": 2,
                "description": "把环境搭建与 Embedding 验证拆成可执行任务。",
                "key_knowledge_points": ["向量数据库", "Embedding", "RAG"],
            },
        ],
    }
    section = _section_by_id(outline, "1.2")

    assert section is not None

    briefs = [
        {
            "video_id": "video_1",
            "title": "RAG 架构全景与 Embedding 在其中的角色",
            "purpose": "帮助学习者理解环境搭建与 Embedding 验证在 RAG 链路中的位置。",
        }
    ]

    import app.orchestration.agents.course_resources as module

    queries_seen: list[str] = []

    async def fake_search(query: str) -> list[dict]:
        queries_seen.append(query)
        if len(queries_seen) == 1:
            return [
                {
                    "title": "Pinecone向量数据库入门 - OpenAI Embedding向量数据存储",
                    "url": "https://www.bilibili.com/video/BV1Pinecone1",
                    "cover_url": "",
                    "source": "Bilibili",
                }
            ]
        return [
            {
                "title": "15分钟弄懂Token和Embedding -- 详解LLM与RAG的数据处理机制",
                "url": "https://www.bilibili.com/video/BV1TokenEmb2",
                "cover_url": "",
                "source": "Bilibili",
            }
        ]

    async def fake_verify(url: str) -> dict:
        if url == "https://www.bilibili.com/video/BV1Pinecone1":
            return {
                "status": "ok",
                "text": "Pinecone向量数据库入门 OpenAI Embedding 向量数据存储 教程",
                "title": "Pinecone向量数据库入门 - OpenAI Embedding向量数据存储",
            }
        if url == "https://www.bilibili.com/video/BV1TokenEmb2":
            return {
                "status": "ok",
                "text": "15分钟弄懂Token和Embedding 详解LLM与RAG的数据处理机制 环境搭建",
                "title": "15分钟弄懂Token和Embedding -- 详解LLM与RAG的数据处理机制",
            }
        raise AssertionError(f"unexpected url: {url}")

    async def fake_youtube_search(_query: str) -> list[dict]:
        return []

    monkeypatch.setattr(module, "_search_bilibili_video_results", fake_search)
    monkeypatch.setattr(module, "_search_youtube_video_results", fake_youtube_search)
    monkeypatch.setattr(module, "_verify_bilibili_video_metadata", fake_verify)

    verified = asyncio.run(_find_verified_video_from_search(briefs, section, outline))

    assert len(queries_seen) == 1
    assert len(verified) == 1
    assert verified[0]["url"] == "https://www.bilibili.com/video/BV1Pinecone1"


def test_find_verified_video_from_search_does_not_score_reachable_results(
    monkeypatch,
) -> None:
    outline = {
        "course_id": "year_3_course_1",
        "course_name": "RAG Core: Embeddings & Vector Search Engine",
        "grade_year": "year_3",
        "sections": [
            {
                "section_id": "1",
                "parent_section_id": None,
                "depth": 1,
                "title": "Data Ingestion & Chunking Strategy",
                "order_index": 1,
                "description": "围绕数据摄取与分块策略展开。",
                "key_knowledge_points": [
                    "Text splitting strategies (recursive character vs semantic)"
                ],
            },
            {
                "section_id": "1.3",
                "parent_section_id": "1",
                "depth": 2,
                "title": "检查点",
                "order_index": 3,
                "description": "确认这一章是否真正学会。",
                "key_knowledge_points": [
                    "Debugging dimension mismatches between query and document embeddings",
                    "A Python script that loads a PDF/Text file, chunks it, generates embeddings, and stores them in a local Vector DB.",
                ],
            },
        ],
    }
    section = _section_by_id(outline, "1.3")

    assert section is not None

    briefs = [
        {
            "video_id": "video_1",
            "title": "RAG 调试实战：维度不匹配错误排查",
            "purpose": "通过屏幕录制演示，展示当 Query 和 Document 向量维度不一致时，Python 控制台的具体报错信息（如 ValueError: Dimension mismatch），并逐步演示如何通过打印 shape 和统一模型实例来定位和修复该问题。",
        }
    ]

    import app.orchestration.agents.course_resources as module

    async def fake_search(_query: str) -> list[dict]:
        return [
            {
                "title": "Qwen3 Embedding 模型详解：文本嵌入与重排序性能全面超越SOTA",
                "url": "https://www.bilibili.com/video/BV1generic12",
                "cover_url": "",
                "source": "Bilibili",
            },
            {
                "title": "RAG 调试实战：维度不匹配错误排查",
                "url": "https://www.bilibili.com/video/BV1abcde1234",
                "cover_url": "",
                "source": "Bilibili",
            },
        ]

    async def fake_verify(url: str) -> dict:
        if url == "https://www.bilibili.com/video/BV1generic12":
            return {
                "status": "ok",
                "text": "Qwen3 Embedding 模型详解 文本嵌入 重排序 检索增强生成 大模型RAG 通义千问",
                "title": "Qwen3 Embedding 模型详解：文本嵌入与重排序性能全面超越SOTA",
            }
        if url == "https://www.bilibili.com/video/BV1abcde1234":
            return {
                "status": "ok",
                "text": "RAG 调试实战 维度不匹配 错误排查 Query Document Embedding shape ValueError Dimension mismatch",
                "title": "RAG 调试实战：维度不匹配错误排查",
            }
        raise AssertionError(f"unexpected url: {url}")

    async def fake_youtube_search(_query: str) -> list[dict]:
        return []

    monkeypatch.setattr(module, "_search_bilibili_video_results", fake_search)
    monkeypatch.setattr(module, "_search_youtube_video_results", fake_youtube_search)
    monkeypatch.setattr(module, "_verify_bilibili_video_metadata", fake_verify)

    verified = asyncio.run(_find_verified_video_from_search(briefs, section, outline))

    assert len(verified) == 1
    assert verified[0]["url"] == "https://www.bilibili.com/video/BV1generic12"


def test_find_verified_video_from_search_uses_youtube_when_bilibili_has_no_verified_match(
    monkeypatch,
) -> None:
    outline = {
        "course_id": "year_3_course_1",
        "course_name": "RAG Core: Embeddings & Vector Search Engine",
        "grade_year": "year_3",
        "sections": [
            {
                "section_id": "1",
                "parent_section_id": None,
                "depth": 1,
                "title": "Data Ingestion & Chunking Strategy",
                "order_index": 1,
                "description": "围绕数据摄取与分块策略展开。",
                "key_knowledge_points": [
                    "Text splitting strategies (recursive character vs semantic)"
                ],
            },
            {
                "section_id": "1.3",
                "parent_section_id": "1",
                "depth": 2,
                "title": "检查点",
                "order_index": 3,
                "description": "确认这一章是否真正学会。",
                "key_knowledge_points": [
                    "Debugging dimension mismatches between query and document embeddings",
                    "A Python script that loads a PDF/Text file, chunks it, generates embeddings, and stores them in a local Vector DB.",
                ],
            },
        ],
    }
    section = _section_by_id(outline, "1.3")

    assert section is not None

    briefs = [
        {
            "video_id": "video_1",
            "title": "RAG 调试实战：维度不匹配错误排查",
            "purpose": "通过屏幕录制演示，展示当 Query 和 Document 向量维度不一致时，Python 控制台的具体报错信息（如 ValueError: Dimension mismatch），并逐步演示如何通过打印 shape 和统一模型实例来定位和修复该问题。",
        }
    ]

    import app.orchestration.agents.course_resources as module

    async def fake_bilibili_search(_query: str) -> list[dict]:
        return []

    async def fake_youtube_search(_query: str) -> list[dict]:
        return [
            {
                "title": "How to solve n8n Supabase Vector Dimensions Embedding error",
                "url": "https://www.youtube.com/watch?v=w6HDiP5eHt0",
                "cover_url": "",
                "source": "YouTube",
            }
        ]

    monkeypatch.setattr(module, "_search_bilibili_video_results", fake_bilibili_search)
    monkeypatch.setattr(module, "_search_youtube_video_results", fake_youtube_search)

    verified = asyncio.run(_find_verified_video_from_search(briefs, section, outline))

    assert len(verified) == 1
    assert verified[0]["url"] == "https://www.youtube.com/watch?v=w6HDiP5eHt0"


import asyncio

from sqlmodel import Session

from app.database import build_engine, init_db, set_engine
from app.models import User, UserCourseKnowledgeOutline
from app.orchestration.agents.course_resources import run_section_markdown_agent
from app.orchestration.agents.models import (
    SectionHtmlAnimationOutput,
    SectionMarkdownOutput,
    SectionVideoSearchOutput,
)


def _payload_from_query(query: str) -> dict:
    return json.loads(query.split("输入：", 1)[1])


def _valid_markdown_video_briefs(title: str = "学习目标") -> list[dict]:
    return [
        {
            "video_id": "video_1",
            "title": f"{title}专项讲解视频",
            "target_markdown_heading": "核心概念",
            "target_paragraph_summary": f"解释「{title}」的核心概念如何服务练习任务。",
            "search_terms": [title, "核心概念", "练习任务"],
            "purpose": f"帮助学习者围绕「{title}」理解核心概念，并把本节内容落到可验收任务。",
        }
    ]


def _linked_list_animation_brief() -> dict:
    return {
        "animation_id": "anim_1",
        "title": "单链表节点指针串联动画",
        "target_markdown_heading": "步骤讲解",
        "target_paragraph_summary": "解释节点、next 指针和 None 终点。",
        "concept": "单链表的节点与指针关系",
        "simulation_type": "data_structure_linked_list",
        "visual_elements": ["头指针", "节点(data,next)", "next 指针", "尾节点 None"],
        "visual_model": {
            "entities": [
                {"id": "head", "kind": "pointer", "label": "head"},
                {"id": "node_1", "kind": "node", "fields": ["data", "next"]},
                {"id": "node_2", "kind": "node", "fields": ["data", "next"]},
                {"id": "none", "kind": "terminal", "label": "None"},
            ],
            "relations": [
                {"from": "head", "to": "node_1", "kind": "points_to"},
                {"from": "node_1.next", "to": "node_2", "kind": "points_to"},
                {"from": "node_2.next", "to": "none", "kind": "points_to"},
            ],
        },
        "timeline": [
            {"step": 1, "action": "show_entity", "target": "head"},
            {"step": 2, "action": "show_entity", "target": "node_1"},
            {"step": 3, "action": "connect", "from": "head", "to": "node_1"},
        ],
        "layout": "横向链式结构",
        "motion": "节点通过 transform 进入，指针线通过 opacity 出现。",
        "interaction": "点击步骤按钮切换。",
        "success_check": [
            "DOM 中包含头指针",
            "DOM 中包含 next 指针",
            "DOM 中包含 None",
        ],
        "placement_hint": "步骤讲解之后",
    }


def _complete_section_markdown(
    section_id: str, title: str, video_id: str = "video_1", animation_id: str = "anim_1"
) -> str:
    return "\n\n".join(
        [
            f"# {section_id} {title}",
            (
                f"## 学习目标\n本节围绕「{title}」展开，先把目标拆成可检查的学习结果。"
                "学习者需要说明输入材料、输出产物、视频资源、HTML 动画和最终验收方式，"
                "并把这些产出连接到作品级 Agent 项目闭环。"
            ),
            (
                "## 核心概念\n"
                "### 需求拆解\n定义：需求拆解是把一句模糊目标转成输入、处理、输出和验收标准。"
                "为什么重要：如果不先拆解，后续 OpenAI-compatible API 调用和页面展示都会缺少边界。"
                "怎么用：先记录用户原话，再标出名词、动作、约束和成功条件。"
                "示例：把“做一个学习助手”拆成输入=学习问题，处理=读取课程上下文并调用模型，输出=结构化建议，验收=建议包含下一步任务。"
                "常见误区：直接写提示词，跳过不做范围和异常情况。"
                "验收方式：同伴只看拆解表，就能判断第一版功能范围。\n\n"
                "### 任务拆分\n定义：任务拆分是把一个小节目标切成若干可以顺序执行的小动作。"
                "为什么重要：它让学习者知道先读什么、写什么、检查什么，而不是只看到一个大标题。"
                "怎么用：把目标拆成读取上下文、整理表格、生成资源 brief、复查保存四步。"
                "示例：当前小节先确认学习目标，再写任务卡，再绑定视频和动画，最后检查可验收标准。"
                "边界：任务拆分不是把所有章节一起生成，而是只处理当前章节里的具体小节内容。"
                "验收方式：每个任务都有独立产出物，并能被截图、表格或运行结果验证。\n\n"
                "### 功能边界\n定义：功能边界说明第一版必须完成什么、暂时不做什么，以及为什么这样取舍。"
                "为什么重要：没有边界，学习内容会不断膨胀，Markdown、视频和 HTML 动画也会变成互不相干的材料。"
                "怎么用：先写用户真实目标，再把输入、处理、输出和不做范围分开。"
                "示例：当前小节只生成教学内容和资源 brief，不处理后续章节、不写整门课正文。"
                "常见误区：把愿景当边界，例如只写“生成高质量内容”，却没有说明可验收产物。"
                "验收方式：同伴只看边界说明，就能判断某个需求是否进入本节。\n\n"
                "### OpenAI-compatible API 调用\n定义：按兼容 OpenAI 的协议组织 model、messages、temperature 和输出格式约束。"
                "为什么重要：它把拆解后的处理步骤接到真实模型能力上。"
                "怎么用：system message 写角色和边界，user message 写本次输入，输出格式写成 JSON 或清晰字段。"
                "示例：生成练习题时，system 只允许输出题目，user 提供 level、topic 和 format。"
                "边界：API 调用不能替代需求拆解，它只能验证拆解是否可执行。"
                "验收方式：能解释每个字段为什么存在，并能处理超时、429、空响应。\n\n"
                "### 验收标准\n定义：验收标准是可以观察、可以复查的完成判断，而不是主观感受。"
                "为什么重要：它让项目驱动学习能留下运行结果、截图、表格或口头解释等证据。"
                "怎么用：把每个输出写成可检查句，例如 Markdown 有完整概念解释、视频 URL 可打开、动画有可见节点。"
                "示例：本节产出必须包含任务卡、资源 brief、视频链接和可渲染动画。"
                "边界：验收标准不是泛泛评价，它必须能指导测试或人工复查。"
                "误区：只写“内容完整”“体验好”，没有可观察证据。\n\n"
                "### 资源绑定\n定义：资源绑定要求 Markdown、视频和 HTML 动画服务同一个小节目标。"
                "为什么重要：否则页面看起来有资源，实际教学主线却断开。"
                "怎么用：正文里的 video:id 与 animation:id 必须完全对应 brief。"
                "示例：学习目标小节的视频讲目标和边界，动画展示目标如何转成检查标准。"
                "注意事项：资源不是装饰，必须能帮助学习者理解或练习。"
            ),
            (
                "## 步骤讲解\n"
                "第一步：读取基础画像、学习路径和章节大纲。输入材料是用户年级、学习偏好、课程目标和当前章节；"
                "具体动作是确认本小节在第一章中的作用；判断依据是目标能否落到一个可交付产物；"
                "输出是一句可验收学习目标。\n\n"
                "第二步：把小节目标改写成任务卡。输入材料是小节标题和关键知识点；"
                "具体动作是明确用户输入、后端处理、模型输出和前端呈现；判断依据是每一栏是否能被代码或页面验证；"
                "输出是一张输入、处理、输出、完成标准表。\n\n"
                "第三步：写出资源 brief。输入材料是任务卡；具体动作是分别说明视频要解决的理解问题、动画要展示的流程节点；"
                "判断依据是 brief 是否能指导下游 agent 生成非占位资源；输出是 video_briefs 和 animation_briefs。\n\n"
                "第四步：拼装并复查。输入材料是 Markdown、视频和动画；具体动作是替换占位符并检查页面块顺序；"
                "判断依据是资源能打开、动画能渲染、检查标准能执行；输出是可保存的 composed markdown。\n\n"
                "| 步骤 | 输入材料 | 产出物 | 验收方式 |\n"
                "| --- | --- | --- | --- |\n"
                "| 目标收敛 | 画像、学习路径、章节大纲 | 一句可验收学习目标 | 同伴能复述本节交付物 |\n"
                "| 任务拆解 | 小节标题和关键知识点 | 输入/处理/输出/验收表 | 每一栏都能被代码或页面验证 |\n"
                "| 资源绑定 | 任务卡和正文重点 | video_briefs、animation_briefs | 占位符 ID 与 brief 完全一致 |"
            ),
            f"<!-- video:id={video_id} -->",
            (
                "## 练习任务\n请在 10 到 15 分钟内完成一张小节任务卡。任务卡必须包含："
                "输入是什么、输出是什么、完成标准是什么、最容易卡住的问题是什么。"
                "如果本节用于生成教学资源，还要写明 Markdown、视频和 HTML 动画分别引用哪些上下文，"
                "以及如何判断它们不是通用占位内容。提交物是一张 markdown 表格或页面截图，"
                "完成标准是同伴只看这张卡就能复述本节要交付什么。"
            ),
            f"<!-- animation:id={animation_id} -->",
            (
                "## 检查标准\n"
                "- [ ] 能用自己的话解释本节目标，并能列出至少两个关键知识点。\n"
                "- [ ] 能给出一个可验收的小产出，例如任务卡、接口调用清单、资源 brief 或渲染截图。\n"
                "- [ ] 能说明视频与动画分别承担什么教学作用，并确认它们与正文占位符一致。\n"
                "- [ ] 能识别低质量内容，例如重复标题、泛泛概念、不可用资源提示或没有绑定学习者画像的说明。\n"
                "- [ ] 能通过运行结果、截图、表格或口头解释证明本节产出可复查。"
            ),
            (f"## 来源\n- 《AI 应用开发项目教程》：{section_id} {title}。"),
            (
                "补充说明：这段测试内容故意写成完整教学文档，用来穿过生产质量门。"
                "如果模型输出太短、缺少必备标题、带旧兜底文案或资源占位符与 brief 不一致，"
                "后端必须拒绝保存并要求重新生成，而不是用本地模板补齐。"
            ),
        ]
    )


def test_markdown_input_requires_full_resource_brief_contract(tmp_path) -> None:
    from sqlmodel import Session

    from app.database import build_engine, init_db, set_engine
    from app.models import User
    from tests.fixtures.knowledge_base import enabled_source, published_textbook
    from tests.fixtures.knowledge_base import section as k_section

    engine = build_engine(postgresql_test_url(tmp_path, "markdown-input-brief-spec"))
    set_engine(engine)
    init_db(engine)
    with Session(engine) as session:
        session.add(
            User(uid="user-1", username="课程用户", identifier="course@example.com")
        )
        session.add(enabled_source(source_id="source-data-structures"))
        textbook = published_textbook(
            textbook_id="textbook-data-structures",
            source_id="source-data-structures",
            title="数据结构教程",
        )
        textbook.outline = {"sections": [{"section_id": "2.3", "title": "单链表"}]}
        session.add(textbook)
        session.add(
            k_section(
                textbook_id="textbook-data-structures",
                section_content_id="linked-list-2-3",
                section_id="2.3",
                title="单链表",
                content_zh="单链表节点包含 data 和 next，next 指向下一个节点，尾节点指向 None。",
                order_index=1,
            )
        )
        session.commit()

    outline = _outline()
    outline["sections"][1].update(
        {
            "source_textbook_id": "textbook-data-structures",
            "source_textbook_title": "数据结构教程",
            "source_section_ids": ["2.3"],
            "source_section_titles": ["单链表"],
            "source_content_chars": 42,
        }
    )
    section = _section_by_id(outline, "1.1")
    assert section is not None

    payload = _markdown_input(
        {"profile": _profile(), "year_learning_paths": _year_learning_paths()},
        outline,
        section,
    )

    assert "source_references" in payload
    assert "target_paragraph_summary" in payload
    assert "visual_model.entities" in payload
    assert "visual_model.relations" in payload
    assert "timeline" in payload
    assert "success_check" in payload
    assert "完整施工图" in payload
    assert "文字说明动画" in payload
    assert '"prompt_budget_applied"' in payload


def test_markdown_quality_rejects_preview_or_prep_document_wording() -> None:
    markdown = _complete_section_markdown("1.1", "单链表").replace(
        "## 学习目标",
        "## 学习目标\n本节是课前预览材料，帮助你先浏览链表内容。\n\n## 学习目标",
        1,
    )

    issue = _markdown_quality_issue(
        markdown,
        {
            "section_id": "1.1",
            "title": "单链表",
            "description": "讲解节点通过指针串联的线性结构。",
            "key_knowledge_points": ["节点", "指针", "None"],
            "source_textbook_id": "textbook-data-structures",
            "source_textbook_title": "数据结构教程",
            "source_section_ids": ["2.3"],
            "source_section_titles": ["单链表"],
        },
        _valid_markdown_video_briefs("单链表"),
        [_linked_list_animation_brief()],
    )

    assert issue == "Markdown 必须是教学文档，不得写成预习或导读材料。"


def test_animation_input_tells_agent_to_implement_visual_model_not_explain_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    outline = _outline()
    outline["sections"][1].update(
        {
            "source_textbook_id": "textbook-data-structures",
            "source_textbook_title": "数据结构教程",
            "source_section_ids": ["2.3"],
            "source_section_titles": ["单链表"],
            "source_content_chars": 842,
        }
    )
    outline["section_markdowns"] = {
        "1.1": {
            "section_id": "1.1",
            "parent_section_id": "1",
            "title": "单链表",
            "markdown": _complete_section_markdown("1.1", "单链表"),
            "source_references": [
                {
                    "textbook_id": "textbook-data-structures",
                    "textbook_title": "数据结构教程",
                    "section_id": "2.3",
                    "section_title": "单链表",
                    "evidence_summary": "依据链表教材内容生成。",
                    "content_char_count": 842,
                }
            ],
            "video_briefs": _valid_markdown_video_briefs("单链表"),
            "animation_briefs": [_linked_list_animation_brief()],
        }
    }
    section = _section_by_id(outline, "1.1")
    assert section is not None
    monkeypatch.setattr(
        "app.orchestration.agents.course_resources.common._textbook_evidence_pack",
        lambda _outline, _section: {
            "textbook_id": "textbook-data-structures",
            "title": "数据结构教程",
            "sections": [
                {
                    "section_id": "2.3",
                    "title": "单链表",
                    "content": "单链表通过节点和指针关系组织数据。",
                }
            ],
            "total_chars": 842,
            "evidence_text": "单链表通过节点和指针关系组织数据。",
        },
    )

    video_query = _video_input({"profile": _profile()}, outline, section)
    query = _animation_input({"profile": _profile()}, outline, section)

    assert "visual_model.entities" in query
    assert "visual_model.relations" in query
    assert "timeline" in query
    assert "禁止做成文字卡片轮播" in query
    assert '"prompt_budget_applied"' in video_query
    assert '"prompt_budget_applied"' in query
    assert "textbook_evidence_pack" not in video_query
    assert "textbook-data-structures" in query


def test_animation_quality_rejects_text_only_html_for_linked_list() -> None:
    issue = _normalized_animation_quality_issue(
        [
            {
                "animation_id": "anim_1",
                "html": '<!doctype html><html><head><meta charset="utf-8"></head><body><section class="section-animation"><style>@media (prefers-reduced-motion: reduce){.section-animation *{opacity: 1 !important;transform: none !important;}}</style><div class="animation-context">单链表说明</div><p>节点通过指针连接。</p></section></body></html>',
            }
        ],
        [_linked_list_animation_brief()],
        {"title": "单链表"},
    )

    assert issue == "动画 HTML 未实现 visual_model.entities。"


def test_animation_quality_accepts_linked_list_simulation_html() -> None:
    html = """<!doctype html><html><head><meta charset="utf-8"></head><body>
    <section class="section-animation">
    <style>
    :root{--line:oklch(70% 0.1 240);}
    @media (prefers-reduced-motion: reduce){.section-animation *{opacity: 1 !important;transform: none !important;}}
    </style>
    <div class="animation-context">单链表节点通过 next 指针串联，尾节点指向 None。</div>
    <svg data-timeline="linked-list">
      <g data-entity-id="head"><text>head 头指针</text></g>
      <g data-entity-id="node_1"><text>data</text><text>next</text></g>
      <g data-entity-id="node_2"><text>data</text><text>next</text></g>
      <g data-entity-id="none"><text>None</text></g>
      <line data-relation-from="head" data-relation-to="node_1"></line>
      <line data-relation-from="node_1.next" data-relation-to="node_2"></line>
      <line data-relation-from="node_2.next" data-relation-to="none"></line>
    </svg>
    <button data-step="1">1</button><button data-step="2">2</button><button data-step="3">3</button>
    </section></body></html>"""

    issue = _normalized_animation_quality_issue(
        [{"animation_id": "anim_1", "html": html}],
        [_linked_list_animation_brief()],
        {"title": "单链表"},
    )

    assert issue is None


def _animation_structure_html(body: str) -> str:
    return (
        '<!doctype html><html><head><meta charset="utf-8"></head><body>'
        '<section class="section-animation">'
        "<style>@media (prefers-reduced-motion: reduce){.section-animation *{"
        "opacity: 1 !important;transform: none !important;}}</style>"
        f'<div class="animation-context">单链表结构动画</div>{body}'
        "</section></body></html>"
    )


@pytest.mark.parametrize(
    ("body", "expected_issue"),
    [
        (
            '<div data-entity-id="head">head</div>'
            '<div data-entity-id="node_1">data next</div>'
            '<div data-entity-id="none">None</div>',
            "动画 HTML 未实现 visual_model.entities。",
        ),
        (
            '<div data-entity-id="head">head</div>'
            '<div data-entity-id="node_1">data next</div>'
            '<div data-entity-id="node_2">data next</div>'
            '<div data-entity-id="none">None</div>',
            "动画 HTML 未实现 visual_model.relations。",
        ),
        (
            '<div data-entity-id="head">head</div>'
            '<div data-entity-id="node_1">data next node_1.next</div>'
            '<div data-entity-id="node_2">data next node_2.next</div>'
            '<div data-entity-id="none">None</div>'
            '<svg><line data-relation-from="head" data-relation-to="node_1"></line>'
            '<line data-relation-from="node_1.next" data-relation-to="node_2"></line>'
            '<line data-relation-from="node_2.next" data-relation-to="none"></line></svg>',
            "动画 HTML 未实现 timeline 或步骤状态。",
        ),
    ],
)
def test_animation_structure_quality_gate_rejects_missing_visual_parts(
    body: str, expected_issue: str
) -> None:
    issue = _normalized_animation_quality_issue(
        [
            {
                "animation_id": "anim_1",
                "html": _animation_structure_html(body),
            }
        ],
        [_linked_list_animation_brief()],
        {"title": "单链表"},
    )

    assert issue == expected_issue


def test_normalize_animation_html_rejects_encoded_color_text() -> None:
    html_text = (
        '<section class="section-animation">'
        "<div>&oklch(72% 0.08 240); 主题</div>"
        "</section>"
    )

    normalized = animation_module._normalize_animation_html(
        html_text, _linked_list_animation_brief()
    )

    assert normalized == ""


def _run_animation_agent_with_model_html(
    monkeypatch: pytest.MonkeyPatch,
    model_html: str,
    deterministic_data: list[dict] | None = None,
) -> dict:
    class RecordingLlm:
        pass

    class AnimationChain:
        async def ainvoke(self, _payload):
            return SectionHtmlAnimationOutput(
                section_id="1.1",
                animations=[
                    {
                        "animation_id": "anim_1",
                        "title": "单链表节点指针串联动画",
                        "html": model_html,
                    }
                ],
            )

    class AnimationPrompt:
        def __or__(self, _other):
            return AnimationChain()

    class PromptFactory:
        @staticmethod
        def from_messages(_messages):
            return AnimationPrompt()

    import app.orchestration.agents.course_resources as course_resources_module

    outline = _outline()
    outline["sections"][1].update(
        {
            "title": "单链表",
            "description": "说明节点通过指针串联的线性结构。",
            "key_knowledge_points": ["节点", "next 指针", "None"],
        }
    )
    brief = _linked_list_animation_brief()
    outline["section_markdowns"] = {
        "1.1": {
            "section_id": "1.1",
            "parent_section_id": "1",
            "title": "单链表",
            "markdown": "# 单链表\n\n完整教学内容",
            "video_briefs": [],
            "animation_briefs": [brief],
        }
    }
    monkeypatch.setattr(course_resources_module, "ChatPromptTemplate", PromptFactory)
    monkeypatch.setattr(animation_module, "_persist_outline", lambda *_args: None)
    if deterministic_data is not None:
        monkeypatch.setattr(
            animation_module,
            "_deterministic_animation_data",
            lambda *_args: deterministic_data,
        )

    return asyncio.run(
        animation_module.run_section_html_animation_agent(
            {
                "user_id": "user-1",
                "course_knowledge": outline,
                "profile": _profile(),
                "year_learning_paths": _year_learning_paths(),
                "course_resource_plan": {
                    "course_id": "year_3_course_1",
                    "target_section_ids": ["1.1"],
                },
                "messages": [],
            },
            RecordingLlm(),
        )
    )


def test_run_animation_agent_rebuilds_deterministic_structure_after_bad_model_html(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model_html = _animation_structure_html(
        "<p>&oklch(72% 0.08 240); 模型只返回文字。</p>"
    )

    result = _run_animation_agent_with_model_html(monkeypatch, model_html)

    animations = result["course_knowledge"]["section_html_animations"]["1.1"][
        "animations"
    ]
    html = animations[0]["html"]
    assert 'data-entity-id="head"' in html
    assert 'data-relation="true"' in html
    assert "<line" in html
    assert "data-timeline=" in html
    assert "prefers-reduced-motion" in html
    assert "单链表" in html
    assert "&oklch" not in html
    assert (
        _normalized_animation_quality_issue(
            animations, [_linked_list_animation_brief()], {"title": "单链表"}
        )
        is None
    )


def test_run_animation_agent_keeps_failure_when_deterministic_rebuild_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model_html = _animation_structure_html("<p>模型只返回文字。</p>")
    invalid_deterministic_data = [
        {
            "animation_id": "anim_1",
            "title": "单链表节点指针串联动画",
            "html": _animation_structure_html("<p>确定性构造仍缺少结构。</p>"),
        }
    ]

    result = _run_animation_agent_with_model_html(
        monkeypatch, model_html, invalid_deterministic_data
    )

    assert result == {
        "error": "课程资源生成失败：HTML 动画未生成，请稍后重试。",
        "hard_error": True,
    }


def test_plain_text_markdown_parse_keeps_rich_resource_brief_schema() -> None:
    section = {
        "section_id": "1.1",
        "parent_section_id": "1",
        "title": "单链表",
        "description": "讲解节点通过指针串联的线性结构。",
        "key_knowledge_points": ["节点", "next 指针", "None"],
        "source_textbook_id": "textbook-data-structures",
        "source_textbook_title": "数据结构教程",
        "source_section_ids": ["2.3"],
        "source_section_titles": ["单链表"],
        "source_content_chars": 42,
    }
    markdown = _complete_section_markdown("1.1", "单链表")
    data = _section_markdown_data_from_plain_text(
        markdown,
        "输入：" + json.dumps({"target_section": section}, ensure_ascii=False),
    )

    assert data["source_references"][0]["textbook_id"] == "textbook-data-structures"
    assert data["video_briefs"][0]["target_paragraph_summary"]
    assert len(data["video_briefs"][0]["search_terms"]) >= 3
    assert (
        data["animation_briefs"][0]["simulation_type"] == "data_structure_linked_list"
    )
    assert data["animation_briefs"][0]["visual_model"]["entities"]
    assert data["animation_briefs"][0]["timeline"]


def test_resource_prompt_budget_slims_payload_without_breaking_json() -> None:
    payload = {
        "textbook_evidence_pack": {
            "textbook_id": "textbook-data-structures",
            "sections": [
                {
                    "section_id": "2.3",
                    "title": "单链表",
                    "evidence_text": "B" * 10000,
                }
            ],
            "evidence_text": "A" * 40000,
        },
        "target_section": {
            "source_textbook_id": "textbook-data-structures",
            "source_section_ids": ["2.3"],
        },
    }

    query = _resource_query_with_prompt_budget(
        "请生成 Markdown JSON。",
        payload,
        phase="markdown",
        protected_fragments=["textbook-data-structures", "2.3"],
    )
    raw_payload = query.partition("输入：")[2]
    parsed_payload = json.loads(raw_payload)

    assert parsed_payload["prompt_budget_applied"] is True
    assert parsed_payload["textbook_evidence_pack"]["textbook_id"] == (
        "textbook-data-structures"
    )
    assert parsed_payload["textbook_evidence_pack"]["sections"][0]["section_id"] == (
        "2.3"
    )
    assert "已按 prompt budget 精简" in query
    assert len(query) <= 28000


def _complete_section_markdown_from_bodies(
    section_id: str,
    title: str,
    section_bodies: dict[str, str],
    video_id: str = "video_1",
    animation_id: str = "anim_1",
) -> str:
    return "\n\n".join(
        [
            f"# {section_id} {title}",
            f"## 学习目标\n{section_bodies['学习目标']}",
            f"## 核心概念\n{section_bodies['核心概念']}",
            f"## 步骤讲解\n{section_bodies['步骤讲解']}",
            f"<!-- video:id={video_id} -->",
            f"## 练习任务\n{section_bodies['练习任务']}",
            f"<!-- animation:id={animation_id} -->",
            f"## 检查标准\n{section_bodies['检查标准']}",
        ]
    )


def test_data_structure_course_outline_and_markdown_use_bound_textbook_evidence(
    tmp_path: Path,
) -> None:
    from langchain_core.messages import AIMessage

    from app.models import Textbook, TextbookSectionContent
    from app.orchestration.agents.course_knowledge import run_course_knowledge_agent

    engine = build_engine(
        postgresql_test_url(tmp_path, "data-structure-outline-markdown")
    )
    set_engine(engine)
    init_db(engine)

    with Session(engine) as session:
        session.add(
            User(uid="user-1", username="课程用户", identifier="course@example.com")
        )
        session.add(
            Textbook(
                textbook_id="textbook-data-structures",
                source_id="source-data-structures",
                title="数据结构教程",
                outline={
                    "sections": [
                        {"section_id": "1.1", "title": "复杂度分析"},
                        {"section_id": "1.2", "title": "数组与列表"},
                        {"section_id": "2.1", "title": "树结构"},
                    ]
                },
                student_availability_status="published",
                outline_review_status="approved",
                ingestion_status="completed",
            )
        )
        session.add(
            TextbookSectionContent(
                section_content_id="ds-section-1-1",
                textbook_id="textbook-data-structures",
                section_id="1.1",
                parent_section_id="1",
                order_index=1,
                title="复杂度分析",
                content_zh="复杂度分析用于判断算法在输入规模增长时的时间和空间开销。",
            )
        )
        session.add(
            TextbookSectionContent(
                section_content_id="ds-section-1-2",
                textbook_id="textbook-data-structures",
                section_id="1.2",
                parent_section_id="1",
                order_index=2,
                title="数组与列表",
                content_zh="数组与列表是线性结构基础，需要比较索引访问和插入删除成本。",
            )
        )
        session.add(
            TextbookSectionContent(
                section_content_id="ds-section-2-1",
                textbook_id="textbook-data-structures",
                section_id="2.1",
                parent_section_id="2",
                order_index=3,
                title="树结构",
                content_zh="树结构用于表达层次关系。",
            )
        )
        session.commit()

    profile = {
        "type": "basic_profile",
        "summary_text": "大三软件工程，项目驱动学习，想补齐数据结构基础。",
        "confirmed_info": {
            "current_grade": "大三",
            "major": "软件工程",
            "learning_stage": "项目实践",
            "has_clear_goal": "是",
            "learning_method_preference": "项目驱动学习",
            "learning_pace_preference": "按周推进",
            "content_preference": ["文档", "代码实践"],
            "need_guidance": "需要",
            "knowledge_foundation": "有 Python 基础",
            "strengths": "能完成小型功能",
            "weaknesses": "复杂度分析不熟",
            "experience": "做过课程项目",
            "short_term_goal": "掌握复杂度与线性结构",
            "long_term_goal": "形成算法工程基础",
            "weekly_available_time": "每周 8 小时",
            "constraints": "时间有限",
        },
    }
    year_learning_paths = {
        "year_3": {
            "current_learning_course": {
                "grade_id": "year_3",
                "course_node_id": "year_3_course_1",
            },
            "grade_plans": {
                "year_3": {
                    "course_nodes": [
                        {
                            "course_node_id": "year_3_course_1",
                            "course_or_chapter_theme": "复杂度分析与线性结构基础",
                            "grade_id": "year_3",
                            "course_goal": "掌握复杂度分析与数组列表基础",
                            "time_arrangement": {
                                "semester_scope": "上学期",
                                "duration": "2 周",
                                "pace_reason": "先补齐基础概念",
                            },
                            "key_points": ["复杂度分析", "数组与列表"],
                            "difficult_points": ["空间开销", "插入删除成本"],
                            "learning_sequence": ["复杂度分析", "数组与列表"],
                            "prerequisite_node_ids": [],
                            "chapter_nodes": [],
                            "core_knowledge_points": [],
                            "knowledge_relations": [],
                            "downstream_resource_direction_ids": [],
                            "acceptance_criteria": ["能比较常见线性结构操作成本"],
                            "source_textbook_id": "textbook-data-structures",
                            "source_textbook_title": "数据结构教程",
                            "source_outline_section_ids": ["1.1", "1.2"],
                        }
                    ]
                }
            },
        }
    }

    class CourseLlm:
        pass

    def naming_payload_from_outline(outline: dict) -> dict:
        return {
            "personalization_summary": outline["personalization_summary"],
            "section_texts": {
                section["section_id"]: {
                    "title": section["title"],
                    "description": section["description"],
                    "key_knowledge_points": section["key_knowledge_points"],
                }
                for section in outline["sections"]
            },
        }

    class CourseOutlineChain:
        async def ainvoke(self, _payload):
            outline = {
                "personalization_summary": "按复杂度与线性结构正文设计完整教学大纲。",
                "sections": [
                    {
                        "section_id": "1",
                        "parent_section_id": None,
                        "depth": 1,
                        "title": "复杂度分析基础",
                        "order_index": 1,
                        "description": "建立复杂度分析的核心边界。",
                        "key_knowledge_points": ["时间开销", "空间开销"],
                        "source_textbook_id": "textbook-data-structures",
                        "source_textbook_title": "数据结构教程",
                        "source_section_ids": ["1.1"],
                        "source_section_titles": ["复杂度分析"],
                        "source_content_chars": 100,
                    },
                    {
                        "section_id": "1.1",
                        "parent_section_id": "1",
                        "depth": 2,
                        "title": "输入规模与资源开销",
                        "order_index": 2,
                        "description": "复杂度分析用于判断算法在输入规模增长时的时间和空间开销。",
                        "key_knowledge_points": ["输入规模", "时间和空间开销"],
                        "source_textbook_id": "textbook-data-structures",
                        "source_textbook_title": "数据结构教程",
                        "source_section_ids": ["1.1"],
                        "source_section_titles": ["复杂度分析"],
                        "source_content_chars": 100,
                    },
                    {
                        "section_id": "1.2",
                        "parent_section_id": "1",
                        "depth": 2,
                        "title": "增长趋势判断",
                        "order_index": 3,
                        "description": "判断输入规模增长时成本如何变化。",
                        "key_knowledge_points": ["增长趋势"],
                        "source_textbook_id": "textbook-data-structures",
                        "source_textbook_title": "数据结构教程",
                        "source_section_ids": ["1.1"],
                        "source_section_titles": ["复杂度分析"],
                        "source_content_chars": 100,
                    },
                ],
                "learning_sequence": ["1", "2"],
                "total_estimated_hours": "10 小时",
            }
            return AIMessage(
                content=json.dumps(
                    naming_payload_from_outline(outline), ensure_ascii=False
                )
            )

    class CourseOutlinePrompt:
        def __or__(self, _other):
            return CourseOutlineChain()

    course_module = __import__(
        "app.orchestration.agents.course_knowledge", fromlist=["ChatPromptTemplate"]
    )
    original_course_prompt_factory = course_module.ChatPromptTemplate

    class CoursePromptFactory:
        @staticmethod
        def from_messages(_messages):
            return CourseOutlinePrompt()

    course_module.ChatPromptTemplate = CoursePromptFactory
    try:
        outline_result = asyncio.run(
            run_course_knowledge_agent(
                {
                    "user_id": "user-1",
                    "profile": profile,
                    "latest_grade_year": "year_3",
                    "year_learning_paths": year_learning_paths,
                    "messages": [],
                },
                CourseLlm(),
            )
        )
    finally:
        course_module.ChatPromptTemplate = original_course_prompt_factory

    assert "error" not in outline_result
    outline = outline_result["course_knowledge"]
    assert [section["section_id"] for section in outline["sections"]] == [
        "1",
        "1.1",
        "1.2",
    ]
    assert "树结构" not in json.dumps(outline, ensure_ascii=False)
    assert "时间和空间开销" in outline["sections"][1]["description"]
    assert outline["sections"][2]["source_section_titles"] == ["数组与列表"]

    captured_queries: list[str] = []

    class MarkdownLlm:
        pass

    class MarkdownChain:
        async def ainvoke(self, payload):
            captured_queries.append(payload["query"])
            parsed = _payload_from_query(payload["query"])
            section_data = parsed["target_section"]
            evidence_text = parsed["textbook_evidence_pack"]["evidence_text"]
            return AIMessage(
                content="\n\n".join(
                    [
                        f"# {section_data['section_id']} {section_data['title']}",
                        f"## 学习目标\n围绕教材证据学习：{evidence_text}",
                        "## 核心概念\n复杂度分析来自教材正文，关注输入规模增长后的资源开销。",
                        (
                            "## 步骤讲解\n"
                            "| 步骤 | 输入材料 | 具体动作 | 产出物 | 验收方式 |\n"
                            "| --- | --- | --- | --- | --- |\n"
                            "| 复杂度判断 | 输入规模 | 比较时间开销和空间开销 | 成本说明 | 能解释增长趋势 |\n"
                            "| 线性结构比较 | 数组与列表 | 对比索引访问和插入删除 | 操作成本表 | 能说清适用场景 |"
                        ),
                        "<!-- video:id=video_1 -->",
                        "## 练习任务\n比较数组和列表在索引访问、插入删除上的成本。",
                        "<!-- animation:id=anim_1 -->",
                        "## 检查标准\n- [ ] 能说清时间开销\n- [ ] 能说清空间开销\n- [ ] 能比较索引访问\n- [ ] 能比较插入删除成本",
                    ]
                )
            )

    class MarkdownPrompt:
        def __or__(self, _other):
            return MarkdownChain()

    class PromptFactory:
        @staticmethod
        def from_messages(_messages):
            return MarkdownPrompt()

    import app.orchestration.agents.course_resources as module

    original_factory = module.ChatPromptTemplate
    module.ChatPromptTemplate = PromptFactory
    try:
        markdown_result = asyncio.run(
            run_section_markdown_agent(
                {
                    "user_id": "user-1",
                    "course_knowledge": outline,
                    "profile": profile,
                    "year_learning_paths": year_learning_paths,
                    "messages": [],
                },
                MarkdownLlm(),
                {
                    "course_id": "year_3_course_1",
                    "section_id": "1.1",
                    "scope": "single_section",
                },
            )
        )
    finally:
        module.ChatPromptTemplate = original_factory

    assert "error" not in markdown_result
    assert len(captured_queries) == 1
    assert "复杂度分析用于判断算法" in captured_queries[0]
    markdown = markdown_result["course_knowledge"]["section_markdowns"]["1.1"][
        "markdown"
    ]
    assert "时间和空间开销" in markdown
    video_brief = markdown_result["course_knowledge"]["section_markdowns"]["1.1"][
        "video_briefs"
    ][0]
    assert "复杂度分析" in video_brief["title"]


def _complete_markdown_output(section_id: str, title: str) -> SectionMarkdownOutput:
    return SectionMarkdownOutput(
        section_id=section_id,
        parent_section_id="1",
        title=title,
        markdown=_complete_section_markdown(section_id, title),
        video_briefs=[
            {
                "video_id": "video_1",
                "title": f"{title}导入视频",
                "purpose": f"帮助学习者把「{title}」落到可验收产出",
            }
        ],
        animation_briefs=[
            {
                "animation_id": "anim_1",
                "title": f"{title}流程动画",
                "concept": f"展示「{title}」如何转成任务、资源和检查标准",
                "visual_elements": ["学习目标", "练习任务", "检查标准"],
                "motion": "三个节点依次淡入，并用连线表现递进关系。",
                "space": "正文宽度的 100%，高度 320px。",
                "placement_hint": "练习任务之后",
            }
        ],
    )


def _complete_animation_html(
    animation_id: str,
    title: str,
    concept: str,
    visual_elements: list[str],
) -> str:
    nodes = "".join(
        f'<div class="node" data-step="{index}">{element}</div>'
        for index, element in enumerate(visual_elements, start=1)
    )
    elements_text = "、".join(visual_elements)
    return (
        '<!doctype html><html><head><meta charset="utf-8"></head><body>'
        f'<section class="section-animation" data-animation-id="{animation_id}">'
        "<style>"
        ":root{--space-sm:8px;--space-md:16px;--space-lg:24px;"
        "--surface:oklch(96% 0.02 90);--panel:oklch(99% 0.01 90);"
        "--text:oklch(28% 0.04 240);--accent:oklch(70% 0.12 190);"
        "--shadow-sm:0 2px 4px oklch(0% 0 0 / 0.05),0 8px 20px oklch(0% 0 0 / 0.06);}"
        ".section-animation{font-family:'LXGW WenKai',serif;background:var(--surface);"
        "color:var(--text);padding:var(--space-lg);box-shadow:var(--shadow-sm);"
        "border-radius:16px;}"
        ".animation-context{margin-bottom:var(--space-md);line-height:1.7;}"
        ".stage{display:flex;gap:var(--space-md);align-items:center;}"
        ".node{opacity:1 !important;transform:none !important;background:var(--panel);"
        "border:1px solid var(--accent);border-radius:12px;padding:var(--space-md);"
        "min-width:120px;text-align:center;}"
        ".connector{opacity:1 !important;transform:none !important;flex:1;height:2px;background:var(--accent);}"
        "@media (prefers-reduced-motion: reduce){.section-animation *{animation:none !important;transition:none !important;}}"
        "</style>"
        '<div class="animation-context">'
        f'<div class="animation-context-title">{title}</div>'
        f'<div class="animation-context-concept">{concept}</div>'
        f'<div class="animation-context-elements">{elements_text}</div>'
        "</div>"
        f'<div class="stage">{nodes}</div>'
        "</section></body></html>"
    )


def test_run_section_markdown_agent_writes_each_first_chapter_child_section(
    tmp_path,
) -> None:
    class RecordingLlm:
        pass

    section_bodies = {
        "学习目标": (
            "本节先把小节目标拆成可验收的学习结果。学习者需要说明当前小节解决什么问题、"
            "输入材料来自哪里、后端如何组织模型调用、页面最终要展示什么内容。完成后，学习者可以把"
            "AI 核心接口调用与 Prompt 工程基础中的一个小任务写成可运行、可检查、可复盘的资源生成流程。"
        ),
        "核心概念": (
            "### API 连通性测试\n"
            "API 连通性测试用于确认密钥、base_url、model、messages 和 timeout 都能进入同一个标准请求。"
            "它不是泛泛点击一次按钮，而是要留下状态码、响应 JSON、错误日志和最小 payload。\n\n"
            "### 标准化请求封装\n"
            "标准化请求封装把模型调用需要的参数集中到一个函数里，避免业务代码散落密钥、模型名和错误处理。"
            "学习者需要说明请求输入、模型输出、异常响应和重试证据之间的关系。"
        ),
        "步骤讲解": (
            "第一步：读取输入材料。输入材料包括用户画像、学习路径、课程大纲和当前小节；具体动作是提取"
            "小节标题、描述和关键知识点；产出物是资源生成上下文。\n\n"
            "第二步：生成五个正文点。输入材料是资源生成上下文；具体动作是分别生成学习目标、核心概念、"
            "步骤讲解、练习任务和检查标准；产出物是五段正文。\n\n"
            "| 步骤 | 输入材料 | 具体动作 | 产出物 | 验收方式 |\n"
            "| --- | --- | --- | --- | --- |\n"
            "| 上下文读取 | 画像、路径、大纲、小节 | 提取目标字段 | 资源生成上下文 | 字段可打印复查 |\n"
            "| 五点生成 | 资源生成上下文 | 并发生成五段正文 | section_bodies | 每段非空且绑定小节 |\n"
            "| 后端拼装 | 五段正文与 brief | 插入标题和资源占位符 | markdown | 占位符 ID 与 brief 一致 |"
        ),
        "练习任务": (
            "请完成一个资源生成任务卡：输入是一个小节标题和三个关键知识点；操作步骤是先写五段正文，"
            "再确认视频 brief 与动画 brief，最后检查 `section_composed_markdowns` 是否能被前端读取。"
            "提交物是一份 Markdown 和一份 blocks 结构截图。"
        ),
        "检查标准": (
            "- [ ] 能说明五个正文点分别来自哪一次模型调用。\n"
            "- [ ] 能展示 Markdown 中的视频占位符与 video_briefs.video_id 完全一致。\n"
            "- [ ] 能展示 Markdown 中的动画占位符与 animation_briefs.animation_id 完全一致。\n"
            "- [ ] 能从数据库 outline_data 中读取 section_composed_markdowns。"
        ),
    }

    class MarkdownChain:
        async def ainvoke(self, payload):
            captured["queries"].append(payload["query"])
            assert "markdown_expansion_section" in payload["query"]
            section = _payload_from_query(payload["query"])["target_section"]
            expansion_section = _payload_from_query(payload["query"])[
                "markdown_expansion_section"
            ]
            captured["sections"].append((section["section_id"], expansion_section))
            if expansion_section == "完整文档":
                return _complete_section_markdown(
                    section["section_id"], section["title"]
                )
            return section_bodies[expansion_section]

    class MarkdownPrompt:
        def __or__(self, _other):
            return MarkdownChain()

    class PromptFactory:
        @staticmethod
        def from_messages(_messages):
            return MarkdownPrompt()

    captured = {"schema": None, "queries": [], "sections": []}
    engine = build_engine(postgresql_test_url(tmp_path, "section-markdown"))
    set_engine(engine)
    init_db(engine)
    with Session(engine) as session:
        session.add(
            User(uid="user-1", username="课程用户", identifier="course@example.com")
        )
        session.add(
            UserCourseKnowledgeOutline(
                user_uid="user-1",
                course_id="year_3_course_1",
                grade_year="year_3",
                course_name="AI 应用开发",
                outline_data=_outline(),
            )
        )
        session.commit()

    import app.orchestration.agents.course_resources as module

    original_factory = module.ChatPromptTemplate
    module.ChatPromptTemplate = PromptFactory
    try:
        result = asyncio.run(
            run_section_markdown_agent(
                {
                    "user_id": "user-1",
                    "course_knowledge": _outline(),
                    "profile": _profile(),
                    "year_learning_paths": _year_learning_paths(),
                    "messages": [],
                },
                RecordingLlm(),
                {
                    "course_id": "year_3_course_1",
                    "section_id": "1",
                    "scope": "chapter_sections",
                },
            )
        )
    finally:
        module.ChatPromptTemplate = original_factory

    assert len(captured["queries"]) == 3
    assert captured["sections"].count(("1.1", "完整文档")) == 1
    assert captured["sections"].count(("1.2", "完整文档")) == 1
    assert captured["sections"].count(("1.3", "完整文档")) == 1
    assert all('"profile"' in query for query in captured["queries"])
    assert all('"year_learning_paths"' in query for query in captured["queries"])
    assert all('"course_knowledge"' in query for query in captured["queries"])
    assert all('"每天 12 小时项目驱动"' in query for query in captured["queries"])
    assert all("作品级 Agent 项目闭环" in query for query in captured["queries"])
    assert all('"sections"' in query for query in captured["queries"])
    assert result["course_resource_plan"]["target_section_ids"] == ["1.1", "1.2", "1.3"]
    assert set(result["course_knowledge"]["section_markdowns"]) == {"1.1", "1.2", "1.3"}
    assert "1" not in result["course_knowledge"]["section_markdowns"]
    first_markdown = result["course_knowledge"]["section_markdowns"]["1.1"]
    assert "<!-- video:id=video_1 -->" in first_markdown["markdown"]
    assert "<!-- animation:id=anim_1 -->" in first_markdown["markdown"]
    assert first_markdown["video_briefs"][0]["video_id"] == "video_1"
    assert first_markdown["animation_briefs"][0]["animation_id"] == "anim_1"
    assert "功能边界" in first_markdown["animation_briefs"][0]["title"]
    assert set(result["course_knowledge"]["section_composed_markdowns"]) == {
        "1.1",
        "1.2",
        "1.3",
    }
    assert (
        result["course_knowledge"]["section_composed_markdowns"]["1.1"]["blocks"][0][
            "type"
        ]
        == "markdown"
    )
    with Session(engine) as session:
        row = session.get(UserCourseKnowledgeOutline, ("user-1", "year_3_course_1"))
    assert row is not None
    assert set(row.outline_data["section_markdowns"]) == {"1.1", "1.2", "1.3"}
    assert set(row.outline_data["section_composed_markdowns"]) == {"1.1", "1.2", "1.3"}


def test_run_section_markdown_agent_returns_error_when_llm_unavailable(
    tmp_path,
) -> None:
    class FailingLlm:
        pass

    class FailingChain:
        async def ainvoke(self, _payload):
            raise RuntimeError("structured generation timeout")

    class MarkdownPrompt:
        def __or__(self, _other):
            return FailingChain()

    class PromptFactory:
        @staticmethod
        def from_messages(_messages):
            return MarkdownPrompt()

    engine = build_engine(postgresql_test_url(tmp_path, "section-markdown-fallback"))
    set_engine(engine)
    init_db(engine)
    with Session(engine) as session:
        session.add(
            User(uid="user-1", username="课程用户", identifier="course@example.com")
        )
        session.add(
            UserCourseKnowledgeOutline(
                user_uid="user-1",
                course_id="year_3_course_1",
                grade_year="year_3",
                course_name="AI 应用开发",
                outline_data=_outline(),
            )
        )
        session.commit()

    import app.orchestration.agents.course_resources as module

    original_factory = module.ChatPromptTemplate
    module.ChatPromptTemplate = PromptFactory
    try:
        result = asyncio.run(
            run_section_markdown_agent(
                {
                    "user_id": "user-1",
                    "course_knowledge": _outline(),
                    "messages": [],
                },
                FailingLlm(),
                {
                    "course_id": "year_3_course_1",
                    "section_id": "1",
                    "scope": "chapter_sections",
                },
            )
        )
    finally:
        module.ChatPromptTemplate = original_factory

    assert result.get("error") is not None
    assert (
        "Markdown 文档未生成" in result["error"]
        or "Markdown 文档生成失败" in result["error"]
    )


def test_run_section_markdown_agent_returns_error_when_model_returns_error(
    tmp_path,
) -> None:
    class RecordingLlm:
        pass

    class ErrorChain:
        async def ainvoke(self, _payload):
            return {"error": "模型无法生成结构化结果"}

    class MarkdownPrompt:
        def __or__(self, _other):
            return ErrorChain()

    class PromptFactory:
        @staticmethod
        def from_messages(_messages):
            return MarkdownPrompt()

    engine = build_engine(
        postgresql_test_url(tmp_path, "section-markdown-model-error-fallback")
    )
    set_engine(engine)
    init_db(engine)
    with Session(engine) as session:
        session.add(
            User(uid="user-1", username="课程用户", identifier="course@example.com")
        )
        session.add(
            UserCourseKnowledgeOutline(
                user_uid="user-1",
                course_id="year_3_course_1",
                grade_year="year_3",
                course_name="AI 应用开发",
                outline_data=_outline(),
            )
        )
        session.commit()

    import app.orchestration.agents.course_resources as module

    original_factory = module.ChatPromptTemplate
    module.ChatPromptTemplate = PromptFactory
    try:
        result = asyncio.run(
            run_section_markdown_agent(
                {
                    "user_id": "user-1",
                    "course_knowledge": _outline(),
                    "profile": _profile(),
                    "year_learning_paths": _year_learning_paths(),
                    "messages": [],
                },
                RecordingLlm(),
                {
                    "course_id": "year_3_course_1",
                    "section_id": "1",
                    "scope": "chapter_sections",
                },
            )
        )
    finally:
        module.ChatPromptTemplate = original_factory

    assert result.get("error") is not None
    assert (
        "Markdown 文档未生成" in result["error"]
        or "Markdown 文档生成失败" in result["error"]
    )


def test_run_section_markdown_agent_persists_markdown_failure_without_clearing_other_composed_sections(
    tmp_path,
) -> None:
    class RecordingLlm:
        pass

    class ErrorChain:
        async def ainvoke(self, _payload):
            return {"error": "模型无法生成结构化结果"}

    class MarkdownPrompt:
        def __or__(self, _other):
            return ErrorChain()

    class PromptFactory:
        @staticmethod
        def from_messages(_messages):
            return MarkdownPrompt()

    existing_composed = {
        "2.1": {
            "section_id": "2.1",
            "parent_section_id": "2",
            "title": "学习目标",
            "markdown": "# 2.1 学习目标\n\n旧章节内容。",
            "blocks": [
                {
                    "type": "markdown",
                    "markdown": "# 2.1 学习目标\n\n旧章节内容。",
                }
            ],
            "generated_at": "2026-06-06T00:00:00Z",
        }
    }
    outline = _outline()
    outline["section_composed_markdowns"] = existing_composed
    engine = build_engine(
        postgresql_test_url(tmp_path, "section-markdown-section-error")
    )
    set_engine(engine)
    init_db(engine)
    with Session(engine) as session:
        session.add(
            User(uid="user-1", username="课程用户", identifier="course@example.com")
        )
        session.add(
            UserCourseKnowledgeOutline(
                user_uid="user-1",
                course_id="year_3_course_1",
                grade_year="year_3",
                course_name="AI 应用开发",
                outline_data=outline,
            )
        )
        session.commit()

    import app.orchestration.agents.course_resources as module

    original_factory = module.ChatPromptTemplate
    module.ChatPromptTemplate = PromptFactory
    try:
        result = asyncio.run(
            run_section_markdown_agent(
                {
                    "user_id": "user-1",
                    "course_knowledge": outline,
                    "profile": _profile(),
                    "year_learning_paths": _year_learning_paths(),
                    "messages": [],
                },
                RecordingLlm(),
                {
                    "course_id": "year_3_course_1",
                    "section_id": "1.1",
                    "scope": "single_section",
                },
            )
        )
    finally:
        module.ChatPromptTemplate = original_factory

    assert result.get("error") is not None
    with Session(engine) as session:
        row = session.get(UserCourseKnowledgeOutline, ("user-1", "year_3_course_1"))
    assert row is not None
    assert row.outline_data["section_composed_markdowns"] == existing_composed
    section_error = row.outline_data["section_resource_errors"]["1.1"]
    assert section_error["section_id"] == "1.1"
    assert section_error["phase"] == "markdown"
    assert section_error["message"] == result["error"]
    assert section_error["retryable"] is True
    assert section_error["updated_at"]


def test_run_section_markdown_agent_accepts_plain_markdown_model_output(
    tmp_path,
) -> None:
    class RecordingLlm:
        pass

    class MarkdownChain:
        async def ainvoke(self, payload):
            section = _payload_from_query(payload["query"])["target_section"]
            return _complete_section_markdown(section["section_id"], section["title"])

    class MarkdownPrompt:
        def __or__(self, _other):
            return MarkdownChain()

    class PromptFactory:
        @staticmethod
        def from_messages(_messages):
            return MarkdownPrompt()

    engine = build_engine(
        postgresql_test_url(tmp_path, "section-markdown-plain-output")
    )
    set_engine(engine)
    init_db(engine)
    with Session(engine) as session:
        session.add(
            User(uid="user-1", username="课程用户", identifier="course@example.com")
        )
        session.add(
            UserCourseKnowledgeOutline(
                user_uid="user-1",
                course_id="year_3_course_1",
                grade_year="year_3",
                course_name="AI 应用开发",
                outline_data=_outline(),
            )
        )
        session.commit()

    import app.orchestration.agents.course_resources as module

    original_factory = module.ChatPromptTemplate
    module.ChatPromptTemplate = PromptFactory
    try:
        result = asyncio.run(
            run_section_markdown_agent(
                {
                    "user_id": "user-1",
                    "course_knowledge": _outline(),
                    "profile": _profile(),
                    "year_learning_paths": _year_learning_paths(),
                    "messages": [],
                },
                RecordingLlm(),
                {
                    "course_id": "year_3_course_1",
                    "section_id": "1",
                    "scope": "chapter_sections",
                },
            )
        )
    finally:
        module.ChatPromptTemplate = original_factory

    assert result["course_resource_plan"]["target_section_ids"] == ["1.1", "1.2", "1.3"]
    first_markdown = result["course_knowledge"]["section_markdowns"]["1.1"]
    assert first_markdown["section_id"] == "1.1"
    assert first_markdown["video_briefs"][0]["video_id"] == "video_1"
    assert first_markdown["animation_briefs"][0]["animation_id"] == "anim_1"
    with Session(engine) as session:
        row = session.get(UserCourseKnowledgeOutline, ("user-1", "year_3_course_1"))
    assert row is not None
    assert set(row.outline_data["section_markdowns"]) == {"1.1", "1.2", "1.3"}


def test_run_section_markdown_agent_accepts_loose_json_without_brief_metadata(
    tmp_path,
) -> None:
    class RecordingLlm:
        pass

    class MarkdownChain:
        async def ainvoke(self, payload):
            section = _payload_from_query(payload["query"])["target_section"]
            return json.dumps(
                {
                    "markdown": _complete_section_markdown(
                        section["section_id"], section["title"]
                    ),
                },
                ensure_ascii=False,
            )

    class MarkdownPrompt:
        def __or__(self, _other):
            return MarkdownChain()

    class PromptFactory:
        @staticmethod
        def from_messages(_messages):
            return MarkdownPrompt()

    engine = build_engine(postgresql_test_url(tmp_path, "section-markdown-loose-json"))
    set_engine(engine)
    init_db(engine)
    with Session(engine) as session:
        session.add(
            User(uid="user-1", username="课程用户", identifier="course@example.com")
        )
        session.add(
            UserCourseKnowledgeOutline(
                user_uid="user-1",
                course_id="year_3_course_1",
                grade_year="year_3",
                course_name="AI 应用开发",
                outline_data=_outline(),
            )
        )
        session.commit()

    import app.orchestration.agents.course_resources as module

    original_factory = module.ChatPromptTemplate
    module.ChatPromptTemplate = PromptFactory
    try:
        result = asyncio.run(
            run_section_markdown_agent(
                {
                    "user_id": "user-1",
                    "course_knowledge": _outline(),
                    "profile": _profile(),
                    "year_learning_paths": _year_learning_paths(),
                    "messages": [],
                },
                RecordingLlm(),
                {
                    "course_id": "year_3_course_1",
                    "section_id": "1.1",
                    "scope": "single_section",
                },
            )
        )
    finally:
        module.ChatPromptTemplate = original_factory

    markdown_data = result["course_knowledge"]["section_markdowns"]["1.1"]
    assert markdown_data["section_id"] == "1.1"
    assert markdown_data["video_briefs"][0]["video_id"] == "video_1"
    assert markdown_data["animation_briefs"][0]["animation_id"] == "anim_1"


def test_run_section_markdown_agent_generates_markdown_from_five_section_bodies_without_full_document_retry(
    tmp_path,
) -> None:
    class RecordingLlm:
        pass

    section_bodies = {
        "学习目标": "本节目标是把 API 连通性测试和 Prompt 工程任务拆成可验收的五点教学内容。",
        "核心概念": "### 功能边界\n功能边界要求学习者区分接口连通、请求封装、Prompt 约束和输出验收。",
        "步骤讲解": (
            "第一步：读取配置和小节上下文。第二步：生成五点正文。第三步：拼装资源占位符。\n\n"
            "| 步骤 | 输入材料 | 具体动作 | 产出物 | 验收方式 |\n"
            "| --- | --- | --- | --- | --- |\n"
            "| 读取 | 课程上下文 | 提取字段 | payload | 字段完整 |\n"
            "| 拼装 | 五点正文 | 插入资源占位符 | markdown | ID 一致 |"
        ),
        "练习任务": "请提交一份五点正文，并检查后端保存的 composed blocks 是否能被前端读取。",
        "检查标准": (
            "- [ ] 有学习目标。\n"
            "- [ ] 有核心概念。\n"
            "- [ ] 有步骤表格。\n"
            "- [ ] 有前端可读的 composed markdown。"
        ),
    }

    class MarkdownChain:
        async def ainvoke(self, payload):
            captured["queries"].append(payload["query"])
            captured["attempts"] += 1
            parsed = _payload_from_query(payload["query"])
            if parsed["markdown_expansion_section"] == "完整文档":
                section = parsed["target_section"]
                return "\n\n".join(
                    [
                        f"# {section['section_id']} {section['title']}",
                        f"## 学习目标\n{section_bodies['学习目标']}",
                        f"## 核心概念\n{section_bodies['核心概念']}",
                        f"## 步骤讲解\n{section_bodies['步骤讲解']}",
                        "<!-- video:id=video_1 -->",
                        f"## 练习任务\n{section_bodies['练习任务']}",
                        "<!-- animation:id=anim_1 -->",
                        f"## 检查标准\n{section_bodies['检查标准']}",
                    ]
                )
            return section_bodies[parsed["markdown_expansion_section"]]

    class MarkdownPrompt:
        def __or__(self, _other):
            return MarkdownChain()

    class PromptFactory:
        @staticmethod
        def from_messages(_messages):
            return MarkdownPrompt()

    captured = {"schema": None, "queries": [], "attempts": 0}
    engine = build_engine(
        postgresql_test_url(tmp_path, "section-markdown-quality-retry")
    )
    set_engine(engine)
    init_db(engine)
    with Session(engine) as session:
        session.add(
            User(uid="user-1", username="课程用户", identifier="course@example.com")
        )
        session.add(
            UserCourseKnowledgeOutline(
                user_uid="user-1",
                course_id="year_3_course_1",
                grade_year="year_3",
                course_name="AI 应用开发",
                outline_data=_outline(),
            )
        )
        session.commit()

    import app.orchestration.agents.course_resources as module

    original_factory = module.ChatPromptTemplate
    module.ChatPromptTemplate = PromptFactory
    try:
        result = asyncio.run(
            run_section_markdown_agent(
                {
                    "user_id": "user-1",
                    "course_knowledge": _outline(),
                    "profile": _profile(),
                    "year_learning_paths": _year_learning_paths(),
                    "messages": [],
                },
                RecordingLlm(),
                {
                    "course_id": "year_3_course_1",
                    "section_id": "1.1",
                    "scope": "single_section",
                },
            )
        )
    finally:
        module.ChatPromptTemplate = original_factory

    assert "error" not in result
    assert captured["attempts"] == 1
    assert all("markdown_expansion_section" in query for query in captured["queries"])
    markdown = result["course_knowledge"]["section_markdowns"]["1.1"]["markdown"]
    assert "### 功能边界" in markdown
    assert "Key Concept" not in markdown
    assert "section_composed_markdowns" in result["course_knowledge"]
    with Session(engine) as session:
        row = session.get(UserCourseKnowledgeOutline, ("user-1", "year_3_course_1"))
    assert row is not None
    saved_markdown = row.outline_data["section_markdowns"]["1.1"]["markdown"]
    assert "### 功能边界" in saved_markdown
    assert "1.1" in row.outline_data["section_composed_markdowns"]


def test_run_section_markdown_agent_expands_short_markdown_with_llm_content(
    tmp_path,
) -> None:
    class RecordingLlm:
        pass

    short_markdown = "\n\n".join(
        [
            "# 1.1 学习目标",
            "## 学习目标\n先建立目标。",
            "## 核心概念\n### 功能边界\n先说明边界。",
            "## 步骤讲解\n第一步：读取材料。\n\n| 步骤 | 输入材料 | 产出物 | 验收方式 |\n| --- | --- | --- | --- |\n| 目标 | 画像 | 目标句 | 可复述 |",
            "<!-- video:id=video_1 -->",
            "## 练习任务\n写一张任务卡。",
            "<!-- animation:id=anim_1 -->",
            "## 检查标准\n- [ ] 有目标。\n- [ ] 有任务。\n- [ ] 有资源。\n- [ ] 有证据。",
            "## 来源\n- 《AI 应用开发项目教程》：1.1 学习目标。",
        ]
    )

    section_bodies = {
        "学习目标": (
            "模型扩写内容会围绕 API 连通性测试、标准化请求封装、Prompt 输入输出边界、"
            "错误响应观察、运行证据留存、任务卡提交和同伴复查展开。学习者要先明确本节不是泛泛了解接口，"
            "而是把一次模型调用拆成密钥读取、请求体组织、超时设置、响应解析和日志记录五个可检查动作。"
            "完成学习后，学习者应能说明为什么不能把 API Key 写死在代码里，为什么请求封装必须保留原始错误，"
            "以及为什么 Prompt 的输入、输出和验收条件要在调用前就写清楚。"
        ),
        "核心概念": (
            "### 功能边界\n"
            "模型扩写内容会围绕 API 连通性测试、标准化请求封装、Prompt 输入输出边界、错误响应观察、运行证据留存、"
            "任务卡提交和同伴复查展开。功能边界要求学习者把“能调通模型”拆成明确范围：本节只验证一条标准请求能稳定返回，"
            "不处理多轮记忆、复杂工具调用和长上下文压缩。这样做的价值是让后续开发有一个可以复用的最小通信层，"
            "每次出现 401、429、timeout 或空响应时，都能先回到这个最小层确认问题位置。\n\n"
            "### 验收标准\n"
            "验收标准不是写一句“接口可用”，而是要留下可复查证据：环境变量截图、请求 payload 示例、响应 JSON 片段、"
            "异常日志和一次失败重试记录。学习者需要能解释每个证据对应哪一个风险点，例如密钥是否被加载、模型名是否正确、"
            "messages 是否符合 OpenAI-compatible 协议、Prompt 是否约束了输出形状，以及失败时是否能定位到网络、鉴权或模型输出问题。"
        ),
        "步骤讲解": (
            "第一步：准备输入材料。输入材料包括 `.env` 中的 API Key、base_url、model，以及一个只包含 system 与 user 的最小 messages。"
            "具体动作是把这些字段写入请求封装函数的参数，而不是散落在业务代码中；判断依据是同伴只看函数签名就能知道调用需要什么；"
            "产出物是一份最小请求配置。\n\n"
            "第二步：执行标准请求。输入材料是请求配置和 Prompt 任务说明；具体动作是设置 timeout、发送 JSON payload、记录状态码和响应头；"
            "判断依据是成功响应能解析出文本，失败响应能保留错误码；产出物是一段可复现的运行日志。\n\n"
            "| 步骤 | 输入材料 | 具体动作 | 产出物 | 验收方式 |\n"
            "| --- | --- | --- | --- | --- |\n"
            "| 配置读取 | `.env`、模型名、base_url | 从环境变量加载并校验非空 | 请求配置对象 | 缺任一字段时能明确报错 |\n"
            "| 请求封装 | messages、temperature、timeout | 组装 OpenAI-compatible payload | JSON 请求体 | payload 字段完整且可打印 |\n"
            "| 响应解析 | HTTP 状态码、响应 JSON | 区分成功文本和错误信息 | 标准返回对象 | 成功与失败都有日志证据 |\n"
            "| Prompt 验收 | 任务目标、输出格式 | 检查输出是否满足格式 | 验收记录 | 能指出不合格输出原因 |"
        ),
        "练习任务": (
            "请完成一个 30 分钟任务卡：输入是一组接口配置字段和一个“生成三条学习建议”的 Prompt；操作步骤是先写 `call_llm_once` 函数，"
            "再用环境变量注入密钥和模型名，然后分别运行一次正常请求、一次错误模型名请求和一次过短 Prompt 请求。输出包括三份日志、"
            "一份 payload 示例和一段对比说明。提交物是 `llm_client.py`、运行截图、失败日志摘录和 Prompt 修改记录。完成标准是同伴可以"
            "用你的文件复现一次成功调用，并能从失败日志里判断问题发生在配置、网络、鉴权还是输出格式。这个任务会把学习目标落到真实工程动作，"
            "避免停留在“知道 API 可以调用”的口头理解。"
        ),
        "检查标准": (
            "- [ ] 能提交一份不含明文 API Key 的 `llm_client.py`，并说明密钥从哪个环境变量读取。\n"
            "- [ ] 能展示一次成功调用的 payload、状态码和响应片段，证明标准化请求封装真实可运行。\n"
            "- [ ] 能展示一次失败调用的错误日志，并说明错误属于配置、鉴权、限流、超时还是输出格式问题。\n"
            "- [ ] 能说明 Prompt 输入、输出格式和验收标准之间的关系，并指出一次不合格输出为什么需要重写 Prompt。\n"
            "- [ ] 能把视频 brief、动画 brief 与正文占位符逐一核对，证明资源不是装饰，而是服务当前小节学习目标。"
        ),
    }

    class MarkdownChain:
        async def ainvoke(self, payload):
            captured["queries"].append(payload["query"])
            if "markdown_expansion_section" in payload["query"]:
                captured["expansion_calls"] += 1
                captured["active_expansions"] += 1
                captured["max_active_expansions"] = max(
                    captured["max_active_expansions"],
                    captured["active_expansions"],
                )
                await asyncio.sleep(0.01)
                captured["active_expansions"] -= 1
                query = payload["query"]
                for section_title, body in section_bodies.items():
                    if f'"markdown_expansion_section": "{section_title}"' in query:
                        return body
                if '"markdown_expansion_section": "完整文档"' in query:
                    section = _payload_from_query(query)["target_section"]
                    return _complete_section_markdown_from_bodies(
                        section["section_id"], section["title"], section_bodies
                    )
                return section_bodies["学习目标"]
            captured["markdown_calls"] += 1
            return SectionMarkdownOutput(
                section_id="1.1",
                parent_section_id="1",
                title="学习目标",
                markdown=short_markdown,
                video_briefs=[
                    {
                        "video_id": "video_1",
                        "title": "学习目标导入视频",
                        "purpose": "帮助学习者理解 API 连通性测试与标准化请求封装",
                    }
                ],
                animation_briefs=[
                    {
                        "animation_id": "anim_1",
                        "title": "学习目标流程动画",
                        "concept": "展示 API 调用目标如何转成任务、资源和检查标准",
                        "visual_elements": [
                            "API 连通性测试",
                            "标准化请求封装",
                            "检查标准",
                        ],
                        "motion": "节点依次通过 opacity 淡入，并用 transform 表现轻微位移。",
                        "space": "正文宽度 100%，高度 320px。",
                        "placement_hint": "练习任务之前。",
                    }
                ],
            )

    class MarkdownPrompt:
        def __or__(self, _other):
            return MarkdownChain()

    class PromptFactory:
        @staticmethod
        def from_messages(_messages):
            return MarkdownPrompt()

    captured = {
        "queries": [],
        "markdown_calls": 0,
        "expansion_calls": 0,
        "active_expansions": 0,
        "max_active_expansions": 0,
    }
    engine = build_engine(postgresql_test_url(tmp_path, "section-markdown-expansion"))
    set_engine(engine)
    init_db(engine)
    with Session(engine) as session:
        session.add(
            User(uid="user-1", username="课程用户", identifier="course@example.com")
        )
        session.add(
            UserCourseKnowledgeOutline(
                user_uid="user-1",
                course_id="year_3_course_1",
                grade_year="year_3",
                course_name="AI 应用开发",
                outline_data=_outline(),
            )
        )
        session.commit()

    import app.orchestration.agents.course_resources as module

    original_factory = module.ChatPromptTemplate
    module.ChatPromptTemplate = PromptFactory
    try:
        result = asyncio.run(
            run_section_markdown_agent(
                {
                    "user_id": "user-1",
                    "course_knowledge": _outline(),
                    "profile": _profile(),
                    "year_learning_paths": _year_learning_paths(),
                    "messages": [],
                },
                RecordingLlm(),
                {
                    "course_id": "year_3_course_1",
                    "section_id": "1.1",
                    "scope": "single_section",
                },
            )
        )
    finally:
        module.ChatPromptTemplate = original_factory

    assert "error" not in result
    assert captured["markdown_calls"] == 0
    assert captured["expansion_calls"] == 1
    assert captured["max_active_expansions"] == 1
    markdown = result["course_knowledge"]["section_markdowns"]["1.1"]["markdown"]
    assert "模型扩写内容会围绕 API 连通性测试" in markdown
    assert (
        _markdown_quality_issue(
            markdown,
            _section_by_id(_outline(), "1.1"),
            result["course_knowledge"]["section_markdowns"]["1.1"]["video_briefs"],
            result["course_knowledge"]["section_markdowns"]["1.1"]["animation_briefs"],
        )
        is None
    )


def test_section_body_from_expansion_text_extracts_requested_heading_from_json_markdown() -> (
    None
):
    raw = json.dumps(
        {
            "markdown": "\n\n".join(
                [
                    "# 1.1 API 连通性测试",
                    "## 学习目标\n目标正文不能被误用。",
                    "## 核心概念\n核心概念正文需要被提取。\n\n### API Key\n用环境变量管理密钥。",
                    "## 步骤讲解\n步骤正文不能被误用。",
                ]
            )
        },
        ensure_ascii=False,
    )

    body = _section_body_from_expansion_text(raw, "核心概念")

    assert "核心概念正文需要被提取" in body
    assert "目标正文不能被误用" not in body
    assert "步骤正文不能被误用" not in body


def test_run_section_markdown_agent_scaffolds_structural_markdown_gaps(
    tmp_path,
) -> None:
    class RecordingLlm:
        pass

    section_bodies = {
        "学习目标": (
            "本节围绕学习目标展开，要求学习者把功能边界转成可检查的学习产出。"
            "完成后需要能说明输入材料、步骤记录、资源占位和检查标准分别服务哪一个学习动作，"
            "并把学习结果保存成可以复查的 Markdown 文档。"
        ),
        "核心概念": (
            "### 功能边界\n"
            "功能边界要求先说明本节只处理学习目标与验收产出的对应关系，不扩展到后续接口接入。"
            "学习者需要把目标、输入、动作、输出和检查证据写成稳定结构，避免只写一句抽象结论。"
        ),
        "步骤讲解": "",
        "练习任务": "",
        "检查标准": (
            "- [ ] 能说明学习目标和功能边界之间的关系。\n"
            "- [ ] 能提交一份包含步骤记录的 Markdown 文档。\n"
            "- [ ] 能解释视频和动画资源分别解决哪一个理解难点。"
        ),
    }

    class MarkdownChain:
        async def ainvoke(self, payload):
            captured["expansion_calls"] += 1
            query = payload["query"]
            expansion_section = _payload_from_query(query)["markdown_expansion_section"]
            if expansion_section == "完整文档":
                section = _payload_from_query(query)["target_section"]
                return _complete_section_markdown_from_bodies(
                    section["section_id"], section["title"], section_bodies
                )
            return section_bodies[expansion_section]

    class MarkdownPrompt:
        def __or__(self, _other):
            return MarkdownChain()

    class PromptFactory:
        @staticmethod
        def from_messages(_messages):
            return MarkdownPrompt()

    captured = {"expansion_calls": 0}
    engine = build_engine(postgresql_test_url(tmp_path, "section-markdown-scaffold"))
    set_engine(engine)
    init_db(engine)
    with Session(engine) as session:
        session.add(
            User(uid="user-1", username="课程用户", identifier="course@example.com")
        )
        session.add(
            UserCourseKnowledgeOutline(
                user_uid="user-1",
                course_id="year_3_course_1",
                grade_year="year_3",
                course_name="AI 应用开发",
                outline_data=_outline(),
            )
        )
        session.commit()

    import app.orchestration.agents.course_resources as module

    original_factory = module.ChatPromptTemplate
    module.ChatPromptTemplate = PromptFactory
    try:
        result = asyncio.run(
            run_section_markdown_agent(
                {
                    "user_id": "user-1",
                    "course_knowledge": _outline(),
                    "profile": _profile(),
                    "year_learning_paths": _year_learning_paths(),
                    "messages": [],
                },
                RecordingLlm(),
                {
                    "course_id": "year_3_course_1",
                    "section_id": "1.1",
                    "scope": "single_section",
                },
            )
        )
    finally:
        module.ChatPromptTemplate = original_factory

    assert "error" not in result
    markdown_data = result["course_knowledge"]["section_markdowns"]["1.1"]
    markdown = markdown_data["markdown"]
    steps_body = markdown.split("## 步骤讲解", 1)[1].split(
        "<!-- video:id=video_1 -->", 1
    )[0]
    checks_body = markdown.split("## 检查标准", 1)[1]
    assert "| 步骤 | 输入材料 | 具体动作 | 产出物 | 验收方式 |" in steps_body
    assert "任务卡：围绕「学习目标」完成一次可复查的小练习。" in markdown
    assert (
        len([line for line in checks_body.splitlines() if line.startswith("- [ ]")])
        >= 4
    )
    assert (
        _markdown_quality_issue(
            markdown,
            _section_by_id(_outline(), "1.1"),
            markdown_data["video_briefs"],
            markdown_data["animation_briefs"],
        )
        is None
    )


def test_run_section_markdown_agent_returns_error_when_quality_repeatedly_fails(
    tmp_path,
) -> None:
    class RecordingLlm:
        pass

    class MarkdownChain:
        async def ainvoke(self, payload):
            if "markdown_expansion_section" in payload["query"]:
                captured["expansion_attempts"] += 1
            else:
                captured["attempts"] += 1
            return {
                "section_id": "1.2",
                "parent_section_id": "1",
                "title": "任务拆解",
                "markdown": "# 1.2 任务拆解\n\n## 学习目标\n太短。\n\n<!-- video:id=video_1 -->\n\n<!-- animation:id=anim_1 -->",
                "video_briefs": [
                    {
                        "video_id": "video_1",
                        "title": "任务拆解视频",
                        "purpose": "理解任务拆解",
                    }
                ],
                "animation_briefs": [
                    {
                        "animation_id": "anim_1",
                        "title": "任务拆解动画",
                        "concept": "展示任务拆解如何转成验收证据",
                        "visual_elements": ["任务拆解", "验收证据"],
                        "motion": "节点依次淡入。",
                        "space": "正文宽度 100%，高度 320px。",
                        "placement_hint": "练习任务之前。",
                    }
                ],
            }

    class MarkdownPrompt:
        def __or__(self, _other):
            return MarkdownChain()

    class PromptFactory:
        @staticmethod
        def from_messages(_messages):
            return MarkdownPrompt()

    captured = {"attempts": 0, "expansion_attempts": 0}
    engine = build_engine(
        postgresql_test_url(tmp_path, "section-markdown-deterministic-rewrite")
    )
    set_engine(engine)
    init_db(engine)
    with Session(engine) as session:
        session.add(
            User(uid="user-1", username="课程用户", identifier="course@example.com")
        )
        session.add(
            UserCourseKnowledgeOutline(
                user_uid="user-1",
                course_id="year_3_course_1",
                grade_year="year_3",
                course_name="AI 应用开发",
                outline_data=_outline(),
            )
        )
        session.commit()

    import app.orchestration.agents.course_resources as module

    original_factory = module.ChatPromptTemplate
    module.ChatPromptTemplate = PromptFactory
    try:
        result = asyncio.run(
            run_section_markdown_agent(
                {
                    "user_id": "user-1",
                    "course_knowledge": _outline(),
                    "profile": _profile(),
                    "year_learning_paths": _year_learning_paths(),
                    "messages": [],
                },
                RecordingLlm(),
                {
                    "course_id": "year_3_course_1",
                    "section_id": "1.2",
                    "scope": "single_section",
                },
            )
        )
    finally:
        module.ChatPromptTemplate = original_factory

    assert result.get("error") is not None
    assert (
        "Markdown 文档质量不合格" in result["error"]
        or "Markdown 文档未生成" in result["error"]
    )
    assert captured["expansion_attempts"] > 0


def test_run_section_markdown_agent_uses_backend_generated_resource_briefs(
    tmp_path,
) -> None:
    class RecordingLlm:
        pass

    section_bodies = {
        "学习目标": "本节目标是确认后端生成视频 brief 和动画 brief，并把它们插入 Markdown。",
        "核心概念": "### 资源 brief\n资源 brief 由后端生成，正文模型只负责教学内容，不负责资源 ID。",
        "步骤讲解": (
            "第一步：生成正文。第二步：生成 brief。第三步：拼装占位符。\n\n"
            "| 步骤 | 输入材料 | 具体动作 | 产出物 | 验收方式 |\n"
            "| --- | --- | --- | --- | --- |\n"
            "| 正文 | 小节上下文 | 生成五点 | section_bodies | 非空 |\n"
            "| 资源 | 小节上下文 | 后端生成 brief | video_1/anim_1 | ID 一致 |"
        ),
        "练习任务": "请核对 Markdown 占位符、video_briefs 和 animation_briefs 三者 ID。",
        "检查标准": (
            "- [ ] video_1 出现在 Markdown。\n"
            "- [ ] anim_1 出现在 Markdown。\n"
            "- [ ] video_briefs 只包含 video_1。\n"
            "- [ ] animation_briefs 只包含 anim_1。"
        ),
    }

    class MarkdownChain:
        async def ainvoke(self, payload):
            captured["queries"].append(payload["query"])
            captured["attempts"] += 1
            parsed = _payload_from_query(payload["query"])
            if parsed["markdown_expansion_section"] == "完整文档":
                section = parsed["target_section"]
                return _complete_section_markdown_from_bodies(
                    section["section_id"], section["title"], section_bodies
                )
            return section_bodies[parsed["markdown_expansion_section"]]

    class MarkdownPrompt:
        def __or__(self, _other):
            return MarkdownChain()

    class PromptFactory:
        @staticmethod
        def from_messages(_messages):
            return MarkdownPrompt()

    captured = {"schema": None, "queries": [], "attempts": 0}
    engine = build_engine(
        postgresql_test_url(tmp_path, "section-markdown-second-repair")
    )
    set_engine(engine)
    init_db(engine)
    with Session(engine) as session:
        session.add(
            User(uid="user-1", username="课程用户", identifier="course@example.com")
        )
        session.add(
            UserCourseKnowledgeOutline(
                user_uid="user-1",
                course_id="year_3_course_1",
                grade_year="year_3",
                course_name="AI 应用开发",
                outline_data=_outline(),
            )
        )
        session.commit()

    import app.orchestration.agents.course_resources as module

    original_factory = module.ChatPromptTemplate
    module.ChatPromptTemplate = PromptFactory
    try:
        result = asyncio.run(
            run_section_markdown_agent(
                {
                    "user_id": "user-1",
                    "course_knowledge": _outline(),
                    "profile": _profile(),
                    "year_learning_paths": _year_learning_paths(),
                    "messages": [],
                },
                RecordingLlm(),
                {
                    "course_id": "year_3_course_1",
                    "section_id": "1.1",
                    "scope": "single_section",
                },
            )
        )
    finally:
        module.ChatPromptTemplate = original_factory

    assert "error" not in result
    assert captured["attempts"] == 1
    markdown = result["course_knowledge"]["section_markdowns"]["1.1"]["markdown"]
    assert "<!-- video:id=video_1 -->" in markdown
    assert "<!-- animation:id=anim_1 -->" in markdown
    assert (
        result["course_knowledge"]["section_markdowns"]["1.1"]["animation_briefs"][0][
            "animation_id"
        ]
        == "anim_1"
    )


def test_run_section_markdown_agent_generates_child_sections_concurrently(
    tmp_path,
) -> None:
    class RecordingLlm:
        pass

    section_bodies = {
        "学习目标": "本节把目标拆成可验收的教学产出，并确认 Markdown、视频和动画都绑定当前小节。",
        "核心概念": "### 任务拆解\n任务拆解要求把输入、处理、输出和验收证据写清楚，避免资源生成变成泛泛正文。",
        "步骤讲解": (
            "第一步：读取小节上下文并提取标题、描述和知识点。\n\n"
            "| 步骤 | 输入材料 | 具体动作 | 产出物 | 验收方式 |\n"
            "| --- | --- | --- | --- | --- |\n"
            "| 读取 | 小节上下文 | 提取字段 | 上下文对象 | 字段非空 |\n"
            "| 生成 | 上下文对象 | 生成五个正文点 | Markdown | 标题完整 |"
        ),
        "练习任务": "请提交一份五点正文和一份 composed blocks 结构，证明后端完成拼装。",
        "检查标准": (
            "- [ ] 有学习目标。\n"
            "- [ ] 有核心概念。\n"
            "- [ ] 有步骤表格。\n"
            "- [ ] 有 composed markdown。"
        ),
    }

    class MarkdownChain:
        async def ainvoke(self, payload):
            captured["active"] += 1
            captured["max_active"] = max(captured["max_active"], captured["active"])
            try:
                await asyncio.sleep(0.01)
                expansion_section = _payload_from_query(payload["query"])[
                    "markdown_expansion_section"
                ]
                if expansion_section == "完整文档":
                    section = _payload_from_query(payload["query"])["target_section"]
                    return _complete_section_markdown(
                        section["section_id"], section["title"]
                    )
                return section_bodies[expansion_section]
            finally:
                captured["active"] -= 1

    class MarkdownPrompt:
        def __or__(self, _other):
            return MarkdownChain()

    class PromptFactory:
        @staticmethod
        def from_messages(_messages):
            return MarkdownPrompt()

    captured = {"schema": None, "active": 0, "max_active": 0}
    engine = build_engine(postgresql_test_url(tmp_path, "section-markdown-concurrent"))
    set_engine(engine)
    init_db(engine)
    with Session(engine) as session:
        session.add(
            User(uid="user-1", username="课程用户", identifier="course@example.com")
        )
        session.add(
            UserCourseKnowledgeOutline(
                user_uid="user-1",
                course_id="year_3_course_1",
                grade_year="year_3",
                course_name="AI 应用开发",
                outline_data=_outline(),
            )
        )
        session.commit()

    import app.orchestration.agents.course_resources as module

    original_factory = module.ChatPromptTemplate
    module.ChatPromptTemplate = PromptFactory
    try:
        result = asyncio.run(
            run_section_markdown_agent(
                {
                    "user_id": "user-1",
                    "course_knowledge": _outline(),
                    "messages": [],
                },
                RecordingLlm(),
                {
                    "course_id": "year_3_course_1",
                    "section_id": "1",
                    "scope": "chapter_sections",
                },
            )
        )
    finally:
        module.ChatPromptTemplate = original_factory

    assert captured["max_active"] == 3
    assert set(result["course_knowledge"]["section_markdowns"]) == {"1.1", "1.2", "1.3"}


def test_run_section_markdown_agent_returns_error_when_failed_section_cannot_be_retried(
    tmp_path,
) -> None:
    class RecordingLlm:
        pass

    class MarkdownChain:
        async def ainvoke(self, payload):
            section = _payload_from_query(payload["query"])["target_section"]
            section_id = section["section_id"]
            captured["attempts"][section_id] = (
                captured["attempts"].get(section_id, 0) + 1
            )
            if section_id == "1.1":
                return SectionMarkdownOutput(
                    section_id="1.1",
                    parent_section_id="1",
                    title="学习目标",
                    markdown="# 学习目标\n\nKey Concept\n\n视频资源暂时不可用",
                    video_briefs=[
                        {
                            "video_id": "video_1",
                            "title": "导入视频",
                            "purpose": "建立直觉",
                        }
                    ],
                    animation_briefs=[
                        {
                            "animation_id": "anim_1",
                            "title": "动画",
                            "concept": "目标流转",
                        }
                    ],
                )
            return _complete_markdown_output(section_id, section["title"])

    class MarkdownPrompt:
        def __or__(self, _other):
            return MarkdownChain()

    class PromptFactory:
        @staticmethod
        def from_messages(_messages):
            return MarkdownPrompt()

    captured = {"schema": None, "attempts": {}}
    engine = build_engine(postgresql_test_url(tmp_path, "section-markdown-batch-retry"))
    set_engine(engine)
    init_db(engine)
    with Session(engine) as session:
        session.add(
            User(uid="user-1", username="课程用户", identifier="course@example.com")
        )
        session.add(
            UserCourseKnowledgeOutline(
                user_uid="user-1",
                course_id="year_3_course_1",
                grade_year="year_3",
                course_name="AI 应用开发",
                outline_data=_outline(),
            )
        )
        session.commit()

    import app.orchestration.agents.course_resources as module

    original_factory = module.ChatPromptTemplate
    module.ChatPromptTemplate = PromptFactory
    try:
        result = asyncio.run(
            run_section_markdown_agent(
                {
                    "user_id": "user-1",
                    "course_knowledge": _outline(),
                    "profile": _profile(),
                    "year_learning_paths": _year_learning_paths(),
                    "messages": [],
                },
                RecordingLlm(),
                {
                    "course_id": "year_3_course_1",
                    "section_id": "1",
                    "scope": "chapter_sections",
                },
            )
        )
    finally:
        module.ChatPromptTemplate = original_factory

    assert result.get("error") is not None
    assert (
        "Markdown 文档未生成" in result["error"]
        or "Markdown 文档质量不合格" in result["error"]
    )


def test_stream_chapter_resource_generation_reports_error_when_resource_llm_fails(
    tmp_path, monkeypatch
) -> None:
    class ResourceLlm:
        pass

    engine = build_engine(postgresql_test_url(tmp_path, "section-stream-fallback"))
    set_engine(engine)
    init_db(engine)
    with Session(engine) as session:
        session.add(
            User(uid="user-1", username="课程用户", identifier="course@example.com")
        )
        session.add(
            UserCourseKnowledgeOutline(
                user_uid="user-1",
                course_id="year_3_course_1",
                grade_year="year_3",
                course_name="AI 应用开发",
                outline_data=_outline(),
            )
        )
        session.commit()

    import app.orchestration.agents.course_resources as module

    async def markdown_agent(state, _llm, explicit_args=None):
        outline = _outline()
        section_markdowns = {}
        for section in outline["sections"]:
            if section["parent_section_id"] != "1":
                continue
            markdown_data = _complete_markdown_output(
                section["section_id"], section["title"]
            ).model_dump()
            section_markdowns[section["section_id"]] = markdown_data
        updated_outline = dict(outline)
        updated_outline["section_markdowns"] = section_markdowns
        return {
            "course_knowledge": updated_outline,
            "course_resource_plan": {
                "course_id": "year_3_course_1",
                "target_section_ids": ["1.1", "1.2", "1.3"],
                "markdown_section_ids": ["1.1", "1.2", "1.3"],
                "video_section_ids": [],
                "animation_section_ids": [],
            },
        }

    class FailingAnimationPrompt:
        async def ainvoke(self, _payload):
            raise RuntimeError("resource generation timeout")

    class PromptFactory:
        @staticmethod
        def from_messages(_messages):
            class ResourcePrompt:
                def __or__(self, _llm):
                    return FailingAnimationPrompt()

            return ResourcePrompt()

    original_factory = module.ChatPromptTemplate
    original_markdown_agent = module.run_section_markdown_agent
    module.ChatPromptTemplate = PromptFactory
    module.run_section_markdown_agent = markdown_agent

    async def verified_search(video_briefs, section, _outline=None):
        brief = video_briefs[0]
        return [
            {
                "brief_id": brief["video_id"],
                "title": (f"{brief['title']} {section['title']} {brief['purpose']}"),
                "url": "https://www.youtube.com/watch?v=resource-animation-test",
                "source": "YouTube",
            }
        ]

    original_verified_search = module._find_verified_video_from_search
    module._find_verified_video_from_search = verified_search
    monkeypatch.setattr(
        animation_module, "_deterministic_animation_data", lambda *_args: []
    )
    try:

        async def collect_events():
            return [
                event
                async for event in module.stream_chapter_resource_generation(
                    {
                        "user_id": "user-1",
                        "session_id": "session-1",
                        "course_knowledge": _outline(),
                        "profile": {},
                        "year_learning_paths": {},
                    },
                    ResourceLlm(),
                    ResourceLlm(),
                    course_id="year_3_course_1",
                    chapter_section_id="1",
                )
            ]

        events = asyncio.run(collect_events())
    finally:
        module.ChatPromptTemplate = original_factory
        module.run_section_markdown_agent = original_markdown_agent
        module._find_verified_video_from_search = original_verified_search

    assert any(event["event"] == "error" for event in events)
    assert events[-1]["event"] == "error"
    assert events[-1]["phase"] == "animation"
    assert events[-1]["message"] == "课程资源生成失败：HTML 动画未生成，请稍后重试。"
    assert not any(event["event"] == "message_completed" for event in events)
    assert not any(event["event"] == "session_completed" for event in events)
    with Session(engine) as session:
        row = session.get(UserCourseKnowledgeOutline, ("user-1", "year_3_course_1"))
    assert row is not None
    assert set(row.outline_data["section_video_links"]) == {"1.1", "1.2", "1.3"}
    assert "section_composed_markdowns" not in row.outline_data


from app.orchestration.agents.course_resources import run_section_video_search_agent


def test_run_section_video_search_agent_writes_url_and_fallback_cover(
    tmp_path, monkeypatch
) -> None:
    class RecordingLlm:
        pass

    class VideoChain:
        async def ainvoke(self, payload):
            captured["queries"].append(payload["query"])
            return SectionVideoSearchOutput(
                section_id="1.1",
                query="AI 应用开发 学习目标 视频教程",
                videos=[
                    {
                        "brief_id": "video_1",
                        "title": "AI 应用开发需求边界与验收标准学习目标讲解",
                        "url": "https://www.youtube.com/watch?v=dummy-video",
                        "cover_url": "",
                        "source": "example.com",
                    }
                ],
            )

    class VideoPrompt:
        def __or__(self, _other):
            return VideoChain()

    class PromptFactory:
        @staticmethod
        def from_messages(_messages):
            return VideoPrompt()

    async def verified_search(_video_briefs, _section, _outline=None):
        captured["verified_search"] += 1
        return [
            {
                "brief_id": "video_1",
                "title": "AI 应用开发需求边界与验收标准学习目标讲解",
                "url": "https://www.youtube.com/watch?v=dummy-video",
                "cover_url": "",
                "source": "example.com",
            }
        ]

    outline = _outline()
    outline["section_markdowns"] = {
        "1.1": {
            "section_id": "1.1",
            "parent_section_id": "1",
            "title": "学习目标",
            "markdown": "# 学习目标\n\n完整教学内容",
            "video_briefs": [
                {
                    "video_id": "video_1",
                    "title": "需求边界导入视频",
                    "purpose": "帮助学习者建立需求边界与验收标准的直觉",
                }
            ],
            "animation_briefs": [],
            "generated_at": "2026-06-06T00:00:00Z",
        }
    }
    captured = {"schema": None, "queries": [], "verified_search": 0}
    engine = build_engine(postgresql_test_url(tmp_path, "section-video"))
    set_engine(engine)
    init_db(engine)
    with Session(engine) as session:
        session.add(
            User(uid="user-1", username="课程用户", identifier="course@example.com")
        )
        session.add(
            UserCourseKnowledgeOutline(
                user_uid="user-1",
                course_id="year_3_course_1",
                grade_year="year_3",
                course_name="AI 应用开发",
                outline_data=outline,
            )
        )
        session.commit()

    import app.orchestration.agents.course_resources as module

    original_factory = module.ChatPromptTemplate
    module.ChatPromptTemplate = PromptFactory
    monkeypatch.setattr(module, "_find_verified_video_from_search", verified_search)
    try:
        result = asyncio.run(
            run_section_video_search_agent(
                {
                    "user_id": "user-1",
                    "course_knowledge": outline,
                    "profile": _profile(),
                    "year_learning_paths": _year_learning_paths(),
                    "course_resource_plan": {
                        "course_id": "year_3_course_1",
                        "target_section_ids": ["1.1"],
                    },
                    "messages": [],
                },
                RecordingLlm(),
            )
        )
    finally:
        module.ChatPromptTemplate = original_factory

    assert captured["queries"] == []
    assert captured["verified_search"] == 1
    videos = result["course_knowledge"]["section_video_links"]["1.1"]["videos"]
    assert videos[0]["brief_id"] == "video_1"
    assert videos[0]["url"] == "https://www.youtube.com/watch?v=dummy-video"
    assert videos[0]["cover_status"] == "fallback"
    assert videos[0]["cover_url"].startswith("data:image/svg+xml;utf8,")


def test_run_section_video_search_agent_retries_transient_search_failure(
    tmp_path, monkeypatch
) -> None:
    class RecordingLlm:
        pass

    class VideoChain:
        async def ainvoke(self, payload):
            captured["queries"].append(payload["query"])
            captured["attempts"] += 1
            if captured["attempts"] == 1:
                raise RuntimeError("临时失败")
            return SectionVideoSearchOutput(
                section_id="1.1",
                query="AI 应用开发 学习目标 视频教程",
                videos=[
                    {
                        "brief_id": "video_1",
                        "title": "需求边界导入视频：需求边界与验收标准重试讲解",
                        "url": "https://www.youtube.com/watch?v=dummy-retried-video",
                        "cover_url": "https://example.com/cover.png",
                        "source": "example.com",
                    }
                ],
            )

    class VideoPrompt:
        def __or__(self, _other):
            return VideoChain()

    class PromptFactory:
        @staticmethod
        def from_messages(_messages):
            return VideoPrompt()

    async def verified_search(_video_briefs, _section, _outline=None):
        captured["search_attempts"] += 1
        if captured["search_attempts"] == 1:
            raise RuntimeError("临时失败")
        return [
            {
                "brief_id": "video_1",
                "title": "需求边界导入视频：需求边界与验收标准重试讲解",
                "url": "https://www.youtube.com/watch?v=dummy-retried-video",
                "cover_url": "https://example.com/cover.png",
                "source": "example.com",
            }
        ]

    outline = _outline()
    outline["section_markdowns"] = {
        "1.1": {
            "section_id": "1.1",
            "parent_section_id": "1",
            "title": "学习目标",
            "markdown": "# 学习目标\n\n完整教学内容",
            "video_briefs": [
                {
                    "video_id": "video_1",
                    "title": "需求边界导入视频",
                    "purpose": "帮助学习者建立需求边界与验收标准的直觉",
                }
            ],
            "animation_briefs": [],
            "generated_at": "2026-06-06T00:00:00Z",
        }
    }
    captured = {"schema": None, "queries": [], "attempts": 0, "search_attempts": 0}
    engine = build_engine(postgresql_test_url(tmp_path, "section-video-retry"))
    set_engine(engine)
    init_db(engine)
    with Session(engine) as session:
        session.add(
            User(uid="user-1", username="课程用户", identifier="course@example.com")
        )
        session.add(
            UserCourseKnowledgeOutline(
                user_uid="user-1",
                course_id="year_3_course_1",
                grade_year="year_3",
                course_name="AI 应用开发",
                outline_data=outline,
            )
        )
        session.commit()

    import app.orchestration.agents.course_resources as module

    original_factory = module.ChatPromptTemplate
    module.ChatPromptTemplate = PromptFactory
    monkeypatch.setattr(module, "_find_verified_video_from_search", verified_search)
    try:
        result = asyncio.run(
            run_section_video_search_agent(
                {
                    "user_id": "user-1",
                    "course_knowledge": outline,
                    "course_resource_plan": {
                        "course_id": "year_3_course_1",
                        "target_section_ids": ["1.1"],
                    },
                    "messages": [],
                },
                RecordingLlm(),
            )
        )
    finally:
        module.ChatPromptTemplate = original_factory

    assert captured["attempts"] == 0
    assert captured["search_attempts"] == 2
    videos = result["course_knowledge"]["section_video_links"]["1.1"]["videos"]
    assert videos[0]["url"] == "https://www.youtube.com/watch?v=dummy-retried-video"


def test_run_section_video_search_agent_saves_first_verified_search_result(
    tmp_path, monkeypatch
) -> None:
    class RecordingLlm:
        pass

    class VideoChain:
        async def ainvoke(self, payload):
            captured["queries"].append(payload["query"])
            captured["attempts"] += 1
            if captured["attempts"] == 1:
                return SectionVideoSearchOutput(
                    section_id="1.1",
                    query="AI 应用开发 学习目标 视频教程",
                    videos=[
                        {
                            "brief_id": "video_1",
                            "title": "通用课程首页",
                            "url": "https://www.youtube.com/watch?v=dummy-generic-video",
                            "cover_url": "",
                            "source": "example.com",
                        }
                    ],
                )
            return SectionVideoSearchOutput(
                section_id="1.1",
                query="AI 应用开发 学习目标 功能边界 验收标准 视频教程",
                videos=[
                    {
                        "brief_id": "video_1",
                        "title": "学习目标：功能边界与验收标准实战讲解",
                        "url": "https://www.youtube.com/watch?v=dummy-repaired-video",
                        "cover_url": "",
                        "source": "example.com",
                    }
                ],
            )

    class VideoPrompt:
        def __or__(self, _other):
            return VideoChain()

    class PromptFactory:
        @staticmethod
        def from_messages(_messages):
            return VideoPrompt()

    async def verified_search(_video_briefs, _section, _outline=None):
        captured["search_attempts"] += 1
        if captured["search_attempts"] == 1:
            return [
                {
                    "brief_id": "video_1",
                    "title": "通用课程首页",
                    "url": "https://www.youtube.com/watch?v=dummy-generic-video",
                    "cover_url": "",
                    "source": "example.com",
                }
            ]
        return [
            {
                "brief_id": "video_1",
                "title": "学习目标：功能边界与验收标准实战讲解",
                "url": "https://www.youtube.com/watch?v=dummy-repaired-video",
                "cover_url": "",
                "source": "example.com",
            }
        ]

    outline = _outline()
    outline["section_markdowns"] = {
        "1.1": {
            "section_id": "1.1",
            "parent_section_id": "1",
            "title": "学习目标",
            "markdown": _complete_section_markdown("1.1", "学习目标"),
            "video_briefs": [
                {
                    "video_id": "video_1",
                    "title": "学习目标导入视频",
                    "purpose": "帮助学习者建立功能边界与验收标准的直觉",
                }
            ],
            "animation_briefs": [],
            "generated_at": "2026-06-06T00:00:00Z",
        }
    }
    captured = {"schema": None, "queries": [], "attempts": 0, "search_attempts": 0}
    engine = build_engine(postgresql_test_url(tmp_path, "section-video-quality-repair"))
    set_engine(engine)
    init_db(engine)
    with Session(engine) as session:
        session.add(
            User(uid="user-1", username="课程用户", identifier="course@example.com")
        )
        session.add(
            UserCourseKnowledgeOutline(
                user_uid="user-1",
                course_id="year_3_course_1",
                grade_year="year_3",
                course_name="AI 应用开发",
                outline_data=outline,
            )
        )
        session.commit()

    import app.orchestration.agents.course_resources as module

    original_factory = module.ChatPromptTemplate
    module.ChatPromptTemplate = PromptFactory
    monkeypatch.setattr(module, "_find_verified_video_from_search", verified_search)
    try:
        result = asyncio.run(
            run_section_video_search_agent(
                {
                    "user_id": "user-1",
                    "course_knowledge": outline,
                    "course_resource_plan": {
                        "course_id": "year_3_course_1",
                        "target_section_ids": ["1.1"],
                    },
                    "messages": [],
                },
                RecordingLlm(),
            )
        )
    finally:
        module.ChatPromptTemplate = original_factory

    assert "error" not in result
    assert captured["attempts"] == 0
    assert captured["search_attempts"] == 1
    videos = result["course_knowledge"]["section_video_links"]["1.1"]["videos"]
    assert videos[0]["url"] == "https://www.youtube.com/watch?v=dummy-generic-video"


def test_run_section_video_search_agent_uses_verified_search_when_llm_videos_stay_bad(
    tmp_path, monkeypatch
) -> None:
    class RecordingLlm:
        pass

    class VideoChain:
        async def ainvoke(self, payload):
            captured["queries"].append(payload["query"])
            captured["attempts"] += 1
            return SectionVideoSearchOutput(
                section_id="1.1",
                query="AI 应用开发 学习目标 视频教程",
                videos=[
                    {
                        "brief_id": "video_1",
                        "title": "通用课程首页",
                        "url": "https://www.youtube.com/watch?v=dummy-generic-video",
                        "cover_url": "",
                        "source": "example.com",
                    }
                ],
            )

    class VideoPrompt:
        def __or__(self, _other):
            return VideoChain()

    class PromptFactory:
        @staticmethod
        def from_messages(_messages):
            return VideoPrompt()

    async def verified_search(_video_briefs, _section, _outline=None):
        captured["verified_search"] += 1
        return [
            {
                "brief_id": "video_1",
                "title": "学习目标：功能边界与验收标准真实视频",
                "url": "https://www.bilibili.com/video/BV1verified0",
                "cover_url": "",
                "source": "Bilibili",
            }
        ]

    outline = _outline()
    outline["section_markdowns"] = {
        "1.1": {
            "section_id": "1.1",
            "parent_section_id": "1",
            "title": "学习目标",
            "markdown": _complete_section_markdown("1.1", "学习目标"),
            "video_briefs": [
                {
                    "video_id": "video_1",
                    "title": "学习目标导入视频",
                    "purpose": "帮助学习者建立功能边界与验收标准的直觉",
                }
            ],
            "animation_briefs": [],
            "generated_at": "2026-06-06T00:00:00Z",
        }
    }
    captured = {"schema": None, "queries": [], "attempts": 0, "verified_search": 0}
    engine = build_engine(
        postgresql_test_url(tmp_path, "section-video-verified-search")
    )
    set_engine(engine)
    init_db(engine)
    with Session(engine) as session:
        session.add(
            User(uid="user-1", username="课程用户", identifier="course@example.com")
        )
        session.add(
            UserCourseKnowledgeOutline(
                user_uid="user-1",
                course_id="year_3_course_1",
                grade_year="year_3",
                course_name="AI 应用开发",
                outline_data=outline,
            )
        )
        session.commit()

    import app.orchestration.agents.course_resources as module

    async def verified_metadata(_url: str) -> dict:
        return {
            "status": "ok",
            "text": "AI 应用开发 学习目标 功能边界 验收标准",
            "title": "学习目标：功能边界与验收标准真实视频",
        }

    original_factory = module.ChatPromptTemplate
    module.ChatPromptTemplate = PromptFactory
    monkeypatch.setattr(module, "_find_verified_video_from_search", verified_search)
    monkeypatch.setattr(module, "_verify_bilibili_video_metadata", verified_metadata)
    try:
        result = asyncio.run(
            run_section_video_search_agent(
                {
                    "user_id": "user-1",
                    "course_knowledge": outline,
                    "course_resource_plan": {
                        "course_id": "year_3_course_1",
                        "target_section_ids": ["1.1"],
                    },
                    "messages": [],
                },
                RecordingLlm(),
            )
        )
    finally:
        module.ChatPromptTemplate = original_factory

    assert "error" not in result
    assert captured["attempts"] == 0
    assert captured["verified_search"] == 1
    videos = result["course_knowledge"]["section_video_links"]["1.1"]["videos"]
    assert videos[0]["url"] == "https://www.bilibili.com/video/BV1verified0"


def test_run_section_video_search_agent_uses_verified_search_when_llm_returns_empty_videos(
    tmp_path, monkeypatch
) -> None:
    class RecordingLlm:
        pass

    class VideoChain:
        async def ainvoke(self, payload):
            captured["queries"].append(payload["query"])
            captured["attempts"] += 1
            return SectionVideoSearchOutput(
                section_id="1.1",
                query="构建本地知识库问答系统 文档解析 文本分块 视频教程",
                videos=[],
            )

    class VideoPrompt:
        def __or__(self, _other):
            return VideoChain()

    class PromptFactory:
        @staticmethod
        def from_messages(_messages):
            return VideoPrompt()

    async def verified_search(_video_briefs, _section, _outline=None):
        captured["verified_search"] += 1
        return [
            {
                "brief_id": "video_1",
                "title": "RAG 本地知识库文档切分与向量检索实战",
                "url": "https://www.bilibili.com/video/BV1ragchunk1",
                "cover_url": "",
                "source": "Bilibili",
            }
        ]

    async def verify_metadata(_url: str) -> dict:
        return {
            "status": "ok",
            "text": "RAG 本地知识库实战：文档解析、文本切分、chunk_size、overlap 与向量检索完整流程",
            "title": "RAG 本地知识库文档切分与向量检索实战",
        }

    outline = _outline()
    outline["course_name"] = "构建本地知识库问答系统 (RAG基础)"
    outline["sections"] = [
        {
            "section_id": "1",
            "parent_section_id": None,
            "depth": 1,
            "title": "非结构化文档解析与智能分块",
            "order_index": 1,
            "description": "围绕 RAG 的文档解析、文本分块与向量化准备展开。",
            "key_knowledge_points": ["PDF 文档解析", "文本分块", "向量化准备"],
        },
        {
            "section_id": "1.1",
            "parent_section_id": "1",
            "depth": 2,
            "title": "文档解析到分块的处理链路",
            "order_index": 2,
            "description": "理解原始文档如何变成可检索片段。",
            "key_knowledge_points": ["非结构化文档解析", "chunk_size", "chunk_overlap"],
        },
    ]
    outline["section_markdowns"] = {
        "1.1": {
            "section_id": "1.1",
            "parent_section_id": "1",
            "title": "文档解析到分块的处理链路",
            "markdown": _complete_section_markdown("1.1", "文档解析到分块的处理链路"),
            "video_briefs": [
                {
                    "video_id": "video_1",
                    "title": "PDF Loader Splitter Embedder 串联演示",
                    "purpose": "展示 PDF 文件如何流经 Loader、Splitter、Embedder 并进入 Vector DB。",
                }
            ],
            "animation_briefs": [],
            "generated_at": "2026-06-06T00:00:00Z",
        }
    }
    captured = {"schema": None, "queries": [], "attempts": 0, "verified_search": 0}
    engine = build_engine(
        postgresql_test_url(tmp_path, "section-video-empty-direct-search")
    )
    set_engine(engine)
    init_db(engine)
    with Session(engine) as session:
        session.add(
            User(uid="user-1", username="课程用户", identifier="course@example.com")
        )
        session.add(
            UserCourseKnowledgeOutline(
                user_uid="user-1",
                course_id="year_3_course_1",
                grade_year="year_3",
                course_name=outline["course_name"],
                outline_data=outline,
            )
        )
        session.commit()

    import app.orchestration.agents.course_resources as module

    original_factory = module.ChatPromptTemplate
    module.ChatPromptTemplate = PromptFactory
    monkeypatch.setattr(module, "_find_verified_video_from_search", verified_search)
    monkeypatch.setattr(module, "_verify_bilibili_video_metadata", verify_metadata)
    try:
        result = asyncio.run(
            run_section_video_search_agent(
                {
                    "user_id": "user-1",
                    "course_knowledge": outline,
                    "course_resource_plan": {
                        "course_id": "year_3_course_1",
                        "target_section_ids": ["1.1"],
                    },
                    "messages": [],
                },
                RecordingLlm(),
            )
        )
    finally:
        module.ChatPromptTemplate = original_factory

    assert "error" not in result
    assert captured["attempts"] == 0
    assert captured["verified_search"] == 1
    videos = result["course_knowledge"]["section_video_links"]["1.1"]["videos"]
    assert videos[0]["url"] == "https://www.bilibili.com/video/BV1ragchunk1"


def test_run_section_video_search_agent_retries_verified_search_when_first_scan_finds_nothing(
    tmp_path, monkeypatch
) -> None:
    class RecordingLlm:
        pass

    class VideoChain:
        async def ainvoke(self, payload):
            captured["queries"].append(payload["query"])
            captured["attempts"] += 1
            return SectionVideoSearchOutput(
                section_id="1.1",
                query="AI 应用开发 学习目标 视频教程",
                videos=[
                    {
                        "brief_id": "video_1",
                        "title": "通用课程首页",
                        "url": "https://example.com/generic-video",
                        "cover_url": "",
                        "source": "example.com",
                    }
                ],
            )

    class VideoPrompt:
        def __or__(self, _other):
            return VideoChain()

    class PromptFactory:
        @staticmethod
        def from_messages(_messages):
            return VideoPrompt()

    async def verified_search(_video_briefs, _section, _outline=None):
        captured["verified_search"] += 1
        if captured["verified_search"] == 1:
            return []
        return [
            {
                "brief_id": "video_1",
                "title": "学习目标：功能边界与验收标准真实视频",
                "url": "https://www.bilibili.com/video/BV1verified0",
                "cover_url": "",
                "source": "Bilibili",
            }
        ]

    outline = _outline()
    outline["section_markdowns"] = {
        "1.1": {
            "section_id": "1.1",
            "parent_section_id": "1",
            "title": "学习目标",
            "markdown": _complete_section_markdown("1.1", "学习目标"),
            "video_briefs": [
                {
                    "video_id": "video_1",
                    "title": "学习目标导入视频",
                    "purpose": "帮助学习者建立功能边界与验收标准的直觉",
                }
            ],
            "animation_briefs": [],
            "generated_at": "2026-06-06T00:00:00Z",
        }
    }
    captured = {"schema": None, "queries": [], "attempts": 0, "verified_search": 0}
    engine = build_engine(
        postgresql_test_url(tmp_path, "section-video-verified-search-retry")
    )
    set_engine(engine)
    init_db(engine)
    with Session(engine) as session:
        session.add(
            User(uid="user-1", username="课程用户", identifier="course@example.com")
        )
        session.add(
            UserCourseKnowledgeOutline(
                user_uid="user-1",
                course_id="year_3_course_1",
                grade_year="year_3",
                course_name="AI 应用开发",
                outline_data=outline,
            )
        )
        session.commit()

    import app.orchestration.agents.course_resources as module

    async def verified_metadata(_url: str) -> dict:
        return {
            "status": "ok",
            "text": "AI 应用开发 学习目标 功能边界 验收标准",
            "title": "学习目标：功能边界与验收标准真实视频",
        }

    original_factory = module.ChatPromptTemplate
    module.ChatPromptTemplate = PromptFactory
    monkeypatch.setattr(module, "_find_verified_video_from_search", verified_search)
    monkeypatch.setattr(module, "_verify_bilibili_video_metadata", verified_metadata)
    try:
        result = asyncio.run(
            run_section_video_search_agent(
                {
                    "user_id": "user-1",
                    "course_knowledge": outline,
                    "course_resource_plan": {
                        "course_id": "year_3_course_1",
                        "target_section_ids": ["1.1"],
                    },
                    "messages": [],
                },
                RecordingLlm(),
            )
        )
    finally:
        module.ChatPromptTemplate = original_factory

    assert "error" not in result
    assert captured["attempts"] == 0
    assert captured["verified_search"] == 2
    videos = result["course_knowledge"]["section_video_links"]["1.1"]["videos"]
    assert videos[0]["url"] == "https://www.bilibili.com/video/BV1verified0"


def test_run_section_video_search_agent_accepts_course_specific_video_metadata(
    tmp_path, monkeypatch
) -> None:
    class RecordingLlm:
        pass

    class VideoChain:
        async def ainvoke(self, payload):
            captured["queries"].append(payload["query"])
            return SectionVideoSearchOutput(
                section_id="1.1",
                query="AI 应用基础架构 向量数据库 Embedding 教程",
                videos=[
                    {
                        "brief_id": "video_1",
                        "title": "Embedding 原理与向量数据库实战",
                        "url": "https://www.bilibili.com/video/BV1courseok1",
                        "cover_url": "",
                        "source": "Bilibili",
                    }
                ],
            )

    class VideoPrompt:
        def __or__(self, _other):
            return VideoChain()

    class PromptFactory:
        @staticmethod
        def from_messages(_messages):
            return VideoPrompt()

    async def verified_search(_video_briefs, _section, _outline=None):
        captured["verified_search"] += 1
        return [
            {
                "brief_id": "video_1",
                "title": "Embedding 原理与向量数据库实战",
                "url": "https://www.bilibili.com/video/BV1courseok1",
                "cover_url": "",
                "source": "Bilibili",
            }
        ]

    async def verify_metadata(_url: str) -> dict:
        return {
            "status": "ok",
            "text": "Embedding 原理 向量数据库 非结构化数据处理 实战讲解",
            "title": "Embedding 原理与向量数据库实战",
        }

    outline = _outline()
    outline["course_name"] = "AI 应用基础架构：向量数据库与非结构化数据处理"
    outline["section_markdowns"] = {
        "1.1": {
            "section_id": "1.1",
            "parent_section_id": "1",
            "title": "学习目标",
            "markdown": _complete_section_markdown("1.1", "学习目标"),
            "video_briefs": [
                {
                    "video_id": "video_1",
                    "title": "Embedding 原理可视化",
                    "purpose": "帮助学习者理解向量数据库与 Embedding 的核心概念",
                }
            ],
            "animation_briefs": [],
            "generated_at": "2026-06-06T00:00:00Z",
        }
    }
    for section in outline["sections"]:
        if isinstance(section, dict) and section.get("section_id") == "1.1":
            section["key_knowledge_points"] = ["向量数据库", "Embedding 原理"]

    captured = {"schema": None, "queries": [], "verified_search": 0}
    engine = build_engine(postgresql_test_url(tmp_path, "section-video-course-topic"))
    set_engine(engine)
    init_db(engine)
    with Session(engine) as session:
        session.add(
            User(uid="user-1", username="课程用户", identifier="course@example.com")
        )
        session.add(
            UserCourseKnowledgeOutline(
                user_uid="user-1",
                course_id="year_3_course_1",
                grade_year="year_3",
                course_name=outline["course_name"],
                outline_data=outline,
            )
        )
        session.commit()

    import app.orchestration.agents.course_resources as module

    original_factory = module.ChatPromptTemplate
    module.ChatPromptTemplate = PromptFactory
    monkeypatch.setattr(module, "_find_verified_video_from_search", verified_search)
    monkeypatch.setattr(module, "_verify_bilibili_video_metadata", verify_metadata)
    try:
        result = asyncio.run(
            run_section_video_search_agent(
                {
                    "user_id": "user-1",
                    "course_knowledge": outline,
                    "course_resource_plan": {
                        "course_id": "year_3_course_1",
                        "target_section_ids": ["1.1"],
                    },
                    "messages": [],
                },
                RecordingLlm(),
            )
        )
    finally:
        module.ChatPromptTemplate = original_factory

    assert "error" not in result
    assert captured["queries"] == []
    assert captured["verified_search"] == 1
    videos = result["course_knowledge"]["section_video_links"]["1.1"]["videos"]
    assert videos[0]["title"] == "Embedding 原理与向量数据库实战"


def test_run_section_video_search_agent_accepts_section_topic_match_without_course_name(
    tmp_path, monkeypatch
) -> None:
    class RecordingLlm:
        pass

    async def verified_search(_video_briefs, _section, _outline=None):
        return [
            {
                "brief_id": "video_1",
                "title": "State对象设计与序列化约束 TypedDict 与 Pydantic 实战讲解",
                "url": "https://www.youtube.com/watch?v=dummy-langgraph-state",
                "cover_url": "",
                "source": "LangGraph 教学",
            }
        ]

    outline = {
        "course_id": "year_3_course_1",
        "course_name": "基于状态图的Agent流程编排实战",
        "grade_year": "year_3",
        "sections": [
            {
                "section_id": "1",
                "parent_section_id": None,
                "depth": 1,
                "order_index": 1,
                "title": "LangGraph核心抽象与最小流程搭建",
                "description": "围绕最小状态图搭建首个可执行流程。",
                "key_knowledge_points": ["State", "Node", "Edge"],
            },
            {
                "section_id": "1.2",
                "parent_section_id": "1",
                "depth": 2,
                "order_index": 2,
                "title": "State对象设计与序列化约束",
                "description": "理解状态对象字段设计和序列化边界。",
                "key_knowledge_points": ["TypedDict", "Pydantic", "序列化约束"],
            },
        ],
        "section_markdowns": {
            "1.2": {
                "section_id": "1.2",
                "parent_section_id": "1",
                "title": "State对象设计与序列化约束",
                "markdown": _complete_section_markdown(
                    "1.2", "State对象设计与序列化约束"
                ),
                "video_briefs": [
                    {
                        "video_id": "video_1",
                        "title": "State对象设计与序列化约束导入视频",
                        "purpose": "帮助学习者理解 TypedDict 与 Pydantic 在 State 设计中的选型差异。",
                    }
                ],
                "animation_briefs": [],
                "generated_at": "2026-06-06T00:00:00Z",
            }
        },
    }
    engine = build_engine(
        postgresql_test_url(tmp_path, "section-video-langgraph-topic")
    )
    set_engine(engine)
    init_db(engine)
    with Session(engine) as session:
        session.add(
            User(uid="user-1", username="课程用户", identifier="course@example.com")
        )
        session.add(
            UserCourseKnowledgeOutline(
                user_uid="user-1",
                course_id="year_3_course_1",
                grade_year="year_3",
                course_name=outline["course_name"],
                outline_data=outline,
            )
        )
        session.commit()

    import app.orchestration.agents.course_resources as module

    monkeypatch.setattr(module, "_find_verified_video_from_search", verified_search)

    result = asyncio.run(
        run_section_video_search_agent(
            {
                "user_id": "user-1",
                "course_knowledge": outline,
                "course_resource_plan": {
                    "course_id": "year_3_course_1",
                    "target_section_ids": ["1.2"],
                },
                "messages": [],
            },
            RecordingLlm(),
        )
    )

    assert "error" not in result
    videos = result["course_knowledge"]["section_video_links"]["1.2"]["videos"]
    assert videos[0]["url"] == "https://www.youtube.com/watch?v=dummy-langgraph-state"


def test_run_section_video_search_agent_returns_hard_error_when_verified_search_stays_empty(
    tmp_path, monkeypatch
) -> None:
    class RecordingLlm:
        pass

    async def verified_search(_video_briefs, _section, _outline=None):
        return []

    outline = _outline()
    outline["section_markdowns"] = {
        "1.1": {
            "section_id": "1.1",
            "parent_section_id": "1",
            "title": "学习目标",
            "markdown": _complete_section_markdown("1.1", "学习目标"),
            "video_briefs": [
                {
                    "video_id": "video_1",
                    "title": "学习目标导入视频",
                    "purpose": "帮助学习者建立功能边界与验收标准的直觉",
                }
            ],
            "animation_briefs": [],
            "generated_at": "2026-06-06T00:00:00Z",
        }
    }
    engine = build_engine(
        postgresql_test_url(tmp_path, "section-video-search-fallback")
    )
    set_engine(engine)
    init_db(engine)
    with Session(engine) as session:
        session.add(
            User(uid="user-1", username="课程用户", identifier="course@example.com")
        )
        session.add(
            UserCourseKnowledgeOutline(
                user_uid="user-1",
                course_id="year_3_course_1",
                grade_year="year_3",
                course_name="AI 应用开发",
                outline_data=outline,
            )
        )
        session.commit()

    import app.orchestration.agents.course_resources as module

    monkeypatch.setattr(module, "_find_verified_video_from_search", verified_search)

    result = asyncio.run(
        run_section_video_search_agent(
            {
                "user_id": "user-1",
                "course_knowledge": outline,
                "course_resource_plan": {
                    "course_id": "year_3_course_1",
                    "target_section_ids": ["1.1"],
                },
                "messages": [],
            },
            RecordingLlm(),
        )
    )

    assert result["hard_error"] is True
    assert result["error"] == "课程资源生成失败：小节 1.1 未找到合格视频。"
    section_video = result["course_knowledge"]["section_video_links"]["1.1"]
    assert section_video["status"] == "unavailable"
    assert (
        section_video["failure_reason"]
        == "未找到合格视频：视频资源为空或未绑定 brief。"
    )


def test_run_section_video_search_agent_returns_hard_error_when_verified_search_times_out(
    tmp_path, monkeypatch, caplog
) -> None:
    class RecordingLlm:
        pass

    async def slow_verified_search(_video_briefs, _section, _outline=None):
        await asyncio.sleep(0.05)
        return []

    outline = _outline()
    outline["section_markdowns"] = {
        "1.1": {
            "section_id": "1.1",
            "parent_section_id": "1",
            "title": "学习目标",
            "markdown": _complete_section_markdown("1.1", "学习目标"),
            "video_briefs": [
                {
                    "video_id": "video_1",
                    "title": "学习目标导入视频",
                    "purpose": "帮助学习者建立功能边界与验收标准的直觉",
                }
            ],
            "animation_briefs": [],
            "generated_at": "2026-06-06T00:00:00Z",
        }
    }
    engine = build_engine(postgresql_test_url(tmp_path, "section-video-search-timeout"))
    set_engine(engine)
    init_db(engine)
    with Session(engine) as session:
        session.add(
            User(uid="user-1", username="课程用户", identifier="course@example.com")
        )
        session.add(
            UserCourseKnowledgeOutline(
                user_uid="user-1",
                course_id="year_3_course_1",
                grade_year="year_3",
                course_name="AI 应用开发",
                outline_data=outline,
            )
        )
        session.commit()

    import app.orchestration.agents.course_resources as module

    monkeypatch.setattr(
        module, "_find_verified_video_from_search", slow_verified_search
    )
    monkeypatch.setattr(module, "_VIDEO_SECTION_TIMEOUT_SECONDS", 0.001)

    result = asyncio.run(
        run_section_video_search_agent(
            {
                "user_id": "user-1",
                "course_knowledge": outline,
                "course_resource_plan": {
                    "course_id": "year_3_course_1",
                    "target_section_ids": ["1.1"],
                },
                "messages": [],
            },
            RecordingLlm(),
        )
    )

    assert result["hard_error"] is True
    assert result["error"] == "课程资源生成失败：小节 1.1 未找到合格视频。"
    section_video = result["course_knowledge"]["section_video_links"]["1.1"]
    assert section_video["status"] == "unavailable"
    assert section_video["failure_reason"] == "未找到合格视频：视频检索超时。"
    assert section_video["videos"] == []
    assert "Video search timed out for section 1.1" in caplog.text


def test_find_verified_video_from_search_only_waits_for_youtube_on_first_query(
    monkeypatch,
) -> None:
    import app.orchestration.agents.course_resources as module

    platform_calls = {"bilibili": 0, "youtube": 0}

    async def bilibili_search(_query: str) -> list[dict]:
        platform_calls["bilibili"] += 1
        return []

    async def youtube_search(_query: str) -> list[dict]:
        platform_calls["youtube"] += 1
        return []

    monkeypatch.setattr(module, "_search_bilibili_video_results", bilibili_search)
    monkeypatch.setattr(module, "_search_youtube_video_results", youtube_search)

    videos = asyncio.run(
        _find_verified_video_from_search(
            [
                {
                    "video_id": "video_1",
                    "title": "算法效率",
                    "purpose": "理解算法效率的必要性",
                }
            ],
            {
                "section_id": "1.1",
                "title": "效率需求的背景",
                "description": "解释算法效率的必要性。",
                "key_knowledge_points": ["算法效率"],
            },
            None,
        )
    )

    assert videos == []
    assert platform_calls == {
        "bilibili": video_module._VIDEO_VERIFIED_QUERY_LIMIT,
        "youtube": 1,
    }


def test_find_verified_video_from_search_validates_query_candidates_concurrently(
    monkeypatch,
) -> None:
    import app.orchestration.agents.course_resources as module

    active_validations = 0
    max_active_validations = 0

    async def bilibili_search(_query: str) -> list[dict]:
        return [
            {
                "title": "算法效率与基本操作计数入门",
                "url": "https://www.bilibili.com/video/BV1AlgoEff01",
                "cover_url": "",
                "source": "Bilibili",
            },
            {
                "title": "算法效率与基本操作计数进阶",
                "url": "https://www.bilibili.com/video/BV1AlgoEff02",
                "cover_url": "",
                "source": "Bilibili",
            },
        ]

    async def youtube_search(_query: str) -> list[dict]:
        return []

    async def verify_metadata(url: str) -> dict:
        nonlocal active_validations, max_active_validations
        active_validations += 1
        max_active_validations = max(max_active_validations, active_validations)
        await asyncio.sleep(0.01)
        active_validations -= 1
        return {
            "status": "ok",
            "text": "算法效率 基本操作计数 处理器速度 复杂度",
            "title": (
                "算法效率与基本操作计数入门"
                if url.endswith("01")
                else "算法效率与基本操作计数进阶"
            ),
        }

    monkeypatch.setattr(module, "_search_bilibili_video_results", bilibili_search)
    monkeypatch.setattr(module, "_search_youtube_video_results", youtube_search)
    monkeypatch.setattr(module, "_verify_bilibili_video_metadata", verify_metadata)

    videos = asyncio.run(
        _find_verified_video_from_search(
            [
                {
                    "video_id": "video_1",
                    "title": "算法效率与基本操作计数",
                    "purpose": "理解算法效率的必要性与基本操作计数",
                }
            ],
            {
                "section_id": "1.1",
                "title": "效率需求的背景",
                "description": "解释算法效率的必要性。",
                "key_knowledge_points": ["算法效率", "基本操作计数"],
            },
            None,
        )
    )

    assert videos
    assert max_active_validations == 2


def test_find_verified_video_from_search_logs_platform_latency(monkeypatch, caplog):
    import app.orchestration.agents.course_resources as module

    caplog.set_level(
        logging.INFO, logger="app.orchestration.agents.course_resources.video"
    )

    async def empty_search(_query):
        return []

    monkeypatch.setattr(module, "_search_bilibili_video_results", empty_search)
    monkeypatch.setattr(module, "_search_youtube_video_results", empty_search)

    result = asyncio.run(
        _find_verified_video_from_search(
            [{"video_id": "video_1", "title": "学习目标导入视频"}],
            {
                "section_id": "1.1",
                "title": "学习目标",
                "description": "明确本节学习目标。",
                "key_knowledge_points": ["功能边界"],
            },
            {},
        )
    )

    assert result == []
    assert "platform=bilibili" in caplog.text
    assert "platform=youtube" in caplog.text


def test_run_section_video_search_agent_rejects_missing_textbook_evidence(
    tmp_path,
    monkeypatch,
) -> None:
    from tests.fixtures.knowledge_base import enabled_source, published_textbook
    from tests.fixtures.knowledge_base import section as k_section

    class RecordingLlm:
        pass

    async def verified_search(_video_briefs, _section, _outline=None):
        raise AssertionError("缺少教材证据时不应搜索视频。")

    outline = _outline()
    outline["sections"][1]["source_textbook_id"] = "textbook-video-missing-evidence"
    outline["sections"][1]["source_textbook_title"] = "视频证据教材"
    outline["sections"][1]["source_section_ids"] = ["9.9"]
    outline["sections"][1]["source_section_titles"] = ["不存在的小节"]
    outline["sections"][1]["source_content_chars"] = 100
    outline["section_markdowns"] = {
        "1.1": {
            "section_id": "1.1",
            "parent_section_id": "1",
            "title": "学习目标",
            "markdown": _complete_section_markdown("1.1", "学习目标"),
            "video_briefs": [
                {
                    "video_id": "video_1",
                    "title": "学习目标导入视频",
                    "purpose": "帮助学习者建立功能边界与验收标准的直觉",
                }
            ],
            "animation_briefs": [],
            "generated_at": "2026-06-06T00:00:00Z",
        }
    }
    engine = build_engine(
        postgresql_test_url(tmp_path, "section-video-missing-evidence")
    )
    set_engine(engine)
    init_db(engine)
    with Session(engine) as session:
        session.add(
            User(uid="user-1", username="课程用户", identifier="course@example.com")
        )
        session.add(enabled_source(source_id="source-video-evidence"))
        tb = published_textbook(
            textbook_id="textbook-video-missing-evidence",
            source_id="source-video-evidence",
            title="视频证据教材",
        )
        tb.outline = {"sections": [{"section_id": "1.1", "title": "存在的小节"}]}
        session.add(tb)
        session.add(
            k_section(
                textbook_id="textbook-video-missing-evidence",
                section_content_id="video-existing-section",
                section_id="1.1",
                title="存在的小节",
                content_zh="存在的小节正文。",
            )
        )
        session.commit()

    import app.orchestration.agents.course_resources as module

    monkeypatch.setattr(module, "_find_verified_video_from_search", verified_search)

    result = asyncio.run(
        run_section_video_search_agent(
            {
                "user_id": "user-1",
                "course_knowledge": outline,
                "course_resource_plan": {
                    "course_id": "year_3_course_1",
                    "target_section_ids": ["1.1"],
                },
                "messages": [],
            },
            RecordingLlm(),
        )
    )

    assert result == {"error": "教材小节不存在。", "hard_error": True}


from app.orchestration.agents.course_resources import run_section_html_animation_agent


def test_run_section_html_animation_agent_uses_animation_briefs(tmp_path) -> None:
    from tests.fixtures.knowledge_base import enabled_source, published_textbook
    from tests.fixtures.knowledge_base import section as k_section

    class RecordingLlm:
        pass

    class AnimationChain:
        async def ainvoke(self, payload):
            captured["queries"].append(payload["query"])
            return SectionHtmlAnimationOutput(
                section_id="1.1",
                animations=[
                    {
                        "animation_id": "section-1-1-animation-1",
                        "title": "目标到验收标准",
                        "html": _complete_animation_html(
                            "section-1-1-animation-1",
                            "目标到验收标准",
                            "展示学习目标如何收敛为验收标准",
                            ["学习目标", "验收标准", "完成证据"],
                        ),
                    }
                ],
            )

    class AnimationPrompt:
        def __or__(self, _other):
            return AnimationChain()

    class PromptFactory:
        @staticmethod
        def from_messages(_messages):
            return AnimationPrompt()

    outline = _outline()
    outline["sections"][1]["source_textbook_id"] = "textbook-animation-evidence"
    outline["sections"][1]["source_textbook_title"] = "动画证据教材"
    outline["sections"][1]["source_section_ids"] = ["1.1"]
    outline["sections"][1]["source_section_titles"] = ["目标到验收标准"]
    outline["sections"][1]["source_content_chars"] = 100
    outline["section_markdowns"] = {
        "1.1": {
            "section_id": "1.1",
            "parent_section_id": "1",
            "title": "学习目标",
            "markdown": "# 学习目标\n\n完整教学内容",
            "video_briefs": [],
            "animation_briefs": [
                {
                    "animation_id": "section-1-1-animation-1",
                    "title": "目标到验收标准",
                    "concept": "展示学习目标如何收敛为验收标准",
                    "visual_elements": ["学习目标", "验收标准", "完成证据"],
                    "motion": "节点依次淡入",
                    "space": "正文宽度",
                    "placement_hint": "核心概念之后",
                }
            ],
            "generated_at": "2026-06-06T00:00:00Z",
        }
    }
    captured = {"schema": None, "queries": []}
    engine = build_engine(postgresql_test_url(tmp_path, "section-animation"))
    set_engine(engine)
    init_db(engine)
    with Session(engine) as session:
        session.add(
            User(uid="user-1", username="课程用户", identifier="course@example.com")
        )
        session.add(enabled_source(source_id="source-animation-evidence"))
        tb = published_textbook(
            textbook_id="textbook-animation-evidence",
            source_id="source-animation-evidence",
            title="动画证据教材",
        )
        tb.outline = {"sections": [{"section_id": "1.1", "title": "目标到验收标准"}]}
        session.add(tb)
        session.add(
            k_section(
                textbook_id="textbook-animation-evidence",
                section_content_id="animation-evidence-section",
                section_id="1.1",
                title="目标到验收标准",
                content_zh="动画证据正文来自知识库，描述学习目标如何收敛为验收标准。",
            )
        )
        session.add(
            UserCourseKnowledgeOutline(
                user_uid="user-1",
                course_id="year_3_course_1",
                grade_year="year_3",
                course_name="AI 应用开发",
                outline_data=outline,
            )
        )
        session.commit()

    import app.orchestration.agents.course_resources as module

    original_factory = module.ChatPromptTemplate
    module.ChatPromptTemplate = PromptFactory
    try:
        result = asyncio.run(
            run_section_html_animation_agent(
                {
                    "user_id": "user-1",
                    "course_knowledge": outline,
                    "profile": _profile(),
                    "year_learning_paths": _year_learning_paths(),
                    "course_resource_plan": {
                        "course_id": "year_3_course_1",
                        "target_section_ids": ["1.1"],
                    },
                    "messages": [],
                },
                RecordingLlm(),
            )
        )
    finally:
        module.ChatPromptTemplate = original_factory

    assert len(captured["queries"]) == 1
    assert '"profile"' in captured["queries"][0]
    assert '"year_learning_paths"' in captured["queries"][0]
    assert '"course_knowledge"' in captured["queries"][0]
    assert '"animation_briefs"' in captured["queries"][0]
    assert "动画证据正文来自知识库" in captured["queries"][0]
    assert '"每天 12 小时项目驱动"' in captured["queries"][0]
    assert "作品级 Agent 项目闭环" in captured["queries"][0]
    animations = result["course_knowledge"]["section_html_animations"]["1.1"][
        "animations"
    ]
    assert animations[0]["animation_id"] == "section-1-1-animation-1"
    assert "section-animation" in animations[0]["html"]
    assert result["course_resource_result"]["markdown_count"] == 1
    assert result["response"].startswith("《AI 应用开发》的 1.1 教学内容已生成")


def test_run_section_html_animation_agent_rejects_missing_textbook_evidence(
    tmp_path,
) -> None:
    from tests.fixtures.knowledge_base import enabled_source, published_textbook
    from tests.fixtures.knowledge_base import section as k_section

    class RecordingLlm:
        pass

    class ExplodingPrompt:
        def __or__(self, _other):
            raise AssertionError("缺少教材证据时不应调用动画 LLM。")

    class PromptFactory:
        @staticmethod
        def from_messages(_messages):
            return ExplodingPrompt()

    outline = _outline()
    outline["sections"][1]["source_textbook_id"] = "textbook-animation-missing"
    outline["sections"][1]["source_textbook_title"] = "动画缺证据教材"
    outline["sections"][1]["source_section_ids"] = ["9.9"]
    outline["sections"][1]["source_section_titles"] = ["不存在的小节"]
    outline["sections"][1]["source_content_chars"] = 100
    outline["section_markdowns"] = {
        "1.1": {
            "section_id": "1.1",
            "parent_section_id": "1",
            "title": "学习目标",
            "markdown": "# 学习目标\n\n完整教学内容",
            "video_briefs": [],
            "animation_briefs": [
                {
                    "animation_id": "section-1-1-animation-1",
                    "title": "目标到验收标准",
                    "concept": "展示学习目标如何收敛为验收标准",
                    "visual_elements": ["学习目标", "验收标准", "完成证据"],
                    "motion": "节点依次淡入",
                    "space": "正文宽度",
                    "placement_hint": "核心概念之后",
                }
            ],
            "generated_at": "2026-06-06T00:00:00Z",
        }
    }
    engine = build_engine(
        postgresql_test_url(tmp_path, "section-animation-missing-evidence")
    )
    set_engine(engine)
    init_db(engine)
    with Session(engine) as session:
        session.add(
            User(uid="user-1", username="课程用户", identifier="course@example.com")
        )
        session.add(enabled_source(source_id="source-animation-missing"))
        tb = published_textbook(
            textbook_id="textbook-animation-missing",
            source_id="source-animation-missing",
            title="动画缺证据教材",
        )
        tb.outline = {"sections": [{"section_id": "1.1", "title": "存在的小节"}]}
        session.add(tb)
        session.add(
            k_section(
                textbook_id="textbook-animation-missing",
                section_content_id="animation-existing-section",
                section_id="1.1",
                title="存在的小节",
                content_zh="存在的小节正文。",
            )
        )
        session.commit()

    import app.orchestration.agents.course_resources as module

    original_factory = module.ChatPromptTemplate
    module.ChatPromptTemplate = PromptFactory
    try:
        result = asyncio.run(
            run_section_html_animation_agent(
                {
                    "user_id": "user-1",
                    "course_knowledge": outline,
                    "profile": _profile(),
                    "year_learning_paths": _year_learning_paths(),
                    "course_resource_plan": {
                        "course_id": "year_3_course_1",
                        "target_section_ids": ["1.1"],
                    },
                    "messages": [],
                },
                RecordingLlm(),
            )
        )
    finally:
        module.ChatPromptTemplate = original_factory

    assert result == {"error": "教材小节不存在。", "hard_error": True}


def test_run_section_html_animation_agent_accepts_plain_html_model_output(
    tmp_path,
) -> None:
    class RecordingLlm:
        pass

    class AnimationChain:
        async def ainvoke(self, payload):
            captured["queries"].append(payload["query"])
            return _complete_animation_html(
                "section-1-1-animation-1",
                "目标到验收标准",
                "展示学习目标如何收敛为验收标准",
                ["学习目标", "验收标准", "完成证据"],
            )

    class AnimationPrompt:
        def __or__(self, _other):
            return AnimationChain()

    class PromptFactory:
        @staticmethod
        def from_messages(_messages):
            return AnimationPrompt()

    outline = _outline()
    outline["section_markdowns"] = {
        "1.1": {
            "section_id": "1.1",
            "parent_section_id": "1",
            "title": "学习目标",
            "markdown": "# 学习目标\n\n完整教学内容",
            "video_briefs": [],
            "animation_briefs": [
                {
                    "animation_id": "section-1-1-animation-1",
                    "title": "目标到验收标准",
                    "concept": "展示学习目标如何收敛为验收标准",
                    "visual_elements": ["学习目标", "验收标准", "完成证据"],
                    "motion": "节点依次淡入",
                    "space": "正文宽度",
                    "placement_hint": "核心概念之后",
                }
            ],
            "generated_at": "2026-06-06T00:00:00Z",
        }
    }
    captured = {"queries": []}
    engine = build_engine(postgresql_test_url(tmp_path, "section-animation-plain-html"))
    set_engine(engine)
    init_db(engine)
    with Session(engine) as session:
        session.add(
            User(uid="user-1", username="课程用户", identifier="course@example.com")
        )
        session.add(
            UserCourseKnowledgeOutline(
                user_uid="user-1",
                course_id="year_3_course_1",
                grade_year="year_3",
                course_name="AI 应用开发",
                outline_data=outline,
            )
        )
        session.commit()

    import app.orchestration.agents.course_resources as module

    original_factory = module.ChatPromptTemplate
    module.ChatPromptTemplate = PromptFactory
    try:
        result = asyncio.run(
            run_section_html_animation_agent(
                {
                    "user_id": "user-1",
                    "course_knowledge": outline,
                    "profile": _profile(),
                    "year_learning_paths": _year_learning_paths(),
                    "course_resource_plan": {
                        "course_id": "year_3_course_1",
                        "target_section_ids": ["1.1"],
                    },
                    "messages": [],
                },
                RecordingLlm(),
            )
        )
    finally:
        module.ChatPromptTemplate = original_factory

    assert len(captured["queries"]) == 1
    animations = result["course_knowledge"]["section_html_animations"]["1.1"][
        "animations"
    ]
    assert animations[0]["animation_id"] == "section-1-1-animation-1"
    assert "section-animation" in animations[0]["html"]
    assert result["course_resource_result"]["animation_count"] == 1


def test_run_section_html_animation_agent_generates_chapter_sections_concurrently(
    tmp_path,
) -> None:
    class RecordingLlm:
        pass

    class AnimationChain:
        async def ainvoke(self, payload):
            section_id = json.loads(payload["query"].split("输入：", 1)[1])[
                "target_section"
            ]["section_id"]
            captured["queries"].append(section_id)
            captured["inflight"] += 1
            captured["max_inflight"] = max(
                captured["max_inflight"], captured["inflight"]
            )
            await asyncio.sleep(0.05)
            captured["inflight"] -= 1
            return SectionHtmlAnimationOutput(
                section_id=section_id,
                animations=[
                    {
                        "animation_id": f"anim_{section_id.replace('.', '_')}",
                        "title": f"{section_id} 流程动画",
                        "html": _complete_animation_html(
                            f"anim_{section_id.replace('.', '_')}",
                            f"{section_id} 流程动画",
                            f"展示 {section_id} 如何从输入推进到验收",
                            [section_id, "验收标准", "完成证据"],
                        ),
                    }
                ],
            )

    class AnimationPrompt:
        def __or__(self, _other):
            return AnimationChain()

    class PromptFactory:
        @staticmethod
        def from_messages(_messages):
            return AnimationPrompt()

    outline = _outline()
    outline["section_markdowns"] = {}
    for section in outline["sections"]:
        section_id = section["section_id"]
        if not section_id.startswith("1."):
            continue
        outline["section_markdowns"][section_id] = {
            "section_id": section_id,
            "parent_section_id": "1",
            "title": section["title"],
            "markdown": f"# {section['title']}\n\n完整教学内容",
            "video_briefs": [],
            "animation_briefs": [
                {
                    "animation_id": f"anim_{section_id.replace('.', '_')}",
                    "title": f"{section['title']}流程动画",
                    "concept": f"展示 {section['title']} 如何从输入推进到验收",
                    "visual_elements": [section["title"], "验收标准", "完成证据"],
                    "motion": "节点依次淡入",
                    "space": "正文宽度",
                    "placement_hint": "核心概念之后",
                }
            ],
            "generated_at": "2026-06-06T00:00:00Z",
        }

    captured = {"queries": [], "inflight": 0, "max_inflight": 0}
    engine = build_engine(postgresql_test_url(tmp_path, "section-animation-concurrent"))
    set_engine(engine)
    init_db(engine)
    with Session(engine) as session:
        session.add(
            User(uid="user-1", username="课程用户", identifier="course@example.com")
        )
        session.add(
            UserCourseKnowledgeOutline(
                user_uid="user-1",
                course_id="year_3_course_1",
                grade_year="year_3",
                course_name="AI 应用开发",
                outline_data=outline,
            )
        )
        session.commit()

    import app.orchestration.agents.course_resources as module

    original_factory = module.ChatPromptTemplate
    module.ChatPromptTemplate = PromptFactory
    try:
        result = asyncio.run(
            run_section_html_animation_agent(
                {
                    "user_id": "user-1",
                    "course_knowledge": outline,
                    "profile": _profile(),
                    "year_learning_paths": _year_learning_paths(),
                    "course_resource_plan": {
                        "course_id": "year_3_course_1",
                        "target_section_ids": ["1.1", "1.2", "1.3"],
                    },
                    "messages": [],
                },
                RecordingLlm(),
            )
        )
    finally:
        module.ChatPromptTemplate = original_factory

    assert set(captured["queries"]) == {"1.1", "1.2", "1.3"}
    assert captured["max_inflight"] >= 2
    assert set(result["course_knowledge"]["section_html_animations"]) == {
        "1.1",
        "1.2",
        "1.3",
    }
    assert result["course_resource_result"]["animation_count"] == 3


def test_run_section_html_animation_agent_rebuilds_when_llm_unavailable(
    tmp_path,
) -> None:
    class RecordingLlm:
        pass

    class BrokenAnimationChain:
        async def ainvoke(self, payload):
            captured["queries"].append(payload["query"])
            raise RuntimeError("animation llm unavailable")

    class AnimationPrompt:
        def __or__(self, _other):
            return BrokenAnimationChain()

    class PromptFactory:
        @staticmethod
        def from_messages(_messages):
            return AnimationPrompt()

    outline = _outline()
    outline["section_markdowns"] = {
        "1.1": {
            "section_id": "1.1",
            "parent_section_id": "1",
            "title": "学习目标",
            "markdown": "# 学习目标\n\n完整教学内容",
            "video_briefs": [],
            "animation_briefs": [
                {
                    "animation_id": "section-1-1-animation-1",
                    "title": "目标到验收标准",
                    "concept": "展示学习目标如何收敛为验收标准",
                    "visual_elements": ["学习目标", "验收标准", "完成证据"],
                    "motion": "节点依次淡入并连接到最终验收。",
                    "space": "正文宽度",
                    "placement_hint": "核心概念之后",
                }
            ],
            "generated_at": "2026-06-06T00:00:00Z",
        }
    }
    captured = {"schema": None, "queries": []}
    engine = build_engine(
        postgresql_test_url(tmp_path, "section-animation-local-fallback")
    )
    set_engine(engine)
    init_db(engine)
    with Session(engine) as session:
        session.add(
            User(uid="user-1", username="课程用户", identifier="course@example.com")
        )
        session.add(
            UserCourseKnowledgeOutline(
                user_uid="user-1",
                course_id="year_3_course_1",
                grade_year="year_3",
                course_name="AI 应用开发",
                outline_data=outline,
            )
        )
        session.commit()

    import app.orchestration.agents.course_resources as module

    original_factory = module.ChatPromptTemplate
    module.ChatPromptTemplate = PromptFactory
    try:
        result = asyncio.run(
            run_section_html_animation_agent(
                {
                    "user_id": "user-1",
                    "course_knowledge": outline,
                    "profile": _profile(),
                    "year_learning_paths": _year_learning_paths(),
                    "course_resource_plan": {
                        "course_id": "year_3_course_1",
                        "target_section_ids": ["1.1"],
                    },
                    "messages": [],
                },
                RecordingLlm(),
            )
        )
    finally:
        module.ChatPromptTemplate = original_factory

    assert len(captured["queries"]) >= 2
    assert "error" not in result
    assert result["course_resource_result"]["animation_count"] == 1
    with Session(engine) as session:
        row = session.get(UserCourseKnowledgeOutline, ("user-1", "year_3_course_1"))
    assert row is not None
    assert "section_html_animations" in row.outline_data


def test_resource_agents_reuse_existing_resources_and_rebuild_missing_animation(
    tmp_path, monkeypatch
) -> None:
    class RecordingLlm:
        pass

    class FailingChain:
        async def ainvoke(self, _payload):
            raise AssertionError("existing markdown/video should be reused")

    class Prompt:
        def __or__(self, _other):
            return FailingChain()

    class PromptFactory:
        @staticmethod
        def from_messages(_messages):
            return Prompt()

    async def verified_search(_video_briefs, _section, _outline=None):
        raise AssertionError("existing video links should be reused")

    import app.orchestration.agents.course_resources as module

    outline = _outline()
    target_sections = [
        section
        for section in outline["sections"]
        if section["section_id"].startswith("1.")
    ]
    outline["section_markdowns"] = {}
    outline["section_video_links"] = {}
    for section in target_sections:
        section_id = section["section_id"]
        markdown_data = _complete_markdown_output(
            section_id, section["title"]
        ).model_dump()
        markdown_data = module._normalize_markdown_resources(markdown_data, section)
        video_briefs = markdown_data["video_briefs"]
        outline["section_markdowns"][section_id] = markdown_data
        outline["section_video_links"][section_id] = {
            "section_id": section_id,
            "parent_section_id": "1",
            "title": section["title"],
            "query": "existing",
            "videos": [
                {
                    "brief_id": video_briefs[0]["video_id"],
                    "title": f"AI 应用开发{section['title']}：{section['key_knowledge_points'][0]}实践讲解",
                    "url": f"https://example.com/videos/{section_id.replace('.', '-')}",
                    "cover_url": "",
                    "cover_status": "fallback",
                    "source": f"example.com {section['title']}",
                }
            ],
            "generated_at": "2026-06-06T00:00:00Z",
        }

    engine = build_engine(postgresql_test_url(tmp_path, "section-resource-reuse"))
    set_engine(engine)
    init_db(engine)
    with Session(engine) as session:
        session.add(
            User(uid="user-1", username="课程用户", identifier="course@example.com")
        )
        session.add(
            UserCourseKnowledgeOutline(
                user_uid="user-1",
                course_id="year_3_course_1",
                grade_year="year_3",
                course_name="AI 应用开发",
                outline_data=outline,
            )
        )
        session.commit()

    original_factory = module.ChatPromptTemplate
    module.ChatPromptTemplate = PromptFactory
    monkeypatch.setattr(module, "_find_verified_video_from_search", verified_search)
    try:
        markdown_result = asyncio.run(
            run_section_markdown_agent(
                {
                    "user_id": "user-1",
                    "course_knowledge": outline,
                    "course_resource_plan": {
                        "course_id": "year_3_course_1",
                        "target_section_ids": ["1.1", "1.2", "1.3"],
                    },
                    "messages": [],
                },
                RecordingLlm(),
            )
        )
        video_result = asyncio.run(
            run_section_video_search_agent(markdown_result, RecordingLlm())
        )
        animation_result = asyncio.run(
            run_section_html_animation_agent(video_result, RecordingLlm())
        )
    finally:
        module.ChatPromptTemplate = original_factory

    assert "error" not in animation_result
    assert animation_result["course_resource_result"]["animation_count"] == 3


from app.orchestration.agents.course_resources import (
    _extract_brief_ids_from_markdown,
    _generated_markdown_seed_data,
    _normalize_animation_html,
    _normalize_markdown_resources,
    _run_with_retries,
    _video_specific_brief_terms,
)


def test_extract_brief_ids_from_markdown_reads_video_and_animation_ids() -> None:
    markdown = "\n".join(
        [
            "# 学习目标",
            "<!-- video:id=video_1 -->",
            "正文继续。",
            "<!-- animation:id=anim_1 -->",
        ]
    )

    assert _extract_brief_ids_from_markdown(markdown, "video") == ["video_1"]
    assert _extract_brief_ids_from_markdown(markdown, "animation") == ["anim_1"]


def test_generated_markdown_seed_briefs_prefer_source_section_titles() -> None:
    section = {
        "section_id": "1.1",
        "parent_section_id": "1",
        "depth": 2,
        "title": "学习目标",
        "description": "学习目标来自教材正文。",
        "key_knowledge_points": ["目标说明"],
        "source_section_titles": ["复杂度分析", "数组与列表"],
    }

    seed = _generated_markdown_seed_data(section)

    video_brief = seed["video_briefs"][0]
    animation_brief = seed["animation_briefs"][0]
    assert "复杂度分析" in video_brief["title"]
    assert "数组与列表" in video_brief["purpose"]
    assert "学习目标导入视频" not in video_brief["title"]
    assert "复杂度分析" in animation_brief["title"]
    assert animation_brief["visual_elements"][:2] == ["复杂度分析", "数组与列表"]


def test_normalize_markdown_resources_rewrites_placeholder_ids_to_brief_ids() -> None:
    normalized = _normalize_markdown_resources(
        {
            "section_id": "1.1",
            "parent_section_id": "1",
            "title": "学习目标",
            "markdown": "\n\n".join(
                [
                    "# 1.1 学习目标",
                    "## 学习目标\n把本节目标落到可验收交付物。",
                    "<!-- video:id=wrong_video -->",
                    "## 核心概念\n功能边界、验收标准和资源绑定。",
                    "<!-- animation:id=wrong_anim -->",
                    "## 步骤讲解\n先确认目标，再拆任务，最后验证结果。",
                    "## 练习任务\n写一张任务卡。",
                    "## 检查标准\n能说明完成标准。",
                ]
            ),
            "video_briefs": [
                {
                    "video_id": "video_1",
                    "title": "学习目标导入视频",
                    "purpose": "帮助学习者把学习目标落到可验收产出",
                }
            ],
            "animation_briefs": [
                {
                    "animation_id": "anim_1",
                    "title": "学习目标流程动画",
                    "concept": "展示学习目标如何转成任务、资源和检查标准",
                    "visual_elements": ["学习目标", "练习任务", "检查标准"],
                    "motion": "三个节点依次淡入",
                    "space": "正文宽度的 100%，高度 320px。",
                    "placement_hint": "练习任务之后",
                }
            ],
        },
        _outline()["sections"][1],
    )

    assert _extract_brief_ids_from_markdown(normalized["markdown"], "video") == [
        "video_1"
    ]
    assert _extract_brief_ids_from_markdown(normalized["markdown"], "animation") == [
        "anim_1"
    ]
    assert "wrong_video" not in normalized["markdown"]
    assert "wrong_anim" not in normalized["markdown"]


def test_normalize_markdown_resources_promotes_common_heading_variants() -> None:
    normalized = _normalize_markdown_resources(
        {
            "section_id": "1.1",
            "parent_section_id": "1",
            "title": "学习目标",
            "markdown": "\n\n".join(
                [
                    "# 1.1 学习目标",
                    "## 🎯 本节目标\n把需求拆解从一句模糊目标转成可验收的小任务。",
                    "### 💡 核心概念：为什么需要边界\n功能边界用于控制第一版范围，验收标准用于判断是否真的完成。",
                    "## 🛠️ 实践步骤：三步拆解法\n先确认课程目标，再拆输入输出，然后写验收标准。",
                    "## 📝 练习任务：写一张任务卡\n包含输入、输出、完成标准和最容易卡住的问题。",
                    "#### ✅ 检查标准与交付物\n能解释目标、列出关键知识点，并给出可验收的小产出。",
                    "<!-- video:id=wrong_video -->",
                    "<!-- animation:id=wrong_anim -->",
                ]
            ),
            "video_briefs": [
                {
                    "video_id": "video_1",
                    "title": "学习目标导入视频",
                    "purpose": "帮助学习者把学习目标落到可验收产出",
                }
            ],
            "animation_briefs": [
                {
                    "animation_id": "anim_1",
                    "title": "学习目标流程动画",
                    "concept": "展示学习目标如何转成任务、资源和检查标准",
                    "visual_elements": ["学习目标", "练习任务", "检查标准"],
                    "motion": "三个节点依次淡入",
                    "space": "正文宽度的 100%，高度 320px。",
                    "placement_hint": "练习任务之后",
                }
            ],
        },
        _outline()["sections"][1],
    )

    for heading in (
        "## 学习目标",
        "## 核心概念",
        "## 步骤讲解",
        "## 练习任务",
        "## 检查标准",
    ):
        assert heading in normalized["markdown"]
    assert _extract_brief_ids_from_markdown(normalized["markdown"], "video") == [
        "video_1"
    ]
    assert _extract_brief_ids_from_markdown(normalized["markdown"], "animation") == [
        "anim_1"
    ]


def test_normalize_markdown_resources_numbers_plain_step_paragraphs() -> None:
    normalized = _normalize_markdown_resources(
        {
            "section_id": "1.3",
            "parent_section_id": "1",
            "title": "检查点",
            "markdown": "\n\n".join(
                [
                    "# 1.3 检查点",
                    "## 学习目标\n确认这一节的检查标准能落到真实可运行证据。",
                    "## 核心概念\n验收标准、运行证据、维度匹配。",
                    "## 步骤讲解\n先确认检查目标和输入数据。\n\n再核对嵌入维度、向量库持久化和返回结果。\n\n最后整理截图、日志和结论。",
                    "## 练习任务\n整理一份检查清单。",
                    "## 检查标准\n- [ ] 能说明检查结论。",
                ]
            ),
            "video_briefs": [
                {
                    "video_id": "video_1",
                    "title": "检查点导入视频",
                    "purpose": "帮助学习者把检查点落到可复查证据",
                }
            ],
            "animation_briefs": [
                {
                    "animation_id": "anim_1",
                    "title": "检查点流程动画",
                    "concept": "展示检查点如何转成证据收集流程",
                    "visual_elements": ["检查目标", "运行日志", "验收结论"],
                    "motion": "三个节点依次淡入",
                    "space": "正文宽度的 100%，高度 320px。",
                    "placement_hint": "练习任务之后",
                }
            ],
        },
        _outline()["sections"][3],
    )

    assert "第一步：" in normalized["markdown"]
    assert "第二步：" in normalized["markdown"]
    assert "第三步：" in normalized["markdown"]


def test_compose_section_content_replaces_video_and_animation_placeholders() -> None:
    section_markdown = {
        "section_id": "1.1",
        "parent_section_id": "1",
        "title": "学习目标",
        "markdown": "# 学习目标\n\n<!-- video:id=video_1 -->\n\n<!-- animation:id=anim_1 -->",
        "video_briefs": [
            {
                "video_id": "video_1",
                "title": "学习目标导入",
                "purpose": "用 5 分钟帮助用户建立直觉",
            }
        ],
        "animation_briefs": [
            {
                "animation_id": "anim_1",
                "title": "目标收敛动画",
                "concept": "展示目标如何收敛为验收标准",
                "visual_elements": ["目标卡片", "验收卡片"],
                "motion": "目标卡片从左向右滑入并与验收卡片连接",
                "space": "正文宽度的 100%，高度 320px",
                "placement_hint": "学习目标之后",
            }
        ],
    }
    video_links = {
        "videos": [
            {
                "brief_id": "video_1",
                "title": "学习目标导入",
                "url": "https://example.com/video",
                "cover_url": "https://example.com/cover.png",
                "cover_status": "provided",
                "source": "example.com",
            }
        ]
    }
    animations = {
        "animations": [
            {
                "brief_id": "anim_1",
                "animation_id": "anim_1",
                "title": "目标收敛动画",
                "html": '<section class="section-animation"></section>',
            }
        ]
    }

    composed = _compose_section_content(section_markdown, video_links, animations)

    assert composed["section_id"] == "1.1"
    assert composed["blocks"][0]["type"] == "markdown"
    assert composed["blocks"][1]["type"] == "video"
    assert composed["blocks"][1]["status"] == "available"
    assert composed["blocks"][2]["type"] == "animation"
    assert composed["blocks"][2]["status"] == "available"


def test_normalize_animation_html_wraps_meta_and_visible_fallback_styles() -> None:
    html = '<div class="section-animation"><style>.node{opacity:0;transform:translateY(20px)}</style><div class="node">功能边界</div></div>'

    normalized = _normalize_animation_html(
        html,
        {
            "title": "目标收敛动画",
            "concept": "展示学习目标如何收敛为验收标准",
            "visual_elements": ["功能边界", "验收标准"],
        },
    )

    assert '<meta charset="utf-8">' in normalized
    assert ".section-animation .node" in normalized
    assert "opacity: 1 !important" in normalized
    assert "transform: none !important" in normalized
    assert "目标收敛动画" in normalized
    assert "展示学习目标如何收敛为验收标准" in normalized
    assert "功能边界" in normalized
    assert "验收标准" in normalized
    assert "功能边界" in normalized


def test_normalize_animation_html_rewrites_model_hardcoded_colors_to_oklch() -> None:
    brief = {
        "animation_id": "anim_1",
        "title": "API 连通性测试与标准化请求封装流程动画",
        "concept": "展示 API 请求如何推进到验收证据",
        "visual_elements": ["API Key 的安全存储与加载", "构建标准的 JSON 请求体"],
    }
    section = _outline()["sections"][1]
    raw_html = (
        '<div class="section-animation" style="background:#f8fafc;color:#475569;box-shadow:0 4px 12px rgba(0,0,0,0.08)">'
        "<style>.node{background:white;border:2px solid #e2e8f0;color:rgb(71,85,105)}</style>"
        '<div class="node">API Key 的安全存储与加载</div>'
        "</div>"
    )

    normalized = _normalize_animation_html(raw_html, brief)
    animations = [
        {"animation_id": "anim_1", "title": brief["title"], "html": normalized}
    ]

    assert "#" not in normalized
    assert "rgba(" not in normalized
    assert "rgb(" not in normalized
    assert "oklch(" in normalized
    assert _normalized_animation_quality_issue(animations, [brief], section) is None


def test_markdown_quality_gate_rejects_placeholder_and_missing_learning_sections() -> (
    None
):
    markdown = "\n".join(
        [
            "# 学习目标",
            "Key Concept",
            "This section explores foundational concepts that will be essential.",
            "视频资源暂时不可用",
        ]
    )

    issue = _markdown_quality_issue(
        markdown,
        _outline()["sections"][1],
        [{"video_id": "video_1", "title": "导入视频", "purpose": "建立直觉"}],
        [{"animation_id": "anim_1", "title": "目标动画", "concept": "目标收敛"}],
    )

    assert issue is not None
    assert "旧兜底" in issue


def test_markdown_quality_gate_rejects_shallow_teaching_document() -> None:
    markdown = "\n\n".join(
        [
            "# 1.1 学习目标",
            (
                "## 学习目标\n"
                "本节目标是理解需求拆解，并能调用 OpenAI-compatible API。"
                "完成后可以写一个简单函数，发起请求并打印结果。"
            ),
            "<!-- video:id=video_1 -->",
            (
                "## 核心概念\n"
                "需求拆解是把用户需求转成程序步骤。"
                "OpenAI-compatible API 调用是用 messages、model 和 temperature 调接口。"
                "验收标准是判断代码是否可运行。"
            ),
            (
                "## 步骤讲解\n"
                "第一步分析需求。第二步写代码。第三步调用 API。第四步处理错误。"
                "例如可以写一个 generate_challenge 函数，然后打印返回内容。"
            ),
            "<!-- animation:id=anim_1 -->",
            (
                "## 练习任务\n"
                "安装依赖，复制代码，替换 API Key，运行 main 函数。"
                "提交控制台截图。"
            ),
            ("## 检查标准\n代码可运行。逻辑清晰。异常感知。输出验证。"),
            ("补充说明：" + "本节围绕 AI Agent 开发需求拆解和 API 调用展开。" * 30),
        ]
    )

    issue = _markdown_quality_issue(
        markdown,
        _outline()["sections"][1],
        [{"video_id": "video_1", "title": "学习目标导入", "purpose": "建立直觉"}],
        [{"animation_id": "anim_1", "title": "目标动画", "concept": "目标收敛"}],
    )

    assert issue is not None
    assert "教学支架不足" in issue


def test_markdown_quality_gate_rejects_missing_teaching_scaffold() -> None:
    markdown = "\n\n".join(
        [
            "# 1.1 学习目标",
            "## 学习目标\n本节围绕需求拆解建立学习目标，并说明如何把目标转成可验收产出。",
            (
                "## 核心概念\n"
                "### 需求拆解\n定义：需求拆解是把模糊需求转成输入、处理、输出和验收条件。"
                "为什么重要：它能减少后续 API 调用和前端展示中的临时补写。"
                "怎么用：先标出用户原话中的名词、动作、约束和成功条件。"
                "示例：智能客服第一版只回答课程资料内的问题。"
                "常见误区：直接写代码或提示词，跳过边界说明。"
                "验收方式：同伴只看拆解结果就能复述第一版做什么。\n\n"
                "### OpenAI-compatible API 调用\n定义：按兼容协议组织 model、messages、temperature 等字段并发起请求。"
                "为什么重要：它把拆解后的处理逻辑接到真实模型能力上。"
                "怎么用：system message 约束角色，user message 放任务输入。"
                "示例：生成练习题时，user message 提供学生水平和主题。"
                "边界：API 调用不是目标本身，而是验证拆解是否可执行。"
                "验收方式：能解释字段作用并处理超时、错误码和空响应。"
            ),
            (
                "## 步骤讲解\n"
                "第一步：把目标写成可验收句。输入材料是章节大纲和学习者画像；具体动作是改写学习目标；判断依据是产出是否包含输入、处理、输出、验收；产出物是一句验收目标。\n\n"
                "第二步：拆出数据流。输入材料是一句业务需求；具体动作是标出用户输入、后端处理、模型请求、模型响应和前端展示；判断依据是每个节点是否有明确字段；产出物是一张四列表。\n\n"
                "第三步：把 API 调用放进拆解表。输入材料是第二步的数据流；具体动作是写出 messages 中 system/user 两类内容；判断依据是 system 约束行为、user 承载具体任务；产出物是一段 payload 说明。\n\n"
                "第四步：补验收和异常。输入材料是 payload 说明；具体动作是写出成功、超时、错误码、空响应四种检查；判断依据是每种情况都有可观察结果；产出物是一份检查清单。"
            ),
            "<!-- video:id=video_1 -->",
            (
                "## 练习任务\n"
                "预计 10 到 15 分钟。输入：一句需求「做一个根据学生水平生成 Python 练习题的 Agent」。"
                "操作步骤：先写输入字段，再写处理步骤，再写 API payload，最后写异常和验收。"
                "输出：一张需求拆解表和一段最小 payload。提交物：markdown 文档。"
                "完成标准：同伴只看表格就能知道第一版功能边界和 API 调用方式。"
            ),
            "<!-- animation:id=anim_1 -->",
            (
                "## 检查标准\n"
                "- [ ] 能用自己的话定义需求拆解，并说明它和直接写代码的区别。\n"
                "- [ ] 能解释 messages、model、temperature 至少 3 个字段在 API 调用中的作用。\n"
                "- [ ] 能给出一张包含输入、处理、输出、验收的拆解表。\n"
                "- [ ] 能通过一次本地请求、伪代码审查或同伴复述证明产出可执行。"
            ),
            "补充说明："
            + "本节围绕 AI Agent 项目闭环展开，强调用可验收产出推进学习。" * 20,
        ]
    )

    issue = _markdown_quality_issue(
        markdown,
        _outline()["sections"][1],
        [{"video_id": "video_1", "title": "导入视频", "purpose": "建立直觉"}],
        [{"animation_id": "anim_1", "title": "目标动画", "concept": "目标收敛"}],
    )

    assert issue is not None
    assert "教学支架" in issue or "关键知识点" in issue


def test_markdown_quality_gate_accepts_english_checkpoint_knowledge_points_with_anchor_coverage() -> (
    None
):
    section = {
        "section_id": "2.3",
        "parent_section_id": "2",
        "depth": 2,
        "title": "检查点",
        "order_index": 8,
        "description": "确认「Embedding Generation & Storage」这一章是否真正学会，并核对进入下一章前必须满足的检查标准。",
        "key_knowledge_points": [
            "Handling large files without memory overflow during chunking",
            "A query function that returns top-3 most similar chunks for a given question string.",
        ],
    }
    markdown = "\n\n".join(
        [
            "# 2.3 检查点",
            (
                "## 学习目标\n"
                "完成这一章的 checkpoint 验收，证明自己已经能稳定处理大文件 chunking、控制 memory overflow，"
                "并写出一个接收 question string、返回 top-3 检索结果的 query function。"
            ),
            (
                "## 核心概念\n"
                "### Chunking 与内存边界\n"
                "定义：这一节关注 handling large files 时如何安排 chunking，让读取、切分、向量化和写入过程都不会触发 memory overflow。"
                "为什么重要：一旦大文件在切分前被整块读入内存，Embedding Generation & Storage 的后续步骤会直接失去可操作性。"
                "怎么用：优先采用流式读取、分批切分和增量写入，把每次进入内存的 chunk 数量控制在可以观测的范围内。"
                "示例：处理 PDF/Text 文件时，先按页读取，再把每一页转换成 chunks，随后分批生成 embeddings 并写入本地索引。"
                "边界：如果业务必须一次性保留全文上下文，就要明确峰值内存预算，而不是假设机器总能扛住。"
                "误区：只关注 chunk_size，却不记录每批 chunk 的数量、平均长度和写入延迟。\n\n"
                "### Query Function 验收\n"
                "定义：checkpoint 不是背概念，而是确认你已经能实现一个 query function，输入 question string，返回 top-3 most similar chunks 和对应分数。"
                "为什么重要：只有拿到 most similar chunks，后续的 RAG 拼接上下文、解释命中原因和做结果校验才有真实基础。"
                "怎么用：先把 question 转成 embedding，再调用检索接口按相似度排序，最后输出前三个 chunks、score 和来源位置。"
                "示例：用户输入一个问题后，函数立即返回 top-3 chunks，并标出每个 chunk 的相似度与原始文档片段。"
                "注意：query function 必须和 document embeddings 使用同一模型，避免维度不一致导致结果失真。"
                "验收方式：只要结果里同时能看到 question、top-3、similar chunks、score 和 source metadata，就说明 retrieval loop 已经可观察。"
            ),
            (
                "## 步骤讲解\n"
                "第一步：准备一份足够大的 PDF/Text 文件。输入材料是原始文档；具体动作是记录文件大小、页数和预估 chunk 数；判断依据是你能提前说明为什么它可能造成 memory overflow；产出物是一张输入说明表。\n\n"
                "第二步：实现分批 chunking。输入材料是原始文档和切分参数；具体动作是按页或按窗口读取文本，再分批生成 chunks；判断依据是运行时内存没有失控增长；产出物是一份 chunking 日志。\n\n"
                "第三步：生成 embeddings 并写入索引。输入材料是 chunks；具体动作是分批做向量化并写入本地 vector store；判断依据是每一批都有成功计数和耗时；产出物是一份写入记录。\n\n"
                "第四步：实现 query function。输入材料是 question string 和索引；具体动作是生成 query embedding、执行相似度检索并返回 top-3 chunks；判断依据是结果包含 score、来源片段和排序依据；产出物是一段可运行脚本。\n\n"
                "| 步骤 | 输入材料 | 具体动作 | 产出物 |\n"
                "| --- | --- | --- | --- |\n"
                "| 大文件分析 | PDF/Text 文件 | 估算 chunk 数和内存风险 | 输入说明表 |\n"
                "| 批量切分 | 文档与参数 | 分批生成 chunks | chunking 日志 |\n"
                "| 向量写入 | chunks | 生成 embeddings 并写入索引 | 写入记录 |\n"
                "| 检索验证 | question string | 返回 top-3 chunks 与 score | 可运行脚本 |"
            ),
            "<!-- video:id=video_1 -->",
            (
                "## 练习任务\n"
                "预计 15 到 20 分钟。输入：一个较大的 PDF/Text 文件和一个 question string。"
                "操作步骤：先做 chunking 压测，再检查 memory overflow 风险，然后实现 query function 并输出 top-3 most similar chunks。"
                "输出：一段脚本、一份运行日志和一次检索结果截图。提交物：markdown 记录或终端截图。"
                "完成标准：能证明大文件处理过程稳定，且 query 结果可以复现。"
            ),
            "<!-- animation:id=anim_1 -->",
            (
                "## 检查标准\n"
                "- [ ] 能解释为什么 handling large files 时，chunking 策略会直接影响 memory overflow 风险。\n"
                "- [ ] 能提交一次真实运行记录，展示分批切分和分批写入没有把内存打满。\n"
                "- [ ] 能运行 query function，并返回 top-3 chunks、score 和来源位置。\n"
                "- [ ] 能用 question string 的检索结果说明为什么这些 chunks 会被判定为 most similar。\n"
                "- [ ] 能通过截图、日志或脚本运行结果证明这一节已经达到 checkpoint。"
            ),
            (
                "补充说明：这个检查点面向真实项目交付，而不是只背概念。你需要留下脚本、日志、截图三类证据，"
                "这样下一章进入向量检索实现时，才可以直接复用这里的 chunking 与 query function 产物继续推进。"
            ),
        ]
    )

    issue = _markdown_quality_issue(
        markdown,
        section,
        [
            {
                "video_id": "video_1",
                "title": "检查点视频",
                "purpose": "演示大文件 chunking 与 query 验收",
            }
        ],
        [
            {
                "animation_id": "anim_1",
                "title": "检查点动画",
                "concept": "展示 chunking 到 query 的闭环",
            }
        ],
    )

    assert issue is None


def test_video_specific_brief_terms_ignore_out_of_outline_tracemalloc_detail() -> None:
    outline = {
        "course_id": "year_3_course_1",
        "course_name": "RAG Core: Embeddings & Vector Search Engine",
        "grade_year": "year_3",
        "sections": [
            {
                "section_id": "2",
                "parent_section_id": None,
                "depth": 1,
                "title": "Embedding Generation & Storage",
                "order_index": 5,
                "description": "围绕 Embedding Generation & Storage 展开。",
                "key_knowledge_points": [
                    "Using HuggingFace/SentenceTransformers for local embeddings"
                ],
            },
            {
                "section_id": "2.3",
                "parent_section_id": "2",
                "depth": 2,
                "title": "检查点",
                "order_index": 8,
                "description": "确认这一章是否真正学会。",
                "key_knowledge_points": [
                    "Handling large files without memory overflow during chunking",
                    "A query function that returns top-3 most similar chunks for a given question string.",
                ],
            },
        ],
    }
    section = _section_by_id(outline, "2.3")

    assert section is not None

    video_briefs = [
        {
            "video_id": "video_1",
            "title": "RAG 内存优化与检索调试实战演示",
            "purpose": "通过屏幕录制演示如何使用 tracemalloc 检测内存泄漏，以及如何解读向量检索的相似度分数。",
        }
    ]

    terms = _video_specific_brief_terms(video_briefs, section, outline)

    assert "tracemalloc" not in terms


def test_markdown_quality_gate_accepts_complete_section_markdown() -> None:
    markdown = "\n\n".join(
        [
            "# 1.1 学习目标",
            "## 学习目标\n完成作品级 Agent 项目闭环，明确本节输入、输出与完成标准。学习者需要把需求拆解从一句模糊目标转成可执行的小任务，并说明每个任务如何验证。",
            (
                "## 核心概念\n"
                "### 功能边界\n定义：功能边界说明第一版必须完成什么、暂时不做什么，以及为什么这样取舍。"
                "为什么重要：没有边界，需求拆解会不断膨胀，OpenAI-compatible API 调用也会被迫承担检索、记忆、权限等不该由它承担的任务。"
                "怎么用：先写用户真实目标，再把输入、处理、输出和不做范围分开。"
                "示例：智能客服第一版只回答课程资料内的问题，不做支付、不做长期记忆、不做人工转接。"
                "常见误区：把愿景当边界，例如写“做一个很好用的助手”，却没有说明输入格式和输出限制。"
                "验收方式：同伴只看边界说明，就能判断某个需求应进入本版还是排到后续版本。\n\n"
                "### 验收标准\n定义：验收标准是可以观察、可以复查的完成判断，而不是主观感受。"
                "为什么重要：它把学习目标变成测试目标，让项目驱动学习有明确收口。"
                "怎么用：把每个输出写成可检查句，例如接口返回 200、响应 JSON 包含 answer 字段、错误码有提示。"
                "示例：调用 API 后必须在 10 秒内返回结构化结果，失败时显示可读错误。"
                "边界：验收标准不是详细测试用例，但必须能指导测试用例怎么写。"
                "误区：只写“功能正常”“体验好”，没有可观察证据。\n\n"
                "### OpenAI-compatible API 调用\n定义：按照 OpenAI 兼容协议组织 model、messages、temperature 等字段并发起请求。"
                "为什么重要：它是把拆解后的处理逻辑接入真实模型能力的接口契约。"
                "怎么用：system message 负责角色和边界，user message 负责本次输入，输出格式用 JSON 或明确字段约束。"
                "示例：生成练习题时，system 限定“只输出题目不输出答案”，user 提供学生水平和主题。"
                "注意事项：必须处理超时、429、空响应和 JSON 解析失败。"
            ),
            (
                "## 步骤讲解\n"
                "第一步：确认课程目标。输入材料是课程大纲、学习路径和学习者画像；具体动作是写出本节要支持的项目闭环；"
                "判断依据是目标能否落到一个可交付产物；输出是一句可验收目标，例如“完成一张需求拆解表和一个最小 API payload”。\n\n"
                "第二步：拆输入、处理、输出。输入材料是一句模糊需求；具体动作是标出用户输入字段、后端处理步骤、模型请求字段和前端展示字段；"
                "判断依据是每个字段是否能被代码读取；输出是一张数据流表。例子：level 表示学生难度，topic 表示题目主题，format 表示输出格式。\n\n"
                "第三步：写验收标准。输入材料是数据流表；具体动作是为每个输出写一条可观察检查；"
                "判断依据是能否用运行结果、日志、截图或同伴复述验证；输出是一份检查清单。\n\n"
                "第四步：安排练习。输入材料是检查清单；具体动作是选择 10 到 15 分钟能完成的一项小产出；"
                "判断依据是练习结果能否直接支持下一节接口接入；输出是一份 project_scope.md 或 payload 示例。\n\n"
                "| 步骤 | 输入材料 | 具体动作 | 产出物 |\n"
                "| --- | --- | --- | --- |\n"
                "| 目标收敛 | 课程目标和画像 | 改写成可验收句 | 一句学习目标 |\n"
                "| 数据流拆解 | 业务需求 | 标出输入、处理、输出、验收 | 四列表 |\n"
                "| API 绑定 | 数据流表 | 写出 messages 和输出格式 | 最小 payload |"
            ),
            "<!-- video:id=video_1 -->",
            (
                "## 练习任务\n"
                "预计 10 到 15 分钟。输入：一句需求“为不同水平学生生成 Python 练习题”。"
                "操作步骤：先写输入字段，再写处理步骤，再写 OpenAI-compatible API payload，最后写异常和验收。"
                "输出：一张包含输入、处理、输出、完成标准的任务卡。"
                "提交物：markdown 表格或截图。完成标准：别人只看任务卡就能判断第一版功能边界、API 调用方式和不做范围。"
            ),
            "<!-- animation:id=anim_1 -->",
            (
                "## 检查标准\n"
                "- [ ] 能用自己的话定义功能边界，并举出至少一个不进入第一版的需求。\n"
                "- [ ] 能解释验收标准和测试用例的区别，并写出至少 3 条可观察验收句。\n"
                "- [ ] 能说明 messages、model、temperature 在 API payload 中分别解决什么问题。\n"
                "- [ ] 能提交一张任务卡，包含输入、处理、输出、完成标准和风险点。\n"
                "- [ ] 能通过运行结果、截图或同伴复述证明这张任务卡可执行。"
            ),
            "补充说明：本节内容服务于大三软件工程学生的项目实践目标，强调用有限时间交付作品级 Agent 项目，而不是堆砌抽象概念。所有练习都要能在本地运行并留下检查证据。",
            "延伸练习：把上面的验收清单交给同伴阅读，让对方只根据清单判断项目是否完成。如果对方还需要追问输入格式、错误处理或展示方式，就说明需求拆解仍然不够具体，需要回到功能边界继续收敛。",
            "产出要求：最终至少留下一份 project_scope.md、一段最小 API 调用代码和一次本地运行截图。这样下一节进入接口接入时，可以直接沿着这些证据继续推进，而不是重新讨论目标。",
        ]
    )

    issue = _markdown_quality_issue(
        markdown,
        _outline()["sections"][1],
        [{"video_id": "video_1", "title": "导入视频", "purpose": "建立直觉"}],
        [{"animation_id": "anim_1", "title": "目标动画", "concept": "目标收敛"}],
    )

    assert issue is None


def test_video_quality_gate_requires_bound_url_and_topic_text() -> None:
    issue = _normalized_video_quality_issue(
        [
            {
                "brief_id": "video_1",
                "title": "通用课程首页",
                "url": "ftp://example.com/video",
                "cover_url": "",
                "source": "",
            }
        ],
        [{"video_id": "video_1", "title": "需求拆解导入", "purpose": "建立直觉"}],
        _outline()["sections"][1],
    )

    assert issue is not None
    assert "URL" in issue


@pytest.mark.parametrize(
    ("url", "expected_issue"),
    [
        ("https://www.bilibili.com", "Bilibili 视频 URL 必须为精确视频页地址。"),
        (
            "https://www.bilibili.com/search?keyword=AI",
            "Bilibili 视频 URL 必须为精确视频页地址。",
        ),
        (
            "bilibili.com/video/BV1xx411x7xx",
            "Bilibili 视频 URL 必须为精确视频页地址。",
        ),
        (
            "https://evilbilibili.com/video/BV1xx411x7xx",
            "Bilibili 视频 URL 必须为精确视频页地址。",
        ),
        (
            "https://www.bilibili.com/video/BV1xx411x7xx?from=search",
            "Bilibili 视频 URL 必须为精确视频页地址。",
        ),
        (
            "https://www.bilibili.com/video/BV1xx411x7xx#fragment",
            "Bilibili 视频 URL 必须为精确视频页地址。",
        ),
        (
            "https://user:password@www.bilibili.com/video/BV1xx411x7xx",
            "Bilibili 视频 URL 必须为精确视频页地址。",
        ),
        (
            "https://www.bilibili.com:8443/video/BV1xx411x7xx",
            "Bilibili 视频 URL 必须为精确视频页地址。",
        ),
    ],
)
def test_video_quality_gate_requires_exact_bilibili_video_url(
    url: str, expected_issue: str
) -> None:
    issue = _normalized_video_quality_issue(
        [
            {
                "brief_id": "video_1",
                "title": "AI 应用开发学习目标与功能边界实践讲解",
                "url": url,
                "cover_url": "",
                "source": "Bilibili",
            }
        ],
        [{"video_id": "video_1", "title": "学习目标导入", "purpose": "功能边界"}],
        _outline()["sections"][1],
    )

    assert issue == expected_issue


def test_video_quality_gate_reports_youtube_error_for_non_watch_url() -> None:
    issue = _normalized_video_quality_issue(
        [
            {
                "brief_id": "video_1",
                "title": "AI 应用开发学习目标与功能边界实践讲解",
                "url": "https://evilbilibili.com/video/BV1xx411x7xx",
                "cover_url": "",
                "source": "YouTube",
            }
        ],
        [{"video_id": "video_1", "title": "学习目标导入", "purpose": "功能边界"}],
        _outline()["sections"][1],
    )

    assert issue == "YouTube 视频 URL 必须为精确 watch 视频页地址。"


@pytest.mark.parametrize(
    "url",
    [
        "http://www.youtube.com/watch?v=video-id",
        "https://www.youtube.com/watch",
        "https://www.youtube.com/watch?feature=share",
        "https://www.youtube.com/watch?v=",
        "https://www.youtube.com/watch?v=video-id&feature=share",
        "https://user:password@www.youtube.com/watch?v=video-id",
        "https://www.youtube.com:8443/watch?v=video-id",
        "https://www.youtube.com/watch?v=video-id#fragment",
        "https://youtube.com/watch?v=video-id",
        "https://m.youtube.com/watch?v=video-id",
    ],
)
def test_is_youtube_watch_url_rejects_non_contract_urls(url: str) -> None:
    assert video_module._is_youtube_watch_url(url) is False


@pytest.mark.parametrize(
    "url",
    [
        "https://www.youtube.com/watch?v=video-id",
        "https://www.youtube.com:443/watch?v=video-id",
    ],
)
def test_is_youtube_watch_url_accepts_exact_watch_urls(url: str) -> None:
    assert video_module._is_youtube_watch_url(url) is True


@pytest.mark.parametrize(
    ("source", "url"),
    [
        ("", "https://evilbilibili.com/video/BV1xx411x7xx"),
        ("", "https://www.bilibili.com/video/BV1xx411x7xx?from=search"),
        ("", "https://www.bilibili.com:8443/video/BV1xx411x7xx"),
        ("Other", "https://evilbilibili.com/video/BV1xx411x7xx"),
        ("Other", "https://www.bilibili.com/video/BV1xx411x7xx?from=search"),
        ("Other", "https://www.bilibili.com:8443/video/BV1xx411x7xx"),
    ],
)
def test_video_quality_gate_rejects_non_contract_url_for_any_source(
    source: str, url: str
) -> None:
    issue = _normalized_video_quality_issue(
        [
            {
                "brief_id": "video_1",
                "title": "AI 应用开发学习目标与功能边界实践讲解",
                "url": url,
                "cover_url": "",
                "source": source,
            }
        ],
        [{"video_id": "video_1", "title": "学习目标导入", "purpose": "功能边界"}],
        _outline()["sections"][1],
    )

    assert issue == "Bilibili 视频 URL 必须为精确视频页地址。"


def test_video_quality_gate_accepts_exact_bilibili_video_url_shape() -> None:
    issue = _normalized_video_quality_issue(
        [
            {
                "brief_id": "video_1",
                "title": "Bilibili 搜索结果 BV1xx411x7xx",
                "url": "https://www.bilibili.com/video/BV1xx411x7xx",
                "cover_url": "",
                "source": "Bilibili",
            }
        ],
        [{"video_id": "video_1", "title": "学习目标导入", "purpose": "功能边界"}],
        _outline()["sections"][1],
    )

    assert issue is None


def test_existing_video_value_rejects_bilibili_search_page_url() -> None:
    outline = _outline()
    section = outline["sections"][1]
    video_briefs = [
        {
            "video_id": "video_1",
            "title": "学习目标导入",
            "purpose": "帮助学习者理解功能边界。",
        }
    ]
    outline["section_video_links"] = {
        "1.1": {
            "section_id": "1.1",
            "videos": [
                {
                    "brief_id": "video_1",
                    "title": "AI 应用开发学习目标与功能边界实践讲解",
                    "url": "https://search.bilibili.com/video?keyword=AI%20应用开发",
                    "cover_url": "",
                    "source": "Bilibili",
                }
            ],
        }
    }

    existing_value = video_module._existing_video_value(outline, section, video_briefs)

    assert existing_value is None


def test_video_quality_gate_rejects_invisible_bilibili_video(monkeypatch) -> None:
    import app.orchestration.agents.course_resources as module

    async def invisible_video(_url: str) -> dict:
        return {"status": "invalid", "reason": "Bilibili 视频不可见：稿件不可见。"}

    monkeypatch.setattr(module, "_verify_bilibili_video_metadata", invisible_video)

    issue = asyncio.run(
        _normalized_video_quality_issue_async(
            [
                {
                    "brief_id": "video_1",
                    "title": "学习目标：功能边界与验收标准",
                    "url": "https://www.bilibili.com/video/BV1xx411x7xx",
                    "cover_url": "",
                    "source": "Bilibili",
                }
            ],
            [
                {
                    "video_id": "video_1",
                    "title": "学习目标导入",
                    "purpose": "功能边界与验收标准",
                }
            ],
            _outline()["sections"][1],
        )
    )

    assert issue is not None
    assert "不可见" in issue


def test_video_quality_gate_accepts_bilibili_metadata_topic_mismatch(
    monkeypatch,
) -> None:
    import app.orchestration.agents.course_resources as module

    async def unrelated_video(_url: str) -> dict:
        return {"status": "ok", "text": "Never Gonna Give You Up Rick Astley 官方 MV"}

    monkeypatch.setattr(module, "_verify_bilibili_video_metadata", unrelated_video)

    issue = asyncio.run(
        _normalized_video_quality_issue_async(
            [
                {
                    "brief_id": "video_1",
                    "title": "学习目标：功能边界与验收标准",
                    "url": "https://www.bilibili.com/video/BV1GJ411x7h7",
                    "cover_url": "",
                    "source": "Bilibili",
                }
            ],
            [
                {
                    "video_id": "video_1",
                    "title": "学习目标导入",
                    "purpose": "功能边界与验收标准",
                }
            ],
            _outline()["sections"][1],
        )
    )

    assert issue is None


def test_video_quality_gate_verifies_youtube_watch_page_access(monkeypatch) -> None:
    requested_urls: list[str] = []

    class ReachableResponse:
        text = '"videoId":"video-id"'

        def raise_for_status(self) -> None:
            return None

    class ReachableClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def get(self, url: str, **_kwargs):
            requested_urls.append(url)
            return ReachableResponse()

    monkeypatch.setattr(
        video_module.httpx, "AsyncClient", lambda **_kwargs: ReachableClient()
    )

    issue = asyncio.run(
        _normalized_video_quality_issue_async(
            [
                {
                    "brief_id": "video_1",
                    "title": "任意标题",
                    "url": "https://www.youtube.com/watch?v=video-id",
                    "source": "YouTube",
                }
            ],
            [{"video_id": "video_1"}],
            _outline()["sections"][1],
        )
    )

    assert issue is None
    assert requested_urls == ["https://www.youtube.com/watch?v=video-id"]


def test_video_quality_gate_rejects_unreachable_youtube_watch_page(
    monkeypatch,
) -> None:
    class UnreachableClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def get(self, *_args, **_kwargs):
            raise httpx.ConnectError("unreachable")

    monkeypatch.setattr(
        video_module.httpx, "AsyncClient", lambda **_kwargs: UnreachableClient()
    )

    issue = asyncio.run(
        _normalized_video_quality_issue_async(
            [
                {
                    "brief_id": "video_1",
                    "title": "任意标题",
                    "url": "https://www.youtube.com/watch?v=video-id",
                    "source": "YouTube",
                }
            ],
            [{"video_id": "video_1"}],
            _outline()["sections"][1],
        )
    )

    assert issue == "YouTube 视频页面校验失败。"


def test_video_quality_gate_rejects_unverified_bilibili_page(monkeypatch) -> None:
    import app.orchestration.agents.course_resources as module

    async def skipped_video(_url: str) -> dict:
        return {"status": "skip"}

    monkeypatch.setattr(module, "_verify_bilibili_video_metadata", skipped_video)

    issue = asyncio.run(
        _normalized_video_quality_issue_async(
            [
                {
                    "brief_id": "video_1",
                    "title": "任意标题",
                    "url": "https://www.bilibili.com/video/BV1GJ411x7h7",
                    "source": "Bilibili",
                }
            ],
            [{"video_id": "video_1"}],
            _outline()["sections"][1],
        )
    )

    assert issue == "Bilibili 视频页面未完成校验。"


def test_animation_quality_gate_requires_visible_chinese_context() -> None:
    issue = _normalized_animation_quality_issue(
        [
            {
                "animation_id": "anim_1",
                "title": "目标动画",
                "html": (
                    '<!doctype html><html><head><meta charset="utf-8"></head><body>'
                    "<style>.section-animation .node{opacity: 1 !important;transform: none !important;}</style>"
                    '<div class="section-animation"><div class="node">User</div></div>'
                    "</body></html>"
                ),
            }
        ],
        [
            {
                "animation_id": "anim_1",
                "title": "目标动画",
                "concept": "目标收敛",
                "visual_elements": ["功能边界"],
            }
        ],
        _outline()["sections"][1],
    )

    assert issue is not None
    assert "上下文" in issue


def test_animation_quality_gate_rejects_hex_and_rgb_colors() -> None:
    issue = _normalized_animation_quality_issue(
        [
            {
                "animation_id": "anim_1",
                "title": "目标动画",
                "html": (
                    '<!doctype html><html><head><meta charset="utf-8"></head><body>'
                    "<style>"
                    ".section-animation .node{opacity: 1 !important;transform: none !important;}"
                    ".section-animation{background:#ffcccc;color:rgb(20, 30, 40);}"
                    "</style>"
                    '<div class="section-animation">'
                    '<div class="animation-context">目标收敛与功能边界</div>'
                    '<div class="node">功能边界</div>'
                    "</div>"
                    "</body></html>"
                ),
            }
        ],
        [
            {
                "animation_id": "anim_1",
                "title": "目标动画",
                "concept": "目标收敛",
                "visual_elements": ["功能边界"],
            }
        ],
        _outline()["sections"][1],
    )

    assert issue is not None
    assert "HEX/RGB" in issue


def test_compose_section_content_downgrades_missing_video_and_animation() -> None:
    section_markdown = {
        "section_id": "1.1",
        "parent_section_id": "1",
        "title": "学习目标",
        "markdown": "# 学习目标\n\n<!-- video:id=video_1 -->\n\n<!-- animation:id=anim_1 -->",
        "video_briefs": [
            {"video_id": "video_1", "title": "学习目标导入", "purpose": "建立直觉"}
        ],
        "animation_briefs": [
            {
                "animation_id": "anim_1",
                "title": "目标动画",
                "concept": "目标收敛",
                "visual_elements": ["目标卡片"],
                "motion": "淡入",
                "space": "高度 320px",
                "placement_hint": "正文中段",
            }
        ],
    }

    composed = _compose_section_content(
        section_markdown, {"videos": []}, {"animations": []}
    )

    assert composed["blocks"][1]["type"] == "video"
    assert composed["blocks"][1]["status"] == "unavailable"
    assert composed["blocks"][2]["type"] == "animation"
    assert composed["blocks"][2]["status"] == "unavailable"


def test_run_with_retries_retries_three_times_then_returns_fallback() -> None:
    attempts = {"count": 0}

    async def failing_action():
        attempts["count"] += 1
        raise RuntimeError("生成失败")

    result = asyncio.run(
        _run_with_retries(failing_action, fallback={"ok": False}, attempts=3)
    )

    assert attempts["count"] == 3
    assert result == {"ok": False}


def test_stream_chapter_resource_generation_stops_when_video_step_fails() -> None:
    import app.orchestration.agents.course_resources as module

    calls = {"animation": 0}
    outline = _outline()

    async def markdown_agent(state, _llm, explicit_args=None):
        return {
            "course_knowledge": outline,
            "course_resource_plan": {
                "course_id": "year_3_course_1",
                "target_section_ids": ["1.1", "1.2", "1.3"],
                "markdown_section_ids": ["1.1", "1.2", "1.3"],
                "video_section_ids": [],
                "animation_section_ids": [],
            },
        }

    async def video_agent(state, _search_llm, explicit_args=None):
        return {"error": "视频资源生成失败，请稍后重试。", "hard_error": True}

    async def animation_agent(state, _llm, explicit_args=None):
        calls["animation"] += 1
        return {"course_knowledge": state["course_knowledge"]}

    original_markdown_agent = module.run_section_markdown_agent
    original_video_agent = module.run_section_video_search_agent
    original_animation_agent = module.run_section_html_animation_agent
    module.run_section_markdown_agent = markdown_agent
    module.run_section_video_search_agent = video_agent
    module.run_section_html_animation_agent = animation_agent
    try:

        async def collect_events():
            return [
                event
                async for event in module.stream_chapter_resource_generation(
                    {
                        "user_id": "user-1",
                        "session_id": "session-1",
                        "course_knowledge": outline,
                        "profile": {},
                        "year_learning_paths": {},
                    },
                    object(),
                    object(),
                    course_id="year_3_course_1",
                    chapter_section_id="1",
                )
            ]

        events = asyncio.run(collect_events())
    finally:
        module.run_section_markdown_agent = original_markdown_agent
        module.run_section_video_search_agent = original_video_agent
        module.run_section_html_animation_agent = original_animation_agent

    assert calls["animation"] == 0
    assert events[-1] == {
        "event": "error",
        "message": "视频资源生成失败，请稍后重试。",
        "recoverable": True,
        "course_id": "year_3_course_1",
        "chapter_section_id": "1",
        "kind": "course_resource_chapter",
        "phase": "video",
        "status": "error",
        "stepId": "leaf-chapter-1-video",
        "agent": "section_video_search_agent",
        "label": "章节视频资源生成失败",
        "section_ids": ["1.1", "1.2", "1.3"],
    }
    assert not any(event["event"] == "message_completed" for event in events)
    assert not any(event["event"] == "session_completed" for event in events)


def test_stream_chapter_resource_generation_reports_agent_phases_in_order() -> None:
    import app.orchestration.agents.course_resources as module

    outline = _outline()
    call_order: list[str] = []

    async def markdown_agent(state, _llm, explicit_args=None):
        call_order.append("markdown")
        next_outline = dict(outline)
        next_outline["section_markdowns"] = {
            section_id: {
                "section_id": section_id,
                "parent_section_id": "1",
                "title": _section_by_id(outline, section_id)["title"],
                "markdown": _complete_section_markdown(
                    section_id, _section_by_id(outline, section_id)["title"]
                ),
                "video_briefs": [
                    {
                        "video_id": "video_1",
                        "title": f"{section_id} 具体视频",
                        "purpose": f"辅助理解 {section_id} 的具体概念。",
                    }
                ],
                "animation_briefs": [
                    {
                        "animation_id": "anim_1",
                        "title": f"{section_id} 具体动画",
                        "concept": f"展示 {section_id} 的具体结构变化。",
                        "visual_elements": ["输入", "处理", "输出"],
                        "motion": "节点依次淡入。",
                        "space": "正文宽度 100%，高度 320px。",
                        "placement_hint": "步骤讲解之后。",
                    }
                ],
            }
            for section_id in ["1.1", "1.2", "1.3"]
        }
        return {
            "course_knowledge": next_outline,
            "course_resource_plan": {
                "course_id": "year_3_course_1",
                "target_section_ids": ["1.1", "1.2", "1.3"],
                "markdown_section_ids": ["1.1", "1.2", "1.3"],
                "video_section_ids": [],
                "animation_section_ids": [],
            },
        }

    async def video_agent(state, _search_llm, explicit_args=None):
        call_order.append("video")
        next_outline = dict(state["course_knowledge"])
        next_outline["section_video_links"] = {
            section_id: {"section_id": section_id, "videos": []}
            for section_id in ["1.1", "1.2", "1.3"]
        }
        next_plan = dict(state["course_resource_plan"])
        next_plan["video_section_ids"] = ["1.1", "1.2", "1.3"]
        return {"course_knowledge": next_outline, "course_resource_plan": next_plan}

    async def animation_agent(state, _llm, explicit_args=None):
        call_order.append("animation")
        next_outline = dict(state["course_knowledge"])
        next_outline["section_html_animations"] = {
            section_id: {"section_id": section_id, "animations": []}
            for section_id in ["1.1", "1.2", "1.3"]
        }
        next_plan = dict(state["course_resource_plan"])
        next_plan["animation_section_ids"] = ["1.1", "1.2", "1.3"]
        return {
            "course_knowledge": next_outline,
            "course_resource_plan": next_plan,
            "course_resource_result": {
                "course_id": "year_3_course_1",
                "generated_section_ids": ["1.1", "1.2", "1.3"],
                "markdown_count": 3,
                "video_count": 0,
                "animation_count": 0,
            },
        }

    original_markdown_agent = module.run_section_markdown_agent
    original_video_agent = module.run_section_video_search_agent
    original_animation_agent = module.run_section_html_animation_agent
    module.run_section_markdown_agent = markdown_agent
    module.run_section_video_search_agent = video_agent
    module.run_section_html_animation_agent = animation_agent
    try:

        async def collect_events():
            return [
                event
                async for event in module.stream_chapter_resource_generation(
                    {
                        "user_id": "user-1",
                        "session_id": "session-1",
                        "course_knowledge": outline,
                        "profile": {},
                        "year_learning_paths": {},
                    },
                    object(),
                    object(),
                    course_id="year_3_course_1",
                    chapter_section_id="1",
                )
            ]

        events = asyncio.run(collect_events())
    finally:
        module.run_section_markdown_agent = original_markdown_agent
        module.run_section_video_search_agent = original_video_agent
        module.run_section_html_animation_agent = original_animation_agent

    phase_events = [
        (event.get("agent"), event.get("phase"), event.get("status"))
        for event in events
        if event.get("event") in {"agent_progress", "agent_result"}
    ]
    assert call_order == ["markdown", "video", "animation"]
    assert ("section_markdown_agent", "markdown", "completed") in phase_events
    assert ("section_video_search_agent", "video", "completed") in phase_events
    assert ("section_html_animation_agent", "animation", "completed") in phase_events
    markdown_completed_index = phase_events.index(
        ("section_markdown_agent", "markdown", "completed")
    )
    video_completed_index = phase_events.index(
        ("section_video_search_agent", "video", "completed")
    )
    animation_completed_index = phase_events.index(
        ("section_html_animation_agent", "animation", "completed")
    )
    assert markdown_completed_index < video_completed_index < animation_completed_index


def test_stream_chapter_resource_generation_generates_bound_resources_for_each_child_section(  # noqa: C901
    tmp_path,
) -> None:
    import app.orchestration.agents.course_resources as module

    def payload_from_query(query: str) -> dict:
        return json.loads(query.split("输入：", 1)[1])

    markdown_bodies = {
        "学习目标": "本节把目标拆成可验收的教学结果，并要求学习者说明输入材料、模型调用、资源 brief 和页面展示之间的关系。",
        "核心概念": "### 资源绑定\n资源绑定要求 Markdown、视频和动画服务同一个小节目标，正文占位符 ID 必须与 brief 完全一致。",
        "步骤讲解": (
            "第一步：读取小节上下文。第二步：生成五个正文点。第三步：后端拼装资源占位符。\n\n"
            "| 步骤 | 输入材料 | 具体动作 | 产出物 | 验收方式 |\n"
            "| --- | --- | --- | --- | --- |\n"
            "| 读取 | 小节上下文 | 提取标题和知识点 | 上下文对象 | 字段可复查 |\n"
            "| 拼装 | 五段正文 | 插入 video 与 animation 占位符 | Markdown | ID 完全一致 |"
        ),
        "练习任务": "请提交一份小节 Markdown 和 composed blocks，证明视频块与动画块可以由后端插入。",
        "检查标准": (
            "- [ ] 能说明五个正文点的生成顺序。\n"
            "- [ ] 能核对视频占位符。\n"
            "- [ ] 能核对动画占位符。\n"
            "- [ ] 能从前端响应读取 composed blocks。"
        ),
    }

    class ResourceLlm:
        pass

    class ResourceChain:
        async def ainvoke(self, payload):
            captured["queries"].append(payload["query"])
            parsed = payload_from_query(payload["query"])
            section = parsed["target_section"]
            section_id = section["section_id"]
            title = section["title"]
            if "markdown_expansion_section" in parsed:
                if parsed["markdown_expansion_section"] == "完整文档":
                    return _complete_section_markdown_from_bodies(
                        section_id, title, markdown_bodies
                    )
                return markdown_bodies[parsed["markdown_expansion_section"]]
            if "section_markdowns" in parsed:
                brief = parsed["section_markdowns"][section_id]["video_briefs"][0]
                parent_title = next(
                    (
                        item["title"]
                        for item in parsed["course_knowledge"]["sections"]
                        if item["section_id"] == section["parent_section_id"]
                    ),
                    "",
                )
                return SectionVideoSearchOutput(
                    section_id=section_id,
                    query=f"AI Agent {title} {section['key_knowledge_points'][0]} 视频教程",
                    videos=[
                        {
                            "brief_id": brief["video_id"],
                            "title": f"{parent_title}{brief['title']}：{section['key_knowledge_points'][0]}实践讲解",
                            "url": f"https://www.youtube.com/watch?v=dummy-{section_id.replace('.', '-')}",
                            "cover_url": "",
                            "source": f"example.com {title}",
                        }
                    ],
                )
            brief = parsed["animation_briefs"][0]
            return SectionHtmlAnimationOutput(
                section_id=section_id,
                animations=[
                    {
                        "animation_id": brief["animation_id"],
                        "title": brief["title"],
                        "html": _complete_animation_html(
                            brief["animation_id"],
                            brief["title"],
                            brief["concept"],
                            brief["visual_elements"],
                        ),
                    }
                ],
            )

    class ResourcePrompt:
        def __or__(self, _llm):
            return ResourceChain()

    class PromptFactory:
        @staticmethod
        def from_messages(_messages):
            return ResourcePrompt()

    async def verified_search(video_briefs, section, _outline=None):
        brief = video_briefs[0]
        section_id = section["section_id"]
        parent_title = next(
            (
                item["title"]
                for item in outline["sections"]
                if item["section_id"] == section["parent_section_id"]
            ),
            "",
        )
        return [
            {
                "brief_id": brief["video_id"],
                "title": f"{parent_title}{brief['title']}：{section['key_knowledge_points'][0]}实践讲解",
                "url": f"https://www.youtube.com/watch?v=dummy-{section_id.replace('.', '-')}",
                "cover_url": "",
                "source": f"example.com {section['title']}",
            }
        ]

    captured = {"queries": []}
    outline = _outline()
    engine = build_engine(postgresql_test_url(tmp_path, "section-stream-complete"))
    set_engine(engine)
    init_db(engine)
    with Session(engine) as session:
        session.add(
            User(uid="user-1", username="课程用户", identifier="course@example.com")
        )
        session.add(
            UserCourseKnowledgeOutline(
                user_uid="user-1",
                course_id="year_3_course_1",
                grade_year="year_3",
                course_name="AI 应用开发",
                outline_data=outline,
            )
        )
        session.commit()

    original_factory = module.ChatPromptTemplate
    module.ChatPromptTemplate = PromptFactory
    original_verified_search = module._find_verified_video_from_search
    module._find_verified_video_from_search = verified_search
    try:

        async def collect_events():
            return [
                event
                async for event in module.stream_chapter_resource_generation(
                    {
                        "user_id": "user-1",
                        "session_id": "session-1",
                        "course_knowledge": outline,
                        "profile": _profile(),
                        "year_learning_paths": _year_learning_paths(),
                    },
                    ResourceLlm(),
                    ResourceLlm(),
                    course_id="year_3_course_1",
                    chapter_section_id="1",
                )
            ]

        events = asyncio.run(collect_events())
    finally:
        module.ChatPromptTemplate = original_factory
        module._find_verified_video_from_search = original_verified_search

    assert all('"profile"' in query for query in captured["queries"])
    assert all('"year_learning_paths"' in query for query in captured["queries"])
    assert all('"course_knowledge"' in query for query in captured["queries"])
    assert events[-2]["event"] == "message_completed"
    assert events[-1]["event"] == "session_completed"
    assert not any(event["event"] == "error" for event in events)

    with Session(engine) as session:
        row = session.get(UserCourseKnowledgeOutline, ("user-1", "year_3_course_1"))
    assert row is not None
    generated = row.outline_data
    assert set(generated["section_markdowns"]) == {"1.1", "1.2", "1.3"}
    assert set(generated["section_video_links"]) == {"1.1", "1.2", "1.3"}
    assert set(generated["section_html_animations"]) == {"1.1", "1.2", "1.3"}
    assert set(generated["section_composed_markdowns"]) == {"1.1", "1.2", "1.3"}
    for section_id in ["1.1", "1.2", "1.3"]:
        markdown = generated["section_markdowns"][section_id]
        video = generated["section_video_links"][section_id]["videos"][0]
        animation = generated["section_html_animations"][section_id]["animations"][0]
        composed_blocks = generated["section_composed_markdowns"][section_id]["blocks"]
        assert (
            _markdown_quality_issue(
                markdown["markdown"],
                _section_by_id(generated, section_id),
                markdown["video_briefs"],
                markdown["animation_briefs"],
            )
            is None
        )
        assert video["brief_id"] == markdown["video_briefs"][0]["video_id"]
        assert video["url"].startswith("https://www.youtube.com/watch?v=dummy-")
        assert (
            animation["animation_id"] == markdown["animation_briefs"][0]["animation_id"]
        )
        assert "animation-context" in animation["html"]
        assert [block["type"] for block in composed_blocks] == [
            "markdown",
            "video",
            "markdown",
            "animation",
            "markdown",
        ]


def test_stream_chapter_resource_generation_accepts_plain_markdown_and_html_outputs(
    tmp_path,
) -> None:
    import app.orchestration.agents.course_resources as module

    def payload_from_query(query: str) -> dict:
        return json.loads(query.split("输入：", 1)[1])

    class ResourceLlm:
        pass

    class ResourceChain:
        async def ainvoke(self, payload):
            parsed = payload_from_query(payload["query"])
            section = parsed["target_section"]
            section_id = section["section_id"]
            title = section["title"]
            if "section_markdowns" not in parsed and "animation_briefs" not in parsed:
                return _complete_section_markdown(
                    section_id,
                    title,
                    f"video_{section_id.replace('.', '_')}",
                    f"anim_{section_id.replace('.', '_')}",
                )
            if "section_markdowns" in parsed:
                brief = parsed["section_markdowns"][section_id]["video_briefs"][0]
                return SectionVideoSearchOutput(
                    section_id=section_id,
                    query=f"AI Agent {title} 视频教程",
                    videos=[
                        {
                            "brief_id": brief["video_id"],
                            "title": f"{title}：{section['key_knowledge_points'][0]}实践讲解",
                            "url": f"https://www.youtube.com/watch?v=dummy-{section_id.replace('.', '-')}",
                            "cover_url": "",
                            "source": "example.com",
                        }
                    ],
                )
            brief = parsed["animation_briefs"][0]
            return _complete_animation_html(
                brief["animation_id"],
                brief["title"],
                brief["concept"],
                brief["visual_elements"],
            )

    class ResourcePrompt:
        def __or__(self, _llm):
            return ResourceChain()

    class PromptFactory:
        @staticmethod
        def from_messages(_messages):
            return ResourcePrompt()

    async def verified_search(video_briefs, section, _outline=None):
        brief = video_briefs[0]
        section_id = section["section_id"]
        parent_title = next(
            (
                item["title"]
                for item in outline["sections"]
                if item["section_id"] == section["parent_section_id"]
            ),
            "",
        )
        return [
            {
                "brief_id": brief["video_id"],
                "title": f"{parent_title}{section['title']}：{section['key_knowledge_points'][0]}实践讲解",
                "url": f"https://www.youtube.com/watch?v=dummy-{section_id.replace('.', '-')}",
                "cover_url": "",
                "source": "example.com",
            }
        ]

    outline = _outline()
    engine = build_engine(postgresql_test_url(tmp_path, "section-stream-plain-output"))
    set_engine(engine)
    init_db(engine)
    with Session(engine) as session:
        session.add(
            User(uid="user-1", username="课程用户", identifier="course@example.com")
        )
        session.add(
            UserCourseKnowledgeOutline(
                user_uid="user-1",
                course_id="year_3_course_1",
                grade_year="year_3",
                course_name="AI 应用开发",
                outline_data=outline,
            )
        )
        session.commit()

    original_factory = module.ChatPromptTemplate
    module.ChatPromptTemplate = PromptFactory
    original_verified_search = module._find_verified_video_from_search
    module._find_verified_video_from_search = verified_search
    try:

        async def collect_events():
            return [
                event
                async for event in module.stream_chapter_resource_generation(
                    {
                        "user_id": "user-1",
                        "session_id": "session-1",
                        "course_knowledge": outline,
                        "profile": _profile(),
                        "year_learning_paths": _year_learning_paths(),
                    },
                    ResourceLlm(),
                    ResourceLlm(),
                    course_id="year_3_course_1",
                    chapter_section_id="1",
                )
            ]

        events = asyncio.run(collect_events())
    finally:
        module.ChatPromptTemplate = original_factory
        module._find_verified_video_from_search = original_verified_search

    assert events[-2]["event"] == "message_completed"
    assert events[-1]["event"] == "session_completed"
    assert not any(event["event"] == "error" for event in events)

    with Session(engine) as session:
        row = session.get(UserCourseKnowledgeOutline, ("user-1", "year_3_course_1"))
    assert row is not None
    generated = row.outline_data
    assert set(generated["section_markdowns"]) == {"1.1", "1.2", "1.3"}
    assert set(generated["section_html_animations"]) == {"1.1", "1.2", "1.3"}
    assert set(generated["section_composed_markdowns"]) == {"1.1", "1.2", "1.3"}
    for section_id in ["1.1", "1.2", "1.3"]:
        markdown = generated["section_markdowns"][section_id]
        animation = generated["section_html_animations"][section_id]["animations"][0]
        composed_blocks = generated["section_composed_markdowns"][section_id]["blocks"]
        assert markdown["video_briefs"][0]["video_id"] == "video_1"
        assert animation["animation_id"] == "anim_1"
        assert "section-animation" in animation["html"]
        assert composed_blocks[1]["status"] == "available"
        assert composed_blocks[3]["status"] == "available"


def test_markdown_quality_gate_accepts_clean_structure_without_keywords():
    from app.orchestration.agents.course_resources import _markdown_quality_issue

    valid_markdown = (
        "# 1.1 学习目标\n\n"
        "## 学习目标\n"
        "这里是学习目标的详细描述，包含知识目标和实战目标。整体字数必须符合限制要求。\n"
        "在学习本小节时，我们需要对数据导入和清洗流程有非常直观的理解，并把这些理解固化到代码实现中。\n"
        "最终的交付物应当包括清洗规则和分块验证样例。\n\n"
        "## 核心概念\n"
        "### 知识点测试\n"
        "这是概念描述。通过对数据预处理逻辑、对齐策略和底层并发调优的讲解，我们可以规避向量数据库检索退化的问题。\n"
        "这个概念帮助我们理清数据清洗前后的区别，并在本地 RAG 系统中实际部署测试。\n"
        "对于稠密向量对齐，我们需要保证 Embedding 维度的对齐并做好容错。\n"
        "在向量数据库检索的过程中，为了保证检索的准确率 and 召回率，我们需要对切分出来的文本块进行精细化的维度转换与对齐。如果因为某些细节问题导致向量维度的差异，整个知识检索系统都会面临崩溃的风险。\n"
        "适用边界：此机制适用于小语种和特定专业领域文档导入的清洗环节。\n"
        "验收标准：能通过比对原始文档和清洗后的 JSON 文件格式来确认掌握。\n\n"
        "## 步骤讲解\n"
        "第一步：读取配置数据。具体动作是确认文件是否存在。产出物是配置字典。\n"
        "第二步：执行转换。具体动作是格式化输出。产出物是文本。\n"
        "第三步：执行分块。具体动作是使用分词器切割。产出物是分块列表。\n"
        "第四步：向量化写入。具体动作是将分块数据上传。产出物是向量检索索引。\n"
        "在此过程中，切分文本的长度应维持在合理区间，并结合实际的硬件配置与并发压力进行相应的调参。\n\n"
        "| 步骤 | 输入材料 | 具体动作 | 产出物 | 验收方式 |\n"
        "| --- | --- | --- | --- | --- |\n"
        "| 1 | 原始数据 | 读取并清洗 | 清洗后文本 | 检查无多余换行 |\n"
        "| 2 | 清洗文本 | 递归切分 | 文本分块 | 确认块大小在512内 |\n"
        "| 3 | 分块数据 | 生成Embedding | 向量列表 | 验证维度为1024 |\n"
        "| 4 | 向量列表 | 写入数据库 | 索引状态 | 检索测试问题 |\n\n"
        "<!-- video:id=video_1 -->\n\n"
        "## 练习任务\n"
        "练习任务详情：请动手尝试初始化向量库配置，提交运行截图或终端日志。\n"
        "操作步骤十分明确，首先在本地起一个 Qdrant 或 Milvus 实例，随后配置 OpenAI/BGE client 进行向量化写入。\n"
        "接着将获取到的向量保存，提交你的 python 写入脚本和运行产生的 log，完成标准是能顺利查询写入数据。\n"
        "请务必在本地搭建好环境后再开始进行写入操作，避免由于网络或认证问题导致写入失败。\n\n"
        "<!-- animation:id=anim_1 -->\n\n"
        "## 检查标准\n"
        "- [ ] 第一条标准已自查并通过\n"
        "- [ ] 第二条标准已自查并通过\n"
        "- [ ] 第三条标准已自查并通过\n"
        "- [ ] 第四条标准已自查并通过\n"
        "这里需要说明视频资源和 HTML 动画分别服务哪个理解难点，保证占位符 ID 一致。\n"
        "我们可以在控制台看到正确的日志输出，代表整个数据处理流程已经闭环通过验收。\n"
        "所有自查步骤都需要细心确认，以保障最后交付物的绝对质量。\n\n"
        "补充说明：本节内容主要为了让大家对向量化以及数据清洗的工作流程有最基本的直观认识。我们不要求大家现在就去深入探究底层索引的高级参数，而是把精力集中在把流程跑通、把结果固化下来这一步。通过记录日志、保存脚本和核对向量维度的正确性，我们可以为后面的检索打下坚实的基础。请确保本地的向量库实例运行正常，并且 API 客户端能顺利发起网络连接。如果在部署过程中遇到任何阻碍，可以先检查本地的 Docker 配置或者模型文件的加载路径是否正确。\n\n"
        "延伸阅读与进阶指引：在生产级别的检索增强生成系统中，数据清洗和分块对最终的检索召回准确率起着决定性的作用。我们在此处强调分批切分与流式处理，正是为了规避大文件导入时的内存溢出风险。在后续的课程中，我们还会接触到混合检索、重排序等更复杂的架构，但其核心数据流依然建立在当前这一节的工作成果之上。请大家务必打好基础，多动手测试不同类型和大小的非结构化文件，仔细比对处理前后的效果差异。\n\n"
        "学习指导：建议大家在本地创建一个专门的实验目录，用来保存本小节产生的所有 rules.md 规则文件、分块数据样例 json 以及检索说明。将这些产出纳入版本管理，能极大方便我们进行追溯与复盘。"
    )

    section = {
        "title": "学习目标",
        "description": "说明学习目标",
        "key_knowledge_points": ["知识点测试"],
    }
    video_briefs = [{"video_id": "video_1"}]
    animation_briefs = [{"animation_id": "anim_1"}]

    issue = _markdown_quality_issue(
        valid_markdown, section, video_briefs, animation_briefs
    )
    assert issue is None


def test_profile_learning_context_text_generates_natural_narrative():
    from app.orchestration.agents.course_resources import _profile_learning_context_text

    state = {
        "profile": {
            "confirmed_info": {
                "current_grade": "大三",
                "major": "软件工程",
                "learning_method_preference": "项目驱动学习",
            }
        }
    }

    text = _profile_learning_context_text(state)
    assert "大三软件工程专业" in text
    assert "项目驱动" in text
    assert ";" not in text
    assert "；" not in text

    state_unknown = {
        "profile": {
            "confirmed_info": {
                "current_grade": "未知",
                "major": "未知",
                "learning_method_preference": "项目驱动学习",
            }
        }
    }
    text_unknown = _profile_learning_context_text(state_unknown)
    assert "未知" not in text_unknown
    assert "根据您偏好的项目驱动学习方法" in text_unknown

    # Test cases with only preference present (no background)
    state_only_pref = {
        "profile": {
            "confirmed_info": {
                "current_grade": "未知",
                "major": "无",
                "learning_method_preference": "实践探究",
            }
        }
    }
    text_only_pref = _profile_learning_context_text(state_only_pref)
    assert "根据您偏好的实践探究方法，本节采用项目实践驱动" in text_only_pref

    # Test cases with none-like placeholders present
    state_placeholders = {
        "profile": {
            "confirmed_info": {
                "current_grade": "暂无",
                "major": "none",
                "learning_method_preference": "无偏好",
            }
        }
    }
    text_placeholders = _profile_learning_context_text(state_placeholders)
    assert (
        text_placeholders
        == "本节采用项目实践驱动的教学设计，侧重动手实践与运行结果校验，以便快速掌握核心技能。"
    )

    # Test case: only grade present, preference is placeholder
    state_only_grade = {
        "profile": {
            "confirmed_info": {
                "current_grade": "硕士",
                "major": "null",
                "learning_method_preference": "没有",
            }
        }
    }
    text_only_grade = _profile_learning_context_text(state_only_grade)
    assert "硕士阶段" in text_only_grade
    assert "偏好" not in text_only_grade

    # Test case: only major present, preference is placeholder
    state_only_major = {
        "profile": {
            "confirmed_info": {
                "current_grade": "none",
                "major": "计算机科学与技术",
                "learning_method_preference": "无",
            }
        }
    }
    text_only_major = _profile_learning_context_text(state_only_major)
    assert "计算机科学与技术专业" in text_only_major
    assert "偏好" not in text_only_major


def test_deterministic_animation_html_generates_interactive_glassmorphism():
    from app.orchestration.agents.course_resources import _deterministic_animation_html

    html_content = _deterministic_animation_html(
        "anim_1", "维度对齐流程", "说明概念", ["分块", "向量化", "对齐"]
    )

    assert "backdrop-filter: blur" in html_content
    assert "box-shadow:" in html_content
    assert "@keyframes pulse" in html_content
    assert 'data-animation-id="anim_1"' in html_content
    assert "function selectStep" in html_content or "addEventListener" in html_content


# ---------------------------------------------------------------------------
# End-to-end integration: simulate real RAG course data flowing through the
# entire deterministic pipeline (section → markdown → quality gate → animation
# → compose → frontend-ready blocks).
# ---------------------------------------------------------------------------


def _rag_outline() -> dict:
    """Simulates a realistic RAG course outline with 3 knowledge points."""
    return {
        "course_id": "year_3_course_1",
        "course_name": "构建本地知识库问答系统 (RAG基础)",
        "grade_year": "year_3",
        "personalization_summary": "项目驱动，先跑通数据清洗和分块流程。",
        "sections": [
            {
                "section_id": "1",
                "parent_section_id": None,
                "depth": 1,
                "title": "数据预处理与分块",
                "order_index": 1,
                "description": "把非结构化文档整理成适合向量化的语料。",
                "key_knowledge_points": ["数据清洗", "文本分块", "向量化准备"],
            },
            {
                "section_id": "1.1",
                "parent_section_id": "1",
                "depth": 2,
                "title": "文本清洗与分块策略",
                "order_index": 2,
                "description": "学习如何清洗原始文档并设计合理的分块策略，确保后续向量检索的召回质量。",
                "key_knowledge_points": ["数据清洗", "文本分块", "重叠率控制"],
            },
            {
                "section_id": "1.2",
                "parent_section_id": "1",
                "depth": 2,
                "title": "向量化与索引构建",
                "order_index": 3,
                "description": "将清洗后的文本块转化为稠密向量并写入向量数据库。",
                "key_knowledge_points": [
                    "Embedding 模型",
                    "向量数据库写入",
                    "维度对齐",
                ],
            },
        ],
        "learning_sequence": ["第一章：数据预处理与分块"],
        "total_estimated_hours": "6 小时",
    }


def _rag_state() -> dict:
    """Simulates a realistic orchestration state with profile and learning path."""
    return {
        "profile": {
            "type": "basic_profile",
            "confirmed_info": {
                "current_grade": "大三",
                "major": "计算机科学与技术",
                "learning_stage": "项目实践",
                "learning_method_preference": "项目驱动学习",
                "content_preference": ["文档", "代码实践"],
                "weekly_available_time": "每天 8 小时",
                "constraints": "需要先补齐 Python 异步编程基础",
            },
        },
        "year_learning_paths": {
            "year_3": {
                "schema_version": "learning_path.v2.course_node",
                "current_learning_course": {
                    "grade_id": "year_3",
                    "course_node_id": "year_3_course_1",
                    "course_or_chapter_theme": "构建本地知识库问答系统",
                    "course_goal": "完成可部署的 RAG 问答系统",
                    "current_focus": "数据清洗与分块策略",
                    "progress_state": "in_progress",
                    "next_action": "完成第一章数据预处理",
                },
                "resource_generation_contract": {
                    "resource_directions": [
                        {
                            "resource_direction_id": "year_3_course_1_resource",
                            "target_node_ids": ["year_3_course_1"],
                            "resource_type": "文档",
                            "generation_goal": "围绕 RAG 数据管线生成教学资源",
                            "content_requirements": [
                                "绑定章节大纲",
                                "引用学习者画像",
                                "补充视频和动画",
                            ],
                            "difficulty_level": "中级",
                        }
                    ]
                },
            }
        },
    }


def test_e2e_profile_text_handles_realistic_and_edge_cases():
    """Verify profile text generation with realistic data and edge cases."""
    # Realistic: all fields present
    state_full = _rag_state()
    text = _profile_learning_context_text(state_full)
    assert "大三" in text
    assert "计算机科学与技术" in text
    assert "项目驱动" in text
    assert ";" not in text
    assert "；" not in text

    # Edge: all fields are placeholders
    state_empty = {
        "profile": {
            "confirmed_info": {
                "current_grade": "未知",
                "major": "无",
                "learning_method_preference": "无偏好",
            }
        }
    }
    text_empty = _profile_learning_context_text(state_empty)
    assert "未知" not in text_empty
    assert "无" not in text_empty
    assert len(text_empty) > 20, "Fallback text should be meaningful"

    # Edge: only preference present
    state_pref_only = {
        "profile": {
            "confirmed_info": {
                "current_grade": "null",
                "major": "none",
                "learning_method_preference": "动手实验",
            }
        }
    }
    text_pref = _profile_learning_context_text(state_pref_only)
    assert "动手实验" in text_pref
    assert "null" not in text_pref


def test_e2e_animation_html_is_self_contained_and_accessible():
    """Verify animation HTML is self-contained, accessible, and dark-mode ready."""
    from app.orchestration.agents.course_resources import _deterministic_animation_html

    html = _deterministic_animation_html(
        "anim_1", "数据清洗流程", "展示清洗步骤", ["解析", "去噪", "标准化"]
    )

    # Self-contained: no external resources
    assert "http" not in html.lower() or "href" not in html.lower(), (
        "No external CSS/JS"
    )
    assert "<script>" in html
    assert "<style>" in html

    # Accessibility: reduced-motion support
    assert "prefers-reduced-motion" in html

    # Dark mode
    assert "prefers-color-scheme: dark" in html

    # Interactive: click handler
    assert "addEventListener" in html or "onclick" in html

    # OKLCH colors (no hex/rgb)
    assert "#" not in html.split("<style>")[1].split("</style>")[0].replace(
        "#detailPanel", ""
    ).replace("#detailTitle", "").replace("#detailDesc", "").replace("#detailIo", "")

    # All 3 steps rendered
    assert "解析" in html
    assert "去噪" in html
    assert "标准化" in html

    # IIFE pattern for JS isolation
    assert "(function()" in html or "(function() {" in html


def test_run_section_markdown_agent_injects_textbook_evidence_cag(tmp_path) -> None:
    from tests.fixtures.knowledge_base import enabled_source, published_textbook
    from tests.fixtures.knowledge_base import section as k_section

    # Set up mock/recording LLM
    class RecordingLlm:
        pass

    section_bodies = {
        "学习目标": "学习目标正文内容来自教材证据包事实。",
        "核心概念": "核心概念解释来自教材证据包事实。",
        "步骤讲解": "步骤讲解正文内容来自教材证据包事实。\n\n| 步骤 | 输入材料 |\n| --- | --- |\n| 1 | 2 |",
        "练习任务": "练习任务正文内容来自教材证据包事实。",
        "检查标准": ("- [ ] 标准 1\n- [ ] 标准 2\n- [ ] 标准 3\n- [ ] 标准 4"),
    }

    captured_queries = []

    class MarkdownChain:
        async def ainvoke(self, payload):
            captured_queries.append(payload["query"])
            parsed = _payload_from_query(payload["query"])
            expansion_section = parsed["markdown_expansion_section"]
            if expansion_section == "完整文档":
                section_data = parsed["target_section"]
                section_id = section_data["section_id"]
                title = section_data["title"]
                evidence_text = parsed["textbook_evidence_pack"]["evidence_text"]
                return "\n\n".join(
                    [
                        f"# {section_id} {title}",
                        f"## 学习目标\n学习目标正文内容来自教材证据包事实：{evidence_text}",
                        "## 核心概念\n### 特定章节标题\n核心概念解释来自教材证据包事实。",
                        "## 步骤讲解\n步骤讲解正文内容来自教材证据包事实。\n\n```text\n步骤: 使用教材证据包\n输入: 特定章节标题\n输出: 教学文档\n```",
                        "<!-- video:id=video_1 -->",
                        "## 练习任务\n练习任务正文内容来自教材证据包事实。",
                        "<!-- animation:id=anim_1 -->",
                        "## 检查标准\n- [ ] 标准 1\n- [ ] 标准 2\n- [ ] 标准 3\n- [ ] 标准 4",
                    ]
                )
            return section_bodies[expansion_section]

    class MarkdownPrompt:
        def __or__(self, _other):
            return MarkdownChain()

    class PromptFactory:
        @staticmethod
        def from_messages(_messages):
            return MarkdownPrompt()

    engine = build_engine(postgresql_test_url(tmp_path, "section-markdown-cag"))
    set_engine(engine)
    init_db(engine)

    # Seed User, Outline, Textbook, Source, and TextbookSectionContent
    with Session(engine) as session:
        session.add(
            User(uid="user-1", username="课程用户", identifier="course@example.com")
        )

        textbook_id = "textbook-cag-structures"
        source_id = "source-cag-id"

        session.add(enabled_source(source_id=source_id))

        tb = published_textbook(
            textbook_id=textbook_id,
            source_id=source_id,
            title="CAG教材",
        )
        tb.outline = {
            "sections": [
                {"section_id": "1.1", "title": "特定章节标题"},
            ]
        }
        session.add(tb)

        # Add actual textbook section content
        session.add(
            k_section(
                textbook_id=textbook_id,
                section_content_id="section-cag-content-id-1",
                section_id="1.1",
                title="特定章节标题",
                content_zh="这是真实存储于教材正文数据库中的特定中文教学段落，用于细粒度证据塞入。",
            )
        )

        # Set up outline which references this textbook and section
        outline_data = _outline()
        outline_data["source_textbook_id"] = textbook_id
        outline_data["source_textbook_title"] = "CAG教材"

        # Bind the textbook info directly to section 1.1
        target_sec = outline_data["sections"][1]
        target_sec["source_textbook_id"] = textbook_id
        target_sec["source_textbook_title"] = "CAG教材"
        target_sec["source_section_ids"] = ["1.1"]
        target_sec["source_section_titles"] = ["特定章节标题"]
        target_sec["source_content_chars"] = 1000

        session.add(
            UserCourseKnowledgeOutline(
                user_uid="user-1",
                course_id="year_3_course_1",
                grade_year="year_3",
                course_name="AI 应用开发",
                outline_data=outline_data,
            )
        )
        session.commit()

    import app.orchestration.agents.course_resources as module

    original_factory = module.ChatPromptTemplate
    module.ChatPromptTemplate = PromptFactory
    try:
        asyncio.run(
            run_section_markdown_agent(
                {
                    "user_id": "user-1",
                    "course_knowledge": outline_data,
                    "profile": _profile(),
                    "year_learning_paths": _year_learning_paths(),
                    "messages": [],
                },
                RecordingLlm(),
                {
                    "course_id": "year_3_course_1",
                    "section_id": "1.1",
                    "scope": "single_section",
                },
            )
        )
    finally:
        module.ChatPromptTemplate = original_factory

    assert len(captured_queries) == 1
    for query in captured_queries:
        assert "这是真实存储于教材正文数据库中的特定中文教学段落" in query
        assert "textbook_evidence_pack" in query
        assert "evidence_text" in query
        assert "教材证据包" in query
        assert "真实内容" in query or "严格基于" in query or "唯一" in query


def test_run_section_markdown_agent_rejects_missing_textbook_evidence(
    tmp_path: Path,
) -> None:
    from tests.fixtures.knowledge_base import enabled_source, published_textbook
    from tests.fixtures.knowledge_base import section as k_section

    class RecordingLlm:
        pass

    class ExplodingPrompt:
        def __or__(self, _other):
            raise AssertionError("缺少教材证据时不应调用 LLM。")

    class PromptFactory:
        @staticmethod
        def from_messages(_messages):
            return ExplodingPrompt()

    engine = build_engine(
        postgresql_test_url(tmp_path, "section-markdown-missing-evidence")
    )
    set_engine(engine)
    init_db(engine)

    with Session(engine) as session:
        session.add(
            User(uid="user-1", username="课程用户", identifier="course@example.com")
        )
        textbook_id = "textbook-missing-evidence"
        source_id = "source-missing-evidence"
        session.add(enabled_source(source_id=source_id))
        tb = published_textbook(
            textbook_id=textbook_id,
            source_id=source_id,
            title="缺证据教材",
        )
        tb.outline = {
            "sections": [
                {"section_id": "1.1", "title": "存在的小节"},
            ]
        }
        session.add(tb)
        session.add(
            k_section(
                textbook_id=textbook_id,
                section_content_id="section-existing-content-id",
                section_id="1.1",
                title="存在的小节",
                content_zh="存在的小节正文。",
            )
        )
        outline_data = _outline()
        target_sec = outline_data["sections"][1]
        target_sec["source_textbook_id"] = textbook_id
        target_sec["source_textbook_title"] = "缺证据教材"
        target_sec["source_section_ids"] = ["9.9"]
        target_sec["source_section_titles"] = ["不存在的小节"]
        target_sec["source_content_chars"] = 100
        session.commit()

    import app.orchestration.agents.course_resources as module

    original_factory = module.ChatPromptTemplate
    module.ChatPromptTemplate = PromptFactory
    try:
        result = asyncio.run(
            run_section_markdown_agent(
                {
                    "user_id": "user-1",
                    "course_knowledge": outline_data,
                    "profile": _profile(),
                    "year_learning_paths": _year_learning_paths(),
                    "messages": [],
                },
                RecordingLlm(),
                {
                    "course_id": "year_3_course_1",
                    "section_id": "1.1",
                    "scope": "single_section",
                },
            )
        )
    finally:
        module.ChatPromptTemplate = original_factory

    assert result == {"error": "教材小节不存在。", "hard_error": True}
