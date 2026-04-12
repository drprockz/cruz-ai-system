"""
Shared test fixtures for the CRUZ AI System test suite.
"""

import os
import pytest

# Set test environment before any app imports
os.environ.setdefault("DATABASE_URL", "postgresql://cruz:password@localhost:5432/cruz_db")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379")
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-ant-test-key")
os.environ.setdefault("ENVIRONMENT", "test")


@pytest.fixture
def sample_trace_id() -> str:
    return "test-trace-00000000-0000-0000-0000-000000000001"


@pytest.fixture
def sample_conversation_id() -> str:
    return "test-conv-00000000-0000-0000-0000-000000000001"
