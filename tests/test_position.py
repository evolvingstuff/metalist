"""Tests for the position management system."""
import pytest
from app.models.position import Position


def test_first_position():
    """Test getting the first position."""
    assert Position.get_first_position() == "a1"


def test_position_between_none():
    """Test generating position when no bounds are given."""
    assert Position.get_position_between(None, None) == "a1"


def test_position_before_first():
    """Test generating position before the first position."""
    pos = Position.get_position_between(None, "a1")
    assert pos < "a1"


def test_position_after_last():
    """Test generating position after the last position."""
    pos = Position.get_position_between("z9", None)
    assert pos > "z9"


def test_position_between_simple():
    """Test generating position between two simple positions."""
    cases = [
        ("a1", "b1"),
        ("a1", "z1"),
        ("a2", "a3"),
        ("a1", "a2"),
    ]
    
    for pos1, pos2 in cases:
        mid = Position.get_position_between(pos1, pos2)
        assert pos1 < mid < pos2, f"Failed: {pos1} < {mid} < {pos2}"


def test_position_between_complex():
    """Test generating position between more complex positions."""
    cases = [
        ("a1", "a2"),    # Simple numeric difference
        ("a1", "b1"),    # First character difference
        ("a1", "a11"),   # One is prefix of other
        ("y9", "z1"),    # Cross-character boundary
        ("a1", "a1"),    # Equal positions
    ]
    
    for pos1, pos2 in cases:
        mid = Position.get_position_between(pos1, pos2)
        if pos1 == pos2:
            assert pos1 < mid, f"Failed for equal positions: {pos1} < {mid}"
        else:
            assert pos1 < mid < pos2, f"Failed for {pos1} < {mid} < {pos2}"


def test_multiple_positions_maintain_order():
    """Test that generating multiple positions between the same bounds maintains order."""
    pos1 = "a1"
    pos2 = "b1"
    
    positions = []
    last_pos = pos1
    for _ in range(10):
        pos = Position.get_position_between(last_pos, pos2)
        positions.append(pos)
        last_pos = pos
    
    # Verify positions are in strictly ascending order
    for i in range(len(positions) - 1):
        assert positions[i] < positions[i + 1], f"Failed: {positions[i]} should be < {positions[i+1]}"


def test_compare_positions():
    """Test position comparison."""
    assert Position.compare("a1", "b1") == -1
    assert Position.compare("b1", "a1") == 1
    assert Position.compare("a1", "a1") == 0
    assert Position.compare("a1a", "a1") == 1
    assert Position.compare("a1", "a1a") == -1
