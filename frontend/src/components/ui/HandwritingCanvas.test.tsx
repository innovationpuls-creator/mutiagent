// @vitest-environment jsdom
import {
	cleanup,
	fireEvent,
	render,
	screen,
	waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { HandwritingCanvas } from "./HandwritingCanvas";

afterEach(() => {
	cleanup();
});

describe("HandwritingCanvas", () => {
	beforeEach(() => {
		HTMLCanvasElement.prototype.getContext = vi.fn().mockReturnValue({
			scale: vi.fn(),
			beginPath: vi.fn(),
			moveTo: vi.fn(),
			lineTo: vi.fn(),
			stroke: vi.fn(),
			clearRect: vi.fn(),
		});
		HTMLCanvasElement.prototype.toDataURL = vi
			.fn()
			.mockReturnValue("data:image/png;base64,fake-data");
	});

	it("should render and trigger clear action", () => {
		const onSave = vi.fn();
		const onClose = vi.fn();
		render(<HandwritingCanvas onSave={onSave} onClose={onClose} />);
		const clearBtn = screen.getByRole("button", { name: /清空/i });
		fireEvent.click(clearBtn);
		expect(clearBtn).toBeDefined();
	});

	it("should trigger onClose when close button is clicked", () => {
		const onSave = vi.fn();
		const onClose = vi.fn();
		render(<HandwritingCanvas onSave={onSave} onClose={onClose} />);
		const closeBtn = screen.getByRole("button", { name: /关闭/i });
		fireEvent.click(closeBtn);
		expect(onClose).toHaveBeenCalled();
	});

	it("keeps the dialog accessible, adapts the canvas width, and closes with Escape", async () => {
		const onClose = vi.fn();
		const { container } = render(
			<HandwritingCanvas onSave={vi.fn()} onClose={onClose} />,
		);

		expect(
			screen
				.getByRole("dialog", { name: "手写笔记/草图" })
				.getAttribute("aria-modal"),
		).toBe("true");
		const canvas = container.querySelector("canvas");
		expect(canvas).not.toBeNull();
		expect(canvas?.getAttribute("style")).not.toContain("width: 480px");

		await waitFor(() => {
			expect(document.activeElement).toBe(
				screen.getByRole("button", { name: "关闭" }),
			);
		});

		fireEvent.keyDown(document, { key: "Escape" });
		expect(onClose).toHaveBeenCalledTimes(1);
	});

	it("should trigger onSave with canvas data when export button is clicked", () => {
		const onSave = vi.fn();
		const onClose = vi.fn();
		render(<HandwritingCanvas onSave={onSave} onClose={onClose} />);
		const saveBtn = screen.getByRole("button", { name: /确认导出/i });
		fireEvent.click(saveBtn);
		expect(onSave).toHaveBeenCalledWith("data:image/png;base64,fake-data");
	});
});
