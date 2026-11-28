import { createHash, timingSafeEqual } from "node:crypto";
import type { MiddlewareHandler } from "hono";
import { GatewayError } from "./errors.js";

export const INTERNAL_TOKEN_HEADER = "X-Internal-Token";

function digest(value: string): Buffer {
	return createHash("sha256").update(value, "utf8").digest();
}

/** Constant-time comparison (both sides hashed to equal length first). */
export function tokensMatch(expected: string, provided: string): boolean {
	return timingSafeEqual(digest(expected), digest(provided));
}

/** Guards /internal/* routes that the Python backend calls (M2 hot-invalidation, M8). */
export function requireInternalToken(expectedToken: string): MiddlewareHandler {
	return async (c, next) => {
		const provided = c.req.header(INTERNAL_TOKEN_HEADER);
		if (!provided) throw new GatewayError(401, undefined, "缺少内部令牌");
		if (!tokensMatch(expectedToken, provided)) {
			throw new GatewayError(403, undefined, "内部令牌无效");
		}
		await next();
	};
}
