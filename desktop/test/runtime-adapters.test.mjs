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

function failedCommandChild() {
	const child = new EventEmitter();
	child.stdout = new EventEmitter();
	child.stderr = new EventEmitter();
	queueMicrotask(() => {
		child.stdout.emit("data", Buffer.from("pg_ctl starting"));
		child.stderr.emit("data", Buffer.from("pg_ctl failed"));
		child.emit("exit", 1, null);
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
			platform: "darwin",
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
		expect(database.instance.client.query).toHaveBeenNthCalledWith(
			2,
			'CREATE DATABASE "onetree"',
		);
		expect(database.instance.createDatabase).not.toHaveBeenCalled();
		expect(database.instance.client.end).toHaveBeenCalledOnce();
	});

	it("reuses an existing application database and delegates lifecycle", async () => {
		const database = createEmbeddedDatabase({
			PostgresClass: FakePostgres,
			access: vi.fn(),
			databaseDir: "C:\\OneTreeData\\database",
			mkdir: vi.fn(),
			platform: "darwin",
		});
		database.instance.client.query.mockResolvedValueOnce({ rowCount: 1 });

		await database.start();
		await database.ensureDatabase();
		await database.stop();

		expect(database.instance.createDatabase).not.toHaveBeenCalled();
		expect(database.instance.start).toHaveBeenCalledOnce();
		expect(database.instance.stop).toHaveBeenCalledOnce();
	});

	it("starts and stops Windows PostgreSQL through pg_ctl", async () => {
		const spawn = vi.fn(() => successfulChild());
		const loadPostgresControl = vi.fn(async () =>
			"C:\\OneTree\\postgres\\pg_ctl.exe",
		);
		const database = createEmbeddedDatabase({
			PostgresClass: FakePostgres,
			access: vi.fn(),
			databaseDir: "C:\\OneTreeData\\database",
			loadPostgresControl,
			mkdir: vi.fn(),
			platform: "win32",
			postgresLogPath: "C:\\OneTreeData\\logs\\postgres.log",
			spawn,
		});

		await database.start();
		await database.stop();

		expect(loadPostgresControl).toHaveBeenCalledTimes(2);
		expect(spawn).toHaveBeenNthCalledWith(
			1,
			"C:\\OneTree\\postgres\\pg_ctl.exe",
			[
				"start",
				"-D",
				"C:\\OneTreeData\\database",
				"-l",
				"C:\\OneTreeData\\logs\\postgres.log",
				"-o",
				"-p 55432 -h 127.0.0.1",
				"-w",
				"-t",
				"60",
			],
			{ windowsHide: true },
		);
		expect(spawn).toHaveBeenNthCalledWith(
			2,
			"C:\\OneTree\\postgres\\pg_ctl.exe",
			[
				"stop",
				"-D",
				"C:\\OneTreeData\\database",
				"-m",
				"fast",
				"-w",
				"-t",
				"60",
			],
			{ windowsHide: true },
		);
		expect(database.instance.start).not.toHaveBeenCalled();
		expect(database.instance.stop).not.toHaveBeenCalled();
	});

	it("reports pg_ctl output and non-zero exits", async () => {
		const onError = vi.fn();
		const onLog = vi.fn();
		const database = createEmbeddedDatabase({
			PostgresClass: FakePostgres,
			access: vi.fn(),
			databaseDir: "C:\\OneTreeData\\database",
			loadPostgresControl: vi.fn(async () => "C:\\Postgres\\pg_ctl.exe"),
			mkdir: vi.fn(),
			onError,
			onLog,
			platform: "win32",
			postgresLogPath: "C:\\OneTreeData\\logs\\postgres.log",
			spawn: vi.fn(() => failedCommandChild()),
		});

		await expect(database.start()).rejects.toThrow(
			"pg_ctl start 失败: code=1, signal=null, stderr=pg_ctl failed",
		);
		expect(onLog).toHaveBeenCalledWith("pg_ctl starting");
		expect(onError).toHaveBeenCalledWith("pg_ctl failed");
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
			openLog: vi.fn(() => ({ end: vi.fn(), fd: 1 })),
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

	it("waits for the runtime log file before spawning a process", async () => {
		const log = new EventEmitter();
		log.end = vi.fn();
		log.fd = null;
		const openLog = vi.fn(() => log);
		const spawn = vi.fn(() => successfulChild());
		const adapter = createProcessAdapter({
			backendExecutable: "C:\\OneTree\\backend\\OneTreeRuntime.exe",
			environment: {},
			logsDir: "C:\\OneTreeData\\logs",
			mkdir: vi.fn(),
			openLog,
			spawn,
		});

		const backendPromise = adapter.startBackend();
		await vi.waitFor(() => expect(openLog).toHaveBeenCalledOnce());
		expect(spawn).not.toHaveBeenCalled();

		log.fd = 42;
		log.emit("open", 42);
		await backendPromise;

		expect(spawn).toHaveBeenCalledOnce();
	});

	it("starts and stops the worker process tree", async () => {
		const workerChild = new EventEmitter();
		workerChild.pid = 41;
		workerChild.exitCode = null;
		const spawn = vi
			.fn()
			.mockReturnValueOnce(workerChild)
			.mockImplementationOnce(() => successfulChild(42));
		const log = { end: vi.fn(), fd: 1 };
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
