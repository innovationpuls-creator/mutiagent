import { describe, expect, test } from "vitest";
import {
	archivedKnowledgeTextbook,
	continuousKnowledgeSections,
	enabledKnowledgeSource,
	extensionResourcesFour,
	extensionResourcesThree,
	followedKnowledgeGap,
	knowledgeGapProfileSessionCache,
	overLimitKnowledgeSections,
	profileWithKnowledgeGap,
	publishedKnowledgeTextbook,
	resolvedKnowledgeGapNotice,
	uncoveredKnowledgeGap,
	unpublishedKnowledgeTextbook,
} from "./knowledgeBase";

describe("knowledge base fixtures", () => {
	test("cover source, textbook, gap, notice, extension resource, and content length contracts", () => {
		expect(enabledKnowledgeSource.status).toBe("enabled");
		expect(publishedKnowledgeTextbook.student_availability_status).toBe(
			"published",
		);
		expect(unpublishedKnowledgeTextbook.student_availability_status).toBe(
			"draft",
		);
		expect(archivedKnowledgeTextbook.student_availability_status).toBe(
			"archived",
		);
		expect(uncoveredKnowledgeGap.status).toBe("open");
		expect(followedKnowledgeGap.gap_id).toBe(uncoveredKnowledgeGap.gap_id);
		expect(resolvedKnowledgeGapNotice.action_payload.action).toBe(
			"regenerate_learning_path_intake",
		);
		expect(extensionResourcesThree).toHaveLength(3);
		expect(extensionResourcesFour).toHaveLength(4);

		const continuousIndexes = continuousKnowledgeSections.map(
			(section) => section.order_index,
		);
		expect(continuousIndexes).toEqual([1, 2]);
		expect(
			overLimitKnowledgeSections.reduce(
				(total, section) => total + section.content_char_count,
				0,
			),
		).toBeGreaterThan(8000);
		expect(profileWithKnowledgeGap.gap_id).toBe(uncoveredKnowledgeGap.gap_id);
		expect(
			knowledgeGapProfileSessionCache.messages[1].sessionMessage?.gap_id,
		).toBe(uncoveredKnowledgeGap.gap_id);
	});
});
