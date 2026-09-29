from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select

from agentic_product_ops.adapters.model.contracts import ModelRequest, ModelResponse, ProviderUsage
from agentic_product_ops.adapters.model.runner import RunStopped
from agentic_product_ops.adapters.persistence.store import Store, artifacts, engine, metadata
from agentic_product_ops.services.spending import SpendingProvider, spending_summary


class Provider:
    def __init__(self, fail=False):
        self.calls = []
        self.fail = fail

    def complete(self, request):
        self.calls.append(request)
        if self.fail:
            raise RunStopped("uncertain call")
        return ModelResponse(
            output_json="{}",
            usage=ProviderUsage(input_tokens=1, output_tokens=1, provider_request_id="mock-id"),
        )


def request():
    return ModelRequest(
        run_id=uuid4(),
        context_id=uuid4(),
        role="requirements_analyst",
        model="test-model",
        system_policy="policy",
        authorized_configuration="scope",
        untrusted_payload="source",
        input_digest="a" * 64,
        output_schema="{}",
        max_input_tokens=100,
        max_output_tokens=100,
    )


@pytest.fixture
def ledger(tmp_path):
    database = engine(f"sqlite:///{tmp_path / 'spending.db'}", testing=True)
    metadata.create_all(database)
    yield Store(database)
    database.dispose()


def wrapper(ledger, provider, maximum="0.004", rate="10"):
    return SpendingProvider(
        ledger,
        "workspace",
        "authorization-1",
        provider,
        model="test-model",
        maximum=Decimal(maximum),
        input_rate=Decimal(rate),
        output_rate=Decimal(rate),
    )


def test_restart_failure_and_duplicate_do_not_release_reservation(ledger):
    failed = Provider(fail=True)
    first = request()
    with pytest.raises(RunStopped):
        wrapper(ledger, failed).complete(first)
    after_restart = Provider()
    with pytest.raises(RunStopped, match="cannot be repeated"):
        wrapper(ledger, after_restart).complete(first)
    wrapper(ledger, after_restart).complete(request())
    with pytest.raises(RunStopped, match="limit reached"):
        wrapper(ledger, after_restart).complete(request())
    assert len(after_restart.calls) == 1
    summary = spending_summary(ledger, "workspace", "authorization-1")
    assert summary["reserved_calls"] == 2 and summary["observed_calls"] == 1
    assert Decimal(summary["reserved_usd"]) == Decimal("0.004")
    with ledger.database.connect() as conn:
        assert (
            len(
                conn.execute(select(artifacts).where(artifacts.c.kind == "spend_reservation")).all()
            )
            == 2
        )


def test_concurrent_reservations_cannot_overspend(ledger):
    provider = Provider()

    def invoke(_):
        try:
            wrapper(ledger, provider).complete(request())
            return True
        except RunStopped:
            return False

    with ThreadPoolExecutor(max_workers=8) as pool:
        assert sum(pool.map(invoke, range(8))) == 2
    assert len(provider.calls) == 2


def test_terms_and_model_are_immutable(ledger):
    provider = Provider()
    wrapper(ledger, provider).complete(request())
    for maximum, rate in [("10", "10"), ("0.004", "1")]:
        with pytest.raises(RunStopped, match="terms changed"):
            wrapper(ledger, provider, maximum, rate).complete(request())
    with pytest.raises(RunStopped, match="model mismatch"):
        wrapper(ledger, provider).complete(request().model_copy(update={"model": "other"}))
    assert len(provider.calls) == 1
