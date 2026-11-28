import { useEffect, useMemo, useState } from "react";
import {
	modelConfigApi,
	SCENES,
	type UsageSummary,
} from "../../api/modelConfig";
import { Tabs } from "../../components/ui/Tabs";
import { useAuth } from "../../contexts/AuthContext";

const RANGES = [
	{ days: 1, label: "今日" },
	{ days: 7, label: "近 7 天" },
	{ days: 30, label: "近 30 天" },
] as const;

const fmt = (n: number) => n.toLocaleString("zh-CN");

function formatCost(requests: number, costUsd: number) {
	if (requests === 0) return "—";
	if (costUsd > 0 && costUsd < 0.01) return "< $0.01";
	return `$${costUsd.toFixed(2)}`;
}

export function UsageSection() {
	const { token } = useAuth();
	const [days, setDays] = useState<number>(7);
	const [usage, setUsage] = useState<UsageSummary | null>(null);
	const [error, setError] = useState<string | null>(null);

	useEffect(() => {
		if (!token) return;
		let cancelled = false;
		setError(null);
		modelConfigApi
			.usage(token, days)
			.then((value) => !cancelled && setUsage(value))
			.catch(
				(err) =>
					!cancelled &&
					setError(err instanceof Error ? err.message : "用量加载失败"),
			);
		return () => {
			cancelled = true;
		};
	}, [token, days]);

	const totals = useMemo(() => {
		const buckets = usage?.buckets ?? [];
		const sum = (pick: (b: (typeof buckets)[number]) => number) =>
			buckets.reduce((acc, b) => acc + pick(b), 0);
		const requests = sum((b) => b.requests);
		return {
			requests,
			success: requests ? sum((b) => b.success_requests) / requests : null,
			input: sum((b) => b.input_tokens),
			output: sum((b) => b.output_tokens),
			cache: sum((b) => b.cache_read_tokens),
			reasoning: sum((b) => b.reasoning_tokens),
		};
	}, [usage]);

	const byScene = useMemo(() => {
		const map = new Map<
			string,
			{ requests: number; tokens: number; cost: number }
		>();
		for (const b of usage?.buckets ?? []) {
			const current = map.get(b.scene) ?? { requests: 0, tokens: 0, cost: 0 };
			current.requests += b.requests;
			current.tokens += b.input_tokens + b.output_tokens;
			current.cost += b.estimated_cost_usd;
			map.set(b.scene, current);
		}
		return [...map.entries()];
	}, [usage]);

	const sceneLabel = (id: string) =>
		SCENES.find((scene) => scene.id === id)?.label ?? id;

	return (
		<section className="mc-section" aria-labelledby="mc-usage-title">
			<header className="mc-section-head">
				<div>
					<h2 id="mc-usage-title">用量与费用</h2>
					<p className="mc-hint">
						用量单位为 Token；费用按模型参考单价估算，仅供参考。
					</p>
				</div>
				<Tabs
					mode="segmented"
					size="sm"
					ariaLabel="时间范围"
					value={String(days)}
					onChange={(next) => setDays(Number(next))}
					items={RANGES.map((range) => ({
						value: String(range.days),
						label: range.label,
					}))}
				/>
			</header>
			{error && (
				<p className="mc-error" role="alert">
					{error}
				</p>
			)}
			{usage && (
				<>
					<dl className="mc-stats">
						<div>
							<dt>调用次数</dt>
							<dd>{fmt(totals.requests)}</dd>
						</div>
						<div>
							<dt>成功率</dt>
							<dd>
								{totals.success === null
									? "—"
									: `${Math.round(totals.success * 100)}%`}
							</dd>
						</div>
						<div>
							<dt>输入</dt>
							<dd>{fmt(totals.input)}</dd>
						</div>
						<div>
							<dt>输出</dt>
							<dd>{fmt(totals.output)}</dd>
						</div>
						<div>
							<dt>缓存命中</dt>
							<dd>{fmt(totals.cache)}</dd>
						</div>
						<div>
							<dt>推理</dt>
							<dd>{fmt(totals.reasoning)}</dd>
						</div>
						<div>
							<dt>估算费用</dt>
							<dd>{formatCost(totals.requests, usage.total_cost_usd)}</dd>
						</div>
					</dl>
					{byScene.length === 0 ? (
						<p className="mc-empty">这段时间还没有调用记录。</p>
					) : (
						<table className="mc-table">
							<caption className="mc-sr">按业务场景分布</caption>
							<thead>
								<tr>
									<th scope="col">场景</th>
									<th scope="col">调用</th>
									<th scope="col">Token</th>
									<th scope="col">费用（USD）</th>
								</tr>
							</thead>
							<tbody>
								{byScene.map(([scene, row]) => (
									<tr key={scene}>
										<th scope="row">{sceneLabel(scene)}</th>
										<td>{fmt(row.requests)}</td>
										<td>{fmt(row.tokens)}</td>
										<td>{formatCost(row.requests, row.cost)}</td>
									</tr>
								))}
							</tbody>
						</table>
					)}
				</>
			)}
		</section>
	);
}
