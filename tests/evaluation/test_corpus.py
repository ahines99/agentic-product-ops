from pathlib import Path

from agentic_product_ops.evaluation.harness import evaluate


def test_frozen_corpus():
    report = evaluate(Path(__file__).resolve().parents[2] / "evals/fixtures/m0-corpus.json")
    assert report["case_count"] >= 15
    assert report["passed"] == report["case_count"]
    assert not report["independent_authorship"]
    assert report["model_calls"] == 0
