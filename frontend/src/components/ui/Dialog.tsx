import { motion, useReducedMotion } from "framer-motion";
import { X } from "lucide-react";
import { type ReactNode, type RefObject, useId, useRef } from "react";
import { useDialogAccessibility } from "./useDialogAccessibility";

export interface DialogProps {
	isOpen: boolean;
	onClose: () => void;
	title?: ReactNode;
	ariaLabel?: string;
	size?: "compact" | "default" | "wide";
	surface?: "light" | "dark";
	closeOnBackdrop?: boolean;
	showCloseButton?: boolean;
	initialFocusRef?: RefObject<HTMLElement>;
	footer?: ReactNode;
	className?: string;
	backdropClassName?: string;
	children: ReactNode;
}

export function Dialog({
	isOpen,
	onClose,
	title,
	ariaLabel,
	size = "default",
	surface = "light",
	closeOnBackdrop = true,
	showCloseButton = true,
	initialFocusRef,
	footer,
	className,
	backdropClassName,
	children,
}: DialogProps) {
	const reduceMotion = useReducedMotion();
	const titleId = useId();
	const defaultTitleRef = useRef<HTMLHeadingElement>(null);
	useDialogAccessibility({
		isOpen,
		onClose,
		initialFocusRef: initialFocusRef ?? defaultTitleRef,
	});

	if (!isOpen) return null;

	const sizeClass =
		size === "compact"
			? "ui-dialog--compact"
			: size === "wide"
				? "ui-dialog--wide"
				: "";

	return (
		<motion.div
			className={["ui-dialog-backdrop", backdropClassName]
				.filter(Boolean)
				.join(" ")}
			initial={{ opacity: 0 }}
			animate={{ opacity: 1 }}
			exit={{ opacity: 0 }}
			transition={reduceMotion ? { duration: 0.1 } : { duration: 0.18 }}
		>
			{closeOnBackdrop ? (
				<button
					type="button"
					tabIndex={-1}
					aria-hidden="true"
					className="ui-backdrop-dismiss"
					onClick={onClose}
				/>
			) : null}
			<section
				role="dialog"
				aria-modal="true"
				aria-labelledby={title ? titleId : undefined}
				aria-label={!title ? ariaLabel : undefined}
				className={[
					"ui-dialog",
					sizeClass,
					surface === "dark" ? "ui-dialog--dark" : "",
					className,
				]
					.filter(Boolean)
					.join(" ")}
				style={{ zIndex: 1 }}
			>
				{(title || showCloseButton) && (
					<header className="ui-dialog-header">
						{title ? (
							<h2
								id={titleId}
								ref={defaultTitleRef}
								tabIndex={-1}
								className="ui-dialog-title"
							>
								{title}
							</h2>
						) : (
							<span />
						)}
						{showCloseButton ? (
							<button
								type="button"
								className="ui-close-btn"
								onClick={onClose}
								aria-label="关闭"
							>
								<X size={18} aria-hidden="true" />
							</button>
						) : null}
					</header>
				)}
				<div className="ui-dialog-body">{children}</div>
				{footer ? <footer className="ui-dialog-footer">{footer}</footer> : null}
			</section>
		</motion.div>
	);
}
