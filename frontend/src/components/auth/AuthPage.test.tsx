import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { AuthProvider } from '../../contexts/AuthContext';
import { AuthPage } from './AuthPage';
import type { AuthResponse } from '../../types/auth';

const mockUser = {
  uid: '00000000-0000-0000-0000-000000000001',
  username: '林小鹿',
  identifier: 'lin@example.com',
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
  });

  it('shows login, register, QQ, and xuexitong access in one auth surface', () => {
    render(
      <MemoryRouter>
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
    expect(screen.getByRole('button', { name: /QQ 登录/ })).toBeTruthy();
    expect(screen.getByRole('button', { name: /学习通登录/ })).toBeTruthy();
    expect(screen.getByText('Planner Agent 倾听你的原始需求')).toBeTruthy();
    expect(screen.getByText('动态更新的多Agent协同学习系统')).toBeTruthy();
  });

  it('submits login and shows in-page success state', async () => {
    const login = vi.fn().mockResolvedValue(makeAuthResponse('password'));

    render(
      <MemoryRouter>
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

  it('shows mock authorization status before OAuth success', async () => {
    const oauth = vi.fn().mockResolvedValue(makeAuthResponse('oauth'));

    render(
      <MemoryRouter>
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

    expect(screen.getByRole('dialog', { name: '模拟授权' })).toBeTruthy();
    expect(screen.getByText('正在打开学习通授权状态面板')).toBeTruthy();
    expect(await screen.findByText('思绪已对齐')).toBeTruthy();
  });
});
