import type { ProtectedCourse, TextbookOutline } from "../backendClient.js";
import { gradeYearFromCurrentGrade } from "./profileContract.js";

export const MIN_COURSES = 4;
export const MAX_COURSES = 8;
export const MAX_SOURCE_SECTIONS = 7;

export type IntakeStatus = "draft" | "risk_pending" | "confirmed";

export interface IntakeCourse {
	title: string;
	purpose: string;
	source_textbook_id: string;
	source_textbook_title: string;
	source_outline_section_ids: string[];
}

export interface IntakeDraft {
	type: "learning_path_intake";
	status: IntakeStatus;
	grade_year: string;
	grade_name: string;
	learning_topic: string;
	courses: IntakeCourse[];
	recommendation_reasons: string[];
	user_modification_summary: string;
	risk_warnings: string[];
	requires_second_confirmation: boolean;
}

const asText = (value: unknown): string => (typeof value === "string" ? value.trim() : "");

export function readIntake(raw: unknown): IntakeDraft | null {
	if (!raw || typeof raw !== "object") return null;
	const value = raw as Record<string, unknown>;
	if (value.type !== "learning_path_intake" || !Array.isArray(value.courses)) return null;
	if (!["draft", "risk_pending", "confirmed"].includes(String(value.status))) return null;
	return value as unknown as IntakeDraft;
}

/** Session state of the intake: `none` when there is no draft at all. */
export function intakeStatusOf(intake: IntakeDraft | null): IntakeStatus | "none" {
	return intake ? intake.status : "none";
}

export interface DraftToolCourse {
	title?: unknown;
	purpose?: unknown;
	source_textbook_id?: unknown;
	source_textbook_title?: unknown;
	source_outline_section_ids?: unknown;
}

/** section ids per textbook that a course may legally cite. */
export type SectionCatalog = Map<string, { title: string; sectionIds: Set<string> }>;

export function catalogOf(outlines: TextbookOutline[]): SectionCatalog {
	const catalog: SectionCatalog = new Map();
	for (const outline of outlines) {
		const entry = catalog.get(outline.textbook_id) ?? { title: outline.title, sectionIds: new Set<string>() };
		for (const section of outline.sections) {
			if (section.section_id && section.title) entry.sectionIds.add(section.section_id);
		}
		catalog.set(outline.textbook_id, entry);
	}
	return catalog;
}

/** Bindings already present in the current draft are trusted verbatim (validated when created). */
function sameBinding(course: IntakeCourse, existing: IntakeCourse[]): boolean {
	return existing.some(
		(old) =>
			old.source_textbook_id === course.source_textbook_id &&
			old.source_outline_section_ids.length === course.source_outline_section_ids.length &&
			old.source_outline_section_ids.every((id, index) => id === course.source_outline_section_ids[index]),
	);
}

export interface ValidatedCourses {
	courses: IntakeCourse[];
	errors: string[];
}

/**
 * Deterministic source-binding check: every course must cite a real textbook and
 * real section ids from the catalog (or an unchanged binding of the current draft).
 * Errors name the exact offending items so the model can fix them in-place.
 */
export function validateDraftCourses(
	rawCourses: unknown,
	catalog: SectionCatalog,
	existing: IntakeCourse[],
): ValidatedCourses {
	const errors: string[] = [];
	if (!Array.isArray(rawCourses)) {
		return { courses: [], errors: ["courses 必须是 4-8 门课程的数组。"] };
	}
	if (rawCourses.length < MIN_COURSES || rawCourses.length > MAX_COURSES) {
		errors.push(`课程数量必须在 ${MIN_COURSES}-${MAX_COURSES} 门之间，当前是 ${rawCourses.length} 门。`);
	}
	const courses: IntakeCourse[] = [];
	rawCourses.forEach((raw: DraftToolCourse, index) => {
		const label = `第 ${index + 1} 门课`;
		const title = asText(raw?.title);
		const purpose = asText(raw?.purpose);
		const textbookId = asText(raw?.source_textbook_id);
		const sectionIds = Array.isArray(raw?.source_outline_section_ids)
			? raw.source_outline_section_ids.map(asText).filter(Boolean)
			: [];
		if (!title) errors.push(`${label}缺少 title。`);
		if (!purpose) errors.push(`${label}《${title}》缺少 purpose（说明教材小节覆盖的学习边界）。`);
		const course: IntakeCourse = {
			title,
			purpose,
			source_textbook_id: textbookId,
			source_textbook_title: "",
			source_outline_section_ids: sectionIds,
		};
		if (sectionIds.length < 1 || sectionIds.length > MAX_SOURCE_SECTIONS) {
			errors.push(`${label}《${title}》必须绑定 1-${MAX_SOURCE_SECTIONS} 个教材小节。`);
		}
		const textbook = catalog.get(textbookId);
		if (textbook) {
			course.source_textbook_title = textbook.title;
			const unknown = sectionIds.filter((id) => !textbook.sectionIds.has(id));
			if (unknown.length > 0 && !sameBinding(course, existing)) {
				errors.push(
					`${label}《${title}》引用了教材「${textbook.title}」中不存在的小节 ID：${unknown.join("、")}。小节 ID 必须逐字复制目录中的 section_id。`,
				);
			}
		} else if (sameBinding(course, existing)) {
			course.source_textbook_title =
				existing.find((old) => old.source_textbook_id === textbookId)?.source_textbook_title ?? "";
		} else {
			errors.push(`${label}《${title}》引用了不存在的教材 ID「${textbookId}」，只能使用你已用 get_textbook_outline 查看过的已发布教材。`);
		}
		courses.push(course);
	});
	return { courses, errors };
}

/** Programmatic risk detection: protected courses that the new draft drops or replaces. */
export function detectRisks(courses: IntakeCourse[], protectedCourses: ProtectedCourse[]): string[] {
	const titles = new Set(courses.map((course) => course.title.trim()));
	return protectedCourses
		.filter((entry) => !titles.has(entry.title.trim()))
		.map((entry) => `替换/删除${entry.reason}的课程《${entry.title}》`);
}

export function buildDraft(input: {
	profile: Record<string, unknown> | null;
	learningTopic: string;
	courses: IntakeCourse[];
	reasons: string[];
	modificationSummary: string;
	risks: string[];
}): IntakeDraft {
	const confirmed = ((input.profile?.confirmed_info as Record<string, unknown> | undefined) ?? {}) as Record<string, unknown>;
	const gradeName = asText(confirmed.current_grade);
	const risky = input.risks.length > 0;
	return {
		type: "learning_path_intake",
		status: risky ? "risk_pending" : "draft",
		grade_year: gradeYearFromCurrentGrade(gradeName),
		grade_name: gradeName,
		learning_topic: input.learningTopic,
		courses: input.courses,
		recommendation_reasons: input.reasons.length > 0 ? input.reasons : [`目标是学习${input.learningTopic}`],
		user_modification_summary: input.modificationSummary,
		risk_warnings: input.risks,
		requires_second_confirmation: risky,
	};
}

export function draftResponseText(intake: IntakeDraft): string {
	const lines = [
		"基础画像已经完成，我先把正式学习路径生成前的课程草稿整理出来。",
		`推荐理由：${intake.recommendation_reasons.join("；")}。`,
		`年级：${intake.grade_name}；主题：${intake.learning_topic}。`,
		"课程草稿：",
		...intake.courses.map((course, index) => `${index + 1}. ${course.title}：${course.purpose}`),
	];
	if (intake.status === "risk_pending") {
		lines.push("\n⚠️【风险提示】检测到本次修改包含以下敏感操作：");
		lines.push(...intake.risk_warnings.map((warning) => `- ${warning}`));
		lines.push(
			"这会导致相关课程的已生成内容或进度丢失。下一步是确认是否继续替换或删除这些课程。如果确认继续，直接告诉我即可；如果想保留原路径，也可以说“先不改”。",
		);
	} else {
		lines.push(
			"下一步是生成正式学习路径，系统会把这份草稿变成具体课程顺序、学习目标、时间安排和下一步行动。可以开始下一步吗？如果同意，直接回复即可，也可以点击“确认并生成学习路径”。如果想改，直接告诉我想怎么调整。",
		);
	}
	return lines.join("\n");
}

export const riskCancelledText = (intake: IntakeDraft): string =>
	`好的，已保留原学习路径，不做本次修改。${intake.learning_topic ? `${intake.learning_topic}的` : ""}课程草稿已回到普通草稿状态，你也可以继续告诉我哪里需要修改。`;

export function noTextbookText(topic: string, hasDraft: boolean): string {
	return hasDraft
		? `知识库暂无覆盖「${topic}」的已发布教材，已加入管理员待办。你原有的课程草稿已为你保留，可以继续调整，或者直接确认原草稿。`
		: `知识库暂无覆盖「${topic}」的已发布教材，已加入管理员待办。你可以换一个学习方向，或者等教材补充后再来规划。`;
}

export function outlineText(outline: TextbookOutline): string {
	const sections = outline.sections.map((section) => `- ${section.section_id}｜${section.title}`).join("\n");
	return `教材 ${outline.textbook_id}｜${outline.title}\n${sections}`;
}
