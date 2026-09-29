from agentic_product_ops.domain.contracts import ID, Contract


class Principal(Contract):
    actor_id: ID
    workspace_id: ID
    roles: tuple[ID, ...]
