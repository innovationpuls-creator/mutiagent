import type { ReactNode } from "react";

export type StatusBadgeVariant = "whisper" | "pill";
export type StatusBadgeTone =
	| "neutral"
	| "success"
	| "warning"
	| "error"
	| "info"
	| "accent";

export interface StatusBadgeProps {
	children: ReactNode;
	variant?: StatusBadgeVariant;
	tone?: StatusBadgeTone;
	surface?: "light" | "dark";
	showDot?: boolean;
	className?: string;
}

export function StatusBadge({
	children,
	variant = "whisper",
	tone = "neutral",
	surface = "light",
	showDot = variant === "whisper",
	className,
}: StatusBadgeProps) {
	return (
		<span
			className={["ui-status-badge", className].filter(Boolean).join(" ")}
			data-variant={variant}
			data-tone={tone}
			data-surface={surface}
		>
			{showDot ? <span className="ui-status-dot" aria-hidden="true" /> : null}
			<span>{children}</span>
		</span>
	);
}
