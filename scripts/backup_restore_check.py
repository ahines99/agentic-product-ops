"""Back up an explicitly disposable loopback database and verify an isolated restore."""

import argparse
import hashlib
import json
import os
import subprocess
from pathlib import Path
from typing import TypedDict
from uuid import uuid4

import psycopg
from psycopg import sql
from sqlalchemy import select
from sqlalchemy.engine import make_url

from agentic_product_ops.adapters.persistence.store import engine, metadata
from agentic_product_ops.domain.contracts import canonical_digest


class TableSnapshot(TypedDict):
    count: int
    digest: str


def snapshot(url: str) -> dict[str, TableSnapshot]:
    database = engine(url)
    try:
        with database.connect() as conn:
            result: dict[str, TableSnapshot] = {}
            for table in metadata.sorted_tables:
                rows = [dict(row) for row in conn.execute(select(table)).mappings()]
                result[table.name] = {
                    "count": len(rows),
                    "digest": canonical_digest(sorted(canonical_digest(row) for row in rows)),
                }
        return result
    finally:
        database.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pg-bin", type=Path, required=True)
    parser.add_argument("--url", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    parsed = make_url(args.url)
    if (
        parsed.host not in {"127.0.0.1", "localhost"}
        or not parsed.database
        or not parsed.database.startswith("product_ops_test")
    ):
        raise SystemExit("Only explicitly disposable loopback test databases are allowed.")
    before = snapshot(args.url)
    if not any(value["count"] for value in before.values()):
        raise SystemExit("Run service tests first; an empty database is not restore evidence.")
    args.output.mkdir(parents=True, exist_ok=True)
    identity = uuid4().hex
    destination = "product_ops_test_restore_" + identity
    dump = args.output.resolve() / (identity + ".dump")
    extension = ".exe" if os.name == "nt" else ""
    dump_binary = (args.pg_bin / ("pg_dump" + extension)).resolve(strict=True)
    restore_binary = (args.pg_bin / ("pg_restore" + extension)).resolve(strict=True)
    environment = {
        **os.environ,
        "PGHOST": parsed.host,
        "PGPORT": str(parsed.port or 5432),
        "PGUSER": parsed.username or "postgres",
        "PGPASSWORD": parsed.password or "",
    }
    with dump.open("xb") as stream:
        subprocess.run(
            [
                str(dump_binary),
                "--format=custom",
                "--no-owner",
                "--no-acl",
                "--dbname",
                parsed.database,
            ],
            env=environment,
            stdout=stream,
            stderr=subprocess.PIPE,
            check=True,
        )
    with psycopg.connect(
        host=parsed.host,
        port=parsed.port or 5432,
        user=parsed.username or "postgres",
        password=parsed.password or "",
        dbname="postgres",
        autocommit=True,
    ) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(destination)))
        try:
            subprocess.run(
                [
                    str(restore_binary),
                    "--exit-on-error",
                    "--no-owner",
                    "--no-acl",
                    "--dbname",
                    destination,
                    str(dump),
                ],
                env=environment,
                capture_output=True,
                check=True,
            )
            after = snapshot(parsed.set(database=destination).render_as_string(hide_password=False))
            if before != after:
                raise RuntimeError("logical restore fingerprint mismatch")
            with psycopg.connect(
                host=parsed.host,
                port=parsed.port or 5432,
                user=parsed.username or "postgres",
                password=parsed.password or "",
                dbname=destination,
            ) as restored:
                try:
                    restored.execute("UPDATE artifacts SET payload=payload")
                except psycopg.errors.RaiseException:
                    restored.rollback()
                else:
                    raise RuntimeError("restored immutable artifact trigger missing")
            report = {
                "schema_version": "1",
                "restored": True,
                "immutable_trigger_verified": True,
                "backup_sha256": hashlib.sha256(dump.read_bytes()).hexdigest(),
                "tables": before,
            }
            with (args.output / (identity + ".json")).open("x", encoding="utf-8") as stream:
                json.dump(report, stream, indent=2)
            print(
                json.dumps(
                    {
                        "restored": True,
                        "immutable_trigger_verified": True,
                        "logical_digest": canonical_digest(before),
                        "report": str(args.output / (identity + ".json")),
                    }
                )
            )
        finally:
            # Exact database created above; never a caller-selected or production database.
            admin.execute(
                sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(destination))
            )


if __name__ == "__main__":
    main()
