import { useCallback, useEffect, useRef } from 'react';
import type { ChatMessage } from '../../types/chat';

const SESSION_PARAM = 'session_id';

export function useChatSession(
  storeSessionId: string | null,
  onSessionRecovered: (messages: ChatMessage[], sessionId: string) => void,
) {
  const recoveredRef = useRef(false);

  const writeSessionToUrl = useCallback((sessionId: string) => {
    const url = new URL(window.location.href);
    url.searchParams.set(SESSION_PARAM, sessionId);
    window.history.replaceState({}, '', url.toString());
  }, []);

  const clearSessionFromUrl = useCallback(() => {
    const url = new URL(window.location.href);
    url.searchParams.delete(SESSION_PARAM);
    window.history.replaceState({}, '', url.toString());
  }, []);

  useEffect(() => {
    if (recoveredRef.current) return;
    const params = new URLSearchParams(window.location.search);
    const sessionId = params.get(SESSION_PARAM);
    if (!sessionId) return;

    try {
      const raw = localStorage.getItem(`session-${sessionId}`);
      if (!raw) return;
      const parsed = JSON.parse(raw) as { messages: ChatMessage[] };
      if (!Array.isArray(parsed.messages)) return;
      recoveredRef.current = true;
      onSessionRecovered(parsed.messages, sessionId);
    } catch {
      clearSessionFromUrl();
    }
  }, [onSessionRecovered, clearSessionFromUrl]);

  useEffect(() => {
    if (!storeSessionId) return;
    writeSessionToUrl(storeSessionId);
  }, [storeSessionId, writeSessionToUrl]);

  const persistSession = useCallback(
    (sessionId: string, messages: ChatMessage[]) => {
      try {
        localStorage.setItem(
          `session-${sessionId}`,
          JSON.stringify({ messages, savedAt: Date.now() }),
        );
      } catch {
        // localStorage full or unavailable — silently fail
      }
    },
    [],
  );

  return { writeSessionToUrl, clearSessionFromUrl, persistSession };
}
