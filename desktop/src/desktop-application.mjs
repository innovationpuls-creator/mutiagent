import path from "node:path";

import { resolveRuntimePaths } from "./runtime-environment.mjs";

export async function startDesktopApplication({
	BrowserWindow,
	app,
	buildEnvironment,
		createController,
		createDatabase,
		createLogger,
		createProcesses,
	dialog,
	loadBuildConfiguration,
	loadJwtSecret,
	resourcesPath,
	waitForHealth,
}) {
	if (!app.requestSingleInstanceLock()) {
		app.quit();
		return null;
	}

	await app.whenReady();
	const userDataPath = app.getPath("userData");
	const runtimePaths = resolveRuntimePaths({ resourcesPath, userDataPath });
	const logger = createLogger(runtimePaths.logsDir);
	logger.info("OneTree desktop runtime starting");
	const buildConfiguration = await loadBuildConfiguration(
		path.win32.join(resourcesPath, "runtime-config.json"),
	);
	const jwtSecret = await loadJwtSecret(
		path.win32.join(userDataPath, "settings.json"),
	);
	const environment = buildEnvironment({
		...buildConfiguration,
		frontendDist: runtimePaths.frontendDist,
		jwtSecret,
		uploadsDir: runtimePaths.uploadsDir,
	});
	const database = createDatabase({
		databaseDir: runtimePaths.postgresDataDir,
		onError: (message) => logger.error(message),
		onLog: (message) => logger.info(message),
		postgresLogPath: path.win32.join(runtimePaths.logsDir, "postgres.log"),
	});
	const processes = createProcesses({
		backendExecutable: runtimePaths.backendExecutable,
		environment,
		logsDir: runtimePaths.logsDir,
	});
	const controller = createController({ database, processes, waitForHealth });
	const window = new BrowserWindow({
		height: 900,
		icon: path.win32.join(resourcesPath, "logo.png"),
		minHeight: 720,
		minWidth: 1100,
		show: false,
		title: "OneTree",
		webPreferences: {
			contextIsolation: true,
			nodeIntegration: false,
			sandbox: true,
		},
		width: 1440,
	});
	window.webContents.setWindowOpenHandler(() => ({ action: "deny" }));

	let shutdownFinished = false;
	let shutdownPromise = null;
	app.on("before-quit", (event) => {
		if (shutdownFinished) {
			return;
		}
		event.preventDefault();
		if (shutdownPromise === null) {
			shutdownPromise = controller.stop().finally(() => {
				shutdownFinished = true;
				app.quit();
			});
		}
	});
	app.on("window-all-closed", () => app.quit());
	app.on("second-instance", () => {
		if (window.isMinimized()) {
			window.restore();
		}
		window.focus();
	});

	try {
		const { url } = await controller.start();
		await window.loadURL(url);
		window.show();
		return { controller, window };
	} catch (error) {
		logger.error(error);
		await controller.stop();
		const message = error instanceof Error ? error.message : String(error);
		dialog.showErrorBox("OneTree 启动失败", message);
		throw error;
	}
}
