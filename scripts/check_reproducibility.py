"""Verify regenerated artifacts and two clean sdist/wheel builds are byte-identical."""

import hashlib
import os
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def digests(paths: list[Path]) -> dict[str, str]:
    return {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}


def main() -> None:
    paths = [
        path
        for folder in (
            "src/agentic_product_ops/fixtures",
            "evals/schemas",
            "evals/fixtures",
            "examples",
        )
        for path in (ROOT / folder).glob("*")
        if path.is_file()
    ]
    before = digests(paths)
    for script in ("generate_fixtures.py", "freeze_corpus.py"):
        subprocess.run([sys.executable, str(ROOT / "scripts" / script)], cwd=ROOT, check=True)
    if digests(paths) != before:
        raise SystemExit(
            "Generated artifacts changed; review and commit the updated source/fixtures."
        )
    with tempfile.TemporaryDirectory(prefix="apo-reproduce-") as directory:
        outputs = []
        for name in ("first", "second"):
            destination = Path(directory) / name
            subprocess.run(
                ["uv", "build", "--no-build-isolation", "--out-dir", str(destination)],
                cwd=ROOT,
                check=True,
                env={**os.environ, "SOURCE_DATE_EPOCH": "1780000000"},
            )
            outputs.append(
                {
                    path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                    for path in destination.iterdir()
                    if path.is_file() and path.name != ".gitignore"
                }
            )
            # Build configuration must exclude operator state even in a Git worktree.
            for archive in destination.glob("*.tar.gz"):
                with tarfile.open(archive) as package:
                    for member in package.getnames():
                        components = Path(member).parts[1:]
                        if any(
                            part in {"out", ".local", ".venv", ".env", "__pycache__"}
                            or (part.startswith(".env.") and part != ".env.example")
                            for part in components
                        ):
                            raise SystemExit("Source archive contains excluded local state.")
        if outputs[0] != outputs[1] or len(outputs[0]) != 2:
            raise SystemExit("Build outputs differ or expected wheel/sdist missing.")
    print(f"Regeneration unchanged; sdist and wheel byte-identical across two builds: {outputs[0]}")


if __name__ == "__main__":
    main()
