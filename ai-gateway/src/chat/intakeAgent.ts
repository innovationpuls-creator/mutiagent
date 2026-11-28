import type { AgentTool, AgentToolResult } from "@earendil-works/pi-agent-core";
import { arr, int, obj, opt, str } from "@earendil-works/pi-schema";
import type { BackendClient, ChatContext, TextbookOutline } from "../backendClient.js";
import { BackendBusinessError } from "../errors.js";
import type { AgentStreamHandle } from "../models/runtime.js";
import { runAgent } from "./agentRunner.js";
import {
	type IntakeDraft,
	buildDraft,
	catalogOf,
	detectRisks,
	draftResponseText,
	intakeStatusOf,
	noTextbookText,
	outlineText,
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
	courses: arr(COURSE_SCHEMA),
	recommendation_reasons: opt(arr(str())),
	user_modification_summary: opt(str()),
});

/** Page sizes the model sees; large libraries are browsed, never dumped. */
const LIST_PAGE = 50;
const OUTLINE_PAGE = 120;
const LIST_SCHEMA = obj({ query: opt(str()), offset: opt(int()) });
const OUTLINE_SCHEMA = obj({ textbook_id: str(), offset: opt(int()) });
const MISSING_SCHEMA = obj({ topic: str() });

const EMPTY = obj({});

function text(value: string, extra: Partial<AgentToolResult<unknown>> = {}): AgentToolResult<unknown> {
	return { content: [{ type: "text", text: value }], details: undefined, ...extra };
}

export function toolNamesForStatus(status: ReturnType<typeof intakeStatusOf>): string[] {
	const names = ["list_textbooks", "get_textbook_outline", "report_missing_textbook", "propose_or_revise_draft"];
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
		"1. 学生想要生成/调整课程（首次规划、增删换课、换主题）：先用 list_textbooks 看知识库里有哪些已发布教材，自己判断哪些相关（教材可能是英文标题，别靠字面匹配），再用 get_textbook_outline 查看相关教材的小节目录，最后调用 propose_or_revise_draft 提交完整草案。",
		"2. courses 里每门课的 source_textbook_id 与 source_outline_section_ids 必须逐字复制你查看过的目录里出现的 ID（每门课 1-7 个小节，需连续），课程顺序就是学习先后顺序，purpose 要说明教材小节覆盖的具体学习边界。不允许编造教材或小节。",
		"3. 知识库里确实没有适合该方向的教材时，调用 report_missing_textbook 登记缺口（不要硬凑不相关的教材）。修改草案时 courses 要给出修改后的完整列表；没改动的课程保持原绑定不变。",
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
	const outlines = new Map<string, TextbookOutline>();
	let outcome: IntakeOutcome | undefined;
	let failures = 0;

	const listTextbooks: AgentTool<any> = {
		name: "list_textbooks",
		label: "查看已发布教材",
		description:
			"分页列出知识库里的已发布教材（id、标题、标签、简介、小节数）。由你判断哪些与学习方向相关；query 只是可选的关键词过滤（教材可能是英文标题，过滤没命中不代表没有，可不带 query 翻页浏览）。",
		parameters: LIST_SCHEMA,
		async execute(_id, params: any) {
			input.emitProgress("正在查看知识库已发布教材");
			const offset = Math.max(0, Math.trunc(params?.offset ?? 0));
			const page = await backend.listPublishedTextbooks({ query: String(params?.query ?? ""), offset, limit: LIST_PAGE });
			if (page.total === 0) return text(params?.query ? `没有教材命中「${params.query}」（可不带 query 浏览全部）。` : "知识库里还没有任何已发布教材。");
			const lines = page.textbooks.map((t) =>
				[
					`${t.textbook_id}｜${t.title}（${t.section_count} 个小节）`,
					t.tags.length > 0 ? `标签：${t.tags.join("、")}` : "",
					t.description ? `简介：${t.description}` : "",
				]
					.filter(Boolean)
					.join("｜"),
			);
			const end = offset + page.textbooks.length;
			const more = end < page.total ? `\n（共 ${page.total} 本，已显示 ${offset + 1}-${end}；用 offset=${end} 继续翻页）` : `\n（共 ${page.total} 本，已全部显示）`;
			return text(lines.join("\n") + more);
		},
	};

	const getOutline: AgentTool<any> = {
		name: "get_textbook_outline",
		label: "查看教材目录",
		description: "查看一本已发布教材的小节 ID 与标题（大书分页，用 offset 继续）；草案里引用的小节 ID 必须来自你看过的目录。",
		parameters: OUTLINE_SCHEMA,
		async execute(_id, params: any) {
			const textbookId = String(params?.textbook_id ?? "").trim();
			if (!textbookId) return text("缺少 textbook_id。", { isError: true });
			const offset = Math.max(0, Math.trunc(params?.offset ?? 0));
			try {
				const page = await backend.getTextbookOutline(textbookId, { offset, limit: OUTLINE_PAGE });
				// Pages of one textbook accumulate: every section the model has seen is citable.
				const seen = outlines.get(page.textbook_id);
				const known = new Map((seen?.sections ?? []).map((section) => [section.section_id, section]));
				for (const section of page.sections) known.set(section.section_id, section);
				outlines.set(page.textbook_id, { ...page, sections: [...known.values()] });
				const total = page.total ?? page.sections.length;
				const end = offset + page.sections.length;
				const tail = end < total ? `\n（共 ${total} 个小节，已显示 ${offset + 1}-${end}；用 offset=${end} 继续）` : "";
				return text(outlineText(page) + tail);
			} catch (error) {
				if (error instanceof BackendBusinessError && error.status === 404) {
					return text(`教材 ${textbookId} 不存在或未发布，请先用 list_textbooks 查看可用教材。`, { isError: true });
				}
				throw error;
			}
		},
	};

	const reportMissing: AgentTool<any> = {
		name: "report_missing_textbook",
		label: "登记教材缺口",
		description: "知识库里没有适合该学习方向的已发布教材时调用：登记知识缺口交给管理员补充，并告知学生。",
		parameters: MISSING_SCHEMA,
		async execute(_id, params: any) {
			const topic = String(params?.topic ?? "").trim();
			if (!topic) return text("缺少 topic。", { isError: true });
			const gapId = await backend.registerKnowledgeGap(
				topic,
				[input.userText, String(context.profile?.summary_text ?? "")].filter(Boolean).join("\n"),
			);
			outcome = { kind: "no_textbook", topic, gapId, text: noTextbookText(topic, intake !== null) };
			return text(`已登记知识缺口「${topic}」（gap_id=${gapId}）。`, { terminate: true });
		},
	};

	const propose: AgentTool<any> = {
		name: "propose_or_revise_draft",
		label: "生成/修改课程草案",
		description: "提交完整的课程草案（4-8 门课，每门绑定已查看过目录的教材小节）。系统会校验来源绑定，未通过会返回具体错误。",
		parameters: PROPOSE_SCHEMA,
		async execute(_id, params: any) {
			const topic = String(params?.learning_topic ?? "").trim();
			if (!topic) return text("缺少 learning_topic。", { isError: true });
			if (outlines.size === 0 && existingCourses.length === 0) {
				return text("还没有查看任何教材目录。请先用 list_textbooks / get_textbook_outline 选出教材与小节，再提交草案。", {
					isError: true,
				});
			}

			const { courses, errors } = validateDraftCourses(params.courses, catalogOf([...outlines.values()]), existingCourses);
			if (errors.length > 0) {
				failures += 1;
				if (failures > MAX_INTAKE_CORRECTIONS) {
					outcome = { kind: "failed", text: `${INTAKE_FAILED_TEXT}\n最后一次校验未通过的原因：${errors[0]}`, corrections: failures - 1 };
					return text("多次校验仍未通过，已停止。", { terminate: true, isError: true });
				}
				return text(`课程草案校验未通过，请逐项修正后重新提交：\n- ${errors.join("\n- ")}`, { isError: true });
			}
			const risks = detectRisks(courses, await backend.getProtectedCourses(input.userUid));
			const draft = buildDraft({
				profile: context.profile,
				learningTopic: topic,
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
		list_textbooks: listTextbooks,
		get_textbook_outline: getOutline,
		report_missing_textbook: reportMissing,
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
