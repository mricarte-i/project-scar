from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest

from app.domain.errors import InvalidWindowError
from app.domain.window import Window


def ts(year: int, month: int = 1, day: int = 1) -> datetime:
    return datetime(year, month, day, tzinfo=UTC)


# construction validation


def test_start_without_timezone_is_rejected():
    with pytest.raises(InvalidWindowError):
        Window(start=datetime(2025, 1, 1), end=ts(2026))


def test_end_without_timezone_is_rejected():
    with pytest.raises(InvalidWindowError):
        Window(start=ts(2025), end=datetime(2026, 1, 1))


def test_start_must_be_before_end():
    with pytest.raises(InvalidWindowError):
        Window(start=ts(2026), end=ts(2025))


def test_equal_start_and_end_is_rejected():
    with pytest.raises(InvalidWindowError):
        Window(start=ts(2025), end=ts(2025))


def test_not_utc_offset_is_normalized_to_utc():
    # 02:00+02:00 is the same instant as 00:00+00:00; the window should store the UTC equivalent
    plus_two = timezone(timedelta(hours=2))
    w = Window(datetime(2025, 1, 1, 2, 0, tzinfo=plus_two), None)
    assert w.start == ts(2025)


def test_open_ended_window():
    w = Window(ts(2025), None)
    assert w.is_open_ended is True


def test_bounded_window_is_not_open_ended():
    w = Window(ts(2025), ts(2026))
    assert w.is_open_ended is False


# contains


def test_contains_is_half_open():
    # [2025, 2026) contains 2025-01-01 but not 2026-01-01
    w = Window(ts(2025), ts(2026))
    assert w.contains(ts(2025)) is True
    assert w.contains(ts(2026)) is False
    assert w.contains(ts(2025, 6, 1)) is True


def test_open_ended_contains_everything_after_start():
    w = Window(ts(2025), None)
    assert w.contains(ts(2025)) is True
    assert w.contains(ts(2026)) is True
    assert w.contains(ts(2024)) is False


# overlaps


def test_adjacent_windows_do_not_overlap():
    # [2025, 2026) and [2026, 2027) are adjacent but do not overlap
    a = Window(ts(2025), ts(2026))
    b = Window(ts(2026), ts(2027))
    assert a.overlaps(b) is False
    assert b.overlaps(a) is False


def test_overlapping_windows():
    a = Window(ts(2025), ts(2027))
    b = Window(ts(2026), ts(2028))
    assert a.overlaps(b) is True
    assert b.overlaps(a) is True  # symmetry check


def test_open_ended_overlaps_anything_after_its_start():
    a = Window(ts(2025), None)
    b = Window(ts(3000), ts(3001))
    assert a.overlaps(b) is True


def test_disjoint_windows_do_not_overlap():
    a = Window(ts(2025), ts(2026))
    b = Window(ts(2030), ts(2031))
    assert a.overlaps(b) is False


# subtract


def test_subtract_no_overlap_returns_self():
    a = Window(ts(2025), ts(2026))
    b = Window(ts(2030), ts(2031))
    assert a.subtract(b) == [a]


def test_subtract_full_cover_returns_empty():
    a = Window(ts(2025), ts(2026))
    b = Window(ts(2024), ts(2027))
    assert a.subtract(b) == []


def test_subtract_clips_tail_single_remainder():
    # b clips the right end -> one left remainder
    a = Window(ts(2025), ts(2030))
    b = Window(ts(2028), None)
    assert a.subtract(b) == [Window(ts(2025), ts(2028))]


def test_subtract_clips_head_single_remainder():
    a = Window(ts(2025), ts(2030))
    b = Window(ts(2024), ts(2027))
    assert a.subtract(b) == [Window(ts(2027), ts(2030))]


def test_subtract_interior_splits_into_two():
    # b sits strictly inside a -> two remainders
    a = Window(ts(2020), ts(2030))
    b = Window(ts(2024), ts(2026))
    assert a.subtract(b) == [
        Window(ts(2020), ts(2024)),
        Window(ts(2026), ts(2030)),
    ]


def test_subtract_open_ended_self_keeps_open_right_remainder():
    a = Window(ts(2020), None)
    b = Window(ts(2023), ts(2026))
    assert a.subtract(b) == [
        Window(ts(2020), ts(2023)),
        Window(ts(2026), None),
    ]


def test_starts_at():
    assert Window(ts(2025), ts(2026)).starts_at(Window(ts(2025), None)) is True
    assert Window(ts(2025), ts(2026)).starts_at(Window(ts(2024), None)) is False
