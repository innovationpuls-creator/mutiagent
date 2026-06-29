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

export interface AdminKnowledgeBaseApi {
	listSources(token: string): Promise<KnowledgeSource[]>;
	listTextbooks(token: string): Promise<Textbook[]>;
	listGaps(token: string): Promise<KnowledgeGapAdmin[]>;
	listExtensionResources(
		token: string,
		textbookId: string,
	): Promise<TextbookExtensionResource[]>;
	runAgent(token: string, message: string): Promise<KnowledgeBaseAgentResponse>;
	confirmSourceResult(
		token: string,
		sourceResult: KnowledgeBaseSourceResult,
	): Promise<KnowledgeBaseSourceConfirmResponse>;
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
	runAgent(token: string, message: string) {
		return requestJson<KnowledgeBaseAgentResponse>(
			token,
			"/api/admin/knowledge-base/agent",
			{ method: "POST", body: JSON.stringify({ message }) },
		);
	},
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
