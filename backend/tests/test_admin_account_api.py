from pathlib import Path

from fastapi.testclient import TestClient
from sqlmodel import Session, create_engine, select

from app.main import create_app
from app.models import (
    ChapterProgress,
    ChapterQuiz,
    ChapterQuizAttempt,
    CourseResourceQuality,
    User,
    UserCourseKnowledgeOutline,
    UserYearLearningPath,
)
from app.services.forest_service import generate_or_read_quiz
from tests.postgres import postgresql_test_url


def make_client(tmp_path: Path, monkeypatch) -> TestClient:
    monkeypatch.setenv("ADMIN_USERNAME", "admin")
    monkeypatch.setenv("ADMIN_IDENTIFIER", "13297540721")
    monkeypatch.setenv("ADMIN_PASSWORD", "123456")
    database_url = postgresql_test_url(tmp_path, "admin-test")
    return TestClient(create_app(database_url=database_url))


def login_token(client: TestClient, account: str, password: str) -> str:
    response = client.post(
        "/api/auth/login",
        json={"account": account, "password": password},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def test_admin_can_manage_accounts(tmp_path: Path, monkeypatch) -> None:
    client = make_client(tmp_path, monkeypatch)
    token = login_token(client, "13297540721", "123456")
    headers = {"Authorization": f"Bearer {token}"}

    create_response = client.post(
        "/api/admin/accounts",
        headers=headers,
        json={
            "username": "管理员用户",
            "identifier": "admin-api-test@example.com",
            "password": "admin-password-123",
            "role": "admin",
            "is_active": True,
            "school": "南山大学",
            "major": "软件工程",
            "class_name": "一班",
        },
    )

    assert create_response.status_code == 201
    created = create_response.json()
    assert created["username"] == "管理员用户"
    assert created["role"] == "admin"
    assert created["is_active"] is True

    list_response = client.get("/api/admin/accounts", headers=headers)
    assert list_response.status_code == 200
    assert any(
        account["identifier"] == "admin-api-test@example.com"
        for account in list_response.json()
    )

    update_response = client.put(
        f"/api/admin/accounts/{created['uid']}",
        headers=headers,
        json={
            "username": "教师用户二号",
            "identifier": "teacher-admin-api-2@example.com",
            "password": "teacher-password-456",
            "role": "student",
            "is_active": False,
            "school": "南山大学",
            "major": "软件工程",
            "class_name": "二班",
        },
    )

    assert update_response.status_code == 200
    updated = update_response.json()
    assert updated["username"] == "教师用户二号"
    assert updated["identifier"] == "teacher-admin-api-2@example.com"
    assert updated["role"] == "student"
    assert updated["is_active"] is False

    delete_response = client.delete(
        f"/api/admin/accounts/{created['uid']}", headers=headers
    )
    assert delete_response.status_code == 204

    final_list_response = client.get("/api/admin/accounts", headers=headers)
    assert final_list_response.status_code == 200
    assert all(
        account["uid"] != created["uid"] for account in final_list_response.json()
    )


def test_admin_rejects_class_name_equal_to_identifier(
    tmp_path: Path, monkeypatch
) -> None:
    client = make_client(tmp_path, monkeypatch)
    token = login_token(client, "13297540721", "123456")
    headers = {"Authorization": f"Bearer {token}"}

    response = client.post(
        "/api/admin/accounts",
        headers=headers,
        json={
            "username": "错误班级",
            "identifier": "18771701100",
            "password": "student-password-123",
            "role": "student",
            "is_active": True,
            "school": "wc",
            "major": "计算机",
            "class_name": "18771701100",
        },
    )

    assert response.status_code == 422
    assert "班级不能填写登录标识" in response.text


def test_student_cannot_manage_accounts(tmp_path: Path, monkeypatch) -> None:
    client = make_client(tmp_path, monkeypatch)
    response = client.post(
        "/api/auth/register",
        json={
            "username": "学生用户",
            "identifier": "student-admin-api@example.com",
            "password": "student-password-123",
            "confirm_password": "student-password-123",
            "school": "南山大学",
            "major": "软件工程",
            "class_name": "一班",
        },
    )
    token = response.json()["access_token"]

    accounts_response = client.get(
        "/api/admin/accounts",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert accounts_response.status_code == 403
    assert accounts_response.json()["detail"] == "需要管理员权限"


def test_admin_batch_updates_accounts(tmp_path: Path, monkeypatch) -> None:
    client = make_client(tmp_path, monkeypatch)
    token = login_token(client, "13297540721", "123456")
    headers = {"Authorization": f"Bearer {token}"}
    first = client.post(
        "/api/admin/accounts",
        headers=headers,
        json={
            "username": "批量一号",
            "identifier": "batch-one@example.com",
            "password": "batch-password-123",
            "role": "student",
            "is_active": True,
            "school": "南山大学",
            "major": "软件工程",
            "class_name": "一班",
        },
    ).json()
    second = client.post(
        "/api/admin/accounts",
        headers=headers,
        json={
            "username": "批量二号",
            "identifier": "batch-two@example.com",
            "password": "batch-password-123",
            "role": "student",
            "is_active": True,
            "school": "南山大学",
            "major": "软件工程",
            "class_name": "一班",
        },
    ).json()

    deactivate_response = client.post(
        "/api/admin/accounts/batch",
        headers=headers,
        json={"action": "deactivate", "uids": [first["uid"], second["uid"]]},
    )
    assert deactivate_response.status_code == 200
    assert {
        account["is_active"]
        for account in deactivate_response.json()
        if account["uid"] in {first["uid"], second["uid"]}
    } == {False}

    role_response = client.post(
        "/api/admin/accounts/batch",
        headers=headers,
        json={
            "action": "set_role",
            "role": "admin",
            "uids": [first["uid"], second["uid"]],
        },
    )
    assert role_response.status_code == 200
    assert {
        account["role"]
        for account in role_response.json()
        if account["uid"] in {first["uid"], second["uid"]}
    } == {"admin"}

    delete_response = client.post(
        "/api/admin/accounts/batch",
        headers=headers,
        json={"action": "delete", "uids": [first["uid"], second["uid"]]},
    )
    assert delete_response.status_code == 200
    assert all(
        account["uid"] not in {first["uid"], second["uid"]}
        for account in delete_response.json()
    )


def test_admin_batch_delete_removes_forest_rows(tmp_path: Path, monkeypatch) -> None:
    client = make_client(tmp_path, monkeypatch)
    token = login_token(client, "13297540721", "123456")
    headers = {"Authorization": f"Bearer {token}"}
    created = client.post(
        "/api/admin/accounts",
        headers=headers,
        json={
            "username": "森林学员",
            "identifier": "forest-admin-delete@example.com",
            "password": "forest-password-123",
            "role": "student",
            "is_active": True,
            "school": "南山大学",
            "major": "软件工程",
            "class_name": "一班",
        },
    ).json()
    database_url = postgresql_test_url(tmp_path, "admin-test")
    engine = create_engine(database_url)

    with Session(engine) as session:
        session.add(
            UserYearLearningPath(
                user_uid=created["uid"],
                grade_year="year_3",
                learning_topic="AI",
                path_data={},
            )
        )
        session.add(
            UserCourseKnowledgeOutline(
                user_uid=created["uid"],
                course_id="year_3_course_2",
                grade_year="year_3",
                course_name="AI Agent 开发",
                outline_data={
                    "course_id": "year_3_course_2",
                    "course_name": "AI Agent 开发",
                    "grade_year": "year_3",
                    "personalization_summary": "",
                    "sections": [
                        {
                            "section_id": "1",
                            "parent_section_id": None,
                            "depth": 1,
                            "title": "第一章",
                            "order_index": 1,
                            "description": "",
                            "key_knowledge_points": [],
                        }
                    ],
                    "learning_sequence": ["第一章"],
                    "total_estimated_hours": "1 小时",
                    "section_composed_markdowns": {},
                },
            )
        )
        session.commit()
        generate_or_read_quiz(
            session,
            created["uid"],
            "year_3_course_2",
            "1",
            [
                {
                    "question_id": "q1",
                    "type": "single_choice",
                    "prompt": "题目",
                    "options": [],
                    "points": 100,
                }
            ],
            regenerate=False,
        )
        quiz = session.exec(
            select(ChapterQuiz).where(ChapterQuiz.user_uid == created["uid"])
        ).one()
        session.add(
            ChapterQuizAttempt(
                attempt_id="attempt-admin-delete",
                quiz_id=quiz.quiz_id,
                user_uid=created["uid"],
                answers={"q1": "A"},
                score=100,
                passed=True,
                grading_result={"score": 100, "passed": True},
            )
        )
        session.add(
            CourseResourceQuality(
                user_uid=created["uid"],
                course_node_id="year_3_course_2",
                accuracy_score=90,
                difficulty_fit_score=88,
                completeness_score=92,
                overall_score=90,
                suggestions=[],
            )
        )
        session.commit()

    delete_response = client.post(
        "/api/admin/accounts/batch",
        headers=headers,
        json={"action": "delete", "uids": [created["uid"]]},
    )

    assert delete_response.status_code == 200
    assert all(account["uid"] != created["uid"] for account in delete_response.json())

    with Session(engine) as session:
        assert session.get(User, created["uid"]) is None
        assert (
            session.exec(
                select(ChapterQuiz).where(ChapterQuiz.user_uid == created["uid"])
            ).all()
            == []
        )
        assert (
            session.exec(
                select(ChapterQuizAttempt).where(
                    ChapterQuizAttempt.user_uid == created["uid"]
                )
            ).all()
            == []
        )
        assert (
            session.exec(
                select(ChapterProgress).where(
                    ChapterProgress.user_uid == created["uid"]
                )
            ).all()
            == []
        )
        assert (
            session.exec(
                select(CourseResourceQuality).where(
                    CourseResourceQuality.user_uid == created["uid"]
                )
            ).all()
            == []
        )


def test_admin_import_updates_existing_and_exports_csv(
    tmp_path: Path, monkeypatch
) -> None:
    client = make_client(tmp_path, monkeypatch)
    token = login_token(client, "13297540721", "123456")
    headers = {"Authorization": f"Bearer {token}"}
    client.post(
        "/api/admin/accounts",
        headers=headers,
        json={
            "username": "旧姓名",
            "identifier": "import-existing@example.com",
            "password": "old-password-123",
            "role": "student",
            "is_active": True,
            "school": "南山大学",
            "major": "软件工程",
            "class_name": "一班",
        },
    )
    csv_text = (
        "username,identifier,password,role,is_active,school,major,class_name\n"
        "新账号,import-new@example.com,new-password-123,admin,true,南山大学,软件工程,一班\n"
        "新姓名,import-existing@example.com,,admin,false,南山大学,软件工程,二班\n"
        "坏账号,bad@example.com,,student,true,南山大学,软件工程,三班\n"
        "错班级,18771701100,student-password-123,student,true,wc,计算机,18771701100\n"
    )

    import_response = client.post(
        "/api/admin/accounts/import",
        headers=headers,
        json={"csv_text": csv_text},
    )

    assert import_response.status_code == 200
    body = import_response.json()
    assert body["created"] == 1
    assert body["updated"] == 1
    assert body["failed"] == 2
    assert body["failures"][0]["identifier"] == "bad@example.com"
    assert body["failures"][1]["identifier"] == "18771701100"
    assert body["failures"][1]["reason"] == "班级不能填写登录标识"

    accounts = client.get("/api/admin/accounts", headers=headers).json()
    new_account = next(
        account
        for account in accounts
        if account["identifier"] == "import-new@example.com"
    )
    updated_account = next(
        account
        for account in accounts
        if account["identifier"] == "import-existing@example.com"
    )
    assert new_account["role"] == "admin"
    assert new_account["school"] == "南山大学"
    assert new_account["major"] == "软件工程"
    assert new_account["class_name"] == "一班"
    assert updated_account["username"] == "新姓名"
    assert updated_account["role"] == "admin"
    assert updated_account["is_active"] is False
    assert updated_account["class_name"] == "二班"

    export_response = client.get("/api/admin/accounts/export", headers=headers)
    assert export_response.status_code == 200
    assert (
        export_response.text.splitlines()[0]
        == "username,identifier,password,role,is_active,school,major,class_name"
    )
    assert "import-new@example.com" in export_response.text


def test_admin_cannot_lock_out_self(tmp_path: Path, monkeypatch) -> None:
    client = make_client(tmp_path, monkeypatch)
    token = login_token(client, "13297540721", "123456")
    headers = {"Authorization": f"Bearer {token}"}
    admin = next(
        account
        for account in client.get("/api/admin/accounts", headers=headers).json()
        if account["identifier"] == "13297540721"
    )

    deactivate_response = client.post(
        "/api/admin/accounts/batch",
        headers=headers,
        json={"action": "deactivate", "uids": [admin["uid"]]},
    )
    assert deactivate_response.status_code == 400
    assert deactivate_response.json()["detail"] == "不能停用当前登录管理员"

    role_response = client.put(
        f"/api/admin/accounts/{admin['uid']}",
        headers=headers,
        json={
            "username": "admin",
            "identifier": "13297540721",
            "role": "student",
            "is_active": True,
            "school": "南山大学",
            "major": "软件工程",
            "class_name": "一班",
        },
    )
    assert role_response.status_code == 400
    assert role_response.json()["detail"] == "不能移除当前登录管理员权限"

    delete_response = client.delete(
        f"/api/admin/accounts/{admin['uid']}", headers=headers
    )
    assert delete_response.status_code == 400
    assert delete_response.json()["detail"] == "不能删除当前登录管理员"
