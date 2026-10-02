"""Preview a constrained proposal; only an explicit security approver may promote it."""

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from agentic_product_ops.adapters.identity.contracts import Principal
from agentic_product_ops.adapters.linear.native_plan import LinearScope, build_native_plan
from agentic_product_ops.adapters.model.contracts import (
    PipelineResult,
    Review,
    RuntimeConfiguration,
)
from agentic_product_ops.adapters.model.runner import ModelProvider
from agentic_product_ops.adapters.persistence.store import Conflict, Missing, Store
from agentic_product_ops.domain.contracts import (
    WorkSpecification,
    canonical_digest,
    seal_specification,
)
from agentic_product_ops.policies.validation import (
    DocumentationPolicy,
    PolicyError,
    ServerPolicy,
    proposal_ready,
)
from agentic_product_ops.services.authority import Authority
from agentic_product_ops.services.clarifications import load_clarifications
from agentic_product_ops.services.durable_analysis import (
    DurableRoleRunner,
    load_analysis,
    recorded_review,
)
from agentic_product_ops.services.plan_inputs import repository_label
from product_ops_handoff.documentation import DocumentationCapability, semantic_digest

LANE_PREFIX = "doc-add-v1-"
BASE_BRANCH = "main"
DOCUMENT_PATH = re.compile(r"(?<![\w/.-])docs/[a-z0-9][a-z0-9_-]{0,80}\.md(?![\w/-])")
FENCED_BLOCK = re.compile(r"^```[^\n`]*\n(.*?)^```[ \t]*$", re.MULTILINE | re.DOTALL)


def constrained_policy(
    base: ServerPolicy, capability: DocumentationCapability
) -> DocumentationPolicy:
    return DocumentationPolicy.model_validate_json(
        json.dumps(
            {
                **base.model_dump(mode="json"),
                "version": capability.policy_version,
                "documentation_capability": capability.model_dump(mode="json"),
            }
        )
    )


def specification_policy(
    store: Store, base: ServerPolicy, spec: WorkSpecification, current: ServerPolicy
) -> ServerPolicy:
    """The policy a revision was proposed under (ADR-029).

    A promoted documentation candidate names its lane policy, whose capability is stored under
    that version. Every other revision keeps the profile's current policy, as before.
    """
    version = spec.risk.policy_version
    if version == current.version or not version.startswith(LANE_PREFIX):
        return current
    capability = DocumentationCapability.model_validate_json(
        json.dumps(store.get(base.workspace_id, "documentation_capability", version))
    )
    if capability.policy_version != version:
        raise PolicyError("documentation capability digest mismatch")
    return constrained_policy(base, capability)


def requested_document(source: str) -> tuple[str, str]:
    """The one docs/ path and one fenced block a documentation request names, verbatim."""
    paths = set(DOCUMENT_PATH.findall(source))
    blocks = FENCED_BLOCK.findall(source)
    if len(paths) != 1 or len(blocks) != 1:
        raise PolicyError("a documentation change names one docs/ path and one fenced block")
    return paths.pop(), blocks[0]


def branch_head(root: Path, branch: str = BASE_BRANCH) -> str:
    """Read a local branch head from Git's files; no Git command or repository code runs."""
    git = root / ".git"
    if git.is_symlink() or not git.is_dir():
        raise PolicyError("documentation lane needs a plain local Git repository")
    reference, value = git / "refs" / "heads" / branch, None
    if reference.is_file() and not reference.is_symlink():
        value = reference.read_text(encoding="ascii").strip()
    elif (git / "packed-refs").is_file():
        for line in (git / "packed-refs").read_text(encoding="ascii").splitlines():
            sha, _, name = line.partition(" ")
            if name == f"refs/heads/{branch}":
                value = sha
    if value is None or re.fullmatch(r"[a-f0-9]{40}", value) is None:
        raise PolicyError("base branch head unavailable")
    return value


def lane_capability(
    store: Store, workspace: str, spec: WorkSpecification
) -> DocumentationCapability:
    """The capability for this exact revision: one the operator bound, else derived from it.

    Derived capabilities take the path and content verbatim from the request and the base
    from the selected repository's main branch, never from model output.
    """
    try:
        return DocumentationCapability.model_validate_json(
            json.dumps(
                store.get(
                    workspace, "documentation_lane", str(spec.specification_id), spec.revision
                )
            )
        )
    except Missing:
        pass
    context = spec.repository_context
    if context is None:
        raise PolicyError("documentation lane requires a selected repository")
    try:
        selection = store.get(workspace, "repository_selection", context.repository_id)
    except Missing:
        raise PolicyError("documentation lane requires a selected repository") from None
    if selection.get("kind") != "local":
        raise PolicyError("documentation lane requires a local repository")
    path, content = requested_document(spec.source_statements[0].text)
    capability = DocumentationCapability(
        semantic_digest=semantic_digest(spec.model_dump(mode="json")),
        repository_id=context.repository_id,
        base_sha=branch_head(Path(selection["location"])),
        path=path,
        content=content,
    )
    capability.validate_specification(spec.model_dump(mode="json"))
    return capability


def bind_lane(
    store: Store, workspace: str, spec: WorkSpecification, capability: DocumentationCapability
) -> None:
    """Record the capability for this revision and under its policy version (immutable)."""
    capability.validate_specification(spec.model_dump(mode="json"))
    with store.database.begin() as conn:
        store.put(
            conn,
            workspace,
            "documentation_lane",
            str(spec.specification_id),
            spec.revision,
            capability.model_dump(mode="json"),
        )
        store.put(
            conn,
            workspace,
            "documentation_capability",
            capability.policy_version,
            1,
            capability.model_dump(mode="json"),
        )


def candidate_for(base: WorkSpecification, policy: DocumentationPolicy) -> WorkSpecification:
    policy.documentation_capability.validate_specification(base.model_dump(mode="json"))
    body = base.model_dump(mode="json")
    body["revision"] += 1
    body["risk"].update(
        tier=1,
        policy_version=policy.version,
        reasons=[
            "Execution limited to the exact inert Markdown addition, pinned repository base, "
            "local review branch and mandatory human merge; "
            "no general agent or repository commands."
        ],
    )
    body["approval_policy"]["policy_version"] = policy.version
    for work in body["work_items"]:
        work["risk_tier"] = 1
    return seal_specification(body)


def preview(
    store: Store,
    base_policy: ServerPolicy,
    configuration: RuntimeConfiguration,
    provider: ModelProvider,
    scope: LinearScope,
    identifier: str,
    capability: DocumentationCapability,
) -> dict[str, Any]:
    """Paid review creates an immutable preview, never human approval or active revision."""
    workspace = base_policy.workspace_id
    base = WorkSpecification.model_validate_json(
        json.dumps(store.get(workspace, "specification", identifier))
    )
    previous = load_analysis(store, workspace, base, base_policy)
    recorded_review(store, workspace, base, base_policy)
    policy = constrained_policy(base_policy, capability)
    candidate = candidate_for(base, policy)
    answers = load_clarifications(store, base, base_policy)
    proposal_ready(candidate, policy, clarifications=answers)
    runner = DurableRoleRunner(
        store,
        workspace,
        candidate.content_digest,
        provider,
        configuration.budget,
        identifier,
        configuration.model,
    )
    review = runner.run(
        "specification_reviewer",
        json.dumps(
            {
                "candidate": candidate.model_dump(mode="json"),
                "execution_capability": capability.model_dump(mode="json"),
                "instruction": (
                    "Review exact source coverage and this constrained documentation plan. "
                    "The consumer enforces one inert addition at a pinned base "
                    "and cannot execute general code. "
                    "No human has approved this preview. "
                    "Flag any requirement the capability cannot satisfy."
                ),
            }
        ),
        policy,
        Review,
    )
    if review.specification_digest != candidate.content_digest or any(
        f.blocking for f in review.findings
    ):
        raise PolicyError("documentation preview requires revision")
    result = PipelineResult.model_validate_json(
        json.dumps(
            {
                "state": "PROPOSED",
                "reason": "reviewed_documentation_preview",
                "analysis": previous.analysis.model_dump(mode="json")
                if previous.analysis
                else None,
                "specification": candidate.model_dump(mode="json"),
                "review": review.model_dump(mode="json"),
                "receipts": [r.model_dump(mode="json") for r in runner.receipts],
            }
        )
    )
    document = {
        "base_digest": base.content_digest,
        "candidate_digest": candidate.content_digest,
        "base_policy": base_policy.model_dump(mode="json"),
        "policy": policy.model_dump(mode="json"),
        "result": result.model_dump(mode="json"),
        "configuration": configuration.model_dump(mode="json"),
        "plan": build_native_plan(
            candidate,
            policy,
            scope,
            clarifications=answers,
            repository_label=repository_label(store, workspace, candidate),
        ).model_dump(mode="json"),
    }
    with store.database.begin() as conn:
        if store.lock_specification(conn, workspace, identifier):
            raise PolicyError("cancelled")
        if (
            store.get(workspace, "specification", identifier, connection=conn)["content_digest"]
            != base.content_digest
        ):
            raise Conflict("preview base superseded")
        store.put(conn, workspace, "documentation_preview", candidate.content_digest, 1, document)
    return document


def promote(
    store: Store,
    authority: Authority,
    base_policy: ServerPolicy,
    actor: Principal,
    candidate_digest: str,
    command_key: str,
) -> dict[str, Any]:
    """Caller must hold an explicit human security decision for this exact preview.

    This command promotes risk classification, not publication approval. The ordinary
    exact-specification/plan approval endpoint remains authoritative for publication.
    """
    if (
        actor.actor_id not in base_policy.security_approvers
        or "security_approver" not in actor.roles
    ):
        raise PolicyError("security approver required")
    workspace = base_policy.workspace_id
    preview_record = store.get(workspace, "documentation_preview", candidate_digest)
    if preview_record["base_policy"] != base_policy.model_dump(mode="json"):
        raise PolicyError("preview policy changed")
    policy = DocumentationPolicy.model_validate_json(json.dumps(preview_record["policy"]))
    result = PipelineResult.model_validate_json(json.dumps(preview_record["result"]))
    candidate = result.specification
    if candidate is None or candidate.content_digest != candidate_digest or result.review is None:
        raise PolicyError("reviewed candidate missing")
    if result.review.specification_digest != candidate_digest or any(
        f.blocking for f in result.review.findings
    ):
        raise PolicyError("review did not accept this exact candidate")
    identifier = str(candidate.specification_id)

    def apply(conn: Any) -> dict[str, Any]:
        if store.lock_specification(conn, workspace, identifier):
            raise PolicyError("cancelled")
        store.lock_specification(conn, workspace, "authority-dispatch")
        grant = authority.check(actor, conn)
        authority._scope(grant, candidate)
        base = WorkSpecification.model_validate_json(
            json.dumps(store.get(workspace, "specification", identifier, connection=conn))
        )
        if base.content_digest != preview_record["base_digest"] or candidate != candidate_for(
            base, policy
        ):
            raise Conflict("stale documentation preview")
        proposal_ready(
            candidate, policy, clarifications=load_clarifications(store, base, base_policy)
        )
        store.put(
            conn,
            workspace,
            "documentation_risk_decision",
            candidate_digest,
            1,
            {
                "actor_id": actor.actor_id,
                "grant_digest": actor.grant_digest,
                "candidate_digest": candidate_digest,
                "policy_version": policy.version,
                "at": datetime.now(UTC).isoformat(),
            },
        )
        store.put(conn, workspace, "specification", identifier, candidate.revision, candidate)
        binding = canonical_digest(
            {
                "specification": candidate_digest,
                "policy": policy.model_dump(mode="json"),
                "runner": "recorded-v1",
            }
        )
        store.put(conn, workspace, "analysis_result", binding, 1, result)
        store.put(conn, workspace, "analysis_runtime", binding, 1, preview_record["configuration"])
        store.put(
            conn,
            workspace,
            "analysis_index",
            identifier,
            candidate.revision,
            {"binding": binding, "content_digest": candidate_digest},
        )
        return {
            "specification_id": identifier,
            "revision": candidate.revision,
            "content_digest": candidate_digest,
            "policy_version": policy.version,
        }

    return store.command(
        workspace,
        actor.actor_id,
        command_key,
        {"action": "promote_documentation_preview", "digest": candidate_digest},
        apply,
    )
