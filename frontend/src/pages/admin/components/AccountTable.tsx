import { KeyRound, Pencil, Trash2 } from "lucide-react";
import { Button } from "../../../components/ui/Button";
import { StatusBadge } from "../../../components/ui/StatusBadge";
import type { AuthRole, AuthUser } from "../../../types/auth";

interface AccountTableProps {
	visibleAccounts: AuthUser[];
	selectedUids: Set<string>;
	currentUser: AuthUser | null;
	busy: boolean;
	allVisibleSelected: boolean;
	toggleAllVisible: () => void;
	toggleSelected: (uid: string) => void;
	toggleAccount: (account: AuthUser) => Promise<void>;
	openEditEditor: (account: AuthUser) => void;
	onResetPassword: (account: AuthUser) => void;
	onDeleteAccount: (account: AuthUser) => void;
}

const roleLabels: Record<AuthRole, string> = {
	student: "学生",
	admin: "管理员",
};

const providerLabels: Record<string, string> = {
	password: "密码",
	qq: "QQ",
	xuexitong: "学习通",
};

const dateFormatter = new Intl.DateTimeFormat("zh-CN", {
	year: "numeric",
	month: "2-digit",
	day: "2-digit",
	hour: "2-digit",
	minute: "2-digit",
});

function formatDate(value: string | null) {
	if (!value) return "暂无";
	const date = new Date(value);
	if (Number.isNaN(date.getTime())) return "暂无";
	return dateFormatter.format(date);
}

export function AccountTable({
	visibleAccounts,
	selectedUids,
	currentUser,
	busy,
	allVisibleSelected,
	toggleAllVisible,
	toggleSelected,
	toggleAccount,
	openEditEditor,
	onResetPassword,
	onDeleteAccount,
}: AccountTableProps) {
	return (
		<section
			className="data-table admin-table"
			aria-label="账号列表"
			aria-busy={busy}
		>
			<div className="data-table-row admin-table-row data-table-head">
				<label className="admin-check-cell">
					<input
						checked={allVisibleSelected}
						onChange={toggleAllVisible}
						type="checkbox"
					/>
					<span className="admin-visually-hidden">选择当前列表全部账号</span>
				</label>
				<span>账号</span>
				<span>角色</span>
				<span>学校 · 专业 · 班级</span>
				<span>状态</span>
				<span className="admin-col-secondary">登录方式</span>
				<span className="admin-col-secondary">创建时间</span>
				<span className="admin-col-secondary">最近登录</span>
				<span className="data-table-sticky-end">操作</span>
			</div>
			{visibleAccounts.map((account) => {
				const isSelf = currentUser?.uid === account.uid;
				return (
					<div className="data-table-row admin-table-row" key={account.uid}>
						<label className="admin-check-cell">
							<input
								checked={selectedUids.has(account.uid)}
								onChange={() => toggleSelected(account.uid)}
								type="checkbox"
								aria-label={`选择 ${account.username}`}
							/>
						</label>
						<span className="admin-user-name">
							<strong>
								{account.username}
								{isSelf ? <small>当前登录</small> : null}
							</strong>
							<span className="admin-cell-sub">{account.identifier}</span>
						</span>
						<span>{roleLabels[account.role]}</span>
						<span className="admin-cell-stack">
							<span>{account.school || "未填写学校"}</span>
							<span className="admin-cell-sub">
								{account.major || "未填写专业"} ·{" "}
								{account.class_name || "未填写班级"}
							</span>
						</span>
						<button
							className="admin-status-toggle"
							type="button"
							onClick={() => void toggleAccount(account)}
							disabled={busy || (isSelf && account.is_active)}
						>
							<StatusBadge
								variant="pill"
								tone={account.is_active ? "success" : "neutral"}
								showDot={false}
							>
								{account.is_active ? "启用" : "停用"}
							</StatusBadge>
						</button>
						<span className="admin-col-secondary">
							{providerLabels[account.provider] ?? account.provider}
						</span>
						<span className="admin-cell-time admin-col-secondary">
							{formatDate(account.created_at)}
						</span>
						<span className="admin-cell-time admin-col-secondary">
							{formatDate(account.last_login_at)}
						</span>
						<span className="admin-row-actions data-table-sticky-end">
							<Button
								variant="icon"
								size="sm"
								onClick={() => openEditEditor(account)}
								aria-label={`编辑 ${account.username}`}
								disabled={busy}
								icon={<Pencil aria-hidden="true" />}
							/>
							<Button
								variant="icon"
								size="sm"
								onClick={() => onResetPassword(account)}
								aria-label={`重置 ${account.username} 的密码`}
								disabled={busy}
								icon={<KeyRound aria-hidden="true" />}
							/>
							<Button
								variant="icon"
								size="sm"
								onClick={() => onDeleteAccount(account)}
								aria-label={`删除 ${account.username}`}
								disabled={busy || isSelf}
								icon={<Trash2 aria-hidden="true" />}
							/>
						</span>
					</div>
				);
			})}
			{visibleAccounts.length === 0 ? (
				<p className="admin-empty">
					{busy ? "正在加载账号。" : "没有匹配的账号。"}
				</p>
			) : null}
		</section>
	);
}
