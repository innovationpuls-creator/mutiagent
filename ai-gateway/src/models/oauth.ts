import { randomBytes } from "node:crypto";
import type { AuthEvent, AuthPrompt } from "@earendil-works/pi-ai";
import { GatewayError, upstreamModelError } from "../errors.js";
import type { ModelRuntime, UserEntry } from "./runtime.js";

const SESSION_TTL_MS = 10 * 60 * 1000;
const START_WAIT_MS = 15_000;

export type OAuthStatus = "pending" | "authorized" | "failed" | "expired";

interface Session {
	state: string;
	userUid: string;
	providerId: string;
	createdAt: number;
	status: OAuthStatus;
	error?: string;
	submitCode?: (code: string) => void;
	abort: AbortController;
	done: Promise<void>;
}

export interface StartResult {
	state: string;
	mode: "redirect" | "device_code";
	auth_url?: string;
	instructions?: string;
	user_code?: string;
	verification_uri?: string;
	expires_in_seconds: number;
}

/**
 * Drives Pi's own provider login flow. State is a one-time random id bound to
 * the user (10 min); the login runs in the gateway, the pasted code is handed to
 * Pi's `manual_code` prompt, and Pi's local callback server (when reachable) wins
 * the race for the automatic mode.
 */
export class OAuthSessions {
	private readonly sessions = new Map<string, Session>();

	constructor(
		private readonly runtime: ModelRuntime,
		private readonly now: () => number = Date.now,
	) {}

	private sweep(): void {
		for (const [state, session] of this.sessions) {
			if (this.now() - session.createdAt > SESSION_TTL_MS) {
				session.abort.abort();
				this.sessions.delete(state);
			}
		}
	}

	private get(userUid: string, providerId: string, state: string): Session {
		this.sweep();
		const session = this.sessions.get(state);
		if (!session || session.userUid !== userUid || session.providerId !== providerId) {
			throw new GatewayError(400, undefined, "授权会话无效或已过期，请重新发起授权");
		}
		return session;
	}

	async start(userUid: string, providerId: string): Promise<StartResult> {
		this.sweep();
		const entry = await this.runtime.getEntry(userUid);
		const provider = entry.models.getProvider(providerId);
		if (!provider?.auth?.oauth) {
			throw new GatewayError(422, undefined, "该服务商不支持 OAuth 登录");
		}
		const state = randomBytes(24).toString("base64url");
		const abort = new AbortController();
		let announce!: (event: AuthEvent) => void;
		const announced = new Promise<AuthEvent>((resolve) => (announce = resolve));
		let resolveCode: ((code: string) => void) | undefined;

		const session: Session = {
			state,
			userUid,
			providerId,
			createdAt: this.now(),
			status: "pending",
			abort,
			done: Promise.resolve(),
		};
		session.submitCode = (code) => resolveCode?.(code);

		const interaction = {
			signal: abort.signal,
			notify: (event: AuthEvent) => {
				if (event.type === "auth_url" || event.type === "device_code") announce(event);
			},
			prompt: (prompt: AuthPrompt) => {
				if (prompt.type !== "manual_code") {
					return Promise.reject(new Error("不支持的交互类型"));
				}
				return new Promise<string>((resolve, reject) => {
					resolveCode = resolve;
					const cancel = () => reject(new Error("授权已取消"));
					abort.signal.addEventListener("abort", cancel, { once: true });
					prompt.signal?.addEventListener("abort", cancel, { once: true });
				});
			},
		};

		session.done = entry.models
			.login(providerId, "oauth", interaction)
			.then(() => {
				session.status = "authorized";
				this.runtime.invalidate(userUid);
			})
			.catch((error: unknown) => {
				if (session.status === "pending") {
					session.status = "failed";
					session.error = error instanceof Error ? error.message.slice(0, 200) : "授权失败";
				}
			});
		this.sessions.set(state, session);

		const first = await Promise.race([
			announced,
			session.done.then(() => undefined),
			new Promise<undefined>((resolve) => setTimeout(() => resolve(undefined), START_WAIT_MS)),
		]);
		if (!first) {
			abort.abort();
			this.sessions.delete(state);
			throw upstreamModelError(session.error ?? "未能获取授权链接，请稍后重试");
		}
		const base = { state, expires_in_seconds: SESSION_TTL_MS / 1000 };
		if (first.type === "device_code") {
			return {
				...base,
				mode: "device_code",
				user_code: first.userCode,
				verification_uri: first.verificationUri,
			};
		}
		if (first.type !== "auth_url") throw upstreamModelError("未能获取授权链接");
		return { ...base, mode: "redirect", auth_url: first.url, instructions: first.instructions };
	}

	async complete(userUid: string, providerId: string, state: string, code: string): Promise<{ status: OAuthStatus }> {
		const session = this.get(userUid, providerId, state);
		if (session.status === "pending" && session.submitCode) {
			const submit = session.submitCode;
			session.submitCode = undefined; // single use
			submit(code);
		}
		await session.done;
		if (session.status === "failed") {
			throw new GatewayError(400, undefined, `授权失败：${session.error ?? "未知错误"}`);
		}
		this.sessions.delete(state);
		return { status: session.status };
	}

	status(userUid: string, providerId: string, state: string): { status: OAuthStatus; error?: string } {
		const session = this.sessions.get(state);
		if (!session || session.userUid !== userUid || session.providerId !== providerId) {
			return { status: "expired" };
		}
		if (this.now() - session.createdAt > SESSION_TTL_MS) return { status: "expired" };
		return { status: session.status, error: session.error };
	}
}

export type { UserEntry };
