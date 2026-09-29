"""Explicit, authenticated, pinned GitHub reads; source bytes never become instructions."""

import base64
import hashlib
import json
import re
import time
from typing import Any

import httpx
from pydantic import SecretStr

from agentic_product_ops.adapters.repository.local import (
    EXCLUDED,
    SECRET,
    Snapshot,
    SnapshotFile,
    SnapshotLimits,
    describe,
)
from agentic_product_ops.domain.contracts import canonical_digest


class GitHubReader:
    """Only read-only endpoints at a fixed origin; no ambient credentials or redirects."""

    def __init__(
        self,
        repositories: dict[str, str],
        transport: httpx.MockTransport | None = None,
        *,
        token: SecretStr | None = None,
        allow_network: bool = False,
    ):
        if transport is not None and not isinstance(transport, httpx.MockTransport):
            raise ValueError("only in-memory mocks may bypass network authorization")
        if transport is None and not allow_network:
            raise ValueError("explicit read authorization required")
        if token is not None and not token.get_secret_value():
            raise ValueError("empty GitHub credential")
        if any(
            not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", value)
            for value in repositories.values()
        ):
            raise ValueError("invalid configured GitHub repository")
        self.repositories = dict(repositories)
        self.client = httpx.Client(
            base_url="https://api.github.com",
            transport=transport,
            follow_redirects=False,
            timeout=5,
            trust_env=False,
            headers={
                "Accept": "application/vnd.github+json",
                "Accept-Encoding": "identity",
                "X-GitHub-Api-Version": "2026-03-10",
                **({"Authorization": "Bearer " + token.get_secret_value()} if token else {}),
            },
        )

    def close(self) -> None:
        self.client.close()

    def read_json(self, path: str, maximum: int, deadline: float) -> dict[str, Any]:
        if time.monotonic() >= deadline:
            raise ValueError("repository inspection time budget exceeded")
        with self.client.stream(
            "GET", path, timeout=min(5, deadline - time.monotonic())
        ) as response:
            if response.status_code != 200 or response.headers.get("content-encoding"):
                raise ValueError("repository provider read failed")
            raw = bytearray()
            for chunk in response.iter_bytes():
                raw.extend(chunk)
                if len(raw) > maximum or time.monotonic() >= deadline:
                    raise ValueError("repository provider response exceeds bound")
        result: dict[str, Any] = json.loads(raw)
        if not isinstance(result, dict):
            raise ValueError("malformed repository provider response")
        return result

    def inspect(
        self, repository_id: str, commit: str, limits: SnapshotLimits | None = None
    ) -> Snapshot:
        try:
            return self._inspect(repository_id, commit, limits)
        except (httpx.HTTPError, KeyError, TypeError, ValueError):
            raise ValueError(
                "repository read held: scope, identity, completeness or bounds"
            ) from None

    def _inspect(
        self, repository_id: str, commit: str, limits: SnapshotLimits | None = None
    ) -> Snapshot:
        if repository_id not in self.repositories or not re.fullmatch(r"[a-f0-9]{40}", commit):
            raise ValueError("allowlisted repository and immutable commit SHA required")
        limits = limits or SnapshotLimits()
        deadline = time.monotonic() + limits.max_seconds
        prefix = f"/repos/{self.repositories[repository_id]}/git"
        pinned = self.read_json(f"{prefix}/commits/{commit}", 100_000, deadline)
        tree_sha = pinned["tree"]["sha"]
        if pinned.get("sha") != commit or not re.fullmatch(r"[a-f0-9]{40}", tree_sha):
            raise ValueError("commit identity mismatch")
        tree = self.read_json(
            f"{prefix}/trees/{tree_sha}?recursive=1", limits.max_total_bytes, deadline
        )
        entries = tree.get("tree")
        if (
            tree.get("sha") != tree_sha
            or tree.get("truncated") is not False
            or not isinstance(entries, list)
        ):
            raise ValueError("incomplete repository tree")
        if len(entries) > limits.max_entries:
            raise ValueError("repository entry budget exceeded")
        if len({entry["path"] for entry in entries}) != len(entries):
            raise ValueError("duplicate tree paths")
        files: list[SnapshotFile] = []
        total = 0
        unknowns = [f"GitHub tree requested at immutable commit {commit}; static metadata only."]
        for entry in sorted(entries, key=lambda item: item["path"]):
            path = entry["path"]
            if time.monotonic() >= deadline:
                raise ValueError("repository inspection time budget exceeded")
            parts = path.split("/")
            if any(part in {"", ".", ".."} for part in parts):
                raise ValueError("unsafe repository path")
            if len(parts) > limits.max_depth:
                unknowns.append("Depth limit excluded entries.")
                continue
            if (
                entry.get("type") != "blob"
                or entry.get("mode") != "100644"
                or not re.fullmatch(r"[A-Za-z0-9_./ -]+", path)
                or any(part.startswith(".") for part in path.split("/"))
                or any(part.casefold() in EXCLUDED for part in parts)
                or not (
                    path.endswith(".py") or path in {"README.md", "CODEOWNERS", "pyproject.toml"}
                )
            ):
                continue
            if (
                type(entry.get("size")) is not int
                or not 0 <= entry["size"] <= limits.max_file_bytes
            ):
                raise ValueError("repository blob size exceeded")
            if len(files) >= limits.max_files:
                raise ValueError("repository file budget exceeded")
            sha = entry["sha"]
            if not re.fullmatch(r"[a-f0-9]{40}", sha):
                raise ValueError("invalid blob SHA")
            blob = self.read_json(
                f"{prefix}/blobs/{sha}", limits.max_file_bytes * 2 + 2000, deadline
            )
            if blob.get("encoding") != "base64":
                raise ValueError("unsupported blob encoding")
            raw = base64.b64decode(blob["content"].replace("\n", ""), validate=True)
            if blob.get("sha") != sha or blob.get("size") != len(raw) or entry["size"] != len(raw):
                raise ValueError("blob metadata identity mismatch")
            total += len(raw)
            if len(raw) > limits.max_file_bytes or total > limits.max_total_bytes:
                raise ValueError("repository byte budget exceeded")
            git_sha = hashlib.sha1(
                f"blob {len(raw)}\0".encode() + raw, usedforsecurity=False
            ).hexdigest()
            if git_sha != sha:
                raise ValueError("Git blob digest mismatch")
            if SECRET.search(raw.decode("utf-8", errors="replace")):
                unknowns.append("Potential sensitive blob excluded.")
                continue
            files.append(describe(path, raw))
        body = {
            "schema_version": "1",
            "repository_id": repository_id,
            "files": [f.model_dump(mode="json") for f in files],
            "unknown_edges": sorted(set(unknowns)),
        }
        return Snapshot.model_validate_json(json.dumps({**body, "digest": canonical_digest(body)}))


class MockGitHubReader(GitHubReader):
    """Compatibility constructor restricted to deterministic in-memory transport."""

    def __init__(self, repositories: dict[str, str], transport: httpx.MockTransport):
        if not isinstance(transport, httpx.MockTransport):
            raise ValueError("live transport disabled")
        super().__init__(repositories, transport)
