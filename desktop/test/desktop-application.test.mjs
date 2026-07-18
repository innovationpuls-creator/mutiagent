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
		stop: vi.fn(),
	};
	const BrowserWindow = vi.fn((options) => new FakeWindow(options));
	const dependencies = {
		BrowserWindow,
		app,
		buildEnvironment: vi.fn(() => ({ APP_ENV: "production" })),
		createController: vi.fn(() => controller),
		createDatabase: vi.fn(() => ({ database: true })),
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
	});
});
