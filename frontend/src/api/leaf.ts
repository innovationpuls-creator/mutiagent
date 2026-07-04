import type {
	LeafAnimationBlock,
	LeafComposedSection,
	LeafContentBlock,
	LeafCourse,
	LeafCourseResponse,
	LeafGenerationStatus,
	LeafSection,
	LeafSectionResourceError,
	LeafVideoBlock,
} from "../types/leaf";
import { API_BASE_URL, notifyAuthInvalidFromError, readApiError } from "./http";

function isRecord(value: unknown): value is Record<string, unknown> {
	return value !== null && typeof value === "object";
}

function isStringArray(value: unknown): value is string[] {
	return (
		Array.isArray(value) && value.every((item) => typeof item === "string")
	);
}

function normalizeCourse(value: unknown): LeafCourse {
	if (!isRecord(value)) throw new Error("叶茂数据格式不正确");
	if (
		typeof value.course_node_id !== "string" ||
		typeof value.grade_id !== "string" ||
		typeof value.course_or_chapter_theme !== "string" ||
		typeof value.course_goal !== "string" ||
		!["completed", "current", "locked"].includes(String(value.status)) ||
		typeof value.has_outline !== "boolean"
	) {
		throw new Error("叶茂数据格式不正确");
	}
	return value as unknown as LeafCourse;
}

function normalizeSection(value: unknown): LeafSection {
	if (!isRecord(value)) throw new Error("叶茂数据格式不正确");
	if (
		typeof value.section_id !== "string" ||
		!(
			value.parent_section_id === null ||
			typeof value.parent_section_id === "string"
		) ||
		typeof value.depth !== "number" ||
		typeof value.title !== "string" ||
		typeof value.order_index !== "number" ||
		typeof value.description !== "string" ||
		!isStringArray(value.key_knowledge_points) ||
		typeof value.source_textbook_id !== "string" ||
		typeof value.source_textbook_title !== "string" ||
		!isStringArray(value.source_section_ids) ||
		!isStringArray(value.source_section_titles) ||
		typeof value.source_content_chars !== "number"
	) {
		throw new Error("叶茂数据格式不正确");
	}
	return value as unknown as LeafSection;
}

function normalizeVideoItem(value: unknown): LeafVideoBlock["videos"][number] {
	if (!isRecord(value) || typeof value.url !== "string") {
		throw new Error("叶茂内容格式不正确");
	}

	return {
		title: typeof value.title === "string" ? value.title : "",
		url: value.url,
		cover_url: typeof value.cover_url === "string" ? value.cover_url : "",
		cover_status:
			typeof value.cover_status === "string" ? value.cover_status : "",
		source: typeof value.source === "string" ? value.source : "",
	};
}

function normalizeVideoBlock(value: Record<string, unknown>): LeafVideoBlock {
	if (
		typeof value.brief_id !== "string" ||
		typeof value.title !== "string" ||
		typeof value.purpose !== "string" ||
		(value.status !== "available" && value.status !== "unavailable") ||
		!Array.isArray(value.videos)
	) {
		throw new Error("叶茂内容格式不正确");
	}
	return {
		type: "video",
		brief_id: value.brief_id,
		title: value.title,
		purpose: value.purpose,
		status: value.status,
		videos: value.videos.map(normalizeVideoItem),
	};
}

function normalizeAnimationBlock(
	value: Record<string, unknown>,
): LeafAnimationBlock {
	if (
		typeof value.brief_id !== "string" ||
		typeof value.title !== "string" ||
		(value.status !== "available" && value.status !== "unavailable") ||
		typeof value.html !== "string"
	) {
		throw new Error("叶茂内容格式不正确");
	}
	return value as unknown as LeafAnimationBlock;
}

function normalizeBlock(value: unknown): LeafContentBlock {
	if (!isRecord(value) || typeof value.type !== "string") {
		throw new Error("叶茂内容格式不正确");
	}
	if (value.type === "markdown" && typeof value.markdown === "string") {
		return { type: "markdown", markdown: value.markdown };
	}
	if (value.type === "video") {
		return normalizeVideoBlock(value);
	}
	if (value.type === "animation") {
		return normalizeAnimationBlock(value);
	}
	throw new Error("叶茂内容格式不正确");
}

function normalizeComposedSection(value: unknown): LeafComposedSection {
	if (!isRecord(value) || !Array.isArray(value.blocks)) {
		throw new Error("叶茂内容格式不正确");
	}
	if (
		typeof value.section_id !== "string" ||
		!(
			value.parent_section_id === null ||
			typeof value.parent_section_id === "string"
		) ||
		typeof value.title !== "string" ||
		typeof value.markdown !== "string" ||
		typeof value.generated_at !== "string"
	) {
		throw new Error("叶茂内容格式不正确");
	}
	return {
		section_id: value.section_id,
		parent_section_id: value.parent_section_id,
		title: value.title,
		markdown: value.markdown,
		blocks: value.blocks.map(normalizeBlock),
		generated_at: value.generated_at,
	};
}

function normalizeSectionResourceError(
	value: unknown,
): LeafSectionResourceError {
	if (!isRecord(value)) {
		throw new Error("叶茂内容格式不正确");
	}
	if (
		typeof value.section_id !== "string" ||
		typeof value.phase !== "string" ||
		typeof value.message !== "string" ||
		typeof value.retryable !== "boolean" ||
		typeof value.updated_at !== "string"
	) {
		throw new Error("叶茂内容格式不正确");
	}
	return value as unknown as LeafSectionResourceError;
}

function normalizeGenerationStatus(
	value: unknown,
): LeafGenerationStatus | null {
	if (value === null || value === undefined) return null;
	if (!isRecord(value)) throw new Error("叶茂数据格式不正确");
	if (
		typeof value.course_node_id !== "string" ||
		typeof value.chapter_section_id !== "string" ||
		value.status !== "running" ||
		typeof value.message !== "string"
	) {
		throw new Error("叶茂数据格式不正确");
	}
	return value as unknown as LeafGenerationStatus;
}

export async function fetchLeafCourse(
	token: string,
	courseNodeId: string,
): Promise<LeafCourseResponse> {
	const response = await fetch(
		`${API_BASE_URL}/api/leaf/courses/${encodeURIComponent(courseNodeId)}`,
		{
			headers: { Authorization: `Bearer ${token}` },
		},
	);

	if (!response.ok) {
		const error = await readApiError(response);
		notifyAuthInvalidFromError(response.status, error);
		throw new Error(
			(typeof error?.detail === "string" ? error.detail : null) ??
				"叶茂数据加载失败",
		);
	}

	const payload = await response.json();
	if (!isRecord(payload) || !Array.isArray(payload.sections)) {
		throw new Error("叶茂数据格式不正确");
	}
	if (
		payload.access_state !== "available" &&
		payload.access_state !== "locked"
	) {
		throw new Error("叶茂数据格式不正确");
	}
	const composedRaw = isRecord(payload.section_composed_markdowns)
		? payload.section_composed_markdowns
		: {};
	const sectionComposedMarkdowns = Object.fromEntries(
		Object.entries(composedRaw).map(([sectionId, value]) => [
			sectionId,
			normalizeComposedSection(value),
		]),
	);
	const resourceErrorsRaw = isRecord(payload.section_resource_errors)
		? payload.section_resource_errors
		: {};
	const sectionResourceErrors = Object.fromEntries(
		Object.entries(resourceErrorsRaw).map(([sectionId, value]) => [
			sectionId,
			normalizeSectionResourceError(value),
		]),
	);

	return {
		access_state: payload.access_state,
		course: normalizeCourse(payload.course),
		outline: isRecord(payload.outline) ? payload.outline : null,
		sections: payload.sections.map(normalizeSection),
		section_composed_markdowns: sectionComposedMarkdowns,
		section_resource_errors: sectionResourceErrors,
		generation_status: normalizeGenerationStatus(payload.generation_status),
		can_generate: payload.can_generate === true,
		first_generatable_chapter_id:
			typeof payload.first_generatable_chapter_id === "string"
				? payload.first_generatable_chapter_id
				: null,
		locked_reason:
			typeof payload.locked_reason === "string" ? payload.locked_reason : null,
	};
}
