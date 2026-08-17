from sqlmodel import Session, create_engine

from config import settings

engine = create_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    connect_args={"check_same_thread": False}
    if "sqlite" in settings.DATABASE_URL
    else {},
)


def get_session():
    with Session(engine) as session:
        yield session
