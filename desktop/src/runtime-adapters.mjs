import { createWriteStream } from "node:fs";
import { access as nodeAccess, mkdir as nodeMkdir } from "node:fs/promises";
import path from "node:path";
import { spawn as nodeSpawn } from "node:child_process";

import EmbeddedPostgres from "embedded-postgres";

const DATABASE_NAME = "onetree";
const DATABASE_PORT = 55432;
const HEALTH_URL = "http://127.0.0.1:8000/api/health/ready";
const WINDOWS_POSTGRES_PACKAGE = "@embedded-postgres/windows-x64";

async function loadWindowsPostgresControl() {
	const binaries = await import(WINDOWS_POSTGRES_PACKAGE);
	return binaries.pg_ctl;
}

export function createEmbeddedDatabase({
	PostgresClass = EmbeddedPostgres,
	access = nodeAccess,
	databaseDir,
	loadPostgresControl = loadWindowsPostgresControl,
	mkdir = nodeMkdir,
	onError = console.error,
	onLog = console.log,
	platform = process.platform,
	postgresLogPath = path.win32.join(databaseDir, "postgres.log"),
	spawn = nodeSpawn,
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

	async function runPostgresControl(command, arguments_) {
		const postgresControl = await loadPostgresControl();
		const child = spawn(postgresControl, [command, ...arguments_], {
			windowsHide: true,
		});
		await new Promise((resolve, reject) => {
			let errorOutput = "";
			child.stdout?.on("data", (chunk) => onLog(chunk.toString("utf8")));
			child.stderr?.on("data", (chunk) => {
				const message = chunk.toString("utf8");
				errorOutput += message;
				onError(message);
			});
			child.once("error", reject);
			child.once("exit", (code, signal) => {
				if (code === 0) {
					resolve();
					return;
				}
				reject(
					new Error(
						`pg_ctl ${command} 失败: code=${code ?? "null"}, signal=${signal ?? "null"}${errorOutput ? `, stderr=${errorOutput.trim()}` : ""}`,
					),
				);
			});
		});
	}

	async function start() {
		if (platform !== "win32") {
			return instance.start();
		}
		await mkdir(path.win32.dirname(postgresLogPath), { recursive: true });
		await runPostgresControl("start", [
			"-D",
			databaseDir,
			"-l",
			postgresLogPath,
			"-o",
			`-p ${DATABASE_PORT} -h 127.0.0.1`,
			"-w",
			"-t",
			"60",
		]);
	}

	async function stop() {
		if (platform !== "win32") {
			return instance.stop();
		}
		await runPostgresControl("stop", [
			"-D",
			databaseDir,
			"-m",
			"fast",
			"-w",
			"-t",
			"60",
		]);
	}

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
		start,
		stop,
		async ensureDatabase() {
			const client = instance.getPgClient("postgres", "127.0.0.1");
			try {
				await client.connect();
				const result = await client.query(
					"SELECT 1 FROM pg_database WHERE datname = $1",
					[DATABASE_NAME],
				);
				if (result.rowCount === 0) {
					await client.query('CREATE DATABASE "onetree"');
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

	async function waitForLogOpen(log) {
		if (typeof log.fd === "number") {
			return;
		}
		await new Promise((resolve, reject) => {
			function cleanup() {
				log.off("open", handleOpen);
				log.off("error", handleError);
			}
			function handleOpen() {
				cleanup();
				resolve();
			}
			function handleError(error) {
				cleanup();
				reject(error);
			}
			log.once("open", handleOpen);
			log.once("error", handleError);
		});
	}

	async function spawnRuntime(mode, logName) {
		await mkdir(logsDir, { recursive: true });
		const log = openLog(path.win32.join(logsDir, logName), { flags: "a" });
		await waitForLogOpen(log);
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
