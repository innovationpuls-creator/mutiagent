import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { TeacherPage } from './TeacherPage';

vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => ({
    token: 'test-token',
    isAuthReady: true,
    user: {
      uid: 'teacher-1',
      username: '测试教师',
      identifier: 'teacher@example.com',
      role: 'teacher',
      provider: 'password',
      is_active: true,
      created_at: '2026-06-02T00:00:00Z',
      last_login_at: null,
    },
    login: vi.fn(),
    logout: vi.fn(),
  }),
}));

vi.mock('framer-motion', async () => {
  const actual = await vi.importActual<typeof import('framer-motion')>('framer-motion');

  const createMockComponent = (tag: string) => {
    const Component = React.forwardRef<
      any,
      React.HTMLAttributes<any> & {
        initial?: unknown;
        animate?: unknown;
        exit?: unknown;
        transition?: unknown;
        layout?: unknown;
        layoutId?: unknown;
        variants?: unknown;
      }
    >(({ children, initial, animate, exit, transition, layout, layoutId, variants, ...props }, ref) => {
      return React.createElement(tag, { ...props, ref }, children);
    });
    Component.displayName = `Motion${tag}`;
    return Component;
  };

  return {
    ...actual,
    AnimatePresence: ({ children }: { children: React.ReactNode }) => <>{children}</>,
    motion: {
      div: createMockComponent('div'),
      main: createMockComponent('main'),
    },
    useReducedMotion: () => true,
  };
});

describe('TeacherPage State Machine & localStorage Saves', () => {
  let store: Record<string, string> = {};

  beforeEach(() => {
    store = {};
    vi.stubGlobal('localStorage', {
      getItem: vi.fn((key: string) => store[key] ?? null),
      setItem: vi.fn((key: string, value: string) => {
        store[key] = value;
      }),
      removeItem: vi.fn((key: string) => {
        delete store[key];
      }),
      clear: vi.fn(() => {
        store = {};
      }),
    });
    vi.useFakeTimers();
  });

  afterEach(() => {
    cleanup();
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it('renders empty state initially, showing dropzone instructions', () => {
    render(<TeacherPage />);
    expect(screen.getByText('拖拽或点击上传培养方案文档')).toBeTruthy();
    expect(
      screen.getByText('支持 PDF, DOCX, DOC, TXT, PNG, JPG, JPEG 格式，文件大小不超过 20MB')
    ).toBeTruthy();
  });

  it('displays error state when uploading an invalid file extension', async () => {
    render(<TeacherPage />);
    const dropzone = screen.getByTestId('dropzone');

    const invalidFile = new File(['dummy content'], 'invalid.exe', {
      type: 'application/octet-stream',
    });

    await act(async () => {
      fireEvent.drop(dropzone, {
        dataTransfer: {
          files: [invalidFile],
        },
      });
    });

    expect(screen.getByText('文件解析失败')).toBeTruthy();
    expect(
      screen.getByText('不支持的文件类型。仅支持 PDF, DOCX, DOC, TXT, PNG, JPG, JPEG 格式')
    ).toBeTruthy();

    // Click "重新上传" to go back to empty
    const retryBtn = screen.getByRole('button', { name: '重新上传' });
    await act(async () => {
      fireEvent.click(retryBtn);
    });

    expect(screen.getByText('拖拽或点击上传培养方案文档')).toBeTruthy();
  });

  it('displays error state when uploading a file larger than 20MB', async () => {
    render(<TeacherPage />);
    const dropzone = screen.getByTestId('dropzone');

    // Create a 21MB file
    const largeFile = new File(['a'.repeat(21 * 1024 * 1024)], 'large.pdf', {
      type: 'application/pdf',
    });

    await act(async () => {
      fireEvent.drop(dropzone, {
        dataTransfer: {
          files: [largeFile],
        },
      });
    });

    expect(screen.getByText('文件解析失败')).toBeTruthy();
    expect(screen.getByText('文件大小超出20MB上限')).toBeTruthy();
  });

  it('advances empty -> loading -> editor on valid file drop', async () => {
    render(<TeacherPage />);
    const dropzone = screen.getByTestId('dropzone');

    const validFile = new File(['dummy content'], 'syllabus.pdf', {
      type: 'application/pdf',
    });

    await act(async () => {
      fireEvent.drop(dropzone, {
        dataTransfer: {
          files: [validFile],
        },
      });
    });

    // Check loading state
    expect(screen.getByText('正在读取培养方案并由AI对齐大纲...')).toBeTruthy();

    // Advance 3 seconds for loader to finish
    await act(async () => {
      vi.advanceTimersByTime(3000);
    });

    // Check editor state
    expect(screen.getByText('培养方案大纲对齐')).toBeTruthy();
    expect(screen.getByText('教师：测试教师 | 正在编辑已对齐的人培课程方案')).toBeTruthy();
    expect(screen.getByText('高等数学 I')).toBeTruthy();
  });

  it('loads existing courses from localStorage on mount and starts in editor state', () => {
    const mockSavedCourses = [
      {
        course_node_id: 'math_1',
        course_or_chapter_theme: '高等数学 I (已保存)',
        course_goal: '微积分',
        status: 'locked',
        has_outline: false,
        is_custom: false,
        time_arrangement: { semester_scope: '1', duration: '64学时/4学分' },
        key_points: ['极限'],
        difficult_points: ['中值定理'],
        acceptance_criteria: ['期末考试'],
      },
    ];
    store['teacher_cultivation_program'] = JSON.stringify(mockSavedCourses);

    render(<TeacherPage />);

    expect(screen.getByText('培养方案大纲对齐')).toBeTruthy();
    expect(screen.getByText('高等数学 I (已保存)')).toBeTruthy();
  });

  it('opens DetailDrawer, edits values, and saves updates to localStorage with key "teacher_cultivation_program"', async () => {
    // Start by uploading file and going to editor
    render(<TeacherPage />);
    const dropzone = screen.getByTestId('dropzone');
    const validFile = new File(['dummy content'], 'syllabus.pdf', {
      type: 'application/pdf',
    });

    await act(async () => {
      fireEvent.drop(dropzone, {
        dataTransfer: {
          files: [validFile],
        },
      });
    });

    await act(async () => {
      vi.advanceTimersByTime(3000);
    });

    // Click on "高等数学 I" course row
    const courseRow = screen.getByText('高等数学 I');
    await act(async () => {
      fireEvent.click(courseRow);
    });

    // Verify DetailDrawer is open
    expect(screen.getByText('编辑课程大纲')).toBeTruthy();

    // Modify Course Theme
    const nameInput = screen.getByLabelText('课程名称') as HTMLInputElement;
    await act(async () => {
      fireEvent.change(nameInput, { target: { value: '高等数学 I (修改版)' } });
    });

    // Modify Course Goal
    const goalInput = screen.getByLabelText('课程目标') as HTMLTextAreaElement;
    await act(async () => {
      fireEvent.change(goalInput, { target: { value: '新的课程目标内容' } });
    });

    // Close DetailDrawer
    const closeBtn = screen.getByText('✕');
    await act(async () => {
      fireEvent.click(closeBtn);
    });

    // Advance timers to allow the exit transition to finish
    await act(async () => {
      vi.advanceTimersByTime(200);
    });

    // Verify DetailDrawer is closed
    expect(screen.queryByText('编辑课程大纲')).toBeNull();

    // Verify editor shows the updated title in the list
    expect(screen.getByText('高等数学 I (修改版)')).toBeTruthy();

    // Click Save & Publish button
    const saveBtn = screen.getByRole('button', { name: '保存并发布' });
    await act(async () => {
      fireEvent.click(saveBtn);
    });

    // Verify Toast Message
    expect(screen.getByText('人培方案已成功发布并对齐！')).toBeTruthy();

    // Fast-forward toast timer
    await act(async () => {
      vi.advanceTimersByTime(1500);
    });
    expect(screen.queryByText('人培方案已成功发布并对齐！')).toBeNull();

    // Verify localStorage contains the saved course details
    const savedStr = store['teacher_cultivation_program'];
    expect(savedStr).not.toBeNull();
    const savedCourses = JSON.parse(savedStr!);
    const updatedMath = savedCourses.find((c: any) => c.course_node_id === 'math_1');
    expect(updatedMath.course_or_chapter_theme).toBe('高等数学 I (修改版)');
    expect(updatedMath.course_goal).toBe('新的课程目标内容');
  });

  it('allows reimporting to clear courses and return to empty state', async () => {
    // start with loaded courses
    const mockSavedCourses = [
      {
        course_node_id: 'math_1',
        course_or_chapter_theme: '高等数学 I',
        status: 'locked',
        has_outline: false,
        is_custom: false,
      },
    ];
    store['teacher_cultivation_program'] = JSON.stringify(mockSavedCourses);

    const confirmSpy = vi.fn(() => true);
    vi.stubGlobal('confirm', confirmSpy);
    if (typeof window !== 'undefined') {
      window.confirm = confirmSpy;
    }

    render(<TeacherPage />);

    // Click reimport button
    const reimportBtn = screen.getByRole('button', { name: '重新导入' });
    await act(async () => {
      fireEvent.click(reimportBtn);
    });

    expect(confirmSpy).toHaveBeenCalled();
    expect(screen.getByText('拖拽或点击上传培养方案文档')).toBeTruthy();
    expect(localStorage.getItem('teacher_cultivation_program')).toBeNull();
  });
});
