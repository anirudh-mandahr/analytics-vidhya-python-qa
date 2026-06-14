"""App settings, read from the environment / .env."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    database_url: str = "postgresql://postgres:postgres@localhost:5432/postgres"

    # LLM provider: "groq" (native) or "openai" (any OpenAI-compatible endpoint,
    # e.g. OpenRouter / Together / OpenAI). The chain is otherwise identical, so
    # swapping providers is a config change, not a code change.
    llm_provider: str = "groq"
    groq_api_key: str = ""
    openai_api_key: str = ""
    openai_base_url: str = ""  # e.g. https://openrouter.ai/api/v1

    llm_model: str = "llama-3.3-70b-versatile"
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"

    # retrieval
    top_k: int = 5
    min_similarity: float = 0.45  # drop cosine hits below this
    max_context_chars_per_doc: int = 2500

    # llm
    llm_temperature: float = 0.1
    llm_max_tokens: int = 1024
    llm_timeout_s: float = 30.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
