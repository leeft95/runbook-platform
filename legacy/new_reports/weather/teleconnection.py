import pandas as pd
import numpy as np
import datetime as dt
import os
import sys
import math
from dateutil.rrule import rrule, MINUTELY
import ecm.cmds.stormvista as sv
import ecm.cmds.sql as sql
import ecm.cmds.bbg as bbg
import ecm.cmds.stormvista as sv
import ecm.cmds.table as table
import ecm.cmds.chart as chart
import ecm.cmds.time_series as ts
from ecm.cmds.cdr import today
from ecm.cmds.config import output_path, html_path, root_path, csv_path
from ecm.cmds.talib import realizedvol
from ecm.cmds._email import send_email
from ecm.cmds.utils import convert_path_to_linux


send_to = ['Commods@elementcapital.com']
report_name = "Teleconnections Update"
file_name = "teleconnection"  # without .py
file_path = f"{root_path}\\autoreports\\reports\\weather\\{file_name}.py"
size_EC00 = 12000000
size_EC00_TTF = 5000000


def add_schedule():
    """
    # schedule to run the report - only need to run once
    """
    sys.path.append(f"{root_path}\\autoreports\\schedule")
    from tasks import WinTaskPoC
    from ecm.atom.wintask.scheduler import ECMWinTask
    from ecm.atom.wintask.utils import Days

    win_task = ECMWinTask(
        days=Days.MONDAY | Days.TUESDAY | Days.WEDNESDAY | Days.THURSDAY | Days.FRIDAY | Days.SATURDAY | Days.SUNDAY,
        start_datetime=dt.datetime(2023, 7, 1, 7, 55),
        timezone="Europe/London",
        repetition_interval=dt.timedelta(hours=12),
        repetition_duration=dt.timedelta(hours=12),
        task_name=report_name,
        task=WinTaskPoC(name=f'"{report_name}"', filepath=f'"{file_path}"'),
        background_task=True,
        python_executable=r"C:\local\python\miniconda\envs\ecm_cmds\pythonw.exe"
    )
    win_task.create_task()


def update():
    update_tele_fcst()
    create_all_fcst_index()


def update_tele_hist():
    ind_list = ["scand", "nao", "ao", "ea", "eawr", "epo", "wpo", "pna"]
    for i in ind_list:
        sdate = sql.read_sql(f"Select MAX(Dates) from SV_TELECONNECTIONS_HIST where Ind='{i}'")
        if sdate.iloc[0, 0] is None:
            sdate = dt.datetime(1948, 12, 31)
        else:
            sdate = sdate.iloc[0, 0]
        data = sv.teleconnections_hist(i)
        data.columns = ["Dates", "Value"]
        data["Dates"] = pd.to_datetime(data["Dates"])
        data = data.loc[data["Dates"] > sdate, :]
        if len(data) > 0:
            data["Ind"] = i
            sql.to_sql(data, "SV_TELECONNECTIONS_HIST")


def update_tele_fcst():
    ind_list = ["scand", "nao", "ao", "ea", "eawr", "epo", "wpo", "pna", "abna"]
    cycle_list = ["00", "06", "12", "18"]
    model_list = ["ecmwf-eps", "gfs-ens-mem"]
    for i in ind_list:
        for j in cycle_list:
            for k in model_list:
                sdate = sql.read_sql(f"Select MAX(As_Of_Date) from SV_TELECONNECTIONS_FCST where Ind='{i}' and Cycle='{j}' and Model='{k}'")
                if sdate.iloc[0, 0] is None:
                    sdate = dt.datetime(2019, 12, 1)
                else:
                    sdate = sdate.iloc[0, 0] + dt.timedelta(1)
                dts = pd.date_range(sdate, today(), freq="D")
                total_data = pd.DataFrame()
                for l in dts:
                    print(i, j, k, l)
                    data = sv.teleconnections(file_date=l, ind=i, cycle=j, model=k)
                    data.rename(columns={"member": "Member"}, inplace=True)
                    if len(data) > 0:
                        if '384' not in data.columns:
                            data['384'] = np.nan
                        data["Ind"] = i
                        data["Cycle"] = j
                        data["Model"] = k
                        data["As_Of_Date"] = l
                        total_data = pd.concat([total_data, data], axis=0)
                sql.to_sql(total_data, "SV_TELECONNECTIONS_FCST")


def create_index(cycle="00", model="ecmwf-eps", start='0'):
    ind_list = ["scand", "nao", "ao", "ea", "eawr", "epo", "wpo", "pna", "abna"]
    res_dict = {}
    for i in ind_list:
        data = sql.read_sql(f"Select * from SV_TELECONNECTIONS_FCST where Ind='{i}' and Cycle='{cycle}' and Model='{model}'")
        data = data.drop('Member', axis=1)
        data = data.groupby("As_Of_Date").mean()
        res_dict[i] = data.loc[:, start:]

    eu_index = pd.DataFrame()
    eu_index['SCAND'] = res_dict['scand'].mean(axis=1)
    eu_index['NAO'] = -res_dict['nao'].mean(axis=1)
    eu_index['AO'] = -res_dict['ao'].mean(axis=1)
    eu_index['EA'] = -res_dict['ea'].mean(axis=1)
    eu_index['EAWR'] = -res_dict['eawr'].mean(axis=1)
    w_scand = eu_index['SCAND'].copy()
    w_scand[w_scand > 0] = 0.2
    w_scand[w_scand < 0] = -0.2
    w_nao = eu_index['NAO'].copy()
    w_nao[w_nao > 0] = 0.2
    w_nao[w_nao < 0] = -0.2
    w_ao = eu_index['AO'].copy()
    w_ao[w_ao > 0] = 0.2
    w_ao[w_ao < 0] = -0.2
    w_ea = eu_index['EA'].copy()
    w_ea[w_ea > 0] = 0.2
    w_ea[w_ea < 0] = -0.2
    w_eawr = eu_index['EAWR'].copy()
    w_eawr[w_eawr > 0] = 0.2
    w_eawr[w_eawr < 0] = -0.2
    eu_index['EU Index'] = (res_dict['scand'] - res_dict['nao'] - res_dict['ao'] - res_dict['ea'] - res_dict['eawr']).mean(axis=1)
    eu_index['adjust'] = w_scand + w_nao + w_ao + w_ea + w_eawr
    eu_index = eu_index[['EU Index', 'NAO', 'AO', 'SCAND', 'EA', 'EAWR', 'adjust']]
    eu_index.to_csv(convert_path_to_linux(f"{csv_path}\\weather\\teleconnections\\EU_{cycle}_{model}_{start}.csv"))

    us_index = pd.DataFrame()
    us_index['EPO'] = -res_dict['epo'].mean(axis=1)
    us_index['WPO'] = -res_dict['wpo'].mean(axis=1)
    us_index['PNA'] = res_dict['pna'].mean(axis=1)
    us_index['NAO'] = -res_dict['nao'].mean(axis=1)
    w_epo = us_index['EPO'].copy()
    w_epo[w_epo > 0] = 0.25
    w_epo[w_epo < 0] = -0.25
    w_wpo = us_index['WPO'].copy()
    w_wpo[w_wpo > 0] = 0.25
    w_wpo[w_wpo < 0] = -0.25
    w_pna = us_index['PNA'].copy()
    w_pna[w_pna > 0] = 0.25
    w_pna[w_pna < 0] = -0.25
    w_nao = us_index['NAO'].copy()
    w_nao[w_nao > 0] = 0.25
    w_nao[w_nao < 0] = -0.25
    us_index['US Index'] = (res_dict['pna'] - res_dict['epo'] - res_dict['wpo'] - res_dict['nao']).mean(axis=1)
    us_index['adjust'] = w_epo + w_wpo + w_pna + w_nao
    us_index = us_index[['US Index', 'EPO', 'WPO', 'PNA', 'NAO', 'adjust']]
    us_index.to_csv(convert_path_to_linux(f"{csv_path}\\weather\\teleconnections\\US_{cycle}_{model}_{start}.csv"))

    us_index = pd.DataFrame()
    us_index['EPO'] = -res_dict['epo'].mean(axis=1)
    us_index['WPO'] = -res_dict['wpo'].mean(axis=1)
    us_index['PNA'] = res_dict['pna'].mean(axis=1)
    us_index['NAO'] = -res_dict['nao'].mean(axis=1)
    us_index['AO'] = -res_dict['ao'].mean(axis=1)
    us_index['ABNA'] = -res_dict['abna'].mean(axis=1)
    w_epo = us_index['EPO'].copy()
    w_epo[w_epo > 0] = 0.25
    w_epo[w_epo < 0] = -0.25
    w_wpo = us_index['WPO'].copy()
    w_wpo[w_wpo > 0] = 0.25
    w_wpo[w_wpo < 0] = -0.25
    w_pna = us_index['PNA'].copy()
    w_pna[w_pna > 0] = 0.25
    w_pna[w_pna < 0] = -0.25
    w_nao = us_index['NAO'].copy()
    w_nao[w_nao > 0] = 0.25
    w_nao[w_nao < 0] = -0.25
    raise NotImplementedError("Photographed teleconnection.py line185 has clipped remaining weights")
    us_index['adjust'] = w_epo + w_wpo + w_pna + w_nao
    us_index = us_index[['US Index', 'EPO', 'WPO', 'PNA', 'NAO', 'ABNA', 'AO', 'adjust']]

    asia_index = pd.DataFrame()
    asia_index['EAWR'] = -res_dict['eawr'].mean(axis=1)
    asia_index['WPO'] = -res_dict['wpo'].mean(axis=1)
    asia_index['SCAND'] = res_dict['scand'].mean(axis=1)
    asia_index['Asia Index'] = (res_dict['scand'] - res_dict['eawr'] - res_dict['wpo']).mean(axis=1)
    asia_index = asia_index[['Asia Index', 'EAWR', 'WPO', 'SCAND']]
    asia_index.to_csv(convert_path_to_linux(f"{csv_path}\\weather\\teleconnections\\ASIA_{cycle}_{model}_{start}.csv"))


def create_all_fcst_index():
    cycle_list = ["00", "12"]
    model_list = ["ecmwf-eps"]
    start_list = ["216"]
    for i in cycle_list:
        for j in model_list:
            for k in start_list:
                print(i, j, k)
                create_index(cycle=i, model=j, start=k)


def create_index_realized():
    ind_list = ["scand", "nao", "ao", "ea", "eawr", "epo", "wpo", "pna"]
    res_dict = {}
    for i in ind_list:
        data = sql.read_sql(f"Select Dates, Value from SV_TELECONNECTIONS_HIST where Ind='{i}' order by Dates")
        data.set_index("Dates", inplace=True)
        data.index = pd.to_datetime(data.index)
        res_dict[i] = data

    eu_index = pd.DataFrame()
    eu_index['SCAND'] = res_dict['scand'].mean(axis=1)
    eu_index['NAO'] = -res_dict['nao'].mean(axis=1)
    eu_index['AO'] = -res_dict['ao'].mean(axis=1)
    eu_index['EA'] = -res_dict['ea'].mean(axis=1)
    eu_index['EAWR'] = -res_dict['eawr'].mean(axis=1)
    eu_index['EU Index'] = (res_dict['scand'] - res_dict['nao'] - res_dict['ao'] - res_dict['ea'] - res_dict['eawr']).mean(axis=1)
    eu_index = eu_index[['EU Index', 'NAO', 'AO', 'SCAND', 'EA', 'EAWR']]
    eu_index.to_csv(convert_path_to_linux(f"{csv_path}\\weather\\teleconnections\\EU_realized.csv"))

    us_index = pd.DataFrame()
    us_index['EPO'] = -res_dict['epo'].mean(axis=1)
    us_index['WPO'] = -res_dict['wpo'].mean(axis=1)
    us_index['PNA'] = res_dict['pna'].mean(axis=1)
    us_index['NAO'] = -res_dict['nao'].mean(axis=1)
    us_index['US Index'] = (res_dict['pna'] - res_dict['epo'] - res_dict['wpo'] - res_dict['nao']).mean(axis=1)
    us_index = us_index[['US Index', 'EPO', 'WPO', 'PNA', 'NAO']]
    us_index.to_csv(convert_path_to_linux(f"{csv_path}\\weather\\teleconnections\\US_realized.csv"))

    asia_index = pd.DataFrame()
    asia_index['EAWR'] = -res_dict['eawr'].mean(axis=1)
    asia_index['WPO'] = -res_dict['wpo'].mean(axis=1)
    asia_index['SCAND'] = res_dict['scand'].mean(axis=1)
    asia_index['Asia Index'] = (res_dict['scand'] - res_dict['eawr'] - res_dict['wpo']).mean(axis=1)
    asia_index = asia_index[['Asia Index', 'EAWR', 'WPO', 'SCAND']]
    asia_index.to_csv(convert_path_to_linux(f"{csv_path}\\weather\\teleconnections\\ASIA_realized.csv"))


if __name__ == "__main__":
    update()
