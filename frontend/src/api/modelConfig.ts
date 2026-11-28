import type { components } from "../types/api";
import {
	API_BASE_URL,
	ApiRequestError,
	notifyAuthInvalidFromError,
	readApiError,
} from "./http";

type Schemas = components["schemas"];
export type ModelConfigView = Schemas["ModelConfigView"];
export type ProviderView = Schemas["ProviderView"];
export type ProviderUpsert = Schemas["ProviderUpsert"];
export type CustomModelView = Schemas["CustomModelView"];
export type CustomModelUpsert = Schemas["CustomModelUpsert"];
export type PreferencesPayload = Schemas["PreferencesPayload"];
export type PreferencesView = Schemas["PreferencesView"];
export type QuickSwitchPayload = Schemas["QuickSwitchPayload"];
export type UsageSummary = Schemas["UsageSummary"];
export type ModelRef = Schemas["ModelRef"];
export type SlotBinding = Schemas["SlotBinding"];
export type RuntimeOptions = Schemas["RuntimeOptions"];

export const THINKING_LEVELS = [
	{ value: "off", label: "关闭" },
	{ value: "minimal", label: "极简" },
	{ value: "low", label: "低" },
	{ value: "medium", label: "中" },
	{ value: "high", label: "高" },
	{ value: "xhigh", label: "极高" },
] as const;
export type ThinkingLevel = (typeof THINKING_LEVELS)[number]["value"];

export function thinkingLabel(level: string | null | undefined): string {
	return THINKING_LEVELS.find((item) => item.value === level)?.label ?? "中";
}

export const SCENES = [
	{
		id: "chat_profile",
		label: "对话与画像",
		adminOnly: false,
		needsVision: false,
	},
	{
		id: "path_outline",
		label: "课程路径与大纲",
		adminOnly: false,
		needsVision: false,
	},
	{
		id: "course_resources",
		label: "小节图文与动画",
		adminOnly: false,
		needsVision: false,
	},
	{
		id: "quiz_vision",
		label: "测验视觉判分与答疑",
		adminOnly: false,
		needsVision: true,
	},
	{
		id: "growth_report",
		label: "成森成长报告",
		adminOnly: false,
		needsVision: false,
	},
	{
		id: "kb_translate",
		label: "教材翻译",
		adminOnly: true,
		needsVision: false,
	},
	{
		id: "kb_search",
		label: "公开教材搜书",
		adminOnly: true,
		needsVision: false,
	},
] as const;
export type SceneId = (typeof SCENES)[number]["id"];

export const PROTOCOLS = [
	{ value: "openai-completions", label: "OpenAI Chat Completions" },
	{ value: "openai-responses", label: "OpenAI Responses" },
	{ value: "anthropic-messages", label: "Anthropic Messages" },
	{ value: "google-generative-ai", label: "Google Generative AI" },
] as const;

// ── Gateway (TS) types ──

export interface CatalogModel {
	id: string;
	name: string;
	api: string;
	reasoning: boolean;
	vision: boolean;
	tools: boolean;
	context_window: number;
	max_tokens: number;
}
export interface CatalogProvider {
	id: string;
	name: string;
	supports_api_key: boolean;
	supports_oauth: boolean;
	models: CatalogModel[];
}
export interface ProbeItem {
	status: "ok" | "failed" | "skipped";
	first_token_ms?: number | null;
	total_ms?: number;
	reason?: string;
}
export interface ProbeResult {
	provider_id: string;
	model_id: string;
	text: ProbeItem;
	tools: ProbeItem;
	vision: ProbeItem;
}
export interface OAuthStart {
	state: string;
	mode: "redirect" | "device_code";
	auth_url?: string;
	instructions?: string;
	user_code?: string;
	verification_uri?: string;
	expires_in_seconds: number;
}

async function request<T>(
	token: string,
	path: string,
	init: { method?: string; body?: unknown } = {},
): Promise<T> {
	const response = await fetch(`${API_BASE_URL}${path}`, {
		method: init.method ?? "GET",
		headers: {
			Authorization: `Bearer ${token}`,
			...(init.body === undefined
				? {}
				: { "Content-Type": "application/json" }),
		},
		body: init.body === undefined ? undefined : JSON.stringify(init.body),
	});
	if (!response.ok) {
		const error = await readApiError(response);
		notifyAuthInvalidFromError(response.status, error);
		const detail =
			typeof error?.detail === "string"
				? error.detail
				: Array.isArray(error?.detail)
					? "输入内容不完整，请检查后重试"
					: "请求失败，请稍后重试";
		throw new ApiRequestError(detail, response.status, error);
	}
	if (response.status === 204) return undefined as T;
	return (await response.json()) as T;
}

const BASE = "/api/model-config";

export const modelConfigApi = {
	get: (token: string) => request<ModelConfigView>(token, BASE),
	saveProvider: (token: string, providerId: string, body: ProviderUpsert) =>
		request<ProviderView>(
			token,
			`${BASE}/providers/${encodeURIComponent(providerId)}`,
			{
				method: "PUT",
				body,
			},
		),
	deleteProvider: (token: string, providerId: string) =>
		request<unknown>(
			token,
			`${BASE}/providers/${encodeURIComponent(providerId)}`,
			{
				method: "DELETE",
			},
		),
	saveCustomModel: (token: string, body: CustomModelUpsert) =>
		request<CustomModelView>(token, `${BASE}/custom-models`, {
			method: "PUT",
			body,
		}),
	deleteCustomModel: (token: string, id: string) =>
		request<unknown>(token, `${BASE}/custom-models/${encodeURIComponent(id)}`, {
			method: "DELETE",
		}),
	savePreferences: (token: string, body: PreferencesPayload) =>
		request<PreferencesView>(token, `${BASE}/preferences`, {
			method: "PUT",
			body,
		}),
	quickSwitch: (token: string, body: QuickSwitchPayload) =>
		request<PreferencesView>(token, `${BASE}/quick-switch`, {
			method: "PATCH",
			body,
		}),
	usage: (token: string, days: number) =>
		request<UsageSummary>(token, `${BASE}/usage?days=${days}`),
};

export const aiModelsApi = {
	catalog: async (token: string) =>
		(
			await request<{ providers: CatalogProvider[] }>(
				token,
				"/api/ai/models/catalog",
			)
		).providers,
	probe: (token: string, providerId: string, modelId: string) =>
		request<ProbeResult>(token, "/api/ai/models/probe", {
			method: "POST",
			body: { provider_id: providerId, model_id: modelId },
		}),
	oauthStart: (token: string, providerId: string) =>
		request<OAuthStart>(
			token,
			`/api/ai/oauth/${encodeURIComponent(providerId)}/start`,
			{
				method: "POST",
			},
		),
	oauthComplete: (
		token: string,
		providerId: string,
		state: string,
		code: string,
	) =>
		request<{ status: string }>(
			token,
			`/api/ai/oauth/${encodeURIComponent(providerId)}/complete`,
			{ method: "POST", body: { state, code } },
		),
	oauthStatus: (token: string, providerId: string, state: string) =>
		request<{
			status: "pending" | "authorized" | "failed" | "expired";
			error?: string;
		}>(
			token,
			`/api/ai/oauth/${encodeURIComponent(providerId)}/status?state=${encodeURIComponent(state)}`,
		),
};
