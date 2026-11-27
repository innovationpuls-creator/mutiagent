import type { RuntimeConfig } from "./models/types.js";
import { BackendBusinessError, internalServiceUnavailable } from "./errors.js";
import { INTERNAL_TOKEN_HEADER } from "./internalAuth.js";
import { type Logger, REQUEST_ID_HEADER, getRequestId } from "./observability.js";

export interface UserAuthStatus {
	user_uid: string;
	exists: boolean;
	role: string | null;
	is_active: boolean;
}

export interface BackendHealth {
	status: string;
	database: string;
}

export interface OAuthLockResult {
	outcome: "unchanged" | "refreshed" | "conflict";
	credential: Record<string, unknown>;
	refresh_fingerprint: string;
	expires_at: string | null;
}

export interface UsageReport {
	request_id?: string | null;
	scene: string;
	provider_id: string;
	model_id: string;
	thinking_level?: string | null;
	input_tokens: number;
	output_tokens: number;
	cache_read_tokens: number;
	cache_write_tokens: number;
	reasoning_tokens: number;
	estimated_cost_usd: number;
	latency_ms: number;
	success: boolean;
	error_code?: string | null;
}

export interface HistoryMessage {
	role: "user" | "assistant";
	content: string;
}

export interface ChatContext {
	session_id: string;
	user_uid: string;
	history: HistoryMessage[];
	session_state: Record<string, unknown>;
	profile: Record<string, unknown> | null;
	has_complete_profile: boolean;
	year_learning_paths: Record<string, unknown> | null;
	latest_grade_year: string | null;
	course_knowledge: Record<string, unknown> | null;
}

export interface OutlineSkeletonSection {
	section_id: string;
	parent_section_id: string | null;
	depth: number;
	source_textbook_title?: string;
	source_section_titles?: string[];
	source_content_chars?: number;
	source_chunk_index?: number | null;
	source_chunk_total?: number | null;
	source_char_range?: number[] | null;
	[key: string]: unknown;
}

export interface OutlineSourceCourse {
	course_node_id: string;
	course_name: string;
	grade_year: string;
	source_textbook_id: string;
	source_textbook_title: string;
	naming_context: Record<string, unknown>;
	skeleton: OutlineSkeletonSection[];
}

export interface OutlineSourceContext {
	grade_year: string;
	current_course_id: string;
	path_fingerprints: Record<string, string>;
	courses: OutlineSourceCourse[];
}

export interface TurnPayload {
	user_message: string;
	image_attachment?: string | null;
	assistant_message?: string | null;
	session_state_patch?: Record<string, unknown> | null;
}

export interface ProgressSnapshot {
	grade_year: string;
	total_courses: number;
	completed_courses: number;
	current_course_id: string;
	current_course_title: string;
	current_progress_state: string;
	next_course_id: string;
	next_course_title: string;
}

export interface LearningOverview {
	has_paths: boolean;
	has_outline: boolean;
	latest_grade_year: string | null;
	current_course_id: string | null;
	progress: ProgressSnapshot[];
	path_text: string;
	outline_text: string;
	next_step_text: string;
}

export interface TextbookContext {
	textbooks: Array<{
		textbook_id: string;
		title: string;
		description?: string;
		outline_summary: Array<{ section_id: string; title: string }>;
	}>;
	gap_id: string | null;
}

export interface ProtectedCourse {
	title: string;
	reason: string;
}

export interface RawProgressSnapshot {
	grade_year: string;
	total_courses: number;
	completed_courses: number;
	current_course_id: string;
	current_progress_state: string;
	next_course_id: string;
}

export interface BackendClient {
	/** Published textbook outlines for a topic; registers a KnowledgeGap when none match. */
	getTextbookContext(learningTopic: string, studentGoalSummary: string): Promise<TextbookContext>;
	getProtectedCourses(userUid: string): Promise<ProtectedCourse[]>;
	getProgressSnapshots(userUid: string): Promise<RawProgressSnapshot[]>;
	/** Expand the model's lightweight plan into the v2 contract; 422 BackendBusinessError if unusable. */
	assembleLearningPath(
		userUid: string,
		gradeYear: string,
		body: { profile: Record<string, unknown>; learning_topic: string; plan: unknown; intake_courses: unknown[] },
	): Promise<{ path_data: Record<string, unknown> }>;
	saveYearLearningPath(
		userUid: string,
		gradeYear: string,
		learningTopic: string,
		pathData: Record<string, unknown>,
	): Promise<void>;
	getOutlineSourceContext(userUid: string, courseRef: string): Promise<OutlineSourceContext>;
	composeOutline(
		userUid: string,
		course: OutlineSourceCourse,
		naming: Record<string, unknown>,
	): Promise<{ outline: Record<string, unknown> }>;
	saveOutlines(
		userUid: string,
		pathFingerprints: Record<string, string>,
		outlines: Record<string, unknown>[],
	): Promise<{ saved_course_ids: string[] }>;
	getInternalHealth(): Promise<BackendHealth>;
	getChatContext(sessionId: string, userUid: string): Promise<ChatContext>;
	persistTurn(sessionId: string, userUid: string, turn: TurnPayload): Promise<{ persisted: string }>;
	putStudentProfile(userUid: string, profileData: Record<string, unknown>): Promise<void>;
	getLearningOverview(userUid: string): Promise<LearningOverview>;
	/** Transitional bridge (M4-M7): raw SSE response of the pre-migration orchestration. */
	openLegacyStream(
		sessionId: string,
		userUid: string,
		body: { message: string; image_attachment?: string | null },
		signal?: AbortSignal,
	): Promise<Response>;
	getUserAuthStatus(userUid: string): Promise<UserAuthStatus>;
	getModelRuntimeConfig(userUid: string): Promise<RuntimeConfig>;
	oauthRefreshLock(
		userUid: string,
		providerId: string,
		body: {
			previous_refresh_fingerprint?: string | null;
			new_credential?: Record<string, unknown> | null;
			expires_at?: string | null;
		},
	): Promise<OAuthLockResult>;
	saveOAuthCredential(
		userUid: string,
		providerId: string,
		body: {
			credential: Record<string, unknown>;
			expires_at?: string | null;
			account_label?: string | null;
		},
	): Promise<void>;
	postModelUsage(userUid: string, usage: UsageReport): Promise<void>;
}

export interface BackendClientOptions {
	baseUrl: string;
	internalToken: string;
	timeoutMs: number;
	logger: Logger;
	fetchImpl?: typeof fetch;
}

async function readDetail(response: Response): Promise<string> {
	try {
		const body = (await response.json()) as { detail?: unknown };
		if (typeof body.detail === "string") return body.detail;
	} catch {
		// fall through
	}
	return `后端请求失败（${response.status}）`;
}

export function createBackendClient(options: BackendClientOptions): BackendClient {
	const { baseUrl, internalToken, timeoutMs, logger } = options;
	const fetchImpl = options.fetchImpl ?? fetch;

	async function request<T>(
		path: string,
		init: { method?: string; body?: unknown; timeoutMs?: number } = {},
	): Promise<T> {
		const response = await rawRequest(path, init);
		try {
			return (await response.json()) as T;
		} catch {
			logger.warn(`python_backend_invalid_json path=${path}`);
			throw internalServiceUnavailable();
		}
	}

	async function rawRequest(
		path: string,
		init: { method?: string; body?: unknown; timeoutMs?: number; signal?: AbortSignal } = {},
	): Promise<Response> {
		const headers: Record<string, string> = {
			Accept: "application/json",
			[INTERNAL_TOKEN_HEADER]: internalToken,
		};
		if (init.body !== undefined) headers["Content-Type"] = "application/json";
		const requestId = getRequestId();
		if (requestId) headers[REQUEST_ID_HEADER] = requestId;

		let response: Response;
		try {
			response = await fetchImpl(`${baseUrl}${path}`, {
				method: init.method ?? "GET",
				headers,
				body: init.body === undefined ? undefined : JSON.stringify(init.body),
				signal: init.signal ?? AbortSignal.timeout(init.timeoutMs ?? timeoutMs),
			});
		} catch (error) {
			const reason = error instanceof Error ? error.name : "unknown";
			logger.warn(`python_backend_unreachable path=${path} reason=${reason}`);
			throw internalServiceUnavailable();
		}

		if (response.status === 401 || response.status === 403) {
			// Token mismatch between services is an operator error, never a user one.
			logger.error(`python_backend_rejected_internal_token path=${path} status=${response.status}`);
			throw internalServiceUnavailable();
		}
		if (response.status >= 500) {
			logger.warn(`python_backend_server_error path=${path} status=${response.status}`);
			throw internalServiceUnavailable();
		}
		if (!response.ok) {
			throw new BackendBusinessError(response.status, await readDetail(response));
		}
		return response;
	}

	return {
		getInternalHealth: () => request<BackendHealth>("/internal/health"),
		getChatContext: (sessionId, userUid) =>
			request<ChatContext>(
				`/internal/chat/sessions/${encodeURIComponent(sessionId)}/context?user_uid=${encodeURIComponent(userUid)}`,
			),
		persistTurn: (sessionId, userUid, turn) =>
			request<{ persisted: string }>(
				`/internal/chat/sessions/${encodeURIComponent(sessionId)}/turn`,
				{ method: "POST", body: { user_uid: userUid, ...turn } },
			),
		async putStudentProfile(userUid, profileData) {
			await request(`/internal/students/${encodeURIComponent(userUid)}/profile`, {
				method: "PUT",
				body: { profile_data: profileData },
			});
		},
		getTextbookContext: (learningTopic, studentGoalSummary) =>
			request<TextbookContext>("/internal/knowledge-base/textbook-context-for-intake", {
				method: "POST",
				body: { learning_topic: learningTopic, student_goal_summary: studentGoalSummary },
			}),
		getProtectedCourses: async (userUid) =>
			(
				await request<{ courses: ProtectedCourse[] }>(
					`/internal/students/${encodeURIComponent(userUid)}/protected-courses`,
				)
			).courses,
		getProgressSnapshots: async (userUid) =>
			(
				await request<{ snapshots: RawProgressSnapshot[] }>(
					`/internal/students/${encodeURIComponent(userUid)}/learning-paths/progress-snapshots`,
				)
			).snapshots,
		assembleLearningPath: (userUid, gradeYear, body) =>
			request(
				`/internal/students/${encodeURIComponent(userUid)}/learning-paths/${encodeURIComponent(gradeYear)}/assemble`,
				{ method: "POST", body, timeoutMs: 60_000 },
			),
		async saveYearLearningPath(userUid, gradeYear, learningTopic, pathData) {
			await request(
				`/internal/students/${encodeURIComponent(userUid)}/learning-paths/${encodeURIComponent(gradeYear)}`,
				{ method: "PUT", body: { learning_topic: learningTopic, path_data: pathData } },
			);
		},
		getOutlineSourceContext: (userUid, courseRef) =>
			request<OutlineSourceContext>(
				`/internal/students/${encodeURIComponent(userUid)}/outline-source-context`,
				{ method: "POST", body: { course_id: courseRef }, timeoutMs: 30_000 },
			),
		composeOutline: (userUid, course, naming) =>
			request<{ outline: Record<string, unknown> }>(
				`/internal/students/${encodeURIComponent(userUid)}/course-outlines/compose`,
				{ method: "POST", body: { course, naming } },
			),
		saveOutlines: (userUid, pathFingerprints, outlines) =>
			request<{ saved_course_ids: string[] }>(
				`/internal/students/${encodeURIComponent(userUid)}/course-outlines/batch`,
				{ method: "POST", body: { path_fingerprints: pathFingerprints, outlines }, timeoutMs: 60_000 },
			),
		getLearningOverview: (userUid) =>
			request<LearningOverview>(`/internal/students/${encodeURIComponent(userUid)}/learning-overview`),
		// A turn can legitimately run for minutes; the signal (client disconnect) bounds it.
		openLegacyStream: (sessionId, userUid, body, signal) =>
			rawRequest(`/internal/chat/sessions/${encodeURIComponent(sessionId)}/legacy-stream`, {
				method: "POST",
				body: { user_uid: userUid, ...body },
				signal: signal ?? AbortSignal.timeout(15 * 60_000),
			}),
		getModelRuntimeConfig: (userUid) =>
			request<RuntimeConfig>(
				`/internal/users/${encodeURIComponent(userUid)}/model-runtime-config`,
			),
		oauthRefreshLock: (userUid, providerId, body) =>
			request<OAuthLockResult>(
				`/internal/users/${encodeURIComponent(userUid)}/providers/${encodeURIComponent(providerId)}/oauth-refresh-lock`,
				{ method: "POST", body },
			),
		async saveOAuthCredential(userUid, providerId, body) {
			await request(
				`/internal/users/${encodeURIComponent(userUid)}/providers/${encodeURIComponent(providerId)}/oauth-credential`,
				{ method: "PUT", body },
			);
		},
		async postModelUsage(userUid, usage) {
			await request(
				`/internal/users/${encodeURIComponent(userUid)}/model-usage`,
				{ method: "POST", body: usage },
			);
		},
		async getUserAuthStatus(userUid) {
			const status = await request<UserAuthStatus>(
				`/internal/users/${encodeURIComponent(userUid)}/auth-status`,
			);
			if (typeof status.exists !== "boolean" || typeof status.is_active !== "boolean") {
				logger.warn("python_backend_unexpected_auth_status_shape");
				throw internalServiceUnavailable();
			}
			return status;
		},
	};
}
