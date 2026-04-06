import pytest
from sqlmodel import Session, SQLModel, create_engine


@pytest.fixture
def config():
    from engine.config import TTRadeConfig
    return TTRadeConfig()


@pytest.fixture
def db_engine(tmp_path):
    db_path = tmp_path / "test.db"
    engine = create_engine(f"sqlite:///{db_path}")
    SQLModel.metadata.create_all(engine)
    return engine


@pytest.fixture
def db_session(db_engine):
    with Session(db_engine) as session:
        yield session
