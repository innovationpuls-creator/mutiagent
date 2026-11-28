import { useSyncExternalStore } from "react";

function canMatchMedia() {
	return (
		typeof window !== "undefined" && typeof window.matchMedia === "function"
	);
}

/**
 * 订阅 CSS 媒体查询。没有 matchMedia（如 jsdom）时返回 false，
 * 页面按窄屏分支渲染。
 */
export function useMediaQuery(query: string): boolean {
	return useSyncExternalStore(
		(onChange) => {
			if (!canMatchMedia()) return () => {};
			const mediaQuery = window.matchMedia(query);
			mediaQuery.addEventListener("change", onChange);
			return () => mediaQuery.removeEventListener("change", onChange);
		},
		() => (canMatchMedia() ? window.matchMedia(query).matches : false),
		() => false,
	);
}
