import { describe, expect, it, vi } from 'vitest';
import type { AgentRunStep, ChatMessage } from '../types/chat';
import { chatReducer, type ChatStore } from './chatReducer';

function assistantMessage(id: string, content: string): ChatMessage {
  return {
    id,
    role: 'assistant',
    content,
    status: 'completed',
    timestamp: 1000,
    runTrace: [],
  };
}

const step: AgentRunStep = {
  stepId: 'learning_path_agent',
  kind: 'agent',
  status: 'success',
  title: '学习路径智能体',
  summary: '学习路径智能体结果返回成功。',
  agent: 'learning_path_agent',
};

describe('chatReducer', () => {
  it('does not attach a later run trace to an earlier assistant message', () => {
    vi.spyOn(Date, 'now').mockReturnValue(2000);
    const state: ChatStore = {
      state: 'streaming',
      messages: [assistantMessage('assistant-1', '第一轮问题')],
      currentSessionId: 'session-1',
      errorMessage: null,
    };

    const next = chatReducer(state, {
      type: 'STEP',
      messageId: 'assistant-2',
      step,
    });

    expect(next.messages[0].runTrace).toEqual([]);
    expect(next.messages[0].content).toBe('第一轮问题');
  });

  it('does not overwrite an earlier assistant message when another message finishes', () => {
    vi.spyOn(Date, 'now').mockReturnValue(2000);
    const state: ChatStore = {
      state: 'streaming',
      messages: [assistantMessage('assistant-1', '第一轮问题')],
      currentSessionId: 'session-1',
      errorMessage: null,
    };

    const next = chatReducer(state, {
      type: 'RUN_DONE',
      messageId: 'assistant-2',
      content: '第二轮完成',
      sessionMessage: null,
      sessionId: 'session-2',
      agentAnswer: null,
      learningPath: null,
    });

    expect(next.messages[0].content).toBe('第一轮问题');
    expect(next.currentSessionId).toBe('session-2');
  });
});
