"""Best-effort parsing of the date and time text exposed by MyCourseVille."""

from __future__ import annotations

import re
from datetime import UTC, date, datetime, time, tzinfo
from zoneinfo import ZoneInfo

COURSEVILLE_TIMEZONE = ZoneInfo("Asia/Bangkok")
TemporalInput = str | int | float | date | datetime | time | None

_DATE_TOKEN = (
    r"(?:"
    r"\d{4}[-/]\d{1,2}[-/]\d{1,2}|"
    r"[A-Za-z]{3,9}\s+\d{1,2}(?:,?\s+)\d{2,4}|"
    r"\d{1,2}\s+[A-Za-z]{3,9}\s+\d{2,4}"
    r")"
)
_TIME_TOKEN = r"\d{1,2}:\d{2}(?::\d{2})?(?:\s*[AP]M)?"
_DATETIME_TOKEN = re.compile(
    rf"(?P<date>{_DATE_TOKEN})\s+(?:at\s+)?(?P<time>{_TIME_TOKEN})",
    flags=re.IGNORECASE,
)
_TIME_TOKEN_RE = re.compile(rf"(?P<time>{_TIME_TOKEN})", flags=re.IGNORECASE)

_DATETIME_FORMATS = (
    "%Y-%m-%dT%H:%M:%S.%f%z",
    "%Y-%m-%dT%H:%M:%S%z",
    "%Y-%m-%dT%H:%M%z",
    "%Y-%m-%d %H:%M:%S%z",
    "%Y-%m-%d %H:%M%z",
    "%b %d %Y %H:%M:%S",
    "%b %d %Y %H:%M",
    "%B %d %Y %H:%M:%S",
    "%B %d %Y %H:%M",
    "%d %b %Y %H:%M:%S",
    "%d %b %Y %H:%M",
    "%d %B %Y %H:%M:%S",
    "%d %B %Y %H:%M",
    "%b %d %Y %I:%M:%S %p",
    "%b %d %Y %I:%M %p",
    "%B %d %Y %I:%M:%S %p",
    "%B %d %Y %I:%M %p",
    "%d %b %Y %I:%M:%S %p",
    "%d %b %Y %I:%M %p",
    "%d %B %Y %I:%M:%S %p",
    "%d %B %Y %I:%M %p",
)
_DATE_FORMATS = (
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%b %d %Y",
    "%b %d %y",
    "%B %d %Y",
    "%B %d %y",
    "%d %b %Y",
    "%d %b %y",
    "%d %B %Y",
    "%d %B %y",
)
_TIME_FORMATS = (
    "%H:%M:%S",
    "%H:%M",
    "%I:%M:%S %p",
    "%I:%M %p",
)


def parse_courseville_datetime(
    value: TemporalInput,
    *,
    timezone: tzinfo = COURSEVILLE_TIMEZONE,
) -> datetime | None:
    """Parse a CourseVille timestamp and return an aware local datetime.

    Naive human-readable values are interpreted in ``Asia/Bangkok`` by
    default. Unrecognized values are intentionally returned as ``None`` so
    callers can continue using the raw upstream field.
    """

    if value is None:
        return None
    if isinstance(value, datetime):
        return _without_sentinel_datetime(_localize(value, timezone))
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            parsed = datetime.fromtimestamp(value, UTC)
        except (OverflowError, OSError, ValueError):
            return None
        return _without_sentinel_datetime(_localize(parsed, timezone))
    if not isinstance(value, str):
        return None

    normalized = _normalize(value)
    if not _contains_clock(normalized):
        return None

    iso_candidate = normalized.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(iso_candidate)
    except ValueError:
        parsed = None
    if parsed is not None:
        return _without_sentinel_datetime(_localize(parsed, timezone))

    candidates = [normalized]
    candidates.extend(
        " ".join(match.group("date", "time")) for match in _DATETIME_TOKEN.finditer(normalized)
    )
    for candidate in candidates:
        candidate = candidate.replace(" at ", " ")
        for date_format in _DATETIME_FORMATS:
            try:
                parsed = datetime.strptime(candidate, date_format)
            except ValueError:
                continue
            return _without_sentinel_datetime(_localize(parsed, timezone))
    return None


def parse_courseville_date(value: TemporalInput) -> date | None:
    """Parse a CourseVille date without inventing a timezone or clock time."""

    if value is None:
        return None
    if isinstance(value, datetime):
        return _without_sentinel_date(_localize(value, COURSEVILLE_TIMEZONE).date())
    if isinstance(value, date):
        return _without_sentinel_date(value)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            parsed = datetime.fromtimestamp(value, UTC)
        except (OverflowError, OSError, ValueError):
            return None
        localized = _without_sentinel_datetime(_localize(parsed, COURSEVILLE_TIMEZONE))
        return localized.date() if localized is not None else None
    if not isinstance(value, str):
        return None

    normalized = _normalize(value)
    candidates = [normalized]
    candidates.extend(match.group(0) for match in re.finditer(_DATE_TOKEN, normalized))
    for candidate in candidates:
        for date_format in _DATE_FORMATS:
            try:
                parsed = datetime.strptime(candidate, date_format).date()
            except ValueError:
                continue
            return _without_sentinel_date(parsed)
    return None


def parse_courseville_time(value: TemporalInput) -> time | None:
    """Parse a CourseVille clock time as a timezone-free ``time`` value."""

    if value is None:
        return None
    if isinstance(value, datetime):
        parsed = _without_sentinel_datetime(_localize(value, COURSEVILLE_TIMEZONE))
        return parsed.timetz().replace(tzinfo=None) if parsed is not None else None
    if isinstance(value, time):
        return value.replace(tzinfo=None)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            parsed = datetime.fromtimestamp(value, UTC)
        except (OverflowError, OSError, ValueError):
            return None
        localized = _without_sentinel_datetime(_localize(parsed, COURSEVILLE_TIMEZONE))
        return localized.timetz().replace(tzinfo=None) if localized is not None else None
    if not isinstance(value, str):
        return None

    normalized = _normalize(value)
    candidates = [normalized]
    candidates.extend(match.group("time") for match in _TIME_TOKEN_RE.finditer(normalized))
    for candidate in candidates:
        candidate = " ".join(candidate.split())
        for time_format in _TIME_FORMATS:
            try:
                return datetime.strptime(candidate, time_format).time()
            except ValueError:
                continue
    return None


def combine_courseville_datetime(day: date | None, clock: time | None) -> datetime | None:
    """Combine parsed local date/time components into an aware datetime."""

    if day is None or clock is None:
        return None
    return datetime.combine(day, clock, tzinfo=COURSEVILLE_TIMEZONE)


def _normalize(value: str) -> str:
    normalized = " ".join(value.replace(",", " ").split()).strip()
    normalized = re.sub(
        r"^(?:due|out|submitted|scheduled|posted|started|last modified)"
        r"(?:\s+(?:on|at))?\s*:?[ \t]*",
        "",
        normalized,
        flags=re.IGNORECASE,
    )
    return re.sub(r"\s+at\s+", " ", normalized, flags=re.IGNORECASE)


def _contains_clock(value: str) -> bool:
    return _TIME_TOKEN_RE.search(value) is not None


def _localize(value: datetime, timezone: tzinfo) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone)
    return value.astimezone(timezone)


def _without_sentinel_datetime(value: datetime) -> datetime | None:
    if value.year == 1970 and value.month == 1 and value.day == 1:
        return None
    return value


def _without_sentinel_date(value: date) -> date | None:
    if value.year == 1970 and value.month == 1 and value.day == 1:
        return None
    return value


__all__ = [
    "COURSEVILLE_TIMEZONE",
    "TemporalInput",
    "combine_courseville_datetime",
    "parse_courseville_date",
    "parse_courseville_datetime",
    "parse_courseville_time",
]
