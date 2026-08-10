from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


def make_engine(database_url: str | None = None):
    url = database_url or get_settings().database_url
    if url.startswith(("postgres://", "postgresql://")):
        url = f"postgresql+psycopg://{url.split('://', 1)[1]}"
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    return create_engine(url, pool_pre_ping=True, connect_args=connect_args)


engine = make_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def use_demo_database(db: Session) -> None:
    from app.services.demo_data import get_demo_engine

    db.close()
    db.bind = get_demo_engine()


def init_db(database_engine=None) -> None:
    from app.models import Base

    Base.metadata.create_all(bind=database_engine or engine)
