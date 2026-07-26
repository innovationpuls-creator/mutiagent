import { motion } from "framer-motion";
import { Upload } from "lucide-react";
import { useRef } from "react";
import { useDialogAccessibility } from "../../../components/ui/useDialogAccessibility";
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
	const passwordInputRef = useRef<HTMLInputElement>(null);
	useDialogAccessibility({
		isOpen: Boolean(resetTarget),
		onClose,
		initialFocusRef: passwordInputRef,
	});

	if (!resetTarget) return null;

	return (
		<motion.div
			className="admin-modal-backdrop"
			initial={{ opacity: 0 }}
			animate={{ opacity: 1 }}
			exit={{ opacity: 0 }}
			transition={{ duration: 0.18 }}
		>
			<section
				aria-labelledby="reset-password-title"
				aria-modal="true"
				className="admin-modal"
				role="dialog"
			>
				<h2 id="reset-password-title">重置密码</h2>
				<p>{resetTarget.username} 的新密码会立即生效。</p>
				<label className="admin-modal-field">
					<span>新密码</span>
					<input
						ref={passwordInputRef}
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
