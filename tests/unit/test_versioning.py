from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.domain.errors import HistoricalEditError, InvalidWindowError, NoAssetValidError
from app.domain.versioning import ExistingVersion, Truncation, plan_retire, plan_supersede
from app.domain.window import Window


def ts(year: int) -> datetime:
    return datetime(year, 1, 1, tzinfo=UTC)


def existing_version(id: int, start: int, end: int | None) -> ExistingVersion:
    return ExistingVersion(
        id=id, window=Window(ts(start), ts(end) if end is not None else None), payload_ref=id
    )


# plan_supersede


def test_create_into_empty_timeline_is_a_single_insert():
    # the "no overlaps" case
    plan = plan_supersede(Window(ts(2025), None), new_payload_ref="p", timeline=[])
    assert len(plan.inserts) == 1
    assert plan.truncations == []
    assert plan.deletions == []
    assert plan.requires_override is False


def test_create_into_overlapping_version():
    # the "overlaps and has 1 remainder" case
    timeline = [existing_version(id=1, start=2020, end=None)]
    plan = plan_supersede(Window(ts(2025), None), new_payload_ref="p", timeline=timeline)

    assert len(plan.inserts) == 1  # only 1 new version to insert
    assert plan.truncations == [Truncation(version_id=1, new_window=Window(ts(2020), ts(2025)))]
    # the existing version is truncated to end at the new version's start
    assert plan.deletions == []
    assert plan.requires_override is False


def test_supersede_delete_requires_override():
    timeline = [existing_version(id=1, start=2025, end=2026)]
    with pytest.raises(HistoricalEditError):
        # asset version 1: [2025, 2026) is fully overlapped by new version p: [2024, 2027)
        # so it will get deleted and replaced by new version p
        plan_supersede(
            Window(ts(2024), ts(2027)),
            new_payload_ref="p",
            timeline=timeline,
        )


def test_create_overlaps_and_replaces_existing_version():
    timeline = [existing_version(id=1, start=2025, end=2026)]
    # asset version 1: [2025, 2026) is fully overlapped by new version p: [2024, 2027)
    # so it will get deleted and replaced by new version p
    plan = plan_supersede(
        Window(ts(2024), ts(2027)),
        new_payload_ref="p",
        timeline=timeline,
        allow_historical_overwrite=True,
    )

    assert [d.version_id for d in plan.deletions] == [1]
    assert plan.requires_override is True


def test_supersede_split_requires_override():
    timeline = [existing_version(id=1, start=2020, end=2030)]
    with pytest.raises(HistoricalEditError) as exc:
        # asset version 1: [2020, 2030) is overlapped by new version p: [2024, 2027)
        # so it will get split into two versions: [2020, 2024) and [2027, 2030)
        plan_supersede(
            Window(ts(2024), ts(2027)),
            new_payload_ref="p",
            timeline=timeline,
        )
    # we get an error and the id of the affected version is in the error details
    assert exc.value.affected_version_ids == [1]


def test_create_overlaps_and_splits_existing_version():
    timeline = [existing_version(id=1, start=2020, end=2030)]
    # asset version 1: [2020, 2030) is overlapped by new version p: [2024, 2027)
    # so it will get split into two versions: [2020, 2024) and [2027, 2030)
    plan = plan_supersede(
        Window(ts(2024), ts(2027)),
        new_payload_ref="p",
        timeline=timeline,
        allow_historical_overwrite=True,
    )

    # truncate original row
    assert plan.truncations == [
        Truncation(version_id=1, new_window=Window(ts(2020), ts(2024))),
    ]
    # we insert the asset version p AND the continuation of the original version
    assert len(plan.inserts) == 2
    continuation = [i for i in plan.inserts if i.lineage_version_id is not None]
    assert len(continuation) == 1
    # the continuation is for version 1 and has the right window
    # and has a reference to the original version
    assert continuation[0].lineage_version_id == 1
    assert continuation[0].window == Window(ts(2027), ts(2030))
    assert plan.deletions == []
    # we're messing with history, so we require override
    assert plan.requires_override is True


def test_non_overlapping_version_arent_modified():
    timeline = [
        existing_version(id=1, start=2010, end=2011),
        existing_version(id=2, start=2012, end=2013),
    ]
    plan = plan_supersede(Window(ts(2020), None), new_payload_ref="p", timeline=timeline)
    assert plan.truncations == []
    assert plan.deletions == []
    assert len(plan.inserts) == 1


# plan_retire


def test_retire_truncates_active_version():
    timeline = [existing_version(id=1, start=2020, end=None)]
    plan = plan_retire(effective=ts(2025), timeline=timeline)
    assert plan.truncations == [Truncation(version_id=1, new_window=Window(ts(2020), ts(2025)))]
    assert plan.deletions == []
    assert plan.inserts == []
    assert plan.requires_override is False


def test_retire_with_no_active_version_raises_error():
    with pytest.raises(NoAssetValidError):
        plan_retire(effective=ts(2025), timeline=[])


def test_retire_inside_already_closed_history_raises_error():
    timeline = [existing_version(id=1, start=2020, end=2030)]
    with pytest.raises(HistoricalEditError):
        plan_retire(effective=ts(2025), timeline=timeline)


def test_retire_where_effective_equals_start_of_active_version_raises_error():
    timeline = [existing_version(id=1, start=2020, end=None)]
    with pytest.raises(InvalidWindowError):
        plan_retire(effective=ts(2020), timeline=timeline)
