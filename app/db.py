"""asyncpg pool and pgvector literal helpers."""
from typing import Sequence

import asyncpg


async def create_pool(dsn: str) -> asyncpg.Pool:
    # statement_cache_size=0 is required behind a transaction-mode pooler
    # (Supabase pgbouncer on 6543); it's harmless on a direct connection.
    return await asyncpg.create_pool(
        dsn=dsn,
        min_size=1,
        max_size=5,
        command_timeout=30,
        statement_cache_size=0,
    )


def vector_literal(vector: Sequence[float]) -> str:
    return "[" + ",".join(str(float(x)) for x in vector) + "]"
