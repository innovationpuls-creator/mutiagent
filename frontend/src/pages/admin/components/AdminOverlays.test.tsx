import {
	cleanup,
	fireEvent,
	render,
	screen,
	waitFor,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { OAuthStatusDialog } from "../../../components/auth/OAuthStatusDialog";
import type { AuthUser } from "../../../types/auth";
import type { BranchCourseNode } from "../../../types/branch";
import { DeleteConfirmModal } from "./DeleteConfirmModal";
import { ProgramDetailDrawer } from "./ProgramDetailDrawer";
import { ResetPasswordModal } from "./ResetPasswordModal";

const account: AuthUser = {
	uid: "account-1",
	username: "测试账号",
	identifier: "student@example.com",
	role: "student",
	school: "示例学校",
	major: "示例专业",
	class_name: "示例班级",
	provider: "password",
	is_active: true,
	created_at: "2026-07-26T00:00:00Z",
	last_login_at: null,
};

const course: BranchCourseNode = {
	course_node_id: "course-1",
	course_or_chapter_theme: "示例课程",
	course_goal: "理解示例课程的学习目标",
	status: "current",
	has_outline: true,
};

function focusTrigger() {
	const trigger = document.createElement("button");
	trigger.textContent = "打开浮层";
	document.body.append(trigger);
	trigger.focus();
	return trigger;
}

afterEach(() => {
	cleanup();
	document.body.replaceChildren();
});

describe("admin overlays", () => {
	it("keeps destructive delete dialog semantic, dismissible with Escape, and restores focus", async () => {
		const trigger = focusTrigger();
		const onClose = vi.fn();
		const { unmount } = render(
			<DeleteConfirmModal
				busy={false}
				deleteTarget={{ type: "single", account }}
				onClose={onClose}
				onConfirm={vi.fn().mockResolvedValue(undefined)}
			/>,
		);

		const dialog = screen.getByRole("dialog", { name: "确认删除 1 个账号？" });
		expect(dialog.getAttribute("aria-modal")).toBe("true");
		expect(document.body.style.overflow).toBe("hidden");

		await waitFor(() => {
			expect(document.activeElement).toBe(
				screen.getByRole("heading", { name: "确认删除 1 个账号？" }),
			);
		});

		fireEvent.keyDown(document, { key: "Escape" });
		expect(onClose).toHaveBeenCalledTimes(1);

		unmount();
		expect(document.activeElement).toBe(trigger);
		expect(document.body.style.overflow).toBe("");
	});

	it("focuses the reset password input and closes with Escape", async () => {
		const onClose = vi.fn();
		render(
			<ResetPasswordModal
				busy={false}
				onClose={onClose}
				onConfirm={vi.fn().mockResolvedValue(undefined)}
				resetPassword=""
				resetTarget={account}
				setResetPassword={vi.fn()}
			/>,
		);

		expect(
			screen
				.getByRole("dialog", { name: "重置密码" })
				.getAttribute("aria-modal"),
		).toBe("true");

		await waitFor(() => {
			expect(document.activeElement).toBe(screen.getByLabelText("新密码"));
		});

		fireEvent.keyDown(document, { key: "Escape" });
		expect(onClose).toHaveBeenCalledTimes(1);
	});

	it("makes QR dialog dismissible with Escape and labels it by its title", async () => {
		const onClose = vi.fn();
		render(<OAuthStatusDialog onClose={onClose} open provider="qq" />);

		const dialog = screen.getByRole("dialog", { name: "使用QQ扫码登录" });
		expect(dialog.getAttribute("aria-modal")).toBe("true");

		await waitFor(() => {
			expect(document.activeElement).toBe(
				screen.getByRole("button", { name: "返回登录" }),
			);
		});

		fireEvent.keyDown(document, { key: "Escape" });
		expect(onClose).toHaveBeenCalledTimes(1);
	});

	it("makes the course drawer semantic, focusable, and dismissible with Escape", async () => {
		const onClose = vi.fn();
		render(
			<ProgramDetailDrawer
				course={course}
				onClose={onClose}
				onUpdateCourse={vi.fn()}
			/>,
		);

		const dialog = screen.getByRole("dialog", { name: "编辑课程大纲" });
		expect(dialog.getAttribute("aria-modal")).toBe("true");

		await waitFor(() => {
			expect(document.activeElement).toBe(
				screen.getByRole("heading", { name: "编辑课程大纲" }),
			);
		});

		fireEvent.keyDown(document, { key: "Escape" });
		expect(onClose).toHaveBeenCalledTimes(1);
	});
});
