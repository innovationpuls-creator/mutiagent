import { Hono } from "hono";
import { cors } from "hono/cors";
import { type AuthVariables, jwtAuth } from "./auth.js";
import type { BackendClient } from "./backendClient.js";
import { SERVICE_NAME, type GatewayConfig } from "./config.js";
import { BackendBusinessError, GatewayError } from "./errors.js";
import { requireInternalToken } from "./internalAuth.js";
import {
	type LogSink,
	REQUEST_ID_HEADER,
	createLogger,
	getRequestId,
	requestIdMiddleware,
	stdoutSink,
} from "./observability.js";

export interface AppDeps {
	config: GatewayConfig;
	backend: BackendClient;
	logSink?: LogSink;
}

export function createApp({ config, backend, logSink = stdoutSink }: AppDeps) {
	const app = new Hono<{ Variables: AuthVariables }>();
	const logger = createLogger(logSink);

	app.use("*", requestIdMiddleware(logSink));
	app.use(
		"*",
		cors({
			origin: config.allowedOrigins,
			credentials: true,
			allowHeaders: ["Authorization", "Content-Type", "Accept", REQUEST_ID_HEADER],
			exposeHeaders: [REQUEST_ID_HEADER],
		}),
	);

	app.get("/api/ai/health/live", (c) => c.json({ status: "ok" }));

	app.get("/api/ai/health/ready", async (c) => {
		try {
			await backend.getInternalHealth();
		} catch {
			return c.json({ status: "error", backend: "unavailable" }, 503);
		}
		return c.json({ status: "ok", backend: "connected" });
	});

	// M1 acceptance probe: JWT verify + Python user check + request-id propagation.
	app.get("/api/ai/ping-auth", jwtAuth(config.jwtSecret, backend), (c) => {
		const { userUid, role } = c.get("auth");
		return c.json({
			status: "ok",
			service: SERVICE_NAME,
			user_uid: userUid,
			role,
			request_id: getRequestId() ?? null,
		});
	});

	// Python -> gateway channel (used from M2 on); same constant-time token check.
	app.use("/internal/*", requireInternalToken(config.internalApiToken));
	app.get("/internal/health", (c) => c.json({ status: "ok" }));

	app.onError((error, c) => {
		if (error instanceof GatewayError) {
			return c.json(error.toBody(), error.status as 401 | 403 | 422 | 428 | 503);
		}
		if (error instanceof BackendBusinessError) {
			return c.json(
				{ detail: error.detail },
				error.status as 400 | 404 | 409 | 422 | 428,
			);
		}
		logger.error(`unhandled_error name=${error instanceof Error ? error.name : "unknown"}`);
		return c.json({ detail: "服务内部错误，请稍后重试" }, 500);
	});
	app.notFound((c) => c.json({ detail: "Not Found" }, 404));

	return app;
}
