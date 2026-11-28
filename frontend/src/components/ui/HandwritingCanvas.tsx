import { motion, useReducedMotion } from "framer-motion";
import { X } from "lucide-react";
import type React from "react";
import { useEffect, useRef, useState } from "react";
import { motionTokens } from "../../styles/motion-tokens";
import { Button } from "./Button";
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
			className="handwriting-backdrop"
			role="dialog"
			aria-labelledby="handwriting-canvas-title"
			aria-modal="true"
			initial={{ opacity: 0 }}
			animate={{ opacity: 1 }}
			exit={{ opacity: 0 }}
			transition={backdropTransition}
		>
			<motion.div
				className="handwriting-dialog"
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
				<div className="handwriting-head">
					<h3 id="handwriting-canvas-title">手写笔记/草图</h3>
					<button
						type="button"
						onClick={onClose}
						ref={closeButtonRef}
						className="ui-close-btn"
						aria-label="关闭"
					>
						<X aria-hidden="true" size={18} />
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
					className="handwriting-surface"
				/>

				<div className="handwriting-toolbar">
					<div className="handwriting-pen">
						<span>笔粗</span>
						<input
							aria-label="笔粗"
							type="range"
							min="1"
							max="10"
							value={lineWidth}
							onChange={(e) => setLineWidth(Number(e.target.value))}
							className="handwriting-range"
						/>
						<span className="handwriting-pen-value">{lineWidth}px</span>
					</div>
					<div className="handwriting-actions">
						<Button variant="secondary" size="sm" onClick={handleClear}>
							清空
						</Button>
						<Button size="sm" onClick={handleSave}>
							确认导出
						</Button>
					</div>
				</div>
			</motion.div>
		</motion.div>
	);
}
