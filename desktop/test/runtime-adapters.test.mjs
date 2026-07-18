import { EventEmitter } from "node:events";

import { describe, expect, it, vi } from "vitest";

import {
	createEmbeddedDatabase,
	createProcessAdapter,
	waitForBackendHealth,
} from "../src/runtime-adapters.mjs";

class FakePostgres {
	constructor(options) {
		this.options = options;
		this.client = {
			connect: vi.fn(),
			end: vi.fn(),
			query: vi.fn(async () => ({ rowCount: 0 })),
		};
		this.initialise = vi.fn();
		this.start = vi.fn();
		this.stop = vi.fn();
		this.createDatabase = vi.fn();
	}

	getPgClient() {
		return this.client;
	}
}

function successfulChild(pid = 42) {
	const child = new EventEmitter();
	child.pid = pid;
	child.exitCode = null;
	queueMicrotask(() => {
		child.exitCode = 0;
		child.emit("exit", 0, null);
	});
	return child;
}

describe("createEmbeddedDatabase", () => {
	it("initialises a new persistent local-only cluster", async () => {
		const access = vi.fn().mockRejectedValueOnce(new Error("missing"));
		const mkdir = vi.fn();
		const onError = vi.fn();
		const onLog = vi.fn();
		const database = createEmbeddedDatabase({
			PostgresClass: FakePostgres,
			access,
			databaseDir: "C:\\OneTreeData\\database",
			mkdir,
			onError,
			onLog,
		});

		await database.initialise();

		expect(mkdir).toHaveBeenCalledWith("C:\\OneTreeData\\database", {
			recursive: true,
		});
		expect(database.instance.options).toMatchObject({
			authMethod: "scram-sha-256",
			persistent: true,
			port: 55432,
			postgresFlags: ["-h", "127.0.0.1"],
			onError,
			onLog,
		});
		expect(database.instance.initialise).toHaveBeenCalledOnce();
	});

	it("does not reinitialise an existing cluster", async () => {
		const database = createEmbeddedDatabase({
			PostgresClass: FakePostgres,
			access: vi.fn(),
			databaseDir: "C:\\OneTreeData\\database",
			mkdir: vi.fn(),
		});

		await database.initialise();

		expect(database.instance.initialise).not.toHaveBeenCalled();
	});

	it("creates the application database only when it is missing", async () => {
		const database = createEmbeddedDatabase({
			PostgresClass: FakePostgres,
			access: vi.fn(),
			databaseDir: "C:\\OneTreeData\\database",
			mkdir: vi.fn(),
		});

		await database.ensureDatabase();

		expect(database.instance.client.query).toHaveBeenCalledWith(
			"SELECT 1 FROM pg_database WHERE datname = $1",
			["onetree"],
		);
		expect(database.instance.createDatabase).toHaveBeenCalledWith("onetree");
		expect(database.instance.client.end).toHaveBeenCalledOnce();
	});

	it("reuses an existing application database and delegates lifecycle", async () => {
		const database = createEmbeddedDatabase({
			PostgresClass: FakePostgres,
			access: vi.fn(),
			databaseDir: "C:\\OneTreeData\\database",
			mkdir: vi.fn(),
		});
		database.instance.client.query.mockResolvedValueOnce({ rowCount: 1 });

		await database.start();
		await database.ensureDatabase();
		await database.stop();

		expect(database.instance.createDatabase).not.toHaveBeenCalled();
		expect(database.instance.start).toHaveBeenCalledOnce();
		expect(database.instance.stop).toHaveBeenCalledOnce();
	});
});

describe("createProcessAdapter", () => {
	it("runs migration and starts backend modes with the packaged executable", async () => {
		const spawn = vi.fn(() => successfulChild());
		const adapter = createProcessAdapter({
			backendExecutable: "C:\\OneTree\\backend\\OneTreeRuntime.exe",
			environment: { APP_ENV: "production" },
			logsDir: "C:\\OneTreeData\\logs",
			mkdir: vi.fn(),
			openLog: vi.fn(() => ({ end: vi.fn() })),
			spawn,
		});

		await adapter.runMigration();
		await adapter.startBackend();

		expect(spawn.mock.calls[0][1]).toEqual(["migrate"]);
		expect(spawn.mock.calls[1][1]).toEqual(["serve"]);
		expect(spawn.mock.calls[1][2]).toMatchObject({
			cwd: "C:\\OneTree\\backend",
			env: expect.objectContaining({ APP_ENV: "production" }),
			windowsHide: true,
		});
	});

	it("starts and stops the worker process tree", async () => {
		const workerChild = new EventEmitter();
		workerChild.pid = 41;
		workerChild.exitCode = null;
		const spawn = vi
			.fn()
			.mockReturnValueOnce(workerChild)
			.mockImplementationOnce(() => successfulChild(42));
		const log = { end: vi.fn() };
		const adapter = createProcessAdapter({
			backendExecutable: "C:\\OneTree\\backend\\OneTreeRuntime.exe",
			environment: {},
			logsDir: "C:\\OneTreeData\\logs",
			mkdir: vi.fn(),
			openLog: vi.fn(() => log),
			spawn,
		});

		const worker = await adapter.startWorker();
		await worker.stop();

		expect(spawn.mock.calls[0][1]).toEqual(["worker"]);
		expect(spawn.mock.calls[1][0]).toBe("taskkill.exe");
		expect(log.end).toHaveBeenCalledOnce();
	});
});

describe("waitForBackendHealth", () => {
	it("retries until readiness succeeds", async () => {
		const fetch = vi
			.fn()
			.mockRejectedValueOnce(new Error("not started"))
			.mockResolvedValueOnce({ ok: true });
		const delay = vi.fn();

		await waitForBackendHealth({ attempts: 2, delay, fetch });

		expect(fetch).toHaveBeenCalledTimes(2);
		expect(delay).toHaveBeenCalledOnce();
	});

	it("fails after the configured number of attempts", async () => {
		const fetch = vi.fn().mockResolvedValue({ ok: false });

		await expect(
			waitForBackendHealth({ attempts: 2, delay: vi.fn(), fetch }),
		).rejects.toThrow("OneTree 后端启动超时");
	});
});
