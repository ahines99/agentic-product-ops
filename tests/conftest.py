from datetime import UTC, datetime

import pytest

from agentic_product_ops.services.drafting import load_fixture


@pytest.fixture
def valid():
    return load_fixture("feature")


@pytest.fixture
def low_risk():
    return load_fixture("handoff")


@pytest.fixture
def now():
    return datetime(2026, 9, 28, tzinfo=UTC)
