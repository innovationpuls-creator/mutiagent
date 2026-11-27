import { cleanup, fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
	CATALOG,
	makeConfig,
	renderWithModels,
	seedAuth,
	stubFetch,
} from "../../test/modelConfigHarness";
import { ModelGuidanceCard, modelErrorInfo } from "./ModelGuidanceCard";
import { ModelQuickSwitcher } from "./ModelQuickSwitcher";

beforeEach(() => {
	seedAuth("student");
});
afterEach(() => {
	cleanup();
	vi.unstubAllGlobals();
});

describe("ModelQuickSwitcher (AC-4)", () => {
	it("shows the current model + thinking level and persists a model switch via quick-switch", async () => {
		const config = makeConfig();
		const { calls } = stubFetch({
			"GET /api/model-config": { json: config },
			"GET /api/ai/models/catalog": { json: { providers: CATALOG } },
			"PATCH /api/model-config/quick-switch": (call) => {
				const body = call.body as {
					model_ref?: unknown;
					thinking_level?: string;
				};
				return {
					json: {
						...config.preferences,
						default_model_ref:
							body.model_ref ?? config.preferences.default_model_ref,
						default_thinking_level:
							body.thinking_level ?? config.preferences.default_thinking_level,
					},
				};
			},
		});
		renderWithModels(<ModelQuickSwitcher />);

		const trigger = await screen.findByRole("button", { name: /GPT Text/ });
		expect(trigger.textContent).toContain("中思考");

		fireEvent.click(trigger);
		fireEvent.click(await screen.findByRole("button", { name: /GPT Vision/ }));
		await waitFor(() =>
			expect(calls.find((c) => c.method === "PATCH")?.body).toEqual({
				model_ref: { provider_id: "openai", model_id: "gpt-vision" },
			}),
		);
		await screen.findByRole("button", { name: /GPT Vision.*中思考/ });

		fireEvent.click(screen.getByRole("button", { name: "极高" }));
		await waitFor(() =>
			expect(calls.filter((c) => c.method === "PATCH").at(-1)?.body).toEqual({
				thinking_level: "xhigh",
			}),
		);
		await screen.findByRole("button", { name: /极高思考/ });
	});

	it("closes on Escape and links to the settings page", async () => {
		stubFetch({
			"GET /api/model-config": { json: makeConfig() },
			"GET /api/ai/models/catalog": { json: { providers: CATALOG } },
		});
		renderWithModels(<ModelQuickSwitcher />);
		fireEvent.click(await screen.findByRole("button", { name: /GPT Text/ }));
		expect(
			screen.getByRole("link", { name: /管理更多模型/ }).getAttribute("href"),
		).toBe("/settings/models");
		fireEvent.keyDown(document, { key: "Escape" });
		await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
	});
});

describe("ModelGuidanceCard (AC-5)", () => {
	it("MODEL_NOT_CONFIGURED links straight to the settings page", () => {
		stubFetch({});
		renderWithModels(
			<ModelGuidanceCard info={{ errorCode: "MODEL_NOT_CONFIGURED" }} />,
		);
		expect(screen.getByText(/请先配置你的个人 AI 模型/)).toBeTruthy();
		expect(
			screen.getByRole("link", { name: "去配置模型" }).getAttribute("href"),
		).toBe("/settings/models");
	});

	it("MODEL_OAUTH_EXPIRED names the provider and deep-links to re-login", async () => {
		const config = makeConfig();
		config.providers[0] = {
			...config.providers[0]!,
			provider_id: "anthropic",
			display_name: "Claude 订阅",
		};
		stubFetch({
			"GET /api/model-config": { json: config },
			"GET /api/ai/models/catalog": { json: { providers: CATALOG } },
		});
		renderWithModels(
			<ModelGuidanceCard
				info={{ errorCode: "MODEL_OAUTH_EXPIRED", provider: "anthropic" }}
			/>,
		);
		await screen.findByText(/「Claude 订阅」的授权已失效/);
		expect(
			screen
				.getByRole("link", { name: /重新登录 Claude 订阅/ })
				.getAttribute("href"),
		).toBe("/settings/models?reauth=anthropic");
	});

	it("admins are sent to /admin/models", () => {
		seedAuth("admin");
		stubFetch({});
		renderWithModels(
			<ModelGuidanceCard info={{ errorCode: "MODEL_NOT_CONFIGURED" }} />,
			"/admin/data",
		);
		expect(
			screen.getByRole("link", { name: "去配置模型" }).getAttribute("href"),
		).toBe("/admin/models");
	});

	it("modelErrorInfo only returns guidance-relevant errors", () => {
		expect(modelErrorInfo({ errorCode: "MODEL_NOT_CONFIGURED" })).toMatchObject(
			{ errorCode: "MODEL_NOT_CONFIGURED" },
		);
		expect(modelErrorInfo({ errorCode: "AUTH_INVALID" })).toBeNull();
		expect(modelErrorInfo(new Error("x"))).toBeNull();
	});
});

describe("ModelConfigProvider resilience", () => {
	it("ignores malformed config payloads instead of crashing consumers", async () => {
		stubFetch({
			"GET /api/model-config": { json: {} },
			"GET /api/ai/models/catalog": { json: { providers: CATALOG } },
		});
		renderWithModels(<ModelQuickSwitcher />);
		await new Promise((resolve) => setTimeout(resolve, 30));
		expect(screen.queryByRole("button", { name: /思考/ })).toBeNull();
	});
});
