import { ConfirmDialog } from "../../../components/ui/ConfirmDialog";
import type { AuthUser } from "../../../types/auth";

export type DeleteTarget =
	| { type: "single"; account: AuthUser }
	| { type: "batch"; accounts: AuthUser[] };

interface DeleteConfirmModalProps {
	deleteTarget: DeleteTarget | null;
	onClose: () => void;
	onConfirm: () => Promise<void>;
	busy: boolean;
}

export function DeleteConfirmModal({
	deleteTarget,
	onClose,
	onConfirm,
	busy,
}: DeleteConfirmModalProps) {
	const count = deleteTarget
		? deleteTarget.type === "single"
			? 1
			: deleteTarget.accounts.length
		: 0;

	return (
		<ConfirmDialog
			isOpen={Boolean(deleteTarget)}
			title={`确认删除 ${count} 个账号？`}
			description="删除会移除账号及该账号关联的学习数据，此操作不可撤销。"
			confirmLabel="确认删除"
			destructive
			busy={busy}
			onConfirm={onConfirm}
			onClose={onClose}
		/>
	);
}
