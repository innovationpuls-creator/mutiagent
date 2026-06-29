import { afterEach, describe, expect, it, vi } from "vitest";
import {
	fetchKnowledgeGapNotices,
	type KnowledgeGapNoticeRead,
} from "./knowledgeBase";

afterEach(() => {
	vi.unstubAllGlobals();
});

describe("fetchKnowledgeGapNotices", () => {
	it("normalizes a single notice object into an array", async () => {
		const notice: KnowledgeGapNoticeRead = {
			notice_id: "notice-1",
			gap_id: "gap-1",
			user_uid: "user-1",
			notice_type: "knowledge_gap_resolved",
			title: "主题已补齐",
			body: "知识库已发布覆盖该主题的教材。",
			action_label: "重新生成学习路径",
			action_payload: {
				action: "regenerate_learning_path_intake",
				learning_topic: "概率论",
				textbook_id: "textbook-1",
			},
			read_at: null,
			created_at: "2026-06-28T10:00:00Z",
		};

		vi.stubGlobal(
			"fetch",
			vi.fn().mockResolvedValue({
				ok: true,
				json: async () => notice,
			}),
		);

		const notices = await fetchKnowledgeGapNotices("token-1");

		expect(Array.isArray(notices)).toBe(true);
		expect(notices).toHaveLength(1);
		expect(notices[0]).toEqual(notice);
	});
});
