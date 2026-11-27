import { useState } from "react";
import {
	aiModelsApi,
	type ProbeItem,
	type ProbeResult,
} from "../../api/modelConfig";
import { useAuth } from "../../contexts/AuthContext";

const ITEMS: Array<{ key: "text" | "tools" | "vision"; label: string }> = [
	{ key: "text", label: "文本" },
	{ key: "tools", label: "工具调用" },
	{ key: "vision", label: "视觉理解" },
];

function symbol(item: ProbeItem, key: string): string {
	if (item.status === "ok") return "✔";
	if (item.status === "failed") return "✘";
	return key === "vision" ? "未声明" : "—";
}

export function ProbeBadges({ result }: { result: ProbeResult }) {
	return (
		<ul className="mc-probe" aria-label="连通性测试结果">
			{ITEMS.map(({ key, label }) => {
				const item = result[key];
				return (
					<li
						key={key}
						className={`mc-probe-badge mc-probe-${item.status}`}
						title={item.reason}
					>
						<span>{label}</span>
						<strong>{symbol(item, key)}</strong>
						{item.status === "ok" &&
							typeof item.first_token_ms === "number" && (
								<em>{item.first_token_ms} ms</em>
							)}
						{item.status !== "ok" && item.reason && (
							<em className="mc-probe-reason">{item.reason}</em>
						)}
					</li>
				);
			})}
		</ul>
	);
}

export function ProbeButton({
	providerId,
	modelId,
	disabled,
	label = "测试连接",
}: {
	providerId: string;
	modelId: string | null;
	disabled?: boolean;
	label?: string;
}) {
	const { token } = useAuth();
	const [result, setResult] = useState<ProbeResult | null>(null);
	const [error, setError] = useState<string | null>(null);
	const [running, setRunning] = useState(false);

	const run = async () => {
		if (!token || !modelId) return;
		setRunning(true);
		setError(null);
		try {
			setResult(await aiModelsApi.probe(token, providerId, modelId));
		} catch (err) {
			setResult(null);
			setError(err instanceof Error ? err.message : "测试失败，请稍后重试");
		} finally {
			setRunning(false);
		}
	};

	return (
		<div className="mc-probe-wrap">
			<button
				type="button"
				className="mc-btn mc-btn-ghost"
				onClick={() => void run()}
				disabled={disabled || running || !modelId}
				title={modelId ? `用 ${modelId} 测试` : "没有可测试的模型"}
			>
				{running ? "测试中…" : label}
			</button>
			{result && <ProbeBadges result={result} />}
			{error && (
				<p className="mc-error" role="alert">
					{error}
				</p>
			)}
		</div>
	);
}
