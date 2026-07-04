import { Search } from "lucide-react";
import { useMemo, useState } from "react";
import type {
	Textbook,
	TextbookSectionContent,
} from "../../api/knowledgeBase";
import { AdminTextbookInspector } from "./AdminTextbookInspector";

interface AdminTextbookBrowserProps {
	textbooks: Textbook[];
	selectedTextbookId: string;
	selectedTextbook: Textbook | null;
	selectedTextbookSections: TextbookSectionContent[];
	isBusy: boolean;
	onSelectTextbook: (textbookId: string) => void;
	onOrganizeSelected: () => Promise<void>;
	onPublishSelected: () => Promise<void>;
	onUnpublishSelected: () => Promise<void>;
	onDeleteSelected: () => Promise<void>;
	onEditSelectedOutline: () => void;
}

function formatStatus(value: string) {
	switch (value) {
		case "published":
			return "已发布";
		case "draft":
			return "草稿";
		case "unpublished":
			return "已下架";
		case "archived":
			return "已归档";
		default:
			return value;
	}
}

function formatOutlineSummary(outline: unknown) {
	if (!outline || typeof outline !== "object") return "暂无大纲";
	const chapters = (outline as { chapters?: unknown }).chapters;
	if (Array.isArray(chapters)) {
		const sectionCount = chapters.reduce((total, chapter) => {
			if (!chapter || typeof chapter !== "object") return total;
			const sections = (chapter as { sections?: unknown }).sections;
			return total + (Array.isArray(sections) ? sections.length : 0);
		}, 0);
		return `${chapters.length} 章 · ${sectionCount} 节`;
	}
	const sections = (outline as { sections?: unknown }).sections;
	if (Array.isArray(sections)) {
		return `${sections.length} 节`;
	}
	return "暂无大纲";
}

function getColorForTextbook(title: string) {
	const hues = [
		"var(--color-accent-sage)",      // 鼠尾草绿
		"var(--color-accent-peach)",     // 柔桃色
		"var(--color-accent-lavender)",  // 雾紫
		"var(--color-accent-salmon)",    // 鲑鱼粉
		"var(--color-primary-soft)",     // 稀释暖珊瑚
		"var(--color-secondary-soft)",   // 雾蓝
	];
	let hash = 0;
	for (let i = 0; i < title.length; i++) {
		hash = title.charCodeAt(i) + ((hash << 5) - hash);
	}
	return hues[Math.abs(hash) % hues.length];
}

export function AdminTextbookBrowser({
	textbooks,
	selectedTextbookId,
	selectedTextbook,
	selectedTextbookSections,
	isBusy,
	onSelectTextbook,
	onOrganizeSelected,
	onPublishSelected,
	onUnpublishSelected,
	onDeleteSelected,
	onEditSelectedOutline,
}: AdminTextbookBrowserProps) {
	const [searchQuery, setSearchQuery] = useState("");
	const [statusFilter, setStatusFilter] = useState<string>("all");

	const filteredTextbooks = useMemo(() => {
		return textbooks.filter((textbook) => {
			const matchesSearch =
				textbook.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
				(textbook.description || "")
					.toLowerCase()
					.includes(searchQuery.toLowerCase()) ||
				(textbook.original_title || "")
					.toLowerCase()
					.includes(searchQuery.toLowerCase());

			const matchesStatus =
				statusFilter === "all" ||
				textbook.student_availability_status === statusFilter;

			return matchesSearch && matchesStatus;
		});
	}, [textbooks, searchQuery, statusFilter]);

	return (
		<section className="admin-kb-workspace" aria-label="教材库浏览器">
			<div className="admin-kb-layout">
				{/* 左侧：教材库目录 */}
				<section className="admin-kb-left-panel" aria-label="教材库目录">
					<div className="admin-kb-panel-header">
						<h3>📚 已导入教材库</h3>
						<p>查看与检索知识库中已录入的所有学术教材</p>
					</div>

					{/* 搜索与过滤工具栏 */}
					<div className="admin-kb-browser-toolbar">
						<div className="admin-search">
							<Search aria-hidden="true" />
							<label className="sr-only" htmlFor="admin-kb-search">
								搜索教材
							</label>
							<input
								id="admin-kb-search"
								type="text"
								value={searchQuery}
								onChange={(e) => setSearchQuery(e.target.value)}
								placeholder="搜索教材标题、英文名或描述..."
							/>
						</div>

						<div className="admin-filter">
							<label className="sr-only" htmlFor="admin-kb-status-filter">
								状态过滤
							</label>
							<select
								id="admin-kb-status-filter"
								value={statusFilter}
								onChange={(e) => setStatusFilter(e.target.value)}
							>
								<option value="all">所有状态</option>
								<option value="draft">草稿</option>
								<option value="published">已发布</option>
								<option value="unpublished">已下架</option>
							</select>
						</div>
					</div>

					{/* 教材列表 */}
					<div className="admin-kb-book-list-container">
						{filteredTextbooks.length > 0 ? (
							<div className="admin-kb-book-grid">
								{filteredTextbooks.map((textbook) => {
									const isSelected = textbook.textbook_id === selectedTextbookId;
									const coverColor = getColorForTextbook(textbook.title);
									const outlineText = formatOutlineSummary(textbook.outline);

									return (
										<button
											key={textbook.textbook_id}
											type="button"
											className={`admin-kb-book-card ${isSelected ? "is-selected" : ""}`}
											onClick={() => onSelectTextbook(textbook.textbook_id)}
											aria-label={`选中教材《${textbook.title}》`}
										>
											<div
												className="admin-kb-book-cover"
												style={{ backgroundColor: coverColor }}
											>
												<span className="book-cover-letter">
													{textbook.title[0] || "📖"}
												</span>
												<div className="book-cover-spine" />
											</div>

											<div className="admin-kb-book-info">
												<div className="admin-kb-book-title-row">
													<strong>{textbook.title}</strong>
													<span
														className={`status-pill is-${textbook.student_availability_status}`}
													>
														{formatStatus(textbook.student_availability_status)}
													</span>
												</div>

												{textbook.original_title && (
													<small className="admin-kb-book-original">
														{textbook.original_title}
													</small>
												)}

												<p className="admin-kb-book-desc">
													{textbook.description || "暂无简介。"}
												</p>

												<div className="admin-kb-book-meta">
													<span>{outlineText}</span>
													<span>
														解析：
														{textbook.ingestion_status === "completed" ||
														textbook.ingestion_status === "ready_for_outline_review"
															? "已就绪"
															: textbook.ingestion_status === "failed"
																? "失败"
																: textbook.ingestion_status === "processing"
																	? "进行中"
																	: "待解析"}
													</span>
												</div>
											</div>
										</button>
									);
								})}
							</div>
						) : (
							<div className="admin-kb-empty-list">
								<p>未找到符合条件的教材。</p>
							</div>
						)}
					</div>
				</section>

				{/* 右侧：教材大纲与资源详情审查面板 */}
				<section className="admin-kb-right-panel" aria-label="详情审查面板">
					<div className="admin-kb-panel-header">
						<h3>📖 教材与解析详情</h3>
						<p>查看教材大纲与管理操作 (已录入 {textbooks.length} 本教材)</p>
					</div>

					<div className="admin-kb-inspector-content">
						<AdminTextbookInspector
							selectedTextbook={selectedTextbook}
							selectedTextbookSections={selectedTextbookSections}
							isBusy={isBusy}
							onOrganizeSelected={onOrganizeSelected}
							onPublishSelected={onPublishSelected}
							onUnpublishSelected={onUnpublishSelected}
							onDeleteSelected={onDeleteSelected}
							onEditSelectedOutline={onEditSelectedOutline}
						/>
					</div>
				</section>
			</div>
		</section>
	);
}
