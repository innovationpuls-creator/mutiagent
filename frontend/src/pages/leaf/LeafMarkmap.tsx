import { ChevronDown, ChevronRight, Share2, Lock, PanelLeftClose } from 'lucide-react';
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
  const isSelected = selectedSectionId === section.section_id;
  const hasChildren = childSections.length > 0;
  const hasComposedContent = hasLeafComposedContent(response, section.section_id);

  return (
    <div className="relative mb-2">
      <div
        className={`px-4 py-2 rounded-full inline-flex items-center gap-2 border cursor-pointer transition-all transform ${
          isSelected
            ? 'bg-[var(--color-primary-soft)] text-[var(--color-primary)] border-[var(--color-primary)] -translate-y-[1px] shadow-sm font-medium'
            : 'bg-[var(--color-surface-raised)] text-[var(--color-text-primary)] border-[var(--glass-border)] hover:border-[var(--color-primary-soft)] hover:-translate-y-[1px]'
        }`}
        onClick={() => onSelectSection(section.section_id)}
      >
        {isSelected ? (
          <span className="w-2 h-2 rounded-full bg-[var(--color-primary)] shrink-0"></span>
        ) : hasComposedContent ? (
          <span className="w-2 h-2 rounded-full bg-[var(--color-success)] shrink-0"></span>
        ) : null}
        <span className="text-sm">{getLeafSectionHeading(section)}</span>
        {hasChildren && (
          <button
            type="button"
            className="p-1 hover:bg-[var(--color-surface-inset)] rounded-full transition-colors ml-1"
            onClick={(e) => {
              e.stopPropagation();
              toggleCollapsedSection(
                section.section_id,
                collapsedSectionIds,
                onCollapsedSectionIdsChange,
              );
            }}
          >
            {isCollapsed ? <ChevronRight className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
          </button>
        )}
      </div>

      {hasChildren && !isCollapsed && (
        <div className="ml-6 mt-3 pl-3 border-l-2 border-[var(--color-border)] flex flex-col gap-3">
          {childSections.map((childSection) => (
            <div className="relative" key={childSection.section_id}>
              {/* Branch connection visual simulation via before pseudo element on parent wrapper */}
              <div className="absolute -left-[14px] top-1/2 w-[12px] h-[2px] bg-[var(--color-border)] rounded-sm"></div>
              <LeafMarkmapNode
                response={response}
                section={childSection}
                selectedSectionId={selectedSectionId}
                collapsedSectionIds={collapsedSectionIds}
                onCollapsedSectionIdsChange={onCollapsedSectionIdsChange}
                onSelectSection={onSelectSection}
              />
            </div>
          ))}
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
}: LeafMarkmapProps) {
  const topLevelSections = getLeafChildSections(response.sections, null);

  if (markmapCollapsed) {
    return null;
  }

  return (
    <aside className="hidden md:flex flex-col fixed left-6 bottom-6 w-[320px] bg-[var(--glass-bg)] backdrop-blur-xl rounded-xl shadow-[var(--shadow-md)] p-6 z-40 top-6 border border-[var(--glass-border)]">
      <div className="flex justify-between items-center mb-8">
        <div>
          <p className="text-lg font-medium text-[var(--color-text-primary)]">{response.course.course_or_chapter_theme}</p>
          <p className="text-sm text-[var(--color-text-muted)] mt-1">章节导航</p>
        </div>
        <button
          aria-hidden="true"
          tabIndex={-1}
          type="button"
          className="p-2 bg-[var(--color-surface-raised)] rounded-full hover:bg-[var(--color-surface-inset)] transition-colors shadow-sm"
          onClick={onToggleMarkmapCollapsed}
        >
          <PanelLeftClose className="w-5 h-5 text-[var(--color-text-secondary)]" />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto pr-2 custom-scrollbar">
        {topLevelSections.length > 0 ? (
          <div className="flex flex-col gap-4">
            <div className="bg-[var(--color-primary-soft)] text-[var(--color-primary)] px-4 py-2 rounded-full inline-flex items-center gap-2 shadow-sm w-fit mb-4">
              <Share2 className="w-4 h-4" />
              <span className="font-medium text-sm">Course Structure</span>
            </div>

            <div className="ml-6 pl-2 border-l-2 border-[var(--color-border)] flex flex-col gap-3">
              {topLevelSections.map((section) => (
                <div className="relative" key={section.section_id}>
                  <div className="absolute -left-[10px] top-1/2 w-[8px] h-[2px] bg-[var(--color-border)] rounded-sm"></div>
                  <LeafMarkmapNode
                    response={response}
                    section={section}
                    selectedSectionId={selectedSectionId}
                    collapsedSectionIds={collapsedSectionIds}
                    onCollapsedSectionIdsChange={onCollapsedSectionIdsChange}
                    onSelectSection={onSelectSection}
                  />
                </div>
              ))}
            </div>

            {response.locked_reason && (
              <div className="mt-8 relative opacity-60">
                <div className="bg-[var(--color-surface-raised)] border-2 border-dashed border-[var(--color-border)] text-[var(--color-text-secondary)] px-4 py-2 rounded-full inline-flex items-center gap-2 cursor-not-allowed w-fit">
                  <Lock className="w-4 h-4" />
                  <span className="font-medium text-sm">Waiting for content</span>
                </div>
              </div>
            )}
          </div>
        ) : (
          <p className="text-[var(--color-text-muted)] text-sm">课程章节还在整理中。</p>
        )}
      </div>
    </aside>
  );
}
