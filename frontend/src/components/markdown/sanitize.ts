import DOMPurify from "dompurify";

export function sanitizeRenderedHtml(html: string): string {
	return DOMPurify.sanitize(html, {
		USE_PROFILES: { html: true, svg: true, svgFilters: true },
	});
}
