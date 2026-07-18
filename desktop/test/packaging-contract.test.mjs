import { readFile } from "node:fs/promises";

import { describe, expect, it } from "vitest";

import { buildCompetitionConfiguration } from "../scripts/write-runtime-config.mjs";

describe("Windows package contract", () => {
	it("builds the exact competition artifact and executable names", async () => {
		const packageJson = JSON.parse(
			await readFile(new URL("../package.json", import.meta.url), "utf8"),
		);

		expect(packageJson.build).toMatchObject({
			artifactName: "11017810作品.${ext}",
			productName: "OneTree",
			win: {
				executableName: "OneTree",
				target: ["zip"],
			},
		});
		expect(packageJson.build.extraResources).toEqual(
			expect.arrayContaining([
				expect.objectContaining({ from: "../frontend/dist", to: "frontend" }),
				expect.objectContaining({
					from: "build/backend/OneTreeRuntime",
					to: "backend",
				}),
				expect.objectContaining({
					from: "build/runtime-config.json",
					to: "runtime-config.json",
				}),
			]),
		);
	});
});

describe("buildCompetitionConfiguration", () => {
	it("uses the exact build-time secret and model keys", () => {
		expect(
			buildCompetitionConfiguration({
				LLM_API_KEY: "competition-key",
				LLM_MODEL: "qwen-model",
			}),
		).toEqual({ apiKey: "competition-key", model: "qwen-model" });
	});

	it("rejects missing competition secrets", () => {
		expect(() => buildCompetitionConfiguration({})).toThrow(
			"LLM_API_KEY and LLM_MODEL are required",
		);
	});
});
