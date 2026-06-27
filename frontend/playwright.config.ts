import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
	testDir: "./e2e",
	timeout: 30_000,
	webServer: [
		{
			command:
				"cd ../backend && if [ ! -x .venv/bin/uvicorn ]; then python3 -m venv .venv && . .venv/bin/activate && pip install -e '.[test]'; else . .venv/bin/activate; fi && uvicorn app.main:app --host 127.0.0.1 --port 8000",
			url: "http://127.0.0.1:8000/api/health",
			reuseExistingServer: !process.env.CI,
			timeout: 120_000,
		},
		{
			command: "npm run dev -- --port 5173",
			url: "http://127.0.0.1:5173",
			reuseExistingServer: !process.env.CI,
			timeout: 120_000,
		},
	],
	use: {
		baseURL: "http://127.0.0.1:5173",
		trace: "retain-on-failure",
	},
	projects: [
		{
			name: "chromium",
			use: { ...devices["Desktop Chrome"] },
		},
	],
});
