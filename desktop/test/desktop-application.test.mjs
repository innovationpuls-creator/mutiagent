import { EventEmitter } from "node:events";

import { describe, expect, it, vi } from "vitest";

import { startDesktopApplication } from "../src/desktop-application.mjs";

class FakeWindow extends EventEmitter {
	constructor(options) {
		super();
		this.options = options;
		this.loadURL = vi.fn();
		this.show = vi.fn();
		this.focus = vi.fn();
		this.isMinimized = vi.fn(() => false);
		this.restore = vi.fn();
		this.webContents = {
			setWindowOpenHandler: vi.fn(),
		};
	}
}

function createHarness() {
	const app = new EventEmitter();
	app.getPath = vi.fn(() => "C:\\Users\\judge\\AppData\\Roaming\\OneTree");
	app.quit = vi.fn();
	app.requestSingleInstanceLock = vi.fn(() => true);
	app.whenReady = vi.fn();
	const controller = {
		start: vi.fn(async () => ({ url: "http://127.0.0.1:8000" })),
		stop: vi.fn(async () => undefined),
	};
	const BrowserWindow = vi.fn(function BrowserWindow(options) {
		return new FakeWindow(options);
	});
	const dependencies = {
		BrowserWindow,
		app,
		buildEnvironment: vi.fn(() => ({ APP_ENV: "production" })),
		createController: vi.fn(() => controller),
		createDatabase: vi.fn(() => ({ database: true })),
		createLogger: vi.fn(() => ({ error: vi.fn(), info: vi.fn() })),
		createProcesses: vi.fn(() => ({ processes: true })),
		dialog: { showErrorBox: vi.fn() },
		loadBuildConfiguration: vi.fn(async () => ({
			apiKey: "competition-key",
			model: "configured-model",
		})),
		loadJwtSecret: vi.fn(async () => "jwt-secret"),
		resourcesPath: "C:\\OneTree\\resources",
		waitForHealth: vi.fn(),
	};
	return { BrowserWindow, app, controller, dependencies };
}

describe("startDesktopApplication", () => {
	it("starts the local runtime before showing the desktop window", async () => {
		const harness = createHarness();

		const result = await startDesktopApplication(harness.dependencies);

		expect(harness.controller.start).toHaveBeenCalledOnce();
		expect(result.window.loadURL).toHaveBeenCalledWith(
			"http://127.0.0.1:8000",
		);
		expect(result.window.show).toHaveBeenCalledOnce();
		expect(harness.dependencies.createDatabase).toHaveBeenCalledWith(
			expect.objectContaining({
				postgresLogPath:
					"C:\\Users\\judge\\AppData\\Roaming\\OneTree\\logs\\postgres.log",
			}),
		);
		expect(harness.BrowserWindow).toHaveBeenCalledWith(
			expect.objectContaining({
				height: 900,
				show: false,
				webPreferences: {
					contextIsolation: true,
					nodeIntegration: false,
					sandbox: true,
				},
				width: 1440,
			}),
		);
	});

	it("quits immediately when another OneTree instance owns the lock", async () => {
		const harness = createHarness();
		harness.app.requestSingleInstanceLock.mockReturnValueOnce(false);

		await expect(
			startDesktopApplication(harness.dependencies),
		).resolves.toBeNull();

		expect(harness.app.quit).toHaveBeenCalledOnce();
		expect(harness.controller.start).not.toHaveBeenCalled();
	});

	it("reports startup errors and stops partially started services", async () => {
		const harness = createHarness();
		harness.controller.start.mockRejectedValueOnce(new Error("startup failed"));

		await expect(
			startDesktopApplication(harness.dependencies),
		).rejects.toThrow("startup failed");

		expect(harness.controller.stop).toHaveBeenCalledOnce();
		expect(harness.dependencies.dialog.showErrorBox).toHaveBeenCalledWith(
			"OneTree 启动失败",
			"startup failed",
		);
		const logger = harness.dependencies.createLogger.mock.results[0].value;
		expect(logger.error).toHaveBeenCalledWith(expect.any(Error));
	});

	it("focuses the existing window for a second launch", async () => {
		const harness = createHarness();
		const result = await startDesktopApplication(harness.dependencies);
		result.window.isMinimized.mockReturnValueOnce(true);

		harness.app.emit("second-instance");

		expect(result.window.restore).toHaveBeenCalledOnce();
		expect(result.window.focus).toHaveBeenCalledOnce();
	});

	it("focuses a visible existing window without restoring it", async () => {
		const harness = createHarness();
		const result = await startDesktopApplication(harness.dependencies);

		harness.app.emit("second-instance");

		expect(result.window.restore).not.toHaveBeenCalled();
		expect(result.window.focus).toHaveBeenCalledOnce();
	});

	it("stops runtime services before quitting", async () => {
		const harness = createHarness();
		await startDesktopApplication(harness.dependencies);
		const event = { preventDefault: vi.fn() };

		harness.app.emit("before-quit", event);
		await vi.waitFor(() => expect(harness.controller.stop).toHaveBeenCalledOnce());

		expect(event.preventDefault).toHaveBeenCalledOnce();
		expect(harness.app.quit).toHaveBeenCalledOnce();
	});

	it("quits when the desktop window is closed", async () => {
		const harness = createHarness();
		await startDesktopApplication(harness.dependencies);

		harness.app.emit("window-all-closed");

		expect(harness.app.quit).toHaveBeenCalledOnce();
	});
});
