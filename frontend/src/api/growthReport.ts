import type { components } from "../types/api";
import { API_BASE_URL, notifyAuthInvalidFromError, readApiError } from "./http";

export type GrowthReport = components["schemas"]["GrowthReport"];
export type ReportEvidence = components["schemas"]["ReportEvidence"];
export type ReportInsight = components["schemas"]["ReportInsight"];
export type ReportAction = components["schemas"]["ReportAction"];
export type ReportStage = "collecting" | "analyzing" | "writing";

function isRecord(value: unknown): value is Record<string, unknown> {
	return value !== null && typeof value === "object";
}

function isInsight(value: unknown): boolean {
	return (
		isRecord(value) &&
		typeof value.title === "string" &&
		typeof value.body === "string" &&
		Array.isArray(value.evidence_ids) &&
		value.evidence_ids.every((id) => typeof id === "string")
	);
}

function parseReport(value: unknown): GrowthReport {
	if (
		!isRecord(value) ||
		typeof value.overview !== "string" ||
		typeof value.generated_at !== "string" ||
		!Number.isFinite(Date.parse(value.generated_at)) ||
		typeof value.coverage !== "string" ||
		!isRecord(value.stats) ||
		![
			value.stats.passed_chapters,
			value.stats.tested_chapters,
			value.stats.attempts,
		].every((n) => typeof n === "number" && Number.isInteger(n) && n >= 0) ||
		!Array.isArray(value.strengths) ||
		!value.strengths.every(isInsight) ||
		!Array.isArray(value.improvements) ||
		!value.improvements.every(isInsight) ||
		!Array.isArray(value.actions) ||
		!value.actions.every(
			(a) =>
				isInsight(a) &&
				isRecord(a) &&
				typeof a.check === "string" &&
				(a.course_id == null || typeof a.course_id === "string"),
		) ||
		!Array.isArray(value.evidence) ||
		!value.evidence.every(
			(e) =>
				isRecord(e) &&
				typeof e.id === "string" &&
				typeof e.title === "string" &&
				typeof e.detail === "string" &&
				["path", "quiz", "chapter", "weakness", "textbook"].includes(
					String(e.kind),
				) &&
				(e.course_id == null || typeof e.course_id === "string"),
		)
	) {
		throw new Error("成长报告数据格式不正确，请重新生成。");
	}
	return value as GrowthReport;
}

function handleEvent(
	frame: string,
	onStage: (stage: ReportStage) => void,
): GrowthReport | null {
	const lines = frame.split("\n");
	const event = lines
		.find((line) => line.startsWith("event:"))
		?.slice(6)
		.trim();
	const data = lines
		.filter((line) => line.startsWith("data:"))
		.map((line) => line.slice(5).trimStart())
		.join("\n");
	if (!data) return null;
	const value: unknown = JSON.parse(data);
	if (event === "report_error")
		throw new Error(
			isRecord(value) && typeof value.message === "string"
				? value.message
				: "成长报告生成失败。",
		);
	if (event === "report_completed") return parseReport(value);
	if (event === "report_stage" && isRecord(value)) {
		if (
			value.stage === "collecting" ||
			value.stage === "analyzing" ||
			value.stage === "writing"
		)
			onStage(value.stage);
	}
	return null;
}

export async function streamGrowthReport(
	token: string,
	signal: AbortSignal,
	onStage: (stage: ReportStage) => void,
): Promise<GrowthReport> {
	const response = await fetch(
		`${API_BASE_URL}/api/branch/canopy/report/stream`,
		{
			method: "POST",
			headers: { Authorization: `Bearer ${token}` },
			signal,
		},
	);
	if (!response.ok) {
		const error = await readApiError(response);
		notifyAuthInvalidFromError(response.status, error);
		throw new Error(
			typeof error?.detail === "string"
				? error.detail
				: "成长报告生成失败，请重试。",
		);
	}
	if (!response.body) throw new Error("报告连接不可用，请重试。");
	const reader = response.body.getReader();
	const decoder = new TextDecoder();
	let buffer = "";
	try {
		while (true) {
			const { done, value } = await reader.read();
			buffer += done
				? decoder.decode()
				: decoder.decode(value, { stream: true });
			buffer = buffer.replace(/\r\n/g, "\n");
			let end = buffer.indexOf("\n\n");
			while (end >= 0) {
				const report = handleEvent(buffer.slice(0, end), onStage);
				buffer = buffer.slice(end + 2);
				if (report) return report;
				end = buffer.indexOf("\n\n");
			}
			if (done) break;
		}
		throw new Error("报告连接已中断，请重新生成。");
	} finally {
		await reader.cancel().catch(() => undefined);
		reader.releaseLock();
	}
}
