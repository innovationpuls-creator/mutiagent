import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import { Outlet } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";
import { AUTH_INVALID_EVENT } from "./api/http";
import { AuthProvider } from "./contexts/AuthContext";
import type { AuthRole } from "./types/auth";

vi.mock("./components/auth/AuthPage", () => ({
	AuthPage: () => <div>Auth Page</div>,
}));

vi.mock("./pages/SproutPage", () => ({
	SproutPage: () => <div>Sprout Page</div>,
}));

vi.mock("./pages/branch/BranchPage", () => ({
	BranchPage: () => <div>Branch Page</div>,
}));

vi.mock("./pages/leaf/LeafPage", () => ({
	LeafPage: () => <div>Leaf Page</div>,
}));

vi.mock("./pages/admin/AdminAccountsPage", () => ({
	AdminAccountsPage: () => <div>Admin Accounts Page</div>,
}));

vi.mock("./pages/admin/AdminKnowledgeBasePage", () => ({
	AdminKnowledgeBasePage: () => <div>Admin Knowledge Base Page</div>,
}));

vi.mock("./pages/admin/AdminProgramsPage", () => ({
	AdminProgramsPage: () => <div>Admin Programs Page</div>,
}));

vi.mock("./components/onboarding/GlobalAiWidget", () => ({
	GlobalAiWidget: () => null,
}));

vi.mock("./components/layout/MainLayout", () => ({
	MainLayout: () => (
		<div>
			<div>Main Layout</div>
			<Outlet />
		</div>
	),
}));

afterEach(() => {
	cleanup();
	vi.unstubAllGlobals();
	window.history.replaceState({}, "", "/");
});

function stubStoredAuth(enabled: boolean, role: AuthRole = "student") {
	vi.stubGlobal("localStorage", {
		getItem: vi.fn((key: string) => {
			if (!enabled || key !== "mutiagent-auth") {
				return null;
			}
			return JSON.stringify({
				token: "token-1",
				user: {
					uid: "user-1",
					username: "测试用户",
					identifier: "user@example.com",
					role,
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
}

function renderApp() {
	return render(
		<AuthProvider>
			<App />
		</AuthProvider>,
	);
}

describe("App routing", () => {
	it("switches from login to sprout when the location changes", async () => {
		stubStoredAuth(true);
		window.history.replaceState({}, "", "/login");

		renderApp();

		expect(screen.getByText("Auth Page")).toBeTruthy();

		await act(async () => {
			window.history.pushState({}, "", "/sprout");
			window.dispatchEvent(new PopStateEvent("popstate"));
			await Promise.resolve();
		});

		await waitFor(() => {
			expect(screen.queryByText("Auth Page")).toBeNull();
			expect(screen.getByText("Main Layout")).toBeTruthy();
			expect(screen.getByText("Sprout Page")).toBeTruthy();
		});
	});

	it("switches between app routes after the location changes", async () => {
		stubStoredAuth(true);
		window.history.replaceState({}, "", "/sprout");

		renderApp();

		await waitFor(() => {
			expect(screen.getByText("Sprout Page")).toBeTruthy();
		});

		await act(async () => {
			window.history.pushState({}, "", "/branch");
			window.dispatchEvent(new PopStateEvent("popstate"));
			await Promise.resolve();
		});

		await waitFor(() => {
			expect(screen.queryByText("Sprout Page")).toBeNull();
			expect(screen.getByText("Branch Page")).toBeTruthy();
		});
	});

	it("renders leaf route for authenticated users", async () => {
		stubStoredAuth(true);
		window.history.replaceState({}, "", "/leaf/year_3_course_1");

		renderApp();

		await waitFor(() => {
			expect(screen.getByText("Main Layout")).toBeTruthy();
			expect(screen.getByText("Leaf Page")).toBeTruthy();
		});
	});

	it("renders admin programs route for authenticated users", async () => {
		stubStoredAuth(true, "admin");
		window.history.replaceState({}, "", "/admin/programs");

		renderApp();

		await waitFor(() => {
			expect(screen.getByText("Admin Programs Page")).toBeTruthy();
		});
	});

	it("renders hidden admin account route for authenticated users", async () => {
		stubStoredAuth(true, "admin");
		window.history.replaceState({}, "", "/admin/accounts");

		renderApp();

		await waitFor(() => {
			expect(screen.getByText("Admin Accounts Page")).toBeTruthy();
		});
	});

	it("renders admin knowledge base route for authenticated admins", async () => {
		stubStoredAuth(true, "admin");
		window.history.replaceState({}, "", "/admin/knowledge-base");

		renderApp();

		await waitFor(() => {
			expect(screen.getByText("Admin Knowledge Base Page")).toBeTruthy();
		});
	});

	it("keeps admin knowledge base route reachable and does not fall back to AIGC entry text", async () => {
		stubStoredAuth(true, "admin");
		window.history.replaceState({}, "", "/admin/knowledge-base");

		renderApp();

		await waitFor(() => {
			expect(screen.getByText("Admin Knowledge Base Page")).toBeTruthy();
		});

		expect(screen.queryByText("AI 教材创作中心")).toBeNull();
		expect(screen.queryByText("一键异步生成教材正文 (AIGC)")).toBeNull();
	});

	it("redirects protected routes to login when no stored auth exists", async () => {
		stubStoredAuth(false);
		window.history.replaceState({}, "", "/branch");

		renderApp();

		await waitFor(() => {
			expect(screen.getByText("Auth Page")).toBeTruthy();
			expect(screen.queryByText("Branch Page")).toBeNull();
		});
	});

	it("returns to login when auth becomes invalid on a protected route", async () => {
		stubStoredAuth(true);
		window.history.replaceState({}, "", "/branch");

		renderApp();

		await waitFor(() => {
			expect(screen.getByText("Branch Page")).toBeTruthy();
		});

		await act(async () => {
			window.dispatchEvent(new Event(AUTH_INVALID_EVENT));
			await Promise.resolve();
		});

		await waitFor(() => {
			expect(screen.getByText("Auth Page")).toBeTruthy();
			expect(screen.queryByText("Branch Page")).toBeNull();
		});
	});
});
