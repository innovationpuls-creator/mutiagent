import {
	cleanup,
	fireEvent,
	screen,
	waitFor,
	within,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
	CATALOG,
	makeConfig,
	OK_PROBE,
	renderWithModels,
	seedAuth,
	stubFetch,
} from "../../test/modelConfigHarness";
import { ModelConfigPage } from "./ModelConfigPage";
import { extractAuthCode } from "./OAuthDialog";

const USAGE = {
	days: 7,
	buckets: [
		{
			date: "2026-11-27",
			scene: "chat_profile",
			requests: 4,
			success_requests: 3,
			input_tokens: 1000,
			output_tokens: 500,
			cache_read_tokens: 200,
			cache_write_tokens: 0,
			reasoning_tokens: 50,
			estimated_cost_usd: 0.0123,
			avg_latency_ms: 800,
		},
	],
	total_requests: 4,
	total_tokens: 1500,
	total_cost_usd: 0.0123,
};

function baseHandlers(overrides: Record<string, unknown> = {}) {
	return {
		"GET /api/model-config/usage": { json: USAGE },
		"GET /api/model-config": { json: makeConfig() },
		"GET /api/ai/models/catalog": { json: { providers: CATALOG } },
		...overrides,
	};
}

beforeEach(() => seedAuth("student"));
afterEach(() => {
	cleanup();
	vi.unstubAllGlobals();
});

describe("ModelConfigPage — providers (AC-3)", () => {
	it("shows masked keys only and the provider status", async () => {
		stubFetch(baseHandlers());
		renderWithModels(<ModelConfigPage />);
		const card = (await screen.findByText("API Key 已启用")).closest(
			"li",
		) as HTMLElement;
		expect(within(card).getByText(/••••9999/)).toBeTruthy();
		fireEvent.click(within(card).getByRole("button", { name: "配置" }));
		const key = (await screen.findByLabelText("API Key")) as HTMLInputElement;
		expect(key.value).toBe("");
		expect(key.placeholder).toContain("••••9999");
		expect(document.body.textContent).not.toMatch(/sk-/);
	});

	it("creates a custom provider", async () => {
		const { calls } = stubFetch(
			baseHandlers({
				"PUT /api/model-config/providers/my-relay": { json: {} },
				"PUT /api/model-config/custom-models": { json: {} },
			}),
		);
		renderWithModels(<ModelConfigPage />);
		fireEvent.click(
			await screen.findByRole("button", {
				name: "添加自定义服务",
			}),
		);
		fireEvent.change(await screen.findByLabelText("Provider 标识"), {
			target: { value: "my-relay" },
		});
		fireEvent.change(screen.getByLabelText("Base URL"), {
			target: { value: "http://relay.test/v1" },
		});
		fireEvent.change(screen.getByLabelText("API Key"), {
			target: { value: "relay-secret" },
		});
		fireEvent.click(screen.getByRole("button", { name: "保存" }));
		await waitFor(() =>
			expect(
				calls.some(
					(c) => c.method === "PUT" && c.path.endsWith("/providers/my-relay"),
				),
			).toBe(true),
		);
		const providerCall = calls.find((c) =>
			c.path.endsWith("/providers/my-relay"),
		);
		expect(providerCall?.body).toMatchObject({
			is_builtin: false,
			protocol: "openai-completions",
			base_url: "http://relay.test/v1",
			api_key: "relay-secret",
			enabled: true,
		});
	});

	it("adds a custom model with capability tags and Compat settings", async () => {
		const config = makeConfig();
		config.providers.push({
			...config.providers[0]!,
			provider_id: "my-relay",
			display_name: "My Relay",
			is_builtin: false,
			protocol: "openai-completions",
			base_url: "http://relay.test/v1",
			has_secret: false,
			secret_mask: null,
		});
		const { calls } = stubFetch(
			baseHandlers({
				"GET /api/model-config": { json: config },
				"PUT /api/model-config/custom-models": { json: {} },
			}),
		);
		renderWithModels(<ModelConfigPage />);
		const card = (await screen.findByText("My Relay")).closest(
			"li",
		) as HTMLElement;
		fireEvent.click(within(card).getByRole("button", { name: "配置" }));
		fireEvent.click(await screen.findByRole("button", { name: "新增模型" }));
		fireEvent.change(screen.getByLabelText("模型 ID"), {
			target: { value: "relay-vl" },
		});
		fireEvent.click(screen.getByLabelText("视觉（图片输入）"));
		fireEvent.change(
			screen.getByLabelText("参考单价 输入（USD / 百万 token）"),
			{ target: { value: "1.5" } },
		);
		fireEvent.click(screen.getByText("Pi Compat 高级兼容项"));
		fireEvent.change(screen.getByLabelText("支持 developer 角色"), {
			target: { value: "false" },
		});
		fireEvent.change(screen.getByLabelText("最大输出参数名"), {
			target: { value: "max_tokens" },
		});
		fireEvent.click(screen.getByRole("button", { name: "保存模型" }));
		await waitFor(() =>
			expect(calls.some((c) => c.path.endsWith("/custom-models"))).toBe(true),
		);
		expect(
			calls.find((c) => c.path.endsWith("/custom-models"))?.body,
		).toMatchObject({
			provider_id: "my-relay",
			model_id: "relay-vl",
			supports_vision: true,
			supports_tools: true,
			pricing: { input: 1.5 },
			compat_config: {
				supportsDeveloperRole: false,
				maxTokensField: "max_tokens",
			},
		});
	});

	it("rejects invalid Compat JSON before calling the API", async () => {
		const config = makeConfig();
		config.providers.push({
			...config.providers[0]!,
			provider_id: "my-relay",
			display_name: "My Relay",
			is_builtin: false,
			protocol: "openai-completions",
			base_url: "http://relay.test/v1",
		});
		const { calls } = stubFetch(
			baseHandlers({ "GET /api/model-config": { json: config } }),
		);
		renderWithModels(<ModelConfigPage />);
		const card = (await screen.findByText("My Relay")).closest(
			"li",
		) as HTMLElement;
		fireEvent.click(within(card).getByRole("button", { name: "配置" }));
		fireEvent.click(await screen.findByRole("button", { name: "新增模型" }));
		fireEvent.change(screen.getByLabelText("模型 ID"), {
			target: { value: "m" },
		});
		fireEvent.click(screen.getByText("Pi Compat 高级兼容项"));
		fireEvent.change(screen.getByLabelText("其他兼容项（JSON，可选）"), {
			target: { value: "{bad" },
		});
		fireEvent.click(screen.getByRole("button", { name: "保存模型" }));
		expect((await screen.findAllByRole("alert")).length).toBeGreaterThan(0);
		expect(calls.some((c) => c.method === "PUT")).toBe(false);
	});

	it("validates a custom provider without Base URL before calling the API", async () => {
		const { calls } = stubFetch(baseHandlers());
		renderWithModels(<ModelConfigPage />);
		fireEvent.click(
			await screen.findByRole("button", {
				name: "添加自定义服务",
			}),
		);
		fireEvent.change(await screen.findByLabelText("Provider 标识"), {
			target: { value: "x" },
		});
		fireEvent.click(screen.getByRole("button", { name: "保存" }));
		expect((await screen.findByRole("alert")).textContent).toContain(
			"Base URL",
		);
		expect(calls.some((c) => c.method === "PUT")).toBe(false);
	});

	it("probe shows text / tools / vision badges and first-token latency", async () => {
		stubFetch(
			baseHandlers({ "POST /api/ai/models/probe": { json: OK_PROBE } }),
		);
		renderWithModels(<ModelConfigPage />);
		const card = (await screen.findByText("API Key 已启用")).closest(
			"li",
		) as HTMLElement;
		fireEvent.click(within(card).getByRole("button", { name: "测试连接" }));
		const badges = await within(card).findByLabelText("连通性测试结果");
		expect(badges.textContent).toContain("文本");
		expect(badges.textContent).toContain("123 ms");
		expect(badges.textContent).toContain("工具调用");
		expect(badges.textContent).toContain("未声明");
	});

	it("shows a clear reason when the probe fails", async () => {
		stubFetch(
			baseHandlers({
				"POST /api/ai/models/probe": {
					json: {
						...OK_PROBE,
						text: {
							status: "failed",
							reason: "认证失败（401）：API Key 无效或无权限",
						},
						tools: { status: "skipped", reason: "文本探针失败，已跳过" },
					},
				},
			}),
		);
		renderWithModels(<ModelConfigPage />);
		const card = (await screen.findByText("API Key 已启用")).closest(
			"li",
		) as HTMLElement;
		fireEvent.click(within(card).getByRole("button", { name: "测试连接" }));
		expect(
			(await within(card).findByLabelText("连通性测试结果")).textContent,
		).toContain("认证失败（401）");
	});
});

describe("ModelConfigPage — slots (AC-1 / AC-2)", () => {
	it("simple mode saves main model, vision model and thinking depth", async () => {
		const { calls } = stubFetch(
			baseHandlers({
				"PUT /api/model-config/preferences": (call: { body: unknown }) => ({
					json: { ...(call.body as object), updated_at: null },
				}),
			}),
		);
		renderWithModels(<ModelConfigPage />);
		const main = (await screen.findByLabelText(
			"主力模型",
		)) as HTMLSelectElement;
		fireEvent.change(main, { target: { value: "openai/gpt-vision" } });
		const vision = screen.getByLabelText(/视觉模型/) as HTMLSelectElement;
		expect(Array.from(vision.options).map((o) => o.value)).toEqual([
			"",
			"openai/gpt-vision",
		]);
		fireEvent.change(vision, { target: { value: "openai/gpt-vision" } });
		fireEvent.click(screen.getByRole("button", { name: "高" }));
		fireEvent.click(screen.getByRole("button", { name: "保存配置" }));
		await waitFor(() =>
			expect(
				calls.some(
					(c) => c.method === "PUT" && c.path.endsWith("/preferences"),
				),
			).toBe(true),
		);
		expect(
			calls.find((c) => c.path.endsWith("/preferences"))?.body,
		).toMatchObject({
			config_mode: "simple",
			default_model_ref: { provider_id: "openai", model_id: "gpt-vision" },
			default_vision_model_ref: {
				provider_id: "openai",
				model_id: "gpt-vision",
			},
			default_thinking_level: "high",
			slot_bindings: {},
		});
		expect(await screen.findByText(/已保存/)).toBeTruthy();
	});

	it("reload shows the saved values", async () => {
		const config = makeConfig();
		config.preferences = {
			...config.preferences,
			default_model_ref: { provider_id: "openai", model_id: "gpt-vision" },
			default_thinking_level: "xhigh",
		};
		stubFetch(baseHandlers({ "GET /api/model-config": { json: config } }));
		renderWithModels(<ModelConfigPage />);
		await waitFor(() =>
			expect(
				(screen.getByLabelText("主力模型") as HTMLSelectElement).value,
			).toBe("openai/gpt-vision"),
		);
		expect(
			screen
				.getAllByRole("button", { name: "极高" })[0]
				?.getAttribute("aria-pressed"),
		).toBe("true");
	});

	it("advanced mode disables non-vision models in the vision slot with a hint", async () => {
		stubFetch(baseHandlers());
		renderWithModels(<ModelConfigPage />);
		await screen.findByLabelText("主力模型");
		fireEvent.click(screen.getByRole("button", { name: "高级" }));
		const select = (await screen.findByLabelText("模型", {
			selector: "#mc-scene-quiz_vision",
		})) as HTMLSelectElement;
		const text = Array.from(select.options).find(
			(o) => o.value === "openai/gpt-text",
		);
		const vision = Array.from(select.options).find(
			(o) => o.value === "openai/gpt-vision",
		);
		expect(text?.disabled).toBe(true);
		expect(text?.textContent).toContain("不支持图片输入");
		expect(vision?.disabled).toBe(false);
	});

	it("only admins see the knowledge-base slots (separate configs per role)", async () => {
		stubFetch(baseHandlers());
		const student = renderWithModels(<ModelConfigPage />);
		await screen.findByLabelText("主力模型");
		fireEvent.click(screen.getByRole("button", { name: "高级" }));
		expect(await screen.findByText("成森成长报告")).toBeTruthy();
		expect(screen.queryByText("教材翻译")).toBeNull();
		expect(screen.queryByText("公开教材搜书")).toBeNull();
		student.unmount();
		cleanup();

		seedAuth("admin");
		renderWithModels(<ModelConfigPage />, "/admin/models");
		await screen.findByLabelText("主力模型");
		fireEvent.click(screen.getByRole("button", { name: "高级" }));
		expect(await screen.findByText("教材翻译")).toBeTruthy();
		expect(screen.getByText("公开教材搜书")).toBeTruthy();
	});

	it("advanced save sends slot bindings with a fallback chain", async () => {
		const { calls } = stubFetch(
			baseHandlers({
				"PUT /api/model-config/preferences": (call: { body: unknown }) => ({
					json: call.body,
				}),
			}),
		);
		renderWithModels(<ModelConfigPage />);
		await screen.findByLabelText("主力模型");
		fireEvent.click(screen.getByRole("button", { name: "高级" }));
		const scene = (await screen.findByLabelText("模型", {
			selector: "#mc-scene-chat_profile",
		})) as HTMLSelectElement;
		fireEvent.change(scene, { target: { value: "openai/gpt-vision" } });
		fireEvent.change(await screen.findByLabelText("添加备用模型"), {
			target: { value: "openai/gpt-text" },
		});
		fireEvent.click(screen.getByRole("button", { name: "保存配置" }));
		await waitFor(() =>
			expect(calls.some((c) => c.method === "PUT")).toBe(true),
		);
		expect(calls.find((c) => c.method === "PUT")?.body).toMatchObject({
			config_mode: "advanced",
			slot_bindings: {
				chat_profile: {
					model_ref: { provider_id: "openai", model_id: "gpt-vision" },
					fallback_chain: [{ provider_id: "openai", model_id: "gpt-text" }],
				},
			},
		});
	});
});

describe("ModelConfigPage — usage", () => {
	it("summarises calls, success rate, tokens and cost", async () => {
		stubFetch(baseHandlers());
		renderWithModels(<ModelConfigPage />);
		await screen.findByText("估算费用");
		const stats = screen.getByText("成功率").closest("div") as HTMLElement;
		expect(stats.textContent).toContain("75%");
		expect(
			(screen.getByText("估算费用").closest("div") as HTMLElement).textContent,
		).toContain("$0.01");
		expect(screen.getByRole("cell", { name: "4" })).toBeTruthy();
	});
});

describe("OAuth dialog (AC-3)", () => {
	it("opens from ?reauth, shows the auth link and completes with a pasted callback URL", async () => {
		const config = makeConfig();
		config.providers.push({
			...config.providers[0]!,
			provider_id: "anthropic",
			display_name: "Claude 订阅",
			auth_type: "oauth",
			has_secret: false,
			secret_mask: null,
			oauth_status: "expired",
		});
		const { calls } = stubFetch(
			baseHandlers({
				"GET /api/model-config": { json: config },
				"POST /api/ai/oauth/anthropic/start": {
					json: {
						state: "st-1",
						mode: "redirect",
						auth_url: "https://auth.test/authorize",
						expires_in_seconds: 600,
					},
				},
				"GET /api/ai/oauth/anthropic/status": { json: { status: "pending" } },
				"POST /api/ai/oauth/anthropic/complete": {
					json: { status: "authorized" },
				},
			}),
		);
		renderWithModels(<ModelConfigPage />, "/settings/models?reauth=anthropic");
		const dialog = await screen.findByRole("dialog", { name: /OAuth 登录/ });
		const link = await within(dialog).findByRole("link", {
			name: "打开授权页",
		});
		expect(link.getAttribute("href")).toBe("https://auth.test/authorize");
		fireEvent.change(within(dialog).getByLabelText("授权码 / 回调 URL"), {
			target: {
				value: "http://localhost:1455/auth/callback?code=abc123&state=zzz",
			},
		});
		fireEvent.click(within(dialog).getByRole("button", { name: "完成授权" }));
		await waitFor(() =>
			expect(calls.find((c) => c.path.endsWith("/complete"))?.body).toEqual({
				state: "st-1",
				code: "abc123",
			}),
		);
		await waitFor(() =>
			expect(screen.queryByRole("dialog", { name: /OAuth 登录/ })).toBeNull(),
		);
	});

	it("Escape closes the dialog", async () => {
		stubFetch(
			baseHandlers({
				"POST /api/ai/oauth/anthropic/start": {
					json: {
						state: "s",
						mode: "redirect",
						auth_url: "https://a.test",
						expires_in_seconds: 600,
					},
				},
				"GET /api/ai/oauth/anthropic/status": { json: { status: "pending" } },
			}),
		);
		renderWithModels(<ModelConfigPage />, "/settings/models?reauth=anthropic");
		await screen.findByRole("dialog", { name: /OAuth 登录/ });
		fireEvent.keyDown(document, { key: "Escape" });
		await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
	});

	it("extractAuthCode accepts a bare code or a callback URL", () => {
		expect(extractAuthCode("  abc ")).toBe("abc");
		expect(extractAuthCode("https://x.test/cb?code=xyz&state=1")).toBe("xyz");
		expect(extractAuthCode("https://x.test/cb")).toBe("https://x.test/cb");
	});
});
