import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import {
	Check,
	ChevronDown,
	ChevronRight,
	ListTree,
	Lock,
	PanelLeftClose,
} from "lucide-react";
import { motionTokens } from "../../styles/motion-tokens";
import type { LeafCourseResponse, LeafSection } from "../../types/leaf";
import {
	getLeafChildSections,
	getLeafSectionHeading,
	hasLeafComposedContent,
} from "./leafContentParser";

const MARKMAP_COLLAPSED_STORAGE_KEY = "mutiagent-leaf-markmap-collapsed";
const SECTION_COLLAPSED_STORAGE_KEY =
	"mutiagent-leaf-markmap-section-collapsed";

function readCollapsedSections(): Set<string> {
	try {
		const rawValue = localStorage.getItem(SECTION_COLLAPSED_STORAGE_KEY);
		if (!rawValue) return new Set();
		const parsedValue = JSON.parse(rawValue) as unknown;
		if (!Array.isArray(parsedValue)) return new Set();
		return new Set(
			parsedValue.filter((item): item is string => typeof item === "string"),
		);
	} catch {
		return new Set();
	}
}

function writeCollapsedSections(collapsedSectionIds: Set<string>) {
	localStorage.setItem(
		SECTION_COLLAPSED_STORAGE_KEY,
		JSON.stringify([...collapsedSectionIds]),
	);
}

function readMarkmapCollapsed(): boolean {
	return localStorage.getItem(MARKMAP_COLLAPSED_STORAGE_KEY) === "true";
}

function writeMarkmapCollapsed(collapsed: boolean) {
	localStorage.setItem(MARKMAP_COLLAPSED_STORAGE_KEY, String(collapsed));
}

interface LeafMarkmapProps {
	response: LeafCourseResponse;
	selectedSectionId: string | null;
	markmapCollapsed: boolean;
	collapsedSectionIds: Set<string>;
	onToggleMarkmapCollapsed: () => void;
	onCollapsedSectionIdsChange: (collapsedSectionIds: Set<string>) => void;
	onSelectSection: (sectionId: string) => void;
	onGenerateOutline: () => void;
}

interface LeafMarkmapNodeProps {
	response: LeafCourseResponse;
	section: LeafSection;
	depth: number;
	selectedSectionId: string | null;
	collapsedSectionIds: Set<string>;
	onCollapsedSectionIdsChange: (collapsedSectionIds: Set<string>) => void;
	onSelectSection: (sectionId: string) => void;
}

export function createInitialCollapsedLeafSections(): Set<string> {
	return readCollapsedSections();
}

export function createInitialLeafMarkmapCollapsed(): boolean {
	return readMarkmapCollapsed();
}

export function persistLeafMarkmapCollapsed(collapsed: boolean) {
	writeMarkmapCollapsed(collapsed);
}

function toggleCollapsedSection(
	sectionId: string,
	collapsedSectionIds: Set<string>,
	onCollapsedSectionIdsChange: (collapsedSectionIds: Set<string>) => void,
) {
	const nextCollapsedSectionIds = new Set(collapsedSectionIds);
	if (nextCollapsedSectionIds.has(sectionId)) {
		nextCollapsedSectionIds.delete(sectionId);
	} else {
		nextCollapsedSectionIds.add(sectionId);
	}
	writeCollapsedSections(nextCollapsedSectionIds);
	onCollapsedSectionIdsChange(nextCollapsedSectionIds);
}

function LeafMarkmapNode({
	response,
	section,
	depth,
	selectedSectionId,
	collapsedSectionIds,
	onCollapsedSectionIdsChange,
	onSelectSection,
}: LeafMarkmapNodeProps) {
	const childSections = getLeafChildSections(
		response.sections,
		section.section_id,
	);
	const isCollapsed = collapsedSectionIds.has(section.section_id);
	const hasChildren = childSections.length > 0;

	// Determine status
	let status: "running" | "completed" | "waiting" | "neutral" = "neutral";
	if (section.section_id === selectedSectionId) {
		status = "running";
	} else if (hasLeafComposedContent(response, section.section_id)) {
		status = "completed";
	} else if (response.first_generatable_chapter_id === section.section_id) {
		status = "waiting";
	}

	// Determine content media types of the section (micro-badges)
	const composed = response.section_composed_markdowns[section.section_id];
	const badges: string[] = [];
	if (composed) {
		const hasVideo = composed.blocks.some((b) => b.type === "video");
		const hasAnimation = composed.blocks.some((b) => b.type === "animation");
		const hasMarkdown =
			composed.blocks.some((b) => b.type === "markdown") ||
			(composed.markdown && composed.markdown.trim().length > 0);

		if (hasVideo) {
			badges.push("//");
		}
		if (hasAnimation) {
			badges.push("*");
		}
		if (!hasVideo && !hasAnimation && hasMarkdown) {
			badges.push("+");
		}
	}

	return (
		<div className="leaf-markmap-journey-node" data-depth={depth}>
			<div className="leaf-markmap-journey-row">
				<span className="leaf-markmap-journey-connector" aria-hidden="true" />
				<div
					className={`leaf-markmap-card ${status === "running" ? "running" : ""}`}
					data-status={status}
					onClick={() => onSelectSection(section.section_id)}
				>
					<div className="leaf-markmap-card-main">
						<div className="leaf-markmap-status-dot">
							{status === "running" && (
								<span className="leaf-markmap-status-core leaf-markmap-status-core-running" />
							)}
							{status === "completed" && (
								<div className="leaf-markmap-status-completed">
									<Check className="leaf-markmap-status-check" />
								</div>
							)}
							{status === "waiting" && (
								<span className="leaf-markmap-status-core leaf-markmap-status-core-waiting" />
							)}
							{status === "neutral" && (
								<span className="leaf-markmap-status-core leaf-markmap-status-core-neutral" />
							)}
						</div>

						<span
							className={`leaf-markmap-title ${
								status === "running"
									? "leaf-markmap-title-running"
									: "leaf-markmap-title-muted"
							}`}
						>
							{getLeafSectionHeading(section)}
						</span>

						{badges.length > 0 && (
							<div className="leaf-markmap-badges">
								{badges.map((badge, i) => (
									<span key={i} className="leaf-markmap-badge">
										{badge}
									</span>
								))}
							</div>
						)}
					</div>

					{hasChildren && (
						<button
							type="button"
							className="leaf-markmap-child-toggle"
							onClick={(e) => {
								e.stopPropagation();
								toggleCollapsedSection(
									section.section_id,
									collapsedSectionIds,
									onCollapsedSectionIdsChange,
								);
							}}
						>
							{isCollapsed ? (
								<ChevronRight className="leaf-markmap-child-toggle-icon" />
							) : (
								<ChevronDown className="leaf-markmap-child-toggle-icon" />
							)}
						</button>
					)}
				</div>
			</div>

			{hasChildren && !isCollapsed && (
				<div className="leaf-markmap-journey-children">
					{childSections.map((childSection, index) => {
						const isLast = index === childSections.length - 1;
						return (
							<div
								className="leaf-markmap-journey-child"
								data-last={isLast}
								key={childSection.section_id}
							>
								<span
									className="leaf-markmap-journey-line"
									aria-hidden="true"
								/>
								<LeafMarkmapNode
									response={response}
									section={childSection}
									depth={depth + 1}
									selectedSectionId={selectedSectionId}
									collapsedSectionIds={collapsedSectionIds}
									onCollapsedSectionIdsChange={onCollapsedSectionIdsChange}
									onSelectSection={onSelectSection}
								/>
							</div>
						);
					})}
				</div>
			)}
		</div>
	);
}

export function LeafMarkmap({
	response,
	selectedSectionId,
	collapsedSectionIds,
	onToggleMarkmapCollapsed,
	onCollapsedSectionIdsChange,
	onSelectSection,
	onGenerateOutline,
}: LeafMarkmapProps) {
	const topLevelSections = getLeafChildSections(response.sections, null);
	const reduceMotion = useReducedMotion();

	return (
		<motion.aside
			initial={reduceMotion ? false : { opacity: 0, x: -40 }}
			animate={reduceMotion ? undefined : { opacity: 1, x: 0 }}
			exit={reduceMotion ? undefined : { opacity: 0, x: -40 }}
			transition={motionTokens.editorial}
			className="leaf-floating-markmap"
		>
			<div className="leaf-floating-markmap-head">
				<div className="leaf-floating-markmap-title-block">
					<h2>{response.course.course_or_chapter_theme}</h2>
					<p>章节导航</p>
				</div>
				<button
					aria-label="收起章节导航"
					type="button"
					className="leaf-floating-markmap-close"
					onClick={onToggleMarkmapCollapsed}
				>
					<PanelLeftClose className="leaf-floating-markmap-close-icon" />
				</button>
			</div>

			<AnimatePresence initial={false}>
				{!response.course.has_outline && (
					<motion.button
						key="outline-draft-button"
						type="button"
						className="leaf-outline-draft-button"
						initial={reduceMotion ? false : { opacity: 0, y: -8 }}
						animate={reduceMotion ? undefined : { opacity: 1, y: 0 }}
						exit={reduceMotion ? undefined : { opacity: 0, y: -8 }}
						transition={motionTokens.editorial}
						onClick={onGenerateOutline}
					>
						<ListTree className="w-4 h-4" />
						<span>生成课程大纲</span>
					</motion.button>
				)}
			</AnimatePresence>

			<div className="leaf-floating-markmap-scroll custom-scrollbar">
				{topLevelSections.length > 0 ? (
					<div className="leaf-markmap-journey">
						<div className="leaf-markmap-journey-root">
							<ListTree className="leaf-markmap-journey-root-icon" />
							<span>Course Structure</span>
						</div>

						<div className="leaf-markmap-journey-list">
							{topLevelSections.map((section, index) => {
								const isLast = index === topLevelSections.length - 1;
								return (
									<div
										className="leaf-markmap-journey-child"
										data-last={isLast}
										key={section.section_id}
									>
										<span
											className="leaf-markmap-journey-line"
											aria-hidden="true"
										/>
										<LeafMarkmapNode
											response={response}
											section={section}
											depth={1}
											selectedSectionId={selectedSectionId}
											collapsedSectionIds={collapsedSectionIds}
											onCollapsedSectionIdsChange={onCollapsedSectionIdsChange}
											onSelectSection={onSelectSection}
										/>
									</div>
								);
							})}
						</div>

						{response.locked_reason && (
							<div className="leaf-markmap-locked">
								<div>
									<Lock className="leaf-markmap-locked-icon" />
									<span>未开放</span>
								</div>
							</div>
						)}
					</div>
				) : (
					<p className="leaf-markmap-empty">课程章节还在整理中。</p>
				)}
			</div>
		</motion.aside>
	);
}
