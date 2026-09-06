import { afterEach, describe, expect, it, vi } from "vitest";
import { streamGrowthReport } from "./growthReport";

const report = {
	overview: "学习表现待验证",
	generated_at: "2026-09-05T00:00:00Z",
	coverage: "无测验记录",
	stats: { passed_chapters: 0, tested_chapters: 0, attempts: 0 },
	strengths: [],
	improvements: [],
	actions: [],
	evidence: [],
};
function respond(chunks: string[]) {
	const bytes = new TextEncoder().encode(chunks.join(""));
	vi.stubGlobal(
		"fetch",
		vi.fn().mockResolvedValue(
			new Response(
				new ReadableStream({
					start(controller) {
						for (let i = 0; i < bytes.length; i += 7)
							controller.enqueue(bytes.slice(i, i + 7));
						controller.close();
					},
				}),
			),
		),
	);
}
afterEach(() => vi.unstubAllGlobals());
describe("growth report stream", () => {
	it("decodes split UTF-8, CRLF and stage events", async () => {
		respond([
			'event: report_stage\r\ndata: {"stage":"writing"}\r\n\r\n',
			`event: report_completed\r\ndata: ${JSON.stringify(report)}\r\n\r\n`,
		]);
		const stage = vi.fn();
		expect(
			await streamGrowthReport("token", new AbortController().signal, stage),
		).toEqual(report);
		expect(stage).toHaveBeenCalledWith("writing");
	});
	it("rejects a truncated stream", async () => {
		respond(['event: report_stage\ndata: {"stage":"analyzing"}\n\n']);
		await expect(
			streamGrowthReport("token", new AbortController().signal, vi.fn()),
		).rejects.toThrow("中断");
	});
	it("rejects invalid completed data", async () => {
		respond(["event: report_completed\ndata: {}\n\n"]);
		await expect(
			streamGrowthReport("token", new AbortController().signal, vi.fn()),
		).rejects.toThrow("格式");
	});
	it("surfaces a server generation error", async () => {
		respond(['event: report_error\ndata: {"message":"暂时不可用"}\n\n']);
		await expect(
			streamGrowthReport("token", new AbortController().signal, vi.fn()),
		).rejects.toThrow("暂时不可用");
	});
});
