"""Explicit local pilot commands. Credentials never appear in command arguments or output."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import secrets
import subprocess
import sys
import time
import webbrowser
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import httpx
import uvicorn
from alembic.config import Config
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from temporalio.client import Client
from temporalio.worker import Worker

from agentic_product_ops.adapters.persistence.store import engine
from agentic_product_ops.adapters.repository.selection import RepositorySelection
from agentic_product_ops.cli import bounded_read
from agentic_product_ops.pilot.config import (
    PilotSettings,
    private_directory,
    read_secrets,
    read_settings,
    secret_from_env,
)
from agentic_product_ops.pilot.runtime import PilotRuntime, discover_linear
from agentic_product_ops.services.authority import ActorGrant
from agentic_product_ops.services.spending import spending_summary
from agentic_product_ops.workflows.activities import dispatch_outbox
from agentic_product_ops.workflows.governance import GovernanceWorkflow
from alembic import command as migrations


def selection(value: str) -> RepositorySelection:
    if value.startswith("github:"):
        repository, separator, commit = value[7:].rpartition("@")
        if not separator:
            raise ValueError("GitHub repository requires @40-character-commit")
        return RepositorySelection(kind="github", location=repository, commit=commit)
    return RepositorySelection(kind="local", location=value)


def initialize(args: argparse.Namespace) -> None:
    directory = args.directory.absolute()
    if (directory / "pilot.json").exists() or (directory / "pilot-secrets.json").exists():
        raise ValueError("pilot initialization never overwrites an existing identity")
    subject = private_directory(directory)
    scope = discover_linear(
        secret_from_env(args.linear_key_file, "LINEAR_API_KEY"), UUID(args.linear_team)
    )
    settings = PilotSettings(
        subject=subject,
        database_url=args.database_url,
        operator=args.operator,
        linear_scope=scope,
        linear_key_file=str(args.linear_key_file.resolve()),
        anthropic_key_file=str(args.anthropic_key_file.resolve()),
        spend_authorization=args.spend_authorization,
        maximum_spend=args.maximum_spend,
        allow_paid_execution=args.allow_paid_execution,
        repository_search_roots=tuple(str(p.resolve()) for p in args.repository_root),
    )
    # Fail connection/migration checks before creating an identity that cannot be overwritten.
    database = engine(settings.database_url)
    try:
        migration = Config(str(args.migrations.resolve()))
        with database.begin() as conn:
            migration.attributes["connection"] = conn
            migrations.upgrade(migration, "head")
    finally:
        database.dispose()
    secret_record = {
        "operator_token": secrets.token_urlsafe(48),
        "storage_key": secrets.token_bytes(32).hex(),
        "signing_key": Ed25519PrivateKey.generate().private_bytes_raw().hex(),
    }
    for name, data in [
        ("pilot-secrets.json", secret_record),
        ("pilot.json", settings.model_dump(mode="json")),
    ]:
        with (directory / name).open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(data, indent=2) + "\n")
    runtime = PilotRuntime(directory)
    try:
        now = datetime.now(UTC)
        runtime.authority.register(
            ActorGrant(
                workspace_id=settings.workspace,
                actor_id=settings.operator,
                issuer=runtime.authority.issuer,
                subject=subject,
                revision=1,
                roles=("product_approver", "security_approver", "intake_reader"),
                team_ids=runtime.policy.teams,
                repository_ids=(),
                allow_any_repository=True,
                issued_at=now,
                expires_at=now + timedelta(days=30),
                enabled=True,
            ),
            administrator=settings.operator,
        )
        print(
            json.dumps(
                {
                    "initialized": True,
                    "model": settings.model,
                    "operator": settings.operator,
                    "linear_scope": scope.model_dump(mode="json"),
                    "maximum_smoke_spend": settings.maximum_spend,
                    "publication_enabled": False,
                }
            )
        )
    finally:
        runtime.store.database.dispose()


def open_console(directory: Path) -> None:
    settings = read_settings(directory)
    if not settings.local_console_enabled:
        raise ValueError("local console is disabled for this profile")
    origin = f"http://127.0.0.1:{settings.api_port}"
    with httpx.Client(trust_env=False, follow_redirects=False, timeout=10) as client:
        try:
            client.get(origin + "/health")
        except httpx.ConnectError:
            # Launch only the installed control-plane package, never target-repository code.
            with (directory / "console-service.log").open("ab") as log:
                process = subprocess.Popen(  # noqa: S603
                    [
                        sys.executable,
                        "-m",
                        "agentic_product_ops.pilot.cli",
                        "--directory",
                        str(directory.resolve()),
                        "serve",
                    ],
                    stdout=log,
                    stderr=log,
                    stdin=subprocess.DEVNULL,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                    start_new_session=os.name != "nt",
                )
            (directory / "console-service.pid").write_text(str(process.pid), encoding="ascii")
            for _ in range(30):
                time.sleep(0.2)
                try:
                    if client.get(origin + "/health").status_code == 200:
                        break
                except httpx.ConnectError:
                    continue
        response = client.post(
            origin + "/v1/local/launch",
            headers={"Authorization": "Bearer " + read_secrets(directory)["operator_token"]},
        )
    if response.status_code != 200:
        raise ValueError("local console unavailable; start this profile's service first")
    url = response.json().get("url", "")
    if not isinstance(url, str) or not url.startswith(origin + "/#launch="):
        raise ValueError("unexpected local launch destination")
    if not webbrowser.open(url):
        raise ValueError("browser could not open; the single-use launch code was not printed")
    print(json.dumps({"console": origin, "session_seconds": 3600}))


async def worker(runtime: PilotRuntime) -> None:
    client = await Client.connect(runtime.settings.temporal_address)
    activities = runtime.activities()
    queue = "product-ops-pilot"
    async with Worker(
        client,
        task_queue=queue,
        workflows=[GovernanceWorkflow],
        activities=[activities.prepare_governance, activities.validate_governance_receipt],
    ):
        print(
            json.dumps(
                {
                    "worker": "ready",
                    "queue": queue,
                    "paid_execution_authorized": runtime.settings.allow_paid_execution,
                }
            ),
            flush=True,
        )
        while True:
            await dispatch_outbox(runtime.store, client, queue)
            heartbeat = runtime.directory / "worker-heartbeat.json"
            temporary = runtime.directory / "worker-heartbeat.tmp"
            temporary.write_text(
                json.dumps({"at": datetime.now(UTC).isoformat()}), encoding="utf-8"
            )
            temporary.replace(heartbeat)
            await asyncio.sleep(1)


async def run(runtime: PilotRuntime) -> None:
    """Own API and worker lifetimes together; propagate failures and clean up siblings."""
    server = uvicorn.Server(
        uvicorn.Config(
            runtime.app(),
            host="127.0.0.1",
            port=runtime.settings.api_port,
            access_log=False,
            proxy_headers=False,
        )
    )
    tasks = [asyncio.create_task(server.serve())]
    if runtime.settings.documentation_capability is None:
        tasks.append(asyncio.create_task(worker(runtime)))
    if runtime.settings.delivery_specification_ids:
        tasks.append(asyncio.create_task(delivery_loop(runtime)))
    if getattr(runtime.settings, "linear_monitor_enabled", False):
        from agentic_product_ops.pilot.monitor import LinearMonitor

        tasks.append(asyncio.create_task(LinearMonitor(runtime).run()))
    try:
        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            task.result()
    finally:
        server.should_exit = True
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


async def delivery_loop(runtime: PilotRuntime) -> None:
    """A durable producer receipt plus consumer idempotency tolerates lost responses."""
    while True:
        states = {}
        for identifier in runtime.settings.delivery_specification_ids:
            try:
                receipt = await asyncio.to_thread(runtime.advance_delivery, identifier)
                states[identifier] = {"state": "ADMITTED", "workflow_id": receipt["workflow_id"]}
            except (ValueError, KeyError, httpx.HTTPError) as exc:
                # Keep credentials and provider bodies out of operational diagnostics.
                states[identifier] = {"state": "HELD", "reason": type(exc).__name__}
        health = runtime.directory / "delivery-health.json"
        temporary = health.with_suffix(".tmp")
        temporary.write_text(json.dumps({"at": datetime.now(UTC).isoformat(), "work": states}))
        temporary.replace(health)
        await asyncio.sleep(10)


def remote(args: argparse.Namespace) -> dict[str, Any]:
    settings = read_settings(args.directory)
    token = read_secrets(args.directory)["operator_token"]
    body: dict[str, Any] = {}
    method = "POST"
    if args.command == "run-issue":
        path = "/v1/intakes/linear"
        body = {"issue": args.issue, "repository": args.repo}
    elif args.command == "prompt":
        path = "/v1/intakes/prompts"
        body = {
            "source": args.text
            if args.text is not None
            else bounded_read(args.input, 16000).decode("utf-8"),
            "repository": args.repo,
        }
    elif args.command == "intake":
        source = bounded_read(args.input, 16000).decode("utf-8")
        declared = [
            line[len("Repository:") :].strip()
            for line in source.splitlines()
            if line.startswith("Repository:")
        ]
        if len(declared) > 1 or (args.repository and declared and args.repository != declared[0]):
            raise ValueError("conflicting repository declarations")
        value = args.repository or (declared[0] if declared else None)
        body = {"source": source}
        if value:
            body["repository"] = selection(value).model_dump(mode="json")
        path = "/v1/intakes"
    else:
        path = f"/v1/specifications/{args.id}"
        if args.command in {"show", "review", "plan"}:
            method = "GET"
            if args.command != "show":
                path += "/" + args.command
        else:
            path += "/" + ("clarifications" if args.command == "answer" else args.command)
            if args.command != "publish":
                body = {"revision": args.revision, "content_digest": args.digest}
            if args.command in {"approve", "reject"}:
                body["plan_digest"] = args.plan_digest
            if args.command == "answer":
                body.update(question_id=args.question, answer=args.answer)
            if args.command == "risk":
                body.update(tier=args.tier, reason=args.reason)
    with httpx.Client(
        base_url=f"http://127.0.0.1:{settings.api_port}",
        trust_env=False,
        follow_redirects=False,
        timeout=120,
        headers={"Authorization": "Bearer " + token},
    ) as client:
        response = client.request(
            method,
            path,
            json=body if method == "POST" else None,
            headers={"Idempotency-Key": getattr(args, "command_id", None) or str(uuid4())},
        )
        if not response.is_success:
            raise ValueError(f"pilot command held with status {response.status_code}")
        result: dict[str, Any] = response.json()
        return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=Path(".local/pilot"))
    commands = parser.add_subparsers(dest="command", required=True)
    init = commands.add_parser(
        "init", help="Create private identity, discover Linear scope and migrate explicit database"
    )
    init.add_argument("--database-url", required=True)
    init.add_argument("--operator", default="alex-hines")
    init.add_argument("--linear-key-file", type=Path, required=True)
    init.add_argument("--linear-team", required=True)
    init.add_argument("--anthropic-key-file", type=Path, required=True)
    init.add_argument("--spend-authorization", required=True)
    init.add_argument("--maximum-spend", required=True)
    init.add_argument("--allow-paid-execution", action="store_true")
    init.add_argument("--migrations", type=Path, default=Path("alembic.ini"))
    init.add_argument("--repository-root", type=Path, action="append", default=[])
    for name in ("serve", "worker", "status", "run", "open"):
        commands.add_parser(name)
    issue = commands.add_parser("run-issue", help="Intake one Linear issue and repository name")
    issue.add_argument("--issue", required=True)
    issue.add_argument("--repo", help="Optional when the issue has a Repository: name line")
    prompt = commands.add_parser(
        "prompt", help="Submit a prompt and repository name; no source ticket required"
    )
    prompt.add_argument("--repo", required=True)
    prompt.add_argument("--command-id")
    source = prompt.add_mutually_exclusive_group(required=True)
    source.add_argument("--text")
    source.add_argument("--input", type=Path)
    intake = commands.add_parser("intake")
    intake.add_argument("--input", type=Path, required=True)
    intake.add_argument("--repository")
    intake.add_argument("--command-id")
    for name in (
        "show",
        "review",
        "plan",
        "approve",
        "reject",
        "answer",
        "cancel",
        "publish",
        "handoff",
        "risk",
        "analyze",
        "evidence",
    ):
        cmd = commands.add_parser(name)
        cmd.add_argument("--id", type=UUID, required=True)
        if name in {"approve", "reject", "answer", "cancel", "risk", "analyze"}:
            cmd.add_argument("--revision", type=int, required=True)
            cmd.add_argument("--digest", required=True)
        if name in {"approve", "reject"}:
            cmd.add_argument("--plan-digest", required=True)
        if name == "answer":
            cmd.add_argument("--question", required=True)
            cmd.add_argument("--answer", required=True)
        if name == "handoff":
            cmd.add_argument("--output", type=Path, required=True)
        if name == "risk":
            cmd.add_argument("--tier", type=int, choices=range(4), required=True)
            cmd.add_argument("--reason", required=True)
        cmd.add_argument("--command-id")
    args = parser.parse_args()
    try:
        if args.command == "init":
            initialize(args)
        elif args.command == "open":
            open_console(args.directory)
        elif args.command in {"serve", "worker", "status", "handoff", "analyze", "evidence", "run"}:
            runtime = PilotRuntime(args.directory)
            try:
                if args.command == "run":
                    asyncio.run(run(runtime))
                elif args.command == "serve":
                    uvicorn.run(
                        runtime.app(),
                        host="127.0.0.1",
                        port=runtime.settings.api_port,
                        access_log=False,
                        proxy_headers=False,
                    )
                elif args.command == "worker":
                    asyncio.run(worker(runtime))
                elif args.command == "analyze":
                    print(
                        json.dumps(
                            runtime.analyze(
                                str(args.id),
                                args.revision,
                                args.digest,
                                args.command_id or str(uuid4()),
                            ),
                            indent=2,
                        )
                    )
                elif args.command == "evidence":
                    print(json.dumps(runtime.evidence(str(args.id)), indent=2))
                elif args.command == "handoff":
                    value = runtime.handoff(str(args.id))
                    with args.output.open("x", encoding="utf-8", newline="\n") as stream:
                        stream.write(json.dumps(value, indent=2) + "\n")
                    print(json.dumps({"exported": True}))
                else:
                    print(
                        json.dumps(
                            {
                                "model": runtime.settings.model,
                                "operator": runtime.settings.operator,
                                "paid_execution_authorized": runtime.settings.allow_paid_execution,
                                "publication_enabled": runtime.settings.allow_publication,
                                "spend_authorization": runtime.settings.spend_authorization,
                                "maximum_spend": runtime.settings.maximum_spend,
                                "spending": spending_summary(
                                    runtime.store,
                                    runtime.settings.workspace,
                                    runtime.settings.spend_authorization,
                                ),
                                "identity_active": runtime.authority.resolve_subject(
                                    runtime.settings.subject
                                )
                                is not None,
                            }
                        )
                    )
            finally:
                runtime.store.database.dispose()
        else:
            print(json.dumps(remote(args), indent=2))
    except Exception:
        # CLI boundary must not echo credentials/DSNs or provider exception bodies.
        print(
            json.dumps({"error": "pilot operation held; check scope, services and saved evidence"})
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
