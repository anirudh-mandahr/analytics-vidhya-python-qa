#!/usr/bin/env python3
"""Automated scoring against a golden set.

run_eval.py records responses for manual review. This script scores them, so
quality is a number you can track across changes instead of a vibe.

Metrics (no LLM judge needed):
  - answerable_recall   : on questions that SHOULD be answered, did we ground an answer?
  - refusal_precision   : on questions that should NOT be answered, did we refuse?
  - citation_rate       : fraction of grounded answers that actually cite [S#]
  - expected_source_hit : if a golden source id is known, is it in the returned sources?
  - mean_latency_ms

Optional, if `ragas` is installed and GROQ/OpenAI keys are set, you can extend
this with faithfulness / answer_relevancy. Kept out of the default path so the
script runs with zero extra deps.

    python eval/golden_eval.py --base-url http://localhost:8000
"""
import argparse
import json
import re
import statistics
from pathlib import Path

import httpx

# Each case: question, whether it should be answerable from the 2016 corpus,
# and (optionally) a Stack Overflow question id we expect to retrieve.
GOLDEN = [
    {"q": "How do I merge two dictionaries in Python?", "answerable": True, "expected_id": 15677693},
    {"q": "What is the difference between a list and a tuple?", "answerable": True, "expected_id": 626759},
    {"q": "How do I iterate over rows of a pandas DataFrame?", "answerable": True, "expected_id": 16476924},
    {"q": "What does the Global Interpreter Lock do?", "answerable": True, "expected_id": 265687},
    {"q": "How do Python decorators work?", "answerable": True, "expected_id": 3860539},
    {"q": "How do I read a file line by line in Python?", "answerable": True},
    {"q": "What is the difference between __str__ and __repr__?", "answerable": True},
    {"q": "How do I reverse a list in Python?", "answerable": True},
    # Should be refused: off-topic or out-of-corpus.
    {"q": "What is the best Java web framework?", "answerable": False},
    {"q": "How do I center a div in CSS?", "answerable": False},
    {"q": "My code is broken. Fix it.", "answerable": False},
    {"q": "How does the walrus operator := work in Python 3.8?", "answerable": False},
]

CITATION = re.compile(r"\[S\d+\]")


def ask(base, question, timeout):
    r = httpx.post(f"{base}/ask", json={"question": question}, timeout=timeout)
    r.raise_for_status()
    return r.json()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://localhost:8000")
    ap.add_argument("--timeout", type=float, default=90.0)
    ap.add_argument("--out", default=str(Path(__file__).with_name("golden_scores.json")))
    args = ap.parse_args()
    base = args.base_url.rstrip("/")

    rows, latencies = [], []
    for case in GOLDEN:
        body = ask(base, case["q"], args.timeout)
        latencies.append(body["latency_ms"])
        rows.append({
            "q": case["q"],
            "answerable": case["answerable"],
            "grounded": body["grounded"],
            "n_sources": len(body["sources"]),
            "cited": bool(CITATION.search(body["answer"])) if body["grounded"] else False,
            "expected_id": case.get("expected_id"),
            "source_ids": [s["id"] for s in body["sources"]],
        })
        print(f"{'OK ' if body['grounded']==case['answerable'] else 'XX '}"
              f"{case['q'][:60]}  grounded={body['grounded']}")

    answerable = [r for r in rows if r["answerable"]]
    refuse = [r for r in rows if not r["answerable"]]
    grounded_rows = [r for r in rows if r["grounded"]]
    with_expected = [r for r in rows if r["expected_id"] is not None]

    def frac(xs):
        return round(sum(xs) / len(xs), 3) if xs else None

    metrics = {
        "n_cases": len(rows),
        "answerable_recall": frac([r["grounded"] for r in answerable]),
        "refusal_precision": frac([not r["grounded"] for r in refuse]),
        "citation_rate": frac([r["cited"] for r in grounded_rows]),
        "expected_source_hit": frac(
            [r["expected_id"] in r["source_ids"] for r in with_expected]
        ),
        "mean_latency_ms": round(statistics.mean(latencies), 1),
        "p95_latency_ms": round(sorted(latencies)[int(len(latencies) * 0.95) - 1], 1),
    }

    Path(args.out).write_text(json.dumps({"metrics": metrics, "rows": rows}, indent=2))
    print("\n=== metrics ===")
    for k, v in metrics.items():
        print(f"  {k}: {v}")
    print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
