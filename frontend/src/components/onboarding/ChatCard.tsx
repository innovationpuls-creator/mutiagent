import React from 'react';
import styled from 'styled-components';
import { MarkdownRenderer } from '../markdown';
import type { ConfirmedInfo, PartialStructuredData, QuestionBoxOption, SessionMessage } from '../../types/chat';

interface ChatCardProps {
  message: SessionMessage;
  onSendReply?: (text: string) => void;
  disabled?: boolean;
  partialData?: PartialStructuredData | null;
}

type FieldKey = keyof ConfirmedInfo;

const FIELD_LABELS: Record<FieldKey, string> = {
  current_grade: '年级',
  major: '专业',
  learning_stage: '阶段',
  has_clear_goal: '目标清晰度',
  learning_method_preference: '学习方式',
  learning_pace_preference: '学习节奏',
  content_preference: '内容形式',
  need_guidance: '引导需求',
  knowledge_foundation: '知识基础',
  strengths: '优势',
  weaknesses: '薄弱点',
  experience: '实践经验',
  short_term_goal: '近期目标',
  long_term_goal: '长期目标',
  weekly_available_time: '每周时间',
  constraints: '主要约束',
};

const FIELD_GROUPS: { title: string; keys: FieldKey[] }[] = [
  { title: '基础信息', keys: ['current_grade', 'major', 'learning_stage', 'has_clear_goal'] },
  {
    title: '学习偏好',
    keys: ['learning_method_preference', 'learning_pace_preference', 'content_preference', 'need_guidance'],
  },
  { title: '能力基础', keys: ['knowledge_foundation', 'strengths', 'weaknesses', 'experience'] },
  { title: '目标与约束', keys: ['short_term_goal', 'long_term_goal', 'weekly_available_time', 'constraints'] },
];

const STAGE_LABELS: Record<SessionMessage['stage'], string> = {
  basic_info: '基础信息',
  learning_preference: '学习偏好',
  ability_basis: '能力基础',
  goal_constraint: '目标约束',
  generated: '画像完成',
};

function fieldValue(info: Partial<ConfirmedInfo> | undefined, key: FieldKey): string {
  const value = info?.[key];
  if (Array.isArray(value)) return value.join('、');
  return typeof value === 'string' ? value : '';
}

function filledFields(info: Partial<ConfirmedInfo> | undefined): Array<[FieldKey, string]> {
  return (Object.keys(FIELD_LABELS) as FieldKey[])
    .map((key) => [key, fieldValue(info, key)] as [FieldKey, string])
    .filter(([, value]) => value.trim().length > 0);
}

function groupFields(info: Partial<ConfirmedInfo> | undefined, keys: FieldKey[]): Array<[FieldKey, string]> {
  return keys
    .map((key) => [key, fieldValue(info, key)] as [FieldKey, string])
    .filter(([, value]) => value.trim().length > 0);
}

function extractQuestions(message: SessionMessage): string[] {
  if (message.question_mode === 'question_box') {
    return message.question_box?.question ? [message.question_box.question] : [];
  }

  const source = message.question_md || message.text;
  const section = source.split('❓ 接下来需要了解：')[1] ?? source.split('接下来需要了解：')[1] ?? '';
  const lines = section
    .split('\n')
    .map((line) => line.replace(/^[-\s]+/, '').trim())
    .filter(Boolean);
  return lines.length > 0 ? lines.slice(0, 3) : [message.text].filter(Boolean);
}

function splitProfileText(text: string): Array<{ title: string; body: string }> {
  const matches = [...text.matchAll(/【([^】]+)】\s*([\s\S]*?)(?=【[^】]+】|$)/g)];
  return matches
    .map((match) => ({ title: match[1].trim(), body: match[2].trim() }))
    .filter((section) => section.title && section.body);
}

function normalizeQuestionOption(option: QuestionBoxOption | string): QuestionBoxOption {
  if (typeof option !== 'string') return option;
  return {
    label: option,
    value: option,
    description: '',
    target_fields: [],
    fills: {},
  };
}

export function ChatCard({ message, onSendReply, disabled = false, partialData }: ChatCardProps) {
  const [inputValue, setInputValue] = React.useState('');
  const [hasSubmittedReply, setHasSubmittedReply] = React.useState(false);
  const confirmed = filledFields(message.confirmed_info);
  const defaultedFields = Array.isArray(message.defaulted_fields) ? message.defaulted_fields : [];
  const options = Array.isArray(message.question_box?.options)
    ? (message.question_box.options as Array<QuestionBoxOption | string>).map(normalizeQuestionOption)
    : [];
  const questions = extractQuestions(message);
  const generatedSections = message.type === 'basic_profile' ? splitProfileText(message.text) : [];
  const profileSummary = generatedSections[0]?.body || message.text || '画像已生成，可以继续补充你的学习目标与约束。';
  const showReplyControls = Boolean(onSendReply) && !hasSubmittedReply;

  const isFieldStreaming = (fieldName: string): boolean => {
    if (!partialData?.partialData || typeof partialData.partialData !== 'object') return false;
    const data = partialData.partialData as Record<string, unknown>;
    return fieldName in data && data[fieldName] !== undefined;
  };

  const submitInlineAnswer = () => {
    const answer = inputValue.trim();
    if (!answer || disabled) return;
    onSendReply?.(answer);
    setHasSubmittedReply(true);
    setInputValue('');
  };

  const submitOptionAnswer = (option: QuestionBoxOption) => {
    if (disabled) return;
    if (option.value === '__free_text__') {
      return;
    }
    onSendReply?.(option.label);
    setHasSubmittedReply(true);
  };

  return (
    <CardWrapper data-state={message.type}>
      <header className="card-head">
        <span className="card-kicker">{STAGE_LABELS[message.stage]}</span>
        <span className="card-state">{message.type === 'basic_profile' ? '已生成' : '采集中'}</span>
      </header>

      {message.type === 'basic_profile' ? (
        <>
          <div className="profile-hero">
            <span className="profile-eyebrow">基础画像</span>
            <h3>画像已整理成可继续更新的学习底稿</h3>
            <p>{profileSummary}</p>
            <div className="profile-meter" aria-label={`已确认 ${confirmed.length} 项画像信息`}>
              <span>已确认 {confirmed.length} 项</span>
              <span>可继续补充或追问</span>
            </div>
          </div>

          <div className="profile-grid">
            {FIELD_GROUPS.map((group) => {
              const fields = groupFields(message.confirmed_info, group.keys);

              return (
                <section className="profile-section" key={group.title} data-empty={fields.length === 0}>
                  <h4>{group.title}</h4>
                  {fields.length > 0 ? (
                    <dl>
                      {fields.map(([key, value]) => (
                        <div key={key} data-streaming={isFieldStreaming(key) ? true : undefined}>
                          <dt>{FIELD_LABELS[key]}</dt>
                          <dd>{value}</dd>
                        </div>
                      ))}
                    </dl>
                  ) : (
                    <p>等待你继续补充。</p>
                  )}
                </section>
              );
            })}
          </div>

          {generatedSections.length > 1 && (
            <div className="profile-narrative">
              {generatedSections.slice(1).map((section) => (
                <section key={section.title}>
                  <h4>{section.title}</h4>
                  <p>{section.body}</p>
                </section>
              ))}
            </div>
          )}
        </>
      ) : (
        <>
          <section className="confirmed-panel">
            <h3>已确认</h3>
            {confirmed.length > 0 ? (
              <div className="confirmed-list">
                  {confirmed.map(([key, value]) => (
                    <span className="info-chip" key={key} data-streaming={isFieldStreaming(key) ? true : undefined}>
                      <strong>{FIELD_LABELS[key]}</strong>
                      {value}
                    </span>
                  ))}
              </div>
            ) : (
              <p className="muted-copy">还没有确认的信息。先从年级、专业或近期目标开始。</p>
            )}
          </section>

          {defaultedFields.length > 0 && (
            <p className="defaulted-note">
              系统已根据上下文补全：{defaultedFields.map((key) => FIELD_LABELS[key as FieldKey] ?? key).join('、')}
            </p>
          )}

          <section className="question-panel">
            <h3>接下来</h3>
            <div className="question-list">
              {questions.map((question, i) => (
                <MarkdownRenderer key={i} content={question} variant="compact" />
              ))}
            </div>
          </section>

          {showReplyControls && (message.question_mode === 'question_box' ? (
            <>
              {options.length > 0 && (
                <div className="options-grid">
                  {options.map((option) => (
                    <button
                      key={`${option.label}:${option.value}`}
                      aria-label={option.label}
                      className="option-btn"
                      disabled={disabled}
                      onClick={() => submitOptionAnswer(option)}
                      type="button"
                    >
                      <span>{option.label}</span>
                      {option.description ? <small>{option.description}</small> : null}
                    </button>
                  ))}
                </div>
              )}
              <div className="input-groove">
                <input
                  type="text"
                  className="input-pebble"
                  placeholder="输入你的学习情况..."
                  value={inputValue}
                  disabled={disabled}
                  onChange={(event) => setInputValue(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter') submitInlineAnswer();
                  }}
                />
                <button type="button" disabled={disabled || !inputValue.trim()} onClick={submitInlineAnswer}>
                  +
                </button>
              </div>
            </>
          ) : (
            <div className="input-groove">
              <input
                type="text"
                className="input-pebble"
                placeholder="输入你的回答..."
                value={inputValue}
                disabled={disabled}
                onChange={(event) => setInputValue(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter') submitInlineAnswer();
                }}
              />
              <button type="button" disabled={disabled || !inputValue.trim()} onClick={submitInlineAnswer}>
                +
              </button>
            </div>
          ))}
        </>
      )}
    </CardWrapper>
  );
}

const CardWrapper = styled.article`
  max-inline-size: min(100%, var(--container-narrow));
  inline-size: fit-content;
  align-self: flex-start;
  color: var(--color-text-primary);
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  padding: var(--space-24);
  box-shadow: var(--shadow-md);

  &[data-state='basic_profile'] {
    inline-size: min(100%, var(--container-default));
    background:
      radial-gradient(circle at 10% 0%, oklch(84% 0.12 63 / 0.22), transparent 34%),
      radial-gradient(circle at 100% 18%, oklch(75% 0.09 135 / 0.16), transparent 32%),
      var(--color-surface-raised);
    border-color: oklch(84% 0.03 73 / 0.76);
    box-shadow: var(--shadow-lg);
  }

  .card-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--gap-sm);
    margin-block-end: var(--space-16);
  }

  .card-kicker,
  .card-state {
    font-size: var(--text-caption);
    line-height: 1.4;
    color: var(--color-text-secondary);
  }

  .card-state {
    display: inline-flex;
    align-items: center;
    gap: var(--space-8);
  }

  .card-state::before {
    content: '';
    inline-size: var(--space-8);
    block-size: var(--space-8);
    border-radius: var(--radius-full);
    background: var(--color-success);
  }

  h3,
  h4,
  p {
    margin: 0;
  }

  h3 {
    font-size: var(--text-h5);
    font-weight: var(--font-weight-medium);
    line-height: 1.4;
  }

  h4 {
    font-size: var(--text-h6);
    font-weight: var(--font-weight-medium);
    line-height: 1.4;
    color: var(--color-text-secondary);
  }

  .confirmed-panel,
  .question-panel,
  .profile-section,
  .profile-hero,
  .profile-narrative section {
    border-radius: var(--radius-md);
    background: var(--color-surface-raised);
    padding: var(--space-16);
  }

  .confirmed-panel,
  .question-panel {
    display: grid;
    gap: var(--gap-sm);
  }

  .confirmed-list {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-8);
  }

  .info-chip {
    display: inline-flex;
    align-items: center;
    gap: var(--space-8);
    border-radius: var(--radius-full);
    padding: var(--space-8) var(--space-12);
    background: var(--color-surface-inset);
    color: var(--color-text-secondary);
    font-size: var(--text-caption);
    line-height: 1.4;
  }

  .info-chip strong {
    color: var(--color-text-primary);
    font-weight: var(--font-weight-medium);
  }

  .info-chip[data-streaming='true'],
  .profile-section div[data-streaming='true'] {
    box-shadow: 0 0 6px var(--color-primary);
    animation: field-pulse 0.8s var(--ease-editorial) infinite alternate;
  }

  .muted-copy,
  .defaulted-note {
    color: var(--color-text-muted);
    font-size: var(--text-body-sm);
    line-height: 1.8;
  }

  .defaulted-note {
    margin-block: var(--space-12);
  }

  .question-panel {
    margin-block-start: var(--space-16);
  }

  .question-list {
    display: grid;
    gap: var(--space-8);
  }

  .question-list p {
    color: var(--color-text-primary);
    line-height: 1.8;
  }

  .question-list p::before {
    content: '//';
    color: var(--color-primary);
    margin-inline-end: var(--space-8);
  }

  .question-list ul,
  .question-list ol {
    margin: 0;
    padding-inline-start: var(--space-24);
    color: var(--color-text-primary);
    line-height: 1.8;
  }

  .question-list li {
    margin-block-end: var(--space-4);
  }

  .options-grid {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-12);
    margin-block-start: var(--space-16);
  }

  .option-btn,
  .input-groove button {
    border: 1px solid var(--color-border);
    border-radius: var(--radius-full);
    background: var(--color-surface-inset);
    color: var(--color-text-primary);
    font-family: var(--font-body);
    font-size: var(--text-body-sm);
    cursor: pointer;
    transition:
      transform var(--duration-lazy-hover) var(--ease-lazy),
      opacity var(--duration-lazy-hover) var(--ease-lazy);
  }

  .option-btn {
    display: inline-flex;
    flex-direction: column;
    align-items: flex-start;
    gap: var(--space-4);
    min-block-size: 44px;
    padding: var(--space-12) var(--space-24);
    text-align: start;
  }

  .option-btn span {
    line-height: 1.4;
  }

  .option-btn small {
    color: var(--color-text-muted);
    font-size: var(--text-caption);
    line-height: 1.5;
  }

  .option-btn:hover,
  .input-groove button:hover {
    transform: translateY(calc(var(--space-4) * -1));
  }

  .input-groove {
    display: flex;
    align-items: center;
    gap: var(--space-8);
    background: var(--color-surface-inset);
    box-shadow: var(--shadow-inset);
    border-radius: var(--radius-full);
    padding: var(--space-4);
    margin-block-start: var(--space-16);
  }

  .input-pebble {
    min-inline-size: 0;
    flex: 1;
    min-block-size: 0;
    background: transparent;
    border: none;
    font-family: var(--font-body);
    font-size: var(--text-body-sm);
    color: var(--color-text-primary);
    outline: none;
    padding-inline: var(--space-12);
  }

  .input-groove button {
    inline-size: var(--space-32);
    block-size: var(--space-32);
    min-inline-size: var(--space-32);
    min-block-size: var(--space-32);
    font-size: var(--text-h4);
    line-height: 1;
  }

  .option-btn:disabled,
  .input-pebble:disabled,
  .input-groove button:disabled {
    cursor: not-allowed;
    opacity: 0.64;
  }

  .profile-hero {
    display: grid;
    gap: var(--space-12);
    margin-block-end: var(--space-16);
    padding: var(--space-24);
  }

  .profile-hero h3 {
    font-size: var(--text-h3);
    color: var(--color-text-primary);
  }

  .profile-hero p,
  .profile-narrative p {
    color: var(--color-text-secondary);
    line-height: 1.9;
  }

  .profile-eyebrow {
    inline-size: fit-content;
    border-radius: var(--radius-full);
    padding: var(--space-8) var(--space-12);
    background: var(--color-primary-soft);
    color: var(--color-text-primary);
    font-size: var(--text-caption);
    line-height: 1.4;
  }

  .profile-meter {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-8);
    margin-block-start: var(--space-4);
  }

  .profile-meter span {
    border-radius: var(--radius-full);
    padding: var(--space-8) var(--space-12);
    background: var(--color-surface-inset);
    color: var(--color-text-secondary);
    font-size: var(--text-caption);
    line-height: 1.4;
  }

  .profile-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: var(--gap-sm);
  }

  .profile-section {
    display: grid;
    gap: var(--space-12);
    align-content: start;
    min-block-size: auto;
  }

  .profile-section dl {
    display: grid;
    gap: var(--space-8);
    margin: 0;
  }

  .profile-section div {
    display: grid;
    gap: var(--space-4);
  }

  .profile-section dt {
    color: var(--color-text-muted);
    font-size: var(--text-caption);
  }

  .profile-section dd {
    margin: 0;
    color: var(--color-text-primary);
    font-size: var(--text-body-sm);
    line-height: 1.7;
  }

  .profile-section[data-empty='true'] {
    background: var(--color-background);
  }

  .profile-section[data-empty='true'] p {
    color: var(--color-text-muted);
    font-size: var(--text-body-sm);
    line-height: 1.8;
  }

  .profile-narrative {
    display: grid;
    gap: var(--space-12);
    margin-block-start: var(--space-16);
  }

  @media (max-width: 767px) {
    inline-size: 100%;
    max-inline-size: 100%;

    .profile-grid {
      grid-template-columns: 1fr;
    }
  }

  @media (prefers-reduced-motion: reduce) {
    .option-btn,
    .input-groove button {
      transition: opacity var(--duration-instant) ease;
      transform: none;
    }

    .info-chip[data-streaming='true'],
    .profile-section div[data-streaming='true'] {
      animation: none;
    }
  }

  @keyframes field-pulse {
    from { box-shadow: 0 0 4px var(--color-primary); }
    to { box-shadow: 0 0 12px var(--color-primary); }
  }
`;
