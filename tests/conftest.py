import os
import tempfile
from pathlib import Path

_tmp = Path(tempfile.mkdtemp(prefix="eink-news-test-"))
os.environ["TESTING"] = "1"
os.environ["DATA_DIR"] = str(_tmp)

from collections.abc import Generator  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlmodel import SQLModel  # noqa: E402

from database import engine, init_db  # noqa: E402
from main import app  # noqa: E402


@pytest.fixture
def data_dir() -> Path:
    return _tmp


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    engine.dispose()
    SQLModel.metadata.drop_all(engine)
    init_db()
    with TestClient(app) as test_client:
        yield test_client



@pytest.fixture
def data_dir() -> Path:
    return _tmp


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    init_db()
    with TestClient(app) as test_client:
        yield test_client
