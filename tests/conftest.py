from __future__ import annotations

import pytest
from runbook.data import DatabasePointerRegistry, create_pointer_schema
from sqlalchemy import create_engine


@pytest.fixture
def pointer_registry() -> DatabasePointerRegistry:
    engine = create_engine("sqlite://")
    create_pointer_schema(engine)
    return DatabasePointerRegistry(engine)
