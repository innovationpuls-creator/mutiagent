import QRCode from "qrcode";
import { useEffect, useRef, useState } from "react";
import { providerLabels } from "../../constants/auth";
import type { OAuthProvider } from "../../types/auth";
import { Button } from "../ui/Button";
import { Dialog } from "../ui/Dialog";

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
		<Dialog
			isOpen
			onClose={onClose}
			title={`使用${label}扫码登录`}
			showCloseButton={false}
			initialFocusRef={closeButtonRef}
			className="oauth-dialog"
			footer={
				<Button ref={closeButtonRef} onClick={onClose}>
					返回登录
				</Button>
			}
		>
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
		</Dialog>
	);
}
