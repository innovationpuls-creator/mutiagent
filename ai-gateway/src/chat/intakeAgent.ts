import type { AgentTool, AgentToolResult } from "@earendil-works/pi-agent-core";
import { arr, obj, opt, str } from "@earendil-works/pi-schema";
import type { BackendClient, ChatContext, TextbookContext } from "../backendClient.js";
import type { AgentStreamHandle } from "../models/runtime.js";
import { runAgent } from "./agentRunner.js";
import {
	type IntakeDraft,
	buildDraft,
	catalogOf,
	catalogText,
	detectRisks,
	draftResponseText,
	intakeStatusOf,
	noTextbookText,
	readIntake,
	riskCancelledText,
	validateDraftCourses,
} from "./intakeContract.js";

/** Source-binding / schema failures the model may repair in-place within one turn. */
export const MAX_INTAKE_CORRECTIONS = 2;
export const INTAKE_FAILED_TEXT = "课程草案生成失败，请重试生成学习路径草案。你原有的草稿没有被改动。";

export type IntakeOutcome =
	| { kind: "proposed"; draft: IntakeDraft; text: string }
	| { kind: "confirmed"; draft: IntakeDraft }
	| { kind: "cancelled"; draft: IntakeDraft; text: string }
	| { kind: "answer"; text: string }
	| { kind: "no_textbook"; topic: string; gapId: string | null; text: string }
	| { kind: "failed"; text: string; corrections: number };

export interface IntakeAgentInput {
	handle: AgentStreamHandle;
	backend: BackendClient;
	userUid: string;
	context: ChatContext;
	userText: string;
	imageDataUrl?: string | null;
	pathText: string;
	signal?: AbortSignal;
	emitProgress: (message: string) => void;
}

const COURSE_SCHEMA = obj({
	title: str(),
	purpose: str(),
	source_textbook_id: str(),
	source_outline_section_ids: arr(str()),
});

const PROPOSE_SCHEMA = obj({
	learning_topic: str(),
	search_topic: opt(str()),
	courses: opt(arr(COURSE_SCHEMA)),
	recommendation_reasons: opt(arr(str())),
	user_modification_summary: opt(str()),
});

const EMPTY = obj({});

function text(value: string, extra: Partial<AgentToolResult<unknown>> = {}): AgentToolResult<unknown> {
	return { content: [{ type: "text", text: value }], details: undefined, ...extra };
}

export function toolNamesForStatus(status: ReturnType<typeof intakeStatusOf>): string[] {
	const names = ["propose_or_revise_draft"];
	if (status === "draft" || status === "confirmed") names.push("confirm_draft");
	if (status === "risk_pending") names.push("confirm_draft", "cancel_risk_revision");
	return names;
}

export function buildIntakePrompt(input: {
	context: ChatContext;
	intake: IntakeDraft | null;
	pathText: string;
}): string {
	const { context, intake } = input;
	const status = intakeStatusOf(intake);
	const confirmed = (context.profile?.confirmed_info ?? {}) as Record<string, unknown>;
	return [
		"你是 OneTree 的「课程草案智能体」。你根据学生画像，从知识库已发布教材中规划 4-8 门课程的草案，并处理学生对草案的确认、修改、取消与追问。",
		`当前草案状态：${status}（none=还没有草案；draft=待确认；risk_pending=修改会替换/删除已开始或已有大纲的课程，需要二次确认；confirmed=已确认）。`,
		"可用工具由当前状态决定，规则：",
		"1. 学生想要生成/调整课程（首次规划、增删换课、换主题）：调用 propose_or_revise_draft。先只传 learning_topic（和需要时的 search_topic）获取教材目录；拿到目录后，再次调用并带上完整的 courses。",
		"2. courses 里每门课的 source_textbook_id 与 source_outline_section_ids 必须逐字复制目录里出现的 ID（每门课 1-7 个小节），课程顺序就是学习先后顺序，purpose 要说明教材小节覆盖的具体学习边界。不允许编造教材或小节。",
		"3. 修改草案时 courses 要给出修改后的完整列表；没改动的课程保持原绑定不变。search_topic 用于检索新增方向的教材，缺省等于 learning_topic。",
		"4. 学生明确同意当前草案（或在风险提示后明确同意覆盖）：调用 confirm_draft。",
		"5. 仅 risk_pending 时：学生反悔、想保留原路径：调用 cancel_risk_revision。",
		"6. 学生只是追问（某门课难不难、为什么这样排、前置要求等）：直接用文字回答，不调用任何工具，不改动草案。",
		"7. 工具返回错误时，按错误信息逐项修正后再调用，不要重复同样的错误。",
		"8. 回答使用简体中文，简洁友好。",
		`学生画像：${JSON.stringify(confirmed)}`,
		`画像摘要：${String(context.profile?.summary_text ?? context.profile?.text ?? "")}`,
		intake ? `当前课程草案：${JSON.stringify(intake)}` : "当前还没有课程草案。",
		input.pathText ? `学生已有学习路径：\n${input.pathText}` : "",
	]
		.filter(Boolean)
		.join("\n");
}

export async function runIntakeAgent(input: IntakeAgentInput): Promise<IntakeOutcome> {
	const { context, backend } = input;
	const intake = readIntake(context.session_state.learning_path_intake);
	const status = intakeStatusOf(intake);
	const existingCourses = intake?.courses ?? [];
	const lookups: TextbookContext[] = [];
	let outcome: IntakeOutcome | undefined;
	let failures = 0;

	const propose: AgentTool<any> = {
		name: "propose_or_revise_draft",
		label: "生成/修改课程草案",
		description:
			"首次生成课程草案，或按学生意见增删换课/换主题修订草案。第一次调用只传 learning_topic 获取教材目录；之后带完整 courses 提交。",
		parameters: PROPOSE_SCHEMA,
		async execute(_id, params: any) {
			const topic = String(params?.learning_topic ?? "").trim();
			const searchTopic = String(params?.search_topic ?? "").trim() || topic;
			if (!topic) return text("缺少 learning_topic。", { isError: true });

			const looked = lookups.length === 0 || !params?.courses;
			if (looked) {
				input.emitProgress(`正在检索「${searchTopic}」的已发布教材目录`);
				const result = await backend.getTextbookContext(
					searchTopic,
					[input.userText, String(input.context.profile?.summary_text ?? "")].filter(Boolean).join("\n"),
				);
				if (result.textbooks.length === 0) {
					outcome = {
						kind: "no_textbook",
						topic: searchTopic,
						gapId: result.gap_id,
						text: noTextbookText(searchTopic, intake !== null),
					};
					return text(`知识库暂无「${searchTopic}」的已发布教材（gap_id=${result.gap_id}），已登记待办。`, {
						terminate: true,
					});
				}
				lookups.push(result);
				if (!params?.courses) {
					return text(
						`已发布教材目录如下，请只使用这些教材与小节 ID 组织 4-8 门课程，然后再次调用并带上 courses：\n\n${catalogText(result)}`,
					);
				}
			}

			const { courses, errors } = validateDraftCourses(params.courses, catalogOf(...lookups), existingCourses);
			if (errors.length > 0) {
				failures += 1;
				if (failures > MAX_INTAKE_CORRECTIONS) {
					outcome = { kind: "failed", text: INTAKE_FAILED_TEXT, corrections: failures - 1 };
					return text("多次校验仍未通过，已停止。", { terminate: true, isError: true });
				}
				return text(`课程草案校验未通过，请逐项修正后重新提交：\n- ${errors.join("\n- ")}`, { isError: true });
			}
			const risks = detectRisks(courses, await backend.getProtectedCourses(input.userUid));
			const draft = buildDraft({
				profile: context.profile,
				learningTopic: intake && !params?.learning_topic ? intake.learning_topic : topic,
				courses,
				reasons: Array.isArray(params.recommendation_reasons)
					? params.recommendation_reasons.map((r: unknown) => String(r).trim()).filter(Boolean)
					: [],
				modificationSummary: String(params.user_modification_summary ?? "").trim() || (intake ? input.userText : ""),
				risks,
			});
			outcome = { kind: "proposed", draft, text: draftResponseText(draft) };
			return text("草案已生成。", { terminate: true });
		},
	};

	const confirm: AgentTool<any> = {
		name: "confirm_draft",
		label: "确认课程草案",
		description: "学生明确同意当前草案（或在风险提示后明确同意覆盖）时调用。",
		parameters: EMPTY,
		async execute() {
			if (!intake) return text("当前没有草案可确认。", { isError: true });
			outcome = {
				kind: "confirmed",
				draft: { ...intake, status: "confirmed", requires_second_confirmation: false, risk_warnings: [] },
			};
			return text("草案已确认。", { terminate: true });
		},
	};

	const cancel: AgentTool<any> = {
		name: "cancel_risk_revision",
		label: "取消风险修改",
		description: "仅风险待确认时：学生反悔、决定保留原路径时调用，草案回到普通草稿状态。",
		parameters: EMPTY,
		async execute() {
			if (!intake) return text("当前没有草案。", { isError: true });
			const draft: IntakeDraft = { ...intake, status: "draft", requires_second_confirmation: false, risk_warnings: [] };
			outcome = { kind: "cancelled", draft, text: riskCancelledText(draft) };
			return text("已取消本次风险修改。", { terminate: true });
		},
	};

	const registry: Record<string, AgentTool<any>> = {
		propose_or_revise_draft: propose,
		confirm_draft: confirm,
		cancel_risk_revision: cancel,
	};
	const tools = toolNamesForStatus(status).map((name) => registry[name]!);

	const result = await runAgent({
		handle: input.handle,
		systemPrompt: buildIntakePrompt({ context, intake, pathText: input.pathText }),
		tools,
		history: context.history,
		userText: input.userText,
		imageDataUrl: input.imageDataUrl,
		signal: input.signal,
		shouldStop: () => outcome !== undefined,
	});

	if (outcome) return outcome;
	const answer = result.text.trim();
	return { kind: "answer", text: answer || "我暂时没能给出有效回复，请换个说法再试一次。" };
}
