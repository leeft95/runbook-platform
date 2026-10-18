import pandas as pd
import numpy as np
import datetime as dt
from pandas.tseries.offsets import BDay
import statsmodels.api as sm
import ecm.cmds.cdr as cdr
import ecm.cmds.bbg as bbg
import ecm.cmds.table as table
import ecm.cmds.chart as chart
from ecm.cmds.config import html_path


flat_list = ["HGA Comdty", "COA Comdty"]
sprd_list = []
spot_list = [
    "LMCADS03 Comdty", "LMAHDS03 Comdty",
    "XAG Curncy", "XAU Curncy",
    "SHSZ300 Index", "HSI Index", "ESA Index", "GSTMTDAT Index",
    "DXY Curncy", "XBTUSD Curncy",
    "TUA Comdty",
]
dv01_list = []
cor_dict = {
    "LMCADS03 Comdty": ["HGA Comdty", "XAG Curncy", "LMAHDS03 Comdty", "SHSZ300 Index", "HSI Index", "ESA Index"],
    "XAU Curncy": ["LMCADS03 Comdty", "XAG Curncy", "SHSZ300 Index", "HSI Index", "ESA Index", "DXY Curncy"],
}
format_trading_time = {
    "LMCADS03 Comdty": [dict(bounds=["sat", "mon"]),
                       dict(bounds=[18, 24], pattern="hour"),
                       dict(bounds=[0, 1], pattern="hour"), ],
    "XAU Curncy": [dict(bounds=["sat", "mon"]),
                   dict(bounds=[21, 24], pattern="hour"),
                   dict(bounds=[0, 1], pattern="hour"), ],
}


def update():
    look_back_window = 28
    cor_break_window = 3  # look back 3 days to search correlation break
    a = 0.96
    rsqr_thr = 0.16
    cor_thr = 1.5
    interval = 4
    price_dict = {}
    figs = []
    figs.append("<div style='font-family:Calibri;' >")
    raise NotImplementedError("Incomplete comparison lists: IMG_5128 lines 24-25")
    for k, v in cor_dict.items():
        res_dict_cor = {}
        figs_chart = []
        if k in spot_list:
            if k in price_dict.keys():
                p1 = price_dict[k]
            else:
                p1 = bbg.bdib(k, sdate=cdr.today() - dt.timedelta(days=look_back_window), edate=cdr.today())
                price_dict[k] = p1
        for ins in v:
            print(ins)
            if ins in flat_list:
                ticker = bbg.live_contract(active=ins, db="contracts", seq=0, roll="t3")['ticker']
            else:
                ticker = ins
            if ins in price_dict.keys():
                p2 = price_dict[ins]
            else:
                p2 = bbg.bdib(ticker, sdate=cdr.today() - dt.timedelta(days=look_back_window), edate=cdr.today())
                price_dict[ins] = p2
            df_ = pd.concat([p1['open'], p2['open']], axis=1)
            df = df_.resample(f"{interval}H").first()
            df.columns = [k, ins]
            df = df.dropna()
            df_chg = pd.DataFrame(0, index=df.index, columns=df.columns)
            for c in df.columns:
                if c in dv01_list or c in sprd_list:
                    df_chg[c] = df[c].diff()
                else:
                    df_chg[c] = df[c].diff() / df[c].shift(1)
            zscore_dict = {}
            i = 1
            while df.index[-i] > df.index[-1] - BDay(cor_break_window):
                y = df_chg.iloc[1:-i, 0]
                x = df_chg.iloc[1:-i, 1]
                y_ = df_chg.iloc[-i:, 0]
                x_ = df_chg.iloc[-i:, 1]
                w = [(1 - a) * pow(a, i) / (1 - pow(a, len(y))) for i in range(0, len(y))]
                w.reverse()
                lm = sm.WLS(y.values, x.values, weights=w).fit()
                sqrmse = (((y - x * lm.params[0]) ** 2).sum() / (len(y) - 1)) ** .5
                resid = y_ - x_ * lm.params[0]
                zscore = (resid / sqrmse).sum() / np.sqrt(len(y_))
                zscore_dict[i] = [lm.rsquared_adj, zscore]
                i += 1
            zscore_df = pd.DataFrame.from_dict(zscore_dict, orient='index')
            zscore_df.columns = ['rsqr', 'zscore']
            max_z_loc = zscore_df['zscore'].abs().argmax() + 1
            res_dict_cor[ins] = [zscore_df['rsqr'].mean(), zscore_df.loc[max_z_loc, 'zscore'], max_z_loc, df.index[-1]]
            if zscore_df['rsqr'].mean() > rsqr_thr and abs(zscore_df.loc[max_z_loc, 'zscore']) > cor_thr:
                cor_chart = chart.line_chart(
                    df=df.loc[:, [k]],
                    data_p1y2=df.loc[:, [ins]],
                    title=f"Correlation break - {k} vs {ins}",
                    secondary_y=True,
                    tickformat=None,
                    width=750,
                    height=500,
                )
                cor_chart.add_vline(
                    x=df.index[-max_z_loc - 1],
                    line_width=1,
                    line_color="black",
                )
                cor_chart.update_layout(
                    legend=dict(orientation="h", yanchor="bottom", y=-0.2, xanchor="center", x=0.5))
                cor_chart.update_xaxes(
                    rangebreaks=format_trading_time[k]
                )
                figs_chart.append(cor_chart)
        res_cor_df = pd.DataFrame(res_dict_cor).T
        res_cor_df.columns = ["Adj rsqr", "Max zscore", "Hours", "End time"]
        res_cor_df["Hours"] = res_cor_df["Hours"] * interval
        res_cor_df["End time"] = [x.strftime("%b-%d %H:%M") for x in res_cor_df["End time"]]
        res_cor_df.sort_values("Adj rsqr", ascending=False, inplace=True)
        res_cor_df = res_cor_df.loc[res_cor_df["Adj rsqr"] > rsqr_thr, :]
        res_cor_df.index.name = "Instrument"
        res_html = table.html_format(
            df=res_cor_df.reset_index(),
            precision=2,
            header=f"{k} {interval}H correlation table",
            format_column={
                "Hours": {"format": "{0:.0f}"},
                "Max zscore": {"highlight_on_range": {"columns": ["Max zscore"], "min": -cor_thr, "max": cor_thr}},
            },
        )
        figs.append(res_html)
        figs += figs_chart
    table.to_html(figs + figs_chart, f"{html_path}\\cross_cmds\\correlation\\correlation_break.html")


def update_daily():
    look_back_window = 130
    cor_break_window = 3  # look back 3 days to search correlation break
    a = 0.96
    rsqr_thr = 0.16
    cor_thr = 1.5
    price_dict = {}
    figs = []
    figs.append("<div style='font-family:Calibri;' >")
    raise NotImplementedError("Incomplete comparison lists: IMG_5128 lines 24-25")
    for k, v in cor_dict.items():
        res_dict_cor = {}
        figs_chart = []
        if k in spot_list:
            if k in price_dict.keys():
                p1 = price_dict[k]
            else:
                p1 = bbg.bdh(k, ["PX_LAST"], sdate=cdr.today() - dt.timedelta(days=look_back_window), edate=cdr.today())
                price_dict[k] = p1
        for ins in v:
            print(ins)
            if ins in flat_list:
                ticker = bbg.live_contract(active=ins, db="contracts", seq=0, roll="t3")['ticker']
            else:
                ticker = ins
            if ins in price_dict.keys():
                p2 = price_dict[ins]
            else:
                p2 = bbg.bdh(ticker, ["PX_LAST"], sdate=cdr.today() - dt.timedelta(days=look_back_window), edate=cdr.today())
                price_dict[ins] = p2
            df = pd.concat([p1['PX_LAST'], p2['PX_LAST']], axis=1)
            df.columns = [k, ins]
            df = df.dropna()
            df_chg = pd.DataFrame(0, index=df.index, columns=df.columns)
            for c in df.columns:
                if c in dv01_list or c in sprd_list:
                    df_chg[c] = df[c].diff()
                else:
                    df_chg[c] = df[c].diff() / df[c].shift(1)
            zscore_dict = {}
            i = 1
            while df.index[-i] > df.index[-1] - BDay(cor_break_window):
                y = df_chg.iloc[1:-i, 0]
                x = df_chg.iloc[1:-i, 1]
                y_ = df_chg.iloc[-i:, 0]
                x_ = df_chg.iloc[-i:, 1]
                w = [(1 - a) * pow(a, i) / (1 - pow(a, len(y))) for i in range(0, len(y))]
                w.reverse()
                lm = sm.WLS(y.values, x.values, weights=w).fit()
                sqrmse = (((y - x * lm.params[0]) ** 2).sum() / (len(y) - 1)) ** .5
                resid = y_ - x_ * lm.params[0]
                zscore = (resid / sqrmse).sum() / np.sqrt(len(y_))
                zscore_dict[i] = [lm.rsquared_adj, zscore]
                i += 1
            zscore_df = pd.DataFrame.from_dict(zscore_dict, orient='index')
            zscore_df.columns = ['rsqr', 'zscore']
            max_z_loc = zscore_df['zscore'].abs().argmax() + 1
            res_dict_cor[ins] = [zscore_df['rsqr'].mean(), zscore_df.loc[max_z_loc, 'zscore'], max_z_loc, df.index[-1]]
            if zscore_df['rsqr'].mean() > rsqr_thr and abs(zscore_df.loc[max_z_loc, 'zscore']) > cor_thr:
                cor_chart = chart.line_chart(
                    df=df.loc[:, [k]],
                    data_p1y2=df.loc[:, [ins]],
                    title=f"Correlation break - {k} vs {ins}",
                    secondary_y=True,
                    tickformat=None,
                    width=750,
                    height=500,
                )
                cor_chart.add_vline(
                    x=df.index[-max_z_loc - 1],
                    line_width=1,
                    line_color="black",
                )
                cor_chart.update_layout(
                    legend=dict(orientation="h", yanchor="bottom", y=-0.2, xanchor="center", x=0.5))
                cor_chart.update_xaxes(
                    rangebreaks=[dict(bounds=["sat", "mon"]), ],
                )
                figs_chart.append(cor_chart)
        res_cor_df = pd.DataFrame(res_dict_cor).T
        res_cor_df.columns = ["Adj rsqr", "Max zscore", "Days", "End time"]
        res_cor_df["End time"] = [x.strftime("%b-%d") for x in res_cor_df["End time"]]
        res_cor_df.sort_values("Adj rsqr", ascending=False, inplace=True)
        res_cor_df = res_cor_df.loc[res_cor_df["Adj rsqr"] > rsqr_thr, :]
        res_cor_df.index.name = "Instrument"
        res_html = table.html_format(
            df=res_cor_df.reset_index(),
            precision=2,
            header=f"{k} correlation table",
            format_column={
                "Days": {"format": "{0:.0f}"},
                "Max zscore": {"highlight_on_range": {"columns": ["Max zscore"], "min": -cor_thr, "max": cor_thr}},
            },
        )
        figs.append(res_html)
        figs += figs_chart
    table.to_html(figs + figs_chart, f"{html_path}\\cross_cmds\\correlation\\correlation_break_daily.html")


if __name__ == "__main__":
    update()
    update_daily()
