import { motion, useReducedMotion } from "framer-motion";
import { Check, X } from "lucide-react";
import type { AuthRole } from "../../../types/auth";

export interface AccountDraft {
	username: string;
	identifier: string;
	password: string;
	role: AuthRole;
	is_active: boolean;
	school: string;
	major: string;
	class_name: string;
}

interface AccountDrawerProps {
	isOpen: boolean;
	busy: boolean;
	editorMode: "create" | "edit";
	draft: AccountDraft;
	setDraft: React.Dispatch<React.SetStateAction<AccountDraft>>;
	editingSelf: boolean;
	closeEditor: () => void;
	saveAccount: () => Promise<void>;
}

export function AccountDrawer({
	isOpen,
	busy,
	editorMode,
	draft,
	setDraft,
	editingSelf,
	closeEditor,
	saveAccount,
}: AccountDrawerProps) {
	const reduceMotion = useReducedMotion();

	if (!isOpen) return null;

	return (
		<motion.aside
			className="admin-drawer"
			aria-label={editorMode === "edit" ? "编辑账号" : "新增账号"}
			initial={reduceMotion ? { opacity: 0 } : { opacity: 0, x: 32 }}
			animate={reduceMotion ? { opacity: 1 } : { opacity: 1, x: 0 }}
			exit={reduceMotion ? { opacity: 0 } : { opacity: 0, x: 32 }}
			transition={
				reduceMotion
					? { duration: 0.12 }
					: { duration: 0.42, ease: [0.33, 1, 0.68, 1] }
			}
		>
			<header>
				<div>
					<p className="admin-kicker">account</p>
					<h2>{editorMode === "edit" ? "编辑账号" : "新增账号"}</h2>
				</div>
				<button type="button" onClick={closeEditor} aria-label="关闭编辑面板">
					<X aria-hidden="true" />
				</button>
			</header>
			<div className="admin-drawer-form">
				<label>
					<span>用户名</span>
					<input
						value={draft.username}
						onChange={(event) =>
							setDraft((current) => ({
								...current,
								username: event.target.value,
							}))
						}
						placeholder="用户名"
					/>
				</label>
				<label>
					<span>登录标识</span>
					<input
						value={draft.identifier}
						onChange={(event) =>
							setDraft((current) => ({
								...current,
								identifier: event.target.value,
							}))
						}
						placeholder="邮箱或手机号"
					/>
				</label>
				<label>
					<span>{editorMode === "edit" ? "新密码" : "密码"}</span>
					<input
						value={draft.password}
						onChange={(event) =>
							setDraft((current) => ({
								...current,
								password: event.target.value,
							}))
						}
						placeholder={editorMode === "edit" ? "留空则不修改密码" : "密码"}
						type="password"
					/>
				</label>
				<label>
					<span>角色</span>
					<select
						value={draft.role}
						onChange={(event) =>
							setDraft((current) => ({
								...current,
								role: event.target.value as AuthRole,
							}))
						}
						disabled={editingSelf}
					>
						<option value="student">学生</option>
						<option value="admin">管理员</option>
					</select>
				</label>
				<label>
					<span>学校</span>
					<input
						value={draft.school}
						onChange={(event) =>
							setDraft((current) => ({
								...current,
								school: event.target.value,
							}))
						}
						placeholder="学校"
					/>
				</label>
				<label>
					<span>专业</span>
					<input
						value={draft.major}
						onChange={(event) =>
							setDraft((current) => ({
								...current,
								major: event.target.value,
							}))
						}
						placeholder="专业"
					/>
				</label>
				<label>
					<span>班级</span>
					<input
						value={draft.class_name}
						onChange={(event) =>
							setDraft((current) => ({
								...current,
								class_name: event.target.value,
							}))
						}
						placeholder="班级"
					/>
				</label>
				<label className="admin-drawer-switch">
					<input
						checked={draft.is_active}
						onChange={(event) =>
							setDraft((current) => ({
								...current,
								is_active: event.target.checked,
							}))
						}
						type="checkbox"
						disabled={editingSelf}
					/>
					<span>{draft.is_active ? "账号启用" : "账号停用"}</span>
				</label>
			</div>
			<footer>
				<button
					className="admin-secondary-action"
					type="button"
					onClick={closeEditor}
				>
					取消
				</button>
				<button
					className="admin-primary-action"
					type="button"
					onClick={() => void saveAccount()}
					disabled={busy}
				>
					<Check aria-hidden="true" />
					<span>{editorMode === "edit" ? "保存修改" : "创建账号"}</span>
				</button>
			</footer>
		</motion.aside>
	);
}
