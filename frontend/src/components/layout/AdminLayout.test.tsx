import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AuthProvider } from "../../contexts/AuthContext";
import { seedAuth } from "../../test/modelConfigHarness";
import { AdminLayout } from "./AdminLayout";

afterEach(() => vi.unstubAllGlobals());

describe("AdminLayout menu", () => {
	it("has a 模型配置 entry pointing to /admin/models (AC-1)", () => {
		seedAuth("admin");
		render(
			<MemoryRouter initialEntries={["/admin/accounts"]}>
				<AuthProvider>
					<AdminLayout />
				</AuthProvider>
			</MemoryRouter>,
		);
		const link = screen.getByRole("link", { name: "模型配置" });
		expect(link.getAttribute("href")).toBe("/admin/models");
	});
});
