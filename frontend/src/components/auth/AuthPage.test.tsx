import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { AuthProvider } from '../../contexts/AuthContext';
import { AuthPage } from './AuthPage';
import type { AuthResponse } from '../../types/auth';

const mockUser = {
  uid: '00000000-0000-0000-0000-000000000001',
  username: '林小鹿',
  identifier: 'lin@example.com',
  role: 'student' as const,
  provider: 'password',
  is_active: true,
  created_at: '2026-01-01T00:00:00.000000',
  last_login_at: null,
};

function makeAuthResponse(authType: AuthResponse['authType']): AuthResponse {
  return {
    access_token: `mock-token-${authType}`,
    token_type: 'bearer',
    authType,
    user: mockUser,
  };
}

describe('AuthPage', () => {
  afterEach(() => {
    cleanup();
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it('shows login, register, QQ, and xuexitong access in one auth surface', () => {
    render(
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <AuthProvider>
          <AuthPage
            authApi={{
              login: vi.fn(),
              register: vi.fn(),
              oauth: vi.fn(),
            }}
          />
        </AuthProvider>
      </MemoryRouter>,
    );

    expect(screen.getByRole('tab', { name: '登录' })).toBeTruthy();
    expect(screen.getByRole('tab', { name: '注册' })).toBeTruthy();
    expect(screen.getByRole('tab', { name: '学生' })).toBeTruthy();
    expect(screen.getByRole('tab', { name: '教师' })).toBeTruthy();
    expect(screen.queryByRole('tab', { name: '管理员' })).toBeNull();
    expect(screen.getByRole('button', { name: /QQ 登录/ })).toBeTruthy();
    expect(screen.getByRole('button', { name: /学习通登录/ })).toBeTruthy();
    expect(screen.getByText('Planner Agent 倾听你的原始需求')).toBeTruthy();
    expect(screen.getByText('动态更新的多Agent协同学习系统')).toBeTruthy();
  });

  it('routes teacher login to the teacher page', async () => {
    vi.stubGlobal('localStorage', {
      getItem: vi.fn(),
      setItem: vi.fn(),
      removeItem: vi.fn(),
    });
    vi.stubGlobal('sessionStorage', {
      setItem: vi.fn(),
    });
    const login = vi.fn().mockResolvedValue({
      ...makeAuthResponse('password'),
      user: { ...mockUser, role: 'teacher' as const },
    });

    render(
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <AuthProvider>
          <Routes>
            <Route
              path="*"
              element={(
                <>
                  <AuthPage
                    authApi={{
                      login,
                      register: vi.fn(),
                      oauth: vi.fn(),
                    }}
                  />
                  <LocationText />
                </>
              )}
            />
          </Routes>
        </AuthProvider>
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByRole('tab', { name: '教师' }));
    fireEvent.change(screen.getByLabelText('账号'), {
      target: { value: 'lin@example.com' },
    });
    fireEvent.change(screen.getByLabelText('密码'), {
      target: { value: 'learn-agent-123' },
    });
    fireEvent.click(screen.getByRole('button', { name: '进入系统' }));

    expect(login).toHaveBeenCalledWith({
      account: 'lin@example.com',
      password: 'learn-agent-123',
    });

    expect(await screen.findByText('思绪已对齐')).toBeTruthy();

    await waitFor(() => {
      expect(screen.getByTestId('location-path').textContent).toBe('/teacher');
    }, { timeout: 2200 });
  });

  it('submits login and shows in-page success state', async () => {
    const login = vi.fn().mockResolvedValue(makeAuthResponse('password'));

    render(
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <AuthProvider>
          <AuthPage
            authApi={{
              login,
              register: vi.fn(),
              oauth: vi.fn(),
            }}
          />
        </AuthProvider>
      </MemoryRouter>,
    );

    fireEvent.change(screen.getByLabelText('账号'), {
      target: { value: 'lin@example.com' },
    });
    fireEvent.change(screen.getByLabelText('密码'), {
      target: { value: 'learn-agent-123' },
    });
    fireEvent.click(screen.getByRole('button', { name: '进入系统' }));

    await waitFor(() => {
      expect(login).toHaveBeenCalledWith({
        account: 'lin@example.com',
        password: 'learn-agent-123',
      });
    });
    expect(await screen.findByText('思绪已对齐')).toBeTruthy();
  });

  it('shows scan QR code without calling OAuth login', async () => {
    const oauth = vi.fn().mockResolvedValue(makeAuthResponse('oauth'));

    render(
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <AuthProvider>
          <AuthPage
            authApi={{
              login: vi.fn(),
              register: vi.fn(),
              oauth,
            }}
          />
        </AuthProvider>
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByRole('button', { name: /学习通登录/ }));

    expect(screen.getByRole('dialog', { name: '扫码登录' })).toBeTruthy();
    expect(screen.getByText('使用学习通扫码登录')).toBeTruthy();
    expect(screen.getByLabelText('学习通 登录二维码')).toBeTruthy();
    expect(await screen.findByAltText('学习通 登录二维码')).toBeTruthy();
    expect(oauth).not.toHaveBeenCalled();
    expect(screen.queryByText('思绪已对齐')).toBeNull();
  });
});

function LocationText() {
  const location = useLocation();
  return <span data-testid="location-path">{location.pathname}</span>;
}
