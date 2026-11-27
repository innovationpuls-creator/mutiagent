import { Annotation, Command, END, START, StateGraph } from "@langchain/langgraph";
import type { LangGraphRunnableConfig } from "@langchain/langgraph";
import type { BackendClient, ChatContext, LearningOverview } from "../backendClient.js";
import type { Logger } from "../observability.js";
import type { AgentStreamHandle, ModelRuntime } from "../models/runtime.js";
import type { SseEventName, SsePayload } from "../sse.js";
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

const last = <T>() => ({ reducer: (_: T, next: T) => next });

const ChatState = Annotation.Root({
	context: Annotation<ChatContext>(last<ChatContext>()),
	response: Annotation<string>({ ...last<string>(), default: () => "" }),
	statePatch: Annotation<Record<string, unknown> | null>({ ...last<Record<string, unknown> | null>(), default: () => null }),
	hasProfile: Annotation<boolean>({ ...last<boolean>(), default: () => false }),
	handoff: Annotation<Handoff | null>({ ...last<Handoff | null>(), default: () => null }),
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
export function isExplicitProtocolAction(query: string, sessionState: Record<string, unknown>): boolean {
	return query.includes(LEAF_RESOURCE_MARKER) || Boolean(sessionState.pending_leaf_regeneration);
}

export function buildChatGraph(deps: ChatGraphDeps) {
	let handle: AgentStreamHandle | undefined;
	let overview: Promise<LearningOverview> | undefined;
	const getOverview = () => (overview ??= deps.backend.getLearningOverview(deps.userUid));

	async function entry(state: State, config: LangGraphRunnableConfig) {
		const emit = writerOf(config);
		const { context } = state;
		if (isExplicitProtocolAction(deps.query, context.session_state)) {
			// Resource generation is migrated in M7; until then the legacy pipeline owns it.
			return new Command({
				goto: "legacy_bridge",
				update: { handoff: { kind: "legacy", target: "course_resources", reason: "显式资源生成协议" } satisfies Handoff },
			});
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
			const agent = handoff.kind === "profile_agent" ? "profile_agent" : handoff.target;
			emit("supervisor_plan", { agent, label: AGENT_LABELS[agent] ?? agent, reason: handoff.reason || `调用 ${AGENT_LABELS[agent] ?? agent}` });
			return new Command({
				goto: handoff.kind === "profile_agent" ? "profile_agent" : "legacy_bridge",
				update: { handoff },
			});
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

	async function legacyBridge(_state: State, config: LangGraphRunnableConfig) {
		deps.progress.bridged = true;
		const response = await deps.backend.openLegacyStream(
			deps.sessionId,
			deps.userUid,
			{ message: deps.query, image_attachment: deps.imageAttachment },
			deps.signal,
		);
		if (!response.body) return {};
		const decoder = new TextDecoder();
		const reader = response.body.getReader();
		try {
			for (;;) {
				const { done, value } = await reader.read();
				if (done) break;
				const frames = decoder.decode(value, { stream: true });
				if (frames) config.writer?.({ kind: "raw", frames } satisfies GraphChunk);
			}
		} finally {
			reader.releaseLock();
		}
		return {};
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
		emit("message_completed", { full_text: state.response });
		emit("session_completed", {
			session_id: deps.sessionId,
			has_profile: state.hasProfile || info.hasProfile,
			has_paths: info.hasPaths,
			has_outline: info.hasOutline,
		});
		return {};
	}

	return new StateGraph(ChatState)
		.addNode("entry", entry, { ends: ["supervisor", "legacy_bridge"] })
		.addNode("supervisor", supervisor, { ends: ["profile_agent", "legacy_bridge", "finalize"] })
		.addNode("profile_agent", profileAgent, { ends: ["finalize"] })
		.addNode("legacy_bridge", legacyBridge)
		.addNode("finalize", finalize)
		.addEdge(START, "entry")
		.addEdge("legacy_bridge", END)
		.addEdge("finalize", END)
		.compile();
}

const AGENT_LABELS: Record<string, string> = {
	profile_agent: "画像智能体",
	learning_path_intake: "课程草案智能体",
	course_knowledge: "课程大纲智能体",
	course_resources: "课程资源智能体",
};
