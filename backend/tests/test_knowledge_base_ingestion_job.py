from __future__ import annotations

from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from sqlmodel import Session, SQLModel, create_engine, select

from app.models import Textbook, TextbookSectionContent
from app.services.knowledge_base_service import (
    complete_knowledge_base_ingestion_job,
    create_knowledge_base_ingestion_job,
    fail_knowledge_base_ingestion_job,
    run_textbook_source_ingestion,
    start_knowledge_base_ingestion_job,
    translate_section_content_to_zh,
)
from tests.fixtures.knowledge_base import enabled_source, textbook
from tests.postgres import postgresql_test_url


def _engine(tmp_path: Path):
    return create_engine(
        postgresql_test_url(tmp_path, "knowledge-base-ingestion-job"),
    )


def _seed_textbook(session: Session) -> None:
    session.add(enabled_source())
    session.add(textbook(textbook_id="textbook-job", title="整理任务教材"))
    session.commit()


def _write_docx_fixture(path: Path) -> None:
    def paragraph(text: str, style: str | None = None) -> str:
        style_xml = ""
        if style is not None:
            style_xml = f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>'
        return f"<w:p>{style_xml}<w:r><w:t>{text}</w:t></w:r></w:p>"

    document_body = "".join(
        [
            paragraph("第 1 章 栈与队列", "Heading1"),
            paragraph("1.1 栈的抽象数据类型", "Heading2"),
            paragraph("栈是一种后进先出的线性表，本段来自上传 DOCX 文件。"),
            paragraph("1.2 队列的基本操作", "Heading2"),
            paragraph("队列是一种先进先出的线性表，本段来自上传 DOCX 文件。"),
        ]
    )
    files = {
        "[Content_Types].xml": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/'
            'content-types"><Default Extension="rels" ContentType="'
            'application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/word/document.xml" ContentType="'
            "application/vnd.openxmlformats-officedocument."
            'wordprocessingml.document.main+xml"/>'
            '<Override PartName="/word/styles.xml" ContentType="'
            "application/vnd.openxmlformats-officedocument."
            'wordprocessingml.styles+xml"/></Types>'
        ),
        "_rels/.rels": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/'
            '2006/relationships"><Relationship Id="rId1" Type="'
            "http://schemas.openxmlformats.org/officeDocument/2006/"
            'relationships/officeDocument" Target="word/document.xml"/>'
            "</Relationships>"
        ),
        "word/styles.xml": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<w:styles xmlns:w="http://schemas.openxmlformats.org/'
            'wordprocessingml/2006/main">'
            '<w:style w:type="paragraph" w:styleId="Heading1">'
            '<w:name w:val="heading 1"/></w:style>'
            '<w:style w:type="paragraph" w:styleId="Heading2">'
            '<w:name w:val="heading 2"/></w:style></w:styles>'
        ),
        "word/document.xml": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<w:document xmlns:w="http://schemas.openxmlformats.org/'
            f'wordprocessingml/2006/main"><w:body>{document_body}'
            "<w:sectPr/></w:body></w:document>"
        ),
    }
    with ZipFile(path, "w", ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)


def test_create_ingestion_job_records_queued_job_without_starting_textbook(
    tmp_path: Path,
) -> None:
    engine = _engine(tmp_path)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        _seed_textbook(session)

        job = create_knowledge_base_ingestion_job(session, "textbook-job")

        stored_textbook = session.get(Textbook, "textbook-job")

    assert job.textbook_id == "textbook-job"
    assert job.job_type == "agent_organize"
    assert job.status == "queued"
    assert job.started_at is None
    assert job.finished_at is None
    assert stored_textbook is not None
    assert stored_textbook.ingestion_status == "not_started"


def test_ingestion_job_running_then_completed_sets_textbook_ready_for_review(
    tmp_path: Path,
) -> None:
    engine = _engine(tmp_path)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        _seed_textbook(session)
        job = create_knowledge_base_ingestion_job(session, "textbook-job")

        running = start_knowledge_base_ingestion_job(session, job.job_id)
        assert running.status == "running"
        assert running.started_at is not None
        assert running.finished_at is None

        completed = complete_knowledge_base_ingestion_job(session, job.job_id)
        stored_textbook = session.get(Textbook, "textbook-job")

    assert completed.status == "completed"
    assert completed.finished_at is not None
    assert completed.error_message == ""
    assert stored_textbook is not None
    assert stored_textbook.ingestion_status == "ready_for_outline_review"
    assert stored_textbook.ingestion_error_message == ""


def test_ingestion_job_running_then_failed_records_error_on_textbook(
    tmp_path: Path,
) -> None:
    engine = _engine(tmp_path)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        _seed_textbook(session)
        job = create_knowledge_base_ingestion_job(session, "textbook-job")
        start_knowledge_base_ingestion_job(session, job.job_id)

        failed = fail_knowledge_base_ingestion_job(
            session,
            job.job_id,
            "教材解析失败。",
        )
        stored_textbook = session.get(Textbook, "textbook-job")

    assert failed.status == "failed"
    assert failed.finished_at is not None
    assert failed.error_message == "教材解析失败。"
    assert stored_textbook is not None
    assert stored_textbook.ingestion_status == "failed"
    assert stored_textbook.ingestion_error_message == "教材解析失败。"


def test_ingestion_job_rejects_invalid_transitions(tmp_path: Path) -> None:
    engine = _engine(tmp_path)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        _seed_textbook(session)
        job = create_knowledge_base_ingestion_job(session, "textbook-job")

        with pytest.raises(ValueError, match="只有 running 整理任务可以完成。"):
            complete_knowledge_base_ingestion_job(session, job.job_id)

        start_knowledge_base_ingestion_job(session, job.job_id)

        with pytest.raises(ValueError, match="只有 queued 整理任务可以开始。"):
            start_knowledge_base_ingestion_job(session, job.job_id)


def test_run_textbook_source_ingestion_fills_outline_and_sections(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = _engine(tmp_path)
    SQLModel.metadata.create_all(engine)

    def fake_parse_source(
        source_url: str, language: str
    ) -> tuple[dict, dict[str, str]]:
        assert source_url == "https://opendatastructures.org/ods-python.pdf"
        assert language == "en"
        return (
            {
                "chapters": [
                    {
                        "chapter_number": 1,
                        "title": "Chapter 1",
                        "sections": [
                            {"section_id": "sec_1_1", "title": "Arrays"},
                            {"section_id": "sec_1_2", "title": "Linked Lists"},
                        ],
                    }
                ]
            },
            {
                "sec_1_1": "Arrays original content.",
                "sec_1_2": "Linked lists original content.",
            },
        )

    monkeypatch.setattr(
        "app.services.knowledge_base_service.parse_textbook_source_to_sections",
        fake_parse_source,
    )
    monkeypatch.setattr(
        "app.services.knowledge_base_service.translate_section_content_to_zh",
        lambda content, source_language="": (
            "数组是原教材中的一种简单数据结构。" if source_language == "en" else content
        ),
    )

    with Session(engine) as session:
        session.add(enabled_source())
        session.add(
            Textbook(
                textbook_id="textbook-source-job",
                source_id="source-admitted",
                title="Open Data Structures",
                original_title="Open Data Structures",
                language="en",
                translated_language="zh",
                description="",
                tags=[],
                download_url="https://opendatastructures.org/ods-python.pdf",
                file_asset_url="https://opendatastructures.org/ods-python.pdf",
                outline={},
                ingestion_status="not_started",
                outline_review_status="unreviewed",
                student_availability_status="draft",
            )
        )
        session.commit()
        job = create_knowledge_base_ingestion_job(session, "textbook-source-job")

        completed = run_textbook_source_ingestion(session, job.job_id)
        stored = session.get(Textbook, "textbook-source-job")

    assert completed.status == "completed"
    assert stored is not None
    assert stored.ingestion_status == "ready_for_outline_review"
    assert stored.outline["chapters"][0]["sections"][0]["section_id"] == "sec_1_1"


def test_translate_section_content_to_zh_translates_english_section(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeResponse:
        content = "数组是一种用于按索引存储元素的数据结构。"

    class FakeLlm:
        def invoke(self, prompt: str) -> FakeResponse:
            assert "Arrays store elements by index." in prompt
            return FakeResponse()

    monkeypatch.setattr(
        "app.services.knowledge_base_service.get_translation_llm",
        lambda: FakeLlm(),
    )

    translated = translate_section_content_to_zh(
        "Arrays store elements by index.",
        "en",
    )

    assert translated == "数组是一种用于按索引存储元素的数据结构。"


def test_translate_section_content_to_zh_returns_original_when_translation_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FailingLlm:
        def invoke(self, _prompt: str) -> None:
            raise TimeoutError("translation timed out")

    monkeypatch.setattr(
        "app.services.knowledge_base_service.get_translation_llm",
        lambda: FailingLlm(),
    )

    content = "Arrays store elements by index."

    assert translate_section_content_to_zh(content, "en") == content


def test_translate_section_content_to_zh_splits_long_english_section(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.services.knowledge_base_service as service_module

    prompts: list[str] = []

    class FakeResponse:
        def __init__(self, content: str) -> None:
            self.content = content

    class FakeLlm:
        def invoke(self, prompt: str) -> FakeResponse:
            prompts.append(prompt)
            if "Arrays store values." in prompt:
                return FakeResponse("数组存储值。")
            return FakeResponse("链表连接节点。")

    monkeypatch.setattr(service_module, "_TRANSLATION_CHUNK_CHAR_LIMIT", 40)
    monkeypatch.setattr(
        "app.services.knowledge_base_service.get_translation_llm",
        lambda: FakeLlm(),
    )

    translated = translate_section_content_to_zh(
        "Arrays store values.\n\nLinked lists connect nodes.",
        "en",
    )

    assert translated == "数组存储值。\n\n链表连接节点。"
    assert len(prompts) == 2


def test_translate_section_content_to_zh_retries_timed_out_chunk(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts = 0

    class FakeResponse:
        content = "数组存储值。"

    class FlakyLlm:
        def invoke(self, _prompt: str) -> FakeResponse:
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise TimeoutError("translation timed out")
            return FakeResponse()

    monkeypatch.setattr(
        "app.services.knowledge_base_service.get_translation_llm",
        lambda: FlakyLlm(),
    )

    translated = translate_section_content_to_zh("Arrays store values.", "en")

    assert translated == "数组存储值。"
    assert attempts == 2


def test_translate_section_content_to_zh_keeps_chinese_section() -> None:
    content = "栈是一种后进先出的线性表。"

    assert translate_section_content_to_zh(content, "zh") == content


def test_run_textbook_source_ingestion_extracts_uploaded_docx_content(
    tmp_path: Path,
) -> None:
    engine = _engine(tmp_path)
    SQLModel.metadata.create_all(engine)
    docx_path = tmp_path / "uploaded-textbook.docx"
    _write_docx_fixture(docx_path)

    with Session(engine) as session:
        session.add(enabled_source())
        session.add(
            Textbook(
                textbook_id="textbook-upload-docx",
                source_id="source-admitted",
                title="上传 DOCX 教材",
                original_title="上传 DOCX 教材",
                language="zh",
                translated_language="zh",
                description="",
                tags=[],
                download_url=str(docx_path),
                file_asset_url=str(docx_path),
                outline={},
                ingestion_status="not_started",
                outline_review_status="unreviewed",
                student_availability_status="draft",
            )
        )
        session.commit()
        job = create_knowledge_base_ingestion_job(session, "textbook-upload-docx")

        completed = run_textbook_source_ingestion(session, job.job_id)
        stored_textbook = session.get(Textbook, "textbook-upload-docx")
        stored_sections = session.exec(
            select(TextbookSectionContent).where(
                TextbookSectionContent.textbook_id == "textbook-upload-docx"
            )
        ).all()

    assert completed.status == "completed"
    assert stored_textbook is not None
    assert stored_textbook.ingestion_status == "ready_for_outline_review"
    assert stored_sections[0].title == "1.1 栈的抽象数据类型"
    assert (
        "栈是一种后进先出的线性表，本段来自上传 DOCX 文件。"
        in stored_sections[0].content_zh
    )


def test_run_textbook_source_ingestion_preserves_original_section_content(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = _engine(tmp_path)
    SQLModel.metadata.create_all(engine)

    def fake_parse_source(
        source_url: str, language: str
    ) -> tuple[dict, dict[str, str]]:
        assert source_url == "https://opendatastructures.org/ods-python.pdf"
        assert language == "en"
        return (
            {
                "chapters": [
                    {
                        "chapter_number": 1,
                        "title": "Chapter 1",
                        "sections": [{"section_id": "sec_1_1", "title": "Arrays"}],
                    }
                ]
            },
            {
                "sec_1_1": (
                    "Arrays are a simple data structure from the original textbook."
                )
            },
        )

    monkeypatch.setattr(
        "app.services.knowledge_base_service.parse_textbook_source_to_sections",
        fake_parse_source,
    )
    monkeypatch.setattr(
        "app.services.knowledge_base_service.translate_section_content_to_zh",
        lambda content, source_language="": (
            "数组是原教材中的一种简单数据结构。" if source_language == "en" else content
        ),
    )
    with Session(engine) as session:
        session.add(enabled_source())
        session.add(
            Textbook(
                textbook_id="textbook-original-content",
                source_id="source-admitted",
                title="Open Data Structures",
                original_title="Open Data Structures",
                language="en",
                translated_language="zh",
                description="",
                tags=[],
                download_url="https://opendatastructures.org/ods-python.pdf",
                file_asset_url="https://opendatastructures.org/ods-python.pdf",
                outline={},
                ingestion_status="not_started",
                outline_review_status="unreviewed",
                student_availability_status="draft",
            )
        )
        session.commit()
        job = create_knowledge_base_ingestion_job(session, "textbook-original-content")

        completed = run_textbook_source_ingestion(session, job.job_id)
        stored_section = session.exec(
            select(TextbookSectionContent).where(
                TextbookSectionContent.textbook_id == "textbook-original-content"
            )
        ).one()

    assert completed.status == "completed"
    assert (
        stored_section.content_original
        == "Arrays are a simple data structure from the original textbook."
    )
    assert (
        stored_section.content_zh
        == "Arrays are a simple data structure from the original textbook."
    )


def test_run_textbook_source_ingestion_keeps_english_sections_without_translation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = _engine(tmp_path)
    SQLModel.metadata.create_all(engine)

    def fake_parse_source(
        source_url: str, language: str
    ) -> tuple[dict, dict[str, str]]:
        assert source_url == "https://artint.info/3e/html/ArtInt3e.html"
        assert language == "en"
        return (
            {
                "chapters": [
                    {
                        "chapter_number": 1,
                        "title": "Chapter 1",
                        "sections": [
                            {"section_id": "sec_1_1", "title": "Agents"},
                            {"section_id": "sec_1_2", "title": "Environments"},
                        ],
                    }
                ]
            },
            {
                "sec_1_1": "Agents act in environments.",
                "sec_1_2": "Environments provide observations.",
            },
        )

    monkeypatch.setattr(
        "app.services.knowledge_base_service.parse_textbook_source_to_sections",
        fake_parse_source,
    )

    with Session(engine) as session:
        session.add(enabled_source())
        session.add(
            Textbook(
                textbook_id="textbook-concurrent-translation",
                source_id="source-admitted",
                title="Artificial Intelligence",
                original_title="Artificial Intelligence",
                language="en",
                translated_language="zh",
                description="",
                tags=[],
                download_url="https://artint.info/3e/html/ArtInt3e.html",
                file_asset_url="https://artint.info/3e/html/ArtInt3e.html",
                outline={},
                ingestion_status="not_started",
                outline_review_status="unreviewed",
                student_availability_status="draft",
            )
        )
        session.commit()
        job = create_knowledge_base_ingestion_job(
            session,
            "textbook-concurrent-translation",
        )

        completed = run_textbook_source_ingestion(session, job.job_id)
        stored_sections = session.exec(
            select(TextbookSectionContent).where(
                TextbookSectionContent.textbook_id == "textbook-concurrent-translation"
            )
        ).all()

    assert completed.status == "completed"
    assert {section.content_original for section in stored_sections} == {
        "Agents act in environments.",
        "Environments provide observations.",
    }
    assert {section.content_zh for section in stored_sections} == {
        "Agents act in environments.",
        "Environments provide observations.",
    }


def test_run_textbook_source_ingestion_allows_english_textbook_content(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = _engine(tmp_path)
    SQLModel.metadata.create_all(engine)

    def fake_parse_source(
        source_url: str, language: str
    ) -> tuple[dict, dict[str, str]]:
        assert source_url == "https://opendatastructures.org/ods-python.pdf"
        assert language == "en"
        return (
            {
                "chapters": [
                    {
                        "chapter_number": 1,
                        "title": "Chapter 1",
                        "sections": [{"section_id": "sec_1_1", "title": "Arrays"}],
                    }
                ]
            },
            {"sec_1_1": "Arrays store elements by index."},
        )

    monkeypatch.setattr(
        "app.services.knowledge_base_service.parse_textbook_source_to_sections",
        fake_parse_source,
    )

    with Session(engine) as session:
        session.add(enabled_source())
        session.add(
            Textbook(
                textbook_id="textbook-english-no-translation",
                source_id="source-admitted",
                title="Open Data Structures",
                original_title="Open Data Structures",
                language="en",
                translated_language="zh",
                description="",
                tags=[],
                download_url="https://opendatastructures.org/ods-python.pdf",
                file_asset_url="https://opendatastructures.org/ods-python.pdf",
                outline={},
                ingestion_status="not_started",
                outline_review_status="unreviewed",
                student_availability_status="draft",
            )
        )
        session.commit()
        job = create_knowledge_base_ingestion_job(
            session,
            "textbook-english-no-translation",
        )

        completed = run_textbook_source_ingestion(session, job.job_id)
        stored_textbook = session.get(Textbook, "textbook-english-no-translation")
        stored_sections = session.exec(
            select(TextbookSectionContent).where(
                TextbookSectionContent.textbook_id == "textbook-english-no-translation"
            )
        ).all()

    assert completed.status == "completed"
    assert stored_textbook is not None
    assert stored_textbook.ingestion_status == "ready_for_outline_review"
    assert len(stored_sections) == 1
    assert stored_sections[0].content_original == "Arrays store elements by index."
    assert stored_sections[0].content_zh == "Arrays store elements by index."


def test_run_textbook_source_ingestion_fails_when_section_content_is_incomplete(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = _engine(tmp_path)
    SQLModel.metadata.create_all(engine)

    def fake_parse_source(
        source_url: str, language: str
    ) -> tuple[dict, dict[str, str]]:
        assert source_url == "https://opendatastructures.org/ods-python.pdf"
        assert language == "en"
        return (
            {
                "chapters": [
                    {
                        "chapter_number": 1,
                        "title": "Chapter 1",
                        "sections": [
                            {"section_id": "sec_1_1", "title": "Arrays"},
                            {"section_id": "sec_1_2", "title": "Linked Lists"},
                        ],
                    }
                ]
            },
            {"sec_1_1": "Arrays original content."},
        )

    monkeypatch.setattr(
        "app.services.knowledge_base_service.parse_textbook_source_to_sections",
        fake_parse_source,
    )

    with Session(engine) as session:
        session.add(enabled_source())
        session.add(
            Textbook(
                textbook_id="textbook-source-job",
                source_id="source-admitted",
                title="Open Data Structures",
                original_title="Open Data Structures",
                language="en",
                translated_language="zh",
                description="",
                tags=[],
                download_url="https://opendatastructures.org/ods-python.pdf",
                file_asset_url="https://opendatastructures.org/ods-python.pdf",
                outline={},
                ingestion_status="not_started",
                outline_review_status="unreviewed",
                student_availability_status="draft",
            )
        )
        session.commit()
        job = create_knowledge_base_ingestion_job(session, "textbook-source-job")

        failed = run_textbook_source_ingestion(session, job.job_id)
        stored = session.get(Textbook, "textbook-source-job")

    assert failed.status == "failed"
    assert failed.error_message == "教材解析失败：未切分出完整小节正文。"
    assert stored is not None
    assert stored.ingestion_status == "failed"
