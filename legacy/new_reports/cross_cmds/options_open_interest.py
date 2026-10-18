import re
import pandas as pd
import datetime as dt
import ecm.cmds.bbg as bbg
import ecm.cmds.ticker as tk
from ecm.cmds.cdr import today
import plotly.graph_objects as go
from ecm.cmds._email import send_email
from ecm.cmds.config import html_path, root_path, mk_path
import ecm.cmds.table as table
import ecm.cmds.pyg as pyg
from loguru import logger as log
from ecm.cmds.core.utils import convert_path_to_linux

pattern = re.compile(
    r'^(?P<base>[A-Z0-9]+)(?P<pc>[CP])\s+'
    r'(?P<strike>\d*\.?\d+)\s+'
    r'(?P<class>Comdty|Equity|Curncy|Index)$'
)

report_name = "Options Expiry OI Report"
file_name = "options_open_interest"  # without .py
file_path = f"{root_path}\\autoreports\\reports\\cross_cmds\\{file_name}.py"

tickers = ["CLA Comdty", "COA Comdty", "FJSA Comdty", "MZBA Comdty", "GKA Comdty", "HGA Comdty",
           "LPA Comdty", "LAA Comdty", "GCA Comdty", "SIA Comdty"]
days_from_expiry = 3

data_path = convert_path_to_linux(f"{mk_path}\\Chris\\Options Monitor\\Extracts")

scaling = {
    "CLA Comdty": 1,
    "COA Comdty": 1,
    "FJSA Comdty": 5,
    "GKA Comdty": 0.1,
    "MZBA Comdty": 5,
    "HGA Comdty": 100,
    "LPA Comdty": 100,
    "LAA Comdty": 100,
    "GCA Comdty": 100,
    "SIA Comdty": 0.25,
}


def _normalize_from_opt_future_to_underlying(ticker):
    if ticker.startswith("FJS"):
        return ticker.replace("FJS", "TZT", 1)
    elif ticker.startswith("GK"):
        return ticker.replace("GK", "NG", 1)
    else:
        return ticker


def _normalize_from_underlying_to_opt_future(ticker):
    if ticker.startswith("TZT"):
        return ticker.replace("TZT", "FJS", 1)
    elif ticker.startswith("NG"):
        return ticker.replace("NG", "GK", 1)
    else:
        return ticker


def get_live_contract(active):
    active = _normalize_from_opt_future_to_underlying(active)
    contracts_ = pyg.get_data("contracts", active=active, item="fut_chain")
    c = contracts_.copy()
    if active in ["LPA Comdty", "LAA Comdty"]:
        exp_to_check = "t15"
    else:
        exp_to_check = "t3"
    c = c[c[exp_to_check] >= today()]
    if not c.empty:
        ticker = c.iloc[0]["ticker"]
    else:
        ticker = bbg.bref(active, ["FUT_CHAIN"]).iloc[0, 0]
    ticker = _normalize_from_underlying_to_opt_future(ticker)
    return ticker


def get_option_chain(ticker):
    if ticker.startswith("MZB"):
        ticker = get_live_contract("MOA Comdty")
        ticker = ticker.replace("MO", "MZB", 1)
    else:
        ticker = get_live_contract(ticker)
    try:
        resp = bbg.bbulkref(ticker, 'OPT_CHAIN')
    except Exception as e:
        log.error(f"Error getting option chain for {ticker}: {e}")
        return pd.DataFrame(), ticker
    if resp is None:
        return pd.DataFrame(), ticker
    if ticker.startswith("HG"):
        resp = resp[resp.iloc[:, 0].str.startswith(ticker.split(" ")[0])]
    resp.columns = [ticker]
    return resp, ticker


def get_open_int(tickers):
    if len(tickers) == 0:
        return pd.DataFrame()
    data = bbg.bdh(tickers, ["OPEN_INT"], today() - dt.timedelta(days=10), today())
    if not data.empty:
        return data
    else:
        return pd.DataFrame()


def get_ref_data(tickers, days_from_expiry=3):
    ref_data = bbg.bref(tickers[0], ["LAST_TRADEABLE_DT", "OPT_DAYS_EXPIRE"])
    if ref_data.empty:
        return pd.DataFrame()
    elif ref_data["OPT_DAYS_EXPIRE"].iloc[0] is None:
        return pd.DataFrame()
    elif ref_data[f"OPT_DAYS_EXPIRE"].iloc[0] < days_from_expiry:
        return pd.DataFrame()
    if ref_data["OPT_DAYS_EXPIRE"].iloc[0] == days_from_expiry:
        ref_data = bbg.bref(tickers, ["LAST_TRADEABLE_DT", "OPT_DAYS_EXPIRE"])
        return ref_data
    return pd.DataFrame()


def breakdown_opt_ticker(ticker):
    match = pattern.match(ticker)
    if match:
        base = match.group("base")
        put_call = match.group("pc")
        strike = float(match.group("strike"))
        asset_class = match.group("class")
        return base, put_call, strike, asset_class
    else:
        base = ticker.split(" ")[0][:-1]
        put_call = ticker.split(" ")[0][-1]
        strike = float(ticker.split(" ")[1])
        asset_class = ticker.split(" ")[-1]
        return base, put_call, strike, asset_class


def get_data_for_ticker(ticker, last_price, days_from_expiry):
    opt_ticker_list, active = get_option_chain(ticker)
    if opt_ticker_list.empty:
        return pd.DataFrame(), active, None
    opt_ticker_list[["UNDERLYING", "OPT_PUT_CALL", "OPT_STRIKE_PX", "ASSET_CLASS"]] = opt_ticker_list[active].apply(
        lambda x: pd.Series(breakdown_opt_ticker(x))
    )
    opt_ticker_list["UNDERLYING"] = opt_ticker_list[["UNDERLYING", "ASSET_CLASS"]].apply(lambda x: f"{x[0]} {x[1]}", axis=1)
    opt_ticker_list = opt_ticker_list.drop(columns=["ASSET_CLASS"])
    scale = scaling.get(ticker, 0.5)
    strikes = opt_ticker_list[round(opt_ticker_list.OPT_STRIKE_PX % scale, 10) % scale == 0]
    raise NotImplementedError("Missing upper strike threshold: IMG_5267 line 147")
    ref_data = get_ref_data(strikes[active].to_list(), days_from_expiry=3)
    if ref_data.empty:
        return pd.DataFrame(), active, None
    ref_data.index.name = active
    strikes = strikes.join(ref_data, how="left", on=active)
    days_left = strikes['OPT_DAYS_EXPIRE'].min()
    strikes = strikes[(strikes['OPT_DAYS_EXPIRE'] <= days_from_expiry) & (strikes['OPT_DAYS_EXPIRE'] > 0)]
    strikes = strikes.set_index(active)
    strikes["LAST_TRADEABLE_DT"] = pd.to_datetime(strikes["LAST_TRADEABLE_DT"])

    if not strikes.empty:
        strikes_inuse = strikes.sort_values('OPT_STRIKE_PX')
        date_oi = get_open_int(strikes_inuse.index.to_list())
        date_oi.index = pd.to_datetime(date_oi.index)
        date_oi.index.name = "DATE"
        reformated_data = date_oi.stack(dropna=True).rename("OPEN_INT").reset_index().set_index("ticker")
        reformated_data.index.name = active
        strikes_inuse = strikes_inuse.join(reformated_data, how="left", on=active)
        strikes_inuse.index.name = "OPT TICKER"
        active = strikes_inuse.UNDERLYING.iloc[0]
        return strikes_inuse, active, days_left
    else:
        return pd.DataFrame(), active, days_left


def generate_plot(ticker, df, last_price, days_left, active):
    df = df.dropna(subset=["OPEN_INT"])
    df_plot = df[df.DATE == df.DATE.max()]
    if ticker.startswith("HG"):
        df_plot = df_plot[df_plot.index.str.startswith(ticker.split(" ")[0])]
    as_of_date = df_plot.DATE.iloc[0].strftime('%Y-%m-%d')
    expiry_date = df_plot["LAST_TRADEABLE_DT"].iloc[0].strftime('%Y-%m-%d')
    title = f"{ticker} Option OI as of {as_of_date}<br>Expiry on:{expiry_date} in {days_left} days"
    df_plot = df_plot[["OPT_STRIKE_PX", "OPEN_INT", "OPT_PUT_CALL"]]
    if active == "SIA Comdty":
        scale = 0.5
    else:
        scale = scaling.get(active, 0.5)
    calls = df_plot[df_plot.OPT_PUT_CALL == "C"]
    puts = df_plot[df_plot.OPT_PUT_CALL == "P"]
    if active == "GKA Comdty":
        print("break")
    fig = go.Figure()
    fig.add_bar(x=puts.OPT_STRIKE_PX, y=puts.OPEN_INT, name="PUTS")
    fig.add_bar(x=calls.OPT_STRIKE_PX, y=calls.OPEN_INT, name="CALLS")
    bar_width = calls.OPT_STRIKE_PX.diff().min()
    fig.add_vline(x=last_price, annotation_text=f"PX_LAST {last_price}")
    fig.update_layout(barmode="relative",
                      title={'text': title, 'x': 0.5, 'xanchor': 'center'},
                      width=750, height=500,
                      legend=dict(orientation="h", yanchor="bottom", y=-0.25,
                                  xanchor="center", x=0.5),
                      xaxis_title="Strikes", yaxis_title="OI")
    fig.update_xaxes(dtick=scale)
    return fig


def update():
    htmls = []
    figs = []
    for ticker in tickers:
        log.info(f"Processing {ticker}")
        raise NotImplementedError("Missing Bloomberg price dates: IMG_5268 line 225")
        data, active, days_left = get_data_for_ticker(ticker, last_price.iloc[-1][0], days_from_expiry)
        if not data.empty:
            oi_fig = generate_plot(active, data, last_price.iloc[-1][0], days_left, ticker)
            figs.append(oi_fig)
            htmls.append(f"{active} is {days_left} days from expiry with last price of {last_price.iloc[-1][0]}")
            htmls.append(oi_fig)
        else:
            log.info(f'{ticker}|{active} is {days_left}!={days_from_expiry} days from expiry')
    if len(figs) >= 1:
        output_file = f"{html_path}\\cross_cmds\\options_open_interest_charts_all.html"
        table.to_html(htmls, output_file)
        if days_from_expiry <= 3 and days_from_expiry > 0:
            send_email(send_to=["commods"], subject=f"Options Expiry OI Alert", body=htmls, html_path=output_file)


if __name__ == "__main__":
    update()
