import re

from ecm.cmds.core.utils import bbgcase

_majors = ["EUR", "USD"]
_eur = ["HUF", "SEK", "NOK", "PLN", "CZK"]
_reverse = ["EUR", "GBP", "NZD", "AUD"]
_reversed = ["USD" + ccy for ccy in _reverse]
_old = ["IRP", "PTE", "FRF", "NLG", "DEM", "ESP", "BEF", "ATS"]
_active = [
    "AED",
    "ARS",
    "AUD",
    "BRL",
    "CAD",
    "CHF",
    "CLP",
    "CNH",
    "CNY",
    "COP",
    "CZK",
    "DKK",
    "EUR",
    "GBP",
    "HKD",
    "HUF",
    "IDR",
    "ILS",
    "INR",
    "JPY",
    "KRW",
    "MXN",
    "MYR",
    "NOK",
    "NZD",
    "PEN",
    "PHP",
    "PLN",
    "RUB",
    "SAR",
    "SEK",
    "SGD",
    "THB",
    "TRY",
    "TWD",
    "VND",
    "ZAR",
    "USD",
]
_active_curncy = ["USD%s Curncy" % ccy for ccy in _active]
_all = _active + _old
_usd = list(set(_active) - set(_eur) - set(_reverse))  # quoted as USDxxx

_ccy = "(%s)" % ("|".join(_all))
_is_fx_ccy = re.compile("^%s$" % _ccy)
_is_fx_ced = re.compile("^%s/%s$" % (_ccy, _ccy))
_is_fx_pair = re.compile("^%s{2}$" % _ccy)
_is_fx_ccy_curncy = re.compile("^%s{1} Curncy$" % _ccy)
_is_fx_pair_curncy = re.compile("^%s{2} Curncy$" % _ccy)
PAIRS = ["EUR" + ccy for ccy in _eur] + [ccy + "USD" for ccy in _reverse] + ["USD" + ccy for ccy in _usd]


def is_fx_ced(ticker):
    """
    assert is_fx_ced('JPY/USD') and not is_fx_ced('ABC/USD')
    """
    return _is_fx_ced.search(ticker) is not None


def is_fx_pair(ticker):
    """
    assert is_fx_pair('JPYUSD') and not is_fx_pair('ABCUSD')
    """
    return _is_fx_pair.search(ticker) is not None


def is_fx_ccy_curncy(ticker):
    """
    assert is_fx_ccy_curncy('JPY Curncy') and not is_fx_ccy('ABC Curncy')
    """
    return _is_fx_ccy_curncy.search(ticker) is not None


def is_fx_ccy(ticker):
    """
    assert is_fx_ccy('JPY') and not is_fx_ccy('ABC')
    """
    return _is_fx_ccy.search(ticker) is not None


def is_fx_pair_curncy(ticker):
    return _is_fx_pair_curncy.search(ticker) is not None


def _is_fx(ticker):
    return is_fx_ced(ticker) or is_fx_pair(ticker) or is_fx_ccy_curncy(ticker) or is_fx_pair_curncy(ticker)


def is_fx(ticker):
    return _is_fx(ticker)


def _as_fx_pair(ticker):
    """
    assert as_fx_pair('usdjpy') =='USDJPY'
    assert as_fx_pair('jpy') =='USDJPY'
    assert as_fx_pair('aud') =='AUDUSD'
    assert as_fx_pair('aud curncy') =='AUDUSD'
    assert as_fx_pair('usd/aud') =='USDAUD'
    """
    ticker = bbgcase(ticker)
    if isinstance(ticker, dict):
        return {as_fx_pair(key): value for key, value in ticker.items()}
    if is_fx_ced(ticker):
        return ticker[:3] + ticker[-3:]
    elif is_fx_pair(ticker):
        return ticker
    elif is_fx_pair_curncy(ticker):
        return ticker[:6]
    elif is_fx_ccy_curncy(ticker) or is_fx_ccy(ticker):
        ccy = ticker[:3]
        if ccy in _reverse:
            return ccy + "USD"
        else:
            return "USD" + ccy
    else:
        raise ValueError("%s not an fx ticker" % ticker)


def as_fx_pair(ticker):
    """
    assert as_fx_pair('usdjpy') =='USDJPY'
    assert as_fx_pair('jpy') =='USDJPY'
    assert as_fx_pair('aud') =='AUDUSD'
    assert as_fx_pair('aud curncy') =='AUDUSD'
    assert as_fx_pair('usd/aud') =='USDAUD'
    """
    return _as_fx_pair(ticker)


def _as_fx_pair_curncy(ticker):
    return as_fx_pair(ticker) + " Curncy"


def as_fx_pair_curncy(ticker):
    return _as_fx_pair_curncy(ticker)
