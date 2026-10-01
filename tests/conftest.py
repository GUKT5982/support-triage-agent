import pytest

from triage.config import PROJECT_ROOT
from triage.data_store import MockDataStore


@pytest.fixture
def store() -> MockDataStore:
    return MockDataStore(PROJECT_ROOT / "data")


@pytest.fixture
def tickets(store):
    return {t.id: t for t in store.sample_tickets}
