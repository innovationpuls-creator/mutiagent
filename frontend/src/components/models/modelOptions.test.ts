import { describe, expect, it } from "vitest";
import { CATALOG, makeConfig } from "../../test/modelConfigHarness";
import {
	buildModelOptions,
	parseRefKey,
	providerStatus,
	providerUsable,
	refKey,
} from "./modelOptions";

describe("modelOptions", () => {
	it("lists catalog models for usable builtin providers with capability flags", () => {
		const options = buildModelOptions(makeConfig(), CATALOG);
		expect(options.map((o) => o.key)).toEqual([
			"openai/gpt-vision",
			"openai/gpt-text",
		]);
		expect(options.find((o) => o.key === "openai/gpt-vision")?.vision).toBe(
			true,
		);
		expect(options.find((o) => o.key === "openai/gpt-text")?.vision).toBe(
			false,
		);
	});

	it("hides providers without a credential and merges custom provider models", () => {
		const config = makeConfig();
		config.providers[0] = {
			...config.providers[0]!,
			has_secret: false,
			secret_mask: null,
		};
		config.providers.push({
			...config.providers[0]!,
			provider_id: "relay",
			display_name: "My Relay",
			is_builtin: false,
			protocol: "openai-completions",
			base_url: "http://relay/v1",
			has_secret: false,
		});
		config.custom_models.push({
			id: "m1",
			provider_id: "relay",
			model_id: "relay-vl",
			display_name: "Relay VL",
			context_window: 1000,
			max_tokens: 100,
			supports_vision: true,
			supports_tools: false,
			supports_reasoning: false,
			compat_config: {},
			pricing: {},
			enabled: true,
			updated_at: "2026-11-27T00:00:00",
		});
		const options = buildModelOptions(config, CATALOG);
		expect(options).toHaveLength(1);
		expect(options[0]).toMatchObject({
			key: "relay/relay-vl",
			vision: true,
			tools: false,
		});
	});

	it("derives provider status labels", () => {
		const config = makeConfig();
		const base = config.providers[0]!;
		expect(providerStatus(undefined)).toEqual({
			tone: "none",
			label: "未配置",
		});
		expect(providerStatus(base).label).toBe("API Key 已启用");
		expect(
			providerStatus({ ...base, auth_type: "oauth", oauth_status: "expired" })
				.label,
		).toBe("授权已过期");
		expect(
			providerStatus({
				...base,
				auth_type: "oauth",
				oauth_status: "authorized",
				oauth_expires_at: "2026-12-01T00:00:00",
			}).tone,
		).toBe("ok");
		expect(
			providerUsable({ ...base, auth_type: "oauth", oauth_status: "expired" }),
		).toBe(false);
	});

	it("round-trips model refs", () => {
		const key = refKey({ provider_id: "a", model_id: "b/c" });
		expect(parseRefKey(key)).toEqual({ provider_id: "a", model_id: "b/c" });
		expect(parseRefKey("")).toBeNull();
	});
});
