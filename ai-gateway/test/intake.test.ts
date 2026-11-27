import { beforeEach, describe, expect, it } from "vitest";
import { catalogOf, detectRisks, validateDraftCourses } from "../src/chat/intakeContract.js";
import { toolNamesForStatus } from "../src/chat/intakeAgent.js";
import { validatePlan } from "../src/chat/pathAgent.js";
import type { TextbookContext } from "../src/backendClient.js";
import { CHAT_USER, baseContext, completeProfile, setupChatHarness } from "./chatHarness.js";

const h = setupChatHarness();
beforeEach(() => h.reset());

const TITLES = ["数据结构入门", "线性结构实践", "树与递归", "查找排序与哈希"];
const TEXTBOOKS: TextbookContext = {
	gap_id: null,
	textbooks: [
		{
			textbook_id: "tb-ds",
			title: "数据结构教材",
			outline_summary: Array.from({ length: 8 }, (_, i) => ({ section_id: `tb-ds-s${i + 1}`, title: `小节 ${i + 1}` })),
		},
	],
};

const course = (index: number, sections = [`tb-ds-s${index + 1}`]) => ({
	title: TITLES[index]!,
	purpose: `覆盖 ${TITLES[index]} 的学习边界`,
	source_textbook_id: "tb-ds",
	source_outline_section_ids: sections,
});
const toolCourses = () => TITLES.map((_, i) => course(i));

function intake(status: "draft" | "risk_pending" | "confirmed", titles = TITLES) {
	return {
		type: "learning_path_intake",
		status,
		grade_year: "year_3",
		grade_name: "大三",
		learning_topic: "数据结构",
		courses: titles.map((title, i) => ({
			title,
			purpose: `覆盖 ${title} 的学习边界`,
			source_textbook_id: "tb-ds",
			source_textbook_title: "数据结构教材",
			source_outline_section_ids: [`tb-ds-s${i + 1}`],
		})),
		recommendation_reasons: ["目标是学习数据结构"],
		user_modification_summary: "",
		risk_warnings: status === "risk_pending" ? ["替换/删除已开始学习的课程《操作系统》"] : [],
		requires_second_confirmation: status === "risk_pending",
	};
}

function ctx(sessionId: string, state: Record<string, unknown> = {}) {
	h.backend.contexts.set(
		`${CHAT_USER}:${sessionId}`,
		baseContext(sessionId, { profile: completeProfile(), has_complete_profile: true, session_state: state }),
	);
}

const delegate = { tool: "delegate_learning_path_intake", args: { reason: "课程草案" } } as const;

function spec(theme: string) {
	return {
		theme,
		semester_scope: "上学期",
		duration: "6 周",
		pace_reason: "按周推进",
		goal: `完成 ${theme}`,
		stage_titles: ["入门", "实践", "复盘"],
		key_points: ["要点一", "要点二", "要点三"],
		difficult_points: ["难点"],
		acceptance_criteria: ["能独立完成练习"],
		difficulty_level: "基础",
	};
}
const plan = (themes = TITLES) => ({
	goal_type: "项目实践",
	grade_goal: "完成数据结构主线",
	desired_outcome: "完成综合项目",
	four_year_outcome: "形成作品集",
	current_focus: "先打牢基础",
	next_action: "先完成第一门课的需求拆解",
	course_specs: themes.map(spec),
});

const patchOf = (index = 0) => h.backend.turns[index]?.turn.session_state_patch;

describe("AC-1 draft Q&A does not trigger anything", () => {
	it("answers from the draft, keeps status draft, never reaches the path node", async () => {
		ctx("s1", { learning_path_intake: intake("draft") });
		h.primary.queue.push(delegate, { text: "第 2 门是线性结构实践，排在数据结构入门之后，因为要先理解复杂度。难度中等。" });
		const res = await h.send("s1", "第 2 门课会不会太难？为什么排在这里？");
		expect(res.frames.find((f) => f.event === "message_completed")?.data.full_text).toContain("线性结构");
		expect(h.backend.turns).toHaveLength(1);
		expect(patchOf()).toBeNull();
		expect(h.backend.assembled).toHaveLength(0);
		expect(h.backend.savedPaths).toHaveLength(0);
		// Tools by state: draft offers propose + confirm only (no cancel).
		expect(h.toolNames(h.primary, 1)).toEqual(["confirm_draft", "propose_or_revise_draft"]);
		// The supervisor knows a draft exists and must route to the draft agent.
		const supervisorPrompt = h.primary.requests[0]!.body.messages[0].content as string;
		expect(supervisorPrompt).toContain("课程草案（状态 draft）");
	});

	it("tool availability follows the state machine (pure)", () => {
		expect(toolNamesForStatus("none")).toEqual(["propose_or_revise_draft"]);
		expect(toolNamesForStatus("draft")).toEqual(["propose_or_revise_draft", "confirm_draft"]);
		expect(toolNamesForStatus("risk_pending")).toEqual(["propose_or_revise_draft", "confirm_draft", "cancel_risk_revision"]);
	});
});

describe("AC-2 source binding validation and in-turn self-correction", () => {
	it("rejects a forged section id and the model repairs it within the same turn", async () => {
		ctx("s2");
		const forged = toolCourses();
		forged[1] = course(1, ["tb-ds-s99"]);
		h.backend.textbooks = TEXTBOOKS;
		h.primary.queue.push(
			delegate,
			{ tool: "propose_or_revise_draft", args: { learning_topic: "数据结构" } },
			{ tool: "propose_or_revise_draft", args: { learning_topic: "数据结构", courses: forged } },
			{ tool: "propose_or_revise_draft", args: { learning_topic: "数据结构", courses: toolCourses() } },
		);
		const res = await h.send("s2", "帮我规划数据结构学习路径");
		expect(res.frames.some((f) => f.event === "error")).toBe(false);
		// The validator's concrete complaint was fed back to the model.
		const feedback = JSON.stringify(h.primary.requests[3]!.body.messages);
		expect(feedback).toContain("tb-ds-s99");
		expect(feedback).toContain("不存在的小节");
		const saved = patchOf()?.learning_path_intake as any;
		expect(saved.status).toBe("draft");
		expect(saved.courses[1].source_outline_section_ids).toEqual(["tb-ds-s2"]);
		expect(saved.courses.every((c: any) => c.source_textbook_title === "数据结构教材")).toBe(true);
		expect(h.backend.textbookLookups).toEqual(["数据结构"]);
		expect(res.frames.find((f) => f.event === "message_completed")?.data.full_text).toContain("课程草稿：");
	});

	it("gives up after the correction budget without storing an invalid draft", async () => {
		ctx("s2b");
		const forged = toolCourses();
		forged[0] = course(0, ["nope"]);
		h.backend.textbooks = TEXTBOOKS;
		const bad = { tool: "propose_or_revise_draft", args: { learning_topic: "数据结构", courses: forged } } as const;
		h.primary.queue.push(delegate, { tool: "propose_or_revise_draft", args: { learning_topic: "数据结构" } }, bad, bad, bad);
		const res = await h.send("s2b", "规划数据结构");
		expect(patchOf()).toBeNull();
		expect(res.frames.find((f) => f.event === "message_completed")?.data.full_text).toContain("课程草案生成失败");
	});

	it("validator unit: count, unknown textbook, unchanged existing binding is trusted", () => {
		const catalog = catalogOf(TEXTBOOKS);
		expect(validateDraftCourses(toolCourses().slice(0, 3), catalog, []).errors.join()).toContain("4-8");
		const alien = toolCourses();
		alien[0] = { ...course(0), source_textbook_id: "tb-ghost" };
		expect(validateDraftCourses(alien, catalog, []).errors.join()).toContain("tb-ghost");
		const old = intake("draft").courses;
		const kept = toolCourses();
		kept[0] = { ...course(0), source_textbook_id: "tb-old", source_outline_section_ids: ["old-1"] };
		const trusted = [{ ...old[0]!, source_textbook_id: "tb-old", source_textbook_title: "旧教材", source_outline_section_ids: ["old-1"] }];
		expect(validateDraftCourses(kept, catalog, trusted).errors).toEqual([]);
	});
});

describe("AC-3 knowledge gap keeps the existing draft", () => {
	it("records the gap, leaves the draft untouched and says so", async () => {
		ctx("s3", { learning_path_intake: intake("draft") });
		h.backend.textbooks = { textbooks: [], gap_id: "gap-quantum" };
		h.primary.queue.push(delegate, {
			tool: "propose_or_revise_draft",
			args: { learning_topic: "数据结构", search_topic: "量子力学" },
		});
		const res = await h.send("s3", "把第 3 门换成量子力学");
		expect(h.backend.textbookLookups).toEqual(["量子力学"]);
		expect(patchOf()).toBeNull();
		const text = res.frames.find((f) => f.event === "message_completed")?.data.full_text as string;
		expect(text).toContain("暂无覆盖「量子力学」的已发布教材");
		expect(text).toContain("原有的课程草稿已为你保留");
		expect(res.frames.find((f) => f.data.update_type === "knowledge_gap_recorded")?.data.gap_id).toBe("gap-quantum");
	});

	it("first-time planning with no textbook guides to another direction", async () => {
		ctx("s3b");
		h.backend.textbooks = { textbooks: [], gap_id: "gap-2" };
		h.primary.queue.push(delegate, { tool: "propose_or_revise_draft", args: { learning_topic: "量子力学" } });
		const res = await h.send("s3b", "我想学量子力学");
		expect(res.frames.find((f) => f.event === "message_completed")?.data.full_text).toContain("换一个学习方向");
		expect(patchOf()).toBeNull();
	});
});

describe("AC-4 risk second confirmation and rollback", () => {
	const protectedOs = [{ title: "操作系统", reason: "已开始学习" }];

	it("a draft that drops a started course becomes risk_pending; cancel rolls back; confirm proceeds", async () => {
		h.backend.protectedCourses = protectedOs;
		h.backend.textbooks = TEXTBOOKS;
		// Turn 1: modification that does not include 操作系统.
		ctx("s4", { learning_path_intake: intake("draft") });
		h.primary.queue.push(
			delegate,
			{ tool: "propose_or_revise_draft", args: { learning_topic: "数据结构", courses: toolCourses(), user_modification_summary: "删掉操作系统" } },
		);
		const t1 = await h.send("s4", "把操作系统删掉");
		const risky = patchOf(0)?.learning_path_intake as any;
		expect(risky.status).toBe("risk_pending");
		expect(risky.requires_second_confirmation).toBe(true);
		expect(risky.risk_warnings).toEqual(["替换/删除已开始学习的课程《操作系统》"]);
		expect(t1.frames.find((f) => f.event === "message_completed")?.data.full_text).toContain("风险提示");

		// Turn 2: change of heart -> back to a plain draft, no path written.
		ctx("s4", { learning_path_intake: risky });
		h.primary.queue.push(delegate, { tool: "cancel_risk_revision", args: {} });
		await h.send("s4", "算了先不改");
		expect(h.toolNames(h.primary, 3)).toEqual(["cancel_risk_revision", "confirm_draft", "propose_or_revise_draft"]);
		const rolled = patchOf(1)?.learning_path_intake as any;
		expect(rolled.status).toBe("draft");
		expect(rolled.risk_warnings).toEqual([]);
		expect(rolled.requires_second_confirmation).toBe(false);
		expect(h.backend.savedPaths).toHaveLength(0);

		// Turn 3: the user insists -> confirm overrides and the path is generated in the same turn.
		ctx("s4", { learning_path_intake: risky });
		h.primary.queue.push(delegate, { tool: "confirm_draft", args: {} }, { tool: "submit_learning_path_plan", args: plan() });
		const t3 = await h.send("s4", "确认覆盖");
		expect(h.backend.savedPaths).toHaveLength(1);
		expect(t3.frames.find((f) => f.event === "message_completed")?.data.full_text).toMatch(/^学习路径已生成/);
	});

	it("risk detection unit: only dropped protected courses are reported", () => {
		const courses = intake("draft").courses;
		expect(detectRisks(courses, [{ title: "线性结构实践", reason: "已有课程大纲" }])).toEqual([]);
		expect(detectRisks(courses, [{ title: "编译原理", reason: "已有课程大纲" }])).toEqual([
			"替换/删除已有课程大纲的课程《编译原理》",
		]);
	});
});

describe("AC-5 confirm flows into the path node in one request", () => {
	it("one SSE: draft node result, path node start, saved path, summary starts with 学习路径已生成", async () => {
		ctx("s5", { learning_path_intake: intake("draft") });
		h.primary.queue.push(delegate, { tool: "confirm_draft", args: {} }, { tool: "submit_learning_path_plan", args: plan() });
		const res = await h.send("s5", "可以，按这个生成吧");
		const events = res.frames.map((f) => `${f.event}:${String(f.data.agent ?? "")}`);
		const draftDone = events.indexOf("agent_result:learning_path_intake");
		const pathStart = events.indexOf("agent_calling:learning_path_agent");
		expect(draftDone).toBeGreaterThan(-1);
		expect(pathStart).toBeGreaterThan(draftDone);

		expect(h.backend.savedPaths).toHaveLength(1);
		const saved = h.backend.savedPaths[0]!;
		expect(saved.gradeYear).toBe("year_3");
		const nodes = (saved.path.grade_plans as any).year_3.course_nodes;
		expect(nodes.map((n: any) => n.course_or_chapter_theme)).toEqual(TITLES);
		// Persist after the path is saved, and the consumed draft is cleared.
		expect(h.backend.order.indexOf("save_path")).toBeLessThan(h.backend.order.indexOf("persist"));
		expect(patchOf()).toEqual({ learning_path_intake: null });
		const done = res.frames.at(-1)!;
		expect(done.event).toBe("session_completed");
		expect(done.data.has_paths).toBe(true);
		expect(res.frames.find((f) => f.event === "message_completed")?.data.full_text).toMatch(/^学习路径已生成/);
		// The assembler received the draft's courses verbatim (titles + bindings).
		expect(h.backend.assembled[0]!.plan.course_specs).toHaveLength(4);
	});

	it("a plan with the wrong course count is repaired once; a second failure is a retryable error and keeps the draft", async () => {
		ctx("s5b", { learning_path_intake: intake("draft") });
		h.primary.queue.push(
			delegate,
			{ tool: "confirm_draft", args: {} },
			{ tool: "submit_learning_path_plan", args: plan(TITLES.slice(0, 3)) },
			{ tool: "submit_learning_path_plan", args: plan() },
		);
		const ok = await h.send("s5b", "确认");
		expect(h.backend.savedPaths).toHaveLength(1);
		expect(JSON.stringify(h.primary.requests[3]!.body.messages)).toContain("必须与已确认课程草案一致");
		expect(ok.frames.some((f) => f.event === "error")).toBe(false);

		h.reset();
		ctx("s5c", { learning_path_intake: intake("draft") });
		h.backend.assembleFailures.push("学习路径规划无法装配：A", "学习路径规划无法装配：B");
		h.primary.queue.push(
			delegate,
			{ tool: "confirm_draft", args: {} },
			{ tool: "submit_learning_path_plan", args: plan() },
			{ tool: "submit_learning_path_plan", args: plan() },
		);
		const bad = await h.send("s5c", "确认");
		expect(h.backend.savedPaths).toHaveLength(0);
		const error = bad.frames.find((f) => f.event === "error")!;
		expect(error.data).toMatchObject({ retryable: true, retryAction: "retry_learning_path" });
		// The user turn is persisted and the confirmed draft survives for a retry.
		expect((patchOf()?.learning_path_intake as any).status).toBe("confirmed");
		expect(bad.frames.some((f) => f.event === "message_completed")).toBe(false);
	});

	it("plan validation unit", () => {
		const draft = intake("draft") as any;
		expect(validatePlan(plan(), draft)).toEqual([]);
		expect(validatePlan(plan(TITLES.slice(0, 3)), draft).join()).toContain("一致");
		const thin = plan();
		thin.course_specs[0]!.key_points = ["一"];
		expect(validatePlan(thin, draft).join()).toContain("key_points");
	});
});

describe("AC-6 existing progress is carried into the refreshed path", () => {
	it("sends the snapshot to the model and lands on the next course", async () => {
		ctx("s6", { learning_path_intake: intake("draft") });
		h.backend.snapshots = [
			{
				grade_year: "year_3",
				total_courses: 4,
				completed_courses: 1,
				current_course_id: "year_3_course_1",
				current_progress_state: "completed",
				next_course_id: "year_3_course_2",
			},
		];
		h.primary.queue.push(delegate, { tool: "confirm_draft", args: {} }, { tool: "submit_learning_path_plan", args: plan() });
		await h.send("s6", "确认");
		const pathPrompt = h.primary.requests[2]!.body.messages[0].content as string;
		expect(pathPrompt).toContain("year_3：共 4 门课程，已完成 1 门");
		const current = h.backend.savedPaths[0]!.path.current_learning_course as any;
		expect(current.course_node_id).toBe("year_3_course_2");
	});
});
