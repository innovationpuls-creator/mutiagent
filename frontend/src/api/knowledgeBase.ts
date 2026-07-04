import type { components } from "../types/api";
import { API_BASE_URL, notifyAuthInvalidFromError, readApiError } from "./http";

export type KnowledgeGapFollowRead =
	components["schemas"]["KnowledgeGapFollowRead"];
export type KnowledgeGapNoticeRead =
	components["schemas"]["KnowledgeGapNoticeRead"];
export type KnowledgeGapRead = components["schemas"]["KnowledgeGapRead"];
export type KnowledgeGapAdmin = components["schemas"]["KnowledgeGapAdminRead"];
export type KnowledgeSource = components["schemas"]["KnowledgeSourceRead"];
export type Textbook = components["schemas"]["TextbookRead"];
export type TextbookExtensionResource =
	components["schemas"]["TextbookExtensionResourceRead"];
export type TextbookSectionContent =
	components["schemas"]["TextbookSectionContentRead"];
export type StructuredTextbookCreateRequest =
	components["schemas"]["StructuredTextbookCreateRequest"];
export type KnowledgeGapFindMaterialsResponse =
	components["schemas"]["KnowledgeGapFindMaterialsResponse"];
export type KnowledgeGapUploadResponse =
	components["schemas"]["KnowledgeGapUploadResponse"];
export type KnowledgeBaseAgentTextbookHit =
	components["schemas"]["KnowledgeBaseAgentTextbookHit"];
export type KnowledgeBaseAgentGapHit =
	components["schemas"]["KnowledgeBaseAgentGapHit"];
export type KnowledgeBaseAgentRequest =
	components["schemas"]["KnowledgeBaseAgentRequest"];
export type KnowledgeBaseAgentResponse =
	components["schemas"]["KnowledgeBaseAgentResponse"];
export type KnowledgeBaseSourceConfirmResponse =
	components["schemas"]["KnowledgeBaseSourceConfirmResponse"];
export type KnowledgeBaseSourceResult =
	components["schemas"]["KnowledgeBaseSourceResult"];
export type KnowledgeBaseIngestionJob =
	components["schemas"]["KnowledgeBaseIngestionJobRead"];

export interface KnowledgeBaseAgentStreamEvent {
	event: string;
	message?: string;
	raw_length?: number;
	normalized_length?: number;
	source_count?: number;
	textbook_count?: number;
	gap_count?: number;
	match_count?: number;
	hit_count?: number;
	result_count?: number;
	reply_length?: number;
	recoverable?: boolean;
	response?: KnowledgeBaseAgentResponse;
}

export interface AdminKnowledgeBaseApi {
	listSources(token: string): Promise<KnowledgeSource[]>;
	listTextbooks(token: string): Promise<Textbook[]>;
	listGaps(token: string): Promise<KnowledgeGapAdmin[]>;
	listExtensionResources(
		token: string,
		textbookId: string,
	): Promise<TextbookExtensionResource[]>;
	listTextbookSections(
		token: string,
		textbookId: string,
	): Promise<TextbookSectionContent[]>;
	runAgent(token: string, message: string): Promise<KnowledgeBaseAgentResponse>;
	streamAgent?(
		token: string,
		message: string,
		onEvent: (event: KnowledgeBaseAgentStreamEvent) => void,
	): Promise<KnowledgeBaseAgentResponse>;
	confirmSourceResult(
		token: string,
		sourceResult: KnowledgeBaseSourceResult,
	): Promise<KnowledgeBaseSourceConfirmResponse>;
	runIngestionJob(
		token: string,
		jobId: string,
	): Promise<KnowledgeBaseIngestionJob>;
	organizeTextbook(
		token: string,
		textbookId: string,
	): Promise<KnowledgeBaseIngestionJob>;
	publishTextbook(token: string, textbookId: string): Promise<Textbook>;
	unpublishTextbook(token: string, textbookId: string): Promise<Textbook>;
	deleteTextbook(token: string, textbookId: string): Promise<void>;
	updateOutline(
		token: string,
		textbookId: string,
		outline: unknown,
	): Promise<Textbook>;
}

async function requestJson<TResponse>(
	token: string,
	path: string,
	init: RequestInit = {},
): Promise<TResponse> {
	const response = await fetch(`${API_BASE_URL}${path}`, {
		...init,
		headers: {
			...(init.body ? { "Content-Type": "application/json" } : {}),
			Authorization: `Bearer ${token}`,
			...init.headers,
		},
	});

	if (!response.ok) {
		const error = await readApiError(response);
		notifyAuthInvalidFromError(response.status, error);
		throw new Error(
			(typeof error?.detail === "string" ? error.detail : null) ??
				"知识库操作失败",
		);
	}

	if (response.status === 204) {
		return undefined as TResponse;
	}

	return (await response.json()) as TResponse;
}

function isRecord(value: unknown): value is Record<string, unknown> {
	return value !== null && typeof value === "object";
}

function getString(value: unknown): string | undefined {
	return typeof value === "string" ? value : undefined;
}

function getNumber(value: unknown): number | undefined {
	return typeof value === "number" ? value : undefined;
}

function getBoolean(value: unknown): boolean | undefined {
	return typeof value === "boolean" ? value : undefined;
}

function normalizeKnowledgeBaseAgentStreamEvent(
	event: string,
	payload: unknown,
): KnowledgeBaseAgentStreamEvent {
	const data = isRecord(payload) ? payload : {};
	return {
		event,
		message: getString(data.message),
		raw_length: getNumber(data.raw_length),
		normalized_length: getNumber(data.normalized_length),
		source_count: getNumber(data.source_count),
		textbook_count: getNumber(data.textbook_count),
		gap_count: getNumber(data.gap_count),
		match_count: getNumber(data.match_count),
		hit_count: getNumber(data.hit_count),
		result_count: getNumber(data.result_count),
		reply_length: getNumber(data.reply_length),
		recoverable: getBoolean(data.recoverable),
		response: isRecord(data.response)
			? (data.response as unknown as KnowledgeBaseAgentResponse)
			: undefined,
	};
}

function parseKnowledgeBaseAgentSse(buffer: string): {
	events: KnowledgeBaseAgentStreamEvent[];
	rest: string;
} {
	const parts = buffer.split("\n\n");
	const rest = parts.pop() ?? "";
	const events = parts
		.map((part) => {
			const lines = part.split("\n");
			const eventLine = lines.find((line) => line.startsWith("event: "));
			const dataLines = lines.filter((line) => line.startsWith("data: "));
			if (!eventLine || dataLines.length === 0) return null;
			const event = eventLine.slice("event: ".length).trim();
			const dataText = dataLines
				.map((line) => line.slice("data: ".length))
				.join("\n");
			return normalizeKnowledgeBaseAgentStreamEvent(
				event,
				JSON.parse(dataText),
			);
		})
		.filter((event): event is KnowledgeBaseAgentStreamEvent => event !== null);
	return { events, rest };
}

async function streamAgent(
	token: string,
	message: string,
	onEvent: (event: KnowledgeBaseAgentStreamEvent) => void,
): Promise<KnowledgeBaseAgentResponse> {
	const response = await fetch(
		`${API_BASE_URL}/api/admin/knowledge-base/agent/stream`,
		{
			method: "POST",
			headers: {
				"Content-Type": "application/json",
				Authorization: `Bearer ${token}`,
				Accept: "text/event-stream",
			},
			body: JSON.stringify({ message }),
		},
	);

	if (!response.ok) {
		const error = await readApiError(response);
		notifyAuthInvalidFromError(response.status, error);
		throw new Error(
			(typeof error?.detail === "string" ? error.detail : null) ??
				"知识库 Agent 处理失败",
		);
	}

	const reader = response.body?.getReader();
	if (!reader) {
		throw new Error("浏览器无法读取知识库实时反馈流");
	}

	const decoder = new TextDecoder();
	let buffer = "";
	let finalResponse: KnowledgeBaseAgentResponse | null = null;

	while (true) {
		const { done, value } = await reader.read();
		buffer += decoder.decode(value ?? new Uint8Array(), { stream: !done });
		if (done && buffer.trim()) {
			buffer += "\n\n";
		}
		const parsed = parseKnowledgeBaseAgentSse(buffer);
		buffer = parsed.rest;
		for (const event of parsed.events) {
			onEvent(event);
			if (event.event === "error") {
				throw new Error(event.message || "知识库 Agent 处理失败");
			}
			if (event.event === "completed" && event.response) {
				finalResponse = event.response;
			}
		}
		if (done) break;
	}

	if (!finalResponse) {
		throw new Error("知识库 Agent 没有返回最终结果");
	}
	return finalResponse;
}

export const adminKnowledgeBaseApi: AdminKnowledgeBaseApi = {
	listSources(token: string) {
		return requestJson<KnowledgeSource[]>(
			token,
			"/api/admin/knowledge-base/sources",
		);
	},
	listTextbooks(token: string) {
		return requestJson<Textbook[]>(
			token,
			"/api/admin/knowledge-base/textbooks",
		);
	},
	listGaps(token: string) {
		return requestJson<KnowledgeGapAdmin[]>(
			token,
			"/api/admin/knowledge-base/gaps",
		);
	},
	listExtensionResources(token: string, textbookId: string) {
		return requestJson<TextbookExtensionResource[]>(
			token,
			`/api/admin/knowledge-base/textbooks/${encodeURIComponent(textbookId)}/extension-resources`,
		);
	},
	listTextbookSections(token: string, textbookId: string) {
		return requestJson<TextbookSectionContent[]>(
			token,
			`/api/admin/knowledge-base/textbooks/${encodeURIComponent(textbookId)}/sections`,
		);
	},
	runAgent(token: string, message: string) {
		return requestJson<KnowledgeBaseAgentResponse>(
			token,
			"/api/admin/knowledge-base/agent",
			{ method: "POST", body: JSON.stringify({ message }) },
		);
	},
	streamAgent,
	confirmSourceResult(token: string, sourceResult: KnowledgeBaseSourceResult) {
		return requestJson<KnowledgeBaseSourceConfirmResponse>(
			token,
			"/api/admin/knowledge-base/source-results/confirm",
			{
				method: "POST",
				body: JSON.stringify({ source_result: sourceResult }),
			},
		);
	},
	runIngestionJob(token: string, jobId: string) {
		return requestJson<KnowledgeBaseIngestionJob>(
			token,
			`/api/admin/knowledge-base/ingestion-jobs/${encodeURIComponent(jobId)}/run`,
			{ method: "POST" },
		);
	},
	organizeTextbook(token: string, textbookId: string) {
		return requestJson<KnowledgeBaseIngestionJob>(
			token,
			`/api/admin/knowledge-base/textbooks/${encodeURIComponent(textbookId)}/agent-organize/run`,
			{ method: "POST" },
		);
	},
	publishTextbook(token: string, textbookId: string) {
		return requestJson<Textbook>(
			token,
			`/api/admin/knowledge-base/textbooks/${encodeURIComponent(textbookId)}/publish`,
			{ method: "POST" },
		);
	},
	unpublishTextbook(token: string, textbookId: string) {
		return requestJson<Textbook>(
			token,
			`/api/admin/knowledge-base/textbooks/${encodeURIComponent(textbookId)}/unpublish`,
			{ method: "POST" },
		);
	},
	deleteTextbook(token: string, textbookId: string) {
		return requestJson<void>(
			token,
			`/api/admin/knowledge-base/textbooks/${encodeURIComponent(textbookId)}`,
			{ method: "DELETE" },
		);
	},
	updateOutline(token: string, textbookId: string, outline: unknown) {
		return requestJson<Textbook>(
			token,
			`/api/admin/knowledge-base/textbooks/${encodeURIComponent(textbookId)}/outline`,
			{
				method: "PUT",
				body: JSON.stringify({ outline }),
			},
		);
	},
};

export async function followKnowledgeGap(
	token: string,
	gapId: string,
): Promise<KnowledgeGapFollowRead> {
	const response = await fetch(
		`${API_BASE_URL}/api/knowledge-base/gaps/${encodeURIComponent(gapId)}/follow`,
		{
			method: "POST",
			headers: { Authorization: `Bearer ${token}` },
		},
	);

	if (!response.ok) {
		const error = await readApiError(response);
		notifyAuthInvalidFromError(response.status, error);
		throw new Error(
			(typeof error?.detail === "string" ? error.detail : null) ??
				"关注主题失败，请稍后重试",
		);
	}

	return (await response.json()) as KnowledgeGapFollowRead;
}

export async function fetchKnowledgeGapNotices(
	token: string,
): Promise<KnowledgeGapNoticeRead[]> {
	const response = await fetch(`${API_BASE_URL}/api/knowledge-base/notices`, {
		headers: { Authorization: `Bearer ${token}` },
	});

	if (!response.ok) {
		const error = await readApiError(response);
		notifyAuthInvalidFromError(response.status, error);
		throw new Error(
			(typeof error?.detail === "string" ? error.detail : null) ??
				"读取提醒失败，请稍后重试",
		);
	}

	const payload = await response.json();
	return Array.isArray(payload)
		? (payload as KnowledgeGapNoticeRead[])
		: [payload];
}
