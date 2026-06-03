import type { AgentRunStep, ChatMessage, ChatState, PartialStructuredData, ThoughtChunkEntry } from '../types/chat';

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
  | { type: 'TEXT_CHUNK'; messageId: string; chunk: string }
  | { type: 'MESSAGE_STARTED'; messageId: string }
  | { type: 'THOUGHT_CHUNK'; messageId: string; stepId: string; text: string }
  | { type: 'DATA_SCHEMA_STARTED'; messageId: string; schemaName: string }
  | { type: 'DATA_CHUNK'; messageId: string; raw: string }
  | { type: 'DATA_COMPLETED'; messageId: string; finalData: unknown }
  | { type: 'CLEAR_ERROR' }
  | { type: 'RESET' }
  | { type: 'NEW_SESSION' }
  | { type: 'LOAD_SESSION'; messages: ChatMessage[]; sessionId: string };

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

    case 'MESSAGE_STARTED':
      return {
        ...state,
        state: 'streaming',
        messages: updateAssistantById(state.messages, action.messageId, (msg) => ({
          ...msg,
          status: 'streaming',
        })),
      };

    case 'TEXT_CHUNK':
      return {
        ...state,
        state: 'streaming',
        messages: updateAssistantById(state.messages, action.messageId, (msg) => ({
          ...msg,
          content: msg.content + action.chunk,
          status: 'streaming',
        })),
      };

    case 'THOUGHT_CHUNK': {
      const entry: ThoughtChunkEntry = {
        stepId: action.stepId,
        text: action.text,
        timestamp: Date.now(),
      };
      return {
        ...state,
        messages: updateAssistantById(state.messages, action.messageId, (msg) => {
          const trace = [...(msg.runTrace ?? [])];
          const stepIdx = trace.findIndex((s) => s.stepId === action.stepId);
          if (stepIdx >= 0) {
            const existingLog = trace[stepIdx].thoughtLog ?? [];
            trace[stepIdx] = {
              ...trace[stepIdx],
              thoughtLog: [...existingLog, entry],
            };
          } else {
            trace.push({
              stepId: action.stepId,
              kind: 'thought',
              status: 'running',
              title: '主智能体思考',
              summary: action.text.slice(0, 50),
              thoughtLog: [entry],
            });
          }
          return { ...msg, runTrace: trace };
        }),
      };
    }

    case 'DATA_SCHEMA_STARTED': {
      const schema: PartialStructuredData = {
        schemaName: action.schemaName,
        partialData: null,
        raw: '',
        timestamp: Date.now(),
      };
      return {
        ...state,
        messages: updateAssistantById(state.messages, action.messageId, (msg) => ({
          ...msg,
          partialData: schema,
        })),
      };
    }

    case 'DATA_CHUNK': {
      return {
        ...state,
        messages: updateAssistantById(state.messages, action.messageId, (msg) => {
          const prev = msg.partialData ?? {
            schemaName: 'Unknown',
            partialData: null,
            raw: '',
            timestamp: Date.now(),
          };
          const mergedRaw = prev.raw + action.raw;
          let parsed: unknown = null;
          try {
            parsed = JSON.parse(mergedRaw);
          } catch {
            parsed = prev.partialData;
          }
          const updated: PartialStructuredData = {
            ...prev,
            raw: mergedRaw,
            partialData: parsed,
            timestamp: Date.now(),
          };
          return { ...msg, partialData: updated };
        }),
      };
    }

    case 'DATA_COMPLETED': {
      return {
        ...state,
        messages: updateAssistantById(state.messages, action.messageId, (msg) => ({
          ...msg,
          partialData: null,
        })),
      };
    }

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
