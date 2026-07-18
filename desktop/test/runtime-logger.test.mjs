import { describe, expect, it, vi } from "vitest";

import { createRuntimeLogger } from "../src/runtime-logger.mjs";

describe("createRuntimeLogger", () => {
	it("writes timestamped desktop and PostgreSQL messages", () => {
		const appendFile = vi.fn();
		const mkdir = vi.fn();
		const logger = createRuntimeLogger("C:\\OneTreeData\\logs", {
			appendFile,
			mkdir,
			now: () => new Date("2026-07-19T00:00:00.000Z"),
		});

		logger.info("database starting");
		logger.error(new Error("database failed"));

		expect(mkdir).toHaveBeenCalledWith("C:\\OneTreeData\\logs", {
			recursive: true,
		});
		expect(appendFile).toHaveBeenNthCalledWith(
			1,
			"C:\\OneTreeData\\logs\\desktop.log",
			"2026-07-19T00:00:00.000Z INFO database starting\n",
			"utf8",
		);
		expect(appendFile).toHaveBeenNthCalledWith(
			2,
			"C:\\OneTreeData\\logs\\desktop.log",
			"2026-07-19T00:00:00.000Z ERROR database failed\n",
			"utf8",
		);
	});
});
