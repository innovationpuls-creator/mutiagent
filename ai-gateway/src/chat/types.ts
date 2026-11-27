import type { SseEventName, SsePayload } from "../sse.js";

export type Emit = (event: SseEventName, payload?: SsePayload) => void;

/** What nodes write through `config.writer`; the route turns it into SSE frames. */
export type GraphChunk =
	| { kind: "event"; event: SseEventName; payload: SsePayload }
	/** Pre-formatted SSE bytes forwarded verbatim (legacy bridge). */
	| { kind: "raw"; frames: string };
