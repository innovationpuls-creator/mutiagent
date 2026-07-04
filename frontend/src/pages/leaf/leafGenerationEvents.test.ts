import { afterEach, describe, expect, it, vi } from "vitest";
import {
	dispatchLeafGenerationCompleted,
	dispatchLeafGenerationEvent,
	LEAF_GENERATION_COMPLETED_EVENT,
	LEAF_GENERATION_EVENT,
	type LeafGenerationCompletedEventDetail,
	type LeafGenerationEventDetail,
} from "./leafGenerationEvents";

describe("dispatchLeafGenerationEvent", () => {
	afterEach(() => {
		vi.restoreAllMocks();
	});

	it("dispatches course resource errors using the backend error field as the message", () => {
		const listener =
			vi.fn<(event: CustomEvent<LeafGenerationEventDetail>) => void>();
		window.addEventListener(LEAF_GENERATION_EVENT, listener as EventListener, {
			once: true,
		});

		dispatchLeafGenerationEvent({
			event: "error",
			kind: "course_resource_chapter",
			course_id: "year_3_course_1",
			chapter_section_id: "1",
			phase: "video",
			status: "error",
			error: "视频资源未生成，请稍后重试。",
		});

		expect(listener).toHaveBeenCalledTimes(1);
		expect(listener.mock.calls[0][0].detail).toEqual({
			courseId: "year_3_course_1",
			chapterSectionId: "1",
			sectionId: null,
			phase: "video",
			status: "error",
			message: "视频资源未生成，请稍后重试。",
		});
	});

	it("dispatches completed events with a reason and keeps course resource as the default", () => {
		const listener =
			vi.fn<(event: CustomEvent<LeafGenerationCompletedEventDetail>) => void>();
		window.addEventListener(
			LEAF_GENERATION_COMPLETED_EVENT,
			listener as EventListener,
		);

		dispatchLeafGenerationCompleted("year_3_course_1");
		dispatchLeafGenerationCompleted("year_3_course_1", "course_outline");

		expect(listener).toHaveBeenCalledTimes(2);
		expect(listener.mock.calls[0][0].detail).toEqual({
			courseId: "year_3_course_1",
			reason: "course_resource",
		});
		expect(listener.mock.calls[1][0].detail).toEqual({
			courseId: "year_3_course_1",
			reason: "course_outline",
		});

		window.removeEventListener(
			LEAF_GENERATION_COMPLETED_EVENT,
			listener as EventListener,
		);
	});

	it.each([
		"markdown",
		"video",
		"animation",
		"compose",
	])("dispatches a refresh completion event after successful %s resource result", (phase) => {
		const generationListener =
			vi.fn<(event: CustomEvent<LeafGenerationEventDetail>) => void>();
		const completedListener =
			vi.fn<(event: CustomEvent<LeafGenerationCompletedEventDetail>) => void>();
		window.addEventListener(
			LEAF_GENERATION_EVENT,
			generationListener as EventListener,
		);
		window.addEventListener(
			LEAF_GENERATION_COMPLETED_EVENT,
			completedListener as EventListener,
		);

		dispatchLeafGenerationEvent({
			event: "agent_result",
			kind: "course_resource_section",
			course_id: "year_3_course_1",
			chapter_section_id: "1",
			section_id: "1.1",
			phase,
			status: "completed",
			success: true,
			summary: "资源阶段已完成",
		});

		expect(generationListener).toHaveBeenCalledTimes(1);
		expect(completedListener).toHaveBeenCalledTimes(1);
		expect(completedListener.mock.calls[0][0].detail).toEqual({
			courseId: "year_3_course_1",
			reason: "course_resource",
		});

		window.removeEventListener(
			LEAF_GENERATION_EVENT,
			generationListener as EventListener,
		);
		window.removeEventListener(
			LEAF_GENERATION_COMPLETED_EVENT,
			completedListener as EventListener,
		);
	});
});
