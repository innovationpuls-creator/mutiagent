"""User-scoped, read-only evidence catalog for growth reports."""

import json
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone

from pydantic import JsonValue
from sqlmodel import Session, select

from app.models import (
    ChapterProgress,
    ChapterQuiz,
    ChapterQuizAttempt,
    ChapterWeakness,
    Textbook,
    TextbookSectionContent,
    UserCourseKnowledgeOutline,
    UserProfile,
)
from app.report_schemas import EvidenceRequest, ReportEvidence, ReportStats
from app.services.learning_path_service import (
    get_all_year_learning_paths,
    get_grade_courses,
)

CATALOG_LIMIT = 30
DETAIL_CHARS = 5000


def compact(value: object, limit: int = DETAIL_CHARS) -> str:
    """Bound untrusted educational content; never include image data URLs."""

    def clean(item: object) -> object:
        if isinstance(item, dict):
            return {k: clean(v) for k, v in item.items() if k != "data_url"}
        if isinstance(item, list):
            return [clean(v) for v in item[:30]]
        if isinstance(item, str):
            return "[图片内容已省略]" if item.startswith("data:") else item[:2000]
        return item

    result = json.dumps(clean(value), ensure_ascii=False, default=str)
    return result if len(result) <= limit else result[:limit] + "…[内容截取]"


@dataclass
class ReportContext:
    stats: ReportStats
    profile: str
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    evidence: dict[str, ReportEvidence] = field(default_factory=dict)
    tools: dict[str, tuple[str, object]] = field(default_factory=dict)
    courses: set[str] = field(default_factory=set)
    unavailable: set[str] = field(default_factory=set)
    prerequisites: dict[str, object] = field(default_factory=dict)
    coverage: str = ""

    def add(self, item: ReportEvidence, tool: str = "", payload: object = None) -> None:
        self.evidence[item.id] = item
        if tool:
            self.tools[item.id] = (tool, payload)

    def summary(self) -> str:
        return json.dumps(
            {
                "stats": self.stats.model_dump(),
                "profile": self.profile,
                "coverage": self.coverage,
                "evidence": [item.model_dump() for item in self.evidence.values()],
                "tools": [
                    {"evidence_id": key, "tool": tool}
                    for key, (tool, _) in self.tools.items()
                ],
                "course_ids": sorted(self.courses),
                "prerequisites": self.prerequisites,
            },
            ensure_ascii=False,
        )


def _add_paths(context: ReportContext, session: Session, uid: str) -> None:
    paths = get_all_year_learning_paths(session, uid)
    for grade, path in paths.items():
        for course in get_grade_courses(path, grade)[:CATALOG_LIMIT]:
            course_id = course.get("course_node_id")
            if not isinstance(course_id, str) or not course_id:
                continue
            context.courses.add(course_id)
            context.prerequisites[course_id] = course.get("prerequisite_node_ids", [])
            context.add(
                ReportEvidence(
                    id=f"path:{course_id}",
                    kind="path",
                    course_id=course_id,
                    title=str(course.get("course_or_chapter_theme", course_id))[:200],
                    detail=("课程目标：" + str(course.get("course_goal", "未填写")))[
                        :600
                    ],
                )
            )


def _add_quizzes(
    context: ReportContext,
    quizzes: list[ChapterQuiz],
    attempts: list[ChapterQuizAttempt],
) -> None:
    by_quiz: dict[str, list[ChapterQuizAttempt]] = defaultdict(list)
    for attempt in attempts:
        by_quiz[attempt.quiz_id].append(attempt)
    ordered = sorted(
        [quiz for quiz in quizzes if by_quiz[quiz.quiz_id]],
        key=lambda q: (
            by_quiz[q.quiz_id][-1].created_at if by_quiz[q.quiz_id] else q.created_at
        ),
        reverse=True,
    )
    for quiz in ordered[:CATALOG_LIMIT]:
        rows = by_quiz[quiz.quiz_id]
        if not rows:
            continue
        first, latest = rows[0], rows[-1]
        course = context.evidence.get(f"path:{quiz.course_node_id}")
        title = course.title if course else quiz.course_node_id
        context.add(
            ReportEvidence(
                id=f"quiz:{quiz.quiz_id}",
                kind="quiz",
                course_id=quiz.course_node_id
                if quiz.course_node_id in context.courses
                else None,
                title=f"{title} · 章节 {quiz.chapter_id}",
                detail=(
                    f"作答 {len(rows)} 次；首次 {first.score} 分，"
                    f"最近 {latest.score} 分；"
                    f"最近作答 {latest.created_at.isoformat()}。"
                    "同一章节的题目可能重新生成，分数变化仅描述记录，不等同能力增长。"
                ),
            ),
            "read_quiz",
            quiz,
        )


def _add_sections(
    context: ReportContext, outlines: list[UserCourseKnowledgeOutline]
) -> None:
    remaining = CATALOG_LIMIT
    for outline in outlines:
        sections = outline.outline_data.get("sections", [])
        if not isinstance(sections, list):
            continue
        for section in sections:
            if not isinstance(section, dict) or remaining <= 0:
                continue
            section_id = section.get("section_id")
            if not isinstance(section_id, str):
                continue
            remaining -= 1
            course_id = (
                outline.course_id if outline.course_id in context.courses else None
            )
            ref = f"chapter:{outline.course_id}:{section_id}"
            context.add(
                ReportEvidence(
                    id=ref,
                    kind="chapter",
                    course_id=course_id,
                    title=f"{outline.course_name} · {section.get('title', section_id)}"[
                        :300
                    ],
                    detail=("章节说明：" + str(section.get("description", "未填写")))[
                        :500
                    ],
                ),
                "read_chapter",
                (outline, section),
            )
            if section.get("source_textbook_id") and section.get("source_section_ids"):
                context.add(
                    ReportEvidence(
                        id=f"textbook:{outline.course_id}:{section_id}",
                        kind="textbook",
                        course_id=course_id,
                        title=str(section.get("source_textbook_title", "教材依据"))[
                            :200
                        ],
                        detail="课程绑定教材；需读取工具确认当前已发布且存在可用正文。",
                    ),
                    "read_textbook",
                    section,
                )


def build_report_context(session: Session, uid: str) -> ReportContext:
    profile = session.get(UserProfile, uid)
    confirmed = profile.profile_data.get("confirmed_info", {}) if profile else {}
    if not isinstance(confirmed, dict):
        confirmed = {}
    quizzes = list(
        session.exec(select(ChapterQuiz).where(ChapterQuiz.user_uid == uid)).all()
    )
    quiz_ids = {q.quiz_id for q in quizzes}
    attempts = [
        a
        for a in session.exec(
            select(ChapterQuizAttempt)
            .where(
                ChapterQuizAttempt.user_uid == uid,
            )
            .order_by(ChapterQuizAttempt.created_at, ChapterQuizAttempt.attempt_id)
        ).all()
        if a.quiz_id in quiz_ids
    ]
    passed = session.exec(
        select(ChapterProgress).where(
            ChapterProgress.user_uid == uid,
            ChapterProgress.state == "passed",
        )
    ).all()
    attempted_ids = {a.quiz_id for a in attempts}
    context = ReportContext(
        stats=ReportStats(
            passed_chapters=len(passed),
            attempts=len(attempts),
            tested_chapters=len(
                {
                    (q.course_node_id, q.chapter_id)
                    for q in quizzes
                    if q.quiz_id in attempted_ids
                }
            ),
        ),
        profile=compact(
            {
                key: confirmed.get(key)
                for key in (
                    "current_grade",
                    "major",
                    "learning_method_preference",
                )
            },
            1500,
        ),
    )
    _add_paths(context, session, uid)
    _add_quizzes(context, quizzes, attempts)
    outlines = list(
        session.exec(
            select(UserCourseKnowledgeOutline)
            .where(
                UserCourseKnowledgeOutline.user_uid == uid,
            )
            .order_by(UserCourseKnowledgeOutline.updated_at.desc())
        ).all()
    )
    _add_sections(context, outlines)
    _add_weaknesses(context, session, uid)
    context.coverage = (
        "统计覆盖截至生成时的全部通关与作答记录；详细分析目录最多收录最近 30 份测验、"
        "30 个课程小节和 30 条薄弱点，按需读取最多 6 项详情。"
        "课程路径代表学习安排，教材和资源不代表已掌握。"
    )
    if not attempts:
        context.coverage += (
            "尚无测验作答记录，本报告仅回顾目标与路径，学习表现待测验验证。"
        )
    return context


def _add_weaknesses(context: ReportContext, session: Session, uid: str) -> None:
    rows = session.exec(
        select(ChapterWeakness)
        .where(
            ChapterWeakness.user_uid == uid,
        )
        .order_by(ChapterWeakness.created_at.desc())
        .limit(CATALOG_LIMIT)
    ).all()
    for row in rows:
        context.add(
            ReportEvidence(
                id=f"weakness:{row.weakness_id}",
                kind="weakness",
                title=row.knowledge_point_name or row.knowledge_point_id,
                course_id=row.course_node_id
                if row.course_node_id in context.courses
                else None,
                detail=f"章节 {row.chapter_id}；记录时间 {row.created_at.isoformat()}；"
                f"严重程度 {row.severity}。这是历史薄弱点记录，不代表目前仍未掌握；"
                "资源生成是否消费该记录不代表已经解决。",
            )
        )


def read_report_evidence(
    session: Session, uid: str, context: ReportContext, request: EvidenceRequest
) -> str:
    tool, payload = context.tools.get(request.evidence_id, ("", None))
    if not tool or tool != request.tool:
        raise ValueError("报告工具请求超出本次证据范围")
    if tool == "read_quiz" and isinstance(payload, ChapterQuiz):
        rows = session.exec(
            select(ChapterQuizAttempt)
            .where(
                ChapterQuizAttempt.user_uid == uid,
                ChapterQuizAttempt.quiz_id == payload.quiz_id,
            )
            .order_by(ChapterQuizAttempt.created_at.desc())
            .limit(3)
        ).all()
        return compact(
            {
                "questions": payload.questions,
                "attempts": [
                    {
                        "score": row.score,
                        "answers": row.answers,
                        "grading_result": row.grading_result,
                        "created_at": row.created_at,
                    }
                    for row in rows
                ],
                "note": "题目可能重新生成；勿将最新题目强配旧答案。",
            }
        )
    if tool == "read_chapter" and isinstance(payload, tuple):
        outline, section = payload
        section_id = section["section_id"]
        markdowns = outline.outline_data.get("section_markdowns", {})
        return compact(
            {
                "section": section,
                "resource": markdowns.get(section_id)
                if isinstance(markdowns, dict)
                else None,
            }
        )
    if tool == "read_textbook" and isinstance(payload, dict):
        content = _read_textbook(session, payload)
        if content is None:
            context.unavailable.add(request.evidence_id)
            return "教材未发布或正文不可用，无可引用正文。"
        context.evidence[request.evidence_id].detail = content[:1200]
        return content
    raise ValueError("报告工具数据不可用")


def _read_textbook(session: Session, section: dict[str, JsonValue]) -> str | None:
    textbook = session.get(Textbook, section["source_textbook_id"])
    if textbook is None or textbook.student_availability_status != "published":
        return None
    ids = section["source_section_ids"]
    if not isinstance(ids, list) or not all(isinstance(value, str) for value in ids):
        return None
    rows = session.exec(
        select(TextbookSectionContent)
        .where(
            TextbookSectionContent.textbook_id == textbook.textbook_id,
            TextbookSectionContent.section_id.in_(ids[:7]),
        )
        .order_by(TextbookSectionContent.order_index)
    ).all()
    sections = [
        f"{row.title}\n{row.content_zh or row.content_original}"
        for row in rows
        if (row.content_zh or row.content_original).strip()
    ]
    if not sections:
        return None
    return (textbook.title + "\n" + "\n\n".join(sections))[:DETAIL_CHARS]
