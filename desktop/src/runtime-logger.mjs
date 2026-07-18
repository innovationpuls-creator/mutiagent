import { appendFile as nodeAppendFile } from "node:fs/promises";
import { mkdir as nodeMkdir } from "node:fs/promises";

function formatMessage(message) {
	if (message instanceof Error) {
		return message.message;
	}
	return String(message);
}

function ignoreAsyncFailure(result) {
	if (result && typeof result.catch === "function") {
		result.catch(() => undefined);
	}
}

export function createRuntimeLogger(
	logsDirectory,
	{
		appendFile = nodeAppendFile,
		mkdir = nodeMkdir,
		now = () => new Date(),
	} = {},
) {
	const logPath = `${logsDirectory}\\desktop.log`;
	let directoryReady = false;

	function write(level, message) {
		if (!directoryReady) {
			directoryReady = true;
			ignoreAsyncFailure(mkdir(logsDirectory, { recursive: true }));
		}
		const line = `${now().toISOString()} ${level} ${formatMessage(message)}\n`;
		ignoreAsyncFailure(appendFile(logPath, line, "utf8"));
	}

	return {
		info(message) {
			write("INFO", message);
		},
		error(message) {
			write("ERROR", message);
		},
	};
}
