import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { LeafPage } from './LeafPage';
import { AuthProvider } from '../../contexts/AuthContext';
import { AiWidgetProvider } from '../../context/AiWidgetContext';

const fetchLeafCourseMock = vi.fn();
const openWithDraftMock = vi.fn();

vi.mock('../../api/leaf', () => ({
  fetchLeafCourse: (...args: unknown[]) => fetchLeafCourseMock(...args),
}));

vi.mock('../../context/AiWidgetContext', async () => {
  const actual = await vi.importActual<typeof import('../../context/AiWidgetContext')>('../../context/AiWidgetContext');
  return {
    ...actual,
    useAiWidget: () => ({
      widgetState: 'HIDDEN',
      setWidgetState: vi.fn(),
      pendingMessage: null,
      openWithMessage: vi.fn(),
      openWithDraft: openWithDraftMock,
      clearPendingMessage: vi.fn(),
    }),
  };
});

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

function leafPayload(overrides: Record<string, unknown> = {}) {
  return {
    access_state: 'available',
    course: {
      course_node_id: 'year_3_course_1',
      grade_id: 'year_3',
      course_or_chapter_theme: 'AI Agent 开发',
      course_goal: '完成 AI Agent 开发',
      status: 'current',
      has_outline: true,
    },
    outline: { course_id: 'year_3_course_1', course_name: 'AI Agent 开发' },
    sections: [
      { section_id: '1', parent_section_id: null, depth: 1, title: '第一章：需求拆解', order_index: 1, description: '确认边界', key_knowledge_points: ['边界'] },
      { section_id: '1.1', parent_section_id: '1', depth: 2, title: '学习目标', order_index: 2, description: '明确目标', key_knowledge_points: ['目标'] },
    ],
    section_composed_markdowns: {
      '1.1': {
        section_id: '1.1',
        parent_section_id: '1',
        title: '学习目标',
        markdown: '# 学习目标',
        generated_at: '2026-06-06T00:00:00Z',
        blocks: [
          { type: 'markdown', markdown: '# 学习目标\n\n正文内容' },
          { type: 'video', brief_id: 'video_1', title: '导入视频', purpose: '建立直觉', status: 'unavailable', videos: [] },
          { type: 'animation', brief_id: 'anim_1', title: '目标动画', status: 'unavailable', html: '' },
        ],
      },
    },
    generation_status: null,
    can_generate: true,
    first_generatable_chapter_id: '1',
    locked_reason: null,
    ...overrides,
  };
}

function renderLeaf(initialPath = '/leaf/year_3_course_1') {
  stubAuth();
  return render(
    <AuthProvider>
      <AiWidgetProvider>
        <MemoryRouter initialEntries={[initialPath]}>
          <Routes>
            <Route path="/leaf/:courseNodeId" element={<LeafPage />} />
            <Route path="/branch" element={<div>Branch Page</div>} />
            <Route path="/forest/:courseNodeId" element={<div>Forest Page</div>} />
          </Routes>
        </MemoryRouter>
      </AiWidgetProvider>
    </AuthProvider>,
  );
}

describe('LeafPage', () => {
  it('loads course content and selects first generated leaf section', async () => {
    fetchLeafCourseMock.mockResolvedValue(leafPayload());

    renderLeaf();

    await waitFor(() => expect(screen.getByText('AI Agent 开发')).toBeTruthy());
    expect(screen.getByText('学习目标')).toBeTruthy();
    expect(screen.getByText('正文内容')).toBeTruthy();
    expect(screen.getByText('视频资源暂时不可用')).toBeTruthy();
    expect(screen.getByText('动画暂时不可用')).toBeTruthy();
  });

  it('opens AI draft prompt from first chapter generation entry', async () => {
    fetchLeafCourseMock.mockResolvedValue(leafPayload({ section_composed_markdowns: {} }));

    renderLeaf();

    await waitFor(() => expect(screen.getByText('让 AI 生成本章内容')).toBeTruthy());
    fireEvent.click(screen.getByText('让 AI 生成本章内容'));

    expect(openWithDraftMock).toHaveBeenCalledWith(expect.stringContaining('[LEAF_RESOURCE_GENERATION]'));
    expect(openWithDraftMock).toHaveBeenCalledWith(expect.stringContaining('course_node_id: year_3_course_1'));
  });

  it('does not show generation entry for completed course', async () => {
    const base = leafPayload();
    fetchLeafCourseMock.mockResolvedValue(leafPayload({
      course: { ...(base.course as Record<string, unknown>), status: 'completed' },
      can_generate: false,
      first_generatable_chapter_id: null,
    }));

    renderLeaf();

    await waitFor(() => expect(screen.getByText('AI Agent 开发')).toBeTruthy());
    expect(screen.queryByText('让 AI 生成本章内容')).toBeNull();
  });

  it('shows generation progress and reloads after generation completes', async () => {
    fetchLeafCourseMock
      .mockResolvedValueOnce(leafPayload({ generation_status: null }))
      .mockResolvedValueOnce(leafPayload());

    renderLeaf();

    await waitFor(() => expect(screen.getByText('AI Agent 开发')).toBeTruthy());

    window.dispatchEvent(new CustomEvent('mutiagent-leaf-generation-event', {
      detail: {
        courseId: 'year_3_course_1',
        chapterSectionId: '1',
        sectionId: '1.1',
        phase: 'markdown',
        status: 'running',
        message: '正在生成文案',
      },
    }));

    expect(screen.getByText('正在生成文案')).toBeTruthy();

    window.dispatchEvent(new CustomEvent('mutiagent-leaf-generation-completed', {
      detail: { courseId: 'year_3_course_1' },
    }));

    await waitFor(() => expect(fetchLeafCourseMock).toHaveBeenCalledTimes(2));
  });
});
