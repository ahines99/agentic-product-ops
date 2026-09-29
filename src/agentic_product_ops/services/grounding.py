"""Deterministic lexical metadata retrieval with explicit missing-evidence accounting."""

import re
from typing import Annotated, Literal

from pydantic import Field

from agentic_product_ops.adapters.repository.local import Snapshot
from agentic_product_ops.domain.contracts import ID, Contract, Digest, Text, WorkSpecification


class GroundingMatch(Contract):
    requirement_id: ID
    file_path: Text
    file_digest: Digest
    matching_terms: tuple[Text, ...]
    tests_in_file: tuple[Text, ...]


class GroundingReport(Contract):
    schema_version: Literal["1"] = "1"
    method: Literal["lexical_static_metadata_v1"] = "lexical_static_metadata_v1"
    specification_digest: Digest
    snapshot_digest: Digest
    requirement_count: Annotated[int, Field(ge=0)]
    matched_requirement_count: Annotated[int, Field(ge=0)]
    missing_requirement_ids: tuple[ID, ...]
    matches: tuple[GroundingMatch, ...]
    limitations: tuple[Text, ...]


def ground(specification: WorkSpecification, snapshot: Snapshot) -> GroundingReport:
    if specification.repository_context is None or (
        specification.repository_context.repository_id != snapshot.repository_id
        or specification.repository_context.snapshot_digest != snapshot.digest
    ):
        raise ValueError("grounding requires the exact attached repository snapshot")
    matches: list[GroundingMatch] = []
    missing: list[str] = []
    ignored = {
        "the",
        "and",
        "with",
        "from",
        "must",
        "should",
        "that",
        "this",
        "when",
        "for",
        "only",
    }
    for requirement in specification.requirements:
        terms = sorted(
            set(re.findall(r"[a-z][a-z0-9]{2,99}", requirement.text.casefold())) - ignored
        )[:20]
        ranked = []
        for file in snapshot.files:
            haystack = " ".join((file.path, *file.symbols, *file.imports)).casefold()
            found = tuple(term for term in terms if term in haystack)
            if found:
                ranked.append((file, found))
        ranked.sort(key=lambda pair: (-len(pair[1]), pair[0].path))
        if not ranked:
            missing.append(requirement.id)
        for file, found in ranked[:10]:
            matches.append(
                GroundingMatch(
                    requirement_id=requirement.id,
                    file_path=file.path,
                    file_digest=file.digest,
                    matching_terms=found,
                    tests_in_file=file.tests,
                )
            )
    return GroundingReport(
        specification_digest=specification.content_digest,
        snapshot_digest=snapshot.digest,
        requirement_count=len(specification.requirements),
        matched_requirement_count=len(specification.requirements) - len(missing),
        missing_requirement_ids=tuple(missing),
        matches=tuple(matches),
        limitations=(
            "Name overlap is retrieval evidence, not proof of behavior or semantic grounding.",
            "Tests are static names in matched files; no tests or repository code were executed.",
            "Excluded files, document bodies and dynamic imports may contain relevant evidence.",
        ),
    )
