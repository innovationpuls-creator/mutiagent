import { motion, useReducedMotion } from "framer-motion";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { authApi as defaultAuthApi } from "../../api/auth";
import { useAuth } from "../../contexts/AuthContext";
import type {
	AuthApi,
	AuthEntry,
	AuthMode,
	AuthResponse,
	OAuthProvider,
	RegisterPayload,
} from "../../types/auth";
import { AuthPanel } from "./AuthPanel";
import { MultiAgentHero } from "./MultiAgentHero";
import { OAuthStatusDialog } from "./OAuthStatusDialog";
import { QQIcon, XuexitongIcon } from "./ProviderIcons";

export interface AuthPageProps {
	authApi?: AuthApi;
}

const SPROUT_INIT_OVERLAY_KEY = "mutiagent-sprout-init-overlay";

function rememberSproutInitOverlay() {
	try {
		window.sessionStorage.setItem(SPROUT_INIT_OVERLAY_KEY, "1");
	} catch {
		/* Storage availability must not block the authenticated route transition. */
	}
}

function routeForAuthResult(authResult: AuthResponse): string {
	if (authResult.user.role === "admin") return "/admin/programs";
	return "/sprout";
}

export function AuthPage({ authApi = defaultAuthApi }: AuthPageProps) {
	const navigate = useNavigate();
	const auth = useAuth();
	const reduceMotion = useReducedMotion();
	const [mode, setMode] = useState<AuthMode>("login");
	const [entry, setEntry] = useState<AuthEntry>("student");
	const [busy, setBusy] = useState(false);
	const [result, setResult] = useState<AuthResponse | null>(null);
	const [error, setError] = useState<string | null>(null);
	const [oauthProvider, setOAuthProvider] = useState<OAuthProvider | null>(
		null,
	);

	const runAuth = async (action: () => Promise<AuthResponse>) => {
		setBusy(true);
		setError(null);
		try {
			const authResult = await action();
			setResult(authResult);
			auth.login(authResult);
			rememberSproutInitOverlay();
			setTimeout(() => {
				navigate(routeForAuthResult(authResult), {
					state: { isFirstLogin: true },
				});
			}, 1500);
		} catch (authError) {
			setError(authError instanceof Error ? authError.message : "登录失败");
		} finally {
			setBusy(false);
			setOAuthProvider(null);
		}
	};

	const handleOAuth = (provider: OAuthProvider) => {
		setOAuthProvider(provider);
	};

	return (
		<motion.main
			className="auth-page"
			exit={
				reduceMotion
					? { opacity: 0 }
					: { opacity: 0, filter: "blur(10px)", transition: { duration: 0.4 } }
			}
		>
			<MultiAgentHero />

			<section className="auth-right-surface">
				<motion.div
					className="auth-panel-wrapper"
					initial={reduceMotion ? false : { opacity: 0, y: 20 }}
					animate={reduceMotion ? undefined : { opacity: 1, y: 0 }}
					transition={
						reduceMotion
							? undefined
							: { duration: 0.8, ease: [0.16, 1, 0.3, 1] }
					}
				>
					<AuthPanel
						busy={busy}
						entry={entry}
						error={error}
						mode={mode}
						result={result}
						onEntryChange={setEntry}
						onModeChange={setMode}
						onLogin={(account, password) =>
							runAuth(() => authApi.login({ account, password }))
						}
						onRegister={(payload: RegisterPayload) =>
							runAuth(() => authApi.register(payload))
						}
					/>

					{!result && (
						<div className="auth-pills-row">
							<button
								type="button"
								className="provider-pill qq"
								aria-label="QQ 登录"
								onClick={() => handleOAuth("qq")}
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
								type="button"
								className="provider-pill xuexitong"
								aria-label="学习通登录"
								onClick={() => handleOAuth("xuexitong")}
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

			<OAuthStatusDialog
				open={Boolean(oauthProvider)}
				provider={oauthProvider}
				onClose={() => setOAuthProvider(null)}
			/>
		</motion.main>
	);
}
