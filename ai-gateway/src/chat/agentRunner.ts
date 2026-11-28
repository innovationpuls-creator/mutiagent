import { Agent, type AgentMessage, type AgentTool } from "@earendil-works/pi-agent-core";
import type { AssistantMessage, ImageContent, Message, UserMessage } from "@earendil-works/pi-ai";
import type { HistoryMessage } from "../backendClient.js";
import { modelCapabilityMismatch, modelOAuthExpired, upstreamModelError } from "../errors.js";
import type { AgentStreamHandle } from "../models/runtime.js";

const MAX_HISTORY_MESSAGES = 24;
/** Hard bound on model<->tool round trips within one graph node. */
export const MAX_AGENT_TURNS = 8;

const ZERO_USAGE = {
	input: 0,
	output: 0,
	cacheRead: 0,
	cacheWrite: 0,
	totalTokens: 0,
	cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 },
};

/** Parse `data:image/png;base64,...` into Pi image content; anything else is ignored. */
export function parseImageDataUrl(dataUrl: string | null | undefined): ImageContent | undefined {
	if (!dataUrl) return undefined;
	const match = /^data:(image\/[A-Za-z0-9.+-]+);base64,(.+)$/s.exec(dataUrl);
	if (!match?.[1] || !match[2]) return undefined;
	return { type: "image", data: match[2], mimeType: match[1] };
}

function modelAcceptsImages(handle: AgentStreamHandle): boolean {
	const input = (handle.model as { input?: string[] }).input;
	return Array.isArray(input) && input.includes("image");
}

export function userMessage(
	handle: AgentStreamHandle,
	text: string,
	imageDataUrl?: string | null,
): UserMessage {
	const image = modelAcceptsImages(handle) ? parseImageDataUrl(imageDataUrl) : undefined;
	return {
		role: "user",
		content: image ? [{ type: "text", text }, image] : text,
		timestamp: Date.now(),
	};
}

/** Past turns are plain text; assistant turns are rebuilt as completed messages. */
export function historyToMessages(handle: AgentStreamHandle, history: HistoryMessage[]): Message[] {
	const model = handle.model as unknown as { api: string; provider: string; id: string };
	return history.slice(-MAX_HISTORY_MESSAGES).map((entry): Message => {
		if (entry.role === "user") {
			return { role: "user", content: entry.content, timestamp: Date.now() };
		}
		return {
			role: "assistant",
			content: [{ type: "text", text: entry.content }],
			api: model.api,
			provider: model.provider,
			model: model.id,
			usage: ZERO_USAGE,
			stopReason: "stop",
			timestamp: Date.now(),
		} as unknown as AssistantMessage;
	});
}

export interface AgentRunInput {
	handle: AgentStreamHandle;
	systemPrompt: string;
	tools: AgentTool<any>[];
	history: HistoryMessage[];
	userText: string;
	imageDataUrl?: string | null;
	signal?: AbortSignal;
	onTextDelta?: (delta: string) => void;
	onToolStart?: (toolName: string, args: unknown) => void;
	onToolEnd?: (toolName: string, result: unknown, isError: boolean) => void;
	/** Stop the loop once the caller already has what it needs (e.g. a terminal tool ran). */
	shouldStop?: () => boolean;
	maxTurns?: number;
}

export interface AgentRunResult {
	/** Text of the final assistant message (after its last tool call), "" if none. */
	text: string;
}

/** Raise a typed gateway error when the model call itself failed. */
function assertNoModelFailure(handle: AgentStreamHandle, messages: AgentMessage[]): void {
	const last = [...messages].reverse().find((m) => (m as { role?: string }).role === "assistant") as
		| AssistantMessage
		| undefined;
	if (!last || (last.stopReason !== "error" && last.stopReason !== "aborted")) return;
	const failure = handle.lastFailure;
	if (failure?.kind === "oauth") throw modelOAuthExpired(failure.provider);
	throw upstreamModelError(`模型调用失败：${(last.errorMessage ?? failure?.message ?? "未知错误").slice(0, 200)}`);
}

export async function runAgent(input: AgentRunInput): Promise<AgentRunResult> {
	// Every agent works through tools; failing fast beats looping on a model that cannot call them.
	if (input.tools.length > 0 && input.handle.supportsTools === false) {
		throw modelCapabilityMismatch(`当前模型（${(input.handle.model as { id?: string }).id ?? "未知"}）在“模型配置”里被标记为不支持工具调用，而这项功能需要工具调用。请换一个支持工具调用的模型。`);
	}
	let turns = 0;
	const agent = new Agent({
		initialState: {
			systemPrompt: input.systemPrompt,
			model: input.handle.model,
			thinkingLevel: "off",
			tools: input.tools,
			messages: historyToMessages(input.handle, input.history),
		},
		streamFn: input.handle.streamFn,
		toolExecution: "sequential",
		finishTurn: () => {
			turns += 1;
			return input.shouldStop?.() || turns >= (input.maxTurns ?? MAX_AGENT_TURNS) ? { action: "end" } : undefined;
		},
	});

	const onAbort = () => agent.abort();
	input.signal?.addEventListener("abort", onAbort, { once: true });

	agent.subscribe((event) => {
		if (event.type === "message_update" && event.assistantMessageEvent.type === "text_delta") {
			input.onTextDelta?.(event.assistantMessageEvent.delta);
		} else if (event.type === "tool_execution_start") {
			input.onToolStart?.(event.toolName, event.args);
		} else if (event.type === "tool_execution_end") {
			input.onToolEnd?.(event.toolName, event.result, event.isError);
		}
	});

	try {
		await agent.prompt(userMessage(input.handle, input.userText, input.imageDataUrl) as AgentMessage);
		await agent.waitForIdle();
	} finally {
		input.signal?.removeEventListener("abort", onAbort);
	}

	const messages = agent.state.messages;
	// A tool-terminated turn legitimately ends on a toolResult; only judge model failures.
	assertNoModelFailure(input.handle, messages);
	const last = messages[messages.length - 1] as { role?: string; content?: unknown } | undefined;
	let text = "";
	if (last?.role === "assistant" && Array.isArray(last.content)) {
		text = (last.content as Array<{ type: string; text?: string }>)
			.filter((part) => part.type === "text")
			.map((part) => part.text ?? "")
			.join("");
	}
	return { text };
}
