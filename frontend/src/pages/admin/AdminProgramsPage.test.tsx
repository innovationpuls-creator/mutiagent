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

const teacherProgramApiMocks = vi.hoisted(() => ({
	getTeacherProgram: vi.fn(),
	publishTeacherProgram: vi.fn(),
}));

const adminDataApiMocks = vi.hoisted(() => ({
	programs: vi.fn(),
}));

const defaultAuthUser: AuthUser = {
	uid: "teacher-1",
	username: "测试教师",
	identifier: "teacher@example.com",
	role: "admin",
	school: "南山大学",
	major: "软件工程",
	class_name: "一班",
	provider: "password",
	is_active: true,
	created_at: "2026-06-02T00:00:00Z",
	last_login_at: null,
};

const authMocks = vi.hoisted(() => ({
	logout: vi.fn(),
	user: {
		uid: "teacher-1",
		username: "测试教师",
		identifier: "teacher@example.com",
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

vi.mock("../../api/teacherProgram", () => ({
	teacherProgramApi: {
		getTeacherProgram: teacherProgramApiMocks.getTeacherProgram,
		publishTeacherProgram: teacherProgramApiMocks.publishTeacherProgram,
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

const navigateMock = vi.fn();
vi.mock("react-router-dom", async () => {
	const actual =
		await vi.importActual<typeof import("react-router-dom")>(
			"react-router-dom",
		);
	return {
		...actual,
		useNavigate: () => navigateMock,
	};
});

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

describe("AdminProgramsPage State Machine & localStorage Saves", () => {
	beforeEach(() => {
		vi.stubGlobal("ResizeObserver", ResizeObserverMock);
		vi.clearAllMocks();
		teacherProgramApiMocks.getTeacherProgram.mockReset();
		teacherProgramApiMocks.publishTeacherProgram.mockReset();
		adminDataApiMocks.programs.mockReset();
		adminDataApiMocks.programs.mockResolvedValue([]);
	});

	afterEach(() => {
		cleanup();
		vi.unstubAllGlobals();
	});

	it("shows empty state when no program is present in backend", async () => {
		teacherProgramApiMocks.getTeacherProgram.mockResolvedValue(null);

		render(<AdminProgramsPage />);
		await flushProgramLoad();

		expect(screen.getByText("拖拽或点击上传培养方案文档")).toBeTruthy();
	});

	it("transitions to loading state and then to editor on successful file upload", async () => {
		teacherProgramApiMocks.getTeacherProgram.mockResolvedValue(null);

		render(<AdminProgramsPage />);
		await flushProgramLoad();

		// Simulate drag and drop
		const dropzone = screen.getByTestId("dropzone");
		const mockFile = new File(["dummy content"], "syllabus.pdf", {
			type: "application/pdf",
		});

		// Trigger file upload via drop
		await act(async () => {
			fireEvent.drop(dropzone, {
				dataTransfer: {
					files: [mockFile],
				},
			});
		});

		// Should show loading status
		expect(screen.getByText("正在读取培养方案并由AI对齐大纲...")).toBeTruthy();

		// Advance mock timer or wait for finished
		await act(async () => {
			await new Promise((resolve) => setTimeout(resolve, 3100));
		});

		// Editor layout headers
		expect(screen.getByText("大纲对齐编辑")).toBeTruthy();
		expect(screen.getByText("高等数学 I")).toBeTruthy();
	});

	it("shows error panel when file format validation fails", async () => {
		teacherProgramApiMocks.getTeacherProgram.mockResolvedValue(null);

		render(<AdminProgramsPage />);
		await flushProgramLoad();

		const dropzone = screen.getByTestId("dropzone");
		const mockFile = new File(["dummy"], "invalid.exe", {
			type: "application/octet-stream",
		});

		await act(async () => {
			fireEvent.drop(dropzone, {
				dataTransfer: {
					files: [mockFile],
				},
			});
		});

		expect(screen.getByText("文件解析失败")).toBeTruthy();
		expect(screen.getByText(/不支持的文件类型/i)).toBeTruthy();

		// Click retry button
		const retryBtn = screen.getByRole("button", { name: "重新上传" });
		await act(async () => {
			fireEvent.click(retryBtn);
		});

		expect(screen.getByText("拖拽或点击上传培养方案文档")).toBeTruthy();
	});

	it("shows error panel when file size exceeds 20MB", async () => {
		teacherProgramApiMocks.getTeacherProgram.mockResolvedValue(null);

		render(<AdminProgramsPage />);
		await flushProgramLoad();

		const dropzone = screen.getByTestId("dropzone");
		// Create file exceeding 20MB (21MB)
		const mockFile = new File(
			[new Uint8Array(21 * 1024 * 1024)],
			"huge_syllabus.pdf",
			{ type: "application/pdf" },
		);

		await act(async () => {
			fireEvent.drop(dropzone, {
				dataTransfer: {
					files: [mockFile],
				},
			});
		});

		expect(screen.getByText("文件解析失败")).toBeTruthy();
		expect(screen.getByText(/文件大小超出20MB/i)).toBeTruthy();
	});

	it("loads and displays existing program correctly", async () => {
		const mockSavedCourses: BranchCourseNode[] = [
			{
				course_node_id: "ds_101",
				course_or_chapter_theme: "高级数据结构",
				course_goal: "掌握高级红黑树及图算法",
				status: "locked",
				has_outline: false,
				is_custom: true,
				time_arrangement: { semester_scope: "4", duration: "48学时" },
				key_points: ["红黑树", "伸展树", "并查集"],
				difficult_points: ["双旋转"],
				acceptance_criteria: ["OJ通过"],
			},
		];

		teacherProgramApiMocks.getTeacherProgram.mockResolvedValue({
			program_id: "program-123",
			teacher_uid: "teacher-1",
			teacher_name: "测试教师",
			teacher_identifier: "teacher@example.com",
			school: "南山大学",
			major: "软件工程",
			class_name: "一班",
			courses: mockSavedCourses,
			published_at: "2026-06-15T10:00:00Z",
			updated_at: "2026-06-15T10:00:00Z",
		});

		render(<AdminProgramsPage />);
		await flushProgramLoad();

		// Check program headers loaded
		expect(screen.getByText("高级数据结构")).toBeTruthy();
		// Selected fields values
		expect(screen.getByDisplayValue("南山大学")).toBeTruthy();
		expect(screen.getByDisplayValue("软件工程")).toBeTruthy();
		expect(screen.getByDisplayValue("一班")).toBeTruthy();
	});

	it("allows editing course details and saves successfully via API", async () => {
		const mockSavedCourses = [
			{
				course_node_id: "math_1",
				course_or_chapter_theme: "高等数学 I",
				status: "locked",
				has_outline: false,
				is_custom: false,
				time_arrangement: { semester_scope: "1", duration: "64学时/4学分" },
			},
		];
		teacherProgramApiMocks.getTeacherProgram.mockResolvedValue({
			program_id: "program-1",
			teacher_uid: "teacher-1",
			teacher_name: "测试教师",
			teacher_identifier: "teacher@example.com",
			school: "南山大学",
			major: "软件工程",
			class_name: "一班",
			courses: mockSavedCourses,
			published_at: "2026-06-15T10:00:00Z",
			updated_at: "2026-06-15T10:00:00Z",
		});

		render(<AdminProgramsPage />);
		await flushProgramLoad();

		// Click on course row to edit
		const courseRow = screen.getByText("高等数学 I");
		await act(async () => {
			fireEvent.click(courseRow);
		});

		// Detail drawer should appear
		expect(screen.getByText("编辑课程大纲")).toBeTruthy();

		// Modify title in input
		const titleInput = screen.getByLabelText("课程名称");
		await act(async () => {
			fireEvent.change(titleInput, { target: { value: "高等数学 A" } });
		});

		// Close drawer
		const closeBtn = screen.getByText("✕");
		await act(async () => {
			fireEvent.click(closeBtn);
		});

		// Check the row reflects the update
		expect(screen.getByText("高等数学 A")).toBeTruthy();

		// Save and publish
		teacherProgramApiMocks.publishTeacherProgram.mockResolvedValue({
			status: "success",
		});
		const saveBtn = screen.getByRole("button", { name: "保存并发布" });
		await act(async () => {
			fireEvent.click(saveBtn);
		});

		expect(teacherProgramApiMocks.publishTeacherProgram).toHaveBeenCalled();
		expect(screen.getByText("人培方案已成功发布并对齐！")).toBeTruthy();
	});

	it("shows toast warning when attempting to publish with incomplete scope fields", async () => {
		const mockSavedCourses = [
			{
				course_node_id: "math_1",
				course_or_chapter_theme: "高等数学 I",
				status: "locked",
				has_outline: false,
				is_custom: false,
				time_arrangement: { semester_scope: "1", duration: "64学时/4学分" },
			},
		];
		teacherProgramApiMocks.getTeacherProgram.mockResolvedValue({
			program_id: "program-1",
			teacher_uid: "teacher-1",
			teacher_name: "测试教师",
			teacher_identifier: "teacher@example.com",
			school: "南山大学",
			major: "软件工程",
			class_name: "", // Incomplete class name
			courses: mockSavedCourses,
			published_at: "2026-06-15T10:00:00Z",
			updated_at: "2026-06-15T10:00:00Z",
		});

		render(<AdminProgramsPage />);
		await flushProgramLoad();

		const saveBtn = screen.getByRole("button", { name: "保存并发布" });
		await act(async () => {
			fireEvent.click(saveBtn);
		});

		expect(
			screen.getByText("请填写学校、专业、班级；这些值必须和学生账号完全一致"),
		).toBeTruthy();
		expect(teacherProgramApiMocks.publishTeacherProgram).not.toHaveBeenCalled();
	});

	it("renders SVG bar charts (credits and hours) when switching to the graph tab", async () => {
		const mockSavedCourses = [
			{
				course_node_id: "math_1",
				course_or_chapter_theme: "高等数学 I",
				status: "locked",
				has_outline: false,
				is_custom: false,
				time_arrangement: { semester_scope: "1", duration: "64学时/4学分" },
			},
		];
		teacherProgramApiMocks.getTeacherProgram.mockResolvedValue({
			program_id: "program-1",
			teacher_uid: "teacher-1",
			teacher_name: "测试教师",
			teacher_identifier: "teacher@example.com",
			school: "南山大学",
			major: "软件工程",
			class_name: "一班",
			courses: mockSavedCourses,
			published_at: "2026-06-15T10:00:00Z",
			updated_at: "2026-06-15T10:00:00Z",
		});

		render(<AdminProgramsPage />);
		await flushProgramLoad();

		// Click on the graph tab
		const graphTab = screen.getByRole("button", { name: "方案依赖图谱" });
		await act(async () => {
			fireEvent.click(graphTab);
		});

		// Verify graph title and stats distribution panel exist
		expect(screen.getByRole("heading", { name: "方案依赖图谱" })).toBeTruthy();
		expect(
			screen.getByText("学期学分分布 (Credits per Semester)"),
		).toBeTruthy();
		expect(screen.getByText("学期课时分布 (Hours per Semester)")).toBeTruthy();
	});
});
