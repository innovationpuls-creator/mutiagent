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
			if (event.key !== "Escape") return;
			event.preventDefault();
			onCloseRef.current();
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
