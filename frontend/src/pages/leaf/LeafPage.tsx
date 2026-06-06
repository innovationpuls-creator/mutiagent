import { useCallback, useEffect, useMemo, useState } from 'react';
import { createPortal, flushSync } from 'react-dom';
import { useParams, useSearchParams } from 'react-router-dom';
import { motion, useReducedMotion } from 'framer-motion';
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
} from './leafContentParser';
import { buildLeafGenerationPrompt } from './leafPrompt';
import {
  LEAF_GENERATION_COMPLETED_EVENT,
  LEAF_GENERATION_EVENT,
  type LeafGenerationEventDetail,
} from './leafGenerationEvents';
import { ChevronRight, PanelLeftClose } from 'lucide-react';
import '../../styles/leaf.css';

type LeafPageStatus = 'idle' | 'loading' | 'ready' | 'error';
const LEAF_NAV_TOGGLE_Z_INDEX = 10000;

interface LeafGenerationCompletedEventDetail {
  courseId: string;
}

function isLeafGenerationCompletedEventDetail(value: unknown): value is LeafGenerationCompletedEventDetail {
  return (
    value !== null
    && typeof value === 'object'
    && 'courseId' in value
    && typeof value.courseId === 'string'
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
): LeafSection | null {
  const firstGeneratableChapter = findLeafSectionById(response.sections, response.first_generatable_chapter_id);
  if (firstGeneratableChapter) return firstGeneratableChapter;
  return getTopLevelSectionForLeaf(response.sections, selectedSection);
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

  const loadLeafCourse = useCallback(async () => {
    if (!token || !courseNodeId) return;
    setStatus('loading');
    setErrorMessage(null);
    try {
      const nextResponse = await fetchLeafCourse(token, courseNodeId);
      setResponse(nextResponse);
      setLiveGenerationStatus(nextResponse.generation_status);
      setStatus('ready');
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : '叶茂数据加载失败');
      setStatus('error');
    }
  }, [courseNodeId, token]);

  useEffect(() => {
    void loadLeafCourse();
  }, [loadLeafCourse]);

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
          status: 'running',
          message: detail.message,
        });
      });
    };

    const handleGenerationCompletedEvent = (event: Event) => {
      const detail = event instanceof CustomEvent ? event.detail : null;
      if (!isLeafGenerationCompletedEventDetail(detail) || detail.courseId !== courseNodeId) return;
      setLiveGenerationMessage(null);
      void loadLeafCourse();
    };

    window.addEventListener(LEAF_GENERATION_EVENT, handleGenerationEvent);
    window.addEventListener(LEAF_GENERATION_COMPLETED_EVENT, handleGenerationCompletedEvent);
    return () => {
      window.removeEventListener(LEAF_GENERATION_EVENT, handleGenerationEvent);
      window.removeEventListener(LEAF_GENERATION_COMPLETED_EVENT, handleGenerationCompletedEvent);
    };
  }, [courseNodeId, loadLeafCourse]);

  const selectedSection = useMemo(() => {
    if (!response) return null;
    return findLeafSectionById(response.sections, selectedSectionId);
  }, [response, selectedSectionId]);

  const composedSection = response ? getLeafComposedSection(response, selectedSectionId) : null;
  const canGenerate = Boolean(
    response
    && response.access_state === 'available'
    && response.can_generate
    && response.course.status !== 'completed',
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
    if (!response) return;
    const generationSection = getGenerationSection(response, selectedSection);
    if (!generationSection) return;
    openWithDraft(buildLeafGenerationPrompt(response.course, generationSection));
  }, [openWithDraft, response, selectedSection]);

  if (!token || !courseNodeId) {
    return null;
  }

  const renderAmbientBackground = () => (
    <div className="fixed top-0 right-0 w-full h-full overflow-hidden -z-10 pointer-events-none">
      <motion.div
        className="absolute top-[-10%] right-[-5%] w-[40vw] h-[40vw] rounded-full mix-blend-multiply filter blur-3xl"
        style={{ backgroundColor: 'var(--color-primary-soft)' }}
        animate={reduceMotion ? {} : { scale: [1, 1.1, 1], x: [0, 10, 0], y: [0, -10, 0], opacity: [0.4, 0.6, 0.4] }}
        transition={{ duration: 8, ease: "easeInOut", repeat: Infinity }}
      />
      <motion.div
        className="absolute bottom-[10%] left-[20%] w-[30vw] h-[30vw] rounded-full mix-blend-multiply filter blur-3xl opacity-30"
        style={{ backgroundColor: 'var(--color-secondary-soft)' }}
        animate={reduceMotion ? {} : { scale: [1, 1.1, 1], x: [0, -10, 0], y: [0, 10, 0], opacity: [0.3, 0.5, 0.3] }}
        transition={{ duration: 10, ease: "easeInOut", repeat: Infinity, delay: 1 }}
      />
    </div>
  );

  if (status === 'loading' || status === 'idle') {
    return (
      <section className="min-h-screen bg-[var(--color-canvas-base)] text-[var(--color-text-primary)] relative overflow-x-hidden flex items-center justify-center" aria-label="叶茂课程加载中">
        {renderAmbientBackground()}
        <div className="text-center">
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
      <section className="min-h-screen bg-[var(--color-canvas-base)] text-[var(--color-text-primary)] relative overflow-x-hidden flex items-center justify-center" aria-label="叶茂课程加载失败">
        {renderAmbientBackground()}
        <div className="text-center">
          <span className="text-[var(--color-error)] text-sm tracking-widest uppercase mb-2 block">// error</span>
          <h1 className="text-2xl font-medium text-[var(--color-secondary)] mb-2">叶茂数据加载失败</h1>
          <p className="text-[var(--color-text-secondary)]">{errorMessage ?? '请稍后再试。'}</p>
        </div>
      </section>
    );
  }

  const markmapToggleButton = typeof document !== 'undefined'
    ? createPortal(
      <button
        aria-label={markmapCollapsed ? '展开章节导航' : '收起章节导航'}
        type="button"
        onClick={() => {
          const nextCollapsed = !markmapCollapsed;
          persistLeafMarkmapCollapsed(nextCollapsed);
          setMarkmapCollapsed(nextCollapsed);
        }}
        className="bg-[var(--color-surface-raised)] rounded-full py-4 px-4 shadow-md transition-all duration-300 cursor-pointer flex items-center group border border-[var(--glass-border)]"
        style={{
          position: 'fixed',
          top: 'calc(var(--space-80) + var(--space-32))',
          left: 'var(--space-16)',
          zIndex: LEAF_NAV_TOGGLE_Z_INDEX,
        }}
      >
        {markmapCollapsed ? (
          <ChevronRight className="w-5 h-5 text-[var(--color-text-secondary)] group-hover:text-[var(--color-primary)] transition-colors" />
        ) : (
          <PanelLeftClose className="w-5 h-5 text-[var(--color-text-secondary)] group-hover:text-[var(--color-primary)] transition-colors" />
        )}
      </button>,
      document.body,
    )
    : null;

  return (
    <section className="min-h-screen bg-[var(--color-canvas-base)] text-[var(--color-text-primary)] relative overflow-x-hidden" aria-label={`${response.course.course_or_chapter_theme}课程内容`}>
      {renderAmbientBackground()}
      {markmapToggleButton}

      {markmapCollapsed ? (
        <>
          <motion.div
            key="collapsed-layout"
            initial={reduceMotion ? false : { opacity: 0, x: -20 }}
            animate={reduceMotion ? undefined : { opacity: 1, x: 0 }}
            transition={motionTokens.editorial}
            className="flex min-h-screen relative"
          >
            <main className="flex-1 w-full max-w-4xl mx-auto py-16 px-6 md:px-16 flex flex-col transition-all duration-500 ease-in-out">
              <LeafTopBar
                course={response.course}
                selectedSection={selectedSection}
                generationStatus={liveGenerationStatus}
                liveGenerationMessage={liveGenerationMessage}
                canGenerate={canGenerate}
                onGenerate={handleGenerate}
              />
              <div className="mt-8">
                <LeafContent
                  section={selectedSection}
                  composedSection={composedSection}
                  lockedReason={response.locked_reason}
                />
              </div>
            </main>
          </motion.div>
        </>
      ) : (
        <motion.div
          key="expanded-layout"
          initial={reduceMotion ? false : { opacity: 0, y: 16 }}
          animate={reduceMotion ? undefined : { opacity: 1, y: 0 }}
          transition={motionTokens.editorial}
          className="flex min-h-[calc(100vh-80px)] pt-6 min-h-screen"
        >
          <LeafMarkmap
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
          />

          <main className="w-full md:ml-[360px] p-4 md:p-10 flex-1 flex flex-col items-center">
            <div className="w-full max-w-4xl flex flex-col gap-8 pb-[100px]">
              <LeafTopBar
                course={response.course}
                selectedSection={selectedSection}
                generationStatus={liveGenerationStatus}
                liveGenerationMessage={liveGenerationMessage}
                canGenerate={canGenerate}
                onGenerate={handleGenerate}
              />
              <LeafContent
                section={selectedSection}
                composedSection={composedSection}
                lockedReason={response.locked_reason}
              />
            </div>
          </main>
        </motion.div>
      )}
    </section>
  );
}
