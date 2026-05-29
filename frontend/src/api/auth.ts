import type {
  AuthApi,
  AuthResponse,
  LoginPayload,
  OAuthPayload,
  RegisterPayload,
} from '../types/auth';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000';

interface ApiAuthResponse {
  token: string;
  auth_type: AuthResponse['authType'];
  user: AuthResponse['user'];
}

interface ApiValidationDetail {
  msg?: string;
}

interface ApiErrorResponse {
  detail?: string | ApiValidationDetail[];
}

function toAuthResponse(payload: ApiAuthResponse): AuthResponse {
  return {
    token: payload.token,
    authType: payload.auth_type,
    user: payload.user,
  };
}

async function requestAuth<TBody>(path: string, body: TBody): Promise<AuthResponse> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(body),
  });

  if (!response.ok) {
    const error = (await response.json().catch(() => null)) as ApiErrorResponse | null;
    throw new Error(extractErrorMessage(error));
  }

  return toAuthResponse((await response.json()) as ApiAuthResponse);
}

export function extractErrorMessage(error: ApiErrorResponse | null): string {
  if (!error?.detail) {
    return '请求失败，请稍后重试';
  }

  if (typeof error.detail === 'string') {
    return error.detail;
  }

  return '表单信息不完整，请检查长度和必填项后重试';
}

export const authApi: AuthApi = {
  login(payload: LoginPayload) {
    return requestAuth('/api/auth/login', payload);
  },
  register(payload: RegisterPayload) {
    return requestAuth('/api/auth/register', {
      username: payload.username,
      identifier: payload.identifier,
      password: payload.password,
      confirm_password: payload.confirmPassword,
    });
  },
  oauth(payload: OAuthPayload) {
    return requestAuth('/api/auth/oauth/mock', {
      provider: payload.provider,
      authorization_code: payload.authorizationCode,
    });
  },
};
