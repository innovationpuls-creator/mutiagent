import { describe, expect, it } from "vitest";
import { type FakeBackend, INTERNAL_TOKEN, fakeBackend, makeApp, signToken } from "./helpers.js";

const REQUEST_ID = /^[A-Za-z0-9._:-]{1,128}$/;
const USER = "00000000-0000-0000-0000-000000000001";

function setup() {
	const backend = fakeBackend();
	backend.users.set(USER, { user_uid: USER, exists: true, role: "student", is_active: true });
	backend.users.set("banned", { user_uid: "banned", exists: true, role: "student", is_active: false });
	return { backend, ...makeApp(backend) };
}

describe("health + request id + access log (AC-1/AC-2)", () => {
	it("live returns ok, a generated request id and a JSON access log", async () => {
		const { app, lines } = setup();
		const res = await app.request("/api/ai/health/live");
		expect(res.status).toBe(200);
		expect(await res.json()).toEqual({ status: "ok" });
		const id = res.headers.get("X-Request-ID") ?? "";
		expect(id).toMatch(REQUEST_ID);
		const log = JSON.parse(lines.at(-1) ?? "{}");
		expect(log).toMatchObject({
			service: "onetree-ai-gateway",
			request_id: id,
			method: "GET",
			path: "/api/ai/health/live",
			status_code: 200,
			message: "request_completed",
			level: "INFO",
		});
		expect(typeof log.duration_ms).toBe("number");
	});

	it("reuses a valid incoming id and replaces an invalid one", async () => {
		const { app } = setup();
		const ok = await app.request("/api/ai/health/live", { headers: { "X-Request-ID": "m1-trace-001" } });
		expect(ok.headers.get("X-Request-ID")).toBe("m1-trace-001");
		const bad = await app.request("/api/ai/health/live", { headers: { "X-Request-ID": "bad id" } });
		expect(bad.headers.get("X-Request-ID")).not.toBe("bad id");
		expect(bad.headers.get("X-Request-ID")).toMatch(REQUEST_ID);
	});

	it("ready reports connected, or 503 unavailable without leaking the token", async () => {
		const { app, backend } = setup();
		const up = await app.request("/api/ai/health/ready");
		expect(up.status).toBe(200);
		expect(await up.json()).toEqual({ status: "ok", backend: "connected" });
		backend.down = true;
		const down = await app.request("/api/ai/health/ready");
		expect(down.status).toBe(503);
		const text = await down.text();
		expect(JSON.parse(text)).toEqual({ status: "error", backend: "unavailable" });
		expect(text).not.toContain(INTERNAL_TOKEN);
	});

	it("404 carries the request id too", async () => {
		const { app } = setup();
		const res = await app.request("/nope");
		expect(res.status).toBe(404);
		expect(res.headers.get("X-Request-ID")).toMatch(REQUEST_ID);
	});
});

describe("ping-auth (AC-4)", () => {
	const get = (app: ReturnType<typeof setup>["app"], token?: string) =>
		app.request("/api/ai/ping-auth", {
			headers: token ? { Authorization: `Bearer ${token}` } : {},
		});

	it("401 with the exact legacy detail for missing / forged / expired / wrong-alg tokens", async () => {
		const { app, backend } = setup();
		const cases = [
			undefined,
			"garbage",
			await signToken(USER, { secret: "other-secret" }),
			await signToken(USER, { expiresIn: Math.floor(Date.now() / 1000) - 60 }),
			await signToken(USER, { alg: "HS512" }),
			await signToken(undefined),
		];
		for (const token of cases) {
			const res = await get(app, token);
			expect(res.status).toBe(401);
			expect(await res.json()).toEqual({ detail: "无效的认证凭证", error_code: "AUTH_INVALID" });
		}
		expect(backend.calls).toHaveLength(0);
	});

	it("200 with user_uid / role for an active account", async () => {
		const { app } = setup();
		const res = await get(app, await signToken(USER));
		expect(res.status).toBe(200);
		expect(await res.json()).toMatchObject({ user_uid: USER, role: "student", status: "ok" });
	});

	it("403 for a disabled account", async () => {
		const { app } = setup();
		const res = await get(app, await signToken("banned"));
		expect(res.status).toBe(403);
		expect(await res.json()).toEqual({ detail: "账号已被禁用", error_code: "ACCOUNT_DISABLED" });
	});

	it("401 用户不存在 (not the auto-logout detail) for unknown uid", async () => {
		const { app } = setup();
		const res = await get(app, await signToken("ghost"));
		expect(res.status).toBe(401);
		expect(((await res.json()) as { detail: string }).detail).toBe("用户不存在");
	});

	it("503 INTERNAL_SERVICE_UNAVAILABLE (never the logout detail) when backend is down", async () => {
		const { app, backend } = setup();
		backend.down = true;
		const res = await get(app, await signToken(USER));
		expect(res.status).toBe(503);
		const body = (await res.json()) as { error_code: string; detail: string };
		expect(body.error_code).toBe("INTERNAL_SERVICE_UNAVAILABLE");
		expect(body.detail).not.toBe("无效的认证凭证");
	});

	it("echoes the same request id in header and body", async () => {
		const { app } = setup();
		const res = await app.request("/api/ai/ping-auth", {
			headers: { Authorization: `Bearer ${await signToken(USER)}`, "X-Request-ID": "m1-trace-001" },
		});
		expect(res.headers.get("X-Request-ID")).toBe("m1-trace-001");
		expect(((await res.json()) as { request_id: string }).request_id).toBe("m1-trace-001");
	});
});

describe("/internal guard", () => {
	const call = (app: ReturnType<typeof setup>["app"], token?: string) =>
		app.request("/internal/health", { headers: token ? { "X-Internal-Token": token } : {} });
	it("401 without, 403 with wrong, 200 with right token", async () => {
		const { app } = setup();
		expect((await call(app)).status).toBe(401);
		expect((await call(app, "wrong")).status).toBe(403);
		expect((await call(app, INTERNAL_TOKEN)).status).toBe(200);
	});
});

export type { FakeBackend };
