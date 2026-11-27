export const AUTH_INVALID_DETAIL = "无效的认证凭证";

export const ERROR_CODES = [
	"AUTH_INVALID",
	"ACCOUNT_DISABLED",
	"MODEL_NOT_CONFIGURED",
	"MODEL_OAUTH_EXPIRED",
	"MODEL_CAPABILITY_MISMATCH",
	"INTERNAL_SERVICE_UNAVAILABLE",
] as const;
export type ErrorCode = (typeof ERROR_CODES)[number];

export interface ErrorExtras {
	provider?: string;
	action?: string;
}

export interface ErrorBody extends ErrorExtras {
	detail: string;
	error_code?: ErrorCode;
}

/** Business error with an explicit HTTP status and the legacy `detail` text. */
export class GatewayError extends Error {
	readonly status: number;
	readonly errorCode: ErrorCode | undefined;
	readonly detail: string;
	readonly extras: ErrorExtras;

	constructor(
		status: number,
		errorCode: ErrorCode | undefined,
		detail: string,
		extras: ErrorExtras = {},
	) {
		super(detail);
		this.name = "GatewayError";
		this.status = status;
		this.errorCode = errorCode;
		this.detail = detail;
		this.extras = extras;
	}

	toBody(): ErrorBody {
		const body: ErrorBody = { detail: this.detail };
		if (this.errorCode) body.error_code = this.errorCode;
		if (this.extras.provider) body.provider = this.extras.provider;
		if (this.extras.action) body.action = this.extras.action;
		return body;
	}
}

/** A non-internal-token 4xx coming from the Python backend; semantics pass through. */
export class BackendBusinessError extends Error {
	readonly status: number;
	readonly detail: string;

	constructor(status: number, detail: string) {
		super(detail);
		this.name = "BackendBusinessError";
		this.status = status;
		this.detail = detail;
	}
}

export const authInvalid = () =>
	new GatewayError(401, "AUTH_INVALID", AUTH_INVALID_DETAIL);
export const userNotFound = () =>
	new GatewayError(401, "AUTH_INVALID", "用户不存在");
export const accountDisabled = () =>
	new GatewayError(403, "ACCOUNT_DISABLED", "账号已被禁用");
export const modelNotConfigured = () =>
	new GatewayError(428, "MODEL_NOT_CONFIGURED", "尚未配置可用的个人模型，请先前往「模型配置」完成设置", {
		action: "open_model_settings",
	});
export const modelOAuthExpired = (provider: string) =>
	new GatewayError(401, "MODEL_OAUTH_EXPIRED", "模型授权已过期，请重新登录对应厂商", {
		provider,
		action: "reauthorize_provider",
	});
export const modelCapabilityMismatch = (detail: string) =>
	new GatewayError(422, "MODEL_CAPABILITY_MISMATCH", detail);
export const internalServiceUnavailable = () =>
	new GatewayError(503, "INTERNAL_SERVICE_UNAVAILABLE", "AI 服务暂时不可用，请稍后重试");
