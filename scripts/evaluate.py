"""Run the frozen corpus and preserve each explicitly named report without overwriting."""

import argparse
from pathlib import Path

from agentic_product_ops.evaluation.harness import write_report

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--corpus", type=Path, default=Path("evals/fixtures/m0-corpus.json"))
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
write_report(args.corpus, args.output)
