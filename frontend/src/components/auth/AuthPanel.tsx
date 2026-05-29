import { ArrowRight, CheckCircle2 } from 'lucide-react';
import { useState } from 'react';
import type { FormEvent } from 'react';
import type { AuthMode, AuthResponse, RegisterPayload } from '../../types/auth';
import { Button } from '../ui/Button';
import { TextField } from '../ui/TextField';

interface AuthPanelProps {
  busy: boolean;
  mode: AuthMode;
  result: AuthResponse | null;
  error: string | null;
  onModeChange(mode: AuthMode): void;
  onLogin(account: string, password: string): Promise<void>;
  onRegister(payload: RegisterPayload): Promise<void>;
}

const initialFields = {
  account: '',
  password: '',
  username: '',
  identifier: '',
  confirmPassword: '',
};

export function AuthPanel(props: AuthPanelProps) {
  if (props.result) {
    return <SuccessPanel result={props.result} />;
  }

  return (
    <div className="auth-panel-dark" aria-label="登录注册">
      <h2>
        {props.mode === 'login' ? 'Welcome back to your space.' : 'A blank canvas for your mind.'}
      </h2>
      <div className="auth-copy-stack">
        <p>
          {props.mode === 'login' ? '外界再喧嚣，这里的思绪依然澄澈。请重新连接。' : '给自己留出一段专注的时间，创建全新的栖息地。'}
        </p>
      </div>
      
      <div className="auth-tabs-dark" role="tablist" aria-label="账号入口">
        <button
          className="auth-tab-dark"
          type="button"
          role="tab"
          aria-selected={props.mode === 'login'}
          onClick={() => props.onModeChange('login')}
        >
          登录
        </button>
        <button
          className="auth-tab-dark"
          type="button"
          role="tab"
          aria-selected={props.mode === 'register'}
          onClick={() => props.onModeChange('register')}
        >
          注册
        </button>
      </div>

      <AuthForm {...props} />
    </div>
  );
}

function AuthForm({ busy, error, mode, onLogin, onRegister }: Omit<AuthPanelProps, 'result' | 'onModeChange'>) {
  const [fields, setFields] = useState(initialFields);
  const setField = (key: keyof typeof initialFields, value: string) => {
    setFields((current) => ({ ...current, [key]: value }));
  };
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (mode === 'login') {
      void onLogin(fields.account, fields.password);
      return;
    }
    void onRegister({
      username: fields.username,
      identifier: fields.identifier,
      password: fields.password,
      confirmPassword: fields.confirmPassword,
    });
  };

  return (
    <form className="auth-form-dark" onSubmit={submit}>
      {mode === 'register' ? (
        <TextField
          label="用户名"
          name="username"
          autoComplete="name"
          value={fields.username}
          onChange={(event) => setField('username', event.target.value)}
          minLength={1}
          required
        />
      ) : null}
      
      <TextField
        label={mode === 'login' ? '账号' : '邮箱或手机号'}
        name={mode === 'login' ? 'account' : 'identifier'}
        autoComplete={mode === 'login' ? 'username' : 'email'}
        value={mode === 'login' ? fields.account : fields.identifier}
        onChange={(event) => setField(mode === 'login' ? 'account' : 'identifier', event.target.value)}
        helperText={mode === 'login' ? '可使用 demo@mutiagent.local' : undefined}
        minLength={3}
        required
      />
      
      <TextField
        label={mode === 'login' ? '密码' : '设置密码'}
        name="password"
        type="password"
        autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
        value={fields.password}
        onChange={(event) => setField('password', event.target.value)}
        minLength={6}
        required
      />
      
      {mode === 'register' ? (
        <TextField
          label="确认密码"
          name="confirmPassword"
          type="password"
          autoComplete="new-password"
          value={fields.confirmPassword}
          onChange={(event) => setField('confirmPassword', event.target.value)}
          minLength={6}
          required
        />
      ) : null}
      
      {error ? <p className="auth-error">{error}</p> : null}
      
      <Button type="submit" loading={busy} icon={<ArrowRight aria-hidden="true" />}>
        {mode === 'login' ? '进入系统' : '完成注册'}
      </Button>
    </form>
  );
}

function SuccessPanel({ result }: { result: AuthResponse }) {
  return (
    <div className="auth-panel-dark auth-success" aria-label="登录成功">
      <CheckCircle2 aria-hidden="true" className="success-icon" />
      <h2>思绪已对齐</h2>
      <p>{result.user.username}，你专属的无边界学习空间已准备就绪。</p>
    </div>
  );
}
