import { useCallback, useEffect, useMemo, useState, type ChangeEvent } from 'react';
import { useParams, useSearchParams } from 'react-router-dom';
import { AnimatePresence, motion, useReducedMotion } from 'framer-motion';
import {
  fetchForestQuizSession,
  generateForestQuiz,
  streamForestAi,
  submitForestQuizAttempt,
} from '../../api/forest';
import { useAuth } from '../../contexts/AuthContext';
import { motionTokens } from '../../styles/motion-tokens';
import type {
  ForestAiContext,
  ForestAttempt,
  ForestQuiz,
  ForestQuizQuestion,
  ForestQuizSession,
} from '../../types/forest';
import { MarkdownRenderer } from '../../components/markdown/MarkdownRenderer';
import { MessageBubble } from '../../components/onboarding/MessageBubble';
import { HandwritingCanvas } from '../../components/ui/HandwritingCanvas';
import { PenTool } from 'lucide-react';
import './forest-quiz.css';

interface ForestMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  imageAttachment?: string | null;
}

type ForestPageStatus = 'idle' | 'loading' | 'ready' | 'error';
type ForestAiStatus = 'idle' | 'streaming' | 'error';

interface ForestAnswerDraft {
  question_id: string;
  value: unknown;
}

interface EmptyForestStateProps {
  label: string;
  title: string;
  message: string;
  ariaLabel: string;
}

interface ForestQuestionPanelProps {
  session: ForestQuizSession;
  quiz: ForestQuiz | null;
  attempt: ForestAttempt | null;
  selectedQuestion: ForestQuizQuestion | null;
  selectedAnswer: unknown;
  canSubmit: boolean;
  isSubmitting: boolean;
  isGenerating: boolean;
  errorMessage: string | null;
  reduceMotion: boolean;
  onSelectQuestion(questionId: string): void;
  onUpdateAnswer(questionId: string, value: unknown): void;
  onGenerateQuiz(): void;
  onSubmit(): void;
}

interface ForestQuestionCardProps {
  question: ForestQuizQuestion;
  selectedAnswer: unknown;
  reduceMotion: boolean;
  onUpdateAnswer(questionId: string, value: unknown): void;
}

interface ForestAiPanelProps {
  quiz: ForestQuiz | null;
  attempt: ForestAttempt | null;
  selectedQuestion: ForestQuizQuestion | null;
  aiStatus: ForestAiStatus;
  messages: ForestMessage[];
  reduceMotion: boolean;
  onAskForestAi(customMessage?: string, attachment?: string | null): void;
}

function getAnswerValue(answers: ForestAnswerDraft[], questionId: string): unknown {
  return answers.find((answer) => answer.question_id === questionId)?.value ?? '';
}

function toAnswerRecord(answers: ForestAnswerDraft[]): Record<string, unknown> {
  return answers.reduce<Record<string, unknown>>((record, answer) => {
    if (typeof answer.value === 'string' && answer.value.trim() === '') return record;
    return { ...record, [answer.question_id]: answer.value };
  }, {});
}

function getQuestionResult(
  attempt: ForestAttempt | null,
  questionId: string | null,
): Record<string, unknown> | null {
  const questionResults = attempt?.grading_result.question_results;
  if (!Array.isArray(questionResults) || !questionId) return null;
  const result = questionResults.find((item) => (
    item !== null
    && typeof item === 'object'
    && 'question_id' in item
    && item.question_id === questionId
  ));
  return result && typeof result === 'object' ? result as Record<string, unknown> : null;
}

function getResultText(attempt: ForestAttempt | null): string {
  if (!attempt) return '提交后，Forest AI 会结合判题结果继续解析。';
  const summary = attempt.grading_result.summary;
  if (typeof summary === 'string' && summary.trim()) return summary;
  return attempt.passed ? '本次测验已通过。' : '本次测验还需要继续打磨。';
}

function getUploadedFileName(answer: unknown): string {
  if (answer === null || typeof answer !== 'object' || !('file_name' in answer)) return '';
  const fileName = answer.file_name;
  return typeof fileName === 'string' ? fileName : '';
}

function readImageAnswer(file: File): Promise<Record<string, string>> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      resolve({
        file_name: file.name,
        mime_type: file.type,
        data_url: typeof reader.result === 'string' ? reader.result : '',
      });
    };
    reader.onerror = () => reject(new Error('图片读取失败'));
    reader.readAsDataURL(file);
  });
}

function buildAiContext(
  courseNodeId: string,
  chapterId: string,
  quiz: ForestQuiz | null,
  question: ForestQuizQuestion | null,
  answer: unknown,
  attempt: ForestAttempt | null,
): ForestAiContext {
  return {
    course_node_id: courseNodeId,
    chapter_id: chapterId,
    quiz_id: quiz?.quiz_id ?? null,
    question_id: question?.question_id ?? null,
    question,
    answer,
    grading_result: getQuestionResult(attempt, question?.question_id ?? null) ?? attempt?.grading_result ?? null,
  };
}

function initAnswers(questions: ForestQuizQuestion[]): ForestAnswerDraft[] {
  return questions
    .filter((q) => q.type === 'code' && q.starter_code)
    .map((q) => ({ question_id: q.question_id, value: q.starter_code }));
}

function EmptyForestState({ label, title, message, ariaLabel }: EmptyForestStateProps) {
  return (
    <section className="forest-quiz-page" aria-label={ariaLabel}>
      <div className="forest-ambient-sun" aria-hidden="true" />
      <div className="forest-empty-state">
        <span>{label}</span>
        <h1>{title}</h1>
        <p>{message}</p>
      </div>
    </section>
  );
}

function ForestQuestionCard({
  question,
  selectedAnswer,
  reduceMotion,
  onUpdateAnswer,
}: ForestQuestionCardProps) {
  const handleImageChange = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;
    onUpdateAnswer(question.question_id, await readImageAnswer(file));
  };
  const uploadedFileName = getUploadedFileName(selectedAnswer);

  return (
    <motion.article
      key={question.question_id}
      className="forest-question-card"
      initial={reduceMotion ? { opacity: 0 } : { opacity: 0, y: 12 }}
      animate={reduceMotion ? { opacity: 1 } : { opacity: 1, y: 0 }}
      exit={reduceMotion ? { opacity: 0 } : { opacity: 0, y: -12 }}
      transition={motionTokens.lazy}
    >
      <div className="forest-question-meta">
        <span>{question.type}</span>
        <span>{question.points} 分</span>
      </div>
      <h2>{question.prompt}</h2>
      {question.type === 'single_choice' ? (
        <div className="forest-options" role="radiogroup" aria-label="选择答案">
          {question.options.map((option) => (
            <label key={option.option_id} className="forest-option">
              <input
                type="radio"
                name={question.question_id}
                value={option.option_id}
                checked={selectedAnswer === option.option_id}
                onChange={() => onUpdateAnswer(question.question_id, option.option_id)}
              />
              <span>{option.text}</span>
            </label>
          ))}
        </div>
      ) : question.type === 'image_upload' ? (
        <label className="forest-upload-box">
          <input type="file" accept="image/*" onChange={handleImageChange} />
          <span>{uploadedFileName || question.image_prompt || '上传图片答案'}</span>
        </label>
      ) : (
        <textarea
          className="forest-answer-box"
          value={typeof selectedAnswer === 'string' ? selectedAnswer : ''}
          onChange={(event) => onUpdateAnswer(question.question_id, event.target.value)}
          placeholder={question.type === 'code' ? question.starter_code : question.image_prompt}
        />
      )}
    </motion.article>
  );
}

function ForestQuestionPanel({
  session,
  quiz,
  attempt,
  selectedQuestion,
  selectedAnswer,
  canSubmit,
  isSubmitting,
  isGenerating,
  errorMessage,
  reduceMotion,
  onSelectQuestion,
  onUpdateAnswer,
  onGenerateQuiz,
  onSubmit,
}: ForestQuestionPanelProps) {
  return (
    <motion.div
      className="forest-question-panel"
      initial={reduceMotion ? { opacity: 0 } : { opacity: 0, y: 16 }}
      animate={reduceMotion ? { opacity: 1 } : { opacity: 1, y: 0 }}
      transition={motionTokens.editorial}
    >
      <header className="forest-panel-header">
        <span>// quiz</span>
        <h1>{session.chapter.title}</h1>
        <p>{session.course.course_or_chapter_theme}</p>
      </header>

      {quiz ? (
        <>
          <div className="forest-question-tabs" aria-label="题目列表">
            {quiz.questions.map((question, index) => (
              <button
                key={question.question_id}
                type="button"
                className={question.question_id === selectedQuestion?.question_id ? 'is-active' : ''}
                onClick={() => onSelectQuestion(question.question_id)}
              >
                {index + 1}
              </button>
            ))}
          </div>

          <AnimatePresence mode="wait">
            {selectedQuestion && (
              <ForestQuestionCard
                question={selectedQuestion}
                selectedAnswer={selectedAnswer}
                reduceMotion={reduceMotion}
                onUpdateAnswer={onUpdateAnswer}
              />
            )}
          </AnimatePresence>

          <div className="forest-actions">
            <p>{getResultText(attempt)}</p>
            <button type="button" onClick={onSubmit} disabled={!canSubmit || isSubmitting}>
              {isSubmitting ? '提交中' : '提交测验'}
            </button>
          </div>
        </>
      ) : (
        <div className="forest-empty-quiz">
          <h2>这一章还没有题目</h2>
          <p>生成后即可开始作答，Forest AI 会使用当前题目上下文解析。</p>
          <button type="button" onClick={onGenerateQuiz} disabled={isGenerating}>
            {isGenerating ? '生成中' : '生成测验'}
          </button>
        </div>
      )}

      {errorMessage && <p className="forest-inline-error">{errorMessage}</p>}
    </motion.div>
  );
}

function ForestAiPanel({
  quiz,
  attempt,
  selectedQuestion,
  aiStatus,
  messages,
  reduceMotion,
  onAskForestAi,
}: ForestAiPanelProps) {
  const [showCanvas, setShowCanvas] = useState(false);
  const [imageAttachment, setImageAttachment] = useState<string | null>(null);
  const [inputValue, setInputValue] = useState('');

  return (
    <motion.aside
      className="forest-ai-panel"
      initial={reduceMotion ? { opacity: 0 } : { opacity: 0, y: 16 }}
      animate={reduceMotion ? { opacity: 1 } : { opacity: 1, y: 0 }}
      transition={motionTokens.editorial}
      aria-label="Forest AI 对话解析"
    >
      <header className="forest-ai-header">
        <span>// Forest AI</span>
        <h2>常驻解析</h2>
      </header>
      <div className="forest-ai-context">
        <p>{selectedQuestion?.prompt ?? '生成题目后，我会读取当前题目。'}</p>
        <span>{attempt ? `得分 ${attempt.score}` : '等待提交结果'}</span>
      </div>
      <div className="forest-ai-response" aria-live="polite">
        {messages.length > 0 ? (
          <div className="forest-ai-messages-list">
            {messages.map((message) => {
              if (message.role === 'user') {
                return (
                  <div key={message.id} className="forest-message-bubble-user-container">
                    <MessageBubble
                      content={message.content}
                      imageAttachment={message.imageAttachment}
                    />
                  </div>
                );
              } else {
                return (
                  <div key={message.id} className="forest-message-bubble-assistant">
                    <MarkdownRenderer content={message.content} />
                  </div>
                );
              }
            })}
          </div>
        ) : (
          <p>选择题目或提交答案后，可以让我解释为什么这样判断。</p>
        )}
      </div>

      {messages.length === 0 && (
        <button
          type="button"
          className="forest-ask-initial-button"
          onClick={() => onAskForestAi()}
          disabled={aiStatus === 'streaming' || !quiz}
          style={{
            paddingInline: 'var(--space-32)',
            minBlockSize: 'calc(var(--space-40) + var(--space-8))',
            borderRadius: 'var(--radius-full)',
            fontWeight: 'var(--font-weight-medium)',
            cursor: 'pointer',
            background: 'var(--gradient-coral)',
            color: 'var(--color-text-inverse)',
            boxShadow: 'var(--shadow-sm)',
            border: 'none',
          }}
        >
          {aiStatus === 'streaming' ? '解析中' : '请 Forest AI 解析'}
        </button>
      )}

      {quiz && (
        <div className="forest-composer-container">
          {imageAttachment && (
            <div className="image-preview-box">
              <img src={imageAttachment} alt="Preview" className="preview-thumbnail" />
              <button
                type="button"
                className="delete-preview-button"
                onClick={() => setImageAttachment(null)}
              >
                ✕
              </button>
            </div>
          )}
          <form
            className="chat-composer"
            onSubmit={(e) => {
              e.preventDefault();
              if (aiStatus === 'streaming' || (!inputValue.trim() && !imageAttachment)) return;
              onAskForestAi(inputValue, imageAttachment);
              setInputValue('');
              setImageAttachment(null);
            }}
          >
            <button
              type="button"
              className="pen-button"
              onClick={() => setShowCanvas(true)}
              title="手写画板"
              disabled={aiStatus === 'streaming'}
            >
              <PenTool className="w-4 h-4" />
            </button>
            <textarea
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              placeholder="自定义追问或手写演算草稿..."
              disabled={aiStatus === 'streaming'}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  if (aiStatus === 'streaming' || (!inputValue.trim() && !imageAttachment)) return;
                  onAskForestAi(inputValue, imageAttachment);
                  setInputValue('');
                  setImageAttachment(null);
                }
              }}
            />
            <button
              type="submit"
              className="submit-button"
              disabled={aiStatus === 'streaming' || (!inputValue.trim() && !imageAttachment)}
            >
              发送
            </button>
          </form>
        </div>
      )}

      {showCanvas && (
        <HandwritingCanvas
          onSave={(data) => {
            setImageAttachment(data);
            setShowCanvas(false);
          }}
          onClose={() => setShowCanvas(false)}
        />
      )}
    </motion.aside>
  );
}

export function ForestQuizPage() {
  const { courseNodeId } = useParams<{ courseNodeId: string }>();
  const [searchParams] = useSearchParams();
  const { token } = useAuth();
  const reduceMotion = useReducedMotion() ?? false;
  const chapterId = searchParams.get('chapter_id');

  const [status, setStatus] = useState<ForestPageStatus>('idle');
  const [session, setSession] = useState<ForestQuizSession | null>(null);
  const [quiz, setQuiz] = useState<ForestQuiz | null>(null);
  const [attempt, setAttempt] = useState<ForestAttempt | null>(null);
  const [selectedQuestionId, setSelectedQuestionId] = useState<string | null>(null);
  const [answers, setAnswers] = useState<ForestAnswerDraft[]>([]);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [isGenerating, setIsGenerating] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [aiStatus, setAiStatus] = useState<ForestAiStatus>('idle');
  const [aiText, setAiText] = useState('');
  const [messages, setMessages] = useState<ForestMessage[]>([]);

  useEffect(() => {
    setMessages([]);
  }, [selectedQuestionId]);

  const selectedQuestion = useMemo(() => {
    if (!quiz) return null;
    return quiz.questions.find((question) => question.question_id === selectedQuestionId) ?? quiz.questions[0] ?? null;
  }, [quiz, selectedQuestionId]);

  const selectedAnswer = selectedQuestion ? getAnswerValue(answers, selectedQuestion.question_id) : '';
  const canSubmit = Boolean(
    quiz && quiz.questions.length > 0 && Object.keys(toAnswerRecord(answers)).length === quiz.questions.length,
  );

  const loadSession = useCallback(async () => {
    if (!token || !courseNodeId || !chapterId) return;
    setStatus('loading');
    setErrorMessage(null);
    try {
      const nextSession = await fetchForestQuizSession(token, courseNodeId, chapterId);
      setSession(nextSession);
      setQuiz(nextSession.quiz);
      setAttempt(nextSession.latest_attempt);
      setSelectedQuestionId(nextSession.quiz?.questions[0]?.question_id ?? null);
      if (nextSession.latest_attempt) {
        const attemptAnswers = Object.entries(nextSession.latest_attempt.answers).map(([qId, val]) => ({
          question_id: qId,
          value: val,
        }));
        setAnswers(attemptAnswers);
      } else if (nextSession.quiz) {
        setAnswers(initAnswers(nextSession.quiz.questions));
      } else {
        setAnswers([]);
      }
      setStatus('ready');
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : '成林测验加载失败');
      setStatus('error');
    }
  }, [chapterId, courseNodeId, token]);

  useEffect(() => {
    void loadSession();
  }, [loadSession]);

  const updateAnswer = useCallback((questionId: string, value: unknown) => {
    setAnswers((currentAnswers) => {
      const exists = currentAnswers.some((answer) => answer.question_id === questionId);
      if (exists) {
        return currentAnswers.map((answer) => (
          answer.question_id === questionId ? { question_id: questionId, value } : answer
        ));
      }
      return [...currentAnswers, { question_id: questionId, value }];
    });
  }, []);

  const handleGenerateQuiz = useCallback(async () => {
    if (!token || !courseNodeId || !chapterId) return;
    setIsGenerating(true);
    setErrorMessage(null);
    try {
      const nextQuiz = await generateForestQuiz(token, courseNodeId, chapterId, false);
      setQuiz(nextQuiz);
      setSelectedQuestionId(nextQuiz.questions[0]?.question_id ?? null);
      setAnswers(initAnswers(nextQuiz.questions));
      setAttempt(null);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : '章节测验生成失败');
    } finally {
      setIsGenerating(false);
    }
  }, [chapterId, courseNodeId, token]);

  const askForestAi = useCallback(async (
    customMessage?: string,
    attachment?: string | null,
    nextAttempt: ForestAttempt | null = attempt
  ) => {
    if (!token || !courseNodeId || !chapterId) return;
    const context = buildAiContext(courseNodeId, chapterId, quiz, selectedQuestion, selectedAnswer, nextAttempt);

    const promptText = customMessage || '请结合当前题目、我的答案与判题结果，给出简洁解析。';

    const userMsg: ForestMessage = {
      id: `user-${Date.now()}`,
      role: 'user',
      content: promptText,
      imageAttachment: attachment,
    };

    const assistantMsgId = `assistant-${Date.now()}`;
    const assistantMsg: ForestMessage = {
      id: assistantMsgId,
      role: 'assistant',
      content: '',
    };

    setMessages((prev) => [...prev, userMsg, assistantMsg]);
    setAiStatus('streaming');

    try {
      await streamForestAi(token, context, promptText, (event) => {
        if (event.event === 'forest_ai_text_chunk' && event.chunk) {
          setMessages((prev) =>
            prev.map((msg) =>
              msg.id === assistantMsgId ? { ...msg, content: msg.content + event.chunk } : msg
            )
          );
        }
        if (event.event === 'forest_error') {
          setAiStatus('error');
          setMessages((prev) =>
            prev.map((msg) =>
              msg.id === assistantMsgId ? { ...msg, content: event.message ?? 'Forest AI 暂时不可用' } : msg
            )
          );
        }
        if (event.event === 'forest_ai_completed') {
          setAiStatus('idle');
        }
      }, attachment);
    } catch (error) {
      setAiStatus('error');
      const errMsg = error instanceof Error ? error.message : 'Forest AI 暂时不可用';
      setMessages((prev) =>
        prev.map((msg) =>
          msg.id === assistantMsgId ? { ...msg, content: errMsg } : msg
        )
      );
    }
  }, [chapterId, courseNodeId, quiz, selectedAnswer, selectedQuestion, token, attempt]);

  const handleSubmit = useCallback(async () => {
    if (!token || !quiz || !canSubmit) return;
    setIsSubmitting(true);
    setErrorMessage(null);
    try {
      const nextAttempt = await submitForestQuizAttempt(token, quiz.quiz_id, { answers: toAnswerRecord(answers) });
      setAttempt(nextAttempt);
      void askForestAi(undefined, null, nextAttempt);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : '测验提交失败');
    } finally {
      setIsSubmitting(false);
    }
  }, [answers, askForestAi, canSubmit, quiz, token]);

  const handleAskForestAi = useCallback((customMessage?: string, attachment?: string | null) => {
    void askForestAi(customMessage, attachment, attempt);
  }, [askForestAi, attempt]);

  if (!token || !courseNodeId) {
    return null;
  }

  if (!chapterId) {
    return (
      <EmptyForestState
        ariaLabel="成林测验缺少章节"
        label="// forest"
        title="还没有选中章节"
        message="请从叶茂章节进入成林测验。"
      />
    );
  }

  if (status === 'loading' || status === 'idle') {
    return (
      <EmptyForestState
        ariaLabel="成林测验加载中"
        label="// loading"
        title="正在准备章节测验"
        message="Forest AI 会在题目旁边等你。"
      />
    );
  }

  if (status === 'error' || !session) {
    return (
      <EmptyForestState
        ariaLabel="成林测验加载失败"
        label="// error"
        title="测验加载失败"
        message={errorMessage ?? '请稍后再试。'}
      />
    );
  }

  return (
    <section className="forest-quiz-page" aria-label={`${session.chapter.title}章节测验`}>
      <div className="forest-ambient-sun" aria-hidden="true" />
      <main className="forest-quiz-shell">
        <ForestQuestionPanel
          session={session}
          quiz={quiz}
          attempt={attempt}
          selectedQuestion={selectedQuestion}
          selectedAnswer={selectedAnswer}
          canSubmit={canSubmit}
          isSubmitting={isSubmitting}
          isGenerating={isGenerating}
          errorMessage={errorMessage}
          reduceMotion={reduceMotion}
          onSelectQuestion={setSelectedQuestionId}
          onUpdateAnswer={updateAnswer}
          onGenerateQuiz={handleGenerateQuiz}
          onSubmit={handleSubmit}
        />

        <ForestAiPanel
          quiz={quiz}
          attempt={attempt}
          selectedQuestion={selectedQuestion}
          aiStatus={aiStatus}
          messages={messages}
          reduceMotion={reduceMotion}
          onAskForestAi={handleAskForestAi}
        />
      </main>
    </section>
  );
}
