import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { AuthProvider } from '../../contexts/AuthContext';
import { ForestQuizPage } from './ForestQuizPage';
import type { ForestQuizSession } from '../../types/forest';

const fetchForestQuizSessionMock = vi.fn();
const generateForestQuizMock = vi.fn();
const submitForestQuizAttemptMock = vi.fn();
const streamForestAiMock = vi.fn();

vi.mock('../../api/forest', () => ({
  fetchForestQuizSession: (...args: unknown[]) => fetchForestQuizSessionMock(...args),
  generateForestQuiz: (...args: unknown[]) => generateForestQuizMock(...args),
  submitForestQuizAttempt: (...args: unknown[]) => submitForestQuizAttemptMock(...args),
  streamForestAi: (...args: unknown[]) => streamForestAiMock(...args),
}));

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

function stubAuth() {
  const store: Record<string, string> = {
    'mutiagent-auth': JSON.stringify({
      token: 'token-1',
      user: {
        uid: 'user-1',
        username: '测试用户',
        identifier: 'user@example.com',
        provider: 'password',
        is_active: true,
        created_at: '2026-06-02T00:00:00Z',
        last_login_at: null,
      },
    }),
  };
  vi.stubGlobal('localStorage', {
    getItem: vi.fn((key: string) => store[key] ?? null),
    setItem: vi.fn((key: string, value: string) => {
      store[key] = value;
    }),
    removeItem: vi.fn((key: string) => {
      delete store[key];
    }),
  });
}

function forestSession(overrides: Partial<ForestQuizSession> = {}): ForestQuizSession {
  return {
    course: {
      course_node_id: 'year_3_course_2',
      grade_id: 'year_3',
      course_or_chapter_theme: 'AI Agent 开发',
      course_goal: '完成 AI Agent 开发',
      status: 'current',
      has_outline: true,
    },
    chapter: {
      section_id: '1',
      parent_section_id: null,
      depth: 1,
      title: '第一章：需求拆解',
      order_index: 1,
      description: '确认边界',
      key_knowledge_points: ['边界'],
    },
    quiz: null,
    latest_attempt: null,
    progress: {
      course_node_id: 'year_3_course_2',
      chapter_id: '1',
      state: 'available',
      best_score: 0,
      latest_attempt_id: null,
      passed_at: null,
      updated_at: '2026-06-09T00:00:00Z',
    },
    next_unlocked_chapter_id: null,
    next_course_id: null,
    ...overrides,
  };
}

function renderForest(initialPath = '/forest/year_3_course_2?chapter_id=1') {
  stubAuth();
  return render(
    <AuthProvider>
      <MemoryRouter initialEntries={[initialPath]}>
        <Routes>
          <Route path="/forest/:courseNodeId" element={<ForestQuizPage />} />
        </Routes>
      </MemoryRouter>
    </AuthProvider>,
  );
}

describe('ForestQuizPage', () => {
  it('shows empty state when chapter_id is missing', async () => {
    renderForest('/forest/year_3_course_2');

    expect(await screen.findByText('还没有选中章节')).toBeTruthy();
    expect(fetchForestQuizSessionMock).not.toHaveBeenCalled();
  });

  it('generates quiz, submits answers, and streams Forest AI analysis', async () => {
    fetchForestQuizSessionMock.mockResolvedValue(forestSession());
    generateForestQuizMock.mockResolvedValue({
      quiz_id: 'quiz_1',
      course_node_id: 'year_3_course_2',
      chapter_id: '1',
      status: 'ready',
      generation_error: '',
      created_at: '2026-06-09T00:00:00Z',
      updated_at: '2026-06-09T00:00:00Z',
      questions: [
        {
          question_id: 'q1',
          type: 'single_choice',
          prompt: '本章首要目标是什么？',
          options: [{ option_id: 'A', text: '确认边界' }],
          starter_code: '',
          image_prompt: '',
          points: 100,
        },
      ],
    });
    submitForestQuizAttemptMock.mockResolvedValue({
      attempt_id: 'attempt_1',
      quiz_id: 'quiz_1',
      score: 72,
      passed: true,
      answers: { q1: 'A' },
      grading_result: { score: 72, passed: true, question_results: [], summary: '已经通过。' },
      created_at: '2026-06-09T00:00:00Z',
    });
    streamForestAiMock.mockImplementation(async (_token, _context, _message, onEvent) => {
      onEvent({ event: 'forest_ai_text_chunk', chunk: '先看题干，' });
      onEvent({ event: 'forest_ai_text_chunk', chunk: '再看答案。' });
      onEvent({ event: 'forest_ai_completed', message: 'completed' });
    });

    renderForest();

    fireEvent.click(await screen.findByRole('button', { name: '生成测验' }));
    await screen.findByRole('heading', { name: '本章首要目标是什么？', level: 2 });
    fireEvent.click(screen.getByLabelText('确认边界'));
    const submitButton = screen.getByRole('button', { name: '提交测验' }) as HTMLButtonElement;
    await waitFor(() => expect(submitButton.disabled).toBe(false));
    fireEvent.click(submitButton);

    await waitFor(() => expect(submitForestQuizAttemptMock).toHaveBeenCalledWith(
      'token-1',
      'quiz_1',
      { answers: { q1: 'A' } },
    ));
    await waitFor(() => expect(screen.getByText('先看题干，再看答案。')).toBeTruthy());
  });

  it('allows user to send custom follow-up message with handwriting canvas drawing', async () => {
    HTMLCanvasElement.prototype.getContext = vi.fn().mockReturnValue({
      scale: vi.fn(),
      beginPath: vi.fn(),
      moveTo: vi.fn(),
      lineTo: vi.fn(),
      stroke: vi.fn(),
      clearRect: vi.fn(),
    });
    HTMLCanvasElement.prototype.toDataURL = vi.fn().mockReturnValue('data:image/png;base64,drawingdata');

    fetchForestQuizSessionMock.mockResolvedValue(forestSession({
      quiz: {
        quiz_id: 'quiz_1',
        course_node_id: 'year_3_course_2',
        chapter_id: '1',
        status: 'ready',
        generation_error: '',
        created_at: '2026-06-09T00:00:00Z',
        updated_at: '2026-06-09T00:00:00Z',
        questions: [
          {
            question_id: 'q1',
            type: 'single_choice',
            prompt: '本章首要目标是什么？',
            options: [{ option_id: 'A', text: '确认边界' }],
            starter_code: '',
            image_prompt: '',
            points: 100,
          },
        ],
      },
    }));

    streamForestAiMock.mockImplementation(async (_token, _context, message, onEvent) => {
      onEvent({ event: 'forest_ai_text_chunk', chunk: `解析自定义问题：${message}` });
      onEvent({ event: 'forest_ai_completed', message: 'completed' });
    });

    renderForest();

    const textarea = await screen.findByPlaceholderText('自定义追问或手写演算草稿...');
    const penButton = screen.getByTitle('手写画板');
    fireEvent.click(penButton);

    expect(screen.getByText('手写笔记/草图')).toBeTruthy();

    const saveButton = screen.getByRole('button', { name: '确认导出' });
    fireEvent.click(saveButton);

    await waitFor(() => expect(screen.queryByText('手写笔记/草图')).toBeNull());
    expect(screen.getByAltText('Preview')).toBeTruthy();

    fireEvent.change(textarea, { target: { value: '为什么这里的A是正确答案？' } });

    const sendButton = screen.getByRole('button', { name: '发送' });
    fireEvent.click(sendButton);

    await waitFor(() => {
      expect(streamForestAiMock).toHaveBeenCalledWith(
        'token-1',
        expect.any(Object),
        '为什么这里的A是正确答案？',
        expect.any(Function),
        'data:image/png;base64,drawingdata'
      );
    });

    await waitFor(() => {
      expect(screen.getByText('解析自定义问题：为什么这里的A是正确答案？')).toBeTruthy();
    });
  });
});
