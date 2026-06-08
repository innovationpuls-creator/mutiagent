import { useCallback, useEffect, useMemo, useState } from 'react';
import { createPortal, flushSync } from 'react-dom';
import { useParams, useSearchParams } from 'react-router-dom';
import { AnimatePresence, motion, useReducedMotion } from 'framer-motion';
import { fetchLeafCourse } from '../../api/leaf';
import { useAiWidget } from '../../context/AiWidgetContext';
import { useAuth } from '../../contexts/AuthContext';
import { motionTokens } from '../../styles/motion-tokens';
import type {
  LeafCourseResponse,
  LeafGenerationStatus,
  LeafSection,
} from '../../types/leaf';
import { LeafContent } from './LeafContent';
import {
  LeafMarkmap,
  createInitialCollapsedLeafSections,
  createInitialLeafMarkmapCollapsed,
  persistLeafMarkmapCollapsed,
} from './LeafMarkmap';
import { LeafTopBar } from './LeafTopBar';
import {
  findLeafSectionById,
  getDefaultLeafSectionId,
  getLeafComposedSection,
  getTopLevelSectionForLeaf,
  hasLeafComposedContent,
} from './leafContentParser';
import { buildCourseOutlineGenerationPrompt, buildLeafGenerationPrompt } from './leafPrompt';
import {
  LEAF_GENERATION_COMPLETED_EVENT,
  LEAF_GENERATION_EVENT,
  type LeafGenerationCompletedEventDetail,
  type LeafGenerationEventDetail,
} from './leafGenerationEvents';
import { ChevronRight, PanelLeftClose } from 'lucide-react';
import '../../styles/leaf.css';

type LeafPageStatus = 'idle' | 'loading' | 'ready' | 'error';
const LEAF_NAV_TOGGLE_Z_INDEX = 10000;
const LEAF_GENERATION_REFRESH_RETRY_MS = 600;
const LEAF_GENERATION_REFRESH_ATTEMPTS = 3;

interface LeafGenerationChapterDraft {
  section_id: string;
  title: string;
}

function isLeafGenerationCompletedEventDetail(value: unknown): value is LeafGenerationCompletedEventDetail {
  return (
    value !== null
    && typeof value === 'object'
    && 'courseId' in value
    && typeof value.courseId === 'string'
    && (
      !('reason' in value)
      || value.reason === 'course_outline'
      || value.reason === 'course_resource'
    )
  );
}

function isLeafGenerationEventDetail(value: unknown): value is LeafGenerationEventDetail {
  return (
    value !== null
    && typeof value === 'object'
    && 'courseId' in value
    && typeof value.courseId === 'string'
    && 'chapterSectionId' in value
    && typeof value.chapterSectionId === 'string'
    && 'message' in value
    && typeof value.message === 'string'
  );
}

function resolveSelectedSectionId(
  response: LeafCourseResponse,
  sectionIdFromUrl: string | null,
): string | null {
  if (sectionIdFromUrl && response.sections.some((section) => section.section_id === sectionIdFromUrl)) {
    return sectionIdFromUrl;
  }
  return getDefaultLeafSectionId(response);
}

function getGenerationSection(
  response: LeafCourseResponse,
  selectedSection: LeafSection | null,
): LeafGenerationChapterDraft | null {
  const selectedTopLevelSection = getTopLevelSectionForLeaf(response.sections, selectedSection);
  if (selectedTopLevelSection) return selectedTopLevelSection;
  const firstGeneratableChapter = findLeafSectionById(response.sections, response.first_generatable_chapter_id);
  if (firstGeneratableChapter) return firstGeneratableChapter;
  if (response.first_generatable_chapter_id) {
    return {
      section_id: response.first_generatable_chapter_id,
      title: response.first_generatable_chapter_id === '1'
        ? '第一章'
        : `第${response.first_generatable_chapter_id}章`,
    };
  }
  return null;
}

export function LeafPage() {
  const { courseNodeId } = useParams<{ courseNodeId: string }>();
  const [searchParams, setSearchParams] = useSearchParams();
  const { token } = useAuth();
  const { openWithDraft } = useAiWidget();
  const reduceMotion = useReducedMotion();
  const sectionIdFromUrl = searchParams.get('section_id');

  const [status, setStatus] = useState<LeafPageStatus>('idle');
  const [response, setResponse] = useState<LeafCourseResponse | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [selectedSectionId, setSelectedSectionId] = useState<string | null>(null);
  const [liveGenerationMessage, setLiveGenerationMessage] = useState<string | null>(null);
  const [liveGenerationStatus, setLiveGenerationStatus] = useState<LeafGenerationStatus | null>(null);
  const [markmapCollapsed, setMarkmapCollapsed] = useState(() => createInitialLeafMarkmapCollapsed());
  const [collapsedSectionIds, setCollapsedSectionIds] = useState<Set<string>>(
    () => createInitialCollapsedLeafSections(),
  );

  const loadLeafCourse = useCallback(async (options?: { background?: boolean }) => {
    if (!token || !courseNodeId) return;
    if (!options?.background) {
      setStatus('loading');
      setErrorMessage(null);
    }
    try {
      const nextResponse = await fetchLeafCourse(token, courseNodeId);
      setResponse(nextResponse);
      setLiveGenerationStatus(nextResponse.generation_status);
      setStatus('ready');
      return nextResponse;
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : '叶茂数据加载失败');
      setStatus('error');
      return null;
    }
  }, [courseNodeId, token]);

  useEffect(() => {
    void loadLeafCourse();
  }, [loadLeafCourse]);

  const refreshLeafCourseAfterGeneration = useCallback(async () => {
    for (let attempt = 0; attempt < LEAF_GENERATION_REFRESH_ATTEMPTS; attempt += 1) {
      const nextResponse = await loadLeafCourse({ background: true });
      if (!nextResponse) return;
      const nextSelectedSectionId = resolveSelectedSectionId(nextResponse, sectionIdFromUrl);
      if (!nextSelectedSectionId || hasLeafComposedContent(nextResponse, nextSelectedSectionId)) {
        return;
      }
      if (attempt + 1 >= LEAF_GENERATION_REFRESH_ATTEMPTS) {
        return;
      }
      await new Promise<void>((resolve) => {
        window.setTimeout(resolve, LEAF_GENERATION_REFRESH_RETRY_MS);
      });
    }
  }, [loadLeafCourse, sectionIdFromUrl]);

  useEffect(() => {
    if (!response) return;
    setSelectedSectionId(resolveSelectedSectionId(response, sectionIdFromUrl));
  }, [response, sectionIdFromUrl]);

  useEffect(() => {
    const handleGenerationEvent = (event: Event) => {
      const detail = event instanceof CustomEvent ? event.detail : null;
      if (!isLeafGenerationEventDetail(detail) || detail.courseId !== courseNodeId) return;
      flushSync(() => {
        setLiveGenerationMessage(detail.message);
        setLiveGenerationStatus({
          course_node_id: detail.courseId,
          chapter_section_id: detail.chapterSectionId,
          status: detail.status === 'error' ? 'error' : 'running',
          message: detail.message,
        });
      });
    };

    const handleGenerationCompletedEvent = (event: Event) => {
      const detail = event instanceof CustomEvent ? event.detail : null;
      if (!isLeafGenerationCompletedEventDetail(detail) || detail.courseId !== courseNodeId) return;
      setLiveGenerationMessage(null);
      if (detail.reason === 'course_outline') {
        void loadLeafCourse({ background: true });
        return;
      }
      void refreshLeafCourseAfterGeneration();
    };

    window.addEventListener(LEAF_GENERATION_EVENT, handleGenerationEvent);
    window.addEventListener(LEAF_GENERATION_COMPLETED_EVENT, handleGenerationCompletedEvent);
    return () => {
      window.removeEventListener(LEAF_GENERATION_EVENT, handleGenerationEvent);
      window.removeEventListener(LEAF_GENERATION_COMPLETED_EVENT, handleGenerationCompletedEvent);
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

  const composedSection = response ? getLeafComposedSection(response, selectedSectionId) : null;
  const canGenerate = Boolean(
    response
    && response.access_state === 'available'
    && response.can_generate
    && response.course.status !== 'completed',
  ) && Boolean(
    generationSection
    && response?.first_generatable_chapter_id
    && generationSection.section_id === response.first_generatable_chapter_id,
  );

  const handleSelectSection = useCallback((sectionId: string) => {
    setSelectedSectionId(sectionId);
    setSearchParams((currentSearchParams) => {
      const nextSearchParams = new URLSearchParams(currentSearchParams);
      nextSearchParams.set('section_id', sectionId);
      return nextSearchParams;
    }, { replace: true });
  }, [setSearchParams]);

  const handleGenerate = useCallback(() => {
    if (!response || !generationSection) return;
    const chapterLeafSections = response.sections.filter(
      (section) => section.parent_section_id === generationSection.section_id,
    );
    const mode = chapterLeafSections.some((section) => hasLeafComposedContent(response, section.section_id))
      ? 'regenerate'
      : 'generate';
    openWithDraft(buildLeafGenerationPrompt(response.course, generationSection, mode));
  }, [generationSection, openWithDraft, response]);

  const handleGenerateOutline = useCallback(() => {
    if (!response) return;
    openWithDraft(buildCourseOutlineGenerationPrompt(response.course));
  }, [openWithDraft, response]);

  if (!token || !courseNodeId) {
    return null;
  }

  if (status === 'loading' || status === 'idle') {
    return (
      <section className="leaf-page min-h-screen text-[var(--color-text-primary)] relative overflow-x-hidden flex items-center justify-center" aria-label="叶茂课程加载中">
        <div className="leaf-ambient-sun" aria-hidden="true" />
        <div className="leaf-paper-canvas" aria-hidden="true" />
        <div className="text-center relative z-10">
          <motion.div
            animate={{ rotate: 360 }}
            transition={{ repeat: Infinity, duration: 2, ease: "linear" }}
            className="w-12 h-12 border-4 border-[var(--color-primary-soft)] border-t-[var(--color-primary)] rounded-full mx-auto mb-6"
          />
          <span className="text-[var(--color-text-muted)] text-sm tracking-widest uppercase mb-2 block">// loading</span>
          <h1 className="text-2xl font-medium text-[var(--color-secondary)] mb-2">正在铺开这一页</h1>
          <p className="text-[var(--color-text-secondary)]">课程内容正在从叶脉里慢慢展开。</p>
        </div>
      </section>
    );
  }

  if (status === 'error' || !response) {
    return (
      <section className="leaf-page min-h-screen text-[var(--color-text-primary)] relative overflow-x-hidden flex items-center justify-center" aria-label="叶茂课程加载失败">
        <div className="leaf-ambient-sun" aria-hidden="true" />
        <div className="leaf-paper-canvas" aria-hidden="true" />
        <div className="text-center relative z-10">
          <span className="text-[var(--color-error)] text-sm tracking-widest uppercase mb-2 block">// error</span>
          <h1 className="text-2xl font-medium text-[var(--color-secondary)] mb-2">叶茂数据加载失败</h1>
          <p className="text-[var(--color-text-secondary)]">{errorMessage ?? '请稍后再试。'}</p>
        </div>
      </section>
    );
  }

  const markmapToggleButton = typeof document !== 'undefined'
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
            className="fixed top-[104px] left-0 bg-[var(--glass-bg)] rounded-r-full py-4 pr-6 pl-4 shadow-[var(--shadow-md)] hover:pr-8 transition-[padding,color,background-color,border-color,text-decoration-color,fill,stroke] duration-300 cursor-pointer flex items-center z-50 group border border-l-0 border-[var(--glass-border)]"
          >
            <ChevronRight className="w-6 h-6 text-[var(--color-text-secondary)] group-hover:text-[var(--color-primary)] transition-colors" />
          </motion.button>
        )}
      </AnimatePresence>,
      document.body,
    )
    : null;

  return (
    <section className="leaf-page min-h-screen text-[var(--color-text-primary)] relative overflow-x-hidden flex" aria-label={`${response.course.course_or_chapter_theme}课程内容`}>
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

      <main
        className={`w-full pt-[104px] pb-16 px-6 md:px-16 flex-1 flex justify-center ${markmapCollapsed ? '' : 'md:ml-[360px]'}`}
        style={{ transition: 'margin 0.76s cubic-bezier(0.25, 1, 0.5, 1)' }}
      >
        <div className="w-full max-w-4xl flex flex-col gap-10 pb-[100px]">
          <LeafTopBar
            course={response.course}
            selectedSection={selectedSection}
            generationStatus={liveGenerationStatus}
            liveGenerationMessage={liveGenerationMessage}
            canGenerate={canGenerate}
            onGenerate={handleGenerate}
          />
          <div
            className={markmapCollapsed ? 'mt-8' : 'mt-0'}
            style={{ transition: 'margin 0.76s cubic-bezier(0.25, 1, 0.5, 1)' }}
          >
            <LeafContent
              section={selectedSection}
              composedSection={composedSection}
              lockedReason={response.locked_reason}
            />
          </div>
        </div>
      </main>
    </section>
  );
}
