---
title: Python QA Assistant
emoji: 🐍
colorFrom: blue
colorTo: green
sdk: docker
app_port: 7860
pinned: false
---

# Python Programming Q&A Assistant

A retrieval-augmented question-answering API for data science learners. Answers
are grounded in the [Stack Overflow Python Questions & Answers](https://www.kaggle.com/datasets/stackoverflow/pythonquestions)
dataset: the service retrieves real Q&A pairs and generates an answer only from
that context, citing its sources. If retrieval finds nothing relevant, it says
so instead of guessing.

The same architecture is the retrieval layer an intelligent tutor needs: swap
the Stack Overflow corpus for course content, lesson transcripts, or a question
bank, and the grounded-answer-with-citations contract carries over directly.

Live URL: https://anirudhm12-python-qa-assistant.hf.space  ·  Docs: https://anirudhm12-python-qa-assistant.hf.space/docs

## Stack

- API: FastAPI (async)
- Orchestration: LangChain, using LCEL (`prompt | llm | parser`)
- Vector store: PostgreSQL + pgvector with an HNSW index, hosted free on Supabase or Neon
- Embeddings: sentence-transformers `all-MiniLM-L6-v2` (384-d), runs on CPU
- LLM: Llama 3.3 70B, served via Groq or any OpenAI-compatible endpoint
  (OpenRouter, Together, OpenAI). The provider is an env var (`LLM_PROVIDER`), so
  swapping is config-only, not a code change
- Hosting: Hugging Face Spaces (Docker), which has enough RAM to run torch

## How it works

Ingestion (offline, run once):

1. Read `Questions.csv` and `Answers.csv`, strip the HTML but keep code blocks.
2. Pair each question with its highest-scored answer.
3. Filter by score and cap the count, then embed the question text.
4. Insert into Postgres and build an HNSW index.

Serving (`POST /ask`):

1. Embed the incoming question.
2. Pull the top-k most similar questions from pgvector.
3. If nothing clears the similarity floor, return a refusal (no LLM call).
4. Otherwise format the retrieved pairs as context and run the LCEL chain.
5. Return the answer plus the source links it was built from.

## Design notes

A few choices that matter for quality:

- Embed the question, store the answer. Learner queries read like questions, so
  matching a query against question text retrieves better than matching it
  against answer prose. The answer is the payload, and never gets embedded.
- Pair on score. This export has no accepted-answer flag, so the top-scored
  answer is the best available signal.
- Keep the corpus small and high-signal. Score thresholds plus a ~60K cap fit a
  free Postgres tier (about 90 MB of vectors and text) without hurting quality.
- Refuse early. If no retrieved pair clears `MIN_SIMILARITY` (0.45 cosine), the
  API returns `grounded: false` before any LLM call. This cleanly catches
  low-similarity input (e.g. a CSS question, or a vague "fix my code"). It does
  not catch *adjacent-domain* queries: a question about Java web frameworks
  still retrieves Python pairs above the floor, because a single bi-encoder
  cosine score does not separate "Python" from "near-Python" reliably. That is
  the documented bi-encoder limitation (see Known limitations and Prior work),
  and the measured `refusal_precision` in `eval/golden_scores.json` reflects it
  honestly rather than papering over it.

## API

`POST /ask`

```bash
curl -X POST <base-url>/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "How do I merge two dictionaries in Python?"}'
```

```json
{
  "answer": "You can merge two dictionaries using dict.update() ... [S1]",
  "sources": [
    {
      "id": 38987,
      "title": "How do I merge two dictionaries in a single expression?",
      "link": "https://stackoverflow.com/questions/38987",
      "similarity": 0.91,
      "answer_score": 5800
    }
  ],
  "grounded": true,
  "latency_ms": 842.3
}
```

`GET /health`

```json
{ "status": "ok", "database": true, "version": "1.0.0" }
```

Status codes: 422 invalid input, 502 LLM backend failure, 503 retrieval/DB failure.

## Setup

Prerequisites:

- Python 3.11+
- A Postgres database with pgvector. On Supabase, enable the `vector` extension
  under Database, Extensions.
- A Groq API key from https://console.groq.com
- The Kaggle dataset extracted to `./data/` (`Questions.csv`, `Answers.csv`)

1. Configure:

```bash
cp .env.example .env   # set DATABASE_URL and GROQ_API_KEY
```

2. Ingest (one-off, roughly 15-30 min on a laptop CPU). Use the direct
   connection string, port 5432:

```bash
pip install -r ingestion/requirements-ingest.txt
python ingestion/ingest.py --data-dir ./data --database-url "$DATABASE_URL"
```

Tunables: `--max-pairs 60000 --min-question-score 2 --min-answer-score 2`.

3. Run the API:

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
# http://localhost:8000/docs
```

4. Test:

```bash
pip install -r requirements-dev.txt
pytest                                                                   # unit tests, no DB/LLM needed
QA_API_BASE_URL=http://localhost:8000 pytest tests/test_integration.py   # live smoke tests
python eval/run_eval.py --base-url http://localhost:8000                 # writes eval/TEST_RESULTS.md
python eval/golden_eval.py --base-url http://localhost:8000              # scores a golden set -> golden_scores.json
```

`run_eval.py` records responses for manual review. `golden_eval.py` scores them
against a small golden set and reports metrics you can track across changes:
answerable-recall, refusal-precision (does it refuse what it should?),
citation-rate, expected-source hit@k, and mean/p95 latency. It runs with no
extra dependencies; a Ragas hook (faithfulness, answer-relevancy) can be layered
on top if you want an LLM-judged score.

The eval harness runs 12 queries across core syntax, debugging, pandas, the GIL,
decorators, and a few edge cases (post-2016 features, an off-topic Java
question, vague input). Results land in `eval/TEST_RESULTS.md`.

## Deploy (Hugging Face Spaces)

1. Create a Space with the Docker SDK.
2. Push this repo. The `Dockerfile` listens on port 7860.
3. Add a YAML header to the Space's `README.md`:

```yaml
---
title: Python QA Assistant
sdk: docker
app_port: 7860
---
```

4. Under Settings, Variables and secrets, add `DATABASE_URL` (use Supabase's
   pooled URL, port 6543; the app sets `statement_cache_size=0` for pgbouncer)
   and the LLM credentials. For Groq: `GROQ_API_KEY`. For an OpenAI-compatible
   provider such as OpenRouter: `LLM_PROVIDER=openai`, `OPENAI_API_KEY`,
   `OPENAI_BASE_URL=https://openrouter.ai/api/v1`, and
   `LLM_MODEL=meta-llama/llama-3.3-70b-instruct`.
5. Open `https://anirudhm12-python-qa-assistant.hf.space/docs`.

Render and Railway free tiers (around 512 MB RAM) are too small for torch plus
sentence-transformers. Use HF Spaces, or switch `app/embeddings.py` to
[fastembed](https://github.com/qdrant/fastembed), an ONNX build of the same
MiniLM model with the same vectors and a much smaller footprint.

## Scaling to 100+ concurrent users

- I/O is async end to end. The DB and LLM calls don't block, and embedding runs
  in a worker thread.
- Pooling with pgbouncer (built into Supabase). The API is stateless, so it
  scales by adding replicas.
- Caching: a Redis exact-match cache on normalized questions, then a semantic
  cache (cosine >= 0.97 on the query embedding). Learner questions repeat a lot,
  and each cache hit removes an LLM call.
- Latency: embedding is ~15 ms, pgvector top-5 is ~10-30 ms at this size, and
  Groq generation is ~0.5-2 s. The LLM dominates, so stream tokens to cut
  perceived latency.
- Cost: MiniLM embeddings are self-hosted (free); a Groq answer is well under a
  cent at ~1K tokens; cache hits cost nothing.

## Prior work

I have built this kind of pipeline before, on a PDF Q&A project
(`github.com/anirudh-mandahr/rag_pdf_qa`) with the same pgvector + Groq + LCEL
core. That version added a cross-encoder reranker and MMR retrieval, and I
diagnosed a bi-encoder failure mode there: on some natural-language queries the
relevant chunk falls outside the top-K because the query embedding lands in a
different region of vector space than the document prose. I traced it through
direct SQL inspection of pgvector and instrumentation of the bi-encoder.
Reranking can't fix that, since it only re-scores what's already in the
candidate pool. The fix is hybrid BM25 + vector retrieval, which is the first
item on the roadmap below.

## Roadmap

- Hybrid retrieval: Postgres full-text (BM25) plus vectors, fused with RRF.
- Cross-encoder reranking over a wider candidate pool.
- Expose retrieval as an MCP tool so a tutor agent can call `/ask` as one step
  in a larger tool-use workflow.
- Point the same pipeline at learning content (lessons, transcripts, a question
  bank) for an intelligent-tutor use case.
- A feedback loop tracking the grounded-answer rate from `golden_eval.py`.

## Layout

```
app/                FastAPI service
  main.py           routes + lifespan
  chain.py          LCEL chain + prompts
  retriever.py      pgvector search
  embeddings.py     sentence-transformers wrapper
  db.py             asyncpg pool helpers
  config.py         settings
  schemas.py        request/response models
ingestion/          one-off CSV -> pgvector pipeline
tests/              unit + integration tests
eval/               12-query harness -> TEST_RESULTS.md
Dockerfile          HF Spaces deployment
```

## Known limitations

- The corpus stops in late 2016, so post-2016 features (f-strings in some forms,
  the walrus operator, the `match` statement) are not covered. These queries
  often still retrieve near-neighbours above the similarity floor, so the
  grounding prompt (answer only from context, flag outdated/missing coverage) is
  the backstop here, not the floor. The floor only catches genuinely
  low-similarity input.
- The similarity floor is a single-score gate, so it does not separate
  adjacent-domain queries (e.g. Java/CSS questions that still match Python
  pairs) from in-scope ones. `eval/golden_scores.json` reports this as a low
  `refusal_precision`; the fix is hybrid retrieval plus a relevance check, not a
  higher floor (which would start refusing valid questions).
- Some retrieved answers use Python 2 idioms; the prompt tells the model to
  point that out.
- Retrieval is single-vector only. Hybrid retrieval and reranking (see Prior
  work) are the next steps.
