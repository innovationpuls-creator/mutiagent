import { afterAll, beforeAll } from "vitest";
import type { ChatContext, LearningOverview } from "../src/backendClient.js";
import { createApp } from "../src/app.js";
import type { RuntimeConfig } from "../src/models/types.js";
import { type FakeBackend, fakeBackend, signToken, testConfig } from "./helpers.js";
import { type MockUpstream, startMockUpstream } from "./mockUpstream.js";

export const CHAT_USER = "u-chat-1";
export const UNCONFIGURED_USER = "u-chat-empty";

export const FULL_CONFIRMED = {
	current_grade: "大三",
	major: "软件工程",
	learning_stage: "有基础",
	has_clear_goal: "是",
	learning_method_preference: "项目驱动学习",
	learning_pace_preference: "每天少量",
	content_preference: ["代码实践"],
	need_guidance: "需要轻量提醒",
	knowledge_foundation: "有前后端基础",
	strengths: "动手能力强",
	weaknesses: "缺少项目经验",
	experience: "有课程项目经验",
	short_term_goal: "找工作",
	long_term_goal: "成为全栈开发者",
	weekly_available_time: "每周 6-10 小时",
	constraints: "平时课程多",
};

export function completeProfile(): Record<string, unknown> {
	return {
		type: "basic_profile",
		stage: "generated",
		question_mode: "question_box",
		confirmed_info: { ...FULL_CONFIRMED },
		defaulted_fields: [],
		question_md: "画像已生成，是否进入学习路径草案智能体？",
		question_box: { question: "下一步？", options: [] },
		text: "总结",
		summary_text: "总结",
	};
}

export const OVERVIEW: LearningOverview = {
	has_paths: true,
	has_outline: true,
	latest_grade_year: "year_3",
	current_course_id: "course-os",
	progress: [
		{
			grade_year: "year_3",
			total_courses: 4,
			completed_courses: 1,
			current_course_id: "course-os",
			current_course_title: "操作系统",
			current_progress_state: "learning",
			next_course_id: "course-os",
			next_course_title: "操作系统",
		},
	],
	path_text: "你的学习路径里已经有这些课程：\n大三（year_3）：4 门课\n1. 操作系统\n2. 计算机网络",
	outline_text: "课程大纲 · 操作系统\n第一章 进程管理",
	next_step_text: "下一步：进入《操作系统》的第一章。",
};

export function baseContext(sessionId: string, overrides: Partial<ChatContext> = {}): ChatContext {
	return {
		session_id: sessionId,
		user_uid: CHAT_USER,
		history: [],
		session_state: {},
		profile: null,
		has_complete_profile: false,
		year_learning_paths: null,
		latest_grade_year: null,
		course_knowledge: null,
		...overrides,
	};
}

export function pathContext(sessionId: string, withOutline = true): ChatContext {
	return baseContext(sessionId, {
		profile: completeProfile(),
		has_complete_profile: true,
		year_learning_paths: { year_3: { grade_plans: {} } },
		latest_grade_year: "year_3",
		course_knowledge: withOutline ? { course_id: "course-os", grade_year: "year_3" } : null,
	});
}

export function runtimeConfig(userUid: string, baseUrl: string, backupUrl?: string): RuntimeConfig {
	const provider = (id: string, url: string) => ({
		provider_id: id,
		display_name: id,
		is_builtin: false,
		protocol: "openai-completions",
		base_url: url,
		headers: {},
		auth_type: "api_key" as const,
		enabled: true,
		api_key: "sk-test-key-1234",
		oauth_credential: null,
		oauth_refresh_fingerprint: null,
	});
	const model = (id: string, modelId: string) => ({
		id: `${id}-${modelId}`,
		provider_id: id,
		model_id: modelId,
		display_name: modelId,
		context_window: 32000,
		max_tokens: 2000,
		supports_vision: false,
		supports_tools: true,
		supports_reasoning: false,
		compat_config: {},
		pricing: { input: 1, output: 2 },
		enabled: true,
	});
	return {
		user_uid: userUid,
		role: "student",
		providers: backupUrl ? [provider("p1", baseUrl), provider("p2", backupUrl)] : [provider("p1", baseUrl)],
		custom_models: backupUrl ? [model("p1", "m-main"), model("p2", "m-backup")] : [model("p1", "m-main")],
		preferences: {
			config_mode: backupUrl ? "advanced" : "simple",
			default_model_ref: { provider_id: "p1", model_id: "m-main" },
			default_vision_model_ref: null,
			default_thinking_level: "off",
			runtime_options: {},
			slot_bindings: backupUrl
				? {
						chat_profile: {
							model_ref: { provider_id: "p1", model_id: "m-main" },
							fallback_chain: [{ provider_id: "p2", model_id: "m-backup" }],
						},
					}
				: {},
		},
	};
}

export interface SseFrame {
	event: string;
	data: Record<string, any>;
}

/** Parse an SSE body; `event: message` frames are unwrapped to their `type`. */
export function parseSse(body: string): SseFrame[] {
	const frames: SseFrame[] = [];
	for (const block of body.split("\n\n")) {
		let event = "";
		let data = "";
		for (const line of block.split("\n")) {
			if (line.startsWith("event: ")) event = line.slice(7);
			else if (line.startsWith("data: ")) data += line.slice(6);
		}
		if (!event || !data) continue;
		const parsed = JSON.parse(data) as Record<string, any>;
		frames.push({ event: event === "message" ? String(parsed.type) : event, data: parsed });
	}
	return frames;
}

export interface ChatHarness {
	backend: FakeBackend;
	primary: MockUpstream;
	backup: MockUpstream;
	app: ReturnType<typeof createApp>;
	send(sessionId: string, message: string, opts?: { user?: string; token?: string | null }): Promise<{
		status: number;
		frames: SseFrame[];
		text: string;
	}>;
	toolNames(upstream?: MockUpstream, index?: number): string[];
	reset(withBackup?: boolean): void;
}

export function setupChatHarness(): ChatHarness {
	const harness = {} as ChatHarness;
	beforeAll(async () => {
		harness.primary = await startMockUpstream();
		harness.backup = await startMockUpstream();
	});
	afterAll(async () => {
		await harness.primary.close();
		await harness.backup.close();
	});

	harness.toolNames = (upstream = harness.primary, index = 0) => {
		const tools = (upstream.requests[index]?.body.tools ?? []) as Array<{ function: { name: string } }>;
		return tools.map((tool) => tool.function.name).sort();
	};

	Object.assign(harness, {
		reset(withBackup = false) {
			harness.backend = fakeBackend();
			harness.backend.users.set(CHAT_USER, { user_uid: CHAT_USER, exists: true, role: "student", is_active: true });
			harness.backend.users.set(UNCONFIGURED_USER, { user_uid: UNCONFIGURED_USER, exists: true, role: "student", is_active: true });
			harness.backend.runtimeConfigs.set(
				CHAT_USER,
				runtimeConfig(CHAT_USER, harness.primary.url, withBackup ? harness.backup.url : undefined),
			);
			harness.backend.runtimeConfigs.set(UNCONFIGURED_USER, {
				user_uid: UNCONFIGURED_USER,
				role: "student",
				providers: [],
				custom_models: [],
				preferences: {
					config_mode: "simple",
					default_model_ref: null,
					default_vision_model_ref: null,
					default_thinking_level: "medium",
					runtime_options: {},
					slot_bindings: {},
				},
			});
			for (const upstream of [harness.primary, harness.backup]) {
				upstream.requests.length = 0;
				upstream.queue.length = 0;
				upstream.script.length = 0;
			}
			harness.app = createApp({ config: testConfig(), backend: harness.backend, logSink: () => {} });
		},
		async send(sessionId: string, message: string, opts: { user?: string; token?: string | null } = {}) {
			const user = opts.user ?? CHAT_USER;
			const token = opts.token === undefined ? await signToken(user) : opts.token;
			const response = await harness.app.request("/api/chat/message", {
				method: "POST",
				headers: {
					"Content-Type": "application/json",
					...(token ? { Authorization: `Bearer ${token}` } : {}),
				},
				body: JSON.stringify({ session_id: sessionId, message }),
			});
			const text = await response.text();
			const isSse = (response.headers.get("content-type") ?? "").includes("text/event-stream");
			return { status: response.status, frames: isSse ? parseSse(text) : [], text };
		},
	});
	return harness;
}
