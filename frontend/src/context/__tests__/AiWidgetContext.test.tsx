import { fireEvent, render, screen } from "@testing-library/react";
import React from "react";
import { expect, test } from "vitest";
import { AiWidgetProvider, useAiWidget } from "../AiWidgetContext";

function TestComponent() {
	const {
		widgetState,
		setWidgetState,
		pendingMessage,
		openWithMessage,
		clearPendingMessage,
	} = useAiWidget();
	return (
		<div>
			<span data-testid="state">{widgetState}</span>
			<span data-testid="pending">{pendingMessage?.text ?? ""}</span>
			<button onClick={() => setWidgetState("EXPANDED")}>Expand</button>
			<button onClick={() => openWithMessage("开始第一门课")}>
				Open With Message
			</button>
			<button onClick={clearPendingMessage}>Clear Pending</button>
		</div>
	);
}

test("provides default state and allows state updates", () => {
	render(
		<AiWidgetProvider>
			<TestComponent />
		</AiWidgetProvider>,
	);
	expect(screen.getByTestId("state").textContent).toBe("HIDDEN");
	fireEvent.click(screen.getByText("Expand"));
	expect(screen.getByTestId("state").textContent).toBe("EXPANDED");
	fireEvent.click(screen.getByText("Open With Message"));
	expect(screen.getByTestId("state").textContent).toBe("EXPANDED");
	expect(screen.getByTestId("pending").textContent).toBe("开始第一门课");
	fireEvent.click(screen.getByText("Clear Pending"));
	expect(screen.getByTestId("pending").textContent).toBe("");
});

function PendingMessageIdProbe() {
	const { pendingMessage, openWithMessage } = useAiWidget();
	return (
		<div>
			<span data-testid="pending-id">{pendingMessage?.id ?? ""}</span>
			<span data-testid="pending-text">{pendingMessage?.text ?? ""}</span>
			<button onClick={() => openWithMessage("第一条消息")}>
				First Pending
			</button>
			<button onClick={() => openWithMessage("第二条消息")}>
				Second Pending
			</button>
		</div>
	);
}

test("assigns unique pending message ids across rapid openWithMessage calls", () => {
	render(
		<AiWidgetProvider>
			<PendingMessageIdProbe />
		</AiWidgetProvider>,
	);

	fireEvent.click(screen.getByText("First Pending"));
	const firstId = screen.getByTestId("pending-id").textContent;
	expect(screen.getByTestId("pending-text").textContent).toBe("第一条消息");

	fireEvent.click(screen.getByText("Second Pending"));
	const secondId = screen.getByTestId("pending-id").textContent;
	expect(screen.getByTestId("pending-text").textContent).toBe("第二条消息");

	expect(firstId).not.toBe("");
	expect(secondId).not.toBe("");
	expect(secondId).not.toBe(firstId);
});
