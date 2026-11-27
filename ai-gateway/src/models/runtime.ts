import {
	type Api,
	type AssistantMessage,
	type AssistantMessageEventStream,
	createAssistantMessageEventStream,
	type Context,
	type CredentialStore,
	type Model,
	type MutableModels,
	type Provider,
	type SimpleStreamOptions,
	type TranscriptContext,
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

/** `Agent`-compatible stream function plus the model it should start from. */
export interface AgentStreamHandle {
	model: Model<Api>;
	streamFn: (
		model: Model<Api>,
		context: TranscriptContext,
		options?: SimpleStreamOptions,
	) => AssistantMessageEventStream;
	resolved: ResolvedScene;
	/** Set when the last attempt of a stream failed; lets the caller raise a typed error. */
	lastFailure?: { kind: FailureKind; code: string; provider: string; message: string };
}

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

	/**
	 * Streaming counterpart of `complete` for Pi's agent loop. The returned `streamFn`
	 * ignores the model the loop passes in: it walks the scene's candidate chain and
	 * only falls back while nothing has been streamed yet (so the client never sees a
	 * half answer from one model followed by another). Usage is reported per attempt.
	 */
	async agentStream(userUid: string, scene: Scene): Promise<AgentStreamHandle> {
		const { entry, resolved } = await this.resolve(userUid, scene);
		const usable = resolved.targets
			.map((ref) => ({ ref, model: entry.models.getModel(ref.provider_id, ref.model_id) }))
			.filter((candidate): candidate is { ref: ModelRef; model: Model<Api> } => candidate.model !== undefined);
		const first = usable[0];
		if (!first) throw upstreamModelError("没有可用的模型");
		const hasFallback = usable.length > 1;

		const handle: AgentStreamHandle = { model: first.model, streamFn: undefined as never, resolved };
		const streamFn: AgentStreamHandle["streamFn"] = (_model, context, options) => {
			const outer = createAssistantMessageEventStream();
			void (async () => {
				let lastError = "没有可用的模型";
				for (const [index, candidate] of usable.entries()) {
					const provider = entry.config.providers.find((p) => p.provider_id === candidate.ref.provider_id);
					const opts = resolved.options;
					const startedAt = performance.now();
					const source = entry.models.streamSimple(candidate.model, context as unknown as Context, {
						...options,
						reasoning: pickReasoning(candidate.model as never, resolved.thinkingLevel),
						temperature: opts.temperature ?? undefined,
						maxTokens: opts.max_tokens ?? undefined,
						timeoutMs: opts.timeout_seconds ? opts.timeout_seconds * 1000 : undefined,
						maxRetries: opts.max_retries ?? (hasFallback ? 0 : undefined),
						cacheRetention: opts.cache_retention ?? undefined,
					});
					const iterator = source[Symbol.asyncIterator]();
					const head = await iterator.next();
					const startsWithError = !head.done && head.value.type === "error";
					let failure: ReturnType<typeof classifyFailure> | undefined;
					let finalMessage: AssistantMessage | undefined;
					if (startsWithError) {
						finalMessage = await source.result();
						failure = classifyFailure(finalMessage.errorMessage ?? "", provider);
						lastError = finalMessage.errorMessage ?? lastError;
					}
					const canFallBack = failure?.kind === "fallback" && index < usable.length - 1;
					if (startsWithError && canFallBack) {
						this.reportAgentAttempt(userUid, scene, candidate.ref, resolved, finalMessage!, startedAt, failure);
						continue;
					}
					// Forward everything from here on (including a terminal error).
					if (!head.done) outer.push(head.value);
					for (let step = await iterator.next(); !step.done; step = await iterator.next()) {
						outer.push(step.value);
					}
					finalMessage = await source.result();
					const finalFailure =
						finalMessage.stopReason === "error" || finalMessage.stopReason === "aborted"
							? (failure ?? classifyFailure(finalMessage.errorMessage ?? "", provider))
							: undefined;
					this.reportAgentAttempt(userUid, scene, candidate.ref, resolved, finalMessage, startedAt, finalFailure);
					handle.lastFailure = finalFailure
						? {
								...finalFailure,
								provider: candidate.ref.provider_id,
								message: finalMessage.errorMessage ?? "",
							}
						: undefined;
					outer.end(finalMessage);
					return;
				}
				handle.lastFailure = { kind: "fallback", code: "ALL_CANDIDATES_FAILED", provider: "", message: lastError };
				outer.push({ type: "error", name: "all_candidates_failed" } as never);
				outer.end({
					role: "assistant",
					content: [],
					stopReason: "error",
					errorMessage: `所有候选模型均不可用：${lastError.slice(0, 200)}`,
				} as unknown as AssistantMessage);
			})().catch((error: unknown) => {
				outer.push({ type: "error", name: "stream_failed" } as never);
				outer.end({
					role: "assistant",
					content: [],
					stopReason: "error",
					errorMessage: error instanceof Error ? error.message : String(error),
				} as unknown as AssistantMessage);
			});
			return outer;
		};
		handle.streamFn = streamFn;
		return handle;
	}

	private reportAgentAttempt(
		userUid: string,
		scene: Scene,
		ref: ModelRef,
		resolved: ResolvedScene,
		message: AssistantMessage,
		startedAt: number,
		failure: { kind: FailureKind; code: string } | undefined,
	): void {
		const usage = message.usage;
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
			latency_ms: Math.round(performance.now() - startedAt),
			success: !failure,
			error_code: failure?.code ?? null,
		});
	}
}
