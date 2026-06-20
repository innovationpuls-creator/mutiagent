import type { AuthMode } from "../../types/auth";

interface AuthTabsProps {
	value: AuthMode;
	onChange(value: AuthMode): void;
}

export function AuthTabs({ value, onChange }: AuthTabsProps) {
	return (
		<div className="auth-tabs" role="tablist" aria-label="账号入口">
			<button
				className="auth-tab"
				type="button"
				role="tab"
				aria-selected={value === "login"}
				onClick={() => onChange("login")}
			>
				登录
			</button>
			<button
				className="auth-tab"
				type="button"
				role="tab"
				aria-selected={value === "register"}
				onClick={() => onChange("register")}
			>
				注册
			</button>
		</div>
	);
}
