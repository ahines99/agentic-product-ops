"""Ticket-owned repository selection under operator policy, with no shell or clone capability."""

import os
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import Field, SecretStr, model_validator

from agentic_product_ops.adapters.repository.github import GitHubReader
from agentic_product_ops.adapters.repository.local import Snapshot, inspect_repository
from agentic_product_ops.domain.contracts import Contract, canonical_digest


class RepositorySelection(Contract):
    kind: Literal["local", "github"]
    location: Annotated[str, Field(min_length=1, max_length=2048)]
    commit: Annotated[str, Field(pattern=r"^[a-f0-9]{40}$")] | None = None

    @model_validator(mode="after")
    def valid(self) -> Self:
        import re

        if self.kind == "github":
            if self.commit is None or not re.fullmatch(
                r"[A-Za-z0-9_-][A-Za-z0-9_.-]*/[A-Za-z0-9_-][A-Za-z0-9_.-]*", self.location
            ):
                raise ValueError("GitHub selection requires owner/repository and pinned commit SHA")
        elif self.commit is not None or not Path(self.location).is_absolute():
            raise ValueError(
                "local selection requires an absolute working-tree path, not a commit claim"
            )
        return self

    def repository_id(self) -> str:
        # Commit is the snapshot identity, not the repository identity.
        location = str(Path(self.location).resolve()) if self.kind == "local" else self.location
        if self.kind == "github" or os.name == "nt":
            location = location.casefold()
        return "repo-" + canonical_digest({"kind": self.kind, "location": location})[:32]


class RepositoryResolver:
    def __init__(self, *, github_token: SecretStr | None = None, allow_github: bool = False):
        self.github_token, self.allow_github = github_token, allow_github

    def __call__(self, selected: RepositorySelection) -> Snapshot:
        RepositorySelection.model_validate_json(selected.model_dump_json())
        identifier = selected.repository_id()
        if selected.kind == "local":
            root = Path(selected.location)
            if (
                root.is_symlink()
                or root.is_junction()
                or any(parent.is_symlink() or parent.is_junction() for parent in root.parents)
                or not root.is_dir()
                or not (root / ".git").exists()
                or (root / ".git").is_symlink()
            ):
                raise ValueError("local selection must be a non-symlink Git working tree")
            return inspect_repository(identifier, {identifier: root.resolve()})
        if not self.allow_github:
            raise ValueError("GitHub read transport is not enabled")
        reader = GitHubReader(
            {identifier: selected.location}, token=self.github_token, allow_network=True
        )
        try:
            if selected.commit is None:
                raise ValueError("pinned commit required")
            return reader.inspect(identifier, selected.commit)
        finally:
            reader.close()
