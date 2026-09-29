"""Offline CLI. No credentials, model calls, repository execution, or live publication."""

import argparse
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

from pydantic import ValidationError

from agentic_product_ops.adapters.artifacts.handoff import Handoff, export_handoff
from agentic_product_ops.adapters.linear.offline import FakeLinear, OfflinePublisher, build_plan
from agentic_product_ops.domain.contracts import (
    ApprovalScope,
    SpecificationApproval,
    WorkSpecification,
)
from agentic_product_ops.policies.validation import PolicyError, ServerPolicy
from agentic_product_ops.services.drafting import draft, load_fixture, output_json
from agentic_product_ops.workflows.lifecycle import State


def bounded_read(path: Path, limit: int = 1_000_000) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise ValueError("input must be a regular, non-symlink file")
    with path.open("rb") as handle:
        data = handle.read(limit + 1)
    if len(data) > limit:
        raise ValueError("input exceeds size limit")
    return data


def simulated_approval(spec: WorkSpecification, now: datetime) -> SpecificationApproval:
    plan = build_plan(spec, ServerPolicy())
    return SpecificationApproval(
        approval_id=UUID("cccccccc-cccc-4ccc-8ccc-cccccccccccc"),
        specification_id=spec.specification_id,
        revision=spec.revision,
        content_digest=spec.content_digest,
        actor_id="offline-reviewer",
        decision="approve",
        scope=ApprovalScope(
            workspace_id="offline-workspace",
            team_ids=tuple(sorted({w.proposed_team_id for w in spec.work_items})),
            repository_ids=tuple(
                sorted({w.repository_id for w in spec.work_items if w.repository_id is not None})
            ),
            plan_digest=plan.content_digest,
            operation_keys=tuple(o.operation_key for o in plan.operations),
            allowed_mutation_count=len(plan.operations),
        ),
        issued_at=now,
        expires_at=now + timedelta(minutes=30),
        policy_version="m0-v1",
    )


def demo(destination: Path) -> None:
    spec = load_fixture("handoff")
    policy, now = ServerPolicy(), datetime(2026, 9, 28, tzinfo=UTC)
    plan, approval = build_plan(spec, policy), simulated_approval(spec, now)
    provider = FakeLinear()
    publisher = OfflinePublisher(provider)
    receipts = publisher.publish(
        spec, plan, approval, policy, authenticated_actor="offline-reviewer", now=now
    )
    publisher.publish(spec, plan, approval, policy, authenticated_actor="offline-reviewer", now=now)
    handoff = export_handoff(spec, approval, plan, receipts, policy)
    # Exclusive files: never silently overwrite an immutable evidence artifact.
    destination.mkdir(parents=True, exist_ok=True)
    for name, document in (
        ("specification.json", spec),
        ("approval.simulated.json", approval),
        ("plan.json", plan),
        ("handoff.simulated.json", handoff),
    ):
        with (destination / name).open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(document.model_dump_json(indent=2) + "\n")
    print(
        json.dumps(
            {
                "mode": "offline_simulation",
                "fake_provider_calls": provider.calls,
                "duplicate_commands": 1,
                "handoff_digest": handoff.artifact_digest,
            }
        )
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    drafting = commands.add_parser(
        "draft", help="Match an authored fixture or stop for clarification"
    )
    drafting.add_argument("--input", type=Path, required=True)
    validate = commands.add_parser("validate", help="Validate a WorkSpecification JSON artifact")
    validate.add_argument("--input", type=Path, required=True)
    demonstration = commands.add_parser(
        "demo", help="Write a simulated approval/publication/handoff"
    )
    demonstration.add_argument("--output", type=Path, required=True)
    verify = commands.add_parser(
        "verify-handoff", help="Verify a simulated handoff artifact digest"
    )
    verify.add_argument("--input", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "draft":
            text = bounded_read(args.input, 16000).decode("utf-8")
            spec, state = draft(text)
            print(output_json(spec, state))
            return 2 if state == State.AWAITING_CLARIFICATION else 0
        if args.command == "validate":
            spec = WorkSpecification.model_validate_json(bounded_read(args.input))
            print(json.dumps({"valid": True, "content_digest": spec.content_digest}))
        elif args.command == "verify-handoff":
            handoff = Handoff.model_validate_json(bounded_read(args.input))
            print(
                json.dumps(
                    {
                        "mode": handoff.mode,
                        "valid": True,
                        "artifact_digest": handoff.artifact_digest,
                    }
                )
            )
        elif args.command == "demo":
            demo(args.output)
    except (OSError, UnicodeError, ValueError, ValidationError, PolicyError) as error:
        # Do not echo user text / Pydantic input_value or provider bodies into logs.
        print(
            json.dumps(
                {
                    "error": type(error).__name__,
                    "message": "Offline operation rejected; "
                    "check schema, policy, input size, and output file existence.",
                }
            ),
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
