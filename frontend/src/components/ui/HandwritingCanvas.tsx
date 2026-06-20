import { motion, useReducedMotion } from "framer-motion";
import type React from "react";
import { useEffect, useRef, useState } from "react";
import { motionTokens } from "../../styles/motion-tokens";

interface HandwritingCanvasProps {
	onSave: (base64Data: string) => void;
	onClose: () => void;
}

export function HandwritingCanvas({ onSave, onClose }: HandwritingCanvasProps) {
	const canvasRef = useRef<HTMLCanvasElement>(null);
	const [isDrawing, setIsDrawing] = useState(false);
	const [lineWidth, setLineWidth] = useState(3);
	const shouldReduceMotion = useReducedMotion();

	useEffect(() => {
		const canvas = canvasRef.current;
		if (!canvas) return;
		const ctx = canvas.getContext("2d");
		if (!ctx) return;

		// Handle high-DPI displays (retina screens)
		const dpr = window.devicePixelRatio || 1;
		const displayWidth = 480;
		const displayHeight = 320;

		canvas.width = displayWidth * dpr;
		canvas.height = displayHeight * dpr;

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

		let clientX, clientY;
		if ("touches" in e) {
			if (e.touches.length === 0) return;
			clientX = e.touches[0].clientX;
			clientY = e.touches[0].clientY;
		} else {
			clientX = e.clientX;
			clientY = e.clientY;
		}

		const rect = canvas.getBoundingClientRect();
		ctx.beginPath();
		ctx.moveTo(clientX - rect.left, clientY - rect.top);
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

		let clientX, clientY;
		if ("touches" in e) {
			if (e.touches.length === 0) return;
			clientX = e.touches[0].clientX;
			clientY = e.touches[0].clientY;
		} else {
			clientX = e.clientX;
			clientY = e.clientY;
		}

		const rect = canvas.getBoundingClientRect();
		ctx.lineTo(clientX - rect.left, clientY - rect.top);
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
					<h3 className="font-medium text-base text-[var(--color-text-primary)]">
						手写笔记/草图
					</h3>
					<button
						onClick={onClose}
						className="text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)] transition-colors duration-[var(--duration-instant)] text-lg leading-none"
						aria-label="关闭"
					>
						×
					</button>
				</div>

				<canvas
					ref={canvasRef}
					style={{ width: "480px", height: "320px" }}
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
