import { modelNotConfigured } from "../errors.js";
import {
	type ModelRef,
	type RuntimeConfig,
	type RuntimeOptions,
	type Scene,
	type ThinkingLevel,
	VISION_SCENES,
} from "./types.js";

export interface ResolvedScene {
	scene: Scene;
	targets: ModelRef[];
	thinkingLevel: ThinkingLevel;
	options: RuntimeOptions;
}

function providerUsable(config: RuntimeConfig, ref: ModelRef): boolean {
	const provider = config.providers.find((p) => p.provider_id === ref.provider_id);
	return provider?.enabled === true;
}

/**
 * advanced + bound slot -> that slot; otherwise simple defaults
 * (vision scenes use the default vision model, everything else the default main model).
 * Nothing configured -> MODEL_NOT_CONFIGURED; never falls back to any global env key.
 */
export function resolveScene(config: RuntimeConfig, scene: Scene): ResolvedScene {
	const prefs = config.preferences;
	const binding = prefs.config_mode === "advanced" ? prefs.slot_bindings?.[scene] : undefined;
	const primary =
		binding?.model_ref ?? (VISION_SCENES.has(scene) ? prefs.default_vision_model_ref : prefs.default_model_ref);
	if (!primary || !providerUsable(config, primary)) throw modelNotConfigured();
	const fallbacks = (binding?.fallback_chain ?? []).filter((ref) => providerUsable(config, ref));
	return {
		scene,
		targets: [primary, ...fallbacks],
		thinkingLevel: binding?.thinking_level ?? prefs.default_thinking_level ?? "medium",
		options: prefs.runtime_options ?? {},
	};
}
