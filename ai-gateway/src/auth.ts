import type { MiddlewareHandler } from "hono";
import { jwtVerify } from "jose";
import type { BackendClient } from "./backendClient.js";
import { accountDisabled, authInvalid, userNotFound } from "./errors.js";

export interface AuthContext {
	userUid: string;
	role: string;
}

export type AuthVariables = { auth: AuthContext };

const BEARER_PATTERN = /^Bearer\s+(\S+)$/i;

/**
 * Mirrors backend get_current_user: HS256 + shared JWT_SECRET, `sub` is user.uid.
 * Any signature/expiry/shape problem is the exact legacy 401 so the frontend
 * auto-logout contract keeps working; ban/missing-user status comes from Python.
 */
export function jwtAuth(
	jwtSecret: string,
	backend: BackendClient,
): MiddlewareHandler<{ Variables: AuthVariables }> {
	const key = new TextEncoder().encode(jwtSecret);
	return async (c, next) => {
		const match = BEARER_PATTERN.exec(c.req.header("Authorization") ?? "");
		if (!match?.[1]) throw authInvalid();

		let sub: unknown;
		try {
			({ payload: { sub } } = await jwtVerify(match[1], key, { algorithms: ["HS256"] }));
		} catch {
			throw authInvalid();
		}
		if (typeof sub !== "string" || sub === "") throw authInvalid();

		const status = await backend.getUserAuthStatus(sub);
		if (!status.exists) throw userNotFound();
		if (!status.is_active) throw accountDisabled();

		c.set("auth", { userUid: sub, role: status.role ?? "student" });
		await next();
	};
}
