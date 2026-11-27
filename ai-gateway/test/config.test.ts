import { describe, expect, it } from "vitest";
import {
	ConfigError,
	DEFAULT_INTERNAL_API_TOKEN,
	DEFAULT_JWT_SECRET,
	loadConfig,
} from "../src/config.js";

const prod = {
	APP_ENV: "production",
	JWT_SECRET: "real-secret",
	INTERNAL_API_TOKEN: "real-token",
	PYTHON_BACKEND_URL: "http://backend:8000/",
};

describe("loadConfig", () => {
	it("uses development defaults and warns about the default internal token", () => {
		const warnings: string[] = [];
		const config = loadConfig({}, (m) => warnings.push(m));
		expect(config.port).toBe(8100);
		expect(config.jwtSecret).toBe(DEFAULT_JWT_SECRET);
		expect(config.internalApiToken).toBe(DEFAULT_INTERNAL_API_TOKEN);
		expect(config.pythonBackendUrl).toBe("http://127.0.0.1:8000");
		expect(warnings).toHaveLength(1);
	});

	it("accepts a complete production configuration and trims the backend url", () => {
		const config = loadConfig(prod, () => {});
		expect(config.isProduction).toBe(true);
		expect(config.pythonBackendUrl).toBe("http://backend:8000");
		expect(config.host).toBe("0.0.0.0");
	});

	it.each(["JWT_SECRET", "INTERNAL_API_TOKEN", "PYTHON_BACKEND_URL"])(
		"refuses production start without %s",
		(key) => {
			const env: Record<string, string | undefined> = { ...prod, [key]: undefined };
			expect(() => loadConfig(env, () => {})).toThrow(ConfigError);
		},
	);

	it("refuses default secrets in production", () => {
		expect(() => loadConfig({ ...prod, JWT_SECRET: DEFAULT_JWT_SECRET }, () => {})).toThrow(
			/JWT_SECRET/,
		);
		expect(() =>
			loadConfig({ ...prod, INTERNAL_API_TOKEN: DEFAULT_INTERNAL_API_TOKEN }, () => {}),
		).toThrow(/INTERNAL_API_TOKEN/);
	});

	it("rejects a non-numeric port", () => {
		expect(() => loadConfig({ PORT: "abc" }, () => {})).toThrow(ConfigError);
	});
});
