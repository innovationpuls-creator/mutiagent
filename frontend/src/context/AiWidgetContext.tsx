import React, { createContext, useCallback, useContext, useRef, useState, ReactNode } from 'react';

export type WidgetState = 'HIDDEN' | 'CENTER_INPUT' | 'PROCESSING' | 'EXPANDED' | 'WIDGET';

export interface PendingWidgetMessage {
  id: number;
  text: string;
}

interface AiWidgetContextType {
  widgetState: WidgetState;
  setWidgetState: (state: WidgetState) => void;
  pendingMessage: PendingWidgetMessage | null;
  openWithMessage: (text: string) => void;
  clearPendingMessage: () => void;
}

const AiWidgetContext = createContext<AiWidgetContextType | undefined>(undefined);

export function AiWidgetProvider({ children }: { children: ReactNode }) {
  const [widgetState, setWidgetState] = useState<WidgetState>('HIDDEN');
  const [pendingMessage, setPendingMessage] = useState<PendingWidgetMessage | null>(null);
  const pendingMessageIdRef = useRef(0);

  const openWithMessage = useCallback((text: string) => {
    pendingMessageIdRef.current += 1;
    setPendingMessage({ id: pendingMessageIdRef.current, text });
    setWidgetState('EXPANDED');
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
    throw new Error('useAiWidget must be used within an AiWidgetProvider');
  }
  return context;
}
