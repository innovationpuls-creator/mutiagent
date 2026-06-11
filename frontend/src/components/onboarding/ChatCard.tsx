import React from 'react';
import { useAiWidget } from '../../context/AiWidgetContext';
import { MarkdownRenderer } from '../markdown';
import type { ConfirmedInfo, PartialStructuredData, QuestionBoxOption, SessionMessage } from '../../types/chat';
import { CardWrapper } from './ChatCard.styles';
import { buildLearningPathGenerationDraft } from '../../onboarding/learningPathFlow';

interface ChatCardProps {
  message: SessionMessage;
  onSendReply?: (text: string) => void;
  disabled?: boolean;
  partialData?: PartialStructuredData | null;
  showPathGenerationCta?: boolean;
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

export function ChatCard({ message, onSendReply, disabled = false, partialData, showPathGenerationCta = true }: ChatCardProps) {
  const { openWithDraft } = useAiWidget();

  const handleGeneratePathDraft = () => {
    openWithDraft(buildLearningPathGenerationDraft());
  };

  const [inputValue, setInputValue] = React.useState('');
  const [hasSubmittedReply, setHasSubmittedReply] = React.useState(false);
  const [formValues, setFormValues] = React.useState<Record<string, string | string[]>>({});
  const [otherInputValues, setOtherInputValues] = React.useState<Record<string, string>>({});
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

  const handleSingleSelect = (fieldName: string, value: string) => {
    if (disabled || hasSubmittedReply) return;
    setFormValues((prev) => ({
      ...prev,
      [fieldName]: value,
    }));
  };

  const handleMultiSelect = (fieldName: string, value: string) => {
    if (disabled || hasSubmittedReply) return;
    setFormValues((prev) => {
      const current = Array.isArray(prev[fieldName]) ? (prev[fieldName] as string[]) : [];
      const updated = current.includes(value)
        ? current.filter((v) => v !== value)
        : [...current, value];
      return {
        ...prev,
        [fieldName]: updated,
      };
    });
  };

  const handleOtherInputChange = (fieldName: string, value: string) => {
    if (disabled || hasSubmittedReply) return;
    setOtherInputValues((prev) => ({
      ...prev,
      [fieldName]: value,
    }));
  };

  const isSubmitDisabled = disabled || hasSubmittedReply || !message.question_form || message.question_form.questions.some((q) => {
    if (!q.required) return false;
    const val = formValues[q.field_name];
    if (q.input_type === 'multi_choice') {
      const arr = Array.isArray(val) ? val : [];
      if (arr.length === 0) return true;
      if (arr.includes('__free_text__') && !otherInputValues[q.field_name]?.trim()) return true;
    } else if (q.input_type === 'single_choice') {
      if (!val) return true;
      if (val === '__free_text__' && !otherInputValues[q.field_name]?.trim()) return true;
    } else {
      if (!otherInputValues[q.field_name]?.trim()) return true;
    }
    return false;
  });

  const handleFormSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (isSubmitDisabled) return;
    
    const lines = ['画像表单提交：'];
    message.question_form!.questions.forEach((q) => {
      const val = formValues[q.field_name];
      if (q.input_type === 'multi_choice') {
        const arr = Array.isArray(val) ? [...val] : [];
        const idx = arr.indexOf('__free_text__');
        if (idx !== -1) {
          arr.splice(idx, 1);
          const other = otherInputValues[q.field_name]?.trim();
          if (other) arr.push(other);
        }
        if (arr.length > 0) {
          lines.push(`${q.field_name}：${arr.join('、')}`);
        }
      } else if (q.input_type === 'single_choice') {
        let str = typeof val === 'string' ? val : '';
        if (str === '__free_text__') {
          str = otherInputValues[q.field_name]?.trim() ?? '';
        }
        if (str) {
          lines.push(`${q.field_name}：${str}`);
        }
      } else {
        const str = otherInputValues[q.field_name]?.trim() ?? '';
        if (str) {
          lines.push(`${q.field_name}：${str}`);
        }
      }
    });
    
    onSendReply?.(lines.join('\n'));
    setHasSubmittedReply(true);
  };

  const renderQuestionForm = () => {
    const form = message.question_form;
    if (!form || !form.questions || form.questions.length === 0) return null;

    return (
      <div className="question-form">
        <div className="form-header">
          <h3>{form.title}</h3>
          {form.description && <p className="form-description">{form.description}</p>}
        </div>
        <div className="form-questions">
          {form.questions.map((q) => {
            const val = formValues[q.field_name];
            const isSingle = q.input_type === 'single_choice';
            const isMulti = q.input_type === 'multi_choice';
            const isFreeText = q.input_type === 'free_text';
            
            const isOtherSelected = isSingle
              ? val === '__free_text__'
              : isMulti && Array.isArray(val) && val.includes('__free_text__');

            return (
              <div key={q.field_name} className="form-question-group">
                <label className="form-question-label">
                  {q.label}
                  {q.required && <span className="required-star">*</span>}
                </label>
                {q.description && <span className="form-field-desc">{q.description}</span>}
                
                {(isSingle || isMulti) && (
                  <div className="chip-grid">
                    {q.options.map((opt) => {
                      const isSelected = isSingle
                        ? val === opt.value
                        : isMulti && Array.isArray(val) && val.includes(opt.value);
                      
                      return (
                        <button
                          key={opt.value}
                          type="button"
                          className={`form-chip ${isSelected ? 'selected' : ''}`}
                          disabled={disabled || hasSubmittedReply}
                          onClick={() => {
                            if (isSingle) {
                              handleSingleSelect(q.field_name, opt.value);
                            } else {
                              handleMultiSelect(q.field_name, opt.value);
                            }
                          }}
                        >
                          {opt.label}
                        </button>
                      );
                    })}
                  </div>
                )}

                {(isFreeText || isOtherSelected) && (
                  <input
                    type="text"
                    className="form-input-text"
                    disabled={disabled || hasSubmittedReply}
                    value={otherInputValues[q.field_name] ?? ''}
                    onChange={(e) => handleOtherInputChange(q.field_name, e.target.value)}
                    placeholder={isFreeText ? '请填写...' : '请补充其他内容...'}
                  />
                )}
              </div>
            );
          })}
        </div>
        
        {showReplyControls && (
          <button
            type="button"
            className="form-submit-btn"
            disabled={isSubmitDisabled}
            onClick={handleFormSubmit}
          >
            {form.submit_label || '提交'}
          </button>
        )}
      </div>
    );
  };

  return (
    <CardWrapper data-state={message.type}>
      <header className="card-head">
        <span className="card-kicker">{STAGE_LABELS[message.stage]}</span>
        <span className="card-state">{message.type === 'basic_profile' ? '已生成' : '采集中'}</span>
      </header>

      {message.type === 'basic_profile' ? (
        <>
          {showPathGenerationCta && (
            <div className="profile-transition-banner">
              <div className="completed-badge">
                <span className="badge-dot" />
                <span>基础画像分析完成</span>
              </div>
              <div className="sprout-avatar-container">
                <div className="sprout-orb">
                  <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="var(--color-primary)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M12 22V12"></path>
                    <path d="M12 12c0-2.8 2.2-5 5-5h2"></path>
                    <path d="M12 15c0-2.8-2.2-5-5-5H5"></path>
                  </svg>
                </div>
              </div>
              <h3>了解自己，是成长的第一步。</h3>
              <p className="transition-explanation">
                我们已经根据你的年级、专业以及优势与瓶颈，为你定制编织了一条专属的课程藤蔓。在你的学习路径中，已自动弱化你熟悉的领域，并为你的薄弱点融入了专项强化章节。
              </p>
              <button className="cta-open-path-btn" onClick={handleGeneratePathDraft} type="button">
                <span>生成学习路径</span>
                <span className="arrow">➔</span>
              </button>
            </div>
          )}

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

          {message.question_form && message.question_form.questions && message.question_form.questions.length > 0 ? (
            renderQuestionForm()
          ) : (
            <>
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
        </>
      )}
    </CardWrapper>
  );
}
