import { KeyRound, Settings2 } from "lucide-react";
import { Link } from "react-router-dom";
import type { ApiErrorCode } from "../../api/http";
import { useAuth } from "../../contexts/AuthContext";
import { useModelConfig } from "../../contexts/ModelConfigContext";
import { modelSettingsPath } from "./modelPaths";
import "./model-config-shared.css";

export interface ModelErrorInfo {
	errorCode?: ApiErrorCode | string | null;
	provider?: string | null;
}

export function isModelGuidanceError(
	info: ModelErrorInfo | null | undefined,
): info is ModelErrorInfo {
	return (
		info?.errorCode === "MODEL_NOT_CONFIGURED" ||
		info?.errorCode === "MODEL_OAUTH_EXPIRED"
	);
}

/** Pulls guidance-relevant fields from SessionStreamError / ApiRequestError-like objects. */
export function modelErrorInfo(error: unknown): ModelErrorInfo | null {
	if (!error || typeof error !== "object") return null;
	const candidate = error as { errorCode?: unknown; provider?: unknown };
	const info: ModelErrorInfo = {
		errorCode:
			typeof candidate.errorCode === "string" ? candidate.errorCode : null,
		provider:
			typeof candidate.provider === "string" ? candidate.provider : null,
	};
	return isModelGuidanceError(info) ? info : null;
}

export function ModelGuidanceCard({ info }: { info: ModelErrorInfo }) {
	const { user } = useAuth();
	const { config, catalog } = useModelConfig();
	const path = modelSettingsPath(user?.role);

	if (info.errorCode === "MODEL_OAUTH_EXPIRED") {
		const providerId = info.provider ?? "";
		const providerName =
			config?.providers.find((p) => p.provider_id === providerId)
				?.display_name ||
			catalog.find((p) => p.id === providerId)?.name ||
			providerId ||
			"模型厂商";
		const target = providerId
			? `${path}?reauth=${encodeURIComponent(providerId)}`
			: path;
		return (
			<div className="mgc" role="alert" data-code="MODEL_OAUTH_EXPIRED">
				<KeyRound aria-hidden="true" size={18} />
				<div className="mgc-body">
					<strong>「{providerName}」的授权已失效</strong>
					<p>请重新登录该厂商，授权完成后即可继续使用。</p>
				</div>
				<Link className="mgc-action" to={target}>
					重新登录 {providerName}
				</Link>
			</div>
		);
	}

	return (
		<div className="mgc" role="alert" data-code="MODEL_NOT_CONFIGURED">
			<Settings2 aria-hidden="true" size={18} />
			<div className="mgc-body">
				<strong>请先配置你的个人 AI 模型</strong>
				<p>
					AI 功能使用你自己配置的模型。添加 API Key 或 OAuth 登录后，30
					秒即可开始使用。
				</p>
			</div>
			<Link className="mgc-action" to={path}>
				去配置模型
			</Link>
		</div>
	);
}
