"""Tests for the position management system."""
import pytest
from app.models.position import Position


def test_first_position():
    """Test getting the first position."""
    assert Position.get_first_position() == "a0"


def test_position_between_none():
    """Test generating position when no bounds are given."""
    assert Position.get_position_between(None, None) == "a0"


def test_position_before_first():
    """Test generating position before the first position."""
    first = Position.get_first_position()  # "a0"
    pos = Position.get_position_between(None, first)
    assert pos < first


def test_position_after_last():
    """Test generating position after the last position."""
    pos = Position.get_position_between("a1", None)
    assert pos > "a1"


def test_position_between_simple():
    """Test generating position between two simple positions."""
    cases = [
        ("a0", "a1"),
        ("a1", "a2"),
        ("a2", "a3"),
        ("a0", "a1"),
    ]
    
    for pos1, pos2 in cases:
        mid = Position.get_position_between(pos1, pos2)
        assert pos1 < mid < pos2, f"Failed: {pos1} < {mid} < {pos2}"


def test_position_between_complex():
    """Test generating position between more complex positions."""
    cases = [
        ("a0", "a1"),      # Simple difference
        ("a1", "a1V"),     # One is prefix of other
        ("a1V", "a2"),     # Complex ordering
    ]
    
    for pos1, pos2 in cases:
        mid = Position.get_position_between(pos1, pos2)
        assert pos1 < mid < pos2, f"Failed for {pos1} < {mid} < {pos2}"


def test_many_positions_before_first():
    """Test generating many positions before the first position."""
    first_pos = Position.get_first_position()  # "a0"
    positions = []
    last_pos = first_pos
    
    # Generate 100 positions before the first position
    for i in range(100):
        pos = Position.get_position_between(None, last_pos)
        positions.append(pos)
        last_pos = pos
        
    # Verify positions are in strictly descending order (Zz, Zy, Zx, etc.)
    for i in range(len(positions) - 1):
        assert positions[i] > positions[i + 1], f"Failed: {positions[i]} should be > {positions[i+1]}"
    
    # Verify all positions are less than the first position
    for pos in positions:
        assert pos < first_pos, f"Failed: {pos} should be < {first_pos}"


def test_multiple_positions_maintain_order():
    """Test that generating multiple positions between the same bounds maintains order."""
    pos1 = "a0"
    pos2 = "a1"
    
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
    assert Position.compare("a0", "a1") == -1
    assert Position.compare("a1", "a0") == 1
    assert Position.compare("a0", "a0") == 0
    assert Position.compare("a1V", "a1") == 1
    assert Position.compare("a1", "a1V") == -1


def test_many_many_positions_before_first():
    """Test generating 1000 positions before first to see what happens."""
    first_pos = Position.get_first_position()  # "a0"
    positions = []
    last_pos = first_pos
    
    # Generate 1000 positions before the first position
    for i in range(1000):
        pos = Position.get_position_between(None, last_pos)
        positions.append(pos)
        last_pos = pos
        
        # Print some interesting samples
        if i in [0, 1, 2, 10, 50, 100, 500, 999]:
            print(f"\nPosition {i}: {pos}")
        
        # Print length stats every 100 positions
        if i > 0 and i % 100 == 0:
            lengths = [len(p) for p in positions]
            avg_len = sum(lengths) / len(lengths)
            max_len = max(lengths)
            print(f"\nAfter {i} insertions:")
            print(f"Average length: {avg_len:.1f}")
            print(f"Max length: {max_len}")
    
    # Verify positions are in strictly descending order
    for i in range(len(positions) - 1):
        assert positions[i] > positions[i + 1], f"Failed: {positions[i]} should be > {positions[i+1]}"
    
    # Verify all positions are less than the first position
    for pos in positions:
        assert pos < first_pos, f"Failed: {pos} should be < {first_pos}"
