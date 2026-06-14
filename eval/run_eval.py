#!/usr/bin/env python3
"""Run the eval queries against a running instance and write eval/TEST_RESULTS.md.

    python eval/run_eval.py --base-url http://localhost:8000
    python eval/run_eval.py --base-url https://your-space.hf.space
"""
import argparse
import datetime
import json
import time
from pathlib import Path

import httpx

QUERIES = [
    ("core syntax", "What is the difference between a list and a tuple in Python?"),
    ("core syntax", "How do I merge two dictionaries in Python?"),
    ("debugging", "Why am I getting a KeyError when accessing my dictionary, and how do I avoid it?"),
    ("data science", "How do I iterate over the rows of a pandas DataFrame?"),
    ("conceptual", "What does the Global Interpreter Lock (GIL) do, and why does it matter for multithreading?"),
    ("code-heavy", "How do decorators work in Python? Show a simple example."),
    ("core syntax", "How do I read a large file line by line without loading the whole file into memory?"),
    ("conceptual", "What is the difference between __str__ and __repr__ in Python?"),
    ("EDGE: post-2016 feature", "How does the walrus operator := work in Python 3.8?"),
    ("EDGE: post-2016 feature", "How do I use structural pattern matching (the match statement) in Python 3.10?"),
    ("EDGE: off-topic", "What is the best Java web framework?"),
    ("EDGE: vague input", "My code is broken. Fix it."),
]

OUTPUT = Path(__file__).with_name("TEST_RESULTS.md")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--timeout", type=float, default=90.0)
    parser.add_argument("--delay", type=float, default=6.0,
                        help="Seconds to wait between queries to stay under the "
                             "LLM provider's per-minute token limit (Groq free tier).")
    args = parser.parse_args()
    base = args.base_url.rstrip("/")

    health = httpx.get(f"{base}/health", timeout=args.timeout).json()
    print(f"/health -> {health}")

    lines = [
        "# API Test Results — Python Programming Q&A Assistant",
        "",
        f"- **Run at:** {datetime.datetime.now(datetime.timezone.utc).isoformat()}",
        f"- **Target:** `{base}`",
        f"- **/health:** `{json.dumps(health)}`",
        "",
        "## Summary",
        "",
        "| # | Category | Question | Grounded | Sources | Latency (ms) |",
        "|---|----------|----------|----------|---------|--------------|",
    ]
    details = ["", "## Detailed responses", ""]

    for i, (category, question) in enumerate(QUERIES, start=1):
        if i > 1 and args.delay:
            time.sleep(args.delay)
        print(f"[{i}/{len(QUERIES)}] {question[:70]}")
        try:
            response = httpx.post(f"{base}/ask", json={"question": question},
                                  timeout=args.timeout)
            response.raise_for_status()
            body = response.json()
            grounded = body["grounded"]
            n_sources = len(body["sources"])
            latency = body["latency_ms"]
            answer = body["answer"]
            sources_md = "\n".join(
                f"- [{s['title']}]({s['link']}) — similarity {s['similarity']}, "
                f"answer score {s['answer_score']}"
                for s in body["sources"]
            ) or "_none_"
        except Exception as exc:  # noqa: BLE001 — we want to record any failure
            grounded, n_sources, latency = "ERROR", 0, "-"
            answer, sources_md = f"Request failed: {exc}", "_none_"

        lines.append(
            f"| {i} | {category} | {question} | {grounded} | {n_sources} | {latency} |"
        )
        details += [
            f"### {i}. [{category}] {question}",
            "",
            f"**Grounded:** {grounded} — **Latency:** {latency} ms",
            "",
            "**Answer:**",
            "",
            "> " + answer.replace("\n", "\n> "),
            "",
            "**Sources:**",
            "",
            sources_md,
            "",
            "**Observation:** _<fill in: correctness, grounding quality, citation use, anything surprising>_",
            "",
            "---",
            "",
        ]

    notes = [
        "",
        "## What to look for when reviewing",
        "",
        "- **Grounding:** answers should cite [S#] sources; claims should trace back to the linked Stack Overflow threads.",
        "- **Short-circuiting (low similarity):** clearly out-of-scope input below the `MIN_SIMILARITY` floor (e.g. the CSS question, the vague 'fix my code' prompt) returns `grounded: false` with no sources and no LLM call.",
        "- **Adjacent-domain limitation (by design, documented):** a single bi-encoder cosine score does not separate Python from near-Python. The Java-framework query still retrieves Python pairs above the floor, so it is *not* refused; instead the grounding prompt makes the model hedge ('the context does not provide enough information') rather than fabricate. This is the bi-encoder limitation called out on the deck and in the README, and is reflected in the `refusal_precision` metric in `golden_scores.json`. The fix is hybrid retrieval + a relevance check, not a higher floor.",
        "- **Corpus boundary:** the corpus ends in late 2016, so post-2016 features (walrus operator, `match` statement) have no strong match. The grounding prompt is the backstop here — the model should flag missing/outdated coverage rather than invent syntax.",
        "- **Outdated idioms:** some retrieved answers are Python 2 era; the prompt instructs the model to flag these.",
        "",
    ]

    OUTPUT.write_text("\n".join(lines + details + notes), encoding="utf-8")
    print(f"\nWrote {OUTPUT}")


if __name__ == "__main__":
    main()
