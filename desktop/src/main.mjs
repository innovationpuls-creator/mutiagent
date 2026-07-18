import { app, BrowserWindow, dialog } from "electron";

import { startDesktopApplication } from "./desktop-application.mjs";
import {
	createEmbeddedDatabase,
	createProcessAdapter,
	waitForBackendHealth,
} from "./runtime-adapters.mjs";
import { createRuntimeLogger } from "./runtime-logger.mjs";
import { loadBuildConfiguration, loadOrCreateJwtSecret } from "./runtime-config.mjs";
import { createRuntimeController } from "./runtime-controller.mjs";
import { buildBackendEnvironment } from "./runtime-environment.mjs";

app.setName("OneTree");

startDesktopApplication({
	BrowserWindow,
	app,
	buildEnvironment: buildBackendEnvironment,
	createController: createRuntimeController,
	createDatabase: createEmbeddedDatabase,
	createLogger: createRuntimeLogger,
	createProcesses: createProcessAdapter,
	dialog,
	loadBuildConfiguration,
	loadJwtSecret: loadOrCreateJwtSecret,
	resourcesPath: process.resourcesPath,
	waitForHealth: waitForBackendHealth,
}).catch(() => {
	app.exit(1);
});
