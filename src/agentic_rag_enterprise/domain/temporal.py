"""E-021 temporal scope model + deterministic parser (build plan §15.4 / §17.1).

``TemporalScope`` is the shared, stable domain model that the retriever, the
temporal filter, and the conflict resolver all consume for a given query
(build plan §15.4: "检索和 SCA 必须使用同一 TemporalScope"). The parser is a
pure, deterministic keyword + regex table — no LLM, no NLP library, no external
date library. Its precedence is frozen (see ``parse_temporal_scope``) so that
"截至 2025-12-31" can never be mis-read as a year ``range``.
"""

from __future__ import annotations

import re
from calendar import monthrange
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

# A strict whitelist of date shapes (build plan §15.4). Order matters: longer
# forms are tried first so a full date is never collapsed to its bare-year tail.
# Every alternative is non-capturing so ``re.findall`` returns whole date strings.
_DATE_PATTERN = (
    r"\d{4}-\d{2}-\d{2}(?:\s+\d{2}:\d{2})?"
    r"|\d{4}/\d{2}/\d{2}"
    r"|\d{4}年(?:\d{1,2}月(?:\d{1,2}日)?)?"
    r"|\d{4}"
)

# Explicit range markers (first-match precedence). Each captures a start and an
# end date token.
_RANGE_PATTERNS = [
    re.compile(
        r"between\s+(" + _DATE_PATTERN + r")\s+and\s+(" + _DATE_PATTERN + r")", re.IGNORECASE
    ),
    re.compile(r"from\s+(" + _DATE_PATTERN + r")\s+to\s+(" + _DATE_PATTERN + r")", re.IGNORECASE),
    re.compile(r"(" + _DATE_PATTERN + r")\s*至\s*(" + _DATE_PATTERN + r")"),
    re.compile(r"(" + _DATE_PATTERN + r")\s*到\s*(" + _DATE_PATTERN + r")"),
    re.compile(r"(" + _DATE_PATTERN + r")\s*~\s*(" + _DATE_PATTERN + r")"),
    re.compile(r"(" + _DATE_PATTERN + r")\s*和\s*(" + _DATE_PATTERN + r")\s*之间"),
]

# as_of markers. Prefix forms (截至 / 截止 / as of / as_of) eat the following
# date; the suffix form (… 为止) takes the date that precedes it.
_AS_OF_PREFIX_RE = re.compile(r"(?:截至|截止|as\s+of|as_of)\s*[:：]?\s*(" + _DATE_PATTERN + r")")
_AS_OF_SUFFIX_RE = re.compile(r"(" + _DATE_PATTERN + r")\s*为止")

# Current markers. English tokens are word-bounded so "knowledge" does not
# accidentally match "now".
_CURRENT_RE = re.compile(r"当前|现在|目前|\bcurrent\b|\bnow\b|\btoday\b", re.IGNORECASE)

# Plausible year band for a bare 4-digit token. Keeps ports ("8080") and other
# stray 4-digit numbers from being read as a temporal year (defensive).
_MIN_YEAR, _MAX_YEAR = 1900, 2999

# Date formats tried (strict) by ``_parse_date``.
_DATE_FORMATS = (
    "%Y-%m-%d %H:%M",
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%Y年%m月%d日",
    "%Y年%m月",
    "%Y年",
    "%Y",
)


class TemporalScope(BaseModel):
    """Shared temporal intent for one query (build plan §15.4 / §17.1).

    Frozen: the resolver and filter must reason over an immutable scope derived
    once at the top of each ``ChatService`` entry point (issue #1 — ``as_of`` was
    previously mis-identified as ``range``; the parser precedence below fixes it).
    """

    model_config = ConfigDict(frozen=True)

    mode: Literal["current", "as_of", "range", "unspecified"]
    as_of: datetime | None = None  # set when mode == "as_of"
    start: datetime | None = None  # set when mode == "range"
    end: datetime | None = None  # set when mode == "range"


def _parse_date(raw: str) -> datetime | None:
    """Strictly parse one date token against the frozen whitelist; never guess."""
    raw = raw.strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    return None


def _expand_to_range(raw: str) -> tuple[datetime, datetime]:
    """Expand a bare-year / bare-date token to an inclusive [start, end] window."""
    dt = _parse_date(raw)
    if dt is None:
        raise ValueError(f"cannot parse temporal date token: {raw!r}")

    if re.fullmatch(r"\d{4}(?:年)?", raw):
        # Bare year → the whole calendar year.
        return datetime(dt.year, 1, 1), datetime(dt.year, 12, 31, 23, 59, 59)
    if re.fullmatch(r"\d{4}年\d{1,2}月", raw):
        last_day = monthrange(dt.year, dt.month)[1]
        return (
            datetime(dt.year, dt.month, 1),
            datetime(dt.year, dt.month, last_day, 23, 59, 59),
        )
    # A specific day (with or without a time component).
    return (
        datetime(dt.year, dt.month, dt.day, 0, 0, 0),
        datetime(dt.year, dt.month, dt.day, 23, 59, 59),
    )


def parse_temporal_scope(query: str, *, now: datetime | None = None) -> TemporalScope:
    """Deterministically classify a query's temporal intent.

    Frozen first-match precedence (build plan §15.4):

    1. **explicit range** — ``between … and …`` / ``from … to …`` / ``… 至 …`` /
       ``… 到 …`` / ``… 之间`` / ``… ~ …``.
    2. **as_of** — ``截至`` / ``as of`` / ``as_of`` / ``截止`` / ``… 为止``
       followed by a parseable date.
    3. **current** — ``当前`` / ``现在`` / ``目前`` / ``current`` / ``now`` /
       ``today``.
    4. **bare-year range** — a bare 4-digit year (or a ``*年*`` reference)
       *without* any of the markers above.
    5. **unspecified** — no temporal marker at all.

    ``now`` is injectable (defaults to ``datetime.now()``) so tests are
    deterministic; it is reserved for future relative-resolution use and does
    not change classification. When an ``as_of`` marker is present the bare-year
    rule is suppressed (issue #1 guard).
    """
    del now  # reserved for future relative resolution; classification is keyword-based
    q = query or ""

    # 1) Explicit range.
    for pattern in _RANGE_PATTERNS:
        match = pattern.search(q)
        if match:
            start = _parse_date(match.group(1))
            end = _parse_date(match.group(2))
            if start is not None and end is not None:
                # Date-only bounds cover the whole day (so "between 2024-01-01 and
                # 2024-12-31" spans the full year, not just its midnights).
                if ":" not in match.group(1):
                    start = start.replace(hour=0, minute=0, second=0, microsecond=0)
                if ":" not in match.group(2):
                    end = end.replace(hour=23, minute=59, second=59, microsecond=0)
                return TemporalScope(mode="range", start=start, end=end)

    # 2) as_of (prefix marker eats the following date; suffix "… 为止" precedes).
    as_of_date: datetime | None = None
    prefix = _AS_OF_PREFIX_RE.search(q)
    if prefix:
        as_of_date = _parse_date(prefix.group(1))
    else:
        suffix = _AS_OF_SUFFIX_RE.search(q)
        if suffix:
            as_of_date = _parse_date(suffix.group(1))
    if as_of_date is not None:
        return TemporalScope(mode="as_of", as_of=as_of_date)

    # 3) current.
    if _CURRENT_RE.search(q):
        return TemporalScope(mode="current")

    # 4) bare-year / bare-date range — suppressed if any as_of marker is present.
    has_as_of_marker = bool(_AS_OF_PREFIX_RE.search(q) or _AS_OF_SUFFIX_RE.search(q))
    if not has_as_of_marker:
        for raw in re.findall(_DATE_PATTERN, q):
            parsed = _parse_date(raw)
            if parsed is None:
                continue
            if parsed.year < _MIN_YEAR or parsed.year > _MAX_YEAR:
                # e.g. a port number "8080" — not a year.
                continue
            start, end = _expand_to_range(raw)
            return TemporalScope(mode="range", start=start, end=end)

    # 5) unspecified.
    return TemporalScope(mode="unspecified")
