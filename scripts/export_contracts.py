"""Freeze the public handoff JSON Schema; CI checks drift without fetching remote references."""

import argparse
import json
from pathlib import Path

from agentic_product_ops.domain.handoff import SignedHandoff

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    target = ROOT / "src/product_ops_handoff/handoff-v2.schema.json"
    document = json.dumps(SignedHandoff.model_json_schema(), indent=2, sort_keys=True) + "\n"
    if args.check:
        if target.read_text(encoding="utf-8") != document:
            raise SystemExit(
                "Public contract schema drift; regenerate and review the protocol change."
            )
    else:
        target.write_text(document, encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
