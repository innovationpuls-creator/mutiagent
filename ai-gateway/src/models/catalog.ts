import { builtinProviders } from "@earendil-works/pi-ai/providers/all";
import type { Provider } from "@earendil-works/pi-ai";

export interface CatalogModel {
	id: string;
	name: string;
	api: string;
	reasoning: boolean;
	vision: boolean;
	tools: boolean;
	context_window: number;
	max_tokens: number;
	cost: { input: number; output: number; cache_read: number; cache_write: number };
}

export interface CatalogProvider {
	id: string;
	name: string;
	supports_api_key: boolean;
	supports_oauth: boolean;
	models: CatalogModel[];
}

let cached: Provider[] | undefined;

export function listCatalog(providers: Provider[] = (cached ??= builtinProviders())): CatalogProvider[] {
	return providers.map((provider) => ({
		id: provider.id,
		name: provider.name ?? provider.id,
		supports_api_key: Boolean(provider.auth?.apiKey),
		supports_oauth: Boolean(provider.auth?.oauth),
		models: provider.getModels().map((model) => ({
			id: model.id,
			name: model.name,
			api: model.api,
			reasoning: model.reasoning,
			vision: model.input.includes("image"),
			// Pi's catalog has no tool-calling flag; every built-in chat model is tool-capable.
			tools: true,
			context_window: model.contextWindow,
			max_tokens: model.maxTokens,
			cost: {
				input: model.cost.input,
				output: model.cost.output,
				cache_read: model.cost.cacheRead,
				cache_write: model.cost.cacheWrite,
			},
		})),
	}));
}

export function builtinCapabilities(
	refs: Array<{ provider_id: string; model_id: string }>,
	providers: Provider[] = (cached ??= builtinProviders()),
): Record<string, { vision: boolean; tools: boolean; reasoning: boolean }> {
	const result: Record<string, { vision: boolean; tools: boolean; reasoning: boolean }> = {};
	for (const ref of refs) {
		const model = providers
			.find((p) => p.id === ref.provider_id)
			?.getModels()
			.find((m) => m.id === ref.model_id);
		if (model) {
			result[`${ref.provider_id}/${ref.model_id}`] = {
				vision: model.input.includes("image"),
				tools: true,
				reasoning: model.reasoning,
			};
		}
	}
	return result;
}
