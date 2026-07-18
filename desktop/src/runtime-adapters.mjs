import { createWriteStream } from "node:fs";
import { access as nodeAccess, mkdir as nodeMkdir } from "node:fs/promises";
import path from "node:path";
import { spawn as nodeSpawn } from "node:child_process";

import EmbeddedPostgres from "embedded-postgres";

const DATABASE_NAME = "onetree";
const DATABASE_PORT = 55432;
const HEALTH_URL = "http://127.0.0.1:8000/api/health/ready";

export function createEmbeddedDatabase({
	PostgresClass = EmbeddedPostgres,
	access = nodeAccess,
	databaseDir,
	mkdir = nodeMkdir,
	onError = console.error,
	onLog = console.log,
}) {
	const instance = new PostgresClass({
		authMethod: "scram-sha-256",
		databaseDir,
		initdbFlags: ["--locale=C", "--encoding=UTF8"],
		password: "onetree-desktop",
		persistent: true,
		port: DATABASE_PORT,
		postgresFlags: ["-h", "127.0.0.1"],
		onError,
		onLog,
		user: "onetree",
	});

	return {
		instance,
		async initialise() {
			const versionPath = path.win32.join(databaseDir, "PG_VERSION");
			try {
				await access(versionPath);
			} catch {
				await mkdir(databaseDir, { recursive: true });
				await instance.initialise();
			}
		},
		start: () => instance.start(),
		stop: () => instance.stop(),
		async ensureDatabase() {
			const client = instance.getPgClient("postgres", "127.0.0.1");
			try {
				await client.connect();
				const result = await client.query(
					"SELECT 1 FROM pg_database WHERE datname = $1",
					[DATABASE_NAME],
				);
				if (result.rowCount === 0) {
					await instance.createDatabase(DATABASE_NAME);
				}
			} finally {
				await client.end();
			}
		},
	};
}

export function createProcessAdapter({
	backendExecutable,
	environment,
	logsDir,
	mkdir = nodeMkdir,
	openLog = createWriteStream,
	spawn = nodeSpawn,
}) {
	const workingDirectory = path.win32.dirname(backendExecutable);

	async function spawnRuntime(mode, logName) {
		await mkdir(logsDir, { recursive: true });
		const log = openLog(path.win32.join(logsDir, logName), { flags: "a" });
		const child = spawn(backendExecutable, [mode], {
			cwd: workingDirectory,
			env: { ...process.env, ...environment },
			stdio: ["ignore", log, log],
			windowsHide: true,
		});
		return { child, exitPromise: waitForExit(child), log };
	}

	function waitForExit(child) {
		return new Promise((resolve, reject) => {
			child.once("error", reject);
			child.once("exit", (code, signal) => {
				if (code === 0) {
					resolve();
					return;
				}
				reject(
					new Error(
						`OneTree 运行进程异常退出: code=${code ?? "null"}, signal=${signal ?? "null"}`,
					),
				);
			});
		});
	}

	function processHandle(child, log) {
		return {
			async stop() {
				if (child.exitCode === null && child.pid !== undefined) {
					const taskkill = spawn(
						"taskkill.exe",
						["/pid", String(child.pid), "/t", "/f"],
						{ windowsHide: true },
					);
					await waitForExit(taskkill).catch(() => undefined);
				}
				log.end();
			},
		};
	}

	return {
		async runMigration() {
			const { exitPromise, log } = await spawnRuntime(
				"migrate",
				"migration.log",
			);
			try {
				await exitPromise;
			} finally {
				log.end();
			}
		},
		async startBackend() {
			const { child, log } = await spawnRuntime("serve", "backend.log");
			return processHandle(child, log);
		},
		async startWorker() {
			const { child, log } = await spawnRuntime("worker", "worker.log");
			return processHandle(child, log);
		},
	};
}

export async function waitForBackendHealth({
	attempts = 120,
	delay = (milliseconds) =>
		new Promise((resolve) => setTimeout(resolve, milliseconds)),
	fetch = globalThis.fetch,
} = {}) {
	for (let attempt = 0; attempt < attempts; attempt += 1) {
		try {
			const response = await fetch(HEALTH_URL);
			if (response.ok) {
				return;
			}
		} catch {
			// The server is expected to refuse connections while it starts.
		}
		if (attempt < attempts - 1) {
			await delay(500);
		}
	}
	throw new Error("OneTree 后端启动超时");
}
