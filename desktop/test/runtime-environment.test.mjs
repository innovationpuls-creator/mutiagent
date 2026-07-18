import path from "node:path";

import { describe, expect, it } from "vitest";

import {
	buildBackendEnvironment,
	resolveRuntimePaths,
} from "../src/runtime-environment.mjs";

describe("resolveRuntimePaths", () => {
	it("resolves packaged resources and writable user data separately", () => {
		expect(
			resolveRuntimePaths({
				resourcesPath: "C:\\Program Files\\OneTree\\resources",
				userDataPath: "C:\\Users\\judge\\AppData\\Roaming\\OneTree",
			}),
		).toEqual({
			backendExecutable: path.win32.join(
				"C:\\Program Files\\OneTree\\resources",
				"backend",
				"OneTreeRuntime.exe",
			),
			frontendDist: path.win32.join(
				"C:\\Program Files\\OneTree\\resources",
				"frontend",
			),
			logsDir: path.win32.join(
				"C:\\Users\\judge\\AppData\\Roaming\\OneTree",
				"logs",
			),
			postgresDataDir: path.win32.join(
				"C:\\Users\\judge\\AppData\\Roaming\\OneTree",
				"database",
			),
			uploadsDir: path.win32.join(
				"C:\\Users\\judge\\AppData\\Roaming\\OneTree",
				"knowledge-base-uploads",
			),
		});
	});
});

describe("buildBackendEnvironment", () => {
	it("builds the exact backend configuration used by the packaged app", () => {
		const environment = buildBackendEnvironment({
			apiKey: "competition-key",
			frontendDist: "C:\\OneTree\\resources\\frontend",
			jwtSecret: "desktop-jwt-secret",
			model: "configured-model",
			uploadsDir: "C:\\OneTreeData\\uploads",
		});

		expect(environment).toMatchObject({
			ALLOWED_ORIGINS: "http://127.0.0.1:8000",
			APP_ENV: "production",
			DATABASE_URL:
				"postgresql://onetree:onetree-desktop@127.0.0.1:55432/onetree",
			JWT_SECRET: "desktop-jwt-secret",
			KNOWLEDGE_BASE_UPLOAD_DIR: "C:\\OneTreeData\\uploads",
			LLM_API_KEY: "competition-key",
			LLM_MODEL: "configured-model",
			ONETREE_FRONTEND_DIST: "C:\\OneTree\\resources\\frontend",
		});
	});
});
