-- Schema for the Stack Overflow Python Q&A corpus.
-- The HNSW index is created by ingest.py AFTER bulk loading (much faster).

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS qa_pairs (
    id             BIGINT PRIMARY KEY,      -- Stack Overflow question id
    title          TEXT NOT NULL,
    question       TEXT NOT NULL,           -- cleaned question body (truncated)
    answer         TEXT NOT NULL,           -- cleaned highest-scored answer
    question_score INTEGER NOT NULL DEFAULT 0,
    answer_score   INTEGER NOT NULL DEFAULT 0,
    link           TEXT NOT NULL,
    embedding      vector(384) NOT NULL     -- all-MiniLM-L6-v2, unit-normalized
)
