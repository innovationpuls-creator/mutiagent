import { ChevronDown, ChevronRight, Share2, Lock, PanelLeftClose, ListTree, Check } from 'lucide-react';
import { AnimatePresence, motion, useReducedMotion } from 'framer-motion';
import { motionTokens } from '../../styles/motion-tokens';
import type { LeafCourseResponse, LeafSection } from '../../types/leaf';
import {
  getLeafChildSections,
  getLeafSectionDescription,
  getLeafSectionHeading,
  getLeafSectionLabel,
  hasLeafComposedContent,
} from './leafContentParser';

const MARKMAP_COLLAPSED_STORAGE_KEY = 'mutiagent-leaf-markmap-collapsed';
const SECTION_COLLAPSED_STORAGE_KEY = 'mutiagent-leaf-markmap-section-collapsed';

function readCollapsedSections(): Set<string> {
  try {
    const rawValue = localStorage.getItem(SECTION_COLLAPSED_STORAGE_KEY);
    if (!rawValue) return new Set();
    const parsedValue = JSON.parse(rawValue) as unknown;
    if (!Array.isArray(parsedValue)) return new Set();
    return new Set(parsedValue.filter((item): item is string => typeof item === 'string'));
  } catch {
    return new Set();
  }
}

function writeCollapsedSections(collapsedSectionIds: Set<string>) {
  localStorage.setItem(SECTION_COLLAPSED_STORAGE_KEY, JSON.stringify([...collapsedSectionIds]));
}

function readMarkmapCollapsed(): boolean {
  return localStorage.getItem(MARKMAP_COLLAPSED_STORAGE_KEY) === 'true';
}

function writeMarkmapCollapsed(collapsed: boolean) {
  localStorage.setItem(MARKMAP_COLLAPSED_STORAGE_KEY, String(collapsed));
}

interface LeafMarkmapProps {
  response: LeafCourseResponse;
  selectedSectionId: string | null;
  markmapCollapsed: boolean;
  collapsedSectionIds: Set<string>;
  onToggleMarkmapCollapsed: () => void;
  onCollapsedSectionIdsChange: (collapsedSectionIds: Set<string>) => void;
  onSelectSection: (sectionId: string) => void;
  onGenerateOutline: () => void;
}

interface LeafMarkmapNodeProps {
  response: LeafCourseResponse;
  section: LeafSection;
  selectedSectionId: string | null;
  collapsedSectionIds: Set<string>;
  onCollapsedSectionIdsChange: (collapsedSectionIds: Set<string>) => void;
  onSelectSection: (sectionId: string) => void;
}

export function createInitialCollapsedLeafSections(): Set<string> {
  return readCollapsedSections();
}

export function createInitialLeafMarkmapCollapsed(): boolean {
  return readMarkmapCollapsed();
}

export function persistLeafMarkmapCollapsed(collapsed: boolean) {
  writeMarkmapCollapsed(collapsed);
}

function toggleCollapsedSection(
  sectionId: string,
  collapsedSectionIds: Set<string>,
  onCollapsedSectionIdsChange: (collapsedSectionIds: Set<string>) => void,
) {
  const nextCollapsedSectionIds = new Set(collapsedSectionIds);
  if (nextCollapsedSectionIds.has(sectionId)) {
    nextCollapsedSectionIds.delete(sectionId);
  } else {
    nextCollapsedSectionIds.add(sectionId);
  }
  writeCollapsedSections(nextCollapsedSectionIds);
  onCollapsedSectionIdsChange(nextCollapsedSectionIds);
}

function LeafMarkmapNode({
  response,
  section,
  selectedSectionId,
  collapsedSectionIds,
  onCollapsedSectionIdsChange,
  onSelectSection,
}: LeafMarkmapNodeProps) {
  const childSections = getLeafChildSections(response.sections, section.section_id);
  const isCollapsed = collapsedSectionIds.has(section.section_id);
  const hasChildren = childSections.length > 0;

  // Determine status
  let status: 'running' | 'completed' | 'waiting' | 'neutral' = 'neutral';
  if (section.section_id === selectedSectionId) {
    status = 'running';
  } else if (hasLeafComposedContent(response, section.section_id)) {
    status = 'completed';
  } else if (response.first_generatable_chapter_id === section.section_id) {
    status = 'waiting';
  }

  // Determine content media types of the section (micro-badges)
  const composed = response.section_composed_markdowns[section.section_id];
  const badges: string[] = [];
  if (composed) {
    const hasVideo = composed.blocks.some((b) => b.type === 'video');
    const hasAnimation = composed.blocks.some((b) => b.type === 'animation');
    const hasMarkdown =
      composed.blocks.some((b) => b.type === 'markdown') ||
      (composed.markdown && composed.markdown.trim().length > 0);

    if (hasVideo) {
      badges.push('//');
    }
    if (hasAnimation) {
      badges.push('*');
    }
    if (!hasVideo && !hasAnimation && hasMarkdown) {
      badges.push('+');
    }
  }

  return (
    <div className="relative flex flex-col w-full">
      <div className="relative flex items-center">
        {/* Branch connection line (matches CSS pseudo-element style) */}
        <div className="absolute -left-4 top-1/2 w-4 h-[2px] bg-[var(--color-border)] rounded-sm pointer-events-none"></div>

        <div
          className={`leaf-markmap-card ${status === 'running' ? 'running' : ''}`}
          onClick={() => onSelectSection(section.section_id)}
        >
          <div className="flex items-center gap-2 min-w-0 flex-1">
            {/* Status Indicator */}
            <div className="flex items-center justify-center w-5 h-5 shrink-0">
              {status === 'running' && (
                <span className="w-2.5 h-2.5 rounded-full bg-[var(--status-running)] animate-pulse" />
              )}
              {status === 'completed' && (
                <div className="flex items-center justify-center w-5 h-5 rounded-full bg-[var(--color-success-bg)] text-[var(--color-success)]">
                  <Check className="w-3.5 h-3.5 stroke-[3]" />
                </div>
              )}
              {status === 'waiting' && (
                <span className="w-2.5 h-2.5 rounded-full bg-[var(--status-waiting)]" />
              )}
              {status === 'neutral' && (
                <span className="w-2.5 h-2.5 rounded-full bg-[var(--status-neutral)]" />
              )}
            </div>

            {/* Title */}
            <span
              className={`text-sm truncate font-medium ${
                status === 'running'
                  ? 'text-[var(--color-text-primary)] font-semibold'
                  : 'text-[var(--color-text-secondary)]'
              }`}
            >
              {getLeafSectionHeading(section)}
            </span>

            {/* Micro-badges */}
            {badges.length > 0 && (
              <div className="flex items-center gap-1 shrink-0 ml-1.5">
                {badges.map((badge, i) => (
                  <span
                    key={i}
                    className="px-1.5 py-0.5 text-[10px] font-mono font-bold bg-[var(--color-surface-inset)] text-[var(--color-text-secondary)] rounded-md border border-[var(--color-border)] leading-none select-none"
                  >
                    {badge}
                  </span>
                ))}
              </div>
            )}
          </div>

          {hasChildren && (
            <button
              type="button"
              className="p-1 hover:bg-[var(--color-surface-inset)] rounded-full transition-colors ml-2 shrink-0"
              onClick={(e) => {
                e.stopPropagation();
                toggleCollapsedSection(
                  section.section_id,
                  collapsedSectionIds,
                  onCollapsedSectionIdsChange,
                );
              }}
            >
              {isCollapsed ? <ChevronRight className="w-3 h-3 text-[var(--color-text-secondary)]" /> : <ChevronDown className="w-3 h-3 text-[var(--color-text-secondary)]" />}
            </button>
          )}
        </div>
      </div>

      {hasChildren && !isCollapsed && (
        <div className="ml-6 flex flex-col z-0">
          {childSections.map((childSection, index) => {
            const isLast = index === childSections.length - 1;
            return (
              <div className="pl-4 py-1.5 relative" key={childSection.section_id}>
                <div 
                  className="absolute left-0 top-0 w-[2px] bg-[var(--color-border)]"
                  style={{ height: isLast ? '24px' : '100%' }}
                ></div>
                <LeafMarkmapNode
                  response={response}
                  section={childSection}
                  selectedSectionId={selectedSectionId}
                  collapsedSectionIds={collapsedSectionIds}
                  onCollapsedSectionIdsChange={onCollapsedSectionIdsChange}
                  onSelectSection={onSelectSection}
                />
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

export function LeafMarkmap({
  response,
  selectedSectionId,
  markmapCollapsed,
  collapsedSectionIds,
  onToggleMarkmapCollapsed,
  onCollapsedSectionIdsChange,
  onSelectSection,
  onGenerateOutline,
}: LeafMarkmapProps) {
  const topLevelSections = getLeafChildSections(response.sections, null);
  const reduceMotion = useReducedMotion();

  return (
    <motion.aside
      initial={reduceMotion ? false : { opacity: 0, x: -40 }}
      animate={reduceMotion ? undefined : { opacity: 1, x: 0 }}
      exit={reduceMotion ? undefined : { opacity: 0, x: -40 }}
      transition={motionTokens.editorial}
      className="hidden md:flex flex-col fixed left-6 w-[320px] bg-[var(--glass-bg)] backdrop-blur-xl rounded-2xl shadow-[var(--shadow-lg)] p-6 z-40 top-[104px] bottom-6 border border-[var(--glass-border)]"
    >
      <div className="flex justify-between items-center mb-8">
        <div>
          <h2 className="text-xl font-medium text-[var(--color-text-primary)]">{response.course.course_or_chapter_theme}</h2>
          <p className="text-xs font-bold text-[var(--color-text-secondary)] mt-1">章节导航</p>
        </div>
        <button
          aria-hidden="true"
          tabIndex={-1}
          type="button"
          className="p-1.5 bg-[var(--color-surface-raised)] rounded-full hover:bg-[var(--color-surface-elevated)] transition-colors border border-[var(--glass-border)] shadow-sm"
          onClick={onToggleMarkmapCollapsed}
        >
          <PanelLeftClose className="w-5 h-5 text-[var(--color-text-secondary)]" />
        </button>
      </div>

      <AnimatePresence initial={false}>
        {!response.course.has_outline && (
          <motion.button
            key="outline-draft-button"
            type="button"
            className="leaf-outline-draft-button"
            initial={reduceMotion ? false : { opacity: 0, y: -8 }}
            animate={reduceMotion ? undefined : { opacity: 1, y: 0 }}
            exit={reduceMotion ? undefined : { opacity: 0, y: -8 }}
            transition={motionTokens.editorial}
            onClick={onGenerateOutline}
          >
            <ListTree className="w-4 h-4" />
            <span>生成课程大纲</span>
          </motion.button>
        )}
      </AnimatePresence>

      <div className="flex-1 overflow-y-auto pr-2 custom-scrollbar">
        {topLevelSections.length > 0 ? (
          <div className="flex flex-col relative">
            <div className="bg-[var(--color-primary-soft)] text-[var(--color-primary)] px-6 py-2 rounded-full inline-flex items-center gap-2 shadow-[var(--shadow-sm)] transform transition-transform cursor-pointer w-fit z-10 relative">
              <Share2 className="w-4 h-4" />
              <span className="font-medium text-sm">Course Structure</span>
            </div>

            <div className="ml-10 mt-4 pl-0 flex flex-col relative z-0">
              {topLevelSections.map((section, index) => {
                const isLast = index === topLevelSections.length - 1;
                return (
                  <div className="pl-4 py-1.5 relative" key={section.section_id}>
                    <div 
                      className="absolute left-0 top-0 w-[2px] bg-[var(--color-border)]"
                      style={{ height: isLast ? '24px' : '100%' }}
                    ></div>
                    <LeafMarkmapNode
                      response={response}
                      section={section}
                      selectedSectionId={selectedSectionId}
                      collapsedSectionIds={collapsedSectionIds}
                      onCollapsedSectionIdsChange={onCollapsedSectionIdsChange}
                      onSelectSection={onSelectSection}
                    />
                  </div>
                );
              })}
            </div>

            {response.locked_reason && (
              <div className="mt-8 relative opacity-60">
                <div className="bg-[var(--color-surface-raised)] border-2 border-dashed border-[var(--color-border)] text-[var(--color-text-secondary)] px-6 py-2 rounded-full inline-flex items-center gap-2 cursor-not-allowed w-fit">
                  <Lock className="w-4 h-4" />
                  <span className="font-medium text-sm">未开放</span>
                </div>
              </div>
            )}
          </div>
        ) : (
          <p className="text-[var(--color-text-muted)] text-sm">课程章节还在整理中。</p>
        )}
      </div>
    </motion.aside>
  );
}
