import { motion } from "framer-motion";
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
	if (!deleteTarget) return null;

	const count =
		deleteTarget.type === "single" ? 1 : deleteTarget.accounts.length;

	return (
		<motion.div
			className="admin-modal-backdrop"
			initial={{ opacity: 0 }}
			animate={{ opacity: 1 }}
			exit={{ opacity: 0 }}
			transition={{ duration: 0.18 }}
		>
			<section className="admin-modal" aria-label="确认删除账号">
				<h2>确认删除 {count} 个账号？</h2>
				<p>删除会移除账号及该账号关联的学习数据，此操作不可撤销。</p>
				<footer>
					<button
						className="admin-secondary-action"
						type="button"
						onClick={onClose}
					>
						取消
					</button>
					<button
						className="admin-danger-action"
						type="button"
						onClick={() => void onConfirm()}
						disabled={busy}
					>
						确认删除
					</button>
				</footer>
			</section>
		</motion.div>
	);
}
