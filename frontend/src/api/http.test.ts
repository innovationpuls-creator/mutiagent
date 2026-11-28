import { afterEach, describe, expect, it, vi } from "vitest";

afterEach(() => {
	vi.unstubAllGlobals();
	vi.unstubAllEnvs();
	vi.resetModules();
});

function stubWindow(hostname: string, origin: string, protocol = "http:") {
	vi.stubGlobal("window", { location: { hostname, origin, protocol } });
}

describe("API_BASE_URL", () => {
	it("uses a same-origin relative path on localhost so the Vite proxy splits routes", async () => {
		vi.stubEnv("NODE_ENV", "development");
		vi.stubEnv("VITE_API_BASE_URL", undefined as unknown as string);
		vi.resetModules();
		stubWindow("localhost", "http://localhost:5173");

		const module = await import("./http");

		expect(module.API_BASE_URL).toBe("");
	});

	it("uses a same-origin relative path on 127.0.0.1", async () => {
		vi.stubEnv("NODE_ENV", "development");
		vi.stubEnv("VITE_API_BASE_URL", undefined as unknown as string);
		vi.resetModules();
		stubWindow("127.0.0.1", "http://127.0.0.1:5173");

		const module = await import("./http");

		expect(module.API_BASE_URL).toBe("");
	});

	it("keeps the fixed backend URL in the test environment", async () => {
		vi.stubEnv("NODE_ENV", "test");
		vi.stubEnv("VITE_API_BASE_URL", undefined as unknown as string);
		vi.resetModules();
		stubWindow("localhost", "http://localhost:5173");

		const module = await import("./http");

		expect(module.API_BASE_URL).toBe("http://127.0.0.1:8000");
	});

	it("lets an explicit VITE_API_BASE_URL take priority", async () => {
		vi.stubEnv("NODE_ENV", "development");
		vi.stubEnv("VITE_API_BASE_URL", "http://127.0.0.1:9999");
		vi.resetModules();
		stubWindow("localhost", "http://localhost:5173");

		const module = await import("./http");

		expect(module.API_BASE_URL).toBe("http://127.0.0.1:9999");
	});

	it("uses the current origin for non-local public deployments", async () => {
		vi.stubEnv("NODE_ENV", "development");
		vi.stubEnv("VITE_API_BASE_URL", undefined as unknown as string);
		vi.resetModules();
		stubWindow("app.example.com", "https://app.example.com", "https:");

		const module = await import("./http");

		expect(module.API_BASE_URL).toBe("https://app.example.com");
	});
});

describe("api error code helpers", () => {
	it("accepts only known error codes and non-empty providers", async () => {
		const http = await import("./http");

		expect(http.getApiErrorCode({ error_code: "MODEL_NOT_CONFIGURED" })).toBe(
			"MODEL_NOT_CONFIGURED",
		);
		expect(http.getApiErrorCode({ error_code: "SOMETHING_NEW" })).toBeNull();
		expect(http.getApiErrorCode({})).toBeNull();
		expect(http.getApiErrorCode(null)).toBeNull();
		expect(http.getApiErrorProvider({ provider: "openai-codex" })).toBe(
			"openai-codex",
		);
		expect(http.getApiErrorProvider({ provider: "  " })).toBeNull();
		expect(http.getApiErrorProvider(null)).toBeNull();
		expect([...http.API_ERROR_CODES]).toHaveLength(6);
	});
});
