"""Shared offline fixtures. Every test runs with no network, no GPU, no keys."""

import pytest

from ensemble.providers.model import MockProvider


@pytest.fixture
def mock_provider() -> MockProvider:
    return MockProvider()
