"""Fail closed on an edited or unavailable enrolled Linear source."""

import json
from collections.abc import Callable

from agentic_product_ops.adapters.linear.intake import LinearSource
from agentic_product_ops.adapters.persistence.store import Missing, Store
from agentic_product_ops.policies.validation import PolicyError


def validate_linear_source(
    store: Store, workspace: str, identifier: str, reader: Callable[[str], LinearSource]
) -> None:
    try:
        value = store.get(workspace, "linear_source", identifier)
    except Missing:
        return  # Prompt-origin specifications have no external source binding.
    enrolled = LinearSource.model_validate_json(json.dumps(value))
    try:
        current = reader(str(enrolled.issue_id))
    except Exception:
        raise PolicyError("Linear source could not be revalidated") from None
    if current.digest() != enrolled.digest():
        raise PolicyError("Linear source changed; a new reviewed specification is required")
