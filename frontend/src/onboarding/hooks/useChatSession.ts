import { useCallback, useEffect, useRef, type MutableRefObject } from 'react';
import { fetchSessionRecoveryData } from '../../api/orchestration';
import type { ChatMessage } from '../../types/chat';
import { hasCompleteBasicProfileSessionMessage } from '../../lib/profileContract';

const SESSION_PARAM = 'session_id';

export interface SessionRecoveryMeta {
  hasCompleteProfile: boolean;
}

function hasInFlightAssistantSnapshot(messages: ChatMessage[]): boolean {
  return messages.some((message) => {
    if (message.role !== 'assistant') return false;
    if (message.status === 'pending' || message.status === 'streaming') return true;
    if (message.activeStepId) return true;
    return (message.runTrace ?? []).some((step) => step.status === 'running');
  });
}

function inferRecoveredHasCompleteProfile(messages: ChatMessage[]): boolean | null {
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const message = messages[index];
    if (message.role !== 'assistant' || !message.sessionMessage) continue;
    if (message.sessionMessage.type === 'collecting') return false;
    if (message.sessionMessage.type === 'basic_profile') {
      return hasCompleteBasicProfileSessionMessage(message.sessionMessage);
    }
  }
  return null;
}

export function useChatSession(
  storeSessionId: string | null,
  token: string | null,
  userUid: string | null,
  onSessionRecovered: (messages: ChatMessage[], sessionId: string) => void,
  recoveryMetaRef?: MutableRefObject<SessionRecoveryMeta | null>,
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
      let cachedMessages: ChatMessage[] | null = null;
      let cachedHasCompleteProfile: boolean | null = null;
      let cachedHasInFlightAssistant = false;
      try {
        const raw = localStorage.getItem(`session-${recoveredSessionId}`);
        if (raw) {
          const parsed = JSON.parse(raw) as {
            messages: ChatMessage[];
            userUid?: unknown;
            hasCompleteProfile?: unknown;
          };
          const cachedUserUid = typeof parsed.userUid === 'string' ? parsed.userUid : null;
          if (Array.isArray(parsed.messages) && cachedUserUid !== null && cachedUserUid === userUid) {
            cachedMessages = parsed.messages;
            cachedHasInFlightAssistant = hasInFlightAssistantSnapshot(parsed.messages);
            const explicitHasCompleteProfile = typeof parsed.hasCompleteProfile === 'boolean'
              ? parsed.hasCompleteProfile
              : null;
            const inferredHasCompleteProfile = inferRecoveredHasCompleteProfile(parsed.messages);
            cachedHasCompleteProfile = inferredHasCompleteProfile ?? explicitHasCompleteProfile;
            if (cachedHasCompleteProfile !== null && !cachedHasInFlightAssistant) {
              if (cancelled) return;
              recoveredSessionIdRef.current = recoveredSessionId;
              if (recoveryMetaRef) {
                recoveryMetaRef.current = { hasCompleteProfile: cachedHasCompleteProfile };
              }
              onSessionRecovered(parsed.messages, recoveredSessionId);
              return;
            }
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
        if (recovered.messages.length === 0 && cachedMessages) {
          recoveredSessionIdRef.current = recoveredSessionId;
          if (recoveryMetaRef) {
            recoveryMetaRef.current = { hasCompleteProfile: cachedHasCompleteProfile ?? false };
          }
          onSessionRecovered(cachedMessages, recoveredSessionId);
          return;
        }
        recoveredSessionIdRef.current = recoveredSessionId;
        if (recoveryMetaRef) {
          recoveryMetaRef.current = { hasCompleteProfile: recovered.hasCompleteProfile };
        }
        onSessionRecovered(recovered.messages, recoveredSessionId);
        return;
      } catch {
        // Fall through to local cache fallback or stale URL cleanup below.
      }

      if (cachedMessages) {
        if (cancelled) return;
        recoveredSessionIdRef.current = recoveredSessionId;
        if (recoveryMetaRef) {
          recoveryMetaRef.current = { hasCompleteProfile: cachedHasCompleteProfile ?? false };
        }
        onSessionRecovered(cachedMessages, recoveredSessionId);
        return;
      }

      if (cancelled) return;
      recoveredSessionIdRef.current = null;
      clearSessionFromUrl();
    }

    void recoverSession();

    return () => {
      cancelled = true;
    };
  }, [storeSessionId, token, userUid, onSessionRecovered, clearSessionFromUrl]);

  useEffect(() => {
    if (!storeSessionId) return;
    recoveredSessionIdRef.current = storeSessionId;
    writeSessionToUrl(storeSessionId);
  }, [storeSessionId, writeSessionToUrl]);

  const persistSession = useCallback(
    (sessionId: string, messages: ChatMessage[], hasCompleteProfile: boolean) => {
      if (!userUid) return;
      try {
        localStorage.setItem(
          `session-${sessionId}`,
          JSON.stringify({ userUid, messages, hasCompleteProfile, savedAt: Date.now() }),
        );
      } catch {
        // localStorage full or unavailable — silently fail
      }
    },
    [userUid],
  );

  const clearPersistedSession = useCallback((sessionId: string) => {
    try {
      localStorage.removeItem(`session-${sessionId}`);
    } catch {
      // localStorage unavailable — silently fail
    }
  }, []);

  return { writeSessionToUrl, clearSessionFromUrl, persistSession, clearPersistedSession };
}
