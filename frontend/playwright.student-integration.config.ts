import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
	testDir: "./e2e",
	testMatch: "student-integration.spec.ts",
	timeout: 30_000,
	workers: 1,
	webServer: [
		{
			command:
				"cd ../backend && uv run uvicorn tests.student_e2e_app:create_student_e2e_app --factory --host 127.0.0.1 --port 8001",
			url: "http://127.0.0.1:8001/api/health",
			reuseExistingServer: false,
			timeout: 120_000,
		},
		{
			command: "npm run dev -- --port 5173",
			url: "http://127.0.0.1:5173",
			reuseExistingServer: !process.env.CI,
			timeout: 120_000,
		},
	],
	use: { baseURL: "http://127.0.0.1:5173", trace: "retain-on-failure" },
	projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
