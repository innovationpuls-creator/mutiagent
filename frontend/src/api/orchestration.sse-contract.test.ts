import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { parseSseChunk } from "./orchestration";

// Shared golden fixture owned by the ai-gateway SSE adapter tests.
// vitest runs from frontend/ (npm test), so resolve relative to the cwd.
const FIXTURE_PATH = resolve(
	process.cwd(),
	"../ai-gateway/test/fixtures/sse-contract.txt",
);

const EXPECTED_EVENTS = [
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
];

describe("SSE golden fixture contract (AC-6)", () => {
	it("fixture file exists", () => {
		expect(
			existsSync(FIXTURE_PATH),
			`missing shared SSE fixture: ${FIXTURE_PATH}`,
		).toBe(true);
	});

	it("parses all 11 event names with no remainder", () => {
		if (!existsSync(FIXTURE_PATH)) {
			throw new Error(`missing shared SSE fixture: ${FIXTURE_PATH}`);
		}
		const text = readFileSync(FIXTURE_PATH, "utf-8");

		const { events, rest } = parseSseChunk(text);

		expect(rest).toBe("");
		const names = new Set(events.map((e) => e.event));
		for (const name of EXPECTED_EVENTS) {
			expect(names, `event ${name} not parsed`).toContain(name);
		}
		for (const name of names) {
			expect(EXPECTED_EVENTS).toContain(name);
		}
	});

	it("unwraps message-wrapped events and ignores heartbeat comments", () => {
		if (!existsSync(FIXTURE_PATH)) {
			throw new Error(`missing shared SSE fixture: ${FIXTURE_PATH}`);
		}
		const text = readFileSync(FIXTURE_PATH, "utf-8");
		expect(text).toContain("event: message");
		expect(text).toContain(": keep-alive");

		const { events } = parseSseChunk(text);

		expect(events.some((e) => (e.event as string) === "message")).toBe(false);
		for (const name of [
			"text_chunk",
			"supervisor_thinking",
			"supervisor_plan",
		]) {
			expect(events.some((e) => e.event === name)).toBe(true);
		}
		expect(events.find((e) => e.event === "text_chunk")?.chunk).toBeTypeOf(
			"string",
		);
	});
});
