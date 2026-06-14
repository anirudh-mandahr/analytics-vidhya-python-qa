"""Query embedding with sentence-transformers.

The model loads on first use and encoding runs in a thread, so the event loop
doesn't block. The import is deferred so the unit tests run without torch.
"""
import asyncio
from typing import List, Optional

_model = None
_model_name_loaded: Optional[str] = None


def _load_model(model_name: str):
    global _model, _model_name_loaded
    if _model is None or _model_name_loaded != model_name:
        from sentence_transformers import SentenceTransformer

        _model = SentenceTransformer(model_name)
        _model_name_loaded = model_name
    return _model


async def embed_query(text: str, model_name: str) -> List[float]:
    model = await asyncio.to_thread(_load_model, model_name)
    vector = await asyncio.to_thread(
        lambda: model.encode(text, normalize_embeddings=True)
    )
    return vector.tolist()
