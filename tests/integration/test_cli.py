import json
import sys
from pathlib import Path

import pytest

from agentic_product_ops.cli import main

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    "name,status,state",
    [
        ("feature-request.md", 0, "PROPOSED"),
        ("ambiguous-request.md", 2, "AWAITING_CLARIFICATION"),
    ],
)
def test_draft(monkeypatch, capsys, name, status, state):
    monkeypatch.setattr(
        sys, "argv", ["product-ops", "draft", "--input", str(ROOT / "examples" / name)]
    )
    assert main() == status
    assert json.loads(capsys.readouterr().out)["state"] == state


def test_demo_and_validate(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(sys, "argv", ["product-ops", "demo", "--output", str(tmp_path)])
    assert main() == 0
    assert json.loads(capsys.readouterr().out)["fake_provider_calls"] == 1
    monkeypatch.setattr(
        sys, "argv", ["product-ops", "validate", "--input", str(tmp_path / "specification.json")]
    )
    assert main() == 0
    capsys.readouterr()
    monkeypatch.setattr(
        sys,
        "argv",
        ["product-ops", "verify-handoff", "--input", str(tmp_path / "handoff.simulated.json")],
    )
    assert main() == 0
    assert json.loads(capsys.readouterr().out)["valid"]


def test_errors_redacted_and_bounded(monkeypatch, capsys, tmp_path):
    source = tmp_path / "input.txt"
    source.write_text("PRIVATE_INPUT_MARKER" * 2000, encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["product-ops", "draft", "--input", str(source)])
    assert main() == 1
    assert "PRIVATE_INPUT_MARKER" not in capsys.readouterr().err


def test_demo_does_not_overwrite(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(sys, "argv", ["product-ops", "demo", "--output", str(tmp_path)])
    assert main() == 0
    before = (tmp_path / "specification.json").read_bytes()
    assert main() == 1
    assert (tmp_path / "specification.json").read_bytes() == before


@pytest.mark.parametrize(
    "name,code,calls", [("feature-request.md", 0, 3), ("ambiguous-request.md", 2, 1)]
)
def test_recorded_roles_with_actual_snapshot(monkeypatch, capsys, tmp_path, name, code, calls):
    marker = tmp_path / "executed.txt"
    (tmp_path / "module.py").write_text(
        f"from pathlib import Path\nPath({str(marker)!r}).touch()\ndef sample(): pass\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "product-ops",
            "roles-demo",
            "--input",
            str(ROOT / "examples" / name),
            "--repository-root",
            str(tmp_path),
            "--repository-id",
            "sample",
        ],
    )
    assert main() == code
    result = json.loads(capsys.readouterr().out)
    assert len(result["receipts"]) == calls
    assert not marker.exists()


def test_inspection_cli_pin(monkeypatch, capsys, tmp_path):
    (tmp_path / "module.py").write_text("def sample(): pass\n", encoding="utf-8")
    args = [
        "product-ops",
        "inspect-repository",
        "--root",
        str(tmp_path),
        "--repository-id",
        "sample",
    ]
    monkeypatch.setattr(sys, "argv", args)
    assert main() == 0
    snapshot = json.loads(capsys.readouterr().out)
    monkeypatch.setattr(sys, "argv", [*args, "--expected-digest", snapshot["digest"]])
    assert main() == 0
    capsys.readouterr()
    (tmp_path / "module.py").write_text("def changed(): pass\n", encoding="utf-8")
    assert main() == 1
