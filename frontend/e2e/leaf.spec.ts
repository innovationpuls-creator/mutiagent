import { expect, type Page, test } from "@playwright/test";

const authState = {
	token: "e2e-token",
	user: {
		uid: "e2e-user",
		role: "student",
		username: "端到端用户",
		identifier: "e2e@example.com",
		provider: "password",
		is_active: true,
		created_at: "2026-06-06T00:00:00Z",
		last_login_at: null,
	},
};

const profileDashboard = {
	hasCompleteProfile: true,
	profile: {
		currentGrade: "大三",
		major: "软件工程",
		learningStage: "项目实践",
		hasClearGoal: "是",
		learningMethodPreference: "项目驱动",
		learningPacePreference: "周末集中",
		contentPreference: ["实践"],
		needGuidance: "需要",
		knowledgeFoundation: "有基础",
		strengths: "执行力强",
		weaknesses: "部署经验不足",
		experience: "做过课程项目",
		shortTermGoal: "完成 AI 项目",
		longTermGoal: "成为 AI 应用开发者",
		weeklyAvailableTime: "每周 8 小时",
		constraints: "周末集中",
	},
	profileCompleteness: 100,
	profileSummaryText: "测试摘要",
	todayLearning: {
		title: "今日学习",
		description: "测试",
		source: "学习路径智能体",
		currentLearningCourse: null,
		currentCourseDetail: null,
		currentCourseOutline: null,
		gradeCourses: [],
		followingCourses: [],
	},
	recommendations: [],
};

const branchOverview = {
	years: {
		year_1: {
			grade_id: "year_1",
			grade_name: "大一",
			has_courses: false,
			has_outline_content: false,
			is_clickable: false,
			current_course_id: null,
			courses: [],
		},
		year_2: {
			grade_id: "year_2",
			grade_name: "大二",
			has_courses: false,
			has_outline_content: false,
			is_clickable: false,
			current_course_id: null,
			courses: [],
		},
		year_3: {
			grade_id: "year_3",
			grade_name: "大三",
			has_courses: true,
			has_outline_content: true,
			is_clickable: true,
			current_course_id: "year_3_course_2",
			courses: [
				{
					course_node_id: "year_3_course_1",
					course_or_chapter_theme: "已完成课程",
					course_goal: "复习",
					status: "completed",
					has_outline: true,
				},
				{
					course_node_id: "year_3_course_2",
					course_or_chapter_theme: "当前课程",
					course_goal: "学习",
					status: "current",
					has_outline: true,
				},
				{
					course_node_id: "year_3_course_3",
					course_or_chapter_theme: "锁定课程",
					course_goal: "以后学习",
					status: "locked",
					has_outline: false,
				},
			],
		},
		year_4: {
			grade_id: "year_4",
			grade_name: "大四",
			has_courses: false,
			has_outline_content: false,
			is_clickable: false,
			current_course_id: null,
			courses: [],
		},
	},
	updated_at: "2026-06-06T00:00:00Z",
};

function leafPayload(courseNodeId: string) {
	return {
		access_state: "available",
		course: {
			course_node_id: courseNodeId,
			grade_id: "year_3",
			course_or_chapter_theme: "AI Agent 开发",
			course_goal: "完成 AI Agent 开发",
			status: "current",
			has_outline: true,
		},
		outline: { course_id: courseNodeId, course_name: "AI Agent 开发" },
		sections: [
			{
				section_id: "1",
				parent_section_id: null,
				depth: 1,
				title: "第一章：需求拆解",
				order_index: 1,
				description: "确认边界",
				key_knowledge_points: ["边界"],
				source_textbook_id: "tb-1",
				source_textbook_title: "AI Agent 教材",
				source_section_ids: ["1"],
				source_section_titles: ["第一章：需求拆解"],
				source_content_chars: 1200,
			},
			{
				section_id: "1.1",
				parent_section_id: "1",
				depth: 2,
				title: "学习目标",
				order_index: 2,
				description: "明确目标",
				key_knowledge_points: ["目标"],
				source_textbook_id: "tb-1",
				source_textbook_title: "AI Agent 教材",
				source_section_ids: ["1.1"],
				source_section_titles: ["学习目标"],
				source_content_chars: 600,
			},
			{
				section_id: "2",
				parent_section_id: null,
				depth: 1,
				title: "第二章：资源编排",
				order_index: 3,
				description: "整理资源",
				key_knowledge_points: ["资源"],
				source_textbook_id: "tb-1",
				source_textbook_title: "AI Agent 教材",
				source_section_ids: ["2"],
				source_section_titles: ["第二章：资源编排"],
				source_content_chars: 900,
			},
		],
		section_composed_markdowns: {
			"1.1": {
				section_id: "1.1",
				parent_section_id: "1",
				title: "学习目标",
				markdown: "# 学习目标",
				generated_at: "2026-06-06T00:00:00Z",
				blocks: [
					{
						type: "markdown",
						markdown: "# 学习目标\n\n正文内容\n\n- 建立边界\n- 拆分任务",
					},
					{
						type: "video",
						brief_id: "video_1",
						title: "导入视频",
						purpose: "建立直觉",
						status: "unavailable",
						videos: [],
					},
					{
						type: "animation",
						brief_id: "anim_1",
						title: "目标动画",
						status: "unavailable",
						html: "",
					},
				],
			},
		},
		section_resource_errors: {},
		chapter_progress: [],
		generation_status: null,
		can_generate: true,
		first_generatable_chapter_id: "1",
		locked_reason: null,
	};
}

async function installMocks(page: Page) {
	await page.addInitScript((state) => {
		localStorage.setItem("mutiagent-auth", JSON.stringify(state));
		localStorage.removeItem("mutiagent-leaf-markmap-collapsed");
		localStorage.removeItem("mutiagent-leaf-markmap-section-collapsed");
	}, authState);

	await page.route("**/api/profile/dashboard", async (route) => {
		await route.fulfill({
			status: 200,
			contentType: "application/json",
			body: JSON.stringify(profileDashboard),
		});
	});
	await page.route("**/api/branch/overview", async (route) => {
		await route.fulfill({
			status: 200,
			contentType: "application/json",
			body: JSON.stringify(branchOverview),
		});
	});
	await page.route("**/api/student/matched-program", async (route) => {
		await route.fulfill({
			status: 200,
			contentType: "application/json",
			body: "null",
		});
	});
	await page.route("**/api/leaf/courses/*", async (route) => {
		const courseNodeId =
			route.request().url().split("/").pop() ?? "year_3_course_2";
		await route.fulfill({
			status: 200,
			contentType: "application/json",
			body: JSON.stringify(leafPayload(courseNodeId)),
		});
	});
	await page.route("**/api/forest/**", async (route) => {
		await route.fulfill({
			status: 200,
			contentType: "application/json",
			body: JSON.stringify({
				course: leafPayload("year_3_course_2").course,
				chapter: leafPayload("year_3_course_2").sections[0],
				quiz: null,
				latest_attempt: null,
				progress: null,
				next_unlocked_chapter_id: null,
				next_course_id: null,
			}),
		});
	});
}

test("branch opens current courses and explains locked courses", async ({
	page,
}) => {
	await installMocks(page);
	await page.goto("/branch");

	await expect(page.getByRole("heading", { name: "你的路径" })).toBeVisible();
	await page
		.getByRole("button", {
			name: /大三第 3 门课程（自选课程）：锁定课程，未开放/,
		})
		.click();
	await expect(page.getByRole("status")).toHaveText(
		"「锁定课程」还未开放，先完成前面的课程。",
	);
	await expect(page).toHaveURL(/\/branch$/);

	const currentCourseButton = page.getByRole("button", {
		name: /大三第 2 门课程（自选课程）：当前课程，进行中/,
	});
	await currentCourseButton.click();
	await expect(currentCourseButton).toHaveAttribute("aria-pressed", "true");
	await currentCourseButton.click();
	await expect(page).toHaveURL(/\/leaf\/year_3_course_2$/);
	await expect(
		page.getByRole("heading", { name: "AI Agent 开发", level: 1 }),
	).toBeVisible();
});

test("leaf renders generated resources and opens AI draft", async ({
	page,
}) => {
	await installMocks(page);
	await page.goto("/leaf/year_3_course_2");

	await expect(
		page.getByRole("heading", { name: "AI Agent 开发", level: 1 }),
	).toBeVisible();
	await expect(
		page.getByRole("heading", { name: "1.1 学习目标", exact: true }),
	).toBeVisible();
	await expect(page.getByText("正文内容")).toBeVisible();
	await expect(page.getByText("视频生成失败")).toBeVisible();
	await expect(page.getByText("动画生成失败")).toBeVisible();

	await page.getByRole("button", { name: "收起章节导航" }).click();
	await expect(
		page.getByRole("button", { name: "展开章节导航" }),
	).toBeVisible();
	await page.getByRole("button", { name: "展开章节导航" }).click();

	await page.getByRole("button", { name: "章节测验" }).click();
	await expect(page).toHaveURL(/\/forest\/year_3_course_2\?chapter_id=1$/);

	await page.goto("/leaf/year_3_course_2");
	await expect(
		page.getByRole("heading", { name: "AI Agent 开发", level: 1 }),
	).toBeVisible();
	await page.getByRole("button", { name: "让 AI 生成本章内容" }).click();
	await expect(page.getByTestId("global-ai-widget-shell")).toBeVisible();
	await expect(page.getByRole("textbox")).toHaveValue(
		/\[LEAF_RESOURCE_GENERATION\]/,
	);
	await expect(page.getByRole("textbox")).toHaveValue(
		/course_node_id: year_3_course_2/,
	);
});
