from dataclass import dataclass, field
from typing import Any

from app.logic.window import Window


@dataclass(frozen=True)
class ExistingVersion:
    """
    row already exists in db
    """

    id: int
    window: Window
    payload_ref: Any


@dataclass(frozen=True)
class Truncation:
    """
    shrinks an existing version's window
    """

    version_id: int
    new_window: Window


@dataclass(frozen=True)
class Insert:
    """
    `lineage_version_id` is set when this row is a continuation of an existing version
    (right-handed remainder of a split)
    """

    window: Window
    payload_ref: Any
    lineage_version_id: int | None = None


@dataclass(frozen=True)
class Deletion:
    version_id: int


@dataclass(frozen=True)
class SupersedePlan:
    truncations: list[Truncation] = field(default_factory=list)
    inserts: list[Insert] = field(default_factory=list)
    deletions: list[Deletion] = field(default_factory=list)

    @property
    def requires_override(self) -> bool:
        if self.deletions:
            return True
        return any(ins.lineage_version_id is not None for ins in self.inserts)


def plan_supersede(
    new_window: Window,
    new_payload_ref: Any,
    timeline: list[ExistingVersion],
    *,
    allow_historical_overwrite: bool = False,
) -> SupersedePlan:
    """
    figure out what operations do we need to introduce `new_window` into `timeline`
    for each existing `version` in `timeline`:
      - if `version.window` does not overlap with `new_window`, we can skip it
      - else we subtract it by `new_window` and:
        - if there is no remainder, it means `new_window` completely covers `version.window`, so we can just
        delete it (or truncate it to 0, which is the same); this is a REPLACE and we should require a flag to avoid unintentional data loss
        - if there is a 1 remainder, we need to truncate `version` to the left
        - if there is a second remainder, it means `new_window` is strictly contained in `version.window`, so we need to insert a new version of the original `version`
        for the right remainder with the same payload reference as `version`
    """
    plan = SupersedePlan(inserts=[Insert(new_window, new_payload_ref)])
    for version in timeline:
        if not version.window.overlaps(new_window):
            continue

        # remainders = should have at least one window, the "left one"; and maybe a "right one" if the new window is strictly contained in the existing one
        remainders = version.window.subtract(new_window)
        if not remainders:
            # new window completely covers the existing one, we can just truncate it to 0
            # this should be a REPLACE...
            # NOTE: require a flag to allow this, to avoid unintentional data loss
            plan.deletions.append(Deletion(version.id))
            continue
        left = remainders[0]
        plan.truncations.append(Truncation(version.id, left))
        for extra in remainders[1:]:
            # if there is a second remainder, it means the new window is strictly contained in the existing one,
            # so we need to insert an extra version for the right remainder with the same payload reference as the existing version
            plan.inserts.append(
                Insert(extra, version.payload_ref, lineage_version_id=version.id)
            )

    if plan.requires_override and not allow_historical_overwrite:
        affected = [d.version_id for d in plan.deletions] + [
            ins.lineage_version_id
            for ins in plan.inserts
            if ins.lineage_version_id is not None
        ]
        raise Exception(
            f"Supersede plan requires override of existing versions, but allow_historical_overwrite is False",
            affected_version_ids=affected,
        )

    return plan
