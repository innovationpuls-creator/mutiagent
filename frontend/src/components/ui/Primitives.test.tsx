import {
	cleanup,
	fireEvent,
	render,
	screen,
	waitFor,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Button } from "./Button";
import { ConfirmDialog } from "./ConfirmDialog";
import { Drawer } from "./Drawer";
import { FeedbackState } from "./FeedbackState";
import { StatusBadge } from "./StatusBadge";
import { Tabs } from "./Tabs";
import { SelectField, TextAreaField, TextField } from "./TextField";

afterEach(() => {
	cleanup();
	document.body.replaceChildren();
});

describe("UI Primitives", () => {
	it("renders Button variants and handles loading/disabled states", () => {
		const onClick = vi.fn();
		render(
			<>
				<Button variant="primary" onClick={onClick}>
					提交
				</Button>
				<Button variant="danger" loading>
					删除
				</Button>
			</>,
		);
		fireEvent.click(screen.getByRole("button", { name: "提交" }));
		expect(onClick).toHaveBeenCalledTimes(1);
		expect(
			(screen.getByRole("button", { name: "处理中" }) as HTMLButtonElement)
				.disabled,
		).toBe(true);
	});

	it("renders TextField, TextAreaField, and SelectField with error state", () => {
		render(
			<>
				<TextField label="邮箱" errorMessage="邮箱格式不正确" />
				<TextAreaField label="备注" helperText="可选说明" />
				<SelectField label="角色" defaultValue="student">
					<option value="student">学生</option>
					<option value="admin">管理员</option>
				</SelectField>
			</>,
		);

		const emailInput = screen.getByLabelText("邮箱");
		expect(emailInput.getAttribute("aria-invalid")).toBe("true");
		expect(screen.getByRole("alert").textContent).toBe("邮箱格式不正确");
		expect(screen.getByLabelText("备注")).toBeTruthy();
		expect(screen.getByLabelText("角色")).toBeTruthy();
	});

	it("renders StatusBadge in whisper and pill variants", () => {
		const { container } = render(
			<>
				<StatusBadge tone="success">已发布</StatusBadge>
				<StatusBadge variant="pill" tone="warning">
					待确认
				</StatusBadge>
			</>,
		);
		const badges = container.querySelectorAll(".ui-status-badge");
		expect(badges[0]?.getAttribute("data-variant")).toBe("whisper");
		expect(badges[1]?.getAttribute("data-variant")).toBe("pill");
	});

	it("switches Tabs with semantic tablist/tab attributes", () => {
		const onChange = vi.fn();
		render(
			<Tabs
				ariaLabel="视图切换"
				value="a"
				onChange={onChange}
				items={[
					{ value: "a", label: "大纲" },
					{ value: "b", label: "图谱" },
				]}
			/>,
		);
		const tabB = screen.getByRole("tab", { name: "图谱" });
		expect(
			screen.getByRole("tab", { name: "大纲" }).getAttribute("aria-selected"),
		).toBe("true");
		fireEvent.click(tabB);
		expect(onChange).toHaveBeenCalledWith("b");
	});

	it("handles ConfirmDialog focus, escape, and non-backdrop close for destructive mode", async () => {
		const onClose = vi.fn();
		const onConfirm = vi.fn();
		render(
			<ConfirmDialog
				isOpen
				destructive
				title="确定清空？"
				description="清空后不可恢复"
				onClose={onClose}
				onConfirm={onConfirm}
			/>,
		);
		const dialog = screen.getByRole("dialog", { name: "确定清空？" });
		await waitFor(() => {
			expect(document.activeElement).toBe(
				screen.getByRole("heading", { name: "确定清空？" }),
			);
		});
		fireEvent.click(dialog.parentElement as HTMLElement);
		expect(onClose).not.toHaveBeenCalled();
		fireEvent.keyDown(document, { key: "Escape" });
		expect(onClose).toHaveBeenCalledTimes(1);
	});

	it("renders floating Drawer and closes on Escape", async () => {
		const onClose = vi.fn();
		render(
			<Drawer isOpen title="编辑课程" onClose={onClose}>
				<p>内容区</p>
			</Drawer>,
		);
		await waitFor(() => {
			expect(document.activeElement).toBe(
				screen.getByRole("heading", { name: "编辑课程" }),
			);
		});
		fireEvent.keyDown(document, { key: "Escape" });
		expect(onClose).toHaveBeenCalledTimes(1);
	});

	it("renders FeedbackState with error role and action", () => {
		render(
			<FeedbackState
				variant="error"
				title="加载失败"
				description="请检查网络后重试"
				actions={<Button>重新加载</Button>}
			/>,
		);
		expect(screen.getByRole("alert")).toBeTruthy();
		expect(screen.getByRole("button", { name: "重新加载" })).toBeTruthy();
	});
});
