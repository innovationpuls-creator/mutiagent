export const SERVICE_NAME = "onetree-ai-gateway";
export const DEFAULT_JWT_SECRET = "mutiagent-dev-secret-key-change-in-production";
export const DEFAULT_INTERNAL_API_TOKEN =
	"mutiagent-dev-internal-token-change-in-production";
export const DEFAULT_PYTHON_BACKEND_URL = "http://127.0.0.1:8000";
export const DEFAULT_PORT = 8100;
const DEVELOPMENT_ORIGINS = ["http://127.0.0.1:5173", "http://localhost:5173"];

export interface GatewayConfig {
	appEnv: string;
	isProduction: boolean;
	host: string;
	port: number;
	jwtSecret: string;
	pythonBackendUrl: string;
	internalApiToken: string;
	allowedOrigins: string[];
	backendTimeoutMs: number;
	sseHeartbeatMs: number;
	/** Optional platform web search/fetch service used by agent tools. */
	webSearchBaseUrl?: string;
	webSearchApiKey?: string;
	/** Web search/fetch calls one user may make per rolling 24h. */
	webSearchDailyLimitPerUser: number;
}

export class ConfigError extends Error {
	constructor(message: string) {
		super(message);
		this.name = "ConfigError";
	}
}

type Env = Record<string, string | undefined>;

function optional(env: Env, key: string): string | undefined {
	const value = env[key]?.trim();
	return value ? value : undefined;
}

function positiveInt(env: Env, key: string, fallback: number): number {
	const raw = optional(env, key);
	if (raw === undefined) return fallback;
	const value = Number(raw);
	if (!Number.isInteger(value) || value <= 0) {
		throw new ConfigError(`${key} 必须是正整数`);
	}
	return value;
}

export function loadConfig(
	env: Env = process.env,
	warn: (message: string) => void = (message) => console.warn(message),
): GatewayConfig {
	const appEnv = (optional(env, "APP_ENV") ?? "development").toLowerCase();
	const isProduction = appEnv === "production";
	const jwtSecret = optional(env, "JWT_SECRET");
	const internalApiToken = optional(env, "INTERNAL_API_TOKEN");
	const pythonBackendUrl = optional(env, "PYTHON_BACKEND_URL");

	if (isProduction) {
		const missing = [
			["JWT_SECRET", jwtSecret],
			["INTERNAL_API_TOKEN", internalApiToken],
			["PYTHON_BACKEND_URL", pythonBackendUrl],
		]
			.filter(([, value]) => !value)
			.map(([key]) => key);
		if (missing.length > 0) {
			throw new ConfigError(`生产环境缺少 ${missing.join("、")}`);
		}
		if (jwtSecret === DEFAULT_JWT_SECRET) {
			throw new ConfigError("生产环境不能使用默认 JWT_SECRET");
		}
		if (internalApiToken === DEFAULT_INTERNAL_API_TOKEN) {
			throw new ConfigError("生产环境不能使用默认 INTERNAL_API_TOKEN");
		}
	} else if (!internalApiToken) {
		warn(
			"INTERNAL_API_TOKEN 未配置，开发环境使用默认内部令牌；生产环境必须显式配置",
		);
	}

	const allowedOrigins = (optional(env, "ALLOWED_ORIGINS") ?? "")
		.split(",")
		.map((origin) => origin.trim())
		.filter(Boolean);

	return {
		appEnv,
		isProduction,
		host: optional(env, "HOST") ?? (isProduction ? "0.0.0.0" : "127.0.0.1"),
		port: positiveInt(env, "PORT", DEFAULT_PORT),
		jwtSecret: jwtSecret ?? DEFAULT_JWT_SECRET,
		pythonBackendUrl: (pythonBackendUrl ?? DEFAULT_PYTHON_BACKEND_URL).replace(
			/\/+$/,
			"",
		),
		internalApiToken: internalApiToken ?? DEFAULT_INTERNAL_API_TOKEN,
		allowedOrigins:
			isProduction || allowedOrigins.length > 0
				? allowedOrigins
				: DEVELOPMENT_ORIGINS,
		backendTimeoutMs: positiveInt(env, "BACKEND_TIMEOUT_MS", 5000),
		sseHeartbeatMs: positiveInt(env, "SSE_HEARTBEAT_MS", 15000),
		webSearchBaseUrl: optional(env, "WEB_SEARCH_BASE_URL"),
		webSearchApiKey: optional(env, "WEB_SEARCH_API_KEY"),
		webSearchDailyLimitPerUser: positiveInt(env, "WEB_SEARCH_DAILY_LIMIT_PER_USER", 200),
	};
}
