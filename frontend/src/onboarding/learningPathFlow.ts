import type { ChatMessage, LearningPathResult } from "../types/chat";

export const LEARNING_PATH_UPDATED_EVENT = "mutiagent-learning-path-updated";
export const LEARNING_PATH_GENERATION_DRAFT = "进入学习路径草案智能体";

export function buildLearningPathGenerationDraft(): string {
	return LEARNING_PATH_GENERATION_DRAFT;
}

export function buildCourseOutlineDraft(
	courseName: string,
	courseNodeId: string,
): string {
	return [
		`帮我生成《${courseName}》的课程大纲`,
		"",
		"[COURSE_OUTLINE_GENERATION]",
		`course_node_id: ${courseNodeId}`,
		"[/COURSE_OUTLINE_GENERATION]",
	].join("\n");
}

export function buildCurrentCourseOutlineDraft(
	path: LearningPathResult,
): string {
	const course = path.current_learning_course;
	return buildCourseOutlineDraft(
		course.course_or_chapter_theme,
		course.course_node_id,
	);
}

export function hasLearningPathInMessages(messages: ChatMessage[]): boolean {
	return messages.some((message) => Boolean(message.learningPath));
}

export function hasLearningOutputInMessages(messages: ChatMessage[]): boolean {
	return messages.some((message) =>
		Boolean(message.learningPath || message.courseKnowledge),
	);
}

export function findLatestLearningPath(
	messages: ChatMessage[],
): LearningPathResult | null {
	for (let index = messages.length - 1; index >= 0; index -= 1) {
		const path = messages[index].learningPath;
		if (path) return path;
	}
	return null;
}

export function dispatchLearningPathUpdated(
	sessionId: string | null | undefined,
): void {
	window.dispatchEvent(
		new CustomEvent(LEARNING_PATH_UPDATED_EVENT, {
			detail: { sessionId: sessionId ?? null },
		}),
	);
}
