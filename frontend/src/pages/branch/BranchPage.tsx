import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import '../../components/home/BlankPage.css';
import './branch.css';
import { motion, AnimatePresence, useReducedMotion } from 'framer-motion';
import { motionTokens } from '../../styles/motion-tokens';
import { SegmentedControl } from '../../components/ui/SegmentedControl';
import { fetchBranchOverview } from '../../api/branch';
import { fetchProfileDashboard } from '../../api/profile';
import { useAuth } from '../../contexts/AuthContext';
import { profileYearIdFromCurrentGrade } from '../../lib/profileContract';
import type { BranchCourseNode, BranchOverview } from '../../types/branch';
import { PathInitOverlay } from '../../components/onboarding/PathInitOverlay';
import { LEARNING_PATH_UPDATED_EVENT } from '../../onboarding/learningPathFlow';

const YEAR_ORDER = ['year_1', 'year_2', 'year_3', 'year_4'] as const;

const YEAR_LABELS = {
  year_1: '大一',
  year_2: '大二',
  year_3: '大三',
  year_4: '大四',
} as const;

type YearId = keyof typeof YEAR_LABELS;
type StageSlot = 'left' | 'center' | 'right';

interface LoadOverviewOptions {
  background?: boolean;
  shouldIgnore?: () => boolean;
}

interface StageCourse {
  slot: StageSlot;
  course: BranchCourseNode;
}

interface StageCourseSet {
  left: BranchCourseNode | null;
  center: BranchCourseNode | null;
  right: BranchCourseNode | null;
}

function statusLabel(status: BranchCourseNode['status']): string {
  switch (status) {
    case 'completed':
      return '已完成';
    case 'current':
      return '进行中';
    default:
      return '未开放';
  }
}

function focusLabel(status: BranchCourseNode['status']): string {
  switch (status) {
    case 'completed':
      return '已完成';
    case 'current':
      return '当前焦点';
    default:
      return '未开放';
  }
}

function iconLabel(status: BranchCourseNode['status']): string {
  switch (status) {
    case 'completed':
      return 'completed';
    case 'current':
      return 'current';
    default:
      return 'locked';
  }
}

function courseSourceLabel(course: BranchCourseNode): string {
  return course.is_custom ? '自选课程' : '人培课程';
}

function CourseSourceBadge({ course }: { course: BranchCourseNode }) {
  const sourceClassName = course.is_custom
    ? 'branch-course-source-badge-custom'
    : 'branch-course-source-badge-self';

  return (
    <span className={`branch-course-source-badge ${sourceClassName}`}>
      {courseSourceLabel(course)}
    </span>
  );
}

function defaultFocusCourseId(courses: BranchCourseNode[], currentCourseId: string | null): string | null {
  if (courses.length === 0) {
    return null;
  }

  const currentIndex = courses.findIndex((course) => course.status === 'current');
  const currentCourseIndex = currentCourseId
    ? courses.findIndex((course) => course.course_node_id === currentCourseId)
    : -1;
  const firstOutlinedIndex = courses.findIndex((course) => course.has_outline);
  const focusIndex = currentIndex >= 0
    ? currentIndex
    : (currentCourseIndex >= 0 ? currentCourseIndex : (firstOutlinedIndex >= 0 ? firstOutlinedIndex : 0));

  return courses[focusIndex]?.course_node_id ?? null;
}

function resolveFocusIndex(
  courses: BranchCourseNode[],
  currentCourseId: string | null,
  focusedCourseId: string | null,
): number {
  if (focusedCourseId) {
    const focusedIndex = courses.findIndex((course) => course.course_node_id === focusedCourseId);
    if (focusedIndex >= 0) {
      return focusedIndex;
    }
  }

  const fallbackCourseId = defaultFocusCourseId(courses, currentCourseId);
  return fallbackCourseId
    ? courses.findIndex((course) => course.course_node_id === fallbackCourseId)
    : -1;
}

function pickStageCourses(
  courses: BranchCourseNode[],
  currentCourseId: string | null,
  focusedCourseId: string | null,
): StageCourse[] {
  if (courses.length === 0) {
    return [];
  }

  const focusIndex = resolveFocusIndex(courses, currentCourseId, focusedCourseId);
  if (focusIndex < 0) {
    return [];
  }

  const stageCourses: StageCourse[] = [];
  const leftCourse = focusIndex > 0 ? courses[focusIndex - 1] : null;
  const centerCourse = courses[focusIndex] ?? null;
  const rightCourse = focusIndex < courses.length - 1 ? courses[focusIndex + 1] : null;

  if (leftCourse) {
    stageCourses.push({ slot: 'left', course: leftCourse });
  }
  if (centerCourse) {
    stageCourses.push({ slot: 'center', course: centerCourse });
  }
  if (rightCourse) {
    stageCourses.push({ slot: 'right', course: rightCourse });
  }

  return stageCourses;
}

function stageLabel(courseCount: number): string {
  return `这一学年共 ${courseCount} 门课程，按顺序慢慢推进。`;
}

function railAriaLabel(gradeName: string, index: number, course: BranchCourseNode): string {
  const source = courseSourceLabel(course);
  return `${gradeName}第 ${index + 1} 门课程（${source}）：${course.course_or_chapter_theme}，${statusLabel(course.status)}`;
}

function toStageCourseSet(stageCourses: StageCourse[]): StageCourseSet {
  let left: BranchCourseNode | null = null;
  let center: BranchCourseNode | null = null;
  let right: BranchCourseNode | null = null;

  for (const item of stageCourses) {
    if (item.slot === 'left') {
      left = item.course;
    } else if (item.slot === 'center') {
      center = item.course;
    } else {
      right = item.course;
    }
  }

  return { left, center, right };
}

function getCourseCoordinate(
  courseId: string,
  coursesList: BranchCourseNode[],
  focusedId: string | null,
  currentId: string | null,
): { x: number; y: number } {
  const stageCourses = pickStageCourses(coursesList, currentId, focusedId);
  const stage = toStageCourseSet(stageCourses);
  if (stage.left?.course_node_id === courseId) return { x: 100, y: 200 };
  if (stage.center?.course_node_id === courseId) return { x: 500, y: 250 };
  if (stage.right?.course_node_id === courseId) return { x: 900, y: 300 };
  const idx = coursesList.findIndex(c => c.course_node_id === courseId);
  const focusIdx = resolveFocusIndex(coursesList, currentId, focusedId);
  if (idx < focusIdx) return { x: -100, y: 200 };
  return { x: 1100, y: 300 };
}

function generateBezierConnectionPath(fromPt: { x: number; y: number }, toPt: { x: number; y: number }): string {
  const cp1 = { x: fromPt.x + (toPt.x - fromPt.x) * 0.5, y: fromPt.y };
  const cp2 = { x: fromPt.x + (toPt.x - fromPt.x) * 0.5, y: toPt.y };
  return `M ${fromPt.x} ${fromPt.y} C ${cp1.x} ${cp1.y}, ${cp2.x} ${cp2.y}, ${toPt.x} ${toPt.y}`;
}

function getCurrentCourseFromOverview(overview: BranchOverview | null): BranchCourseNode | null {
  if (!overview) return null;
  for (const yearId of YEAR_ORDER) {
    const year = overview.years[yearId];
    if (!year) continue;
    const currentCourse = year.current_course_id
      ? year.courses.find((course) => course.course_node_id === year.current_course_id)
      : null;
    if (currentCourse) return currentCourse;
    const fallbackCurrent = year.courses.find((course) => course.status === 'current');
    if (fallbackCurrent) return fallbackCurrent;
  }
  return null;
}

function yearIdFromProfileGrade(currentGrade: string): YearId | null {
  return profileYearIdFromCurrentGrade(currentGrade);
}

function MascotBlob() {
  return (
    <svg aria-hidden="true" className="branch-mascot-svg" viewBox="0 0 120 120">
      <path
        className="branch-mascot-body"
        d="M60 18C84 18 96 36 96 58C96 82 78 98 60 98C38 98 20 84 20 58C20 36 34 18 60 18Z"
      />
      <circle cx="46" cy="52" r="4" className="branch-mascot-face" />
      <circle cx="74" cy="52" r="4" className="branch-mascot-face" />
      <ellipse cx="38" cy="62" rx="6" ry="4" className="branch-mascot-cheek" />
      <ellipse cx="82" cy="62" rx="6" ry="4" className="branch-mascot-cheek" />
      <path d="M47 70C51 76 56 79 60 79C64 79 69 76 73 70" className="branch-mascot-smile" />
    </svg>
  );
}

function StageIcon({ kind }: { kind: string }) {
  if (kind === 'completed') {
    return (
      <svg aria-hidden="true" className="branch-stage-icon-svg" viewBox="0 0 48 48">
        <path d="M18 24.5L22 28.5L30 19.5" className="branch-stage-icon-stroke" />
      </svg>
    );
  }

  if (kind === 'current') {
    return (
      <svg aria-hidden="true" className="branch-stage-icon-svg" viewBox="0 0 48 48">
        <circle cx="24" cy="24" r="8" className="branch-stage-icon-stroke" />
        <circle cx="16" cy="18" r="2.2" className="branch-stage-icon-stroke branch-stage-icon-dot" />
        <circle cx="32" cy="18" r="2.2" className="branch-stage-icon-stroke branch-stage-icon-dot" />
        <circle cx="24" cy="32" r="2.2" className="branch-stage-icon-stroke branch-stage-icon-dot" />
      </svg>
    );
  }

  return (
    <svg aria-hidden="true" className="branch-stage-icon-svg" viewBox="0 0 48 48">
      <rect x="14" y="21" width="20" height="14" rx="4" className="branch-stage-icon-stroke" />
      <path d="M18 21V17C18 13.7 20.7 11 24 11C27.3 11 30 13.7 30 17V21" className="branch-stage-icon-stroke" />
    </svg>
  );
}

interface Point {
  x: number;
  y: number;
}

function bezierPoint(p0: Point, p1: Point, p2: Point, p3: Point, t: number): Point {
  const oneMinusT = 1 - t;
  const mt2 = oneMinusT * oneMinusT;
  const mt3 = mt2 * oneMinusT;
  const t2 = t * t;
  const t3 = t2 * t;
  return {
    x: mt3 * p0.x + 3 * mt2 * t * p1.x + 3 * oneMinusT * t2 * p2.x + t3 * p3.x,
    y: mt3 * p0.y + 3 * mt2 * t * p1.y + 3 * oneMinusT * t2 * p2.y + t3 * p3.y,
  };
}

function getBezierTangent(p0: Point, p1: Point, p2: Point, p3: Point, t: number): Point {
  const oneMinusT = 1 - t;
  const mt2 = oneMinusT * oneMinusT;
  const t2 = t * t;
  const dx = 3 * mt2 * (p1.x - p0.x) + 6 * oneMinusT * t * (p2.x - p1.x) + 3 * t2 * (p3.x - p2.x);
  const dy = 3 * mt2 * (p1.y - p0.y) + 6 * oneMinusT * t * (p2.y - p1.y) + 3 * t2 * (p3.y - p2.y);
  return { x: dx, y: dy };
}

function generateWigglySegment(
  p0: Point,
  p1: Point,
  p2: Point,
  p3: Point,
  steps = 50,
  offsetAmp = 8,
  freq1 = 4,
  freq2 = 10,
): Point[] {
  const points: Point[] = [];
  for (let i = 0; i <= steps; i++) {
    const t = i / steps;
    const pt = bezierPoint(p0, p1, p2, p3, t);

    if (t > 0.02 && t < 0.98) {
      const tangent = getBezierTangent(p0, p1, p2, p3, t);
      const len = Math.sqrt(tangent.x * tangent.x + tangent.y * tangent.y);
      if (len > 0) {
        const nx = -tangent.y / len;
        const ny = tangent.x / len;
        const wiggle = Math.sin(t * Math.PI * freq1) * Math.cos(t * Math.PI * freq2);
        const fade = Math.sin(t * Math.PI);
        const offset = wiggle * offsetAmp * fade;
        pt.x += nx * offset;
        pt.y += ny * offset;
      }
    }
    points.push(pt);
  }
  return points;
}

function pointsToPath(points: Point[]): string {
  if (points.length === 0) return '';
  let d = `M ${points[0].x.toFixed(1)} ${points[0].y.toFixed(1)}`;
  for (let i = 1; i < points.length; i++) {
    d += ` L ${points[i].x.toFixed(1)} ${points[i].y.toFixed(1)}`;
  }
  return d;
}

function generateTendrilPath(startPt: Point, normal: Point, length = 50, dir = 1): string {
  const p0 = startPt;
  const p1 = {
    x: startPt.x + normal.x * length * 0.4,
    y: startPt.y + normal.y * length * 0.4,
  };
  const p2 = {
    x: p1.x + (normal.y * dir) * length * 0.4,
    y: p1.y - (normal.x * dir) * length * 0.4,
  };
  const p3 = {
    x: p2.x - normal.x * length * 0.2,
    y: p2.y - normal.y * length * 0.2,
  };

  const points: Point[] = [];
  for (let i = 0; i <= 15; i++) {
    const t = i / 15;
    points.push(bezierPoint(p0, p1, p2, p3, t));
  }
  return pointsToPath(points);
}

function VineLeaf({ point, tangent, scale = 1 }: { point: Point; tangent: Point; scale?: number }) {
  const angle = Math.atan2(tangent.y, tangent.x) * (180 / Math.PI);
  return (
    <path
      d="M 0 0 C 8 -8, 16 -4, 20 0 C 16 4, 8 8, 0 0"
      fill="oklch(78% 0.06 140 / 0.48)"
      stroke="oklch(74% 0.08 140 / 0.68)"
      strokeWidth={1.2}
      transform={`translate(${point.x}, ${point.y}) rotate(${angle}) scale(${scale})`}
      style={{ transformOrigin: '0px 0px', transition: 'all 0.3s ease' }}
    />
  );
}

const seg1_p0 = { x: 0, y: 200 };
const seg1_p1 = { x: 250, y: 200 };
const seg1_p2 = { x: 300, y: 250 };
const seg1_p3 = { x: 500, y: 250 };

const seg2_p0 = { x: 500, y: 250 };
const seg2_p1 = { x: 700, y: 250 };
const seg2_p2 = { x: 750, y: 300 };
const seg2_p3 = { x: 1000, y: 300 };

const points1 = generateWigglySegment(seg1_p0, seg1_p1, seg1_p2, seg1_p3, 50, 7, 3.5, 9);
const points2 = generateWigglySegment(seg2_p0, seg2_p1, seg2_p2, seg2_p3, 50, 7, 3.5, 9);

const mainVinePoints = [...points1, ...points2.slice(1)];
const mainVinePath = pointsToPath(mainVinePoints);

const tangent1 = getBezierTangent(seg1_p0, seg1_p1, seg1_p2, seg1_p3, 0.35);
const len1 = Math.sqrt(tangent1.x * tangent1.x + tangent1.y * tangent1.y);
const normal1 = len1 > 0 ? { x: -tangent1.y / len1, y: tangent1.x / len1 } : { x: 0, y: 0 };
const tendril1Path = generateTendrilPath(points1[18], normal1, 40, 1);

const tangent2 = getBezierTangent(seg2_p0, seg2_p1, seg2_p2, seg2_p3, 0.65);
const len2 = Math.sqrt(tangent2.x * tangent2.x + tangent2.y * tangent2.y);
const normal2 = len2 > 0 ? { x: -tangent2.y / len2, y: tangent2.x / len2 } : { x: 0, y: 0 };
const tendril2Path = generateTendrilPath(points2[32], { x: -normal2.x, y: -normal2.y }, 35, -1);

function PathSession({
  gradeName,
  courses,
  currentCourseId,
  onOpenCourse,
  showCoachmark,
  onCloseCoachmark,
  allCourses = [],
}: {
  gradeName: string;
  courses: BranchCourseNode[];
  currentCourseId: string | null;
  onOpenCourse: (course: BranchCourseNode) => void;
  showCoachmark?: boolean;
  onCloseCoachmark?: () => void;
  allCourses?: BranchCourseNode[];
}) {
  const reduceMotion = useReducedMotion();

  const resolvedCourses = useMemo(() => {
    return courses.map((c) => {
      if (c.is_custom && c.parent_preset_id) {
        const parent = allCourses.find((pc) => pc.course_node_id === c.parent_preset_id);
        if (parent && parent.status === 'completed' && c.status === 'locked') {
          return { ...c, status: 'current' as const };
        }
      }
      return c;
    });
  }, [courses, allCourses]);

  const [focusedCourseId, setFocusedCourseId] = useState<string | null>(() =>
    defaultFocusCourseId(resolvedCourses, currentCourseId),
  );
  const [lockedCourseHint, setLockedCourseHint] = useState<string | null>(null);

  useEffect(() => {
    const nextDefaultFocusCourseId = defaultFocusCourseId(resolvedCourses, currentCourseId);
    setFocusedCourseId((currentFocusedCourseId) => {
      if (
        currentFocusedCourseId
        && resolvedCourses.some((course) => course.course_node_id === currentFocusedCourseId)
      ) {
        return currentFocusedCourseId;
      }
      return nextDefaultFocusCourseId;
    });
    setLockedCourseHint(null);
  }, [resolvedCourses, currentCourseId]);

  useEffect(() => {
    if (!showCoachmark || !onCloseCoachmark) return undefined;
    
    const handleWindowClick = () => {
      onCloseCoachmark();
    };
    
    const timer = setTimeout(() => {
      window.addEventListener('click', handleWindowClick);
    }, 10);

    return () => {
      clearTimeout(timer);
      window.removeEventListener('click', handleWindowClick);
    };
  }, [showCoachmark, onCloseCoachmark]);

  const stageCourses = pickStageCourses(resolvedCourses, currentCourseId, focusedCourseId);
  const stage = toStageCourseSet(stageCourses);

  function courseIndex(course: BranchCourseNode): number {
    return resolvedCourses.findIndex((item) => item.course_node_id === course.course_node_id);
  }

  function courseButtonLabel(course: BranchCourseNode): string {
    return railAriaLabel(gradeName, courseIndex(course), course);
  }

  function handleCourseClick(course: BranchCourseNode): void {
    if (showCoachmark && onCloseCoachmark) {
      onCloseCoachmark();
    }
    if (focusedCourseId !== course.course_node_id) {
      setFocusedCourseId(course.course_node_id);
      if (course.status === 'completed' || course.status === 'current') {
        setLockedCourseHint(null);
      } else {
        setLockedCourseHint(`「${course.course_or_chapter_theme}」还未开放，先完成前面的课程。`);
      }
      return;
    }
    if (course.status === 'completed' || course.status === 'current') {
      setLockedCourseHint(null);
      onOpenCourse(course);
      return;
    }
    setLockedCourseHint(`「${course.course_or_chapter_theme}」还未开放，先完成前面的课程。`);
  }

  const highlightPaths = useMemo(() => {
    if (!focusedCourseId) return [];
    const focusedCourse = resolvedCourses.find(c => c.course_node_id === focusedCourseId);
    if (!focusedCourse) return [];

    const connections: { from: string; to: string }[] = [];
    const seenFrom = new Set<string>();

    if (focusedCourse.parent_preset_id) {
      connections.push({ from: focusedCourse.parent_preset_id, to: focusedCourseId });
      seenFrom.add(focusedCourse.parent_preset_id);
    }
    if (focusedCourse.prerequisite_ids) {
      focusedCourse.prerequisite_ids.forEach((prereqId) => {
        if (!seenFrom.has(prereqId)) {
          connections.push({ from: prereqId, to: focusedCourseId });
          seenFrom.add(prereqId);
        }
      });
    }

    return connections.map(({ from, to }) => {
      const fromPt = getCourseCoordinate(from, resolvedCourses, focusedCourseId, currentCourseId);
      const toPt = getCourseCoordinate(to, resolvedCourses, focusedCourseId, currentCourseId);
      const d = generateBezierConnectionPath(fromPt, toPt);
      return { d, key: `highlight-path-${from}-${to}` };
    });
  }, [focusedCourseId, resolvedCourses, currentCourseId]);

  return (
    <section className="branch-session" aria-label={`${gradeName}课程路径`}>
      <div className="branch-session-header">
        <h1 className="branch-session-title">你的路径</h1>
        <p className="branch-session-subtitle">慢一点，你正在稳稳向前。</p>
        {resolvedCourses.length > 0 ? (
          <p className="branch-session-caption">{stageLabel(resolvedCourses.length)}</p>
        ) : null}
      </div>

      <div className="branch-stage">
        <div className="branch-stage-particle branch-stage-particle-1" aria-hidden="true" />
        <div className="branch-stage-particle branch-stage-particle-2" aria-hidden="true" />
        <div className="branch-stage-particle branch-stage-particle-3" aria-hidden="true" />
        <div className="branch-stage-particle branch-stage-particle-4" aria-hidden="true" />
        <div className="branch-stage-particle branch-stage-particle-5" aria-hidden="true" />

        {stageCourses.length > 0 ? (
          <div className="branch-stage-canvas">
            <svg className="branch-stage-curve" aria-hidden="true" viewBox="0 0 1000 500" preserveAspectRatio="none">
              {/* Drop-shadow glow behind the main vine */}
              <path
                d={mainVinePath}
                fill="none"
                stroke="oklch(78% 0.06 140 / 0.15)"
                strokeWidth={8}
                strokeLinecap="round"
              />
              
              {/* Main organic Vine stem */}
              <path
                d={mainVinePath}
                fill="none"
                stroke="oklch(78% 0.06 140 / 0.65)"
                strokeWidth={4.5}
                strokeLinecap="round"
              />

              {/* A secondary thin winding fiber to add organic complexity */}
              <path
                d={mainVinePath}
                fill="none"
                stroke="oklch(80% 0.09 56 / 0.45)"
                strokeWidth={1.5}
                strokeLinecap="round"
                strokeDasharray="6 8"
              />

              {/* Tendril 1 */}
              <path
                d={tendril1Path}
                fill="none"
                stroke="oklch(78% 0.06 140 / 0.48)"
                strokeWidth={2}
                strokeLinecap="round"
              />

              {/* Tendril 2 */}
              <path
                d={tendril2Path}
                fill="none"
                stroke="oklch(78% 0.06 140 / 0.48)"
                strokeWidth={2}
                strokeLinecap="round"
              />

              {/* Vine Leaves */}
              <VineLeaf point={points1[10]} tangent={getBezierTangent(seg1_p0, seg1_p1, seg1_p2, seg1_p3, 0.2)} scale={0.8} />
              <VineLeaf point={points1[28]} tangent={getBezierTangent(seg1_p0, seg1_p1, seg1_p2, seg1_p3, 0.55)} scale={0.7} />
              <VineLeaf point={points2[22]} tangent={getBezierTangent(seg2_p0, seg2_p1, seg2_p2, seg2_p3, 0.45)} scale={0.85} />
              <VineLeaf point={points2[40]} tangent={getBezierTangent(seg2_p0, seg2_p1, seg2_p2, seg2_p3, 0.8)} scale={0.75} />

              {/* Flowing micro-particles (disabled when prefers-reduced-motion is true) */}
              {!reduceMotion && (
                <>
                  <circle r="3.5" fill="oklch(80% 0.09 56 / 0.85)">
                    <animateMotion
                      path={mainVinePath}
                      dur="14s"
                      repeatCount="indefinite"
                    />
                  </circle>
                  <circle r="2.5" fill="oklch(78% 0.06 140 / 0.85)">
                    <animateMotion
                      path={mainVinePath}
                      dur="20s"
                      begin="7s"
                      repeatCount="indefinite"
                    />
                  </circle>
                </>
              )}

              {/* Highlight connection paths */}
              {highlightPaths.map(({ d, key }) => (
                <path
                  key={key}
                  d={d}
                  fill="none"
                  data-testid="branch-highlight-path"
                  className="branch-highlight-path"
                />
              ))}
            </svg>
            <div className="branch-stage-layout">
              {stage.left ? (
                <div className="branch-stage-slot branch-stage-slot-left">
                  <motion.button
                    className={`branch-blob-card branch-blob-card-${iconLabel(stage.left.status)} ${stage.left.is_custom ? 'branch-blob-card-custom' : ''}`}
                    type="button"
                    aria-label={courseButtonLabel(stage.left)}
                    aria-pressed={stage.left.course_node_id === focusedCourseId}
                    whileHover={reduceMotion ? undefined : { y: -5, scale: 1.05 }}
                    whileTap={reduceMotion ? undefined : { y: -1, scale: 1.01 }}
                    transition={motionTokens.lazy}
                    onClick={() => handleCourseClick(stage.left as BranchCourseNode)}
                  >
                    <div className={`branch-blob-icon branch-blob-icon-${iconLabel(stage.left.status)}`} aria-hidden="true">
                      <StageIcon kind={iconLabel(stage.left.status)} />
                      {stage.left.is_custom && <span className="branch-custom-glow-dot" aria-hidden="true" />}
                    </div>
                    <div className="branch-blob-text">
                      <CourseSourceBadge course={stage.left} />
                      <h2 className="branch-blob-title">{stage.left.course_or_chapter_theme}</h2>
                      <p className={`branch-blob-status branch-blob-status-${iconLabel(stage.left.status)}`}>{statusLabel(stage.left.status)}</p>
                    </div>
                  </motion.button>
                </div>
              ) : null}

              {stage.center ? (
                <div className="branch-stage-slot branch-stage-slot-center branch-node-center" style={{ position: 'relative' }}>
                  <div className="branch-mascot" aria-hidden="true">
                    <MascotBlob />
                  </div>
                  {showCoachmark && (
                    <div className="leaf-coachmark-balloon" onClick={onCloseCoachmark}>
                      <span>✨ 点击此处，开启第一章学习</span>
                      <div className="balloon-arrow" />
                    </div>
                  )}
                  <motion.article
                    className="branch-blob-card-shell"
                  >
                    {iconLabel(stage.center.status) === 'current' && (
                      <div className="branch-current-glow" aria-hidden="true" />
                    )}
                    <motion.button
                      className={`branch-blob-card branch-blob-card-${iconLabel(stage.center.status)} ${stage.center.is_custom ? 'branch-blob-card-custom' : ''}`}
                      type="button"
                      aria-label={courseButtonLabel(stage.center)}
                      aria-pressed={stage.center.course_node_id === focusedCourseId}
                      whileHover={reduceMotion ? undefined : { y: -5, scale: 1.02 }}
                      whileTap={reduceMotion ? undefined : { y: -1, scale: 1.005 }}
                      transition={motionTokens.lazy}
                      onClick={() => handleCourseClick(stage.center as BranchCourseNode)}
                    >
                      <div className="branch-blob-copy-current">
                        <div className={`branch-blob-icon branch-blob-icon-${iconLabel(stage.center.status)}`} aria-hidden="true">
                          <StageIcon kind={iconLabel(stage.center.status)} />
                          {stage.center.is_custom && <span className="branch-custom-glow-dot" aria-hidden="true" />}
                        </div>
                        <div className="branch-blob-text">
                          <span className="branch-blob-eyebrow">{focusLabel(stage.center.status)}</span>
                          <CourseSourceBadge course={stage.center} />
                          <h2 className="branch-blob-title branch-blob-title-current">
                            {stage.center.course_or_chapter_theme}
                          </h2>
                        </div>
                      </div>
                      {(stage.center.status === 'current' || stage.center.status === 'completed') && (
                        <motion.span
                          className="branch-focus-button"
                          whileHover={reduceMotion ? undefined : { y: -2 }}
                          whileTap={reduceMotion ? undefined : { y: 0, scale: 0.992 }}
                          transition={motionTokens.lazy}
                        >
                          <span>专注模式</span>
                          <motion.span
                            className="branch-focus-button-arrow"
                            aria-hidden="true"
                            whileHover={reduceMotion ? undefined : { x: 4 }}
                            transition={motionTokens.lazy}
                          >
                            →
                          </motion.span>
                        </motion.span>
                      )}
                    </motion.button>
                  </motion.article>
                </div>
              ) : null}

              {stage.right ? (
                <div className="branch-stage-slot branch-stage-slot-right">
                  <motion.button
                    className={`branch-blob-card branch-blob-card-${iconLabel(stage.right.status)} ${stage.right.is_custom ? 'branch-blob-card-custom' : ''}`}
                    type="button"
                    aria-label={courseButtonLabel(stage.right)}
                    aria-pressed={stage.right.course_node_id === focusedCourseId}
                    whileHover={reduceMotion ? undefined : { y: -3, scale: 1.02 }}
                    whileTap={reduceMotion ? undefined : { y: -1, scale: 0.995 }}
                    transition={motionTokens.lazy}
                    onClick={() => handleCourseClick(stage.right as BranchCourseNode)}
                  >
                    <div className={`branch-blob-icon branch-blob-icon-${iconLabel(stage.right.status)}`} aria-hidden="true">
                      <StageIcon kind={iconLabel(stage.right.status)} />
                      {stage.right.is_custom && <span className="branch-custom-glow-dot" aria-hidden="true" />}
                    </div>
                    <div className="branch-blob-text">
                      <CourseSourceBadge course={stage.right} />
                      <h2 className="branch-blob-title">{stage.right.course_or_chapter_theme}</h2>
                      <p className={`branch-blob-status branch-blob-status-${iconLabel(stage.right.status)}`}>{statusLabel(stage.right.status)}</p>
                    </div>
                  </motion.button>
                </div>
              ) : null}
            </div>
          </div>
        ) : (
          <div className="branch-stage-empty">
            <p className="branch-stage-empty-title">这个年级还没有课程路径</p>
            <span className="branch-stage-empty-text">生成课程后，这里会展示该年级自己的学习节奏。</span>
          </div>
        )}
      </div>

      {lockedCourseHint ? (
        <p className="branch-course-rail-hint" role="status">{lockedCourseHint}</p>
      ) : null}

    </section>
  );
}

export function BranchPage() {
  const reduceMotion = useReducedMotion();
  const navigate = useNavigate();
  const location = useLocation();
  const { token, isAuthReady } = useAuth();
  const [overview, setOverview] = useState<BranchOverview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeYear, setActiveYear] = useState<YearId>('year_1');
  const [showPathOverlay, setShowPathOverlay] = useState(() => {
    return location.state?.justGeneratedProfile === true;
  });
  const [showCoachmark, setShowCoachmark] = useState(false);
  const isMountedRef = useRef(true);

  const loadOverview = useCallback(async (options?: LoadOverviewOptions) => {
      if (!isAuthReady) {
        return;
      }

      if (!token) {
        setOverview(null);
        setLoading(false);
        setError('登录后可查看课程路径。');
        return;
      }

      if (!options?.background) {
        setLoading(true);
        setError(null);
      }

      try {
        const [nextOverview, dashboard] = await Promise.all([
          fetchBranchOverview(token),
          fetchProfileDashboard(token),
        ]);

        const storedProgram = localStorage.getItem('teacher_cultivation_program');
        if (storedProgram) {
          try {
            const presetCourses: BranchCourseNode[] = JSON.parse(storedProgram);
            presetCourses.forEach((preset) => {
              const sem = parseInt(preset.time_arrangement?.semester_scope || '1', 10);
              let yearId: 'year_1' | 'year_2' | 'year_3' | 'year_4' = 'year_1';
              if (sem >= 7) yearId = 'year_4';
              else if (sem >= 5) yearId = 'year_3';
              else if (sem >= 3) yearId = 'year_2';

              const year = nextOverview.years[yearId];
              if (year) {
                const existIdx = year.courses.findIndex((c) => c.course_node_id === preset.course_node_id);
                if (existIdx >= 0) {
                  year.courses[existIdx] = {
                    ...preset,
                    ...year.courses[existIdx], // API fields override preset ones
                    key_points: preset.key_points,
                    difficult_points: preset.difficult_points,
                    acceptance_criteria: preset.acceptance_criteria,
                  };
                } else {
                  year.courses.push(preset);
                }
                year.has_courses = true;
                year.is_clickable = true;
              }
            });
          } catch (e) {
            // ignore parsing errors
          }
        }

        if (!isMountedRef.current || options?.shouldIgnore?.()) {
          return;
        }
        setOverview(nextOverview);
        const mappedProfileYear = yearIdFromProfileGrade(dashboard.profile.currentGrade);
        const firstClickable = YEAR_ORDER.find((yearId) => nextOverview.years[yearId]?.is_clickable);
        const preferredYear = mappedProfileYear && nextOverview.years[mappedProfileYear]?.is_clickable
          ? mappedProfileYear
          : null;
        setActiveYear((currentYear) => (
          options?.background && nextOverview.years[currentYear]?.is_clickable
            ? currentYear
            : preferredYear ?? firstClickable ?? 'year_1'
        ));
      } catch (loadError) {
        if (!isMountedRef.current || options?.shouldIgnore?.()) {
          return;
        }
        const message = loadError instanceof Error ? loadError.message : '课程路径加载失败';
        setOverview(null);
        setError(message);
      } finally {
        if (!options?.background && isMountedRef.current && !options?.shouldIgnore?.()) {
          setLoading(false);
        }
      }
  }, [isAuthReady, token]);

  useEffect(() => {
    let cancelled = false;
    isMountedRef.current = true;
    void loadOverview({ shouldIgnore: () => cancelled });
    return () => {
      cancelled = true;
      isMountedRef.current = false;
    };
  }, [loadOverview]);

  useEffect(() => {
    const handleLearningPathUpdated = () => {
      void loadOverview({ background: true });
    };

    window.addEventListener(LEARNING_PATH_UPDATED_EVENT, handleLearningPathUpdated);
    return () => {
      window.removeEventListener(LEARNING_PATH_UPDATED_EVENT, handleLearningPathUpdated);
    };
  }, [loadOverview]);

  const options = YEAR_ORDER.map((yearId) => overview?.years[yearId]?.grade_name ?? YEAR_LABELS[yearId]);
  const labelToYearId = Object.fromEntries(
    YEAR_ORDER.map((yearId, index) => [options[index], yearId]),
  ) as Record<string, YearId>;
  const disabledOptions = YEAR_ORDER
    .filter((yearId) => !(overview?.years[yearId]?.is_clickable ?? false))
    .map((yearId) => overview?.years[yearId]?.grade_name ?? YEAR_LABELS[yearId]);
  const activeLabel = overview?.years[activeYear]?.grade_name ?? YEAR_LABELS[activeYear];
  const activeYearData = overview?.years[activeYear] ?? null;
  const currentCourse = getCurrentCourseFromOverview(overview);

  return (
    <>
      <motion.main
        className="home-page"
        initial={reduceMotion ? false : { opacity: 0 }}
        animate={reduceMotion ? undefined : { opacity: 1 }}
        exit={reduceMotion ? { opacity: 0 } : { opacity: 0, transition: { duration: 0.4 } }}
      >
      <div className="home-ambient-sun" aria-hidden="true" />
      <div className="home-paper-canvas" aria-hidden="true" />

      <div className="home-content branch-content">
        <nav className="branch-nav" aria-label="年级切换">
          <SegmentedControl
            options={options}
            active={activeLabel}
            onChange={(label) => {
              const yearId = labelToYearId[label];
              if (yearId) {
                setActiveYear(yearId);
              }
            }}
            disabledOptions={disabledOptions}
          />
        </nav>

        <div className="branch-view-container">
          {loading ? (
            <div className="branch-feedback-card">
              <p className="branch-feedback-title">正在加载课程路径</p>
              <span className="branch-feedback-text">请稍候片刻。</span>
            </div>
          ) : error ? (
            <div className="branch-feedback-card">
              <p className="branch-feedback-title">课程路径暂时不可用</p>
              <span className="branch-feedback-text">{error}</span>
            </div>
          ) : (
            <motion.div
              key={activeYear}
              initial={reduceMotion ? { opacity: 0 } : { opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              transition={motionTokens.editorial}
              style={{ width: '100%' }}
            >
              <PathSession
                gradeName={activeYearData?.grade_name ?? YEAR_LABELS[activeYear]}
                courses={activeYearData?.courses ?? []}
                currentCourseId={activeYearData?.current_course_id ?? null}
                onOpenCourse={(course) => {
                  navigate(`/leaf/${encodeURIComponent(course.course_node_id)}`);
                }}
                showCoachmark={showCoachmark}
                onCloseCoachmark={() => setShowCoachmark(false)}
                allCourses={overview ? YEAR_ORDER.flatMap((yId) => overview.years[yId]?.courses ?? []) : []}
              />
            </motion.div>
          )}
        </div>
      </div>
      </motion.main>

      <AnimatePresence>
        {showPathOverlay && (
          <PathInitOverlay
            currentCourseName={currentCourse?.course_or_chapter_theme ?? null}
            currentCourseId={currentCourse?.course_node_id ?? null}
            onComplete={() => {
              setShowPathOverlay(false);
              setShowCoachmark(true);
            }}
          />
        )}
      </AnimatePresence>
    </>
  );
}
