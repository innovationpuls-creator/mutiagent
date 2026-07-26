import QRCode from "qrcode";
import { useEffect, useRef, useState } from "react";
import { providerLabels } from "../../constants/auth";
import type { OAuthProvider } from "../../types/auth";
import { useDialogAccessibility } from "../ui/useDialogAccessibility";

interface OAuthStatusDialogProps {
	onClose(): void;
	provider: OAuthProvider | null;
	open: boolean;
}

export function OAuthStatusDialog({
	onClose,
	provider,
	open,
}: OAuthStatusDialogProps) {
	const [qrCodeUrl, setQrCodeUrl] = useState<string | null>(null);
	const closeButtonRef = useRef<HTMLButtonElement>(null);
	useDialogAccessibility({
		isOpen: open && Boolean(provider),
		onClose,
		initialFocusRef: closeButtonRef,
	});

	useEffect(() => {
		if (!open || !provider) {
			setQrCodeUrl(null);
			return;
		}

		const payloadUrl = new URL("/auth/qr", window.location.origin);
		payloadUrl.searchParams.set("provider", provider);
		payloadUrl.searchParams.set(
			"authorization_code",
			`qr-${provider}-${Date.now()}`,
		);

		void QRCode.toString(payloadUrl.toString(), {
			type: "svg",
			errorCorrectionLevel: "M",
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
		<div className="oauth-dialog-backdrop">
			<div
				aria-labelledby="oauth-status-title"
				className="oauth-dialog"
				role="dialog"
				aria-label="扫码登录"
				aria-modal="true"
			>
				<span className="section-kicker">扫码登录</span>
				<h2 id="oauth-status-title">使用{label}扫码登录</h2>
				<figure className="oauth-qr-shell" aria-label={`${label} 登录二维码`}>
					{qrCodeUrl ? (
						<img
							className="oauth-qr-image"
							src={qrCodeUrl}
							alt={`${label} 登录二维码`}
						/>
					) : (
						<div className="oauth-qr-loading" aria-hidden="true" />
					)}
				</figure>
				<p>请使用{label} App 扫描二维码，在手机上确认后继续。</p>
				<button
					className="oauth-dialog-close"
					type="button"
					onClick={onClose}
					ref={closeButtonRef}
				>
					返回登录
				</button>
			</div>
		</div>
	);
}
