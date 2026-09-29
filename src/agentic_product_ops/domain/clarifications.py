"""Public answer receipts are evidence, never self-authenticating proposal fields."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field

from agentic_product_ops.domain.contracts import ID, Contract, Digest, Text, Timestamp


class ClarificationReceipt(Contract):
    schema_version: Literal["1"] = "1"
    id: ID
    workspace_id: ID
    specification_id: UUID
    base_revision: Annotated[int, Field(ge=1)]
    base_digest: Digest
    question_id: ID
    question_text: Text
    answer: Text
    actor_id: ID
    resolved_at: Timestamp
