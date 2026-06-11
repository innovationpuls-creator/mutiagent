import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { AdminAccountApi } from '../../api/admin';
import { AuthProvider } from '../../contexts/AuthContext';
import type { AuthUser } from '../../types/auth';
import { AdminAccountsPage } from './AdminAccountsPage';

const adminAccount: AuthUser = {
  uid: 'admin-1',
  username: 'admin',
  identifier: '13297540721',
  role: 'admin',
  provider: 'password',
  is_active: true,
  created_at: '2026-06-02T00:00:00Z',
  last_login_at: null,
};

const teacherAccount: AuthUser = {
  uid: 'teacher-1',
  username: '王教师',
  identifier: 'teacher@example.com',
  role: 'teacher',
  provider: 'password',
  is_active: true,
  created_at: '2026-06-02T00:00:00Z',
  last_login_at: null,
};

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function stubStoredAuth() {
  vi.stubGlobal('localStorage', {
    getItem: vi.fn((key: string) => {
      if (key !== 'mutiagent-auth') return null;
      return JSON.stringify({
        token: 'token-1',
        user: adminAccount,
      });
    }),
    setItem: vi.fn(),
    removeItem: vi.fn(),
  });
}

function renderAdminPage(adminApi: AdminAccountApi) {
  return render(
    <MemoryRouter initialEntries={['/admin/accounts']} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <AuthProvider>
        <AdminAccountsPage adminApi={adminApi} />
      </AuthProvider>
    </MemoryRouter>,
  );
}

describe('AdminAccountsPage', () => {
  it('renders menu and manages accounts through the admin API', async () => {
    stubStoredAuth();
    const adminApi: AdminAccountApi = {
      listAccounts: vi.fn().mockResolvedValue([adminAccount]),
      createAccount: vi.fn().mockResolvedValue(teacherAccount),
      updateAccount: vi.fn()
        .mockResolvedValueOnce({
          ...teacherAccount,
          username: '王教师二号',
          identifier: 'teacher-2@example.com',
          role: 'student',
          is_active: true,
        })
        .mockResolvedValueOnce({
          ...teacherAccount,
          username: '王教师二号',
          identifier: 'teacher-2@example.com',
          role: 'student',
          is_active: false,
        }),
      deleteAccount: vi.fn().mockResolvedValue(undefined),
      batchAccounts: vi.fn().mockResolvedValue([adminAccount]),
      importAccounts: vi.fn().mockResolvedValue({ created: 0, updated: 0, failed: 0, failures: [] }),
      exportAccounts: vi.fn().mockResolvedValue('username,identifier,password,role,is_active\n'),
    };

    renderAdminPage(adminApi);

    expect(screen.getByRole('navigation', { name: '管理员菜单' })).toBeTruthy();
    expect(screen.getByRole('link', { name: '账号管理' })).toBeTruthy();

    await waitFor(() => {
      expect(screen.getByText('admin')).toBeTruthy();
    });

    expect(adminApi.listAccounts).toHaveBeenCalledWith('token-1');

    fireEvent.click(screen.getByRole('button', { name: '新增账号' }));
    fireEvent.change(screen.getByLabelText('用户名'), {
      target: { value: '王教师' },
    });
    fireEvent.change(screen.getByLabelText('登录标识'), {
      target: { value: 'teacher@example.com' },
    });
    fireEvent.change(screen.getByLabelText('密码'), {
      target: { value: 'teacher-password-123' },
    });
    const roleSelects = screen.getAllByLabelText('角色');
    fireEvent.change(roleSelects[roleSelects.length - 1], {
      target: { value: 'teacher' },
    });
    fireEvent.click(screen.getByRole('button', { name: '创建账号' }));

    await waitFor(() => {
      expect(adminApi.createAccount).toHaveBeenCalledWith('token-1', {
        username: '王教师',
        identifier: 'teacher@example.com',
        password: 'teacher-password-123',
        role: 'teacher',
        is_active: true,
      });
      expect(screen.getByText('王教师')).toBeTruthy();
    });

    fireEvent.change(screen.getByLabelText('查询账号'), {
      target: { value: 'teacher@example.com' },
    });

    const list = screen.getByRole('region', { name: '账号列表' });
    expect(within(list).getByText('王教师')).toBeTruthy();
    expect(within(list).queryByText('admin')).toBeNull();

    fireEvent.change(screen.getByLabelText('查询账号'), {
      target: { value: '' },
    });

    fireEvent.click(screen.getByRole('button', { name: '编辑 王教师' }));
    fireEvent.change(screen.getByLabelText('用户名'), {
      target: { value: '王教师二号' },
    });
    fireEvent.change(screen.getByLabelText('登录标识'), {
      target: { value: 'teacher-2@example.com' },
    });
    const editRoleSelects = screen.getAllByLabelText('角色');
    fireEvent.change(editRoleSelects[editRoleSelects.length - 1], {
      target: { value: 'student' },
    });
    fireEvent.click(screen.getByRole('button', { name: '保存修改' }));

    await waitFor(() => {
      expect(adminApi.updateAccount).toHaveBeenCalledWith('token-1', 'teacher-1', {
        username: '王教师二号',
        identifier: 'teacher-2@example.com',
        role: 'student',
        is_active: true,
      });
      expect(screen.getByText('王教师二号')).toBeTruthy();
    });

    const enabledStatusButton = screen.getAllByRole('button', { name: '启用' }).find((button) => !button.hasAttribute('disabled'));
    expect(enabledStatusButton).toBeTruthy();
    fireEvent.click(enabledStatusButton!);

    await waitFor(() => {
      expect(adminApi.updateAccount).toHaveBeenLastCalledWith('token-1', 'teacher-1', {
        username: '王教师二号',
        identifier: 'teacher-2@example.com',
        role: 'student',
        is_active: false,
      });
    });

    fireEvent.click(screen.getByRole('button', { name: '删除 王教师二号' }));
    fireEvent.click(screen.getByRole('button', { name: '确认删除' }));

    await waitFor(() => {
      expect(adminApi.deleteAccount).toHaveBeenCalledWith('token-1', 'teacher-1');
      expect(screen.queryByText('王教师二号')).toBeNull();
    });
  });
});
