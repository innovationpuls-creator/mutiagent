import {
	type AssistantMessage,
	type Context,
	type CredentialStore,
	type Model,
	type MutableModels,
	type Provider,
	getSupportedThinkingLevels,
} from "@earendil-works/pi-ai";
import type { BackendClient, UsageReport } from "../backendClient.js";
import { modelOAuthExpired, upstreamModelError } from "../errors.js";
import { type Logger, getRequestId } from "../observability.js";
import { createBackendCredentialStore } from "./credentialStore.js";
import { type ResolvedScene, resolveScene } from "./resolver.js";
import type { ModelRef, RuntimeConfig, RuntimeProvider, Scene, ThinkingLevel } from "./types.js";
import { buildUserModels } from "./userModels.js";

export interface UserEntry {
	config: RuntimeConfig;
	models: MutableModels;
	store: CredentialStore;
}

export interface RuntimeDeps {
	backend: BackendClient;
	logger: Logger;
	ttlMs?: number;
	builtinOverride?: Provider[];
	now?: () => number;
}

export interface Attempt {
	ref: ModelRef;
	ok: boolean;
	error?: string;
	error_code?: string;
	latency_ms: number;
}

export interface SceneResult {
	message: AssistantMessage;
	used: ModelRef;
	thinking_level: ThinkingLevel;
	attempts: Attempt[];
}

export type FailureKind = "oauth" | "fallback" | "fatal";

const TRANSIENT = /timeout|timed out|etimedout|econnreset|econnrefused|enotfound|fetch failed|network|overloaded|socket hang up/i;
const OAUTH_HINT = /oauth|refresh|invalid_grant|token (has )?expired|unauthori[sz]ed/i;

export function classifyFailure(
	message: string,
	provider: RuntimeProvider | undefined,
): { kind: FailureKind; code: string } {
	const status = /^(\d{3})\b/.exec(message.trim())?.[1];
	const code = status ? Number(status) : undefined;
	if (provider?.auth_type === "oauth" && (code === 401 || code === 403 || OAUTH_HINT.test(message))) {
		return { kind: "oauth", code: "MODEL_OAUTH_EXPIRED" };
	}
	if (code === 429) return { kind: "fallback", code: "HTTP_429" };
	if (code !== undefined && code >= 500) return { kind: "fallback", code: `HTTP_${code}` };
	if (TRANSIENT.test(message)) return { kind: "fallback", code: "UPSTREAM_TIMEOUT" };
	return { kind: "fatal", code: code ? `HTTP_${code}` : "UPSTREAM_ERROR" };
}

type Reasoning = Exclude<ThinkingLevel, "off">;

function pickReasoning(model: Model<never>, level: ThinkingLevel): Reasoning | undefined {
	if (level === "off" || !model.reasoning) return undefined;
	const supported = getSupportedThinkingLevels(model) as string[];
	if (supported.includes(level)) return level as Reasoning;
	const order: Reasoning[] = ["xhigh", "high", "medium", "low", "minimal"];
	return order.find((candidate) => supported.includes(candidate) && order.indexOf(candidate) >= order.indexOf(level));
}

export class ModelRuntime {
	private readonly cache = new Map<string, { expiresAt: number; entry: Promise<UserEntry> }>();
	private readonly pending = new Set<Promise<unknown>>();
	private readonly ttlMs: number;
	private readonly now: () => number;

	constructor(private readonly deps: RuntimeDeps) {
		this.ttlMs = deps.ttlMs ?? 60_000;
		this.now = deps.now ?? Date.now;
	}

	async buildEntry(config: RuntimeConfig): Promise<UserEntry> {
		const store = createBackendCredentialStore(config.user_uid, config, this.deps.backend);
		const models = buildUserModels(config, store, { builtinOverride: this.deps.builtinOverride });
		return { config, models, store };
	}

	getEntry(userUid: string): Promise<UserEntry> {
		const cached = this.cache.get(userUid);
		if (cached && cached.expiresAt > this.now()) return cached.entry;
		const entry = this.deps.backend
			.getModelRuntimeConfig(userUid)
			.then((config) => this.buildEntry(config));
		this.cache.set(userUid, { expiresAt: this.now() + this.ttlMs, entry });
		entry.catch(() => {
			if (this.cache.get(userUid)?.entry === entry) this.cache.delete(userUid);
		});
		return entry;
	}

	invalidate(userUid: string): boolean {
		return this.cache.delete(userUid);
	}

	async resolve(userUid: string, scene: Scene): Promise<{ entry: UserEntry; resolved: ResolvedScene }> {
		const entry = await this.getEntry(userUid);
		return { entry, resolved: resolveScene(entry.config, scene) };
	}

	/** Wait for in-flight usage reports (tests, graceful shutdown). */
	async flush(): Promise<void> {
		await Promise.allSettled([...this.pending]);
	}

	private report(userUid: string, usage: UsageReport): void {
		const task = this.deps.backend
			.postModelUsage(userUid, usage)
			.catch(() => this.deps.logger.warn(`model_usage_report_failed scene=${usage.scene} model=${usage.model_id}`))
			.finally(() => this.pending.delete(task));
		this.pending.add(task);
	}

	async complete(
		userUid: string,
		scene: Scene,
		context: Context,
		options: { signal?: AbortSignal; sessionId?: string } = {},
	): Promise<SceneResult> {
		const { entry, resolved } = await this.resolve(userUid, scene);
		const attempts: Attempt[] = [];
		const hasFallback = resolved.targets.length > 1;
		let lastError = "没有可用的模型";
		for (const ref of resolved.targets) {
			const provider = entry.config.providers.find((p) => p.provider_id === ref.provider_id);
			const model = entry.models.getModel(ref.provider_id, ref.model_id);
			if (!model) {
				attempts.push({ ref, ok: false, error: "模型不存在", error_code: "MODEL_NOT_FOUND", latency_ms: 0 });
				lastError = `模型 ${ref.model_id} 不存在`;
				continue;
			}
			const opts = resolved.options;
			const startedAt = performance.now();
			let message: AssistantMessage;
			try {
				message = await entry.models.completeSimple(model, context, {
					reasoning: pickReasoning(model as never, resolved.thinkingLevel),
					temperature: opts.temperature ?? undefined,
					maxTokens: opts.max_tokens ?? undefined,
					timeoutMs: opts.timeout_seconds ? opts.timeout_seconds * 1000 : undefined,
					maxRetries: opts.max_retries ?? (hasFallback ? 0 : undefined),
					cacheRetention: opts.cache_retention ?? undefined,
					sessionId: options.sessionId,
					signal: options.signal,
				});
			} catch (error) {
				message = {
					stopReason: "error",
					errorMessage: error instanceof Error ? error.message : String(error),
				} as AssistantMessage;
			}
			const latency = Math.round(performance.now() - startedAt);
			const usage = message.usage;
			const failed = message.stopReason === "error" || message.stopReason === "aborted";
			const failure = failed ? classifyFailure(message.errorMessage ?? "", provider) : undefined;
			this.report(userUid, {
				request_id: getRequestId() ?? null,
				scene,
				provider_id: ref.provider_id,
				model_id: ref.model_id,
				thinking_level: resolved.thinkingLevel,
				input_tokens: usage?.input ?? 0,
				output_tokens: usage?.output ?? 0,
				cache_read_tokens: usage?.cacheRead ?? 0,
				cache_write_tokens: usage?.cacheWrite ?? 0,
				reasoning_tokens: usage?.reasoning ?? 0,
				estimated_cost_usd: usage?.cost?.total ?? 0,
				latency_ms: latency,
				success: !failed,
				error_code: failure?.code ?? null,
			});
			if (!failure) {
				attempts.push({ ref, ok: true, latency_ms: latency });
				return { message, used: ref, thinking_level: resolved.thinkingLevel, attempts };
			}
			attempts.push({ ref, ok: false, error: (message.errorMessage ?? "").slice(0, 200), error_code: failure.code, latency_ms: latency });
			lastError = message.errorMessage ?? lastError;
			if (failure.kind === "oauth") throw modelOAuthExpired(ref.provider_id);
			if (failure.kind === "fatal") throw upstreamModelError(`模型调用失败：${lastError.slice(0, 200)}`);
		}
		throw upstreamModelError(`所有候选模型均不可用：${lastError.slice(0, 200)}`);
	}
}
