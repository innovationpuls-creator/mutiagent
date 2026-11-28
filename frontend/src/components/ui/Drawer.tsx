import { motion, useReducedMotion } from "framer-motion";
import { X } from "lucide-react";
import { type ReactNode, type RefObject, useId, useRef } from "react";
import { useDialogAccessibility } from "./useDialogAccessibility";

export interface DrawerProps {
	isOpen: boolean;
	onClose: () => void;
	title: ReactNode;
	kicker?: string;
	headerActions?: ReactNode;
	footer?: ReactNode;
	initialFocusRef?: RefObject<HTMLElement>;
	closeAriaLabel?: string;
	className?: string;
	children: ReactNode;
}

export function Drawer({
	isOpen,
	onClose,
	title,
	kicker,
	headerActions,
	footer,
	initialFocusRef,
	closeAriaLabel = "关闭面板",
	className,
	children,
}: DrawerProps) {
	const reduceMotion = useReducedMotion();
	const titleId = useId();
	const defaultTitleRef = useRef<HTMLHeadingElement>(null);
	useDialogAccessibility({
		isOpen,
		onClose,
		initialFocusRef: initialFocusRef ?? defaultTitleRef,
	});

	if (!isOpen) return null;

	return (
		<div className="ui-drawer-backdrop">
			<button
				type="button"
				tabIndex={-1}
				aria-hidden="true"
				className="ui-backdrop-dismiss"
				onClick={onClose}
			/>
			<motion.aside
				role="dialog"
				aria-modal="true"
				aria-labelledby={titleId}
				className={["ui-drawer", className].filter(Boolean).join(" ")}
				initial={reduceMotion ? { opacity: 0 } : { x: "100%" }}
				animate={reduceMotion ? { opacity: 1 } : { x: 0 }}
				exit={reduceMotion ? { opacity: 0 } : { x: "100%" }}
				transition={
					reduceMotion
						? { duration: 0.12 }
						: { duration: 0.42, ease: [0.33, 1, 0.68, 1] }
				}
			>
				<header className="ui-drawer-header">
					<div>
						{kicker ? <p className="admin-kicker">{kicker}</p> : null}
						<h2
							id={titleId}
							ref={defaultTitleRef}
							tabIndex={-1}
							className="ui-drawer-title"
						>
							{title}
						</h2>
					</div>
					<div className="ui-dialog-footer">
						{headerActions}
						<button
							type="button"
							className="ui-close-btn"
							onClick={onClose}
							aria-label={closeAriaLabel}
						>
							<X size={18} aria-hidden="true" />
						</button>
					</div>
				</header>
				<div className="ui-drawer-body">{children}</div>
				{footer ? <footer className="ui-drawer-footer">{footer}</footer> : null}
			</motion.aside>
		</div>
	);
}
