import { act, cleanup, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { Outlet } from 'react-router-dom';
import { App } from './App';
import { AuthProvider } from './contexts/AuthContext';
import { AUTH_INVALID_EVENT } from './api/http';

vi.mock('./components/auth/AuthPage', () => ({
  AuthPage: () => <div>Auth Page</div>,
}));

vi.mock('./pages/SproutPage', () => ({
  SproutPage: () => <div>Sprout Page</div>,
}));

vi.mock('./pages/branch/BranchPage', () => ({
  BranchPage: () => <div>Branch Page</div>,
}));

vi.mock('./pages/leaf/LeafPage', () => ({
  LeafPage: () => <div>Leaf Page</div>,
}));

vi.mock('./components/onboarding/GlobalAiWidget', () => ({
  GlobalAiWidget: () => null,
}));

vi.mock('./components/layout/MainLayout', () => ({
  MainLayout: () => (
    <div>
      <div>Main Layout</div>
      <Outlet />
    </div>
  ),
}));

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  window.history.replaceState({}, '', '/');
});

function stubStoredAuth(enabled: boolean) {
  vi.stubGlobal('localStorage', {
    getItem: vi.fn((key: string) => {
      if (!enabled || key !== 'mutiagent-auth') {
        return null;
      }
      return JSON.stringify({
        token: 'token-1',
        user: {
          uid: 'user-1',
          username: '测试用户',
          identifier: 'user@example.com',
          provider: 'password',
          is_active: true,
          created_at: '2026-06-02T00:00:00Z',
          last_login_at: null,
        },
      });
    }),
    setItem: vi.fn(),
    removeItem: vi.fn(),
  });
}

function renderApp() {
  return render(
    <AuthProvider>
      <App />
    </AuthProvider>,
  );
}

describe('App routing', () => {
  it('switches from login to sprout when the location changes', async () => {
    stubStoredAuth(true);
    window.history.replaceState({}, '', '/login');

    renderApp();

    expect(screen.getByText('Auth Page')).toBeTruthy();

    await act(async () => {
      window.history.pushState({}, '', '/sprout');
      window.dispatchEvent(new PopStateEvent('popstate'));
      await Promise.resolve();
    });

    await waitFor(() => {
      expect(screen.queryByText('Auth Page')).toBeNull();
      expect(screen.getByText('Main Layout')).toBeTruthy();
      expect(screen.getByText('Sprout Page')).toBeTruthy();
    });
  });

  it('switches between app routes after the location changes', async () => {
    stubStoredAuth(true);
    window.history.replaceState({}, '', '/sprout');

    renderApp();

    await waitFor(() => {
      expect(screen.getByText('Sprout Page')).toBeTruthy();
    });

    await act(async () => {
      window.history.pushState({}, '', '/branch');
      window.dispatchEvent(new PopStateEvent('popstate'));
      await Promise.resolve();
    });

    await waitFor(() => {
      expect(screen.queryByText('Sprout Page')).toBeNull();
      expect(screen.getByText('Branch Page')).toBeTruthy();
    });
  });

  it('renders leaf route for authenticated users', async () => {
    stubStoredAuth(true);
    window.history.replaceState({}, '', '/leaf/year_3_course_1');

    renderApp();

    await waitFor(() => {
      expect(screen.getByText('Main Layout')).toBeTruthy();
      expect(screen.getByText('Leaf Page')).toBeTruthy();
    });
  });

  it('redirects protected routes to login when no stored auth exists', async () => {
    stubStoredAuth(false);
    window.history.replaceState({}, '', '/branch');

    renderApp();

    await waitFor(() => {
      expect(screen.getByText('Auth Page')).toBeTruthy();
      expect(screen.queryByText('Branch Page')).toBeNull();
    });
  });

  it('returns to login when auth becomes invalid on a protected route', async () => {
    stubStoredAuth(true);
    window.history.replaceState({}, '', '/branch');

    renderApp();

    await waitFor(() => {
      expect(screen.getByText('Branch Page')).toBeTruthy();
    });

    await act(async () => {
      window.dispatchEvent(new Event(AUTH_INVALID_EVENT));
      await Promise.resolve();
    });

    await waitFor(() => {
      expect(screen.getByText('Auth Page')).toBeTruthy();
      expect(screen.queryByText('Branch Page')).toBeNull();
    });
  });
});
