"""Contract tests for the course resource agent."""

# ruff: noqa: E501,E402

from __future__ import annotations

import asyncio
import json

import pytest
from dashscope import Generation

from app.orchestration.agents.course_resources import (
    aliyun_bilibili_search as aliyun_bilibili_search_module,
)
from app.orchestration.agents.course_resources import animation as animation_module
from app.orchestration.agents.course_resources.aliyun_bilibili_search import (
    _search_aliyun_bilibili_sources,
)
from app.orchestration.agents.course_resources.common import (
    SECTION_MARKDOWN_EXPANSION_SYSTEM_PROMPT,
    _resource_query_with_prompt_budget,
)


class _DashScopeResponse:
    def __init__(self, *, content: object, search_results: object) -> None:
        self.status_code = 200
        self.output = {
            "choices": [{"message": {"content": content}}],
            "search_info": {"search_results": search_results},
        }


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


def test_aliyun_bilibili_search_uses_native_dashscope_contract(
    monkeypatch,
) -> None:
    calls: list[dict] = []
    responses = iter(
        [
            iter(
                [
                    _DashScopeResponse(
                        content=[],
                        search_results=[
                            {
                                "title": "第一条",
                                "url": "https://www.bilibili.com/video/BV1234567890",
                                "site_name": None,
                                "index": 1,
                            },
                            {
                                "title": "第二条",
                                "url": "https://www.bilibili.com/video/BV0987654321",
                                "site_name": "哔哩哔哩",
                                "index": 2,
                            },
                        ],
                    )
                ]
            ),
            _DashScopeResponse(
                content=[{"text": '```json\n{"indexes":[2,1]}\n```'}],
                search_results=[],
            ),
        ]
    )

    def conversation_call(**kwargs):
        calls.append(kwargs)
        return next(responses)

    monkeypatch.setenv("LLM_API_KEY", "native-search-key")
    monkeypatch.setenv("LLM_MODEL", "qwen-search-model")
    monkeypatch.setattr(
        aliyun_bilibili_search_module.MultiModalConversation,
        "call",
        conversation_call,
    )

    results = asyncio.run(
        _search_aliyun_bilibili_sources(
            "数据结构 算法效率 时间复杂度 操作次数",
            "精确的小节语义范围",
        )
    )

    assert [result.index for result in results] == [2, 1]
    assert calls == [
        {
            "api_key": "native-search-key",
            "model": "qwen-search-model",
            "messages": [
                {
                    "role": "system",
                    "content": [
                        {
                            "text": (
                                "使用联网搜索查找与输入小节语义最相关的 "
                                "Bilibili 教学视频。"
                            )
                        }
                    ],
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "text": (
                                "数据结构 算法效率 时间复杂度 操作次数\n"
                                "只返回 Bilibili 视频稿件来源。"
                            )
                        }
                    ],
                },
            ],
            "enable_search": True,
            "search_options": {
                "forced_search": True,
                "search_strategy": "agent",
                "enable_source": True,
            },
            "stream": True,
            "incremental_output": True,
        },
        {
            "api_key": "native-search-key",
            "model": "qwen-search-model",
            "messages": [
                {
                    "role": "system",
                    "content": [
                        {
                            "text": (
                                "根据小节语义，对给定的真实搜索来源按相关性从高到低排序。"
                                "返回所有语义相关来源的索引，不判断 URL 形态，"
                                "不遗漏较低排名来源。"
                                '只返回严格 JSON：{"indexes":[整数索引]}。'
                            )
                        }
                    ],
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "text": json.dumps(
                                {
                                    "section_scope": "精确的小节语义范围",
                                    "search_results": [
                                        {
                                            "index": 1,
                                            "title": "第一条",
                                            "site_name": "",
                                        },
                                        {
                                            "index": 2,
                                            "title": "第二条",
                                            "site_name": "哔哩哔哩",
                                        },
                                    ],
                                },
                                ensure_ascii=False,
                            )
                        }
                    ],
                },
            ],
        },
    ]


def test_aliyun_bilibili_search_uses_generation_for_text_model_endpoint(
    monkeypatch,
) -> None:
    endpoint_error = _DashScopeResponse(content=[], search_results=[])
    endpoint_error.status_code = 400
    endpoint_error.code = "InvalidParameter"
    endpoint_error.message = (
        "url error, please check url！ For details, see: "
        "https://help.aliyun.com/zh/model-studio/error-code#error-url"
    )
    multimodal_calls: list[dict] = []
    generation_calls: list[dict] = []
    generation_responses = iter(
        [
            iter(
                [
                    _DashScopeResponse(
                        content=[],
                        search_results=[
                            {
                                "title": "算法复杂度课程",
                                "url": "https://www.bilibili.com/video/BV1234567890",
                                "site_name": None,
                                "index": 4,
                            }
                        ],
                    )
                ]
            ),
            _DashScopeResponse(
                content='{"indexes":[4]}',
                search_results=[],
            ),
        ]
    )

    def multimodal_call(**kwargs):
        multimodal_calls.append(kwargs)
        return iter([endpoint_error])

    def generation_call(**kwargs):
        generation_calls.append(kwargs)
        return next(generation_responses)

    monkeypatch.setenv("LLM_API_KEY", "key")
    monkeypatch.setenv("LLM_MODEL", "text-model")
    monkeypatch.setattr(
        aliyun_bilibili_search_module.MultiModalConversation,
        "call",
        multimodal_call,
    )
    monkeypatch.setattr(Generation, "call", generation_call)

    results = asyncio.run(
        _search_aliyun_bilibili_sources("数据结构 时间复杂度", "小节语义")
    )

    assert [source.index for source in results] == [4]
    assert len(multimodal_calls) == 1
    assert len(generation_calls) == 2
    assert generation_calls[0]["messages"] == [
        {
            "role": "system",
            "content": aliyun_bilibili_search_module._SEARCH_SYSTEM_PROMPT,
        },
        {
            "role": "user",
            "content": "数据结构 时间复杂度\n只返回 Bilibili 视频稿件来源。",
        },
    ]
    assert generation_calls[0]["enable_search"] is True
    assert generation_calls[0]["result_format"] == "message"
    assert generation_calls[0]["search_options"] == {
        "forced_search": True,
        "search_strategy": "agent",
        "enable_source": True,
    }
    assert generation_calls[0]["stream"] is True
    assert generation_calls[0]["incremental_output"] is True
    assert generation_calls[1]["messages"][0] == {
        "role": "system",
        "content": aliyun_bilibili_search_module._SELECTION_SYSTEM_PROMPT,
    }


@pytest.mark.parametrize(
    ("content", "expected_indexes"),
    [
        ('{"indexes":[3,1,3,2]}', [3, 1, 2]),
        ('{"indexes":[true,1,"2",2]}', [1, 2]),
        ('{"indexes":[99]}', []),
        ('{"indexes":"1"}', []),
        ('{"url":"https://www.bilibili.com/video/BV0000000000"}', []),
        ("", []),
        ("not-json", []),
    ],
)
def test_aliyun_bilibili_search_only_returns_indexed_search_info_sources(
    monkeypatch,
    content: str,
    expected_indexes: list[int],
) -> None:
    responses = iter(
        [
            iter(
                [
                    _DashScopeResponse(
                        content=[
                            {
                                "text": (
                                    '{"url":"https://www.bilibili.com/video/'
                                    'BV0000000000"}'
                                )
                            }
                        ],
                        search_results=[
                            {
                                "title": f"来源 {index}",
                                "url": (
                                    f"https://www.bilibili.com/video/BV{index:010d}"
                                ),
                                "site_name": "哔哩哔哩",
                                "index": index,
                            }
                            for index in (1, 2, 3)
                        ],
                    )
                ]
            ),
            _DashScopeResponse(
                content=[{"text": content}],
                search_results=[],
            ),
        ]
    )
    monkeypatch.setenv("LLM_API_KEY", "key")
    monkeypatch.setenv("LLM_MODEL", "model")
    monkeypatch.setattr(
        aliyun_bilibili_search_module.MultiModalConversation,
        "call",
        lambda **_kwargs: next(responses),
    )

    results = asyncio.run(_search_aliyun_bilibili_sources("query", "scope"))

    assert [result.index for result in results] == expected_indexes
    assert all("BV0000000000" not in result.url for result in results)


def test_aliyun_bilibili_search_rejects_invalid_response_contract(monkeypatch) -> None:
    monkeypatch.setenv("LLM_API_KEY", "key")
    monkeypatch.setenv("LLM_MODEL", "model")
    invalid_responses = [
        _DashScopeResponse(content='{"indexes":[1]}', search_results=None),
        _DashScopeResponse(
            content='{"indexes":[1]}',
            search_results=[
                {
                    "title": "标题",
                    "url": "https://www.bilibili.com/video/BV0000000001",
                    "site_name": "哔哩哔哩",
                    "index": "1",
                }
            ],
        ),
    ]
    invalid_responses[0].status_code = 503

    for response in invalid_responses:
        monkeypatch.setattr(
            aliyun_bilibili_search_module.MultiModalConversation,
            "call",
            lambda **_kwargs: iter([response]),
        )
        assert asyncio.run(_search_aliyun_bilibili_sources("query", "scope")) == []


def test_aliyun_bilibili_search_returns_empty_without_config_or_on_sdk_error(
    monkeypatch,
) -> None:
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    assert asyncio.run(_search_aliyun_bilibili_sources("query", "scope")) == []

    monkeypatch.setenv("LLM_API_KEY", "key")
    monkeypatch.setenv("LLM_MODEL", "model")

    def fail_call(**_kwargs):
        raise TimeoutError("search timeout")

    monkeypatch.setattr(
        aliyun_bilibili_search_module.MultiModalConversation,
        "call",
        fail_call,
    )
    assert asyncio.run(_search_aliyun_bilibili_sources("query", "scope")) == []


def test_markdown_expansion_prompt_allows_english_evidence_but_requires_chinese_output() -> (
    None
):
    assert "英文" in SECTION_MARKDOWN_EXPANSION_SYSTEM_PROMPT
    assert "evidence_text" in SECTION_MARKDOWN_EXPANSION_SYSTEM_PROMPT
    assert "中文" in SECTION_MARKDOWN_EXPANSION_SYSTEM_PROMPT


def test_section_markdown_system_prompt_matches_full_document_generation() -> None:
    assert "完整 Markdown 文档" in SECTION_MARKDOWN_EXPANSION_SYSTEM_PROMPT
    assert "禁止输出完整 Markdown 文档" not in SECTION_MARKDOWN_EXPANSION_SYSTEM_PROMPT
    assert "禁止输出 `#` 或 `##` 标题" not in SECTION_MARKDOWN_EXPANSION_SYSTEM_PROMPT
    assert "禁止输出视频或动画占位符" not in SECTION_MARKDOWN_EXPANSION_SYSTEM_PROMPT


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


def _animation_structure_html(body: str) -> str:
    return (
        '<!doctype html><html><head><meta charset="utf-8"></head><body>'
        '<section class="section-animation">'
        "<style>@media (prefers-reduced-motion: reduce){.section-animation *{"
        "opacity: 1 !important;transform: none !important;}}</style>"
        f'<div class="animation-context">单链表结构动画</div>{body}'
        "</section></body></html>"
    )


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


def test_markdown_quality_gate_accepts_clean_structure_without_keywords():
    from app.orchestration.agents.course_resources.markdown import (
        _markdown_quality_issue,
    )

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


def test_deterministic_animation_html_generates_interactive_glassmorphism():
    from app.orchestration.agents.course_resources.animation import (
        _deterministic_animation_html,
    )

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


def test_e2e_animation_html_is_self_contained_and_accessible():
    """Verify animation HTML is self-contained, accessible, and dark-mode ready."""
    from app.orchestration.agents.course_resources.animation import (
        _deterministic_animation_html,
    )

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
