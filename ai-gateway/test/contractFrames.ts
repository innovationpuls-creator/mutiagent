import { modelNotConfigured } from "../src/errors.js";
import {
	HEARTBEAT_FRAME,
	SSE_EVENT_NAMES,
	type SseEventName,
	errorEventFromGatewayError,
	formatSseEvent,
} from "../src/sse.js";

export const PAYLOADS: Record<SseEventName, Record<string, unknown>> = {
	session_started: { session_id: "s-1" },
	supervisor_thinking: { message: "正在分析你的需求..." },
	supervisor_plan: { agent: "profile_agent", label: "画像智能体", reason: "调用 画像智能体" },
	agent_calling: { agent: "profile_agent", label: "画像智能体", args: "{}" },
	agent_progress: { stepId: "s1", agent: "profile_agent", message: "处理中" },
	agent_result: { agent: "profile_agent", success: true, summary: "完成" },
	text_chunk: { chunk: "你好，世界\n第二行" },
	data_update: { update_type: "profile", years: ["大一"] },
	message_completed: { full_text: "你好，世界\n第二行" },
	session_completed: { session_id: "s-1", has_profile: true, has_paths: false, has_outline: false },
	error: errorEventFromGatewayError(modelNotConfigured()),
};

/** Golden contract frames; the frontend parseSseChunk test reads the same file. */
export function buildContractFrames(): string {
	return (
		SSE_EVENT_NAMES.map((n) => formatSseEvent(n, PAYLOADS[n])).join(HEARTBEAT_FRAME) + HEARTBEAT_FRAME
	);
}

