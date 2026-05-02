"""Reset HANDLER_REGISTRY around every handler test to insulate from
import-time auto-registration side effects."""

import pytest


@pytest.fixture(autouse=True)
def _reset_handler_registry():
    from workers.tasks.dispatch import clear_handler_registry
    clear_handler_registry()
    yield
    clear_handler_registry()
