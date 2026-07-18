import { randomBytes as nodeRandomBytes } from "node:crypto";
import { mkdir as nodeMkdir, readFile as nodeReadFile, writeFile as nodeWriteFile } from "node:fs/promises";
import path from "node:path";

export async function loadBuildConfiguration(
	configurationPath,
	{ readFile = nodeReadFile } = {},
) {
	const rawConfiguration = await readFile(configurationPath, "utf8");
	const configuration = JSON.parse(rawConfiguration);
	if (
		typeof configuration.apiKey !== "string" ||
		configuration.apiKey.trim() === "" ||
		typeof configuration.model !== "string" ||
		configuration.model.trim() === ""
	) {
		throw new Error("比赛运行配置不完整");
	}
	return {
		apiKey: configuration.apiKey.trim(),
		model: configuration.model.trim(),
	};
}

export async function loadOrCreateJwtSecret(
	settingsPath,
	{
		mkdir = nodeMkdir,
		randomBytes = nodeRandomBytes,
		readFile = nodeReadFile,
		writeFile = nodeWriteFile,
	} = {},
) {
	try {
		const currentSettings = JSON.parse(await readFile(settingsPath, "utf8"));
		if (
			typeof currentSettings.jwtSecret === "string" &&
			currentSettings.jwtSecret.length > 0
		) {
			return currentSettings.jwtSecret;
		}
	} catch {
		// First launch creates the settings file below.
	}

	const jwtSecret = randomBytes(48).toString("hex");
	await mkdir(path.win32.dirname(settingsPath), { recursive: true });
	await writeFile(
		settingsPath,
		`${JSON.stringify({ jwtSecret }, null, 2)}\n`,
		"utf8",
	);
	return jwtSecret;
}
