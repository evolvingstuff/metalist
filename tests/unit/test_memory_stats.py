from app.services.memory_service import MemoryStats


def test_ratio_increases_with_positive_feedback():
    baseline = MemoryStats(0, 0).ratio
    one_positive = MemoryStats(1, 0).ratio
    three_positive = MemoryStats(3, 0).ratio

    assert 0.0 < baseline < 1.0
    assert baseline < one_positive < three_positive < 1.0


def test_ratio_decreases_with_additional_negative_feedback():
    one_negative = MemoryStats(0, 1).ratio
    many_negative = MemoryStats(0, 3).ratio

    assert 0.0 < many_negative < one_negative < 1.0
