import {
	cleanup,
	fireEvent,
	render,
	screen,
	waitFor,
} from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { GlobalAiWidget } from "../components/onboarding/GlobalAiWidget";
import { AiWidgetProvider } from "../contexts/AiWidgetContext";
import { AuthProvider } from "../contexts/AuthContext";
import { SproutPage } from "./SproutPage";

vi.mock("../components/home/SproutHero", () => ({
	SproutHero: () => {
		return (
			<div>
				<div>Sprout Hero</div>
			</div>
		);
	},
}));

afterEach(() => {
	cleanup();
	vi.restoreAllMocks();
	vi.unstubAllGlobals();
	vi.useRealTimers();
});

describe("SproutPage", () => {
	it("shows the homepage immediately and opens AI only on demand", async () => {
		vi.stubGlobal("scrollTo", vi.fn());
		const sessionStorageGetItem = vi.fn(() => null);
		const sessionStorageRemoveItem = vi.fn();
		vi.stubGlobal("sessionStorage", {
			getItem: sessionStorageGetItem,
			removeItem: sessionStorageRemoveItem,
		});
		vi.stubGlobal("localStorage", {
			getItem: vi.fn((key: string) => {
				if (key !== "mutiagent-auth") return null;
				return JSON.stringify({
					token: "token-1",
					user: {
						uid: "user-1",
						username: "测试用户",
						identifier: "user@example.com",
						provider: "password",
						is_active: true,
						created_at: "2026-06-02T00:00:00Z",
						last_login_at: null,
					},
				});
			}),
			setItem: vi.fn(),
			removeItem: vi.fn(),
		});

		render(
			<AuthProvider>
				<MemoryRouter
					initialEntries={[
						{ pathname: "/sprout", state: { isFirstLogin: true } },
					]}
					future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
				>
					<AiWidgetProvider>
						<Routes>
							<Route path="/sprout" element={<SproutPage />} />
						</Routes>
						<GlobalAiWidget />
					</AiWidgetProvider>
				</MemoryRouter>
			</AuthProvider>,
		);

		expect(screen.getByText("Sprout Hero")).toBeTruthy();
		expect(
			document.querySelector('[data-sprout-init-overlay="true"]'),
		).toBeNull();
		fireEvent.click(
			await screen.findByRole("button", { name: "打开 AI 学习助手" }),
		);
		await waitFor(() =>
			expect(screen.getByLabelText("AI 基础画像对话")).toBeTruthy(),
		);
		fireEvent.click(screen.getByRole("button", { name: "收起 AI 对话" }));
		expect(sessionStorageRemoveItem).not.toHaveBeenCalledWith(
			"mutiagent-sprout-init-overlay",
		);
	});
});
