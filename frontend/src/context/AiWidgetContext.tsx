import React, {
	createContext,
	type ReactNode,
	useCallback,
	useContext,
	useRef,
	useState,
} from "react";

export type WidgetState =
	| "HIDDEN"
	| "CENTER_INPUT"
	| "PROCESSING"
	| "EXPANDED"
	| "WIDGET";

export interface PendingWidgetMessage {
	id: number;
	text: string;
	mode: "auto_send" | "draft";
}

interface AiWidgetContextType {
	widgetState: WidgetState;
	setWidgetState: (state: WidgetState) => void;
	pendingMessage: PendingWidgetMessage | null;
	openWithMessage: (text: string) => void;
	openWithDraft: (text: string) => void;
	clearPendingMessage: () => void;
}

const AiWidgetContext = createContext<AiWidgetContextType | undefined>(
	undefined,
);
const WIDGET_STATE_STORAGE_KEY = "mutiagent-ai-widget-state";

function loadInitialWidgetState(): WidgetState {
	if (typeof window === "undefined") {
		return "HIDDEN";
	}

	try {
		return window.sessionStorage.getItem(WIDGET_STATE_STORAGE_KEY) === "WIDGET"
			? "WIDGET"
			: "HIDDEN";
	} catch {
		return "HIDDEN";
	}
}

function persistWidgetState(state: WidgetState): void {
	if (typeof window === "undefined") {
		return;
	}

	try {
		if (state === "WIDGET") {
			window.sessionStorage.setItem(WIDGET_STATE_STORAGE_KEY, "WIDGET");
			return;
		}

		if (state === "HIDDEN") {
			window.sessionStorage.removeItem(WIDGET_STATE_STORAGE_KEY);
		}
	} catch {
		/* sessionStorage can be unavailable in restricted browser contexts */
	}
}

export function AiWidgetProvider({ children }: { children: ReactNode }) {
	const [widgetState, setWidgetStateValue] = useState<WidgetState>(
		loadInitialWidgetState,
	);
	const [pendingMessage, setPendingMessage] =
		useState<PendingWidgetMessage | null>(null);
	const pendingMessageIdRef = useRef(0);

	const setWidgetState = useCallback((state: WidgetState) => {
		persistWidgetState(state);
		setWidgetStateValue(state);
	}, []);

	const openWithMessage = useCallback((text: string) => {
		pendingMessageIdRef.current += 1;
		setPendingMessage({
			id: pendingMessageIdRef.current,
			text,
			mode: "auto_send",
		});
		setWidgetState("EXPANDED");
	}, []);

	const openWithDraft = useCallback((text: string) => {
		pendingMessageIdRef.current += 1;
		setPendingMessage({ id: pendingMessageIdRef.current, text, mode: "draft" });
		setWidgetState("EXPANDED");
	}, []);

	const clearPendingMessage = useCallback(() => {
		setPendingMessage(null);
	}, []);

	return (
		<AiWidgetContext.Provider
			value={{
				widgetState,
				setWidgetState,
				pendingMessage,
				openWithMessage,
				openWithDraft,
				clearPendingMessage,
			}}
		>
			{children}
		</AiWidgetContext.Provider>
	);
}

export function useAiWidget() {
	const context = useContext(AiWidgetContext);
	if (context === undefined) {
		throw new Error("useAiWidget must be used within an AiWidgetProvider");
	}
	return context;
}
