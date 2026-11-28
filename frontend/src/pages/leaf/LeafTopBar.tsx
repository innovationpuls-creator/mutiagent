import { ArrowLeft, PenLine, PenTool } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { Button } from "../../components/ui/Button";
import {
	StatusBadge,
	type StatusBadgeTone,
} from "../../components/ui/StatusBadge";
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
	sectionResourceRetryable: boolean;
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

function courseStatusTone(status: LeafCourse["status"]): StatusBadgeTone {
	switch (status) {
		case "completed":
			return "success";
		case "current":
			return "warning";
		case "locked":
			return "neutral";
	}
}

function PingDot({ className }: { className: string }) {
	return (
		<span className="relative flex h-2 w-2" aria-hidden="true">
			<span
				className={`animate-ping absolute inline-flex h-full w-full rounded-full opacity-75 ${className}`}
			/>
			<span
				className={`relative inline-flex rounded-full h-2 w-2 ${className}`}
			/>
		</span>
	);
}

export function LeafTopBar({
	course,
	selectedSection,
	generationStatus,
	liveGenerationMessage,
	sectionResourceRetryable,
	canGenerate,
	onGenerate,
}: LeafTopBarProps) {
	const navigate = useNavigate();
	const statusMessage =
		liveGenerationMessage ?? generationStatus?.message ?? null;
	const isGenerationError = generationStatus?.status === "error";
	const generationLabel = isGenerationError ? "生成失败" : "生成中";
	const chapterId =
		selectedSection?.parent_section_id ?? selectedSection?.section_id ?? "1";

	return (
		<nav className="relative z-10 flex items-center justify-between gap-4 mb-12">
			<div className="flex items-center gap-3">
				<Button
					variant="ghost"
					size="sm"
					icon={<ArrowLeft aria-hidden="true" />}
					onClick={() => navigate("/branch")}
				>
					返回路径
				</Button>
				<span className="leaf-topbar-sep" aria-hidden="true">
					/
				</span>
				<h1 className="leaf-topbar-title">{course.course_or_chapter_theme}</h1>
			</div>

			<div className="flex items-center flex-wrap gap-4 justify-end">
				{statusMessage ? (
					<div role="status">
						<StatusBadge
							variant="pill"
							tone={isGenerationError ? "error" : "info"}
							showDot={false}
						>
							<span className="inline-flex items-center gap-2">
								{isGenerationError ? (
									<span
										className="leaf-status-dot leaf-status-dot-error"
										aria-hidden="true"
									/>
								) : (
									<PingDot className="leaf-status-dot-success" />
								)}
								<span>{generationLabel}</span>
								<span>{statusMessage}</span>
							</span>
						</StatusBadge>
					</div>
				) : (
					<StatusBadge
						tone={courseStatusTone(course.status)}
						showDot={course.status !== "current"}
					>
						<span className="inline-flex items-center gap-2">
							{course.status === "current" ? (
								<PingDot className="leaf-status-dot-warning" />
							) : null}
							<span>{courseStatusLabel(course.status)}</span>
						</span>
					</StatusBadge>
				)}

				<div className="leaf-topbar-divider" aria-hidden="true" />

				<Button
					variant="secondary"
					size="sm"
					icon={<PenTool aria-hidden="true" />}
					onClick={() =>
						navigate(
							`/forest/${encodeURIComponent(course.course_node_id)}?chapter_id=${encodeURIComponent(chapterId)}`,
						)
					}
				>
					章节测验
				</Button>

				{canGenerate ? (
					<Button
						variant="primary"
						size="sm"
						icon={<PenLine aria-hidden="true" />}
						onClick={onGenerate}
					>
						{sectionResourceRetryable ? "重试当前章节" : "让 AI 生成本章内容"}
					</Button>
				) : null}
			</div>
		</nav>
	);
}
