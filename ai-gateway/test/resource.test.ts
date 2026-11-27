import { beforeEach, describe, expect, it } from "vitest";
import { parseLeafResourceRequest } from "../src/chat/resourceAgent.js";
import { CHAT_USER, pathContext, setupChatHarness } from "./chatHarness.js";

const h = setupChatHarness();
beforeEach(() => {
	h.reset();
	h.primary.respond = undefined;
});

const DOC = "## 学习目标\n- 能解释概念\n\n## 核心概念\n正文";
const HTML = "<div class='section-animation'>demo</div>";

/** Answers each model call by the tool it was offered, so parallel calls stay deterministic. */
function scriptModel(opts: { badMarkdownFirst?: number; markdown?: (sid: string) => string } = {}) {
	let bad = opts.badMarkdownFirst ?? 0;
	h.primary.respond = (body) => {
		const names = (body.tools ?? []).map((t: any) => t.function.name as string);
		const prompt = String(body.messages?.[0]?.content ?? "");
		if (names.includes("submit_section_markdown")) {
			if (bad > 0) {
				bad -= 1;
				return { tool: "submit_section_markdown", args: { markdown: "只有一句话" } };
			}
			const sid = /小节 ([\d.]+)/.exec(JSON.stringify(body.messages))?.[1] ?? "?";
			return { tool: "submit_section_markdown", args: { markdown: opts.markdown?.(sid) ?? DOC } };
		}
		if (names.includes("submit_section_animations")) {
			return { tool: "submit_section_animations", args: { animations: [{ animation_id: "anim_1", title: "演示", html: HTML }] } };
		}
		if (names.includes("delegate_course_resources")) {
			return { tool: "delegate_course_resources", args: { chapter_section_id: "1", reason: "生成章节内容" } };
		}
		return { text: `（未预期的调用：${prompt.slice(0, 20)}）` };
	};
}

const BUTTON = (mode = "generate") =>
	`帮我生成《课程》第一章的教学内容。\n\n[LEAF_RESOURCE_GENERATION]\ncourse_node_id: course-os\nchapter_section_id: 1\nscope: chapter_sections\nmode: ${mode}\n[/LEAF_RESOURCE_GENERATION]\n\n要求：生成这一章所有叶子小节。`;

function setup(sessionId: string, state: Record<string, unknown> = {}) {
	h.backend.contexts.set(`${CHAT_USER}:${sessionId}`, { ...pathContext(sessionId, true), session_state: state });
}
const completed = (res: Awaited<ReturnType<typeof h.send>>) => res.frames.find((f) => f.event === "message_completed")?.data.full_text as string;
const sectionEvents = (res: Awaited<ReturnType<typeof h.send>>, phase: string, section: string) =>
	res.frames.filter((f) => f.data.phase === phase && f.data.section_id === section);

describe("request protocol", () => {
	it("parses the explicit block and ignores plain text", () => {
		expect(parseLeafResourceRequest(BUTTON("regenerate"))).toEqual({
			courseNodeId: "course-os",
			chapterSectionId: "1",
			scope: "chapter_sections",
			mode: "regenerate",
		});
		expect(parseLeafResourceRequest("帮我生成第一章内容")).toBeNull();
		expect(parseLeafResourceRequest("[LEAF_RESOURCE_GENERATION]\ncourse_node_id: x\n[/LEAF_RESOURCE_GENERATION]")).toBeNull();
	});
});

describe("AC-1 one subgraph for both entries", () => {
	it("the button protocol skips the supervisor and emits events the leaf page consumes", async () => {
		setup("r1");
		scriptModel();
		const res = await h.send("r1", BUTTON());
		expect(res.frames.some((f) => f.event === "supervisor_plan")).toBe(false);
		const compose = sectionEvents(res, "compose", "1.1").find((f) => f.event === "agent_result");
		expect(compose?.data).toMatchObject({
			course_id: "course-os",
			chapter_section_id: "1",
			section_id: "1.1",
			kind: "course_resource_section",
			status: "completed",
			success: true,
		});
		expect(completed(res)).toBe("本章教学内容已生成。");
		expect(h.backend.turns).toHaveLength(1);
		expect(h.backend.resource.saves.filter((s) => s.phase === "compose")).toHaveLength(3);
	});

	it("natural language reaches the same node through the supervisor tool", async () => {
		setup("r1b");
		scriptModel();
		const res = await h.send("r1b", "生成第一章教学内容");
		expect(res.frames.find((f) => f.event === "supervisor_plan")?.data).toMatchObject({ agent: "course_resources" });
		expect(h.backend.resource.prepares).toEqual([{ chapterRef: "1", mode: "generate" }]);
		expect(sectionEvents(res, "compose", "1.3").some((f) => f.data.success === true)).toBe(true);
		expect(completed(res)).toBe("本章教学内容已生成。");
	});
});

describe("AC-2 parallel video and animation, readable as soon as a section is done", () => {
	it("overlaps the two branches inside a section and composes the first section before the chapter ends", async () => {
		setup("r2");
		scriptModel();
		h.backend.resource.markdownDelayMs = { "1.2": 150 };
		h.backend.resource.videoDelayMs = 80;
		const res = await h.send("r2", BUTTON());
		const video = h.backend.resource.videoSpans.find((s) => s.sectionId === "1.1")!;
		const animation = h.backend.resource.animationSpans.find((s) => s.sectionId === "1.1")!;
		expect(video.start).toBeLessThan(animation.end);
		expect(animation.start).toBeLessThan(video.end);
		const firstCompose = h.backend.resource.saves.find((s) => s.phase === "compose" && s.sectionId === "1.1")!;
		const secondMarkdown = h.backend.resource.saves.find((s) => s.phase === "markdown" && s.sectionId === "1.2")!;
		expect(firstCompose.at).toBeLessThanOrEqual(secondMarkdown.at);
		const names = res.frames.map((f) => f.event);
		expect(names.indexOf("message_completed")).toBeGreaterThan(res.frames.findIndex((f) => f.data.phase === "compose" && f.data.section_id === "1.1"));
	});
});

describe("AC-3 checkpoint resume", () => {
	it("re-running after an animation failure only redoes the failed section's animation and compose", async () => {
		setup("r3");
		scriptModel();
		h.backend.resource.animationBroken.add("1.2");
		const first = await h.send("r3", BUTTON());
		expect(completed(first)).toContain("小节 1.2 生成失败");
		expect(h.backend.resource.finishes[0]!.succeeded.sort()).toEqual(["1.1", "1.3"]);
		const failedSave = h.backend.resource.saves.find((s) => s.sectionId === "1.2" && s.failure);
		expect(failedSave?.phase).toBe("animation");

		h.backend.resource.animationBroken.clear();
		h.backend.resource.saves.length = 0;
		const modelCallsBefore = h.primary.requests.length;
		const second = await h.send("r3", BUTTON());
		expect(completed(second)).toBe("本章教学内容已生成。");
		const phases = h.backend.resource.saves.map((s) => `${s.sectionId}:${s.phase}`).sort();
		// 1.1 and 1.3 only re-compose (cheap, deterministic); 1.2 redoes animation + compose.
		expect(phases).toEqual(["1.1:compose", "1.2:animation", "1.2:compose", "1.3:compose"]);
		const secondCalls = h.primary.requests.slice(modelCallsBefore);
		expect(secondCalls).toHaveLength(1);
		expect(secondCalls[0]!.body.tools.map((t: any) => t.function.name)).toEqual(["submit_section_animations"]);
		const reused = sectionEvents(second, "markdown", "1.1").find((f) => f.event === "agent_result");
		expect(reused?.data.message).toContain("直接复用");
	});

	it("a regenerate request ignores checkpoints and runs every phase with the focus", async () => {
		setup("r3b");
		scriptModel();
		h.backend.resource.checkpoints.set("1.1", { markdown: "completed", video: "completed", animation: "completed", compose: "completed" });
		await h.send("r3b", BUTTON("regenerate"));
		expect(h.backend.resource.saves.filter((s) => s.sectionId === "1.1").map((s) => s.phase).sort()).toEqual(["animation", "compose", "markdown", "video"]);
	});
});

describe("AC-4 video degradation", () => {
	it("no qualified video: text and animation still land and the section is composed", async () => {
		setup("r4");
		scriptModel();
		h.backend.resource.videoMode = "unavailable";
		const res = await h.send("r4", BUTTON());
		const event = sectionEvents(res, "video", "1.1").find((f) => f.event === "agent_result");
		expect(event?.data).toMatchObject({ video_unavailable: true, status: "completed" });
		expect(String(event?.data.message)).toContain("暂未找到合适教学视频");
		expect(res.frames.some((f) => f.event === "error")).toBe(false);
		expect(completed(res)).toBe("本章教学内容已生成。");
		expect(h.backend.resource.saves.filter((s) => s.phase === "compose")).toHaveLength(3);
	});

	it("an exploding video source degrades the same way", async () => {
		setup("r4b");
		scriptModel();
		h.backend.resource.videoMode = "throws";
		const res = await h.send("r4b", BUTTON());
		expect(completed(res)).toBe("本章教学内容已生成。");
		expect(h.backend.resource.saves.some((s) => s.phase === "video")).toBe(false);
	});
});

describe("markdown and animation self-correction", () => {
	it("feeds the validator's issue back and accepts the repaired document", async () => {
		setup("r4c");
		scriptModel({ badMarkdownFirst: 1 });
		h.backend.resource.sections = ["1.1"];
		const res = await h.send("r4c", BUTTON());
		expect(completed(res)).toBe("本章教学内容已生成。");
		const feedback = JSON.stringify(h.primary.requests.find((r) => JSON.stringify(r.body.messages).includes("缺少“学习目标”标题"))?.body.messages);
		expect(feedback).toContain("缺少“学习目标”标题");
		expect(h.backend.resource.validations).toHaveLength(2);
	});

	it("gives up on a document after the correction budget and records the section as failed", async () => {
		setup("r4d");
		scriptModel({ badMarkdownFirst: 10 });
		h.backend.resource.sections = ["1.1"];
		const res = await h.send("r4d", BUTTON());
		expect(res.frames.find((f) => f.event === "error")?.data).toMatchObject({ kind: "course_resource_chapter", status: "error", retryable: false });
		expect(h.backend.resource.saves.find((s) => s.failure)?.phase).toBe("markdown");
		expect(h.backend.resource.finishes).toHaveLength(1);
	});

	it("falls back to the template animation when the model's animation cannot be repaired", async () => {
		setup("r4e");
		scriptModel();
		h.backend.resource.sections = ["1.1"];
		h.backend.resource.animationNeedsTemplate.add("1.1");
		const res = await h.send("r4e", BUTTON());
		expect(completed(res)).toBe("本章教学内容已生成。");
		const done = sectionEvents(res, "animation", "1.1").find((f) => f.event === "agent_result");
		expect(String(done?.data.message)).toContain("模板");
	});
});

describe("AC-5 explicit regeneration focus", () => {
	it("asks for a focus, stores it structurally (no hidden tag), then uses and clears it", async () => {
		setup("r5");
		scriptModel();
		h.backend.resource.prepareOverride = { status: "needs_focus", chapter_section_id: "1" };
		const ask = await h.send("r5", BUTTON("generate"));
		expect(completed(ask)).toBe("重新生成本章前，请告诉我下一版需要侧重哪里。");
		expect(completed(ask)).not.toContain("LEAF_REGEN_PENDING");
		const patch = h.backend.turns[0]!.turn.session_state_patch as any;
		expect(patch.pending_leaf_regeneration).toMatchObject({ course_node_id: "course-os", chapter_section_id: "1" });
		expect(patch.pending_leaf_regeneration.requested_at).toBeTruthy();
		expect(h.backend.resource.saves).toHaveLength(0);
		expect(h.backend.resource.locked).toBe(false);

		// Next turn: the answer is the focus; no supervisor call, mode regenerate.
		h.backend.resource.prepareOverride = null;
		setup("r5b", { pending_leaf_regeneration: patch.pending_leaf_regeneration });
		const res = await h.send("r5b", "多讲一些复杂度的例题");
		expect(res.frames.some((f) => f.event === "supervisor_plan")).toBe(false);
		expect(h.backend.resource.prepares.at(-1)).toEqual({ chapterRef: "1", mode: "regenerate" });
		expect(h.backend.resource.markdownFocus.every((f) => f === "多讲一些复杂度的例题")).toBe(true);
		const clear = h.backend.turns.at(-1)!.turn.session_state_patch as any;
		expect(clear).toEqual({ pending_leaf_regeneration: null });
	});
});

describe("AC-6 chapter lock", () => {
	it("a second request while one is running is refused, and the lock is free afterwards", async () => {
		setup("r6");
		setup("r6b");
		scriptModel();
		h.backend.resource.videoDelayMs = 120;
		const [first, second] = await Promise.all([h.send("r6", BUTTON()), (async () => {
			await new Promise((r) => setTimeout(r, 30));
			return h.send("r6b", BUTTON());
		})()]);
		expect(completed(first)).toBe("本章教学内容已生成。");
		const refusal = second.frames.find((f) => f.event === "error");
		expect(refusal?.data).toMatchObject({ message: "这一章正在生成。", kind: "course_resource_chapter", status: "error" });
		expect(h.backend.resource.locked).toBe(false);
		setup("r6c");
		expect(completed(await h.send("r6c", BUTTON()))).toBe("本章教学内容已生成。");
	});

	it("releases the lock when a section blows up mid-way", async () => {
		setup("r6d");
		scriptModel();
		h.backend.resource.failSaveOf = { sectionId: "1.2", phase: "compose" };
		const res = await h.send("r6d", BUTTON());
		expect(completed(res)).toContain("小节 1.2 生成失败");
		expect(h.backend.resource.locked).toBe(false);
		expect(h.backend.resource.finishes).toHaveLength(1);
		h.backend.resource.failSaveOf = null;
		setup("r6e");
		expect(completed(await h.send("r6e", BUTTON()))).toBe("本章教学内容已生成。");
	});

	it("gate refusals are plain replies, not errors, and take no lock", async () => {
		setup("r6f");
		scriptModel();
		h.backend.resource.prepareOverride = { status: "refused", message: "只能为当前课程生成教学内容。" };
		const res = await h.send("r6f", BUTTON());
		expect(completed(res)).toBe("只能为当前课程生成教学内容。");
		expect(res.frames.some((f) => f.event === "error")).toBe(false);
		expect(h.backend.resource.finishes).toHaveLength(0);
	});
});
