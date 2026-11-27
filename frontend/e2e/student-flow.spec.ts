import { expect, type Page, test } from "@playwright/test";

const stamp = "2026-10-07T00:00:00Z";
const auth = {
	token: "test-token",
	user: {
		uid: "student-flow",
		role: "student",
		username: "小林",
		identifier: "student@example.com",
		provider: "password",
		is_active: true,
		created_at: stamp,
		last_login_at: null,
	},
};
const section = {
	section_id: "1",
	parent_section_id: null,
	depth: 1,
	title: "第一章：问题分析",
	order_index: 1,
	description: "学习如何分解问题",
	key_knowledge_points: [],
	source_textbook_id: "",
	source_textbook_title: "",
	source_section_ids: [],
	source_section_titles: [],
	source_content_chars: 0,
};
const course = {
	course_node_id: "c1",
	grade_id: "year_1",
	course_or_chapter_theme: "程序设计基础",
	course_goal: "理解问题，完成练习",
	status: "current",
	has_outline: true,
};
const leaf = {
	access_state: "available",
	course,
	outline: { course_id: "c1", sections: [section] },
	sections: [section],
	section_composed_markdowns: {},
	section_resource_errors: {},
	generation_status: null,
	can_generate: true,
	first_generatable_chapter_id: "1",
	locked_reason: null,
	chapter_progress: [
		{
			chapter_id: "1",
			state: "available",
			best_score: 0,
			latest_attempt_id: null,
		},
	],
};
const questions = [
	{
		question_id: "choice",
		type: "single_choice",
		prompt: "先做什么？",
		options: [{ option_id: "A", text: "分析问题" }],
		starter_code: "",
		image_prompt: "",
		points: 30,
	},
	{
		question_id: "code",
		type: "code",
		prompt: "输出 hello",
		options: [],
		starter_code: "",
		image_prompt: "",
		points: 40,
	},
	{
		question_id: "image",
		type: "image_upload",
		prompt: "画出流程图",
		options: [],
		starter_code: "",
		image_prompt: "上传流程图",
		points: 30,
	},
];
const quiz = {
	quiz_id: "quiz1",
	quiz_version: "a".repeat(64),
	course_node_id: "c1",
	chapter_id: "1",
	status: "ready",
	questions,
	generation_error: "",
	created_at: stamp,
	updated_at: stamp,
};
const canopy = {
	courses: [],
	active_rate: 50,
	quality_scores: {},
	completed_count: 0,

	avg_score: 90,
	focused_hours: 0,
	growth_stage: 2,

	milestones: [],
};
const profile = Object.fromEntries(
	[
		"currentGrade",
		"major",
		"learningStage",
		"hasClearGoal",
		"learningMethodPreference",
		"learningPacePreference",
		"needGuidance",
		"knowledgeFoundation",
		"strengths",
		"weaknesses",
		"experience",
		"shortTermGoal",
		"longTermGoal",
		"weeklyAvailableTime",
		"constraints",
	].map((key) => [key, key === "currentGrade" ? "大一" : "已确认"]),
);
const dashboard = {
	hasCompleteProfile: true,
	profile: { ...profile, contentPreference: ["实践"] },
	profileCompleteness: 100,
	profileSummaryText: "按自己的节奏学习",
	todayLearning: {
		title: "继续学习",
		description: "完成当前课程",
		source: "学习路径",
		currentLearningCourse: {
			...course,
			time_arrangement: {
				semester_scope: "上学期",
				duration: "4周",
				pace_reason: "按学习节奏",
			},
			current_focus: "继续第一章",
			progress_state: "in_progress",
			next_action: "阅读第一章",
		},
		currentCourseDetail: null,
		currentCourseOutline: null,
		gradeCourses: [],
		followingCourses: [],
	},
	recommendations: [],
};
async function install(
	page: Page,
	options: {
		storageFailure?: boolean;
		version?: string;
		unconfirmed?: boolean;
		incomplete?: boolean;
		noCourses?: boolean;
		noQuiz?: boolean;
	} = {},
) {
	await page.addInitScript(
		({ auth, storageFailure }) => {
			if (!localStorage.getItem("mutiagent-auth"))
				localStorage.setItem("mutiagent-auth", JSON.stringify(auth));
			if (storageFailure)
				Object.defineProperty(window, "indexedDB", {
					value: {
						open: () => {
							throw new Error("storage unavailable");
						},
					},
				});
		},
		{ auth, storageFailure: options.storageFailure },
	);
	let result: Record<string, unknown> | null = null;
	let postedId = "";
	let writes = 0;
	await page.route("**/api/**", async (route) => {
		const url = new URL(route.request().url());
		if (!url.pathname.startsWith("/api/")) return route.continue();
		const body = (data: unknown, status = 200) =>
			route.fulfill({
				status,
				contentType: "application/json",
				body: JSON.stringify(data),
			});
		if (url.pathname === "/api/auth/login")
			return body({
				access_token: auth.token,
				token_type: "bearer",
				auth_type: "password",
				user: auth.user,
			});
		if (url.pathname === "/api/profile/dashboard")
			return body({
				...dashboard,
				hasCompleteProfile: !options.incomplete,
				todayLearning: options.noCourses
					? {
							...dashboard.todayLearning,
							currentCourse: null,
							currentLearningCourse: null,
						}
					: dashboard.todayLearning,
			});
		if (url.pathname === "/api/branch/overview")
			return body({
				years: {
					year_1: {
						grade_id: "year_1",
						grade_name: "大一",
						has_courses: true,
						has_outline_content: true,
						is_clickable: true,
						current_course_id: "c1",
						courses: [
							...(options.noCourses ? [] : [course]),
							{
								...course,
								course_node_id: "locked",
								status: "locked",
								course_or_chapter_theme: "进阶课程",
							},
						],
					},
				},
				updated_at: stamp,
			});
		if (url.pathname === "/api/student/matched-program") return body(null);
		if (url.pathname.startsWith("/api/leaf/courses/")) return body(leaf);
		if (url.pathname.includes("/chapters/1/quiz"))
			return body({
				course,
				chapter: section,
				quiz: options.noQuiz
					? null
					: {
							...quiz,
							quiz_version: options.version ?? quiz.quiz_version,
							questions: options.unconfirmed
								? questions.slice(0, 1)
								: questions,
						},
				latest_attempt: null,
				progress: {
					course_node_id: "c1",
					chapter_id: "1",
					state: "available",
					best_score: 0,
					latest_attempt_id: null,
					passed_at: null,
					updated_at: stamp,
				},
				next_unlocked_chapter_id: null,
				next_course_id: null,
			});
		if (url.pathname.endsWith("/attempts/stream")) {
			writes++;
			const data = route.request().postDataJSON();
			postedId = data.client_submission_id;
			result = {
				attempt: {
					attempt_id: "attempt1",
					quiz_id: "quiz1",
					quiz_version: quiz.quiz_version,
					answers: data.answers,
					score: 90,
					passed: true,
					grading_result: { summary: "通过", question_results: [] },
					created_at: stamp,
				},
				weaknesses: [],
				canopy_overview: canopy,
				next_unlocked_chapter_id: null,
				next_course_id: null,
			};
			// The server has committed, but its terminal SSE event never reaches the browser.
			return route.fulfill({
				contentType: "text/event-stream",
				body: 'event: status\ndata: {"phase":"grading","message":"正在批改"}\n\n',
			});
		}
		if (url.pathname.includes("/submissions/"))
			return body(
				!options.unconfirmed && result ? result : { detail: "尚未确认" },
				!options.unconfirmed && result ? 200 : 404,
			);
		if (url.pathname === "/api/chat/start")
			return body({
				session_id: "profile-session",
				messages: [],
				profile: null,
			});
		if (url.pathname.includes("/api/chat/sessions/"))
			return body({
				session_id: "profile-session",
				messages: [],
				profile: null,
			});
		if (url.pathname.endsWith("/ai/stream"))
			return route.fulfill({
				contentType: "text/event-stream",
				body: 'event: forest_ai_completed\ndata: {"message":"completed"}\n\n',
			});
		return body({ detail: "not used" }, 404);
	});
	return { writes: () => writes, submissionId: () => postedId };
}
for (const width of [375, 768, 1280])
	test(`student learning and durable submission at ${width}px`, async ({
		page,
	}) => {
		await page.setViewportSize({ width, height: 900 });
		await page.emulateMedia({ reducedMotion: "reduce" });
		const server = await install(page);
		await page.goto("/sprout");
		await expect(
			page.getByRole("heading", { name: "继续今天的学习" }),
		).toBeVisible();
		for (const name of [
			"学习首页",
			"学习路径",
			"课程学习",
			"章节测验",
			"学习成长",
		])
			await expect(
				page.getByRole("link", { name: new RegExp(name) }),
			).toBeVisible();
		await page.getByRole("button", { name: "打开 AI 学习助手" }).focus();
		await page.keyboard.press("Enter");
		await expect(page.getByLabel("AI 基础画像对话")).toBeVisible();
		await page.keyboard.press("Escape");
		await expect(
			page.getByRole("button", { name: "打开 AI 学习助手" }),
		).toBeFocused();
		await page.screenshot({
			path: test.info().outputPath(`home-${width}.png`),
			fullPage: true,
		});
		if (width < 1024) {
			const profileCard = page.getByRole("button", { name: /今天.*你的画像/ });
			await profileCard.scrollIntoViewIfNeeded();
			await expect(profileCard).toBeInViewport({ ratio: 1 });
			const card = await profileCard.boundingBox();
			const nav = await page
				.getByRole("navigation", { name: "学习阶段", exact: true })
				.boundingBox();
			if (!card || !nav) throw new Error("Missing student layout");
			expect(card.y + card.height).toBeLessThanOrEqual(nav.y);
			await page.screenshot({
				path: test.info().outputPath(`home-bottom-${width}.png`),
			});
		}
		await page.getByRole("button", { name: "继续学习" }).click();
		await expect(page).toHaveURL(/\/leaf\/c1/);
		await page.getByRole("link", { name: /章节测验/ }).click();
		await expect(page.getByText("尚未解锁")).toBeVisible();
		await page.getByRole("button", { name: "查看章节" }).click();
		await page.getByRole("link", { name: "开始测验" }).click();
		await page.getByLabel("分析问题").check();
		await page.getByRole("button", { name: "2", exact: true }).click();
		await page.getByLabel("代码答案").fill("print('hello')");
		await page.getByRole("button", { name: "3", exact: true }).click();
		await page.locator('input[type="file"]').setInputFiles({
			name: "answer.png",
			mimeType: "image/png",
			buffer: Buffer.from(
				"iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aE6sAAAAASUVORK5CYII=",
				"base64",
			),
		});
		await expect(page.getByText("answer.png")).toBeVisible();
		await expect(page.getByText("已保存到本机")).toBeVisible();
		await page.reload();
		await expect(page.getByText("answer.png")).toBeVisible();
		await page.getByRole("button", { name: "2", exact: true }).click();
		await expect(page.getByLabel("代码答案")).toHaveValue("print('hello')");
		await page.screenshot({
			path: test.info().outputPath(`quiz-${width}.png`),
			fullPage: true,
		});
		const submitButton = page.getByRole("button", {
			name: "提交测验",
			exact: true,
		});
		await submitButton.scrollIntoViewIfNeeded();
		if (width < 1024) {
			const viewport = await page
				.locator(".student-content-viewport")
				.boundingBox();
			const nav = await page
				.getByRole("navigation", { name: "学习阶段", exact: true })
				.boundingBox();
			const button = await submitButton.boundingBox();
			if (!viewport || !nav || !button)
				throw new Error("Missing student layout");
			expect(viewport.y + viewport.height).toBeLessThanOrEqual(nav.y);
			expect(button.y + button.height).toBeLessThanOrEqual(nav.y);
			await expect(submitButton).toBeInViewport({ ratio: 1 });
			expect(
				await submitButton.evaluate((element) => {
					const box = element.getBoundingClientRect();
					return element.contains(
						document.elementFromPoint(
							box.x + box.width / 2,
							box.y + box.height / 2,
						),
					);
				}),
			).toBe(true);
		}
		await page.screenshot({
			path: test.info().outputPath(`quiz-submit-${width}.png`),
		});
		await submitButton.click();
		await expect(page.getByRole("dialog", { name: "测验结果" })).toBeVisible();
		await expect(page.getByText("90", { exact: true })).toBeVisible();
		expect(server.writes()).toBe(1);
		expect(server.submissionId()).toMatch(/^[a-f0-9-]{36}$/);
		await page.keyboard.press("Escape");
		await expect(
			page.getByRole("dialog", { name: "测验结果" }),
		).not.toBeVisible();
		expect(
			await page.evaluate(
				() => document.documentElement.scrollWidth <= innerWidth,
			),
		).toBe(true);
	});
test("failed storage preserves code and blocks leaving until an explicit choice", async ({
	page,
}) => {
	await install(page, { storageFailure: true });
	await page.goto("/forest/c1?chapter_id=1");
	await page.getByRole("button", { name: "2", exact: true }).click();
	await page.getByLabel("代码答案").fill("unsaved answer");
	await page.getByRole("link", { name: /学习首页/ }).click();
	await expect(
		page.getByRole("alertdialog", { name: "草稿尚未保存" }),
	).toBeVisible();
	await page.getByRole("button", { name: "继续作答" }).click();
	await expect(page.getByLabel("代码答案")).toHaveValue("unsaved answer");
});

test("two windows resolve revisions explicitly without losing current input", async ({
	page,
	context,
}) => {
	await install(page);
	await page.goto("/forest/c1?chapter_id=1");
	await page.getByRole("button", { name: "2", exact: true }).click();
	await page.getByLabel("代码答案").fill("first draft");
	await expect(page.getByText("已保存到本机")).toBeVisible();
	const other = await context.newPage();
	await install(other);
	await other.goto("/forest/c1?chapter_id=1");
	await expect(other.getByLabel("代码答案")).toHaveValue("first draft");
	await expect(other.getByText("已保存到本机")).toBeVisible();
	await page.getByLabel("代码答案").fill("newer draft");
	await expect(
		page.getByRole("button", { name: "读取已保存草稿" }),
	).toBeVisible();
	await expect(page.getByLabel("代码答案")).toHaveValue("newer draft");
	await page.getByRole("button", { name: "保留当前输入" }).click();
	await expect(page.getByText("已保存到本机")).toBeVisible();
	await other.getByLabel("代码答案").fill("other input");
	await expect(
		other.getByRole("button", { name: "读取已保存草稿" }),
	).toBeVisible();
	await other.getByRole("button", { name: "读取已保存草稿" }).click();
	await expect(other.getByLabel("代码答案")).toHaveValue("newer draft");
});

test("new question version retains but never applies an older draft", async ({
	page,
}) => {
	await install(page);
	await page.goto("/forest/c1?chapter_id=1");
	await page.getByRole("button", { name: "2", exact: true }).click();
	await page.getByLabel("代码答案").fill("old version answer");
	await expect(page.getByText("已保存到本机")).toBeVisible();
	await page.unroute("**/api/**");
	await install(page, { version: "b".repeat(64) });
	await page.reload();
	await expect(
		page.getByText("题目已更新，旧草稿仍保留在本机，未套用到新题"),
	).toBeVisible();
	await page.getByRole("button", { name: "2", exact: true }).click();
	await expect(page.getByLabel("代码答案")).toHaveValue("");
});

test("unconfirmed submission survives reload and retries only on demand with the same UUID", async ({
	page,
}) => {
	const server = await install(page, { unconfirmed: true });
	await page.goto("/forest/c1?chapter_id=1");
	await page.getByLabel("分析问题").check();
	await page.getByRole("button", { name: "提交测验", exact: true }).click();
	await expect(
		page.getByRole("button", { name: "使用原答案重试" }),
	).toBeVisible();
	const id = server.submissionId();
	await page.reload();
	await expect(
		page.getByRole("button", { name: "使用原答案重试" }),
	).toBeVisible();
	expect(server.writes()).toBe(1);
	await expect(page.getByLabel("分析问题")).toBeDisabled();
	await page.getByRole("button", { name: "使用原答案重试" }).click();
	await expect(
		page.getByRole("button", { name: "使用原答案重试" }),
	).toBeVisible();
	expect(server.writes()).toBe(2);
	expect(server.submissionId()).toBe(id);
});

test("incomplete profile waits for the student to start collection", async ({
	page,
}) => {
	await install(page, { incomplete: true });
	await page.goto("/sprout");
	await expect(
		page.getByRole("button", { name: "完善学习画像" }),
	).toBeVisible();
	await expect(page.getByLabel("AI 基础画像对话")).not.toBeVisible();
	await page.getByRole("button", { name: "完善学习画像" }).click();
	await expect(page.getByLabel("AI 基础画像对话")).toBeVisible();
});

test("a chapter without questions offers an enabled generation action", async ({
	page,
}) => {
	await install(page, { noQuiz: true });
	await page.goto("/forest/c1?chapter_id=1");
	await expect(
		page.getByRole("heading", { name: "这一章还没有题目" }),
	).toBeVisible();
	await expect(page.getByRole("button", { name: "生成测验" })).toBeEnabled();
});

test("no courses offers the learning path instead of a dead start action", async ({
	page,
}) => {
	await install(page, { noCourses: true });
	await page.goto("/sprout");
	await expect(
		page.getByRole("button", { name: "查看学习路径" }),
	).toBeVisible();
	await expect(
		page.getByRole("button", { name: "继续学习", exact: true }),
	).not.toBeVisible();
});

test("a shorter mobile viewport keeps focused input and submit clear of navigation", async ({
	page,
}) => {
	await page.setViewportSize({ width: 375, height: 560 });
	await install(page);
	await page.goto("/forest/c1?chapter_id=1");
	await page.getByRole("button", { name: "2", exact: true }).click();
	const answer = page.getByLabel("代码答案");
	await answer.fill("keyboard-sized viewport");
	await answer.scrollIntoViewIfNeeded();
	const nav = await page
		.getByRole("navigation", { name: "学习阶段", exact: true })
		.boundingBox();
	const input = await answer.boundingBox();
	if (!nav || !input) throw new Error("Missing input or navigation");
	expect(input.y + input.height).toBeLessThanOrEqual(nav.y);
	await expect(answer).toBeInViewport({ ratio: 1 });
	const submit = page.getByRole("button", { name: "提交测验", exact: true });
	await submit.scrollIntoViewIfNeeded();
	await expect(submit).toBeInViewport({ ratio: 1 });
	const button = await submit.boundingBox();
	if (!button) throw new Error("Missing submission action");
	expect(button.y + button.height).toBeLessThanOrEqual(nav.y);
	await page.screenshot({
		path: test.info().outputPath("quiz-short-375.png"),
	});
});

test("visual viewport resize lifts navigation above a simulated soft keyboard", async ({
	page,
}) => {
	await page.setViewportSize({ width: 375, height: 900 });
	await page.addInitScript(() => {
		const viewport = new EventTarget();
		Object.defineProperties(viewport, {
			height: { value: 560 },
			offsetTop: { value: 0 },
		});
		Object.defineProperty(window, "visualViewport", { value: viewport });
	});
	await install(page);
	await page.goto("/forest/c1?chapter_id=1");
	await page.getByRole("button", { name: "2", exact: true }).click();
	const input = page.getByLabel("代码答案");
	await input.fill("soft keyboard");
	await input.scrollIntoViewIfNeeded();
	const nav = await page
		.getByRole("navigation", { name: "学习阶段", exact: true })
		.boundingBox();
	const answer = await input.boundingBox();
	if (!nav || !answer) throw new Error("Missing visible controls");
	expect(nav.y + nav.height).toBeLessThanOrEqual(560);
	expect(answer.y + answer.height).toBeLessThanOrEqual(nav.y);
});

test("failed submission snapshot stays editable and can be saved and submitted after recovery", async ({
	page,
}) => {
	const server = await install(page, { unconfirmed: true });
	await page.goto("/forest/c1?chapter_id=1");
	await expect(page.getByText("已保存到本机")).toBeVisible();
	await page.evaluate(() => {
		const original = IDBDatabase.prototype.transaction;
		IDBDatabase.prototype.transaction = function (...args) {
			if (args[1] === "readwrite")
				throw new Error("storage temporarily unavailable");
			return original.apply(this, args);
		};
		Object.assign(window, {
			restoreDraftStorage: () => {
				IDBDatabase.prototype.transaction = original;
			},
		});
	});
	await page.getByLabel("分析问题").check();
	await expect(page.getByRole("button", { name: "重试保存" })).toBeVisible();
	await page.getByRole("button", { name: "提交测验", exact: true }).click();
	await expect(
		page.getByText("storage temporarily unavailable").first(),
	).toBeVisible();
	await expect(page.getByLabel("分析问题")).toBeEnabled();
	expect(server.writes()).toBe(0);
	await expect(page.getByRole("button", { name: "原样重试提交" })).toHaveCount(
		0,
	);
	await page.evaluate(() => {
		(
			window as unknown as { restoreDraftStorage(): void }
		).restoreDraftStorage();
	});
	await page.getByRole("button", { name: "重试保存" }).click();
	await expect(page.getByText("已保存到本机")).toBeVisible();
	await page.getByRole("button", { name: "提交测验", exact: true }).click();
	await expect(
		page.getByRole("button", { name: "重新查询提交结果" }),
	).toBeVisible();
	expect(server.writes()).toBe(1);
});

test("logout and login restore the same student's local draft without an automatic profile opener", async ({
	page,
}) => {
	await install(page);
	await page.goto("/forest/c1?chapter_id=1");
	await page.getByRole("button", { name: "2", exact: true }).click();
	await page.getByLabel("代码答案").fill("draft across login");
	await expect(page.getByText("已保存到本机")).toBeVisible();
	await page.getByRole("button", { name: "切换个人菜单" }).click();
	await page.getByRole("menuitem", { name: "退出登录" }).click();
	await expect(page.getByLabel("密码", { exact: true })).toBeVisible();
	await page.locator('input[name="account"]').fill("student@example.com");
	await page.getByLabel("密码", { exact: true }).fill("password123");
	await page.locator('button[type="submit"]').click();
	await expect(page).toHaveURL(/\/sprout/);
	await expect(page.getByLabel("AI 基础画像对话")).toHaveCount(0);
	await page.getByRole("link", { name: /章节测验/ }).click();
	await page.getByRole("button", { name: "查看章节" }).click();
	await page.getByRole("link", { name: "开始测验" }).click();
	await expect(page.getByLabel("代码答案")).toHaveValue("draft across login");
});
