import {
	act,
	cleanup,
	fireEvent,
	render,
	screen,
	waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { GrowthReport } from "../../api/growthReport";
import { GrowthReportPanel } from "./GrowthReportPanel";
import { useGrowthReport } from "./useGrowthReport";

const stream = vi.fn();
Object.defineProperty(HTMLElement.prototype, "scrollIntoView", {
	configurable: true,
	value: vi.fn(),
});
afterEach(cleanup);
const navigate = vi.fn();
vi.mock("../../api/growthReport", () => ({
	streamGrowthReport: (...args: unknown[]) => stream(...args),
}));
vi.mock("react-router-dom", () => ({ useNavigate: () => navigate }));
const report: GrowthReport = {
	overview: "你已开始通过练习检查学习成果。",
	generated_at: "2026-09-05T00:00:00Z",
	coverage: "统计覆盖累计记录",
	stats: { passed_chapters: 1, tested_chapters: 2, attempts: 3 },
	strengths: [
		{
			title: "完成循环练习",
			body: "已通过章节测验。",
			evidence_ids: ["quiz:1"],
		},
	],
	improvements: [],
	actions: [
		{
			title: "检查循环边界",
			body: "回到练习复盘。",
			check: "写出边界条件。",
			course_id: "course-1",
			evidence_ids: ["quiz:1"],
		},
	],
	evidence: [
		{
			id: "quiz:1",
			kind: "quiz",
			title: "循环测验",
			detail: "最近作答 85 分",
			course_id: "course-1",
		},
	],
};
function Harness({ token = "token" }: { token?: string }) {
	const state = useGrowthReport(token);
	return (
		<>
			<button type="button" disabled={!!state.stage} onClick={state.generate}>
				生成
			</button>
			<GrowthReportPanel {...state} onGenerate={state.generate} />
		</>
	);
}
beforeEach(() => {
	stream.mockReset();
	navigate.mockReset();
});
describe("growth report panel", () => {
	it("generates, exposes evidence and navigates to the course", async () => {
		stream.mockResolvedValue(report);
		render(<Harness />);
		fireEvent.click(screen.getByRole("button", { name: "生成" }));
		expect(await screen.findByText(report.overview)).toBeDefined();
		fireEvent.click(screen.getAllByText("查看依据 · 1")[0]);
		expect(screen.getAllByText("最近作答 85 分").length).toBeGreaterThan(0);
		fireEvent.click(screen.getByRole("button", { name: "前往对应课程" }));
		expect(navigate).toHaveBeenCalledWith("/leaf/course-1");
	});
	it("keeps the previous report when regeneration fails", async () => {
		stream
			.mockResolvedValueOnce(report)
			.mockRejectedValueOnce(new Error("模型暂时不可用"));
		render(<Harness />);
		fireEvent.click(screen.getByRole("button", { name: "生成" }));
		await screen.findByText(report.overview);
		fireEvent.click(screen.getByRole("button", { name: "重新生成" }));
		expect(await screen.findByRole("alert")).toBeDefined();
		expect(screen.getByText(report.overview)).toBeDefined();
	});
	it("clears report and aborts pending work on account change", async () => {
		let finish: (value: GrowthReport) => void = () => undefined;
		stream.mockImplementation(
			() =>
				new Promise<GrowthReport>((resolve) => {
					finish = resolve;
				}),
		);
		const { rerender } = render(<Harness token="one" />);
		fireEvent.click(screen.getByRole("button", { name: "生成" }));
		const signal = stream.mock.calls[0][1] as AbortSignal;
		rerender(<Harness token="two" />);
		expect(signal.aborted).toBe(true);
		await act(async () => {
			finish(report);
		});
		await waitFor(() => expect(screen.queryByText(report.overview)).toBeNull());
	});
});
