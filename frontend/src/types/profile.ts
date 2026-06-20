import {
	type CourseKnowledgeResult,
	type CourseNode,
	isCourseKnowledgeResult,
	type LearningPathResult,
} from "./chat";

/**
 * 用户画像数据类型
 * 基于 Dify Agent 的 basic_profile → generated 阶段输出的 confirmed_info 结构
 */

export interface UserProfile {
	currentGrade: string;
	major: string;
	learningStage: string;
	hasClearGoal: string;
	learningMethodPreference: string;
	learningPacePreference: string;
	contentPreference: string[];
	needGuidance: string;
	knowledgeFoundation: string;
	strengths: string;
	weaknesses: string;
	experience: string;
	shortTermGoal: string;
	longTermGoal: string;
	weeklyAvailableTime: string;
	constraints: string;
}

export type RecommendationAccent = "lavender" | "sage" | "peach";

export interface LearningRecommendation {
	id: string;
	title: string;
	duration: string;
	description: string;
	accent: RecommendationAccent;
}

export interface TodayLearning {
	title: string;
	description: string;
	source: string;
	currentLearningCourse: LearningPathResult["current_learning_course"] | null;
	currentCourseDetail: CourseNode | null;
	currentCourseOutline: CourseKnowledgeResult | null;
	gradeCourses: CourseNode[];
	followingCourses: CourseNode[];
}

export interface ProfileDashboardData {
	profile: UserProfile;
	profileCompleteness: number;
	profileSummaryText: string;
	todayLearning: TodayLearning;
	recommendations: LearningRecommendation[];
}

function isRecord(value: unknown): value is Record<string, unknown> {
	return value !== null && typeof value === "object";
}

function isStringArray(value: unknown): value is string[] {
	return (
		Array.isArray(value) && value.every((item) => typeof item === "string")
	);
}

function isRecommendationAccent(value: unknown): value is RecommendationAccent {
	return value === "lavender" || value === "sage" || value === "peach";
}

function isTimeArrangement(
	value: unknown,
): value is CourseNode["time_arrangement"] {
	return (
		isRecord(value) &&
		typeof value.semester_scope === "string" &&
		typeof value.duration === "string" &&
		typeof value.pace_reason === "string"
	);
}

function isCurrentLearningCourse(
	value: unknown,
): value is NonNullable<TodayLearning["currentLearningCourse"]> {
	return (
		isRecord(value) &&
		typeof value.grade_id === "string" &&
		typeof value.course_node_id === "string" &&
		typeof value.course_or_chapter_theme === "string" &&
		typeof value.course_goal === "string" &&
		isTimeArrangement(value.time_arrangement) &&
		typeof value.current_focus === "string" &&
		(value.progress_state === "in_progress" ||
			value.progress_state === "completed") &&
		typeof value.next_action === "string"
	);
}

function isCourseNode(value: unknown): value is CourseNode {
	return (
		isRecord(value) &&
		typeof value.course_node_id === "string" &&
		typeof value.grade_id === "string" &&
		typeof value.course_or_chapter_theme === "string" &&
		isTimeArrangement(value.time_arrangement) &&
		typeof value.course_goal === "string" &&
		Array.isArray(value.prerequisite_node_ids) &&
		Array.isArray(value.chapter_nodes) &&
		Array.isArray(value.core_knowledge_points) &&
		isStringArray(value.key_points) &&
		isStringArray(value.difficult_points) &&
		isStringArray(value.learning_sequence) &&
		Array.isArray(value.knowledge_relations) &&
		isStringArray(value.downstream_resource_direction_ids) &&
		isStringArray(value.acceptance_criteria)
	);
}

function isUserProfile(value: unknown): value is UserProfile {
	return (
		isRecord(value) &&
		typeof value.currentGrade === "string" &&
		typeof value.major === "string" &&
		typeof value.learningStage === "string" &&
		typeof value.hasClearGoal === "string" &&
		typeof value.learningMethodPreference === "string" &&
		typeof value.learningPacePreference === "string" &&
		isStringArray(value.contentPreference) &&
		typeof value.needGuidance === "string" &&
		typeof value.knowledgeFoundation === "string" &&
		typeof value.strengths === "string" &&
		typeof value.weaknesses === "string" &&
		typeof value.experience === "string" &&
		typeof value.shortTermGoal === "string" &&
		typeof value.longTermGoal === "string" &&
		typeof value.weeklyAvailableTime === "string" &&
		typeof value.constraints === "string"
	);
}

function isTodayLearning(value: unknown): value is TodayLearning {
	return (
		isRecord(value) &&
		typeof value.title === "string" &&
		typeof value.description === "string" &&
		typeof value.source === "string" &&
		(value.currentLearningCourse === null ||
			isCurrentLearningCourse(value.currentLearningCourse)) &&
		(value.currentCourseDetail === null ||
			isCourseNode(value.currentCourseDetail)) &&
		(value.currentCourseOutline === null ||
			isCourseKnowledgeResult(value.currentCourseOutline)) &&
		Array.isArray(value.gradeCourses) &&
		value.gradeCourses.every((course) => isCourseNode(course)) &&
		Array.isArray(value.followingCourses) &&
		value.followingCourses.every((course) => isCourseNode(course))
	);
}

function isLearningRecommendation(
	value: unknown,
): value is LearningRecommendation {
	return (
		isRecord(value) &&
		typeof value.id === "string" &&
		typeof value.title === "string" &&
		typeof value.duration === "string" &&
		typeof value.description === "string" &&
		isRecommendationAccent(value.accent)
	);
}

export function isProfileDashboardData(
	value: unknown,
): value is ProfileDashboardData {
	return (
		isRecord(value) &&
		isUserProfile(value.profile) &&
		typeof value.profileCompleteness === "number" &&
		typeof value.profileSummaryText === "string" &&
		isTodayLearning(value.todayLearning) &&
		Array.isArray(value.recommendations) &&
		value.recommendations.every((item) => isLearningRecommendation(item))
	);
}
