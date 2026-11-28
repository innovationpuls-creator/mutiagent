import { Check } from "lucide-react";
import { Button } from "../../../components/ui/Button";
import { Drawer } from "../../../components/ui/Drawer";
import { SelectField, TextField } from "../../../components/ui/TextField";
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
	const bind =
		(key: "username" | "identifier" | "password" | "school" | "major") =>
		(event: React.ChangeEvent<HTMLInputElement>) =>
			setDraft((current) => ({ ...current, [key]: event.target.value }));

	return (
		<Drawer
			isOpen={isOpen}
			onClose={closeEditor}
			title={editorMode === "edit" ? "编辑账号" : "新增账号"}
			closeAriaLabel="关闭编辑面板"
			footer={
				<>
					<Button variant="secondary" onClick={closeEditor}>
						取消
					</Button>
					<Button
						icon={<Check aria-hidden="true" />}
						onClick={() => void saveAccount()}
						disabled={busy}
					>
						{editorMode === "edit" ? "保存修改" : "创建账号"}
					</Button>
				</>
			}
		>
			<div className="admin-drawer-form">
				<TextField
					label="用户名"
					name="account-username"
					value={draft.username}
					onChange={bind("username")}
					placeholder="用户名"
				/>
				<TextField
					label="登录标识"
					name="account-identifier"
					value={draft.identifier}
					onChange={bind("identifier")}
					placeholder="邮箱或手机号"
				/>
				<TextField
					label={editorMode === "edit" ? "新密码" : "密码"}
					name="account-password"
					value={draft.password}
					onChange={bind("password")}
					placeholder={editorMode === "edit" ? "留空则不修改密码" : "密码"}
					type="password"
				/>
				<SelectField
					label="角色"
					name="account-role"
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
				</SelectField>
				<TextField
					label="学校"
					name="account-school"
					value={draft.school}
					onChange={bind("school")}
					placeholder="学校"
				/>
				<TextField
					label="专业"
					name="account-major"
					value={draft.major}
					onChange={bind("major")}
					placeholder="专业"
				/>
				<TextField
					label="班级"
					name="account-class-name"
					value={draft.class_name}
					onChange={(event) =>
						setDraft((current) => ({
							...current,
							class_name: event.target.value,
						}))
					}
					placeholder="班级"
				/>
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
		</Drawer>
	);
}
