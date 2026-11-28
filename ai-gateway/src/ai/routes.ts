import { Hono } from "hono";
import { type AuthVariables, jwtAuth } from "../auth.js";
import type { BackendClient } from "../backendClient.js";
import { GatewayError } from "../errors.js";
import type { ModelRuntime } from "../models/runtime.js";
import type { Logger } from "../observability.js";
import { createSseResponse } from "../sse.js";
import { streamForestAi, type ForestAiBody } from "./forestAi.js";
import { runGrowthReport } from "./growthReport.js";
import { runKnowledgeBaseAgent } from "./kbAgent.js";
import { translateChunk } from "./kb.js";
import type { WebConfig } from "../tools/web.js";
import { generateQuiz, gradeQuiz, type GradeInput, type QuizMaterial } from "./quiz.js";

async function jsonBody(request: Request): Promise<Record<string, unknown>> {
	try {
		const raw = await request.json();
		return raw && typeof raw === "object" ? (raw as Record<string, unknown>) : {};
	} catch {
		throw new GatewayError(422, undefined, "请求体必须是 JSON");
	}
}

function requireUid(body: Record<string, unknown>): string {
	const uid = body.user_uid;
	if (typeof uid !== "string" || uid.length < 1) throw new GatewayError(422, undefined, "缺少 user_uid");
	return uid;
}

const frame = (event: string, payload: Record<string, unknown>) => `event: ${event}\ndata: ${JSON.stringify(payload)}\n\n`;

function failurePayload(error: unknown, fallback: string): Record<string, unknown> {
	if (error instanceof GatewayError) {
		return { message: error.detail, ...(error.errorCode ? { error_code: error.errorCode } : {}) };
	}
	return { message: fallback };
}

/** Python -> gateway AI jobs (internal token already enforced by the app). */
export function internalAiRoutes(deps: { runtime: ModelRuntime }) {
	const app = new Hono();
	app.post("/quiz/generate", async (c) => {
		const body = await jsonBody(c.req.raw);
		requireUid(body);
		return c.json(await generateQuiz(deps.runtime, body as unknown as QuizMaterial));
	});
	app.post("/quiz/grade", async (c) => {
		const body = await jsonBody(c.req.raw);
		requireUid(body);
		return c.json(await gradeQuiz(deps.runtime, body as unknown as GradeInput));
	});
	app.post("/kb/translate-chunk", async (c) => {
		const body = await jsonBody(c.req.raw);
		const uid = requireUid(body);
		if (typeof body.content !== "string" || !body.content.trim()) throw new GatewayError(422, undefined, "content 不能为空");
		return c.json(await translateChunk(deps.runtime, { user_uid: uid, content: body.content }));
	});
	return app;
}

export interface StreamRouteDeps {
	jwtSecret: string;
	backend: BackendClient;
	runtime: ModelRuntime;
	logger: Logger;
	heartbeatMs: number;
	web: WebConfig;
}

/** `POST /api/forest/ai/stream` and `POST /api/branch/canopy/report/stream`. */
export function aiStreamRoutes(deps: StreamRouteDeps) {
	const app = new Hono<{ Variables: AuthVariables }>();

	app.post("/forest/ai/stream", jwtAuth(deps.jwtSecret, deps.backend), async (c) => {
		const { userUid } = c.get("auth");
		const raw = await jsonBody(c.req.raw);
		const message = raw.message;
		if (typeof message !== "string" || message.length < 1 || message.length > 4000) {
			throw new GatewayError(422, undefined, "message 长度需在 1-4000 之间");
		}
		const body: ForestAiBody = {
			course_node_id: String(raw.course_node_id ?? ""),
			chapter_id: String(raw.chapter_id ?? ""),
			quiz_id: typeof raw.quiz_id === "string" ? raw.quiz_id : null,
			message,
			active_question_context: (raw.active_question_context as Record<string, unknown>) ?? {},
			image_attachment: typeof raw.image_attachment === "string" ? raw.image_attachment : null,
		};
		return createSseResponse(
			async (writer) => {
				try {
					await streamForestAi({
						runtime: deps.runtime,
						backend: deps.backend,
						userUid,
						body,
						signal: writer.signal,
						onChunk: (chunk) => writer.sendRaw(frame("forest_ai_text_chunk", { chunk })),
					});
					writer.sendRaw(frame("forest_ai_completed", { message: "completed" }));
				} catch (error) {
					if (writer.closed || writer.signal.aborted) return;
					writer.sendRaw(frame("forest_error", failurePayload(error, "Forest AI 暂时不可用")));
				}
			},
			{ heartbeatMs: deps.heartbeatMs },
		);
	});

	app.post("/admin/knowledge-base/agent/stream", jwtAuth(deps.jwtSecret, deps.backend), async (c) => {
		const { userUid, role } = c.get("auth");
		if (role !== "admin") throw new GatewayError(403, undefined, "仅管理员可使用知识库智能体");
		const raw = await jsonBody(c.req.raw);
		const message = typeof raw.message === "string" ? raw.message.trim() : "";
		if (message.length < 1 || message.length > 4000) throw new GatewayError(422, undefined, "message 长度需在 1-4000 之间");
		return createSseResponse(
			async (writer) => {
				try {
					await runKnowledgeBaseAgent({
						runtime: deps.runtime,
						backend: deps.backend,
						web: deps.web,
						userUid,
						message,
						signal: writer.signal,
						emit: (event) => writer.sendRaw(frame(event.event, event.payload)),
					});
				} catch (error) {
					if (writer.closed || writer.signal.aborted) return;
					deps.logger.warn(`kb_agent_failed name=${error instanceof Error ? error.name : "unknown"}`);
					writer.sendRaw(frame("error", { ...failurePayload(error, "知识库 Agent 处理失败。"), recoverable: true }));
				}
			},
			{ heartbeatMs: deps.heartbeatMs },
		);
	});

	app.post("/branch/canopy/report/stream", jwtAuth(deps.jwtSecret, deps.backend), (c) => {
		const { userUid } = c.get("auth");
		return createSseResponse(
			async (writer) => {
				try {
					const outcome = await runGrowthReport({
						runtime: deps.runtime,
						backend: deps.backend,
						userUid,
						signal: writer.signal,
						onStage: (stage) => writer.sendRaw(frame("report_stage", { stage })),
					});
					if (outcome.ok) writer.sendRaw(frame("report_completed", outcome.report));
					else writer.sendRaw(frame("report_error", { message: "成长报告暂时未能生成，请稍后重试。" }));
				} catch (error) {
					if (writer.closed || writer.signal.aborted) return;
					deps.logger.warn(`growth_report_failed name=${error instanceof Error ? error.name : "unknown"}`);
					const payload = failurePayload(error, "成长报告暂时未能生成，请稍后重试。");
					writer.sendRaw(frame("report_error", error instanceof GatewayError ? payload : { message: String(payload.message) }));
				}
			},
			{ heartbeatMs: deps.heartbeatMs },
		);
	});
	return app;
}
