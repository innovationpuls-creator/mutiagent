import type { ReactNode } from "react";

export interface TabItem<T extends string> {
	value: T;
	label: string;
	icon?: ReactNode;
	disabled?: boolean;
}

export interface TabsProps<T extends string> {
	items: ReadonlyArray<TabItem<T>>;
	value: T;
	onChange: (value: T) => void;
	ariaLabel: string;
	className?: string;
	size?: "sm" | "md";
	/**
	 * `tabs` 切换内容面板（role="tab"）；`segmented` 只是筛选/选项切换
	 * （按钮 + aria-pressed），外观一致。
	 */
	mode?: "tabs" | "segmented";
}

export function Tabs<T extends string>({
	items,
	value,
	onChange,
	ariaLabel,
	className,
	size = "md",
	mode = "tabs",
}: TabsProps<T>) {
	const classes = ["ui-tabs", className].filter(Boolean).join(" ");
	const renderLabel = (item: TabItem<T>) => (
		<>
			{item.icon ? <span aria-hidden="true">{item.icon}</span> : null}
			<span>{item.label}</span>
		</>
	);

	if (mode === "segmented") {
		return (
			<fieldset className={classes} data-size={size}>
				<legend className="sr-only">{ariaLabel}</legend>
				{items.map((item) => {
					const selected = item.value === value;
					return (
						<button
							key={item.value}
							type="button"
							aria-pressed={selected}
							data-selected={selected}
							disabled={item.disabled}
							className="ui-tab"
							onClick={() => onChange(item.value)}
						>
							{renderLabel(item)}
						</button>
					);
				})}
			</fieldset>
		);
	}

	return (
		<div
			className={classes}
			role="tablist"
			aria-label={ariaLabel}
			data-size={size}
		>
			{items.map((item) => {
				const selected = item.value === value;
				return (
					<button
						key={item.value}
						type="button"
						role="tab"
						aria-selected={selected}
						data-selected={selected}
						disabled={item.disabled}
						className="ui-tab"
						onClick={() => onChange(item.value)}
					>
						{renderLabel(item)}
					</button>
				);
			})}
		</div>
	);
}
