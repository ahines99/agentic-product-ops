from pathlib import Path

from agentic_product_ops.evaluation.harness import evaluate


def test_frozen_corpus():
    report = evaluate(Path(__file__).resolve().parents[2] / "evals/fixtures/m0-corpus.json")
    assert report["case_count"] >= 15
    assert report["passed"] == report["case_count"]
    assert not report["independent_authorship"]
    assert report["model_calls"] == 0


def test_expanded_routing_corpus_is_honest_about_scope():
    report = evaluate(Path(__file__).resolve().parents[2] / "evals/fixtures/m1-routing-corpus.json")
    assert report["case_count"] == 45
    assert report["passed"] == 45
    assert not report["human_validation"]
    assert not report["independent_authorship"]
