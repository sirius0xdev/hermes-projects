"""Fixtures for cache layer tests.

Cache tests use fakeredis and don't need the DB models.
"""
from __future__ import annotations

import pytest
from fakeredis import FakeAsyncRedis, FakeServer

from data_service.app.cache.service import CacheService


@pytest.fixture
def server() -> FakeServer:
    return FakeServer()


@pytest.fixture
def fake_redis(server: FakeServer) -> FakeAsyncRedis:
    return FakeAsyncRedis(server=server)


@pytest.fixture
def cache(fake_redis: FakeAsyncRedis) -> CacheService:
    return CacheService(fake_redis)
