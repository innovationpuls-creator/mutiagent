from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

from app.database import get_engine
from app.main import create_app
from app.models import (
    KnowledgeBaseIngestionJob,
    KnowledgeGap,
    KnowledgeGapFollow,
    KnowledgeGapNotice,
    Textbook,
    UserCourseKnowledgeOutline,
    UserYearLearningPath,
)
from tests.fixtures.knowledge_base import (
    admitted_source_payload,
    blocked_source_payload,
    extension_resource,
    extension_resource_payload,
    gap_resolved_notice,
    structured_textbook_payload,
    uncovered_topic_gap,
)


def make_client(tmp_path: Path, monkeypatch) -> TestClient:
    monkeypatch.setenv("ADMIN_USERNAME", "管理员")
    monkeypatch.setenv("ADMIN_IDENTIFIER", "admin-kb@example.com")
    monkeypatch.setenv("ADMIN_PASSWORD", "admin-password-123")
    database_url = f"sqlite:///{tmp_path / 'knowledge-base-api.db'}"
    return TestClient(create_app(database_url=database_url))


def login_token(client: TestClient, account: str, password: str) -> str:
    response = client.post(
        "/api/auth/login",
        json={"account": account, "password": password},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def register_student(client: TestClient, identifier: str, username: str) -> dict:
    response = client.post(
        "/api/auth/register",
        json={
            "username": username,
            "identifier": identifier,
            "password": "student-password-123",
            "confirm_password": "student-password-123",
            "school": "南山大学",
            "major": "软件工程",
            "class_name": "一班",
        },
    )
    assert response.status_code == 201
    return response.json()


def admin_headers(client: TestClient) -> dict[str, str]:
    token = login_token(client, "admin-kb@example.com", "admin-password-123")
    return {"Authorization": f"Bearer {token}"}


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def create_gap(gap_id: str = "gap-api", normalized_topic: str = "概率论") -> None:
    with Session(get_engine()) as session:
        session.add(
            uncovered_topic_gap(gap_id=gap_id, normalized_topic=normalized_topic)
        )
        session.commit()


def create_notice(notice_id: str, gap_id: str, user_uid: str) -> None:
    with Session(get_engine()) as session:
        session.add(
            gap_resolved_notice(
                notice_id=notice_id,
                gap_id=gap_id,
                user_uid=user_uid,
            )
        )
        session.commit()


def test_student_cannot_access_admin_knowledge_base_routes(
    tmp_path: Path, monkeypatch
) -> None:
    client = make_client(tmp_path, monkeypatch)
    student = register_student(client, "student-kb-admin@example.com", "学生用户")

    response = client.get(
        "/api/admin/knowledge-base/sources",
        headers=auth_headers(student["access_token"]),
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "需要管理员权限"


def test_admin_cannot_use_student_knowledge_base_routes(
    tmp_path: Path, monkeypatch
) -> None:
    client = make_client(tmp_path, monkeypatch)
    headers = admin_headers(client)
    create_gap()

    response = client.post(
        "/api/knowledge-base/gaps/gap-api/follow",
        headers=headers,
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "需要学生身份"


def test_admin_can_create_and_list_sources(tmp_path: Path, monkeypatch) -> None:
    client = make_client(tmp_path, monkeypatch)
    headers = admin_headers(client)

    create_response = client.post(
        "/api/admin/knowledge-base/sources",
        headers=headers,
        json=admitted_source_payload(),
    )
    assert create_response.status_code == 201
    assert create_response.json()["source_id"] == "source-admitted-api"

    list_response = client.get("/api/admin/knowledge-base/sources", headers=headers)

    assert list_response.status_code == 200
    assert [source["source_id"] for source in list_response.json()] == [
        "source-admitted-api"
    ]


def test_admin_can_upload_publish_and_receive_service_detail_on_publish_failure(
    tmp_path: Path, monkeypatch
) -> None:
    client = make_client(tmp_path, monkeypatch)
    headers = admin_headers(client)
    client.post(
        "/api/admin/knowledge-base/sources",
        headers=headers,
        json=admitted_source_payload(),
    )
    client.post(
        "/api/admin/knowledge-base/sources",
        headers=headers,
        json=blocked_source_payload(),
    )

    upload_response = client.post(
        "/api/admin/knowledge-base/textbooks",
        headers=headers,
        json=structured_textbook_payload(),
    )
    assert upload_response.status_code == 201
    assert upload_response.json()["student_availability_status"] == "draft"

    list_response = client.get("/api/admin/knowledge-base/textbooks", headers=headers)
    assert list_response.status_code == 200
    assert [textbook["textbook_id"] for textbook in list_response.json()] == [
        "textbook-linear-api"
    ]

    publish_response = client.post(
        "/api/admin/knowledge-base/textbooks/textbook-linear-api/publish",
        headers=headers,
    )
    assert publish_response.status_code == 200
    assert publish_response.json()["student_availability_status"] == "published"

    failed_upload_response = client.post(
        "/api/admin/knowledge-base/textbooks",
        headers=headers,
        json=structured_textbook_payload(
            textbook_id="textbook-blocked-api",
            source_id="source-blocked-api",
            title="未准入教材",
        ),
    )
    assert failed_upload_response.status_code == 201

    failed_publish_response = client.post(
        "/api/admin/knowledge-base/textbooks/textbook-blocked-api/publish",
        headers=headers,
    )
    assert failed_publish_response.status_code == 400
    assert failed_publish_response.json()["detail"] == "教材来源未通过准入校验。"


def test_publish_rejects_missing_archived_and_incomplete_textbooks(
    tmp_path: Path, monkeypatch
) -> None:
    client = make_client(tmp_path, monkeypatch)
    headers = admin_headers(client)
    client.post(
        "/api/admin/knowledge-base/sources",
        headers=headers,
        json=admitted_source_payload(),
    )

    missing_response = client.post(
        "/api/admin/knowledge-base/textbooks/missing-textbook/publish",
        headers=headers,
    )
    assert missing_response.status_code == 404
    assert missing_response.json()["detail"] == "教材不存在。"

    incomplete_payload = structured_textbook_payload(
        textbook_id="textbook-incomplete-api",
        title="正文不完整教材",
    )
    incomplete_payload["sections"].append(
        {
            "section_content_id": "section-textbook-incomplete-api-empty",
            "section_id": "1.2",
            "parent_section_id": None,
            "order_index": 2,
            "title": "空正文",
            "original_title": "Empty Content",
            "content_zh": "   ",
            "content_char_count": 0,
        }
    )
    incomplete_payload["textbook"]["outline"]["sections"].append(
        {"section_id": "1.2", "title": "空正文"}
    )
    client.post(
        "/api/admin/knowledge-base/textbooks",
        headers=headers,
        json=incomplete_payload,
    )
    incomplete_response = client.post(
        "/api/admin/knowledge-base/textbooks/textbook-incomplete-api/publish",
        headers=headers,
    )
    assert incomplete_response.status_code == 400
    assert incomplete_response.json()["detail"] == "教材缺少完整中文正文。"

    client.post(
        "/api/admin/knowledge-base/textbooks",
        headers=headers,
        json=structured_textbook_payload(textbook_id="textbook-archived-api"),
    )
    client.post(
        "/api/admin/knowledge-base/textbooks/textbook-archived-api/publish",
        headers=headers,
    )
    delete_response = client.delete(
        "/api/admin/knowledge-base/textbooks/textbook-archived-api",
        headers=headers,
    )
    assert delete_response.status_code == 204
    archived_response = client.post(
        "/api/admin/knowledge-base/textbooks/textbook-archived-api/publish",
        headers=headers,
    )
    assert archived_response.status_code == 400
    assert archived_response.json()["detail"] == "已归档教材不能发布。"


def test_agent_organize_returns_queued_job_and_job_query_reads_it(
    tmp_path: Path, monkeypatch
) -> None:
    client = make_client(tmp_path, monkeypatch)
    headers = admin_headers(client)
    client.post(
        "/api/admin/knowledge-base/sources",
        headers=headers,
        json=admitted_source_payload(),
    )
    client.post(
        "/api/admin/knowledge-base/textbooks",
        headers=headers,
        json=structured_textbook_payload(textbook_id="textbook-organize-api"),
    )

    organize_response = client.post(
        "/api/admin/knowledge-base/textbooks/textbook-organize-api/agent-organize",
        headers=headers,
    )

    assert organize_response.status_code == 201
    job = organize_response.json()
    assert job["textbook_id"] == "textbook-organize-api"
    assert job["job_type"] == "agent_organize"
    assert job["status"] == "queued"

    read_response = client.get(
        f"/api/admin/knowledge-base/ingestion-jobs/{job['job_id']}",
        headers=headers,
    )

    assert read_response.status_code == 200
    assert read_response.json() == job


def test_find_materials_returns_only_admitted_sources_and_updates_gap(
    tmp_path: Path, monkeypatch
) -> None:
    client = make_client(tmp_path, monkeypatch)
    headers = admin_headers(client)
    client.post(
        "/api/admin/knowledge-base/sources",
        headers=headers,
        json=admitted_source_payload(),
    )
    client.post(
        "/api/admin/knowledge-base/sources",
        headers=headers,
        json=blocked_source_payload(),
    )
    create_gap()

    gaps_response = client.get("/api/admin/knowledge-base/gaps", headers=headers)
    assert gaps_response.status_code == 200
    assert gaps_response.json()[0]["gap_id"] == "gap-api"
    assert [source["source_id"] for source in gaps_response.json()[0]["sources"]] == [
        "source-admitted-api"
    ]
    assert gaps_response.json()[0]["actions"] == ["find-materials", "upload"]

    response = client.post(
        "/api/admin/knowledge-base/gaps/gap-api/find-materials",
        headers=headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["gap"]["status"] == "material_searching"
    assert [source["source_id"] for source in body["sources"]] == [
        "source-admitted-api"
    ]
    with Session(get_engine()) as session:
        gap = session.get(KnowledgeGap, "gap-api")
        assert gap is not None
        assert gap.status == "material_searching"


def test_upload_updates_gap_material_found_without_publishing_textbook(
    tmp_path: Path, monkeypatch
) -> None:
    client = make_client(tmp_path, monkeypatch)
    headers = admin_headers(client)
    client.post(
        "/api/admin/knowledge-base/sources",
        headers=headers,
        json=admitted_source_payload(),
    )
    create_gap(normalized_topic="矩阵")

    response = client.post(
        "/api/admin/knowledge-base/gaps/gap-api/upload",
        headers=headers,
        json=structured_textbook_payload(textbook_id="textbook-gap-upload-api"),
    )

    assert response.status_code == 201
    assert response.json()["gap"]["status"] == "material_found"
    assert response.json()["textbook"]["student_availability_status"] == "draft"
    with Session(get_engine()) as session:
        gap = session.get(KnowledgeGap, "gap-api")
        textbook = session.get(Textbook, "textbook-gap-upload-api")
        assert gap is not None
        assert gap.status == "material_found"
        assert textbook is not None
        assert textbook.student_availability_status == "draft"
        assert textbook.published_at is None


def test_upload_rejects_textbook_that_does_not_cover_gap(
    tmp_path: Path, monkeypatch
) -> None:
    client = make_client(tmp_path, monkeypatch)
    headers = admin_headers(client)
    client.post(
        "/api/admin/knowledge-base/sources",
        headers=headers,
        json=admitted_source_payload(),
    )
    create_gap(normalized_topic="概率论")

    response = client.post(
        "/api/admin/knowledge-base/gaps/gap-api/upload",
        headers=headers,
        json=structured_textbook_payload(textbook_id="textbook-gap-mismatch-api"),
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "上传教材未覆盖该知识缺口。"
    with Session(get_engine()) as session:
        gap = session.get(KnowledgeGap, "gap-api")
        textbook = session.get(Textbook, "textbook-gap-mismatch-api")
        assert gap is not None
        assert gap.status == "open"
        assert textbook is None


def test_unpublish_archives_non_draft_and_delete_removes_draft_rows(
    tmp_path: Path, monkeypatch
) -> None:
    client = make_client(tmp_path, monkeypatch)
    headers = admin_headers(client)
    client.post(
        "/api/admin/knowledge-base/sources",
        headers=headers,
        json=admitted_source_payload(),
    )
    client.post(
        "/api/admin/knowledge-base/textbooks",
        headers=headers,
        json=structured_textbook_payload(textbook_id="textbook-draft-delete-api"),
    )
    client.post(
        "/api/admin/knowledge-base/textbooks/textbook-draft-delete-api/extension-resources",
        headers=headers,
        json={
            "resource_id": "resource-draft-delete-api",
            "section_id": "1.1",
            "resource_type": "webpage",
            "title_zh": "草稿扩展资料",
            "render_mode": "webpage",
            "status": "published",
        },
    )
    organize_response = client.post(
        "/api/admin/knowledge-base/textbooks/textbook-draft-delete-api/agent-organize",
        headers=headers,
    )
    assert organize_response.status_code == 201
    job_id = organize_response.json()["job_id"]

    draft_delete_response = client.delete(
        "/api/admin/knowledge-base/textbooks/textbook-draft-delete-api",
        headers=headers,
    )
    assert draft_delete_response.status_code == 204
    with Session(get_engine()) as session:
        assert session.get(Textbook, "textbook-draft-delete-api") is None
        assert session.get(KnowledgeBaseIngestionJob, job_id) is None

    client.post(
        "/api/admin/knowledge-base/textbooks",
        headers=headers,
        json=structured_textbook_payload(textbook_id="textbook-archive-api"),
    )
    client.post(
        "/api/admin/knowledge-base/textbooks/textbook-archive-api/publish",
        headers=headers,
    )

    unpublish_response = client.post(
        "/api/admin/knowledge-base/textbooks/textbook-archive-api/unpublish",
        headers=headers,
    )
    assert unpublish_response.status_code == 200
    assert unpublish_response.json()["student_availability_status"] == "unpublished"
    assert unpublish_response.json()["unpublished_at"] is not None

    repeated_unpublish_response = client.post(
        "/api/admin/knowledge-base/textbooks/textbook-archive-api/unpublish",
        headers=headers,
    )
    assert repeated_unpublish_response.status_code == 400
    assert repeated_unpublish_response.json()["detail"] == "只有已发布教材可以下架。"

    archive_response = client.delete(
        "/api/admin/knowledge-base/textbooks/textbook-archive-api",
        headers=headers,
    )
    assert archive_response.status_code == 204
    with Session(get_engine()) as session:
        archived_textbook = session.get(Textbook, "textbook-archive-api")
        assert archived_textbook is not None
        assert archived_textbook.student_availability_status == "archived"
        assert archived_textbook.archived_at is not None


def test_delete_archives_draft_textbook_when_student_binding_exists(
    tmp_path: Path, monkeypatch
) -> None:
    client = make_client(tmp_path, monkeypatch)
    headers = admin_headers(client)
    client.post(
        "/api/admin/knowledge-base/sources",
        headers=headers,
        json=admitted_source_payload(),
    )
    client.post(
        "/api/admin/knowledge-base/textbooks",
        headers=headers,
        json=structured_textbook_payload(textbook_id="textbook-bound-api"),
    )
    student = register_student(client, "student-bound@example.com", "绑定学生")
    user_uid = student["user"]["uid"]
    with Session(get_engine()) as session:
        session.add(
            UserYearLearningPath(
                user_uid=user_uid,
                grade_year="year_2",
                learning_topic="线性代数",
                path_data={
                    "grade_plans": {
                        "year_2": {
                            "course_nodes": [
                                {
                                    "course_node_id": "year_2_course_1",
                                    "source_textbook_id": "textbook-bound-api",
                                }
                            ]
                        }
                    }
                },
            )
        )
        session.add(
            UserCourseKnowledgeOutline(
                user_uid=user_uid,
                course_id="year_2_course_1",
                grade_year="year_2",
                course_name="线性代数",
                outline_data={
                    "sections": [
                        {
                            "section_id": "section-1",
                            "source_textbook_id": "textbook-bound-api",
                        }
                    ]
                },
            )
        )
        session.commit()

    response = client.delete(
        "/api/admin/knowledge-base/textbooks/textbook-bound-api",
        headers=headers,
    )

    assert response.status_code == 204
    with Session(get_engine()) as session:
        textbook = session.get(Textbook, "textbook-bound-api")
        assert textbook is not None
        assert textbook.student_availability_status == "archived"
        assert textbook.archived_at is not None


def test_extension_resource_create_and_flat_list(tmp_path: Path, monkeypatch) -> None:
    client = make_client(tmp_path, monkeypatch)
    headers = admin_headers(client)
    client.post(
        "/api/admin/knowledge-base/sources",
        headers=headers,
        json=admitted_source_payload(),
    )
    client.post(
        "/api/admin/knowledge-base/textbooks",
        headers=headers,
        json=structured_textbook_payload(textbook_id="textbook-extension-api"),
    )

    create_response = client.post(
        "/api/admin/knowledge-base/textbooks/textbook-extension-api/extension-resources",
        headers=headers,
        json=extension_resource_payload(
            extension_resource(
                resource_id="resource-extension-api",
                textbook_id="textbook-extension-api",
                section_id="1.1",
                title_zh="矩阵乘法扩展阅读",
                status="published",
            )
        ),
    )
    assert create_response.status_code == 201
    for index, status_value in enumerate(
        ["draft", "published", "published", "published", "published"], start=1
    ):
        with Session(get_engine()) as session:
            session.add(
                extension_resource(
                    resource_id=f"resource-admin-visible-{index}",
                    textbook_id="textbook-extension-api",
                    section_id="1.1",
                    title_zh=f"管理扩展资料 {index}",
                    status=status_value,
                )
            )
            session.commit()

    list_response = client.get(
        "/api/admin/knowledge-base/textbooks/textbook-extension-api/extension-resources",
        headers=headers,
        params=[("section_id", "1.1"), ("section_id", "1.2")],
    )

    assert list_response.status_code == 200
    assert [resource["resource_id"] for resource in list_response.json()] == [
        "resource-admin-visible-1",
        "resource-admin-visible-2",
        "resource-admin-visible-3",
        "resource-admin-visible-4",
        "resource-admin-visible-5",
        "resource-extension-api",
    ]

    missing_list_response = client.get(
        "/api/admin/knowledge-base/textbooks/missing-textbook/extension-resources",
        headers=headers,
    )
    assert missing_list_response.status_code == 404
    assert missing_list_response.json()["detail"] == "教材不存在。"

    missing_create_response = client.post(
        "/api/admin/knowledge-base/textbooks/missing-textbook/extension-resources",
        headers=headers,
        json=extension_resource_payload(
            extension_resource(
                resource_id="resource-missing-textbook",
                textbook_id="missing-textbook",
                section_id="1.1",
                title_zh="缺失教材扩展资料",
                status="published",
            )
        ),
    )
    assert missing_create_response.status_code == 404
    assert missing_create_response.json()["detail"] == "教材不存在。"


def test_student_follow_is_idempotent_and_notice_visibility_is_user_scoped(
    tmp_path: Path, monkeypatch
) -> None:
    client = make_client(tmp_path, monkeypatch)
    first_student = register_student(
        client, "student-gap-one@example.com", "关注学生一"
    )
    second_student = register_student(
        client, "student-gap-two@example.com", "关注学生二"
    )
    create_gap()

    first_response = client.post(
        "/api/knowledge-base/gaps/gap-api/follow",
        headers=auth_headers(first_student["access_token"]),
    )
    repeated_response = client.post(
        "/api/knowledge-base/gaps/gap-api/follow",
        headers=auth_headers(first_student["access_token"]),
    )
    assert first_response.status_code == 200
    assert repeated_response.status_code == 200
    assert repeated_response.json()["follow_id"] == first_response.json()["follow_id"]
    with Session(get_engine()) as session:
        gap = session.get(KnowledgeGap, "gap-api")
        assert gap is not None
        assert gap.follow_count == 1

    create_notice("notice-first-student", "gap-api", first_student["user"]["uid"])

    first_notices = client.get(
        "/api/knowledge-base/notices",
        headers=auth_headers(first_student["access_token"]),
    )
    second_notices = client.get(
        "/api/knowledge-base/notices",
        headers=auth_headers(second_student["access_token"]),
    )

    assert [notice["notice_id"] for notice in first_notices.json()] == [
        "notice-first-student"
    ]
    assert second_notices.json() == []


def test_follow_handles_unique_constraint_conflict_as_idempotent_success(
    tmp_path: Path, monkeypatch
) -> None:
    client = make_client(tmp_path, monkeypatch)
    student = register_student(
        client, "student-follow-conflict@example.com", "关注冲突学生"
    )
    create_gap()
    with Session(get_engine()) as session:
        session.add(
            KnowledgeGapFollow(
                follow_id="gap-follow-conflict",
                gap_id="gap-api",
                user_uid=student["user"]["uid"],
            )
        )
        session.commit()

    def raise_unique_conflict(*_args: object, **_kwargs: object) -> object:
        raise IntegrityError("INSERT", {}, Exception("duplicate follow"))

    monkeypatch.setattr(
        "app.api.knowledge_base.follow_knowledge_gap",
        raise_unique_conflict,
    )

    response = client.post(
        "/api/knowledge-base/gaps/gap-api/follow",
        headers=auth_headers(student["access_token"]),
    )

    assert response.status_code == 200
    assert response.json()["follow_id"] == "gap-follow-conflict"


def test_notice_read_only_marks_owned_notice(tmp_path: Path, monkeypatch) -> None:
    client = make_client(tmp_path, monkeypatch)
    first_student = register_student(
        client, "student-notice-one@example.com", "提醒学生一"
    )
    second_student = register_student(
        client, "student-notice-two@example.com", "提醒学生二"
    )
    create_gap()
    create_notice("notice-owned-by-first", "gap-api", first_student["user"]["uid"])
    create_notice("notice-owned-by-second", "gap-api", second_student["user"]["uid"])

    forbidden_response = client.post(
        "/api/knowledge-base/notices/notice-owned-by-first/read",
        headers=auth_headers(second_student["access_token"]),
    )
    assert forbidden_response.status_code == 404

    read_response = client.post(
        "/api/knowledge-base/notices/notice-owned-by-first/read",
        headers=auth_headers(first_student["access_token"]),
    )

    assert read_response.status_code == 200
    assert read_response.json()["notice_id"] == "notice-owned-by-first"
    assert read_response.json()["read_at"] is not None
    with Session(get_engine()) as session:
        first_notice = session.get(KnowledgeGapNotice, "notice-owned-by-first")
        second_notice = session.get(KnowledgeGapNotice, "notice-owned-by-second")
        assert first_notice is not None
        assert first_notice.read_at is not None
        assert second_notice is not None
        assert second_notice.read_at is None


def test_admin_update_textbook_outline(tmp_path: Path, monkeypatch) -> None:
    client = make_client(tmp_path, monkeypatch)
    headers = admin_headers(client)

    client.post(
        "/api/admin/knowledge-base/sources",
        headers=headers,
        json=admitted_source_payload(),
    )
    create_res = client.post(
        "/api/admin/knowledge-base/textbooks",
        headers=headers,
        json=structured_textbook_payload(textbook_id="textbook-outline-test"),
    )
    assert create_res.status_code == 201

    new_outline = {
        "chapters": [
            {
                "chapter_number": 1,
                "title": "更新后的第一章",
                "sections": [{"section_id": "sec_1_1", "title": "更新后的1.1小节"}],
            }
        ]
    }

    put_res = client.put(
        "/api/admin/knowledge-base/textbooks/textbook-outline-test/outline",
        headers=headers,
        json=new_outline,
    )
    assert put_res.status_code == 200
    assert put_res.json()["outline"] == new_outline
    assert put_res.json()["outline_review_status"] == "approved"

    with Session(get_engine()) as session:
        tb = session.get(Textbook, "textbook-outline-test")
        assert tb is not None
        assert tb.outline == new_outline
        assert tb.outline_review_status == "approved"


def test_admin_generate_textbook_outline(tmp_path: Path, monkeypatch) -> None:
    from app.api.knowledge_base import GeneratedTextbookOutline
    from app.services.document_parser_service import ChapterOutline, SectionOutline

    class FakeWorkerLLM:
        def with_structured_output(self, schema):
            self.schema = schema
            return self

        def invoke(self, prompt):
            return GeneratedTextbookOutline(
                title="AI测试教材",
                description="这是一本由AI自动生成的测试教材",
                chapters=[
                    ChapterOutline(
                        chapter_number=1,
                        title="第一章 AI绪论",
                        sections=[
                            SectionOutline(
                                section_id="sec_1_1", title="1.1 走进AI时代"
                            ),
                        ],
                    )
                ],
            )

    monkeypatch.setattr(
        "app.api.knowledge_base.get_worker_llm", lambda: FakeWorkerLLM()
    )

    client = make_client(tmp_path, monkeypatch)
    headers = admin_headers(client)

    response = client.post(
        "/api/admin/knowledge-base/generate-outline",
        headers=headers,
        json={"prompt": "生成一本AI教材", "tags": ["AI", "测试"]},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "AI测试教材"
    assert data["description"] == "这是一本由AI自动生成的测试教材"
    assert data["tags"] == ["AI", "测试"]
    assert data["student_availability_status"] == "draft"

    textbook_id = data["textbook_id"]
    with Session(get_engine()) as session:
        tb = session.get(Textbook, textbook_id)
        assert tb is not None
        assert tb.title == "AI测试教材"
        assert tb.student_availability_status == "draft"
        assert tb.outline_review_status == "approved"


def test_admin_generate_textbook_contents_and_progress(
    tmp_path: Path, monkeypatch
) -> None:
    from sqlmodel import select

    from app.api.knowledge_base import GeneratedTextbookOutline
    from app.services.document_parser_service import ChapterOutline, SectionOutline

    class FakeWorkerLLM:
        def with_structured_output(self, schema):
            self.schema = schema
            return self

        def invoke(self, prompt):
            return GeneratedTextbookOutline(
                title="AI测试教材",
                description="这是一本由AI自动生成的测试教材",
                chapters=[
                    ChapterOutline(
                        chapter_number=1,
                        title="第一章 AI绪论",
                        sections=[
                            SectionOutline(
                                section_id="sec_1_1", title="1.1 走进AI时代"
                            ),
                        ],
                    )
                ],
            )

        async def ainvoke(self, prompt):
            class FakeResponse:
                content = (
                    "这是AI自动生成的教材段落内容。包含了理论讲解、"
                    "代码示例和详细的概念分析。字数足够多。"
                )

            return FakeResponse()

    monkeypatch.setattr(
        "app.api.knowledge_base.get_worker_llm", lambda: FakeWorkerLLM()
    )
    monkeypatch.setattr(
        "app.services.knowledge_base_service.get_worker_llm", lambda: FakeWorkerLLM()
    )

    client = make_client(tmp_path, monkeypatch)
    headers = admin_headers(client)

    gen_res = client.post(
        "/api/admin/knowledge-base/generate-outline",
        headers=headers,
        json={"prompt": "生成一本AI教材", "tags": ["AI", "测试"]},
    )
    assert gen_res.status_code == 201
    textbook_id = gen_res.json()["textbook_id"]

    prog_res = client.get(
        f"/api/admin/knowledge-base/textbooks/{textbook_id}/generation-progress",
        headers=headers,
    )
    assert prog_res.status_code == 200
    prog_data = prog_res.json()
    assert prog_data["progress_percentage"] == 0.0
    assert prog_data["status"] == "not_started"

    gen_cont_res = client.post(
        f"/api/admin/knowledge-base/textbooks/{textbook_id}/generate-content",
        headers=headers,
    )
    assert gen_cont_res.status_code == 201
    job_data = gen_cont_res.json()
    assert job_data["textbook_id"] == textbook_id
    assert job_data["job_type"] == "aigc_generation"

    prog_res2 = client.get(
        f"/api/admin/knowledge-base/textbooks/{textbook_id}/generation-progress",
        headers=headers,
    )
    assert prog_res2.status_code == 200
    prog_data2 = prog_res2.json()
    assert prog_data2["progress_percentage"] == 100.0
    assert prog_data2["status"] == "completed"

    from app.models import TextbookSectionContent

    with Session(get_engine()) as session:
        contents = session.exec(
            select(TextbookSectionContent).where(
                TextbookSectionContent.textbook_id == textbook_id
            )
        ).all()
        assert len(contents) == 1
        assert contents[0].section_id == "sec_1_1"
        assert contents[0].content_zh.startswith("这是AI自动生成的教材段落内容")
