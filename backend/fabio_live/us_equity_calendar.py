"""NYSE (XNYS) equity session schedule for Fabio runtime and launchers.

Uses ``exchange_calendars`` (calendar key ``XNYS``). Session open/close reflect
official regular hours including early-close days; see ``portal/docs/EXCHANGE_CALENDAR.md``.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from functools import lru_cache
from zoneinfo import ZoneInfo

import pandas as pd

from fabio_live.constants import (
    EOD_CLOSE_BEFORE_SESSION_MINUTES,
    EOD_SUMMARY_AFTER_SESSION_CLOSE_MINUTES,
    MARKET_TIMEZONE,
    OPENING_RANGE_DURATION_MINUTES,
    SIGNAL_END_BUFFER_BEFORE_SESSION_CLOSE_MINUTES,
    SIGNAL_END_HOUR,
)


@lru_cache(maxsize=1)
def _xnys_calendar():
    import exchange_calendars as xcals

    return xcals.get_calendar("XNYS")


def naive_session_label(day: datetime.date) -> pd.Timestamp:
    """Timezone-naive date label required by exchange_calendars ``is_session``."""
    return pd.Timestamp(day)


def is_nyse_trading_day(day: datetime.date) -> bool:
    return bool(_xnys_calendar().is_session(naive_session_label(day)))


@dataclass(frozen=True)
class NyseSessionSchedule:
    """Regular-session milestones in America/New_York."""

    session_date: datetime.date
    session_open_et: datetime.datetime
    session_close_et: datetime.datetime
    or_end_et: datetime.datetime
    eod_force_flatten_et: datetime.datetime
    eod_summary_et: datetime.datetime
    effective_signal_end_et: datetime.datetime

    @property
    def market_close_et(self) -> datetime.datetime:
        return self.session_close_et


def get_nyse_session_schedule_et(
    day: datetime.date,
    *,
    eod_before_close_minutes: int | None = None,
    summary_after_close_minutes: int | None = None,
    signal_end_buffer_before_close_minutes: int | None = None,
    opening_range_duration_minutes: int | None = None,
    signal_end_hour: int | None = None,
) -> NyseSessionSchedule | None:
    """
    Return session milestone datetimes in ``America/New_York``, or None if closed.

    ``or_end_et`` is ``session_open_et + opening_range_duration_minutes`` (Fabio OR window).
    ``effective_signal_end_et`` is the earlier of the nominal 2pm ET cutoff and
    ``session_close_et - signal_end_buffer_before_close_minutes``.
    """
    cal = _xnys_calendar()
    lbl = naive_session_label(day)
    if not cal.is_session(lbl):
        return None

    eod_b = int(
        eod_before_close_minutes
        if eod_before_close_minutes is not None
        else EOD_CLOSE_BEFORE_SESSION_MINUTES
    )
    summary_a = int(
        summary_after_close_minutes
        if summary_after_close_minutes is not None
        else EOD_SUMMARY_AFTER_SESSION_CLOSE_MINUTES
    )
    sig_buf = int(
        signal_end_buffer_before_close_minutes
        if signal_end_buffer_before_close_minutes is not None
        else SIGNAL_END_BUFFER_BEFORE_SESSION_CLOSE_MINUTES
    )
    or_dur = int(
        opening_range_duration_minutes
        if opening_range_duration_minutes is not None
        else OPENING_RANGE_DURATION_MINUTES
    )
    se_h = int(signal_end_hour if signal_end_hour is not None else SIGNAL_END_HOUR)

    tz = ZoneInfo(MARKET_TIMEZONE)
    open_utc = cal.session_open(lbl)
    close_utc = cal.session_close(lbl)
    open_et = open_utc.tz_convert(tz)
    close_et = close_utc.tz_convert(tz)

    or_end_et = open_et + datetime.timedelta(minutes=or_dur)
    flatten_et = close_et - datetime.timedelta(minutes=max(0, eod_b))
    summary_et = close_et + datetime.timedelta(minutes=max(0, summary_a))

    nominal_signal_end_et = datetime.datetime(
        day.year,
        day.month,
        day.day,
        se_h,
        0,
        0,
        tzinfo=tz,
    )
    max_signal_et = close_et - datetime.timedelta(minutes=max(0, sig_buf))
    effective_signal_et = min(nominal_signal_end_et, max_signal_et)

    return NyseSessionSchedule(
        session_date=day,
        session_open_et=open_et,
        session_close_et=close_et,
        or_end_et=or_end_et,
        eod_force_flatten_et=flatten_et,
        eod_summary_et=summary_et,
        effective_signal_end_et=effective_signal_et,
    )


def get_session_schedule_for_now_et(now_et: datetime.datetime) -> NyseSessionSchedule | None:
    """Resolve schedule for the calendar date of ``now_et`` in America/New_York."""
    if now_et.tzinfo is None:
        now_et = now_et.replace(tzinfo=ZoneInfo(MARKET_TIMEZONE))
    else:
        now_et = now_et.astimezone(ZoneInfo(MARKET_TIMEZONE))
    return get_nyse_session_schedule_et(now_et.date())
