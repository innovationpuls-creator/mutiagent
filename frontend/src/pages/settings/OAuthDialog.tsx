import { useCallback, useEffect, useRef, useState } from "react";
import { aiModelsApi, type OAuthStart } from "../../api/modelConfig";
import { useDialogAccessibility } from "../../components/ui/useDialogAccessibility";
import { useAuth } from "../../contexts/AuthContext";

/** Accepts a bare code or a pasted callback URL and returns the code. */
export function extractAuthCode(input: string): string {
	const text = input.trim();
	try {
		const url = new URL(text);
		return url.searchParams.get("code") ?? text;
	} catch {
		return text;
	}
}

export function OAuthDialog({
	providerId,
	providerName,
	onClose,
	onAuthorized,
}: {
	providerId: string;
	providerName: string;
	onClose: () => void;
	onAuthorized: () => void;
}) {
	const { token } = useAuth();
	const [session, setSession] = useState<OAuthStart | null>(null);
	const [error, setError] = useState<string | null>(null);
	const [code, setCode] = useState("");
	const [busy, setBusy] = useState(false);
	const [copied, setCopied] = useState(false);
	const closeRef = useRef<HTMLButtonElement>(null);
	const startedRef = useRef(false);
	useDialogAccessibility({ isOpen: true, onClose, initialFocusRef: closeRef });

	const authorized = useCallback(() => {
		onAuthorized();
		onClose();
	}, [onAuthorized, onClose]);

	useEffect(() => {
		if (!token || startedRef.current) return;
		startedRef.current = true;
		aiModelsApi
			.oauthStart(token, providerId)
			.then((result) => setSession(result))
			.catch((err) =>
				setError(
					err instanceof Error ? err.message : "无法发起授权，请稍后重试",
				),
			);
	}, [token, providerId]);

	// Automatic-callback vendors finish on their own: poll the gateway.
	useEffect(() => {
		if (!token || !session) return undefined;
		const timer = window.setInterval(() => {
			aiModelsApi
				.oauthStatus(token, providerId, session.state)
				.then((status) => {
					if (status.status === "authorized") authorized();
					else if (status.status === "failed")
						setError(status.error ?? "授权失败，请重试");
					else if (status.status === "expired")
						setError("授权会话已过期，请关闭后重新发起");
				})
				.catch(() => {});
		}, 2000);
		return () => window.clearInterval(timer);
	}, [token, session, providerId, authorized]);

	const submit = async () => {
		if (!token || !session || !code.trim()) return;
		setBusy(true);
		setError(null);
		try {
			await aiModelsApi.oauthComplete(
				token,
				providerId,
				session.state,
				extractAuthCode(code),
			);
			authorized();
		} catch (err) {
			setError(
				err instanceof Error ? err.message : "授权失败，请检查授权码后重试",
			);
		} finally {
			setBusy(false);
		}
	};

	const copy = async (text: string) => {
		try {
			await navigator.clipboard.writeText(text);
			setCopied(true);
			window.setTimeout(() => setCopied(false), 1500);
		} catch {
			setCopied(false);
		}
	};

	return (
		<div className="mc-backdrop">
			<div
				className="mc-dialog"
				role="dialog"
				aria-modal="true"
				aria-labelledby="mc-oauth-title"
			>
				<header className="mc-dialog-head">
					<h2 id="mc-oauth-title">OAuth 登录 · {providerName}</h2>
					<button
						ref={closeRef}
						type="button"
						className="mc-btn mc-btn-ghost"
						onClick={onClose}
					>
						关闭
					</button>
				</header>
				{!session && !error && (
					<p role="status">正在向 {providerName} 申请授权…</p>
				)}
				{session?.mode === "redirect" && session.auth_url && (
					<div className="mc-stack">
						<p>
							1.
							在新窗口打开授权页并登录；若厂商会自动回调，完成后这里会自动刷新。
						</p>
						<div className="mc-row">
							<a
								className="mc-btn mc-btn-primary"
								href={session.auth_url}
								target="_blank"
								rel="noopener noreferrer"
							>
								打开授权页
							</a>
							<button
								type="button"
								className="mc-btn"
								onClick={() => void copy(session.auth_url ?? "")}
							>
								{copied ? "已复制" : "复制授权链接"}
							</button>
						</div>
						{session.instructions && (
							<p className="mc-hint">{session.instructions}</p>
						)}
						<p>
							2. 如果厂商显示授权码或跳转到 localhost，请把授权码或完整回调 URL
							粘贴到下面：
						</p>
						<label className="mc-field">
							<span>授权码 / 回调 URL</span>
							<input
								value={code}
								onChange={(event) => setCode(event.target.value)}
								autoComplete="off"
								spellCheck={false}
							/>
						</label>
						<button
							type="button"
							className="mc-btn mc-btn-primary"
							disabled={busy || !code.trim()}
							onClick={() => void submit()}
						>
							{busy ? "验证中…" : "完成授权"}
						</button>
					</div>
				)}
				{session?.mode === "device_code" && (
					<div className="mc-stack">
						<p>在下面的页面输入验证码完成授权，完成后本窗口会自动刷新。</p>
						<p className="mc-device-code">
							<span className="mc-sr">验证码：</span>
							{session.user_code}
						</p>
						{session.verification_uri && (
							<a
								className="mc-btn mc-btn-primary"
								href={session.verification_uri}
								target="_blank"
								rel="noopener noreferrer"
							>
								打开验证页面
							</a>
						)}
					</div>
				)}
				{error && (
					<p className="mc-error" role="alert">
						{error}
					</p>
				)}
			</div>
		</div>
	);
}
