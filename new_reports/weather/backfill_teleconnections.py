import pandas as pd
import datetime as dt
import ecm.cmds.stormvista as sv
import ecm.cmds.time_series as ts
import ecm.cmds.chart as chart
from ecm.cmds.config import csv_path
from ecm.cmds.cdr import today
from concurrent.futures import ThreadPoolExecutor as tp_exec


weather_folder = f"{csv_path}\\weather\\"
neg_cols = {
    "EU": ["NAO", "AO", "EA", "EAWR"],
    "US": ["EPO", "WPO", "PNA", "NAO"],
    "Asia": ["EAWR", "WPO"]
}

hist_data_cache = {}


def get_forecast_data_for_date(date, run, ind, model, region):
    try:
        ind_frame = sv.teleconnections(date, ind.lower(), cycle=run, model=model, backfill=True)
        ind_frame.loc['mean'] = ind_frame.mean()
        ind_frame = ind_frame.drop('member', axis=1)
        ind_frame = ind_frame.transpose()
        ret = ind_frame['mean'] * -1 if ind in neg_cols.get(region, []) else ind_frame['mean']
        ret.drop(ret.index[:9], inplace=True)
        ret = ret.mean()
    except Exception as e:
        raw_actual_hist = hist_data_cache.get(ind, pd.DataFrame())
        if raw_actual_hist.empty:
            raw_actual_hist = sv.teleconnections_hist(ind=ind.lower()).set_index("Date")
            raw_actual_hist.index = pd.to_datetime(raw_actual_hist.index)
            hist_data_cache[ind] = raw_actual_hist
        ret = raw_actual_hist.loc[date].Value * -1 if ind in neg_cols.get(region, []) else raw_actual_hist.loc[date].Value
    return ret


def get_date_data_func(d, cols, run, region, model):
    print(f"Processing date {d.strftime('%Y-%m-%d')}")
    ind_date = []
    for ind in cols:
        if ind != f"{region} Index":
            mean_fcst_ind = get_forecast_data_for_date(d, run, ind, model, region)
            val = pd.Series(data=[mean_fcst_ind], index=[d], name=ind)
            ind_date.append(val)
    hist_row = pd.DataFrame(ind_date).T
    hist_row[f"{region} Index"] = hist_row.sum(axis=1)
    return hist_row


def backfill(run='00', model='ecmwf-eps', region='EU', sdate="2019-01-01"):
    existing_data = ts.read_csv(weather_folder + f'{region}_{run}_{model}.csv', index_name='Unnamed: 0')
    min_date = existing_data.index.min()
    hist_dates = pd.date_range(sdate, min_date - dt.timedelta(days=1))
    hist_rows = []
    args = [(d, existing_data.columns, run, region, model) for d in hist_dates]
    with tp_exec() as pool:
        hist_rows = pool.map(get_date_data_func, *zip(*args))
    hist_data = pd.concat(hist_rows)
    backfilled_data = pd.concat([hist_data[existing_data.columns], existing_data])
    backfilled_data.to_csv(weather_folder + f'{region}_{run}_{model}.csv')


def weather_index_table_chart(run='00', region="EU"):
    sdate = dt.datetime(2024, 10, 1)
    weather_folder = f"{csv_path}\\weather\\"
    data_eu_ori = ts.read_csv(weather_folder + f'{region}_{run}_ecmwf-eps.csv', index_name='Unnamed: 0')
    data_eu = data_eu_ori.copy()
    raise NotImplementedError("Photographed backfill_teleconnections.py line 71 has a clipped reindex expression")
    eu_season = chart.seasonal_chart_new(
        df=...,
        title="Europe - seasonal weather index",
        start_month=10, start_day=1, end_month=4, end_day=30, over_year=True,
        height=500, width=750
    ).show()
    print("break")


if __name__ == '__main__':
    regions = ["EU", "US", "Asia"]
    runs = ["00", "12"]
    models = ["ecmwf-eps", "gfs-ens-mem"]
    for region in regions:
        for run in runs:
            for model in models:
                backfill(model=model, region=region, run=run)
            weather_index_table_chart(run=run, region=region)
