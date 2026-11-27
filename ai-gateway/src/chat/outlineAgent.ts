import type { AgentTool, AgentToolResult } from "@earendil-works/pi-agent-core";
import { arr, obj, str } from "@earendil-works/pi-schema";
import type { BackendClient, OutlineSourceCourse } from "../backendClient.js";
import { BackendBusinessError, GatewayError } from "../errors.js";
import type { AgentStreamHandle } from "../models/runtime.js";
import { runAgent } from "./agentRunner.js";

export const ALL_CURRENT_GRADE = "__all_current_grade__";
/** One in-place repair of the Chinese naming; the compliance check itself lives in the backend. */
export const MAX_NAMING_CORRECTIONS = 1;
export const DEFAULT_OUTLINE_CONCURRENCY = 2;
export const PATH_CHANGED_TEXT = "学习路径在生成期间已更新，本次大纲未保存，请重新生成课程大纲。";

const NAMING_SCHEMA = obj({
	personalization_summary: str(),
	sections: arr(
		obj({
			section_id: str(),
			title: str(),
			description: str(),
			key_knowledge_points: arr(str()),
		}),
	),
});

export interface OutlineFailure {
	courseName: string;
	reason: string;
}

export type OutlineOutcome =
	| {
			kind: "generated";
			text: string;
			savedCourseIds: string[];
			failures: OutlineFailure[];
			gradeYear: string;
	  }
	| { kind: "blocked"; text: string }
	| { kind: "path_changed"; text: string }
	| { kind: "failed"; text: string };

export interface OutlineAgentInput {
	handle: AgentStreamHandle;
	backend: BackendClient;
	userUid: string;
	courseRef: string;
	userText: string;
	concurrency?: number;
	signal?: AbortSignal;
	emitProgress: (message: string) => void;
}

function text(value: string, extra: Partial<AgentToolResult<unknown>> = {}): AgentToolResult<unknown> {
	return { content: [{ type: "text", text: value }], details: undefined, ...extra };
}

export function buildNamingPrompt(course: OutlineSourceCourse, userText: string): string {
	const sections = course.skeleton.map((section) => ({
		section_id: section.section_id,
		level: section.depth === 1 ? "章" : "节",
		parent: section.parent_section_id,
		source_titles: section.source_section_titles ?? [],
		source_chars: section.source_content_chars ?? 0,
		part:
			section.source_chunk_total && section.source_chunk_total > 1
				? `教材小节被拆成 ${section.source_chunk_total} 个部分，这是第 ${section.source_chunk_index} 部分`
				: undefined,
	}));
	return [
		"你是 OneTree 的「课程大纲智能体」。后端已经确定了章节结构与教材来源绑定，你只负责为每个学生端章节起中文教学标题、写说明和知识点。",
		"规则：",
		"1. 调用 submit_outline_naming 提交，sections 必须覆盖下面列出的每一个 section_id，不能多也不能少。",
		"2. title、description、key_knowledge_points 全部使用自然的简体中文教学表达。",
		"3. 不得直接复制英文教材标题，也不得出现 sec_1_1 这类教材内部编号。",
		"4. 同一教材小节被拆成多个部分时，用不同的中文标题体现各部分内容的递进，不要重复。",
		"5. personalization_summary 用一两句话说明这份大纲如何贴合该学生的课程目标与节奏。",
		"6. 工具返回错误时按错误信息修正后重新提交；一次提交即可，不要输出长文。",
		`课程：${JSON.stringify(course.naming_context)}`,
		`教材：${course.source_textbook_title}`,
		`章节结构：\n${JSON.stringify(sections, null, 1)}`,
		`学生最新输入：${userText}`,
	].join("\n");
}

export function sectionTextsOf(params: any): Record<string, unknown> {
	const texts: Record<string, unknown> = {};
	for (const item of Array.isArray(params?.sections) ? params.sections : []) {
		const id = String(item?.section_id ?? "").trim();
		if (!id) continue;
		texts[id] = {
			title: item.title,
			description: item.description,
			key_knowledge_points: item.key_knowledge_points,
		};
	}
	return texts;
}

/** Name one course's sections with the model, validating through the backend. */
export async function nameCourseOutline(
	input: OutlineAgentInput,
	course: OutlineSourceCourse,
): Promise<Record<string, unknown>> {
	let outline: Record<string, unknown> | undefined;
	let failures = 0;
	let lastReason = "";

	const submit: AgentTool<any> = {
		name: "submit_outline_naming",
		label: "提交章节命名",
		description: "提交该课程每个章节的中文标题、说明与知识点；系统会校验并装配正式大纲。",
		parameters: NAMING_SCHEMA,
		async execute(_id, params: any) {
			const fail = (message: string): AgentToolResult<unknown> => {
				failures += 1;
				lastReason = message;
				if (failures > MAX_NAMING_CORRECTIONS) {
					return text("多次修正后仍未通过，已停止。", { terminate: true, isError: true });
				}
				return text(`章节命名未通过，请修正后重新提交：\n- ${message}`, { isError: true });
			};
			try {
				({ outline } = await input.backend.composeOutline(input.userUid, course, {
					personalization_summary: params?.personalization_summary,
					section_texts: sectionTextsOf(params),
				}));
			} catch (error) {
				if (error instanceof BackendBusinessError && error.status === 422) return fail(error.detail);
				throw error;
			}
			return text("大纲已装配。", { terminate: true });
		},
	};

	await runAgent({
		handle: input.handle,
		systemPrompt: buildNamingPrompt(course, input.userText),
		tools: [submit],
		history: [],
		userText: "请为这门课程的章节命名并提交。",
		signal: input.signal,
		shouldStop: () => outline !== undefined || failures > MAX_NAMING_CORRECTIONS,
		maxTurns: MAX_NAMING_CORRECTIONS + 3,
	});
	if (!outline) throw new Error(lastReason || "模型未提交章节命名");
	return outline;
}

/** Run `worker` over `items` with at most `limit` in flight, preserving result order. */
export async function mapWithConcurrency<T, R>(
	items: T[],
	limit: number,
	worker: (item: T, index: number) => Promise<R>,
): Promise<R[]> {
	const results = new Array<R>(items.length);
	let next = 0;
	const lanes = Array.from({ length: Math.max(1, Math.min(limit, items.length)) }, async () => {
		for (;;) {
			const index = next++;
			if (index >= items.length) return;
			results[index] = await worker(items[index]!, index);
		}
	});
	await Promise.all(lanes);
	return results;
}

function textbookSummary(outlines: Record<string, unknown>[], courses: OutlineSourceCourse[]): string {
	const lines: string[] = [];
	for (const outline of outlines) {
		const source = courses.find((c) => c.course_node_id === outline.course_id);
		const sections = Array.isArray(outline.sections) ? (outline.sections as Array<Record<string, unknown>>) : [];
		const titles = sections
			.filter((s) => s.depth === 2)
			.map((s) => String(s.title ?? "").trim())
			.filter(Boolean);
		if (!source?.source_textbook_title) continue;
		const limit = 8;
		const shown = titles
			.slice(0, limit)
			.map((t) => `「${t}」`)
			.join("、");
		const tail = titles.length > limit ? `等共 ${titles.length} 个章节/小节` : "";
		lines.push(shown ? `教材《${source.source_textbook_title}》（运用了${shown}${tail}）` : `教材《${source.source_textbook_title}》`);
	}
	return lines.length > 0 ? `\n\n在生成大纲时，我主要运用了知识库中以下教材及内容：\n- ${lines.join("\n- ")}` : "";
}

export function outlineSummaryText(
	outlines: Record<string, unknown>[],
	courses: OutlineSourceCourse[],
	failures: OutlineFailure[],
	allGrade: boolean,
): string {
	const refs = textbookSummary(outlines, courses);
	let head: string;
	if (outlines.length === 0) {
		head = "";
	} else if (allGrade && outlines.length + failures.length > 1) {
		head = `本年级 ${outlines.length} 门课程的章节大纲已生成。`;
	} else {
		const name = String(outlines[0]?.course_name ?? "").trim();
		const summary = String(outlines[0]?.personalization_summary ?? "").trim();
		head = [`课程大纲已生成：《${name}》`, summary].filter(Boolean).join("，") + "。";
	}
	const failureText =
		failures.length > 0
			? `\n\n以下课程大纲生成失败：${failures.map((f) => `《${f.courseName}》`).join("、")}。已生成的大纲不受影响，你可以说“单独补生成《${failures[0]!.courseName}》大纲”来重试。`
			: "";
	return `${head}${refs}${failureText}`.trim();
}

export async function runOutlineAgent(input: OutlineAgentInput): Promise<OutlineOutcome> {
	let context;
	try {
		context = await input.backend.getOutlineSourceContext(input.userUid, input.courseRef);
	} catch (error) {
		// Unknown course, no path, textbook not visible: nothing may reach the model.
		if (error instanceof BackendBusinessError && error.status === 422) return { kind: "blocked", text: error.detail };
		throw error;
	}
	const allGrade = input.courseRef.trim() === ALL_CURRENT_GRADE;
	const total = context.courses.length;
	const outlines: Record<string, unknown>[] = [];
	const failures: OutlineFailure[] = [];
	let done = 0;

	await mapWithConcurrency(context.courses, input.concurrency ?? DEFAULT_OUTLINE_CONCURRENCY, async (course) => {
		try {
			outlines.push(await nameCourseOutline(input, course));
			done += 1;
			input.emitProgress(`已完成《${course.course_name}》大纲（${done}/${total}）`);
		} catch (error) {
			// An expired model authorisation fails every course the same way: surface it as such.
			if (error instanceof GatewayError && error.errorCode === "MODEL_OAUTH_EXPIRED") throw error;
			if (input.signal?.aborted) throw error;
			done += 1;
			failures.push({ courseName: course.course_name, reason: error instanceof Error ? error.message : String(error) });
			input.emitProgress(`《${course.course_name}》大纲生成失败（${done}/${total}）`);
		}
	});

	if (outlines.length === 0) {
		return {
			kind: "failed",
			text: `课程大纲生成失败：${failures.map((f) => `《${f.courseName}》`).join("、")}。请稍后重试。`,
		};
	}
	// Keep path order regardless of which lane finished first.
	const order = new Map(context.courses.map((c, i) => [c.course_node_id, i]));
	outlines.sort((a, b) => (order.get(String(a.course_id)) ?? 0) - (order.get(String(b.course_id)) ?? 0));
	try {
		const saved = await input.backend.saveOutlines(input.userUid, context.path_fingerprints, outlines);
		return {
			kind: "generated",
			text: outlineSummaryText(outlines, context.courses, failures, allGrade),
			savedCourseIds: saved.saved_course_ids,
			failures,
			gradeYear: context.grade_year,
		};
	} catch (error) {
		if (error instanceof BackendBusinessError && error.status === 409) return { kind: "path_changed", text: PATH_CHANGED_TEXT };
		throw error;
	}
}
