import { afterEach, describe, expect, test, vi } from "vitest";
import { fetchLeafCourse } from "./leaf";

afterEach(() => {
	vi.restoreAllMocks();
	vi.unstubAllGlobals();
});

describe("leaf api", () => {
	test("normalizes video items so cover fields are always safe to consume", async () => {
		vi.stubGlobal(
			"fetch",
			vi.fn().mockResolvedValue({
				ok: true,
				json: async () => ({
					access_state: "available",
					course: {
						course_node_id: "year_3_course_1",
						grade_id: "year_3",
						course_or_chapter_theme: "AI Agent 开发",
						course_goal: "完成 AI Agent 开发",
						status: "current",
						has_outline: true,
					},
					outline: {
						course_id: "year_3_course_1",
						course_name: "AI Agent 开发",
					},
					sections: [
						{
							section_id: "1",
							parent_section_id: null,
							depth: 1,
							title: "第一章：需求拆解",
							order_index: 1,
							description: "确认边界",
							key_knowledge_points: ["边界"],
							source_textbook_id: "textbook-rag",
							source_textbook_title: "AI 应用开发项目教程",
							source_section_ids: ["2.1"],
							source_section_titles: ["知识库问答边界"],
							source_content_chars: 2400,
						},
					],
					section_composed_markdowns: {
						"1": {
							section_id: "1",
							parent_section_id: null,
							title: "第一章：需求拆解",
							markdown: "# 第一章",
							generated_at: "2026-06-06T00:00:00Z",
							blocks: [
								{
									type: "video",
									brief_id: "video_1",
									title: "导入视频",
									purpose: "建立直觉",
									status: "available",
									videos: [
										{
											title: "PromptTemplate 实战",
											url: "https://www.youtube.com/watch?v=nQX61qSL-uE",
										},
									],
								},
							],
						},
					},
					generation_status: null,
					can_generate: true,
					first_generatable_chapter_id: "1",
					locked_reason: null,
				}),
			}),
		);

		const result = await fetchLeafCourse("token", "year_3_course_1");
		const video = result.section_composed_markdowns["1"]?.blocks[0];

		expect(video?.type).toBe("video");
		if (video?.type !== "video") {
			throw new Error("expected video block");
		}
		expect(video.videos[0]).toEqual({
			title: "PromptTemplate 实战",
			url: "https://www.youtube.com/watch?v=nQX61qSL-uE",
			cover_url: "",
			cover_status: "",
			source: "",
		});
	});

	test("rejects malformed video items without a string url", async () => {
		vi.stubGlobal(
			"fetch",
			vi.fn().mockResolvedValue({
				ok: true,
				json: async () => ({
					access_state: "available",
					course: {
						course_node_id: "year_3_course_1",
						grade_id: "year_3",
						course_or_chapter_theme: "AI Agent 开发",
						course_goal: "完成 AI Agent 开发",
						status: "current",
						has_outline: true,
					},
					outline: {
						course_id: "year_3_course_1",
						course_name: "AI Agent 开发",
					},
					sections: [
						{
							section_id: "1",
							parent_section_id: null,
							depth: 1,
							title: "第一章：需求拆解",
							order_index: 1,
							description: "确认边界",
							key_knowledge_points: ["边界"],
							source_textbook_id: "textbook-rag",
							source_textbook_title: "AI 应用开发项目教程",
							source_section_ids: ["2.1"],
							source_section_titles: ["知识库问答边界"],
							source_content_chars: 2400,
						},
					],
					section_composed_markdowns: {
						"1": {
							section_id: "1",
							parent_section_id: null,
							title: "第一章：需求拆解",
							markdown: "# 第一章",
							generated_at: "2026-06-06T00:00:00Z",
							blocks: [
								{
									type: "video",
									brief_id: "video_1",
									title: "导入视频",
									purpose: "建立直觉",
									status: "available",
									videos: [
										{
											title: "PromptTemplate 实战",
											url: 123,
										},
									],
								},
							],
						},
					},
					generation_status: null,
					can_generate: true,
					first_generatable_chapter_id: "1",
					locked_reason: null,
				}),
			}),
		);

		await expect(fetchLeafCourse("token", "year_3_course_1")).rejects.toThrow(
			"叶茂内容格式不正确",
		);
	});
});
