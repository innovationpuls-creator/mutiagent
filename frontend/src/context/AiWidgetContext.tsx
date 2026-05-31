import React, { createContext, useContext, useState, ReactNode } from 'react';

export type WidgetState = 'HIDDEN' | 'CENTER_INPUT' | 'PROCESSING' | 'EXPANDED' | 'WIDGET';

interface AiWidgetContextType {
  widgetState: WidgetState;
  setWidgetState: (state: WidgetState) => void;
}

const AiWidgetContext = createContext<AiWidgetContextType | undefined>(undefined);

export function AiWidgetProvider({ children }: { children: ReactNode }) {
  const [widgetState, setWidgetState] = useState<WidgetState>('HIDDEN');
  return (
    <AiWidgetContext.Provider value={{ widgetState, setWidgetState }}>
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
