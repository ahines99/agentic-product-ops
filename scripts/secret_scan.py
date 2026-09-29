"""Scan Git-indexed and untracked, nonignored files without echoing detected secrets."""

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    # Default detectors remain enabled; only exact JSON digest lines are nonsecret exceptions.
    inventory = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    paths = sorted(set(filter(None, inventory.stdout.split("\0"))))
    if not paths:
        raise SystemExit("No repository files found to scan.")
    result = subprocess.run(
        [
            "detect-secrets",
            "--cores",
            "1",
            "scan",
            "--no-verify",
            "--exclude-lines",
            r'^\s*"(?:source_digest|content_digest|artifact_digest|corpus_digest|'
            r'specification_digest|digest)": "[a-f0-9]{64}",?\s*$',
            *paths,
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    report = json.loads(result.stdout)
    findings = report["results"]
    if findings:
        for path, entries in findings.items():
            for entry in entries:
                print(f"{path}:{entry['line_number']}: {entry['type']}")
        raise SystemExit("Secret scan failed. Inspect locally; never print raw secret values.")
    print(f"Secret scan passed for {len(paths)} repository files (default detectors and filters).")


if __name__ == "__main__":
    main()
