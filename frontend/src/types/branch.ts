export type BranchCourseStatus = "completed" | "current" | "locked";

export interface BranchCourseNode {
	course_node_id: string;
	course_or_chapter_theme: string;
	course_goal: string;
	status: BranchCourseStatus;
	has_outline: boolean;

	// 新增可选元数据
	is_custom?: boolean;
	parent_preset_id?: string;
	prerequisite_ids?: string[];
	time_arrangement?: {
		semester_scope: string;
		duration: string;
		pace_reason?: string;
	};
	key_points?: string[];
	difficult_points?: string[];
	acceptance_criteria?: string[];
}

export interface BranchYear {
	grade_id: string;
	grade_name: string;
	has_courses: boolean;
	has_outline_content: boolean;
	is_clickable: boolean;
	current_course_id: string | null;
	courses: BranchCourseNode[];
}

export interface BranchOverview {
	years: Record<string, BranchYear>;
	updatedAt: string | null;
}
