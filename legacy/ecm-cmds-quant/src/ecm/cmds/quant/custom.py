import datetime as dt
import math

import ecm.cmds.core.bbg as bbg
import ecm.cmds.core.chart as chart
import ecm.cmds.core.pyg as pyg
import ecm.cmds.core.table as table
import ecm.cmds.core.talib as talib
import ecm.cmds.core.ticker as tk
import ecm.cmds.vendor.data as dv
import ecm.cmds.vendor._kpler as kpler
import ecm.cmds.vendor._rvx as rvx
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from ecm.cmds.core.cdr import CDR
from ecm.cmds.core.cdr import today
from ecm.cmds.core.config import data_path
from ecm.cmds.core.config import root_path
from pandas.tseries.offsets import BDay
from plotly.subplots import make_subplots
from scipy import stats


def var_report(strategy=None, substrategy=None, start_date=None):
    if start_date is None:
        start_date = today() - dt.timedelta(days=92)
    if strategy is None and substrategy is None:
        var = rvx.total_var(level="strategy", start=start_date)
        pnl = rvx.total_pnl(level="strategy", start=start_date)
        pnl_rep = rvx.total_pnl(level="strategy", start=dt.datetime(2018, 1, 1))
        title = "Var for L025"
    elif strategy is not None and substrategy is None:
        var = rvx.var(strategy=strategy, level="strategy", start=start_date)
        pnl = rvx.pnl(strategy=strategy, level="strategy", start=start_date)
        pnl_rep = rvx.pnl(strategy=strategy, level="strategy", start=dt.datetime(2018, 1, 1))
        title = f"Var for {strategy}"
    elif strategy is None and substrategy is not None:
        print("Please choose strategy")
        raise
    else:
        var = rvx.var(strategy=strategy, level="substrategy", start=start_date)
        pnl = rvx.pnl(strategy=strategy, level="substrategy", start=start_date)
        pnl_rep = rvx.pnl(strategy=strategy, level="substrategy", start=dt.datetime(2018, 1, 1))
        if isinstance(substrategy, list):
            var = var[substrategy]
            pnl = pnl[substrategy]
            pnl_rep = pnl_rep[substrategy]
            title = f"Var for {strategy}-{','.join(substrategy)}"
        else:
            var = var[[substrategy]]
            pnl = pnl[[substrategy]]
            pnl_rep = pnl_rep[[substrategy]]
            title = f"Var for {strategy}-{substrategy}"
    var = var.sum(axis=1).to_frame("var")
    var["var 20d mean"] = var.iloc[:, 0].rolling(20).mean()
    pnl = pnl.sum(axis=1).to_frame("daily pnl")
    pnl_rep = pnl_rep.sum(axis=1).to_frame("daily pnl")
    cum_pnl = pnl_rep.iloc[:, 0].cumsum().to_frame("cum pnl").reindex(pnl.index)
    return chart.line_chart(
        df=var * -1,
        data_p1y2=cum_pnl,
        data_p2y1=pnl,
        y_axis_title="var",
        p1y2_axis_title="cum pnl",
        p2y1_axis_title="daily pnl",
        subplots=[0.7, 0.3],
        title=title,
        tickformat=None,
        secondary_y=True,
        highlight_dict={
            "var": {"color": "black"},
            "var mean": {"color": "red"},
            "cum pnl": {"color": "blue"},
            "daily pnl": {"mode": "bars", "color": "green"},
        },
    )


def oi_vwap_tracker(base_ticker, start_date=None, end_date=None, fp=None, sprd=None, asset_class="Comdty"):
    """
    Returns a table that shows change between start_date and end_date

    """
    if end_date is None:
        end_date = today()
    if start_date is None:
        start_date = today() - dt.timedelta(28)
    if fp is None:
        fp = ["1"]
    if sprd is None:
        sprd = ["1-2", "2-3"]
    fp_list = [f"{base_ticker}{x} {asset_class}" for x in fp]
    sprd_list = [f"S:{base_ticker}{base_ticker} {x} {asset_class}" for x in sprd]
    sprd_tickers = (bbg.bref(sprd_list, ["GENERIC_SPREAD_TICKER_EXTENSION"])).iloc[:, 0].to_list()
    raise NotImplementedError("Missing spread ticker expression: IMG_5459 line 97")

    fp_price_daily = bbg.bdh(fp_list, ["PX_LAST"], today() - dt.timedelta(364), today())
    sprd_price_daily = bbg.bdh(sprd_list, ["PX_LAST"], today() - dt.timedelta(364), today())

    fp_price_intraday = pd.DataFrame()
    sprd_price_intraday = pd.DataFrame()
    for x in fp_list:
        try:
            temp_df = (bbg.bdib(x, today() - dt.timedelta(7), today() + dt.timedelta(1), interval=10)["close"]).to_frame(x)
        except Exception:
            temp_df = pd.DataFrame(
                np.nan,
                index=[today() + dt.timedelta(hours=dt.datetime.now().hour - 1)],
                columns=[x],
            )
        fp_price_intraday = pd.concat([fp_price_intraday, temp_df], axis=1)
    for x in sprd_list:
        try:
            temp_df = (bbg.bdib(x, today() - dt.timedelta(7), today() + dt.timedelta(1), interval=10)["close"]).to_frame(x)
        except Exception:
            temp_df = pd.DataFrame(
                np.nan,
                index=[today() + dt.timedelta(hours=dt.datetime.now().hour - 1)],
                columns=[x],
            )
        sprd_price_intraday = pd.concat([sprd_price_intraday, temp_df], axis=1)

    fp_vwap = bbg.bref(
        fp_list,
        ["EQY_WEIGHTED_AVG_PX"],
        option=[
            ("VWAP_START_TIME", "00:00:00"),
            ("VWAP_END_TIME", "23:00:00"),
            ("VWAP_START_DT", f"{start_date.strftime('%Y%m%d')}"),
            ("VWAP_END_DT", f"{end_date.strftime('%Y%m%d')}"),
        ],
    )
    sprd_vwap = bbg.bref(
        sprd_list,
        ["EQY_WEIGHTED_AVG_PX"],
        option=[
            ("VWAP_START_TIME", "00:00:00"),
            ("VWAP_END_TIME", "23:00:00"),
            ("VWAP_START_DT", f"{start_date.strftime('%Y%m%d')}"),
            ("VWAP_END_DT", f"{end_date.strftime('%Y%m%d')}"),
        ],
    )
    fp_oi_chg = bbg.bref(
        fp_list,
        ["INTERVAL_NET_CHANGE"],
        option=[
            ("MARKET_DATA_OVERRIDE", "FUT_AGGTE_OPEN_INT"),
            ("START_DATE_OVERRIDE", f"{start_date.strftime('%Y%m%d')}"),
            ("END_DATE_OVERRIDE", f"{end_date.strftime('%Y%m%d')}"),
        ],
    )
    fp_tickers = bbg.bref(fp_list, ["FUT_CUR_GEN_TICKER"])

    fp_oi_chg_ = fp_oi_chg.iloc[:, 0]
    if isinstance(fp_oi_chg_.index, pd.MultiIndex):
        fp_oi_chg_.index = fp_oi_chg_.index[0]
    fp_vwap_ = fp_vwap.iloc[:, 0]
    if isinstance(fp_vwap_.index, pd.MultiIndex):
        fp_vwap_.index = fp_vwap_.index[0]
    fp_last = fp_price_daily.iloc[-1, :]
    try:
        fp_vs_vwap = fp_last / fp_vwap_ - 1
    except Exception:
        fp_vs_vwap = pd.Series(fp_last.values / fp_vwap_.values, index=fp_last.index)
    fp_price_daily_ = fp_price_daily.loc[(fp_price_daily.index >= start_date) & (fp_price_daily.index <= end_date)]
    if fp_price_daily_.empty:
        return f"No Data Available for {base_ticker} on {start_date} -> {end_date}"
    fp_chg = fp_price_daily_.iloc[-1, :] / fp_price_daily_.iloc[0, :] - 1
    fp_pct = [(fp_price_daily[_idx][-1] - np.min(x)) / (np.max(x) - np.min(x)) for _idx, x in fp_price_daily_.items()]
    fp_pct = pd.Series(fp_pct, index=fp_price_daily.columns)
    fp_days = fp_price_intraday.index.normalize().unique()
    fp_days = fp_days[fp_days.dayofweek != 5]
    fp_days = fp_days[fp_days.dayofweek != 6]
    fp_days = fp_days[-3]
    fp_price_intraday_chg = (fp_price_intraday.diff()).loc[fp_price_intraday.index >= fp_days, :]
    fp_sr3 = fp_price_intraday_chg.mean() / fp_price_intraday_chg.std() * np.sqrt(len(fp_price_intraday_chg))
    fp_price_daily_chg = fp_price_daily / fp_price_daily.shift(1) - 1
    fp_sr22 = fp_price_daily_chg.iloc[-22:, :].mean() / fp_price_daily_chg.iloc[-22:, :].std() * np.sqrt(22)
    fp_emva3 = fp_last - pd.concat(
        [
            pd.DataFrame(
                talib.mva(fp_price_daily.iloc[:, x].values, 3, type="e"),
                index=fp_price_daily.index,
                columns=[fp_price_daily.columns[x]],
            )
            for x in range(len(fp_price_daily.columns))
        ],
        axis=1,
    )
    fp_emva8 = fp_last - pd.concat(
        [
            pd.DataFrame(
                talib.mva(fp_price_daily.iloc[:, x].values, 8, type="e"),
                index=fp_price_daily.index,
                columns=[fp_price_daily.columns[x]],
            )
            for x in range(len(fp_price_daily.columns))
        ],
        axis=1,
    )
    fp_emva14 = fp_last - pd.concat(
        [
            pd.DataFrame(
                talib.mva(fp_price_daily.iloc[:, x].values, 14, type="e"),
                index=fp_price_daily.index,
                columns=[fp_price_daily.columns[x]],
            )
            for x in range(len(fp_price_daily.columns))
        ],
        axis=1,
    )
    fp_emva50 = fp_last - pd.concat(
        [
            pd.DataFrame(
                talib.mva(fp_price_daily.iloc[:, x].values, 50, type="e"),
                index=fp_price_daily.index,
                columns=[fp_price_daily.columns[x]],
            )
            for x in range(len(fp_price_daily.columns))
        ],
        axis=1,
    )
    fp_emva100 = fp_last - pd.concat(
        [
            pd.DataFrame(
                talib.mva(fp_price_daily.iloc[:, x].values, 100, type="e"),
                index=fp_price_daily.index,
                columns=[fp_price_daily.columns[x]],
            )
            for x in range(len(fp_price_daily.columns))
        ],
        axis=1,
    )
    if base_ticker in ["GC", "SI"]:
        fp_cta_ori = rvx.rvx(
            ticker=f"CTA LN4 CM PM {base_ticker}_COMDTY",
            field="SIGNAL",
            sdate=start_date,
            edate=end_date,
        )
    elif base_ticker in ["HG"]:
        fp_cta_ori = rvx.rvx(
            ticker=f"CTA LN4 CM IM {base_ticker}_COMDTY",
            field="SIGNAL",
            sdate=start_date,
            edate=end_date,
        )
    else:
        fp_cta_ori = rvx.rvx(
            ticker=f"CTA LN4 CM EN {base_ticker}_COMDTY",
            field="SIGNAL",
            sdate=start_date,
            edate=end_date,
        )
    if len(fp_cta_ori) > 0:
        fp_cta = pd.Series([fp_cta_ori.iloc[-1, 0]] * len(fp_price_daily.columns), index=fp_price_daily.columns)
        fp_cta_chg = pd.Series(
            [fp_cta_ori.iloc[-1, 0] - fp_cta_ori.iloc[0, 0]] * len(fp_price_daily.columns),
            index=fp_price_daily.columns,
        )
    else:
        fp_cta = pd.Series(np.nan, index=fp_last.index)
        fp_cta_chg = pd.Series(np.nan, index=fp_last.index)

    sprd_vwap_ = sprd_vwap.iloc[:, 0]
    if isinstance(sprd_vwap_.index, pd.MultiIndex):
        sprd_vwap_.index = sprd_vwap_.index[0]
    sprd_last = sprd_price_daily.iloc[-1, :]
    sprd_vs_vwap = sprd_last - sprd_vwap_
    sprd_price_daily_ = sprd_price_daily.loc[(sprd_price_daily.index >= start_date) & (sprd_price_daily.index <= end_date)]
    sprd_chg = sprd_price_daily_.iloc[-1, :] - sprd_price_daily_.iloc[0, :]
    sprd_pct = [(x[-1] - np.min(x)) / (np.max(x) - np.min(x)) for _idx, x in sprd_price_daily_.items()]
    sprd_pct = pd.Series(sprd_pct, index=sprd_price_daily.columns)
    sprd_days = sprd_price_intraday.index.normalize().unique()
    sprd_days = sprd_days[sprd_days.dayofweek != 5]
    sprd_days = sprd_days[sprd_days.dayofweek != 6]
    sprd_days = sprd_days[-3]
    sprd_price_intraday_chg = (sprd_price_intraday.diff()).loc[sprd_price_intraday.index >= sprd_days, :]
    sprd_sr3 = sprd_price_intraday_chg.mean() / sprd_price_intraday_chg.std() * np.sqrt(len(sprd_price_intraday_chg))
    sprd_price_daily_chg = sprd_price_daily.diff()
    sprd_sr22 = sprd_price_daily_chg.iloc[-22:, :].mean() / sprd_price_daily_chg.iloc[-22:, :].std() * np.sqrt(22)
    sprd_emva3 = sprd_last - pd.concat(
        [
            pd.DataFrame(
                talib.mva(sprd_price_daily.iloc[:, x].values, 3, type="e"),
                index=sprd_price_daily.index,
                columns=[sprd_price_daily.columns[x]],
            )
            for x in range(len(sprd_price_daily.columns))
        ],
        axis=1,
    )
    sprd_emva8 = sprd_last - pd.concat(
        [
            pd.DataFrame(
                talib.mva(sprd_price_daily.iloc[:, x].values, 8, type="e"),
                index=sprd_price_daily.index,
                columns=[sprd_price_daily.columns[x]],
            )
            for x in range(len(sprd_price_daily.columns))
        ],
        axis=1,
    )
    sprd_emva14 = sprd_last - pd.concat(
        [
            pd.DataFrame(
                talib.mva(sprd_price_daily.iloc[:, x].values, 14, type="e"),
                index=sprd_price_daily.index,
                columns=[sprd_price_daily.columns[x]],
            )
            for x in range(len(sprd_price_daily.columns))
        ],
        axis=1,
    )
    sprd_emva50 = sprd_last - pd.concat(
        [
            pd.DataFrame(
                talib.mva(sprd_price_daily.iloc[:, x].values, 50, type="e"),
                index=sprd_price_daily.index,
                columns=[sprd_price_daily.columns[x]],
            )
            for x in range(len(sprd_price_daily.columns))
        ],
        axis=1,
    )
    sprd_emva100 = sprd_last - pd.concat(
        [
            pd.DataFrame(
                talib.mva(sprd_price_daily.iloc[:, x].values, 100, type="e"),
                index=sprd_price_daily.index,
                columns=[sprd_price_daily.columns[x]],
            )
            for x in range(len(sprd_price_daily.columns))
        ],
        axis=1,
    )

    output = pd.concat(
        [
            fp_last,
            fp_last - fp_vwap_,
            fp_chg,
            fp_oi_chg_,
            fp_vwap_,
            fp_vs_vwap,
            fp_pct,
            fp_sr3,
            fp_sr22,
            fp_emva3.iloc[-1, :],
            fp_emva8.iloc[-1, :],
            fp_emva14.iloc[-1, :],
            fp_emva50.iloc[-1, :],
            fp_emva100.iloc[-1, :],
            fp_cta,
            fp_cta_chg,
        ],
        axis=1,
    )
    output.columns = [
        "Last Price", "diff", "Period Chg", "OI Chg", "VWAP", "% vs vwap",
        "Percentile", "3D Sharpe", "22D Sharpe", "vs 3D EMA", "vs 8D EMA",
        "vs 14D EMA", "vs 50D EMA", "vs 100D EMA", "CTA Signal", "CTA Chg",
    ]
    output = output.T
    if fp_tickers.shape[0] == 1:
        output.columns = [x if not pd.isnull(x) else fp_tickers.index[i][0].split(" ")[0] for i, x in enumerate(fp_tickers.iloc[:, 0])]
    else:
        output.columns = [x if not pd.isnull(x) else fp_tickers.index[i].split(" ")[0] for i, x in enumerate(fp_tickers.iloc[:, 0])]

    output_sprd = pd.concat(
        [
            sprd_last,
            sprd_last - sprd_vwap_,
            sprd_chg,
            sprd_vwap_,
            sprd_vs_vwap,
            sprd_pct,
            sprd_sr3,
            sprd_sr22,
            sprd_emva3.iloc[-1, :],
            sprd_emva8.iloc[-1, :],
            sprd_emva14.iloc[-1, :],
            sprd_emva50.iloc[-1, :],
            sprd_emva100.iloc[-1, :],
        ],
        axis=1,
    )
    output_sprd.columns = [
        "Last Price", "diff", "Period Chg", "VWAP", "% vs vwap", "Percentile",
        "3D Sharpe", "22D Sharpe", "vs 3D EMA", "vs 8D EMA", "vs 14D EMA",
        "vs 50D EMA", "vs 100D EMA",
    ]
    output_sprd = output_sprd.T
    output_sprd.columns = [tk.convert_spread_ticker(x).split(" ")[0] for x in sprd_price_daily.columns]

    output_combine = pd.concat([output, output_sprd], axis=1)
    output_combine.index.name = start_date.strftime("%Y-%m-%d")
    output_combine.reset_index(inplace=True)
    format_c = list(output_combine.columns[1:])
    format_c1 = list(output.columns)
    return table.html_format(
        df=output_combine,
        precision=2,
        hide_rows=[15],
        format_column={
            tuple(output_combine.columns): {"width": "80px", "text-align": "center"},
            tuple(output_combine.columns[1:]): {"highlight": [0, 1]},
            output_combine.columns[0]: {"right_border": True},
            format_c1[-1]: {"right_border": True},
        },
        format_row={
            2: {"format": "{:.2%}", "columns": format_c1, "bottom_border": True},
            3: {"format": "{:,.0f}", "columns": format_c},
            5: {"format": "{:.2%}", "columns": format_c1},
            6: {"format": "{:.0%}", "columns": format_c, "bottom_border": True},
            8: {"bottom_border": True},
            13: {"bottom_border": True},
        },
    )


class Trade(object):
    def __init__(self, contract, entry_date, direction, **kwargs):
        risk = kwargs.get("risk", 100000)
        method = kwargs.get("method", "fixed_sl_tp")
        ref_date = kwargs.get("ref_date", None)
        stop_price = kwargs.get("stop_price", None)
        entry_price = kwargs.get("entry_price", None)
        take_profit = kwargs.get("take_profit", None)
        self.contract = contract
        self.active = tk.contract2active(self.contract)
        if tk.is_future_contract(contract):
            self.ref = pyg.get_data("contracts", active=self.active, item="ref")
            self.fut_val_pt = float(self.ref["FUT_VAL_PT"])
            self.fut_tick_val = float(self.ref["FUT_TICK_VAL"])
            self.fut_tick_size = float(self.ref["FUT_TICK_SIZE"])
        else:
            self.fut_val_pt = 1.0
            self.fut_tick_size = 1.0
            self.fut_tick_val = 1.0
        if isinstance(entry_date, str):
            self.entry_date = dt.datetime.strptime(entry_date, "%Y%m%d")
        else:
            self.entry_date = entry_date
        if ref_date is not None:
            if isinstance(ref_date, str):
                self.ref_date = [dt.datetime.strptime(ref_date, "%Y%m%d"), dt.datetime.strptime(ref_date, "%Y%m%d")]
            elif isinstance(ref_date, dt.datetime):
                self.ref_date = [ref_date, ref_date]
            elif isinstance(ref_date, list) and len(ref_date) == 2:
                self.ref_date = [dt.datetime.strptime(ref_date[0], "%Y%m%d"), dt.datetime.strptime(ref_date[1], "%Y%m%d")]
        else:
            raise ValueError("Need ref date")
        if direction in [1, "BUY", "buy", "Buy", "B", "b"]:
            self.direction = 1
        elif direction in [-1, "SELL", "sell", "Sell", "S", "s"]:
            self.direction = -1
        self.risk = risk
        self.method = method
        self.price = self.get_price(ticker=contract, sdate=self.entry_date - dt.timedelta(182))
        if entry_price is None:
            self.entry_price = self.price.loc[self.entry_date, "PX_LAST"]
        else:
            self.entry_price = entry_price
        if stop_price is None:
            raise ValueError("Need stop price")
        else:
            self.stop_lvl = stop_price
        if take_profit is None:
            self.tp_lvl = self.entry_price + self.direction * abs(self.entry_price - stop_price) * 3
        else:
            self.tp_lvl = take_profit
        self.ref_high, self.ref_low, self.ref_vwap, self.ref_atr = self.get_ref_date_info()
        self.num_contracts = self.cal_size()
        func = getattr(self, method)
        self.df_signal = func(self.stop_lvl, self.tp_lvl)
        self.pnl = self.cal_pnl()
        self.exit_date = self.df_signal.loc[~np.isnan(self.df_signal["exit_signal"]), :].index[0]
        self.exit_price = self.df_signal.loc[~np.isnan(self.df_signal["exit_price"]), "exit_price"].values[0]

    @staticmethod
    def get_price(ticker, fields=None, sdate=None, edate=None):
        """
        get open/high/low/close/volume/oi for one contract
        """
        sdate = sdate or dt.datetime(2025, 1, 1)
        edate = edate or today()
        fields = fields or ["PX_OPEN", "PX_HIGH", "PX_LOW", "PX_LAST"]
        price = bbg.bdh(ticker, fields, sdate, edate)
        return price.loc[sdate:edate, :]

    def cal_stop(self, atr_thr=2, atr_window=30, reward_to_risk=2, **kwargs):
        ref_price = kwargs.get("ref_price", None)
        take_profit = kwargs.get("take_profit", None)
        if self.ref_date is None and ref_price is None:
            avg_tr = talib.atr(
                highp=self.price["PX_HIGH"].values,
                lowp=self.price["PX_LOW"].values,
                closep=self.price["PX_LAST"].values,
                window=atr_window,
            )
            avg_tr = pd.Series(avg_tr, index=self.price.index)
            if self.direction == 1:
                stop_lvl = self.entry_price - atr_thr * avg_tr.loc[self.entry_date]
                tp_lvl_1 = self.entry_price + atr_thr * avg_tr.loc[self.entry_date]
                if take_profit is not None:
                    tp_lvl = take_profit
                else:
                    tp_lvl = self.entry_price + reward_to_risk * atr_thr * avg_tr.loc[self.entry_date]
            elif self.direction == -1:
                stop_lvl = self.entry_price + atr_thr * avg_tr.loc[self.entry_date]
                tp_lvl_1 = self.entry_price - atr_thr * avg_tr.loc[self.entry_date]
                if take_profit is not None:
                    tp_lvl = take_profit
                else:
                    tp_lvl = self.entry_price - reward_to_risk * atr_thr * avg_tr.loc[self.entry_date]
        elif isinstance(ref_price, float) or isinstance(ref_price, int):
            stop_lvl = ref_price
            if self.direction == 1:
                if take_profit is not None:
                    tp_lvl = take_profit
                else:
                    tp_lvl = self.entry_price + np.abs(self.entry_price - stop_lvl) * reward_to_risk
                tp_lvl_1 = self.entry_price + np.abs(self.entry_price - stop_lvl)
            elif self.direction == -1:
                if take_profit is not None:
                    tp_lvl = take_profit
                else:
                    tp_lvl = self.entry_price - np.abs(self.entry_price - stop_lvl) * reward_to_risk
                tp_lvl_1 = self.entry_price - np.abs(self.entry_price - stop_lvl)
        elif self.ref_date is not None:
            p = bbg.bdh(
                self.contract,
                ["PX_OPEN", "PX_HIGH", "PX_LOW", "PX_LAST", "EQY_WEIGHTED_AVG_PX", "PX_VOLUME"],
                self.ref_date[0],
                self.ref_date[1],
            )
            p.dropna(inplace=True)
            if p.shape[0] == 1:
                if ref_price.lower() == "vwap":
                    if "EQY_WEIGHTED_AVG_PX" in p.columns:
                        stop_lvl = p["EQY_WEIGHTED_AVG_PX"].iloc[0]
                    else:
                        stop_lvl = p["PX_LAST"].iloc[0]
                elif ref_price.lower() in ["px_last", "last", "close", "settle"]:
                    stop_lvl = p["PX_LAST"].iloc[0]
                elif ref_price.lower() in ["px_high", "high"]:
                    stop_lvl = p["PX_HIGH"].iloc[0]
                elif ref_price.lower() in ["px_low", "low"]:
                    stop_lvl = p["PX_LOW"].iloc[0]
                elif ref_price.lower() in ["px_open", "open"]:
                    stop_lvl = p["PX_OPEN"].iloc[0]
                else:
                    stop_lvl = p[ref_price].iloc[0]
                if self.direction == 1:
                    if take_profit is not None:
                        tp_lvl = take_profit
                    else:
                        tp_lvl = self.entry_price + np.abs(self.entry_price - stop_lvl) * reward_to_risk
                    tp_lvl_1 = self.entry_price + np.abs(self.entry_price - stop_lvl)
                elif self.direction == -1:
                    if take_profit is not None:
                        tp_lvl = take_profit
                    else:
                        tp_lvl = self.entry_price - np.abs(self.entry_price - stop_lvl) * reward_to_risk
                    tp_lvl_1 = self.entry_price - np.abs(self.entry_price - stop_lvl)
            elif p.shape[0] > 1:
                if ref_price.lower() == "vwap":
                    if "EQY_WEIGHTED_AVG_PX" in p.columns:
                        stop_lvl = (p["EQY_WEIGHTED_AVG_PX"] * p["PX_VOLUME"] / p["PX_VOLUME"].sum()).sum()
                    else:
                        stop_lvl = (p["PX_LAST"] * p["PX_VOLUME"] / p["PX_VOLUME"].sum()).sum()
                elif ref_price.lower() in ["px_last", "last", "close", "settle"]:
                    stop_lvl = p["PX_LAST"].mean()
                elif ref_price.lower() in ["px_high", "high"]:
                    stop_lvl = p["PX_HIGH"].max()
                elif ref_price.lower() in ["px_low", "low"]:
                    stop_lvl = p["PX_LOW"].min()
                elif ref_price.lower() in ["px_open", "open"]:
                    stop_lvl = p["PX_OPEN"].mean()
                else:
                    stop_lvl = p[ref_price].iloc[0]
                if self.direction == 1:
                    if take_profit is not None:
                        tp_lvl = take_profit
                    else:
                        tp_lvl = self.entry_price + np.abs(self.entry_price - stop_lvl) * reward_to_risk
                    tp_lvl_1 = self.entry_price + np.abs(self.entry_price - stop_lvl)
                elif self.direction == -1:
                    if take_profit is not None:
                        tp_lvl = take_profit
                    else:
                        tp_lvl = self.entry_price - np.abs(self.entry_price - stop_lvl) * reward_to_risk
                    tp_lvl_1 = self.entry_price - np.abs(self.entry_price - stop_lvl)
        else:
            print("Add stop level")
            raise
        return stop_lvl, tp_lvl, tp_lvl_1

    def cal_size(self):
        loss_per_contract = np.abs(self.entry_price - self.stop_lvl) * self.fut_val_pt
        return self.risk / loss_per_contract

    def cal_pnl(self):
        self.df_signal["num_contracts"] = self.num_contracts
        price_ = self.price["PX_LAST"].copy()
        price_.loc[self.entry_date] = self.entry_price
        price_chg = price_.diff()
        pnl = self.num_contracts * self.fut_val_pt * np.sign(self.df_signal["trade"]) * price_chg.reindex(self.df_signal.index)
        return pnl

    def get_chart(self):
        sloc = self.price.index.get_loc(self.entry_date)
        eloc = self.price.index.get_loc(self.exit_date)
        sloc = np.max([0, sloc - 65])
        eloc = np.min([len(self.price), eloc + 65])
        data = self.price.iloc[sloc:eloc, :]
        fig = make_subplots()
        fig.add_trace(
            go.Candlestick(
                x=data.index,
                open=data["PX_OPEN"],
                high=data["PX_HIGH"],
                low=data["PX_LOW"],
                close=data["PX_LAST"],
                name="price",
            )
        )
        if self.direction == 1:
            entry_color = "green"
            exit_color = "red"
        elif self.direction == -1:
            entry_color = "red"
            exit_color = "green"
        fig.add_vline(
            x=self.entry_date,
            line_width=2,
            line_color=entry_color,
            label=dict(text="Entry", textposition="start"),
        )
        fig.add_vline(
            x=self.exit_date,
            line_width=2,
            line_color=exit_color,
            label=dict(text="Exit", textposition="start"),
        )
        fig.add_hline(
            y=self.stop_lvl,
            line_width=3,
            line_dash="dash",
            line_color="orange",
            label=dict(
                text="Stop",
                textposition="end",
                yanchor="top",
            ),
        )
        fig.add_hline(
            y=self.tp_lvl,
            line_width=3,
            line_dash="dash",
            line_color="blue",
            label=dict(
                text="Take profit",
                textposition="end",
                yanchor="top",
            ),
        )
        fig.add_hline(
            y=self.entry_price,
            line_width=3,
            line_dash="dash",
            line_color="black",
            label=dict(
                text="Entry price",
                textposition="end",
                yanchor="top",
            ),
        )
        fig.update_layout(
            title={
                "text": f"{self.contract} pnl: {'{:,.0f}'.format(self.pnl.sum())}",
                "x": 0.5,
                "xanchor": "center",
            },
            xaxis_rangeslider_visible=False,
            barmode="stack",
            width=750,
            height=500,
        )
        return fig

    def summary(self):
        df = pd.DataFrame(
            0,
            index=[0],
            columns=[
                "Contract",
                "Entry date",
                "Num contracts",
                "Px Entry",
                "Px Last",
                "Px Stop",
                "Px Take Profit",
                "Live pnl",
                "Stop pnl",
                "Take profit pnl",
                "Live risk reward",
                "Last date",
                "Holding Days",
            ],
        )
        df.loc[0, "Contract"] = self.contract
        df.loc[0, "Entry date"] = self.entry_date.strftime("%Y-%m-%d")
        df.loc[0, "Num contracts"] = self.num_contracts * self.direction
        df.loc[0, "Px Entry"] = self.entry_price
        df.loc[0, "Px Last"] = self.exit_price
        df.loc[0, "Px Stop"] = self.stop_lvl
        df.loc[0, "Px Take Profit"] = self.tp_lvl
        df.loc[0, "Live pnl"] = self.pnl.sum()
        df.loc[0, "Stop pnl"] = self.num_contracts * self.fut_val_pt * (self.stop_lvl - self.exit_price) * self.direction
        df.loc[0, "Take profit pnl"] = self.num_contracts * self.fut_val_pt * (self.tp_lvl - self.exit_price) * self.direction
        df.loc[0, "Live risk reward"] = abs(df.loc[0, "Take profit pnl"] / df.loc[0, "Stop pnl"])
        df.loc[0, "Last date"] = self.exit_date.strftime("%Y-%m-%d")
        df.loc[0, "Holding Days"] = len(pd.bdate_range(self.entry_date, self.exit_date)) - 1
        return df

    def save_trade(self, df, real=False):
        raise NotImplementedError("Missing real/simulated trade CSV destinations: IMG_5470 lines 772, 774")

    def create_order(self, order_type="TWAP", duration=10):
        if self.direction == 1:
            return (
                f"Please buy {'{:.0f}'.format(self.num_contracts)} "
                f"{self.contract} {order_type} in next {duration} mins. "
                f"Stop: {'{:.2f}'.format(self.stop_lvl)}, "
                f"target: {'{:.2f}'.format(self.tp_lvl)}, OCO, GTC"
            )
        elif self.direction == -1:
            return (
                f"Please sell {'{:.0f}'.format(self.num_contracts)} "
                f"{self.contract} {order_type} in next {duration} mins. "
                f"Stop: {'{:.2f}'.format(self.stop_lvl)}, "
                f"target: {'{:.2f}'.format(self.tp_lvl)}, OCO, GTC"
            )

    def fixed_sl_tp(self, stop_lvl, tp_lvl):
        df_signal = pd.DataFrame(
            np.nan,
            index=self.price.index,
            columns=[
                "entry_signal",
                "entry_price",
                "entry_price_under",
                "trade",
                "exit_signal",
                "exit_price",
                "exit_type",
            ],
        )
        sloc = self.price.index.get_loc(self.entry_date)
        df_signal.loc[self.entry_date, "entry_signal"] = self.direction
        df_signal.loc[self.entry_date, "entry_price"] = self.entry_price
        df_signal.loc[self.entry_date, "entry_price_under"] = self.entry_price
        in_trade = self.direction
        update_stop = 0
        for i in range(sloc, len(self.price)):
            if in_trade > 0 and self.price["PX_LAST"].iloc[i] < stop_lvl and not update_stop:
                df_signal.loc[df_signal.index[i], "exit_type"] = 1
                df_signal.loc[df_signal.index[i], "exit_signal"] = -in_trade
                df_signal.loc[df_signal.index[i], "trade"] = in_trade
                df_signal.loc[df_signal.index[i], "exit_price"] = self.price["PX_LAST"].iloc[i]
                in_trade = 0
            elif in_trade < 0 and self.price["PX_LAST"].iloc[i] > stop_lvl and not update_stop:
                df_signal.loc[df_signal.index[i], "exit_type"] = 1
                df_signal.loc[df_signal.index[i], "exit_signal"] = -in_trade
                df_signal.loc[df_signal.index[i], "trade"] = in_trade
                df_signal.loc[df_signal.index[i], "exit_price"] = self.price["PX_LAST"].iloc[i]
                in_trade = 0
            elif in_trade > 0 and self.price["PX_LAST"].iloc[i] > tp_lvl:
                df_signal.loc[df_signal.index[i], "exit_type"] = 3
                df_signal.loc[df_signal.index[i], "exit_signal"] = -in_trade
                df_signal.loc[df_signal.index[i], "trade"] = in_trade
                df_signal.loc[df_signal.index[i], "exit_price"] = self.price["PX_LAST"].iloc[i]
                in_trade = 0
            elif in_trade < 0 and self.price["PX_LAST"].iloc[i] < tp_lvl:
                df_signal.loc[df_signal.index[i], "exit_type"] = 3
                df_signal.loc[df_signal.index[i], "exit_signal"] = -in_trade
                df_signal.loc[df_signal.index[i], "trade"] = in_trade
                df_signal.loc[df_signal.index[i], "exit_price"] = self.price["PX_LAST"].iloc[i]
                in_trade = 0
            elif in_trade != 0:
                df_signal.loc[df_signal.index[i], "trade"] = in_trade
            if i == len(df_signal) - 1 and in_trade:
                df_signal.loc[df_signal.index[i], "exit_signal"] = -in_trade
                df_signal.loc[df_signal.index[i], "exit_price"] = self.price["PX_LAST"].iloc[i]
                df_signal.loc[df_signal.index[i], "exit_type"] = 0
                df_signal.loc[df_signal.index[i], "trade"] = in_trade
                in_trade = 0
        return df_signal

    def change_sl_tp(self, stop_lvl, tp_lvl, tp_lvl_1):
        df_signal = pd.DataFrame(
            np.nan,
            index=self.price.index,
            columns=[
                "entry_signal",
                "entry_price",
                "entry_price_under",
                "trade",
                "exit_signal",
                "exit_price",
                "exit_type",
            ],
        )
        sloc = self.price.index.get_loc(self.entry_date)
        df_signal.loc[self.entry_date, "entry_signal"] = self.direction
        df_signal.loc[self.entry_date, "entry_price"] = self.entry_price
        df_signal.loc[self.entry_date, "entry_price_under"] = self.entry_price
        in_trade = self.direction
        update_stop = 0
        for i in range(sloc, len(self.price)):
            if in_trade > 0 and self.price["PX_LAST"].iloc[i] < stop_lvl and not update_stop:
                df_signal.loc[df_signal.index[i], "exit_type"] = 1
                df_signal.loc[df_signal.index[i], "exit_signal"] = -in_trade
                df_signal.loc[df_signal.index[i], "trade"] = in_trade
                df_signal.loc[df_signal.index[i], "exit_price"] = self.price["PX_LAST"].iloc[i]
                in_trade = 0
                update_stop = 0
            elif in_trade < 0 and self.price["PX_LAST"].iloc[i] > stop_lvl and not update_stop:
                df_signal.loc[df_signal.index[i], "exit_type"] = 1
                df_signal.loc[df_signal.index[i], "exit_signal"] = -in_trade
                df_signal.loc[df_signal.index[i], "trade"] = in_trade
                df_signal.loc[df_signal.index[i], "exit_price"] = self.price["PX_LAST"].iloc[i]
                in_trade = 0
                update_stop = 0
            elif in_trade > 0 and self.price["PX_LAST"].iloc[i] < stop_lvl and update_stop:
                df_signal.loc[df_signal.index[i], "exit_type"] = 2
                df_signal.loc[df_signal.index[i], "exit_signal"] = -in_trade
                df_signal.loc[df_signal.index[i], "trade"] = in_trade
                df_signal.loc[df_signal.index[i], "exit_price"] = self.price["PX_LAST"].iloc[i]
                in_trade = 0
                update_stop = 0
            elif in_trade < 0 and self.price["PX_LAST"].iloc[i] > stop_lvl and update_stop:
                df_signal.loc[df_signal.index[i], "exit_type"] = 2
                df_signal.loc[df_signal.index[i], "exit_signal"] = -in_trade
                df_signal.loc[df_signal.index[i], "trade"] = in_trade
                df_signal.loc[df_signal.index[i], "exit_price"] = self.price["PX_LAST"].iloc[i]
                in_trade = 0
                update_stop = 0
            elif in_trade > 0 and self.price["PX_LAST"].iloc[i] > tp_lvl:
                df_signal.loc[df_signal.index[i], "exit_type"] = 3
                df_signal.loc[df_signal.index[i], "exit_signal"] = -in_trade
                df_signal.loc[df_signal.index[i], "trade"] = in_trade
                df_signal.loc[df_signal.index[i], "exit_price"] = self.price["PX_LAST"].iloc[i]
                in_trade = 0
                update_stop = 0
            elif in_trade < 0 and self.price["PX_LAST"].iloc[i] < tp_lvl:
                df_signal.loc[df_signal.index[i], "exit_type"] = 3
                df_signal.loc[df_signal.index[i], "exit_signal"] = -in_trade
                df_signal.loc[df_signal.index[i], "trade"] = in_trade
                df_signal.loc[df_signal.index[i], "exit_price"] = self.price["PX_LAST"].iloc[i]
                in_trade = 0
                update_stop = 0
            elif in_trade > 0 and self.price["PX_LAST"].iloc[i] > tp_lvl_1 and not update_stop:
                stop_lvl = self.entry_price
                df_signal.loc[df_signal.index[i], "trade"] = in_trade
                update_stop = 1
            elif in_trade < 0 and self.price["PX_LAST"].iloc[i] < tp_lvl_1 and not update_stop:
                stop_lvl = self.entry_price
                df_signal.loc[df_signal.index[i], "trade"] = in_trade
                update_stop = 1
            elif in_trade != 0:
                df_signal.loc[df_signal.index[i], "trade"] = in_trade
            if i == len(df_signal) - 1 and in_trade:
                df_signal.loc[df_signal.index[i], "exit_signal"] = -in_trade
                df_signal.loc[df_signal.index[i], "exit_price"] = self.price["PX_LAST"].iloc[i]
                df_signal.loc[df_signal.index[i], "exit_type"] = 0
                df_signal.loc[df_signal.index[i], "trade"] = in_trade
                in_trade = 0
        return df_signal

    def get_ref_date_info(self):
        p = bbg.bdh(
            self.contract,
            ["PX_OPEN", "PX_HIGH", "PX_LOW", "PX_LAST", "EQY_WEIGHTED_AVG_PX", "PX_VOLUME"],
            self.ref_date[0],
            self.ref_date[1],
        )
        p.dropna(inplace=True)
        if self.ref_date[0] == self.ref_date[1]:
            atr = p["PX_HIGH"] - p["PX_LOW"]
        else:
            raise NotImplementedError("Missing reference-period ATR calculation: IMG_5473/IMG_5474 lines 957-958")
        return [p["PX_HIGH"].max(), p["PX_LOW"].min(), p["EQY_WEIGHTED_AVG_PX"].iloc[-1], atr]


def season(active, spread=True, field="PX_LAST", method="change", entry_day=-1, exit_day=-1):
    """
    Calculate contract seasonality
    Entry and Exit are relative to expiry dates
    return html table
    """
    flat_m_list = ["F", "G", "H", "J", "K", "M", "N", "Q", "U", "V", "X", "Z"]
    sprd_m_list = [
        "F-G", "G-H", "H-J", "J-K", "K-M", "M-N", "N-Q", "Q-U", "U-V", "V-X", "X-Z", "Z-F",
    ]
    sdate = dt.datetime(2010, 1, 1)
    cd = CDR(active=active)
    if spread:
        contracts_ = pyg.get_data("spreads", active=active, item="sprd_chain")
        m_list = sprd_m_list
    else:
        contracts_ = pyg.get_data("contracts", active=active, item="fut_chain")
        m_list = flat_m_list
    contracts = contracts_.copy()
    raise NotImplementedError("Missing contract selection horizon: IMG_5474 line 992")
    if entry_day == -1:
        contracts["start_t"] = contracts["t1"].shift(1)
    elif entry_day == -2:
        contracts["start_t"] = contracts["t2"].shift(1)
    elif entry_day == -3:
        contracts["start_t"] = contracts["t3"].shift(1)
    elif entry_day == -4:
        contracts["start_t"] = contracts["t4"].shift(1)
    elif entry_day == -5:
        contracts["start_t"] = contracts["t5"].shift(1)
    elif entry_day == 0:
        contracts["start_t"] = contracts["last_t"].shift(1)
    else:
        contracts["start_t"] = contracts["last_t"].shift(1)
        if entry_day < 0:
            contracts["start_t"] = [cd.bday_adj(x["start_t"], entry_day, adj="p") for i, x in contracts.iterrows()]
        else:
            contracts["start_t"] = [cd.bday_adj(x["start_t"], entry_day, adj="f") for i, x in contracts.iterrows()]
    if exit_day == -1:
        contracts["end_t"] = contracts["t1"]
    elif exit_day == -2:
        contracts["end_t"] = contracts["t2"]
    elif exit_day == -3:
        contracts["end_t"] = contracts["t3"]
    elif exit_day == -4:
        contracts["end_t"] = contracts["t4"]
    elif exit_day == -5:
        contracts["end_t"] = contracts["t5"]
    elif exit_day == 0:
        contracts["end_t"] = contracts["last_t"]
    else:
        if exit_day < 0:
            contracts["end_t"] = [cd.bday_adj(x["last_t"], exit_day, adj="p") for i, x in contracts.iterrows()]
        else:
            print("Exit cannot be after expiry")
            raise
    season_df = pd.DataFrame(0, index=range(2010, today().year + 1), columns=m_list)
    for i in m_list:
        if "-" in i:
            same_month = contracts.loc[contracts["m"] == i[0], :]
        else:
            same_month = contracts.loc[contracts["m"] == i, :]
        all_price = pd.DataFrame()
        for _idx, row in same_month.iterrows():
            if row["start_t"] <= today():
                if row["end_t"] >= today():
                    price = bbg.bdh(row["ticker"], [field], row["start_t"], today())
                else:
                    if spread:
                        try:
                            price = pyg.get_data(
                                f"spreads_{field}",
                                active=active,
                                m=row["m"],
                                y=row["y"],
                                far_m=row["far_m"],
                                far_y=row["far_y"],
                            )
                        except Exception:
                            price1 = pyg.get_data(f"contracts_{field}", active=active, m=row["m"], y=row["y"])
                            price2 = pyg.get_data(f"contracts_{field}", active=active, m=row["far_m"], y=row["far_y"])
                            price = price1 - price2
                    else:
                        price = pyg.get_data(f"contracts_{field}", active=active, m=row["m"], y=row["y"])
                    price = price.loc[(price.index >= row["start_t"]) & (price.index <= row["end_t"])]
                if method.lower() in ["chg", "change"]:
                    if spread:
                        season_df.loc[row["y"], i] = price.iloc[-1, 0] - price.iloc[0, 0]
                    else:
                        try:
                            if method.lower() in ["chg", "change"]:
                                season_df.loc[row["y"], i] = (price.iloc[-1, 0] - price.iloc[0, 0]) / price.iloc[0, 0]
                        except Exception:
                            print("error")
                            raise
                elif method.lower() in ["high", "max"]:
                    season_df.loc[row["y"], i] = price.iloc[:, 0].max()
                elif method.lower() in ["low", "min"]:
                    season_df.loc[row["y"], i] = price.iloc[:, 0].min()
                elif method.lower() in ["mean", "average"]:
                    season_df.loc[row["y"], i] = price.iloc[:, 0].mean()
                elif method.lower() in ["last"]:
                    season_df.loc[row["y"], i] = price.iloc[-1, 0]
                all_price = pd.concat([all_price, price.reset_index(drop=True)], axis=1)
    season_df.index = season_df.index.map(str)
    season_df.loc["Mean ex last"] = season_df.iloc[:-1, :].mean(axis=0)
    pctl = pd.DataFrame(np.nan, index=["Last percentile"], columns=season_df.columns)
    for col in season_df.columns:
        pctl.loc["Last percentile", col] = stats.percentileofscore(season_df[col].iloc[:-2], season_df[col].iloc[-2]) / 100
    season_df = pd.concat([season_df, pctl], axis=0)
    season_df.index.name = "Year"
    season_df.reset_index(inplace=True)
    if spread:
        contract_type = "spread"
    else:
        contract_type = "outright"
    return table.html_format(
        df=season_df,
        header=f"{active} {contract_type} seasonality",
        precision=2,
        format_column={
            season_df.columns[0]: {"width": "100px", "text-align": "center", "bold": True},
            tuple(season_df.columns[1:]): {"width": "80px", "text-align": "center"},
        },
        format_row={
            len(season_df) - 3: {"bottom_border": True},
            len(season_df) - 2: {"bold": True},
            len(season_df) - 1: {"bold": True, "format": "{:.0%}", "columns": list(season_df.columns[1:])},
        },
    )


class Momentum(object):
    def __init__(self, contract, **kwargs):
        self.capital = kwargs.get("capital", 10000000)
        sdate = kwargs.get("sdate", "2024-08-01")
        pars = kwargs.get("pars", [8, 14, 30])
        stop_par = kwargs.get("stop_par", 14)
        adj_size = kwargs.get("adj_size", True)
        type = kwargs.get("type", "e")
        self.target_vol = 10
        if "-" in sdate:
            _sdate = dt.datetime.strptime(sdate, "%Y-%m-%d")
        elif "/" in sdate:
            _sdate = dt.datetime.strptime(sdate, "%d/%m/%Y")
        self.sdate = _sdate - BDay(30)
        self._sdate = _sdate
        self.contract = contract
        if tk.is_spread(contract):
            self.contract_under, _temp = tk.spread_to_flat(tk.convert_spread_ticker(contract, long_to_short=False))
        else:
            self.contract_under = contract
        self.active = tk.contract2active(self.contract_under)
        if tk.is_future_contract(self.contract_under):
            self.ref = pyg.get_data("contracts", active=self.active, item="ref")
            self.fut_val_pt = float(self.ref["FUT_VAL_PT"])
            self.fut_tick_val = float(self.ref["FUT_TICK_VAL"])
            self.fut_tick_size = float(self.ref["FUT_TICK_SIZE"])
        else:
            self.fut_val_pt = 1.0
            self.fut_tick_size = 1.0
            self.fut_tick_val = 1.0
        self.price = self.get_price(contract, sdate=self.sdate)
        self.price_under = self.get_price(self.contract_under, sdate=self.sdate)
        self.pars = pars
        self.signal, mv1, mv2, mv3, mvstp = self.mva(price=self.price, pars=self.pars, stop_par=stop_par, type=type, adj_size=adj_size)
        self.signal = (1 / (1 + math.e ** (-self.signal))) * 2 - 1
        if isinstance(self.pars, list) and len(self.pars) == 3:
            other_data = pd.concat([mv1, mv2, mv3], axis=1)
            other_data.columns = self.pars
        elif isinstance(self.pars, int):
            other_data = mv1.to_frame(self.pars)
        self.summary, self.df_signal = self.get_summary()
        self.df_signal["pnl"] = self.cal_pnl(adj_size=adj_size)
        self.pnl = self.df_signal["pnl"]
        self.chart = self.get_chart(other_data)
        if np.isnan(self.df_signal["trade"].iloc[-1]):
            self.direction = 0
        else:
            self.direction = np.sign(self.df_signal["trade"].iloc[-1])
        self.info = self.get_info(mv1, mv2, mv3, mvstp)
        if len(self.summary) > 0:
            self.summary["Contracts"] = 0
            self.summary["Pnl"] = 0
            for idx, row in self.summary.iterrows():
                if self.df_signal.index.get_loc(row["Entry date"]) == len(self.df_signal) - 1:
                    self.summary.loc[idx, "Contracts"] = self.df_signal["num_contracts"].iloc[self.df_signal.index.get_loc(row["Entry date"])]
                    self.summary.loc[idx, "Pnl"] = self.pnl.loc[row["Entry date"] : row["Exit date"]].sum()
                else:
                    raise NotImplementedError("Missing per-trade position/PnL offsets: IMG_5477 lines 1169-1170")
            self.summary["Entry date"] = self.summary["Entry date"].astype(str)
            self.summary["Exit date"] = self.summary["Exit date"].astype(str)
            last_row = self.summary.index[-1] + 1
            self.summary.loc[last_row, "Entry date"] = "Average"
            self.summary.loc[last_row, "Exit date"] = "-"
            self.summary.loc[last_row, "Direction"] = "-"
            self.summary.loc[last_row, "Entry price"] = self.summary["Entry price"].mean()
            self.summary.loc[last_row, "Exit price"] = self.summary["Exit price"].mean()
            self.summary.loc[last_row, "Contracts"] = self.summary["Contracts"].abs().mean()
            self.summary.loc[last_row, "Pnl"] = self.summary["Pnl"].mean()

    @staticmethod
    def get_price(ticker, fields=None, sdate=None, edate=None):
        """
        get open/high/low/close/volume/oi for one contract
        """
        sdate = sdate or dt.datetime(2010, 1, 1)
        edate = edate or today()
        fields = fields or ["PX_OPEN", "PX_HIGH", "PX_LOW", "PX_LAST"]
        price = bbg.bdh(ticker, fields, sdate, edate)
        return price.loc[sdate:edate, :]

    @staticmethod
    def mva(price, pars=None, stop_par=14, window=30, type="e", adj_size=False):
        if pars is None:
            pars = [8, 14, 30]
        signal_price_nona = (price["PX_HIGH"] + price["PX_LOW"] + price["PX_LAST"]) / 3
        signal_price_nona.dropna(inplace=True)
        if isinstance(pars, list) and len(pars) == 3:
            if len(signal_price_nona) > 40:
                mv1 = talib.mva(signal_price_nona.values, n=pars[0], type=type)
                mv1 = pd.Series(mv1, index=signal_price_nona.index)
                mv2 = talib.mva(signal_price_nona.values, n=pars[1], type=type)
                mv2 = pd.Series(mv2, index=signal_price_nona.index)
                mv3 = talib.mva(signal_price_nona.values, n=pars[2], type=type)
                mv3 = pd.Series(mv3, index=signal_price_nona.index)
                mvstp = talib.mva(signal_price_nona.values, n=stop_par, type=type)
                mvstp = pd.Series(mvstp, index=signal_price_nona.index)
                signal1 = (price["PX_LAST"] - mv1) / signal_price_nona.rolling(window).std()
                signal2 = (mv1 - mv2) / signal_price_nona.rolling(window).std()
                signal3 = (mv2 - mv3) / signal_price_nona.rolling(window).std()
                signal4 = (price["PX_LAST"] - mvstp) / signal_price_nona.rolling(window).std()
                signal = pd.Series(0.0, index=signal_price_nona.index)
                ls = 0
                if adj_size:
                    for i in range(1, len(signal)):
                        if signal1[i] > 0 and signal2[i] > 0 and signal3[i] > 0:
                            signal[i] = signal1[i] + signal2[i] + signal3[i]
                            ls = 1
                        elif signal4[i] > 0 and ls == 1:
                            signal[i] = max([0, signal1[i]]) + max([0, signal2[i]]) + max([0, signal3[i]])
                        elif signal1[i] < 0 and signal2[i] < 0 and signal3[i] < 0:
                            signal[i] = signal1[i] + signal2[i] + signal3[i]
                            ls = -1
                        elif signal4[i] < 0 and ls == -1:
                            signal[i] = min([0, signal1[i]]) + min([0, signal2[i]]) + min([0, signal3[i]])
                        else:
                            signal[i] = 0
                            ls = 0
                else:
                    for i in range(1, len(signal)):
                        if signal1[i] > 0 and signal2[i] > 0 and signal3[i] > 0:
                            signal[i] = 1
                            ls = 1
                        elif signal4[i] > 0 and ls == 1:
                            signal[i] = 1
                        elif signal1[i] < 0 and signal2[i] < 0 and signal3[i] < 0:
                            signal[i] = -1
                            ls = -1
                        elif signal4[i] < 0 and ls == -1:
                            signal[i] = -1
                        else:
                            signal[i] = 0
                            ls = 0
                signal = signal.reindex(price.index).fillna(method="ffill")
            else:
                print("Not enough data points!")
                signal = pd.Series(np.nan, index=price.index)
        elif isinstance(pars, int):
            mv1 = talib.mva(signal_price_nona.values, n=pars, type=type)
            mv1 = pd.Series(mv1, index=signal_price_nona.index)
            if adj_size:
                signal = (signal_price_nona - mv1) / signal_price_nona.rolling(pars).std()
            else:
                signal = pd.Series(0.0, index=signal_price_nona.index)
                signal[signal_price_nona >= mv1] = 1
                signal[signal_price_nona < mv1] = -1
            signal = signal.reindex(price.index).fillna(method="ffill")
            mv2 = pd.Series(0, signal.index)
            mv3 = pd.Series(0, signal.index)
            mvstp = pd.Series(0, signal.index)
        return signal, mv1, mv2, mv3, mvstp

    def get_summary(self, signal=None):
        if signal is None:
            signal = self.signal
        df_signal = pd.DataFrame(
            np.nan,
            index=signal.index,
            columns=[
                "entry_signal",
                "entry_price",
                "entry_price_under",
                "trade",
                "exit_signal",
                "exit_price",
                "exit_type",
            ],
        )
        trade_list = []
        in_trade = 0
        for idx, i in enumerate(signal):
            if i > 0 and in_trade == 0:
                entry_date = signal.index[idx]
                entry_price = self.price.loc[entry_date, "PX_LAST"]
                df_signal.loc[df_signal.index[idx], "entry_signal"] = 1
                df_signal.loc[df_signal.index[idx], "entry_price"] = entry_price
                df_signal.loc[df_signal.index[idx], "entry_price_under"] = self.price_under.loc[entry_date, "PX_LAST"]
                in_trade = 1
            elif i < 0 and in_trade == 0:
                entry_date = signal.index[idx]
                entry_price = self.price.loc[entry_date, "PX_LAST"]
                df_signal.loc[df_signal.index[idx], "entry_signal"] = -1
                df_signal.loc[df_signal.index[idx], "entry_price"] = entry_price
                df_signal.loc[df_signal.index[idx], "entry_price_under"] = self.price_under.loc[entry_date, "PX_LAST"]
                in_trade = -1
            elif i > 0 and in_trade < 0:
                exit_date = signal.index[idx]
                exit_price = self.price.loc[exit_date, "PX_LAST"]
                df_signal.loc[df_signal.index[idx], "trade"] = signal[signal.index[idx - 1]]
                df_signal.loc[df_signal.index[idx], "exit_signal"] = -in_trade
                df_signal.loc[df_signal.index[idx], "exit_price"] = exit_price
                df_signal.loc[df_signal.index[idx], "exit_type"] = 1
                trade_list.append([entry_date, entry_price, exit_date, exit_price, in_trade])
                entry_date = signal.index[idx]
                entry_price = self.price.loc[entry_date, "PX_LAST"]
                df_signal.loc[df_signal.index[idx], "entry_signal"] = 1
                df_signal.loc[df_signal.index[idx], "entry_price"] = entry_price
                df_signal.loc[df_signal.index[idx], "entry_price_under"] = self.price_under.loc[entry_date, "PX_LAST"]
                in_trade = 1
            elif i < 0 and in_trade > 0:
                exit_date = signal.index[idx]
                exit_price = self.price.loc[exit_date, "PX_LAST"]
                df_signal.loc[df_signal.index[idx], "trade"] = signal[signal.index[idx - 1]]
                df_signal.loc[df_signal.index[idx], "exit_signal"] = -in_trade
                df_signal.loc[df_signal.index[idx], "exit_price"] = exit_price
                df_signal.loc[df_signal.index[idx], "exit_type"] = 1
                trade_list.append([entry_date, entry_price, exit_date, exit_price, in_trade])
                entry_date = signal.index[idx]
                entry_price = self.price.loc[entry_date, "PX_LAST"]
                df_signal.loc[df_signal.index[idx], "entry_signal"] = -1
                df_signal.loc[df_signal.index[idx], "entry_price"] = entry_price
                df_signal.loc[df_signal.index[idx], "entry_price_under"] = self.price_under.loc[entry_date, "PX_LAST"]
                in_trade = -1
            elif i == 0 and in_trade:
                exit_date = signal.index[idx]
                exit_price = self.price.loc[exit_date, "PX_LAST"]
                df_signal.loc[df_signal.index[idx], "trade"] = signal[signal.index[idx - 1]]
                df_signal.loc[df_signal.index[idx], "exit_signal"] = -in_trade
                df_signal.loc[df_signal.index[idx], "exit_price"] = exit_price
                df_signal.loc[df_signal.index[idx], "exit_type"] = 1
                trade_list.append([entry_date, entry_price, exit_date, exit_price, in_trade])
                in_trade = 0
            elif in_trade:
                df_signal.loc[df_signal.index[idx], "trade"] = signal[signal.index[idx - 1]]
            if idx == len(signal) - 1 and in_trade:
                exit_date = signal.index[idx]
                exit_price = self.price.loc[exit_date, "PX_LAST"]
                df_signal.loc[df_signal.index[idx], "trade"] = signal[signal.index[idx]]
                df_signal.loc[df_signal.index[idx], "exit_signal"] = -in_trade
                df_signal.loc[df_signal.index[idx], "exit_price"] = exit_price
                df_signal.loc[df_signal.index[idx], "exit_type"] = 2
                trade_list.append([entry_date, entry_price, exit_date, exit_price, in_trade])
        return pd.DataFrame(trade_list, columns=["Entry date", "Entry price", "Exit date", "Exit price", "Direction"]), df_signal

    def get_chart(self, other_data):
        data = self.price
        fig = make_subplots(rows=3, cols=1, row_heights=[0.6, 0.2, 0.2])
        fig.add_trace(
            go.Candlestick(
                x=data.index,
                open=data["PX_OPEN"],
                high=data["PX_HIGH"],
                low=data["PX_LOW"],
                close=data["PX_LAST"],
                name="price",
            )
        )
        for col in other_data.columns:
            fig.add_trace(
                go.Scatter(
                    x=data.index,
                    y=other_data[col],
                    mode="lines",
                    name=col,
                )
            )
        fig.add_trace(
            go.Scatter(
                x=data.index,
                y=self.signal,
                mode="lines",
                name="signal",
            ),
            row=2,
            col=1,
        )
        fig.add_trace(
            go.Scatter(
                x=data.index,
                y=self.pnl.cumsum(),
                mode="lines",
                name="pnl",
            ),
            row=3,
            col=1,
        )
        for _idx, row in self.summary.iterrows():
            entry_date = row["Entry date"]
            exit_date = row["Exit date"]
            if row["Direction"] == 1:
                entry_color = "green"
                exit_color = "red"
                rgba = "rgba(0, 255, 0, 0.1)"
            elif row["Direction"] == -1:
                entry_color = "red"
                exit_color = "green"
                rgba = "rgba(255, 0, 0, 0.1)"
            fig.add_vline(
                x=entry_date,
                line_width=2,
                line_color=entry_color,
                row=1,
                col=1,
            )
            fig.add_vline(
                x=exit_date,
                line_width=2,
                line_color=exit_color,
                row=1,
                col=1,
            )
            raise NotImplementedError("Missing trade-rectangle chart arguments: IMG_5481 line 1429")
        fig.update_xaxes(
            rangebreaks=[
                dict(bounds=["sat", "mon"]),
            ]
        )
        fig.update_layout(
            title={
                "text": f"{self.contract}",
                "x": 0.5,
                "xanchor": "center",
            },
            xaxis_rangeslider_visible=False,
            barmode="stack",
            width=900,
            height=600,
        )
        return fig

    def cal_size(self, df_signal=None, adj_size=True):
        if df_signal is None:
            df_signal = self.df_signal
        price_chg = self.price["PX_LAST"].diff()
        price_under_chg = self.price_under["PX_LAST"].diff()
        price_chg_pct = 100 * price_under_chg / self.price_under["PX_LAST"].shift(1)
        price_chg_pct.fillna(value=0, inplace=True)
        real_vol = talib.realizedvol(price_chg_pct, rollwindow=20, annualize=260, decay_factor=0.94)
        real_vol.fillna(value=self.target_vol, inplace=True)
        if self.contract != self.contract_under:
            price_under_chg = self.price_under["PX_LAST"].diff()
            spread_vol = talib.realizedvol(price_chg, rollwindow=20, annualize=260, returnseries=True, decay_factor=0.94)
            spread_vol.fillna(method="bfill", inplace=True)
            price_vol = talib.realizedvol(price_under_chg, rollwindow=20, annualize=260, returnseries=True, decay_factor=0.94)
            price_vol.fillna(method="bfill", inplace=True)
            size_adj = self.capital * self.target_vol / real_vol * price_vol / spread_vol
        else:
            size_adj = self.capital * self.target_vol / real_vol
        if adj_size:
            raise NotImplementedError("Missing adjusted contract-sizing expression: IMG_5482 line 1467")
        else:
            raise NotImplementedError("Missing contract-sizing expression: IMG_5482 line 1469")
        return num_contracts.fillna(0).astype(int)

    def cal_pnl(self, df_signal=None, adj_size=True):
        if df_signal is None:
            df_signal = self.df_signal
        df_signal["num_contracts"] = self.cal_size(df_signal=df_signal, adj_size=adj_size)
        price_chg = self.price["PX_LAST"].diff()
        pnl = df_signal["num_contracts"] * self.fut_val_pt * price_chg.reindex(df_signal.index)
        return pnl.fillna(0)

    def create_order(self, order_type="TWAP", duration=10):
        if self.df_signal["trade"].iloc[-1] > 0:
            return (
                f"Please buy {'{:.0f}'.format(abs(self.df_signal['num_contracts'].iloc[-1]))} "
                f"{self.contract} {order_type} in next {duration} mins. "
            )
        elif self.df_signal["trade"].iloc[-1] < 0:
            return (
                f"Please sell {'{:.0f}'.format(abs(self.df_signal['num_contracts'].iloc[-1]))} "
                f"{self.contract} {order_type} in next {duration} mins. "
            )

    def get_info(self, mv1, mv2, mv3, mvstp, tp=None):
        px_last = self.price["PX_LAST"].iloc[-1]
        risk = abs(px_last - mvstp[-1])
        if tp is not None:
            tp_ = tp
            rr = abs(px_last - tp) / risk
        else:
            rr = 3
            if mvstp[-1] < px_last:
                tp_ = px_last + rr * risk
            elif mvstp[-1] > px_last:
                tp_ = px_last - rr * risk
        raise NotImplementedError("Missing information mapping fields: IMG_5483 line 1510")

    def optimization(self, par_list):
        par_str = [" ".join(str(y) for y in x) for x in par_list]
        df_out = pd.DataFrame(0, index=par_str, columns=["Pnl", "Sharpe Ratio", "Max Drawdown", "Calmar Ratio"])
        for idx, par in enumerate(par_list):
            signal, mv1, mv2, mv3 = self.mva(price=self.price, pars=par[:3], stop_par=par[-2], type=par[-1])
            summary, df_signal = self.get_summary(signal=signal)
            df_signal["pnl"] = self.cal_pnl(df_signal=df_signal)
            pnl = df_signal.loc[df_signal.index >= self.sdate, "pnl"]
            df_out.loc[par_str[idx], "Pnl"] = pnl.sum()
            df_out.loc[par_str[idx], "Sharpe Ratio"] = pnl.mean() / pnl.std() * np.sqrt(260)
            df_out.loc[par_str[idx], "Max Drawdown"] = (pnl.cumsum() - pnl.cummax()).min()
            df_out.loc[par_str[idx], "Calmar Ratio"] = np.abs(pnl.sum() / (pnl.cumsum() - pnl.cummax()).min())
        return df_out


class Oil(object):
    def __init__(self, country="India", sdate="2018-01-01"):
        self.country = country
        self.sdate = sdate
        self.folder = f"{root_path}\\outputs\\htmls\\oil\\analysis"

    def crude_imports(self, flow_direction="Export"):
        crude_imports_by_country = self.kpler_flow(country=self.country, direction="import", product="crude", split="origin", sdate=self.sdate, flow_direction=flow_direction)
        crude_imports_by_grade = self.kpler_flow(country=self.country, direction="import", product="crude", split="grade", sdate=self.sdate, flow_direction=flow_direction)
        return crude_imports_by_country, crude_imports_by_grade

    def crude_exports(self, flow_direction="Export"):
        crude_exports_by_country = self.kpler_flow(
            country=self.country,
            direction="export",
            product="crude",
            split="destination",
            sdate=self.sdate,
            flow_direction=flow_direction,
        )
        crude_exports_by_grade = self.kpler_flow(country=self.country, direction="export", product="crude", split="grade", sdate=self.sdate, flow_direction=flow_direction)
        return crude_exports_by_country, crude_exports_by_grade

    def product_imports(self, flow_direction="Export"):
        product_exports_by_country = self.kpler_flow(country=self.country, direction="import", product="products", split="origin", sdate=self.sdate, flow_direction=flow_direction)
        product_exports_by_grade = self.kpler_flow(
            country=self.country,
            direction="import",
            product="products",
            split="grade",
            sdate=self.sdate,
            flow_direction=flow_direction,
        )
        return product_exports_by_country, product_exports_by_grade

    def product_exports(self):
        product_exports_by_country = self.kpler_flow(
            country=self.country,
            direction="export",
            product="products",
            split="destination",
            sdate=self.sdate,
        )
        product_exports_by_grade = self.kpler_flow(
            country=self.country,
            direction="export",
            product="products",
            split="grade",
            sdate=self.sdate,
        )
        return product_exports_by_country, product_exports_by_grade

    @staticmethod
    def kpler_flow(country, **kwargs):
        """
        Use flowDirection=Export because it confirms faster than import
        Kpler classifies actual export flows based on the time a laden vessel departs the port.
        Imports, on the other hand, are recorded when a vessel completes its discharge at the disport - hen[photo clipped]
        Additionally, we classify future exports/imports based on the vessel's signal, predictive model or[photo clipped]
        """
        direction = kwargs.get("direction", "import")
        product = kwargs.get("product", "crude%2fco")
        split = kwargs.get("split", "Origin%20Countries")
        sdate = kwargs.get("sdate", "2018-01-01")
        flow_direction = kwargs.get("flow_direction", "Export")
        if " " in country:
            country_ = country.replace(" ", "%20")
        else:
            country_ = country
        if direction.lower() in ["import", "imports", "to"]:
            to_from = "to"
        elif direction.lower() in ["export", "exports", "from"]:
            to_from = "from"
        if product.lower() in ["clean%20products", "products", "clean", "product"]:
            product_ = "Clean%20Products"
        elif product.lower() in ["crude%2fco", "crude", "dirty"]:
            product_ = "crude%2fco"
        if split.lower() in ["origin%20countries", "origin countries", "origin"]:
            split_ = "Origin%20Countries"
        elif split.lower() in ["destination%20countries", "destination countries", "destination"]:
            split_ = "Destination%20Countries"
        elif split.lower() in ["grades", "grade"]:
            split_ = "Grades"
        elif split.lower() in ["origin%20ports", "origin ports"]:
            split_ = "Origin%20Ports"
        elif split.lower() in ["destination%20ports", "destination ports"]:
            split_ = "Destination%20Ports"
        else:
            split_ = split
        flows = dv.kpler(
            link=(
                f"/v1/flows?{to_from}Zones={country_}&products={product_}&flowDirection={flow_direction}&"
                f"split={split_}&granularity=daily&withForecast=true&onlyRealized=true&"
                f"startDate={sdate}&unit=kbd"
            )
        )
        flows = kpler.convert_to_ts(kpler_links=flows, end_dt="0d")
        flows["Total"] = flows.sum(axis=1)
        return flows

    def analysis(self, data, top=10, ma=10, name="Country"):
        if ma is not None:
            data_ = data.rolling(ma).mean()
        else:
            data_ = data.copy()
        if "Total" not in data_.columns:
            data_["Total"] = data_.sum(axis=1)
        top_n = data_.iloc[-1, :].sort_values(ascending=False)[: top + 1]
        if top_n.all() == 0:
            data_1 = data.mean()
            top_n = data_1.sort_values(ascending=False)[: top + 1]
        total = top_n["Total"]
        total_top_n = top_n.sum() - total
        top_n[f"Total top {str(top)}"] = total_top_n
        top_n = top_n.sort_values(ascending=False)
        top_n = top_n.to_frame(name)
        top_n["%"] = top_n / total
        return top_n

    def summary_table(self, data, top=8, name="Country", header="Crude imports", file_path=None):
        names = self.analysis(data, top=top, ma=20, name=name)
        top_data = data[names.drop(index=f"Total top {top}").index]
        if file_path is None:
            file_path = f"{self.folder}\\{self.country}_{name.replace('/', ' ')}.html"
        return self.table_format2_vs_month(data=top_data, table_head=name, header=header, file_path=file_path)

    def summary_chart(self, data, title, top=8, length=91):
        names = self.analysis(data, top=top, ma=10, name="temp")
        top_data = data[names.drop(index=f"Total top {top}").index].rolling(10).mean()
        return chart.line_chart(df=top_data.iloc[-length:, 1:], title=title, tickformat=None)

    @staticmethod
    def table_format2_vs_month(data, table_head, header, file_path, ma=10, format_row=None):
        if ma is not None:
            data_ = data.rolling(ma).mean()
        else:
            data_ = data.copy()
        figs = []
        for i in data_.columns:
            raise NotImplementedError("Missing seasonal-chart arguments: IMG_5485 line 1666")
        table.figures_to_html(figs, file_path)
        chart_link = f'<a href="{file_path}">{table_head}</a>'
        raise NotImplementedError("Missing monthly-table arguments: IMG_5485 line 1670")
        html_tb = Oil._html_format(df=tb, header=header, format_row=format_row)
        return html_tb.replace(table_head, chart_link)

    @staticmethod
    def _html_format(df, header, format_row=None):
        if format_row is None:
            format_row = {}
        return table.html_format(
            df=df,
            header=header,
            footer=None,
            show_date=False,
            format_column={
                "0": {"width": "120px", "text-align": "left"},
                "1": {"width": "80px", "text-align": "center", "highlight_z": [1, "_mean", "_std"]},
                "2": {"width": "80px", "text-align": "center", "highlight_z": [2, "_mean1", "_std1"]},
                "3": {"width": "80px", "text-align": "center"},
                "4": {"width": "80px", "text-align": "center"},
                "5": {"width": "80px", "text-align": "center"},
                "6": {"width": "80px", "text-align": "center"},
                "7": {"width": "80px", "text-align": "center"},
                "8": {"width": "80px", "text-align": "center"},
                "9": {"width": "80px", "text-align": "center"},
            },
            format_row=format_row,
            precision=0,
            hide_cols=["_last_update", "_mean", "_std", "_mean1", "_std1"],
        )


if __name__ == "__main__":
    raise NotImplementedError("Missing example Momentum arguments: IMG_5486 line 1727")
    trade.create_order()
    res = trade.summary
