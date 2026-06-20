import { motion } from "framer-motion";
import React, { memo } from "react";
import "../../styles/organic-canvas.css";
import type { NodeStatus } from "./NodeCard";

interface BezierEdgeProps {
	id: string;
	startX: number;
	startY: number;
	endX: number;
	endY: number;
	status: NodeStatus | "future";
}

const BezierEdge = memo(function BezierEdge({
	id,
	startX,
	startY,
	endX,
	endY,
	status,
}: BezierEdgeProps) {
	// Delta X * 0.5 tension ensures smooth organic curves
	const deltaX = Math.abs(endX - startX);
	const tension = deltaX * 0.5;
	const d = `M ${startX} ${startY} C ${startX + tension} ${startY}, ${endX - tension} ${endY}, ${endX} ${endY}`;

	return (
		<g className={`edge-group edge-${status}`}>
			{/* Background invisible path for easier hit detection if needed later */}
			<path d={d} fill="none" stroke="transparent" strokeWidth={20} />

			{/* Visible Path */}
			<motion.path
				d={d}
				fill="none"
				className="bezier-path"
				initial={{ pathLength: 0 }}
				animate={{ pathLength: 1, d }}
				transition={{ duration: 0.8, ease: "easeOut" }}
			/>

			{/* Active Pulse Effect */}
			{status === "in-progress" && (
				<motion.path
					d={d}
					fill="none"
					className="bezier-pulse"
					animate={{ strokeDashoffset: [100, 0] }}
					transition={{ duration: 3, repeat: Infinity, ease: "linear" }}
				/>
			)}
		</g>
	);
});

export default BezierEdge;
