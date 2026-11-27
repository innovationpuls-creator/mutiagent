import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import {
	HEARTBEAT_FRAME,
	SSE_EVENT_NAMES,
	createSseResponse,
	errorEventPayload,
	formatSseEvent,
} from "../src/sse.js";
import { PAYLOADS, buildContractFrames } from "./contractFrames.js";

describe("SSE adapter (AC-6)", () => {
	it("covers exactly the 11 frontend event names", () => {
		expect(SSE_EVENT_NAMES).toHaveLength(11);
	});

	it("wraps text_chunk / supervisor_thinking / supervisor_plan as event: message with payload.type", () => {
		for (const name of ["text_chunk", "supervisor_thinking", "supervisor_plan"] as const) {
			const frame = formatSseEvent(name, { x: 1 });
			expect(frame.startsWith("event: message\ndata: ")).toBe(true);
			expect(JSON.parse(frame.split("data: ")[1] ?? "")).toEqual({ x: 1, type: name });
			expect(frame.endsWith("\n\n")).toBe(true);
		}
	});

	it("emits the other 8 names as-is, single-line data, Chinese unescaped", () => {
		const frame = formatSseEvent("message_completed", PAYLOADS.message_completed);
		expect(frame).toBe('event: message_completed\ndata: {"full_text":"你好，世界\\n第二行"}\n\n');
		expect(frame.split("\n")).toHaveLength(4);
	});

	it("matches the golden fixture byte for byte", () => {
		const fixture = readFileSync(new URL("./fixtures/sse-contract.txt", import.meta.url), "utf8");
		expect(buildContractFrames()).toBe(fixture);
	});

	it("streams with the anti-buffering headers, heartbeats and a final error frame", async () => {
		const response = createSseResponse(
			async (w) => {
				w.send("session_started", { session_id: "s" });
				await new Promise((r) => setTimeout(r, 40));
				throw new Error("boom");
			},
			{ heartbeatMs: 10, onError: () => errorEventPayload({ message: "失败" }) },
		);
		expect(response.headers.get("Content-Type")).toBe("text/event-stream; charset=utf-8");
		expect(response.headers.get("Cache-Control")).toBe("no-cache");
		expect(response.headers.get("X-Accel-Buffering")).toBe("no");
		const body = await response.text();
		expect(body.startsWith('event: session_started\ndata: {"session_id":"s"}\n\n')).toBe(true);
		expect(body).toContain(HEARTBEAT_FRAME);
		expect(body.endsWith('event: error\ndata: {"message":"失败","recoverable":true,"retryable":false}\n\n')).toBe(true);
	});
});
