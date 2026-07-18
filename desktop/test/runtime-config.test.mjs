import { describe, expect, it, vi } from "vitest";

import {
	loadBuildConfiguration,
	loadOrCreateJwtSecret,
} from "../src/runtime-config.mjs";

describe("loadBuildConfiguration", () => {
	it("reads the competition model configuration", async () => {
		const readFile = vi.fn(async () =>
			JSON.stringify({ apiKey: "competition-key", model: "configured-model" }),
		);

		await expect(
			loadBuildConfiguration("C:\\OneTree\\runtime-config.json", { readFile }),
		).resolves.toEqual({
			apiKey: "competition-key",
			model: "configured-model",
		});
	});

	it("rejects an incomplete build configuration", async () => {
		const readFile = vi.fn(async () => JSON.stringify({ apiKey: "" }));

		await expect(
			loadBuildConfiguration("C:\\OneTree\\runtime-config.json", { readFile }),
		).rejects.toThrow("比赛运行配置不完整");
	});
});

describe("loadOrCreateJwtSecret", () => {
	it("reuses the persisted secret", async () => {
		const readFile = vi.fn(async () =>
			JSON.stringify({ jwtSecret: "persisted-secret" }),
		);

		await expect(
			loadOrCreateJwtSecret("C:\\OneTreeData\\settings.json", {
				mkdir: vi.fn(),
				randomBytes: vi.fn(),
				readFile,
				writeFile: vi.fn(),
			}),
		).resolves.toBe("persisted-secret");
	});

	it("creates and persists a secret on first launch", async () => {
		const writeFile = vi.fn();
		const mkdir = vi.fn();
		const randomBytes = vi.fn(() => Buffer.from("generated-secret"));

		await expect(
			loadOrCreateJwtSecret("C:\\OneTreeData\\settings.json", {
				mkdir,
				randomBytes,
				readFile: vi.fn().mockRejectedValueOnce(new Error("missing")),
				writeFile,
			}),
		).resolves.toBe(Buffer.from("generated-secret").toString("hex"));
		expect(mkdir).toHaveBeenCalledWith("C:\\OneTreeData", {
			recursive: true,
		});
		expect(writeFile).toHaveBeenCalledOnce();
	});
});
