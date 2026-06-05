import asyncio
from sqlmodel import Session
from app.database import get_engine
from app.models import User
from app.services.learning_path_service import get_all_year_learning_paths

def test():
    with Session(get_engine()) as session:
        user = session.query(User).first()
        paths = get_all_year_learning_paths(session, user.uid)
        for grade_year, path in paths.items():
            print(grade_year)
            current = path.get("current_learning_course", {})
            print("Current:", current.get("course_or_chapter_theme"))
            for course in path.get("grade_plans", {}).get(grade_year, {}).get("course_nodes", []):
                print(" -", course.get("course_or_chapter_theme"))

test()
