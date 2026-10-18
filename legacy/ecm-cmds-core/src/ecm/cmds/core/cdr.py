import datetime as dt

import ecm.cmds.core.pyg as pyg
import pandas as pd
from ecm.cmds.core.ticker import as_active
from ecm.cmds.core.ticker import is_active_contract
from ecm.cmds.core.ticker import is_future_contract
from pandas.tseries.holiday import USFederalHolidayCalendar
from pandas.tseries.offsets import CustomBusinessDay
from pyg_mongo import mongo_table
from pytz import timezone


month_str2int = {
    "F": 1,
    "G": 2,
    "H": 3,
    "J": 4,
    "K": 5,
    "M": 6,
    "N": 7,
    "Q": 8,
    "U": 9,
    "V": 10,
    "X": 11,
    "Z": 12,
}


month_int2str = {v: k for k, v in month_str2int.items()}


def today():
    return dt.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)


def today_ldn():
    utc_date = dt.datetime.now().astimezone(timezone("Europe/London")).replace(hour=0, minute=0, second=0, microsecond=0)
    utc_date = utc_date.replace(tzinfo=None)
    return utc_date


def now_ldn():
    ldn_dt = dt.datetime.now().astimezone(timezone("Europe/London"))
    ldn_dt = ldn_dt.replace(tzinfo=None)
    return ldn_dt


def bday_adj(date, t, adj=None, holidays=None):
    """
    add/minus t days to base_date, adjust a non-business day to prev/following bussiness date

    :Parameters:
    ----------------
    date : datetime.
    t : int - number of days
    adj : None or p/f/m
        adjustment convention: 'prev/following/modified following'
    holidays: datetime list or datetimeindex

    :Returns:
    -------
    datetime
        nearby business day

    """
    if isinstance(holidays, pd.Series):
        holidays = pd.to_datetime(holidays.to_list())
    elif isinstance(holidays, pd.DataFrame) and holidays.shape[1] == 1:
        holidays = pd.to_datetime(holidays.iloc[:, 0].to_list())
    CBD = CustomBusinessDay(n=t, calendar=USFederalHolidayCalendar()) if holidays is None else CustomBusinessDay(n=t, holidays=holidays)
    CBD1 = CustomBusinessDay(n=t + 1, calendar=USFederalHolidayCalendar()) if holidays is None else CustomBusinessDay(n=t + 1, holidays=holidays)
    edate = date + CBD
    if (holidays is not None and edate in holidays) or (date + CBD == date + CBD1):
        bd = CustomBusinessDay(1, holidays=holidays)
        if adj in ["p", "prev", "previous", "b", "back"]:
            return edate - bd
        elif adj in ["f", "follow", "following", "forward", "next", "n", None]:
            return edate
    else:
        return edate


def cdr_codes():
    cursor = mongo_table(db="bbg", table="cal", url=pyg.url)
    return [cursor[x].code for x in range(len(cursor))]


class CDR(object):
    """
    Date manipulation based on bloomberg ticker
    """

    def __init__(self, active):
        """
        Return holidays of the exchange as list
        """
        if is_active_contract(active):
            self.code = pyg.get_data("contracts", active=active, item="ref")["CALENDAR_CODE"]
        elif is_future_contract(active):
            self.code = pyg.get_data("contracts", active=as_active(active), item="ref")["CALENDAR_CODE"]
        elif active in cdr_codes():
            self.code = active
        self.holidays = pd.to_datetime(pyg.get_data("cal", code=self.code)["holidays"])

    def is_bday(self, date):
        return date.weekday() not in [5, 6] and date not in self.holidays.values

    def bday_adj(self, date, t, adj=None):
        return bday_adj(date=date, t=t, adj=adj, holidays=self.holidays)

    def drange(self, t0, t1, adj=None):
        dts = pd.bdate_range(t0, t1)
        return [x for x in dts if x not in self.holidays.values]


def cdate2dt(t):
    """
    converts C# datetime object to datetime
    """
    return dt.datetime(t.Year, t.Month, t.Day, t.Hour, t.Minute, t.Second)


def getworkingdays(from_date, to_date):
    from_weekday = from_date.weekday()
    to_weekday = to_date.weekday()
    if from_weekday > 5:
        from_weekday = 0
    day_diff = to_weekday - from_weekday
    whole_weeks = ((to_date - from_date).days - day_diff) / 7
    workdays_in_whole_weeks = whole_weeks * 5
    beginning_end_correction = min(day_diff, 5) - (max(to_date.weekday() - 4, 0) % 5)
    working_days = workdays_in_whole_weeks + beginning_end_correction
    return working_days


def datetime_range(start, end, delta):
    current = start
    while current <= end:
        yield current
        current += delta


def next_month(m):
    if (m + 1) % 12 == 0:
        return 12
    else:
        return (m + 1) % 12


def last_month(m):
    if (m - 1) % 12 == 0:
        return 12
    else:
        return (m - 1) % 12


