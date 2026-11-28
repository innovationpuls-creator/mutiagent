import { Brain, ChevronDown, Cpu, Eye, Wrench } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";
import { Link } from "react-router-dom";
import {
	THINKING_LEVELS,
	type ThinkingLevel,
	thinkingLabel,
} from "../../api/modelConfig";
import { useAuth } from "../../contexts/AuthContext";
import { useModelConfig } from "../../contexts/ModelConfigContext";
import { refKey } from "./modelOptions";
import { modelSettingsPath } from "./modelPaths";
import "./model-config-shared.css";

export function ModelQuickSwitcher({ className = "" }: { className?: string }) {
	const { user } = useAuth();
	const { config, options, quickSwitch, needsSetup } = useModelConfig();
	const [isOpen, setIsOpen] = useState(false);
	const [pending, setPending] = useState(false);
	const [error, setError] = useState<string | null>(null);
	const rootRef = useRef<HTMLDivElement>(null);
	const popoverId = useId();

	useEffect(() => {
		if (!isOpen) return undefined;
		const onPointerDown = (event: MouseEvent) => {
			if (
				event.target instanceof Node &&
				!rootRef.current?.contains(event.target)
			) {
				setIsOpen(false);
			}
		};
		const onKeyDown = (event: KeyboardEvent) => {
			if (event.key === "Escape") setIsOpen(false);
		};
		document.addEventListener("mousedown", onPointerDown);
		document.addEventListener("keydown", onKeyDown);
		return () => {
			document.removeEventListener("mousedown", onPointerDown);
			document.removeEventListener("keydown", onKeyDown);
		};
	}, [isOpen]);

	if (!config) return null;

	const preferences = config.preferences;
	const currentKey = refKey(preferences.default_model_ref);
	const current = options.find((option) => option.key === currentKey);
	const level = preferences.default_thinking_level as ThinkingLevel;
	const settingsPath = modelSettingsPath(user?.role);

	const apply = async (input: Parameters<typeof quickSwitch>[0]) => {
		setPending(true);
		setError(null);
		try {
			await quickSwitch(input);
		} catch (err) {
			setError(err instanceof Error ? err.message : "切换失败，请稍后重试");
		} finally {
			setPending(false);
		}
	};

	return (
		<div className={`mqs ${className}`} ref={rootRef}>
			<button
				type="button"
				className="mqs-trigger"
				aria-haspopup="dialog"
				aria-expanded={isOpen}
				aria-controls={isOpen ? popoverId : undefined}
				onClick={() => setIsOpen((open) => !open)}
			>
				<Cpu aria-hidden="true" size={14} />
				<span className="mqs-model">
					{current?.label ??
						(needsSetup
							? "未配置模型"
							: (preferences.default_model_ref?.model_id ?? "未选择"))}
				</span>
				<span className="mqs-level">{thinkingLabel(level)}思考</span>
				<ChevronDown aria-hidden="true" size={14} />
			</button>
			{isOpen && (
				<div
					className="mqs-popover"
					id={popoverId}
					role="dialog"
					aria-label="切换模型与思考深度"
				>
					<div className="mqs-section">
						<p className="mqs-heading">模型</p>
						{options.length === 0 ? (
							<p className="mqs-empty">还没有可用模型，请先到模型配置添加。</p>
						) : (
							<ul className="mqs-list">
								{options.map((option) => (
									<li key={option.key}>
										<button
											type="button"
											className="mqs-option"
											aria-pressed={option.key === currentKey}
											disabled={pending}
											onClick={() => void apply({ model_ref: option.ref })}
										>
											<span className="mqs-option-name">{option.label}</span>
											<span className="mqs-option-meta">
												{option.providerLabel}
											</span>
											<span className="mqs-icons" aria-hidden="true">
												{option.vision && <Eye size={12} />}
												{option.reasoning && <Brain size={12} />}
												{option.tools && <Wrench size={12} />}
											</span>
										</button>
									</li>
								))}
							</ul>
						)}
					</div>
					<div className="mqs-section">
						<p className="mqs-heading" id={`${popoverId}-level`}>
							思考深度
						</p>
						<div
							className="mqs-levels"
							role="toolbar"
							aria-labelledby={`${popoverId}-level`}
						>
							{THINKING_LEVELS.map((item) => (
								<button
									key={item.value}
									type="button"
									aria-pressed={item.value === level}
									className="mqs-level-btn"
									disabled={pending}
									onClick={() => void apply({ thinking_level: item.value })}
								>
									{item.label}
								</button>
							))}
						</div>
					</div>
					{error && (
						<p className="mqs-error" role="alert">
							{error}
						</p>
					)}
					<Link
						className="mqs-manage"
						to={settingsPath}
						onClick={() => setIsOpen(false)}
					>
						管理更多模型 →
					</Link>
				</div>
			)}
		</div>
	);
}
