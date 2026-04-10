from sqlalchemy import create_engine, Column, Text, Integer, DateTime, func
from sqlalchemy.orm import declarative_base, sessionmaker
from config import DATABASE_URL

engine = create_engine(
    DATABASE_URL,
    pool_size=10 if "postgresql" in DATABASE_URL else 5,
    max_overflow=20 if "postgresql" in DATABASE_URL else 0,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()


class Record(Base):
    __tablename__ = "records"

    id = Column(Text, primary_key=True)
    answers = Column(Text, nullable=False)
    result_code = Column(Text, nullable=False)
    result_name = Column(Text, nullable=False)
    ip_hash = Column(Text)
    user_agent = Column(Text)
    created_at = Column(DateTime, server_default=func.now())


class PageView(Base):
    __tablename__ = "page_views"

    id = Column(Integer, primary_key=True, autoincrement=True)
    page = Column(Text, nullable=False)
    referrer = Column(Text)
    ip_hash = Column(Text)
    user_agent = Column(Text)
    created_at = Column(DateTime, server_default=func.now())


def init_db():
    Base.metadata.create_all(engine)
