"""FastAPI service for the Python Q&A pipeline.

  POST /ask     grounded answer + cited Stack Overflow sources
  GET  /health  liveness + database connectivity
"""
import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import RedirectResponse

from . import chain as chain_module
from . import db, embeddings, retriever
from .config import get_settings
from .schemas import AskRequest, AskResponse, HealthResponse, Source

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("python_qa")


@asynccontextmanager
async def lifespan(application: FastAPI):
    settings = get_settings()
    application.state.pool = await db.create_pool(settings.database_url)
    application.state.chain = chain_module.build_answer_chain(settings)
    # warm the model so the first request isn't slow
    await embeddings.embed_query("warmup", settings.embedding_model)
    logger.info("startup complete: pool ready, model warmed")
    yield
    await application.state.pool.close()


app = FastAPI(
    title="Python Programming Q&A Assistant",
    description=(
        "Retrieval-augmented Q&A for data science learners, grounded in "
        "Stack Overflow Python questions and answers. "
        "FastAPI, pgvector, sentence-transformers, LangChain (LCEL), Groq."
    ),
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/", include_in_schema=False)
async def root() -> RedirectResponse:
    return RedirectResponse(url="/docs")


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    database_ok = False
    pool = getattr(app.state, "pool", None)
    if pool is not None:
        try:
            database_ok = (await pool.fetchval("SELECT 1")) == 1
        except Exception:
            logger.exception("health check: database unreachable")
    return HealthResponse(status="ok" if database_ok else "degraded", database=database_ok)


@app.post("/ask", response_model=AskResponse)
async def ask(request: AskRequest) -> AskResponse:
    settings = get_settings()
    started = time.perf_counter()

    try:
        query_vector = await embeddings.embed_query(request.question, settings.embedding_model)
        docs = await retriever.search(
            app.state.pool, query_vector, settings.top_k, settings.min_similarity
        )
    except Exception:
        logger.exception("retrieval failed")
        raise HTTPException(
            status_code=503,
            detail="Retrieval backend is unavailable. Please try again shortly.",
        )

    # nothing relevant came back: refuse instead of calling the LLM
    if not docs:
        return AskResponse(
            answer=chain_module.NO_CONTEXT_ANSWER,
            sources=[],
            grounded=False,
            latency_ms=round((time.perf_counter() - started) * 1000, 1),
        )

    context = chain_module.format_context(docs, settings.max_context_chars_per_doc)
    try:
        answer = await app.state.chain.ainvoke(
            {"context": context, "question": request.question}
        )
    except Exception:
        logger.exception("generation failed")
        raise HTTPException(
            status_code=502,
            detail="The LLM backend returned an error. Please try again shortly.",
        )

    sources = [
        Source(
            id=int(d["id"]),
            title=d["title"],
            link=d["link"],
            similarity=round(float(d["similarity"]), 4),
            answer_score=d.get("answer_score"),
        )
        for d in docs
    ]
    return AskResponse(
        answer=answer,
        sources=sources,
        grounded=True,
        latency_ms=round((time.perf_counter() - started) * 1000, 1),
    )
