export type AuthMode = 'login' | 'register';
export type AuthEntry = 'student' | 'teacher';
export type AuthRole = 'student' | 'teacher' | 'admin';
export type OAuthProvider = 'qq' | 'xuexitong';
export type AuthType = 'password' | 'oauth';

export interface AuthUser {
  uid: string;
  username: string;
  identifier: string;
  role: AuthRole;
  provider: string;
  is_active: boolean;
  created_at: string;
  last_login_at: string | null;
}

export interface AuthResponse {
  access_token: string;
  token_type: string;
  authType: AuthType;
  user: AuthUser;
}

export interface LoginPayload {
  account: string;
  password: string;
}

export interface RegisterPayload {
  username: string;
  identifier: string;
  password: string;
  confirmPassword: string;
  role: AuthRole;
}

export interface OAuthPayload {
  provider: OAuthProvider;
  authorizationCode: string;
}

export interface AuthApi {
  login(payload: LoginPayload): Promise<AuthResponse>;
  register(payload: RegisterPayload): Promise<AuthResponse>;
  oauth(payload: OAuthPayload): Promise<AuthResponse>;
}
