"""Prompt, context formatting, and the LCEL answer chain.

Retrieval runs outside the chain (see retriever.py) so /ask can reuse the pool
and bail out before any LLM call when nothing relevant comes back. Generation
itself is just prompt | llm | parser.
"""
from typing import Any, Dict, List

SYSTEM_PROMPT = """You are a Python programming assistant helping data science learners.

You answer questions using ONLY the provided context, which consists of real \
Stack Overflow questions and their top-voted answers about Python.

Rules:
- Ground every claim in the context. Cite supporting sources inline as [S1], [S2], etc.
- Include short, runnable code examples when they help the learner.
- If the context does not contain enough information to answer reliably, say so \
explicitly and answer only what the context supports. Never invent libraries, \
APIs, or behavior that is not in the context.
- The corpus only covers Stack Overflow activity up to late 2016. If an answer \
relies on outdated idioms (e.g. Python 2 syntax), point that out and tell the \
learner to check the current Python docs.
- Be concise, friendly, and direct."""

HUMAN_PROMPT = """Context:
{context}

Learner question: {question}"""

NO_CONTEXT_ANSWER = (
    "I couldn't find any sufficiently relevant Python Q&A in my knowledge base "
    "(Stack Overflow Python questions up to 2016) to answer this reliably, so I "
    "won't guess. If this is a Python question, try rephrasing it with more "
    "detail. Note that I may also lack coverage of Python features released "
    "after 2016."
)


def format_context(docs: List[Dict[str, Any]], max_chars_per_doc: int = 2500) -> str:
    blocks = []
    for i, doc in enumerate(docs, start=1):
        answer = (doc.get("answer") or "")[:max_chars_per_doc]
        blocks.append(
            f"[S{i}] Stack Overflow question: {doc['title']}\n"
            f"Top answer (score {doc.get('answer_score', 'n/a')}):\n"
            f"{answer}\n"
            f"Source: {doc['link']}"
        )
    return "\n\n---\n\n".join(blocks)


def _build_llm(settings):
    """Construct the chat model for the configured provider.

    Generation is identical across providers (prompt | llm | parser); only the
    client differs, so switching is a config change rather than a code change.
    """
    if settings.llm_provider == "openai":
        # Any OpenAI-compatible endpoint (OpenRouter, Together, OpenAI, ...).
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=settings.llm_model,
            api_key=settings.openai_api_key or None,
            base_url=settings.openai_base_url or None,
            temperature=settings.llm_temperature,
            max_tokens=settings.llm_max_tokens,
            timeout=settings.llm_timeout_s,
            max_retries=2,
        )

    from langchain_groq import ChatGroq

    return ChatGroq(
        model=settings.llm_model,
        api_key=settings.groq_api_key or None,
        temperature=settings.llm_temperature,
        max_tokens=settings.llm_max_tokens,
        timeout=settings.llm_timeout_s,
        max_retries=2,
    )


def build_answer_chain(settings):
    from langchain_core.output_parsers import StrOutputParser
    from langchain_core.prompts import ChatPromptTemplate

    llm = _build_llm(settings)
    prompt = ChatPromptTemplate.from_messages(
        [("system", SYSTEM_PROMPT), ("human", HUMAN_PROMPT)]
    )
    return prompt | llm | StrOutputParser()
