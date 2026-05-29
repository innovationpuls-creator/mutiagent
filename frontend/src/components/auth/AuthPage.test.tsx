import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { AuthPage } from './AuthPage';
import type { AuthResponse } from '../../types/auth';

const mockUser = {
  id: 1,
  username: '林小鹿',
  identifier: 'lin@example.com',
  provider: 'password',
};

function makeAuthResponse(authType: AuthResponse['authType']): AuthResponse {
  return {
    token: `mock-token-${authType}`,
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
      <AuthPage
        authApi={{
          login: vi.fn(),
          register: vi.fn(),
          oauth: vi.fn(),
        }}
      />,
    );

    expect(screen.getByRole('tab', { name: '登录' })).toBeTruthy();
    expect(screen.getByRole('tab', { name: '注册' })).toBeTruthy();
    expect(screen.getByRole('button', { name: /QQ 登录/ })).toBeTruthy();
    expect(screen.getByRole('button', { name: /学习通登录/ })).toBeTruthy();
    expect(screen.getByLabelText('多智能体处理动画')).toBeTruthy();
    expect(screen.getByText('把混乱目标安静整理成学习地图。')).toBeTruthy();
  });

  it('submits login and shows in-page success state', async () => {
    const login = vi.fn().mockResolvedValue(makeAuthResponse('password'));

    render(
      <AuthPage
        authApi={{
          login,
          register: vi.fn(),
          oauth: vi.fn(),
        }}
      />,
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
    expect(await screen.findByText('已进入系统')).toBeTruthy();
  });

  it('shows mock authorization status before OAuth success', async () => {
    const oauth = vi.fn().mockResolvedValue(makeAuthResponse('oauth'));

    render(
      <AuthPage
        authApi={{
          login: vi.fn(),
          register: vi.fn(),
          oauth,
        }}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: /学习通登录/ }));

    expect(screen.getByRole('dialog', { name: '模拟授权' })).toBeTruthy();
    expect(screen.getByText('正在打开学习通授权状态面板')).toBeTruthy();
    expect(await screen.findByText('已进入系统')).toBeTruthy();
  });
});
