import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { CanopyPage } from "./CanopyPage";

const fetchCanopyOverviewMock = vi.fn();
const navigateMock = vi.fn();

vi.mock("../../api/branch", () => ({
	fetchCanopyOverview: (...args: unknown[]) => fetchCanopyOverviewMock(...args),
}));

vi.mock("../../contexts/AuthContext", () => ({
	useAuth: () => ({
		token: "test-token",
		isAuthReady: true,
		user: null,
		login: vi.fn(),
		logout: vi.fn(),
	}),
}));

vi.mock("react-router-dom", async () => {
	const actual =
		await vi.importActual<typeof import("react-router-dom")>(
			"react-router-dom",
		);
	return {
		...actual,
		useNavigate: () => navigateMock,
	};
});

describe("CanopyPage", () => {
	beforeEach(() => {
		fetchCanopyOverviewMock.mockResolvedValue({
			courses: [
				{
					id: "year_1_course_1",
					title: "编程基础",
					grade: "year_1",
					status: "in_progress",
					score: undefined,
					description: "完成 编程基础",
					prerequisite_ids: [],
				},
				{
					id: "year_2_course_1",
					title: "数据库系统",
					grade: "year_2",
					status: "in_progress",
					score: undefined,
					description: "完成 数据库系统",
					prerequisite_ids: ["year_1_course_1"],
				},
			],
			growthStage: 1,
			completedCount: 0,
			activeRate: 0,
			avgScore: 86,
			focusedHours: 8,
			milestones: [
				{
					date: "2026.06.01",
					title: "萌芽期 - 画像建立完成",
					desc: "完成 AI 多轮对话评估，生成专属树苗。",
					reached: true,
				},
			],
		});
		navigateMock.mockReset();
	});

	it("should render knowledge graph page with fetched statistics", async () => {
		render(<CanopyPage />);

		expect(
			await screen.findByRole("heading", { name: "知识雨林图谱", level: 2 }),
		).toBeDefined();
		expect(screen.getByText("当前阶段：种子 · 雨林点亮率 0%")).toBeDefined();
		expect(screen.getByText("已点亮叶片数")).toBeDefined();
		expect(screen.getByText("0")).toBeDefined();
		expect(screen.getByText("测验平均得分")).toBeDefined();
		expect(screen.getByText("86分")).toBeDefined();
		expect(screen.getByText("专注学习时长")).toBeDefined();
		expect(screen.getByText("8.0小时")).toBeDefined();
	});
});
