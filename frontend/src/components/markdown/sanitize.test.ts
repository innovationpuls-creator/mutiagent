import { describe, expect, it } from "vitest";
import { sanitizeRenderedHtml } from "./sanitize";

describe("sanitizeRenderedHtml", () => {
	it("preserves Mermaid SVG structure while removing executable markup", () => {
		const sanitized = sanitizeRenderedHtml(
			'<svg viewBox="0 0 10 10" onload="alert(1)"><script>alert(1)</script><path d="M0 0" /></svg>',
		);

		expect(sanitized).toContain("<svg");
		expect(sanitized).toContain("viewBox");
		expect(sanitized).toContain("<path");
		expect(sanitized).not.toContain("<script");
		expect(sanitized).not.toContain("onload");
	});

	it("preserves Prism token markup while removing unsafe URL attributes", () => {
		const sanitized = sanitizeRenderedHtml(
			'<span class="token keyword">const</span><a href="javascript:alert(1)">bad</a>',
		);

		expect(sanitized).toContain('class="token keyword"');
		expect(sanitized).not.toContain("javascript:");
	});
});
