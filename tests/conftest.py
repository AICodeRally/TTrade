import pytest
from sqlmodel import Session
from engine.config import TTRadeConfig
from engine.db import init_db


@pytest.fixture
def config():
    return TTRadeConfig()


@pytest.fixture
def db_engine(tmp_path):
    db_path = tmp_path / "test.db"
    return init_db(str(db_path))


@pytest.fixture
def db_session(db_engine):
    with Session(db_engine) as session:
        yield session
