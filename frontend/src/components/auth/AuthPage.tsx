import { useState } from 'react';
import { authApi as defaultAuthApi } from '../../api/auth';
import type { AuthApi, AuthMode, AuthResponse, OAuthProvider, RegisterPayload } from '../../types/auth';
import { AuthPanel } from './AuthPanel';
import { MultiAgentHero } from './MultiAgentHero';
import { OAuthStatusDialog } from './OAuthStatusDialog';

export interface AuthPageProps {
  authApi?: AuthApi;
}

const oauthDelayMs = 620;

export function AuthPage({ authApi = defaultAuthApi }: AuthPageProps) {
  const [mode, setMode] = useState<AuthMode>('login');
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<AuthResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [oauthProvider, setOAuthProvider] = useState<OAuthProvider | null>(null);

  const runAuth = async (action: () => Promise<AuthResponse>) => {
    setBusy(true);
    setError(null);
    try {
      setResult(await action());
    } catch (authError) {
      setError(authError instanceof Error ? authError.message : '登录失败');
    } finally {
      setBusy(false);
      setOAuthProvider(null);
    }
  };

  const handleOAuth = async (provider: OAuthProvider) => {
    setOAuthProvider(provider);
    await new Promise((resolve) => window.setTimeout(resolve, oauthDelayMs));
    await runAuth(() =>
      authApi.oauth({
        provider,
        authorizationCode: `mock-${provider}-authorization`,
      }),
    );
  };

  return (
    <main className="auth-page">
      <MultiAgentHero />

      <section className="auth-right-surface">
        <div className="auth-panel-wrapper">
          <AuthPanel
            busy={busy}
            error={error}
            mode={mode}
            result={result}
            onModeChange={setMode}
            onLogin={(account, password) => runAuth(() => authApi.login({ account, password }))}
            onRegister={(payload: RegisterPayload) => runAuth(() => authApi.register(payload))}
          />

          {!result && (
            <div className="auth-pills-row">
              <button className="provider-pill qq" onClick={() => void handleOAuth('qq')}>
                <span className="pill-icon">Q</span>
                <div className="pill-text">
                  <strong>QQ 登录</strong>
                  <span>A familiar start</span>
                </div>
              </button>
              <button className="provider-pill xuexitong" onClick={() => void handleOAuth('xuexitong')}>
                <span className="pill-icon">//</span>
                <div className="pill-text">
                  <strong>学习通登录</strong>
                  <span>Your academic space</span>
                </div>
              </button>
            </div>
          )}
        </div>
      </section>

      <OAuthStatusDialog open={Boolean(oauthProvider)} provider={oauthProvider} />
    </main>
  );
}
