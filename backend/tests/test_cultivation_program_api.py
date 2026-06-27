from pathlib import Path

from fastapi.testclient import TestClient
from sqlmodel import Session, create_engine, select

from app.main import create_app
from app.models import UserYearLearningPath


def make_client(tmp_path: Path, monkeypatch) -> TestClient:
    monkeypatch.setenv("ADMIN_USERNAME", "admin")
    monkeypatch.setenv("ADMIN_IDENTIFIER", "13297540721")
    monkeypatch.setenv("ADMIN_PASSWORD", "123456")
    return TestClient(
        create_app(database_url=f"sqlite:///{tmp_path / 'program-test.db'}")
    )


def register(
    client: TestClient, identifier: str, role: str, class_name: str = "一班"
) -> dict:
    response = client.post(
        "/api/auth/register",
        json={
            "username": identifier.split("@")[0],
            "identifier": identifier,
            "password": "program-password-123",
            "confirm_password": "program-password-123",
            "role": role,
            "school": "南山大学",
            "major": "软件工程",
            "class_name": class_name,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def auth_header(auth_response: dict) -> dict:
    return {"Authorization": f"Bearer {auth_response['access_token']}"}


def course_payload() -> list[dict]:
    return [
        {
            "course_node_id": "teacher_course_1",
            "course_or_chapter_theme": "C++ 高级编程",
            "course_goal": "补充学校培养方案课程",
            "status": "locked",
            "has_outline": False,
            "time_arrangement": {"semester_scope": "2", "duration": "48学时/3学分"},
        }
    ]


def test_teacher_program_publish_is_unique_per_cohort_and_student_matches(
    tmp_path: Path, monkeypatch
) -> None:
    client = make_client(tmp_path, monkeypatch)
    teacher = register(client, "teacher-program@example.com", "admin")
    other_teacher = register(client, "teacher-program-2@example.com", "admin")
    student = register(client, "student-program@example.com", "student")

    publish_response = client.post(
        "/api/teacher/program/publish",
        headers=auth_header(teacher),
        json={"courses": course_payload()},
    )
    assert publish_response.status_code == 200
    body = publish_response.json()
    assert body["school"] == "南山大学"
    assert body["major"] == "软件工程"
    assert body["class_name"] == "一班"
    assert body["courses"][0]["course_node_id"] == "teacher_course_1"

    conflict_response = client.post(
        "/api/teacher/program/publish",
        headers=auth_header(other_teacher),
        json={"courses": course_payload()},
    )
    assert conflict_response.status_code == 409
    assert conflict_response.json()["detail"] == "该学校、专业、班级已有已发布人培方案"

    matched_response = client.get(
        "/api/student/matched-program", headers=auth_header(student)
    )
    assert matched_response.status_code == 200
    assert matched_response.json()["teacher_uid"] == teacher["user"]["uid"]


def test_student_matching_requires_exact_school_major_and_class_name(
    tmp_path: Path, monkeypatch
) -> None:
    client = make_client(tmp_path, monkeypatch)
    teacher = register(
        client, "exact-teacher@example.com", "admin", class_name="一班"
    )
    student = register(
        client, "exact-student@example.com", "student", class_name="二班"
    )

    publish_response = client.post(
        "/api/teacher/program/publish",
        headers=auth_header(teacher),
        json={"courses": course_payload()},
    )
    assert publish_response.status_code == 200

    matched_response = client.get(
        "/api/student/matched-program", headers=auth_header(student)
    )
    assert matched_response.status_code == 200
    assert matched_response.json() is None


def test_admin_can_publish_program_for_selected_cohort(
    tmp_path: Path, monkeypatch
) -> None:
    client = make_client(tmp_path, monkeypatch)
    admin_token = client.post(
        "/api/auth/login",
        json={"account": "13297540721", "password": "123456"},
    ).json()["access_token"]
    student = register(
        client, "admin-program-student@example.com", "student", class_name="三班"
    )

    publish_response = client.post(
        "/api/teacher/program/publish",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "school": "南山大学",
            "major": "软件工程",
            "class_name": "三班",
            "courses": course_payload(),
        },
    )

    assert publish_response.status_code == 200
    body = publish_response.json()
    assert body["school"] == "南山大学"
    assert body["major"] == "软件工程"
    assert body["class_name"] == "三班"

    matched_response = client.get(
        "/api/student/matched-program", headers=auth_header(student)
    )
    assert matched_response.status_code == 200
    assert matched_response.json()["teacher_identifier"] == "13297540721"


def test_student_matching_without_cohort_returns_no_program(
    tmp_path: Path, monkeypatch
) -> None:
    client = make_client(tmp_path, monkeypatch)
    token = client.post(
        "/api/auth/login",
        json={"account": "demo@mutiagent.local", "password": "demo123456"},
    ).json()["access_token"]

    matched_response = client.get(
        "/api/student/matched-program",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert matched_response.status_code == 200
    assert matched_response.json() is None


def test_admin_data_management_reads_and_clears_learning_data(
    tmp_path: Path, monkeypatch
) -> None:
    client = make_client(tmp_path, monkeypatch)
    admin_token = client.post(
        "/api/auth/login",
        json={"account": "13297540721", "password": "123456"},
    ).json()["access_token"]
    headers = {"Authorization": f"Bearer {admin_token}"}
    student = register(client, "data-student@example.com", "student")
    student_uid = student["user"]["uid"]
    engine = create_engine(
        f"sqlite:///{tmp_path / 'program-test.db'}",
        connect_args={"check_same_thread": False},
    )

    with Session(engine) as session:
        session.add(
            UserYearLearningPath(
                user_uid=student_uid,
                grade_year="year_1",
                learning_topic="AI",
                path_data={"grade_year": "year_1"},
            )
        )
        session.commit()

    overview_response = client.get("/api/admin/data/overview", headers=headers)
    assert overview_response.status_code == 200
    assert overview_response.json()["learning_data"]["year_learning_paths"] == 1

    data_response = client.get(
        f"/api/admin/data/users/{student_uid}/learning-data", headers=headers
    )
    assert data_response.status_code == 200
    assert len(data_response.json()["year_learning_paths"]) == 1

    delete_response = client.delete(
        f"/api/admin/data/users/{student_uid}/learning-data", headers=headers
    )
    assert delete_response.status_code == 204
    with Session(engine) as session:
        assert (
            session.exec(
                select(UserYearLearningPath).where(
                    UserYearLearningPath.user_uid == student_uid
                )
            ).all()
            == []
        )
