"""Run all local foundation gates, stopping immediately on the first failure."""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    commands = [
        ["uv", "lock", "--check"],
        ["ruff", "check", "."],
        ["ruff", "format", "--check", "."],
        ["mypy"],
        ["pytest"],
        [sys.executable, "scripts/check_docs.py"],
        [sys.executable, "scripts/secret_scan.py"],
        [sys.executable, "scripts/check_reproducibility.py"],
        ["uv", "build", "--no-build-isolation"],
        [sys.executable, "scripts/wheel_smoke.py"],
        [
            "uv",
            "export",
            "--locked",
            "--no-emit-project",
            "--quiet",
            "--output-file",
            "out/requirements.txt",
        ],
        ["pip-audit", "-r", "out/requirements.txt", "--disable-pip", "--no-deps"],
    ]
    for command in commands:
        print("RUN " + " ".join(command), flush=True)
        subprocess.run(command, cwd=ROOT, check=True)
    print("All local foundation gates passed. Hosted CI and live integrations remain unverified.")


if __name__ == "__main__":
    main()
