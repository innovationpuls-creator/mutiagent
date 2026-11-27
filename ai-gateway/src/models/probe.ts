import type { AssistantMessage, Context, Model } from "@earendil-works/pi-ai";
import type { UserEntry } from "./runtime.js";

export type ProbeStatus = "ok" | "failed" | "skipped";

export interface ProbeItem {
	status: ProbeStatus;
	first_token_ms?: number | null;
	total_ms?: number;
	reason?: string;
}

export interface ProbeResult {
	provider_id: string;
	model_id: string;
	text: ProbeItem;
	tools: ProbeItem;
	vision: ProbeItem;
}

// 1x1 red PNG.
const RED_PIXEL =
	"iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGP4z8DwHwAFAAH/q842iQAAAABJRU5ErkJggg==";

const PROBE_TIMEOUT_MS = 20_000;

export function sanitizeError(text: string, secrets: Array<string | null | undefined> = []): string {
	let clean = text;
	for (const secret of secrets) {
		if (secret && secret.length >= 4) clean = clean.split(secret).join("***");
	}
	clean = clean
		.replace(/(sk|key|tok)[-_][A-Za-z0-9_-]{8,}/gi, "***")
		.replace(/Bearer\s+[A-Za-z0-9._-]+/gi, "Bearer ***");
	return clean.slice(0, 240);
}

function explain(message: string): string {
	const status = /^(\d{3})\b/.exec(message.trim())?.[1];
	if (status === "401" || status === "403") return `认证失败（${status}）：API Key 无效或无权限`;
	if (status === "404") return "模型或接口地址不存在（404），请检查 Base URL 与模型 ID";
	if (status === "429") return "上游限流（429），稍后重试";
	if (status && Number(status) >= 500) return `上游服务错误（${status}）`;
	if (/timeout|timed out/i.test(message)) return "请求超时，请检查网络与 Base URL";
	if (/ECONNREFUSED|ENOTFOUND|fetch failed|network/i.test(message)) return "无法连接上游，请检查 Base URL";
	return message;
}

async function run(
	entry: UserEntry,
	model: Model<never>,
	context: Context,
	secrets: Array<string | null | undefined>,
	extra: { maxTokens: number },
): Promise<{ item: ProbeItem; message?: AssistantMessage }> {
	const startedAt = performance.now();
	let firstToken: number | null = null;
	try {
		const stream = entry.models.streamSimple(model as never, context, {
			maxTokens: extra.maxTokens,
			timeoutMs: PROBE_TIMEOUT_MS,
			maxRetries: 0,
		});
		for await (const event of stream) {
			if (firstToken === null && (event.type === "text_delta" || event.type === "toolcall_start" || event.type === "thinking_delta")) {
				firstToken = Math.round(performance.now() - startedAt);
			}
		}
		const message = await stream.result();
		const total = Math.round(performance.now() - startedAt);
		if (message.stopReason === "error" || message.stopReason === "aborted") {
			return { item: { status: "failed", total_ms: total, reason: sanitizeError(explain(message.errorMessage ?? "未知错误"), secrets) } };
		}
		return { item: { status: "ok", first_token_ms: firstToken, total_ms: total }, message };
	} catch (error) {
		const raw = error instanceof Error ? error.message : String(error);
		return {
			item: { status: "failed", total_ms: Math.round(performance.now() - startedAt), reason: sanitizeError(explain(raw), secrets) },
		};
	}
}

export async function probeModel(
	entry: UserEntry,
	providerId: string,
	modelId: string,
): Promise<ProbeResult> {
	const provider = entry.config.providers.find((p) => p.provider_id === providerId);
	const secrets = [provider?.api_key, ...Object.values(provider?.headers ?? {})];
	const base = { provider_id: providerId, model_id: modelId };
	const model = provider?.enabled ? entry.models.getModel(providerId, modelId) : undefined;
	const failed = (reason: string): ProbeItem => ({ status: "failed", reason });
	if (!model) {
		const reason = provider ? "模型不存在或服务商未启用" : "服务商未配置";
		return { ...base, text: failed(reason), tools: { status: "skipped", reason }, vision: { status: "skipped", reason } };
	}

	const text = await run(
		entry,
		model as never,
		{ messages: [{ role: "user", content: "Reply with the single word: OK", timestamp: Date.now() }] },
		secrets,
		{ maxTokens: 32 },
	);
	if (text.item.status === "failed") {
		const skipped: ProbeItem = { status: "skipped", reason: "文本探针失败，已跳过" };
		return { ...base, text: text.item, tools: skipped, vision: skipped };
	}

	const toolRun = await run(
		entry,
		model as never,
		{
			messages: [{ role: "user", content: "Call the ping tool with value 1.", timestamp: Date.now() }],
			tools: [
				{
					name: "ping",
					description: "Connectivity check",
					parameters: { type: "object", properties: { value: { type: "number" } }, required: ["value"] },
				},
			],
		},
		secrets,
		{ maxTokens: 64 },
	);
	let tools = toolRun.item;
	if (tools.status === "ok" && !toolRun.message?.content.some((block) => block.type === "toolCall")) {
		tools = { ...tools, status: "failed", reason: "模型未返回工具调用，可能不支持 Function Calling" };
	}

	let vision: ProbeItem = { status: "skipped", reason: "模型未声明图片输入能力" };
	if (model.input.includes("image")) {
		vision = (
			await run(
				entry,
				model as never,
				{
					messages: [
						{
							role: "user",
							content: [
								{ type: "text", text: "What color is this image? One word." },
								{ type: "image", data: RED_PIXEL, mimeType: "image/png" },
							],
							timestamp: Date.now(),
						},
					],
				},
				secrets,
				{ maxTokens: 32 },
			)
		).item;
	}
	return { ...base, text: text.item, tools, vision };
}
