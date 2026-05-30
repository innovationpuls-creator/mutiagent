import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react';
import type { AuthResponse, AuthUser } from '../types/auth';

interface AuthState {
  user: AuthUser | null;
  token: string | null;
  isAuthReady: boolean;
  login(authResponse: AuthResponse): void;
  logout(): void;
}

const AuthContext = createContext<AuthState | null>(null);

const STORAGE_KEY = 'mutiagent-auth';

function loadAuth(): { user: AuthUser; token: string } | null {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored) {
      const parsed = JSON.parse(stored) as { user: AuthUser; token: string };
      if (parsed.user?.uid && parsed.token) return parsed;
    }
  } catch {
    /* corrupted data — treat as logged out */
  }
  return null;
}

function saveAuth(user: AuthUser | null, token: string | null) {
  if (user && token) {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ user, token }));
  } else {
    localStorage.removeItem(STORAGE_KEY);
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [isAuthReady, setIsAuthReady] = useState(false);

  useEffect(() => {
    const stored = loadAuth();
    if (stored) {
      setUser(stored.user);
      setToken(stored.token);
    }
    setIsAuthReady(true);
  }, []);

  const login = useCallback((authResponse: AuthResponse) => {
    setUser(authResponse.user);
    setToken(authResponse.access_token);
    saveAuth(authResponse.user, authResponse.access_token);
  }, []);

  const logout = useCallback(() => {
    setUser(null);
    setToken(null);
    saveAuth(null, null);
  }, []);

  return (
    <AuthContext.Provider value={{ user, token, isAuthReady, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthState {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}
