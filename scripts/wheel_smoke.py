"""Install wheel with locked dependencies, then exercise offline outside the source tree."""

import os
import subprocess
import sys
import tempfile
import venv
from importlib.metadata import version
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    wheels = sorted(
        (ROOT / "dist").glob(f"agentic_product_ops-{version('agentic-product-ops')}-*.whl")
    )
    if len(wheels) != 1:
        raise SystemExit("Build exactly one wheel in dist before smoke testing.")
    with tempfile.TemporaryDirectory(prefix="apo-wheel-") as directory:
        scratch = Path(directory).resolve()
        target = scratch / "venv"
        venv.create(target, with_pip=False)
        executable = target / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        env = {k: v for k, v in os.environ.items() if k not in {"PYTHONPATH", "PYTHONHOME"}}
        requirements = scratch / "runtime-requirements.txt"
        subprocess.run(
            [
                "uv",
                "export",
                "--locked",
                "--no-dev",
                "--no-emit-project",
                "--quiet",
                "--output-file",
                str(requirements),
            ],
            cwd=ROOT,
            env=env,
            check=True,
        )
        subprocess.run(
            [
                "uv",
                "pip",
                "install",
                "--python",
                str(executable),
                "--require-hashes",
                "-r",
                str(requirements),
            ],
            cwd=scratch,
            env=env,
            check=True,
        )
        subprocess.run(
            [
                "uv",
                "pip",
                "install",
                "--offline",
                "--no-deps",
                "--python",
                str(executable),
                str(wheels[0]),
            ],
            cwd=scratch,
            env=env,
            check=True,
        )
        subprocess.run(
            [
                str(executable),
                "-I",
                "-c",
                "from pathlib import Path; import agentic_product_ops as p; "
                f"assert Path(p.__file__).is_relative_to({str(target)!r})",
            ],
            cwd=scratch,
            env=env,
            check=True,
        )
        command = [str(executable), "-I", "-m", "agentic_product_ops.cli"]
        entrypoint = target / ("Scripts/product-ops.exe" if os.name == "nt" else "bin/product-ops")
        subprocess.run(
            [str(entrypoint), "--help"], cwd=scratch, env=env, check=True, capture_output=True
        )
        for name, expected in (("feature-request.md", 0), ("ambiguous-request.md", 2)):
            source = scratch / name
            source.write_bytes((ROOT / "examples" / name).read_bytes())
            result = subprocess.run(
                [*command, "draft", "--input", str(source)],
                cwd=scratch,
                env=env,
                capture_output=True,
                check=False,
            )
            if result.returncode != expected:
                raise SystemExit(f"clean wheel {name} returned {result.returncode}")
            result = subprocess.run(
                [*command, "roles-demo", "--input", str(source)],
                cwd=scratch,
                env=env,
                capture_output=True,
                check=False,
            )
            if result.returncode != expected:
                raise SystemExit(f"clean wheel roles {name} returned {result.returncode}")
        repository = scratch / "sample-repository"
        repository.mkdir()
        (repository / "sample.py").write_text("def sample(): pass\n", encoding="utf-8")
        subprocess.run(
            [
                *command,
                "roles-demo",
                "--input",
                str(scratch / "feature-request.md"),
                "--repository-root",
                str(repository),
                "--repository-id",
                "sample",
            ],
            cwd=scratch,
            env=env,
            capture_output=True,
            check=True,
        )
        subprocess.run(
            [*command, "demo", "--output", str(scratch / "output")],
            cwd=scratch,
            env=env,
            check=True,
        )
        subprocess.run(
            [*command, "verify-handoff", "--input", str(scratch / "output/handoff.simulated.json")],
            cwd=scratch,
            env=env,
            check=True,
        )
    print(
        f"Clean wheel passed on Python {sys.version.split()[0]}, "
        "outside checkout, locked dependencies and offline execution."
    )


if __name__ == "__main__":
    main()
