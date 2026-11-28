import { useEffect, useMemo, useState } from "react";
import {
	modelConfigApi,
	type PreferencesPayload,
	SCENES,
	type SlotBinding,
	THINKING_LEVELS,
	type ThinkingLevel,
} from "../../api/modelConfig";
import {
	type ModelOption,
	parseRefKey,
	refKey,
} from "../../components/models/modelOptions";
import { Button } from "../../components/ui/Button";
import { Tabs } from "../../components/ui/Tabs";
import { useAuth } from "../../contexts/AuthContext";
import { useModelConfig } from "../../contexts/ModelConfigContext";
import { ProbeButton } from "./ProbeBadges";

type Mode = "simple" | "advanced";
type CacheRetention = "none" | "short" | "long" | "";

function ModelSelect({
	id,
	label,
	value,
	options,
	onChange,
	requireVision = false,
	emptyLabel = "请选择模型",
}: {
	id: string;
	label: string;
	value: string;
	options: ModelOption[];
	onChange: (key: string) => void;
	requireVision?: boolean;
	emptyLabel?: string;
}) {
	return (
		<label className="mc-field" htmlFor={id}>
			<span>{label}</span>
			<select id={id} value={value} onChange={(e) => onChange(e.target.value)}>
				<option value="">{emptyLabel}</option>
				{options.map((option) => {
					const blocked = requireVision && !option.vision;
					return (
						<option key={option.key} value={option.key} disabled={blocked}>
							{option.label} · {option.providerLabel}
							{blocked ? "（不支持图片输入）" : ""}
						</option>
					);
				})}
			</select>
		</label>
	);
}

function LevelControl({
	value,
	onChange,
	label,
}: {
	value: ThinkingLevel;
	onChange: (level: ThinkingLevel) => void;
	label: string;
}) {
	return (
		<div className="mc-field">
			<span id={`lvl-${label}`}>{label}</span>
			<Tabs
				mode="segmented"
				size="sm"
				ariaLabel={label}
				value={value}
				onChange={onChange}
				items={THINKING_LEVELS}
			/>
		</div>
	);
}

export function SlotSection() {
	const { token, user } = useAuth();
	const { config, options, setConfig } = useModelConfig();
	const prefs = config?.preferences;
	const isAdmin = user?.role === "admin";

	const [mode, setMode] = useState<Mode>("simple");
	const [main, setMain] = useState("");
	const [vision, setVision] = useState("");
	const [level, setLevel] = useState<ThinkingLevel>("medium");
	const [bindings, setBindings] = useState<Record<string, SlotBinding>>({});
	const [temperature, setTemperature] = useState("");
	const [timeout, setTimeoutValue] = useState("");
	const [retries, setRetries] = useState("");
	const [cache, setCache] = useState<CacheRetention>("");
	const [busy, setBusy] = useState(false);
	const [error, setError] = useState<string | null>(null);
	const [saved, setSaved] = useState(false);

	useEffect(() => {
		if (!prefs) return;
		setMode(prefs.config_mode === "advanced" ? "advanced" : "simple");
		setMain(refKey(prefs.default_model_ref));
		setVision(refKey(prefs.default_vision_model_ref));
		setLevel(prefs.default_thinking_level as ThinkingLevel);
		setBindings({ ...(prefs.slot_bindings as Record<string, SlotBinding>) });
		const rt = prefs.runtime_options ?? {};
		setTemperature(rt.temperature != null ? String(rt.temperature) : "");
		setTimeoutValue(
			rt.timeout_seconds != null ? String(rt.timeout_seconds) : "",
		);
		setRetries(rt.max_retries != null ? String(rt.max_retries) : "");
		setCache((rt.cache_retention as CacheRetention | null) ?? "");
	}, [prefs]);

	const visionOptions = useMemo(
		() => options.filter((option) => option.vision),
		[options],
	);
	const scenes = SCENES.filter((scene) => !scene.adminOnly || isAdmin);

	if (!config || !prefs) return null;

	const setBinding = (
		sceneId: string,
		changes: Partial<SlotBinding> | null,
	) => {
		setBindings((current) => {
			const next = { ...current };
			if (changes === null) delete next[sceneId];
			else {
				const existing = next[sceneId];
				const merged = { ...existing, ...changes } as SlotBinding;
				if (!merged.model_ref) return current;
				next[sceneId] = merged;
			}
			return next;
		});
	};

	const save = async () => {
		if (!token) return;
		setError(null);
		setSaved(false);
		const mainRef = parseRefKey(main);
		if (!mainRef) return setError("请先选择主力模型");
		const num = (
			text: string,
			name: string,
			integer = false,
		): number | null | undefined => {
			if (!text.trim()) return null;
			const n = Number(text);
			if (!Number.isFinite(n) || n < 0 || (integer && !Number.isInteger(n))) {
				setError(`${name}格式不正确`);
				return undefined;
			}
			return n;
		};
		const temp = num(temperature, "温度");
		const to = num(timeout, "超时", true);
		const rt = num(retries, "重试次数", true);
		if (temp === undefined || to === undefined || rt === undefined) return;
		const payload: PreferencesPayload = {
			config_mode: mode,
			default_model_ref: mainRef,
			default_vision_model_ref: parseRefKey(vision),
			default_thinking_level: level,
			runtime_options: {
				temperature: temp,
				timeout_seconds: to,
				max_retries: rt,
				cache_retention: cache || null,
			},
			slot_bindings:
				mode === "advanced"
					? (bindings as PreferencesPayload["slot_bindings"])
					: {},
		};
		setBusy(true);
		try {
			const preferences = await modelConfigApi.savePreferences(token, payload);
			setConfig({ ...config, preferences });
			setSaved(true);
		} catch (err) {
			setError(err instanceof Error ? err.message : "保存失败，请稍后重试");
		} finally {
			setBusy(false);
		}
	};

	const mainRef = parseRefKey(main);

	return (
		<section className="mc-section" aria-labelledby="mc-slots-title">
			<header className="mc-section-head">
				<div>
					<h2 id="mc-slots-title">选择要用的模型</h2>
					<p className="mc-hint">
						选好主力模型就能开始学习；需要看图的场景再选一个视觉模型。「高级」可按场景单独指定模型和备用模型。
					</p>
				</div>
				<Tabs
					mode="segmented"
					size="sm"
					ariaLabel="配置模式"
					value={mode}
					onChange={setMode}
					items={[
						{ value: "simple", label: "极简" },
						{ value: "advanced", label: "高级" },
					]}
				/>
			</header>
			{options.length === 0 && (
				<p className="mc-warn">
					还没有可选模型：先在上方配置模型服务（预置服务商填写密钥或授权登录，也可以添加自定义模型）。
				</p>
			)}
			<div className="mc-form">
				<ModelSelect
					id="mc-main"
					label="主力模型"
					value={main}
					options={options}
					onChange={setMain}
				/>
				<ModelSelect
					id="mc-vision"
					label="视觉模型（仅展示支持图片输入的模型）"
					value={vision}
					options={visionOptions}
					onChange={setVision}
					emptyLabel="不设置"
				/>
				<LevelControl value={level} onChange={setLevel} label="默认思考深度" />
				{mainRef && (
					<ProbeButton
						providerId={mainRef.provider_id}
						modelId={mainRef.model_id}
						label="测试主力模型"
					/>
				)}
			</div>

			{mode === "advanced" && (
				<div className="mc-stack">
					<h3>按场景配置</h3>
					<ul className="mc-list">
						{scenes.map((scene) => {
							const binding = bindings[scene.id];
							const key = refKey(binding?.model_ref);
							const chain = binding?.fallback_chain ?? [];
							return (
								<li key={scene.id} className="mc-scene">
									<strong>{scene.label}</strong>
									<ModelSelect
										id={`mc-scene-${scene.id}`}
										label="模型"
										value={key}
										options={options}
										requireVision={scene.needsVision}
										emptyLabel="跟随默认"
										onChange={(next) => {
											const ref = parseRefKey(next);
											if (!ref) setBinding(scene.id, null);
											else setBinding(scene.id, { model_ref: ref });
										}}
									/>
									{binding && (
										<>
											<label className="mc-field">
												<span>思考深度</span>
												<select
													value={binding.thinking_level ?? ""}
													onChange={(e) =>
														setBinding(scene.id, {
															thinking_level: (e.target.value ||
																null) as ThinkingLevel | null,
														})
													}
												>
													<option value="">跟随默认</option>
													{THINKING_LEVELS.map((item) => (
														<option key={item.value} value={item.value}>
															{item.label}
														</option>
													))}
												</select>
											</label>
											<div className="mc-field">
												<span>备用回退链（按顺序尝试）</span>
												<ol className="mc-chain">
													{chain.map((ref, index) => (
														<li key={refKey(ref)}>
															<span>{refKey(ref)}</span>
															<span className="mc-row">
																<Button
																	variant="ghost"
																	size="sm"
																	disabled={index === 0}
																	aria-label={`上移 ${refKey(ref)}`}
																	onClick={() => {
																		const next = [...chain];
																		[next[index - 1], next[index]] = [
																			next[index]!,
																			next[index - 1]!,
																		];
																		setBinding(scene.id, {
																			fallback_chain: next,
																		});
																	}}
																>
																	↑
																</Button>
																<Button
																	variant="ghost"
																	size="sm"
																	aria-label={`移除 ${refKey(ref)}`}
																	onClick={() =>
																		setBinding(scene.id, {
																			fallback_chain: chain.filter(
																				(_, i) => i !== index,
																			),
																		})
																	}
																>
																	移除
																</Button>
															</span>
														</li>
													))}
												</ol>
												{chain.length < 5 && (
													<ModelSelect
														id={`mc-chain-${scene.id}`}
														label="添加备用模型"
														value=""
														options={options.filter(
															(o) =>
																o.key !== key &&
																!chain.some((c) => refKey(c) === o.key) &&
																(!scene.needsVision || o.vision),
														)}
														emptyLabel="选择备用模型…"
														onChange={(next) => {
															const ref = parseRefKey(next);
															if (ref)
																setBinding(scene.id, {
																	fallback_chain: [...chain, ref],
																});
														}}
													/>
												)}
											</div>
										</>
									)}
								</li>
							);
						})}
					</ul>
					<h3>运行参数（对所有场景生效）</h3>
					<div className="mc-grid-2">
						<label className="mc-field">
							<span>温度（0–2，留空使用模型默认）</span>
							<input
								inputMode="decimal"
								value={temperature}
								onChange={(e) => setTemperature(e.target.value)}
							/>
						</label>
						<label className="mc-field">
							<span>单次超时（秒）</span>
							<input
								inputMode="numeric"
								value={timeout}
								onChange={(e) => setTimeoutValue(e.target.value)}
							/>
						</label>
						<label className="mc-field">
							<span>重试次数</span>
							<input
								inputMode="numeric"
								value={retries}
								onChange={(e) => setRetries(e.target.value)}
							/>
						</label>
						<label className="mc-field">
							<span>Prompt 缓存</span>
							<select
								value={cache}
								onChange={(e) => setCache(e.target.value as CacheRetention)}
							>
								<option value="">默认</option>
								<option value="none">关闭</option>
								<option value="short">短期</option>
								<option value="long">长期</option>
							</select>
						</label>
					</div>
				</div>
			)}
			{error && (
				<p className="mc-error" role="alert">
					{error}
				</p>
			)}
			{saved && (
				<p className="mc-ok" role="status">
					已保存，下一轮对话立即按新配置生效。
				</p>
			)}
			<div className="mc-row">
				<Button
					variant="primary"
					size="sm"
					disabled={busy || options.length === 0}
					onClick={() => void save()}
				>
					{busy ? "保存中…" : "保存配置"}
				</Button>
			</div>
		</section>
	);
}
