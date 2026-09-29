"""Start a temporary loopback Temporal server and run its integration tests without credentials."""

import argparse
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--temporal-cli", type=Path, required=True)
    arguments = parser.parse_args()
    binary = arguments.temporal_cli.resolve(strict=True)
    with socket.socket() as reserved:
        reserved.bind(("127.0.0.1", 0))
        port = reserved.getsockname()[1]
    with tempfile.TemporaryDirectory(prefix="apo-temporal-") as scratch:
        with (Path(scratch) / "server.log").open("w", encoding="utf-8") as log:
            server = subprocess.Popen(
                [
                    str(binary),
                    "server",
                    "start-dev",
                    "--ip",
                    "127.0.0.1",
                    "--port",
                    str(port),
                    "--headless",
                    "--db-filename",
                    str(Path(scratch) / "history.db"),
                ],
                stdout=log,
                stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            try:
                ready = False
                for _ in range(100):
                    if server.poll() is not None:
                        raise RuntimeError("local Temporal server exited")
                    with socket.socket() as probe:
                        if probe.connect_ex(("127.0.0.1", port)) == 0:
                            ready = True
                            break
                    time.sleep(0.1)
                if not ready:
                    raise RuntimeError("local Temporal server startup timed out")
                subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "pytest",
                        "tests/runtime/test_temporal.py",
                        "tests/runtime/test_connected_governance.py",
                        "tests/integration/test_revisions.py",
                        "--no-cov",
                        "-q",
                    ],
                    cwd=ROOT,
                    check=True,
                    env={**os.environ, "PRODUCT_OPS_TEST_TEMPORAL_ADDRESS": f"127.0.0.1:{port}"},
                )
            finally:
                server.terminate()
                server.wait(timeout=15)


if __name__ == "__main__":
    main()
