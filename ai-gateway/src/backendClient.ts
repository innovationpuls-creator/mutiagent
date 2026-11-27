import { BackendBusinessError, internalServiceUnavailable } from "./errors.js";
import { INTERNAL_TOKEN_HEADER } from "./internalAuth.js";
import { type Logger, REQUEST_ID_HEADER, getRequestId } from "./observability.js";

export interface UserAuthStatus {
	user_uid: string;
	exists: boolean;
	role: string | null;
	is_active: boolean;
}

export interface BackendHealth {
	status: string;
	database: string;
}

export interface BackendClient {
	getInternalHealth(): Promise<BackendHealth>;
	getUserAuthStatus(userUid: string): Promise<UserAuthStatus>;
}

export interface BackendClientOptions {
	baseUrl: string;
	internalToken: string;
	timeoutMs: number;
	logger: Logger;
	fetchImpl?: typeof fetch;
}

async function readDetail(response: Response): Promise<string> {
	try {
		const body = (await response.json()) as { detail?: unknown };
		if (typeof body.detail === "string") return body.detail;
	} catch {
		// fall through
	}
	return `后端请求失败（${response.status}）`;
}

export function createBackendClient(options: BackendClientOptions): BackendClient {
	const { baseUrl, internalToken, timeoutMs, logger } = options;
	const fetchImpl = options.fetchImpl ?? fetch;

	async function request<T>(path: string): Promise<T> {
		const headers: Record<string, string> = {
			Accept: "application/json",
			[INTERNAL_TOKEN_HEADER]: internalToken,
		};
		const requestId = getRequestId();
		if (requestId) headers[REQUEST_ID_HEADER] = requestId;

		let response: Response;
		try {
			response = await fetchImpl(`${baseUrl}${path}`, {
				method: "GET",
				headers,
				signal: AbortSignal.timeout(timeoutMs),
			});
		} catch (error) {
			const reason = error instanceof Error ? error.name : "unknown";
			logger.warn(`python_backend_unreachable path=${path} reason=${reason}`);
			throw internalServiceUnavailable();
		}

		if (response.status === 401 || response.status === 403) {
			// Token mismatch between services is an operator error, never a user one.
			logger.error(`python_backend_rejected_internal_token path=${path} status=${response.status}`);
			throw internalServiceUnavailable();
		}
		if (response.status >= 500) {
			logger.warn(`python_backend_server_error path=${path} status=${response.status}`);
			throw internalServiceUnavailable();
		}
		if (!response.ok) {
			throw new BackendBusinessError(response.status, await readDetail(response));
		}
		try {
			return (await response.json()) as T;
		} catch {
			logger.warn(`python_backend_invalid_json path=${path}`);
			throw internalServiceUnavailable();
		}
	}

	return {
		getInternalHealth: () => request<BackendHealth>("/internal/health"),
		async getUserAuthStatus(userUid) {
			const status = await request<UserAuthStatus>(
				`/internal/users/${encodeURIComponent(userUid)}/auth-status`,
			);
			if (typeof status.exists !== "boolean" || typeof status.is_active !== "boolean") {
				logger.warn("python_backend_unexpected_auth_status_shape");
				throw internalServiceUnavailable();
			}
			return status;
		},
	};
}
