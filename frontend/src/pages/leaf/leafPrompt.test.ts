import { describe, expect, it } from "vitest";
import type { LeafCourse, LeafSection } from "../../types/leaf";
import {
	buildCourseOutlineGenerationPrompt,
	buildLeafGenerationPrompt,
} from "./leafPrompt";

describe("buildCourseOutlineGenerationPrompt", () => {
	it("keeps the exact course name in the outline draft prompt", () => {
		const course: LeafCourse = {
			course_node_id: "year_3_course_1",
			grade_id: "year_3",
			course_or_chapter_theme: "构建本地知识库问答系统 (RAG基础)",
			course_goal: "完成本地知识库问答系统",
			status: "current",
			has_outline: false,
		};

		expect(buildCourseOutlineGenerationPrompt(course)).toBe(
			"帮我生成《构建本地知识库问答系统 (RAG基础)》的大纲",
		);
	});
});

describe("buildLeafGenerationPrompt", () => {
	it("includes the bound textbook context for the selected chapter", () => {
		const course: LeafCourse = {
			course_node_id: "year_3_course_1",
			grade_id: "year_3",
			course_or_chapter_theme: "构建本地知识库问答系统 (RAG基础)",
			course_goal: "完成本地知识库问答系统",
			status: "current",
			has_outline: true,
		};
		const chapter: LeafSection = {
			section_id: "1.1",
			parent_section_id: "1",
			depth: 2,
			title: "需求边界",
			order_index: 2,
			description: "确认知识库问答系统的需求边界。",
			key_knowledge_points: ["需求拆解"],
			source_textbook_id: "textbook-rag",
			source_textbook_title: "AI 应用开发项目教程",
			source_section_ids: ["2.1", "2.2"],
			source_section_titles: ["知识库问答边界", "验收标准"],
			source_content_chars: 3200,
		};

		const prompt = buildLeafGenerationPrompt(course, chapter);

		expect(prompt).toContain("source_textbook_id: textbook-rag");
		expect(prompt).toContain("source_textbook_title: AI 应用开发项目教程");
		expect(prompt).toContain("source_section_ids: 2.1, 2.2");
		expect(prompt).toContain("source_section_titles: 知识库问答边界, 验收标准");
		expect(prompt).toContain("source_content_chars: 3200");
		expect(prompt).toContain("只能使用当前章节绑定教材小节的中文正文证据包");
	});
});
