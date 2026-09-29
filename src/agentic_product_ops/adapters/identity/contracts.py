from agentic_product_ops.domain.contracts import ID, Contract, Digest


class Principal(Contract):
    actor_id: ID
    workspace_id: ID
    roles: tuple[ID, ...]
    grant_digest: Digest | None = None
