import type { SessionAgentEvent } from "../../api/orchestration";

export const LEAF_GENERATION_EVENT = "mutiagent-leaf-generation-event";
export const LEAF_GENERATION_COMPLETED_EVENT =
	"mutiagent-leaf-generation-completed";

export interface LeafGenerationEventDetail {
	courseId: string;
	chapterSectionId: string;
	sectionId: string | null;
	phase: string;
	status: string;
	message: string;
}

export type LeafGenerationCompletedReason =
	| "course_outline"
	| "course_resource";

export interface LeafGenerationCompletedEventDetail {
	courseId: string;
	reason: LeafGenerationCompletedReason;
}

export function dispatchLeafGenerationEvent(event: SessionAgentEvent) {
	if (!event.course_id || !event.chapter_section_id) return;
	if (
		event.kind !== "course_resource_section" &&
		event.kind !== "course_resource_chapter"
	)
		return;
	const courseId = event.course_id;
	window.dispatchEvent(
		new CustomEvent<LeafGenerationEventDetail>(LEAF_GENERATION_EVENT, {
			detail: {
				courseId,
				chapterSectionId: event.chapter_section_id,
				sectionId: event.section_id ?? null,
				phase: event.phase ?? "",
				status: event.status ?? "",
				message: event.message ?? event.error ?? event.summary ?? "",
			},
		}),
	);
	if (
		event.event === "agent_result" &&
		event.success === true &&
		event.status === "completed"
	) {
		dispatchLeafGenerationCompleted(courseId);
	}
}

export function dispatchLeafGenerationCompleted(
	courseId: string,
	reason: LeafGenerationCompletedReason = "course_resource",
) {
	window.dispatchEvent(
		new CustomEvent<LeafGenerationCompletedEventDetail>(
			LEAF_GENERATION_COMPLETED_EVENT,
			{ detail: { courseId, reason } },
		),
	);
}
