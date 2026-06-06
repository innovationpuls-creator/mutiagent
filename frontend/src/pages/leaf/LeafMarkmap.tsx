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
    <li className="leaf-markmap-item">
      <div className="leaf-markmap-row" data-selected={isSelected ? 'true' : 'false'}>
        {hasChildren ? (
          <button
            type="button"
            className="leaf-markmap-collapse"
            aria-label={isCollapsed ? '展开章节' : '折叠章节'}
            aria-expanded={!isCollapsed}
            onClick={() => toggleCollapsedSection(
              section.section_id,
              collapsedSectionIds,
              onCollapsedSectionIdsChange,
            )}
          >
            {isCollapsed ? '+' : '−'}
          </button>
        ) : (
          <span className="leaf-markmap-spacer" aria-hidden="true" />
        )}

        <button
          type="button"
          className="leaf-markmap-node"
          onClick={() => onSelectSection(section.section_id)}
        >
          <span className="leaf-markmap-node-label">{getLeafSectionLabel(section.section_id)}</span>
          <span className="leaf-markmap-node-title">{getLeafSectionHeading(section)}</span>
          <span className="leaf-markmap-node-description">{getLeafSectionDescription(section)}</span>
        </button>

        {hasComposedContent ? (
          <span className="leaf-markmap-status" aria-label="已生成内容">*</span>
        ) : null}
      </div>

      {hasChildren && !isCollapsed ? (
        <ol className="leaf-markmap-children">
          {childSections.map((childSection) => (
            <LeafMarkmapNode
              key={childSection.section_id}
              response={response}
              section={childSection}
              selectedSectionId={selectedSectionId}
              collapsedSectionIds={collapsedSectionIds}
              onCollapsedSectionIdsChange={onCollapsedSectionIdsChange}
              onSelectSection={onSelectSection}
            />
          ))}
        </ol>
      ) : null}
    </li>
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
    return (
      <button
        type="button"
        className="leaf-markmap-handle"
        aria-label="展开章节导航"
        onClick={onToggleMarkmapCollapsed}
      >
        <span aria-hidden="true">{'>'}</span>
      </button>
    );
  }

  return (
    <aside className="leaf-markmap" aria-label="章节导航">
      <div className="leaf-markmap-head">
        <div>
          <span className="leaf-eyebrow">// markmap</span>
          <h2>章节叶脉</h2>
        </div>
        <button
          type="button"
          className="leaf-markmap-toggle"
          aria-label="收起章节导航"
          onClick={onToggleMarkmapCollapsed}
        >
          //
        </button>
      </div>

      {topLevelSections.length > 0 ? (
        <ol className="leaf-markmap-list">
          {topLevelSections.map((section) => (
            <LeafMarkmapNode
              key={section.section_id}
              response={response}
              section={section}
              selectedSectionId={selectedSectionId}
              collapsedSectionIds={collapsedSectionIds}
              onCollapsedSectionIdsChange={onCollapsedSectionIdsChange}
              onSelectSection={onSelectSection}
            />
          ))}
        </ol>
      ) : (
        <p className="leaf-empty-text">课程章节还在整理中。</p>
      )}
    </aside>
  );
}
