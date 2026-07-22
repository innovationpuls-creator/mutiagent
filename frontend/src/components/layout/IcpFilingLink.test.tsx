import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { IcpFilingLink } from "./IcpFilingLink";

afterEach(cleanup);

describe("IcpFilingLink", () => {
	it("does not render an empty filing link", () => {
		const { container } = render(<IcpFilingLink filingNumber="" />);

		expect(container).toBeEmptyDOMElement();
	});

	it("renders the exact filing number and Ministry of Industry link", () => {
		render(<IcpFilingLink filingNumber="粤ICP备2026100568号-1" />);

		const link = screen.getByRole("link", {
			name: "粤ICP备2026100568号-1",
		});
		expect(link).toHaveAttribute("href", "https://beian.miit.gov.cn/");
		expect(link).toHaveAttribute("target", "_blank");
		expect(link).toHaveAttribute("rel", "noreferrer");
	});
});
