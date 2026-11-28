import { AlertCircle, Inbox, LoaderCircle } from "lucide-react";
import type { ReactNode } from "react";

export type FeedbackStateVariant = "loading" | "empty" | "error";

export interface FeedbackStateProps {
	variant: FeedbackStateVariant;
	title: string;
	description?: ReactNode;
	icon?: ReactNode;
	actions?: ReactNode;
	ariaLabel?: string;
	className?: string;
}

export function FeedbackState({
	variant,
	title,
	description,
	icon,
	actions,
	ariaLabel,
	className,
}: FeedbackStateProps) {
	const defaultIcon =
		variant === "error" ? (
			<AlertCircle size={22} aria-hidden="true" />
		) : variant === "loading" ? (
			<LoaderCircle size={22} aria-hidden="true" />
		) : (
			<Inbox size={22} aria-hidden="true" />
		);

	const role = variant === "error" ? "alert" : "status";

	return (
		<section
			className={["ui-feedback", className].filter(Boolean).join(" ")}
			data-variant={variant}
			role={role}
			aria-label={ariaLabel}
		>
			<div className="ui-feedback-icon" aria-hidden="true">
				{icon ?? defaultIcon}
			</div>
			<h2 className="ui-feedback-title">{title}</h2>
			{description ? <p className="ui-feedback-desc">{description}</p> : null}
			{actions ? <div className="ui-feedback-actions">{actions}</div> : null}
		</section>
	);
}
