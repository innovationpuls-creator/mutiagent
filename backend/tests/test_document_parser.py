import pytest

from app.services.document_parser_service import (
    DocumentParseError,
    _numbered_markdown_links,
    _TimeoutRequestsSession,
    extract_outline_by_heading_rules,
    get_fallback_markdown_for_pdf,
    locate_and_slice_sections,
    parse_and_slice_pdf,
    parse_html_to_markdown,
    parse_pdf_to_markdown,
)


def test_locate_and_slice_sections():
    md_text = (
        "# 第一章 绪论\n"
        "1.1 什么是数据结构\n"
        "数据结构是计算机存储、组织数据的方式。\n"
        "1.2 算法分析\n"
        "算法分析指的是..."
    )
    outline = {
        "chapters": [
            {
                "chapter_number": 1,
                "title": "第一章 绪论",
                "sections": [
                    {"section_id": "sec_1_1", "title": "1.1 什么是数据结构"},
                    {"section_id": "sec_1_2", "title": "1.2 算法分析"},
                ],
            }
        ]
    }
    sections = locate_and_slice_sections(md_text, outline)
    assert len(sections) == 2
    assert "数据结构是" in sections["sec_1_1"]
    assert "算法分析指" in sections["sec_1_2"]


def test_locate_and_slice_sections_missing_and_ordering():
    # If a section title is missing in the markdown, it should skip it.
    # The others should still slice correctly.
    md_text = (
        "# 第一章 绪论\n1.1 什么是数据结构\n数据结构是...\n1.3 课程总结\n这是总结。"
    )
    outline = {
        "chapters": [
            {
                "chapter_number": 1,
                "title": "第一章 绪论",
                "sections": [
                    {"section_id": "sec_1_1", "title": "1.1 什么是数据结构"},
                    {"section_id": "sec_1_2", "title": "1.2 算法分析"},
                    {"section_id": "sec_1_3", "title": "1.3 课程总结"},
                ],
            }
        ]
    }
    sections = locate_and_slice_sections(md_text, outline)
    assert len(sections) == 2
    assert "sec_1_1" in sections
    assert "sec_1_2" not in sections
    assert "sec_1_3" in sections
    assert "数据结构是" in sections["sec_1_1"]
    assert "这是总结" in sections["sec_1_3"]


def test_locate_and_slice_sections_handles_repeated_titles_in_order():
    md_text = (
        "# 1 Algorithms\n"
        "# Introduction\n"
        "第一章导言正文。\n"
        "# What Is a Data Structure?\n"
        "数据结构正文。\n"
        "# 2 Recursion\n"
        "# Introduction\n"
        "第二章导言正文。\n"
        "# Base Cases\n"
        "基本情形正文。"
    )
    outline = {
        "chapters": [
            {
                "chapter_number": 1,
                "title": "1 Algorithms",
                "sections": [
                    {"section_id": "sec_1_1", "title": "Introduction"},
                    {"section_id": "sec_1_2", "title": "What Is a Data Structure?"},
                ],
            },
            {
                "chapter_number": 2,
                "title": "2 Recursion",
                "sections": [
                    {"section_id": "sec_2_1", "title": "Introduction"},
                    {"section_id": "sec_2_2", "title": "Base Cases"},
                ],
            },
        ]
    }

    sections = locate_and_slice_sections(md_text, outline)

    assert "第一章导言正文" in sections["sec_1_1"]
    assert "数据结构正文" in sections["sec_1_2"]
    assert "第二章导言正文" in sections["sec_2_1"]
    assert "基本情形正文" in sections["sec_2_2"]


def test_get_fallback_markdown_for_pdf():
    try:
        import pypdf  # noqa: F401
    except ImportError:
        pass
    with pytest.raises(DocumentParseError):
        get_fallback_markdown_for_pdf("dummy.pdf")


def test_parse_pdf_to_markdown_fallback():
    with pytest.raises(DocumentParseError):
        parse_pdf_to_markdown("dummy.pdf")


def test_parse_and_slice_pdf():
    with pytest.raises(DocumentParseError):
        parse_and_slice_pdf("dummy.pdf")


def test_extract_outline_by_heading_rules_uses_real_headings():
    markdown_text = (
        "## 第一章 栈与队列\n"
        "### 1.1 栈的抽象数据类型\n"
        "栈正文。\n"
        "### 1.2 队列的基本操作\n"
        "队列正文。\n"
    )

    outline = extract_outline_by_heading_rules(markdown_text)

    assert outline == {
        "chapters": [
            {
                "chapter_number": 1,
                "title": "第一章 栈与队列",
                "sections": [
                    {"section_id": "sec_1_1", "title": "1.1 栈的抽象数据类型"},
                    {"section_id": "sec_1_2", "title": "1.2 队列的基本操作"},
                ],
            }
        ]
    }


def test_extract_outline_by_heading_rules_handles_pressbooks_style_headings():
    markdown_text = (
        "# Book Title: An Open Guide to Data Structures and Algorithms\n"
        "## Contents\n"
        "1. [Introduction](https://example.test/book/chapter-1/#section-1)\n"
        "# 1 Algorithms, Big-O, and Complexity\n"
        "# Introduction\n"
        "正文。\n"
        "# What Is a Data Structure?\n"
        "正文。\n"
        "# 2 Recursion\n"
        "# Introduction\n"
        "正文。\n"
        "# Base Cases\n"
        "正文。\n"
    )

    outline = extract_outline_by_heading_rules(markdown_text)

    assert outline == {
        "chapters": [
            {
                "chapter_number": 1,
                "title": "1 Algorithms, Big-O, and Complexity",
                "sections": [
                    {"section_id": "sec_1_1", "title": "Introduction"},
                    {"section_id": "sec_1_2", "title": "What Is a Data Structure?"},
                ],
            },
            {
                "chapter_number": 2,
                "title": "2 Recursion",
                "sections": [
                    {"section_id": "sec_2_1", "title": "Introduction"},
                    {"section_id": "sec_2_2", "title": "Base Cases"},
                ],
            },
        ]
    }


def test_parse_html_to_markdown_uses_page_headings_and_body(tmp_path):
    html_path = tmp_path / "book.html"
    html_path.write_text(
        """
        <html>
          <body>
            <nav>导航不应进入正文</nav>
            <h2>第一章 栈与队列</h2>
            <h3>1.1 栈的抽象数据类型</h3>
            <p>栈是一种后进先出的线性结构。</p>
            <h3>1.2 队列的基本操作</h3>
            <p>队列是一种先进先出的线性结构。</p>
          </body>
        </html>
        """,
        encoding="utf-8",
    )

    markdown = parse_html_to_markdown(str(html_path))

    assert "## 第一章 栈与队列" in markdown
    assert "### 1.1 栈的抽象数据类型" in markdown
    assert "栈是一种后进先出的线性结构。" in markdown


def test_numbered_markdown_links_strip_optional_link_title() -> None:
    markdown = (
        "1. [1 Artificial Intelligence and Agents]"
        '(ArtInt3e.Ch1.html "In Artificial Intelligence")'
    )

    links = _numbered_markdown_links(markdown)

    assert links == ["ArtInt3e.Ch1.html"]


def test_markitdown_requests_session_applies_default_timeout(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_request(self, method, url, **kwargs):
        captured["method"] = method
        captured["url"] = url
        captured["timeout"] = kwargs.get("timeout")
        raise RuntimeError("stop before network")

    monkeypatch.setattr("requests.Session.request", fake_request)

    with pytest.raises(RuntimeError, match="stop before network"):
        _TimeoutRequestsSession().get("https://example.test/book.html")

    assert captured == {
        "method": "GET",
        "url": "https://example.test/book.html",
        "timeout": 20.0,
    }
