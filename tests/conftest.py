"""Shared test fixtures."""

import pytest

from _fakes import FakeClient


@pytest.fixture
def fake_client_factory():
    return FakeClient
