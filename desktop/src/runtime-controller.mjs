export const DESKTOP_URL = "http://127.0.0.1:8000";

export function createRuntimeController({ database, processes, waitForHealth }) {
	let backend = null;
	let worker = null;
	let databaseStarted = false;
	let stopPromise = null;

	async function stopStartedComponents() {
		if (worker !== null) {
			await worker.stop();
			worker = null;
		}
		if (backend !== null) {
			await backend.stop();
			backend = null;
		}
		if (databaseStarted) {
			await database.stop();
			databaseStarted = false;
		}
	}

	return {
		async start() {
			try {
				await database.initialise();
				await database.start();
				databaseStarted = true;
				await database.ensureDatabase();
				await processes.runMigration();
				backend = await processes.startBackend();
				await waitForHealth();
				worker = await processes.startWorker();
				return { url: DESKTOP_URL };
			} catch (error) {
				await stopStartedComponents();
				throw error;
			}
		},

		async stop() {
			if (stopPromise === null) {
				stopPromise = stopStartedComponents();
			}
			await stopPromise;
		},
	};
}
