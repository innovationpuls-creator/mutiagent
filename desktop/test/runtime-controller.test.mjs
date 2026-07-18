import { describe, expect, it, vi } from "vitest";

import { createRuntimeController } from "../src/runtime-controller.mjs";

function createHarness() {
	const calls = [];
	const backend = { stop: vi.fn(async () => calls.push("stop:backend")) };
	const worker = { stop: vi.fn(async () => calls.push("stop:worker")) };
	const database = {
		initialise: vi.fn(async () => calls.push("database:initialise")),
		start: vi.fn(async () => calls.push("database:start")),
		ensureDatabase: vi.fn(async () => calls.push("database:ensure")),
		stop: vi.fn(async () => calls.push("database:stop")),
	};
	const processes = {
		runMigration: vi.fn(async () => calls.push("migration:run")),
		startBackend: vi.fn(async () => {
			calls.push("backend:start");
			return backend;
		}),
		startWorker: vi.fn(async () => {
			calls.push("worker:start");
			return worker;
		}),
	};
	const waitForHealth = vi.fn(async () => calls.push("health:ready"));

	return { backend, calls, database, processes, waitForHealth, worker };
}

describe("createRuntimeController", () => {
	it("starts every runtime component in dependency order", async () => {
		const harness = createHarness();
		const controller = createRuntimeController(harness);

		await expect(controller.start()).resolves.toEqual({
			url: "http://127.0.0.1:8000",
		});
		expect(harness.calls).toEqual([
			"database:initialise",
			"database:start",
			"database:ensure",
			"migration:run",
			"backend:start",
			"health:ready",
			"worker:start",
		]);
	});

	it("stops child processes before the database", async () => {
		const harness = createHarness();
		const controller = createRuntimeController(harness);
		await controller.start();
		harness.calls.length = 0;

		await controller.stop();

		expect(harness.calls).toEqual([
			"stop:worker",
			"stop:backend",
			"database:stop",
		]);
	});

	it("cleans up components when startup fails", async () => {
		const harness = createHarness();
		harness.waitForHealth.mockRejectedValueOnce(new Error("backend unavailable"));
		const controller = createRuntimeController(harness);

		await expect(controller.start()).rejects.toThrow("backend unavailable");
		expect(harness.backend.stop).toHaveBeenCalledOnce();
		expect(harness.worker.stop).not.toHaveBeenCalled();
		expect(harness.database.stop).toHaveBeenCalledOnce();
	});

	it("makes repeated stop calls safe", async () => {
		const harness = createHarness();
		const controller = createRuntimeController(harness);
		await controller.start();

		await controller.stop();
		await controller.stop();

		expect(harness.worker.stop).toHaveBeenCalledOnce();
		expect(harness.backend.stop).toHaveBeenCalledOnce();
		expect(harness.database.stop).toHaveBeenCalledOnce();
	});
});
