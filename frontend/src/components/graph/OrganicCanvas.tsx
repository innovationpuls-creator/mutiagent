import dagre from "dagre";
import { motion } from "framer-motion";
import React, { useEffect, useMemo, useRef, useState } from "react";
import BezierEdge from "./BezierEdge";
import { NodeCard, type NodeStatus } from "./NodeCard";
import "../../styles/organic-canvas.css";

export interface GraphNode {
	id: string;
	title: string;
	status: NodeStatus;
	agentMessage?: string;
	completedConcepts: number;
	totalConcepts: number;
}

export interface GraphEdge {
	id: string;
	source: string;
	target: string;
	status: NodeStatus | "future";
}

interface OrganicCanvasProps {
	nodes: GraphNode[];
	edges: GraphEdge[];
}

interface NodeSize {
	width: number;
	height: number;
}

interface LayoutNode extends GraphNode {
	x: number;
	y: number;
	width: number;
	height: number;
}

export function OrganicCanvas({ nodes, edges }: OrganicCanvasProps) {
	// 1. First Pass: Store actual DOM sizes reported by ResizeObserver
	const [nodeSizes, setNodeSizes] = useState<Record<string, NodeSize>>({});
	const nodeRefs = useRef<Record<string, HTMLDivElement | null>>({});

	// Setup ResizeObserver to catch any size changes (like Agent expanding text)
	useEffect(() => {
		const observer = new ResizeObserver((entries) => {
			let changed = false;
			const newSizes = { ...nodeSizes };

			entries.forEach((entry) => {
				const id = (entry.target as HTMLElement).dataset.nodeId;
				if (id) {
					const width =
						entry.borderBoxSize[0]?.inlineSize ?? entry.contentRect.width;
					const height =
						entry.borderBoxSize[0]?.blockSize ?? entry.contentRect.height;

					if (
						newSizes[id]?.width !== width ||
						newSizes[id]?.height !== height
					) {
						newSizes[id] = { width, height };
						changed = true;
					}
				}
			});

			if (changed) {
				setNodeSizes(newSizes);
			}
		});

		Object.values(nodeRefs.current).forEach((node) => {
			if (node) observer.observe(node);
		});

		return () => observer.disconnect();
	}, [nodes]); // Re-bind observer if node list changes

	// 2. Second Pass: Run Dagre Layout when we have sizes for all nodes
	const layout = useMemo(() => {
		// Wait until all nodes have reported their physical dimensions
		if (nodes.some((n) => !nodeSizes[n.id])) return null;

		const g = new dagre.graphlib.Graph();
		g.setGraph({ rankdir: "LR", nodesep: 60, ranksep: 120, align: "UL" });
		g.setDefaultEdgeLabel(() => ({}));

		nodes.forEach((node) => {
			const size = nodeSizes[node.id];
			// Dagre uses center-based coordinates by default
			g.setNode(node.id, { width: size.width, height: size.height });
		});

		edges.forEach((edge) => {
			g.setEdge(edge.source, edge.target);
		});

		dagre.layout(g);

		const layoutNodes = nodes.map((node) => {
			const { x, y, width, height } = g.node(node.id);
			return { ...node, x, y, width, height };
		});

		return { layoutNodes, layoutEdges: edges };
	}, [nodes, edges, nodeSizes]);

	return (
		<div className="organic-canvas-root">
			{/* Underlying SVG Layer for Edges - pointer-events: none is in CSS */}
			<svg className="organic-svg-layer">
				<defs>
					{/* Subtle Glow Filter for Active Paths */}
					<filter id="glow" x="-20%" y="-20%" width="140%" height="140%">
						<feGaussianBlur stdDeviation="4" result="blur" />
						<feComposite in="SourceGraphic" in2="blur" operator="over" />
					</filter>
				</defs>

				{layout &&
					layout.layoutEdges.map((edge) => {
						const sourceNode = layout.layoutNodes.find(
							(n) => n.id === edge.source,
						);
						const targetNode = layout.layoutNodes.find(
							(n) => n.id === edge.target,
						);
						if (!sourceNode || !targetNode) return null;

						// Anchor Offset Check: Strictly calculate right edge and left edge
						const startX = sourceNode.x + sourceNode.width / 2;
						const startY = sourceNode.y;
						const endX = targetNode.x - targetNode.width / 2;
						const endY = targetNode.y;

						return (
							<BezierEdge
								key={edge.id}
								id={edge.id}
								startX={startX}
								startY={startY}
								endX={endX}
								endY={endY}
								status={edge.status}
							/>
						);
					})}
			</svg>

			{/* Foreground Layer for Nodes */}
			<div className="organic-nodes-layer">
				{nodes.map((node) => {
					const layoutNode = layout?.layoutNodes.find((n) => n.id === node.id);

					return (
						<motion.div
							key={node.id}
							className="node-wrapper"
							data-node-id={node.id}
							ref={(el) => {
								nodeRefs.current[node.id] = el;
							}}
							animate={
								layoutNode
									? {
											x: layoutNode.x - layoutNode.width / 2,
											y: layoutNode.y - layoutNode.height / 2,
											opacity: 1,
										}
									: { opacity: 0 }
							} // Hidden until measured and calculated
							transition={{ duration: 0.6, ease: [0.4, 0, 0.2, 1] }} // Smooth Framer Motion Tween
							style={{
								// Prevent jumping on first mount
								position: "absolute",
								top: 0,
								left: 0,
								opacity: 0,
							}}
						>
							<NodeCard {...node} />
						</motion.div>
					);
				})}
			</div>
		</div>
	);
}
