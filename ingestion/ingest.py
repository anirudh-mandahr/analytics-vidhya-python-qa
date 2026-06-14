#!/usr/bin/env python3
"""Load the Kaggle "Stack Overflow - Python Questions" dataset into pgvector.

Dataset: https://www.kaggle.com/datasets/stackoverflow/pythonquestions
Expects Questions.csv and Answers.csv (latin-1 encoded) in --data-dir.

A few things worth knowing about how this works:
  - There's no accepted-answer flag in this export, so each question gets
    paired with its highest-scored answer.
  - We embed the question (title + body), not the answer. Learner queries read
    like questions, so question-to-question similarity retrieves better. The
    answer is stored as the payload.
  - Score thresholds plus a cap keep the corpus inside a free Postgres tier.
  - The HNSW index is built after the bulk load (faster than maintaining it
    during inserts).

    python ingestion/ingest.py --data-dir ./data --database-url $DATABASE_URL
"""
import argparse
import os
import re
import sys
import time
from pathlib import Path
from typing import Dict, Set, Tuple

import pandas as pd
from bs4 import BeautifulSoup

SCHEMA_PATH = Path(__file__).with_name("schema.sql")

INSERT_SQL = """
INSERT INTO qa_pairs
    (id, title, question, answer, question_score, answer_score, link, embedding)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s::vector)
ON CONFLICT (id) DO NOTHING
"""

HNSW_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS qa_pairs_embedding_hnsw
ON qa_pairs USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64)
"""


def html_to_text(raw_html: str) -> str:
    """HTML to text, keeping code blocks as fenced/backticked Markdown."""
    soup = BeautifulSoup(raw_html or "", "lxml")
    for pre in soup.find_all("pre"):
        code_text = pre.get_text()
        pre.replace_with(f"\n```python\n{code_text.strip()}\n```\n")
    for code in soup.find_all("code"):
        code.replace_with(f"`{code.get_text()}`")
    text = soup.get_text()
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def load_questions(data_dir: Path, min_score: int) -> pd.DataFrame:
    print("Loading Questions.csv ...", flush=True)
    df = pd.read_csv(
        data_dir / "Questions.csv",
        encoding="latin-1",
        usecols=["Id", "Score", "Title", "Body"],
    )
    df = df.dropna(subset=["Title", "Body"])
    df = df[df["Score"] >= min_score]
    print(f"  kept {len(df):,} questions with score >= {min_score}", flush=True)
    return df


def load_best_answers(
    data_dir: Path, question_ids: Set[int], min_score: int
) -> Dict[int, Tuple[int, str]]:
    """Stream Answers.csv in chunks, keeping the top-scored answer per question."""
    print("Scanning Answers.csv for the best answer per question ...", flush=True)
    best: Dict[int, Tuple[int, str]] = {}
    chunks = pd.read_csv(
        data_dir / "Answers.csv",
        encoding="latin-1",
        usecols=["ParentId", "Score", "Body"],
        chunksize=200_000,
    )
    for chunk in chunks:
        chunk = chunk.dropna(subset=["Body"])
        chunk = chunk[(chunk["Score"] >= min_score) & chunk["ParentId"].isin(question_ids)]
        for row in chunk.itertuples(index=False):
            current = best.get(row.ParentId)
            if current is None or row.Score > current[0]:
                best[int(row.ParentId)] = (int(row.Score), row.Body)
    print(f"  found qualifying answers for {len(best):,} questions", flush=True)
    return best


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, required=True,
                        help="Folder with Questions.csv and Answers.csv")
    parser.add_argument("--database-url", default=None,
                        help="Postgres DSN (or set DATABASE_URL). Use the direct "
                             "connection, port 5432, for ingestion.")
    parser.add_argument("--max-pairs", type=int, default=60_000)
    parser.add_argument("--min-question-score", type=int, default=2)
    parser.add_argument("--min-answer-score", type=int, default=2)
    parser.add_argument("--batch-size", type=int, default=256)
    parser.add_argument("--embedding-model",
                        default="sentence-transformers/all-MiniLM-L6-v2")
    args = parser.parse_args()

    dsn = args.database_url or os.getenv("DATABASE_URL")
    if not dsn:
        print("ERROR: pass --database-url or set DATABASE_URL.")
        return 1

    questions = load_questions(args.data_dir, args.min_question_score)
    best = load_best_answers(args.data_dir, set(questions["Id"]), args.min_answer_score)

    questions = questions[questions["Id"].isin(best.keys())]
    questions = (
        questions.sort_values("Score", ascending=False)
        .head(args.max_pairs)
        .reset_index(drop=True)
    )
    print(f"Selected {len(questions):,} Q&A pairs (cap {args.max_pairs:,}).", flush=True)

    # heavy imports here so --help stays fast
    import psycopg
    from sentence_transformers import SentenceTransformer

    print(f"Loading embedding model: {args.embedding_model} ...", flush=True)
    model = SentenceTransformer(args.embedding_model)

    schema_sql = SCHEMA_PATH.read_text()
    started = time.time()
    inserted = 0

    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            for statement in schema_sql.split(";"):
                if statement.strip():
                    cur.execute(statement)
            conn.commit()

            total = len(questions)
            for start in range(0, total, args.batch_size):
                batch = questions.iloc[start : start + args.batch_size]
                rows, texts = [], []
                for q in batch.itertuples(index=False):
                    answer_score, answer_html = best[int(q.Id)]
                    question_text = html_to_text(q.Body)[:2000]
                    answer_text = html_to_text(answer_html)[:4000]
                    texts.append(f"{q.Title}\n{question_text[:1500]}")
                    rows.append([
                        int(q.Id),
                        str(q.Title),
                        question_text,
                        answer_text,
                        int(q.Score),
                        answer_score,
                        f"https://stackoverflow.com/questions/{int(q.Id)}",
                    ])

                vectors = model.encode(texts, normalize_embeddings=True,
                                       show_progress_bar=False)
                params = [
                    row + ["[" + ",".join(str(float(x)) for x in vec) + "]"]
                    for row, vec in zip(rows, vectors)
                ]
                cur.executemany(INSERT_SQL, params)
                conn.commit()
                inserted += len(params)
                elapsed = time.time() - started
                print(f"  {inserted:,}/{total:,} ({100 * inserted / total:.1f}%) "
                      f"- {elapsed:.0f}s", flush=True)

            print("Building HNSW index ...", flush=True)
            cur.execute(HNSW_INDEX_SQL)
            cur.execute("ANALYZE qa_pairs")
            conn.commit()

    print(f"Done. {inserted:,} pairs in {time.time() - started:.0f}s.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
