"""Request and response models for the API."""
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


class AskRequest(BaseModel):
    question: str = Field(
        ...,
        max_length=2000,
        description="A Python-related question from a learner.",
        examples=["How do I merge two dictionaries in Python?"],
    )

    @field_validator("question")
    @classmethod
    def question_must_have_content(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 3:
            raise ValueError("question must have at least 3 non-whitespace characters")
        return value


class Source(BaseModel):
    id: int = Field(description="Stack Overflow question id")
    title: str
    link: str
    similarity: float = Field(description="Cosine similarity between query and question")
    answer_score: Optional[int] = None


class AskResponse(BaseModel):
    answer: str
    sources: List[Source]
    grounded: bool = Field(
        description="True if generated from retrieved context, "
        "False if no relevant context was found."
    )
    latency_ms: float


class HealthResponse(BaseModel):
    status: str
    database: bool
    version: str = "1.0.0"
