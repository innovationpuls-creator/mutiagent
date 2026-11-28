import { describe, expect, it } from "vitest";
import { modelNotConfigured, modelOAuthExpired } from "../src/errors.js";
import { errorEventFromGatewayError } from "../src/sse.js";

describe("model error codes", () => {
	it("HTTP bodies keep detail and add error_code/provider/action", () => {
		expect(modelNotConfigured().status).toBe(428);
		expect(modelNotConfigured().toBody()).toMatchObject({
			error_code: "MODEL_NOT_CONFIGURED",
			action: "open_model_settings",
		});
		const expired = modelOAuthExpired("openai-codex");
		expect(expired.status).toBe(401);
		expect(expired.toBody()).toMatchObject({ error_code: "MODEL_OAUTH_EXPIRED", provider: "openai-codex" });
		expect(expired.toBody().detail).not.toBe("无效的认证凭证");
	});

	it("SSE error events carry the same fields", () => {
		expect(errorEventFromGatewayError(modelOAuthExpired("openai-codex"))).toMatchObject({
			error_code: "MODEL_OAUTH_EXPIRED",
			provider: "openai-codex",
			recoverable: true,
			retryable: false,
		});
	});
});
