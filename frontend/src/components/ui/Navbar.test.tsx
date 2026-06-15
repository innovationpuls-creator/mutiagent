import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import React from 'react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { AuthProvider } from '../../contexts/AuthContext';
import { Navbar } from './Navbar';

vi.mock('framer-motion', async () => {
  const actual = await vi.importActual<typeof import('framer-motion')>('framer-motion');

  const createMockComponent = (tag: string) => {
    const Component = React.forwardRef<
      HTMLElement,
      React.HTMLAttributes<HTMLElement> & {
        initial?: unknown;
        animate?: unknown;
        exit?: unknown;
        transition?: unknown;
        variants?: unknown;
        layoutId?: unknown;
      }
    >(({ children, initial, animate, exit, transition, variants, layoutId, ...props }, ref) => {
      return React.createElement(tag, { ...props, ref }, children);
    });
    Component.displayName = `Motion${tag}`;
    return Component;
  };

  return {
    ...actual,
    AnimatePresence: ({ children }: { children: React.ReactNode }) => <>{children}</>,
    motion: new Proxy(
      {
        div: createMockComponent('div'),
        nav: createMockComponent('nav'),
        span: createMockComponent('span'),
        button: createMockComponent('button'),
      },
      {
        get: (target, prop) => {
          if (prop in target) {
            return target[prop as keyof typeof target];
          }
          if (typeof prop === 'string') {
            return createMockComponent(prop);
          }
          return undefined;
        },
      },
    ),
    useReducedMotion: () => true,
  };
});

describe('Navbar teacher program import', () => {
  let store: Record<string, string>;

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it('imports a teacher program from the avatar menu and binds it to the student', async () => {
    store = {
      'mutiagent-auth': JSON.stringify({
        token: 'token-1',
        user: {
          uid: 'student-1',
          username: '测试学生',
          identifier: 'student@example.com',
          role: 'student',
          provider: 'password',
          is_active: true,
          created_at: '2026-06-02T00:00:00Z',
          last_login_at: null,
        },
      }),
      'teacher_cultivation_program_share_registry': JSON.stringify({
        'OT-TEACH': {
          inviteCode: 'OT-TEACH',
          teacherUid: 'teacher-1',
          teacherName: '测试教师',
          teacherIdentifier: 'teacher@example.com',
          courses: [
            {
              course_node_id: 'teacher_course_1',
              course_or_chapter_theme: '高等数学 I',
              course_goal: '教师发布的人培课程',
              status: 'locked',
              has_outline: false,
              is_custom: true,
              time_arrangement: { semester_scope: '1', duration: '64学时/4学分' },
            },
          ],
          publishedAt: '2026-06-15T10:00:00.000Z',
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
      clear: vi.fn(() => {
        store = {};
      }),
    });

    render(
      <AuthProvider>
        <MemoryRouter>
          <Navbar />
        </MemoryRouter>
      </AuthProvider>,
    );

    fireEvent.click(screen.getByRole('button', { name: '切换个人菜单' }));
    fireEvent.click(screen.getByRole('menuitem', { name: /导入人培方案/ }));

    expect(screen.getByRole('dialog', { name: '导入人培方案' })).toBeTruthy();

    fireEvent.change(screen.getByLabelText('教师口令'), { target: { value: 'ot-teach' } });
    fireEvent.click(screen.getByRole('button', { name: '导入方案' }));

    await waitFor(() => {
      expect(screen.getByText('已导入测试教师的人培方案。')).toBeTruthy();
    });

    const bindings = JSON.parse(store['student_teacher_program_bindings']);
    expect(bindings['student-1'].inviteCode).toBe('OT-TEACH');
    expect(bindings['student-1'].teacherUid).toBe('teacher-1');
  });
});
