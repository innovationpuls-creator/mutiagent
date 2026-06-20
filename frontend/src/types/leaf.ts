import type { BranchCourseStatus } from "./branch";

export type LeafAccessState = "available" | "locked";

export interface LeafCourse {
	course_node_id: string;
	grade_id: string;
	course_or_chapter_theme: string;
	course_goal: string;
	status: BranchCourseStatus;
	has_outline: boolean;
}

export interface LeafSection {
	section_id: string;
	parent_section_id: string | null;
	depth: number;
	title: string;
	order_index: number;
	description: string;
	key_knowledge_points: string[];
}

export interface LeafGenerationStatus {
	course_node_id: string;
	chapter_section_id: string;
	status: "running" | "error";
	message: string;
}

export interface LeafMarkdownBlock {
	type: "markdown";
	markdown: string;
	recommendation_reason?: string;
}

export interface LeafVideoBlock {
	type: "video";
	brief_id: string;
	title: string;
	purpose: string;
	status: "available" | "unavailable";
	videos: Array<{
		title: string;
		url: string;
		cover_url: string;
		cover_status: string;
		source: string;
	}>;
}

export interface LeafAnimationBlock {
	type: "animation";
	brief_id: string;
	title: string;
	status: "available" | "unavailable";
	html: string;
}

export type LeafContentBlock =
	| LeafMarkdownBlock
	| LeafVideoBlock
	| LeafAnimationBlock;

export interface LeafComposedSection {
	section_id: string;
	parent_section_id: string | null;
	title: string;
	markdown: string;
	blocks: LeafContentBlock[];
	generated_at: string;
}

export interface LeafCourseResponse {
	access_state: LeafAccessState;
	course: LeafCourse;
	outline: Record<string, unknown> | null;
	sections: LeafSection[];
	section_composed_markdowns: Record<string, LeafComposedSection>;
	generation_status: LeafGenerationStatus | null;
	can_generate: boolean;
	first_generatable_chapter_id: string | null;
	locked_reason: string | null;
}
