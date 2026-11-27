import { SignJWT } from "jose";
import type {
	BackendClient,
	ChatContext,
	LearningOverview,
	TurnPayload,
	UsageReport,
	UserAuthStatus,
} from "../src/backendClient.js";
import type { RuntimeConfig } from "../src/models/types.js";
import { createApp } from "../src/app.js";
import { type GatewayConfig, loadConfig } from "../src/config.js";
import { BackendBusinessError, internalServiceUnavailable } from "../src/errors.js";

export const JWT_SECRET = "test-jwt-secret";
export const INTERNAL_TOKEN = "test-internal-token";

export function testConfig(overrides: Partial<GatewayConfig> = {}): GatewayConfig {
	return {
		...loadConfig({ JWT_SECRET, INTERNAL_API_TOKEN: INTERNAL_TOKEN }, () => {}),
		...overrides,
	};
}

export interface FakeBackend extends BackendClient {
	users: Map<string, UserAuthStatus>;
	down: boolean;
	calls: string[];
	runtimeConfigs: Map<string, RuntimeConfig>;
	usage: Array<{ userUid: string; usage: UsageReport }>;
	savedCredentials: Array<{ userUid: string; providerId: string; credential: unknown }>;
	contexts: Map<string, ChatContext>;
	turns: Array<{ sessionId: string; userUid: string; turn: TurnPayload }>;
	profiles: Array<{ userUid: string; profile: Record<string, unknown> }>;
	overviews: Map<string, LearningOverview>;
	/** Raw SSE text returned by the legacy bridge, if a test scripts one. */
	legacyFrames: string | null;
	legacyCalls: Array<{ sessionId: string; userUid: string; message: string }>;
	order: string[];
}

export function fakeBackend(): FakeBackend {
	const backend: FakeBackend = {
		users: new Map(),
		down: false,
		calls: [],
		runtimeConfigs: new Map(),
		usage: [],
		savedCredentials: [],
		contexts: new Map(),
		turns: [],
		profiles: [],
		overviews: new Map(),
		legacyFrames: null,
		legacyCalls: [],
		order: [],
		async getChatContext(sessionId, userUid) {
			backend.calls.push(`context:${sessionId}`);
			const context = backend.contexts.get(`${userUid}:${sessionId}`);
			if (!context) throw new BackendBusinessError(404, "会话不存在");
			return structuredClone(context);
		},
		async persistTurn(sessionId, userUid, turn) {
			backend.order.push("persist");
			backend.turns.push({ sessionId, userUid, turn });
			return { persisted: turn.assistant_message ? "full" : "user_only" };
		},
		async putStudentProfile(userUid, profile) {
			backend.order.push("profile");
			backend.profiles.push({ userUid, profile });
		},
		async getLearningOverview(userUid) {
			backend.calls.push(`overview:${userUid}`);
			const overview = backend.overviews.get(userUid);
			if (!overview) throw new Error(`no overview for ${userUid}`);
			return overview;
		},
		async openLegacyStream(sessionId, userUid, body) {
			backend.calls.push(`legacy:${sessionId}`);
			backend.legacyCalls.push({ sessionId, userUid, message: body.message });
			return new Response(backend.legacyFrames ?? "", { status: 200 });
		},
		async getModelRuntimeConfig(uid) {
			backend.calls.push(`runtime:${uid}`);
			if (backend.down) throw internalServiceUnavailable();
			const config = backend.runtimeConfigs.get(uid);
			if (!config) throw new Error(`no runtime config for ${uid}`);
			return config;
		},
		async oauthRefreshLock() {
			return { outcome: "unchanged" } as never;
		},
		async saveOAuthCredential(userUid, providerId, credential) {
			backend.savedCredentials.push({ userUid, providerId, credential });
		},
		async postModelUsage(userUid, usage) {
			backend.usage.push({ userUid, usage });
		},
		async getInternalHealth() {
			backend.calls.push("health");
			if (backend.down) throw internalServiceUnavailable();
			return { status: "ok", database: "connected" };
		},
		async getUserAuthStatus(uid) {
			backend.calls.push(`user:${uid}`);
			if (backend.down) throw internalServiceUnavailable();
			return (
				backend.users.get(uid) ?? { user_uid: uid, exists: false, role: null, is_active: false }
			);
		},
	};
	return backend;
}

export function makeApp(backend: BackendClient, config = testConfig()) {
	const lines: string[] = [];
	const app = createApp({ config, backend, logSink: (line) => lines.push(line) });
	return { app, lines };
}

export async function signToken(
	sub: string | undefined,
	options: { secret?: string; expiresIn?: string | number; alg?: "HS256" | "HS512" } = {},
): Promise<string> {
	const jwt = new SignJWT({}).setProtectedHeader({ alg: options.alg ?? "HS256" });
	if (sub !== undefined) jwt.setSubject(sub);
	jwt.setExpirationTime(options.expiresIn ?? "2h");
	return jwt.sign(new TextEncoder().encode(options.secret ?? JWT_SECRET));
}
