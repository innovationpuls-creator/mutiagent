import { render, screen } from '@testing-library/react';
import React, { useEffect } from 'react';
import { afterEach, expect, test, vi } from 'vitest';
import { AiGreetingInput } from '../AiGreetingInput';
import { AiWidgetProvider, useAiWidget } from '../../../context/AiWidgetContext';
import { AuthProvider } from '../../../contexts/AuthContext';

function ExpandedWidget() {
  const { setWidgetState } = useAiWidget();

  useEffect(() => {
    setWidgetState('EXPANDED');
  }, [setWidgetState]);

  return <AiGreetingInput />;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

test('renders AiGreetingInput cleanly without CSS areas', () => {
  const { container } = render(
    <AuthProvider>
      <AiWidgetProvider>
        <AiGreetingInput />
      </AiWidgetProvider>
    </AuthProvider>
  );
  // Ensure the 15 css-hover grid areas are removed
  expect(container.querySelectorAll('.area').length).toBe(0);
});

test('shows the Codex-style progress panel beside the chat flow when expanded', async () => {
  vi.stubGlobal('scrollTo', vi.fn());

  render(
    <AuthProvider>
      <AiWidgetProvider>
        <ExpandedWidget />
      </AiWidgetProvider>
    </AuthProvider>,
  );

  expect(await screen.findByLabelText('多智能体调用状态')).toBeTruthy();
  expect(screen.getByText('进度')).toBeTruthy();
  expect(screen.getByText('步骤')).toBeTruthy();
  expect(screen.getByText('完整调用记录')).toBeTruthy();
  expect(screen.getByText('读取上下文')).toBeTruthy();
  expect(screen.getByText('意图识别智能体')).toBeTruthy();
  expect(screen.getByText('基础画像智能体')).toBeTruthy();
  expect(screen.getByLabelText('对话内容')).toBeTruthy();
});
