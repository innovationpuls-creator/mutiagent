import { motion } from "framer-motion";
import { Upload } from "lucide-react";
import type { AuthUser } from "../../../types/auth";

interface ResetPasswordModalProps {
	resetTarget: AuthUser | null;
	resetPassword: string;
	setResetPassword: (val: string) => void;
	onClose: () => void;
	onConfirm: () => Promise<void>;
	busy: boolean;
}

export function ResetPasswordModal({
	resetTarget,
	resetPassword,
	setResetPassword,
	onClose,
	onConfirm,
	busy,
}: ResetPasswordModalProps) {
	if (!resetTarget) return null;

	return (
		<motion.div
			className="admin-modal-backdrop"
			initial={{ opacity: 0 }}
			animate={{ opacity: 1 }}
			exit={{ opacity: 0 }}
			transition={{ duration: 0.18 }}
		>
			<section className="admin-modal" aria-label="重置密码">
				<h2>重置密码</h2>
				<p>{resetTarget.username} 的新密码会立即生效。</p>
				<label className="admin-modal-field">
					<span>新密码</span>
					<input
						value={resetPassword}
						onChange={(event) => setResetPassword(event.target.value)}
						type="password"
						placeholder="输入新密码"
					/>
				</label>
				<footer>
					<button
						className="admin-secondary-action"
						type="button"
						onClick={onClose}
					>
						取消
					</button>
					<button
						className="admin-primary-action"
						type="button"
						onClick={() => void onConfirm()}
						disabled={busy}
					>
						<Upload aria-hidden="true" />
						<span>保存密码</span>
					</button>
				</footer>
			</section>
		</motion.div>
	);
}
