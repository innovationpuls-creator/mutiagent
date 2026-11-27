import { serve } from "@hono/node-server";
import { createApp } from "./app.js";
import { createBackendClient } from "./backendClient.js";
import { ConfigError, loadConfig } from "./config.js";
import { createLogger, formatLogLine, stdoutSink } from "./observability.js";

const logger = createLogger();

let config: ReturnType<typeof loadConfig>;
try {
	config = loadConfig(process.env, (message) => logger.warn(message));
} catch (error) {
	if (error instanceof ConfigError) {
		logger.error(`startup_refused: ${error.message}`);
		process.exit(1);
	}
	throw error;
}

const backend = createBackendClient({
	baseUrl: config.pythonBackendUrl,
	internalToken: config.internalApiToken,
	timeoutMs: config.backendTimeoutMs,
	logger,
});
const app = createApp({ config, backend, logSink: stdoutSink });

const server = serve({ fetch: app.fetch, port: config.port, hostname: config.host }, (info) => {
	stdoutSink(
		formatLogLine({
			message: `gateway_listening address=${info.address} port=${info.port} env=${config.appEnv}`,
		}),
	);
});

const shutdown = () => {
	server.close(() => process.exit(0));
	setTimeout(() => process.exit(0), 5000).unref();
};
process.on("SIGTERM", shutdown);
process.on("SIGINT", shutdown);
