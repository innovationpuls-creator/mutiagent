import {
	act,
	cleanup,
	fireEvent,
	render,
	screen,
} from "@testing-library/react";
import React from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { AuthUser } from "../../types/auth";
import type { BranchCourseNode } from "../../types/branch";
import { AdminProgramsPage } from "./AdminProgramsPage";

const adminProgramApiMocks = vi.hoisted(() => ({
	getProgram: vi.fn(),
	publishProgram: vi.fn(),
}));

const adminDataApiMocks = vi.hoisted(() => ({
	programs: vi.fn(),
}));

const authMocks = vi.hoisted(() => ({
	logout: vi.fn(),
	user: {
		uid: "admin-1",
		username: "测试管理员",
		identifier: "admin@example.com",
		role: "admin",
		school: "南山大学",
		major: "软件工程",
		class_name: "一班",
		provider: "password",
		is_active: true,
		created_at: "2026-06-02T00:00:00Z",
		last_login_at: null,
	} as AuthUser,
}));

vi.mock("../../contexts/AuthContext", () => ({
	useAuth: () => ({
		token: "test-token",
		isAuthReady: true,
		user: authMocks.user,
		login: vi.fn(),
		logout: authMocks.logout,
	}),
}));

vi.mock("../../api/adminProgram", () => ({
	adminProgramApi: {
		getProgram: adminProgramApiMocks.getProgram,
		publishProgram: adminProgramApiMocks.publishProgram,
	},
}));

vi.mock("../../api/adminData", () => ({
	adminDataApi: {
		programs: adminDataApiMocks.programs,
	},
}));

vi.mock("../../components/graph/OrganicCanvas", () => ({
	OrganicCanvas: () => <div data-testid="organic-canvas" />,
}));

vi.mock("framer-motion", async () => {
	const actual =
		await vi.importActual<typeof import("framer-motion")>("framer-motion");

	const createMockComponent = (tag: string) => {
		const Component = React.forwardRef<
			HTMLElement,
			React.HTMLAttributes<HTMLElement>
		>(({ children, ...props }, ref) => {
			const { transition, animate, exit, initial, ...cleanProps } =
				props as Record<string, unknown>;
			return React.createElement(tag, { ...cleanProps, ref }, children);
		});
		Component.displayName = `mock-${tag}`;
		return Component;
	};

	return {
		...actual,
		motion: {
			main: createMockComponent("main"),
			div: createMockComponent("div"),
			section: createMockComponent("section"),
			p: createMockComponent("p"),
			header: createMockComponent("header"),
			aside: createMockComponent("aside"),
			footer: createMockComponent("footer"),
			button: actual.motion.button,
		},
		AnimatePresence: ({ children }: { children: React.ReactNode }) => (
			<>{children}</>
		),
		useReducedMotion: () => false,
	};
});

class ResizeObserverMock {
	observe() {}
	unobserve() {}
	disconnect() {}
}

const flushProgramLoad = async () => {
	await act(async () => {
		await new Promise((resolve) => setTimeout(resolve, 0));
	});
};

describe("AdminProgramsPage manual editing and JSON import/export", () => {
	beforeEach(() => {
		vi.stubGlobal("ResizeObserver", ResizeObserverMock);
		vi.clearAllMocks();
		adminProgramApiMocks.getProgram.mockReset();
		adminProgramApiMocks.publishProgram.mockReset();
		adminDataApiMocks.programs.mockReset();
		adminDataApiMocks.programs.mockResolvedValue([]);
	});

	afterEach(() => {
		cleanup();
		vi.unstubAllGlobals();
	});

	it("shows manual creation and JSON import actions when no program exists", async () => {
		adminProgramApiMocks.getProgram.mockResolvedValue(null);

		render(<AdminProgramsPage />);
		await flushProgramLoad();

		expect(screen.getByText("创建或导入培养方案")).toBeTruthy();
		expect(screen.getByRole("button", { name: "手动添加课程" })).toBeTruthy();
		expect(screen.getByRole("button", { name: "导入 JSON" })).toBeTruthy();
		expect(screen.getByRole("button", { name: "下载 JSON 模板" })).toBeTruthy();
		expect(screen.queryByText(/PDF, DOCX/i)).toBeNull();
	});

	it("imports real courses from a valid JSON file without mock fixtures", async () => {
		adminProgramApiMocks.getProgram.mockResolvedValue(null);

		render(<AdminProgramsPage />);
		await flushProgramLoad();

		const input = screen.getByTestId("json-file-input") as HTMLInputElement;
		const jsonPayload = JSON.stringify([
			{
				course_node_id: "net_101",
				course_or_chapter_theme: "计算机网络原理",
				course_goal: "掌握分层网络协议栈与路由原理",
				time_arrangement: { semester_scope: "4", duration: "48学时/3学分" },
				key_points: ["TCP 拥塞控制", "OSPF 路由"],
			},
		]);
		const jsonFile = new File([jsonPayload], "curriculum.json", {
			type: "application/json",
		});

		await act(async () => {
			fireEvent.change(input, { target: { files: [jsonFile] } });
		});

		expect(await screen.findByText("大纲对齐编辑")).toBeTruthy();
		expect(screen.getByText("计算机网络原理")).toBeTruthy();
		expect(screen.queryByText("高等数学 I")).toBeNull();
	});

	it("rejects non-JSON files with explicit error state", async () => {
		adminProgramApiMocks.getProgram.mockResolvedValue(null);

		render(<AdminProgramsPage />);
		await flushProgramLoad();

		const input = screen.getByTestId("json-file-input");
		const invalidFile = new File(["pdf bytes"], "syllabus.pdf", {
			type: "application/pdf",
		});

		await act(async () => {
			fireEvent.change(input, { target: { files: [invalidFile] } });
		});

		expect(screen.getByText("JSON 导入失败")).toBeTruthy();
		expect(screen.getByText(/仅支持导入 \.json 格式/)).toBeTruthy();

		await act(async () => {
			fireEvent.click(screen.getByRole("button", { name: "返回" }));
		});

		expect(screen.getByText("创建或导入培养方案")).toBeTruthy();
	});

	it("rejects malformed JSON schema cleanly", async () => {
		adminProgramApiMocks.getProgram.mockResolvedValue(null);

		render(<AdminProgramsPage />);
		await flushProgramLoad();

		const input = screen.getByTestId("json-file-input");
		const invalidJsonFile = new File(
			[JSON.stringify([{ course_goal: "missing id and theme" }])],
			"bad.json",
			{ type: "application/json" },
		);

		await act(async () => {
			fireEvent.change(input, { target: { files: [invalidJsonFile] } });
		});

		expect(await screen.findByText("JSON 导入失败")).toBeTruthy();
		expect(
			screen.getByText(
				/缺少必填字段 course_node_id 或 course_or_chapter_theme/,
			),
		).toBeTruthy();
	});

	it("allows manual course creation, editing, deletion, and publishing via API", async () => {
		adminProgramApiMocks.getProgram.mockResolvedValue(null);
		adminProgramApiMocks.publishProgram.mockResolvedValue({
			program_id: "program-1",
		});

		render(<AdminProgramsPage />);
		await flushProgramLoad();

		await act(async () => {
			fireEvent.click(screen.getByRole("button", { name: "手动添加课程" }));
		});

		expect(screen.getByText("编辑课程大纲")).toBeTruthy();
		await act(async () => {
			fireEvent.change(screen.getByLabelText("课程名称"), {
				target: { value: "编译原理实战" },
			});
		});

		await act(async () => {
			fireEvent.click(screen.getByLabelText("关闭课程大纲抽屉"));
		});

		expect(screen.getByText("编译原理实战")).toBeTruthy();

		await act(async () => {
			fireEvent.click(screen.getByRole("button", { name: "保存并发布" }));
		});

		expect(adminProgramApiMocks.publishProgram).toHaveBeenCalledWith(
			"test-token",
			[
				expect.objectContaining({
					course_node_id: "course_1",
					course_or_chapter_theme: "编译原理实战",
					is_custom: true,
				}),
			],
			{ school: "南山大学", major: "软件工程", className: "一班" },
		);
		expect(screen.getByText("人培方案已成功发布并对齐！")).toBeTruthy();
	});

	it("exports loaded program courses as JSON", async () => {
		const mockSavedCourses: BranchCourseNode[] = [
			{
				course_node_id: "ds_101",
				course_or_chapter_theme: "高级数据结构",
				course_goal: "掌握高级红黑树及图算法",
				status: "locked",
				has_outline: false,
				is_custom: true,
				time_arrangement: { semester_scope: "4", duration: "48学时" },
			},
		];
		adminProgramApiMocks.getProgram.mockResolvedValue({
			program_id: "program-123",
			admin_uid: "admin-1",
			admin_name: "测试管理员",
			admin_identifier: "admin@example.com",
			school: "南山大学",
			major: "软件工程",
			class_name: "一班",
			courses: mockSavedCourses,
			published_at: "2026-06-15T10:00:00Z",
			updated_at: "2026-06-15T10:00:00Z",
		});

		const createObjectUrlMock = vi.fn(() => "blob:program");
		const revokeObjectUrlMock = vi.fn();
		vi.stubGlobal("URL", {
			createObjectURL: createObjectUrlMock,
			revokeObjectURL: revokeObjectUrlMock,
		});
		const clickSpy = vi
			.spyOn(HTMLAnchorElement.prototype, "click")
			.mockImplementation(() => {});

		render(<AdminProgramsPage />);
		await flushProgramLoad();

		expect(screen.getByText("高级数据结构")).toBeTruthy();
		await act(async () => {
			fireEvent.click(screen.getByRole("button", { name: "导出 JSON" }));
		});

		expect(createObjectUrlMock).toHaveBeenCalled();
		expect(clickSpy).toHaveBeenCalled();
		expect(revokeObjectUrlMock).toHaveBeenCalledWith("blob:program");
	});

	it("shows toast warning when attempting to publish with incomplete scope fields", async () => {
		adminProgramApiMocks.getProgram.mockResolvedValue({
			program_id: "program-1",
			admin_uid: "admin-1",
			admin_name: "测试管理员",
			admin_identifier: "admin@example.com",
			school: "南山大学",
			major: "软件工程",
			class_name: "",
			courses: [
				{
					course_node_id: "math_1",
					course_or_chapter_theme: "高等数学 I",
					course_goal: "掌握微积分",
					status: "locked",
					has_outline: false,
					is_custom: true,
					time_arrangement: { semester_scope: "1", duration: "64学时/4学分" },
				},
			],
			published_at: "2026-06-15T10:00:00Z",
			updated_at: "2026-06-15T10:00:00Z",
		});

		render(<AdminProgramsPage />);
		await flushProgramLoad();

		await act(async () => {
			fireEvent.click(screen.getByRole("button", { name: "保存并发布" }));
		});

		expect(
			screen.getByText("请填写学校、专业、班级；这些值必须和学生账号完全一致"),
		).toBeTruthy();
		expect(adminProgramApiMocks.publishProgram).not.toHaveBeenCalled();
	});

	it("renders SVG bar charts when switching to the graph tab", async () => {
		adminProgramApiMocks.getProgram.mockResolvedValue({
			program_id: "program-1",
			admin_uid: "admin-1",
			admin_name: "测试管理员",
			admin_identifier: "admin@example.com",
			school: "南山大学",
			major: "软件工程",
			class_name: "一班",
			courses: [
				{
					course_node_id: "math_1",
					course_or_chapter_theme: "高等数学 I",
					course_goal: "掌握微积分",
					status: "locked",
					has_outline: false,
					is_custom: true,
					time_arrangement: { semester_scope: "1", duration: "64学时/4学分" },
				},
			],
			published_at: "2026-06-15T10:00:00Z",
			updated_at: "2026-06-15T10:00:00Z",
		});

		render(<AdminProgramsPage />);
		await flushProgramLoad();

		await act(async () => {
			fireEvent.click(screen.getByRole("tab", { name: "方案依赖图谱" }));
		});

		expect(screen.getByRole("heading", { name: "方案依赖图谱" })).toBeTruthy();
		expect(screen.getByText("学期学分分布")).toBeTruthy();
		expect(screen.getByText("学期课时分布")).toBeTruthy();
	});
});
