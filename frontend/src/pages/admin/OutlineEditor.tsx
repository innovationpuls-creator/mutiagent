import {
	Check,
	Loader2,
	Save,
} from "lucide-react";
import { useEffect, useState } from "react";
import type { Textbook, TextbookSectionContent } from "../../api/knowledgeBase";
import { MarkdownRenderer } from "../../components/markdown";

interface OutlineSection {
	section_id: string;
	title: string;
	description?: string;
	key_knowledge_points?: string[];
}

interface OutlineChapter {
	chapter_id?: string;
	chapter_number: number;
	title: string;
	description?: string;
	sections: OutlineSection[];
}

interface OutlineData {
	chapters: OutlineChapter[];
}

interface OutlineEditorProps {
	textbook: Textbook;
	sections: TextbookSectionContent[];
	onSave: (updatedOutline: OutlineData) => Promise<void>;
}

export function OutlineEditor({ textbook, sections, onSave }: OutlineEditorProps) {
	const [outline, setOutline] = useState<OutlineData>({ chapters: [] });
	const [selectedSectionId, setSelectedSectionId] = useState<string | null>(null);
	const [isSaving, setIsSaving] = useState(false);
	const [saveSuccess, setSaveSuccess] = useState(false);
	const [error, setError] = useState<string | null>(null);

	// Sync local state when textbook changes
	useEffect(() => {
		if (textbook.outline && typeof textbook.outline === "object") {
			const rawOutline = textbook.outline as Record<string, unknown>;
			if (Array.isArray(rawOutline.chapters)) {
				setOutline(rawOutline as unknown as OutlineData);
			} else if (Array.isArray(rawOutline.sections)) {
				// Convert flat sections to chapter structure if needed
				const chaptersMap = new Map<string, OutlineChapter>();
				const sectionsList = rawOutline.sections as {
					depth?: number;
					parent_section_id?: string | null;
					section_id: string;
					title: string;
					description?: string;
					key_knowledge_points?: string[];
				}[];
				for (const sec of sectionsList) {
					if (sec.depth === 1 || !sec.parent_section_id) {
						const chNum = Number.parseInt(sec.section_id, 10) || 1;
						chaptersMap.set(sec.section_id, {
							chapter_id: sec.section_id,
							chapter_number: chNum,
							title: sec.title,
							description: sec.description || "",
							sections: [],
						});
					}
				}
				for (const sec of sectionsList) {
					if (sec.depth === 2 && sec.parent_section_id) {
						const ch = chaptersMap.get(sec.parent_section_id);
						if (ch) {
							ch.sections.push({
								section_id: sec.section_id,
								title: sec.title,
								description: sec.description || "",
								key_knowledge_points: sec.key_knowledge_points || [],
							});
						}
					}
				}
				setOutline({ chapters: Array.from(chaptersMap.values()) });
			} else {
				setOutline({ chapters: [] });
			}
		} else {
			setOutline({ chapters: [] });
		}
		setError(null);
		setSaveSuccess(false);
	}, [textbook]);

	// Auto select first section on outline load
	useEffect(() => {
		if (outline.chapters.length > 0) {
			const firstChapter = outline.chapters[0];
			if (firstChapter.sections && firstChapter.sections.length > 0) {
				setSelectedSectionId(firstChapter.sections[0].section_id);
				return;
			}
			setSelectedSectionId(firstChapter.chapter_id || String(firstChapter.chapter_number));
			return;
		}
		setSelectedSectionId(null);
	}, [outline]);

	const handleChapterChange = (
		chapterIndex: number,
		field: keyof OutlineChapter,
		value: string,
	) => {
		const updatedChapters = [...outline.chapters];
		updatedChapters[chapterIndex] = {
			...updatedChapters[chapterIndex],
			[field]: value,
		} as OutlineChapter;
		setOutline({ chapters: updatedChapters });
	};

	const handleSectionChange = (
		chapterIndex: number,
		sectionIndex: number,
		field: keyof OutlineSection,
		value: string,
	) => {
		const updatedChapters = [...outline.chapters];
		const updatedSections = [...updatedChapters[chapterIndex].sections];
		updatedSections[sectionIndex] = {
			...updatedSections[sectionIndex],
			[field]: value,
		} as OutlineSection;
		updatedChapters[chapterIndex] = {
			...updatedChapters[chapterIndex],
			sections: updatedSections,
		};
		setOutline({ chapters: updatedChapters });
	};

	const handleSave = async () => {
		// Validations
		for (const ch of outline.chapters) {
			if (!ch.title.trim()) {
				setError("章节标题不能为空");
				return;
			}
			for (const sec of ch.sections) {
				if (!sec.title.trim()) {
					setError(`章节「${ch.title}」下的子小节标题不能为空`);
					return;
				}
			}
		}

		setIsSaving(true);
		setError(null);
		setSaveSuccess(false);
		try {
			await onSave(outline);
			setSaveSuccess(true);
			setTimeout(() => setSaveSuccess(false), 3000);
		} catch (err) {
			setError(err instanceof Error ? err.message : "保存大纲失败");
		} finally {
			setIsSaving(false);
		}
	};

	return (
		<div className="outline-editor-container">
			<div className="outline-editor-workspace">
				{/* Left column: Outline list */}
				<div className="outline-tree-panel">
					<div className="outline-tree-header">
						<h3>章节目录</h3>
					</div>

					<div className="outline-chapters-list">
						{outline.chapters.map((chapter, chIdx) => (
							<div
								key={chapter.chapter_number}
								className="outline-chapter-card"
							>
								<div
									className={`outline-chapter-header clickable ${selectedSectionId === (chapter.chapter_id || String(chapter.chapter_number)) ? "is-active" : ""}`}
									onClick={() => setSelectedSectionId(chapter.chapter_id || String(chapter.chapter_number))}
									style={{ cursor: "pointer", borderRadius: "var(--radius-sm)", padding: "var(--space-4) var(--space-8)" }}
								>
									<div className="chapter-info">
										<span className="chapter-tag">
											Chapter {chapter.chapter_number}
										</span>
										<input
											type="text"
											className="chapter-title-input"
											value={chapter.title}
											onChange={(e) =>
												handleChapterChange(chIdx, "title", e.target.value)
											}
											onClick={(e) => e.stopPropagation()}
										/>
									</div>
								</div>

								<div className="outline-sections-list">
									{chapter.sections.map((section, secIdx) => {
										const isSelected = section.section_id === selectedSectionId;
										return (
											<div
												key={section.section_id}
												className={`outline-section-row clickable ${isSelected ? "is-active" : ""}`}
												onClick={() => setSelectedSectionId(section.section_id)}
												style={{ cursor: "pointer" }}
											>
												<span className="section-id-tag">
													{section.section_id}
												</span>
												<input
													type="text"
													className="section-title-input"
													value={section.title}
													onChange={(e) =>
														handleSectionChange(
															chIdx,
															secIdx,
															"title",
															e.target.value,
														)
													}
													onClick={(e) => e.stopPropagation()}
												/>
											</div>
										);
									})}
								</div>
							</div>
						))}

						{outline.chapters.length === 0 && (
							<div className="empty-outline-state">
								<p>当前教材暂无大纲，可在来源整理后手动补齐。</p>
							</div>
						)}
					</div>

					<div className="outline-tree-footer">
						{error && <p className="editor-error-msg">{error}</p>}
						<button
							type="button"
							className="admin-primary-action save-outline-btn"
							onClick={handleSave}
							disabled={isSaving}
						>
							{isSaving ? (
								<Loader2 className="spinner" size={16} />
							) : saveSuccess ? (
								<Check size={16} />
							) : (
								<Save size={16} />
							)}
							<span>
								{isSaving
									? "正在保存..."
									: saveSuccess
										? "已成功保存"
										: "保存大纲配置"}
							</span>
						</button>
					</div>
				</div>

				{/* Right column: Section content preview */}
				<article className="admin-kb-section-preview outline-preview-panel">
					{selectedSectionId ? (
						(() => {
							const activeSectionContent = sections.find(
								(sec) => sec.section_id === selectedSectionId,
							);
							const activeSectionOutline = outline.chapters
								.flatMap((ch) => [
									{ section_id: ch.chapter_id || String(ch.chapter_number), title: ch.title },
									...ch.sections,
								])
								.find((sec) => sec.section_id === selectedSectionId);

							const titleText = activeSectionOutline?.title || "未命名小节";
							const contentText = activeSectionContent
								? (activeSectionContent.content_zh || activeSectionContent.content_original || "").trim()
								: "";

							return (
								<>
									<div className="admin-kb-section-preview-head">
										<div>
											<span>章节正文 ({selectedSectionId})</span>
											<h6>{titleText}</h6>
										</div>
										<strong>
											{contentText ? `${contentText.length} 字` : "无正文"}
										</strong>
									</div>
									{contentText ? (
										<MarkdownRenderer
											content={contentText}
											enableMath={true}
											enableSyntaxHighlight={true}
											enableMermaid={true}
										/>
									) : (
										<p className="admin-kb-section-empty">
											当前小节暂无正文，请先重新整理教材生成真实内容。
										</p>
									)}
								</>
							);
						})()
					) : (
						<div className="admin-kb-section-empty">
							<p>请在左侧目录选择一个小节查看正文。</p>
						</div>
					)}
				</article>
			</div>
		</div>
	);
}
