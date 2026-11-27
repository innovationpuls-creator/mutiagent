import { expect, test } from "@playwright/test";

for (const width of [375, 768, 1280]) {
	test(`real API learning and committed-result recovery at ${width}px`, async ({
		page,
		request,
	}) => {
		await page.setViewportSize({ width, height: 900 });
		await page.emulateMedia({ reducedMotion: "reduce" });
		let submittedId = "";
		let quizId = "";
		let originalResult: unknown = null;
		await page.route("**/api/**", async (route) => {
			const url = new URL(route.request().url());
			if (!url.pathname.startsWith("/api/")) return route.continue();
			const response = await route.fetch({
				url: `http://127.0.0.1:8001${url.pathname}${url.search}`,
			});
			if (url.pathname.endsWith("/attempts/stream")) {
				submittedId = route.request().postDataJSON().client_submission_id;
				quizId = url.pathname.split("/")[4];
				const stream = await response.text();
				const done = stream.match(/event: done\ndata: ([^\n]+)/);
				if (!done) throw new Error(`Backend did not commit: ${stream}`);
				originalResult = JSON.parse(done[1]);
				await route.fulfill({
					status: 200,
					contentType: "text/event-stream",
					body: 'event: status\ndata: {"message":"正在批改"}\n\n',
				});
				return;
			}
			await route.fulfill({ response });
		});
		await page.goto("/login");
		await page.locator('input[name="account"]').fill("forest@example.com");
		await page.getByLabel("密码", { exact: true }).fill("student-password");
		await page.locator('button[type="submit"]').click();
		await expect(page).toHaveURL(/\/sprout/);
		await page.getByRole("button", { name: "继续学习", exact: true }).click();
		await expect(page).toHaveURL(/\/leaf\/year_3_course_2/);
		await page.getByRole("link", { name: /章节测验/ }).click();
		await page.getByRole("button", { name: "查看章节" }).first().click();
		await page
			.getByRole("link", { name: /开始测验|再次测验/ })
			.first()
			.click();
		await page.getByLabel("正确答案").check();
		await expect(page.getByText("已保存到本机")).toBeVisible();
		await page.getByRole("button", { name: "提交测验", exact: true }).click();
		await expect(page.getByRole("dialog", { name: "测验结果" })).toBeVisible();
		const token = await page.evaluate(
			() => JSON.parse(localStorage.getItem("mutiagent-auth") ?? "{}").token,
		);
		const recovered = await request.get(
			`http://127.0.0.1:8001/api/forest/quizzes/${quizId}/submissions/${submittedId}`,
			{ headers: { Authorization: `Bearer ${token}` } },
		);
		expect(recovered.status()).toBe(200);
		expect(await recovered.json()).toEqual(originalResult);
		const stats = page.locator(".forest-overlay-panel");
		await expect(stats.getByText("0 / 2", { exact: true })).toBeVisible();
		await expect(stats.getByText("1 章", { exact: true })).toBeVisible();
		await expect(stats.getByText(/\d+(\.\d+)? 小时/)).toBeVisible();
		await expect(stats).toHaveCSS("opacity", "1");
		await page.screenshot({
			path: test.info().outputPath(`real-result-${width}.png`),
		});
		await page.getByRole("button", { name: /解锁下一章/ }).click();
		await expect(page).toHaveURL(/\/leaf\/year_3_course_2\?section_id=2/);
	});
}
