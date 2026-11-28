export const SCENES = [
	"chat_profile",
	"path_outline",
	"course_resources",
	"quiz_vision",
	"growth_report",
	"kb_translate",
	"kb_search",
] as const;
export type Scene = (typeof SCENES)[number];

export const THINKING_LEVELS = ["off", "minimal", "low", "medium", "high", "xhigh"] as const;
export type ThinkingLevel = (typeof THINKING_LEVELS)[number];

export const VISION_SCENES: ReadonlySet<Scene> = new Set(["quiz_vision"]);

export interface ModelRef {
	provider_id: string;
	model_id: string;
}

export interface RuntimeProvider {
	provider_id: string;
	display_name: string;
	is_builtin: boolean;
	protocol: string;
	base_url: string;
	headers: Record<string, string>;
	auth_type: "api_key" | "oauth";
	enabled: boolean;
	api_key: string | null;
	oauth_credential: Record<string, unknown> | null;
	oauth_refresh_fingerprint: string | null;
}

export interface RuntimeCustomModel {
	id: string;
	provider_id: string;
	model_id: string;
	display_name: string;
	context_window: number;
	max_tokens: number;
	supports_vision: boolean;
	supports_tools: boolean;
	supports_reasoning: boolean;
	compat_config: Record<string, unknown>;
	pricing: Record<string, number>;
	enabled: boolean;
}

export interface SlotBinding {
	model_ref: ModelRef;
	thinking_level?: ThinkingLevel | null;
	fallback_chain?: ModelRef[];
}

export interface RuntimeOptions {
	temperature?: number | null;
	max_tokens?: number | null;
	timeout_seconds?: number | null;
	max_retries?: number | null;
	cache_retention?: "none" | "short" | "long" | null;
}

export interface RuntimePreferences {
	config_mode: "simple" | "advanced";
	default_model_ref: ModelRef | null;
	default_vision_model_ref: ModelRef | null;
	default_thinking_level: ThinkingLevel;
	runtime_options: RuntimeOptions;
	slot_bindings: Partial<Record<Scene, SlotBinding>>;
}

export interface RuntimeConfig {
	user_uid: string;
	role: string | null;
	providers: RuntimeProvider[];
	custom_models: RuntimeCustomModel[];
	preferences: RuntimePreferences;
}
