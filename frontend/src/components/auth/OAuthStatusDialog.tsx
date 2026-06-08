import { useEffect, useState } from 'react';
import QRCode from 'qrcode';
import type { OAuthProvider } from '../../types/auth';
import { providerLabels } from '../../constants/auth';

interface OAuthStatusDialogProps {
  onClose(): void;
  provider: OAuthProvider | null;
  open: boolean;
}

export function OAuthStatusDialog({ onClose, provider, open }: OAuthStatusDialogProps) {
  const [qrCodeUrl, setQrCodeUrl] = useState<string | null>(null);

  useEffect(() => {
    if (!open || !provider) {
      setQrCodeUrl(null);
      return;
    }

    const payloadUrl = new URL('/auth/qr', window.location.origin);
    payloadUrl.searchParams.set('provider', provider);
    payloadUrl.searchParams.set('authorization_code', `qr-${provider}-${Date.now()}`);

    void QRCode.toString(payloadUrl.toString(), {
      type: 'svg',
      errorCorrectionLevel: 'M',
      margin: 2,
      scale: 8,
    }).then((svg) => {
      setQrCodeUrl(`data:image/svg+xml;utf8,${encodeURIComponent(svg)}`);
    });
  }, [open, provider]);

  if (!open || !provider) {
    return null;
  }

  const label = providerLabels[provider];

  return (
    <div className="oauth-dialog-backdrop" role="presentation">
      <div className="oauth-dialog" role="dialog" aria-label="扫码登录" aria-modal="true">
        <span className="section-kicker">扫码登录</span>
        <h2>使用{label}扫码登录</h2>
        <div className="oauth-qr-shell" aria-label={`${label} 登录二维码`}>
          {qrCodeUrl ? (
            <img className="oauth-qr-image" src={qrCodeUrl} alt={`${label} 登录二维码`} />
          ) : (
            <div className="oauth-qr-loading" aria-hidden="true" />
          )}
        </div>
        <p>请使用{label} App 扫描二维码，在手机上确认后继续。</p>
        <button className="oauth-dialog-close" type="button" onClick={onClose}>
          返回登录
        </button>
      </div>
    </div>
  );
}
