import React from 'react';
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
