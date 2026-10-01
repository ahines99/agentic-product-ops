"""Trusted inputs for rebuilding an exact publication plan from durable records."""

from pathlib import PureWindowsPath

from agentic_product_ops.adapters.persistence.store import Missing, Store
from agentic_product_ops.domain.contracts import WorkSpecification


def repository_label(store: Store, workspace: str, spec: WorkSpecification) -> str | None:
    """The human name of the specification's repository, from the stored selection.

    Specifications carry only a hashed repository identity. The name written into tickets
    (``Repository: <name>``) comes from the operator's recorded selection, never from model text.
    """
    context = spec.repository_context
    if context is None:
        return None
    try:
        selection = store.get(workspace, "repository_selection", context.repository_id)
    except Missing:
        return None
    if selection.get("kind") == "local":
        return PureWindowsPath(str(selection["location"])).name or None
    location = selection.get("location")
    return str(location) if location else None
