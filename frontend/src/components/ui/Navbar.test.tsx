import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import React from "react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AuthProvider } from "../../contexts/AuthContext";
import { Navbar } from "./Navbar";

vi.mock("framer-motion", async () => {
	const actual =
		await vi.importActual<typeof import("framer-motion")>("framer-motion");

	const createMockComponent = (tag: string) => {
		const Component = React.forwardRef<
			HTMLElement,
			React.HTMLAttributes<HTMLElement> & {
				initial?: unknown;
				animate?: unknown;
				exit?: unknown;
				transition?: unknown;
				variants?: unknown;
				layoutId?: unknown;
			}
		>(
			(
				{
					children,
					initial,
					animate,
					exit,
					transition,
					variants,
					layoutId,
					...props
				},
				ref,
			) => {
				return React.createElement(tag, { ...props, ref }, children);
			},
		);
		Component.displayName = `Motion${tag}`;
		return Component;
	};

	return {
		...actual,
		AnimatePresence: ({ children }: { children: React.ReactNode }) => (
			<>{children}</>
		),
		motion: new Proxy(
			{
				div: createMockComponent("div"),
				nav: createMockComponent("nav"),
				span: createMockComponent("span"),
				button: createMockComponent("button"),
			},
			{
				get: (target, prop) => {
					if (prop in target) {
						return target[prop as keyof typeof target];
					}
					if (typeof prop === "string") {
						return createMockComponent(prop);
					}
					return undefined;
				},
			},
		),
		useReducedMotion: () => true,
	};
});

describe("Navbar teacher program import removal", () => {
	let store: Record<string, string>;

	afterEach(() => {
		cleanup();
		vi.restoreAllMocks();
		vi.unstubAllGlobals();
	});

	it("does not show manual teacher program import in the avatar menu", async () => {
		store = {
			"mutiagent-auth": JSON.stringify({
				token: "token-1",
				user: {
					uid: "student-1",
					username: "测试学生",
					identifier: "student@example.com",
					role: "student",
					school: "南山大学",
					major: "软件工程",
					class_name: "一班",
					provider: "password",
					is_active: true,
					created_at: "2026-06-02T00:00:00Z",
					last_login_at: null,
				},
			}),
		};

		vi.stubGlobal("localStorage", {
			getItem: vi.fn((key: string) => store[key] ?? null),
			setItem: vi.fn((key: string, value: string) => {
				store[key] = value;
			}),
			removeItem: vi.fn((key: string) => {
				delete store[key];
			}),
			clear: vi.fn(() => {
				store = {};
			}),
		});

		render(
			<AuthProvider>
				<MemoryRouter>
					<Navbar />
				</MemoryRouter>
			</AuthProvider>,
		);

		fireEvent.click(screen.getByRole("button", { name: "切换个人菜单" }));
		expect(screen.queryByRole("menuitem", { name: /导入人培方案/ })).toBeNull();
		expect(screen.queryByRole("dialog", { name: "导入人培方案" })).toBeNull();
	});
});
