import { Check } from "lucide-react";
import { useRef } from "react";
import { Button } from "../../../components/ui/Button";
import { Dialog } from "../../../components/ui/Dialog";
import { TextField } from "../../../components/ui/TextField";
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

	return (
		<Dialog
			isOpen={Boolean(resetTarget)}
			onClose={onClose}
			title="重置密码"
			size="compact"
			showCloseButton={false}
			initialFocusRef={passwordInputRef}
			footer={
				<>
					<Button variant="secondary" onClick={onClose}>
						取消
					</Button>
					<Button
						icon={<Check aria-hidden="true" />}
						onClick={() => void onConfirm()}
						disabled={busy}
					>
						保存密码
					</Button>
				</>
			}
		>
			<p>{resetTarget?.username} 的新密码会立即生效。</p>
			<TextField
				ref={passwordInputRef}
				label="新密码"
				name="reset-password"
				value={resetPassword}
				onChange={(event) => setResetPassword(event.target.value)}
				type="password"
				placeholder="输入新密码"
			/>
		</Dialog>
	);
}
