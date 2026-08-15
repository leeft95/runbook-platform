"""Exchange calendar helper functions."""

import datetime as dt
from collections.abc import Iterable
from typing import Literal

import pandas as pd
from pandas.tseries.holiday import USFederalHolidayCalendar
from pandas.tseries.offsets import BDay, CustomBusinessDay, MonthEnd
from pytz import timezone


def _normalize_timestamp(date: str | dt.datetime | pd.Timestamp) -> pd.Timestamp:
    """Normalize timestamp."""
    ts = pd.Timestamp(date)
    if ts.tzinfo is not None:
        ts = ts.tz_localize(None)
    return ts.normalize()


class TradingCalendar:
    """Business-day calendar built from an optional holiday list."""

    def __init__(self, holidays_list: Iterable[str | dt.datetime | pd.Timestamp] | None = None) -> None:
        if holidays_list is None:
            self._holiday_calendar = USFederalHolidayCalendar()
            self._holidays: tuple[pd.Timestamp, ...] = ()
        else:
            self._holiday_calendar = None
            self._holidays = tuple(_normalize_timestamp(h) for h in holidays_list)

    def _bday_offset(self, n: int = 1) -> BDay | CustomBusinessDay:
        """Handle bday offset."""
        if self._holiday_calendar is not None:
            return CustomBusinessDay(n=n, calendar=self._holiday_calendar)
        return CustomBusinessDay(n=n, holidays=list(self._holidays))

    def adjust(
        self,
        date: str | dt.datetime | pd.Timestamp,
        n: int,
        adj: str | None = None,
    ) -> dt.datetime:
        """Shift by n business days, then apply adj convention if the result is a non-business day.

        adj values:
          None / "f" / "follow" / "following"  → roll forward (default)
          "p" / "prev" / "previous"             → roll backward
          "m" / "modified_following"            → roll forward unless it crosses a month boundary, then roll back
        n=0 rolls the input date itself to the nearest business day using adj.
        """
        date_ts = _normalize_timestamp(date)
        one_bday = self._bday_offset(1)
        shifted_ts = date_ts if n == 0 else pd.Timestamp(date_ts + self._bday_offset(n))

        rolled_fwd = pd.Timestamp(one_bday.rollforward(shifted_ts))
        if shifted_ts == rolled_fwd:
            return shifted_ts.to_pydatetime()

        # shifted_ts is not a business day — apply convention
        if adj in (None, "f", "follow", "following"):
            return rolled_fwd.to_pydatetime()
        if adj in ("p", "prev", "previous"):
            return pd.Timestamp(one_bday.rollback(shifted_ts)).to_pydatetime()
        if adj in ("m", "modified_following"):
            if rolled_fwd.month != shifted_ts.month:
                return pd.Timestamp(one_bday.rollback(shifted_ts)).to_pydatetime()
            return rolled_fwd.to_pydatetime()
        raise ValueError(f"Unknown adjustment convention: {adj!r}")

    def business_day_range(
        self,
        start: str | dt.datetime | pd.Timestamp,
        end: str | dt.datetime | pd.Timestamp,
        inclusive: Literal["both", "left", "right", "neither"] = "both",
    ) -> pd.DatetimeIndex:
        """Return business days between start and end using this calendar."""
        start_ts = _normalize_timestamp(start)
        end_ts = _normalize_timestamp(end)
        return pd.date_range(start=start_ts, end=end_ts, freq=self._bday_offset(1), inclusive=inclusive)

    def trading_month_start(self, date: str | dt.datetime | pd.Timestamp) -> dt.datetime:
        """First business day of the month containing date."""
        ts = _normalize_timestamp(date)
        start = ts.replace(day=1)
        rolled = self._bday_offset(1).rollforward(start)
        return pd.Timestamp(rolled).to_pydatetime()

    def trading_month_end(self, date: str | dt.datetime | pd.Timestamp) -> dt.datetime:
        """Last business day of the month containing date."""
        ts = _normalize_timestamp(date)
        month_end = ts + MonthEnd(0)
        rolled = self._bday_offset(1).rollback(month_end)
        return pd.Timestamp(rolled).to_pydatetime()

    def trading_month_bounds(self, date: str | dt.datetime | pd.Timestamp) -> tuple[dt.datetime, dt.datetime]:
        """Tuple of (trading_month_start, trading_month_end)."""
        return self.trading_month_start(date), self.trading_month_end(date)


# Helper functions for common calendar operations


def today():
    """Handle today."""
    return dt.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)


def today_utc():
    """Handle today utc."""
    return dt.datetime.now(tz=timezone("UTC")).replace(hour=0, minute=0, second=0, microsecond=0)


def now_lnd():
    """Handle now lnd."""
    return dt.datetime.now(tz=timezone("Europe/London")).replace(tzinfo=None)


def adjust_bdays(
    date: str | dt.datetime,
    n: int,
    holidays_list: list[dt.datetime] | None = None,
    adj: str | None = None,
) -> dt.datetime:
    """Adjust a date by n business days, taking into account holidays.

    Args:
        date: The date to adjust.
        n: The number of business days to adjust by. Can be positive or negative.
            n=0 rolls the date itself to the nearest business day using adj.
        holidays_list: Holiday list to exclude. Defaults to None (US Federal holidays).
        adj: Adjustment convention when landing on a non-business day.
            None / "f" / "follow" / "following"  → following business day (default)
            "p" / "prev" / "previous"             → previous business day
            "m" / "modified_following"            → following, unless it crosses a month
                                                    boundary, then previous

    Returns:
        The adjusted datetime.
    """
    return TradingCalendar(holidays_list=holidays_list).adjust(date=date, n=n, adj=adj)
