from app.services.document_parser_service import (
    get_fallback_markdown_for_pdf,
    locate_and_slice_sections,
    parse_and_slice_pdf,
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


def test_get_fallback_markdown_for_pdf():
    md = get_fallback_markdown_for_pdf("dummy.pdf")
    assert "# dummy" in md
    assert "第一章 绪论" in md
    assert "1.1 什么是数据结构" in md
    assert "2.2 顺序表与链表" in md


def test_parse_pdf_to_markdown_fallback():
    # Calling parse_pdf_to_markdown without env vars should trigger fallback
    md = parse_pdf_to_markdown("dummy.pdf")
    assert "# dummy" in md
    assert "1.1 什么是数据结构" in md


def test_parse_and_slice_pdf():
    # Tests the complete pipeline using fallback
    markdown_text, outline, sections = parse_and_slice_pdf("dummy.pdf")
    assert len(markdown_text) > 0
    assert "chapters" in outline
    assert len(sections) > 0
    assert "sec_1_1" in sections
    assert "数据结构是" in sections["sec_1_1"]
