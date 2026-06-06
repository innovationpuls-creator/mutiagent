import { useCallback, useEffect, useMemo, useState } from 'react';
import { flushSync } from 'react-dom';
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
import '../../styles/leaf.css';

type LeafPageStatus = 'idle' | 'loading' | 'ready' | 'error';

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

  if (status === 'loading' || status === 'idle') {
    return (
      <section className="leaf-page leaf-page-loading" aria-label="叶茂课程加载中">
        <div className="leaf-ambient" aria-hidden="true" />
        <div className="leaf-loading-card">
          <span className="leaf-eyebrow">// loading</span>
          <h1>正在铺开这一页</h1>
          <p>课程内容正在从叶脉里慢慢展开。</p>
        </div>
      </section>
    );
  }

  if (status === 'error' || !response) {
    return (
      <section className="leaf-page leaf-page-loading" aria-label="叶茂课程加载失败">
        <div className="leaf-ambient" aria-hidden="true" />
        <div className="leaf-loading-card">
          <span className="leaf-eyebrow">// error</span>
          <h1>叶茂数据加载失败</h1>
          <p>{errorMessage ?? '请稍后再试。'}</p>
        </div>
      </section>
    );
  }

  return (
    <section className="leaf-page" aria-label={`${response.course.course_or_chapter_theme}课程内容`}>
      <div className="leaf-ambient" aria-hidden="true" />
      <motion.div
        className="leaf-shell"
        initial={reduceMotion ? false : { opacity: 0, y: 16 }}
        animate={reduceMotion ? undefined : { opacity: 1, y: 0 }}
        transition={motionTokens.editorial}
      >
        <LeafTopBar
          course={response.course}
          selectedSection={selectedSection}
          generationStatus={liveGenerationStatus}
          liveGenerationMessage={liveGenerationMessage}
          canGenerate={canGenerate}
          onGenerate={handleGenerate}
        />

        <div className="leaf-workspace" data-map-collapsed={markmapCollapsed ? 'true' : 'false'}>
          <LeafMarkmap
            response={response}
            selectedSectionId={selectedSectionId}
            markmapCollapsed={markmapCollapsed}
            collapsedSectionIds={collapsedSectionIds}
            onToggleMarkmapCollapsed={() => {
              setMarkmapCollapsed((current) => {
                const next = !current;
                persistLeafMarkmapCollapsed(next);
                return next;
              });
            }}
            onCollapsedSectionIdsChange={setCollapsedSectionIds}
            onSelectSection={handleSelectSection}
          />

          <LeafContent
            section={selectedSection}
            composedSection={composedSection}
            lockedReason={response.locked_reason}
          />
        </div>
      </motion.div>
    </section>
  );
}
