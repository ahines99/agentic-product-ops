"""Paid, opt-in evaluation of initial requirements analysis with real Anthropic calls.

Every model call is reserved against a durable, explicit spend cap before it is sent. Results are
stored in a local SQLite file, so rerunning the same command replays finished cases instead of
paying again. Every attempt is kept, including failures. Scores are deterministic keyword checks
(see ``agentic_product_ops.evaluation.model_eval``), not independent semantic adjudication.

Example:
    python -m uv run python scripts/run_model_eval.py --allow-paid-execution \
        --cases evals/fixtures/m2-model-cases.json --key-file .local/anthropic.env \
        --max-spend 20 --authorization model-eval-2026-09-30 \
        --database out/model-eval.db --output evals/reports/model-eval-2026-09-30.json
"""

import argparse
import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from agentic_product_ops.adapters.model.anthropic import AnthropicProvider
from agentic_product_ops.adapters.model.contracts import ModelBudget, RuntimeConfiguration
from agentic_product_ops.adapters.model.runner import RunStopped
from agentic_product_ops.adapters.persistence.store import (
    Conflict,
    Missing,
    Store,
    engine,
    metadata,
)
from agentic_product_ops.domain.contracts import WorkSpecification
from agentic_product_ops.evaluation.model_eval import answer, extract, intake, score, summarize
from agentic_product_ops.pilot.config import secret_from_env
from agentic_product_ops.policies.validation import PolicyError, ServerPolicy
from agentic_product_ops.services.revisions import revise_specification
from agentic_product_ops.services.spending import SpendingProvider, spending_summary

MODEL = "claude-opus-5-5"
# Conservative reservation rates used by the pilot. Reservations bound spend from above.
RESERVE_INPUT, RESERVE_OUTPUT = Decimal("8"), Decimal("20")
# Published standard rates recorded in docs/history/v05-validation-record.md, for estimates only.
STANDARD_INPUT, STANDARD_OUTPUT = Decimal("4"), Decimal("20")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-paid-execution", action="store_true", required=True)
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--key-file", type=Path, required=True)
    parser.add_argument("--max-spend", type=Decimal, required=True)
    parser.add_argument("--authorization", required=True)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--only", nargs="*", default=None)
    parser.add_argument("--configuration-id", default="model-eval-v1")
    parser.add_argument(
        "--answers",
        type=Path,
        help="Round 2: product-owner answers keyed by case and question ID",
    )
    args = parser.parse_args()

    corpus = json.loads(args.cases.read_text(encoding="utf-8"))
    cases = [c for c in corpus["cases"] if args.only is None or c["id"] in args.only]
    policy = ServerPolicy(
        version="pilot-v1",
        workspace_id="model-eval",
        teams=("product",),
        repositories=(),
        allow_any_repository=True,
        approvers=("evaluator",),
        security_approvers=("evaluator",),
    )
    configuration = RuntimeConfiguration(
        configuration_id=args.configuration_id,
        provider_id="anthropic-messages",
        model=MODEL,
        budget=ModelBudget(
            max_calls=6,
            max_input_bytes=200000,
            max_output_tokens=6000,
            max_estimated_cost=Decimal("4"),
            input_cost_per_million=RESERVE_INPUT,
            output_cost_per_million=RESERVE_OUTPUT,
        ),
    )
    args.database.parent.mkdir(parents=True, exist_ok=True)
    database = engine(f"sqlite:///{args.database}", testing=True)
    metadata.create_all(database)
    store = Store(database)
    provider = SpendingProvider(
        store,
        policy.workspace_id,
        args.authorization,
        AnthropicProvider(
            model=MODEL,
            api_key=secret_from_env(args.key_file, "ANTHROPIC_API_KEY"),
            allow_paid_execution=True,
        ),
        model=MODEL,
        maximum=args.max_spend,
        input_rate=RESERVE_INPUT,
        output_rate=RESERVE_OUTPUT,
    )
    answers = json.loads(args.answers.read_text(encoding="utf-8")) if args.answers else None
    runs, scores = [], []
    for case in cases:
        if answers is not None:
            if case["id"] not in answers:
                continue
            identifier = str(
                intake(case["id"], case["request"], policy, datetime.now(UTC)).specification_id
            )
            current = WorkSpecification.model_validate_json(
                json.dumps(store.get(policy.workspace_id, "specification", identifier))
            )
            with database.begin() as conn:
                for question in current.unresolved_questions:
                    text = answers[case["id"]].get(question.id)
                    if question.blocking and question.resolution is None and text:
                        current = answer(
                            store, conn, current, question.id, text, "evaluator", datetime.now(UTC)
                        )
            try:
                result = revise_specification(
                    store, identifier, current.content_digest, policy, configuration, provider
                )
                observed = extract(result)
            except (RunStopped, PolicyError, Conflict, Missing) as error:
                observed = {
                    "state": "ERROR",
                    "reason": type(error).__name__,
                    "requirements": [],
                    "blocking_questions": [],
                    "work_items": [],
                    "calls": 0,
                }
            # After answers every case should reach a reviewed proposal.
            expected = {**case, "expected_outcome": "propose", "must_ask_about": []}
            runs.append({"case": case, "answers": answers[case["id"]], "observed": observed})
            scores.append(score(expected, observed))
            print(json.dumps({"case": case["id"], "state": observed["state"]}), flush=True)
            continue
        seed = intake(case["id"], case["request"], policy, datetime.now(UTC))
        identifier = str(seed.specification_id)
        try:
            seed = WorkSpecification.model_validate_json(
                json.dumps(store.get(policy.workspace_id, "specification", identifier, 1))
            )
        except Missing:
            with database.begin() as conn:
                store.put(conn, policy.workspace_id, "specification", identifier, 1, seed)
        try:
            result = revise_specification(
                store,
                identifier,
                seed.content_digest,
                policy,
                configuration,
                provider,
                initial=True,
            )
            observed = extract(result)
        except (RunStopped, PolicyError, Conflict, Missing) as error:
            observed = {
                "state": "ERROR",
                "reason": type(error).__name__,
                "requirements": [],
                "blocking_questions": [],
                "work_items": [],
                "calls": 0,
            }
        runs.append({"case": case, "observed": observed})
        scores.append(score(case, observed))
        print(json.dumps({"case": case["id"], "state": observed["state"]}), flush=True)

    spend = spending_summary(store, policy.workspace_id, args.authorization)
    input_tokens, output_tokens = spend["input_tokens"], spend["output_tokens"]
    report = {
        "schema_version": "1",
        "generated_at": datetime.now(UTC).isoformat(),
        "model": MODEL,
        "configuration": configuration.model_dump(mode="json"),
        "corpus_author": corpus.get("author"),
        "cases_file": args.cases.as_posix(),
        "summary": summarize(scores),
        "spend": {
            **spend,
            "estimated_usd_standard_rates": str(
                (input_tokens * STANDARD_INPUT + output_tokens * STANDARD_OUTPUT) / 1_000_000
            ),
            "cap_usd": str(args.max_spend),
        },
        "scores": scores,
        "runs": runs,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"summary": report["summary"], "spend": report["spend"]}, indent=2))
    database.dispose()


if __name__ == "__main__":
    main()
