import { cleanup, render, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { ChatMessage } from '../../types/chat';
import { useChatSession } from './useChatSession';

function message(id: string, content: string): ChatMessage {
  return {
    id,
    role: 'assistant',
    content,
    status: 'completed',
    timestamp: 1000,
  };
}

function Harness({
  storeSessionId,
  onRecovered,
  tick,
}: {
  storeSessionId: string | null;
  onRecovered: (messages: ChatMessage[], sessionId: string) => void;
  tick: number;
}) {
  useChatSession(storeSessionId, (messages, sessionId) => onRecovered(messages, sessionId));
  return <span>{tick}</span>;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  window.history.replaceState({}, '', '/');
});

function stubLocalStorage(initial: Record<string, string> = {}) {
  const store = { ...initial };
  vi.stubGlobal('localStorage', {
    getItem: vi.fn((key: string) => store[key] ?? null),
    setItem: vi.fn((key: string, value: string) => {
      store[key] = value;
    }),
    removeItem: vi.fn((key: string) => {
      delete store[key];
    }),
  });
}

describe('useChatSession', () => {
  it('does not recover stale localStorage after the active session writes its id to the URL', async () => {
    stubLocalStorage({
      'session-session-1': JSON.stringify({ messages: [message('assistant-1', '旧问题')], savedAt: 1000 }),
    });
    const onRecovered = vi.fn();
    window.history.replaceState({}, '', '/sprout');

    const { rerender } = render(
      <Harness storeSessionId={null} onRecovered={onRecovered} tick={0} />,
    );
    rerender(<Harness storeSessionId="session-1" onRecovered={onRecovered} tick={1} />);

    await waitFor(() => expect(window.location.search).toBe('?session_id=session-1'));
    rerender(<Harness storeSessionId="session-1" onRecovered={onRecovered} tick={2} />);

    expect(onRecovered).not.toHaveBeenCalled();
  });
});
