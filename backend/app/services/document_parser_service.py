import logging
import os
import re
from typing import Any, Dict, List, Tuple
from urllib.parse import urljoin, urlparse

import requests
from markitdown import MarkItDown
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

_MARKITDOWN_REQUEST_TIMEOUT_SECONDS = float(
    os.getenv("TEXTBOOK_MARKITDOWN_REQUEST_TIMEOUT_SECONDS", "20")
)


class DocumentParseError(RuntimeError):
    """Raised when a textbook source cannot be parsed into real sections."""


class _TimeoutRequestsSession(requests.Session):
    def request(self, method: str, url: str, **kwargs: Any) -> requests.Response:
        kwargs.setdefault("timeout", _MARKITDOWN_REQUEST_TIMEOUT_SECONDS)
        return super().request(method, url, **kwargs)


class SectionOutline(BaseModel):
    section_id: str = Field(
        ...,
        description="Unique section ID, e.g., sec_1_1, sec_1_2",
    )
    title: str = Field(
        ...,
        description="Title of the section, exactly as it appears in the markdown",
    )


class ChapterOutline(BaseModel):
    chapter_number: int = Field(
        ...,
        description="Chapter number, e.g., 1",
    )
    title: str = Field(
        ...,
        description="Chapter title, exactly as it appears in the markdown",
    )
    sections: List[SectionOutline] = Field(
        ...,
        description="Sections in this chapter",
    )


class TextbookOutline(BaseModel):
    chapters: List[ChapterOutline] = Field(..., description="List of chapters")


def locate_and_slice_sections(
    markdown_text: str, outline: Dict[str, Any]
) -> Dict[str, str]:
    """Finds the start index of each section heading in the markdown text.

    Sorts them by index, and slices the markdown string accordingly.
    Preserves markdown header symbols (e.g. #, ##) by searching for the start
    of the line.
    """
    sections_content = {}
    all_titles = []

    for ch in outline.get("chapters", []):
        for sec in ch.get("sections", []):
            all_titles.append((sec["section_id"], sec["title"]))

    found_positions = []
    line_start_idx = 0
    line_positions: list[tuple[str, int]] = []
    for line in markdown_text.splitlines(keepends=True):
        line_positions.append((line.strip(), line_start_idx))
        line_start_idx += len(line)

    search_start_idx = 0
    for sec_id, title in all_titles:
        found_start_idx = _next_section_heading_position(
            line_positions,
            title,
            search_start_idx,
        )
        if found_start_idx is None:
            continue
        found_positions.append((sec_id, title, found_start_idx))
        search_start_idx = found_start_idx + len(title)

    found_positions.sort(key=lambda x: x[2])

    for i, (sec_id, title, start_idx) in enumerate(found_positions):
        if i + 1 < len(found_positions):
            end_idx = found_positions[i + 1][2]
        else:
            end_idx = len(markdown_text)
        sections_content[sec_id] = markdown_text[start_idx:end_idx].strip()

    return sections_content


def extract_outline_from_markdown(markdown_text: str) -> Dict[str, Any]:
    """Extract a structured outline from headings present in parsed text."""
    if not markdown_text.strip():
        raise DocumentParseError("教材正文为空，无法提取目录。")
    return extract_outline_by_heading_rules(markdown_text)


def extract_outline_by_heading_rules(markdown_text: str) -> Dict[str, Any]:
    """Extract a conservative outline from headings present in parsed text."""
    chapters: list[dict[str, Any]] = []
    current_chapter: dict[str, Any] | None = None
    section_counts: dict[int, int] = {}
    current_chapter_heading_level = 0
    heading_pattern = re.compile(r"^(#{1,4})\s+(.+?)\s*$")
    numbered_chapter_pattern = re.compile(
        r"^(?:第\s*[一二三四五六七八九十百\d]+\s*[章节篇]|Chapter\s+\d+)\b",
        re.IGNORECASE,
    )
    numeric_chapter_pattern = re.compile(r"^\d+\.?\s+.+")
    numbered_section_pattern = re.compile(r"^\d+(?:\.\d+)+\s+.+")

    for raw_line in markdown_text.splitlines():
        line_context = _outline_line_context(
            raw_line,
            heading_pattern,
            numbered_chapter_pattern,
            numeric_chapter_pattern,
            numbered_section_pattern,
        )
        if line_context is None:
            continue
        title, heading_match, heading_level = line_context

        if numbered_section_pattern.match(title):
            if current_chapter is None:
                current_chapter = _new_outline_chapter(1, "正文")
                chapters.append(current_chapter)
                section_counts[1] = 0
                current_chapter_heading_level = 1
            _append_outline_section(current_chapter, section_counts, title)
            continue

        if _line_starts_chapter(
            title,
            heading_match,
            heading_level,
            current_chapter,
            numbered_chapter_pattern,
            numeric_chapter_pattern,
        ):
            chapter_number = len(chapters) + 1
            current_chapter = _new_outline_chapter(chapter_number, title)
            chapters.append(current_chapter)
            section_counts[chapter_number] = 0
            current_chapter_heading_level = heading_level
            continue

        if heading_match is not None and current_chapter is not None:
            if heading_level >= current_chapter_heading_level:
                _append_outline_section(current_chapter, section_counts, title)
            continue

    outline = {"chapters": [chapter for chapter in chapters if chapter["sections"]]}
    if not _outline_has_sections(outline):
        raise DocumentParseError("未能从教材正文中提取可切片目录。")
    return outline


def _outline_line_context(
    raw_line: str,
    heading_pattern: re.Pattern[str],
    chapter_pattern: re.Pattern[str],
    numeric_chapter_pattern: re.Pattern[str],
    section_pattern: re.Pattern[str],
) -> tuple[str, re.Match[str] | None, int] | None:
    line = raw_line.strip()
    if not line or _looks_like_toc_entry(line):
        return None
    heading_match = heading_pattern.match(line)
    title = _outline_title_from_line(
        line,
        heading_match,
        chapter_pattern,
        numeric_chapter_pattern,
        section_pattern,
    )
    if not title or _looks_like_book_metadata_heading(title):
        return None
    heading_level = len(heading_match.group(1)) if heading_match else 0
    return title, heading_match, heading_level


def _next_section_heading_position(
    line_positions: list[tuple[str, int]],
    title: str,
    search_start_idx: int,
) -> int | None:
    normalized_title = _normalize_heading_text(title)
    for line, start_idx in line_positions:
        if start_idx < search_start_idx:
            continue
        if _looks_like_toc_entry(line):
            continue
        if _normalize_heading_text(line) == normalized_title:
            return start_idx
    return None


def _new_outline_chapter(chapter_number: int, title: str) -> dict[str, Any]:
    return {
        "chapter_number": chapter_number,
        "title": title,
        "sections": [],
    }


def _append_outline_section(
    chapter: dict[str, Any],
    section_counts: dict[int, int],
    title: str,
) -> None:
    chapter_number = chapter["chapter_number"]
    section_counts[chapter_number] += 1
    chapter["sections"].append(
        {
            "section_id": f"sec_{chapter_number}_{section_counts[chapter_number]}",
            "title": title,
        }
    )


def _line_starts_chapter(
    title: str,
    heading_match: re.Match[str] | None,
    heading_level: int,
    current_chapter: dict[str, Any] | None,
    chapter_pattern: re.Pattern[str],
    numeric_chapter_pattern: re.Pattern[str],
) -> bool:
    return bool(
        chapter_pattern.match(title)
        or numeric_chapter_pattern.match(title)
        or (
            heading_match is not None and current_chapter is None and heading_level <= 2
        )
    )


def _looks_like_toc_entry(line: str) -> bool:
    normalized = line.strip()
    if not normalized:
        return False
    has_dot_leader = bool(
        ". . ." in normalized
        or re.search(r"\.{4,}", normalized)
        or re.search(r"\s(?:\.\s*){2,}\d+\s*$", normalized)
        or re.search(r"(?:\.\s*){3,}\d+\s*$", normalized)
    )
    return bool(has_dot_leader and re.search(r"\s+\d+\s*$", normalized))


def _looks_like_book_metadata_heading(title: str) -> bool:
    normalized = _normalize_heading_text(title).strip().lower()
    return normalized in {
        "artificial intelligence 3e",
        "authors",
        "book information",
        "contents",
        "license",
        "metadata",
        "subject",
        "table of contents",
    } or normalized.startswith("book title:")


def _normalize_heading_text(line: str) -> str:
    cleaned = re.sub(r"^#{1,6}\s+", "", line.strip())
    cleaned = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", cleaned)
    return re.sub(r"\s+", " ", cleaned)


def _outline_title_from_line(
    line: str,
    heading_match: re.Match[str] | None,
    chapter_pattern: re.Pattern[str],
    numeric_chapter_pattern: re.Pattern[str],
    section_pattern: re.Pattern[str],
) -> str:
    if heading_match:
        return heading_match.group(2).strip()
    if "](" in line:
        return ""
    if section_pattern.match(line):
        return line
    if chapter_pattern.match(line):
        return line
    if numeric_chapter_pattern.match(line):
        return line
    return ""


def convert_textbook_source_to_markdown(source_url_or_path: str) -> str:
    try:
        logger.info(
            "Converting textbook source with MarkItDown: %s",
            source_url_or_path,
        )
        result = MarkItDown(
            enable_plugins=False,
            requests_session=_TimeoutRequestsSession(),
        ).convert(source_url_or_path)
    except Exception as exc:
        raise DocumentParseError(f"MarkItDown 转换失败：{exc}") from exc
    markdown = getattr(result, "text_content", "")
    if not isinstance(markdown, str) or not markdown.strip():
        raise DocumentParseError("MarkItDown 未抽取到可解析正文。")
    return markdown.strip()


def get_fallback_markdown_for_pdf(pdf_path_or_url: str) -> str:
    """Convert PDF to Markdown through MarkItDown."""
    return convert_textbook_source_to_markdown(pdf_path_or_url)


def parse_pdf_to_markdown(pdf_path_or_url: str) -> str:
    """Convert PDF to Markdown through MarkItDown."""
    return convert_textbook_source_to_markdown(pdf_path_or_url)


def parse_and_slice_pdf(
    pdf_path_or_url: str,
) -> Tuple[str, Dict[str, Any], Dict[str, str]]:
    """Orchestrates the ingestion pipeline for a PDF.

    1. Parses PDF to Markdown through MarkItDown.
    2. Extracts structured outline from the Markdown.
    3. Slices the Markdown into sections based on the outline using physical
       positioning.

    Returns:
        (markdown_text, outline, sections_content)
    """
    logger.info("Starting parsing and slicing pipeline for: %s", pdf_path_or_url)

    markdown_text = parse_pdf_to_markdown(pdf_path_or_url)
    outline = extract_outline_from_markdown(markdown_text)
    sections_content = locate_and_slice_sections(markdown_text, outline)
    if not sections_content:
        raise DocumentParseError("未能按目录切分出教材正文。")

    return markdown_text, outline, sections_content


def parse_html_to_markdown(source_url_or_path: str, max_linked_pages: int = 80) -> str:
    markdown = convert_textbook_source_to_markdown(source_url_or_path)
    linked_markdowns = _convert_linked_numbered_pages(
        source_url_or_path,
        markdown,
        seen_urls={source_url_or_path},
        depth=0,
        max_pages=max_linked_pages,
    )
    if linked_markdowns:
        return "\n\n".join(linked_markdowns)
    return markdown


def parse_and_slice_html(
    source_url_or_path: str,
    max_linked_pages: int = 80,
) -> Tuple[str, Dict[str, Any], Dict[str, str]]:
    logger.info(
        "Starting HTML parsing and slicing pipeline for: %s",
        source_url_or_path,
    )
    markdown_text = parse_html_to_markdown(
        source_url_or_path,
        max_linked_pages=max_linked_pages,
    )
    outline = extract_outline_from_markdown(markdown_text)
    sections_content = locate_and_slice_sections(markdown_text, outline)
    if not sections_content:
        raise DocumentParseError("未能按 HTML 目录切分出教材正文。")
    return markdown_text, outline, sections_content


def parse_textbook_source_to_sections(
    source_url: str,
    language: str,
    max_linked_pages: int = 80,
) -> tuple[dict[str, Any], dict[str, str]]:
    if _source_is_pdf(source_url):
        _, outline, sections_content = parse_and_slice_pdf(source_url)
    else:
        _, outline, sections_content = parse_and_slice_html(
            source_url,
            max_linked_pages=max_linked_pages,
        )
    return outline, sections_content


def _ensure_local_pdf(pdf_path_or_url: str) -> str:
    raise DocumentParseError("PDF 本地化由 MarkItDown 处理。")


def _cleanup_temp_pdf(local_path: str, original_path_or_url: str) -> None:
    return None


def _outline_has_sections(outline: dict[str, Any]) -> bool:
    chapters = outline.get("chapters")
    if isinstance(chapters, list):
        return any(
            isinstance(chapter, dict)
            and isinstance(chapter.get("sections"), list)
            and len(chapter["sections"]) > 0
            for chapter in chapters
        )
    sections = outline.get("sections")
    return isinstance(sections, list) and len(sections) > 0


def _source_is_pdf(source_url_or_path: str) -> bool:
    parsed = urlparse(source_url_or_path)
    path = parsed.path or source_url_or_path
    if path.lower().endswith(".pdf"):
        return True
    if os.path.exists(source_url_or_path):
        return False
    if parsed.scheme not in {"http", "https"}:
        return False
    try:
        import httpx

        with httpx.Client(follow_redirects=True, timeout=15.0) as client:
            response = client.head(source_url_or_path)
            if response.status_code in {403, 405}:
                response = client.get(
                    source_url_or_path,
                    headers={"Range": "bytes=0-0"},
                )
            content_type = response.headers.get("content-type", "").lower()
            return "application/pdf" in content_type
    except Exception as exc:
        logger.warning("Failed to detect source content type: %s", exc)
        return False


def _read_html_source(source_url_or_path: str) -> str:
    return convert_textbook_source_to_markdown(source_url_or_path)


def _convert_linked_numbered_pages(
    source_url_or_path: str,
    markdown: str,
    *,
    seen_urls: set[str],
    depth: int,
    max_pages: int,
) -> list[str]:
    if depth >= 2 or len(seen_urls) >= max_pages:
        return []
    parsed_source = urlparse(source_url_or_path)
    if parsed_source.scheme not in {"http", "https"}:
        return []
    links = _numbered_markdown_links(markdown)
    if not links:
        return []
    source_origin = (parsed_source.scheme, parsed_source.netloc)
    converted: list[str] = []
    for href in links[:max_pages]:
        absolute_url = _url_without_fragment(urljoin(source_url_or_path, href))
        parsed_link = urlparse(absolute_url)
        if (parsed_link.scheme, parsed_link.netloc) != source_origin:
            continue
        if absolute_url in seen_urls:
            continue
        seen_urls.add(absolute_url)
        try:
            logger.info(
                "Converting linked textbook page %s (%s/%s)",
                absolute_url,
                len(seen_urls),
                max_pages,
            )
            converted_markdown = convert_textbook_source_to_markdown(absolute_url)
        except DocumentParseError as exc:
            logger.info("Skipping linked textbook page %s: %s", absolute_url, exc)
            continue
        converted.append(converted_markdown)
        converted.extend(
            _convert_linked_numbered_pages(
                absolute_url,
                converted_markdown,
                seen_urls=seen_urls,
                depth=depth + 1,
                max_pages=max_pages,
            )
        )
        if len(seen_urls) >= max_pages:
            break
    return converted[:max_pages]


def _numbered_markdown_links(markdown: str) -> list[str]:
    links: list[str] = []
    for label, href in re.findall(r"\[([^\]]+)\]\(([^)]+)\)", markdown):
        clean_label = _normalize_heading_text(label)
        if re.match(r"^\d+(?:\.\d+)*\.?\s+.+", clean_label):
            clean_href = _clean_markdown_href(href)
            if clean_href:
                links.append(clean_href)
    return links


def _clean_markdown_href(href: str) -> str:
    clean_href = href.strip()
    title_match = re.match(r"^([^\"']+?)\s+[\"'].+[\"']$", clean_href)
    if title_match:
        clean_href = title_match.group(1).strip()
    return clean_href


def _url_without_fragment(url: str) -> str:
    parsed = urlparse(url)
    return parsed._replace(fragment="").geturl()
