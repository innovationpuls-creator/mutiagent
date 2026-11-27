import { Annotation, Command, END, START, StateGraph } from "@langchain/langgraph";
import type { LangGraphRunnableConfig } from "@langchain/langgraph";
import type { BackendClient, ChatContext, LearningOverview } from "../backendClient.js";
import type { Logger } from "../observability.js";
import type { AgentStreamHandle, ModelRuntime } from "../models/runtime.js";
import type { SseEventName, SsePayload } from "../sse.js";
import { type IntakeDraft, readIntake } from "./intakeContract.js";
import { runIntakeAgent } from "./intakeAgent.js";
import { runOutlineAgent } from "./outlineAgent.js";
import { runPathAgent } from "./pathAgent.js";
import { parseLeafResourceRequest, readPendingRegeneration, runResourceAgent } from "./resourceAgent.js";
import { runProfileAgent } from "./profileAgent.js";
import { isCompleteProfile } from "./profileContract.js";
import { type Handoff, runSupervisor, stageOf } from "./supervisor.js";
import type { Emit, GraphChunk } from "./types.js";

export const LEAF_RESOURCE_MARKER = "[LEAF_RESOURCE_GENERATION]";
const FALLBACK_ANSWER = "我暂时没能给出有效回复，请换个说法再试一次。";

export interface ChatGraphDeps {
	backend: BackendClient;
	runtime: ModelRuntime;
	logger: Logger;
	userUid: string;
	sessionId: string;
	query: string;
	imageAttachment: string | null;
	signal?: AbortSignal;
	/** Set by nodes so the route knows what to do when the stream fails midway. */
	progress: { bridged: boolean; persisted: boolean };
}

export interface ChatFailure {
	agent: string;
	label: string;
	message: string;
	retryAction?: string;
	extra?: Record<string, unknown>;
}

export interface ResourceRequest {
	courseId: string;
	chapterRef: string;
	mode: "generate" | "regenerate";
	focus: string;
	/** The request came from a pending-regeneration answer, which must be cleared either way. */
	fromPending: boolean;
}

const last = <T>() => ({ reducer: (_: T, next: T) => next });

const ChatState = Annotation.Root({
	context: Annotation<ChatContext>(last<ChatContext>()),
	response: Annotation<string>({ ...last<string>(), default: () => "" }),
	statePatch: Annotation<Record<string, unknown> | null>({ ...last<Record<string, unknown> | null>(), default: () => null }),
	hasProfile: Annotation<boolean>({ ...last<boolean>(), default: () => false }),
	handoff: Annotation<Handoff | null>({ ...last<Handoff | null>(), default: () => null }),
	/** Set when a confirmed draft flows into the path node within the same request. */
	confirmedIntake: Annotation<IntakeDraft | null>({ ...last<IntakeDraft | null>(), default: () => null }),
	pathGenerated: Annotation<boolean>({ ...last<boolean>(), default: () => false }),
	outlineGenerated: Annotation<boolean>({ ...last<boolean>(), default: () => false }),
	/** Failure to surface as an SSE error after the turn is persisted. */
	failure: Annotation<ChatFailure | null>({ ...last<ChatFailure | null>(), default: () => null }),
	resourceRequest: Annotation<ResourceRequest | null>({ ...last<ResourceRequest | null>(), default: () => null }),
});
type State = typeof ChatState.State;

function writerOf(config: LangGraphRunnableConfig): Emit {
	return (event: SseEventName, payload: SsePayload = {}) => {
		const chunk: GraphChunk = { kind: "event", event, payload };
		config.writer?.(chunk);
	};
}

function memoryEvent(stepId: string, message: string, success?: boolean): SsePayload {
	const event: SsePayload = {
		stepId,
		kind: "memory_loader",
		agent: "memory_loader",
		label: "记忆提取",
		message,
	};
	if (success !== undefined) {
		event.success = success;
		event.summary = message;
	}
	return event;
}

/** Only explicit protocol actions skip the supervisor (no keyword interception). */
export function explicitResourceRequest(query: string, sessionState: Record<string, unknown>): ResourceRequest | null {
	const parsed = parseLeafResourceRequest(query);
	if (parsed) {
		return {
			courseId: parsed.courseNodeId,
			chapterRef: parsed.chapterSectionId,
			mode: parsed.mode,
			focus: parsed.mode === "regenerate" ? query : "",
			fromPending: Boolean(sessionState.pending_leaf_regeneration),
		};
	}
	const pending = readPendingRegeneration(sessionState.pending_leaf_regeneration);
	if (!pending) return null;
	return {
		courseId: pending.course_node_id,
		chapterRef: pending.chapter_section_id,
		mode: "regenerate",
		focus: query,
		fromPending: true,
	};
}

export function buildChatGraph(deps: ChatGraphDeps) {
	let handle: AgentStreamHandle | undefined;
	let pathHandle: AgentStreamHandle | undefined;
	let overview: Promise<LearningOverview> | undefined;
	const getOverview = () => (overview ??= deps.backend.getLearningOverview(deps.userUid));

	async function entry(state: State, config: LangGraphRunnableConfig) {
		const emit = writerOf(config);
		const { context } = state;
		const resourceRequest = explicitResourceRequest(deps.query, context.session_state);
		if (resourceRequest) {
			// The button protocol and a pending-regeneration answer skip the supervisor, never a keyword guess.
			emit("session_started", { session_id: deps.sessionId, query: deps.query });
			handle = await deps.runtime.agentStream(deps.userUid, "path_outline");
			return new Command({ goto: "resource_agent", update: { resourceRequest } });
		}
		emit("session_started", { session_id: deps.sessionId, query: deps.query });
		for (const [id, label] of [
			["memory-history-load", "历史对话记录"],
			["memory-profile-load", "用户画像数据"],
			["memory-path-load", "学习路径数据"],
			["memory-outline-load", "课程大纲数据"],
		] as const) {
			emit("agent_calling", memoryEvent(id, `正在读取${label}`));
			emit("agent_result", memoryEvent(id, `${label}已装入本轮上下文`, true));
		}
		emit("agent_result", memoryEvent("memory-context-load", "历史对话、用户画像、学习路径与课程大纲已完成状态组装", true));
		// Unconfigured model: stop before the supervisor, nothing is written.
		handle = await deps.runtime.agentStream(deps.userUid, "chat_profile");
		return new Command({ goto: "supervisor" });
	}

	async function supervisor(state: State, config: LangGraphRunnableConfig) {
		const emit = writerOf(config);
		const { context } = state;
		if (context.profile) emit("data_update", { update_type: "profile_loaded", summary: "已加载历史学习画像" });
		if (context.year_learning_paths) {
			const years = Object.keys(context.year_learning_paths);
			emit("data_update", { update_type: "paths_loaded", years, summary: `已加载 ${years.length} 个年级的学习路径` });
		}
		const result = await runSupervisor({
			handle: handle!,
			context,
			userText: deps.query,
			imageDataUrl: deps.imageAttachment,
			signal: deps.signal,
			emit,
			getOverview,
		});
		if (result.kind === "handoff") {
			const { handoff } = result;
			const agent =
				handoff.kind === "profile_agent"
					? "profile_agent"
					: handoff.kind === "intake"
						? "learning_path_intake"
						: handoff.kind === "outline"
							? "course_knowledge"
							: "course_resources";
			emit("supervisor_plan", { agent, label: AGENT_LABELS[agent] ?? agent, reason: handoff.reason || `调用 ${AGENT_LABELS[agent] ?? agent}` });
			const goto =
				handoff.kind === "profile_agent"
					? "profile_agent"
					: handoff.kind === "intake"
						? "intake_agent"
						: handoff.kind === "outline"
							? "outline_agent"
							: "resource_agent";
			const courseId = String(context.course_knowledge?.course_id ?? "");
			const resourceRequest: ResourceRequest | null =
				handoff.kind === "resources"
					? { courseId, chapterRef: handoff.chapterRef, mode: "generate", focus: "", fromPending: false }
					: null;
			return new Command({ goto, update: { handoff, resourceRequest } });
		}
		return new Command({ goto: "finalize", update: { response: result.text || FALLBACK_ANSWER } });
	}

	async function profileAgent(state: State, config: LangGraphRunnableConfig) {
		const emit = writerOf(config);
		const stepId = "profile-agent";
		emit("agent_calling", { stepId, kind: "agent", agent: "profile_agent", label: "画像智能体", message: "正在整理你的学习画像" });
		const outcome = await runProfileAgent({
			handle: handle!,
			history: state.context.history,
			userText: deps.query,
			imageDataUrl: deps.imageAttachment,
			existingProfile: state.context.profile,
			pendingFollowup: state.context.session_state.pending_profile_followup,
			signal: deps.signal,
			emitProgress: (message) => emit("agent_progress", { stepId, agent: "profile_agent", message }),
			savePersisted: (profile) => deps.backend.putStudentProfile(deps.userUid, profile),
		});
		emit("data_update", {
			update_type: outcome.kind === "basic_profile" ? "profile_saved" : "profile_collecting",
			summary: outcome.kind === "basic_profile" ? "学习画像已保存" : "已记录画像草稿，等待学生补充",
		});
		emit("agent_result", { stepId, kind: "agent", agent: "profile_agent", label: "画像智能体", success: true, summary: outcome.kind === "basic_profile" ? "画像已生成" : "等待学生补充画像信息" });
		emit("text_chunk", { chunk: outcome.text });
		return new Command({
			goto: "finalize",
			update: {
				response: outcome.text,
				statePatch: outcome.statePatch,
				hasProfile: isCompleteProfile(outcome.profile),
			},
		});
	}

	async function intakeAgent(state: State, config: LangGraphRunnableConfig) {
		const emit = writerOf(config);
		const stepId = "learning-path-intake-agent";
		emit("agent_calling", { stepId, kind: "agent", agent: "learning_path_intake", label: "课程草案智能体", message: "正在处理课程草案" });
		pathHandle ??= await deps.runtime.agentStream(deps.userUid, "path_outline");
		const context = state.context;
		const overviewData = stageOf(context).hasPaths ? await getOverview() : null;
		const outcome = await runIntakeAgent({
			handle: pathHandle,
			backend: deps.backend,
			userUid: deps.userUid,
			context,
			userText: deps.query,
			imageDataUrl: deps.imageAttachment,
			pathText: overviewData?.path_text ?? "",
			signal: deps.signal,
			emitProgress: (message) => emit("agent_progress", { stepId, agent: "learning_path_intake", message }),
		});
		const done = (summary: string, success = true) =>
			emit("agent_result", { stepId, kind: "agent", agent: "learning_path_intake", label: "课程草案智能体", success, summary });

		if (outcome.kind === "confirmed") {
			// Same request, no hand-back to the student: draft node -> path node.
			done("课程草案已确认");
			return new Command({
				goto: "learning_path_agent",
				update: { confirmedIntake: outcome.draft, statePatch: { learning_path_intake: outcome.draft } },
			});
		}
		let patch: Record<string, unknown> | null = null;
		if (outcome.kind === "proposed" || outcome.kind === "cancelled") {
			patch = { learning_path_intake: outcome.draft };
			emit("data_update", {
				update_type: "learning_path_intake",
				summary: outcome.draft.status === "risk_pending" ? "课程草案待风险确认" : "课程草案已更新",
			});
		}
		if (outcome.kind === "no_textbook") {
			emit("data_update", { update_type: "knowledge_gap_recorded", gap_id: outcome.gapId, summary: `已登记知识缺口：${outcome.topic}` });
		}
		done(
			outcome.kind === "proposed" ? "课程草案已生成" : outcome.kind === "failed" ? "课程草案生成失败" : "已回复",
			outcome.kind !== "failed",
		);
		emit("text_chunk", { chunk: outcome.text });
		return new Command({ goto: "finalize", update: { response: outcome.text, statePatch: patch } });
	}

	async function learningPathAgent(state: State, config: LangGraphRunnableConfig) {
		const emit = writerOf(config);
		const stepId = "learning-path-agent";
		const intake = state.confirmedIntake ?? readIntake(state.context.session_state.learning_path_intake);
		if (!intake || intake.status !== "confirmed") {
			return new Command({ goto: "finalize", update: { response: "请先确认课程草案，再生成正式学习路径。" } });
		}
		emit("agent_calling", { stepId, kind: "agent", agent: "learning_path_agent", label: "学习路径智能体", message: "正在生成按年学习路径" });
		pathHandle ??= await deps.runtime.agentStream(deps.userUid, "path_outline");
		const outcome = await runPathAgent({
			handle: pathHandle,
			backend: deps.backend,
			userUid: deps.userUid,
			context: state.context,
			intake,
			userText: deps.query,
			signal: deps.signal,
			emitProgress: (message) => emit("agent_progress", { stepId, agent: "learning_path_agent", message }),
		});
		if (outcome.kind === "failed") {
			emit("agent_result", { stepId, kind: "agent", agent: "learning_path_agent", label: "学习路径智能体", success: false, summary: "学习路径生成失败" });
			// The confirmed draft stays in session_state so a retry only re-runs the path node.
			return new Command({
				goto: "finalize",
				update: {
					response: outcome.text,
					failure: { agent: "learning_path_agent", label: "学习路径智能体", message: outcome.text, retryAction: "retry_learning_path" },
				},
			});
		}
		emit("data_update", {
			update_type: "learning_path_generated",
			label: "学习路径",
			grade_year: outcome.gradeYear,
			years: [outcome.gradeYear],
			summary: "学习路径已保存",
		});
		emit("agent_result", { stepId, kind: "agent", agent: "learning_path_agent", label: "学习路径智能体", success: true, summary: "学习路径已生成" });
		emit("text_chunk", { chunk: outcome.text });
		return new Command({
			goto: "finalize",
			// The draft has served its purpose; later edits start a fresh one from the saved path.
			update: { response: outcome.text, statePatch: { learning_path_intake: null }, pathGenerated: true },
		});
	}

	async function outlineAgent(state: State, config: LangGraphRunnableConfig) {
		const emit = writerOf(config);
		const stepId = "course-knowledge-agent";
		const label = "课程大纲智能体";
		const courseRef = state.handoff?.kind === "outline" ? state.handoff.courseRef : "";
		emit("agent_calling", { stepId, kind: "agent", agent: "course_knowledge", label, message: "正在生成课程大纲" });
		pathHandle ??= await deps.runtime.agentStream(deps.userUid, "path_outline");
		const outcome = await runOutlineAgent({
			handle: pathHandle,
			backend: deps.backend,
			userUid: deps.userUid,
			courseRef,
			userText: deps.query,
			signal: deps.signal,
			emitProgress: (message) => emit("agent_progress", { stepId, agent: "course_knowledge", message }),
		});
		const ok = outcome.kind === "generated";
		emit("agent_result", {
			stepId,
			kind: "agent",
			agent: "course_knowledge",
			label,
			success: ok,
			summary: ok
				? outcome.failures.length > 0
					? `已生成 ${outcome.savedCourseIds.length} 门课程大纲，${outcome.failures.length} 门失败`
					: "课程大纲已生成"
				: "课程大纲未生成",
		});
		if (ok) {
			emit("data_update", {
				update_type: "course_knowledge_generated",
				label: "课程大纲",
				grade_year: outcome.gradeYear,
				course_ids: outcome.savedCourseIds,
				summary: "课程大纲已保存",
			});
		}
		emit("text_chunk", { chunk: outcome.text });
		return new Command({ goto: "finalize", update: { response: outcome.text, outlineGenerated: ok } });
	}

	async function resourceAgent(state: State, config: LangGraphRunnableConfig) {
		const emit = writerOf(config);
		const request = state.resourceRequest;
		const label = "课程资源智能体";
		if (!request || !request.courseId) {
			return new Command({
				goto: "finalize",
				update: { response: "请先生成课程大纲，再生成教学内容。", statePatch: request?.fromPending ? { pending_leaf_regeneration: null } : null },
			});
		}
		emit("agent_calling", { stepId: "course-resource-agent", kind: "agent", agent: "course_resources", label, message: "正在生成本章教学内容" });
		pathHandle ??= await deps.runtime.agentStream(deps.userUid, "path_outline");
		const outcome = await runResourceAgent({
			handle: pathHandle,
			backend: deps.backend,
			userUid: deps.userUid,
			courseId: request.courseId,
			chapterRef: request.chapterRef,
			mode: request.mode,
			regenerationFocus: request.focus,
			signal: deps.signal,
			emit,
		});
		const clear = request.fromPending ? { pending_leaf_regeneration: null } : null;
		emit("agent_result", {
			stepId: "course-resource-agent",
			kind: "agent",
			agent: "course_resources",
			label,
			success: outcome.kind === "completed",
			summary: outcome.kind === "completed" ? "本章教学内容已处理" : "本章教学内容未生成",
		});
		if (outcome.kind === "needs_focus") {
			// A focus question: remember it explicitly instead of hiding a tag in the reply text.
			const pending = { course_node_id: request.courseId, chapter_section_id: outcome.chapterSectionId, requested_at: new Date().toISOString() };
			emit("text_chunk", { chunk: outcome.text });
			return new Command({ goto: "finalize", update: { response: outcome.text, statePatch: { pending_leaf_regeneration: pending } } });
		}
		if (outcome.kind === "busy" || outcome.kind === "failed") {
			const chapter = outcome.kind === "failed" ? outcome.chapterSectionId : request.chapterRef;
			return new Command({
				goto: "finalize",
				update: {
					response: "",
					statePatch: clear,
					failure: {
						agent: "course_resources",
						label,
						message: outcome.text,
						extra: {
							course_id: request.courseId,
							chapter_section_id: chapter,
							kind: "course_resource_chapter",
							phase: "generation",
							status: "error",
						},
					},
				},
			});
		}
		emit("text_chunk", { chunk: outcome.text });
		return new Command({ goto: "finalize", update: { response: outcome.text, statePatch: clear, outlineGenerated: true } });
	}

	async function finalize(state: State, config: LangGraphRunnableConfig) {
		const emit = writerOf(config);
		const { context } = state;
		// Persist first; the frontend treats message_completed as "safe to refresh".
		await deps.backend.persistTurn(deps.sessionId, deps.userUid, {
			user_message: deps.query,
			image_attachment: deps.imageAttachment,
			assistant_message: state.response,
			session_state_patch: state.statePatch,
		});
		deps.progress.persisted = true;
		const info = stageOf(context);
		if (state.failure) {
			emit("error", {
				agent: state.failure.agent,
				label: state.failure.label,
				message: state.failure.message,
				recoverable: true,
				retryable: Boolean(state.failure.retryAction),
				...(state.failure.retryAction ? { retryAction: state.failure.retryAction } : {}),
				...state.failure.extra,
			});
			return {};
		}
		emit("message_completed", { full_text: state.response });
		emit("session_completed", {
			session_id: deps.sessionId,
			has_profile: state.hasProfile || info.hasProfile,
			has_paths: info.hasPaths || state.pathGenerated,
			has_outline: info.hasOutline || state.outlineGenerated,
		});
		return {};
	}

	return new StateGraph(ChatState)
		.addNode("entry", entry, { ends: ["supervisor", "resource_agent"] })
		.addNode("supervisor", supervisor, { ends: ["profile_agent", "intake_agent", "outline_agent", "resource_agent", "finalize"] })
		.addNode("profile_agent", profileAgent, { ends: ["finalize"] })
		.addNode("intake_agent", intakeAgent, { ends: ["learning_path_agent", "finalize"] })
		.addNode("learning_path_agent", learningPathAgent, { ends: ["finalize"] })
		.addNode("outline_agent", outlineAgent, { ends: ["finalize"] })
		.addNode("resource_agent", resourceAgent, { ends: ["finalize"] })
		.addNode("finalize", finalize)
		.addEdge(START, "entry")
		.addEdge("finalize", END)
		.compile();
}

const AGENT_LABELS: Record<string, string> = {
	profile_agent: "画像智能体",
	learning_path_intake: "课程草案智能体",
	course_knowledge: "课程大纲智能体",
	course_resources: "课程资源智能体",
};
