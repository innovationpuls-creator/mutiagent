export type AuthMode = 'login' | 'register';
export type OAuthProvider = 'qq' | 'xuexitong';
export type AuthType = 'password' | 'oauth';

export interface AuthUser {
  id: number;
  username: string;
  identifier: string;
  provider: string;
}

export interface AuthResponse {
  token: string;
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
