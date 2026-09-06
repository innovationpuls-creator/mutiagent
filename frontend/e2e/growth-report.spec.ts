import { expect, test } from "@playwright/test";
import type { GrowthReport } from "../src/api/growthReport";

const report: GrowthReport = {
	generated_at: "2026-09-05T06:00:00Z",
	stats: { passed_chapters: 3, tested_chapters: 4, attempts: 7 },
	overview:
		"你已经把编程基础中的概念，逐步变成可以运行和检查的代码。测验记录显示，你开始主动关注循环的执行过程；接下来，把边界条件和异常输入纳入练习，会让这份基础更加扎实。",
	strengths: [
		{
			title: "从理解概念到完成练习",
			body: "你已有章节通关记录，能够通过代码表达基本的循环逻辑。这些完成记录，是继续学习数据结构的起点。",
			evidence_ids: ["quiz:loop"],
		},
	],
	improvements: [
		{
			title: "让边界检查成为习惯",
			body: "最近一次判题反馈指出，循环结束条件还值得复盘。建议从空输入、单个元素和重复元素开始检查。",
			evidence_ids: ["quiz:loop"],
		},
	],
	actions: [
		{
			title: "重新检查循环练习",
			body: "回到编程基础课程，为自己的实现补上边界用例，并解释每个用例检查了什么。",
			check: "代码能处理空输入和单个元素，并能说明循环何时结束。",
			evidence_ids: ["quiz:loop"],
			course_id: "year_1_course_1",
		},
	],
	evidence: [
		{
			id: "quiz:loop",
			kind: "quiz",
			title: "编程基础 · 循环测验",
			detail: "最近作答 85 分。判题反馈：循环主体正确，边界条件需要复习。",
			course_id: "year_1_course_1",
		},
	],
	coverage: "浏览器测试使用合成报告。统计覆盖累计记录；正文判断关联具体测验。",
};

test("成森成长报告：生成、证据、失败保留与移动端", async ({
	page,
}, testInfo) => {
	await page.addInitScript(() =>
		localStorage.setItem(
			"mutiagent-auth",
			JSON.stringify({
				token: "report-e2e",
				user: {
					uid: "report-user",
					username: "学习者",
					role: "student",
					is_active: true,
				},
			}),
		),
	);
	await page.route("**/api/branch/canopy", (route) =>
		route.fulfill({
			json: {
				courses: [
					{
						id: "year_1_course_1",
						title: "编程基础",
						grade: "year_1",
						status: "current",
						description: "完成编程基础",
						prerequisite_ids: [],
					},
				],
				growth_stage: 3,
				completed_count: 3,
				active_rate: 40,
				avg_score: 85,
				focused_hours: 14,
				quality_scores: {},
				milestones: [
					{
						date: "2026.09.01",
						title: "萌芽期 - 画像建立完成",
						desc: "开始建立自己的学习路径。",
						reached: true,
					},
				],
			},
		}),
	);
	let calls = 0;
	let release = () => {};
	const firstResponse = new Promise<void>((resolve) => {
		release = resolve;
	});
	await page.route("**/api/branch/canopy/report/stream", async (route) => {
		calls += 1;
		if (calls === 1) await firstResponse;
		return route.fulfill({
			contentType: "text/event-stream",
			body:
				calls === 2
					? 'event: report_error\ndata: {"message":"报告暂时未能生成，请重试。"}\n\n'
					: `event: report_stage\ndata: {"stage":"writing"}\n\nevent: report_completed\ndata: ${JSON.stringify(report)}\n\n`,
		});
	});
	await page.setViewportSize({ width: 1440, height: 1000 });
	await page.goto("/canopy");
	await page.getByRole("button", { name: "生成成长报告", exact: true }).click();
	const panel = page.getByRole("region", { name: "AI 成长报告" });
	await expect(panel.getByRole("status")).toContainText("正在整理学习记录");
	await expect
		.poll(async () => (await panel.boundingBox())?.y ?? -1)
		.toBeGreaterThan(0);
	await expect
		.poll(async () => (await panel.boundingBox())?.y ?? 1000)
		.toBeLessThan(300);
	release();
	await expect(panel.getByText(report.overview)).toBeVisible();
	await panel.getByText("查看依据 · 1").first().click();
	await expect(
		panel.getByText(report.evidence[0].detail).first(),
	).toBeVisible();
	await panel.evaluate((element) =>
		element.scrollIntoView({ block: "start", behavior: "instant" }),
	);
	await page.screenshot({ path: testInfo.outputPath("report-desktop.png") });
	await page.getByRole("button", { name: "重新生成", exact: true }).click();
	await expect(panel.getByRole("alert")).toContainText("报告暂时未能生成");
	await expect(panel.getByText(report.overview)).toBeVisible();
	await panel.getByRole("button", { name: "重试", exact: true }).click();
	await expect(panel.getByRole("alert")).toHaveCount(0);
	await page.setViewportSize({ width: 390, height: 844 });
	await page.emulateMedia({ reducedMotion: "reduce" });
	await expect(panel).toBeVisible();
	expect(
		await panel.evaluate(
			(element) => element.scrollWidth <= element.clientWidth,
		),
	).toBe(true);
	await panel.evaluate((element) =>
		element.scrollIntoView({ block: "start", behavior: "instant" }),
	);
	await page.screenshot({ path: testInfo.outputPath("report-mobile.png") });
	await panel.getByRole("button", { name: "前往对应课程" }).click();
	await expect(page).toHaveURL(/\/leaf\/year_1_course_1$/);
});
