import pandas as pd
import numpy as np
import datetime as dt
import statsmodels.api as sm
import matplotlib.pyplot as plt
import ecm.cmds.pyg as pyg
import ecm.cmds.bbg as bbg
from ecm.cmds.config import output_path


base_path = f"{output_path}\\csvs\\cross_cmds\\market_scan"

start_date = pd.to_datetime("2008-01-01")


def get_futures_price(active, fields=['PX_LAST'], seq=0):
    df = pd.DataFrame()
    df_adj = pd.DataFrame()
    for i in fields:
        p1 = pyg.get_data('contracts', active=active, item=f'{i}_gen')[seq]
        p2 = pyg.get_data('contracts', active=active, item=f'{i}_roll')[seq]
    p1 = p1.to_frame(i.upper())
    p2 = p2.to_frame(i.upper())
    df = pd.concat([df, p1], axis=1)
    df = df[df.index >= start_date]
    df_adj = pd.concat([df_adj, p2], axis=1)
    df_adj = df_adj[df_adj.index >= start_date]

    return df, df_adj


def get_spot_price(active, fields=['PX_LAST'], seq=0):
    actv = active.split(" ")
    if actv[0].startswith("LM"):
        ticker = f"{actv[0]} LME {actv[1]}"
    elif actv[-1] == "Curncy":
        ticker = f"{actv[0]} BGN {actv[-1]}"
    else:
        ticker = active
    df = pd.DataFrame()
    for i in fields:
        p1 = pyg.get_data('spot', ticker=ticker, field=i)
    df = pd.concat([df, p1], axis=1)
    df = df[df.index >= start_date]

    return df


def cal_ret_futures(active, period="M"):
    price_gen, price_adj = get_futures_price(active=active, fields=["PX_LAST"])
    price_chg = price_adj.diff() / price_gen.shift(1)
    price_gen_m = price_gen.resample(period).last()
    price_adj_m = price_adj.resample(period).last()
    price_std_m = price_chg.resample(period).std()
    price_days_m = price_chg.resample(period).count()
    month_return = price_adj_m.diff() / price_gen_m.shift(1)
    month_zscore = month_return / (price_std_m * np.sqrt(price_days_m))
    return month_return, month_zscore


def cal_ret_spot(active, period="M"):
    price_gen = get_spot_price(active=active, fields=["PX_LAST"])
    price_chg = price_gen.diff() / price_gen.shift(1)
    price_gen_m = price_gen.resample(period).last()
    price_std_m = price_chg.resample(period).std()
    price_days_m = price_chg.resample(period).count()
    month_return = price_gen_m.diff() / price_gen_m.shift(1)
    month_zscore = month_return / (price_std_m * np.sqrt(price_days_m))
    return month_return, month_zscore


def auto_correl_t(data):
    model = sm.tsa.arima.ARIMA(data.dropna(), order=(1, 0, 0))
    res = model.fit()
    return (res.params / res.bse)[1]


def get_stats(active, offset, start_date, typ="Futures", mode="M"):
    if typ == "Futures":
        df, df_adj = get_futures_price(active=active, start_date=start_date)
    else:
        df, df_adj = get_spot_price(active=active, start_date=start_date)
    df_adj_samples = df_adj.resample(mode)
    stats_list = []
    for idx, sample in df_adj_samples:
        period_px = sample.loc[:idx - dt.timedelta(days=offset)].ffill().bfill()
        if period_px.empty:
            continue
        period_px_chng = period_px.diff() / period_px.shift(1)
        period_ret = (period_px.iloc[-1] - period_px.iloc[0]) / period_px.iloc[0]
        period_std = period_px_chng.std()
        period_z_score = period_ret / (period_std * np.sqrt(len(period_px)))
        result = dict(date=idx, period_return=period_ret[0], period_z_score=period_z_score[0])
        stats_list.append(result)

    stats = pd.DataFrame(stats_list).set_index("date")
    return stats.period_return, stats.period_z_score


def update():
    base_file = pd.read_excel(f"{base_path}\\EOM-EOQ.Rebal.xlsx")
    base_file = base_file.set_index("Ticker")
    results_dict = dict()
    for active in base_file.index:
        print(active)
        typ = bbg.bref(active, "SECURITY_TYP2")["SECURITY_TYP2"][0]
        if typ in ['Future']:
            month_return, month_zscore = cal_ret_futures(active=active, period="M")
            quarter_return, quarter_zscore = cal_ret_futures(active=active, period="Q")
        else:
            month_return, month_zscore = cal_ret_spot(active=active, period="M")
            quarter_return, quarter_zscore = cal_ret_spot(active=active, period="Q")
        m_ret_pct = month_return.dropna() * 100
        m_ret_pct = m_ret_pct.T
        m_ret_pct.columns = [x.strftime("%Y-%m") for x in m_ret_pct.columns]
        m_ret_pct.index = ['Return %']
        m_ret_pct.index.name = 'Field'
        m_ret_pct = m_ret_pct.reset_index()
        m_ret_pct['Ticker'] = active
        m_zscore = month_zscore.T
        m_zscore.columns = [x.strftime("%Y-%m") for x in m_zscore.columns]
        m_zscore.index = ['Zscore']
        m_zscore.index.name = 'Field'
        m_zscore = m_zscore.reset_index()
        m_zscore['Ticker'] = active

        monthly_acrz = month_return.rolling(20).apply(lambda x: auto_correl_t(x))
        m_acrz = monthly_acrz.T
        col_filter = [x for x in m_acrz.columns if x >= dt.datetime(2010, 1, 1)]
        m_acrz = m_acrz[col_filter]
        m_acrz.columns = [x.strftime("%Y-%m") for x in m_acrz.columns]
        m_acrz.index = ['chg AC1 tstat']
        m_acrz.index.name = 'Field'
        m_acrz = m_acrz.reset_index()
        m_acrz['Ticker'] = active

        monthly_aczz = month_zscore.rolling(20).apply(lambda x: auto_correl_t(x))
        m_aczz = monthly_aczz.T
        col_filter = [x for x in m_aczz.columns if x >= dt.datetime(2010, 1, 1)]
        m_aczz = m_aczz[col_filter]
        m_aczz.columns = [x.strftime("%Y-%m") for x in m_aczz.columns]
        m_aczz.index = ['z AC1 tstat']
        m_aczz.index.name = 'Field'
        m_aczz = m_aczz.reset_index()
        m_aczz['Ticker'] = active

        fig = None  # sm.graphics.tsa.plot_acf(month_return.dropna(), lags=12)
        model = sm.tsa.arima.ARIMA(month_return.dropna(), order=(1, 0, 0))
        res = model.fit()

        q_ret_pct = quarter_return.dropna() * 100
        q_ret_pct = q_ret_pct.T
        col_filter = [x for x in q_ret_pct.columns if x >= dt.datetime(2010, 1, 1)]
        q_ret_pct = q_ret_pct[col_filter]
        q_ret_pct.columns = pd.PeriodIndex(q_ret_pct.columns, freq="Q")

        q_ret_pct.index = ["Return %"]
        q_ret_pct.index.name = 'Field'
        q_ret_pct = q_ret_pct.reset_index()
        q_ret_pct['Ticker'] = active
        q_zscore = quarter_zscore.T
        col_filter = [x for x in q_zscore.columns if x >= dt.datetime(2010, 1, 1)]
        q_zscore = q_zscore[col_filter]
        q_zscore.columns = pd.PeriodIndex(q_zscore.columns, freq="Q")
        q_zscore = q_zscore.sort_index(axis=1)

        q_zscore.index = ['Zscore']
        q_zscore.index.name = 'Field'
        q_zscore = q_zscore.reset_index()
        q_zscore['Ticker'] = active

        quarter_acrz = quarter_return.rolling(20).apply(lambda x: auto_correl_t(x))
        q_acrz = quarter_acrz.T
        col_filter = [x for x in q_acrz.columns if x >= dt.datetime(2010, 1, 1)]
        q_acrz = q_acrz[col_filter]
        q_acrz.columns = pd.PeriodIndex(q_acrz.columns, freq="Q")
        q_acrz.index = ['chg AC1 tstat']
        q_acrz.index.name = 'Field'
        q_acrz = q_acrz.reset_index()
        q_acrz['Ticker'] = active

        quarter_aczz = quarter_zscore.rolling(20).apply(lambda x: auto_correl_t(x))
        q_aczz = quarter_aczz.T
        col_filter = [x for x in q_aczz.columns if x >= dt.datetime(2010, 1, 1)]
        q_aczz = q_aczz[col_filter].copy()
        q_aczz.columns = pd.PeriodIndex(q_aczz.columns, freq="Q")
        q_aczz.index = ['z AC1 tstat']
        q_aczz.index.name = 'Field'
        q_aczz = q_aczz.reset_index()
        q_aczz['Ticker'] = active

        fig_qa = None  # sm.graphics.tsa.plot_acf(quarter_return.dropna(), lags=12)
        model_qa = sm.tsa.arima.ARIMA(quarter_return.dropna(), order=(1, 0, 0))
        res_qa = model_qa.fit()
        raise NotImplementedError("Missing model-result dictionary entries: IMG_5135 lines 194-195")
        results_dict[active] = dict(monthly=dict(ret=m_ret_pct, zscore=m_zscore, ract=m_acrz, zact=m_aczz),
                                    quaterly=dict(ret=q_ret_pct, zscore=q_zscore, ract=q_acrz, zact=q_aczz))
    all_monthly = pd.DataFrame()
    all_quaterly = pd.DataFrame()
    for k, v in results_dict.items():
        print(k)
        monthly_ret = v["monthly"]["ret"]
        monthly_zscore = v["monthly"]["zscore"]
        monthly_ract = v["monthly"]["ract"]
        monthly_zact = v["monthly"]["zact"]
        monthly = pd.concat([monthly_ret, monthly_ract, monthly_zscore, monthly_zact])
        all_monthly = pd.concat([all_monthly, monthly])
        quaterly_ret = v["quaterly"]["ret"]
        quaterly_zscore = v["quaterly"]["zscore"]
        quaterly_ract = v["quaterly"]["ract"]
        quaterly_zact = v["quaterly"]["zact"]
        quaterly = pd.concat([quaterly_ret, quaterly_ract, quaterly_zscore, quaterly_zact])
        all_quaterly = pd.concat([all_quaterly, quaterly])
    quaterly_file = base_file.join(all_quaterly.set_index("Ticker")).reset_index().set_index(["Instr", "Ticker", "Field"])
    quaterly_file = quaterly_file.sort_index(axis=1)
    quaterly_file = quaterly_file.sort_index(axis=0)
    quaterly_file = quaterly_file.reset_index()
    q_out_path = f"{base_path}\\EOQ.Rebal_1.xlsx"
    quaterly_file.to_excel(q_out_path)
    monthly_file = base_file.join(all_monthly.set_index("Ticker")).reset_index().set_index(["Instr", "Ticker", "Field"])
    monthly_file = monthly_file.sort_index(axis=1)
    monthly_file = monthly_file.sort_index(axis=0)
    monthly_file = monthly_file.reset_index()
    m_out_path = f"{base_path}\\EOM.Rebal_1.xlsx"
    monthly_file.to_excel(m_out_path)
    print("break")


def process_results():
    quaterly = pd.read_excel(f"{base_path}\\EOQ.Rebal_1.xlsx").drop(columns=["Unnamed: 0"])
    q_zscore = quaterly[quaterly["Field"] == "z AC1 tstat"].drop(columns=["Field", "Instr"]).set_index("Ticker")
    q_return = quaterly[quaterly["Field"] == "chg AC1 tstat"].drop(columns=["Field", "Instr"]).set_index("Ticker")
    results = []
    for col in q_zscore:
        result = dict()
        df = q_zscore[col].dropna()
        if df.empty:
            continue
        top_perform = df[df == df.max()].index[0]
        low_perform = df[df == df.min()].index[0]
        result["Quater"] = col
        result["Top Zscore"] = top_perform
        result["Low Zscore"] = low_perform
        next_q = str(pd.Period((pd.to_datetime(col) + pd.DateOffset(months=3)), freq="Q"))
        if next_q in q_return.columns:
            next_ret_top = q_return.loc[top_perform][next_q]
            result["Next Q % Return Top cond"] = next_ret_top > 0
            next_ret_low = q_return.loc[low_perform][next_q]
            result["Next Q % Return Low cond"] = next_ret_low < 0
        else:
            result["Next Q % Return Top cond"] = False
            result["Next Q % Return Low cond"] = False
        results.append(result)
    res_df_q = pd.DataFrame(results)
    res_top_q = res_df_q[["Quater", "Top Zscore", "Next Q % Return Top cond"]]
    res_low_q = res_df_q[["Quater", "Low Zscore", "Next Q % Return Low cond"]]
    rql = res_low_q.set_index("Quater").T
    rqt = res_top_q.set_index("Quater").T
    res_q = pd.concat([rql, rqt])
    print(res_q)

    monthly = pd.read_excel(f"{base_path}\\EOM.Rebal_1.xlsx").drop(columns=["Unnamed: 0"])
    m_zscore = monthly[monthly["Field"] == "z AC1 tstat"].drop(columns=["Field", "Instr"]).set_index("Ticker")
    m_return = monthly[monthly["Field"] == "chg AC1 tstat"].drop(columns=["Field", "Instr"]).set_index("Ticker")
    results = []
    for col in m_zscore:
        result = dict()
        df = m_zscore[col].dropna()
        if df.empty:
            continue
        top_perform = df[df == df.max()].index[0]
        low_perform = df[df == df.min()].index[0]
        result["Month"] = col
        result["Top Zscore"] = top_perform
        result["Low Zscore"] = low_perform
        next_q = (pd.to_datetime(col) + pd.DateOffset(months=1)).strftime("%Y-%m")
        if next_q in m_return.columns:
            next_ret_top = m_return.loc[top_perform][next_q]
            result["Next Q % Return Top cond"] = next_ret_top > 0
            next_ret_low = m_return.loc[low_perform][next_q]
            result["Next Q % Return Low cond"] = next_ret_low < 0
        else:
            result["Next Q % Return Top cond"] = False
            result["Next Q % Return Low cond"] = False
        results.append(result)
    res_df_m = pd.DataFrame(results)
    res_top_m = res_df_m[["Month", "Top Zscore", "Next Q % Return Top cond"]]
    res_low_m = res_df_m[["Month", "Low Zscore", "Next Q % Return Low cond"]]
    rml = res_low_m.set_index("Month").T
    rmt = res_top_m.set_index("Month").T
    res_m = pd.concat([rml, rmt])
    print(res_m)


if __name__ == "__main__":
    update()
