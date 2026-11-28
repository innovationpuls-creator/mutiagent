import type {
	CatalogProvider,
	ModelConfigView,
	ModelRef,
	ProviderView,
} from "../../api/modelConfig";

export interface ModelOption {
	ref: ModelRef;
	key: string;
	label: string;
	providerLabel: string;
	vision: boolean;
	tools: boolean;
	reasoning: boolean;
}

export const refKey = (ref: ModelRef | null | undefined): string =>
	ref ? `${ref.provider_id}/${ref.model_id}` : "";

export function parseRefKey(key: string): ModelRef | null {
	const index = key.indexOf("/");
	if (index <= 0) return null;
	return { provider_id: key.slice(0, index), model_id: key.slice(index + 1) };
}

/** Whether a provider can currently be called (credential present / authorised). */
export function providerUsable(provider: ProviderView): boolean {
	if (!provider.enabled) return false;
	if (!provider.is_builtin) return true; // keyless local relays are valid
	if (provider.auth_type === "oauth")
		return provider.oauth_status === "authorized";
	return provider.has_secret;
}

export function providerStatus(provider: ProviderView | undefined): {
	tone: "none" | "ok" | "warn";
	label: string;
} {
	if (!provider) return { tone: "none", label: "未配置" };
	if (!provider.enabled) return { tone: "none", label: "已停用" };
	if (provider.auth_type === "oauth") {
		if (provider.oauth_status === "expired")
			return { tone: "warn", label: "授权已过期" };
		if (provider.oauth_status === "authorized") {
			const until = provider.oauth_expires_at
				? `，${new Date(provider.oauth_expires_at).toLocaleDateString("zh-CN")} 前有效`
				: "";
			return { tone: "ok", label: `OAuth 已授权${until}` };
		}
		return { tone: "none", label: "未授权" };
	}
	if (provider.has_secret) return { tone: "ok", label: "API Key 已启用" };
	return {
		tone: provider.is_builtin ? "none" : "ok",
		label: provider.is_builtin ? "未配置" : "已启用（无密钥）",
	};
}

export function buildModelOptions(
	config: ModelConfigView | null,
	catalog: CatalogProvider[],
): ModelOption[] {
	if (!config) return [];
	const options: ModelOption[] = [];
	for (const provider of config.providers) {
		if (!providerUsable(provider)) continue;
		const providerLabel = provider.display_name || provider.provider_id;
		if (provider.is_builtin) {
			const entry = catalog.find((item) => item.id === provider.provider_id);
			for (const model of entry?.models ?? []) {
				options.push({
					ref: { provider_id: provider.provider_id, model_id: model.id },
					key: `${provider.provider_id}/${model.id}`,
					label: model.name || model.id,
					providerLabel,
					vision: model.vision,
					tools: model.tools,
					reasoning: model.reasoning,
				});
			}
		} else {
			for (const model of config.custom_models) {
				if (model.provider_id !== provider.provider_id || !model.enabled)
					continue;
				options.push({
					ref: { provider_id: provider.provider_id, model_id: model.model_id },
					key: `${provider.provider_id}/${model.model_id}`,
					label: model.display_name || model.model_id,
					providerLabel,
					vision: model.supports_vision,
					tools: model.supports_tools,
					reasoning: model.supports_reasoning,
				});
			}
		}
	}
	return options;
}
