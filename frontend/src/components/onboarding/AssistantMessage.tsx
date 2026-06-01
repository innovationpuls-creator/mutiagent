import React from 'react';
import styled from 'styled-components';
import type { ChatMessage } from '../../types/chat';
import { AgentRunTimeline } from './AgentRunTimeline';
import { StreamingText } from './StreamingText';

interface SystemMessageProps {
  message: ChatMessage;
}

export function SystemMessage({ message }: SystemMessageProps) {
  return (
    <div
      style={{
        width: 'fit-content',
        maxInlineSize: 'min(100%, var(--container-narrow))',
        borderRadius: 'var(--radius-md)',
        padding: 'var(--space-8) var(--space-16)',
        background: message.status === 'error'
          ? 'var(--color-error-bg)'
          : 'var(--color-surface-inset)',
        color: message.status === 'error'
          ? 'var(--color-error)'
          : 'var(--color-text-secondary)',
        fontFamily: 'var(--font-body)',
        fontSize: 'var(--text-caption)',
        lineHeight: 1.6,
        alignSelf: 'center',
      }}
    >
      {message.content}
    </div>
  );
}

interface AssistantMessageProps {
  message: ChatMessage;
  onSendReply?: (text: string) => void;
  disabled?: boolean;
}

export function AssistantMessage({ message, onSendReply, disabled }: AssistantMessageProps) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-8)' }}>
      {(message.runTrace && message.runTrace.length > 0) && (
        <AgentRunTimeline
          steps={message.runTrace}
          status={message.status}
        />
      )}

      {message.status === 'pending' && !message.content ? (
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 'var(--space-8)',
            padding: 'var(--space-12) var(--space-16)',
            borderRadius: 'var(--radius-md)',
            background: 'var(--color-surface-inset)',
            fontFamily: 'var(--font-body)',
            fontSize: 'var(--text-caption)',
            color: 'var(--color-text-secondary)',
          }}
        >
          <span>处理中...</span>
        </div>
      ) : message.content ? (
        <StreamingText content={message.content} status={message.status} />
      ) : null}

      {message.agentAnswer?.questionBox && (
        <QuestionBoxPanel>
          <p>{message.agentAnswer.questionBox.question}</p>
          <div>
            {message.agentAnswer.questionBox.options.map((option) => (
              <button
                key={option}
                type="button"
                disabled={disabled || !onSendReply}
                onClick={() => onSendReply?.(option)}
              >
                {option}
              </button>
            ))}
          </div>
        </QuestionBoxPanel>
      )}

      {message.status === 'error' && message.error && (
        <div
          style={{
            borderRadius: 'var(--radius-md)',
            padding: 'var(--space-8) var(--space-16)',
            background: 'var(--color-error-bg)',
            color: 'var(--color-error)',
            fontFamily: 'var(--font-body)',
            fontSize: 'var(--text-caption)',
            lineHeight: 1.6,
          }}
        >
          {message.error}
        </div>
      )}
    </div>
  );
}

const QuestionBoxPanel = styled.div`
  display: grid;
  gap: var(--space-12);
  inline-size: fit-content;
  max-inline-size: min(100%, var(--container-narrow));
  border-radius: var(--radius-md);
  background: var(--color-primary-soft);
  padding: var(--space-16);
  box-shadow: var(--shadow-sm);
  font-family: var(--font-body);

  p {
    margin: 0;
    color: var(--color-text-primary);
    font-size: var(--text-body-sm);
    line-height: 1.8;
    text-wrap: pretty;
  }

  div {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-8);
  }

  button {
    min-block-size: calc(var(--space-40) + var(--space-4));
    border: none;
    border-radius: var(--radius-full);
    background: var(--color-surface-raised);
    color: var(--color-text-primary);
    cursor: pointer;
    font-family: var(--font-body);
    font-size: var(--text-button);
    font-weight: var(--font-weight-medium);
    line-height: 1;
    padding: var(--space-12) var(--space-16);
    box-shadow: var(--shadow-sm);
    transition:
      transform var(--duration-lazy-hover) var(--ease-lazy),
      opacity var(--duration-lazy-hover) var(--ease-lazy);
  }

  button:hover:not(:disabled) {
    transform: translateY(calc(var(--space-4) * -1));
  }

  button:disabled {
    cursor: not-allowed;
    opacity: 0.64;
  }

  @media (prefers-reduced-motion: reduce) {
    button {
      transition: opacity var(--duration-instant) ease;
      transform: none;
    }
  }
`;
