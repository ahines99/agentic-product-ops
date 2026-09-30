"""Resolve a short name only within operator-configured local roots, without execution."""

import re
from pathlib import Path

from agentic_product_ops.adapters.repository.selection import RepositorySelection
from agentic_product_ops.policies.validation import PolicyError


class RepositoryNames:
    def __init__(self, roots: tuple[Path, ...]):
        self.roots = roots

    def __call__(self, name: str) -> RepositorySelection:
        if not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}", name) or name.endswith("."):
            raise PolicyError("repository name must be one directory component")
        matches = set()
        for root in self.roots:
            candidate = root / name
            if not root.is_absolute() or any(
                p.is_symlink() or p.is_junction() for p in (candidate, *candidate.parents)
            ):
                raise PolicyError("repository root cannot traverse links")
            if candidate.is_dir() and (candidate / ".git").exists():
                matches.add(candidate.resolve())
        if len(matches) != 1:
            raise PolicyError("repository name missing or ambiguous in configured roots")
        return RepositorySelection(kind="local", location=str(matches.pop()))
