"""Structural execution briefs; never a semantic-quality or execution authorization claim."""

from agentic_product_ops.domain.contracts import WorkSpecification

EXECUTION_POLICY = "pilot-execution-v1"
PLACEHOLDERS = {"todo", "tbd", "done", "works", "it works", "as expected", "tests pass"}
SUPPORTED_VERIFICATION = {"automated_test", "documentation", "manual_behavior"}


def ticket_findings(spec: WorkSpecification) -> tuple[str, ...]:
    findings = []
    if not spec.work_items:
        findings.append("No proposed work items yet.")
    if spec.repository_context is None:
        findings.append("A current repository snapshot is required.")
    for work in spec.work_items:
        if work.repository_id is None:
            findings.append(f"{work.local_id}: repository binding is missing.")
        covered = {r for c in work.acceptance_criteria for r in c.requirement_ids}
        if covered != set(work.requirement_ids):
            findings.append(f"{work.local_id}: every assigned requirement needs its own coverage.")
        for criterion in work.acceptance_criteria:
            for text in (criterion.text, criterion.evidence_required):
                if text.strip(" .!\n").casefold() in PLACEHOLDERS:
                    findings.append(f"{criterion.id}: replace placeholder outcome/evidence.")
    return tuple(dict.fromkeys(findings))


def delivery_findings(spec: WorkSpecification) -> tuple[str, ...]:
    findings = list(ticket_findings(spec))
    if len(spec.work_items) != 1 or spec.dependencies:
        findings.append(
            "The installed Delivery adapter accepts one independent ticket per handoff."
        )
    if spec.risk.tier not in (0, 1):
        findings.append("Current risk policy holds automatic Delivery handoff at this tier.")
    if any(
        criterion.verification_kind not in SUPPORTED_VERIFICATION
        for work in spec.work_items
        for criterion in work.acceptance_criteria
    ):
        findings.append("A verification kind is not supported by the installed Delivery adapter.")
    return tuple(dict.fromkeys(findings))
