import { beforeEach, describe, expect, it } from "vitest";
import { gatedToolNames, stageOf } from "../src/chat/supervisor.js";
import {
	CHAT_USER,
	FULL_CONFIRMED,
	OVERVIEW,
	UNCONFIGURED_USER,
	baseContext,
	completeProfile,
	pathContext,
	setupChatHarness,
} from "./chatHarness.js";

const h = setupChatHarness();
beforeEach(() => h.reset());

const delegateProfile = { tool: "delegate_profile_agent", args: { reason: "采集画像" } } as const;

function names(frames: { event: string }[]) {
	return frames.map((f) => f.event);
}

describe("AC-1 stage tool gating", () => {
	it("gates the tool list by business state (pure)", () => {
		const a = stageOf({ profile: null, year_learning_paths: null, course_knowledge: null });
		expect(gatedToolNames(a)).toEqual(["delegate_profile_agent"]);
		const b = stageOf({ profile: completeProfile(), year_learning_paths: null, course_knowledge: null });
		expect(gatedToolNames(b)).toEqual([
			"delegate_profile_agent",
			"delegate_learning_path_intake",
			"get_student_progress_summary",
		]);
		const c = stageOf({ profile: completeProfile(), year_learning_paths: { year_1: {} }, course_knowledge: null });
		expect(gatedToolNames(c)).toEqual([
			...gatedToolNames(b),
			"get_learning_path",
			"get_course_outline",
			"delegate_course_knowledge",
		]);
		const cWithOutline = stageOf({ profile: completeProfile(), year_learning_paths: { year_1: {} }, course_knowledge: { course_id: "x" } });
		expect(gatedToolNames(cWithOutline)).toContain("delegate_course_resources");
		// A collecting (incomplete) profile never unlocks later stages, even with stale paths.
		const stale = stageOf({ profile: { ...completeProfile(), type: "collecting" }, year_learning_paths: { year_1: {} }, course_knowledge: null });
		expect(stale.stage).toBe("A");
	});

	it("a new account asking for outline+path only receives the profile tool", async () => {
		h.backend.contexts.set(`${CHAT_USER}:s-a`, baseContext("s-a"));
		h.primary.queue.push({ text: "我们先来完善你的学习画像吧，先告诉我你的年级和专业。" });
		const res = await h.send("s-a", "直接帮我生成大纲和学习路径");
		expect(res.status).toBe(200);
		expect(h.toolNames()).toEqual(["delegate_profile_agent"]);
		expect(res.frames.at(-2)?.event).toBe("message_completed");
		expect(res.frames.at(-1)?.event).toBe("session_completed");
	});

	it("a hallucinated out-of-stage tool call is rejected", async () => {
		h.backend.contexts.set(`${CHAT_USER}:s-b`, baseContext("s-b"));
		h.primary.queue.push(
			{ tool: "delegate_learning_path_intake", args: {} },
			{ text: "要先完善画像才能生成路径哦。" },
		);
		const res = await h.send("s-b", "直接帮我生成大纲和学习路径");
		expect(res.frames.find((f) => f.event === "message_completed")?.data.full_text).toContain("画像");
	});
});

describe("AC-2/3/4 profile collection", () => {
	it("collects over turns: question_box card, merge, then a complete basic_profile", async () => {
		h.backend.contexts.set(`${CHAT_USER}:s-p`, baseContext("s-p"));
		// Turn 1: only the grade is known.
		h.primary.queue.push(delegateProfile, {
			tool: "ask_profile_question",
			args: { partial_confirmed: { current_grade: "大三" }, question_md: "你的专业是什么？", field: "major" },
		});
		const t1 = await h.send("s-p", "我大三");
		expect(names(t1.frames)).toContain("supervisor_plan");
		const collecting = h.backend.profiles[0]!.profile as any;
		expect(collecting.type).toBe("collecting");
		expect(collecting.confirmed_info.current_grade).toBe("大三");
		expect(collecting.question_mode).toBe("question_box");
		expect(Array.isArray(collecting.question_box.options)).toBe(true);
		expect(typeof collecting.question_box.question).toBe("string");
		expect(Array.isArray(collecting.defaulted_fields)).toBe(true);
		expect(t1.frames.find((f) => f.event === "message_completed")?.data.full_text).toBe(collecting.text);
		expect(h.backend.turns[0]!.turn.session_state_patch).toMatchObject({ pending_profile_followup: expect.anything() });

		// Turn 2: the stored draft is carried into the next turn (page refresh safe).
		h.backend.contexts.set(
			`${CHAT_USER}:s-p`,
			baseContext("s-p", { profile: collecting, session_state: { pending_profile_followup: { field: "major" } } }),
		);
		h.primary.queue.push(delegateProfile, {
			tool: "ask_profile_question",
			args: { partial_confirmed: { major: "软件工程" }, question_md: "你的近期目标是？", field: "short_term_goal" },
		});
		await h.send("s-p", "软件工程");
		const second = h.backend.profiles[1]!.profile as any;
		expect(second.confirmed_info).toMatchObject({ current_grade: "大三", major: "软件工程" });
		expect(second.question_box.options.map((o: any) => o.label)).toContain("找工作");

		// Turn 3: everything confirmed -> complete profile in the exact frontend shape.
		h.backend.contexts.set(`${CHAT_USER}:s-p`, baseContext("s-p", { profile: second }));
		h.primary.queue.push(delegateProfile, {
			tool: "save_student_profile",
			args: { confirmed_info: FULL_CONFIRMED, summary_text: "【基础学习画像总结】大三软件工程，目标找工作。" },
		});
		const t3 = await h.send("s-p", "目标找工作，其余你按我之前说的来");
		const basic = h.backend.profiles[2]!.profile as any;
		expect(basic.type).toBe("basic_profile");
		expect(basic.stage).toBe("generated");
		expect(Object.keys(basic.confirmed_info).sort()).toEqual(Object.keys(FULL_CONFIRMED).sort());
		expect(basic.text).toBe(basic.summary_text);
		expect(t3.frames.find((f) => f.event === "message_completed")?.data.full_text).toBe(basic.summary_text);
		expect(t3.frames.at(-1)?.data.has_profile).toBe(true);
		expect(h.backend.turns[2]!.turn.session_state_patch).toEqual({ pending_profile_followup: null });
	});

	it("unsupported grade never reaches storage; the student is asked again", async () => {
		h.backend.contexts.set(`${CHAT_USER}:s-g`, baseContext("s-g"));
		h.primary.queue.push(delegateProfile, {
			tool: "ask_profile_question",
			args: { partial_confirmed: { current_grade: "研二", major: "软件工程" }, question_md: "好的" },
		});
		const res = await h.send("s-g", "我研二，软件工程，想学 AI");
		const saved = h.backend.profiles[0]!.profile as any;
		expect(saved.type).toBe("collecting");
		expect(saved.confirmed_info.current_grade).toBe("");
		expect(saved.confirmed_info.major).toBe("软件工程");
		expect(saved.text).toContain("研二");
		expect(saved.text).toContain("大一到大四");
		expect(saved.question_box.options.map((o: any) => o.value)).toEqual(["大一", "大二", "大三", "大四", "__free_text__"]);
		expect(names(res.frames)).not.toContain("error");
	});

	it("a save with an unsupported grade is rejected in-loop and the model self-corrects", async () => {
		h.backend.contexts.set(`${CHAT_USER}:s-g2`, baseContext("s-g2"));
		h.primary.queue.push(
			delegateProfile,
			{ tool: "save_student_profile", args: { confirmed_info: { ...FULL_CONFIRMED, current_grade: "研二" }, summary_text: "x" } },
			{ tool: "ask_profile_question", args: { partial_confirmed: {}, question_md: "你目前是本科几年级？", field: "current_grade" } },
		);
		const res = await h.send("s-g2", "我研二，软件工程，想学 AI");
		expect(h.backend.profiles).toHaveLength(1);
		const saved = h.backend.profiles[0]!.profile as any;
		expect(saved.type).toBe("collecting");
		expect(saved.confirmed_info.current_grade).not.toBe("研二");
		// The rejection text was fed back to the model (3rd upstream request carries it).
		expect(JSON.stringify(h.primary.requests.at(-1)!.body.messages)).toContain("不在支持范围");
		expect(names(res.frames)).not.toContain("error");
	});

	it("gives up after two self-corrections and falls back to a deterministic card", async () => {
		h.backend.contexts.set(`${CHAT_USER}:s-g3`, baseContext("s-g3"));
		const bad = { tool: "save_student_profile", args: { confirmed_info: { ...FULL_CONFIRMED, current_grade: "研二" }, summary_text: "x" } } as const;
		h.primary.queue.push(delegateProfile, bad, bad, bad, bad);
		const res = await h.send("s-g3", "我研二");
		const saved = h.backend.profiles[0]!.profile as any;
		expect(saved.type).toBe("collecting");
		expect(saved.confirmed_info.current_grade).toBe("");
		expect(saved.text).toContain("研二");
		// delegate + 3 save attempts (initial + 2 corrections); the 4th scripted reply is unused.
		expect(h.primary.requests).toHaveLength(4);
		expect(names(res.frames)).not.toContain("error");
	});

	it("default fill: one turn completes the profile and records defaulted fields", async () => {
		h.backend.contexts.set(`${CHAT_USER}:s-d`, baseContext("s-d"));
		const { has_clear_goal, learning_pace_preference, need_guidance, long_term_goal, constraints, ...rest } = FULL_CONFIRMED;
		h.primary.queue.push(delegateProfile, {
			tool: "save_student_profile",
			args: {
				confirmed_info: { ...rest, content_preference: [], strengths: "", weaknesses: "" },
				summary_text: "大三软件工程，按默认生成。",
				use_defaults: true,
				defaults_quote: "按默认帮我生成",
			},
		});
		const res = await h.send("s-d", "直接按默认帮我生成画像");
		const basic = h.backend.profiles[0]!.profile as any;
		expect(basic.type).toBe("basic_profile");
		expect(Object.keys(basic.confirmed_info)).toHaveLength(16);
		for (const key of ["has_clear_goal", "learning_pace_preference", "need_guidance", "long_term_goal", "constraints", "strengths", "weaknesses", "content_preference"]) {
			expect(basic.defaulted_fields).toContain(key);
		}
		expect(basic.defaulted_fields).not.toContain("major");
		expect(res.frames.at(-1)?.data.has_profile).toBe(true);
	});

	it("use_defaults without the student's request is refused", async () => {
		h.backend.contexts.set(`${CHAT_USER}:s-d2`, baseContext("s-d2"));
		h.primary.queue.push(
			delegateProfile,
			{ tool: "save_student_profile", args: { confirmed_info: { current_grade: "大三", major: "软件工程" }, summary_text: "x", use_defaults: true, defaults_quote: "按默认补全" } },
			{ tool: "ask_profile_question", args: { partial_confirmed: {}, question_md: "你的近期目标是？", field: "short_term_goal" } },
		);
		await h.send("s-d2", "我大三软件工程");
		expect(JSON.stringify(h.primary.requests.at(-1)!.body.messages)).toContain("defaults_quote");
		const saved = h.backend.profiles[0]!.profile as any;
		expect(saved.type).toBe("collecting");
	});

	it("core fields cannot be marked as defaulted without the student's request", async () => {
		h.backend.contexts.set(`${CHAT_USER}:s-d3`, baseContext("s-d3"));
		h.primary.queue.push(
			delegateProfile,
			{ tool: "save_student_profile", args: { confirmed_info: FULL_CONFIRMED, summary_text: "x", defaulted_fields: ["short_term_goal"] } },
			{ tool: "ask_profile_question", args: { partial_confirmed: {}, question_md: "你的近期目标是？", field: "short_term_goal" } },
		);
		await h.send("s-d3", "我大三软件工程");
		expect(JSON.stringify(h.primary.requests.at(-1)!.body.messages)).toContain("必须来自学生的真实表达");
		expect((h.backend.profiles[0]!.profile as any).type).toBe("collecting");
	});
});

describe("AC-5 free-form read-only queries", () => {
	it("answers from the read-only tool's real data, with no keyword table", async () => {
		h.backend.contexts.set(`${CHAT_USER}:s-q`, pathContext("s-q"));
		h.backend.overviews.set(CHAT_USER, OVERVIEW);
		h.primary.queue.push(
			{ tool: "get_student_progress_summary", args: {} },
			{ text: "你目前在大三，正在学《操作系统》，已完成 1/4 门课。" },
		);
		const res = await h.send("s-q", "下个月我主要要学哪几门课？");
		expect(h.toolNames()).toEqual(
			expect.arrayContaining(["get_student_progress_summary", "get_learning_path", "get_course_outline", "delegate_course_resources"]),
		);
		// The tool result (real DB data) was handed back to the model.
		expect(JSON.stringify(h.primary.requests[1]!.body.messages)).toContain("操作系统");
		expect(names(res.frames)).toEqual(expect.arrayContaining(["data_update", "text_chunk"]));
		expect(res.frames.find((f) => f.event === "data_update" && f.data.update_type === "progress_loaded")).toBeTruthy();
		expect(res.frames.find((f) => f.event === "message_completed")?.data.full_text).toContain("《操作系统》");
	});

	it("reads the outline tool too, emitting course_knowledge_loaded", async () => {
		h.backend.contexts.set(`${CHAT_USER}:s-o`, pathContext("s-o"));
		h.backend.overviews.set(CHAT_USER, OVERVIEW);
		h.primary.queue.push({ tool: "get_course_outline", args: {} }, { text: "大纲第一章是进程管理。" });
		const res = await h.send("s-o", "看看大纲");
		const update = res.frames.find((f) => f.event === "data_update" && f.data.update_type === "course_knowledge_loaded");
		expect(update?.data.course_id).toBe("course-os");
	});
});

describe("AC-6 persistence order and failures", () => {
	it("persists the turn before announcing completion", async () => {
		h.backend.contexts.set(`${CHAT_USER}:s-t`, baseContext("s-t"));
		const events: string[] = [];
		const original = h.backend.persistTurn;
		h.backend.persistTurn = async (...args) => {
			events.push("persist");
			return original(...args);
		};
		h.primary.queue.push({ text: "你好呀！" });
		const res = await h.send("s-t", "你好");
		const turn = h.backend.turns[0]!;
		expect(turn.turn).toMatchObject({ user_message: "你好", assistant_message: "你好呀！" });
		expect(events).toEqual(["persist"]);
		expect(names(res.frames).slice(-2)).toEqual(["message_completed", "session_completed"]);
	});

	it("when the full persist fails there is no completion event, only an error", async () => {
		h.backend.contexts.set(`${CHAT_USER}:s-f`, baseContext("s-f"));
		let calls = 0;
		const original = h.backend.persistTurn;
		h.backend.persistTurn = async (sessionId, userUid, turn) => {
			calls += 1;
			if (calls === 1) throw new Error("db down");
			return original(sessionId, userUid, turn);
		};
		h.primary.queue.push({ text: "好的" });
		const res = await h.send("s-f", "你好");
		expect(names(res.frames)).toContain("error");
		expect(names(res.frames)).not.toContain("message_completed");
		// Fallback keeps the student's message and never writes an empty AI row.
		const fallback = h.backend.turns.at(-1)!.turn;
		expect(fallback.user_message).toBe("你好");
		expect(fallback.assistant_message ?? null).toBeNull();
	});

	it("an unconfigured model stops before the supervisor and writes nothing", async () => {
		h.backend.contexts.set(`${UNCONFIGURED_USER}:s-n`, { ...baseContext("s-n"), user_uid: UNCONFIGURED_USER });
		const res = await h.send("s-n", "你好", { user: UNCONFIGURED_USER });
		const error = res.frames.find((f) => f.event === "error");
		expect(error?.data).toMatchObject({ error_code: "MODEL_NOT_CONFIGURED", action: "open_model_settings" });
		expect(names(res.frames)).not.toContain("message_completed");
		expect(h.backend.turns).toHaveLength(0);
		expect(h.primary.requests).toHaveLength(0);
	});

	it("a model marked as unable to call tools is refused with a clear, actionable error", async () => {
		const config = h.backend.runtimeConfigs.get(CHAT_USER)!;
		h.backend.runtimeConfigs.set(CHAT_USER, {
			...config,
			custom_models: config.custom_models.map((row) => ({ ...row, supports_tools: false })),
		});
		h.backend.contexts.set(`${CHAT_USER}:s-nt`, baseContext("s-nt"));
		h.primary.queue.push(delegateProfile);
		const res = await h.send("s-nt", "我大三");
		const error = res.frames.find((f) => f.event === "error");
		expect(error?.data).toMatchObject({ error_code: "MODEL_CAPABILITY_MISMATCH" });
		expect(String(error?.data.message)).toContain("不支持工具调用");
		expect(names(res.frames)).not.toContain("message_completed");
	});

	it("a failing model keeps the user's message and reports an error event", async () => {
		h.backend.contexts.set(`${CHAT_USER}:s-m`, baseContext("s-m"));
		h.primary.script.push(400);
		const res = await h.send("s-m", "你好");
		expect(names(res.frames)).toContain("error");
		expect(names(res.frames)).not.toContain("message_completed");
		expect(h.backend.turns).toHaveLength(1);
		expect(h.backend.turns[0]!.turn.assistant_message ?? null).toBeNull();
	});
});

describe("entry routing", () => {
	it("the explicit leaf-resource protocol skips the supervisor but still needs a configured model", async () => {
		h.backend.contexts.set(`${UNCONFIGURED_USER}:s-l`, { ...baseContext("s-l"), user_uid: UNCONFIGURED_USER });
		const res = await h.send(
			"s-l",
			"[LEAF_RESOURCE_GENERATION]\ncourse_node_id: c1\nchapter_section_id: s1\nscope: chapter_sections\nmode: generate\n[/LEAF_RESOURCE_GENERATION]",
			{ user: UNCONFIGURED_USER },
		);
		expect(res.frames.find((f) => f.event === "error")?.data).toMatchObject({ error_code: "MODEL_NOT_CONFIGURED" });
		// Nothing was gated, locked or written: the chapter lock is never taken without a model.
		expect(h.backend.resource.prepares).toHaveLength(0);
		expect(h.backend.turns).toHaveLength(0);
		expect(h.primary.requests).toHaveLength(0);
	});

	it("a pending regeneration answer goes straight to the resource node without a supervisor call", async () => {
		h.backend.contexts.set(
			`${CHAT_USER}:s-r`,
			baseContext("s-r", { session_state: { pending_leaf_regeneration: { course_node_id: "c1", chapter_section_id: "s1" } } }),
		);
		h.backend.resource.prepareOverride = { status: "refused", message: "只能为当前课程生成教学内容。" };
		const res = await h.send("s-r", "多讲一些例题");
		expect(h.backend.resource.prepares).toEqual([{ chapterRef: "s1", mode: "regenerate" }]);
		expect(h.primary.requests).toHaveLength(0);
		// The pending marker is consumed even when the request is refused.
		expect(h.backend.turns[0]!.turn.session_state_patch).toEqual({ pending_leaf_regeneration: null });
		expect(res.frames.find((f) => f.event === "message_completed")?.data.full_text).toBe("只能为当前课程生成教学内容。");
	});

	it("keyword-looking messages are NOT intercepted any more", async () => {
		h.backend.contexts.set(`${CHAT_USER}:s-k`, pathContext("s-k"));
		h.backend.overviews.set(CHAT_USER, OVERVIEW);
		h.primary.queue.push({ text: "我来帮你看看。" });
		await h.send("s-k", "下一步学什么？看看大纲和学习路径");
		expect(h.primary.requests).toHaveLength(1);
	});
});

describe("HTTP contract", () => {
	it("401 without a token, 404 for an unknown session, 422 for a bad body", async () => {
		expect((await h.send("s-x", "hi", { token: null })).status).toBe(401);
		expect((await h.send("missing", "hi")).status).toBe(404);
		const response = await h.app.request("/api/chat/message", {
			method: "POST",
			headers: { "Content-Type": "application/json", Authorization: `Bearer ${await (await import("./helpers.js")).signToken(CHAT_USER)}` },
			body: JSON.stringify({ session_id: "s", message: "" }),
		});
		expect(response.status).toBe(422);
	});

	it("falls back to the next candidate model when the first is overloaded", async () => {
		h.reset(true);
		h.backend.contexts.set(`${CHAT_USER}:s-fb`, baseContext("s-fb"));
		h.primary.script.push(503);
		h.backup.queue.push({ text: "备用模型回复" });
		const res = await h.send("s-fb", "你好");
		expect(res.frames.find((f) => f.event === "message_completed")?.data.full_text).toBe("备用模型回复");
		expect(h.primary.requests).toHaveLength(1);
		expect(h.backup.requests).toHaveLength(1);
		await h.app.request("/internal/health", { headers: { "X-Internal-Token": "test-internal-token" } });
	});
});
