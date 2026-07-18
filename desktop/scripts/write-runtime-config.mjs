import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

export function buildCompetitionConfiguration(environment) {
	const apiKey = environment.LLM_API_KEY?.trim();
	const model = environment.LLM_MODEL?.trim();
	if (!apiKey || !model) {
		throw new Error("LLM_API_KEY and LLM_MODEL are required");
	}
	return { apiKey, model };
}

export async function writeRuntimeConfiguration(environment = process.env) {
	const configuration = buildCompetitionConfiguration(environment);
	const buildDirectory = path.resolve(
		path.dirname(fileURLToPath(import.meta.url)),
		"..",
		"build",
	);
	await mkdir(buildDirectory, { recursive: true });
	await writeFile(
		path.join(buildDirectory, "runtime-config.json"),
		`${JSON.stringify(configuration, null, 2)}\n`,
		{ encoding: "utf8", mode: 0o600 },
	);
}

const invokedPath = process.argv[1] ? path.resolve(process.argv[1]) : "";
if (invokedPath === fileURLToPath(import.meta.url)) {
	await writeRuntimeConfiguration();
}
