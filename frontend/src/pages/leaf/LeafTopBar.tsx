import { ArrowLeft, PenTool, Sparkles } from "lucide-react";
import { useNavigate } from "react-router-dom";
import type {
	LeafCourse,
	LeafGenerationStatus,
	LeafSection,
} from "../../types/leaf";

interface LeafTopBarProps {
	course: LeafCourse;
	selectedSection: LeafSection | null;
	generationStatus: LeafGenerationStatus | null;
	liveGenerationMessage: string | null;
	canGenerate: boolean;
	onGenerate: () => void;
}

function courseStatusLabel(status: LeafCourse["status"]): string {
	switch (status) {
		case "completed":
			return "已完成";
		case "current":
			return "进行中";
		case "locked":
			return "未开放";
	}
}

export function LeafTopBar({
	course,
	selectedSection,
	generationStatus,
	liveGenerationMessage,
	canGenerate,
	onGenerate,
}: LeafTopBarProps) {
	const navigate = useNavigate();
	const statusMessage =
		liveGenerationMessage ?? generationStatus?.message ?? null;
	const isGenerationError = generationStatus?.status === "error";
	const generationLabel = isGenerationError ? "生成失败" : "生成中";
	const generationPillClass = isGenerationError
		? "bg-[var(--color-error-bg)] text-[var(--color-error)]"
		: "bg-[var(--color-info-bg)] text-[var(--color-secondary)]";
	const generationDotClass = isGenerationError
		? "bg-[var(--color-error)]"
		: "bg-[var(--color-success)]";
	const chapterId =
		selectedSection?.parent_section_id ?? selectedSection?.section_id ?? "1";

	return (
		<nav className="relative z-10 flex items-center justify-between gap-4 mb-12">
			<div className="flex items-center gap-3">
				<button
					type="button"
					className="group flex items-center gap-1.5 text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)]"
					onClick={() => navigate("/branch")}
				>
					<ArrowLeft className="w-4 h-4 group-hover:-translate-x-0.5 transition-[transform,opacity] duration-[var(--duration-lazy-hover)] ease-[var(--ease-lazy)]" />
					<span className="text-sm font-medium">返回路径</span>
				</button>
				<span className="text-[var(--color-border)] text-sm font-light">/</span>
				<h1 className="text-[var(--color-text-primary)] text-base font-medium tracking-normal truncate max-w-[200px] md:max-w-[400px]">
					{course.course_or_chapter_theme}
				</h1>
			</div>

			<div className="flex items-center flex-wrap gap-4 justify-end">
				{statusMessage ? (
					<div
						className={`flex items-center gap-2 px-3 py-1.5 rounded-full text-sm font-medium border border-[var(--glass-border)] shadow-[var(--shadow-sm)] ${generationPillClass}`}
						role="status"
					>
						<span className="relative flex h-2 w-2">
							{isGenerationError ? null : (
								<span
									className={`animate-ping absolute inline-flex h-full w-full rounded-full opacity-75 ${generationDotClass}`}
								/>
							)}
							<span
								className={`relative inline-flex rounded-full h-2 w-2 ${generationDotClass}`}
							/>
						</span>
						<span>{generationLabel}</span>
						<span>{statusMessage}</span>
					</div>
				) : (
					<div className="flex items-center gap-2 text-sm font-medium text-[var(--color-text-secondary)]">
						{course.status === "current" && (
							<span className="relative flex h-2 w-2">
								<span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-[var(--color-warning)] opacity-75" />
								<span className="relative inline-flex rounded-full h-2 w-2 bg-[var(--color-warning)]" />
							</span>
						)}
						<span className="text-[var(--color-text-primary)] font-medium">
							{courseStatusLabel(course.status)}
						</span>
					</div>
				)}

				<div
					className="h-4 w-px bg-[var(--color-border)] opacity-60 mx-1"
					aria-hidden="true"
				/>

				<button
					type="button"
					className="group flex items-center gap-1.5 px-4 py-1.5 rounded-full bg-[var(--glass-bg)] hover:bg-[var(--color-surface)] text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] text-xs font-medium border border-[var(--glass-border)] hover:border-[var(--color-primary-soft)] hover:-translate-y-[1px] transition-[transform,opacity] duration-[var(--duration-lazy-hover)] ease-[var(--ease-lazy)] backdrop-blur-sm"
					onClick={() =>
						navigate(
							`/forest/${encodeURIComponent(course.course_node_id)}?chapter_id=${encodeURIComponent(chapterId)}`,
						)
					}
				>
					<PenTool className="w-3.5 h-3.5 transition-colors" />
					<span>章节测验</span>
				</button>

				{canGenerate ? (
					<button
						type="button"
						className="group relative flex items-center gap-1.5 px-5 py-1.5 rounded-full overflow-hidden shadow-[var(--shadow-sm)] hover:shadow-[var(--shadow-md)] hover:-translate-y-[1px] active:translate-y-0 transition-[transform,opacity] duration-[var(--duration-lazy-hover)] ease-[var(--ease-lazy)] bg-[var(--gradient-coral)] text-[var(--color-text-inverse)]"
						onClick={onGenerate}
					>
						<div className="absolute inset-0 bg-[var(--color-hover-wash)] opacity-0 group-hover:opacity-20 transition-opacity duration-[var(--duration-lazy-hover)]" />
						<div className="relative flex items-center gap-1.5 text-xs font-medium tracking-normal">
							<Sparkles className="w-3.5 h-3.5 animate-pulse" />
							<span>让 AI 生成本章内容</span>
						</div>
					</button>
				) : null}
			</div>
		</nav>
	);
}
