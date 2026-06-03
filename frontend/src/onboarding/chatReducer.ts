import type { AgentRunStep, ChatMessage, ChatState } from '../types/chat';

export interface ChatStore {
  state: ChatState;
  messages: ChatMessage[];
  currentSessionId: string | null;
  errorMessage: string | null;
}

export const initialChatStore: ChatStore = {
  state: 'idle',
  messages: [],
  currentSessionId: null,
  errorMessage: null,
};

export type ChatAction =
  | { type: 'ADD_USER_MESSAGE'; id: string; content: string }
  | { type: 'ADD_ASSISTANT_MESSAGE'; id: string }
  | { type: 'STEP'; messageId: string; step: AgentRunStep }
  | {
    type: 'RUN_DONE';
    messageId: string;
    content: string;
    sessionMessage: ChatMessage['sessionMessage'];
    sessionId?: string;
    agentAnswer?: ChatMessage['agentAnswer'];
    learningPath?: ChatMessage['learningPath'];
  }
  | { type: 'RUN_ERROR'; messageId: string; message: string }
  | { type: 'CONNECTING' }
  | { type: 'STREAMING_STARTED' }
  | { type: 'CLEAR_ERROR' }
  | { type: 'RESET' }
  | { type: 'NEW_SESSION' }
  | { type: 'LOAD_SESSION'; messages: ChatMessage[]; sessionId: string };

function updateLastAssistant(messages: ChatMessage[], updater: (msg: ChatMessage) => ChatMessage): ChatMessage[] {
  const updated = [...messages];
  for (let i = updated.length - 1; i >= 0; i -= 1) {
    if (updated[i].role === 'assistant') {
      updated[i] = updater(updated[i]);
      return updated;
    }
  }
  return updated;
}

function updateAssistantById(
  messages: ChatMessage[],
  messageId: string,
  updater: (msg: ChatMessage) => ChatMessage,
): ChatMessage[] {
  const messageIndex = messages.findIndex((msg) => msg.id === messageId && msg.role === 'assistant');
  if (messageIndex < 0) return messages;

  return messages.map((msg, index) => (index === messageIndex ? updater(msg) : msg));
}

export function chatReducer(state: ChatStore, action: ChatAction): ChatStore {
  switch (action.type) {
    case 'ADD_USER_MESSAGE': {
      const userMsg: ChatMessage = {
        id: action.id,
        role: 'user',
        content: action.content,
        status: 'completed',
        timestamp: Date.now(),
      };
      return {
        ...state,
        state: 'connecting',
        messages: [...state.messages, userMsg],
        errorMessage: null,
      };
    }

    case 'ADD_ASSISTANT_MESSAGE': {
      const assistantMsg: ChatMessage = {
        id: action.id,
        role: 'assistant',
        content: '',
        status: 'pending',
        timestamp: Date.now(),
        runTrace: [],
      };
      return {
        ...state,
        messages: [...state.messages, assistantMsg],
        errorMessage: null,
      };
    }

    case 'CONNECTING':
      return { ...state, state: 'connecting' };

    case 'STREAMING_STARTED':
      return { ...state, state: 'streaming' };

    case 'STEP': {
      const step = action.step;
      return {
        ...state,
        state: 'streaming',
        messages: updateAssistantById(state.messages, action.messageId, (msg) => {
          const trace = [...(msg.runTrace ?? [])];
          const existingIdx = trace.findIndex((s) => s.stepId === step.stepId);
          if (existingIdx >= 0) {
            trace[existingIdx] = step;
          } else {
            trace.push(step);
          }
          const activeStep = [...trace].reverse().find((s) => s.status === 'running');
          return {
            ...msg,
            status: 'streaming',
            runTrace: trace,
            activeStepId: activeStep?.stepId ?? null,
          };
        }),
      };
    }

    case 'RUN_DONE': {
      return {
        ...state,
        state: 'idle',
        currentSessionId: action.sessionId ?? state.currentSessionId,
        messages: updateAssistantById(state.messages, action.messageId, (msg) => ({
          ...msg,
          content: action.content,
          sessionMessage: action.sessionMessage,
          agentAnswer: action.agentAnswer ?? null,
          learningPath: action.learningPath ?? null,
          status: 'completed',
          activeStepId: null,
        })),
      };
    }

    case 'RUN_ERROR': {
      return {
        ...state,
        state: 'error',
        errorMessage: action.message,
        messages: updateAssistantById(state.messages, action.messageId, (msg) => ({
          ...msg,
          status: 'error',
          error: action.message,
          activeStepId: null,
        })),
      };
    }

    case 'CLEAR_ERROR':
      return { ...state, errorMessage: null };

    case 'RESET':
      return { ...initialChatStore };

    case 'NEW_SESSION':
      return { ...initialChatStore };

    case 'LOAD_SESSION':
      return {
        ...state,
        state: 'idle',
        messages: action.messages,
        currentSessionId: action.sessionId,
        errorMessage: null,
      };

    default:
      return state;
  }
}

let counter = 0;
export function nextMessageId(): string {
  counter += 1;
  return `msg-${Date.now()}-${counter}`;
}
