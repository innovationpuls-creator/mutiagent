import type { OAuthProvider } from '../../types/auth';
import { providerLabels } from '../../constants/auth';

interface OAuthStatusDialogProps {
  provider: OAuthProvider | null;
  open: boolean;
}

export function OAuthStatusDialog({ provider, open }: OAuthStatusDialogProps) {
  if (!open || !provider) {
    return null;
  }

  const label = providerLabels[provider];

  return (
    <div className="oauth-dialog-backdrop" role="presentation">
      <div className="oauth-dialog" role="dialog" aria-label="模拟授权">
        <span className="section-kicker">模拟授权</span>
        <h2>正在打开{label}授权状态面板</h2>
        <div className="oauth-progress" aria-hidden="true">
          <span />
        </div>
        <p>校验身份来源、同步基础学习画像，然后返回登录页内的成功状态。</p>
      </div>
    </div>
  );
}
