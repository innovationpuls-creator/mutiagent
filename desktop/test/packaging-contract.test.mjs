import { readFile } from "node:fs/promises";
import path from "node:path";

import { describe, expect, it, vi } from "vitest";

import {
	buildCompetitionConfiguration,
	writeRuntimeConfiguration,
} from "../scripts/write-runtime-config.mjs";

describe("Windows package contract", () => {
	it("archives only the source directories required for the submission", async () => {
		const workflow = await readFile(
			new URL("../../.github/workflows/windows-portable.yml", import.meta.url),
			"utf8",
		);

		expect(workflow).toContain(
			'git archive --format=zip --output="desktop/dist/11017810源码.zip" HEAD frontend backend desktop .github/workflows/windows-portable.yml',
		);
	});

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
		expect(packageJson.build.extraFiles).toContainEqual({
			from: "resources/使用说明.pdf",
			to: "使用说明.pdf",
		});
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

	it("writes only the validated runtime configuration", async () => {
		const mkdir = vi.fn();
		const writeFile = vi.fn();

		await writeRuntimeConfiguration(
			{ LLM_API_KEY: " competition-key ", LLM_MODEL: " qwen-model " },
			{ buildDirectory: "C:\\OneTree\\build", mkdir, writeFile },
		);

		expect(mkdir).toHaveBeenCalledWith("C:\\OneTree\\build", {
			recursive: true,
		});
		expect(writeFile).toHaveBeenCalledWith(
			path.join("C:\\OneTree\\build", "runtime-config.json"),
			'{\n  "apiKey": "competition-key",\n  "model": "qwen-model"\n}\n',
			{ encoding: "utf8", mode: 0o600 },
		);
	});
});
