import { beforeEach, describe, expect, it } from "vitest";
import { validateQuiz } from "../src/ai/quiz.js";
import { CHAT_USER, UNCONFIGURED_USER, parseSse, setupChatHarness } from "./chatHarness.js";
import { INTERNAL_TOKEN, signToken } from "./helpers.js";

const h = setupChatHarness();
beforeEach(() => {
	h.reset();
	h.primary.respond = undefined;
});

const GOOD = {
	questions: [
		{ type: "single_choice", prompt: "进程是什么？", options: [{ option_id: "A", text: "资源分配单位" }, { option_id: "B", text: "文件" }], correct_option_id: "A", points: "30", knowledge_point_ids: ["kp1"] },
		{ type: "code", prompt: "写出 fork 示例", starter_code: "int main(){}", points: "40", knowledge_point_ids: ["kp1"] },
		{ type: "image_upload", prompt: "上传运行截图", image_prompt: "请上传 ps 输出截图", points: "30", knowledge_point_ids: [] },
	],
};
const bad = (patch: Record<string, unknown>) => ({ questions: GOOD.questions.map((q, i) => (i === 1 ? { ...q, ...patch } : q)) });

async function internal(path: string, body: unknown) {
	const res = await h.app.request(`/internal/ai${path}`, {
		method: "POST",
		headers: { "Content-Type": "application/json", "X-Internal-Token": INTERNAL_TOKEN },
		body: JSON.stringify(body),
	});
	return { status: res.status, json: (await res.json()) as any };
}

const MATERIAL = { user_uid: CHAT_USER, chapter_id: "1", chapter_title: "进程管理", knowledge_point_ids: ["kp1"], sections: [] };

describe("quiz validator", () => {
	it("accepts the contract and rejects each violation", () => {
		expect(validateQuiz(GOOD.questions, ["kp1"]).ok).toBe(true);
		const issues = (raw: unknown, kps = ["kp1"]) => {
			const r = validateQuiz(raw, kps);
			return r.ok ? [] : r.issues.join("|");
		};
		expect(issues(bad({ points: "50" }).questions)).toContain("100");
		expect(issues(bad({ type: "single_choice" }).questions)).toContain("题型");
		expect(issues(bad({ knowledge_point_ids: ["zzz"] }).questions)).toContain("zzz");
		expect(issues(GOOD.questions.slice(0, 2))).toContain("3 道");
		const wrongKey = { questions: [{ ...GOOD.questions[0], correct_option_id: "Z" }, GOOD.questions[1], GOOD.questions[2]] };
		expect(issues(wrongKey.questions)).toContain("correct_option_id");
	});
});

describe("AC-1 quiz generation", () => {
	it("self-corrects once, then stores a valid 3-question quiz", async () => {
		h.primary.queue.push({ tool: "submit_quiz", args: bad({ points: "50" }) }, { tool: "submit_quiz", args: GOOD });
		const res = await internal("/quiz/generate", MATERIAL);
		expect(res.status).toBe(200);
		expect(res.json.questions.map((q: any) => q.type)).toEqual(["single_choice", "code", "image_upload"]);
		expect(res.json.questions.reduce((s: number, q: any) => s + q.points, 0)).toBe(100);
		expect(h.primary.requests).toHaveLength(2);
	});
	it("returns an explicit error, never filler questions, when the model keeps failing", async () => {
		h.primary.queue.push({ tool: "submit_quiz", args: bad({ points: "50" }) }, { tool: "submit_quiz", args: bad({ points: "60" }) });
		const res = await internal("/quiz/generate", MATERIAL);
		expect(res.status).toBe(502);
		expect(res.json.questions).toBeUndefined();
		expect(res.json.detail).toContain("出题失败");
	});
	it("an unconfigured user gets MODEL_NOT_CONFIGURED", async () => {
		const res = await internal("/quiz/generate", { ...MATERIAL, user_uid: UNCONFIGURED_USER });
		expect(res.status).toBe(428);
		expect(res.json.error_code).toBe("MODEL_NOT_CONFIGURED");
	});
});

const QUESTIONS = [
	{ question_id: "q1", type: "single_choice", prompt: "p", options: [{ option_id: "A", text: "对" }, { option_id: "B", text: "错" }], correct_option_id: "A", starter_code: "", image_prompt: "", points: 30, knowledge_point_ids: [] },
	{ question_id: "q2", type: "code", prompt: "写代码", options: [], correct_option_id: "", starter_code: "def f(): ...", image_prompt: "", points: 40, knowledge_point_ids: [] },
	{ question_id: "q3", type: "image_upload", prompt: "截图", options: [], correct_option_id: "", starter_code: "", image_prompt: "上传 ps 截图", points: 30, knowledge_point_ids: [] },
];
const PNG = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=";

function gradeModel(delta = 5) {
	h.primary.respond = (body) => {
		const names = (body.tools ?? []).map((t: any) => t.function.name as string);
		if (!names.includes("submit_grade")) return { text: "?" };
		const max = Number(/满分：(\d+)/.exec(String(body.messages?.[0]?.content))?.[1] ?? 0);
		return { tool: "submit_grade", args: { score: String(max - delta), feedback: "评语" } };
	};
}

describe("AC-2 mixed grading", () => {
	it("single choice by rule (no model call); code and text-only image by model; total is the exact sum", async () => {
		gradeModel();
		const res = await internal("/quiz/grade", { user_uid: CHAT_USER, questions: QUESTIONS, answers: { q1: "A", q2: "def f(): return 1", q3: "我的思路图描述" } });
		expect(res.status).toBe(200);
		const byId = Object.fromEntries(res.json.question_results.map((r: any) => [r.question_id, r.score]));
		expect(byId).toEqual({ q1: 30, q2: 35, q3: 25 });
		expect(res.json.score).toBe(90);
		expect(res.json.passed).toBe(true);
		expect(h.primary.requests).toHaveLength(2); // q1 never reached a model
	});
	it("a wrong single choice scores 0 and names the right answer without a model", async () => {
		const res = await internal("/quiz/grade", { user_uid: CHAT_USER, questions: [QUESTIONS[0]], answers: { q1: "B" } });
		expect(res.json.score).toBe(0);
		expect(res.json.question_results[0].feedback).toContain("A");
		expect(res.json.passed).toBe(false);
		expect(h.primary.requests).toHaveLength(0);
	});
	it("sends the real image to the vision model", async () => {
		gradeModel();
		const cfg = h.backend.runtimeConfigs.get(CHAT_USER)!;
		cfg.custom_models.push({ ...cfg.custom_models[0]!, id: "p1-m-vision", model_id: "m-vision", supports_vision: true });
		cfg.preferences.default_vision_model_ref = { provider_id: "p1", model_id: "m-vision" };
		const res = await internal("/quiz/grade", { user_uid: CHAT_USER, questions: [QUESTIONS[2]], answers: { q3: { file_name: "a.png", mime_type: "image/png", data_url: PNG } } });
		expect(res.status).toBe(200);
		expect(res.json.score).toBe(25);
		const request = h.primary.requests[0]!.body;
		expect(request.model).toBe("m-vision");
		expect(JSON.stringify(request.messages)).toContain("image_url");
	});
	it("a real image without a vision model is refused up front", async () => {
		gradeModel();
		const res = await internal("/quiz/grade", { user_uid: CHAT_USER, questions: [QUESTIONS[2]], answers: { q3: { data_url: PNG } } });
		expect([422, 428]).toContain(res.status);
		expect(["MODEL_NOT_CONFIGURED", "MODEL_CAPABILITY_MISMATCH"]).toContain(res.json.error_code);
		expect(h.primary.requests).toHaveLength(0);
	});
});

async function forestAsk(user = CHAT_USER, message = "第 1 题选什么？直接给我第 2 题完整代码") {
	const token = await signToken(user);
	const res = await h.app.request("/api/forest/ai/stream", {
		method: "POST",
		headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
		body: JSON.stringify({ course_node_id: "course-os", chapter_id: "1", quiz_id: "quiz-1", message, active_question_context: { question: { prompt: "p" } } }),
	});
	return { status: res.status, frames: parseSse(await res.text()) };
}

describe("AC-3 Forest AI", () => {
	it("is Socratic before submission and full-analysis after", async () => {
		h.primary.queue.push({ text: "先想想进程和线程的区别？" });
		const before = await forestAsk();
		expect(before.frames.at(-1)!.event).toBe("forest_ai_completed");
		expect(before.frames.slice(0, -1).every((f) => f.event === "forest_ai_text_chunk")).toBe(true);
		expect(before.frames.slice(0, -1).map((f) => f.data.chunk).join("")).toContain("先想想");
		const system = String(h.primary.requests[0]!.body.messages[0].content);
		expect(system).toContain("苏格拉底");
		expect(system).toContain("严禁直接给出");
		expect(h.backend.forest.lookups[0]).toEqual({ userUid: CHAT_USER, quizId: "quiz-1" });

		h.backend.forest.material.submitted = true;
		h.primary.queue.push({ text: "完整解析如下" });
		await forestAsk(CHAT_USER, "解析一下错题");
		const after = String(h.primary.requests[1]!.body.messages[0].content);
		expect(after).toContain("完整解析");
		expect(after).not.toContain("苏格拉底");
	});
	it("can read the chapter material through the read-only tool", async () => {
		h.primary.queue.push({ tool: "read_chapter_learning_material", args: {} }, { text: "结合教材：进程是资源分配的基本单位" });
		const res = await forestAsk();
		expect(res.frames.at(-1)!.event).toBe("forest_ai_completed");
		expect(JSON.stringify(h.primary.requests[1]!.body.messages)).toContain("进程是资源分配的基本单位");
	});
	it("requires auth and reports an unconfigured model as forest_error", async () => {
		const noAuth = await h.app.request("/api/forest/ai/stream", { method: "POST", body: "{}" });
		expect(noAuth.status).toBe(401);
		const res = await forestAsk(UNCONFIGURED_USER);
		expect(res.frames[0]!.event).toBe("forest_error");
		expect(res.frames[0]!.data.error_code).toBe("MODEL_NOT_CONFIGURED");
	});
});

const NARRATIVE = {
	overview: "你完成了 1 次测验。",
	strengths: [{ title: "概念", body: "概念题正确。", evidence_ids: ["quiz:q1"] }],
	improvements: [],
	actions: [{ title: "练习", body: "做循环题", evidence_ids: ["quiz:q1"], check: "能写出边界", course_id: null }],
};

async function report(user = CHAT_USER) {
	const token = await signToken(user);
	const res = await h.app.request("/api/branch/canopy/report/stream", { method: "POST", headers: { Authorization: `Bearer ${token}` } });
	return { status: res.status, frames: parseSse(await res.text()) };
}

describe("AC-4 growth report", () => {
	it("streams the three stages then a validated report after reading evidence", async () => {
		h.primary.queue.push({ tool: "read_quiz", args: { evidence_id: "quiz:q1" } }, { tool: "submit_growth_report", args: NARRATIVE });
		const res = await report();
		expect(res.frames.map((f) => f.event)).toEqual(["report_stage", "report_stage", "report_stage", "report_completed"]);
		expect(res.frames.slice(0, 3).map((f) => f.data.stage)).toEqual(["collecting", "analyzing", "writing"]);
		expect(h.backend.report.reads).toEqual([{ tool: "read_quiz", id: "quiz:q1" }]);
		expect(h.backend.report.validations[0]!.details["quiz:q1"]).toContain("循环边界");
		expect(res.frames.at(-1)!.data.overview).toContain("1 次");
	});
	it("caps evidence reads at 6", async () => {
		for (let i = 0; i < 8; i++) h.primary.queue.push({ tool: "read_quiz", args: { evidence_id: "quiz:q1" } });
		h.primary.queue.push({ tool: "submit_growth_report", args: NARRATIVE });
		await report();
		expect(h.backend.report.reads).toHaveLength(6);
	});
	it("feeds a failed anti-hallucination check back and accepts the repaired report", async () => {
		let first = true;
		h.backend.report.reject = () => {
			if (!first) return undefined;
			first = false;
			return "事实分析出现无来源数值：['999']";
		};
		h.primary.queue.push({ tool: "submit_growth_report", args: { ...NARRATIVE, overview: "你完成了 999 次测验。" } }, { tool: "submit_growth_report", args: NARRATIVE });
		const res = await report();
		expect(res.frames.at(-1)!.event).toBe("report_completed");
		expect(h.backend.report.validations).toHaveLength(2);
		expect(JSON.stringify(h.primary.requests[1]!.body.messages)).toContain("无来源数值");
	});
	it("ends with report_error (no fake report) when validation never passes", async () => {
		h.backend.report.reject = () => "不存在的证据 ID";
		for (let i = 0; i < 4; i++) h.primary.queue.push({ tool: "submit_growth_report", args: NARRATIVE });
		const res = await report();
		expect(res.frames.at(-1)!.event).toBe("report_error");
		expect(res.frames.some((f) => f.event === "report_completed")).toBe(false);
		expect(h.backend.report.validations).toHaveLength(3);
	});
});

describe("AC-5 knowledge-base AI", () => {
	it("translates on the triggering admin's model", async () => {
		h.primary.queue.push({ text: "数组按索引存储元素。" });
		const res = await internal("/kb/translate-chunk", { user_uid: CHAT_USER, content: "Arrays store elements by index." });
		expect(res.json.translated).toBe("数组按索引存储元素。");
		expect(String(h.primary.requests[0]!.body.messages.at(-1).content)).toContain("Arrays store");
		await h.app.request("/internal/health", { headers: { "X-Internal-Token": INTERNAL_TOKEN } });
	});
	it("returns structured candidates from the search model", async () => {
		h.primary.queue.push({ text: '好的：[{"title":"OS Book","source_url":"https://example.org/os.pdf","source_type":"pdf"}, "junk"]' });
		const res = await internal("/kb/search-textbook-sources", { user_uid: CHAT_USER, topic: "操作系统", limit: 5 });
		expect(res.json.candidates).toEqual([{ title: "OS Book", source_url: "https://example.org/os.pdf", source_type: "pdf" }]);
	});
	it("an admin without a model is blocked with MODEL_NOT_CONFIGURED", async () => {
		for (const [path, body] of [
			["/kb/translate-chunk", { content: "x" }],
			["/kb/search-textbook-sources", { topic: "x", limit: 3 }],
		] as const) {
			const res = await internal(path, { user_uid: UNCONFIGURED_USER, ...body });
			expect(res.status).toBe(428);
			expect(res.json.error_code).toBe("MODEL_NOT_CONFIGURED");
		}
	});
	it("rejects calls without the internal token", async () => {
		const res = await h.app.request("/internal/ai/kb/translate-chunk", { method: "POST", body: "{}" });
		expect(res.status).toBe(401);
	});
});
