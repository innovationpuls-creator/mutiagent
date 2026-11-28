import {
	type Api,
	type CredentialStore,
	type Model,
	type MutableModels,
	type Provider,
	createModels,
	createProvider,
} from "@earendil-works/pi-ai";
import { anthropicMessagesApi } from "@earendil-works/pi-ai/api/anthropic-messages.lazy";
import { googleGenerativeAIApi } from "@earendil-works/pi-ai/api/google-generative-ai.lazy";
import { openAICompletionsApi } from "@earendil-works/pi-ai/api/openai-completions.lazy";
import { openAIResponsesApi } from "@earendil-works/pi-ai/api/openai-responses.lazy";
import { builtinProviders } from "@earendil-works/pi-ai/providers/all";
import type { RuntimeConfig, RuntimeCustomModel, RuntimeProvider } from "./types.js";

export const PROTOCOLS = [
	"openai-completions",
	"openai-responses",
	"anthropic-messages",
	"google-generative-ai",
] as const;

function apiFor(protocol: string) {
	switch (protocol) {
		case "openai-completions":
			return openAICompletionsApi();
		case "openai-responses":
			return openAIResponsesApi();
		case "anthropic-messages":
			return anthropicMessagesApi();
		case "google-generative-ai":
			return googleGenerativeAIApi();
		default:
			return undefined;
	}
}

let cachedBuiltins: Provider[] | undefined;
function getBuiltins(): Provider[] {
	cachedBuiltins ??= builtinProviders();
	return cachedBuiltins;
}

/** Providers used instead of the real built-ins (tests / acceptance harness). */
export interface BuildOptions {
	builtinOverride?: Provider[];
}

function customModel(provider: RuntimeProvider, row: RuntimeCustomModel): Model<Api> {
	const pricing = row.pricing ?? {};
	return {
		id: row.model_id,
		name: row.display_name || row.model_id,
		api: provider.protocol,
		provider: provider.provider_id,
		baseUrl: provider.base_url,
		reasoning: row.supports_reasoning,
		input: row.supports_vision ? ["text", "image"] : ["text"],
		cost: {
			input: Number(pricing.input ?? 0),
			output: Number(pricing.output ?? 0),
			cacheRead: Number(pricing.cacheRead ?? pricing.cache_read ?? 0),
			cacheWrite: Number(pricing.cacheWrite ?? pricing.cache_write ?? 0),
		},
		contextWindow: row.context_window,
		maxTokens: row.max_tokens,
		...(Object.keys(provider.headers).length > 0 ? { headers: provider.headers } : {}),
		...(Object.keys(row.compat_config ?? {}).length > 0 ? { compat: row.compat_config } : {}),
	} as Model<Api>;
}

function customProvider(provider: RuntimeProvider, rows: RuntimeCustomModel[]): Provider | undefined {
	const api = apiFor(provider.protocol);
	if (!api) return undefined;
	const apiKey = provider.api_key;
	return createProvider({
		id: provider.provider_id,
		name: provider.display_name || provider.provider_id,
		baseUrl: provider.base_url,
		// Keyless local servers resolve as configured with no key; never reads env vars.
		auth: { apiKey: { name: provider.display_name, resolve: async () => ({ auth: apiKey ? { apiKey } : {} }) } },
		models: rows.filter((row) => row.enabled).map((row) => customModel(provider, row)),
		api,
	} as never);
}

/**
 * Per-user Pi `Models` collection: built-in providers (credentials from the user's
 * stored keys only, env vars of the gateway host are never consulted) plus the
 * user's custom providers and models.
 */
export function buildUserModels(
	config: RuntimeConfig,
	credentials: CredentialStore,
	options: BuildOptions = {},
): MutableModels {
	const models = createModels({
		credentials,
		authContext: { env: async () => undefined, fileExists: async () => false },
	});
	for (const provider of options.builtinOverride ?? getBuiltins()) models.setProvider(provider);
	for (const provider of config.providers) {
		if (provider.is_builtin || !provider.enabled) continue;
		const rows = config.custom_models.filter((row) => row.provider_id === provider.provider_id);
		const built = customProvider(provider, rows);
		if (built) models.setProvider(built);
	}
	return models;
}
