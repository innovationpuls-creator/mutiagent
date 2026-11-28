import type { AgentTool, AgentToolResult } from "@earendil-works/pi-agent-core";
import { arr, obj, str } from "@earendil-works/pi-schema";
import type { BackendClient, ResourcePhase, ResourceSectionInfo } from "../backendClient.js";
import { BackendBusinessError, GatewayError } from "../errors.js";
import type { AgentStreamHandle } from "../models/runtime.js";
import { runAgent } from "./agentRunner.js";
import { runVideoAgent } from "./videoAgent.js";
import type { WebConfig } from "../tools/web.js";
import { mapWithConcurrency } from "./outlineAgent.js";
import type { Emit } from "./types.js";

export const DEFAULT_SECTION_CONCURRENCY = 2;
/** Repairs of the section document / animation in place before giving up on a phase. */
export const MAX_MARKDOWN_CORRECTIONS = 2;
export const MAX_ANIMATION_CORRECTIONS = 1;
export const NEEDS_FOCUS_TEXT = "重新生成本章前，请告诉我下一版需要侧重哪里。";
export const CHAPTER_DONE_TEXT = "本章教学内容已生成。";

const MARKDOWN_SCHEMA = obj({ markdown: str() });
const ANIMATION_SCHEMA = obj({
	animations: arr(obj({ animation_id: str(), title: str(), html: str() })),
});

export interface LeafResourceRequest {
	courseNodeId: string;
	chapterSectionId: string;
	scope: string;
	mode: "generate" | "regenerate";
}

const BLOCK = /\[LEAF_RESOURCE_GENERATION\](.*?)\[\/LEAF_RESOURCE_GENERATION\]/s;

/** The explicit button protocol: a structured block, never a keyword guess. */
export function parseLeafResourceRequest(query: string): LeafResourceRequest | null {
	const match = BLOCK.exec(query);
	if (!match?.[1]) return null;
	const fields: Record<string, string> = {};
	for (const line of match[1].split("\n")) {
		const index = line.indexOf(":");
		if (index > 0) fields[line.slice(0, index).trim()] = line.slice(index + 1).trim();
	}
	const { course_node_id: courseNodeId, chapter_section_id: chapterSectionId, scope, mode } = fields;
	if (!courseNodeId || !chapterSectionId || !scope || !mode) return null;
	return { courseNodeId, chapterSectionId, scope, mode: mode === "regenerate" ? "regenerate" : "generate" };
}

export interface PendingRegeneration {
	course_node_id: string;
	chapter_section_id: string;
	requested_at: string;
}

export function readPendingRegeneration(value: unknown): PendingRegeneration | null {
	if (!value || typeof value !== "object") return null;
	const record = value as Record<string, unknown>;
	const course = String(record.course_node_id ?? "").trim();
	const chapter = String(record.chapter_section_id ?? "").trim();
	if (!course || !chapter) return null;
	return { course_node_id: course, chapter_section_id: chapter, requested_at: String(record.requested_at ?? "") };
}

export interface FailedSection {
	sectionId: string;
	phase: ResourcePhase;
	reason: string;
}

export type ResourceOutcome =
	| { kind: "refused"; text: string }
	| { kind: "busy"; text: string }
	| { kind: "needs_focus"; chapterSectionId: string; text: string }
	| {
			kind: "completed";
			chapterSectionId: string;
			text: string;
			succeeded: string[];
			failed: FailedSection[];
	  }
	| { kind: "failed"; chapterSectionId: string; text: string; failed: FailedSection[] };

export interface ResourceAgentInput {
	handle: AgentStreamHandle;
	backend: BackendClient;
	userUid: string;
	courseId: string;
	chapterRef: string;
	mode: "generate" | "regenerate";
	regenerationFocus: string;
	concurrency?: number;
	web: WebConfig;
	signal?: AbortSignal;
	emit: Emit;
	now?: () => number;
}

function text(value: string, extra: Partial<AgentToolResult<unknown>> = {}): AgentToolResult<unknown> {
	return { content: [{ type: "text", text: value }], details: undefined, ...extra };
}

const PHASE_AGENT: Record<ResourcePhase, { agent: string; label: string; order: number }> = {
	markdown: { agent: "section_markdown_agent", label: "文案", order: 1 },
	video: { agent: "section_video_search_agent", label: "视频", order: 2 },
	animation: { agent: "section_html_animation_agent", label: "动画", order: 3 },
	compose: { agent: "compose_resource", label: "拼装", order: 4 },
};

class SectionStageError extends Error {
	constructor(
		readonly phase: ResourcePhase,
		message: string,
	) {
		super(message);
	}
}

export async function runResourceAgent(input: ResourceAgentInput): Promise<ResourceOutcome> {
	const { backend, userUid, courseId, emit } = input;
	const prepared = await backend.prepareResourceGeneration(userUid, courseId, input.chapterRef, input.mode);
	if (prepared.status === "refused") return { kind: "refused", text: prepared.message };
	if (prepared.status === "busy") return { kind: "busy", text: prepared.message };
	if (prepared.status === "needs_focus") {
		return { kind: "needs_focus", chapterSectionId: prepared.chapter_section_id, text: NEEDS_FOCUS_TEXT };
	}

	const chapterId = prepared.chapter_section_id;
	const succeeded: string[] = [];
	const failed: FailedSection[] = [];
	const reuse = input.mode !== "regenerate";
	const refs = (sectionId: string) => ({
		course_id: courseId,
		chapter_section_id: chapterId,
		section_id: sectionId,
		kind: "course_resource_section",
	});

	const phaseEvent = (
		section: ResourceSectionInfo,
		phase: ResourcePhase,
		status: "running" | "completed" | "error",
		message: string,
		extra: Record<string, unknown> = {},
	) => {
		const meta = PHASE_AGENT[phase];
		const done = status !== "running";
		emit(done ? "agent_result" : "agent_progress", {
			agent: meta.agent,
			agent_order: meta.order,
			phase,
			status,
			stepId: `leaf-section-${section.section_id}-${phase}`,
			message,
			label: `${section.section_id} ${meta.label}`,
			success: status === "completed",
			...refs(section.section_id),
			...extra,
		});
	};

	// ── per-phase work; each returns without throwing for "degrade" outcomes ──
	async function markdownStage(section: ResourceSectionInfo): Promise<void> {
		const prompt = await backend.getMarkdownPrompt(userUid, courseId, section.section_id, input.regenerationFocus);
		let value: Record<string, unknown> | undefined;
		let failures = 0;
		let lastIssue = "";
		const submit: AgentTool<any> = {
			name: "submit_section_markdown",
			label: "提交小节教学文档",
			description: "提交本小节完整的 Markdown 教学文档；系统会做质量校验并给出需要修正的问题。",
			parameters: MARKDOWN_SCHEMA,
			async execute(_id, params: any) {
				const result = await backend.validateMarkdown(userUid, courseId, section.section_id, String(params?.markdown ?? ""));
				if (result.ok) {
					value = result.value;
					return text("文档已通过校验。", { terminate: true });
				}
				failures += 1;
				lastIssue = result.issue;
				if (failures > MAX_MARKDOWN_CORRECTIONS) return text("多次修正后仍未通过，已停止。", { terminate: true, isError: true });
				return text(`文档未通过校验，请按问题修正后重新提交完整文档：\n- ${result.issue}`, { isError: true });
			},
		};
		await runAgent({
			handle: input.handle,
			systemPrompt: `${prompt.system_prompt}\n\n写完后必须调用 submit_section_markdown 提交完整 Markdown 文档；工具返回问题时修正后重新提交。`,
			tools: [submit],
			history: [],
			userText: prompt.query,
			signal: input.signal,
			shouldStop: () => value !== undefined || failures > MAX_MARKDOWN_CORRECTIONS,
			maxTurns: MAX_MARKDOWN_CORRECTIONS + 3,
		});
		if (!value) throw new SectionStageError("markdown", lastIssue || "模型未提交文档");
		await backend.saveSectionResource(userUid, courseId, section.section_id, { phase: "markdown", value });
	}

	async function videoStage(section: ResourceSectionInfo): Promise<{ unavailable: boolean }> {
		const result = await runVideoAgent({
			handle: input.handle,
			backend,
			web: input.web,
			userUid,
			courseId,
			sectionId: section.section_id,
			signal: input.signal,
		});
		await backend.saveSectionResource(userUid, courseId, section.section_id, { phase: "video", value: result.value });
		return { unavailable: result.status === "unavailable" };
	}

	async function animationStage(section: ResourceSectionInfo): Promise<{ fallback: boolean }> {
		const prompt = await backend.getAnimationPrompt(userUid, courseId, section.section_id);
		let animationValue: Record<string, unknown> | undefined;
		let usedFallback = false;
		if (prompt.needed) {
			let failures = 0;
			const submit: AgentTool<any> = {
				name: "submit_section_animations",
				label: "提交 HTML 动画",
				description: "提交本小节 animation_briefs 对应的可嵌入 HTML 动画；系统会做结构与安全校验。",
				parameters: ANIMATION_SCHEMA,
				async execute(_id, params: any) {
					const result = await backend.validateAnimations(
						userUid,
						courseId,
						section.section_id,
						Array.isArray(params?.animations) ? params.animations : [],
						false,
					);
					if (result.ok) {
						animationValue = result.value;
						return text("动画已通过校验。", { terminate: true });
					}
					failures += 1;
					if (failures > MAX_ANIMATION_CORRECTIONS) return text("修正次数已用完。", { terminate: true, isError: true });
					return text(`动画未通过校验，请按问题修正后重新提交：\n- ${result.issue}`, { isError: true });
				},
			};
			try {
				await runAgent({
					handle: input.handle,
					systemPrompt: `${prompt.system_prompt}\n\n生成后必须调用 submit_section_animations 提交；工具返回问题时修正后重新提交。`,
					tools: [submit],
					history: [],
					userText: prompt.query,
					signal: input.signal,
					shouldStop: () => animationValue !== undefined || failures > MAX_ANIMATION_CORRECTIONS,
					maxTurns: MAX_ANIMATION_CORRECTIONS + 3,
				});
			} catch (error) {
				if (error instanceof GatewayError && error.errorCode === "MODEL_OAUTH_EXPIRED") throw error;
				if (input.signal?.aborted) throw error;
				// A flaky model call must not cost the student the animation: fall through to the template.
			}
		}
		if (!animationValue) {
			const fallback = await backend.validateAnimations(userUid, courseId, section.section_id, [], true);
			if (!fallback.ok) throw new SectionStageError("animation", fallback.issue);
			animationValue = fallback.value;
			usedFallback = prompt.needed;
		}
		await backend.saveSectionResource(userUid, courseId, section.section_id, { phase: "animation", value: animationValue });
		return { fallback: usedFallback };
	}

	async function runSection(section: ResourceSectionInfo): Promise<void> {
		const done = (phase: ResourcePhase) => reuse && section.checkpoints[phase] === "completed";
		try {
			if (done("markdown")) {
				phaseEvent(section, "markdown", "completed", "文案已有检查点，直接复用");
			} else {
				phaseEvent(section, "markdown", "running", "正在生成文案，并写入视频与动画占位要求");
				await markdownStage(section);
				phaseEvent(section, "markdown", "completed", "文案与资源 brief 已生成，正在并行检索视频并生成动画");
			}

			const video = async () => {
				if (done("video")) {
					phaseEvent(section, "video", "completed", "视频已有检查点，直接复用");
					return;
				}
				phaseEvent(section, "video", "running", "正在按 video_briefs 检索具体视频");
				try {
					const { unavailable } = await videoStage(section);
					phaseEvent(
						section,
						"video",
						"completed",
						unavailable ? "该小节暂未找到合适教学视频，已平稳跳过" : "视频检索已完成",
						unavailable ? { video_unavailable: true } : {},
					);
				} catch (error) {
					if (error instanceof GatewayError && error.errorCode === "MODEL_OAUTH_EXPIRED") throw error;
					if (input.signal?.aborted) throw error;
					// The video source is an external service: never let it block text and animation.
					phaseEvent(section, "video", "completed", "视频检索暂不可用，已平稳跳过", { video_unavailable: true });
				}
			};
			const animation = async () => {
				if (done("animation")) {
					phaseEvent(section, "animation", "completed", "动画已有检查点，直接复用");
					return;
				}
				phaseEvent(section, "animation", "running", "正在按 animation_briefs 生成交互动画");
				const { fallback } = await animationStage(section);
				phaseEvent(section, "animation", "completed", fallback ? "已使用教学交互模板动画" : "动画生成完成");
			};
			const branches = await Promise.allSettled([video(), animation()]);
			const rejected = branches.find((b): b is PromiseRejectedResult => b.status === "rejected");
			if (rejected) throw rejected.reason;

			await backend.saveSectionResource(userUid, courseId, section.section_id, { phase: "compose" });
			phaseEvent(section, "compose", "completed", "正文、视频与动画资源已按占位符拼装完成，本小节可阅读");
			succeeded.push(section.section_id);
		} catch (error) {
			if (error instanceof GatewayError && error.errorCode === "MODEL_OAUTH_EXPIRED") throw error;
			if (input.signal?.aborted) throw error;
			const phase = error instanceof SectionStageError ? error.phase : "markdown";
			const reason = error instanceof Error ? error.message : String(error);
			const message = `小节 ${section.section_id} 的${PHASE_AGENT[phase].label}生成失败：${reason}`.slice(0, 300);
			failed.push({ sectionId: section.section_id, phase, reason });
			try {
				await backend.saveSectionResource(userUid, courseId, section.section_id, { phase, failure: message });
			} catch (saveError) {
				if (!(saveError instanceof BackendBusinessError)) throw saveError;
			}
			phaseEvent(section, phase, "error", message);
		}
	}

	try {
		emit("agent_calling", {
			agent: "section_markdown_agent",
			phase: "markdown",
			status: "queued",
			stepId: `leaf-chapter-${chapterId}`,
			message: `正在为第 ${chapterId} 章准备 ${prepared.sections.length} 个小节`,
			label: "章节资源调度智能体",
			course_id: courseId,
			chapter_section_id: chapterId,
			kind: "course_resource_chapter",
			section_ids: prepared.sections.map((s) => s.section_id),
		});
		await mapWithConcurrency(prepared.sections, input.concurrency ?? DEFAULT_SECTION_CONCURRENCY, runSection);
	} finally {
		// Whatever happened above, the chapter must never stay locked.
		try {
			await backend.finishResourceGeneration(userUid, courseId, chapterId, succeeded);
		} catch {
			// The lock also expires on its own; do not mask the original outcome.
		}
	}

	const order = new Map(prepared.sections.map((s, i) => [s.section_id, i]));
	failed.sort((a, b) => (order.get(a.sectionId) ?? 0) - (order.get(b.sectionId) ?? 0));
	if (succeeded.length === 0) {
		return {
			kind: "failed",
			chapterSectionId: chapterId,
			failed,
			text: `课程资源生成失败：小节 ${failed.map((f) => f.sectionId).join("、")} 未能生成，请稍后重试。`,
		};
	}
	if (failed.length > 0) {
		return {
			kind: "completed",
			chapterSectionId: chapterId,
			succeeded,
			failed,
			text: `本章已生成 ${succeeded.length} 个小节；小节 ${failed.map((f) => f.sectionId).join("、")} 生成失败，可直接点击重试补跑，已成功的小节会自动复用。`,
		};
	}
	return { kind: "completed", chapterSectionId: chapterId, succeeded, failed, text: CHAPTER_DONE_TEXT };
}
