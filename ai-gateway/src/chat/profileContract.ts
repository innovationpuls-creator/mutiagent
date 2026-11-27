/**
 * Deterministic profile contract. The model only fills business-semantic fields;
 * every object that reaches storage or the frontend card is assembled here so it
 * always satisfies `pickProfile` / `hasCompleteBasicProfileRecord`
 * (frontend/src/api/orchestration.ts), regardless of model quality.
 */

export const CONFIRMED_KEYS = [
	"current_grade",
	"major",
	"learning_stage",
	"has_clear_goal",
	"learning_method_preference",
	"learning_pace_preference",
	"content_preference",
	"need_guidance",
	"knowledge_foundation",
	"strengths",
	"weaknesses",
	"experience",
	"short_term_goal",
	"long_term_goal",
	"weekly_available_time",
	"constraints",
] as const;
export type ConfirmedKey = (typeof CONFIRMED_KEYS)[number];
export type ConfirmedInfo = Record<ConfirmedKey, string | string[]>;

/** Must come from the student's own words unless they asked for defaults. */
export const CORE_KEYS: readonly ConfirmedKey[] = [
	"current_grade",
	"major",
	"learning_stage",
	"short_term_goal",
	"weekly_available_time",
	"learning_method_preference",
];
export const SECONDARY_KEYS: readonly ConfirmedKey[] = CONFIRMED_KEYS.filter(
	(key) => !CORE_KEYS.includes(key),
);

export const UNKNOWN_VALUE = "未知";
export const FREE_TEXT_VALUE = "__free_text__";

const GRADE_LABELS: Array<[string, string]> = [
	["大一", "year_1"],
	["大1", "year_1"],
	["一年级", "year_1"],
	["大二", "year_2"],
	["大2", "year_2"],
	["二年级", "year_2"],
	["大三", "year_3"],
	["大3", "year_3"],
	["三年级", "year_3"],
	["大四", "year_4"],
	["大4", "year_4"],
	["四年级", "year_4"],
];

export function gradeYearFromCurrentGrade(grade: unknown): string {
	const text = String(grade ?? "").trim();
	if (!text) return "";
	return GRADE_LABELS.find(([label]) => text.includes(label))?.[1] ?? "";
}

export function isSupportedGrade(grade: unknown): boolean {
	return gradeYearFromCurrentGrade(grade) !== "";
}

export function unsupportedGradeMessage(grade: unknown): string {
	const text = String(grade ?? "").trim();
	const head = text
		? `当前学习路径只支持大一到大四。你当前提供的年级是「${text}」，请先确认对应的本科年级。`
		: "当前学习路径只支持大一到大四，请先确认你的本科年级。";
	return `${head} 如果你想继续生成学习路径，请先告诉我对应的本科年级（大一到大四）。`;
}

const DEFAULT_FILL_MARKERS = [
	"随便帮我填",
	"不确定的你随便帮我填",
	"直接生成",
	"你直接生成",
	"帮我直接生成",
	"不用问了",
	"不用再问了",
	"不需要这么详细",
	"跳过",
	"先跳过",
	"不用这么详细",
	"快速生成",
	"直接帮我生成",
];
const DEFAULT_FILL_CONTEXT = ["画像", "补全", "填", "生成"];

/** The student explicitly asked the system to fill unknown fields with defaults. */
export function allowsDefaultFill(text: string): boolean {
	const normalized = text.trim();
	if (!normalized) return false;
	if (DEFAULT_FILL_MARKERS.some((marker) => normalized.includes(marker))) return true;
	return normalized.includes("默认") && DEFAULT_FILL_CONTEXT.some((marker) => normalized.includes(marker));
}

export interface ProfileOption {
	label: string;
	value: string;
	description: string;
	target_fields: string[];
	fills: Record<string, string | string[]>;
}

export const FREE_TEXT_OPTION: ProfileOption = {
	label: "其他",
	value: FREE_TEXT_VALUE,
	description: "以上都不符合，我来输入",
	target_fields: [],
	fills: {},
};

function fieldOption(
	field: ConfirmedKey,
	label: string,
	description: string,
	value = label,
): ProfileOption {
	return {
		label,
		value,
		description,
		target_fields: [field],
		fills: { [field]: field === "content_preference" ? [value] : value },
	};
}

interface FieldQuestion {
	question: string;
	stage: "basic_info" | "learning_preference" | "ability_basis" | "goal_constraint";
	options: ProfileOption[];
}

const gradeOptions = (description: string): ProfileOption[] => [
	...(["大一", "大二", "大三", "大四"] as const).map((grade) =>
		fieldOption("current_grade", `我是${grade}`, description, grade),
	),
	FREE_TEXT_OPTION,
];

/** Standard preset options; the model may not invent options for these fields. */
export const FIELD_QUESTIONS: Partial<Record<ConfirmedKey, FieldQuestion>> = {
	current_grade: {
		question: "为了生成基础画像，请先告诉我你的年级。",
		stage: "basic_info",
		options: gradeOptions("先确认年级，再继续补充其他信息"),
	},
	major: {
		question: "为了生成基础画像，请先告诉我你的专业。",
		stage: "basic_info",
		options: [],
	},
	learning_stage: {
		question: "你目前的学习阶段是？",
		stage: "learning_preference",
		options: [
			fieldOption("learning_stage", "有基础", "已学过相关课程，有一定基础"),
			fieldOption("learning_stage", "刚入门", "刚开始接触这个领域"),
			fieldOption("learning_stage", "项目实践", "已有项目经验，想进一步提升"),
			fieldOption("learning_stage", "准备就业", "即将毕业，以就业为导向"),
			FREE_TEXT_OPTION,
		],
	},
	has_clear_goal: {
		question: "你的学习目标清晰吗？",
		stage: "learning_preference",
		options: [
			fieldOption("has_clear_goal", "目标明确", "清楚自己要学什么", "是"),
			fieldOption("has_clear_goal", "大致有方向", "知道大方向，细节待定"),
			fieldOption("has_clear_goal", "还没想好", "需要帮助探索方向", "否"),
			FREE_TEXT_OPTION,
		],
	},
	learning_method_preference: {
		question: "你偏好哪种学习方式？",
		stage: "learning_preference",
		options: [
			fieldOption("learning_method_preference", "项目驱动学习", "通过做项目来学"),
			fieldOption("learning_method_preference", "系统课程学习", "按课程体系系统学习"),
			fieldOption("learning_method_preference", "AI 交互式学习", "通过与 AI 对话来学习"),
			fieldOption("learning_method_preference", "刷题巩固", "通过大量练习来掌握"),
			FREE_TEXT_OPTION,
		],
	},
	learning_pace_preference: {
		question: "你希望什么学习节奏？",
		stage: "learning_preference",
		options: [
			fieldOption("learning_pace_preference", "每天少量", "每天 1-2 小时"),
			fieldOption("learning_pace_preference", "周末集中", "周末集中学习"),
			fieldOption("learning_pace_preference", "按项目里程碑推进", "按项目进度灵活安排"),
			fieldOption("learning_pace_preference", "高强度冲刺", "短期内集中大量学习"),
			FREE_TEXT_OPTION,
		],
	},
	content_preference: {
		question: "你偏好什么内容形式？",
		stage: "learning_preference",
		options: [
			fieldOption("content_preference", "文档为主", "喜欢阅读文档学习", "文档"),
			fieldOption("content_preference", "视频为主", "喜欢看视频学习", "视频"),
			fieldOption("content_preference", "代码实践为主", "喜欢通过写代码学习", "代码实践"),
			fieldOption("content_preference", "项目案例为主", "喜欢通过完整项目学习", "项目案例"),
			FREE_TEXT_OPTION,
		],
	},
	need_guidance: {
		question: "你需要什么程度的引导？",
		stage: "learning_preference",
		options: [
			fieldOption("need_guidance", "需要强引导", "希望有详细步骤指导"),
			fieldOption("need_guidance", "需要轻量提醒", "偶尔需要关键节点提醒"),
			fieldOption("need_guidance", "更喜欢自主探索", "自己摸索为主"),
			FREE_TEXT_OPTION,
		],
	},
	knowledge_foundation: {
		question: "你目前的知识基础是什么？",
		stage: "ability_basis",
		options: [
			fieldOption("knowledge_foundation", "编程基础扎实", "数据结构、算法、设计模式等掌握较好"),
			fieldOption("knowledge_foundation", "有前后端基础", "了解 Web 开发基本流程"),
			fieldOption("knowledge_foundation", "有 Python 基础", "能用 Python 写脚本和小工具"),
			FREE_TEXT_OPTION,
		],
	},
	strengths: {
		question: "你的优势是什么？",
		stage: "ability_basis",
		options: [
			fieldOption("strengths", "动手能力强", "善于从零开始做项目"),
			fieldOption("strengths", "学习能力强", "能快速掌握新技术"),
			fieldOption("strengths", "逻辑思维好", "善于分析和拆解问题"),
			FREE_TEXT_OPTION,
		],
	},
	weaknesses: {
		question: "你的薄弱点是什么？",
		stage: "ability_basis",
		options: [
			fieldOption("weaknesses", "缺少项目经验", "理论知识有但实战少"),
			fieldOption("weaknesses", "缺少系统训练", "知识比较零散"),
			fieldOption("weaknesses", "调试能力不足", "遇到问题不知从何排查"),
			FREE_TEXT_OPTION,
		],
	},
	experience: {
		question: "你有什么相关经验？",
		stage: "ability_basis",
		options: [
			fieldOption("experience", "有课程项目经验", "做过课程设计或大作业"),
			fieldOption("experience", "有实习经验", "参加过企业实习"),
			fieldOption("experience", "有个人项目经验", "自己做过独立项目"),
			FREE_TEXT_OPTION,
		],
	},
	short_term_goal: {
		question: "你的近期目标是什么？",
		stage: "learning_preference",
		options: [
			fieldOption("short_term_goal", "找工作", "以就业为近期目标"),
			fieldOption("short_term_goal", "考研", "以考研为近期目标"),
			fieldOption("short_term_goal", "提升能力", "以提升技术能力为目标"),
			fieldOption("short_term_goal", "完成一个项目", "做出一个可运行的作品"),
			FREE_TEXT_OPTION,
		],
	},
	long_term_goal: {
		question: "你的长期目标是什么？",
		stage: "goal_constraint",
		options: [
			fieldOption("long_term_goal", "成为全栈开发者", "前后端都能独立完成"),
			fieldOption("long_term_goal", "成为 AI 应用开发者", "专注于 AI 应用方向"),
			fieldOption("long_term_goal", "还没想好", "先学着再说"),
			FREE_TEXT_OPTION,
		],
	},
	weekly_available_time: {
		question: "每周可投入多少时间学习？",
		stage: "learning_preference",
		options: [
			fieldOption("weekly_available_time", "每周 6-10 小时", "中等投入"),
			fieldOption("weekly_available_time", "每周 10-15 小时", "较高投入"),
			fieldOption("weekly_available_time", "每周 15 小时以上", "高强度投入"),
			FREE_TEXT_OPTION,
		],
	},
	constraints: {
		question: "你有什么主要约束或限制？",
		stage: "goal_constraint",
		options: [
			fieldOption("constraints", "平时课程多", "学期中时间紧张"),
			fieldOption("constraints", "缺少指导", "没有合适的引路人"),
			fieldOption("constraints", "没有特别约束", "时间精力都比较充裕"),
			FREE_TEXT_OPTION,
		],
	},
};

/** Reasonable fallbacks for secondary fields when the student asked for defaults. */
export const SECONDARY_DEFAULTS: Record<string, string | string[]> = {
	has_clear_goal: "大致有方向",
	learning_pace_preference: "按项目里程碑推进",
	content_preference: ["代码实践", "项目案例"],
	need_guidance: "需要轻量提醒",
	knowledge_foundation: "具备本专业基础课程知识",
	strengths: "工程实现与课程学习能力",
	weaknesses: "大型项目实战经验",
	experience: "课程学习阶段",
	long_term_goal: "形成系统学习能力",
	constraints: "平时学习节奏，避免过高强度",
};

export const CORE_DEFAULTS: Record<string, string> = {
	learning_stage: "有基础",
	learning_method_preference: "项目驱动学习",
	short_term_goal: "完成一个可运行的课程级项目",
	weekly_available_time: "每周 6-10 小时",
};

function isEmpty(key: ConfirmedKey, value: unknown): boolean {
	if (key === "content_preference") {
		return !Array.isArray(value) || value.length === 0 || value.every((item) => !String(item).trim());
	}
	const text = typeof value === "string" ? value.trim() : "";
	return text === "" || text === UNKNOWN_VALUE;
}

export function emptyConfirmedInfo(): ConfirmedInfo {
	return Object.fromEntries(
		CONFIRMED_KEYS.map((key) => [key, key === "content_preference" ? [] : ""]),
	) as ConfirmedInfo;
}

/** Normalize arbitrary input into the 16-key shape (unknown keys are dropped). */
export function normalizeConfirmed(raw: unknown): ConfirmedInfo {
	const result = emptyConfirmedInfo();
	if (!raw || typeof raw !== "object") return result;
	const source = raw as Record<string, unknown>;
	for (const key of CONFIRMED_KEYS) {
		const value = source[key];
		if (key === "content_preference") {
			if (Array.isArray(value)) {
				result[key] = value.map((item) => String(item).trim()).filter(Boolean);
			} else if (typeof value === "string" && value.trim()) {
				result[key] = value.split(/[，,、；;/\s]+/).map((item) => item.trim()).filter(Boolean);
			}
		} else if (typeof value === "string") {
			result[key] = value.trim();
		}
	}
	return result;
}

/** Fields the incoming patch fills; empty / unknown patch values never erase data. */
export function mergeConfirmed(base: ConfirmedInfo, patch: unknown): ConfirmedInfo {
	const incoming = normalizeConfirmed(patch);
	const merged = { ...base };
	for (const key of CONFIRMED_KEYS) {
		if (!isEmpty(key, incoming[key])) merged[key] = incoming[key];
	}
	return merged;
}

export function missingKeys(confirmed: ConfirmedInfo, keys: readonly ConfirmedKey[] = CONFIRMED_KEYS): ConfirmedKey[] {
	return keys.filter((key) => isEmpty(key, confirmed[key]));
}

export function missingCoreKeys(confirmed: ConfirmedInfo): ConfirmedKey[] {
	return missingKeys(confirmed, CORE_KEYS);
}

export interface QuestionBox {
	question: string;
	options: ProfileOption[];
}

export interface CollectingProfile {
	type: "collecting";
	stage: string;
	question_mode: "question_box";
	confirmed_info: ConfirmedInfo;
	defaulted_fields: string[];
	question_md: string;
	question_box: QuestionBox;
	question_form: null;
	text: string;
}

export interface BasicProfile {
	type: "basic_profile";
	stage: "generated";
	question_mode: "question_box";
	confirmed_info: ConfirmedInfo;
	defaulted_fields: string[];
	question_md: string;
	question_box: QuestionBox;
	text: string;
	summary_text: string;
}

export function buildCollectingProfile(input: {
	confirmed: ConfirmedInfo;
	questionMd: string;
	options: ProfileOption[];
	stage: string;
	defaulted?: string[];
}): CollectingProfile {
	const question = input.questionMd.trim();
	return {
		type: "collecting",
		stage: input.stage,
		question_mode: "question_box",
		confirmed_info: input.confirmed,
		defaulted_fields: input.defaulted ?? [],
		question_md: question,
		question_box: { question, options: input.options },
		question_form: null,
		text: question,
	};
}

export const NEXT_STEP_BOX: QuestionBox = {
	question: "画像已生成，下一步要进入学习路径草案智能体吗？",
	options: [
		{
			label: "进入学习路径草案智能体",
			value: "进入学习路径草案智能体",
			description: "根据当前画像定制学习路径草案结构",
			target_fields: [],
			fills: {},
		},
		{
			label: "修改画像方向",
			value: "修改画像方向",
			description: "继续补充年级、专业、目标或偏好",
			target_fields: [],
			fills: {},
		},
	],
};

export function buildBasicProfile(input: {
	confirmed: ConfirmedInfo;
	defaulted: string[];
	summary: string;
}): BasicProfile {
	return {
		type: "basic_profile",
		stage: "generated",
		question_mode: "question_box",
		confirmed_info: input.confirmed,
		defaulted_fields: input.defaulted,
		question_md: "画像已生成，是否进入学习路径草案智能体？",
		question_box: NEXT_STEP_BOX,
		text: input.summary,
		summary_text: input.summary,
	};
}

/** Draft carried from the stored profile (a `collecting` row or a completed one). */
export function draftFromProfile(profile: Record<string, unknown> | null): ConfirmedInfo {
	return normalizeConfirmed(profile?.confirmed_info);
}

export function isCompleteProfile(profile: Record<string, unknown> | null): boolean {
	if (!profile || profile.type !== "basic_profile") return false;
	const confirmed = profile.confirmed_info;
	if (!confirmed || typeof confirmed !== "object") return false;
	const record = confirmed as Record<string, unknown>;
	return (
		CONFIRMED_KEYS.every((key) => Object.hasOwn(record, key)) && isSupportedGrade(record.current_grade)
	);
}

/** The single next question when the model gave nothing usable (deterministic fallback). */
export function nextQuestionCard(confirmed: ConfirmedInfo, defaulted: string[] = []): CollectingProfile {
	const grade = String(confirmed.current_grade ?? "").trim();
	if (grade && !isSupportedGrade(grade)) {
		return buildCollectingProfile({
			confirmed: { ...confirmed, current_grade: "" },
			questionMd: unsupportedGradeMessage(grade),
			options: gradeOptions("按本科年级继续生成画像"),
			stage: "basic_info",
			defaulted,
		});
	}
	const order: ConfirmedKey[] = [
		"current_grade",
		"major",
		"learning_stage",
		"short_term_goal",
		"weekly_available_time",
		"learning_method_preference",
	];
	const key = order.find((candidate) => isEmpty(candidate, confirmed[candidate]));
	if (key) {
		const preset = FIELD_QUESTIONS[key]!;
		return buildCollectingProfile({
			confirmed,
			questionMd:
				key === "current_grade" && isEmpty("major", confirmed.major)
					? "为了生成基础画像，请先告诉我你的年级和专业。"
					: preset.question,
			options: preset.options,
			stage: preset.stage,
			defaulted,
		});
	}
	return buildCollectingProfile({
		confirmed,
		questionMd: "核心信息已收齐，还有几项补充信息，直接告诉我，或回复“按默认帮我生成画像”。",
		options: [],
		stage: "basic_info",
		defaulted,
	});
}
