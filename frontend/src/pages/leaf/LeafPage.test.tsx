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

function decodeSvgDataUrl(value: string) {
  const parts = value.split(',', 2);
  return parts[1] ? decodeURIComponent(parts[1]) : '';
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

    await waitFor(() => expect(screen.getByRole('heading', { name: '1.1 学习目标', level: 1 })).toBeTruthy());
    expect(screen.getByLabelText('AI Agent 开发课程内容')).toBeTruthy();
    expect(screen.getByText('学习目标')).toBeTruthy();
    expect(screen.getByText('正文内容')).toBeTruthy();
    expect(screen.getByText('视频生成失败')).toBeTruthy();
    expect(screen.getByText('动画生成失败')).toBeTruthy();
    expect(screen.queryByText('Key Concept')).toBeNull();
    expect(screen.queryByText('Lesson Quiz')).toBeNull();
    expect(screen.queryByText('Question 1 of 3')).toBeNull();
    expect(screen.queryByText('It provides a foundational overview.')).toBeNull();
  });

  it('renders generated teaching tables and code blocks as markdown content', async () => {
    fetchLeafCourseMock.mockResolvedValue(leafPayload({
      section_composed_markdowns: {
        '1.1': {
          section_id: '1.1',
          parent_section_id: '1',
          title: '学习目标',
          markdown: '# 学习目标',
          generated_at: '2026-06-06T00:00:00Z',
          blocks: [
            {
              type: 'markdown',
              markdown: [
                '## 步骤讲解',
                '',
                '| 步骤 | 输入材料 | 产出物 |',
                '| --- | --- | --- |',
                '| 目标收敛 | 画像、学习路径、章节大纲 | 可验收学习目标 |',
                '',
                '```json',
                '{"model":"qwen","messages":[]}',
                '```',
              ].join('\n'),
            },
          ],
        },
      },
    }));

    renderLeaf();

    await waitFor(() => expect(screen.getByRole('heading', { name: '1.1 学习目标', level: 1 })).toBeTruthy());
    expect(screen.getByRole('table')).toBeTruthy();
    expect(screen.getByRole('columnheader', { name: '步骤' })).toBeTruthy();
    expect(screen.getByRole('cell', { name: '可验收学习目标' })).toBeTruthy();
    expect(screen.getByText('{"model":"qwen","messages":[]}')).toBeTruthy();
  });

  it('renders the video cover when a video resource is available', async () => {
    fetchLeafCourseMock.mockResolvedValue(leafPayload({
      section_composed_markdowns: {
        '1.1': {
          section_id: '1.1',
          parent_section_id: '1',
          title: '学习目标',
          markdown: '# 学习目标',
          generated_at: '2026-06-06T00:00:00Z',
          blocks: [
            {
              type: 'video',
              brief_id: 'video_1',
              title: '导入视频',
              purpose: '建立直觉',
              status: 'available',
              videos: [
                {
                  title: '深入 LangChain 系列 - PromptTemplate',
                  url: 'https://www.youtube.com/watch?v=nQX61qSL-uE',
                  cover_url: 'https://img.youtube.com/vi/nQX61qSL-uE/hqdefault.jpg',
                  cover_status: 'provided',
                  source: 'youtube',
                },
              ],
            },
          ],
        },
      },
    }));

    renderLeaf();

    const image = await screen.findByAltText('深入 LangChain 系列 - PromptTemplate');
    expect(image.getAttribute('src')).toBe('https://img.youtube.com/vi/nQX61qSL-uE/hqdefault.jpg');
    expect(screen.getByText('深入 LangChain 系列 - PromptTemplate')).toBeTruthy();
  });

  it('falls back to a local svg cover when cover_url is empty', async () => {
    fetchLeafCourseMock.mockResolvedValue(leafPayload({
      section_composed_markdowns: {
        '1.1': {
          section_id: '1.1',
          parent_section_id: '1',
          title: '学习目标',
          markdown: '# 学习目标',
          generated_at: '2026-06-06T00:00:00Z',
          blocks: [
            {
              type: 'video',
              brief_id: 'video_1',
              title: '导入视频',
              purpose: '建立直觉',
              status: 'available',
              videos: [
                {
                  title: 'PromptTemplate 实战',
                  url: 'https://www.youtube.com/watch?v=nQX61qSL-uE',
                  cover_url: '',
                  cover_status: '',
                  source: 'youtube',
                },
              ],
            },
          ],
        },
      },
    }));

    renderLeaf();

    const image = await screen.findByAltText('PromptTemplate 实战');
    const src = image.getAttribute('src') ?? '';
    expect(src.startsWith('data:image/svg+xml;utf8,')).toBe(true);
    expect(decodeSvgDataUrl(src)).toContain('PromptTemplate 实战');
  });

  it('falls back to a local svg cover when the remote image fails to load', async () => {
    fetchLeafCourseMock.mockResolvedValue(leafPayload({
      section_composed_markdowns: {
        '1.1': {
          section_id: '1.1',
          parent_section_id: '1',
          title: '学习目标',
          markdown: '# 学习目标',
          generated_at: '2026-06-06T00:00:00Z',
          blocks: [
            {
              type: 'video',
              brief_id: 'video_1',
              title: '导入视频',
              purpose: '建立直觉',
              status: 'available',
              videos: [
                {
                  title: 'LCEL 表达式基础',
                  url: 'https://www.youtube.com/watch?v=nQX61qSL-uE',
                  cover_url: 'https://img.youtube.com/vi/nQX61qSL-uE/missing.jpg',
                  cover_status: 'provided',
                  source: 'youtube',
                },
              ],
            },
          ],
        },
      },
    }));

    renderLeaf();

    const image = await screen.findByAltText('LCEL 表达式基础');
    expect(image.getAttribute('src')).toBe('https://img.youtube.com/vi/nQX61qSL-uE/missing.jpg');

    fireEvent.error(image);

    const src = image.getAttribute('src') ?? '';
    expect(src.startsWith('data:image/svg+xml;utf8,')).toBe(true);
    expect(decodeSvgDataUrl(src)).toContain('LCEL 表达式基础');
  });

  it('opens AI draft prompt from first chapter generation entry', async () => {
    fetchLeafCourseMock.mockResolvedValue(leafPayload({ section_composed_markdowns: {} }));

    renderLeaf();

    await waitFor(() => expect(screen.getByText('让 AI 生成本章内容')).toBeTruthy());
    fireEvent.click(screen.getByText('让 AI 生成本章内容'));

    expect(openWithDraftMock).toHaveBeenCalledWith(expect.stringContaining('[LEAF_RESOURCE_GENERATION]'));
    expect(openWithDraftMock).toHaveBeenCalledWith(expect.stringContaining('course_node_id: year_3_course_1'));
    expect(openWithDraftMock).toHaveBeenCalledWith(expect.stringContaining('mode: generate'));
  });

  it('opens AI draft prompt from the left outline generation entry', async () => {
    const base = leafPayload();
    fetchLeafCourseMock.mockResolvedValue(leafPayload({
      course: { ...(base.course as Record<string, unknown>), has_outline: false },
      outline: null,
      sections: [],
      section_composed_markdowns: {},
      first_generatable_chapter_id: '1',
    }));

    renderLeaf();

    await waitFor(() => expect(screen.getByText('生成课程大纲')).toBeTruthy());
    fireEvent.click(screen.getByText('生成课程大纲'));

    expect(openWithDraftMock).toHaveBeenCalledWith('帮我生成《AI Agent 开发》的大纲');
  });

  it('refreshes leaf outline after course outline generation completes and hides the outline entry', async () => {
    const base = leafPayload();
    fetchLeafCourseMock
      .mockResolvedValueOnce(leafPayload({
        course: { ...(base.course as Record<string, unknown>), has_outline: false },
        outline: null,
        sections: [],
        section_composed_markdowns: {},
        first_generatable_chapter_id: '1',
      }))
      .mockResolvedValueOnce(leafPayload());

    renderLeaf();

    await waitFor(() => expect(screen.getByText('生成课程大纲')).toBeTruthy());

    window.dispatchEvent(new CustomEvent('mutiagent-leaf-generation-completed', {
      detail: { courseId: 'year_3_course_1', reason: 'course_outline' },
    }));

    await waitFor(() => expect(fetchLeafCourseMock).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(screen.queryByText('生成课程大纲')).toBeNull());
    expect(screen.getByRole('heading', { name: '1.1 学习目标', level: 1 })).toBeTruthy();
  });

  it('hides the generation entry when the selected chapter is not the first generatable chapter', async () => {
    const base = leafPayload({
      sections: [
        { section_id: '1', parent_section_id: null, depth: 1, title: '第一章：需求拆解', order_index: 1, description: '确认边界', key_knowledge_points: ['边界'] },
        { section_id: '1.1', parent_section_id: '1', depth: 2, title: '学习目标', order_index: 2, description: '明确目标', key_knowledge_points: ['目标'] },
        { section_id: '3', parent_section_id: null, depth: 1, title: '第三章：Vector Similarity Search Implementation', order_index: 3, description: '实现向量检索', key_knowledge_points: ['向量检索'] },
        { section_id: '3.1', parent_section_id: '3', depth: 2, title: '学习目标', order_index: 4, description: '明确第三章目标', key_knowledge_points: ['向量检索目标'] },
      ],
      section_composed_markdowns: {
        '1.1': {
          section_id: '1.1',
          parent_section_id: '1',
          title: '学习目标',
          markdown: '# 学习目标',
          generated_at: '2026-06-06T00:00:00Z',
          blocks: [{ type: 'markdown', markdown: '# 学习目标\n\n正文内容' }],
        },
      },
      first_generatable_chapter_id: '1',
    });
    fetchLeafCourseMock.mockResolvedValue(base);

    renderLeaf('/leaf/year_3_course_1?section_id=3.1');

    await waitFor(() => expect(screen.getByRole('heading', { name: '3.1 学习目标', level: 1 })).toBeTruthy());
    expect(screen.queryByText('让 AI 生成本章内容')).toBeNull();
  });

  it('opens AI regeneration prompt when the chapter already has generated leaf content', async () => {
    fetchLeafCourseMock.mockResolvedValue(leafPayload());

    renderLeaf();

    await waitFor(() => expect(screen.getByText('让 AI 生成本章内容')).toBeTruthy());
    fireEvent.click(screen.getByText('让 AI 生成本章内容'));

    expect(openWithDraftMock).toHaveBeenCalledWith(expect.stringContaining('[LEAF_RESOURCE_GENERATION]'));
    expect(openWithDraftMock).toHaveBeenCalledWith(expect.stringContaining('chapter_section_id: 1'));
    expect(openWithDraftMock).toHaveBeenCalledWith(expect.stringContaining('mode: regenerate'));
  });

  it('opens AI draft prompt even when the course outline has not been generated yet', async () => {
    const base = leafPayload();
    fetchLeafCourseMock.mockResolvedValue(leafPayload({
      course: { ...(base.course as Record<string, unknown>), has_outline: false },
      outline: null,
      sections: [],
      section_composed_markdowns: {},
      first_generatable_chapter_id: '1',
    }));

    renderLeaf();

    await waitFor(() => expect(screen.getByText('让 AI 生成本章内容')).toBeTruthy());
    fireEvent.click(screen.getByText('让 AI 生成本章内容'));

    expect(openWithDraftMock).toHaveBeenCalledWith(expect.stringContaining('第一章'));
    expect(openWithDraftMock).toHaveBeenCalledWith(expect.stringContaining('chapter_section_id: 1'));
  });

  it('does not show generation entry for completed course', async () => {
    const base = leafPayload();
    fetchLeafCourseMock.mockResolvedValue(leafPayload({
      course: { ...(base.course as Record<string, unknown>), status: 'completed' },
      can_generate: false,
      first_generatable_chapter_id: null,
    }));

    renderLeaf();

    await waitFor(() => expect(screen.getByRole('heading', { name: '1.1 学习目标', level: 1 })).toBeTruthy());
    expect(screen.queryByText('让 AI 生成本章内容')).toBeNull();
  });

  it('shows generation progress and reloads after generation completes', async () => {
    fetchLeafCourseMock
      .mockResolvedValueOnce(leafPayload({ generation_status: null }))
      .mockResolvedValueOnce(leafPayload({ section_composed_markdowns: {} }))
      .mockResolvedValueOnce(leafPayload());

    renderLeaf();

    await waitFor(() => expect(screen.getByRole('heading', { name: '1.1 学习目标', level: 1 })).toBeTruthy());

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
      detail: { courseId: 'year_3_course_1', reason: 'course_resource' },
    }));

    await waitFor(() => expect(fetchLeafCourseMock).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(fetchLeafCourseMock).toHaveBeenCalledTimes(3));
  });

  it('shows generation failure without reloading stale content', async () => {
    fetchLeafCourseMock.mockResolvedValue(leafPayload({ generation_status: null }));

    renderLeaf();

    await waitFor(() => expect(screen.getByRole('heading', { name: '1.1 学习目标', level: 1 })).toBeTruthy());

    window.dispatchEvent(new CustomEvent('mutiagent-leaf-generation-event', {
      detail: {
        courseId: 'year_3_course_1',
        chapterSectionId: '1',
        sectionId: null,
        phase: 'video',
        status: 'error',
        message: '视频资源未生成，请稍后重试。',
      },
    }));

    expect(screen.getByRole('status').textContent).toContain('生成失败');
    expect(screen.getByText('视频资源未生成，请稍后重试。')).toBeTruthy();
    expect(fetchLeafCourseMock).toHaveBeenCalledTimes(1);
  });
});
