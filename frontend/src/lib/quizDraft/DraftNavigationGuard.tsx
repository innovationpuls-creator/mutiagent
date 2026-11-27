import { useContext, useEffect, useRef, useState } from "react";
import { UNSAFE_DataRouterContext, useBlocker } from "react-router-dom";
import { useDialogAccessibility } from "../../components/ui/useDialogAccessibility";

interface Props {
	dirty: boolean;
	save: () => Promise<void>;
}
function RouterGuard({ dirty, save }: Props) {
	const blocker = useBlocker(dirty);
	const [error, setError] = useState(false);
	const closeRef = useRef<HTMLButtonElement>(null);
	useDialogAccessibility({
		isOpen: blocker.state === "blocked" && error,
		onClose: () => {
			if (blocker.state === "blocked") blocker.reset();
		},
		initialFocusRef: closeRef,
	});
	useEffect(() => {
		if (blocker.state !== "blocked") {
			setError(false);
			return;
		}
		let cancelled = false;
		save()
			.then(() => {
				if (!cancelled && blocker.state === "blocked") blocker.proceed();
			})
			.catch(() => {
				if (!cancelled) setError(true);
			});
		return () => {
			cancelled = true;
		};
	}, [blocker, save]);
	if (blocker.state !== "blocked" || !error) return null;
	return (
		<div className="draft-navigation-backdrop">
			<div
				className="draft-navigation-warning"
				role="alertdialog"
				aria-modal="true"
				aria-label="草稿尚未保存"
			>
				<h2>草稿尚未保存</h2>
				<p>继续作答或重试保存，可以保留当前答案。</p>
				<button ref={closeRef} type="button" onClick={() => blocker.reset()}>
					继续作答
				</button>
				<button
					type="button"
					onClick={() => {
						void save()
							.then(() => blocker.proceed())
							.catch(() => setError(true));
					}}
				>
					重试保存并离开
				</button>
				<button type="button" onClick={() => blocker.proceed()}>
					不保存并离开
				</button>
			</div>
		</div>
	);
}
export function DraftNavigationGuard(props: Props) {
	const context = useContext(UNSAFE_DataRouterContext);
	useEffect(() => {
		const listener = (event: BeforeUnloadEvent) => {
			if (props.dirty) {
				event.preventDefault();
				event.returnValue = "";
			}
		};
		window.addEventListener("beforeunload", listener);
		return () => window.removeEventListener("beforeunload", listener);
	}, [props.dirty]);
	return context ? <RouterGuard {...props} /> : null;
}
