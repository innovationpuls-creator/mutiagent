import type { LeafCourse, LeafSection } from "../../types/leaf";

type LeafGenerationChapter = Pick<
	LeafSection,
	| "section_id"
	| "title"
	| "source_textbook_id"
	| "source_textbook_title"
	| "source_section_ids"
	| "source_section_titles"
	| "source_content_chars"
>;
type LeafGenerationMode = "generate" | "regenerate";

function joinSourceItems(items: string[]): string {
	return items.join(", ");
}

export function buildLeafGenerationPrompt(
	course: LeafCourse,
	chapter: LeafGenerationChapter,
	mode: LeafGenerationMode = "generate",
): string {
	return [
		`帮我生成《${course.course_or_chapter_theme}》${chapter.title}的教学内容。`,
		"",
		"[LEAF_RESOURCE_GENERATION]",
		`course_node_id: ${course.course_node_id}`,
		`chapter_section_id: ${chapter.section_id}`,
		"scope: chapter_sections",
		`mode: ${mode}`,
		"[/LEAF_RESOURCE_GENERATION]",
		"",
		"绑定教材上下文：",
		`source_textbook_id: ${chapter.source_textbook_id}`,
		`source_textbook_title: ${chapter.source_textbook_title}`,
		`source_section_ids: ${joinSourceItems(chapter.source_section_ids)}`,
		`source_section_titles: ${joinSourceItems(chapter.source_section_titles)}`,
		`source_content_chars: ${chapter.source_content_chars}`,
		"",
		"要求：生成这一章所有叶子小节的 Markdown、视频资源、HTML 动画，并拼装保存。",
		"只能使用当前章节绑定教材小节的中文正文证据包；未覆盖内容进入管理员待办，不临时补写。",
	].join("\n");
}

export function buildCourseOutlineGenerationPrompt(course: LeafCourse): string {
	return `帮我生成《${course.course_or_chapter_theme}》的大纲`;
}
