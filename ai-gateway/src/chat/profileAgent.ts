import type { AgentTool, AgentToolResult } from "@earendil-works/pi-agent-core";
import { arr, bool, obj, opt, str } from "@earendil-works/pi-schema";
import type { HistoryMessage } from "../backendClient.js";
import type { AgentStreamHandle } from "../models/runtime.js";
import { runAgent } from "./agentRunner.js";
import {
	CONFIRMED_KEYS,
	CORE_DEFAULTS,
	CORE_KEYS,
	type ConfirmedInfo,
	type ConfirmedKey,
	FIELD_QUESTIONS,
	FREE_TEXT_OPTION,
	type ProfileOption,
	SECONDARY_DEFAULTS,
	SECONDARY_KEYS,
	UNKNOWN_VALUE,
	allowsDefaultFill,
	buildBasicProfile,
	buildCollectingProfile,
	draftFromProfile,
	isSupportedGrade,
	mergeConfirmed,
	missingCoreKeys,
	missingKeys,
	nextQuestionCard,
	normalizeConfirmed,
	unsupportedGradeMessage,
} from "./profileContract.js";

/** The student may be re-asked / corrected at most this many times within one turn. */
export const MAX_SELF_CORRECTIONS = 2;

export interface ProfileOutcome {
	profile: Record<string, unknown>;
	/** The text the frontend matches against `profile.text` / `profile.summary_text`. */
	text: string;
	kind: "collecting" | "basic_profile";
	/** Patch to merge into session_state (null deletes). */
	statePatch: Record<string, unknown>;
	selfCorrections: number;
	usedFallback: boolean;
}

export interface ProfileAgentInput {
	handle: AgentStreamHandle;
	history: HistoryMessage[];
	userText: string;
	imageDataUrl?: string | null;
	existingProfile: Record<string, unknown> | null;
	pendingFollowup: unknown;
	signal?: AbortSignal;
	savePersisted: (profile: Record<string, unknown>) => Promise<void>;
	emitProgress: (message: string) => void;
}

const EDITABLE_PARTIAL = Object.fromEntries(
	CONFIRMED_KEYS.map((key) => [key, opt(key === "content_preference" ? arr(str()) : str())]),
);

function toolResult(text: string, extra: Partial<AgentToolResult<unknown>> = {}): AgentToolResult<unknown> {
	return { content: [{ type: "text", text }], details: undefined, ...extra };
}

function sanitizeOptions(raw: unknown, field: ConfirmedKey | undefined): ProfileOption[] {
	if (!Array.isArray(raw)) return [];
	const options: ProfileOption[] = [];
	for (const item of raw.slice(0, 6)) {
		if (!item || typeof item !== "object") continue;
		const record = item as Record<string, unknown>;
		const label = typeof record.label === "string" ? record.label.trim() : "";
		if (!label) continue;
		const value = typeof record.value === "string" && record.value.trim() ? record.value.trim() : label;
		const description = typeof record.description === "string" ? record.description.trim() : "";
		options.push({
			label,
			value,
			description,
			target_fields: field ? [field] : [],
			fills: field ? { [field]: field === "content_preference" ? [value] : value } : {},
		});
	}
	return options.length > 0 ? [...options, FREE_TEXT_OPTION] : [];
}

function isKey(value: unknown): value is ConfirmedKey {
	return typeof value === "string" && (CONFIRMED_KEYS as readonly string[]).includes(value);
}

function keyList(raw: unknown): ConfirmedKey[] {
	return Array.isArray(raw) ? [...new Set(raw.filter(isKey))] : [];
}

export function buildProfileSystemPrompt(input: {
	draft: ConfirmedInfo;
	defaultsAllowed: boolean;
	pendingFollowup: unknown;
	weaknessNote: string;
}): string {
	return [
		"你是 OneTree 学习平台的「画像智能体」，负责通过自然对话为大学生建立学习画像。",
		"你只能通过两个工具推进：",
		"- ask_profile_question：本轮信息还不够时，保存已提取到的字段，并向学生提出【一个】追问。",
		"- save_student_profile：16 个字段全部确认后，保存完整画像。",
		"",
		"规则：",
		"1. 每一轮必须以调用且仅调用一个工具结束，不要只回复文字。",
		"2. 只记录学生真实表达过的信息，不得编造；学生没说的字段不要写进 partial_confirmed。",
		`3. 核心字段（${CORE_KEYS.join("、")}）必须来自学生的真实表达；次要字段（${SECONDARY_KEYS.join("、")}）学生未提及时可以合理推断，但必须在 defaulted_fields 中列出。`,
		"4. 年级只支持：大一、大二、大三、大四（写成这四个词之一）。研究生、大五、高中等不在范围内——不要保存这类年级，改调 ask_profile_question 礼貌说明并请学生确认本科年级。",
		"5. 追问尽量针对缺口最大的核心字段；对有标准选项的字段，把 field 设为该字段名，系统会提供标准选项，不要自己编选项。",
		`6. 只有学生明确要求“按默认/快速生成/不用问了”时，才可将 use_defaults 设为 true；${
			input.defaultsAllowed
				? "本轮学生【已经】提出了这样的要求，可以对缺失字段使用默认值（并在 defaulted_fields 中列出）。"
				: "本轮学生【没有】提出这样的要求，use_defaults 必须为 false。"
		}`,
		"7. 工具返回错误时，按错误原因修正后重试；无法修正就改为向学生追问。",
		"8. 回复语言：简体中文，语气友好简洁。",
		"",
		`当前已记录的画像草稿（空字符串/空数组表示还未确认）：\n${JSON.stringify(input.draft, null, 2)}`,
		input.pendingFollowup
			? `上一轮的待回答追问：${JSON.stringify(input.pendingFollowup)}`
			: "",
		input.weaknessNote,
	]
		.filter((line) => line !== "")
		.join("\n");
}

export async function runProfileAgent(input: ProfileAgentInput): Promise<ProfileOutcome> {
	const defaultsAllowed = allowsDefaultFill(input.userText);
	let draft = draftFromProfile(input.existingProfile);
	let outcome: ProfileOutcome | undefined;
	let corrections = 0;

	const record = (value: ProfileOutcome) => {
		outcome = value;
	};

	const askTool: AgentTool<any> = {
		name: "ask_profile_question",
		label: "追问画像信息",
		description:
			"保存本轮提取到的画像字段并向学生提出一个追问（需要学生点选或输入）。信息不足、年级不合法、或需要澄清时调用。",
		parameters: obj({
			partial_confirmed: obj(EDITABLE_PARTIAL, { open: false }),
			missing_fields: opt(arr(str())),
			question_md: str(),
			field: opt(str()),
			options: opt(
				arr(obj({ label: str(), value: opt(str()), description: opt(str()) })),
			),
		}),
		async execute(_id, params: any): Promise<AgentToolResult<unknown>> {
			const incoming = normalizeConfirmed(params.partial_confirmed);
			let merged = mergeConfirmed(draft, incoming);
			const grade = String(merged.current_grade ?? "").trim();
			// Never persist an unsupported grade; replace the model's question with the
			// deterministic grade prompt so the student always sees the real reason.
			if (grade && !isSupportedGrade(grade)) {
				merged = { ...merged, current_grade: "" };
				const card = nextQuestionCard({ ...merged, current_grade: grade });
				return finishCollecting(card.confirmed_info, card.question_md, card.question_box.options, card.stage, ["current_grade"]);
			}
			const rawField: unknown = params.field;
			const field = isKey(rawField) ? rawField : undefined;
			const preset = field ? FIELD_QUESTIONS[field] : undefined;
			const customOptions = sanitizeOptions(params.options, field);
			const options = customOptions.length > 0 ? customOptions : (preset?.options ?? []);
			const question = String(params.question_md ?? "").trim() || preset?.question || "请补充一下画像信息。";
			const stage = !merged.current_grade || !merged.major ? "basic_info" : (preset?.stage ?? "learning_preference");
			return finishCollecting(merged, question, options, stage, Array.isArray(params.missing_fields) ? params.missing_fields : []);
		},
	};

	function finishCollecting(
		confirmed: ConfirmedInfo,
		question: string,
		options: ProfileOption[],
		stage: string,
		missing: string[],
	): AgentToolResult<unknown> {
		const profile = buildCollectingProfile({ confirmed, questionMd: question, options, stage });
		draft = confirmed;
		record({
			profile: profile as unknown as Record<string, unknown>,
			text: profile.text,
			kind: "collecting",
			statePatch: { pending_profile_followup: { missing_fields: missing, question } },
			selfCorrections: corrections,
			usedFallback: false,
		});
		return toolResult("已向学生提出追问，等待学生回复。", { terminate: true });
	}

	const saveTool: AgentTool<any> = {
		name: "save_student_profile",
		label: "保存学习画像",
		description:
			"16 个字段全部确认后保存完整画像。字段缺失、年级不在大一~大四、核心字段无来源时会返回错误，请按错误修正。",
		parameters: obj({
			// Fields stay optional at the schema level: our validator names exactly what is missing.
			confirmed_info: obj(EDITABLE_PARTIAL),
			summary_text: str(),
			use_defaults: opt(bool()),
			defaulted_fields: opt(arr(str())),
		}),
		async execute(_id, params: any): Promise<AgentToolResult<unknown>> {
			const fail = (reason: string): AgentToolResult<unknown> => {
				corrections += 1;
				return toolResult(reason, { isError: true });
			};
			const confirmed = mergeConfirmed(draft, params.confirmed_info);
			// Keep whatever the student really told us even if this save is rejected.
			draft = confirmed;
			const defaulted = keyList(params.defaulted_fields);
			if (!isSupportedGrade(confirmed.current_grade)) {
				return fail(
					`current_grade「${confirmed.current_grade || "空"}」不在支持范围（只支持 大一、大二、大三、大四）。请调用 ask_profile_question 向学生确认本科年级，不要保存。`,
				);
			}
			if (params.use_defaults === true && !defaultsAllowed) {
				return fail("学生本轮没有要求使用默认值，use_defaults 必须为 false。请改为追问缺失字段。");
			}
			const useDefaults = params.use_defaults === true && defaultsAllowed;
			const coreDefaulted = defaulted.filter((key) => CORE_KEYS.includes(key));
			if (coreDefaulted.length > 0 && !useDefaults) {
				return fail(
					`核心字段 ${coreDefaulted.join("、")} 必须来自学生的真实表达，不能标记为默认。请调用 ask_profile_question 追问。`,
				);
			}
			// Fill what the student asked us to default; only secondary fields otherwise.
			const filled = { ...confirmed };
			const autoDefaulted = new Set<string>(defaulted);
			if (useDefaults) {
				for (const key of missingKeys(filled)) {
					const fallback = key in CORE_DEFAULTS ? CORE_DEFAULTS[key] : SECONDARY_DEFAULTS[key];
					if (key === "current_grade" || key === "major" || fallback === undefined) continue;
					(filled as Record<string, unknown>)[key] = fallback;
					autoDefaulted.add(key);
				}
			}
			const stillMissing = missingKeys(filled);
			if (stillMissing.length > 0) {
				const coreMissing = missingCoreKeys(filled);
				return fail(
					`以下字段仍为空或未知：${stillMissing.join("、")}。${
						coreMissing.length > 0
							? `其中核心字段 ${coreMissing.join("、")} 请调用 ask_profile_question 向学生追问。`
							: "次要字段可以根据对话合理推断并列入 defaulted_fields，或继续追问。"
					}`,
				);
			}
			if (Object.values(filled).some((value) => value === UNKNOWN_VALUE)) {
				return fail(`字段值不能是「${UNKNOWN_VALUE}」。`);
			}
			const summary = String(params.summary_text ?? "").trim();
			if (!summary) return fail("summary_text 不能为空，请用一两句话总结学生画像。");
			// Secondary fields the model inferred without the student saying so.
			const defaultedFields = [...autoDefaulted].filter((key) => !CORE_KEYS.includes(key as ConfirmedKey) || useDefaults);
			const profile = buildBasicProfile({ confirmed: filled, defaulted: defaultedFields, summary });
			draft = filled;
			record({
				profile: profile as unknown as Record<string, unknown>,
				text: profile.summary_text,
				kind: "basic_profile",
				statePatch: { pending_profile_followup: null },
				selfCorrections: corrections,
				usedFallback: false,
			});
			return toolResult("画像已保存。", { terminate: true });
		},
	};

	await runAgent({
		handle: input.handle,
		systemPrompt: buildProfileSystemPrompt({
			draft,
			defaultsAllowed,
			pendingFollowup: input.pendingFollowup,
			weaknessNote: weaknessNote(input.existingProfile),
		}),
		tools: [askTool, saveTool],
		history: input.history,
		userText: input.userText,
		imageDataUrl: input.imageDataUrl,
		signal: input.signal,
		onToolStart: (name) => input.emitProgress(name === "save_student_profile" ? "正在校验并保存学习画像" : "正在整理需要向你确认的信息"),
		shouldStop: () => outcome !== undefined || corrections > MAX_SELF_CORRECTIONS,
	});

	const result: ProfileOutcome =
		outcome ??
		fallbackOutcome(draft, corrections);
	await input.savePersisted(result.profile);
	return result;
}

/** The model produced no valid terminal tool call (or exhausted its corrections). */
function fallbackOutcome(draft: ConfirmedInfo, corrections: number): ProfileOutcome {
	const card = nextQuestionCard(draft);
	return {
		profile: card as unknown as Record<string, unknown>,
		text: card.text,
		kind: "collecting",
		statePatch: { pending_profile_followup: { missing_fields: missingCoreKeys(card.confirmed_info), question: card.text } },
		selfCorrections: corrections,
		usedFallback: true,
	};
}

function weaknessNote(profile: Record<string, unknown> | null): string {
	const confirmed = profile?.confirmed_info as Record<string, unknown> | undefined;
	const weaknesses = typeof confirmed?.weaknesses === "string" ? confirmed.weaknesses : "";
	return weaknesses.includes("[Adaptive Weaknesses]")
		? `学生近期测验暴露的薄弱点（供参考，不要直接当作学生自述）：${weaknesses}`
		: "";
}

export { unsupportedGradeMessage };
