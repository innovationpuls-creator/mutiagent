import { createHash } from "node:crypto";
import { createProvider } from "@earendil-works/pi-ai";
import { openAICompletionsApi } from "@earendil-works/pi-ai/api/openai-completions.lazy";
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { createApp } from "../src/app.js";
import { BackendBusinessError } from "../src/errors.js";
import type { OAuthLockResult } from "../src/backendClient.js";
import { ModelRuntime } from "../src/models/runtime.js";
import type { RuntimeConfig } from "../src/models/types.js";
import { createLogger } from "../src/observability.js";
import { fakeBackend, signToken, testConfig } from "./helpers.js";
import { type MockUpstream, startMockUpstream } from "./mockUpstream.js";

const USER = "u-oauth-1";
const OTHER = "u-oauth-2";
let upstream: MockUpstream;

beforeAll(async () => {
	upstream = await startMockUpstream();
});
afterAll(async () => {
	await upstream.close();
});

const fingerprint = (refresh: string) => createHash("sha256").update(refresh).digest("hex");

function mockOAuthProvider(counters: { refresh: number }) {
	return createProvider({
		id: "mockoauth",
		name: "Mock OAuth",
		baseUrl: upstream.url,
		auth: {
			oauth: {
				name: "Mock OAuth",
				async login(interaction: any) {
					interaction.notify({ type: "auth_url", url: "https://auth.example.test/authorize?x=1", instructions: "粘贴授权码" });
					const code = await interaction.prompt({ type: "manual_code", message: "code" });
					return { type: "oauth", access: `access-${code}`, refresh: `refresh-${code}`, expires: Date.now() + 3600_000 };
				},
				async refresh(credential: any) {
					counters.refresh += 1;
					await new Promise((r) => setTimeout(r, 50));
					return { ...credential, access: `access-new-${counters.refresh}`, refresh: `refresh-new-${counters.refresh}`, expires: Date.now() + 3600_000 };
				},
				async toAuth(credential: any) {
					return { apiKey: credential.access };
				},
			},
		},
		models: [
			{
				id: "mo-1",
				name: "mo-1",
				api: "openai-completions",
				provider: "mockoauth",
				baseUrl: upstream.url,
				reasoning: false,
				input: ["text"],
				cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
				contextWindow: 8000,
				maxTokens: 1000,
			},
		],
		api: openAICompletionsApi(),
	} as never);
}

function oauthConfig(userUid: string, credential: Record<string, unknown> | null): RuntimeConfig {
	return {
		user_uid: userUid,
		role: "student",
		providers: credential
			? [
					{
						provider_id: "mockoauth",
						display_name: "Mock",
						is_builtin: true,
						protocol: "openai-completions",
						base_url: "",
						headers: {},
						auth_type: "oauth",
						enabled: true,
						api_key: null,
						oauth_credential: credential,
						oauth_refresh_fingerprint: fingerprint(String(credential.refresh)),
					},
				]
			: [],
		custom_models: [],
		preferences: {
			config_mode: "simple",
			default_model_ref: { provider_id: "mockoauth", model_id: "mo-1" },
			default_vision_model_ref: null,
			default_thinking_level: "off",
			runtime_options: {},
			slot_bindings: {},
		},
	};
}

function setup(credential: Record<string, unknown> | null) {
	const counters = { refresh: 0 };
	const backend = fakeBackend();
	for (const uid of [USER, OTHER]) backend.users.set(uid, { user_uid: uid, exists: true, role: "student", is_active: true });
	backend.runtimeConfigs.set(USER, oauthConfig(USER, credential));
	backend.runtimeConfigs.set(OTHER, oauthConfig(OTHER, null));

	// Stateful compare-and-swap, mirroring the Python row-locked implementation.
	let row = credential ? { credential, fingerprint: fingerprint(String(credential.refresh)) } : null;
	backend.oauthRefreshLock = async (_uid, _pid, body) => {
		if (!row) throw new BackendBusinessError(404, "未找到");
		let outcome: OAuthLockResult["outcome"] = "unchanged";
		if (body.new_credential) {
			if (body.previous_refresh_fingerprint === row.fingerprint) {
				row = { credential: body.new_credential, fingerprint: fingerprint(String(body.new_credential.refresh)) };
				outcome = "refreshed";
			} else outcome = "conflict";
		}
		return { outcome, credential: row.credential, refresh_fingerprint: row.fingerprint, expires_at: null };
	};
	const origSave = backend.saveOAuthCredential;
	backend.saveOAuthCredential = async (uid, pid, body) => {
		await origSave(uid, pid, body);
		row = { credential: body.credential, fingerprint: fingerprint(String(body.credential.refresh)) };
	};

	const builtinOverride = [mockOAuthProvider(counters)];
	const runtime = new ModelRuntime({ backend, logger: createLogger(() => {}), builtinOverride });
	const app = createApp({ config: testConfig(), backend, logSink: () => {}, runtime, builtinOverride });
	return { counters, backend, runtime, app, getRow: () => row };
}

const ctx = { messages: [{ role: "user" as const, content: "hi", timestamp: 1 }] };

describe("OAuth concurrent refresh (AC-4)", () => {
	it("5 concurrent calls on an expired token trigger exactly one upstream refresh", async () => {
		const { runtime, counters, getRow } = setup({ access: "old", refresh: "refresh-old", expires: Date.now() - 1000 });
		upstream.requests.length = 0;
		const results = await Promise.all(Array.from({ length: 5 }, () => runtime.complete(USER, "chat_profile", ctx)));
		expect(results.every((r) => r.message.stopReason === "stop")).toBe(true);
		expect(counters.refresh).toBe(1);
		expect(getRow()?.credential.refresh).toBe("refresh-new-1");
		for (const req of upstream.requests) expect(req.headers.authorization).toBe("Bearer access-new-1");
	});

	it("two separate gateway entries (cache miss) still refresh once", async () => {
		const first = setup({ access: "old", refresh: "refresh-old", expires: Date.now() - 1000 });
		const second = new ModelRuntime({ backend: first.backend, logger: createLogger(() => {}), builtinOverride: [mockOAuthProvider(first.counters)] });
		await Promise.all([first.runtime.complete(USER, "chat_profile", ctx), second.complete(USER, "chat_profile", ctx)]);
		expect(first.counters.refresh).toBe(1);
	});

	it("an upstream 401 on an OAuth provider surfaces MODEL_OAUTH_EXPIRED with the provider", async () => {
		const { runtime } = setup({ access: "valid", refresh: "refresh-ok", expires: Date.now() + 3600_000 });
		upstream.script.push(401);
		await expect(runtime.complete(USER, "chat_profile", ctx)).rejects.toMatchObject({
			status: 401,
			errorCode: "MODEL_OAUTH_EXPIRED",
			extras: { provider: "mockoauth" },
		});
	});
});

describe("OAuth login flow (AC-4 ①)", () => {
	async function call(app: any, user: string, path: string, body?: unknown, method = "POST") {
		const token = await signToken(user);
		const res = await app.request(path, {
			method,
			headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
			body: body === undefined ? undefined : JSON.stringify(body),
		});
		return { status: res.status, json: (await res.json()) as any };
	}

	it("start -> paste code -> credential stored once; state is bound to the user and single-use", async () => {
		const { app, backend } = setup(null);
		const start = await call(app, USER, "/api/ai/oauth/mockoauth/start");
		expect(start.status).toBe(200);
		expect(start.json).toMatchObject({ mode: "redirect", auth_url: expect.stringContaining("https://auth.example.test/") });
		const { state } = start.json;

		expect((await call(app, USER, `/api/ai/oauth/mockoauth/status?state=${state}`, undefined, "GET")).json.status).toBe("pending");

		const stolen = await call(app, OTHER, "/api/ai/oauth/mockoauth/complete", { state, code: "abc" });
		expect(stolen.status).toBe(400);

		const done = await call(app, USER, "/api/ai/oauth/mockoauth/complete", { state, code: "abc" });
		expect(done.status).toBe(200);
		expect(done.json.status).toBe("authorized");
		expect(backend.savedCredentials).toHaveLength(1);
		expect((backend.savedCredentials[0]!.credential as any).credential.access).toBe("access-abc");

		const replay = await call(app, USER, "/api/ai/oauth/mockoauth/complete", { state, code: "abc" });
		expect(replay.status).toBe(400);
		expect(backend.savedCredentials).toHaveLength(1);
	});

	it("rejects providers without OAuth support", async () => {
		const { app } = setup(null);
		const res = await call(app, USER, "/api/ai/oauth/nonexistent/start");
		expect(res.status).toBe(422);
	});
});
