# Designed for Hugging Face Spaces (Docker SDK) — also works on Render/Railway
# with the port changed. The embedding model is baked into the image so cold
# starts don't download ~90 MB.

FROM python:3.11-slim

# HF Spaces runs containers as a non-root user with uid 1000.
RUN useradd -m -u 1000 user
WORKDIR /app

# CPU-only torch first (prevents pulling multi-GB CUDA wheels).
COPY requirements.txt .
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir -r requirements.txt

# Bake the embedding model into the image.
ENV HF_HOME=/app/.cache
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')" \
    && chown -R user:user /app

COPY --chown=user:user app ./app

USER user
EXPOSE 7860
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "7860"]
