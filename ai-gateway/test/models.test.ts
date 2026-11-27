import { afterAll, beforeAll, beforeEach, describe, expect, it } from "vitest";
import { createApp } from "../src/app.js";
import { ModelRuntime } from "../src/models/runtime.js";
import type { RuntimeConfig, RuntimeCustomModel, RuntimeProvider } from "../src/models/types.js";
import { createLogger } from "../src/observability.js";
import { type FakeBackend, fakeBackend, signToken, testConfig } from "./helpers.js";
import { type MockUpstream, startMockUpstream } from "./mockUpstream.js";

const USER = "u-model-1";
const EMPTY_USER = "u-empty";

let primary: MockUpstream;
let backup: MockUpstream;

beforeAll(async () => {
	primary = await startMockUpstream();
	backup = await startMockUpstream();
});
afterAll(async () => {
	await primary.close();
	await backup.close();
});

function provider(id: string, baseUrl: string, extra: Partial<RuntimeProvider> = {}): RuntimeProvider {
	return {
		provider_id: id,
		display_name: id,
		is_builtin: false,
		protocol: "openai-completions",
		base_url: baseUrl,
		headers: { "X-Tenant": "acme" },
		auth_type: "api_key",
		enabled: true,
		api_key: "sk-test-key-1234",
		oauth_credential: null,
		oauth_refresh_fingerprint: null,
		...extra,
	};
}

function model(providerId: string, modelId: string, extra: Partial<RuntimeCustomModel> = {}): RuntimeCustomModel {
	return {
		id: `${providerId}-${modelId}`,
		provider_id: providerId,
		model_id: modelId,
		display_name: modelId,
		context_window: 8000,
		max_tokens: 1000,
		supports_vision: false,
		supports_tools: true,
		supports_reasoning: false,
		compat_config: {},
		pricing: { input: 1, output: 2 },
		enabled: true,
		...extra,
	};
}

function config(overrides: Partial<RuntimeConfig> = {}): RuntimeConfig {
	return {
		user_uid: USER,
		role: "student",
		providers: [provider("p1", primary.url), provider("p2", backup.url)],
		custom_models: [model("p1", "m-main"), model("p2", "m-backup")],
		preferences: {
			config_mode: "advanced",
			default_model_ref: { provider_id: "p1", model_id: "m-main" },
			default_vision_model_ref: null,
			default_thinking_level: "off",
			runtime_options: {},
			slot_bindings: {
				chat_profile: {
					model_ref: { provider_id: "p1", model_id: "m-main" },
					fallback_chain: [{ provider_id: "p2", model_id: "m-backup" }],
				},
			},
		},
		...overrides,
	};
}

const emptyConfig = (): RuntimeConfig => ({
	user_uid: EMPTY_USER,
	role: "student",
	providers: [],
	custom_models: [],
	preferences: {
		config_mode: "simple",
		default_model_ref: null,
		default_vision_model_ref: null,
		default_thinking_level: "medium",
		runtime_options: {},
		slot_bindings: {},
	},
});

function setup() {
	const backend: FakeBackend = fakeBackend();
	for (const uid of [USER, EMPTY_USER]) {
		backend.users.set(uid, { user_uid: uid, exists: true, role: "student", is_active: true });
	}
	backend.runtimeConfigs.set(USER, config());
	backend.runtimeConfigs.set(EMPTY_USER, emptyConfig());
	const logger = createLogger(() => {});
	const runtime = new ModelRuntime({ backend, logger });
	const app = createApp({ config: testConfig(), backend, logSink: () => {}, runtime });
	return { backend, runtime, app };
}

const ctx = { messages: [{ role: "user" as const, content: "hi", timestamp: 1 }] };

beforeEach(() => {
	for (const m of [primary, backup]) {
		m.requests.length = 0;
		m.script.length = 0;
		m.reply = "OK";
	}
});

describe("custom provider runtime (AC-2)", () => {
	it("passes custom headers, api key and compat settings to the upstream", async () => {
		const { backend, runtime } = setup();
		backend.runtimeConfigs.set(
			USER,
			config({ custom_models: [model("p1", "m-main", { compat_config: { maxTokensField: "max_tokens" } }), model("p2", "m-backup")] }),
		);
		const result = await runtime.complete(USER, "path_outline", ctx);
		expect(result.message.stopReason).toBe("stop");
		const req = primary.requests[0]!;
		expect(req.headers["x-tenant"]).toBe("acme");
		expect(req.headers.authorization).toBe("Bearer sk-test-key-1234");
		expect(req.body.model).toBe("m-main");
		expect(req.body.max_tokens).toBeDefined();
		expect(req.body.max_completion_tokens).toBeUndefined();
	});
});

describe("fallback, hot invalidation and usage (AC-6)", () => {
	it("falls back to the backup on 429 and on 500", async () => {
		const { runtime, backend } = setup();
		for (const status of [429, 500]) {
			primary.script.push(status);
			const result = await runtime.complete(USER, "chat_profile", ctx);
			expect(result.used.model_id).toBe("m-backup");
			expect(result.message.stopReason).toBe("stop");
			expect(result.attempts.map((a) => a.ok)).toEqual([false, true]);
		}
		await runtime.flush();
		const failures = backend.usage.filter((u) => !u.usage.success);
		expect(failures.map((f) => f.usage.error_code)).toEqual(["HTTP_429", "HTTP_500"]);
		expect(backend.usage.filter((u) => u.usage.success)).toHaveLength(2);
	});

	it("reports tokens, estimated cost and latency", async () => {
		const { runtime, backend } = setup();
		await runtime.complete(USER, "chat_profile", ctx);
		await runtime.flush();
		const row = backend.usage[0]!.usage;
		expect(row).toMatchObject({ scene: "chat_profile", provider_id: "p1", model_id: "m-main", input_tokens: 12, output_tokens: 3, success: true });
		expect(row.estimated_cost_usd).toBeGreaterThan(0);
		expect(row.latency_ms).toBeGreaterThanOrEqual(0);
	});

	it("serves cached config until invalidated, then applies the new one immediately", async () => {
		const { runtime, backend, app } = setup();
		await runtime.complete(USER, "path_outline", ctx);
		expect(primary.requests).toHaveLength(1);

		const switched = config();
		switched.preferences.default_model_ref = { provider_id: "p2", model_id: "m-backup" };
		backend.runtimeConfigs.set(USER, switched);

		await runtime.complete(USER, "path_outline", ctx);
		expect(primary.requests).toHaveLength(2); // stale cache still points at p1

		const res = await app.request("/internal/cache/invalidate-user-model-config", {
			method: "POST",
			headers: { "X-Internal-Token": "test-internal-token", "Content-Type": "application/json" },
			body: JSON.stringify({ user_uid: USER }),
		});
		expect(res.status).toBe(200);
		await runtime.complete(USER, "path_outline", ctx);
		expect(backup.requests).toHaveLength(1);
		expect(primary.requests).toHaveLength(2);
	});

	it("surfaces a non-retryable upstream error without fallback", async () => {
		const { runtime } = setup();
		primary.script.push(400);
		await expect(runtime.complete(USER, "chat_profile", ctx)).rejects.toMatchObject({ status: 502 });
		expect(backup.requests).toHaveLength(0);
	});
});

describe("unconfigured users (AC-7)", () => {
	it("returns 428 MODEL_NOT_CONFIGURED and never uses global env keys", async () => {
		process.env.OPENAI_API_KEY = "sk-global-should-never-be-used";
		const { app } = setup();
		const token = await signToken(EMPTY_USER);
		const res = await app.request("/api/ai/models/scene-check", {
			method: "POST",
			headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
			body: JSON.stringify({ scene: "chat_profile" }),
		});
		expect(res.status).toBe(428);
		expect(await res.json()).toMatchObject({ error_code: "MODEL_NOT_CONFIGURED", action: "open_model_settings" });
		process.env.OPENAI_API_KEY = undefined;
		delete process.env.OPENAI_API_KEY;
	});
});

describe("probe (AC-5)", () => {
	async function probe(app: ReturnType<typeof setup>["app"], body: unknown) {
		const token = await signToken(USER);
		const res = await app.request("/api/ai/models/probe", {
			method: "POST",
			headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
			body: JSON.stringify(body),
		});
		return { status: res.status, json: (await res.json()) as any };
	}

	it("reports text/tools ok, vision skipped for a text-only model, with first-token latency", async () => {
		const { app } = setup();
		const { status, json } = await probe(app, { provider_id: "p1", model_id: "m-main" });
		expect(status).toBe(200);
		expect(json.text.status).toBe("ok");
		expect(typeof json.text.first_token_ms).toBe("number");
		expect(json.tools.status).toBe("ok");
		expect(json.vision.status).toBe("skipped");
	});

	it("probes vision for an image-capable model", async () => {
		const { app, backend } = setup();
		backend.runtimeConfigs.set(
			USER,
			config({ custom_models: [model("p1", "m-main", { supports_vision: true }), model("p2", "m-backup")] }),
		);
		const { json } = await probe(app, { provider_id: "p1", model_id: "m-main" });
		expect(json.vision.status).toBe("ok");
		const visionReq = primary.requests.at(-1)!;
		expect(JSON.stringify(visionReq.body.messages)).toContain("image_url");
	});

	it("explains an invalid key without leaking it", async () => {
		const { app } = setup();
		primary.script.push(401);
		const { json } = await probe(app, { provider_id: "p1", model_id: "m-main" });
		expect(json.text.status).toBe("failed");
		expect(json.text.reason).toContain("认证失败");
		expect(JSON.stringify(json)).not.toContain("sk-test-key-1234");
		expect(json.tools.status).toBe("skipped");
	});
});

describe("catalog", () => {
	it("lists Pi built-in providers with capability metadata", async () => {
		const { app } = setup();
		const token = await signToken(USER);
		const res = await app.request("/api/ai/models/catalog", { headers: { Authorization: `Bearer ${token}` } });
		expect(res.status).toBe(200);
		const body = (await res.json()) as any;
		expect(body.providers.length).toBeGreaterThan(5);
		const openai = body.providers.find((p: any) => p.id === "openai");
		expect(openai.models[0]).toHaveProperty("vision");
		expect(openai.models[0]).toHaveProperty("context_window");
	});
});
