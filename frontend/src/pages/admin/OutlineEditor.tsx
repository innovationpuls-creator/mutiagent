import {
	ArrowDown,
	ArrowUp,
	Check,
	Loader2,
	Plus,
	Save,
	Sparkles,
	Trash2,
} from "lucide-react";
import { useEffect, useState } from "react";
import type { Textbook } from "../../api/knowledgeBase";

interface OutlineSection {
	section_id: string;
	title: string;
	description?: string;
	key_knowledge_points?: string[];
}

interface OutlineChapter {
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
	onSave: (updatedOutline: OutlineData) => Promise<void>;
	generateOutlineApi: (prompt: string, tags: string[]) => Promise<Textbook>;
}

export function OutlineEditor({
	textbook,
	onSave,
	generateOutlineApi,
}: OutlineEditorProps) {
	const [outline, setOutline] = useState<OutlineData>({ chapters: [] });
	const [copilotPrompt, setCopilotPrompt] = useState("");
	const [copilotTags, setCopilotTags] = useState("");
	const [isCopilotBusy, setIsCopilotBusy] = useState(false);
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
				const sections = rawOutline.sections as {
					depth?: number;
					parent_section_id?: string | null;
					section_id: string;
					title: string;
					description?: string;
					key_knowledge_points?: string[];
				}[];
				for (const sec of sections) {
					if (sec.depth === 1 || !sec.parent_section_id) {
						const chNum = Number.parseInt(sec.section_id, 10) || 1;
						chaptersMap.set(sec.section_id, {
							chapter_number: chNum,
							title: sec.title,
							description: sec.description || "",
							sections: [],
						});
					}
				}
				for (const sec of sections) {
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

	const handleAddChapter = () => {
		const nextChNum = outline.chapters.length + 1;
		const newChapter: OutlineChapter = {
			chapter_number: nextChNum,
			title: `第${nextChNum}章 新增章节`,
			description: "",
			sections: [],
		};
		setOutline({ chapters: [...outline.chapters, newChapter] });
	};

	const handleAddSection = (chapterIndex: number) => {
		const chapter = outline.chapters[chapterIndex];
		const nextSecNum = chapter.sections.length + 1;
		const parentId = String(chapter.chapter_number);
		const newSection: OutlineSection = {
			section_id: `${parentId}.${nextSecNum}`,
			title: `${parentId}.${nextSecNum} 新增小节`,
			description: "",
			key_knowledge_points: [],
		};
		const updatedChapters = [...outline.chapters];
		updatedChapters[chapterIndex] = {
			...chapter,
			sections: [...chapter.sections, newSection],
		};
		setOutline({ chapters: updatedChapters });
	};

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

	const handleDeleteChapter = (chapterIndex: number) => {
		const updatedChapters = outline.chapters.filter(
			(_, i) => i !== chapterIndex,
		);
		// Re-index chapter numbers
		const reindexed = updatedChapters.map((ch, i) => {
			const newNum = i + 1;
			const updatedSections = ch.sections.map((sec, j) => ({
				...sec,
				section_id: `${newNum}.${j + 1}`,
			}));
			return {
				...ch,
				chapter_number: newNum,
				title: ch.title.replace(/^第\d+章/, `第${newNum}章`),
				sections: updatedSections,
			};
		});
		setOutline({ chapters: reindexed });
	};

	const handleDeleteSection = (chapterIndex: number, sectionIndex: number) => {
		const chapter = outline.chapters[chapterIndex];
		const updatedSections = chapter.sections.filter(
			(_, i) => i !== sectionIndex,
		);
		// Re-index section ids
		const parentId = String(chapter.chapter_number);
		const reindexedSections = updatedSections.map((sec, i) => ({
			...sec,
			section_id: `${parentId}.${i + 1}`,
			title: sec.title.replace(/^\d+\.\d+/, `${parentId}.${i + 1}`),
		}));
		const updatedChapters = [...outline.chapters];
		updatedChapters[chapterIndex] = {
			...chapter,
			sections: reindexedSections,
		};
		setOutline({ chapters: updatedChapters });
	};

	const handleMoveChapter = (index: number, direction: "up" | "down") => {
		if (direction === "up" && index === 0) return;
		if (direction === "down" && index === outline.chapters.length - 1) return;

		const targetIndex = direction === "up" ? index - 1 : index + 1;
		const updated = [...outline.chapters];
		const temp = updated[index];
		updated[index] = updated[targetIndex];
		updated[targetIndex] = temp;

		// Re-index everything to keep structure clean
		const reindexed = updated.map((ch, i) => {
			const newNum = i + 1;
			const updatedSections = ch.sections.map((sec, j) => ({
				...sec,
				section_id: `${newNum}.${j + 1}`,
				title: sec.title.replace(/^\d+\.\d+/, `${newNum}.${j + 1}`),
			}));
			return {
				...ch,
				chapter_number: newNum,
				title: ch.title.replace(/^第\d+章/, `第${newNum}章`),
				sections: updatedSections,
			};
		});
		setOutline({ chapters: reindexed });
	};

	const handleMoveSection = (
		chapterIndex: number,
		sectionIndex: number,
		direction: "up" | "down",
	) => {
		const chapter = outline.chapters[chapterIndex];
		if (direction === "up" && sectionIndex === 0) return;
		if (direction === "down" && sectionIndex === chapter.sections.length - 1)
			return;

		const targetIndex =
			direction === "up" ? sectionIndex - 1 : sectionIndex + 1;
		const updatedSections = [...chapter.sections];
		const temp = updatedSections[sectionIndex];
		updatedSections[sectionIndex] = updatedSections[targetIndex];
		updatedSections[targetIndex] = temp;

		const parentId = String(chapter.chapter_number);
		const reindexedSections = updatedSections.map((sec, i) => ({
			...sec,
			section_id: `${parentId}.${i + 1}`,
			title: sec.title.replace(/^\d+\.\d+/, `${parentId}.${i + 1}`),
		}));

		const updatedChapters = [...outline.chapters];
		updatedChapters[chapterIndex] = {
			...chapter,
			sections: reindexedSections,
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
			if (ch.sections.length < 3) {
				setError(`「${ch.title}」必须至少包含 3 个小节`);
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

	const handleCopilotGenerate = async () => {
		if (!copilotPrompt.trim()) return;
		setIsCopilotBusy(true);
		setError(null);
		try {
			const tags = copilotTags
				.split(",")
				.map((t) => t.trim())
				.filter(Boolean);
			const generated = await generateOutlineApi(copilotPrompt, tags);
			if (generated.outline && typeof generated.outline === "object") {
				const rawOutline = generated.outline as Record<string, unknown>;
				if (Array.isArray(rawOutline.chapters)) {
					setOutline(rawOutline as unknown as OutlineData);
					setCopilotPrompt("");
				} else {
					throw new Error("生成的 AI 大纲结构不正确");
				}
			}
		} catch (err) {
			setError(err instanceof Error ? err.message : "AI 大纲协同生成失败");
		} finally {
			setIsCopilotBusy(false);
		}
	};

	return (
		<div className="outline-editor-container">
			<div className="outline-editor-workspace">
				<div className="outline-tree-panel">
					<div className="outline-tree-header">
						<h3>大纲结构微调</h3>
						<button
							type="button"
							className="admin-secondary-action add-ch-btn"
							onClick={handleAddChapter}
						>
							<Plus size={16} />
							<span>添加新章节</span>
						</button>
					</div>

					<div className="outline-chapters-list">
						{outline.chapters.map((chapter, chIdx) => (
							<div
								key={chapter.chapter_number}
								className="outline-chapter-card"
							>
								<div className="outline-chapter-header">
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
										/>
									</div>
									<div className="chapter-actions">
										<button
											type="button"
											title="上移"
											onClick={() => handleMoveChapter(chIdx, "up")}
											disabled={chIdx === 0}
										>
											<ArrowUp size={14} />
										</button>
										<button
											type="button"
											title="下移"
											onClick={() => handleMoveChapter(chIdx, "down")}
											disabled={chIdx === outline.chapters.length - 1}
										>
											<ArrowDown size={14} />
										</button>
										<button
											type="button"
											title="删除"
											className="delete-btn"
											onClick={() => handleDeleteChapter(chIdx)}
										>
											<Trash2 size={14} />
										</button>
									</div>
								</div>

								<div className="outline-sections-list">
									{chapter.sections.map((section, secIdx) => (
										<div
											key={section.section_id}
											className="outline-section-row"
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
											/>
											<div className="section-actions">
												<button
													type="button"
													title="上移"
													onClick={() => handleMoveSection(chIdx, secIdx, "up")}
													disabled={secIdx === 0}
												>
													<ArrowUp size={12} />
												</button>
												<button
													type="button"
													title="下移"
													onClick={() =>
														handleMoveSection(chIdx, secIdx, "down")
													}
													disabled={secIdx === chapter.sections.length - 1}
												>
													<ArrowDown size={12} />
												</button>
												<button
													type="button"
													title="删除"
													className="delete-btn"
													onClick={() => handleDeleteSection(chIdx, secIdx)}
												>
													<Trash2 size={12} />
												</button>
											</div>
										</div>
									))}
									<button
										type="button"
										className="add-sec-inline-btn"
										onClick={() => handleAddSection(chIdx)}
									>
										<Plus size={14} />
										<span>添加子小节</span>
									</button>
								</div>
							</div>
						))}

						{outline.chapters.length === 0 && (
							<div className="empty-outline-state">
								<p>当前教材暂无大纲，可在右侧通过 AI Copilot 协同快速生成。</p>
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

				<div className="outline-copilot-sidebar">
					<div className="copilot-header">
						<Sparkles className="copilot-glow-icon" size={18} />
						<h3>大纲 AI 协同 Copilot</h3>
					</div>

					<div className="copilot-body">
						<div className="copilot-prompt-section">
							<label htmlFor="copilot-input-area">
								<span>协同创作提示词</span>
								<textarea
									id="copilot-input-area"
									placeholder="例如：生成一份‘FastAPI 核心架构’的教学大纲，包含路由设计、依赖注入与中间件三个章节，每个章节要有 3 个详细的小节。"
									value={copilotPrompt}
									onChange={(e) => setCopilotPrompt(e.target.value)}
								/>
							</label>
						</div>

						<div className="copilot-tags-section">
							<label htmlFor="copilot-tags-input">
								<span>课程标签（用逗号分隔）</span>
								<input
									id="copilot-tags-input"
									type="text"
									placeholder="例如：FastAPI, Python, Web开发"
									value={copilotTags}
									onChange={(e) => setCopilotTags(e.target.value)}
								/>
							</label>
						</div>

						<div className="copilot-quick-chips">
							<span>常用创作推荐</span>
							<div className="chips-grid">
								{[
									"数据结构与复杂度分析大纲",
									"Git 与团队协同工作流大纲",
									"React 与 TypeScript 前端开发",
									"FastAPI 高并发服务端实战",
								].map((chip) => (
									<button
										key={chip}
										type="button"
										className="copilot-chip"
										onClick={() => setCopilotPrompt(chip)}
									>
										{chip}
									</button>
								))}
							</div>
						</div>

						<button
							type="button"
							className="admin-primary-action copilot-generate-btn"
							onClick={handleCopilotGenerate}
							disabled={isCopilotBusy || !copilotPrompt.trim()}
						>
							{isCopilotBusy ? (
								<Loader2 className="spinner" size={16} />
							) : (
								<Sparkles size={16} />
							)}
							<span>
								{isCopilotBusy ? "正在协同创作中..." : "AI 协同创作大纲"}
							</span>
						</button>
					</div>
				</div>
			</div>
		</div>
	);
}
