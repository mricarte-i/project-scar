from dataclasses import dataclass
from datetime import datetime, timezone


def _ensure_utc(ts: datetime, label: str) -> datetime:
    if ts.tzinfo is None:
        raise ValueError(f"{label} must include timezone offset (no naive datetimes)")
    return ts.astimezone(timezone.utc)


@dataclass(frozen=True)
class Window:
    start: datetime
    end: datetime | None

    def __post_init__(self):
        start = _ensure_utc(self.start, "start")
        object.__setattr__(self, "start", start)
        if self.end is not None:
            end = _ensure_utc(self.end, "end")
            object.__setattr__(self, "end", end)
            if not start < end:
                raise ValueError(f"empty window: start {start} is not before end {end}")

    @property
    def is_open_ended(self) -> bool:
        return self.end is None

    def contains(self, ts: datetime) -> bool:
        ts = _ensure_utc(ts, "ts")
        if ts < self.start:
            return False
        return self.end is None or ts < self.end

    def overlaps(self, other: Window) -> bool:
        self_start_before_other_end = other.end is None or self.start < other.end
        other_start_before_self_end = self.end is None or other.start < self.end
        """
        [s1, e1) overlaps [s2, e2) if s1 < e2 and s2 < e1
        if e1 or e2 is None, the corresponding condition is always true
        """
        return self_start_before_other_end and other_start_before_self_end

    def subtract(self, other: Window) -> list[Window]:
        if not self.overlaps(other):
            return [self]
        """
        if we do have an overlap betwen A and B (and we're A), we have two cases:
        1. we want to subtract [sB, eB) from [sA, eA) and sA < sB < eA <= eB
           in this case we want to return [sA, sB)
        2. we want to subtract [sB, eB) from [sA, eA) and sB <= sA < eB < eA (AND eB is not None)
           in this case we want to return [eB, eA)
        """
        remainders: list[Window] = []
        if self.start < other.start:
            remainders.append(Window(self.start, other.start))
        if other.end is None or (self.end is not None and other.end < self.end):
            remainders.append(Window(other.end, self.end))
        return remainders

    def starts_at(self, other: Window) -> bool:
        return self.start == other.start
