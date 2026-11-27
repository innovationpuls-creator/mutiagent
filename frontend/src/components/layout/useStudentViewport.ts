import { useLayoutEffect } from "react";

// Soft keyboards can resize the visual viewport without resizing CSS vh units.
export function useStudentViewport() {
	useLayoutEffect(() => {
		const viewport = window.visualViewport;
		const style = document.documentElement.style;
		const update = () => {
			const height = viewport?.height ?? window.innerHeight;
			const inset = Math.max(
				0,
				window.innerHeight - height - (viewport?.offsetTop ?? 0),
			);
			style.setProperty("--student-viewport-height", `${height}px`);
			style.setProperty("--student-keyboard-inset", `${inset}px`);
		};
		update();
		window.addEventListener("resize", update);
		viewport?.addEventListener("resize", update);
		viewport?.addEventListener("scroll", update);
		return () => {
			window.removeEventListener("resize", update);
			viewport?.removeEventListener("resize", update);
			viewport?.removeEventListener("scroll", update);
			style.removeProperty("--student-viewport-height");
			style.removeProperty("--student-keyboard-inset");
		};
	}, []);
}
