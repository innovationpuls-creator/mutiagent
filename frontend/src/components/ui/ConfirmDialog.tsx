import type { ReactNode } from "react";
import { Button } from "./Button";
import { Dialog } from "./Dialog";

export interface ConfirmDialogProps {
	isOpen: boolean;
	title: string;
	description?: ReactNode;
	confirmLabel?: string;
	cancelLabel?: string;
	destructive?: boolean;
	busy?: boolean;
	onConfirm: () => void | Promise<void>;
	onClose: () => void;
}

export function ConfirmDialog({
	isOpen,
	title,
	description,
	confirmLabel = "确认",
	cancelLabel = "取消",
	destructive = false,
	busy = false,
	onConfirm,
	onClose,
}: ConfirmDialogProps) {
	return (
		<Dialog
			isOpen={isOpen}
			onClose={onClose}
			title={title}
			size="compact"
			closeOnBackdrop={!destructive}
			showCloseButton={false}
			footer={
				<>
					<Button variant="secondary" onClick={onClose} disabled={busy}>
						{cancelLabel}
					</Button>
					<Button
						variant={destructive ? "danger" : "primary"}
						onClick={() => void onConfirm()}
						loading={busy}
					>
						{confirmLabel}
					</Button>
				</>
			}
		>
			{description ? <p>{description}</p> : null}
		</Dialog>
	);
}
