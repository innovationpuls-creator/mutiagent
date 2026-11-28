import { beforeEach, describe, expect, it } from "vitest";
import type { OutlineSourceContext, OutlineSourceCourse } from "../src/backendClient.js";
import { mapWithConcurrency } from "../src/chat/outlineAgent.js";
import { CHAT_USER, pathContext, setupChatHarness } from "./chatHarness.js";

const h = setupChatHarness();
beforeEach(() => h.reset());

const ALL = "__all_current_grade__";

function course(index: number): OutlineSourceCourse {
	const long = index === 1;
	return {
		course_node_id: `year_3_course_${index}`,
		course_name: `课程${index}`,
		grade_year: "year_3",
		source_textbook_id: `tb-${index}`,
		source_textbook_title: `教材${index}`,
		naming_context: { course_name: `课程${index}`, course_goal: "掌握核心概念" },
		skeleton: [
			{ section_id: "1", parent_section_id: null, depth: 1, source_section_titles: ["Chapter"] },
			{
				section_id: "1.1",
				parent_section_id: "1",
				depth: 2,
				source_section_titles: ["Complexity Analysis"],
				source_content_chars: long ? 6500 : 3000,
				source_chunk_index: long ? 1 : null,
				source_chunk_total: long ? 2 : null,
			},
			...(long
				? [
						{
							section_id: "1.2",
							parent_section_id: "1",
							depth: 2,
							source_section_titles: ["Complexity Analysis"],
							source_content_chars: 6500,
							source_chunk_index: 2,
							source_chunk_total: 2,
						},
					]
				: []),
		],
	};
}

function context(count: number): OutlineSourceContext {
	return {
		grade_year: "year_3",
		current_course_id: "year_3_course_1",
		path_fingerprints: { year_3: "fp-1" },
		courses: Array.from({ length: count }, (_, i) => course(i + 1)),
	};
}

/** Naming that covers every id any fake course uses, so lane scheduling order does not matter. */
const naming = (title = "时间复杂度入门") => ({
	personalization_summary: "按你的节奏安排",
	sections: ["1", "1.1", "1.2"].map((id) => ({
		section_id: id,
		title,
		description: "用中文说明本节要学什么",
		key_knowledge_points: ["知识点一", "知识点二"],
	})),
});
const submit = (title?: string) => ({ tool: "submit_outline_naming", args: naming(title) }) as const;
const delegate = (courseRef = "") => ({ tool: "delegate_course_knowledge", args: { course_ref: courseRef, reason: "生成大纲" } }) as const;

function setup(sessionId: string, count: number) {
	h.backend.contexts.set(`${CHAT_USER}:${sessionId}`, pathContext(sessionId, false));
	h.backend.outlineContext = context(count);
}
const done = (res: Awaited<ReturnType<typeof h.send>>) => res.frames.find((f) => f.event === "message_completed")?.data.full_text as string;

describe("single course", () => {
	it("generates, saves atomically with the path fingerprint, and replies with the legacy prefix", async () => {
		setup("o1", 1);
		h.primary.queue.push(delegate(), submit());
		const res = await h.send("o1", "帮我生成课程大纲");
		expect(h.backend.outlineLookups).toEqual([""]);
		expect(h.backend.savedOutlines).toHaveLength(1);
		expect(h.backend.savedOutlines[0]!.pathFingerprints).toEqual({ year_3: "fp-1" });
		expect(done(res)).toMatch(/^课程大纲已生成：《课程1》/);
		expect(done(res)).toContain("教材《教材1》");
		expect(res.frames.find((f) => f.event === "data_update" && f.data.update_type === "course_knowledge_generated")).toBeTruthy();
		const complete = res.frames.find((f) => f.event === "session_completed");
		expect(complete?.data.has_outline).toBe(true);
		// Persist first, then the completion events.
		expect(h.backend.order.indexOf("save_outlines")).toBeLessThan(h.backend.order.indexOf("persist"));
		expect(h.backend.turns).toHaveLength(1);
	});

	it("passes a course reference through to the backend", async () => {
		setup("o1b", 1);
		h.primary.queue.push(delegate("线性结构实践"), submit());
		await h.send("o1b", "给线性结构实践生成大纲");
		expect(h.backend.outlineLookups).toEqual(["线性结构实践"]);
	});

	it("tells the model about split sections and demands Chinese, internal-id-free names", async () => {
		setup("o1c", 2);
		h.primary.queue.push(delegate(ALL), submit(), submit());
		await h.send("o1c", "本年级所有课程大纲");
		const prompts = h.primary.requests.slice(1).map((r) => r.body.messages[0].content as string);
		expect(prompts.some((p) => p.includes("这是第 1 部分") && p.includes("拆成 2 个部分"))).toBe(true);
		expect(prompts.every((p) => p.includes("sec_1_1") && p.includes("不得直接复制英文教材标题"))).toBe(true);
	});
});

describe("AC-2 compliance self-correction", () => {
	it("feeds an English title and an internal id back once and accepts the repaired naming", async () => {
		setup("o2", 1);
		h.primary.queue.push(delegate(), submit("Complexity Analysis"), submit("讲解 sec_1_1 的内容"), submit("时间复杂度入门"));
		const res = await h.send("o2", "生成大纲");
		// MAX_NAMING_CORRECTIONS = 1: the second bad attempt exhausts it, so no outline is saved.
		expect(h.backend.savedOutlines).toHaveLength(0);
		expect(done(res)).toContain("课程大纲生成失败");
		const feedback = JSON.stringify(h.primary.requests[2]!.body.messages);
		expect(feedback).toContain("不能直接暴露英文教材标题");
	});

	it("accepts the repaired naming after exactly one correction", async () => {
		setup("o2b", 1);
		h.primary.queue.push(delegate(), submit("Complexity Analysis"), submit("时间复杂度入门"));
		const res = await h.send("o2b", "生成大纲");
		expect(h.backend.composed).toHaveLength(2);
		expect(h.backend.savedOutlines).toHaveLength(1);
		expect(done(res)).toMatch(/^课程大纲已生成/);
	});
});

describe("AC-3 all-year generation", () => {
	it("generates every course, reports progress per course, saves in one batch", async () => {
		setup("o3", 5);
		h.primary.queue.push(delegate(ALL), ...Array.from({ length: 5 }, () => submit()));
		const res = await h.send("o3", "为本年级所有课程生成大纲");
		const progress = res.frames.filter((f) => f.event === "agent_progress" && f.data.agent === "course_knowledge").map((f) => f.data.message as string);
		expect(progress).toHaveLength(5);
		expect(progress.at(-1)).toContain("（5/5）");
		expect(progress.every((m) => m.startsWith("已完成《"))).toBe(true);
		expect(h.backend.savedOutlines).toHaveLength(1);
		const ids = h.backend.savedOutlines[0]!.outlines.map((o) => o.course_id);
		expect(ids).toEqual(["year_3_course_1", "year_3_course_2", "year_3_course_3", "year_3_course_4", "year_3_course_5"]);
		expect(done(res)).toMatch(/^本年级 5 门课程的章节大纲已生成。/);
	});

	it("never runs more lanes than the configured concurrency", async () => {
		let inFlight = 0;
		let peak = 0;
		const results = await mapWithConcurrency([1, 2, 3, 4, 5], 2, async (n) => {
			inFlight += 1;
			peak = Math.max(peak, inFlight);
			await new Promise((r) => setTimeout(r, 20));
			inFlight -= 1;
			return n * 2;
		});
		expect(peak).toBe(2);
		expect(results).toEqual([2, 4, 6, 8, 10]);
	});

	it("runs wall-clock time clearly below serial", async () => {
		const started = Date.now();
		await mapWithConcurrency([1, 2, 3, 4], 2, () => new Promise((r) => setTimeout(r, 50)));
		expect(Date.now() - started).toBeLessThan(160); // serial would be >= 200
	});
});

describe("AC-4 partial success", () => {
	it("saves the courses that worked and offers to regenerate the failed one alone", async () => {
		setup("o4", 5);
		h.backend.composeAlwaysFail.add("课程5");
		// Either lane may pick up course 5; surplus submits are simply not consumed.
		h.primary.queue.push(delegate(ALL), ...Array.from({ length: 8 }, () => submit()));
		const res = await h.send("o4", "为本年级所有课程生成大纲");
		expect(h.backend.savedOutlines[0]!.outlines.map((o) => o.course_name).sort()).toEqual(["课程1", "课程2", "课程3", "课程4"]);
		const text = done(res);
		expect(text).toContain("以下课程大纲生成失败：《课程5》");
		expect(text).toContain("单独补生成《课程5》大纲");
		expect(res.frames.some((f) => f.event === "error")).toBe(false);
		const result = res.frames.find((f) => f.event === "agent_result" && f.data.agent === "course_knowledge");
		expect(result?.data.success).toBe(true);
		expect(result?.data.summary).toContain("1 门失败");
	});

	it("reports a total failure without saving anything", async () => {
		setup("o4b", 1);
		h.backend.composeAlwaysFail.add("课程1");
		h.primary.queue.push(delegate(), ...Array.from({ length: 4 }, () => submit()));
		const res = await h.send("o4b", "生成大纲");
		expect(h.backend.savedOutlines).toHaveLength(0);
		expect(done(res)).toContain("课程大纲生成失败：《课程1》");
		expect(h.backend.turns).toHaveLength(1);
	});
});

describe("AC-5 dirty-write guard", () => {
	it("a 409 from the batch save yields a clear regenerate message and no outline", async () => {
		setup("o5", 2);
		h.backend.saveConflict = true;
		h.primary.queue.push(delegate(ALL), submit(), submit());
		const res = await h.send("o5", "为本年级所有课程生成大纲");
		expect(h.backend.savedOutlines).toHaveLength(0);
		expect(done(res)).toContain("请重新生成课程大纲");
		expect(res.frames.some((f) => f.event === "session_completed")).toBe(true);
		expect(res.frames.find((f) => f.event === "session_completed")?.data.has_outline).toBe(false);
	});
});

describe("AC-6 textbook visibility gate", () => {
	it("blocks before any naming model call and shows the backend's student-facing reason", async () => {
		setup("o6", 1);
		h.backend.outlineContext = "《课程1》绑定的教材当前不可用（已下架或未发布），暂时无法生成课程大纲。";
		h.primary.queue.push(delegate());
		const res = await h.send("o6", "生成大纲");
		expect(h.primary.requests).toHaveLength(1); // only the supervisor routed
		expect(h.backend.composed).toHaveLength(0);
		expect(done(res)).toContain("教材当前不可用");
		expect(h.backend.savedOutlines).toHaveLength(0);
		expect(res.frames.some((f) => f.event === "error")).toBe(false);
	});
});
