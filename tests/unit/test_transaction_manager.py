import pytest

from app.services.transaction_manager import TransactionManager


class DummyCommand:
    def __init__(self, name: str):
        self.func_name = name
        self.undo = lambda db: None
        self.redo = lambda db: None


@pytest.fixture
def manager():
    tm = TransactionManager()
    return tm


def test_check_context_change_clears_stack(manager):
    manager.command_stack.stack = [DummyCommand("cmd1"), DummyCommand("cmd2")]
    manager.command_stack.current_index = 1
    manager.last_search_query = "alpha"

    manager.check_context_change("beta")

    assert manager.command_stack.stack == []
    assert manager.command_stack.current_index == -1
    assert manager.last_search_query == "beta"


def test_check_context_change_ignores_whitespace(manager):
    manager.command_stack.stack = []
    manager.last_search_query = "foo"

    manager.check_context_change("  foo  ")

    assert manager.command_stack.stack == []
    assert manager.last_search_query == "foo"


def test_check_client_ownership_clears_when_different(manager):
    manager.command_stack.stack = [DummyCommand("cmd1")]
    manager.command_stack.current_index = 0
    manager.active_client_id = "client-a"

    manager.check_client_ownership("client-b")

    assert manager.command_stack.stack == []
    assert manager.active_client_id == "client-b"


def test_check_client_ownership_keeps_when_same(manager):
    manager.command_stack.stack = [DummyCommand("cmd1")]
    manager.command_stack.current_index = 0
    manager.active_client_id = "client-a"

    manager.check_client_ownership("client-a")

    assert manager.command_stack.stack
    assert manager.active_client_id == "client-a"
