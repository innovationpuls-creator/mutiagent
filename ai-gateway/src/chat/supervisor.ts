import type { AgentTool, AgentToolResult } from "@earendil-works/pi-agent-core";
import { obj, opt, str } from "@earendil-works/pi-schema";
import type { ChatContext, HistoryMessage, LearningOverview } from "../backendClient.js";
import type { AgentStreamHandle } from "../models/runtime.js";
import { runAgent } from "./agentRunner.js";
import { intakeStatusOf, readIntake } from "./intakeContract.js";
import { isCompleteProfile } from "./profileContract.js";
import type { Emit } from "./types.js";

export type Stage = "A" | "B" | "C";

export type Handoff =
	| { kind: "profile_agent"; reason: string }
	| { kind: "intake"; reason: string }
	/** Not migrated yet (M6-M7): the Python legacy pipeline still owns these. */
	| { kind: "legacy"; target: "course_knowledge" | "course_resources"; reason: string };

export interface StageInfo {
	stage: Stage;
	hasProfile: boolean;
	hasPaths: boolean;
	hasOutline: boolean;
}

export function stageOf(context: Pick<ChatContext, "profile" | "year_learning_paths" | "course_knowledge">): StageInfo {
	const hasProfile = isCompleteProfile(context.profile);
	const hasPaths = Boolean(context.year_learning_paths && Object.keys(context.year_learning_paths).length > 0);
	const hasOutline = Boolean(context.course_knowledge);
	// Stage B/C need a complete profile; paths without one cannot be acted on.
	const stage: Stage = !hasProfile ? "A" : hasPaths ? "C" : "B";
	return { stage, hasProfile, hasPaths, hasOutline };
}

/** Tool names a stage may use. Pure function: the gate is data, not prompt text. */
export function gatedToolNames(info: StageInfo): string[] {
	const names = ["delegate_profile_agent"];
	if (info.stage === "A") return names;
	names.push("delegate_learning_path_intake", "get_student_progress_summary");
	if (info.stage === "B") return names;
	names.push("get_learning_path", "get_course_outline", "delegate_course_knowledge");
	if (info.hasOutline) names.push("delegate_course_resources");
	return names;
}

const REASON = obj({ reason: opt(str()) });
const NO_ARGS = obj({});

const STAGE_HINT: Record<Stage, string> = {
	A: "学生还没有完整的学习画像。你本轮只能通过 delegate_profile_agent 推进（学生要路径/大纲/资源时，也先引导完善画像），或者直接回答简单的闲聊/学习问题。",
	B: "学生已有完整画像，但还没有按年学习路径。可以委派学习路径草案智能体，或查询进度，也可以直接回答学习问题。",
	C: "学生已有画像与学习路径。查询类问题请调用只读工具拿真实数据再回答；需要生成/调整时委派对应智能体。",
};

export function buildSupervisorPrompt(info: StageInfo, context: ChatContext): string {
	const followup = context.session_state.pending_profile_followup;
	const intakeStatus = intakeStatusOf(readIntake(context.session_state.learning_path_intake));
	return [
		"你是 OneTree 学习平台的「主管智能体」，面向大学生，帮助他们完成画像、学习路径、课程大纲与课程学习。",
		"原则：",
		"1. 只使用本轮提供的工具；没有对应工具的能力，说明需要先完成前置步骤并给出引导，绝不假装已经完成。",
		"2. 学生询问自己的学习进度/路径/大纲时，必须调用只读工具取真实数据，再用自然语言组织回答，不要凭记忆编造。",
		"3. 需要委派智能体时调用对应 delegate_* 工具即可，不要自己代写其产出；调用后本轮由该智能体接手。",
		"4. 普通学习问答直接回答，简洁、准确、友好，使用简体中文。",
		`当前阶段：${info.stage}。${STAGE_HINT[info.stage]}`,
		intakeStatus !== "none"
			? `注意：当前存在课程草案（状态 ${intakeStatus}）。学生对草案的任何回应——确认、修改、取消或追问某门课——都必须委派 delegate_learning_path_intake，不要自己回答或改动草案。`
			: "",
		followup ? `注意：上一轮正在向学生采集画像字段，待回答追问：${JSON.stringify(followup)}。学生若在回答它，请委派画像智能体。` : "",
	]
		.filter(Boolean)
		.join("\n");
}

export interface SupervisorInput {
	handle: AgentStreamHandle;
	context: ChatContext;
	userText: string;
	imageDataUrl?: string | null;
	signal?: AbortSignal;
	emit: Emit;
	getOverview: () => Promise<LearningOverview>;
}

export type SupervisorResult =
	| { kind: "answer"; text: string; stage: Stage; toolNames: string[] }
	| { kind: "handoff"; handoff: Handoff; stage: Stage; toolNames: string[] };

function text(value: string, extra: Partial<AgentToolResult<unknown>> = {}): AgentToolResult<unknown> {
	return { content: [{ type: "text", text: value }], details: undefined, ...extra };
}

export async function runSupervisor(input: SupervisorInput): Promise<SupervisorResult> {
	const info = stageOf(input.context);
	let handoff: Handoff | undefined;
	let step = 0;

	const delegate = (
		name: string,
		description: string,
		make: (reason: string) => Handoff,
	): AgentTool<any> => ({
		name,
		label: name,
		description,
		parameters: REASON,
		async execute(_id, params: any) {
			handoff = make(String(params?.reason ?? "").trim());
			return text("已委派，本轮由对应智能体接手。", { terminate: true });
		},
	});

	const readOnly = (
		name: string,
		label: string,
		description: string,
		load: () => Promise<{ body: string; update: Record<string, unknown> }>,
	): AgentTool<any> => ({
		name,
		label,
		description,
		parameters: NO_ARGS,
		async execute() {
			const stepId = `supervisor-tool-${name}-${++step}`;
			input.emit("agent_calling", { stepId, kind: "tool", agent: name, label, message: `正在${label}` });
			const { body, update } = await load();
			input.emit("data_update", update);
			input.emit("agent_result", { stepId, kind: "tool", agent: name, label, success: true, summary: `${label}完成` });
			return text(body);
		},
	});

	const registry: Record<string, AgentTool<any>> = {
		delegate_profile_agent: delegate(
			"delegate_profile_agent",
			"委派画像智能体：采集或更新学生的学习画像（年级、专业、目标、偏好等）。",
			(reason) => ({ kind: "profile_agent", reason }),
		),
		delegate_learning_path_intake: delegate(
			"delegate_learning_path_intake",
			"委派课程草案智能体：生成/修改/确认课程草案；草案确认后会在同一轮自动生成按年学习路径。学生想规划、调整课程或回应草案时调用。",
			(reason) => ({ kind: "intake", reason }),
		),
		delegate_course_knowledge: delegate(
			"delegate_course_knowledge",
			"委派课程大纲智能体：为学生当前课程生成或重新生成课程大纲。",
			(reason) => ({ kind: "legacy", target: "course_knowledge", reason }),
		),
		delegate_course_resources: delegate(
			"delegate_course_resources",
			"委派课程资源智能体：为已有大纲的章节生成教学文档、视频与动画资源。",
			(reason) => ({ kind: "legacy", target: "course_resources", reason }),
		),
		get_student_progress_summary: readOnly(
			"get_student_progress_summary",
			"查询学习进度",
			"只读：查询学生各年级的学习进度（已完成课程数、当前课程、下一门课程）。",
			async () => {
				const overview = await input.getOverview();
				const body = overview.has_paths
					? JSON.stringify({ latest_grade_year: overview.latest_grade_year, progress: overview.progress }, null, 2)
					: "学生还没有学习路径，因此没有学习进度。";
				return { body, update: { update_type: "progress_loaded", summary: "已查询学习进度" } };
			},
		),
		get_learning_path: readOnly(
			"get_learning_path",
			"读取学习路径",
			"只读：读取学生已生成的按年学习路径（每个年级有哪些课程）。",
			async () => {
				const overview = await input.getOverview();
				return {
					body: overview.path_text || "学生还没有学习路径。",
					update: {
						update_type: "learning_path_loaded",
						label: "学习路径",
						years: Object.keys(input.context.year_learning_paths ?? {}),
						summary: "已从数据库读取学习路径",
					},
				};
			},
		),
		get_course_outline: readOnly(
			"get_course_outline",
			"读取课程大纲",
			"只读：读取学生当前课程的大纲（章节、核心知识点、已生成资源）及下一步建议。",
			async () => {
				const overview = await input.getOverview();
				const knowledge = input.context.course_knowledge ?? {};
				return {
					body: overview.has_outline
						? `${overview.outline_text}\n\n${overview.next_step_text}`
						: "当前课程还没有生成大纲。",
					update: {
						update_type: "course_knowledge_loaded",
						label: "课程大纲",
						course_id: String(knowledge.course_id ?? ""),
						grade_year: String(knowledge.grade_year ?? ""),
						summary: "已从数据库读取课程大纲",
					},
				};
			},
		),
	};
	const toolNames = gatedToolNames(info);
	const tools = toolNames.map((name) => registry[name]!);

	input.emit("supervisor_thinking", { message: "正在分析你的需求..." });
	const history: HistoryMessage[] = input.context.history;
	const result = await runAgent({
		handle: input.handle,
		systemPrompt: buildSupervisorPrompt(info, input.context),
		tools,
		history,
		userText: input.userText,
		imageDataUrl: input.imageDataUrl,
		signal: input.signal,
		onTextDelta: (delta) => input.emit("text_chunk", { chunk: delta }),
		shouldStop: () => handoff !== undefined,
	});

	if (handoff) return { kind: "handoff", handoff, stage: info.stage, toolNames };
	return { kind: "answer", text: result.text.trim(), stage: info.stage, toolNames };
}
