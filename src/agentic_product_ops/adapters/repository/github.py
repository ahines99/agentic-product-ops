"""Pinned GitHub tree/blob reader through an explicitly injected mock HTTP transport."""

import base64
import hashlib
import json
import re
from typing import Any

import httpx

from agentic_product_ops.adapters.repository.local import (
    SECRET,
    Snapshot,
    SnapshotFile,
    SnapshotLimits,
    describe,
)
from agentic_product_ops.domain.contracts import canonical_digest


class MockGitHubReader:
    """Read adapter exercised against recorded HTTP fixtures; no credentials or live transport."""

    def __init__(self, repositories: dict[str, str], transport: httpx.MockTransport):
        if not isinstance(transport, httpx.MockTransport):
            raise ValueError("live transport disabled")
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
        )

    def close(self) -> None:
        self.client.close()

    def read_json(self, path: str, maximum: int) -> dict[str, Any]:
        with self.client.stream("GET", path) as response:
            if response.status_code != 200:
                raise ValueError("repository provider read failed")
            raw = bytearray()
            for chunk in response.iter_bytes():
                raw.extend(chunk)
                if len(raw) > maximum:
                    raise ValueError("repository provider response exceeds bound")
        result: dict[str, Any] = json.loads(raw)
        if not isinstance(result, dict):
            raise ValueError("malformed repository provider response")
        return result

    def inspect(
        self, repository_id: str, commit: str, limits: SnapshotLimits | None = None
    ) -> Snapshot:
        if repository_id not in self.repositories or not re.fullmatch(r"[a-f0-9]{40}", commit):
            raise ValueError("allowlisted repository and immutable commit SHA required")
        limits = limits or SnapshotLimits()
        prefix = f"/repos/{self.repositories[repository_id]}/git"
        tree = self.read_json(f"{prefix}/trees/{commit}?recursive=1", limits.max_total_bytes)
        entries = tree.get("tree")
        if tree.get("truncated") is not False or not isinstance(entries, list):
            raise ValueError("incomplete repository tree")
        if len(entries) > limits.max_entries:
            raise ValueError("repository entry budget exceeded")
        files: list[SnapshotFile] = []
        total = 0
        unknowns = [f"GitHub tree requested at immutable commit {commit}; static metadata only."]
        for entry in sorted(entries, key=lambda item: item["path"]):
            path = entry["path"]
            if (
                entry.get("type") != "blob"
                or entry.get("mode") != "100644"
                or not re.fullmatch(r"[A-Za-z0-9_./ -]+", path)
                or any(part.startswith(".") for part in path.split("/"))
                or not (
                    path.endswith(".py") or path in {"README.md", "CODEOWNERS", "pyproject.toml"}
                )
            ):
                continue
            if entry.get("size", limits.max_file_bytes + 1) > limits.max_file_bytes:
                raise ValueError("repository blob size exceeded")
            if len(files) >= limits.max_files:
                raise ValueError("repository file budget exceeded")
            sha = entry["sha"]
            if not re.fullmatch(r"[a-f0-9]{40}", sha):
                raise ValueError("invalid blob SHA")
            blob = self.read_json(f"{prefix}/blobs/{sha}", limits.max_file_bytes * 2 + 2000)
            if blob.get("encoding") != "base64":
                raise ValueError("unsupported blob encoding")
            raw = base64.b64decode(blob["content"].replace("\n", ""), validate=True)
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
            "unknown_edges": unknowns,
        }
        return Snapshot.model_validate_json(json.dumps({**body, "digest": canonical_digest(body)}))
