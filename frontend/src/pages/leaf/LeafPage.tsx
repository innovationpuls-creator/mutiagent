import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { ChevronRight } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { createPortal, flushSync } from "react-dom";
import { useParams, useSearchParams } from "react-router-dom";
import { fetchLeafCourse } from "../../api/leaf";
import { FeedbackState } from "../../components/ui/FeedbackState";
import { useAiWidget } from "../../contexts/AiWidgetContext";
import { useAuth } from "../../contexts/AuthContext";
import { motionTokens } from "../../styles/motion-tokens";
import type {
	LeafCourseResponse,
	LeafGenerationStatus,
	LeafSection,
} from "../../types/leaf";
import { LeafContent } from "./LeafContent";
import {
	createInitialCollapsedLeafSections,
	createInitialLeafMarkmapCollapsed,
	LeafMarkmap,
	persistLeafMarkmapCollapsed,
} from "./LeafMarkmap";
import { LeafTopBar } from "./LeafTopBar";
import {
	findLeafSectionById,
	getDefaultLeafSectionId,
	getLeafComposedSection,
	getTopLevelSectionForLeaf,
	hasLeafComposedContent,
} from "./leafContentParser";
import {
	LEAF_GENERATION_COMPLETED_EVENT,
	LEAF_GENERATION_EVENT,
	type LeafGenerationCompletedEventDetail,
	type LeafGenerationEventDetail,
} from "./leafGenerationEvents";
import {
	buildCourseOutlineGenerationPrompt,
	buildLeafGenerationPrompt,
} from "./leafPrompt";
import "../../styles/leaf.css";

type LeafPageStatus = "idle" | "loading" | "ready" | "error";
const LEAF_GENERATION_REFRESH_RETRY_MS = 600;
const LEAF_GENERATION_REFRESH_ATTEMPTS = 3;

interface LeafGenerationChapterDraft {
	section_id: string;
	title: string;
	source_textbook_id: string;
	source_textbook_title: string;
	source_section_ids: string[];
	source_section_titles: string[];
	source_content_chars: number;
}

function fallbackLeafGenerationChapter(
	sectionId: string,
): LeafGenerationChapterDraft {
	return {
		section_id: sectionId,
		title: sectionId === "1" ? "第一章" : `第${sectionId}章`,
		source_textbook_id: "",
		source_textbook_title: "",
		source_section_ids: [],
		source_section_titles: [],
		source_content_chars: 0,
	};
}

function hasBoundTextbookSource(chapter: LeafGenerationChapterDraft): boolean {
	return (
		chapter.source_textbook_id.trim().length > 0 &&
		chapter.source_textbook_title.trim().length > 0 &&
		chapter.source_section_ids.length > 0 &&
		chapter.source_section_titles.length > 0 &&
		chapter.source_content_chars > 0
	);
}

function isLeafGenerationCompletedEventDetail(
	value: unknown,
): value is LeafGenerationCompletedEventDetail {
	return (
		value !== null &&
		typeof value === "object" &&
		"courseId" in value &&
		typeof value.courseId === "string" &&
		(!("reason" in value) ||
			value.reason === "course_outline" ||
			value.reason === "course_resource")
	);
}

function isLeafGenerationEventDetail(
	value: unknown,
): value is LeafGenerationEventDetail {
	return (
		value !== null &&
		typeof value === "object" &&
		"courseId" in value &&
		typeof value.courseId === "string" &&
		"chapterSectionId" in value &&
		typeof value.chapterSectionId === "string" &&
		"message" in value &&
		typeof value.message === "string"
	);
}

function resolveSelectedSectionId(
	response: LeafCourseResponse,
	sectionIdFromUrl: string | null,
): string | null {
	if (
		sectionIdFromUrl &&
		response.sections.some((section) => section.section_id === sectionIdFromUrl)
	) {
		return sectionIdFromUrl;
	}
	return getDefaultLeafSectionId(response);
}

function getGenerationSection(
	response: LeafCourseResponse,
	selectedSection: LeafSection | null,
): LeafGenerationChapterDraft | null {
	const selectedTopLevelSection = getTopLevelSectionForLeaf(
		response.sections,
		selectedSection,
	);
	if (selectedTopLevelSection) return selectedTopLevelSection;
	const firstGeneratableChapter = findLeafSectionById(
		response.sections,
		response.first_generatable_chapter_id,
	);
	if (firstGeneratableChapter) return firstGeneratableChapter;
	if (response.first_generatable_chapter_id) {
		return fallbackLeafGenerationChapter(response.first_generatable_chapter_id);
	}
	return null;
}

export function LeafPage() {
	const { courseNodeId } = useParams<{ courseNodeId: string }>();
	const [searchParams, setSearchParams] = useSearchParams();
	const { token, user } = useAuth();
	const { openWithDraft } = useAiWidget();
	const reduceMotion = useReducedMotion();
	const sectionIdFromUrl = searchParams.get("section_id");
	const readingKey = `onetree:reading:${user?.uid}:${courseNodeId}`;
	const rememberedSection = (() => {
		try {
			return localStorage.getItem(readingKey);
		} catch {
			return null;
		}
	})();

	const [status, setStatus] = useState<LeafPageStatus>("idle");
	const [response, setResponse] = useState<LeafCourseResponse | null>(null);
	const [errorMessage, setErrorMessage] = useState<string | null>(null);
	const [selectedSectionId, setSelectedSectionId] = useState<string | null>(
		null,
	);
	const [liveGenerationMessage, setLiveGenerationMessage] = useState<
		string | null
	>(null);
	const [liveGenerationStatus, setLiveGenerationStatus] =
		useState<LeafGenerationStatus | null>(null);
	const [markmapCollapsed, setMarkmapCollapsed] = useState(() =>
		createInitialLeafMarkmapCollapsed(),
	);
	const [collapsedSectionIds, setCollapsedSectionIds] = useState<Set<string>>(
		() => createInitialCollapsedLeafSections(),
	);

	const loadLeafCourse = useCallback(
		async (options?: { background?: boolean }) => {
			if (!token || !courseNodeId) return;
			if (!options?.background) {
				setStatus("loading");
				setErrorMessage(null);
			}
			try {
				const nextResponse = await fetchLeafCourse(token, courseNodeId);
				setResponse(nextResponse);
				setLiveGenerationStatus(nextResponse.generation_status);
				setStatus("ready");
				return nextResponse;
			} catch (error) {
				setErrorMessage(
					error instanceof Error ? error.message : "叶茂数据加载失败",
				);
				setStatus("error");
				return null;
			}
		},
		[courseNodeId, token],
	);

	useEffect(() => {
		void loadLeafCourse();
	}, [loadLeafCourse]);

	const refreshLeafCourseAfterGeneration = useCallback(async () => {
		for (
			let attempt = 0;
			attempt < LEAF_GENERATION_REFRESH_ATTEMPTS;
			attempt += 1
		) {
			const nextResponse = await loadLeafCourse({ background: true });
			if (!nextResponse) return;
			const nextSelectedSectionId = resolveSelectedSectionId(
				nextResponse,
				sectionIdFromUrl ?? rememberedSection,
			);
			if (
				!nextSelectedSectionId ||
				hasLeafComposedContent(nextResponse, nextSelectedSectionId)
			) {
				return;
			}
			if (attempt + 1 >= LEAF_GENERATION_REFRESH_ATTEMPTS) {
				return;
			}
			await new Promise<void>((resolve) => {
				window.setTimeout(resolve, LEAF_GENERATION_REFRESH_RETRY_MS);
			});
		}
	}, [loadLeafCourse, sectionIdFromUrl, rememberedSection]);

	useEffect(() => {
		if (!response) return;
		const validUrl = response.sections.some(
			(section) => section.section_id === sectionIdFromUrl,
		);
		setSelectedSectionId(
			resolveSelectedSectionId(
				response,
				validUrl ? sectionIdFromUrl : rememberedSection,
			),
		);
	}, [response, sectionIdFromUrl, rememberedSection]);

	useEffect(() => {
		if (
			!user ||
			!selectedSectionId ||
			!response?.sections.some((s) => s.section_id === selectedSectionId)
		)
			return;
		try {
			localStorage.setItem(readingKey, selectedSectionId);
		} catch {
			/* Reading remains available without local storage. */
		}
	}, [user, response, selectedSectionId, readingKey]);

	useEffect(() => {
		const handleGenerationEvent = (event: Event) => {
			const detail = event instanceof CustomEvent ? event.detail : null;
			if (
				!isLeafGenerationEventDetail(detail) ||
				detail.courseId !== courseNodeId
			)
				return;
			flushSync(() => {
				setLiveGenerationMessage(detail.message);
				setLiveGenerationStatus({
					course_node_id: detail.courseId,
					chapter_section_id: detail.chapterSectionId,
					status: detail.status === "error" ? "error" : "running",
					message: detail.message,
				});
			});
		};

		const handleGenerationCompletedEvent = (event: Event) => {
			const detail = event instanceof CustomEvent ? event.detail : null;
			if (
				!isLeafGenerationCompletedEventDetail(detail) ||
				detail.courseId !== courseNodeId
			)
				return;
			setLiveGenerationMessage(null);
			if (detail.reason === "course_outline") {
				void loadLeafCourse({ background: true });
				return;
			}
			void refreshLeafCourseAfterGeneration();
		};

		window.addEventListener(LEAF_GENERATION_EVENT, handleGenerationEvent);
		window.addEventListener(
			LEAF_GENERATION_COMPLETED_EVENT,
			handleGenerationCompletedEvent,
		);
		return () => {
			window.removeEventListener(LEAF_GENERATION_EVENT, handleGenerationEvent);
			window.removeEventListener(
				LEAF_GENERATION_COMPLETED_EVENT,
				handleGenerationCompletedEvent,
			);
		};
	}, [courseNodeId, loadLeafCourse, refreshLeafCourseAfterGeneration]);

	const selectedSection = useMemo(() => {
		if (!response) return null;
		return findLeafSectionById(response.sections, selectedSectionId);
	}, [response, selectedSectionId]);

	const generationSection = useMemo(() => {
		if (!response) return null;
		return getGenerationSection(response, selectedSection);
	}, [response, selectedSection]);

	const composedSection = response
		? getLeafComposedSection(response, selectedSectionId)
		: null;
	const selectedSectionResourceError =
		response && selectedSectionId
			? (response.section_resource_errors?.[selectedSectionId] ?? null)
			: null;
	const canGenerate =
		Boolean(
			response &&
				response.access_state === "available" &&
				response.can_generate &&
				response.course.status !== "completed",
		) &&
		Boolean(
			generationSection &&
				response?.first_generatable_chapter_id &&
				generationSection.section_id === response.first_generatable_chapter_id,
		);

	const handleSelectSection = useCallback(
		(sectionId: string) => {
			setSelectedSectionId(sectionId);
			setSearchParams(
				(currentSearchParams) => {
					const nextSearchParams = new URLSearchParams(currentSearchParams);
					nextSearchParams.set("section_id", sectionId);
					return nextSearchParams;
				},
				{ replace: true },
			);
		},
		[setSearchParams],
	);

	const handleGenerate = useCallback(() => {
		if (!response || !generationSection) return;
		if (!hasBoundTextbookSource(generationSection)) {
			openWithDraft(buildCourseOutlineGenerationPrompt(response.course));
			return;
		}
		const chapterLeafSections = response.sections.filter(
			(section) => section.parent_section_id === generationSection.section_id,
		);
		const mode = chapterLeafSections.some((section) =>
			hasLeafComposedContent(response, section.section_id),
		)
			? "regenerate"
			: "generate";
		openWithDraft(
			buildLeafGenerationPrompt(response.course, generationSection, mode),
		);
	}, [generationSection, openWithDraft, response]);

	const handleGenerateOutline = useCallback(() => {
		if (!response) return;
		openWithDraft(buildCourseOutlineGenerationPrompt(response.course));
	}, [openWithDraft, response]);

	if (!token || !courseNodeId) {
		return null;
	}

	if (status === "loading" || status === "idle") {
		return (
			<section
				className="leaf-page leaf-page-centered"
				aria-label="叶茂课程加载中"
			>
				<div className="leaf-ambient-sun" aria-hidden="true" />
				<div className="leaf-paper-canvas" aria-hidden="true" />
				<FeedbackState
					className="relative z-10"
					variant="loading"
					title="正在铺开这一页"
					description="课程内容正在从叶脉里慢慢展开。"
					icon={
						<motion.div
							animate={{ rotate: 360 }}
							transition={{ repeat: Infinity, duration: 2, ease: "linear" }}
							className="leaf-loading-ring"
						/>
					}
				/>
			</section>
		);
	}

	if (status === "error" || !response) {
		return (
			<section
				className="leaf-page leaf-page-centered"
				aria-label="叶茂课程加载失败"
			>
				<div className="leaf-ambient-sun" aria-hidden="true" />
				<div className="leaf-paper-canvas" aria-hidden="true" />
				<FeedbackState
					className="relative z-10"
					variant="error"
					title="叶茂数据加载失败"
					description={errorMessage ?? "请稍后再试。"}
				/>
			</section>
		);
	}

	const markmapToggleButton =
		typeof document !== "undefined"
			? createPortal(
					<AnimatePresence>
						{markmapCollapsed && (
							<motion.button
								key="markmap-toggle-button"
								initial={reduceMotion ? false : { opacity: 0, x: -20 }}
								animate={reduceMotion ? undefined : { opacity: 1, x: 0 }}
								exit={reduceMotion ? undefined : { opacity: 0, x: -20 }}
								transition={motionTokens.editorial}
								aria-label="展开章节导航"
								type="button"
								onClick={() => {
									persistLeafMarkmapCollapsed(false);
									setMarkmapCollapsed(false);
								}}
								className="leaf-markmap-expand"
							>
								<ChevronRight aria-hidden="true" />
							</motion.button>
						)}
					</AnimatePresence>,
					document.body,
				)
			: null;

	return (
		<section
			className="leaf-page"
			aria-label={`${response.course.course_or_chapter_theme}课程内容`}
		>
			<div className="leaf-ambient-sun" aria-hidden="true" />
			<div className="leaf-paper-canvas" aria-hidden="true" />
			{markmapToggleButton}

			<AnimatePresence mode="wait">
				{!markmapCollapsed && (
					<LeafMarkmap
						key="expanded-layout"
						response={response}
						selectedSectionId={selectedSectionId}
						markmapCollapsed={markmapCollapsed}
						collapsedSectionIds={collapsedSectionIds}
						onToggleMarkmapCollapsed={() => {
							persistLeafMarkmapCollapsed(true);
							setMarkmapCollapsed(true);
						}}
						onCollapsedSectionIdsChange={setCollapsedSectionIds}
						onSelectSection={handleSelectSection}
						onGenerateOutline={handleGenerateOutline}
					/>
				)}
			</AnimatePresence>

			<div
				className={`leaf-page-main ${markmapCollapsed ? "leaf-page-main-collapsed" : "leaf-page-main-with-map"}`}
			>
				<div className="leaf-page-main-inner">
					<LeafTopBar
						course={response.course}
						selectedSection={selectedSection}
						generationStatus={liveGenerationStatus}
						liveGenerationMessage={liveGenerationMessage}
						sectionResourceRetryable={
							selectedSectionResourceError?.retryable ?? false
						}
						canGenerate={canGenerate}
						onGenerate={handleGenerate}
					/>
					<div className={markmapCollapsed ? "mt-8" : "mt-0"}>
						<LeafContent
							section={selectedSection}
							composedSection={composedSection}
							sectionResourceError={selectedSectionResourceError}
							lockedReason={response.locked_reason}
						/>
					</div>
				</div>
			</div>
		</section>
	);
}
