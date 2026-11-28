export const API_ERROR_CODES = [
	"AUTH_INVALID",
	"ACCOUNT_DISABLED",
	"MODEL_NOT_CONFIGURED",
	"MODEL_OAUTH_EXPIRED",
	"MODEL_CAPABILITY_MISMATCH",
	"INTERNAL_SERVICE_UNAVAILABLE",
] as const;

export type ApiErrorCode = (typeof API_ERROR_CODES)[number];

export interface ApiErrorResponse {
	detail?: string | { msg?: string }[];
	error_code?: ApiErrorCode | string;
	provider?: string;
	action?: string;
}

export function parseApiErrorCode(value: unknown): ApiErrorCode | null {
	return typeof value === "string" &&
		(API_ERROR_CODES as readonly string[]).includes(value)
		? (value as ApiErrorCode)
		: null;
}

export function parseNonEmptyString(value: unknown): string | null {
	return typeof value === "string" && value.trim() ? value : null;
}

export const AUTH_INVALID_EVENT = "mutiagent-auth-invalid";
export const INVALID_AUTH_DETAIL = "无效的认证凭证";

export async function readApiError(
	response: Response,
): Promise<ApiErrorResponse | null> {
	return (await response.json().catch(() => null)) as ApiErrorResponse | null;
}

export function getApiErrorDetail(
	error: ApiErrorResponse | null,
): string | null {
	return typeof error?.detail === "string" ? error.detail : null;
}

export function getApiErrorCode(
	error: ApiErrorResponse | null,
): ApiErrorCode | null {
	return parseApiErrorCode(error?.error_code);
}

export function getApiErrorProvider(
	error: ApiErrorResponse | null,
): string | null {
	return parseNonEmptyString(error?.provider);
}

export function getApiErrorAction(
	error: ApiErrorResponse | null,
): string | null {
	return parseNonEmptyString(error?.action);
}

export class ApiRequestError extends Error {
	status: number;
	errorCode: ApiErrorCode | null;
	provider: string | null;
	action: string | null;
	detail: string | null;

	constructor(
		message: string,
		status: number,
		error: ApiErrorResponse | null = null,
	) {
		super(message);
		this.name = "ApiRequestError";
		this.status = status;
		this.errorCode = getApiErrorCode(error);
		this.provider = getApiErrorProvider(error);
		this.action = getApiErrorAction(error);
		this.detail = getApiErrorDetail(error);
	}
}

export function notifyAuthInvalidFromError(
	status: number,
	error: ApiErrorResponse | null,
): void {
	if (status !== 401 || getApiErrorDetail(error) !== INVALID_AUTH_DETAIL) {
		return;
	}

	if (typeof window === "undefined") {
		return;
	}

	window.dispatchEvent(new Event(AUTH_INVALID_EVENT));
}

function getBrowserApiBaseUrl(): string {
	if (typeof process !== "undefined" && process.env.NODE_ENV === "test") {
		return "http://127.0.0.1:8000";
	}

	if (typeof window === "undefined" || !window.location.hostname) {
		return "http://127.0.0.1:8000";
	}

	// Local dev: same-origin relative path so the Vite proxy splits
	// /api/ai -> TS gateway (8100) and /api -> Python backend (8000).
	if (
		window.location.hostname === "127.0.0.1" ||
		window.location.hostname === "localhost"
	) {
		return "";
	}

	return window.location.origin;
}

export const API_BASE_URL =
	import.meta.env.VITE_API_BASE_URL ?? getBrowserApiBaseUrl();
