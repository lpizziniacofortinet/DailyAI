"""Shared publication-date parsing and freshness evaluation utilities.

Ensures consistent, fail-closed temporal semantics across Research (Agent 1)
and Fact-Check (Agent 2) stages, with an injectable reference clock for
deterministic testing.
"""

from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Callable, Optional

from dateutil import parser as date_parser
from pydantic import BaseModel, Field

Clock = Callable[[], datetime]


def utc_now() -> datetime:
    """Default UTC clock."""
    return datetime.now(timezone.utc)


def _normalize_utc(dt: datetime) -> datetime:
    """Normalize a naive or timezone-aware datetime to UTC."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


class DateEvaluationStatus(str, Enum):
    """Classification of an article's publication date."""

    FRESH = "FRESH"
    STALE = "STALE"
    FUTURE = "FUTURE"
    MISSING = "MISSING"
    MALFORMED = "MALFORMED"


class DateEvaluation(BaseModel):
    """Structured result of evaluating a publication date against freshness rules."""

    status: DateEvaluationStatus = Field(..., description="Freshness classification")
    parsed_date: Optional[datetime] = Field(
        default=None, description="Parsed UTC datetime if valid"
    )
    raw_date: Optional[str] = Field(
        default=None, description="Original unparsed date string"
    )
    reason: Optional[str] = Field(
        default=None, description="Human-readable explanation for rejection/quarantine"
    )
    date_unverified: bool = Field(
        default=False,
        description="True when the publication date is missing or unparseable",
    )

    @property
    def is_fresh(self) -> bool:
        """Return True only when the date was validly parsed and within bounds."""
        return self.status == DateEvaluationStatus.FRESH

    def should_reject(self, strict_mode: bool = True) -> bool:
        """Return True if the item should be rejected/quarantined under the given mode."""
        if self.status in (DateEvaluationStatus.STALE, DateEvaluationStatus.FUTURE):
            return True
        if self.status in (DateEvaluationStatus.MISSING, DateEvaluationStatus.MALFORMED):
            return strict_mode
        return False


def evaluate_publication_date(
    date_str: Optional[str],
    lookback_hours: int,
    buffer_days: int = 2,
    now: Optional[datetime] = None,
    future_tolerance_hours: int = 24,
) -> DateEvaluation:
    """Evaluate a publication date string against freshness and sanity bounds.

    - Missing or blank dates -> MISSING (date_unverified=True)
    - Unparseable dates -> MALFORMED (date_unverified=True)
    - Naive datetimes are interpreted as UTC; aware datetimes are converted to UTC
    - Dates > now + future_tolerance_hours -> FUTURE
    - Dates < now - (lookback_hours + buffer_days * 24) -> STALE
    - Dates on the exact boundary are considered FRESH
    """
    reference_now = _normalize_utc(now) if now is not None else utc_now()

    if date_str is None or not str(date_str).strip():
        return DateEvaluation(
            status=DateEvaluationStatus.MISSING,
            raw_date=date_str,
            reason="Publication date is missing; strict mode requires a verifiable date.",
            date_unverified=True,
        )

    cleaned = str(date_str).strip()
    try:
        parsed = date_parser.parse(cleaned)
    except (ValueError, TypeError, OverflowError):
        return DateEvaluation(
            status=DateEvaluationStatus.MALFORMED,
            raw_date=date_str,
            reason=f"Publication date '{cleaned}' is malformed and cannot be verified.",
            date_unverified=True,
        )

    parsed_utc = _normalize_utc(parsed)

    if parsed_utc > reference_now + timedelta(hours=future_tolerance_hours):
        return DateEvaluation(
            status=DateEvaluationStatus.FUTURE,
            parsed_date=parsed_utc,
            raw_date=date_str,
            reason=f"Publication date '{cleaned}' is unexpectedly in the future.",
            date_unverified=False,
        )

    max_age = timedelta(hours=lookback_hours + (buffer_days * 24))
    cutoff = reference_now - max_age
    if parsed_utc < cutoff:
        return DateEvaluation(
            status=DateEvaluationStatus.STALE,
            parsed_date=parsed_utc,
            raw_date=date_str,
            reason=(
                f"Article published on {cleaned} is too old "
                f"(freshness window: {lookback_hours} hours)."
            ),
            date_unverified=False,
        )

    return DateEvaluation(
        status=DateEvaluationStatus.FRESH,
        parsed_date=parsed_utc,
        raw_date=date_str,
        reason=None,
        date_unverified=False,
    )


def is_article_outdated(
    date_str: Optional[str],
    lookback_hours: int,
    buffer_days: int = 2,
    now: Optional[datetime] = None,
    strict_mode: bool = True,
) -> bool:
    """Return True if an article fails the publication date freshness gate.

    Fails closed when `strict_mode=True`: missing or malformed dates are treated
    as unacceptable rather than silently fresh.
    """
    evaluation = evaluate_publication_date(
        date_str=date_str,
        lookback_hours=lookback_hours,
        buffer_days=buffer_days,
        now=now,
    )
    return evaluation.should_reject(strict_mode=strict_mode)
