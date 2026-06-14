"""Shared test fixtures and fakes (no DB, no torch, no LLM required)."""
import pytest
from fastapi.testclient import TestClient

from app.main import app


class FakePool:
    """Stands in for an asyncpg pool."""

    def __init__(self, healthy: bool = True):
        self.healthy = healthy

    async def fetchval(self, query, *args):
        if not self.healthy:
            raise RuntimeError("db down")
        return 1

    async def fetch(self, query, *args):
        if not self.healthy:
            raise RuntimeError("db down")
        return []

    async def close(self):
        pass


class FakeChain:
    """Stands in for the LCEL generation chain; counts invocations."""

    def __init__(self, answer: str = "Lists are mutable; tuples are immutable. [S1]",
                 fail: bool = False):
        self.answer = answer
        self.fail = fail
        self.calls = 0

    async def ainvoke(self, inputs):
        self.calls += 1
        if self.fail:
            raise RuntimeError("llm down")
        return self.answer


SAMPLE_DOC = {
    "id": 123,
    "title": "What is the difference between list and tuple?",
    "question": "I keep seeing both used...",
    "answer": "Lists are mutable, tuples are immutable ...",
    "question_score": 100,
    "answer_score": 42,
    "link": "https://stackoverflow.com/questions/123",
    "similarity": 0.83,
}


@pytest.fixture
def client():
    """TestClient with healthy fakes pre-installed on app.state.

    Lifespan is intentionally NOT run (no real DB / model needed).
    """
    app.state.pool = FakePool()
    app.state.chain = FakeChain()
    return TestClient(app)
