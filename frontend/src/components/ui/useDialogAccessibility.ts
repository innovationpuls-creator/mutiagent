import { type RefObject, useEffect, useRef } from "react";

interface UseDialogAccessibilityOptions {
	isOpen: boolean;
	onClose: () => void;
	initialFocusRef: RefObject<HTMLElement>;
}

export function useDialogAccessibility({
	isOpen,
	onClose,
	initialFocusRef,
}: UseDialogAccessibilityOptions) {
	const onCloseRef = useRef(onClose);
	const returnFocusRef = useRef<HTMLElement | null>(null);

	useEffect(() => {
		onCloseRef.current = onClose;
	}, [onClose]);

	useEffect(() => {
		if (!isOpen) return;

		const activeElement = document.activeElement;
		returnFocusRef.current =
			activeElement instanceof HTMLElement ? activeElement : null;
		const previousOverflow = document.body.style.overflow;
		document.body.style.overflow = "hidden";

		const handleKeyDown = (event: KeyboardEvent) => {
			if (event.key === "Escape") {
				event.preventDefault();
				onCloseRef.current();
				return;
			}
			if (event.key !== "Tab") return;
			const dialog = initialFocusRef.current?.closest(
				'[role="dialog"], [role="alertdialog"]',
			);
			const controls = Array.from(
				dialog?.querySelectorAll<HTMLElement>(
					'button:not(:disabled), a[href], input:not(:disabled), textarea:not(:disabled), select:not(:disabled), [tabindex="0"]',
				) ?? [],
			).filter((element) => element.getClientRects().length > 0);
			const first = controls[0],
				last = controls.at(-1);
			if (event.shiftKey && document.activeElement === first) {
				event.preventDefault();
				last?.focus();
			} else if (!event.shiftKey && document.activeElement === last) {
				event.preventDefault();
				first?.focus();
			}
		};

		document.addEventListener("keydown", handleKeyDown);
		const focusTimer = window.setTimeout(() => {
			initialFocusRef.current?.focus();
		}, 0);

		return () => {
			window.clearTimeout(focusTimer);
			document.removeEventListener("keydown", handleKeyDown);
			document.body.style.overflow = previousOverflow;
			returnFocusRef.current?.focus();
			returnFocusRef.current = null;
		};
	}, [initialFocusRef, isOpen]);
}
