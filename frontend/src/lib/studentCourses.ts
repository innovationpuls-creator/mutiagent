import type { BranchCourseNode, BranchOverview } from "../types/branch";
export function normalizeProgramCourses(
	rawCourses: unknown,
): BranchCourseNode[] {
	if (!Array.isArray(rawCourses)) return [];
	return rawCourses
		.filter((course): course is BranchCourseNode => {
			if (!course || typeof course !== "object" || Array.isArray(course))
				return false;
			const node = course as Partial<BranchCourseNode>;
			return (
				typeof node.course_node_id === "string" &&
				typeof node.course_or_chapter_theme === "string" &&
				typeof node.course_goal === "string" &&
				typeof node.status === "string" &&
				typeof node.has_outline === "boolean"
			);
		})
		.map((course) => ({
			...course,
			status: course.status === "locked" ? "current" : course.status,
			is_custom: true,
		}));
}

export function mergeProgramCourses(
	overview: BranchOverview,
	presetCourses: BranchCourseNode[],
) {
	presetCourses.forEach((preset) => {
		const sem = parseInt(preset.time_arrangement?.semester_scope || "1", 10);
		let yearId: "year_1" | "year_2" | "year_3" | "year_4" = "year_1";
		if (sem >= 7) yearId = "year_4";
		else if (sem >= 5) yearId = "year_3";
		else if (sem >= 3) yearId = "year_2";

		const year = overview.years[yearId];
		if (year) {
			const existIdx = year.courses.findIndex(
				(course) => course.course_node_id === preset.course_node_id,
			);
			if (existIdx >= 0) {
				const existingCourse = year.courses[existIdx];
				year.courses[existIdx] = {
					...preset,
					...existingCourse,
					status: existingCourse.status,
					key_points: preset.key_points,
					difficult_points: preset.difficult_points,
					acceptance_criteria: preset.acceptance_criteria,
					is_custom: true,
				};
			} else {
				year.courses.push(preset);
			}
			year.has_courses = true;
			year.is_clickable = true;
		}
	});
}
