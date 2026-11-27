import { useState } from "react";
import {
	type CustomModelUpsert,
	type CustomModelView,
	modelConfigApi,
} from "../../api/modelConfig";
import { useAuth } from "../../contexts/AuthContext";

type Tri = "" | "true" | "false";
const COMPAT_FLAGS = [
	{ key: "supportsDeveloperRole", label: "支持 developer 角色" },
	{ key: "supportsStore", label: "支持 store 参数" },
	{ key: "supportsUsageInStreaming", label: "流式返回 usage" },
	{ key: "supportsReasoningEffort", label: "支持 reasoning_effort" },
] as const;

interface Draft {
	model_id: string;
	display_name: string;
	context_window: string;
	max_tokens: string;
	supports_vision: boolean;
	supports_tools: boolean;
	supports_reasoning: boolean;
	price_input: string;
	price_output: string;
	flags: Record<string, Tri>;
	maxTokensField: "" | "max_tokens" | "max_completion_tokens";
	extra: string;
}

const emptyDraft = (): Draft => ({
	model_id: "",
	display_name: "",
	context_window: "128000",
	max_tokens: "8192",
	supports_vision: false,
	supports_tools: true,
	supports_reasoning: false,
	price_input: "",
	price_output: "",
	flags: {},
	maxTokensField: "",
	extra: "",
});

function draftFrom(model: CustomModelView): Draft {
	const compat = { ...(model.compat_config as Record<string, unknown>) };
	const flags: Record<string, Tri> = {};
	for (const { key } of COMPAT_FLAGS) {
		if (typeof compat[key] === "boolean")
			flags[key] = compat[key] ? "true" : "false";
		delete compat[key];
	}
	const maxTokensField =
		compat.maxTokensField === "max_tokens" ||
		compat.maxTokensField === "max_completion_tokens"
			? compat.maxTokensField
			: "";
	delete compat.maxTokensField;
	const pricing = model.pricing as Record<string, number>;
	return {
		model_id: model.model_id,
		display_name: model.display_name,
		context_window: String(model.context_window),
		max_tokens: String(model.max_tokens),
		supports_vision: model.supports_vision,
		supports_tools: model.supports_tools,
		supports_reasoning: model.supports_reasoning,
		price_input: pricing.input !== undefined ? String(pricing.input) : "",
		price_output: pricing.output !== undefined ? String(pricing.output) : "",
		flags,
		maxTokensField,
		extra: Object.keys(compat).length ? JSON.stringify(compat, null, 2) : "",
	};
}

export function buildCompat(draft: Draft): Record<string, unknown> {
	let compat: Record<string, unknown> = {};
	if (draft.extra.trim()) {
		const parsed = JSON.parse(draft.extra);
		if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
			throw new Error("其他兼容项必须是 JSON 对象");
		}
		compat = parsed as Record<string, unknown>;
	}
	for (const { key } of COMPAT_FLAGS) {
		const value = draft.flags[key];
		if (value) compat[key] = value === "true";
	}
	if (draft.maxTokensField) compat.maxTokensField = draft.maxTokensField;
	return compat;
}

export function CustomModelsPanel({
	providerId,
	models,
	onChanged,
}: {
	providerId: string;
	models: CustomModelView[];
	onChanged: () => Promise<void>;
}) {
	const { token } = useAuth();
	const [draft, setDraft] = useState<Draft | null>(null);
	const [error, setError] = useState<string | null>(null);
	const [busy, setBusy] = useState(false);

	const patch = (changes: Partial<Draft>) =>
		setDraft((d) => (d ? { ...d, ...changes } : d));

	const save = async () => {
		if (!token || !draft) return;
		setError(null);
		const contextWindow = Number(draft.context_window);
		const maxTokens = Number(draft.max_tokens);
		if (!draft.model_id.trim()) return setError("请填写模型 ID");
		if (!Number.isInteger(contextWindow) || contextWindow < 1)
			return setError("上下文窗口必须是正整数");
		if (!Number.isInteger(maxTokens) || maxTokens < 1)
			return setError("最大输出必须是正整数");
		let compat: Record<string, unknown>;
		try {
			compat = buildCompat(draft);
		} catch (err) {
			return setError(
				err instanceof Error ? err.message : "兼容项 JSON 格式不正确",
			);
		}
		const pricing: Record<string, number> = {};
		if (draft.price_input.trim()) pricing.input = Number(draft.price_input);
		if (draft.price_output.trim()) pricing.output = Number(draft.price_output);
		if (Object.values(pricing).some((v) => !Number.isFinite(v) || v < 0))
			return setError("参考单价必须是非负数字");
		const body: CustomModelUpsert = {
			provider_id: providerId,
			model_id: draft.model_id.trim(),
			display_name: draft.display_name.trim() || null,
			context_window: contextWindow,
			max_tokens: maxTokens,
			supports_vision: draft.supports_vision,
			supports_tools: draft.supports_tools,
			supports_reasoning: draft.supports_reasoning,
			compat_config: compat,
			pricing,
			enabled: true,
		};
		setBusy(true);
		try {
			await modelConfigApi.saveCustomModel(token, body);
			await onChanged();
			setDraft(null);
		} catch (err) {
			setError(err instanceof Error ? err.message : "保存失败，请稍后重试");
		} finally {
			setBusy(false);
		}
	};

	const remove = async (model: CustomModelView) => {
		if (!token) return;
		setBusy(true);
		setError(null);
		try {
			await modelConfigApi.deleteCustomModel(token, model.id);
			await onChanged();
		} catch (err) {
			setError(err instanceof Error ? err.message : "删除失败，请稍后重试");
		} finally {
			setBusy(false);
		}
	};

	return (
		<section className="mc-stack" aria-label="自定义模型">
			<div className="mc-row mc-between">
				<h3>自定义模型</h3>
				{!draft && (
					<button
						type="button"
						className="mc-btn"
						onClick={() => setDraft(emptyDraft())}
					>
						新增模型
					</button>
				)}
			</div>
			{models.length === 0 && !draft && (
				<p className="mc-hint">还没有模型，先添加一个模型 ID。</p>
			)}
			<ul className="mc-list">
				{models.map((model) => (
					<li key={model.id} className="mc-list-item">
						<span>
							<strong>{model.display_name || model.model_id}</strong>
							<small>
								{model.model_id} · {model.supports_vision ? "视觉 " : ""}
								{model.supports_tools ? "工具 " : ""}
								{model.supports_reasoning ? "思考" : ""}
							</small>
						</span>
						<span className="mc-row">
							<button
								type="button"
								className="mc-btn mc-btn-ghost"
								onClick={() => setDraft(draftFrom(model))}
							>
								编辑
							</button>
							<button
								type="button"
								className="mc-btn mc-btn-danger"
								disabled={busy}
								onClick={() => void remove(model)}
								aria-label={`删除模型 ${model.model_id}`}
							>
								删除
							</button>
						</span>
					</li>
				))}
			</ul>
			{draft && (
				<div className="mc-form">
					<label className="mc-field">
						<span>模型 ID</span>
						<input
							value={draft.model_id}
							onChange={(e) => patch({ model_id: e.target.value })}
						/>
					</label>
					<label className="mc-field">
						<span>展示名（可选）</span>
						<input
							value={draft.display_name}
							onChange={(e) => patch({ display_name: e.target.value })}
						/>
					</label>
					<div className="mc-grid-2">
						<label className="mc-field">
							<span>上下文窗口</span>
							<input
								inputMode="numeric"
								value={draft.context_window}
								onChange={(e) => patch({ context_window: e.target.value })}
							/>
						</label>
						<label className="mc-field">
							<span>最大输出</span>
							<input
								inputMode="numeric"
								value={draft.max_tokens}
								onChange={(e) => patch({ max_tokens: e.target.value })}
							/>
						</label>
					</div>
					<fieldset className="mc-checks">
						<legend>能力标签</legend>
						<label>
							<input
								type="checkbox"
								checked={draft.supports_vision}
								onChange={(e) => patch({ supports_vision: e.target.checked })}
							/>
							视觉（图片输入）
						</label>
						<label>
							<input
								type="checkbox"
								checked={draft.supports_tools}
								onChange={(e) => patch({ supports_tools: e.target.checked })}
							/>
							工具调用
						</label>
						<label>
							<input
								type="checkbox"
								checked={draft.supports_reasoning}
								onChange={(e) =>
									patch({ supports_reasoning: e.target.checked })
								}
							/>
							思考
						</label>
					</fieldset>
					<div className="mc-grid-2">
						<label className="mc-field">
							<span>参考单价 输入（USD / 百万 token）</span>
							<input
								inputMode="decimal"
								value={draft.price_input}
								onChange={(e) => patch({ price_input: e.target.value })}
							/>
						</label>
						<label className="mc-field">
							<span>参考单价 输出</span>
							<input
								inputMode="decimal"
								value={draft.price_output}
								onChange={(e) => patch({ price_output: e.target.value })}
							/>
						</label>
					</div>
					<details className="mc-details">
						<summary>Pi Compat 高级兼容项</summary>
						<div className="mc-stack">
							{COMPAT_FLAGS.map(({ key, label }) => (
								<label key={key} className="mc-field">
									<span>{label}</span>
									<select
										value={draft.flags[key] ?? ""}
										onChange={(e) =>
											patch({
												flags: { ...draft.flags, [key]: e.target.value as Tri },
											})
										}
									>
										<option value="">默认</option>
										<option value="true">是</option>
										<option value="false">否</option>
									</select>
								</label>
							))}
							<label className="mc-field">
								<span>最大输出参数名</span>
								<select
									value={draft.maxTokensField}
									onChange={(e) =>
										patch({
											maxTokensField: e.target.value as Draft["maxTokensField"],
										})
									}
								>
									<option value="">默认</option>
									<option value="max_tokens">max_tokens</option>
									<option value="max_completion_tokens">
										max_completion_tokens
									</option>
								</select>
							</label>
							<label className="mc-field">
								<span>其他兼容项（JSON，可选）</span>
								<textarea
									rows={4}
									value={draft.extra}
									onChange={(e) => patch({ extra: e.target.value })}
									spellCheck={false}
								/>
							</label>
						</div>
					</details>
					<div className="mc-row">
						<button
							type="button"
							className="mc-btn mc-btn-primary"
							disabled={busy}
							onClick={() => void save()}
						>
							{busy ? "保存中…" : "保存模型"}
						</button>
						<button
							type="button"
							className="mc-btn mc-btn-ghost"
							onClick={() => {
								setDraft(null);
								setError(null);
							}}
						>
							取消
						</button>
					</div>
				</div>
			)}
			{error && (
				<p className="mc-error" role="alert">
					{error}
				</p>
			)}
		</section>
	);
}
