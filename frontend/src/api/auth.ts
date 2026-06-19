import type {
  AuthApi,
  AuthResponse,
  AuthUser,
  LoginPayload,
  OAuthPayload,
  RegisterPayload,
} from '../types/auth';
import { API_BASE_URL } from './http';

interface ApiAuthResponse {
  access_token: string;
  token_type: string;
  auth_type: AuthResponse['authType'];
  user: {
    uid: string;
    username: string;
    identifier: string;
    role: AuthUser['role'];
    school: string;
    major: string;
    class_name: string;
    provider: string;
    is_active: boolean;
    created_at: string;
    last_login_at: string | null;
  };
}

interface ApiErrorResponse {
  detail?: string | { msg?: string }[];
}

function toAuthUser(raw: ApiAuthResponse['user']): AuthUser {
  return {
    uid: raw.uid,
    username: raw.username,
    identifier: raw.identifier,
    role: raw.role,
    school: raw.school,
    major: raw.major,
    class_name: raw.class_name,
    provider: raw.provider,
    is_active: raw.is_active,
    created_at: raw.created_at,
    last_login_at: raw.last_login_at,
  };
}

function toAuthResponse(payload: ApiAuthResponse): AuthResponse {
  return {
    access_token: payload.access_token,
    token_type: payload.token_type,
    authType: payload.auth_type,
    user: toAuthUser(payload.user),
  };
}

async function requestAuth<TBody>(path: string, body: TBody): Promise<AuthResponse> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
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
      role: payload.role,
      school: payload.school,
      major: payload.major,
      class_name: payload.className,
    });
  },
  oauth(payload: OAuthPayload) {
    return requestAuth('/api/auth/oauth/mock', {
      provider: payload.provider,
      authorization_code: payload.authorizationCode,
    });
  },
};
