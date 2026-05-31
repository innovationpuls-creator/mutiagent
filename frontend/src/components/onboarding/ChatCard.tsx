import React from 'react';
import styled from 'styled-components';
import ReactMarkdown from 'react-markdown';
import type { SessionMessage } from '../../types/chat';

interface ChatCardProps {
  message: SessionMessage;
  onSendReply?: (text: string) => void;
}

export function ChatCard({ message, onSendReply }: ChatCardProps) {
  const [inputValue, setInputValue] = React.useState('');

  const renderContent = () => {
    if (message.type === 'basic_profile') {
      return (
        <div className="md-content">
          <ReactMarkdown>{message.text}</ReactMarkdown>
        </div>
      );
    }

    if (message.question_mode === 'question_box') {
      return (
        <>
          <div className="md-content">
            <ReactMarkdown>{message.text}</ReactMarkdown>
            {message.question_box.question && <h3>{message.question_box.question}</h3>}
          </div>
          <div className="options-grid">
            {message.question_box.options.map((opt) => (
              <button 
                key={opt} 
                className="option-btn"
                onClick={() => onSendReply?.(opt)}
              >
                {opt}
              </button>
            ))}
          </div>
        </>
      );
    }

    return (
      <>
        <div className="md-content">
          <ReactMarkdown>{message.question_md}</ReactMarkdown>
        </div>
        <div className="input-groove">
          <input 
            type="text" 
            className="input-pebble" 
            placeholder="输入你的回答..." 
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && inputValue.trim()) {
                onSendReply?.(inputValue.trim());
                setInputValue('');
              }
            }}
          />
        </div>
      </>
    );
  };

  return (
    <CardWrapper>
      {renderContent()}
    </CardWrapper>
  );
}

const CardWrapper = styled.div`
  background: var(--material-dark-panel, oklch(18% 0.035 235));
  /* Chat bubble style: slightly asymmetrical border radius */
  border-radius: 24px 24px 24px 8px;
  padding: var(--space-24, 24px) var(--space-32, 32px);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.12);
  
  /* Layout constraints */
  max-width: 85%;
  width: fit-content;
  align-self: flex-start;
  
  color: var(--color-text-inverse, oklch(96% 0.025 75));

  .md-content {
    font-size: var(--text-body, 1rem);
    line-height: 2;
  }
  
  .md-content h3 {
    font-family: var(--font-heading, 'LXGW WenKai');
    font-weight: var(--font-weight-medium, 500);
    margin-top: var(--space-24, 24px);
    margin-bottom: var(--space-12, 12px);
  }
  
  .md-content ul {
    padding-left: 0;
    list-style: none;
    margin-bottom: var(--space-16, 16px);
  }
  
  .md-content ul li {
    position: relative;
    padding-left: var(--space-24, 24px);
    margin-bottom: var(--space-8, 8px);
    color: var(--color-text-inverse-secondary, oklch(80% 0.025 75));
  }
  
  .md-content ul li::before {
    content: "//";
    position: absolute;
    left: 0;
    color: var(--color-primary, oklch(76% 0.12 55));
    font-weight: var(--font-weight-medium, 500);
  }
  
  .md-content hr {
    border: none;
    border-top: 1px solid var(--material-dark-border, oklch(38% 0.04 235));
    margin: var(--space-24, 24px) 0;
  }

  .input-groove {
    background: var(--material-dark-inset, oklch(13% 0.035 235));
    box-shadow: inset 0 1px 2px oklch(8% 0.03 235 / 0.48), inset 0 -1px 1px oklch(100% 0 0 / 0.05);
    border-radius: var(--radius-lg, 32px);
    padding: var(--space-12, 12px) var(--space-16, 16px);
    margin-top: var(--space-24, 24px);
  }

  .input-pebble {
    width: 100%;
    background: transparent;
    border: none;
    font-family: inherit;
    font-size: inherit;
    color: inherit;
    outline: none;
  }
  
  .options-grid {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-12, 12px);
    margin-top: var(--space-24, 24px);
  }
  
  .option-btn {
    background: transparent;
    border: 1px solid var(--material-dark-border, oklch(38% 0.04 235));
    color: var(--color-text-inverse-secondary, oklch(80% 0.025 75));
    border-radius: var(--radius-full, 9999px);
    padding: var(--space-12, 12px) var(--space-24, 24px);
    font-family: inherit;
    font-size: inherit;
    cursor: pointer;
    transition: all 420ms cubic-bezier(0.33, 1, 0.68, 1);
  }
  
  .option-btn:hover {
    background: var(--material-dark-inset, oklch(13% 0.035 235));
    color: var(--color-text-inverse, oklch(96% 0.025 75));
  }
`;
