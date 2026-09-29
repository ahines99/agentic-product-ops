"""Private pilot configuration and bounded credential loading, never dotenv execution."""

import csv
import getpass
import io
import json
import os
import subprocess
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import Field, SecretStr, model_validator
from sqlalchemy.engine import make_url

from agentic_product_ops.adapters.linear.native_plan import LinearScope
from agentic_product_ops.cli import bounded_read
from agentic_product_ops.domain.contracts import ID, Contract


class PilotSettings(Contract):
    schema_version: Literal["1"] = "1"
    workspace: ID = "product-ops-pilot"
    operator: ID = "alex-hines"
    subject: str
    database_url: str
    temporal_address: str = "127.0.0.1:18233"
    api_port: Annotated[int, Field(ge=1024, le=65535)] = 18001
    linear_scope: LinearScope
    linear_key_file: str
    anthropic_key_file: str
    github_key_file: str | None = None
    model: Literal["claude-opus-5-5"] = "claude-opus-5-5"
    spend_authorization: ID
    maximum_spend: Annotated[str, Field(pattern=r"^\d+(\.\d{1,2})?$")]
    allow_paid_execution: bool = False
    allow_publication: bool = False

    @model_validator(mode="after")
    def local_profile(self) -> Self:
        database = make_url(self.database_url)
        if (
            database.drivername != "postgresql+psycopg"
            or database.host not in {"127.0.0.1", "localhost"}
            or database.database != "product_ops_pilot"
            or database.query
        ):
            raise ValueError("pilot requires a separate loopback product_ops_pilot database")
        host, separator, port = self.temporal_address.rpartition(":")
        if host not in {"127.0.0.1", "localhost"} or not separator or not port.isdigit():
            raise ValueError("pilot Temporal must use loopback")
        if not 1024 <= int(port) <= 65535 or Decimal(self.maximum_spend) <= 0:
            raise ValueError("invalid pilot port or budget")
        for path in (self.linear_key_file, self.anthropic_key_file, self.github_key_file):
            if path is not None and not Path(path).is_absolute():
                raise ValueError("credential references must be absolute paths")
        return self


def secret_from_env(path: Path, name: str) -> SecretStr:
    found = []
    for line in bounded_read(path, 64000).decode("utf-8-sig").splitlines():
        key, separator, value = line.strip().partition("=")
        if separator and key.strip() == name:
            found.append(value.strip().strip("\"'"))
    if len(found) != 1 or not found[0] or any(c.isspace() for c in found[0]):
        raise ValueError("missing or malformed configured credential")
    return SecretStr(found[0])


def private_directory(path: Path) -> str:
    if (
        path.is_symlink()
        or path.is_junction()
        or any(parent.is_symlink() or parent.is_junction() for parent in path.parents)
    ):
        raise ValueError("private directory cannot traverse links")
    path = path.resolve()
    if path.exists() and (path.is_symlink() or not path.is_dir()):
        raise ValueError("private directory must be a real directory")
    path.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        system = Path(os.environ["SystemRoot"]) / "System32"
        record = subprocess.check_output(  # noqa: S603
            [str(system / "whoami.exe"), "/user", "/fo", "csv", "/nh"], text=True
        )
        subject = list(csv.reader(io.StringIO(record)))[0][-1]
        result = subprocess.run(  # noqa: S603
            [
                str(system / "icacls.exe"),
                str(path),
                "/inheritance:r",
                "/grant:r",
                f"*{subject}:(OI)(CI)F",
            ],
            capture_output=True,
            check=False,
        )
        if result.returncode:
            raise ValueError("private directory ACL setup failed")
    else:
        path.chmod(0o700)
        subject = "unix-user:" + getpass.getuser()
    return subject


def read_settings(directory: Path) -> PilotSettings:
    return PilotSettings.model_validate_json(bounded_read(directory / "pilot.json"))


def read_secrets(directory: Path) -> dict[str, str]:
    value = json.loads(bounded_read(directory / "pilot-secrets.json", 16000))
    if (
        not isinstance(value, dict)
        or set(value) != {"operator_token", "storage_key", "signing_key"}
        or not all(isinstance(v, str) for v in value.values())
    ):
        raise ValueError("invalid pilot secret record")
    return value
