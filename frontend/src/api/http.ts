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

function getBrowserApiBaseUrl(): string {
  if (typeof process !== 'undefined' && process.env.NODE_ENV === 'test') {
    return 'http://127.0.0.1:8000';
  }

  if (typeof window === 'undefined' || !window.location.hostname) {
    return 'http://127.0.0.1:8000';
  }

  if (window.location.hostname === '127.0.0.1' || window.location.hostname === 'localhost') {
    return `${window.location.protocol}//${window.location.hostname}:8000`;
  }

  return window.location.origin;
}

export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? (
  getBrowserApiBaseUrl()
);
