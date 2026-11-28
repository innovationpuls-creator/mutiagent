import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiRequestError, AUTH_INVALID_EVENT } from "./http";
import {
	fetchSessionState,
	type SessionAgentEvent,
	SessionStreamError,
	startSession,
	streamSession,
} from "./orchestration";

function jsonResponse(status: number, body: unknown): Response {
	return new Response(JSON.stringify(body), {
		status,
		headers: { "Content-Type": "application/json" },
	});
}

function sseResponse(text: string): Response {
	const encoder = new TextEncoder();
	return new Response(
		new ReadableStream({
			start(controller) {
				controller.enqueue(encoder.encode(text));
				controller.close();
			},
		}),
		{ status: 200, headers: { "Content-Type": "text/event-stream" } },
	);
}

function sseErrorFrame(data: Record<string, unknown>): string {
	return `event: error\ndata: ${JSON.stringify(data)}\n\n`;
}

const NOT_CONFIGURED_BODY = {
	detail: "尚未配置可用的个人模型",
	error_code: "MODEL_NOT_CONFIGURED",
	action: "open_model_settings",
};
const OAUTH_EXPIRED_BODY = {
	detail: "模型授权已过期",
	error_code: "MODEL_OAUTH_EXPIRED",
	provider: "openai-codex",
};

describe("unified error codes (AC-7)", () => {
	const authInvalid = vi.fn();

	afterEach(() => {
		window.removeEventListener(AUTH_INVALID_EVENT, authInvalid);
		authInvalid.mockReset();
		vi.unstubAllGlobals();
	});

	function listen() {
		window.addEventListener(AUTH_INVALID_EVENT, authInvalid);
	}

	describe("non-streaming HTTP path", () => {
		it("surfaces 428 MODEL_NOT_CONFIGURED on requestChat errors", async () => {
			listen();
			vi.stubGlobal(
				"fetch",
				vi.fn().mockResolvedValue(jsonResponse(428, NOT_CONFIGURED_BODY)),
			);

			const error = await startSession("t", "hi").catch((e) => e);

			expect(error).toBeInstanceOf(ApiRequestError);
			expect(error.message).toBe("尚未配置可用的个人模型");
			expect(error.status).toBe(428);
			expect(error.errorCode).toBe("MODEL_NOT_CONFIGURED");
			expect(error.action).toBe("open_model_settings");
			expect(error.provider).toBeNull();
			expect(authInvalid).not.toHaveBeenCalled();
		});

		it("surfaces 401 MODEL_OAUTH_EXPIRED with provider and does not log out", async () => {
			listen();
			vi.stubGlobal(
				"fetch",
				vi.fn().mockResolvedValue(jsonResponse(401, OAUTH_EXPIRED_BODY)),
			);

			const error = await fetchSessionState("t", "s1").catch((e) => e);

			expect(error).toBeInstanceOf(ApiRequestError);
			expect(error.message).toBe("模型授权已过期");
			expect(error.status).toBe(401);
			expect(error.errorCode).toBe("MODEL_OAUTH_EXPIRED");
			expect(error.provider).toBe("openai-codex");
			expect(authInvalid).not.toHaveBeenCalled();
		});

		it("still logs out for 401 with the exact legacy detail", async () => {
			listen();
			vi.stubGlobal(
				"fetch",
				vi
					.fn()
					.mockResolvedValue(jsonResponse(401, { detail: "无效的认证凭证" })),
			);

			await expect(startSession("t", "hi")).rejects.toThrow("无效的认证凭证");
			expect(authInvalid).toHaveBeenCalledTimes(1);
		});

		it("logs out for a gateway 401 AUTH_INVALID carrying the exact detail", async () => {
			listen();
			vi.stubGlobal(
				"fetch",
				vi.fn().mockResolvedValue(
					jsonResponse(401, {
						detail: "无效的认证凭证",
						error_code: "AUTH_INVALID",
					}),
				),
			);

			const error = await startSession("t", "hi").catch((e) => e);

			expect(error.errorCode).toBe("AUTH_INVALID");
			expect(authInvalid).toHaveBeenCalledTimes(1);
		});

		it("does not log out for 401 AUTH_INVALID with a different detail", async () => {
			listen();
			vi.stubGlobal(
				"fetch",
				vi.fn().mockResolvedValue(
					jsonResponse(401, {
						detail: "其他原因",
						error_code: "AUTH_INVALID",
					}),
				),
			);

			await expect(startSession("t", "hi")).rejects.toThrow("其他原因");
			expect(authInvalid).not.toHaveBeenCalled();
		});

		it("ignores unknown error_code and legacy bodies without throwing", async () => {
			vi.stubGlobal(
				"fetch",
				vi
					.fn()
					.mockResolvedValueOnce(
						jsonResponse(500, { detail: "boom", error_code: "FUTURE_CODE" }),
					)
					.mockResolvedValueOnce(jsonResponse(500, { detail: "legacy" }))
					.mockResolvedValueOnce(new Response("not json", { status: 502 })),
			);

			const unknown = await startSession("t", "hi").catch((e) => e);
			expect(unknown.errorCode).toBeNull();
			expect(unknown.message).toBe("boom");

			const legacy = await startSession("t", "hi").catch((e) => e);
			expect(legacy.errorCode).toBeNull();
			expect(legacy.provider).toBeNull();
			expect(legacy.message).toBe("legacy");

			const garbage = await startSession("t", "hi").catch((e) => e);
			expect(garbage.errorCode).toBeNull();
			expect(garbage.message).toBe("对话请求失败，请稍后重试");
		});
	});

	describe("streamSession HTTP failure", () => {
		it("surfaces 428 MODEL_NOT_CONFIGURED on SessionStreamError", async () => {
			listen();
			vi.stubGlobal(
				"fetch",
				vi.fn().mockResolvedValue(jsonResponse(428, NOT_CONFIGURED_BODY)),
			);

			const error = await streamSession("t", "hi", "s1", vi.fn()).catch(
				(e) => e,
			);

			expect(error).toBeInstanceOf(SessionStreamError);
			expect(error.message).toBe("尚未配置可用的个人模型");
			expect(error.sessionId).toBe("s1");
			expect(error.errorCode).toBe("MODEL_NOT_CONFIGURED");
			expect(error.action).toBe("open_model_settings");
			expect(authInvalid).not.toHaveBeenCalled();
		});

		it("surfaces 401 MODEL_OAUTH_EXPIRED with provider on SessionStreamError", async () => {
			listen();
			vi.stubGlobal(
				"fetch",
				vi.fn().mockResolvedValue(jsonResponse(401, OAUTH_EXPIRED_BODY)),
			);

			const error = await streamSession("t", "hi", "s1", vi.fn()).catch(
				(e) => e,
			);

			expect(error).toBeInstanceOf(SessionStreamError);
			expect(error.errorCode).toBe("MODEL_OAUTH_EXPIRED");
			expect(error.provider).toBe("openai-codex");
			expect(authInvalid).not.toHaveBeenCalled();
		});

		it("keeps the old constructor signature working", () => {
			const error = new SessionStreamError("x", "s1");
			expect(error.errorCode).toBeNull();
			expect(error.provider).toBeNull();
			expect(error.action).toBeNull();
		});
	});

	describe("SSE error event", () => {
		async function runWithErrorFrame(data: Record<string, unknown>) {
			vi.stubGlobal(
				"fetch",
				vi.fn().mockResolvedValue(sseResponse(sseErrorFrame(data))),
			);
			const events: SessionAgentEvent[] = [];
			const error = await streamSession("t", "hi", "s1", (e) =>
				events.push(e),
			).catch((e) => e);
			return { error, events };
		}

		it("surfaces MODEL_NOT_CONFIGURED on SessionStreamError and onEvent", async () => {
			const { error, events } = await runWithErrorFrame({
				message: "尚未配置可用的个人模型",
				recoverable: false,
				retryable: false,
				error_code: "MODEL_NOT_CONFIGURED",
				action: "open_model_settings",
			});

			expect(error).toBeInstanceOf(SessionStreamError);
			expect(error.message).toBe("尚未配置可用的个人模型");
			expect(error.errorCode).toBe("MODEL_NOT_CONFIGURED");
			expect(error.action).toBe("open_model_settings");
			expect(events).toHaveLength(1);
			expect(events[0]).toMatchObject({
				event: "error",
				error_code: "MODEL_NOT_CONFIGURED",
				action: "open_model_settings",
				recoverable: false,
				retryable: false,
			});
		});

		it("surfaces MODEL_OAUTH_EXPIRED with provider", async () => {
			const { error, events } = await runWithErrorFrame({
				message: "模型授权已过期",
				recoverable: true,
				retryable: false,
				error_code: "MODEL_OAUTH_EXPIRED",
				provider: "openai-codex",
			});

			expect(error.errorCode).toBe("MODEL_OAUTH_EXPIRED");
			expect(error.provider).toBe("openai-codex");
			expect(events[0].error_code).toBe("MODEL_OAUTH_EXPIRED");
			expect(events[0].provider).toBe("openai-codex");
		});

		it("ignores an unknown error_code safely", async () => {
			const { error, events } = await runWithErrorFrame({
				message: "出错了",
				recoverable: true,
				retryable: true,
				error_code: "FUTURE_CODE",
				provider: "",
			});

			expect(error).toBeInstanceOf(SessionStreamError);
			expect(error.message).toBe("出错了");
			expect(error.errorCode).toBeNull();
			expect(error.provider).toBeNull();
			expect(events[0].error_code).toBeUndefined();
			expect(events[0].provider).toBeUndefined();
		});

		it("legacy SSE error events without error_code still work", async () => {
			const { error, events } = await runWithErrorFrame({
				message: "legacy failure",
				recoverable: true,
				retryable: true,
			});

			expect(error.message).toBe("legacy failure");
			expect(error.errorCode).toBeNull();
			expect(events[0].error_code).toBeUndefined();
			expect(authInvalid).not.toHaveBeenCalled();
		});
	});
});
