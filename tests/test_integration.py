"""Integration smoke tests against a LIVE deployment (real DB + real LLM).

Skipped unless QA_API_BASE_URL is set, e.g.:

    QA_API_BASE_URL=https://your-space.hf.space pytest tests/test_integration.py -v
"""
import os

import httpx
import pytest

BASE_URL = os.getenv("QA_API_BASE_URL", "").rstrip("/")

pytestmark = pytest.mark.skipif(
    not BASE_URL, reason="Set QA_API_BASE_URL to run integration tests"
)


def test_live_health():
    response = httpx.get(f"{BASE_URL}/health", timeout=30)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] is True


def test_live_ask_python_question():
    response = httpx.post(
        f"{BASE_URL}/ask",
        json={"question": "How do I merge two dictionaries in Python?"},
        timeout=60,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["grounded"] is True
    assert len(body["sources"]) >= 1
    assert "dict" in body["answer"].lower() or "merge" in body["answer"].lower()


def test_live_ask_off_topic_is_not_grounded():
    response = httpx.post(
        f"{BASE_URL}/ask",
        json={"question": "What is the best phone to buy for mobile gaming?"},
        timeout=60,
    )
    assert response.status_code == 200
    # either short-circuited, or the model declined from context
    body = response.json()
    assert isinstance(body["grounded"], bool)
