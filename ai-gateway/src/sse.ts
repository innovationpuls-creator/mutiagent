import type { ErrorCode, GatewayError } from "./errors.js";

/** The 11 event names the frontend `parseSseChunk` understands. */
export const SSE_EVENT_NAMES = [
	"session_started",
	"supervisor_thinking",
	"supervisor_plan",
	"agent_calling",
	"agent_progress",
	"agent_result",
	"text_chunk",
	"data_update",
	"message_completed",
	"session_completed",
	"error",
] as const;
export type SseEventName = (typeof SSE_EVENT_NAMES)[number];

/** Legacy backend wraps these as `event: message` with the real name in payload.type. */
const MESSAGE_WRAPPED: ReadonlySet<SseEventName> = new Set([
	"text_chunk",
	"supervisor_thinking",
	"supervisor_plan",
]);

export const SSE_HEADERS = {
	"Content-Type": "text/event-stream; charset=utf-8",
	"Cache-Control": "no-cache",
	"X-Accel-Buffering": "no",
} as const;

export const HEARTBEAT_FRAME = ": keep-alive\n\n";

export type SsePayload = Record<string, unknown>;

export function formatSseEvent(name: SseEventName, payload: SsePayload = {}): string {
	if (MESSAGE_WRAPPED.has(name)) {
		return `event: message\ndata: ${JSON.stringify({ ...payload, type: name })}\n\n`;
	}
	return `event: ${name}\ndata: ${JSON.stringify(payload)}\n\n`;
}

export interface ErrorEventInput {
	message: string;
	recoverable?: boolean;
	retryable?: boolean;
	errorCode?: ErrorCode;
	provider?: string;
	action?: string;
}

export function errorEventPayload(input: ErrorEventInput): SsePayload {
	const payload: SsePayload = {
		message: input.message,
		recoverable: input.recoverable ?? true,
		retryable: input.retryable ?? false,
	};
	if (input.errorCode) payload.error_code = input.errorCode;
	if (input.provider) payload.provider = input.provider;
	if (input.action) payload.action = input.action;
	return payload;
}

export function errorEventFromGatewayError(error: GatewayError): SsePayload {
	return errorEventPayload({
		message: error.detail,
		errorCode: error.errorCode,
		provider: error.extras.provider,
		action: error.extras.action,
		recoverable: error.status !== 503,
		retryable: error.status === 503,
	});
}

export interface SseWriter {
	send(name: SseEventName, payload?: SsePayload): void;
	readonly closed: boolean;
	readonly signal: AbortSignal;
}

export interface SseResponseOptions {
	heartbeatMs: number;
	/** Convert a producer failure into the final `error` event payload. */
	onError?: (error: unknown) => SsePayload;
}

/**
 * Build a streaming SSE Response. The producer pushes frames through the writer;
 * heartbeats keep proxies from idling the connection during long reasoning.
 */
export function createSseResponse(
	producer: (writer: SseWriter) => Promise<void>,
	options: SseResponseOptions,
): Response {
	const encoder = new TextEncoder();
	const abort = new AbortController();
	let closed = false;
	let timer: ReturnType<typeof setInterval> | undefined;

	const stream = new ReadableStream<Uint8Array>({
		start(controller) {
			const write = (frame: string) => {
				if (closed) return;
				controller.enqueue(encoder.encode(frame));
			};
			const finish = () => {
				if (closed) return;
				closed = true;
				if (timer) clearInterval(timer);
				controller.close();
			};
			const writer: SseWriter = {
				send: (name, payload) => write(formatSseEvent(name, payload)),
				get closed() {
					return closed;
				},
				signal: abort.signal,
			};
			timer = setInterval(() => write(HEARTBEAT_FRAME), options.heartbeatMs);
			timer.unref?.();
			void producer(writer)
				.catch((error: unknown) => {
					const payload = options.onError?.(error) ??
						errorEventPayload({ message: "对话请求失败，请稍后重试。" });
					write(formatSseEvent("error", payload));
				})
				.finally(finish);
		},
		cancel() {
			closed = true;
			if (timer) clearInterval(timer);
			abort.abort();
		},
	});

	return new Response(stream, { status: 200, headers: SSE_HEADERS });
}
