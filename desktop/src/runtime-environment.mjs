import path from "node:path";

const DATABASE_URL =
	"postgresql://onetree:onetree-desktop@127.0.0.1:55432/onetree";
const DESKTOP_ORIGIN = "http://127.0.0.1:8000";
const DEFAULT_LLM_BASE_URL =
	"https://dashscope.aliyuncs.com/compatible-mode/v1";

export function resolveRuntimePaths({ resourcesPath, userDataPath }) {
	return {
		backendExecutable: path.win32.join(
			resourcesPath,
			"backend",
			"OneTreeRuntime.exe",
		),
		frontendDist: path.win32.join(resourcesPath, "frontend"),
		logsDir: path.win32.join(userDataPath, "logs"),
		postgresDataDir: path.win32.join(userDataPath, "database"),
		uploadsDir: path.win32.join(userDataPath, "knowledge-base-uploads"),
	};
}

export function buildBackendEnvironment({
	apiKey,
	frontendDist,
	jwtSecret,
	model,
	uploadsDir,
}) {
	return {
		ALLOWED_ORIGINS: DESKTOP_ORIGIN,
		APP_ENV: "production",
		DATABASE_URL,
		JWT_SECRET: jwtSecret,
		KNOWLEDGE_BASE_UPLOAD_DIR: uploadsDir,
		LLM_API_KEY: apiKey,
		LLM_BASE_URL: DEFAULT_LLM_BASE_URL,
		LLM_MODEL: model,
		ONETREE_FRONTEND_DIST: frontendDist,
	};
}
