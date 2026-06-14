"""Cosine similarity search over qa_pairs (pgvector)."""
from typing import Any, Dict, List, Sequence

from .db import vector_literal

SEARCH_SQL = """
SELECT
    id,
    title,
    question,
    answer,
    question_score,
    answer_score,
    link,
    1 - (embedding <=> $1::vector) AS similarity
FROM qa_pairs
ORDER BY embedding <=> $1::vector
LIMIT $2
"""


async def search(
    pool,
    query_vector: Sequence[float],
    top_k: int,
    min_similarity: float,
) -> List[Dict[str, Any]]:
    # The min_similarity cutoff is what lets /ask refuse off-topic questions
    # before it ever calls the LLM.
    rows = await pool.fetch(SEARCH_SQL, vector_literal(query_vector), top_k)
    docs = [dict(row) for row in rows]
    return [d for d in docs if float(d["similarity"]) >= min_similarity]
