import { Hono } from "hono";
import { type AuthVariables, jwtAuth } from "../auth.js";
import type { BackendClient } from "../backendClient.js";
import { GatewayError } from "../errors.js";
import type { ModelRuntime } from "../models/runtime.js";
import type { Logger } from "../observability.js";
import {
	createSseResponse,
	errorEventFromGatewayError,
	errorEventPayload,
} from "../sse.js";
import { type ChatGraphDeps, buildChatGraph } from "./graph.js";
import type { GraphChunk } from "./types.js";

const MAX_MESSAGE_CHARS = 4000;
const MAX_SESSION_ID_CHARS = 80;

export interface ChatRouteDeps {
	jwtSecret: string;
	backend: BackendClient;
	runtime: ModelRuntime;
	logger: Logger;
	heartbeatMs: number;
}

interface ChatBody {
	session_id: string;
	message: string;
	image_attachment: string | null;
}

async function parseBody(request: Request): Promise<ChatBody> {
	let raw: unknown;
	try {
		raw = await request.json();
	} catch {
		throw new GatewayError(422, undefined, "请求体必须是 JSON");
	}
	const body = (raw && typeof raw === "object" ? raw : {}) as Record<string, unknown>;
	const sessionId = body.session_id;
	const message = body.message;
	if (typeof sessionId !== "string" || sessionId.length < 1 || sessionId.length > MAX_SESSION_ID_CHARS) {
		throw new GatewayError(422, undefined, "session_id 无效");
	}
	if (typeof message !== "string" || message.length < 1 || message.length > MAX_MESSAGE_CHARS) {
		throw new GatewayError(422, undefined, `message 长度需在 1-${MAX_MESSAGE_CHARS} 之间`);
	}
	const image = body.image_attachment;
	if (image !== undefined && image !== null && typeof image !== "string") {
		throw new GatewayError(422, undefined, "image_attachment 无效");
	}
	return { session_id: sessionId, message, image_attachment: (image as string | null | undefined) ?? null };
}

/** `POST /api/chat/message` — same path, auth and SSE contract as the Python route it replaces. */
export function chatRoutes(deps: ChatRouteDeps) {
	const app = new Hono<{ Variables: AuthVariables }>();

	app.post("/message", jwtAuth(deps.jwtSecret, deps.backend), async (c) => {
		const { userUid } = c.get("auth");
		const body = await parseBody(c.req.raw);
		// Same pre-flight as before: unknown/foreign session is an HTTP 404, not an SSE error.
		const context = await deps.backend.getChatContext(body.session_id, userUid);

		return createSseResponse(
			async (writer) => {
				const progress: ChatGraphDeps["progress"] = { bridged: false, persisted: false };
				const graph = buildChatGraph({
					backend: deps.backend,
					runtime: deps.runtime,
					logger: deps.logger,
					userUid,
					sessionId: body.session_id,
					query: body.message,
					imageAttachment: body.image_attachment,
					signal: writer.signal,
					progress,
				});
				try {
					const stream = await graph.stream(
						{ context },
						{ streamMode: "custom", signal: writer.signal },
					);
					for await (const chunk of stream as AsyncIterable<GraphChunk>) {
						if (writer.closed) break;
						if (chunk.kind === "raw") writer.sendRaw(chunk.frames);
						else writer.send(chunk.event, chunk.payload);
					}
				} catch (error) {
					if (writer.closed || writer.signal.aborted) return;
					await reportFailure(error, body, userUid, progress, deps, writer);
				}
			},
			{
				heartbeatMs: deps.heartbeatMs,
				onError: () => errorEventPayload({ message: "对话请求失败，请稍后重试。" }),
			},
		);
	});

	return app;
}

async function reportFailure(
	error: unknown,
	body: ChatBody,
	userUid: string,
	progress: ChatGraphDeps["progress"],
	deps: ChatRouteDeps,
	writer: { send: (name: "error", payload: Record<string, unknown>) => void },
): Promise<void> {
	if (error instanceof GatewayError) {
		writer.send("error", errorEventFromGatewayError(error));
	} else {
		deps.logger.error(`chat_stream_failed name=${error instanceof Error ? error.name : "unknown"}`);
		writer.send("error", errorEventPayload({ message: "对话请求失败，请稍后重试。" }));
	}
	// Nothing was handled for an unconfigured model, and the legacy bridge persists on
	// its own; for every other failure keep what the student typed (never an empty AI row).
	const skipPersist =
		progress.bridged ||
		progress.persisted ||
		(error instanceof GatewayError && error.errorCode === "MODEL_NOT_CONFIGURED");
	if (skipPersist) return;
	try {
		await deps.backend.persistTurn(body.session_id, userUid, {
			user_message: body.message,
			image_attachment: body.image_attachment,
		});
	} catch {
		deps.logger.warn("chat_user_message_fallback_persist_failed");
	}
}
