import { useCallback, useEffect, useRef } from 'react';
import { fetchSessionRecoveryData } from '../../api/orchestration';
import type { ChatMessage } from '../../types/chat';

const SESSION_PARAM = 'session_id';

export function useChatSession(
  storeSessionId: string | null,
  token: string | null,
  onSessionRecovered: (messages: ChatMessage[], sessionId: string) => void,
) {
  const recoveredSessionIdRef = useRef<string | null>(null);

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
    if (storeSessionId) return;
    const params = new URLSearchParams(window.location.search);
    const sessionId = params.get(SESSION_PARAM);
    if (!sessionId) {
      recoveredSessionIdRef.current = null;
      return;
    }
    const recoveredSessionId = sessionId;
    if (recoveredSessionIdRef.current === recoveredSessionId) return;

    let cancelled = false;

    async function recoverSession() {
      try {
        const raw = localStorage.getItem(`session-${recoveredSessionId}`);
        if (raw) {
          const parsed = JSON.parse(raw) as { messages: ChatMessage[] };
          if (Array.isArray(parsed.messages)) {
            if (cancelled) return;
            recoveredSessionIdRef.current = recoveredSessionId;
            onSessionRecovered(parsed.messages, recoveredSessionId);
            return;
          }
        }
      } catch {
        // Fall through to server recovery.
      }

      if (!token) {
        return;
      }

      try {
        const recovered = await fetchSessionRecoveryData(token, recoveredSessionId);
        if (cancelled) return;
        if (recovered.messages.length > 0) {
          recoveredSessionIdRef.current = recoveredSessionId;
          onSessionRecovered(recovered.messages, recoveredSessionId);
          return;
        }
      } catch {
        // Ignore and clear stale URL below.
      }

      if (cancelled) return;
      recoveredSessionIdRef.current = null;
      clearSessionFromUrl();
    }

    void recoverSession();

    return () => {
      cancelled = true;
    };
  }, [storeSessionId, token, onSessionRecovered, clearSessionFromUrl]);

  useEffect(() => {
    if (!storeSessionId) return;
    recoveredSessionIdRef.current = storeSessionId;
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
