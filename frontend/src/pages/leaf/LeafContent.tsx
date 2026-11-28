import { BookOpen, FileText, LayoutDashboard, Play } from "lucide-react";
import { useEffect, useState } from "react";
import { MarkdownRenderer } from "../../components/markdown";
import { FeedbackState } from "../../components/ui/FeedbackState";
import { StatusBadge } from "../../components/ui/StatusBadge";
import type {
	LeafAnimationBlock,
	LeafComposedSection,
	LeafContentBlock,
	LeafSection,
	LeafSectionResourceError,
	LeafVideoBlock,
} from "../../types/leaf";
import {
	getLeafSectionDescription,
	getLeafSectionHeading,
	getLeafSectionLabel,
} from "./leafContentParser";

interface LeafContentProps {
	section: LeafSection | null;
	composedSection: LeafComposedSection | null;
	sectionResourceError: LeafSectionResourceError | null;
	lockedReason: string | null;
}

function escapeSvgText(value: string) {
	return value
		.replaceAll("&", "&amp;")
		.replaceAll("<", "&lt;")
		.replaceAll(">", "&gt;")
		.replaceAll('"', "&quot;")
		.replaceAll("'", "&apos;");
}

function buildFallbackVideoCoverDataUrl(title: string) {
	const safeTitle = title.trim() || "课程视频";
	const svg = [
		"<svg xmlns='http://www.w3.org/2000/svg' width='640' height='360' viewBox='0 0 640 360'>",
		"<rect width='640' height='360' fill='oklch(22% 0.04 220)'/>",
		"<circle cx='320' cy='150' r='54' fill='oklch(76% 0.12 55)' opacity='0.85'/>",
		"<polygon points='305,122 305,178 352,150' fill='oklch(96% 0.025 75)'/>",
		`<text x='320' y='255' text-anchor='middle' font-size='28' fill='oklch(92% 0.025 75)'>${escapeSvgText(safeTitle)}</text>`,
		"</svg>",
	].join("");
	return `data:image/svg+xml;utf8,${encodeURIComponent(svg)}`;
}

function VideoCard({ block, index }: { block: LeafVideoBlock; index: number }) {
	const firstVideo = block.videos[0] ?? null;
	const videoTitle = firstVideo?.title || block.title;
	const fallbackCoverSrc = buildFallbackVideoCoverDataUrl(videoTitle);
	const normalizedCoverUrl = firstVideo?.cover_url.trim() ?? "";
	const [coverSrc, setCoverSrc] = useState(
		normalizedCoverUrl || fallbackCoverSrc,
	);

	useEffect(() => {
		setCoverSrc(normalizedCoverUrl || fallbackCoverSrc);
	}, [fallbackCoverSrc, normalizedCoverUrl]);

	if (block.status !== "available" || !firstVideo?.url) {
		return (
			<section
				className="leaf-media-missing"
				key={`${block.brief_id}-${index}`}
			>
				<span className="leaf-media-kind">视频</span>
				<h3 className="leaf-media-title">{block.title}</h3>
				<p className="leaf-media-missing-purpose">{block.purpose}</p>
				<StatusBadge variant="pill" tone="error" showDot={false}>
					视频生成失败
				</StatusBadge>
			</section>
		);
	}

	return (
		<section className="leaf-video" key={`${block.brief_id}-${index}`}>
			<a
				href={firstVideo.url}
				target="_blank"
				rel="noreferrer"
				className="leaf-video-link"
			>
				<img
					src={coverSrc}
					alt={videoTitle}
					className="leaf-video-cover"
					onError={() => {
						if (coverSrc !== fallbackCoverSrc) {
							setCoverSrc(fallbackCoverSrc);
						}
					}}
				/>
				<span className="leaf-video-play" aria-hidden="true">
					<Play fill="currentColor" />
				</span>
				<span className="leaf-video-caption">
					<strong>{videoTitle}</strong>
					<span>
						<Play aria-hidden="true" /> 视频资源
					</span>
				</span>
			</a>
		</section>
	);
}

function renderVideo(block: LeafVideoBlock, index: number) {
	return (
		<VideoCard block={block} index={index} key={`${block.brief_id}-${index}`} />
	);
}

function renderAnimation(block: LeafAnimationBlock, index: number) {
	if (block.status !== "available" || !block.html.trim()) {
		return (
			<section
				className="leaf-media-missing"
				key={`${block.brief_id}-${index}`}
			>
				<span className="leaf-media-kind">动画</span>
				<h3 className="leaf-media-title">{block.title}</h3>
				<StatusBadge variant="pill" tone="error" showDot={false}>
					动画生成失败
				</StatusBadge>
			</section>
		);
	}

	return (
		<section className="leaf-animation" key={`${block.brief_id}-${index}`}>
			<header className="leaf-animation-head">
				<span className="leaf-media-kind">互动画布</span>
				<h3 className="leaf-media-title">{block.title}</h3>
			</header>
			<div className="leaf-animation-frame">
				<iframe
					title={block.title}
					sandbox="allow-scripts"
					srcDoc={block.html}
				/>
			</div>
		</section>
	);
}

function sanitizeMarkdown(markdown: string): string {
	if (!markdown) return "";

	// 1. Strip top-level H1 headings (e.g. # Title)
	let cleaned = markdown
		.trim()
		.replace(/^#\s+.*$/m, "")
		.trim();

	// 2. Remove consecutive duplicate subsection headings
	const lines = cleaned.split("\n");
	const resultLines: string[] = [];
	let lastHeading = "";

	for (let i = 0; i < lines.length; i++) {
		const line = lines[i].trim();
		const headingMatch = line.match(/^#{2,6}\s+(.+)$/);
		if (headingMatch) {
			const headingText = headingMatch[1].trim().replace(/[:：*_\s]+$/, "");
			if (headingText === lastHeading) {
				continue;
			}
			lastHeading = headingText;
		} else if (line !== "") {
			const cleanLine = line.replace(/^[*_\s#]+|[*_\s：:#]+$/g, "").trim();
			if (cleanLine === lastHeading) {
				continue;
			}
		}
		resultLines.push(lines[i]);
	}
	cleaned = resultLines.join("\n");

	// 3. Normalize step headings (e.g., remove Markdown heading symbols from steps)
	const stepPattern =
		/^(?:#{1,6}\s*)?(步骤讲解)?(第[一二三四五六七八九十\d]+步)\s*[：:]\s*(?:#{1,6}\s*)?(.*)$/;
	const finalLines = cleaned.split("\n").map((line) => {
		const trimmed = line.trim();
		const match = trimmed.match(stepPattern);
		if (match) {
			const stepLabel = match[2];
			const stepContent = match[3];
			return `${stepLabel}：${stepContent}`;
		}
		return line;
	});

	return finalLines.join("\n").trim();
}

function renderContentBlock(block: LeafContentBlock, index: number) {
	if (block.type === "markdown") {
		return (
			<div key={`markdown-${index}`}>
				<MarkdownRenderer
					content={sanitizeMarkdown(block.markdown)}
					enableMath={true}
					enableSyntaxHighlight={true}
					enableMermaid={true}
				/>
				{block.recommendation_reason && (
					<p className="leaf-recommendation-reason">
						{block.recommendation_reason}
					</p>
				)}
			</div>
		);
	}
	if (block.type === "video") return renderVideo(block, index);
	return renderAnimation(block, index);
}

export function LeafContent({
	section,
	composedSection,
	sectionResourceError,
	lockedReason,
}: LeafContentProps) {
	if (!section) {
		return (
			<FeedbackState
				variant="empty"
				title="课程章节还没有准备好"
				description={lockedReason ?? "章节结构生成后会显示在这里。"}
				icon={<LayoutDashboard aria-hidden="true" />}
			/>
		);
	}

	return (
		<article className="leaf-section">
			<header className="leaf-section-head">
				<p className="leaf-section-label">
					<BookOpen aria-hidden="true" />
					{getLeafSectionLabel(section.section_id)}
				</p>
				<h1>{getLeafSectionHeading(section)}</h1>
				<p className="leaf-section-description">
					{getLeafSectionDescription(section)}
				</p>
			</header>

			{sectionResourceError ? (
				<FeedbackState
					variant="error"
					title="这一节生成失败"
					description={sectionResourceError.message}
					icon={<FileText aria-hidden="true" />}
				/>
			) : composedSection ? (
				<div className="leaf-section-blocks">
					{composedSection.blocks.length > 0 ? (
						composedSection.blocks.map(renderContentBlock)
					) : (
						<MarkdownRenderer
							content={sanitizeMarkdown(composedSection.markdown)}
							enableMath={true}
							enableSyntaxHighlight={true}
							enableMermaid={true}
						/>
					)}
				</div>
			) : (
				<FeedbackState
					variant="empty"
					title="这一节还没有生成内容"
					description="可以从本章入口请 AI 生成 Markdown、视频资源和 HTML 动画。"
					icon={<FileText aria-hidden="true" />}
				/>
			)}
		</article>
	);
}
