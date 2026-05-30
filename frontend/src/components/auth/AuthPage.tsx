import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion, useReducedMotion } from 'framer-motion';
import { authApi as defaultAuthApi } from '../../api/auth';
import type { AuthApi, AuthMode, AuthResponse, OAuthProvider, RegisterPayload } from '../../types/auth';
import { AuthPanel } from './AuthPanel';
import { MultiAgentHero } from './MultiAgentHero';
import { OAuthStatusDialog } from './OAuthStatusDialog';
import { QQIcon, XuexitongIcon } from './ProviderIcons';

export interface AuthPageProps {
  authApi?: AuthApi;
}

const oauthDelayMs = 620;

export function AuthPage({ authApi = defaultAuthApi }: AuthPageProps) {
  const navigate = useNavigate();
  const reduceMotion = useReducedMotion();
  const [mode, setMode] = useState<AuthMode>('login');
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<AuthResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [oauthProvider, setOAuthProvider] = useState<OAuthProvider | null>(null);

  const runAuth = async (action: () => Promise<AuthResponse>) => {
    setBusy(true);
    setError(null);
    try {
      const authResult = await action();
      setResult(authResult);
      // Wait to show the success message, then transition with exit animation
      setTimeout(() => {
        navigate('/onboarding');
      }, 1500);
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
    <motion.main
      className="auth-page"
      exit={reduceMotion ? { opacity: 0 } : { opacity: 0, filter: 'blur(10px)', transition: { duration: 0.4 } }}
    >
      <MultiAgentHero />

      <section className="auth-right-surface">
        <motion.div
          className="auth-panel-wrapper"
          initial={reduceMotion ? false : { opacity: 0, y: 20 }}
          animate={reduceMotion ? undefined : { opacity: 1, y: 0 }}
          transition={reduceMotion ? undefined : { duration: 0.8, ease: [0.16, 1, 0.3, 1] }}
        >
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
              <button
                className="provider-pill qq"
                aria-label="QQ 登录"
                onClick={() => void handleOAuth('qq')}
              >
                <span className="pill-icon" aria-hidden="true">
                  <QQIcon className="pill-icon-svg" />
                </span>
                <div className="pill-text">
                  <strong>QQ 登录</strong>
                  <span>A familiar start</span>
                </div>
              </button>
              <button
                className="provider-pill xuexitong"
                aria-label="学习通登录"
                onClick={() => void handleOAuth('xuexitong')}
              >
                <span className="pill-icon" aria-hidden="true">
                  <XuexitongIcon className="pill-icon-svg" />
                </span>
                <div className="pill-text">
                  <strong>学习通登录</strong>
                  <span>Your academic space</span>
                </div>
              </button>
            </div>
          )}
        </motion.div>
      </section>

      <OAuthStatusDialog open={Boolean(oauthProvider)} provider={oauthProvider} />
    </motion.main>
  );
}
