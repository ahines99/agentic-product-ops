"""Shared Linear outcome type."""


class UnknownOutcome(ValueError):
    """The caller must reconcile; never blindly repeat a mutation."""
