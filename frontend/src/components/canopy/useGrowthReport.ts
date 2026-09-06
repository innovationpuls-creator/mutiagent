import { useEffect, useRef, useState } from "react";
import {
	type GrowthReport,
	type ReportStage,
	streamGrowthReport,
} from "../../api/growthReport";

export function useGrowthReport(token: string | null) {
	const [report, setReport] = useState<GrowthReport | null>(null);
	const [stage, setStage] = useState<ReportStage | null>(null);
	const [error, setError] = useState<string | null>(null);
	const request = useRef<AbortController | null>(null);
	// biome-ignore lint/correctness/useExhaustiveDependencies: Reports are scoped to the authentication token.
	useEffect(() => {
		setReport(null);
		setError(null);
		setStage(null);
		return () => {
			request.current?.abort();
			request.current = null;
		};
	}, [token]);

	async function generate() {
		if (!token || request.current) return;
		const controller = new AbortController();
		request.current = controller;
		setError(null);
		setStage("collecting");
		try {
			const result = await streamGrowthReport(
				token,
				controller.signal,
				(next) => {
					if (!controller.signal.aborted) setStage(next);
				},
			);
			if (!controller.signal.aborted) setReport(result);
		} catch (failure) {
			if (!controller.signal.aborted)
				setError(
					failure instanceof Error
						? failure.message
						: "成长报告生成失败，请重试。",
				);
		} finally {
			if (request.current === controller) {
				request.current = null;
				setStage(null);
			}
		}
	}
	return { report, stage, error, generate };
}
