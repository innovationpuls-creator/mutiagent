import { AnimatePresence } from "framer-motion";
import { Download, FileUp, Plus, Search, X } from "lucide-react";
import { type ChangeEvent, useEffect, useMemo, useRef, useState } from "react";
import {
	type AdminAccountApi,
	type AdminBatchAction,
	type AdminImportResult,
	adminApi as defaultAdminApi,
} from "../../api/admin";
import { useAuth } from "../../contexts/AuthContext";
import type { AuthRole, AuthUser } from "../../types/auth";
import { type AccountDraft, AccountDrawer } from "./components/AccountDrawer";
import { AccountTable } from "./components/AccountTable";
import {
	DeleteConfirmModal,
	type DeleteTarget,
} from "./components/DeleteConfirmModal";
import { ResetPasswordModal } from "./components/ResetPasswordModal";
import "./admin.css";

interface AdminAccountsPageProps {
	adminApi?: AdminAccountApi;
}

type RoleFilter = AuthRole | "all";
type StatusFilter = "all" | "active" | "disabled";
type EditorMode = "create" | "edit";

const emptyDraft: AccountDraft = {
	username: "",
	identifier: "",
	password: "",
	role: "student",
	is_active: true,
	school: "",
	major: "",
	class_name: "",
};

function toDraft(account: AuthUser): AccountDraft {
	return {
		username: account.username,
		identifier: account.identifier,
		password: "",
		role: account.role,
		is_active: account.is_active,
		school: account.school,
		major: account.major,
		class_name: account.class_name,
	};
}

function selectedAccountList(accounts: AuthUser[], selectedUids: Set<string>) {
	return accounts.filter((account) => selectedUids.has(account.uid));
}

export function AdminAccountsPage({
	adminApi = defaultAdminApi,
}: AdminAccountsPageProps) {
	const { token, user } = useAuth();
	const importInputRef = useRef<HTMLInputElement>(null);
	const [accounts, setAccounts] = useState<AuthUser[]>([]);
	const [draft, setDraft] = useState<AccountDraft>(emptyDraft);
	const [editorMode, setEditorMode] = useState<EditorMode>("create");
	const [editingAccount, setEditingAccount] = useState<AuthUser | null>(null);
	const [isEditorOpen, setIsEditorOpen] = useState(false);
	const [query, setQuery] = useState("");
	const [roleFilter, setRoleFilter] = useState<RoleFilter>("all");
	const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
	const [selectedUids, setSelectedUids] = useState<Set<string>>(
		() => new Set(),
	);
	const [batchRole, setBatchRole] = useState<AuthRole>("student");
	const [deleteTarget, setDeleteTarget] = useState<DeleteTarget | null>(null);
	const [resetTarget, setResetTarget] = useState<AuthUser | null>(null);
	const [resetPassword, setResetPassword] = useState("");
	const [importResult, setImportResult] = useState<AdminImportResult | null>(
		null,
	);
	const [busy, setBusy] = useState(false);
	const [error, setError] = useState<string | null>(null);

	useEffect(() => {
		if (!token) return;
		let cancelled = false;
		setBusy(true);
		setError(null);
		adminApi
			.listAccounts(token)
			.then((nextAccounts) => {
				if (!cancelled) setAccounts(nextAccounts);
			})
			.catch((accountError) => {
				if (!cancelled)
					setError(
						accountError instanceof Error
							? accountError.message
							: "账号加载失败",
					);
			})
			.finally(() => {
				if (!cancelled) setBusy(false);
			});
		return () => {
			cancelled = true;
		};
	}, [adminApi, token]);

	const visibleAccounts = useMemo(() => {
		const text = query.trim().toLowerCase();
		return accounts.filter((account) => {
			const matchesText =
				!text ||
				account.username.toLowerCase().includes(text) ||
				account.identifier.toLowerCase().includes(text);
			const matchesRole = roleFilter === "all" || account.role === roleFilter;
			const matchesStatus =
				statusFilter === "all" ||
				(statusFilter === "active" ? account.is_active : !account.is_active);
			return matchesText && matchesRole && matchesStatus;
		});
	}, [accounts, query, roleFilter, statusFilter]);

	const selectedAccounts = useMemo(
		() => selectedAccountList(accounts, selectedUids),
		[accounts, selectedUids],
	);
	const visibleSelectedCount = visibleAccounts.filter((account) =>
		selectedUids.has(account.uid),
	).length;
	const allVisibleSelected =
		visibleAccounts.length > 0 &&
		visibleSelectedCount === visibleAccounts.length;
	const selectedHasSelf = Boolean(user && selectedUids.has(user.uid));
	const editingSelf = Boolean(user && editingAccount?.uid === user.uid);

	const replaceAccounts = (nextAccounts: AuthUser[]) => {
		setAccounts(nextAccounts);
		setSelectedUids((current) => {
			const nextUids = new Set(nextAccounts.map((account) => account.uid));
			return new Set([...current].filter((uid) => nextUids.has(uid)));
		});
	};

	const closeEditor = () => {
		setDraft(emptyDraft);
		setEditingAccount(null);
		setEditorMode("create");
		setIsEditorOpen(false);
	};

	const openCreateEditor = () => {
		setDraft(emptyDraft);
		setEditingAccount(null);
		setEditorMode("create");
		setError(null);
		setIsEditorOpen(true);
	};

	const openEditEditor = (account: AuthUser) => {
		setDraft(toDraft(account));
		setEditingAccount(account);
		setEditorMode("edit");
		setError(null);
		setIsEditorOpen(true);
	};

	const saveAccount = async () => {
		if (!token) return;
		const username = draft.username.trim();
		const identifier = draft.identifier.trim();
		const password = draft.password.trim();
		if (!username || !identifier) {
			setError("用户名和登录标识不能为空");
			return;
		}
		const school = draft.school.trim();
		const major = draft.major.trim();
		const class_name = draft.class_name.trim();
		if (!school || !major || !class_name) {
			setError("学校、专业、班级不能为空");
			return;
		}
		if (editorMode === "create" && !password) {
			setError("新增账号必须填写密码");
			return;
		}
		if (editingSelf && (draft.role !== "admin" || !draft.is_active)) {
			setError("当前登录管理员不能停用自己，也不能移除自己的管理员权限");
			return;
		}

		setBusy(true);
		setError(null);
		try {
			if (editorMode === "edit" && editingAccount) {
				const updated = await adminApi.updateAccount(
					token,
					editingAccount.uid,
					{
						username,
						identifier,
						role: draft.role,
						is_active: draft.is_active,
						school,
						major,
						class_name,
						...(password ? { password } : {}),
					},
				);
				setAccounts((current) =>
					current.map((account) =>
						account.uid === updated.uid ? updated : account,
					),
				);
			} else {
				const created = await adminApi.createAccount(token, {
					username,
					identifier,
					password,
					role: draft.role,
					is_active: draft.is_active,
					school,
					major,
					class_name,
				});
				setAccounts((current) => [created, ...current]);
			}
			closeEditor();
		} catch (accountError) {
			setError(
				accountError instanceof Error ? accountError.message : "账号保存失败",
			);
		} finally {
			setBusy(false);
		}
	};

	const requestDeleteAccount = (account: AuthUser) => {
		if (user && account.uid === user.uid) {
			setError("不能删除当前登录管理员");
			return;
		}
		setDeleteTarget({ type: "single", account });
	};

	const confirmDelete = async () => {
		if (!token || !deleteTarget) return;
		setBusy(true);
		setError(null);
		try {
			if (deleteTarget.type === "single") {
				await adminApi.deleteAccount(token, deleteTarget.account.uid);
				setAccounts((current) =>
					current.filter((account) => account.uid !== deleteTarget.account.uid),
				);
				setSelectedUids((current) => {
					const next = new Set(current);
					next.delete(deleteTarget.account.uid);
					return next;
				});
			} else {
				const deletedUids = deleteTarget.accounts.map((account) => account.uid);
				const nextAccounts = await adminApi.batchAccounts(token, {
					action: "delete",
					uids: deletedUids,
				});
				replaceAccounts(nextAccounts);
			}
			setDeleteTarget(null);
			if (
				editingAccount &&
				deleteTarget.type === "single" &&
				editingAccount.uid === deleteTarget.account.uid
			) {
				closeEditor();
			}
		} catch (accountError) {
			setError(
				accountError instanceof Error ? accountError.message : "账号删除失败",
			);
		} finally {
			setBusy(false);
		}
	};

	const toggleAccount = async (account: AuthUser) => {
		if (!token) return;
		if (user && account.uid === user.uid && account.is_active) {
			setError("不能停用当前登录管理员");
			return;
		}
		setBusy(true);
		setError(null);
		try {
			const updated = await adminApi.updateAccount(token, account.uid, {
				username: account.username,
				identifier: account.identifier,
				role: account.role,
				is_active: !account.is_active,
				school: account.school,
				major: account.major,
				class_name: account.class_name,
			});
			setAccounts((current) =>
				current.map((item) => (item.uid === account.uid ? updated : item)),
			);
		} catch (accountError) {
			setError(
				accountError instanceof Error
					? accountError.message
					: "账号状态更新失败",
			);
		} finally {
			setBusy(false);
		}
	};

	const toggleSelected = (uid: string) => {
		setSelectedUids((current) => {
			const next = new Set(current);
			if (next.has(uid)) {
				next.delete(uid);
			} else {
				next.add(uid);
			}
			return next;
		});
	};

	const toggleAllVisible = () => {
		setSelectedUids((current) => {
			const next = new Set(current);
			if (allVisibleSelected) {
				for (const account of visibleAccounts) {
					next.delete(account.uid);
				}
			} else {
				for (const account of visibleAccounts) {
					next.add(account.uid);
				}
			}
			return next;
		});
	};

	const runBatch = async (action: AdminBatchAction, role?: AuthRole) => {
		if (!token || selectedAccounts.length === 0) return;
		if ((action === "delete" || action === "deactivate") && selectedHasSelf) {
			setError("批量操作不能删除或停用当前登录管理员");
			return;
		}
		if (action === "set_role" && selectedHasSelf && role !== "admin") {
			setError("不能把当前登录管理员改成非管理员角色");
			return;
		}
		setBusy(true);
		setError(null);
		try {
			const nextAccounts = await adminApi.batchAccounts(token, {
				action,
				uids: selectedAccounts.map((account) => account.uid),
				...(role ? { role } : {}),
			});
			replaceAccounts(nextAccounts);
		} catch (accountError) {
			setError(
				accountError instanceof Error ? accountError.message : "批量操作失败",
			);
		} finally {
			setBusy(false);
		}
	};

	const requestBatchDelete = () => {
		if (selectedAccounts.length === 0) return;
		if (selectedHasSelf) {
			setError("批量删除不能包含当前登录管理员");
			return;
		}
		setDeleteTarget({ type: "batch", accounts: selectedAccounts });
	};

	const saveResetPassword = async () => {
		if (!token || !resetTarget) return;
		const password = resetPassword.trim();
		if (!password) {
			setError("重置密码不能为空");
			return;
		}
		setBusy(true);
		setError(null);
		try {
			const updated = await adminApi.updateAccount(token, resetTarget.uid, {
				username: resetTarget.username,
				identifier: resetTarget.identifier,
				role: resetTarget.role,
				is_active: resetTarget.is_active,
				school: resetTarget.school,
				major: resetTarget.major,
				class_name: resetTarget.class_name,
				password,
			});
			setAccounts((current) =>
				current.map((account) =>
					account.uid === updated.uid ? updated : account,
				),
			);
			setResetTarget(null);
			setResetPassword("");
		} catch (accountError) {
			setError(
				accountError instanceof Error ? accountError.message : "密码重置失败",
			);
		} finally {
			setBusy(false);
		}
	};

	const importCsv = async (event: ChangeEvent<HTMLInputElement>) => {
		if (!token) return;
		const file = event.target.files?.[0];
		event.target.value = "";
		if (!file) return;
		setBusy(true);
		setError(null);
		try {
			const csvText = await file.text();
			const result = await adminApi.importAccounts(token, csvText);
			setImportResult(result);
			const nextAccounts = await adminApi.listAccounts(token);
			replaceAccounts(nextAccounts);
		} catch (accountError) {
			setError(
				accountError instanceof Error ? accountError.message : "CSV 导入失败",
			);
		} finally {
			setBusy(false);
		}
	};

	const exportCsv = async () => {
		if (!token) return;
		setBusy(true);
		setError(null);
		try {
			const csvText = await adminApi.exportAccounts(token);
			const blob = new Blob([csvText], { type: "text/csv;charset=utf-8" });
			const url = URL.createObjectURL(blob);
			const link = document.createElement("a");
			link.href = url;
			link.download = "accounts.csv";
			document.body.appendChild(link);
			link.click();
			link.remove();
			URL.revokeObjectURL(url);
		} catch (accountError) {
			setError(
				accountError instanceof Error ? accountError.message : "账号导出失败",
			);
		} finally {
			setBusy(false);
		}
	};

	return (
		<>
			<header className="admin-header">
				<div>
					<p className="admin-kicker">backstage</p>
					<h1 id="admin-title">账号管理</h1>
				</div>
				<div className="admin-header-actions">
					<button
						className="admin-secondary-action"
						type="button"
						onClick={() => void exportCsv()}
						disabled={busy}
					>
						<Download aria-hidden="true" />
						<span>导出 CSV</span>
					</button>
					<button
						className="admin-secondary-action"
						type="button"
						onClick={() => importInputRef.current?.click()}
						disabled={busy}
					>
						<FileUp aria-hidden="true" />
						<span>导入 CSV</span>
					</button>
					<input
						ref={importInputRef}
						className="admin-file-input"
						type="file"
						accept=".csv,text/csv"
						onChange={(event) => void importCsv(event)}
					/>
					<button
						className="admin-primary-action"
						type="button"
						onClick={openCreateEditor}
						disabled={busy}
					>
						<Plus aria-hidden="true" />
						<span>新增账号</span>
					</button>
				</div>
			</header>

			<section className="admin-toolbar" aria-label="账号筛选和批量管理">
				<label className="admin-search">
					<Search aria-hidden="true" />
					<span className="admin-visually-hidden">查询账号</span>
					<input
						value={query}
						onChange={(event) => setQuery(event.target.value)}
						placeholder="搜索用户名或登录标识"
					/>
				</label>
				<label className="admin-filter">
					<span>角色</span>
					<select
						value={roleFilter}
						onChange={(event) =>
							setRoleFilter(event.target.value as RoleFilter)
						}
					>
						<option value="all">全部角色</option>
						<option value="student">学生</option>
						<option value="admin">管理员</option>
					</select>
				</label>
				<label className="admin-filter">
					<span>状态</span>
					<select
						value={statusFilter}
						onChange={(event) =>
							setStatusFilter(event.target.value as StatusFilter)
						}
					>
						<option value="all">全部状态</option>
						<option value="active">启用</option>
						<option value="disabled">停用</option>
					</select>
				</label>
			</section>

			{selectedAccounts.length > 0 ? (
				<section className="admin-batchbar" aria-label="批量管理工具栏">
					<span className="admin-batch-count">
						已选 {selectedAccounts.length} 个账号
					</span>
					<button
						type="button"
						onClick={() => void runBatch("activate")}
						disabled={busy}
					>
						批量启用
					</button>
					<button
						type="button"
						onClick={() => void runBatch("deactivate")}
						disabled={busy || selectedHasSelf}
					>
						批量停用
					</button>
					<label className="admin-batch-role">
						<span>改为</span>
						<select
							value={batchRole}
							onChange={(event) => setBatchRole(event.target.value as AuthRole)}
						>
							<option value="student">学生</option>
							<option value="admin">管理员</option>
						</select>
					</label>
					<button
						type="button"
						onClick={() => void runBatch("set_role", batchRole)}
						disabled={busy || (selectedHasSelf && batchRole !== "admin")}
					>
						批量改角色
					</button>
					<button
						className="admin-danger-action"
						type="button"
						onClick={requestBatchDelete}
						disabled={busy || selectedHasSelf}
					>
						批量删除
					</button>
					<button
						className="admin-clear-action"
						type="button"
						onClick={() => setSelectedUids(new Set<string>())}
					>
						清空选择
					</button>
				</section>
			) : null}

			{error ? <p className="admin-error">{error}</p> : null}

			{importResult ? (
				<section className="admin-import-result" aria-label="CSV 导入结果">
					<div>
						<strong>导入完成</strong>
						<span>
							创建 {importResult.created} 个，更新 {importResult.updated}{" "}
							个，失败 {importResult.failed} 行
						</span>
					</div>
					{importResult.failures.length > 0 ? (
						<ul>
							{importResult.failures.map((failure) => (
								<li key={`${failure.row}-${failure.identifier ?? "empty"}`}>
									第 {failure.row} 行：{failure.identifier ?? "无登录标识"}，
									{failure.reason}
								</li>
							))}
						</ul>
					) : null}
					<button
						type="button"
						onClick={() => setImportResult(null)}
						aria-label="关闭导入结果"
					>
						<X aria-hidden="true" />
					</button>
				</section>
			) : null}

			<AccountTable
				visibleAccounts={visibleAccounts}
				selectedUids={selectedUids}
				currentUser={user}
				busy={busy}
				allVisibleSelected={allVisibleSelected}
				toggleAllVisible={toggleAllVisible}
				toggleSelected={toggleSelected}
				toggleAccount={toggleAccount}
				openEditEditor={openEditEditor}
				onResetPassword={(account) => {
					setResetTarget(account);
					setResetPassword("");
					setError(null);
				}}
				onDeleteAccount={requestDeleteAccount}
			/>

			<AnimatePresence>
				{isEditorOpen ? (
					<AccountDrawer
						isOpen={isEditorOpen}
						busy={busy}
						editorMode={editorMode}
						draft={draft}
						setDraft={setDraft}
						editingSelf={editingSelf}
						closeEditor={closeEditor}
						saveAccount={saveAccount}
					/>
				) : null}
			</AnimatePresence>

			<AnimatePresence>
				{deleteTarget ? (
					<DeleteConfirmModal
						deleteTarget={deleteTarget}
						onClose={() => setDeleteTarget(null)}
						onConfirm={confirmDelete}
						busy={busy}
					/>
				) : null}
			</AnimatePresence>

			<AnimatePresence>
				{resetTarget ? (
					<ResetPasswordModal
						resetTarget={resetTarget}
						resetPassword={resetPassword}
						setResetPassword={setResetPassword}
						onClose={() => {
							setResetTarget(null);
							setResetPassword("");
						}}
						onConfirm={saveResetPassword}
						busy={busy}
					/>
				) : null}
			</AnimatePresence>
		</>
	);
}
