"""Unit tests for the API (retrieval, embeddings and LLM are mocked)."""
from conftest import SAMPLE_DOC, FakeChain, FakePool

from app import embeddings, retriever
from app.main import app


def _patch_pipeline(monkeypatch, docs):
    async def fake_embed(text, model_name):
        return [0.0] * 384

    async def fake_search(pool, query_vector, top_k, min_similarity):
        return docs

    monkeypatch.setattr(embeddings, "embed_query", fake_embed)
    monkeypatch.setattr(retriever, "search", fake_search)


# ---------- /health ----------

def test_health_ok(client):
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] is True


def test_health_degraded_when_db_down(client):
    app.state.pool = FakePool(healthy=False)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "degraded"


# ---------- /ask : happy path ----------

def test_ask_returns_grounded_answer_with_sources(client, monkeypatch):
    _patch_pipeline(monkeypatch, [dict(SAMPLE_DOC)])
    response = client.post("/ask", json={"question": "list vs tuple in Python?"})
    assert response.status_code == 200
    body = response.json()
    assert body["grounded"] is True
    assert "[S1]" in body["answer"]
    assert len(body["sources"]) == 1
    assert body["sources"][0]["id"] == 123
    assert body["sources"][0]["link"].startswith("https://stackoverflow.com/")
    assert body["latency_ms"] >= 0


# ---------- /ask : no relevant context ----------

def test_ask_short_circuits_llm_when_no_context(client, monkeypatch):
    _patch_pipeline(monkeypatch, [])
    chain = FakeChain()
    app.state.chain = chain
    response = client.post("/ask", json={"question": "Best Java web framework?"})
    assert response.status_code == 200
    body = response.json()
    assert body["grounded"] is False
    assert body["sources"] == []
    assert chain.calls == 0  # LLM not called


# ---------- /ask : input validation ----------

def test_ask_rejects_empty_question(client):
    assert client.post("/ask", json={"question": ""}).status_code == 422


def test_ask_rejects_whitespace_only_question(client):
    assert client.post("/ask", json={"question": "   \n  "}).status_code == 422


def test_ask_rejects_missing_question_field(client):
    assert client.post("/ask", json={}).status_code == 422


def test_ask_rejects_overlong_question(client):
    assert client.post("/ask", json={"question": "x" * 3000}).status_code == 422


# ---------- /ask : dependency failures ----------

def test_ask_returns_503_when_retrieval_fails(client, monkeypatch):
    async def fake_embed(text, model_name):
        return [0.0] * 384

    async def boom(pool, query_vector, top_k, min_similarity):
        raise RuntimeError("db down")

    monkeypatch.setattr(embeddings, "embed_query", fake_embed)
    monkeypatch.setattr(retriever, "search", boom)
    response = client.post("/ask", json={"question": "What is a decorator?"})
    assert response.status_code == 503


def test_ask_returns_502_when_llm_fails(client, monkeypatch):
    _patch_pipeline(monkeypatch, [dict(SAMPLE_DOC)])
    app.state.chain = FakeChain(fail=True)
    response = client.post("/ask", json={"question": "What is a decorator?"})
    assert response.status_code == 502
