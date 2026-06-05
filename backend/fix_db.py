import asyncio
from sqlmodel import Session, select
from app.database import get_engine
from app.models import User, UserYearLearningPath

def fix():
    with Session(get_engine()) as session:
        user = session.query(User).first()
        if user:
            paths = session.exec(select(UserYearLearningPath).where(UserYearLearningPath.user_uid == user.uid)).all()
            for p in paths:
                session.delete(p)
            session.commit()
            print(f"Deleted fallback paths for user {user.uid}")

fix()
