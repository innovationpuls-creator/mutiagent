export interface ApiErrorResponse {
  detail?: string | { msg?: string }[];
}

export const AUTH_INVALID_EVENT = 'mutiagent-auth-invalid';
export const INVALID_AUTH_DETAIL = '无效的认证凭证';

export async function readApiError(response: Response): Promise<ApiErrorResponse | null> {
  return (await response.json().catch(() => null)) as ApiErrorResponse | null;
}

export function getApiErrorDetail(error: ApiErrorResponse | null): string | null {
  return typeof error?.detail === 'string' ? error.detail : null;
}

export function notifyAuthInvalidFromError(status: number, error: ApiErrorResponse | null): void {
  if (status !== 401 || getApiErrorDetail(error) !== INVALID_AUTH_DETAIL) {
    return;
  }

  if (typeof window === 'undefined') {
    return;
  }

  window.dispatchEvent(new Event(AUTH_INVALID_EVENT));
}
