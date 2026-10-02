"""Read allowlisted local snapshots without executing code or sending raw file bytes to models."""

from __future__ import annotations

import ast
import hashlib
import os
import re
import stat
import time
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from agentic_product_ops.domain.contracts import (
    ID,
    Contract,
    Digest,
    Evidence,
    RepositoryContext,
    Text,
    canonical_digest,
)

EXCLUDED = frozenset(
    {".git", ".venv", "node_modules", "vendor", "dist", "build", "out", "htmlcov", "__pycache__"}
)
SECRET = re.compile(
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----|(?:AKIA|ASIA)[A-Z0-9]{16}|"
    r"(?:gh[pousr]_|github_pat_|sk_live_|lin_api_)[A-Za-z0-9_]+|"
    r"(?i:password|secret|token|api[_-]?key)\s*[:=]\s*['\"][^'\"]{8,}['\"]"
)


class SnapshotLimits(Contract):
    max_files: Annotated[int, Field(gt=0, le=5000)] = 1000
    max_entries: Annotated[int, Field(gt=0, le=20000)] = 10000
    max_file_bytes: Annotated[int, Field(gt=0, le=1_000_000)] = 100_000
    max_total_bytes: Annotated[int, Field(gt=0, le=20_000_000)] = 8_000_000
    max_depth: Annotated[int, Field(gt=0, le=30)] = 12
    max_seconds: Annotated[int, Field(gt=0, le=60)] = 10


class SnapshotFile(Contract):
    path: Text
    digest: Digest
    size: Annotated[int, Field(ge=0)]
    imports: tuple[Text, ...]
    symbols: tuple[Text, ...]
    tests: tuple[Text, ...]
    routes: tuple[Text, ...]
    parse_error: bool


class Snapshot(Contract):
    schema_version: Literal["1"] = "1"
    repository_id: ID
    files: tuple[SnapshotFile, ...]
    unknown_edges: tuple[Text, ...]
    digest: Digest

    @model_validator(mode="after")
    def integrity(self) -> Self:
        if self.digest != canonical_digest(self.model_dump(mode="json", exclude={"digest"})):
            raise ValueError("snapshot digest mismatch")
        if len({f.path for f in self.files}) != len(self.files):
            raise ValueError("duplicate snapshot path")
        return self

    def context(self) -> RepositoryContext:
        evidence = tuple(
            Evidence(
                id=f"E{index}",
                path=file.path,
                blob_digest=file.digest,
                excerpt=(
                    f"Static metadata only; symbols: {', '.join(file.symbols[:20]) or 'none'}; "
                    f"imports: {', '.join(file.imports[:20]) or 'none'}"
                ),
            )
            for index, file in enumerate(self.files[:50], 1)
        )
        return RepositoryContext(
            repository_id=self.repository_id,
            snapshot_id=f"sha256:{self.digest}",
            snapshot_digest=self.digest,
            evidence=evidence,
            relevant_tests=tuple(f.path for f in self.files if f.tests),
            unknown_edges=self.unknown_edges
            + (
                "Metadata does not prove behavior; dynamic routes/imports may be absent.",
                "Document/configuration bodies deliberately excluded from model context.",
            ),
            confidence=Decimal("0.5"),
        )


def safe_file(path: Path, root: Path, limit: int) -> bytes:
    # Snapshot identity detects normal changes, but this is not an OS-level hostile FS sandbox.
    if path.is_symlink() or not path.resolve().is_relative_to(root):
        raise ValueError("repository link or path escape")
    if any(part.is_symlink() for part in path.parents if part != root and root in part.parents):
        raise ValueError("repository parent link")
    before = path.stat(follow_symlinks=False)
    if not stat.S_ISREG(before.st_mode) or before.st_size > limit:
        raise ValueError("nonregular or oversized file")
    with path.open("rb") as handle:
        opened = os.fstat(handle.fileno())
        if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
            raise ValueError("file changed during open")
        raw = handle.read(limit + 1)
        after = os.fstat(handle.fileno())
    if len(raw) > limit or (opened.st_size, opened.st_mtime_ns) != (
        after.st_size,
        after.st_mtime_ns,
    ):
        raise ValueError("file changed during read")
    return raw


def describe(path: str, raw: bytes) -> SnapshotFile:
    imports: set[str] = set()
    symbols: set[str] = set()
    tests: set[str] = set()
    routes: set[str] = set()
    parse_error = False
    if path.endswith(".py"):
        try:
            tree = ast.parse(raw.decode("utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imports.update(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imports.add(node.module)
                elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    symbols.add(node.name)
                    if node.name.startswith("test_"):
                        tests.add(node.name)
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        for decorator in node.decorator_list:
                            if isinstance(decorator, ast.Call) and isinstance(
                                decorator.func, ast.Attribute
                            ):
                                if decorator.func.attr in {"get", "post", "put", "patch", "delete"}:
                                    # Names only; literal paths may contain sensitive material.
                                    routes.add(f"{decorator.func.attr}:{node.name}")
        except (SyntaxError, UnicodeError, RecursionError, ValueError):
            parse_error = True
    return SnapshotFile(
        path=path,
        digest=hashlib.sha256(raw).hexdigest(),
        size=len(raw),
        imports=tuple(sorted(imports)),
        symbols=tuple(sorted(symbols)),
        tests=tuple(sorted(tests)),
        routes=tuple(sorted(routes)),
        parse_error=parse_error,
    )


def inspect_repository(
    repository_id: str,
    roots: dict[str, Path],
    *,
    limits: SnapshotLimits | None = None,
    expected_digest: str | None = None,
) -> Snapshot:
    if repository_id not in roots:
        raise ValueError("repository outside configured allowlist")
    configured = roots[repository_id]
    if configured.is_symlink() or configured.is_junction():
        raise ValueError("repository root cannot be a link")
    root = configured.resolve(strict=True)
    limits = limits or SnapshotLimits()
    started, visited, total = time.monotonic(), 0, 0
    files: list[SnapshotFile] = []
    unknowns = ["Read-only bounded working-tree snapshot; not a claim of a clean Git commit."]
    queue = [root]
    while queue:
        directory = queue.pop(0)
        if time.monotonic() - started > limits.max_seconds:
            raise ValueError("repository inspection time budget exceeded")
        entries: list[Path] = []
        with os.scandir(directory) as iterator:
            for entry in iterator:
                visited += 1
                if visited > limits.max_entries:
                    raise ValueError("repository entry budget exceeded")
                entries.append(Path(entry.path))
        for path in sorted(entries):
            relative = path.relative_to(root).as_posix()
            if path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction()):
                unknowns.append("A link/junction was excluded.")
                continue
            if path.name.startswith(".") or path.name in EXCLUDED:
                continue
            if path.is_dir():
                if len(path.relative_to(root).parts) < limits.max_depth:
                    queue.append(path)
                else:
                    unknowns.append("Depth limit excluded subdirectories.")
                continue
            if not re.fullmatch(r"[A-Za-z0-9_./ -]+", relative):
                continue
            if not (
                path.suffix == ".py"
                or path.name in {"README.md", "CODEOWNERS", "pyproject.toml"}
                or (path.suffix == ".md" and relative.startswith("docs/"))
            ):
                continue
            if len(files) >= limits.max_files:
                raise ValueError("repository file budget exceeded")
            try:
                raw = safe_file(path, root, limits.max_file_bytes)
            except (OSError, ValueError):
                unknowns.append(
                    "An unreadable, changed, nonregular or oversized file was excluded."
                )
                continue
            total += len(raw)
            if total > limits.max_total_bytes:
                raise ValueError("repository byte budget exceeded")
            if SECRET.search(raw.decode("utf-8", errors="replace")):
                unknowns.append("Potential sensitive content excluded from snapshot metadata.")
                continue
            file = describe(relative, raw)
            if file.parse_error:
                unknowns.append("Some Python could not be statically parsed.")
            files.append(file)
    body = {
        "schema_version": "1",
        "repository_id": repository_id,
        "files": tuple(sorted(files, key=lambda f: f.path)),
        "unknown_edges": tuple(sorted(set(unknowns))),
    }
    import json

    serialized = {
        **body,
        "files": [f.model_dump(mode="json") for f in sorted(files, key=lambda f: f.path)],
    }
    snapshot = Snapshot.model_validate_json(
        json.dumps({**serialized, "digest": canonical_digest(serialized)})
    )
    if expected_digest is not None and snapshot.digest != expected_digest:
        raise ValueError("pinned snapshot changed")
    return snapshot


def search(
    snapshot: Snapshot, terms: tuple[str, ...], max_results: int = 20
) -> tuple[SnapshotFile, ...]:
    if not 0 < max_results <= 100 or len(terms) > 20 or any(len(term) > 100 for term in terms):
        raise ValueError("search bounds exceeded")
    return tuple(
        file
        for file in snapshot.files
        if any(
            term.casefold() in " ".join((file.path, *file.symbols, *file.imports)).casefold()
            for term in terms
        )
    )[:max_results]
