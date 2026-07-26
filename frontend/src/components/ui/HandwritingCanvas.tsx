import { motion, useReducedMotion } from "framer-motion";
import type React from "react";
import { useEffect, useRef, useState } from "react";
import { motionTokens } from "../../styles/motion-tokens";
import { useDialogAccessibility } from "./useDialogAccessibility";

const CANVAS_DISPLAY_WIDTH = 480;
const CANVAS_DISPLAY_HEIGHT = 320;

interface HandwritingCanvasProps {
	onSave: (base64Data: string) => void;
	onClose: () => void;
}

function getCanvasPoint(
	event:
		| React.MouseEvent<HTMLCanvasElement>
		| React.TouchEvent<HTMLCanvasElement>,
	canvas: HTMLCanvasElement,
) {
	const pointer =
		"touches" in event
			? event.touches.length > 0
				? event.touches[0]
				: null
			: event;
	if (!pointer) return null;

	const rect = canvas.getBoundingClientRect();
	if (rect.width === 0 || rect.height === 0) return null;
	return {
		x: (pointer.clientX - rect.left) * (CANVAS_DISPLAY_WIDTH / rect.width),
		y: (pointer.clientY - rect.top) * (CANVAS_DISPLAY_HEIGHT / rect.height),
	};
}

export function HandwritingCanvas({ onSave, onClose }: HandwritingCanvasProps) {
	const canvasRef = useRef<HTMLCanvasElement>(null);
	const [isDrawing, setIsDrawing] = useState(false);
	const [lineWidth, setLineWidth] = useState(3);
	const shouldReduceMotion = useReducedMotion();
	const closeButtonRef = useRef<HTMLButtonElement>(null);
	useDialogAccessibility({
		isOpen: true,
		onClose,
		initialFocusRef: closeButtonRef,
	});

	useEffect(() => {
		const canvas = canvasRef.current;
		if (!canvas) return;
		const ctx = canvas.getContext("2d");
		if (!ctx) return;

		// Handle high-DPI displays (retina screens)
		const dpr = window.devicePixelRatio || 1;
		canvas.width = CANVAS_DISPLAY_WIDTH * dpr;
		canvas.height = CANVAS_DISPLAY_HEIGHT * dpr;

		ctx.scale(dpr, dpr);
		ctx.lineCap = "round";
		ctx.lineJoin = "round";

		const baseColor = getComputedStyle(canvas)
			.getPropertyValue("--color-text-primary")
			.trim();
		ctx.strokeStyle = baseColor || "oklch(26% 0.04 235)"; // Deep blue-gray ink
	}, []);

	const startDrawing = (
		e:
			| React.MouseEvent<HTMLCanvasElement>
			| React.TouchEvent<HTMLCanvasElement>,
	) => {
		const canvas = canvasRef.current;
		if (!canvas) return;
		const ctx = canvas.getContext("2d");
		if (!ctx) return;

		const point = getCanvasPoint(e, canvas);
		if (!point) return;
		ctx.beginPath();
		ctx.moveTo(point.x, point.y);
		ctx.lineWidth = lineWidth;
		ctx.lineCap = "round";
		ctx.lineJoin = "round";

		const baseColor = getComputedStyle(canvas)
			.getPropertyValue("--color-text-primary")
			.trim();
		ctx.strokeStyle = baseColor || "oklch(26% 0.04 235)";
		setIsDrawing(true);
	};

	const draw = (
		e:
			| React.MouseEvent<HTMLCanvasElement>
			| React.TouchEvent<HTMLCanvasElement>,
	) => {
		if (!isDrawing) return;
		const canvas = canvasRef.current;
		if (!canvas) return;
		const ctx = canvas.getContext("2d");
		if (!ctx) return;

		const point = getCanvasPoint(e, canvas);
		if (!point) return;
		ctx.lineTo(point.x, point.y);
		ctx.stroke();
	};

	const stopDrawing = () => {
		setIsDrawing(false);
	};

	const handleClear = () => {
		const canvas = canvasRef.current;
		if (!canvas) return;
		const ctx = canvas.getContext("2d");
		if (!ctx) return;
		const dpr = window.devicePixelRatio || 1;
		ctx.clearRect(0, 0, canvas.width / dpr, canvas.height / dpr);
	};

	const handleSave = () => {
		const canvas = canvasRef.current;
		if (!canvas) return;
		onSave(canvas.toDataURL("image/png"));
	};

	const backdropTransition = shouldReduceMotion
		? { duration: 0.12 }
		: motionTokens.lazy;
	const modalTransition = shouldReduceMotion
		? { duration: 0.12 }
		: motionTokens.editorial;

	return (
		<motion.div
			className="fixed inset-0 bg-[var(--color-overlay)] flex items-center justify-center z-[999999]"
			role="dialog"
			aria-labelledby="handwriting-canvas-title"
			aria-modal="true"
			initial={{ opacity: 0 }}
			animate={{ opacity: 1 }}
			exit={{ opacity: 0 }}
			transition={backdropTransition}
		>
			<motion.div
				className="bg-[var(--color-surface)] p-[var(--space-24)] rounded-[var(--radius-lg)] shadow-[var(--shadow-lg)] w-full max-w-lg flex flex-col gap-[var(--space-16)]"
				initial={
					shouldReduceMotion
						? { opacity: 0 }
						: { opacity: 0, scale: 0.96, y: 12 }
				}
				animate={{ opacity: 1, scale: 1, y: 0 }}
				exit={
					shouldReduceMotion
						? { opacity: 0 }
						: { opacity: 0, scale: 0.96, y: 12 }
				}
				transition={modalTransition}
			>
				<div className="flex justify-between items-center">
					<h3
						className="font-medium text-base text-[var(--color-text-primary)]"
						id="handwriting-canvas-title"
					>
						手写笔记/草图
					</h3>
					<button
						type="button"
						onClick={onClose}
						ref={closeButtonRef}
						className="text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)] transition-colors duration-[var(--duration-instant)] text-lg leading-none"
						aria-label="关闭"
					>
						×
					</button>
				</div>

				<canvas
					ref={canvasRef}
					style={{
						width: `min(100%, ${CANVAS_DISPLAY_WIDTH}px)`,
						height: "auto",
						aspectRatio: `${CANVAS_DISPLAY_WIDTH} / ${CANVAS_DISPLAY_HEIGHT}`,
					}}
					onMouseDown={startDrawing}
					onMouseMove={draw}
					onMouseUp={stopDrawing}
					onMouseLeave={stopDrawing}
					onTouchStart={startDrawing}
					onTouchMove={draw}
					onTouchEnd={stopDrawing}
					className="border border-[var(--color-border)] rounded-[var(--radius-sm)] bg-[var(--color-surface-inset)] cursor-crosshair touch-none shadow-inner"
				/>

				<div className="flex justify-between items-center gap-[var(--space-16)]">
					<div className="flex items-center gap-[var(--space-8)]">
						<span className="text-xs text-[var(--color-text-secondary)]">
							笔粗:
						</span>
						<input
							aria-label="笔粗"
							type="range"
							min="1"
							max="10"
							value={lineWidth}
							onChange={(e) => setLineWidth(Number(e.target.value))}
							className="h-1 bg-[var(--color-surface-inset)] rounded-lg appearance-none cursor-pointer accent-[var(--color-primary)] w-24"
						/>
						<span className="text-xs text-[var(--color-text-muted)] w-6 text-right">
							{lineWidth}px
						</span>
					</div>
					<div className="flex gap-[var(--space-8)]">
						<motion.button
							onClick={handleClear}
							className="px-[var(--space-16)] py-[var(--space-pill-padding)] rounded-full border border-[var(--color-border)] text-xs text-[var(--color-text-secondary)] hover:bg-[var(--color-hover-wash)] transition-colors"
							whileHover={shouldReduceMotion ? undefined : { scale: 1.02 }}
							whileTap={shouldReduceMotion ? undefined : { scale: 0.98 }}
						>
							清空
						</motion.button>
						<motion.button
							onClick={handleSave}
							className="px-[var(--space-16)] py-[var(--space-pill-padding)] rounded-full bg-[var(--gradient-coral)] text-[var(--color-text-inverse)] text-xs font-medium hover:opacity-95 shadow-sm"
							whileHover={shouldReduceMotion ? undefined : { scale: 1.02 }}
							whileTap={shouldReduceMotion ? undefined : { scale: 0.98 }}
						>
							确认导出
						</motion.button>
					</div>
				</div>
			</motion.div>
		</motion.div>
	);
}
