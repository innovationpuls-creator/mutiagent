import { SignJWT } from "jose";
import type {
	BackendClient,
	ChatContext,
	LearningOverview,
	OutlineSourceContext,
	ProtectedCourse,
	ResourcePhase,
	ResourcePrepare,
	ResourceSectionInfo,
	RawProgressSnapshot,
	PublishedTextbook,
	TextbookOutline,
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
	kb: { overview: Record<string, unknown>; rejectUrls: Set<string>; verified: Array<Record<string, unknown>> };
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
	order: string[];
	textbooks: PublishedTextbook[];
	textbookOutlines: Map<string, TextbookOutline>;
	/** Every textbook-catalog call in order: "list", "outline:<id>". */
	textbookLookups: string[];
	gaps: Array<{ topic: string; summary: string; gapId: string }>;
	protectedCourses: ProtectedCourse[];
	snapshots: RawProgressSnapshot[];
	/** When set, assemble answers 422 with this detail (once per entry). */
	assembleFailures: string[];
	assembled: Array<{ gradeYear: string; plan: any }>;
	savedPaths: Array<{ userUid: string; gradeYear: string; topic: string; path: Record<string, unknown> }>;
	/** Source context served to the outline agent; a string makes the lookup answer 422 with it. */
	outlineContext: OutlineSourceContext | string;
	outlineLookups: string[];
	/** Course names whose compose should always answer 422 (simulates an unrecoverable failure). */
	composeAlwaysFail: Set<string>;
	composed: Array<{ course: string; naming: any }>;
	savedOutlines: Array<{ pathFingerprints: Record<string, string>; outlines: Record<string, unknown>[] }>;
	/** When true the batch save answers 409 (path changed meanwhile). */
	saveConflict: boolean;
	resource: FakeResources;
	forest: {
		material: { chapter_title: string; sections: Array<{ section_id: string; title: string; markdown: string }>; submitted: boolean };
		lookups: Array<{ userUid: string; quizId: string | null }>;
	};
	report: {
		summary: string;
		evidence: Map<string, string>;
		reads: Array<{ tool: string; id: string }>;
		validations: Array<{ narrative: any; details: Record<string, string> }>;
		/** Return an issue string to reject the narrative; undefined accepts it. */
		reject: (narrative: any, details: Record<string, string>) => string | undefined;
	};
}

export interface FakeResources {
	/** Overrides prepare outright (refused / needs_focus ...). */
	prepareOverride: ResourcePrepare | null;
	sections: string[];
	locked: boolean;
	prepares: Array<{ chapterRef: string; mode: string }>;
	finishes: Array<{ chapterId: string; succeeded: string[] }>;
	saves: Array<{ sectionId: string; phase: ResourcePhase; value?: unknown; failure?: string; at: number }>;
	checkpoints: Map<string, Partial<Record<ResourcePhase, string>>>;
	markdownFocus: string[];
	validations: Array<{ sectionId: string; markdown: string }>;
	/** Section ids whose animation (model and template) always fails. */
	animationBroken: Set<string>;
	/** Sections whose model animation fails validation but whose template works. */
	animationNeedsTemplate: Set<string>;
	videoMode: "available" | "unavailable" | "throws";
	videoVerifies: string[];
	videoComposes: Array<{ videos: Array<{ brief_id: string; url: string }>; unavailable_reason?: string }>;
	/** Issues returned (in order) by composeVideo before it starts accepting. */
	videoComposeIssue: string[] | null;
	videoDelayMs: number;
	videoSpans: Array<{ sectionId: string; start: number; end: number }>;
	animationSpans: Array<{ sectionId: string; start: number; end: number }>;
	failSaveOf: { sectionId: string; phase: ResourcePhase } | null;
	markdownDelayMs: Record<string, number>;
}

export function fakeBackend(): FakeBackend {
	const backend: FakeBackend = {
		users: new Map(),
		kb: { overview: { textbook_count: 0, gap_count: 1, textbooks: [], gaps: [{ gap_id: "g1", topic: "操作系统", status: "open", student_goals: [] }] }, rejectUrls: new Set(), verified: [] },
		down: false,
		calls: [],
		runtimeConfigs: new Map(),
		usage: [],
		savedCredentials: [],
		contexts: new Map(),
		turns: [],
		profiles: [],
		overviews: new Map(),
		order: [],
		textbooks: [],
		textbookOutlines: new Map(),
		textbookLookups: [],
		gaps: [],
		protectedCourses: [],
		snapshots: [],
		assembleFailures: [],
		assembled: [],
		savedPaths: [],
		outlineContext: "请先生成学习路径。",
		outlineLookups: [],
		composeAlwaysFail: new Set(),
		composed: [],
		savedOutlines: [],
		saveConflict: false,
		forest: {
			material: { chapter_title: "进程管理", sections: [{ section_id: "1.1", title: "进程", markdown: "进程是资源分配的基本单位。" }], submitted: false },
			lookups: [],
		},
		report: {
			summary: '{"stats":{"attempts":1},"evidence":[{"id":"quiz:q1"},{"id":"chapter:c1"}]}',
			evidence: new Map([
				["quiz:q1", "第二题循环边界出错"],
				["chapter:c1", "章节正文"],
			]),
			reads: [],
			validations: [],
			reject: () => undefined,
		},
		resource: {
			prepareOverride: null,
			sections: ["1.1", "1.2", "1.3"],
			locked: false,
			prepares: [],
			finishes: [],
			saves: [],
			checkpoints: new Map(),
			markdownFocus: [],
			validations: [],
			animationBroken: new Set(),
			animationNeedsTemplate: new Set(),
			videoMode: "available",
			videoVerifies: [],
			videoComposes: [],
			videoComposeIssue: null,
			videoDelayMs: 40,
			videoSpans: [],
			animationSpans: [],
			failSaveOf: null,
			markdownDelayMs: {},
		},
		async prepareResourceGeneration(_uid, courseId, chapterRef, mode) {
			const r = backend.resource;
			r.prepares.push({ chapterRef, mode });
			if (r.prepareOverride) return structuredClone(r.prepareOverride);
			if (r.locked) return { status: "busy", message: "这一章正在生成。" };
			r.locked = true;
			const sections: ResourceSectionInfo[] = r.sections.map((id) => ({
				section_id: id,
				title: `小节 ${id}`,
				checkpoints: { ...(r.checkpoints.get(id) ?? {}) },
				has_composed: r.checkpoints.get(id)?.compose === "completed",
				has_markdown: Boolean(r.checkpoints.get(id)?.markdown),
			}));
			return { status: "ready", course_id: courseId, course_name: "课程", chapter_section_id: chapterRef || "1", sections };
		},
		async finishResourceGeneration(_uid, _course, chapterId, succeeded) {
			backend.resource.finishes.push({ chapterId, succeeded });
			backend.resource.locked = false;
		},
		async getMarkdownPrompt(_uid, _course, _sectionId, focus) {
			backend.resource.markdownFocus.push(focus);
			await new Promise((r) => setTimeout(r, backend.resource.markdownDelayMs[_sectionId] ?? 0));
			return { system_prompt: "你是小节教学文档智能体。", query: `请为小节 ${_sectionId} 生成文档。` };
		},
		async validateMarkdown(_uid, _course, sectionId, raw) {
			backend.resource.validations.push({ sectionId, markdown: raw });
			if (!raw.includes("## 学习目标")) return { ok: false, issue: "缺少“学习目标”标题。" };
			return { ok: true, value: { section_id: sectionId, markdown: raw } };
		},
		async getVideoContext(_uid, _course, sectionId) {
			const r = backend.resource;
			const start = Date.now();
			await new Promise((resolve) => setTimeout(resolve, r.videoDelayMs));
			r.videoSpans.push({ sectionId, start, end: Date.now() });
			if (r.videoMode === "throws") throw new BackendBusinessError(502, "视频源不可用");
			return { section: { title: sectionId }, video_briefs: [{ video_id: "v1", title: "示例", purpose: "讲清概念" }] };
		},
		async verifyVideo(url) {
			backend.resource.videoVerifies.push(url);
			return { ok: true, url, title: "时间复杂度入门讲解", text: "讲解" };
		},
		async composeVideo(_uid, _course, sectionId, body) {
			const r = backend.resource;
			r.videoComposes.push(body);
			if (r.videoComposeIssue) return { ok: false, issue: r.videoComposeIssue.shift() ?? "" } as never;
			if (body.videos.length === 0 || r.videoMode === "unavailable") {
				return { ok: true, status: "unavailable", value: { section_id: sectionId, status: "unavailable", videos: [] } };
			}
			return { ok: true, status: "available", value: { section_id: sectionId, status: "available", videos: body.videos } };
		},
		async getAnimationPrompt(_uid, _course, _sectionId) {
			return { needed: true, system_prompt: "你是 HTML 动画智能体。", query: "请生成动画。" };
		},
		async validateAnimations(_uid, _course, sectionId, animations, fallback) {
			const r = backend.resource;
			const start = Date.now();
			await new Promise((resolve) => setTimeout(resolve, 30));
			r.animationSpans.push({ sectionId, start, end: Date.now() });
			if (r.animationBroken.has(sectionId)) return { ok: false, issue: "动画结构不合格。" };
			if (fallback) return { ok: true, value: { section_id: sectionId, animations: [{ animation_id: "anim_1", html: "<div class='section-animation'>template</div>" }] } };
			if (r.animationNeedsTemplate.has(sectionId)) return { ok: false, issue: "缺少交互控件。" };
			const first = (animations as Array<{ html?: string }>)[0];
			if (!first?.html?.includes("section-animation")) return { ok: false, issue: "根节点必须包含 section-animation。" };
			return { ok: true, value: { section_id: sectionId, animations } };
		},
		async getForestMaterial(userUid, _course, _chapter, quizId) {
			backend.forest.lookups.push({ userUid, quizId });
			return backend.forest.material;
		},
		async getReportContext() {
			return {
				summary: backend.report.summary,
				evidence_ids: [...backend.report.evidence.keys()],
				tools: {},
				has_attempts: true,
			};
		},
		async readReportEvidence(_uid, tool, id) {
			backend.report.reads.push({ tool, id });
			const text = backend.report.evidence.get(id);
			return text === undefined ? { ok: false, issue: "报告工具请求超出本次证据范围" } : { ok: true, text };
		},
		async validateReport(_uid, narrative, details) {
			backend.report.validations.push({ narrative, details });
			const issue = backend.report.reject(narrative, details);
			return issue ? { ok: false, issue } : { ok: true, report: { ...(narrative as object), stats: { attempts: 1 }, evidence: [] } };
		},
		async saveSectionResource(_uid, _course, sectionId, body) {
			const r = backend.resource;
			if (r.failSaveOf && r.failSaveOf.sectionId === sectionId && r.failSaveOf.phase === body.phase && !body.failure) {
				throw new BackendBusinessError(500, "存储异常");
			}
			r.saves.push({ sectionId, phase: body.phase, value: body.value, failure: body.failure, at: Date.now() });
			const current = r.checkpoints.get(sectionId) ?? {};
			current[body.phase] = body.failure ? "failed" : "completed";
			r.checkpoints.set(sectionId, current);
		},
		async getOutlineSourceContext(_userUid, courseRef) {
			backend.outlineLookups.push(courseRef);
			if (typeof backend.outlineContext === "string") throw new BackendBusinessError(422, backend.outlineContext);
			return structuredClone(backend.outlineContext);
		},
		async composeOutline(_userUid, course, naming: any) {
			backend.composed.push({ course: course.course_name, naming });
			if (backend.composeAlwaysFail.has(course.course_name)) throw new BackendBusinessError(422, "章节命名始终不合规。");
			const texts = (naming.section_texts ?? {}) as Record<string, any>;
			const missing = course.skeleton.filter((s) => !texts[s.section_id]).map((s) => s.section_id);
			if (missing.length > 0) throw new BackendBusinessError(422, `缺少章节文案：${missing.join("、")}`);
			for (const [id, t] of Object.entries(texts)) {
				const visible = `${t.title}\n${t.description}\n${(t.key_knowledge_points ?? []).join("\n")}`;
				if (/sec_\d/i.test(visible)) throw new BackendBusinessError(422, `章节 ${id} 的可见文案包含教材内部编号（如 sec_1_1）。`);
				if (/[A-Za-z]{4,}/.test(visible)) throw new BackendBusinessError(422, "课程大纲可见文案不能直接暴露英文教材标题。");
			}
			return {
				outline: {
					course_id: course.course_node_id,
					course_name: course.course_name,
					grade_year: course.grade_year,
					personalization_summary: naming.personalization_summary,
					sections: course.skeleton.map((s) => ({ ...s, title: texts[s.section_id].title })),
				},
			};
		},
		async saveOutlines(_userUid, pathFingerprints, outlines) {
			if (backend.saveConflict) throw new BackendBusinessError(409, "学习路径已更新，请重新生成课程大纲。");
			backend.order.push("save_outlines");
			backend.savedOutlines.push({ pathFingerprints, outlines });
			return { saved_course_ids: outlines.map((o) => String(o.course_id)) };
		},
		async getKnowledgeBaseOverview() {
			return structuredClone(backend.kb.overview);
		},
		async verifyTextbookSource(candidate) {
			backend.kb.verified.push(candidate);
			if (backend.kb.rejectUrls.has(String(candidate.source_url))) {
				return { accepted: false, reason: "source_url 无法访问。", source_result: null };
			}
			return {
				accepted: true,
				reason: "",
				source_result: {
					source_result_id: `source-result-${backend.kb.verified.length}`,
					title: candidate.title,
					source_url: candidate.source_url,
					source_type: candidate.source_type,
					already_imported: false,
					textbook_id: null,
				},
			};
		},
		async listPublishedTextbooks() {
			backend.textbookLookups.push("list");
			backend.order.push("textbooks");
			return structuredClone(backend.textbooks);
		},
		async getTextbookOutline(textbookId) {
			backend.textbookLookups.push(`outline:${textbookId}`);
			const outline = backend.textbookOutlines.get(textbookId);
			if (!outline) throw new BackendBusinessError(404, "教材不存在或未发布。");
			return structuredClone(outline);
		},
		async registerKnowledgeGap(topic, summary) {
			const gapId = `gap-${backend.gaps.length + 1}`;
			backend.gaps.push({ topic, summary, gapId });
			return gapId;
		},
		async getProtectedCourses() {
			return structuredClone(backend.protectedCourses);
		},
		async getProgressSnapshots() {
			return structuredClone(backend.snapshots);
		},
		async assembleLearningPath(_userUid, gradeYear, body) {
			backend.assembled.push({ gradeYear, plan: body.plan });
			const failure = backend.assembleFailures.shift();
			if (failure) throw new BackendBusinessError(422, failure);
			const courses = body.intake_courses as Array<{ title: string; source_textbook_id: string }>;
			const nodes = courses.map((course, index) => ({
				course_node_id: `${gradeYear}_course_${index + 1}`,
				course_or_chapter_theme: course.title,
				source_textbook_id: course.source_textbook_id,
			}));
			const completed = backend.snapshots.find((s) => s.grade_year === gradeYear)?.completed_courses ?? 0;
			const current = nodes[Math.min(completed, nodes.length - 1)]!;
			return {
				path_data: {
					schema_version: "learning_path.v2.course_node",
					grade_plans: { [gradeYear]: { course_nodes: nodes } },
					current_learning_course: { ...current, progress_state: "in_progress", next_action: "先完成需求拆解" },
				},
			};
		},
		async saveYearLearningPath(userUid, gradeYear, topic, path) {
			backend.order.push("save_path");
			backend.savedPaths.push({ userUid, gradeYear, topic, path });
		},
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
