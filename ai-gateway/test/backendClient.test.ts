import { describe, expect, it, vi } from "vitest";
import { createBackendClient } from "../src/backendClient.js";
import { BackendBusinessError, GatewayError } from "../src/errors.js";
import { createLogger, requestIdMiddleware } from "../src/observability.js";
import { Hono } from "hono";

function client(fetchImpl: typeof fetch) {
	const logs: string[] = [];
	return {
		logs,
		client: createBackendClient({
			baseUrl: "http://backend:8000",
			internalToken: "secret-token",
			timeoutMs: 50,
			logger: createLogger((l) => logs.push(l)),
			fetchImpl,
		}),
	};
}
const json = (body: unknown, status = 200) =>
	new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

describe("backend client", () => {
	it("injects the internal token and propagates the ambient request id", async () => {
		const fetchImpl = vi.fn(async () => json({ status: "ok", database: "connected" }));
		const { client: c } = client(fetchImpl as unknown as typeof fetch);
		const app = new Hono();
		app.use("*", requestIdMiddleware(() => {}));
		app.get("/x", async (ctx) => ctx.json(await c.getInternalHealth()));
		await app.request("/x", { headers: { "X-Request-ID": "m1-trace-001" } });
		const [url, init] = fetchImpl.mock.calls[0] as unknown as [string, RequestInit];
		expect(url).toBe("http://backend:8000/internal/health");
		const headers = init.headers as Record<string, string>;
		expect(headers["X-Internal-Token"]).toBe("secret-token");
		expect(headers["X-Request-ID"]).toBe("m1-trace-001");
	});

	it("maps 5xx, network failure, timeout and token rejection to 503 without leaking the token", async () => {
		const cases: Array<() => Promise<Response>> = [
			async () => json({}, 500),
			async () => {
				throw new TypeError("fetch failed");
			},
			async () => json({ detail: "内部令牌无效" }, 403),
			async () => json({ detail: "缺少内部令牌" }, 401),
		];
		for (const impl of cases) {
			const { client: c, logs } = client(impl as unknown as typeof fetch);
			const error = await c.getInternalHealth().catch((e: unknown) => e);
			expect(error).toBeInstanceOf(GatewayError);
			expect((error as GatewayError).status).toBe(503);
			expect((error as GatewayError).errorCode).toBe("INTERNAL_SERVICE_UNAVAILABLE");
			expect(logs.join("")).not.toContain("secret-token");
		}
	});

	it("times out slow backends", async () => {
		const slow = ((_: string, init: RequestInit) =>
			new Promise((_, reject) => {
				init.signal?.addEventListener("abort", () => reject(new DOMException("t", "TimeoutError")));
			})) as unknown as typeof fetch;
		const { client: c } = client(slow);
		await expect(c.getInternalHealth()).rejects.toMatchObject({ status: 503 });
	});

	it("passes other 4xx through as business errors", async () => {
		const { client: c } = client((async () => json({ detail: "nope" }, 404)) as unknown as typeof fetch);
		await expect(c.getInternalHealth()).rejects.toBeInstanceOf(BackendBusinessError);
	});

	it("encodes the user uid in the path", async () => {
		const fetchImpl = vi.fn(async () => json({ user_uid: "a/b", exists: true, role: "student", is_active: true }));
		const { client: c } = client(fetchImpl as unknown as typeof fetch);
		await c.getUserAuthStatus("a/b");
		expect((fetchImpl.mock.calls[0] as unknown as [string])[0]).toContain("/users/a%2Fb/auth-status");
	});
});
