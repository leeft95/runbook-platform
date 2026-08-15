from __future__ import annotations

import datetime as dt

from runbook.core.calendar import TradingCalendar, adjust_bdays


def test_adjust_bdays_uses_custom_holiday_list() -> None:
    holidays = [dt.datetime(2024, 1, 1)]
    assert adjust_bdays("2024-01-01", 0, holidays) == dt.datetime(2024, 1, 2)
    assert adjust_bdays("2024-01-02", 1, holidays) == dt.datetime(2024, 1, 3)
    assert adjust_bdays("2024-01-03", -1, holidays) == dt.datetime(2024, 1, 2)


def test_trading_calendar_business_day_range_skips_weekends_and_holidays() -> None:
    cal = TradingCalendar([dt.datetime(2024, 1, 1)])
    out = cal.business_day_range("2023-12-29", "2024-01-03")
    assert out.tolist() == [
        dt.datetime(2023, 12, 29),
        dt.datetime(2024, 1, 2),
        dt.datetime(2024, 1, 3),
    ]


def test_trading_calendar_trading_month_bounds_use_calendar_rules() -> None:
    cal = TradingCalendar([dt.datetime(2024, 1, 1), dt.datetime(2024, 1, 31)])
    start, end = cal.trading_month_bounds("2024-01-15")
    assert start == dt.datetime(2024, 1, 2)
    assert end == dt.datetime(2024, 1, 30)
