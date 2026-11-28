import { Hono } from "hono";
import { cors } from "hono/cors";
import { type AuthVariables, jwtAuth } from "./auth.js";
import type { BackendClient } from "./backendClient.js";
import { SERVICE_NAME, type GatewayConfig } from "./config.js";
import { BackendBusinessError, GatewayError } from "./errors.js";
import { requireInternalToken } from "./internalAuth.js";
import { chatRoutes } from "./chat/routes.js";
import { aiStreamRoutes, internalAiRoutes } from "./ai/routes.js";
import { OAuthSessions } from "./models/oauth.js";
import { internalModelRoutes, modelRoutes } from "./models/routes.js";
import { ModelRuntime } from "./models/runtime.js";
import type { Provider } from "@earendil-works/pi-ai";
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
	/** Replaces Pi built-in providers (tests / acceptance harness only). */
	builtinOverride?: Provider[];
	runtime?: ModelRuntime;
}

export function createApp({ config, backend, logSink = stdoutSink, builtinOverride, runtime }: AppDeps) {
	const app = new Hono<{ Variables: AuthVariables }>();
	const logger = createLogger(logSink);
	const modelRuntime = runtime ?? new ModelRuntime({ backend, logger, builtinOverride });
	const oauth = new OAuthSessions(modelRuntime);

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
	app.route("/internal", internalModelRoutes({ runtime: modelRuntime, builtinOverride }));
	app.route("/internal/ai", internalAiRoutes({ runtime: modelRuntime }));
	app.route(
		"/api/ai",
		modelRoutes({ jwtSecret: config.jwtSecret, backend, runtime: modelRuntime, oauth, builtinOverride }),
	);

	// Takes over POST /api/chat/message from Python (M4); /start and /sessions stay there.
	app.route(
		"/api/chat",
		chatRoutes({
			jwtSecret: config.jwtSecret,
			backend,
			runtime: modelRuntime,
			logger,
			heartbeatMs: config.sseHeartbeatMs,
		}),
	);

	// M8: Forest AI answers and the growth report stream are orchestrated here too.
	app.route(
		"/api",
		aiStreamRoutes({
			jwtSecret: config.jwtSecret,
			backend,
			runtime: modelRuntime,
			logger,
			heartbeatMs: config.sseHeartbeatMs,
			web: { baseUrl: config.webSearchBaseUrl, apiKey: config.webSearchApiKey },
		}),
	);

	app.onError((error, c) => {
		if (error instanceof GatewayError) {
			return c.json(error.toBody(), error.status as 400 | 401 | 403 | 422 | 428 | 502 | 503);
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
