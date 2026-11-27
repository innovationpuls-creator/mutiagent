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

export type ResourcePhase = "markdown" | "video" | "animation" | "compose";

export interface ResourceSectionInfo {
	section_id: string;
	title: string;
	checkpoints: Partial<Record<ResourcePhase, string>>;
	has_composed: boolean;
	has_markdown: boolean;
}

export type ResourcePrepare =
	| { status: "refused"; message: string }
	| { status: "busy"; message: string }
	| { status: "needs_focus"; chapter_section_id: string }
	| {
			status: "ready";
			course_id: string;
			course_name: string;
			chapter_section_id: string;
			sections: ResourceSectionInfo[];
	  };

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

export interface ForestMaterial {
	chapter_title: string;
	sections: Array<{ section_id: string; title: string; markdown: string }>;
	/** Server-side truth: the student already has a graded attempt for this quiz. */
	submitted: boolean;
}

export interface ReportContextView {
	summary: string;
	evidence_ids: string[];
	tools: Record<string, string>;
	has_attempts: boolean;
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
	prepareResourceGeneration(
		userUid: string,
		courseId: string,
		chapterRef: string,
		mode: string,
	): Promise<ResourcePrepare>;
	finishResourceGeneration(
		userUid: string,
		courseId: string,
		chapterId: string,
		succeededSectionIds: string[],
	): Promise<void>;
	getMarkdownPrompt(
		userUid: string,
		courseId: string,
		sectionId: string,
		regenerationFocus: string,
	): Promise<{ system_prompt: string; query: string }>;
	validateMarkdown(
		userUid: string,
		courseId: string,
		sectionId: string,
		rawOutput: string,
	): Promise<{ ok: true; value: Record<string, unknown> } | { ok: false; issue: string }>;
	searchSectionVideo(
		userUid: string,
		courseId: string,
		sectionId: string,
	): Promise<{ status: "available" | "unavailable"; value: Record<string, unknown> }>;
	getAnimationPrompt(
		userUid: string,
		courseId: string,
		sectionId: string,
	): Promise<{ needed: false } | { needed: true; system_prompt: string; query: string }>;
	validateAnimations(
		userUid: string,
		courseId: string,
		sectionId: string,
		animations: unknown[],
		fallback: boolean,
	): Promise<{ ok: true; value: Record<string, unknown> } | { ok: false; issue: string }>;
	saveSectionResource(
		userUid: string,
		courseId: string,
		sectionId: string,
		body: { phase: ResourcePhase; value?: Record<string, unknown> | null; failure?: string },
	): Promise<void>;
	getForestMaterial(
		userUid: string,
		courseNodeId: string,
		chapterId: string,
		quizId: string | null,
	): Promise<ForestMaterial>;
	getReportContext(userUid: string): Promise<ReportContextView>;
	readReportEvidence(
		userUid: string,
		tool: string,
		evidenceId: string,
	): Promise<{ ok: true; text: string } | { ok: false; issue: string }>;
	validateReport(
		userUid: string,
		narrative: unknown,
		details: Record<string, string>,
	): Promise<{ ok: true; report: Record<string, unknown> } | { ok: false; issue: string }>;
	getInternalHealth(): Promise<BackendHealth>;
	getChatContext(sessionId: string, userUid: string): Promise<ChatContext>;
	persistTurn(sessionId: string, userUid: string, turn: TurnPayload): Promise<{ persisted: string }>;
	putStudentProfile(userUid: string, profileData: Record<string, unknown>): Promise<void>;
	getLearningOverview(userUid: string): Promise<LearningOverview>;
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

const courseBase = (userUid: string, courseId: string) =>
	`/internal/students/${encodeURIComponent(userUid)}/courses/${encodeURIComponent(courseId)}`;
const sectionBase = (userUid: string, courseId: string, sectionId: string) =>
	`${courseBase(userUid, courseId)}/sections/${encodeURIComponent(sectionId)}`;

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
		prepareResourceGeneration: (userUid, courseId, chapterRef, mode) =>
			request<ResourcePrepare>(
				`${courseBase(userUid, courseId)}/chapters/${encodeURIComponent(chapterRef || "default")}/generation-prepare`,
				{ method: "POST", body: { mode } },
			),
		async finishResourceGeneration(userUid, courseId, chapterId, succeededSectionIds) {
			await request(`${courseBase(userUid, courseId)}/chapters/${encodeURIComponent(chapterId)}/generation-finish`, {
				method: "POST",
				body: { succeeded_section_ids: succeededSectionIds },
				timeoutMs: 60_000,
			});
		},
		getMarkdownPrompt: (userUid, courseId, sectionId, regenerationFocus) =>
			request(`${sectionBase(userUid, courseId, sectionId)}/markdown/prompt`, {
				method: "POST",
				body: { regeneration_focus: regenerationFocus },
			}),
		validateMarkdown: (userUid, courseId, sectionId, rawOutput) =>
			request(`${sectionBase(userUid, courseId, sectionId)}/markdown/validate`, {
				method: "POST",
				body: { raw_output: rawOutput },
				timeoutMs: 30_000,
			}),
		searchSectionVideo: (userUid, courseId, sectionId) =>
			request(`${sectionBase(userUid, courseId, sectionId)}/video/search`, {
				method: "POST",
				timeoutMs: 120_000,
			}),
		getAnimationPrompt: (userUid, courseId, sectionId) =>
			request(`${sectionBase(userUid, courseId, sectionId)}/animation/prompt`, {
				method: "POST",
				body: {},
			}),
		validateAnimations: (userUid, courseId, sectionId, animations, fallback) =>
			request(`${sectionBase(userUid, courseId, sectionId)}/animation/validate`, {
				method: "POST",
				body: { animations, fallback },
				timeoutMs: 30_000,
			}),
		async saveSectionResource(userUid, courseId, sectionId, body) {
			await request(`${sectionBase(userUid, courseId, sectionId)}/resources`, { method: "PUT", body });
		},
		getForestMaterial: (userUid, courseNodeId, chapterId, quizId) =>
			request<ForestMaterial>(
				`/internal/forest/chapters/${encodeURIComponent(courseNodeId)}/${encodeURIComponent(chapterId)}/material?user_uid=${encodeURIComponent(userUid)}${quizId ? `&quiz_id=${encodeURIComponent(quizId)}` : ""}`,
			),
		getReportContext: (userUid) =>
			request<ReportContextView>(`/internal/canopy/${encodeURIComponent(userUid)}/report-context`, { timeoutMs: 30_000 }),
		readReportEvidence: (userUid, tool, evidenceId) =>
			request(`/internal/canopy/${encodeURIComponent(userUid)}/report-evidence`, {
				method: "POST",
				body: { tool, evidence_id: evidenceId },
				timeoutMs: 30_000,
			}),
		validateReport: (userUid, narrative, details) =>
			request(`/internal/canopy/${encodeURIComponent(userUid)}/report-validate`, {
				method: "POST",
				body: { narrative, details },
				timeoutMs: 30_000,
			}),
		getLearningOverview: (userUid) =>
			request<LearningOverview>(`/internal/students/${encodeURIComponent(userUid)}/learning-overview`),
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
