import { type HTMLMotionProps, motion } from "framer-motion";
import { forwardRef, type ReactNode } from "react";

export type ButtonVariant =
	| "primary"
	| "secondary"
	| "ghost"
	| "danger"
	| "icon"
	| "dark";

export type ButtonSize = "sm" | "md";

export interface ButtonProps extends HTMLMotionProps<"button"> {
	variant?: ButtonVariant;
	size?: ButtonSize;
	loading?: boolean;
	icon?: ReactNode;
	children?: ReactNode;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
	function Button(
		{
			variant = "primary",
			size = "md",
			loading = false,
			icon,
			children,
			className,
			disabled,
			type = "button",
			...buttonProps
		},
		ref,
	) {
		const classes = [
			"button",
			`button-${variant}`,
			size === "sm" ? "button-sm" : "",
			className,
		]
			.filter(Boolean)
			.join(" ");

		return (
			<motion.button
				ref={ref}
				type={type}
				className={classes}
				disabled={disabled || loading}
				whileHover={
					disabled || loading
						? undefined
						: { scale: 1.02, boxShadow: "0 8px 24px oklch(82% 0.08 60 / 0.4)" }
				}
				whileTap={disabled || loading ? undefined : { scale: 0.98 }}
				{...buttonProps}
			>
				{icon ? (
					<span className="button-icon-glyph" aria-hidden="true">
						{icon}
					</span>
				) : null}
				{loading ? (
					<span>处理中</span>
				) : children !== undefined && children !== null ? (
					<span>{children}</span>
				) : null}
			</motion.button>
		);
	},
);
