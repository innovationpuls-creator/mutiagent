import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { ArrowRight, CheckCircle2 } from "lucide-react";
import type { FormEvent } from "react";
import { useCallback, useState } from "react";
import type {
	AuthEntry,
	AuthMode,
	AuthResponse,
	RegisterPayload,
} from "../../types/auth";
import { Button } from "../ui/Button";
import { TextField } from "../ui/TextField";

const EMAIL_RE = /^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$/;
const PHONE_RE = /^1[3-9]\d[\s]?\d{4}[\s]?\d{4}$/;
const IDENTIFIER_HINT = "请输入有效的邮箱或手机号（11 位中国大陆手机号）";

function validateIdentifier(value: string): string | null {
	const trimmed = value.trim();
	if (!trimmed) return null;
	if (EMAIL_RE.test(trimmed) || PHONE_RE.test(trimmed)) return null;
	return IDENTIFIER_HINT;
}

interface AuthPanelProps {
	busy: boolean;
	entry: AuthEntry;
	mode: AuthMode;
	result: AuthResponse | null;
	error: string | null;
	onEntryChange(entry: AuthEntry): void;
	onModeChange(mode: AuthMode): void;
	onLogin(account: string, password: string): Promise<void>;
	onRegister(payload: RegisterPayload): Promise<void>;
}

const initialFields = {
	account: "",
	password: "",
	username: "",
	identifier: "",
	confirmPassword: "",
	school: "",
	major: "",
	className: "",
};

const tabs: { value: AuthMode; label: string }[] = [
	{ value: "login", label: "登录" },
	{ value: "register", label: "注册" },
];

const entries: { value: AuthEntry; label: string }[] = [
	{ value: "student", label: "学生" },
	{ value: "admin", label: "管理员" },
];

export function AuthPanel(props: AuthPanelProps) {
	const reduceMotion = useReducedMotion();

	if (props.result) {
		return <SuccessPanel result={props.result} />;
	}

	const isLogin = props.mode === "login";
	const pillTransition = reduceMotion
		? { duration: 0 }
		: { duration: 0.42, ease: [0.33, 1, 0.68, 1] as const };

	return (
		<section className="auth-glass-panel" aria-label="登录注册">
			<p className="auth-overline">A QUIET SPACE TO LEARN</p>
			<h2>
				{isLogin ? (
					<>
						<em>欢迎回来</em>，<br />
						回到你的栖息地。
					</>
				) : (
					<>
						一张<em>空白画布</em>，<br />
						写给你的心绪。
					</>
				)}
			</h2>
			{isLogin ? (
				<div className="auth-copy-stack">
					<p>外界再喧嚣，这里的思绪依然澄澈。请重新连接。</p>
				</div>
			) : null}

			<div className="auth-entry-tabs" role="tablist" aria-label="登录身份">
				{entries.map((entry) => (
					<button
						key={entry.value}
						className="auth-entry-tab"
						type="button"
						role="tab"
						aria-selected={props.entry === entry.value}
						onClick={() => props.onEntryChange(entry.value)}
					>
						{props.entry === entry.value ? (
							<motion.span
								className="auth-entry-active"
								layoutId="auth-entry-active"
								transition={pillTransition}
							/>
						) : null}
						<span className="auth-entry-label">{entry.label}</span>
					</button>
				))}
			</div>

			<div className="auth-pill-tabs" role="tablist" aria-label="账号入口">
				{tabs.map((tab) => (
					<button
						key={tab.value}
						className="auth-pill-tab"
						type="button"
						role="tab"
						aria-selected={props.mode === tab.value}
						onClick={() => props.onModeChange(tab.value)}
					>
						{props.mode === tab.value ? (
							<motion.span
								className="auth-pill-active"
								layoutId="auth-pill-active"
								transition={pillTransition}
							/>
						) : null}
						<span className="auth-pill-label">{tab.label}</span>
					</button>
				))}
			</div>

			<AuthForm {...props} />
		</section>
	);
}

function AuthForm({
	busy,
	entry,
	error,
	mode,
	onLogin,
	onRegister,
}: Omit<AuthPanelProps, "result" | "onModeChange" | "onEntryChange">) {
	const [fields, setFields] = useState(initialFields);
	const [identifierError, setIdentifierError] = useState<string | null>(null);
	const reduceMotion = useReducedMotion();

	const fieldKey = mode === "login" ? "account" : ("identifier" as const);
	const fieldValue = fields[fieldKey];

	const setField = (key: keyof typeof initialFields, value: string) => {
		setFields((current) => ({ ...current, [key]: value }));
	};

	const validateAndSetError = useCallback((value: string) => {
		const err = validateIdentifier(value);
		setIdentifierError(err);
		return err;
	}, []);

	const handleBlur = useCallback(() => {
		validateAndSetError(fieldValue);
	}, [validateAndSetError, fieldValue]);

	const submit = (event: FormEvent<HTMLFormElement>) => {
		event.preventDefault();
		const err = validateAndSetError(fieldValue);
		if (err) return;

		if (mode === "login") {
			void onLogin(fields.account, fields.password);
			return;
		}
		void onRegister({
			username: fields.username,
			identifier: fields.identifier,
			password: fields.password,
			confirmPassword: fields.confirmPassword,
			role: entry,
			school: fields.school,
			major: fields.major,
			className: fields.className,
		});
	};

	const fieldReveal = reduceMotion
		? undefined
		: {
				initial: { opacity: 0, y: 12 },
				animate: { opacity: 1, y: 0 },
				exit: { opacity: 0, y: -8 },
				transition: { duration: 0.42, ease: [0.25, 1, 0.5, 1] as const },
			};

	return (
		<form className="auth-form-glass" onSubmit={submit}>
			<AnimatePresence mode="popLayout" initial={false}>
				{mode === "register" ? (
					<motion.div key="username" layout {...fieldReveal}>
						<TextField
							label="用户名"
							name="username"
							autoComplete="name"
							value={fields.username}
							onChange={(event) => setField("username", event.target.value)}
							minLength={1}
							required
						/>
					</motion.div>
				) : null}

				<motion.div key="identifier" layout {...fieldReveal}>
					<TextField
						label={mode === "login" ? "账号" : "账号（邮箱或手机号）"}
						name={mode === "login" ? "account" : "identifier"}
						autoComplete={mode === "login" ? "username" : "email"}
						value={fieldValue}
						onChange={(event) => setField(fieldKey, event.target.value)}
						onBlur={handleBlur}
						minLength={3}
						required
						aria-invalid={identifierError ? "true" : undefined}
					/>
					{identifierError ? (
						<p className="auth-field-error">{identifierError}</p>
					) : null}
				</motion.div>

				<motion.div key="password" layout {...fieldReveal}>
					<TextField
						label={mode === "login" ? "密码" : "设置密码"}
						name="password"
						type="password"
						autoComplete={
							mode === "login" ? "current-password" : "new-password"
						}
						value={fields.password}
						onChange={(event) => setField("password", event.target.value)}
						minLength={6}
						required
					/>
				</motion.div>

				{mode === "register" ? (
					<>
						<motion.div key="school" layout {...fieldReveal}>
							<TextField
								label="学校"
								name="school"
								autoComplete="organization"
								value={fields.school}
								onChange={(event) => setField("school", event.target.value)}
								minLength={1}
								required
							/>
						</motion.div>
						<motion.div key="major" layout {...fieldReveal}>
							<TextField
								label="专业"
								name="major"
								autoComplete="organization-title"
								value={fields.major}
								onChange={(event) => setField("major", event.target.value)}
								minLength={1}
								required
							/>
						</motion.div>
						<motion.div key="className" layout {...fieldReveal}>
							<TextField
								label="班级"
								name="className"
								value={fields.className}
								onChange={(event) => setField("className", event.target.value)}
								minLength={1}
								required
							/>
						</motion.div>
						<motion.div key="confirmPassword" layout {...fieldReveal}>
							<TextField
								label="确认密码"
								name="confirmPassword"
								type="password"
								autoComplete="new-password"
								value={fields.confirmPassword}
								onChange={(event) =>
									setField("confirmPassword", event.target.value)
								}
								minLength={6}
								required
							/>
						</motion.div>
					</>
				) : null}
			</AnimatePresence>

			{error ? <p className="auth-error">{error}</p> : null}

			<Button
				type="submit"
				loading={busy}
				icon={<ArrowRight aria-hidden="true" />}
			>
				{mode === "login" ? "进入系统" : "完成注册"}
			</Button>
		</form>
	);
}

function SuccessPanel({ result }: { result: AuthResponse }) {
	const reduceMotion = useReducedMotion();
	return (
		<motion.div
			className="auth-glass-panel auth-success"
			aria-label="登录成功"
			initial={reduceMotion ? false : { opacity: 0, scale: 0.96 }}
			animate={reduceMotion ? undefined : { opacity: 1, scale: 1 }}
			transition={
				reduceMotion ? undefined : { duration: 0.6, ease: [0.25, 1, 0.5, 1] }
			}
		>
			<CheckCircle2 aria-hidden="true" className="success-icon" />
			<h2>思绪已对齐</h2>
			<p>{result.user.username}，你专属的无边界学习空间已准备就绪。</p>
		</motion.div>
	);
}
