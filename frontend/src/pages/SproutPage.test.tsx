import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { SproutPage } from './SproutPage';
import { AiWidgetProvider } from '../context/AiWidgetContext';
import { GlobalAiWidget } from '../components/onboarding/GlobalAiWidget';
import { AuthProvider } from '../contexts/AuthContext';

vi.mock('../components/home/SproutHero', () => ({
  SproutHero: () => {
    return (
      <div>
        <div>Sprout Hero</div>
      </div>
    );
  },
}));

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe('SproutPage', () => {
  it('shows the center input after the intro and waits for the user to expand it on first login', async () => {
    vi.stubGlobal('scrollTo', vi.fn());
    const sessionStorageGetItem = vi.fn(() => null);
    const sessionStorageRemoveItem = vi.fn();
    vi.stubGlobal('sessionStorage', {
      getItem: sessionStorageGetItem,
      removeItem: sessionStorageRemoveItem,
    });
    vi.stubGlobal('localStorage', {
      getItem: vi.fn((key: string) => {
        if (key !== 'mutiagent-auth') return null;
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

    render(
      <AuthProvider>
        <MemoryRouter
          initialEntries={[{ pathname: '/sprout', state: { isFirstLogin: true } }]}
          future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
        >
          <AiWidgetProvider>
            <Routes>
              <Route path="/sprout" element={<SproutPage />} />
            </Routes>
            <GlobalAiWidget />
          </AiWidgetProvider>
        </MemoryRouter>
      </AuthProvider>,
    );

    await waitFor(() => {
      expect(screen.getByText('在开启旅程之前，想先听听你的声音。')).toBeTruthy();
    }, { timeout: 12000 });

    let centerInputCard: Element | null = null;
    await waitFor(() => {
      centerInputCard = document.querySelector('.card.initial');
      expect(centerInputCard).toBeTruthy();
    }, { timeout: 4000 });

    expect(screen.getByText('在开启旅程之前，想先听听你的声音。')).toBeTruthy();

    fireEvent.click(centerInputCard as Element);

    await waitFor(() => {
      expect(screen.getByLabelText('AI 基础画像对话')).toBeTruthy();
    });

    expect(sessionStorageRemoveItem).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: '收起 AI 对话' }));

    await waitFor(() => {
      expect(sessionStorageRemoveItem).toHaveBeenCalledWith('mutiagent-sprout-init-overlay');
    });
  }, 22000);

});
