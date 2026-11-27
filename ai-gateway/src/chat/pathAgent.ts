import type { AgentTool, AgentToolResult } from "@earendil-works/pi-agent-core";
import { arr, obj, opt, str } from "@earendil-works/pi-schema";
import type { BackendClient, ChatContext, RawProgressSnapshot } from "../backendClient.js";
import { BackendBusinessError } from "../errors.js";
import type { AgentStreamHandle } from "../models/runtime.js";
import { runAgent } from "./agentRunner.js";
import { type IntakeDraft, MAX_COURSES, MIN_COURSES } from "./intakeContract.js";

/** One in-place repair of the lightweight plan; the contract itself is assembled by the backend. */
export const MAX_PLAN_CORRECTIONS = 1;
export const PATH_FAILED_TEXT = "学习路径生成失败，请重试生成学习路径。你已确认的课程草稿仍然保留。";

const SPEC_SCHEMA = obj({
	theme: str(),
	semester_scope: str(),
	duration: str(),
	pace_reason: str(),
	goal: str(),
	stage_titles: arr(str()),
	key_points: arr(str()),
	difficult_points: arr(str()),
	acceptance_criteria: arr(str()),
	difficulty_level: str(),
});

const PLAN_SCHEMA = obj({
	goal_type: str(),
	grade_goal: str(),
	desired_outcome: str(),
	four_year_outcome: str(),
	current_focus: str(),
	next_action: str(),
	course_specs: arr(SPEC_SCHEMA),
	specific_requirements: opt(str()),
});

export type PathOutcome =
	| { kind: "generated"; gradeYear: string; path: Record<string, unknown>; text: string }
	| { kind: "failed"; text: string; reason: string };

export interface PathAgentInput {
	handle: AgentStreamHandle;
	backend: BackendClient;
	userUid: string;
	context: ChatContext;
	intake: IntakeDraft;
	userText: string;
	signal?: AbortSignal;
	emitProgress: (message: string) => void;
}

function text(value: string, extra: Partial<AgentToolResult<unknown>> = {}): AgentToolResult<unknown> {
	return { content: [{ type: "text", text: value }], details: undefined, ...extra };
}

export function formatSnapshots(snapshots: RawProgressSnapshot[]): string {
	if (snapshots.length === 0) return "已有学习路径完成度摘要：无历史数据。";
	const lines = snapshots.map((snapshot) => {
		const extras = [
			snapshot.current_course_id ? `当前课程 ${snapshot.current_course_id}` : "",
			snapshot.current_progress_state ? `当前状态 ${snapshot.current_progress_state}` : "",
			snapshot.next_course_id ? `下一门 ${snapshot.next_course_id}` : "",
		].filter(Boolean);
		const head = `${snapshot.grade_year}：共 ${snapshot.total_courses} 门课程，已完成 ${snapshot.completed_courses} 门`;
		return extras.length > 0 ? `${head}，${extras.join("，")}` : head;
	});
	return ["已有学习路径完成度摘要：", ...lines].join("\n");
}

export function validatePlan(plan: any, intake: IntakeDraft): string[] {
	const errors: string[] = [];
	const specs = Array.isArray(plan?.course_specs) ? plan.course_specs : [];
	if (specs.length < MIN_COURSES || specs.length > MAX_COURSES) {
		errors.push(`course_specs 数量必须在 ${MIN_COURSES}-${MAX_COURSES} 门之间。`);
	}
	if (specs.length !== intake.courses.length) {
		errors.push(
			`course_specs 数量必须与已确认课程草案一致：草案有 ${intake.courses.length} 门，你给了 ${specs.length} 门（按草案顺序一一对应）。`,
		);
	}
	specs.forEach((spec: any, index: number) => {
		const label = `第 ${index + 1} 门课（${intake.courses[index]?.title ?? "?"}）`;
		const clean = (value: unknown) => (Array.isArray(value) ? value.map((v) => String(v).trim()).filter(Boolean) : []);
		if (!String(spec?.goal ?? "").trim()) errors.push(`${label}缺少 goal。`);
		if (clean(spec?.stage_titles).length < 3) errors.push(`${label}的 stage_titles 至少 3 个。`);
		if (clean(spec?.key_points).length < 3) errors.push(`${label}的 key_points 至少 3 个。`);
		if (clean(spec?.difficult_points).length < 1) errors.push(`${label}的 difficult_points 至少 1 个。`);
		if (clean(spec?.acceptance_criteria).length < 1) errors.push(`${label}的 acceptance_criteria 至少 1 个。`);
	});
	return errors;
}

export function pathSummaryText(path: Record<string, unknown>): string {
	const current = path.current_learning_course as Record<string, unknown> | undefined;
	const theme = String(current?.course_or_chapter_theme ?? "").trim();
	const next = String(current?.next_action ?? "").trim();
	if (!current) return "学习路径已生成。";
	const clauses = ["学习路径已生成"];
	if (theme) clauses.push(`当前建议先学习《${theme}》`);
	if (next) clauses.push(`下一步：${next}`);
	return `${clauses.join("，")}。`;
}

export function buildPathPrompt(input: PathAgentInput, snapshots: RawProgressSnapshot[]): string {
	const { intake } = input;
	return [
		"你是 OneTree 的「学习路径智能体」。你只做轻量的教学规划，最终的路径图谱、章节节点与契约字段由系统程序装配，你不需要输出它们。",
		`请为 ${intake.grade_year}（${intake.grade_name}）规划「${intake.learning_topic}」的学年学习路径，并调用 submit_learning_path_plan 提交。`,
		"规则：",
		"1. course_specs 必须与已确认课程草案一一对应：数量相同、顺序相同；每门课给出学期范围、预计周期、节奏理由、课程目标、阶段标题（≥3）、核心知识点（≥3）、重难点（≥1）、验收标准（≥1）和难度等级（入门/基础/中级/高级）。",
		"2. 课程标题与教材来源由系统按草案回填，你不要更改课程方向，也不要增删课程。",
		"3. 如果已有学习进度，要在其基础上延续，不要让学生从第一门课重新开始。",
		"4. 工具返回错误时按错误信息修正后重新提交。",
		"5. 一次提交即可，不要输出自然语言长文。",
		`已确认课程草案：\n${intake.courses.map((c, i) => `${i + 1}. ${c.title}：${c.purpose}`).join("\n")}`,
		`学生画像：${JSON.stringify(input.context.profile?.confirmed_info ?? {})}`,
		`学习主题：${intake.learning_topic}`,
		formatSnapshots(snapshots),
		`学生最新输入：${input.userText}`,
	].join("\n");
}

export async function runPathAgent(input: PathAgentInput): Promise<PathOutcome> {
	const { backend, intake } = input;
	const snapshots = await backend.getProgressSnapshots(input.userUid);
	let outcome: PathOutcome | undefined;
	let failures = 0;
	let lastReason = "";

	const submit: AgentTool<any> = {
		name: "submit_learning_path_plan",
		label: "提交学习路径规划",
		description: "提交轻量学习路径规划（与课程草案一一对应的 course_specs）。系统会装配并保存正式路径。",
		parameters: PLAN_SCHEMA,
		async execute(_id, params: any) {
			const fail = (message: string): AgentToolResult<unknown> => {
				failures += 1;
				lastReason = message;
				if (failures > MAX_PLAN_CORRECTIONS) {
					outcome = { kind: "failed", text: PATH_FAILED_TEXT, reason: message };
					return text("多次修正后仍未通过，已停止。", { terminate: true, isError: true });
				}
				return text(`规划未通过，请修正后重新提交：\n- ${message}`, { isError: true });
			};

			const errors = validatePlan(params, intake);
			if (errors.length > 0) return fail(errors.join("\n- "));
			input.emitProgress("正在装配学习路径图谱与契约");
			let pathData: Record<string, unknown>;
			try {
				({ path_data: pathData } = await backend.assembleLearningPath(input.userUid, intake.grade_year, {
					profile: input.context.profile ?? {},
					learning_topic: intake.learning_topic,
					plan: params,
					intake_courses: intake.courses,
				}));
			} catch (error) {
				if (error instanceof BackendBusinessError && error.status === 422) return fail(error.detail);
				throw error;
			}
			await backend.saveYearLearningPath(input.userUid, intake.grade_year, intake.learning_topic, pathData);
			outcome = {
				kind: "generated",
				gradeYear: intake.grade_year,
				path: pathData,
				text: pathSummaryText(pathData),
			};
			return text("学习路径已保存。", { terminate: true });
		},
	};

	await runAgent({
		handle: input.handle,
		systemPrompt: buildPathPrompt(input, snapshots),
		tools: [submit],
		history: [],
		userText: "请规划并提交学习路径。",
		signal: input.signal,
		shouldStop: () => outcome !== undefined,
		maxTurns: MAX_PLAN_CORRECTIONS + 3,
	});

	return outcome ?? { kind: "failed", text: PATH_FAILED_TEXT, reason: lastReason || "模型未提交规划" };
}
