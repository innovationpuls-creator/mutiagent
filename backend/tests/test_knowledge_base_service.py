from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, SQLModel, create_engine, select

from app import schemas as app_schemas
from app.models import (
    KnowledgeBaseIngestionJob,
    KnowledgeGap,
    KnowledgeGapFollow,
    KnowledgeGapNotice,
    KnowledgeSource,
    Textbook,
    TextbookExtensionResource,
    TextbookSectionContent,
)
from app.schema_upgrades import run_schema_upgrades
from app.schemas import (
    KnowledgeBaseIngestionJobStatusContract,
    KnowledgeGapNoticeStatusContract,
    KnowledgeGapStatusContract,
    KnowledgeSourceStatusContract,
    TextbookStatusContract,
)
from app.services import knowledge_base_service
from app.services.knowledge_base_service import (
    add_textbook_extension_resource,
    create_gap_resolved_notices_for_textbook,
    create_knowledge_source,
    create_or_update_knowledge_gap,
    delete_knowledge_source,
    follow_knowledge_gap,
    get_published_textbook_context_for_topic,
    get_textbook_evidence_pack,
    is_source_admitted_for_primary_textbook,
    list_admitted_knowledge_sources,
    list_extension_resources_for_sections,
    list_knowledge_sources,
    publish_textbook,
    update_knowledge_source,
    upsert_structured_textbook,
)
from tests.fixtures.knowledge_base import (
    enabled_source as _admitted_source,
)
from tests.fixtures.knowledge_base import (
    extension_resource as _extension_resource,
)
from tests.fixtures.knowledge_base import (
    section as _section,
)
from tests.fixtures.knowledge_base import (
    textbook as _textbook,
)
from tests.postgres import postgresql_test_url

KNOWLEDGE_MODELS = (
    KnowledgeSource,
    Textbook,
    TextbookSectionContent,
    TextbookExtensionResource,
    KnowledgeGap,
    KnowledgeGapFollow,
    KnowledgeGapNotice,
    KnowledgeBaseIngestionJob,
)


def _knowledge_engine(tmp_path: Path):
    return create_engine(
        postgresql_test_url(tmp_path, "knowledge-base"),
    )


def test_search_real_textbook_sources_rejects_non_textbook_urls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw_results = [
        {
            "title": "Open Data Structures",
            "original_title": "Open Data Structures",
            "language": "en",
            "source_url": "https://opendatastructures.org/ods-python.pdf",
            "source_type": "pdf",
            "provider_name": "Open Data Structures",
            "description": "Open textbook.",
            "tags": ["数据结构"],
            "parseability_score": 95,
            "parseability_reason": "PDF 稳定可访问。",
            "topic_summary": "覆盖数据结构。",
        },
        {
            "title": "占位教材",
            "source_url": "https://example.com/book.pdf",
            "source_type": "pdf",
            "parseability_score": 80,
            "parseability_reason": "占位链接。",
            "topic_summary": "无效来源。",
        },
        {
            "title": "教程页面",
            "source_url": "https://blog.example.edu/data-structures",
            "source_type": "webpage",
            "parseability_score": 70,
            "parseability_reason": "普通教程网页。",
            "topic_summary": "不是教材。",
        },
    ]

    monkeypatch.setattr(
        knowledge_base_service,
        "_search_real_textbook_sources_with_llm",
        lambda topic, limit: raw_results,
    )
    monkeypatch.setattr(
        knowledge_base_service,
        "_is_reachable_textbook_url",
        lambda url: url == "https://opendatastructures.org/ods-python.pdf",
    )
    monkeypatch.setattr(
        knowledge_base_service,
        "parse_textbook_source_to_sections",
        lambda source_url, language, **kwargs: (
            {
                "chapters": [
                    {
                        "chapter_number": 1,
                        "title": "Chapter 1",
                        "sections": [{"section_id": "sec_1_1", "title": "Arrays"}],
                    }
                ]
            },
            {"sec_1_1": "Arrays original content."},
        ),
    )

    results = knowledge_base_service.search_real_textbook_sources("数据结构", limit=5)

    assert [result.source_result_id for result in results] == ["source-result-bef2583d"]
    assert results[0].title == "Open Data Structures"
    assert results[0].source_type == "pdf"
    assert results[0].is_recommended is True


def test_search_real_textbook_sources_rejects_unparseable_reachable_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw_results = [
        {
            "title": "Open Data Structures",
            "original_title": "Open Data Structures",
            "language": "en",
            "source_url": "https://opendatastructures.org/ods-python.pdf",
            "source_type": "pdf",
            "provider_name": "Open Data Structures",
            "description": "Open textbook.",
            "tags": ["数据结构"],
            "parseability_score": 95,
            "parseability_reason": "PDF 稳定可访问。",
            "topic_summary": "覆盖数据结构。",
        }
    ]

    monkeypatch.setattr(
        knowledge_base_service,
        "_search_real_textbook_sources_with_llm",
        lambda topic, limit: raw_results,
    )
    monkeypatch.setattr(
        knowledge_base_service,
        "_is_reachable_textbook_url",
        lambda url: True,
    )
    monkeypatch.setattr(
        knowledge_base_service,
        "parse_textbook_source_to_sections",
        lambda source_url, language, **kwargs: (
            {
                "chapters": [
                    {
                        "chapter_number": 1,
                        "title": "Chapter 1",
                        "sections": [{"section_id": "sec_1_1", "title": "Arrays"}],
                    }
                ]
            },
            {},
        ),
    )

    results = knowledge_base_service.search_real_textbook_sources("数据结构", limit=5)

    assert results == []


def test_search_real_textbook_sources_uses_known_open_textbook_when_llm_is_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parsed_urls: list[str] = []

    monkeypatch.setattr(
        knowledge_base_service,
        "_search_real_textbook_sources_with_llm",
        lambda topic, limit: [],
    )
    monkeypatch.setattr(
        knowledge_base_service,
        "_is_reachable_textbook_url",
        lambda url: url == "https://opendatastructures.org/ods-python/",
    )

    def parse_source(
        source_url: str, language: str, **kwargs: object
    ) -> tuple[dict, dict[str, str]]:
        parsed_urls.append(source_url)
        assert source_url == "https://opendatastructures.org/ods-python/"
        assert language == "en"
        assert kwargs == {"max_linked_pages": 8}
        return (
            {
                "chapters": [
                    {
                        "chapter_number": 1,
                        "title": "1. Introduction",
                        "sections": [
                            {
                                "section_id": "sec_1_1",
                                "title": "1.1 The Need for Efficiency",
                            }
                        ],
                    }
                ]
            },
            {"sec_1_1": "Real Open Data Structures section content."},
        )

    monkeypatch.setattr(
        knowledge_base_service,
        "parse_textbook_source_to_sections",
        parse_source,
    )

    results = knowledge_base_service.search_real_textbook_sources("数据结构", limit=5)

    assert parsed_urls == ["https://opendatastructures.org/ods-python/"]
    assert [result.source_result_id for result in results] == ["source-result-a19d6118"]
    assert results[0].title == "Open Data Structures (Python Edition)"
    assert results[0].source_type == "html"
    assert results[0].source_url == "https://opendatastructures.org/ods-python/"
    assert results[0].is_recommended is True


def test_search_real_textbook_sources_rejects_agent_development_docs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw_results = [
        {
            "title": "LangChain Agents 概念与开发指南",
            "original_title": "LangChain Agents",
            "language": "en",
            "source_url": "https://python.langchain.com/docs/concepts/agents/",
            "source_type": "html",
            "provider_name": "LangChain",
            "description": "Agent developer guide and documentation.",
            "tags": ["agent开发"],
            "parseability_score": 95,
            "parseability_reason": "HTML docs are parseable.",
            "topic_summary": "介绍 LangChain agent 开发。",
        },
        {
            "title": "LLM Powered Autonomous Agents",
            "original_title": "LLM Powered Autonomous Agents",
            "language": "en",
            "source_url": "https://lilianweng.github.io/posts/2023-06-23-agent/",
            "source_type": "html",
            "provider_name": "Lilian Weng Blog",
            "description": "Blog article about LLM agents.",
            "tags": ["agent开发"],
            "parseability_score": 92,
            "parseability_reason": "结构清晰的博客。",
            "topic_summary": "介绍 LLM agent 架构。",
        },
        {
            "title": "AI Agents in LangGraph",
            "original_title": "AI Agents in LangGraph",
            "language": "en",
            "source_url": "https://www.deeplearning.ai/short-courses/ai-agents-in-langgraph/",
            "source_type": "html",
            "provider_name": "DeepLearning.AI",
            "description": "Short course page.",
            "tags": ["agent开发"],
            "parseability_score": 90,
            "parseability_reason": "课程介绍页包含模块划分。",
            "topic_summary": "介绍 LangGraph agent 开发。",
        },
        {
            "title": "从零开始构建智能体 (Hello-Agents)",
            "original_title": "Hello-Agents",
            "language": "zh",
            "source_url": "https://github.com/datawhalechina/hello-agents",
            "source_type": "html",
            "provider_name": "Datawhale",
            "description": "GitHub 仓库 README 和 Markdown 文档。",
            "tags": ["agent开发"],
            "parseability_score": 88,
            "parseability_reason": "GitHub仓库的README和Markdown文档结构清晰。",
            "topic_summary": "介绍智能体开发实践。",
        },
        {
            "title": "Dify 智能体 (Agent) 构建与编排指南",
            "original_title": "Dify Agent Guide",
            "language": "zh",
            "source_url": (
                "https://docs.dify.ai/zh-hans/guides/application-orchestrate/agent"
            ),
            "source_type": "html",
            "provider_name": "Dify",
            "description": "Dify 文档站点。",
            "tags": ["agent开发"],
            "parseability_score": 86,
            "parseability_reason": "文档站点结构规范。",
            "topic_summary": "介绍 Dify agent 配置。",
        },
    ]
    parsed_urls: list[str] = []
    reachable_urls = {
        "https://artint.info/3e/html/ArtInt3e.html",
        "https://python.langchain.com/docs/concepts/agents/",
        "https://lilianweng.github.io/posts/2023-06-23-agent/",
        "https://www.deeplearning.ai/short-courses/ai-agents-in-langgraph/",
        "https://github.com/datawhalechina/hello-agents",
        "https://docs.dify.ai/zh-hans/guides/application-orchestrate/agent",
    }

    monkeypatch.setattr(
        knowledge_base_service,
        "_search_real_textbook_sources_with_llm",
        lambda topic, limit: raw_results,
    )
    monkeypatch.setattr(
        knowledge_base_service,
        "_is_reachable_textbook_url",
        lambda url: url in reachable_urls,
    )

    def parse_source(
        source_url: str, language: str, **kwargs: object
    ) -> tuple[dict, dict[str, str]]:
        parsed_urls.append(source_url)
        return (
            {
                "chapters": [
                    {
                        "chapter_number": 1,
                        "title": "Part I Agents in the World",
                        "sections": [
                            {
                                "section_id": "sec_1_1",
                                "title": "What are Agents and How Can They be Built?",
                            }
                        ],
                    }
                ]
            },
            {"sec_1_1": f"Real textbook content from {source_url}."},
        )

    monkeypatch.setattr(
        knowledge_base_service,
        "parse_textbook_source_to_sections",
        parse_source,
    )

    results = knowledge_base_service.search_real_textbook_sources("agent开发", limit=5)

    assert parsed_urls == ["https://artint.info/3e/html/ArtInt3e.html"]
    assert [result.source_url for result in results] == [
        "https://artint.info/3e/html/ArtInt3e.html"
    ]
    assert results[0].title == (
        "Artificial Intelligence: Foundations of Computational Agents"
    )
    assert results[0].is_recommended is True


def test_search_real_textbook_sources_returns_five_known_open_textbooks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reachable_urls = {
        "https://opendatastructures.org/ods-python/",
        "https://opendatastructures.org/ods-java/",
        "https://opendatastructures.org/ods-cpp/",
        ("https://pressbooks.palni.org/anopenguidetodatastructuresandalgorithms/"),
        "https://opendsa-server.cs.vt.edu/ODSA/Books/Everything/html/",
    }

    monkeypatch.setattr(
        knowledge_base_service,
        "_search_real_textbook_sources_with_llm",
        lambda topic, limit: [],
    )
    monkeypatch.setattr(
        knowledge_base_service,
        "_is_reachable_textbook_url",
        lambda url: url in reachable_urls,
    )
    monkeypatch.setattr(
        knowledge_base_service,
        "parse_textbook_source_to_sections",
        lambda source_url, language, **kwargs: (
            {
                "chapters": [
                    {
                        "chapter_number": 1,
                        "title": "1. Introduction",
                        "sections": [
                            {
                                "section_id": "sec_1_1",
                                "title": "1.1 The Need for Efficiency",
                            }
                        ],
                    }
                ]
            },
            {"sec_1_1": f"Real textbook content from {source_url}."},
        ),
    )

    results = knowledge_base_service.search_real_textbook_sources("数据结构", limit=5)

    assert [result.source_url for result in results] == [
        "https://opendatastructures.org/ods-python/",
        "https://opendatastructures.org/ods-java/",
        "https://opendatastructures.org/ods-cpp/",
        ("https://pressbooks.palni.org/anopenguidetodatastructuresandalgorithms/"),
        "https://opendsa-server.cs.vt.edu/ODSA/Books/Everything/html/",
    ]
    assert [result.is_recommended for result in results] == [
        True,
        False,
        False,
        False,
        False,
    ]


def test_search_real_textbook_sources_skips_parse_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw_results = [
        {
            "title": "Broken PDF",
            "original_title": "Broken PDF",
            "language": "en",
            "source_url": "https://opendatastructures.org/ods-python.pdf",
            "source_type": "pdf",
            "provider_name": "Open Data Structures",
            "description": "PDF source.",
            "tags": ["数据结构"],
            "parseability_score": 95,
            "parseability_reason": "PDF source.",
            "topic_summary": "覆盖数据结构。",
        }
    ]

    monkeypatch.setattr(
        knowledge_base_service,
        "_search_real_textbook_sources_with_llm",
        lambda topic, limit: raw_results,
    )
    monkeypatch.setattr(
        knowledge_base_service,
        "_is_reachable_textbook_url",
        lambda url: (
            url
            in {
                "https://opendatastructures.org/ods-python/",
                "https://opendatastructures.org/ods-python.pdf",
            }
        ),
    )

    def parse_source(
        source_url: str, language: str, **kwargs: object
    ) -> tuple[dict, dict[str, str]]:
        if source_url == "https://opendatastructures.org/ods-python.pdf":
            raise knowledge_base_service.DocumentParseError("PDF 无法切片。")
        return (
            {
                "chapters": [
                    {
                        "chapter_number": 1,
                        "title": "1. Introduction",
                        "sections": [
                            {
                                "section_id": "sec_1_1",
                                "title": "1.1 The Need for Efficiency",
                            }
                        ],
                    }
                ]
            },
            {"sec_1_1": "Real Open Data Structures section content."},
        )

    monkeypatch.setattr(
        knowledge_base_service,
        "parse_textbook_source_to_sections",
        parse_source,
    )

    results = knowledge_base_service.search_real_textbook_sources("数据结构", limit=5)

    assert [result.source_url for result in results] == [
        "https://opendatastructures.org/ods-python/"
    ]


def test_run_knowledge_base_agent_source_search_does_not_create_textbook(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = _knowledge_engine(tmp_path)
    run_schema_upgrades(engine)
    SQLModel.metadata.create_all(engine)

    source_result = app_schemas.KnowledgeBaseSourceResult(
        source_result_id="source-result-ods-python",
        title="Open Data Structures",
        original_title="Open Data Structures",
        language="en",
        source_url="https://opendatastructures.org/ods-python.pdf",
        source_type="pdf",
        provider_name="Open Data Structures",
        description="Open textbook.",
        tags=["数据结构"],
        parseability_score=95,
        parseability_reason="PDF 稳定可访问。",
        topic_summary="覆盖数据结构。",
        is_recommended=True,
    )
    monkeypatch.setattr(
        knowledge_base_service,
        "search_real_textbook_sources",
        lambda topic, limit=5: [source_result],
    )

    with Session(engine) as session:
        session.add(_admitted_source())
        response = knowledge_base_service.run_knowledge_base_agent(session, "数据结构")
        textbooks = session.exec(select(Textbook)).all()

    assert response.selected_textbook_id is None
    assert response.selected_source_result_id == "source-result-ods-python"
    assert len(response.source_results) == 1
    assert textbooks == []


def test_hybrid_search_textbooks_falls_back_cleanly(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = _knowledge_engine(tmp_path)
    run_schema_upgrades(engine)
    SQLModel.metadata.create_all(engine)

    textbook = _textbook(textbook_id="textbook-hybrid", title="FastAPI 高性能开发")
    textbook.student_availability_status = "published"

    with Session(engine) as session:
        session.add(textbook)
        session.commit()

        results = knowledge_base_service.hybrid_search_textbooks(session, "FastAPI", 10)

    assert results
    assert results[0].title == "FastAPI 高性能开发"


def test_schema_upgrades_create_knowledge_base_tables(tmp_path: Path) -> None:
    engine = _knowledge_engine(tmp_path)

    run_schema_upgrades(engine)
    run_schema_upgrades(engine)
    SQLModel.metadata.create_all(engine)

    inspector = inspect(engine)
    for model in KNOWLEDGE_MODELS:
        assert inspector.has_table(model.__tablename__)


def test_knowledge_json_fields_use_jsonb(tmp_path: Path) -> None:
    engine = _knowledge_engine(tmp_path)
    run_schema_upgrades(engine)

    inspector = inspect(engine)
    json_fields = {
        Textbook.__tablename__: {"tags", "outline"},
        KnowledgeGap.__tablename__: {"student_goal_summaries"},
        KnowledgeGapNotice.__tablename__: {"action_payload"},
    }

    for table_name, expected_fields in json_fields.items():
        columns = {
            column["name"]: str(column["type"]).lower()
            for column in inspector.get_columns(table_name)
        }
        for field_name in expected_fields:
            assert columns[field_name] == "jsonb"


def test_status_contracts_accept_documented_values() -> None:
    KnowledgeSourceStatusContract(
        status="enabled",
        download_status="verified",
        parse_status="supported",
        license_review_status="approved",
        human_review_status="reviewed",
    )
    TextbookStatusContract(
        ingestion_status="ready_for_outline_review",
        outline_review_status="approved",
        student_availability_status="published",
    )
    KnowledgeBaseIngestionJobStatusContract(status="running")
    KnowledgeGapStatusContract(status="material_found")
    KnowledgeGapNoticeStatusContract(
        notice_type="knowledge_gap_resolved",
        action_payload={
            "action": "regenerate_learning_path_intake",
            "learning_topic": "线性代数",
            "textbook_id": "textbook-1",
        },
    )


def test_notice_action_payload_contract_rejects_extra_keys() -> None:
    with pytest.raises(ValidationError):
        KnowledgeGapNoticeStatusContract(
            notice_type="knowledge_gap_resolved",
            action_payload={
                "action": "regenerate_learning_path_intake",
                "learning_topic": "线性代数",
                "textbook_id": "textbook-1",
                "extra": "x",
            },
        )


def test_extension_resource_render_mode_contract_accepts_documented_values() -> None:
    schema_type = getattr(app_schemas, "TextbookExtensionResourceRenderModeContract")

    for render_mode in ("reader", "video", "webpage"):
        schema_type(render_mode=render_mode)


@pytest.mark.parametrize(
    ("schema_type", "payload"),
    [
        (
            KnowledgeSourceStatusContract,
            {
                "status": "paused",
                "download_status": "verified",
                "parse_status": "supported",
                "license_review_status": "approved",
                "human_review_status": "reviewed",
            },
        ),
        (
            TextbookStatusContract,
            {
                "ingestion_status": "ready",
                "outline_review_status": "approved",
                "student_availability_status": "published",
            },
        ),
        (
            TextbookStatusContract,
            {
                "ingestion_status": "completed",
                "outline_review_status": "pending",
                "student_availability_status": "published",
            },
        ),
        (
            TextbookStatusContract,
            {
                "ingestion_status": "completed",
                "outline_review_status": "approved",
                "student_availability_status": "visible",
            },
        ),
        (KnowledgeBaseIngestionJobStatusContract, {"status": "waiting"}),
        (KnowledgeGapStatusContract, {"status": "done"}),
        (
            KnowledgeGapNoticeStatusContract,
            {
                "notice_type": "resolved",
                "action_payload": {
                    "action": "regenerate_learning_path_intake",
                    "learning_topic": "线性代数",
                    "textbook_id": "textbook-1",
                },
            },
        ),
        (
            KnowledgeGapNoticeStatusContract,
            {
                "notice_type": "knowledge_gap_resolved",
                "action_payload": {
                    "action": "refresh_outline",
                    "learning_topic": "线性代数",
                    "textbook_id": "textbook-1",
                },
            },
        ),
        (
            KnowledgeGapNoticeStatusContract,
            {
                "notice_type": "knowledge_gap_resolved",
                "action_payload": {
                    "action": "regenerate_learning_path_intake",
                    "learning_topic": "线性代数",
                },
            },
        ),
    ],
)
def test_status_contracts_reject_undocumented_values(
    schema_type: type,
    payload: dict,
) -> None:
    with pytest.raises(ValidationError):
        schema_type(**payload)


def test_extension_resource_render_mode_contract_rejects_other_values() -> None:
    schema_type = getattr(app_schemas, "TextbookExtensionResourceRenderModeContract")

    with pytest.raises(ValidationError):
        schema_type(render_mode="audio")


def _valid_notice_action_payload() -> dict[str, str]:
    return {
        "action": "regenerate_learning_path_intake",
        "learning_topic": "线性代数",
        "textbook_id": "textbook-1",
    }


@pytest.mark.parametrize(
    ("case_name", "row_factory"),
    [
        (
            "knowledge_source_status",
            lambda: KnowledgeSource(
                source_id="source-invalid-status",
                name="来源",
                status="paused",
                download_status="verified",
                parse_status="supported",
                license_review_status="approved",
                human_review_status="reviewed",
            ),
        ),
        (
            "knowledge_source_download_status",
            lambda: KnowledgeSource(
                source_id="source-invalid-download-status",
                name="来源",
                status="enabled",
                download_status="ready",
                parse_status="supported",
                license_review_status="approved",
                human_review_status="reviewed",
            ),
        ),
        (
            "knowledge_source_parse_status",
            lambda: KnowledgeSource(
                source_id="source-invalid-parse-status",
                name="来源",
                status="enabled",
                download_status="verified",
                parse_status="ready",
                license_review_status="approved",
                human_review_status="reviewed",
            ),
        ),
        (
            "knowledge_source_license_review_status",
            lambda: KnowledgeSource(
                source_id="source-invalid-license-review-status",
                name="来源",
                status="enabled",
                download_status="verified",
                parse_status="supported",
                license_review_status="pending",
                human_review_status="reviewed",
            ),
        ),
        (
            "knowledge_source_human_review_status",
            lambda: KnowledgeSource(
                source_id="source-invalid-human-review-status",
                name="来源",
                status="enabled",
                download_status="verified",
                parse_status="supported",
                license_review_status="approved",
                human_review_status="pending",
            ),
        ),
        (
            "textbook_ingestion_status",
            lambda: Textbook(
                textbook_id="textbook-invalid-ingestion",
                source_id="source-1",
                title="教材",
                ingestion_status="ready",
                outline_review_status="approved",
                student_availability_status="published",
            ),
        ),
        (
            "textbook_outline_review_status",
            lambda: Textbook(
                textbook_id="textbook-invalid-outline-review",
                source_id="source-1",
                title="教材",
                ingestion_status="completed",
                outline_review_status="pending",
                student_availability_status="published",
            ),
        ),
        (
            "textbook_student_availability_status",
            lambda: Textbook(
                textbook_id="textbook-invalid-student-availability",
                source_id="source-1",
                title="教材",
                ingestion_status="completed",
                outline_review_status="approved",
                student_availability_status="visible",
            ),
        ),
        (
            "textbook_extension_resource_render_mode",
            lambda: TextbookExtensionResource(
                resource_id="resource-invalid-render-mode",
                textbook_id="textbook-1",
                section_id="1.1",
                resource_type="video",
                title_zh="扩展资料",
                render_mode="audio",
            ),
        ),
        (
            "knowledge_gap_status",
            lambda: KnowledgeGap(
                gap_id="gap-invalid-status",
                normalized_topic="线性代数",
                status="done",
            ),
        ),
        (
            "knowledge_gap_notice_type",
            lambda: KnowledgeGapNotice(
                notice_id="notice-invalid-type",
                gap_id="gap-1",
                user_uid="user-1",
                notice_type="resolved",
                title="主题已补齐",
                action_payload=_valid_notice_action_payload(),
            ),
        ),
        (
            "knowledge_gap_notice_action_payload_action",
            lambda: KnowledgeGapNotice(
                notice_id="notice-invalid-action",
                gap_id="gap-1",
                user_uid="user-1",
                notice_type="knowledge_gap_resolved",
                title="主题已补齐",
                action_payload={
                    "action": "refresh_outline",
                    "learning_topic": "线性代数",
                    "textbook_id": "textbook-1",
                },
            ),
        ),
        (
            "knowledge_gap_notice_action_payload_keys",
            lambda: KnowledgeGapNotice(
                notice_id="notice-invalid-payload-keys",
                gap_id="gap-1",
                user_uid="user-1",
                notice_type="knowledge_gap_resolved",
                title="主题已补齐",
                action_payload={
                    "action": "regenerate_learning_path_intake",
                    "learning_topic": "线性代数",
                },
            ),
        ),
        (
            "knowledge_gap_notice_action_payload_extra_keys",
            lambda: KnowledgeGapNotice(
                notice_id="notice-invalid-payload-extra-keys",
                gap_id="gap-1",
                user_uid="user-1",
                notice_type="knowledge_gap_resolved",
                title="主题已补齐",
                action_payload={
                    "action": "regenerate_learning_path_intake",
                    "learning_topic": "线性代数",
                    "textbook_id": "textbook-1",
                    "extra": "x",
                },
            ),
        ),
        (
            "knowledge_base_ingestion_job_status",
            lambda: KnowledgeBaseIngestionJob(
                job_id="job-invalid-status",
                textbook_id="textbook-1",
                job_type="parse",
                status="waiting",
            ),
        ),
    ],
)
def test_persistence_rejects_undocumented_values(
    tmp_path: Path,
    case_name: str,
    row_factory: object,
) -> None:
    engine = _knowledge_engine(tmp_path / case_name)
    run_schema_upgrades(engine)

    with Session(engine) as session:
        session.add(row_factory())
        with pytest.raises(IntegrityError):
            session.commit()


def test_section_content_zh_is_stored_exactly(tmp_path: Path) -> None:
    engine = _knowledge_engine(tmp_path)
    run_schema_upgrades(engine)
    SQLModel.metadata.create_all(engine)

    content_zh = "这是学生端生成链路使用的唯一中文正文来源。\n第二行必须保持不变。"
    with Session(engine) as session:
        session.add(
            TextbookSectionContent(
                section_content_id="section-content-1",
                textbook_id="textbook-1",
                section_id="1.1",
                parent_section_id="1",
                order_index=1,
                title="向量空间",
                original_title="Vector Spaces",
                content_zh=content_zh,
                content_char_count=len(content_zh),
            )
        )
        session.commit()

    with Session(engine) as session:
        stored = session.get(TextbookSectionContent, "section-content-1")
        assert stored is not None
        assert stored.content_zh == content_zh
        assert stored.content_char_count == len(content_zh)


def test_notice_action_payload_persists_when_documented_shape_is_used(
    tmp_path: Path,
) -> None:
    engine = _knowledge_engine(tmp_path)
    run_schema_upgrades(engine)
    SQLModel.metadata.create_all(engine)

    payload = _valid_notice_action_payload()
    with Session(engine) as session:
        session.add(
            KnowledgeGapNotice(
                notice_id="notice-valid-action-payload",
                gap_id="gap-1",
                user_uid="user-1",
                title="主题已补齐",
                action_payload=payload,
            )
        )
        session.commit()

    with Session(engine) as session:
        stored = session.get(KnowledgeGapNotice, "notice-valid-action-payload")
        assert stored is not None
        assert stored.action_payload == payload


def test_gap_topic_and_section_identity_are_unique(tmp_path: Path) -> None:
    engine = _knowledge_engine(tmp_path)
    run_schema_upgrades(engine)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        session.add(
            KnowledgeGap(
                gap_id="gap-topic-1",
                normalized_topic="线性代数",
            )
        )
        session.commit()

        session.add(
            KnowledgeGap(
                gap_id="gap-topic-2",
                normalized_topic="线性代数",
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

        session.add(
            _section(
                textbook_id="textbook-section-identity",
                section_content_id="section-identity-1",
                section_id="1.1",
                title="矩阵乘法",
                content_zh="第一份正文",
            )
        )
        session.commit()

        session.add(
            _section(
                textbook_id="textbook-section-identity",
                section_content_id="section-identity-2",
                section_id="1.1",
                title="矩阵乘法",
                content_zh="第二份正文",
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()


def test_schema_upgrades_replaces_loose_notice_action_payload_check(
    tmp_path: Path,
) -> None:
    engine = _knowledge_engine(tmp_path)
    run_schema_upgrades(engine)

    with engine.begin() as connection:
        connection.execute(
            text(
                "ALTER TABLE knowledgegapnotice "
                "DROP CONSTRAINT ck_knowledgegapnotice_action_payload"
            )
        )
        connection.execute(
            text(
                """
                ALTER TABLE knowledgegapnotice
                ADD CONSTRAINT ck_knowledgegapnotice_action_payload
                CHECK (
                    (action_payload IS NOT NULL)
                    AND (jsonb_typeof(action_payload) = 'object')
                    AND (action_payload ? 'action')
                    AND (action_payload ? 'learning_topic')
                    AND (action_payload ? 'textbook_id')
                    AND (
                        (action_payload ->> 'action')
                        = 'regenerate_learning_path_intake'
                    )
                    AND ((action_payload ->> 'learning_topic') IS NOT NULL)
                    AND ((action_payload ->> 'textbook_id') IS NOT NULL)
                ) NOT VALID
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO knowledgegapnotice
                    (
                        notice_id, gap_id, user_uid, notice_type, title, body,
                        action_label, action_payload, read_at, created_at
                    )
                VALUES
                    (
                        'notice-legacy-extra-action-payload', 'gap-1', 'user-1',
                        'knowledge_gap_resolved', '主题已补齐', '',
                        '重新生成学习路径',
                        '{"action":"regenerate_learning_path_intake","learning_topic":"线性代数","textbook_id":"textbook-1","extra":"x"}'::jsonb,
                        NULL, '2026-06-01 00:00:00'
                    )
                """
            )
        )

    run_schema_upgrades(engine)
    run_schema_upgrades(engine)

    with Session(engine) as session:
        upgraded_notice = session.get(
            KnowledgeGapNotice, "notice-legacy-extra-action-payload"
        )
        assert upgraded_notice is not None
        assert upgraded_notice.action_payload == _valid_notice_action_payload()

    with Session(engine) as session:
        session.add(
            KnowledgeGapNotice(
                notice_id="notice-upgraded-action-payload",
                gap_id="gap-1",
                user_uid="user-1",
                title="主题已补齐",
                action_payload=_valid_notice_action_payload() | {"extra": "x"},
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()


def test_source_crud_and_admission_gate_filtering(tmp_path: Path) -> None:
    engine = _knowledge_engine(tmp_path)
    run_schema_upgrades(engine)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        admitted_source = create_knowledge_source(
            session,
            _knowledge_source(
                source_id="source-admitted",
                name="已准入来源",
                download_status="verified",
                parse_status="supported",
                license_review_status="approved",
                human_review_status="reviewed",
            ),
        )
        blocked_source = create_knowledge_source(
            session,
            _knowledge_source(
                source_id="source-blocked",
                name="未审查来源",
                download_status="verified",
                parse_status="supported",
                license_review_status="approved",
                human_review_status="unreviewed",
            ),
        )

        assert is_source_admitted_for_primary_textbook(admitted_source) is True
        assert is_source_admitted_for_primary_textbook(blocked_source) is False
        assert [row.source_id for row in list_knowledge_sources(session)] == [
            "source-admitted",
            "source-blocked",
        ]
        assert [row.source_id for row in list_admitted_knowledge_sources(session)] == [
            "source-admitted"
        ]

        updated_source = update_knowledge_source(
            session,
            "source-blocked",
            human_review_status="reviewed",
            name="已补审来源",
        )

        assert updated_source.name == "已补审来源"
        assert [row.source_id for row in list_admitted_knowledge_sources(session)] == [
            "source-admitted",
            "source-blocked",
        ]
        assert delete_knowledge_source(session, "source-blocked") is True
        assert session.get(KnowledgeSource, "source-blocked") is None


def test_disabled_source_is_excluded_from_primary_textbook_admission(
    tmp_path: Path,
) -> None:
    engine = _knowledge_engine(tmp_path)
    run_schema_upgrades(engine)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        admitted_source = create_knowledge_source(session, _admitted_source())
        disabled_source = create_knowledge_source(
            session,
            _knowledge_source(
                source_id="source-disabled",
                name="停用来源",
                status="disabled",
                download_status="verified",
                parse_status="supported",
                license_review_status="approved",
                human_review_status="reviewed",
            ),
        )

        assert is_source_admitted_for_primary_textbook(admitted_source) is True
        assert is_source_admitted_for_primary_textbook(disabled_source) is False
        assert [row.source_id for row in list_admitted_knowledge_sources(session)] == [
            "source-admitted"
        ]


def test_update_knowledge_source_rejects_invalid_key_without_partial_write(
    tmp_path: Path,
) -> None:
    engine = _knowledge_engine(tmp_path)
    run_schema_upgrades(engine)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        create_knowledge_source(
            session,
            _knowledge_source(source_id="source-partial-update", name="原始来源"),
        )

        with pytest.raises(ValueError, match="知识来源字段不存在：missing_field"):
            update_knowledge_source(
                session,
                "source-partial-update",
                name="不应写入",
                missing_field="无效字段",
            )

        session.add(_knowledge_source(source_id="source-later-commit", name="稍后提交"))
        session.commit()
        session.expire_all()

        stored_source = session.get(KnowledgeSource, "source-partial-update")
        assert stored_source is not None
        assert stored_source.name == "原始来源"


def test_update_knowledge_source_rejects_runtime_attribute_without_partial_write(
    tmp_path: Path,
) -> None:
    engine = _knowledge_engine(tmp_path)
    run_schema_upgrades(engine)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        create_knowledge_source(
            session,
            _knowledge_source(source_id="source-runtime-attribute", name="原始来源"),
        )

        with pytest.raises(ValueError, match="知识来源字段不存在：metadata"):
            update_knowledge_source(
                session,
                "source-runtime-attribute",
                name="不应写入",
                metadata="无效字段",
            )

        session.add(
            _knowledge_source(source_id="source-runtime-later", name="稍后提交")
        )
        session.commit()
        session.expire_all()

        stored_source = session.get(KnowledgeSource, "source-runtime-attribute")
        assert stored_source is not None
        assert stored_source.name == "原始来源"


def test_upsert_structured_textbook_replaces_sections_and_counts_content(
    tmp_path: Path,
) -> None:
    engine = _knowledge_engine(tmp_path)
    run_schema_upgrades(engine)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        create_knowledge_source(session, _admitted_source())
        textbook = _textbook(
            textbook_id="textbook-structured",
            title="线性代数",
            outline={
                "sections": [
                    {
                        "section_id": "1",
                        "title": "矩阵",
                        "children": [
                            {"section_id": "1.1", "title": "矩阵乘法"},
                            {"section_id": "1.2", "title": "行列式"},
                        ],
                    }
                ]
            },
        )
        first_content = "矩阵乘法的中文正文"

        stored_textbook = upsert_structured_textbook(
            session,
            textbook,
            [
                _section(
                    textbook_id="textbook-structured",
                    section_content_id="section-content-old",
                    section_id="1.1",
                    title="矩阵乘法",
                    content_zh=first_content,
                    content_char_count=0,
                )
            ],
        )

        assert stored_textbook.textbook_id == "textbook-structured"
        stored_section = session.get(TextbookSectionContent, "section-content-old")
        assert stored_section is not None
        assert stored_section.content_char_count == len(first_content)

        replacement_content = "行列式的中文正文"
        upsert_structured_textbook(
            session,
            textbook,
            [
                _section(
                    textbook_id="textbook-structured",
                    section_content_id="section-content-new",
                    section_id="1.2",
                    title="行列式",
                    content_zh=replacement_content,
                    content_char_count=999,
                )
            ],
        )

        assert session.get(TextbookSectionContent, "section-content-old") is None
        replacement_section = session.get(TextbookSectionContent, "section-content-new")
        assert replacement_section is not None
        assert replacement_section.content_char_count == len(replacement_content)


def test_upsert_structured_textbook_rejects_duplicate_section_ids(
    tmp_path: Path,
) -> None:
    engine = _knowledge_engine(tmp_path)
    run_schema_upgrades(engine)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        textbook = _textbook(
            textbook_id="textbook-duplicate-section-id",
            title="重复小节教材",
            outline={"sections": [{"section_id": "1.1", "title": "矩阵乘法"}]},
        )

        with pytest.raises(ValueError, match="教材小节重复。"):
            upsert_structured_textbook(
                session,
                textbook,
                [
                    _section(
                        textbook_id="textbook-duplicate-section-id",
                        section_content_id="section-duplicate-id-1",
                        section_id="1.1",
                        title="矩阵乘法",
                        content_zh="第一份正文",
                    ),
                    _section(
                        textbook_id="textbook-duplicate-section-id",
                        section_content_id="section-duplicate-id-2",
                        section_id="1.1",
                        title="矩阵乘法",
                        content_zh="第二份正文",
                    ),
                ],
            )

        assert session.get(Textbook, "textbook-duplicate-section-id") is None
        assert session.get(TextbookSectionContent, "section-duplicate-id-1") is None
        assert session.get(TextbookSectionContent, "section-duplicate-id-2") is None


def test_upsert_structured_textbook_rejects_published_status(
    tmp_path: Path,
) -> None:
    engine = _knowledge_engine(tmp_path)
    run_schema_upgrades(engine)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        textbook = _textbook(
            textbook_id="textbook-published-ingest",
            title="已发布入库教材",
            outline={"sections": [{"section_id": "1.1", "title": "矩阵乘法"}]},
            outline_review_status="approved",
        )
        textbook.student_availability_status = "published"

        with pytest.raises(ValueError, match="结构化入库不能直接发布教材。"):
            upsert_structured_textbook(
                session,
                textbook,
                [
                    _section(
                        textbook_id="textbook-published-ingest",
                        section_content_id="section-published-ingest",
                        section_id="1.1",
                        title="矩阵乘法",
                        content_zh="矩阵乘法正文",
                    )
                ],
            )


def test_upsert_structured_textbook_rejects_existing_published_textbook(
    tmp_path: Path,
) -> None:
    engine = _knowledge_engine(tmp_path)
    run_schema_upgrades(engine)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        create_knowledge_source(session, _admitted_source())
        upsert_structured_textbook(
            session,
            _textbook(
                textbook_id="textbook-published-reingest",
                title="已发布教材",
                outline={"sections": [{"section_id": "1.1", "title": "矩阵乘法"}]},
                outline_review_status="approved",
            ),
            [
                _section(
                    textbook_id="textbook-published-reingest",
                    section_content_id="section-published-reingest-old",
                    section_id="1.1",
                    title="矩阵乘法",
                    content_zh="已发布正文",
                )
            ],
        )
        published_textbook = publish_textbook(session, "textbook-published-reingest")
        published_at = published_textbook.published_at
        assert published_at is not None

        with pytest.raises(ValueError):
            upsert_structured_textbook(
                session,
                _textbook(
                    textbook_id="textbook-published-reingest",
                    title="默认草稿入库",
                    outline={"sections": [{"section_id": "1.1", "title": "矩阵乘法"}]},
                    outline_review_status="approved",
                ),
                [
                    _section(
                        textbook_id="textbook-published-reingest",
                        section_content_id="section-published-reingest-new",
                        section_id="1.1",
                        title="矩阵乘法",
                        content_zh="不应写入的新正文",
                    )
                ],
            )

        session.expire_all()
        stored_textbook = session.get(Textbook, "textbook-published-reingest")
        assert stored_textbook is not None
        assert stored_textbook.student_availability_status == "published"
        assert stored_textbook.published_at == published_at
        assert stored_textbook.title == "已发布教材"
        new_section = session.get(
            TextbookSectionContent, "section-published-reingest-new"
        )
        assert new_section is None
        old_section = session.get(
            TextbookSectionContent, "section-published-reingest-old"
        )
        assert old_section is not None
        assert old_section.content_zh == "已发布正文"


def test_upsert_structured_textbook_rejects_sections_outside_outline(
    tmp_path: Path,
) -> None:
    engine = _knowledge_engine(tmp_path)
    run_schema_upgrades(engine)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        textbook = _textbook(
            textbook_id="textbook-outline-bound",
            title="目录绑定教材",
            outline={"sections": [{"section_id": "1.1", "title": "矩阵乘法"}]},
        )
        upsert_structured_textbook(
            session,
            textbook,
            [
                _section(
                    textbook_id="textbook-outline-bound",
                    section_content_id="section-outline-bound-old",
                    section_id="1.1",
                    title="矩阵乘法",
                    content_zh="旧正文",
                )
            ],
        )

        with pytest.raises(ValueError, match="教材小节不存在。"):
            upsert_structured_textbook(
                session,
                textbook,
                [
                    _section(
                        textbook_id="textbook-outline-bound",
                        section_content_id="section-outline-bound-new",
                        section_id="9.9",
                        title="未声明小节",
                        content_zh="新正文",
                    )
                ],
            )

        assert (
            session.get(TextbookSectionContent, "section-outline-bound-old") is not None
        )
        assert session.get(TextbookSectionContent, "section-outline-bound-new") is None


def test_upsert_structured_textbook_uses_stored_outline_for_existing_textbook(
    tmp_path: Path,
) -> None:
    engine = _knowledge_engine(tmp_path)
    run_schema_upgrades(engine)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        upsert_structured_textbook(
            session,
            _textbook(
                textbook_id="textbook-stored-outline-bound",
                title="已存目录教材",
                outline={"sections": [{"section_id": "1.1", "title": "矩阵乘法"}]},
            ),
            [
                _section(
                    textbook_id="textbook-stored-outline-bound",
                    section_content_id="section-stored-outline-old",
                    section_id="1.1",
                    title="矩阵乘法",
                    content_zh="旧正文",
                )
            ],
        )

        incoming_textbook = _textbook(
            textbook_id="textbook-stored-outline-bound",
            title="已存目录教材",
            outline={
                "sections": [
                    {"section_id": "1.1", "title": "矩阵乘法"},
                    {"section_id": "1.2", "title": "行列式"},
                ]
            },
        )

        with pytest.raises(ValueError, match="教材小节不存在。"):
            upsert_structured_textbook(
                session,
                incoming_textbook,
                [
                    _section(
                        textbook_id="textbook-stored-outline-bound",
                        section_content_id="section-stored-outline-new",
                        section_id="1.2",
                        title="行列式",
                        content_zh="新正文",
                    )
                ],
            )

        assert (
            session.get(TextbookSectionContent, "section-stored-outline-old")
            is not None
        )
        assert session.get(TextbookSectionContent, "section-stored-outline-new") is None


def test_upsert_structured_textbook_rejects_section_missing_from_final_outline(
    tmp_path: Path,
) -> None:
    engine = _knowledge_engine(tmp_path)
    run_schema_upgrades(engine)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        upsert_structured_textbook(
            session,
            _textbook(
                textbook_id="textbook-final-outline-bound",
                title="最终目录教材",
                outline={"sections": [{"section_id": "1.1", "title": "矩阵乘法"}]},
            ),
            [
                _section(
                    textbook_id="textbook-final-outline-bound",
                    section_content_id="section-final-outline-old",
                    section_id="1.1",
                    title="矩阵乘法",
                    content_zh="旧正文",
                )
            ],
        )

        incoming_textbook = _textbook(
            textbook_id="textbook-final-outline-bound",
            title="最终目录教材",
            outline={"sections": [{"section_id": "2.1", "title": "向量空间"}]},
        )

        with pytest.raises(ValueError, match="教材小节不存在。"):
            upsert_structured_textbook(
                session,
                incoming_textbook,
                [
                    _section(
                        textbook_id="textbook-final-outline-bound",
                        section_content_id="section-final-outline-new",
                        section_id="1.1",
                        title="矩阵乘法",
                        content_zh="新正文",
                    )
                ],
            )

        stored_textbook = session.get(Textbook, "textbook-final-outline-bound")
        assert stored_textbook is not None
        assert stored_textbook.outline == {
            "sections": [{"section_id": "1.1", "title": "矩阵乘法"}]
        }
        assert (
            session.get(TextbookSectionContent, "section-final-outline-old") is not None
        )
        assert session.get(TextbookSectionContent, "section-final-outline-new") is None


def test_publish_textbook_enforces_service_gates(tmp_path: Path) -> None:
    engine = _knowledge_engine(tmp_path)
    run_schema_upgrades(engine)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        session.add(
            _textbook(
                textbook_id="textbook-missing-source",
                source_id="source-missing",
                title="缺少来源",
                outline={"sections": [{"section_id": "1", "title": "矩阵"}]},
                outline_review_status="approved",
            )
        )
        session.add(_knowledge_source(source_id="source-blocked", name="未准入来源"))
        session.add(
            _textbook(
                textbook_id="textbook-blocked-source",
                source_id="source-blocked",
                title="未准入教材",
                outline={"sections": [{"section_id": "1", "title": "矩阵"}]},
                outline_review_status="approved",
            )
        )
        session.add(_admitted_source())
        session.add(
            _textbook(
                textbook_id="textbook-empty-outline",
                title="空目录教材",
                outline={},
                outline_review_status="approved",
            )
        )
        session.add(
            _textbook(
                textbook_id="textbook-no-content",
                title="无正文教材",
                outline={"sections": [{"section_id": "1", "title": "矩阵"}]},
                outline_review_status="approved",
            )
        )
        session.add(
            _section(
                textbook_id="textbook-no-content",
                section_content_id="section-empty-content",
                section_id="1.1",
                content_zh="",
            )
        )
        session.add(
            _textbook(
                textbook_id="textbook-unreviewed-outline",
                title="未校对目录教材",
                outline={"sections": [{"section_id": "1.1", "title": "矩阵"}]},
                outline_review_status="unreviewed",
            )
        )
        session.add(
            _section(
                textbook_id="textbook-unreviewed-outline",
                section_content_id="section-unreviewed-outline",
                section_id="1.1",
                content_zh="矩阵正文",
            )
        )
        session.commit()

        for textbook_id, message in (
            ("textbook-missing-source", "教材来源未通过准入校验。"),
            ("textbook-blocked-source", "教材来源未通过准入校验。"),
            ("textbook-empty-outline", "教材缺少中文目录。"),
            ("textbook-no-content", "教材缺少中文正文。"),
        ):
            with pytest.raises(ValueError, match=message):
                publish_textbook(session, textbook_id)

        # Test publishing unreviewed outline automatically approves it
        published_tb = publish_textbook(session, "textbook-unreviewed-outline")
        assert published_tb.outline_review_status == "approved"
        assert published_tb.student_availability_status == "published"

        session.add(
            _textbook(
                textbook_id="textbook-mixed-content",
                title="部分空白正文教材",
                outline={"sections": [{"section_id": "1", "title": "矩阵"}]},
                outline_review_status="approved",
            )
        )
        session.add(
            _section(
                textbook_id="textbook-mixed-content",
                section_content_id="section-whitespace-content",
                section_id="1.1",
                content_zh="   ",
                order_index=1,
            )
        )
        session.add(
            _section(
                textbook_id="textbook-mixed-content",
                section_content_id="section-valid-content",
                section_id="1.2",
                content_zh="有效中文正文",
                order_index=2,
            )
        )
        session.commit()

        with pytest.raises(ValueError, match="教材缺少完整中文正文。"):
            publish_textbook(session, "textbook-mixed-content")

        session.add(
            _textbook(
                textbook_id="textbook-missing-outline-content-row",
                title="缺少目录正文行教材",
                outline={
                    "sections": [
                        {
                            "section_id": "1",
                            "title": "矩阵",
                            "children": [
                                {"section_id": "1.1", "title": "矩阵乘法"},
                                {"section_id": "1.2", "title": "行列式"},
                            ],
                        }
                    ]
                },
                outline_review_status="approved",
            )
        )
        session.add(
            _section(
                textbook_id="textbook-missing-outline-content-row",
                section_content_id="section-missing-outline-content-row",
                section_id="1.1",
                content_zh="矩阵乘法正文",
            )
        )
        session.commit()

        with pytest.raises(ValueError, match="教材缺少完整中文正文。"):
            publish_textbook(session, "textbook-missing-outline-content-row")


def test_publish_textbook_allows_english_original_content(
    tmp_path: Path,
) -> None:
    engine = _knowledge_engine(tmp_path)
    run_schema_upgrades(engine)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        session.add(_admitted_source())
        session.add(
            _textbook(
                textbook_id="textbook-english-without-zh",
                title="Open Data Structures",
                outline={"sections": [{"section_id": "1.1", "title": "Arrays"}]},
                outline_review_status="approved",
                language="en",
                translated_language="zh",
            )
        )
        session.add(
            _section(
                textbook_id="textbook-english-without-zh",
                section_content_id="section-english-without-zh",
                section_id="1.1",
                content_original="Arrays store elements in contiguous memory.",
                content_zh="Arrays store elements in contiguous memory.",
            )
        )
        session.commit()

        published = publish_textbook(session, "textbook-english-without-zh")

    assert published.student_availability_status == "published"
    assert published.published_at is not None


def test_publish_textbook_allows_english_textbook_with_chinese_annotation(
    tmp_path: Path,
) -> None:
    engine = _knowledge_engine(tmp_path)
    run_schema_upgrades(engine)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        session.add(_admitted_source())
        session.add(
            _textbook(
                textbook_id="textbook-english-with-zh",
                title="Open Data Structures",
                outline={"sections": [{"section_id": "1.1", "title": "Arrays"}]},
                outline_review_status="approved",
                language="en",
                translated_language="zh",
            )
        )
        session.add(
            _section(
                textbook_id="textbook-english-with-zh",
                section_content_id="section-english-with-zh",
                section_id="1.1",
                content_original="Arrays store elements in contiguous memory.",
                content_zh="数组把元素存储在连续内存中。",
            )
        )
        session.commit()

        published = publish_textbook(session, "textbook-english-with-zh")

    assert published.student_availability_status == "published"
    assert published.published_at is not None


def test_textbook_evidence_pack_uses_english_original_when_chinese_content_missing(
    tmp_path: Path,
) -> None:
    engine = _knowledge_engine(tmp_path)
    run_schema_upgrades(engine)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        session.add(_admitted_source())
        session.add(
            _textbook(
                textbook_id="textbook-english-evidence",
                title="Open Data Structures",
                outline={"sections": [{"section_id": "1.1", "title": "Arrays"}]},
                outline_review_status="approved",
                language="en",
                translated_language="zh",
                student_availability_status="published",
            )
        )
        session.add(
            _section(
                textbook_id="textbook-english-evidence",
                section_content_id="section-english-evidence",
                section_id="1.1",
                content_original="Arrays store elements by index.",
                content_zh="",
            )
        )
        session.commit()

        pack = get_textbook_evidence_pack(
            session,
            "textbook-english-evidence",
            ["1.1"],
        )

    assert pack["total_chars"] == len("Arrays store elements by index.")
    assert pack["evidence_text"] == "Arrays store elements by index."


def test_publish_textbook_rejects_outline_without_named_sections(
    tmp_path: Path,
) -> None:
    engine = _knowledge_engine(tmp_path)
    run_schema_upgrades(engine)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        session.add(_admitted_source())
        session.add(
            _textbook(
                textbook_id="textbook-empty-sections-outline",
                title="空小节目录教材",
                outline={"sections": []},
                outline_review_status="approved",
            )
        )
        session.add(
            _section(
                textbook_id="textbook-empty-sections-outline",
                section_content_id="section-empty-sections-outline",
                section_id="1.1",
                title="矩阵乘法",
                content_zh="矩阵乘法正文",
            )
        )
        session.commit()

        with pytest.raises(ValueError, match="教材缺少中文目录。"):
            publish_textbook(session, "textbook-empty-sections-outline")


def test_publish_textbook_rolls_back_when_notice_creation_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = _knowledge_engine(tmp_path)
    run_schema_upgrades(engine)
    SQLModel.metadata.create_all(engine)

    def fail_notice_creation(
        _session: Session, _textbook_id: str, *, commit: bool = True
    ) -> list[KnowledgeGapNotice]:
        assert commit is False
        raise RuntimeError("notice creation failed")

    monkeypatch.setattr(
        knowledge_base_service,
        "create_gap_resolved_notices_for_textbook",
        fail_notice_creation,
    )

    with Session(engine) as session:
        create_knowledge_source(session, _admitted_source())
        upsert_structured_textbook(
            session,
            _textbook(
                textbook_id="textbook-notice-failure",
                title="发布回滚教材",
                outline={"sections": [{"section_id": "1.1", "title": "矩阵乘法"}]},
                outline_review_status="approved",
            ),
            [
                _section(
                    textbook_id="textbook-notice-failure",
                    section_content_id="section-notice-failure",
                    section_id="1.1",
                    title="矩阵乘法",
                    content_zh="矩阵乘法正文",
                )
            ],
        )

        with pytest.raises(RuntimeError, match="notice creation failed"):
            publish_textbook(session, "textbook-notice-failure")

        session.rollback()
        session.expire_all()
        stored_textbook = session.get(Textbook, "textbook-notice-failure")
        assert stored_textbook is not None
        assert stored_textbook.student_availability_status == "draft"
        assert stored_textbook.published_at is None


def test_context_only_returns_published_summary_and_creates_gap(
    tmp_path: Path,
) -> None:
    engine = _knowledge_engine(tmp_path)
    run_schema_upgrades(engine)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        create_knowledge_source(session, _admitted_source())
        upsert_structured_textbook(
            session,
            _textbook(
                textbook_id="textbook-published",
                title="线性代数",
                description="覆盖矩阵和向量空间",
                tags=["矩阵", "向量空间"],
                outline={
                    "sections": [
                        {
                            "section_id": "1",
                            "title": "矩阵",
                            "children": [{"section_id": "1.1", "title": "矩阵乘法"}],
                        }
                    ]
                },
                outline_review_status="approved",
            ),
            [
                _section(
                    textbook_id="textbook-published",
                    section_content_id="section-context-published",
                    section_id="1.1",
                    title="矩阵乘法",
                    content_zh="矩阵乘法正文不能出现在上下文摘要里。",
                )
            ],
        )
        publish_textbook(session, "textbook-published")
        upsert_structured_textbook(
            session,
            _textbook(
                textbook_id="textbook-draft",
                title="矩阵专题草稿",
                description="未发布教材不能进入上下文",
                tags=["矩阵"],
                outline={"sections": [{"section_id": "1.1", "title": "矩阵"}]},
                outline_review_status="approved",
            ),
            [
                _section(
                    textbook_id="textbook-draft",
                    section_content_id="section-context-draft",
                    section_id="1.1",
                    title="矩阵",
                    content_zh="未发布正文",
                )
            ],
        )

        context = get_published_textbook_context_for_topic(
            session,
            "矩阵",
            student_goal_summary="希望复习矩阵计算",
        )

        assert context == {
            "textbooks": [
                {
                    "textbook_id": "textbook-published",
                    "title": "线性代数",
                    "source_id": "source-admitted",
                    "tags": ["矩阵", "向量空间"],
                    "description": "覆盖矩阵和向量空间",
                    "outline_summary": [
                        {"section_id": "1", "title": "矩阵"},
                        {"section_id": "1.1", "title": "矩阵乘法"},
                    ],
                }
            ],
            "gap_id": None,
        }
        assert "content_zh" not in str(context)

        missing_context = get_published_textbook_context_for_topic(
            session,
            "概率论",
            student_goal_summary="希望学习概率基础",
        )

        assert missing_context["textbooks"] == []
        gap = session.get(KnowledgeGap, missing_context["gap_id"])
        assert gap is not None
        assert gap.normalized_topic == "概率论"
        assert gap.student_goal_summaries == ["希望学习概率基础"]


def test_context_includes_published_textbook_matched_by_description_or_outline(
    tmp_path: Path,
) -> None:
    engine = _knowledge_engine(tmp_path)
    run_schema_upgrades(engine)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        create_knowledge_source(session, _admitted_source())
        upsert_structured_textbook(
            session,
            _textbook(
                textbook_id="textbook-description-outline",
                title="计算机科学导论",
                description="包含复杂度分析和递归思维。",
                tags=["计算机科学"],
                outline={
                    "sections": [
                        {
                            "section_id": "1",
                            "title": "基础概念",
                            "children": [{"section_id": "1.1", "title": "图遍历算法"}],
                        }
                    ]
                },
                outline_review_status="approved",
            ),
            [
                _section(
                    textbook_id="textbook-description-outline",
                    section_content_id="section-description-outline",
                    section_id="1.1",
                    title="图遍历算法",
                    content_zh="图遍历正文",
                )
            ],
        )
        publish_textbook(session, "textbook-description-outline")

        description_context = get_published_textbook_context_for_topic(
            session,
            "复杂度分析",
            student_goal_summary="希望学习复杂度",
        )
        outline_context = get_published_textbook_context_for_topic(
            session,
            "图遍历算法",
            student_goal_summary="希望学习图遍历",
        )

        assert [
            textbook["textbook_id"] for textbook in description_context["textbooks"]
        ] == ["textbook-description-outline"]
        assert description_context["gap_id"] is None
        assert [
            textbook["textbook_id"] for textbook in outline_context["textbooks"]
        ] == ["textbook-description-outline"]
        assert outline_context["gap_id"] is None
        assert session.exec(select(KnowledgeGap)).all() == []


def test_context_gap_normalizes_whitespace_topic(tmp_path: Path) -> None:
    engine = _knowledge_engine(tmp_path)
    run_schema_upgrades(engine)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        spaced_context = get_published_textbook_context_for_topic(
            session,
            " 概率论 ",
            student_goal_summary="第一次触发",
        )
        trimmed_context = get_published_textbook_context_for_topic(
            session,
            "概率论",
            student_goal_summary="第二次触发",
        )

        assert spaced_context["gap_id"] == trimmed_context["gap_id"]
        gap = session.get(KnowledgeGap, spaced_context["gap_id"])
        assert gap is not None
        assert gap.normalized_topic == "概率论"
        assert gap.trigger_count == 2
        assert gap.student_goal_summaries == ["第一次触发", "第二次触发"]


def test_evidence_pack_accepts_only_existing_contiguous_textbook_sections(
    tmp_path: Path,
) -> None:
    engine = _knowledge_engine(tmp_path)
    run_schema_upgrades(engine)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        create_knowledge_source(session, _admitted_source())
        upsert_structured_textbook(
            session,
            _textbook(
                textbook_id="textbook-evidence",
                title="证据包教材",
                outline={
                    "sections": [
                        {"section_id": f"1.{index}", "title": f"小节 {index}"}
                        for index in range(1, 10)
                    ]
                },
                outline_review_status="approved",
            ),
            [
                _section(
                    textbook_id="textbook-evidence",
                    section_content_id=f"section-evidence-{index}",
                    section_id=f"1.{index}",
                    order_index=index,
                    title=f"小节 {index}",
                    content_zh=f"第 {index} 节中文正文",
                )
                for index in range(1, 10)
            ],
        )
        publish_textbook(session, "textbook-evidence")
        upsert_structured_textbook(
            session,
            _textbook(
                textbook_id="textbook-empty-evidence",
                title="空证据包教材",
                outline={"sections": [{"section_id": "2.1", "title": "空正文"}]},
                outline_review_status="approved",
            ),
            [
                _section(
                    textbook_id="textbook-empty-evidence",
                    section_content_id="section-empty-evidence",
                    section_id="2.1",
                    order_index=1,
                    title="空正文",
                    content_zh="",
                )
            ],
        )
        empty_evidence_textbook = session.get(Textbook, "textbook-empty-evidence")
        assert empty_evidence_textbook is not None
        empty_evidence_textbook.student_availability_status = "published"
        session.add(empty_evidence_textbook)
        session.add(
            _section(
                textbook_id="textbook-evidence",
                section_content_id="section-evidence-too-long",
                section_id="1.99",
                order_index=99,
                title="超长小节",
                content_zh="字" * 8001,
            )
        )
        session.commit()

        evidence_pack = get_textbook_evidence_pack(
            session,
            "textbook-evidence",
            ["1.1", "1.2", "1.3"],
        )

        assert evidence_pack == {
            "textbook_id": "textbook-evidence",
            "title": "证据包教材",
            "sections": [
                {"section_id": "1.1", "title": "小节 1"},
                {"section_id": "1.2", "title": "小节 2"},
                {"section_id": "1.3", "title": "小节 3"},
            ],
            "total_chars": len("第 1 节中文正文第 2 节中文正文第 3 节中文正文"),
            "evidence_text": "第 1 节中文正文\n\n第 2 节中文正文\n\n第 3 节中文正文",
        }

        for section_ids, message in (
            (["1.1", "1.3"], "教材小节必须连续。"),
            ([f"1.{index}" for index in range(1, 9)], "证据包最多包含 7 个小节。"),
            (["1.1", "missing"], "教材小节不存在。"),
            (["1.99"], "证据包超过 8000 个中文字符。"),
        ):
            with pytest.raises(ValueError, match=message):
                get_textbook_evidence_pack(session, "textbook-evidence", section_ids)

        with pytest.raises(ValueError, match="证据包为空。"):
            get_textbook_evidence_pack(
                session,
                "textbook-empty-evidence",
                ["2.1"],
            )
        gap = session.exec(
            select(KnowledgeGap).where(
                KnowledgeGap.normalized_topic == "textbook-empty-evidence"
            )
        ).first()
        assert gap is not None


def test_evidence_pack_rejects_empty_section_ids_with_gap(tmp_path: Path) -> None:
    engine = _knowledge_engine(tmp_path)
    run_schema_upgrades(engine)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        create_knowledge_source(session, _admitted_source())
        upsert_structured_textbook(
            session,
            _textbook(
                textbook_id="textbook-empty-section-ids",
                title="空小节列表教材",
                outline={"sections": [{"section_id": "1.1", "title": "矩阵乘法"}]},
                outline_review_status="approved",
            ),
            [
                _section(
                    textbook_id="textbook-empty-section-ids",
                    section_content_id="section-empty-section-ids",
                    section_id="1.1",
                    title="矩阵乘法",
                    content_zh="矩阵乘法正文",
                )
            ],
        )
        publish_textbook(session, "textbook-empty-section-ids")

        with pytest.raises(ValueError, match="证据包为空。"):
            get_textbook_evidence_pack(session, "textbook-empty-section-ids", [])

        gap = session.exec(
            select(KnowledgeGap).where(
                KnowledgeGap.normalized_topic == "textbook-empty-section-ids"
            )
        ).first()
        assert gap is not None


def test_evidence_pack_uses_actual_content_length_for_limit(
    tmp_path: Path,
) -> None:
    engine = _knowledge_engine(tmp_path)
    run_schema_upgrades(engine)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        create_knowledge_source(session, _admitted_source())
        upsert_structured_textbook(
            session,
            _textbook(
                textbook_id="textbook-stale-count",
                title="低计数教材",
                outline={"sections": [{"section_id": "1.1", "title": "矩阵乘法"}]},
                outline_review_status="approved",
            ),
            [
                _section(
                    textbook_id="textbook-stale-count",
                    section_content_id="section-stale-count",
                    section_id="1.1",
                    title="矩阵乘法",
                    content_zh="矩阵乘法正文",
                )
            ],
        )
        publish_textbook(session, "textbook-stale-count")
        stored_section = session.get(TextbookSectionContent, "section-stale-count")
        assert stored_section is not None
        stored_section.content_zh = "字" * 8001
        stored_section.content_char_count = 1
        session.add(stored_section)
        session.commit()

        with pytest.raises(ValueError, match="证据包超过 8000 个中文字符。"):
            get_textbook_evidence_pack(session, "textbook-stale-count", ["1.1"])


def test_gap_follow_and_resolved_notices_are_idempotent(tmp_path: Path) -> None:
    engine = _knowledge_engine(tmp_path)
    run_schema_upgrades(engine)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        gap = create_or_update_knowledge_gap(
            session,
            "线性代数",
            student_goal_summary="准备学习矩阵",
        )
        same_gap = create_or_update_knowledge_gap(
            session,
            "线性代数",
            student_goal_summary="准备学习矩阵",
        )
        create_or_update_knowledge_gap(
            session,
            "线性代数",
            student_goal_summary="需要补齐向量空间",
        )

        assert same_gap.gap_id == gap.gap_id
        stored_gap = session.get(KnowledgeGap, gap.gap_id)
        assert stored_gap is not None
        assert stored_gap.trigger_count == 3
        assert stored_gap.student_goal_summaries == [
            "准备学习矩阵",
            "需要补齐向量空间",
        ]

        first_follow = follow_knowledge_gap(session, gap.gap_id, "user-1")
        repeated_follow = follow_knowledge_gap(session, gap.gap_id, "user-1")
        follow_knowledge_gap(session, gap.gap_id, "user-2")

        assert repeated_follow.follow_id == first_follow.follow_id
        session.refresh(stored_gap)
        assert stored_gap.follow_count == 2

        create_knowledge_source(session, _admitted_source())
        upsert_structured_textbook(
            session,
            _textbook(
                textbook_id="textbook-resolved-gap",
                title="线性代数",
                description="覆盖矩阵与向量空间",
                tags=["线性代数"],
                outline={"sections": [{"section_id": "1.1", "title": "矩阵"}]},
                outline_review_status="approved",
            ),
            [
                _section(
                    textbook_id="textbook-resolved-gap",
                    section_content_id="section-resolved-gap",
                    section_id="1.1",
                    title="矩阵",
                    content_zh="线性代数正文",
                )
            ],
        )

        publish_textbook(session, "textbook-resolved-gap")
        create_gap_resolved_notices_for_textbook(session, "textbook-resolved-gap")

        session.refresh(stored_gap)
        assert stored_gap.status == "resolved"
        assert stored_gap.resolved_textbook_id == "textbook-resolved-gap"
        assert stored_gap.resolved_at is not None

        notices = session.exec(select(KnowledgeGapNotice)).all()
        assert len(notices) == 2
        assert {notice.user_uid for notice in notices} == {"user-1", "user-2"}
        for notice in notices:
            assert notice.notice_type == "knowledge_gap_resolved"
            assert notice.read_at is None
            assert notice.action_payload == {
                "action": "regenerate_learning_path_intake",
                "learning_topic": "线性代数",
                "textbook_id": "textbook-resolved-gap",
            }


def test_gap_follow_and_notice_duplicates_are_rejected(tmp_path: Path) -> None:
    engine = _knowledge_engine(tmp_path)
    run_schema_upgrades(engine)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        gap = create_or_update_knowledge_gap(session, "线性代数")
        session.add(
            KnowledgeGapFollow(
                follow_id="gap-follow-unique-1",
                gap_id=gap.gap_id,
                user_uid="user-unique",
            )
        )
        session.commit()

        session.add(
            KnowledgeGapFollow(
                follow_id="gap-follow-unique-2",
                gap_id=gap.gap_id,
                user_uid="user-unique",
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

        session.add(
            KnowledgeGapNotice(
                notice_id="gap-notice-unique-1",
                gap_id=gap.gap_id,
                user_uid="user-unique",
                notice_type="knowledge_gap_resolved",
                title="线性代数已补齐",
                action_payload={
                    "action": "regenerate_learning_path_intake",
                    "learning_topic": "线性代数",
                    "textbook_id": "textbook-unique",
                },
            )
        )
        session.commit()

        session.add(
            KnowledgeGapNotice(
                notice_id="gap-notice-unique-2",
                gap_id=gap.gap_id,
                user_uid="user-unique",
                notice_type="knowledge_gap_resolved",
                title="线性代数已补齐",
                action_payload={
                    "action": "regenerate_learning_path_intake",
                    "learning_topic": "线性代数",
                    "textbook_id": "textbook-unique",
                },
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()


def test_add_textbook_extension_resource_rejects_missing_section(
    tmp_path: Path,
) -> None:
    engine = _knowledge_engine(tmp_path)
    run_schema_upgrades(engine)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        session.add(
            _section(
                textbook_id="textbook-extension-bound",
                section_content_id="section-extension-bound",
                section_id="1.1",
                title="矩阵乘法",
                content_zh="矩阵乘法正文",
            )
        )
        session.commit()

        with pytest.raises(ValueError, match="教材小节不存在。"):
            add_textbook_extension_resource(
                session,
                _extension_resource(
                    resource_id="resource-missing-section",
                    textbook_id="textbook-extension-bound",
                    section_id="9.9",
                    title_zh="未绑定资料",
                    status="published",
                ),
            )

        assert (
            session.get(TextbookExtensionResource, "resource-missing-section") is None
        )


def test_extension_resources_are_limited_to_three_visible_rows_per_section(
    tmp_path: Path,
) -> None:
    engine = _knowledge_engine(tmp_path)
    run_schema_upgrades(engine)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        session.add(
            _section(
                textbook_id="textbook-extension",
                section_content_id="section-extension-1",
                section_id="1.1",
                title="第一节",
                content_zh="第一节正文",
            )
        )
        session.add(
            _section(
                textbook_id="textbook-extension",
                section_content_id="section-extension-2",
                section_id="1.2",
                title="第二节",
                content_zh="第二节正文",
            )
        )
        session.add(
            _section(
                textbook_id="textbook-other",
                section_content_id="section-extension-other",
                section_id="1.1",
                title="其他教材第一节",
                content_zh="其他教材正文",
            )
        )
        session.commit()

        for index in range(1, 5):
            add_textbook_extension_resource(
                session,
                _extension_resource(
                    resource_id=f"resource-visible-{index}",
                    textbook_id="textbook-extension",
                    section_id="1.1",
                    title_zh=f"扩展资料 {index}",
                    status="published",
                ),
            )
        add_textbook_extension_resource(
            session,
            _extension_resource(
                resource_id="resource-hidden",
                textbook_id="textbook-extension",
                section_id="1.1",
                title_zh="隐藏资料",
                status="draft",
            ),
        )
        add_textbook_extension_resource(
            session,
            _extension_resource(
                resource_id="resource-other-textbook",
                textbook_id="textbook-other",
                section_id="1.1",
                title_zh="其他教材资料",
                status="published",
            ),
        )
        add_textbook_extension_resource(
            session,
            _extension_resource(
                resource_id="resource-section-two",
                textbook_id="textbook-extension",
                section_id="1.2",
                title_zh="第二节资料",
                status="published",
            ),
        )

        resources_by_section = list_extension_resources_for_sections(
            session,
            "textbook-extension",
            ["1.1", "1.2", "1.3"],
        )

        assert {
            section_id: [resource.resource_id for resource in resources]
            for section_id, resources in resources_by_section.items()
        } == {
            "1.1": [
                "resource-visible-1",
                "resource-visible-2",
                "resource-visible-3",
            ],
            "1.2": ["resource-section-two"],
            "1.3": [],
        }


def _knowledge_source(
    *,
    source_id: str,
    name: str,
    status: str = "enabled",
    download_status: str = "unverified",
    parse_status: str = "unverified",
    license_review_status: str = "unreviewed",
    human_review_status: str = "unreviewed",
) -> KnowledgeSource:
    return KnowledgeSource(
        source_id=source_id,
        name=name,
        status=status,
        download_status=download_status,
        parse_status=parse_status,
        license_review_status=license_review_status,
        human_review_status=human_review_status,
    )
