import { API_BASE_URL, notifyAuthInvalidFromError, readApiError } from './http';
import type { AuthRole, AuthUser } from '../types/auth';

export interface AdminAccountPayload {
  username: string;
  identifier: string;
  role: AuthRole;
  is_active: boolean;
  school: string;
  major: string;
  class_name: string;
  password?: string;
}

export type AdminBatchAction = 'activate' | 'deactivate' | 'delete' | 'set_role';

export interface AdminImportResult {
  created: number;
  updated: number;
  failed: number;
  failures: { row: number; identifier: string | null; reason: string }[];
}

export interface AdminAccountApi {
  listAccounts(token: string): Promise<AuthUser[]>;
  createAccount(token: string, payload: AdminAccountPayload & { password: string }): Promise<AuthUser>;
  updateAccount(token: string, uid: string, payload: AdminAccountPayload): Promise<AuthUser>;
  deleteAccount(token: string, uid: string): Promise<void>;
  batchAccounts(token: string, payload: { action: AdminBatchAction; uids: string[]; role?: AuthRole }): Promise<AuthUser[]>;
  importAccounts(token: string, csvText: string): Promise<AdminImportResult>;
  exportAccounts(token: string): Promise<string>;
}

async function requestAdmin<TResponse>(
  token: string,
  path: string,
  init: RequestInit = {},
): Promise<TResponse> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      ...(init.body ? { 'Content-Type': 'application/json' } : {}),
      Authorization: `Bearer ${token}`,
      ...init.headers,
    },
  });

  if (!response.ok) {
    const error = await readApiError(response);
    notifyAuthInvalidFromError(response.status, error);
    throw new Error((typeof error?.detail === 'string' ? error.detail : null) ?? '后台账号操作失败');
  }

  if (response.status === 204) {
    return undefined as TResponse;
  }

  return (await response.json()) as TResponse;
}

export const adminApi: AdminAccountApi = {
  listAccounts(token: string) {
    return requestAdmin<AuthUser[]>(token, '/api/admin/accounts');
  },
  createAccount(token: string, payload: AdminAccountPayload & { password: string }) {
    return requestAdmin<AuthUser>(token, '/api/admin/accounts', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },
  updateAccount(token: string, uid: string, payload: AdminAccountPayload) {
    return requestAdmin<AuthUser>(token, `/api/admin/accounts/${uid}`, {
      method: 'PUT',
      body: JSON.stringify(payload),
    });
  },
  deleteAccount(token: string, uid: string) {
    return requestAdmin<void>(token, `/api/admin/accounts/${uid}`, {
      method: 'DELETE',
    });
  },
  batchAccounts(token: string, payload: { action: AdminBatchAction; uids: string[]; role?: AuthRole }) {
    return requestAdmin<AuthUser[]>(token, '/api/admin/accounts/batch', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },
  importAccounts(token: string, csvText: string) {
    return requestAdmin<AdminImportResult>(token, '/api/admin/accounts/import', {
      method: 'POST',
      body: JSON.stringify({ csv_text: csvText }),
    });
  },
  async exportAccounts(token: string) {
    const response = await fetch(`${API_BASE_URL}/api/admin/accounts/export`, {
      headers: {
        Authorization: `Bearer ${token}`,
      },
    });
    if (!response.ok) {
      const error = await readApiError(response);
      notifyAuthInvalidFromError(response.status, error);
      throw new Error((typeof error?.detail === 'string' ? error.detail : null) ?? '账号导出失败');
    }
    return response.text();
  },
};
