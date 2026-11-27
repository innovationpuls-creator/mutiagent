import { render } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter } from "react-router-dom";
import { vi } from "vitest";
import type {
	CatalogProvider,
	ModelConfigView,
	ProbeResult,
} from "../api/modelConfig";
import { AuthProvider } from "../contexts/AuthContext";
import { ModelConfigProvider } from "../contexts/ModelConfigContext";

export const CATALOG: CatalogProvider[] = [
	{
		id: "openai",
		name: "OpenAI",
		supports_api_key: true,
		supports_oauth: false,
		models: [
			{
				id: "gpt-vision",
				name: "GPT Vision",
				api: "openai-responses",
				reasoning: true,
				vision: true,
				tools: true,
				context_window: 128000,
				max_tokens: 8192,
			},
			{
				id: "gpt-text",
				name: "GPT Text",
				api: "openai-responses",
				reasoning: false,
				vision: false,
				tools: true,
				context_window: 128000,
				max_tokens: 8192,
			},
		],
	},
	{
		id: "anthropic",
		name: "Anthropic",
		supports_api_key: true,
		supports_oauth: true,
		models: [],
	},
];

export function makeConfig(
	overrides: Partial<ModelConfigView> = {},
): ModelConfigView {
	return {
		providers: [
			{
				provider_id: "openai",
				display_name: "OpenAI",
				is_builtin: true,
				protocol: "",
				base_url: "",
				headers: {},
				auth_type: "api_key",
				has_secret: true,
				secret_mask: "••••9999",
				oauth_status: null,
				oauth_expires_at: null,
				oauth_account_label: null,
				enabled: true,
				updated_at: "2026-11-27T00:00:00",
			},
		],
		custom_models: [],
		preferences: {
			config_mode: "simple",
			default_model_ref: { provider_id: "openai", model_id: "gpt-text" },
			default_vision_model_ref: null,
			default_thinking_level: "medium",
			runtime_options: {},
			slot_bindings: {},
			updated_at: null,
		},
		...overrides,
	} as ModelConfigView;
}

export const OK_PROBE: ProbeResult = {
	provider_id: "openai",
	model_id: "gpt-text",
	text: { status: "ok", first_token_ms: 123, total_ms: 150 },
	tools: { status: "ok", first_token_ms: 200, total_ms: 220 },
	vision: { status: "skipped", reason: "模型未声明图片输入能力" },
};

export interface FetchCall {
	method: string;
	path: string;
	body: unknown;
}

type Handler = (
	call: FetchCall,
) => { status?: number; json: unknown } | undefined;

/** Routes fetch by "METHOD /path" prefix; unknown routes return 404. */
export function stubFetch(handlers: Record<string, Handler | unknown>) {
	const calls: FetchCall[] = [];
	const fn = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
		const url = new URL(String(input), "http://localhost");
		const method = (init?.method ?? "GET").toUpperCase();
		const call: FetchCall = {
			method,
			path: `${url.pathname}${url.search}`,
			body: init?.body ? JSON.parse(String(init.body)) : undefined,
		};
		calls.push(call);
		const key = Object.keys(handlers).find((k) =>
			`${method} ${call.path}`.startsWith(k),
		);
		if (!key)
			return new Response(JSON.stringify({ detail: "Not Found" }), {
				status: 404,
			});
		const entry = handlers[key];
		const result =
			typeof entry === "function"
				? (entry as Handler)(call)
				: entry && typeof entry === "object" && "json" in entry
					? (entry as { status?: number; json: unknown })
					: { json: entry };
		return new Response(JSON.stringify(result?.json ?? {}), {
			status: result?.status ?? 200,
			headers: { "Content-Type": "application/json" },
		});
	});
	vi.stubGlobal("fetch", fn);
	return { calls, fn };
}

/** jsdom's localStorage is shadowed by Node's in this runner; stub a Map-backed one. */
export function seedAuth(role: "student" | "admin" = "student") {
	const store = new Map<string, string>();
	vi.stubGlobal("localStorage", {
		getItem: (key: string) => store.get(key) ?? null,
		setItem: (key: string, value: string) => void store.set(key, value),
		removeItem: (key: string) => void store.delete(key),
		clear: () => store.clear(),
	});
	localStorage.setItem(
		"mutiagent-auth",
		JSON.stringify({
			token: "test-token",
			user: {
				uid: `uid-${role}`,
				username: role === "admin" ? "管理员" : "小明",
				identifier: `${role}@example.test`,
				role,
				school: "",
				major: "",
				class_name: "",
			},
		}),
	);
}

export function renderWithModels(ui: ReactElement, route = "/settings/models") {
	return render(
		<MemoryRouter initialEntries={[route]}>
			<AuthProvider>
				<ModelConfigProvider>{ui}</ModelConfigProvider>
			</AuthProvider>
		</MemoryRouter>,
	);
}
