import sys
import pandas as pd
import numpy as np
import os
import requests
from urllib3.exceptions import InsecureRequestWarning
from concurrent.futures import ThreadPoolExecutor
requests.packages.urllib3.disable_warnings(category=InsecureRequestWarning) # type: ignore
import datetime as dt
from sqlalchemy import create_engine
pd.options.plotting.backend = "plotly"
import plotly.graph_objects as go
from dateutil.relativedelta import relativedelta
import ecm.cmds.sql as sql
import ecm.cmds.bbg as bbg
from ecm.cmds.cdr import today
from ecm.cmds.data import gen_new_iir_token
from ecm.cmds.config import root_path, oil_group
import ecm.cmds.table as table
import ecm.cmds.chart as chart
import ecm.cmds.time_series as ts
import ecm.cmds.data as dv
from ecm.cmds._email import send_email
from ecm.cmds.config import html_path, data_path, json_path
from ecm.cmds.utils import convert_path_to_linux


def _unrecovered(message, *visible_arguments):
    raise NotImplementedError(message)


send_to = oil_group
report_name = "IIR Outages New"
file_name = "iir_outages_new" # without .py
file_path = f"{root_path}\\autoreports\\reports\\oil\\{file_name}.py"
table_name = "IIR_CDU_new"
url = 'https://api.industrialinfo.com/idb/v2.3/'


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
        start_datetime=dt.datetime(2022, 7, 1, 9, 34), timezone="Europe/London", task_name=report_name,
        task=WinTaskPoC(name=f'"{report_name}"', filepath=f'"{file_path}"'), background_task=True,
        python_excecutable=r"C:\local\python\miniconda\envs\ecm_cmds\pythonw.exe")
    win_task.create_task()


def move_data():
    sql_str = """select offlineEventKey, eventId, eventType, eventStatusDesc,
        associatedEntityStartDate, associatedEntityEndDate,
        associatedEntityPrevStartDate, associatedEntityPrevEndDate,
        associatedEntityType, associatedPlantId, eventStartDate,
        eventEndDate, eventDuration, prevStartDate, prevEndDate,
        unitId, unitName, plantName, plantOwnerName,
        tradingRegionName, unitTypeDesc, unitTypeGroup, eventComments,
        liveDate, releaseDate, [plantPhysicalAddress.city],
        [plantPhysicalAddress.stateName], [plantPhysicalAddress.countryName],
        [offlineCapacity.productId], [offlineCapacity.productDesc],
        [offlineCapacity.unitCapacity], [offlineCapacity.capacityOffline],
        [offlineCapacity.uom], isoRtoRegion, [fuel.primaryFuel],
        min(As_of_date) as As_of_date from IIR_CDU group by offlineEventKey, eventId, eventType, eventStatusDesc,
        associatedEntityStartDate, associatedEntityEndDate,
        associatedEntityPrevStartDate, associatedEntityPrevEndDate,
        associatedEntityType, associatedPlantId, eventStartDate,
        eventEndDate, eventDuration, prevStartDate, prevEndDate,
        unitId, unitName, plantName, plantOwnerName,
        tradingRegionName, unitTypeDesc, unitTypeGroup, eventComments,
        liveDate, releaseDate, [plantPhysicalAddress.city],
        [plantPhysicalAddress.stateName], [plantPhysicalAddress.countryName],
        [offlineCapacity.productId], [offlineCapacity.productDesc],
        [offlineCapacity.unitCapacity], [offlineCapacity.capacityOffline],
        [offlineCapacity.uom], isoRtoRegion, [fuel.primaryFuel] order by As_of_date"""
    df = sql.read_sql(sql_str)
    sql.to_sql(df, table_name, index=False)


def download_iir_other():
    token = gen_new_iir_token()
    headers = {'Authorization': (token)}
    def get_data(i, j):
        testttl_weekly = requests.post(
            f'{url}offlineevents/summary?unitTypeId=000{j:02d}&limit=10&offset={i}', headers=headers,
            stream=_unrecovered('IIR outages 97: clipped stream argument'), verify=False)
        json_response = testttl_weekly.json()
        return json_response
    datatotal = pd.DataFrame()
    with ThreadPoolExecutor() as pool:
        json_responses = pool.map(get_data, [0]*3, [1,4,9])
    for json_response in json_responses:
        try:
            df2 = pd.json_normalize(json_response, record_path='offlineEvents')
            datatotal = pd.concat([datatotal, df2], axis=0)
        except:
            pass
    datatotal.to_csv("H:\\temp\\iir.csv")


def download_iir(unitTypeGroup):
    token = gen_new_iir_token()
    headers = {'Authorization': (token)}
    unit_dict = {"Crude": "1", "Cat Cracker": "4", "Hydrocracking": "9"}
    def get_data(i, j):
        testttl_weekly = requests.post(
            f'{url}offlineevents/summary?unitTypeId=0000{j}&limit=1000&offset={i}', headers=headers,
            **_unrecovered('IIR outages 124: clipped request kwargs beginning stream'))
        json_response = testttl_weekly.json()
        return json_response
    datatotal = pd.DataFrame()
    with ThreadPoolExecutor() as pool:
        json_responses = pool.map(get_data, range(0, 6000, 1000), [unit_dict[unitTypeGroup]] * len(range(0, 6000, 1000)))
    for json_response in json_responses:
        try:
            df2 = pd.json_normalize(json_response, record_path='offlineEvents')
            datatotal = pd.concat([datatotal, df2], axis=0)
        except:
            pass
    datatotal['associatedEntityStartDate'] = datatotal['associatedEntityStartDate'].str[:10]
    datatotal['associatedEntityEndDate'] = datatotal['associatedEntityEndDate'].str[:10]
    datatotal['eventStartDate'] = datatotal['eventStartDate'].str[:10]
    datatotal['eventEndDate'] = datatotal['eventEndDate'].str[:10]
    datatotal['prevStartDate'] = datatotal['prevStartDate'].str[:10]
    datatotal['prevEndDate'] = datatotal['prevEndDate'].str[:10]
    datatotal['associatedEntityPrevStartDate'] = datatotal['associatedEntityPrevStartDate'].str[:10]
    datatotal['associatedEntityPrevEndDate'] = datatotal['associatedEntityPrevEndDate'].str[:10]
    datatotal['liveDate'] = datatotal['liveDate'].str[:10]
    datatotal['releaseDate'] = datatotal['releaseDate'].str[:10]
    exist_data = sql.read_sql(f"select * from {table_name} where unitTypeGroup='{unitTypeGroup}' order by As_of_date")
    exist_data.drop("As_of_date", axis=1, inplace=True)
    if "qcDate" in datatotal.columns:
        datatotal["qcDate"] = pd.to_datetime(datatotal["qcDate"].apply(lambda x: x.split("Z")[0]))
    new_data1 = datatotal.merge(exist_data,
        on=['offlineEventKey', 'eventId', 'eventType', 'eventStatusDesc', 'eventCause', 'eventConfirmationStatus', 'eventDatePrecision',
            'associatedEntityStartDate', 'associatedEntityEndDate', 'associatedEntityPrevStartDate', 'associatedEntityPrevEndDate',
            'associatedEntityType', 'associatedPlantId', 'eventStartDate', 'eventEndDate', 'eventDuration', 'prevStartDate', 'prevEndDate',
            'unitId', 'unitName', 'plantName', 'plantOwnerName', 'tradingRegionName', 'unitTypeDesc', 'unitTypeGroup', 'eventComments',
            'liveDate', 'releaseDate', 'plantPhysicalAddress.city', 'plantPhysicalAddress.stateName', 'plantPhysicalAddress.countryName',
            'offlineCapacity.productId', 'offlineCapacity.productDesc', 'offlineCapacity.unitCapacity', 'offlineCapacity.capacityOffline',
            'offlineCapacity.uom', 'isoRtoRegion', 'fuel.primaryFuel', 'qcDate'], how='left', indicator=True)
    new_data2 = new_data1.loc[new_data1['_merge'] == 'left_only', :]
    if len(new_data2) > 0:
        new_data2.drop("_merge", axis=1, inplace=True)
        new_data2['As_of_date'] = today()
        sql.to_sql(new_data2, table_name, index=False)


def process_eventid(capacity=False):
    """
    One eventId can have mulitple rows because of revision
    Only keep the record that has the latest release date
    return a dataframe that has unique eventId as columns and date as index, filled with capacity in outage
    save data to increase process speed
    """
    if capacity:
        folder = "IIR_capacity"
    else:
        folder = "IIR"
    data = sql.read_sql(f"Select * from {table_name} where unitTypeGroup='Crude' order by releaseDate, As_of_date")
    event_id = data["eventId"].unique()
    if "all_events.csv" in os.listdir(convert_path_to_linux(f"{data_path}\\{folder}")):
        all_event = ts.read_csv(f"{data_path}\\{folder}\\all_events.csv", index_name="Unnamed: 0")
    else:
        all_event = pd.DataFrame()
    all_event_live = all_event.copy()
    for i in event_id:
        if str(i) not in all_event.columns:
            print(i)
            event = data.loc[data["eventId"] == i, :]
            one_event = pd.DataFrame()
            for idx, row in event.iterrows():
                dts = pd.date_range(row["eventStartDate"], row["eventEndDate"])
                event_1 = pd.DataFrame(0, index=dts, columns=[row["releaseDate"]])
                if row["eventStatusDesc"] != "Cancelled":
                    if capacity:
                        event_1.loc[:, :] = row["offlineCapacity.unitCapacity"]
                    else:
                        event_1.loc[:, :] = row["offlineCapacity.capacityOffline"]
                else:
                    if capacity:
                        event_1.loc[:, :] = row["offlineCapacity.unitCapacity"]
                try:
                    one_event = pd.concat([one_event, event_1], axis=1)
                except:
                    print("error")
            one_event.fillna(0, inplace=True)
            if event["eventStatusDesc"].iloc[-1] in ["Cancelled", "Past"]:
                one_event.to_csv(convert_path_to_linux(f"{data_path}\\{folder}\\{i}.csv"))
                all_event = pd.concat([all_event, one_event.iloc[:, -1].to_frame(i)], axis=1)
            all_event_live = pd.concat([all_event_live, one_event.iloc[:, -1].to_frame(i)], axis=1)
    all_event.to_csv(convert_path_to_linux(f"{data_path}\\{folder}\\all_events.csv"))
    all_event_live.to_csv(convert_path_to_linux(f"{data_path}\\{folder}\\all_events_{today().strftime('%Y%m%d')}.csv"))


def get_refinery_event(unitTypeGroup):
    """
    There could be multiple eventId for one outage
    Only keep the record that has the latest release date
    return a dataframe that has unique eventId as columns and date as index, filled with capacity in outage
    No need to save as data is much less than CDU
    """
    sql_str = _unrecovered('IIR outages 229–230: clipped refinery latest-release SQL',
        "SELECT t1.* FROM IIR_CDU_new t1 INNER JOIN(SELECT eventId, MAX(releaseDate) as max_value",
        " GROUP BY eventId) AS t2 ON t1.eventId = t2.eventId AND t1.releaseDate = t2.max_value AND t1.unit")
    data = sql.read_sql(sql_str)
    all_event = pd.DataFrame()
    for idx, row in data.iterrows():
        dts = pd.date_range(row["eventStartDate"], row["eventEndDate"])
        _unrecovered('IIR outages 235–239: unphotographed refinery event construction and exception branch')
        print("error")
    all_event.fillna(0, inplace=True)
    return data, all_event


def iir_outages(send_to=None):
    data = sql.read_sql(f"Select * from {table_name} where unitTypeGroup='Crude' order by releaseDate, As_of_date")
    data_7d = sql.read_sql(_unrecovered('IIR outages 247: clipped historical SQL releaseDate filter',
        f"Select * from {table_name} where unitTypeGroup='Crude' and releaseDate < '"))
    data_fcc_og, events_fcc = get_refinery_event(unitTypeGroup="Cat Cracker")
    data_hyc_og, events_hyc = get_refinery_event(unitTypeGroup="Hydrocracking")
    all_events = ts.read_csv(f"{data_path}\\IIR\\all_events_{today().strftime('%Y%m%d')}.csv", index_name="Unnamed: 0")
    all_events.fillna(value=0, inplace=True)
    global_capacity_df = refinery_capacity_platts()
    try:
        all_events_7d = ts.read_csv(f"{data_path}\\IIR\\all_events_{(today()-dt.timedelta(7)).strftime('%Y%m%d')}.csv", index_name="Unnamed: 0")
        all_events_7d.fillna(value=0, inplace=True)
        if all_events_7d.empty:
            raise ValueError(f"No Data in file all_events_{(today()-dt.timedelta(7)).strftime('%Y%m%d')}.csv")
    except Exception as e:
        print(e)
        print("Using all events latest for the data")
        all_events_7d = all_events.copy()
    all_regions = {}
    all_regions_plan = {}
    all_regions_unplan = {}
    all_regions_7d = {}
    all_regions_plan_7d = {}
    all_regions_unplan_7d = {}
    all_regions_fcc = {}
    all_regions_fcc_plan = {}
    all_regions_fcc_unplan = {}
    all_regions_hyc = {}
    all_regions_hyc_plan = {}
    all_regions_hyc_unplan = {}
    region_dict = {
        "World": {},
        "EU": {"plantPhysicalAddress.countryName": (
            'Germany', 'France', 'Ireland', 'United Kingdom', 'Sweden', 'Norway', 'Denmark', 'Finland',
            *_unrecovered('IIR outages 279: clipped EU country list tail'),
            'Netherlands', 'Belgium', 'Italy', 'Greece', 'Spain', 'Portugal', 'Turkey', 'Switzerland',
            *_unrecovered('IIR outages 280: clipped EU country list tail'),
            'Austria', 'Belgium', 'Bulgaria', 'Poland', 'Czech Republic', 'Hungary', 'Slovakia',
            *_unrecovered('IIR outages 281: clipped EU country list tail beginning Romani'))},
        "NWE1": {"plantPhysicalAddress.countryName": (
            'Poland', 'Ireland', 'United Kingdom', 'Sweden', 'Norway', 'Denmark', 'Finland',
            *_unrecovered('IIR outages 283: clipped NWE1 country list tail beginning Netherland'))},
        "NWE2": {"plantPhysicalAddress.countryName": 'France', "tradingRegionName": 'Northwest Europe'},
        "NWE3": {"plantName": (
            'Gelsenkirchen Horst Refinery', 'Gelsenkirchen Scholven Refinery',
            'Hamburg-Harburg Base Oil Refinery',
            'Holborn Refinery', 'Rheinland Godorf Refinery (North)',
            'Rheinland Wesseling Refinery (South)',
            'Lingen Emsland Refinery', 'Schwedt Refinery', 'Heide Refinery', 'Leuna Refinery')},
        "MED1": {"plantPhysicalAddress.countryName": (
            'Italy', 'Greece', 'Spain', 'Portugal', 'Turkey', 'Switzerland', 'Croatia', 'Austria',
            'Belgium', 'Bulgaria')},
        "MED2": {"plantPhysicalAddress.countryName": 'France', 'tradingRegionName': 'Mediterranean'},
        "MED3": {"plantName": ('Bayernoil Neustadt Refinery', 'Bayernoil Vohburg Refinery', 'Burghausen Refinery',
                              'Ingolstadt Refinery', 'MiRO Refinery Karlsruhe')},
        "US": {"plantPhysicalAddress.countryName": "U.S.A."},
        "P2 and P3": {"tradingRegionName": ('II', 'III')},
        **_unrecovered('IIR outages 298–299: unphotographed P2 and Asia region entries'),
        "India": {"plantPhysicalAddress.countryName": "India"},
        "China": {"plantPhysicalAddress.countryName": "China"},
        "Japan": {"plantPhysicalAddress.countryName": "Japan"},
        "Middle East": {"tradingRegionName": "Middle East"},
    }
    chart_dict = {"World": ["World", "EU", "US", "Asia", "Middle East"], "US": ["US", "P2 and P3", "P2"],
                  "EU": ["EU", "NWE", "MED"], "Asia": ["Asia", "China", "India", "Japan"]}
    region_dict_refinery = {
        "World": {},
        "EU": {"tradingRegionName": ("Mediterranean", "Northwest Europe", "Eastern Europe")},
        "US": {"plantPhysicalAddress.countryName": ("U.S.A.",)},
        "Asia": {"tradingRegionName": ("North Asia", "South Asia", "Southeast Asia", "Central Asia")},
        "Middle East": {"tradingRegionName": ("Middle East",)},
    }
    for key, val in region_dict.items():
        data_region = data.copy()
        data_region_7d = data_7d.copy()
        if key != "World":
            for key1, val1 in val.items():
                if isinstance(val1, tuple):
                    data_region = data_region.loc[data_region[key1].isin(val1)]
                    data_region_7d = data_region_7d.loc[data_region_7d[key1].isin(val1)]
                else:
                    data_region = data_region.loc[data_region[key1] == val1]
                    data_region_7d = data_region_7d.loc[data_region_7d[key1] == val1]
        unique_events = all_events[[str(x) for x in data_region["eventId"].unique()]]
        unique_events_7d = all_events_7d[[str(x) for x in data_region_7d["eventId"].unique()]]
        all_regions_plan[key] = _unrecovered('IIR outages 331: clipped planned event selection', unique_events, data_region)
        all_regions_plan_7d[key] = _unrecovered('IIR outages 332: clipped planned historical event selection', unique_events_7d, data_region_7d)
        all_regions_unplan[key] = _unrecovered('IIR outages 333: clipped unplanned event selection', unique_events, data_region)
        all_regions_unplan_7d[key] = _unrecovered('IIR outages 334: clipped unplanned historical event selection', unique_events_7d, data_region_7d)
        all_regions[key] = unique_events.sum(axis=1)
        all_regions_7d[key] = unique_events_7d.sum(axis=1)
        if key in region_dict_refinery.keys():
            data_fcc = data_fcc_og.copy()
            data_hyc = data_hyc_og.copy()
            if key != "World":
                new_dict = region_dict_refinery[key]
                data_fcc = data_fcc.loc[data_fcc[next(iter(new_dict))].isin(new_dict[next(iter(new_dict))])]
                data_hyc = data_hyc.loc[data_hyc[next(iter(new_dict))].isin(new_dict[next(iter(new_dict))])]
            all_regions_fcc_plan[key] = _unrecovered('IIR outages 345: clipped FCC planned selection', events_fcc, data_fcc)
            all_regions_fcc_unplan[key] = _unrecovered('IIR outages 346: clipped FCC unplanned selection', events_fcc, data_fcc)
            all_regions_fcc[key] = events_fcc[[x for x in data_fcc.loc[:, 'eventId'].unique()]].sum(axis=1)
            all_regions_hyc_plan[key] = _unrecovered('IIR outages 348: clipped hydrocracking planned selection', events_hyc, data_hyc)
            all_regions_hyc_unplan[key] = _unrecovered('IIR outages 349: clipped hydrocracking unplanned selection', events_hyc, data_hyc)
            all_regions_hyc[key] = events_hyc[[x for x in data_hyc.loc[:, 'eventId'].unique()]].sum(axis=1)
    all_regions["NWE"] = all_regions["NWE1"] + all_regions["NWE2"] + all_regions["NWE3"]
    all_regions_7d["NWE"] = all_regions_7d["NWE1"] + all_regions_7d["NWE2"] + all_regions_7d["NWE3"]
    all_regions_plan["NWE"] = all_regions_plan["NWE1"] + all_regions_plan["NWE2"] + all_regions_plan["NWE3"]
    all_regions_plan_7d["NWE"] = all_regions_plan_7d["NWE1"] + all_regions_plan_7d["NWE2"] + all_regions_plan_7d["NWE3"]
    all_regions_unplan["NWE"] = all_regions_unplan["NWE1"] + all_regions_unplan["NWE2"] + all_regions_unplan["NWE3"]
    all_regions_unplan_7d["NWE"] = all_regions_unplan_7d["NWE1"] + all_regions_unplan_7d["NWE2"] + all_regions_unplan_7d["NWE3"]
    all_regions["MED"] = all_regions["MED1"] + all_regions["MED2"] + all_regions["MED3"]
    all_regions_7d["MED"] = all_regions_7d["MED1"] + all_regions_7d["MED2"] + all_regions_7d["MED3"]
    all_regions_plan["MED"] = all_regions_plan["MED1"] + all_regions_plan["MED2"] + all_regions_plan["MED3"]
    all_regions_plan_7d["MED"] = all_regions_plan_7d["MED1"] + all_regions_plan_7d["MED2"] + all_regions_plan_7d["MED3"]
    all_regions_unplan["MED"] = all_regions_unplan["MED1"] + all_regions_unplan["MED2"] + all_regions_unplan["MED3"]
    all_regions_unplan_7d["MED"] = all_regions_unplan_7d["MED1"] + all_regions_unplan_7d["MED2"] + all_regions_unplan_7d["MED3"]
    all_regions_df = pd.DataFrame.from_dict(all_regions)
    all_regions_df_7d = pd.DataFrame.from_dict(all_regions_7d)
    all_regions_plan_df = pd.DataFrame.from_dict(all_regions_plan)
    all_regions_plan_df_7d = pd.DataFrame.from_dict(all_regions_plan_7d)
    all_regions_unplan_df = pd.DataFrame.from_dict(all_regions_unplan)
    all_regions_unplan_df_7d = pd.DataFrame.from_dict(all_regions_unplan_7d)
    all_regions_fcc_df = pd.DataFrame.from_dict(all_regions_fcc)
    all_regions_fcc_plan_df = pd.DataFrame.from_dict(all_regions_fcc_plan)
    all_regions_fcc_unplan_df = pd.DataFrame.from_dict(all_regions_fcc_unplan)
    all_regions_hyc_df = pd.DataFrame.from_dict(all_regions_hyc)
    all_regions_hyc_plan_df = pd.DataFrame.from_dict(all_regions_hyc_plan)
    all_regions_hyc_unplan_df = pd.DataFrame.from_dict(all_regions_hyc_unplan)
    figs = []
    figs.append("<div style='font-family:Calibri;' >")
    link_path_dict = {}
    for key, val in chart_dict.items():
        print(key)
        sub_figs = []
        sub_figs.append("<div style='font-family:Calibri;' >")
        total_capacity = global_capacity_df[val]
        total = all_regions_df[val]
        total_7d = all_regions_df_7d[val]
        planned = all_regions_plan_df[val]
        planned_7d = all_regions_plan_df_7d[val]
        unplanned = all_regions_unplan_df[val]
        unplanned_7d = all_regions_unplan_df_7d[val]
        html_table_plan, html_chart_plan, _, data_adj_plan = create_table(planned / 1000, sub_title="planned CDU", data_7d_ori=planned_7d/1000)
        html_table_unplan, html_chart_unplan, _, data_adj_unplan = create_table(unplanned / 1000,
            sub_title="unplanned CDU", data_7d_ori=unplanned_7d/1000, unplan=unplanned/1000, replace=True)
        total_adj = data_adj_plan + data_adj_unplan
        html_table, html_chart, html_chart_unified, data_adj_total = create_table(total_adj, sub_title="total CDU")
        avail_capacity_m = (total_capacity - total_adj.resample('MS').mean())/1000 # convert to mbd
        avail_capacity_m = pd.concat([avail_capacity_m, (global_capacity_df[["Other"]] / 1000).reindex(avail_capacity_m.index)], axis=1)
        avail_capacity_m0 = _unrecovered('IIR outages 409: clipped available capacity current date window', avail_capacity_m)
        avail_capacity_m1 = _unrecovered('IIR outages 410: clipped available capacity prior date window', avail_capacity_m)
        avail_capacity_yoy = avail_capacity_m0.reset_index(drop=True) - avail_capacity_m1.reset_index(drop=True)
        avail_capacity_yoy.index = avail_capacity_m0.index
        avail_capacity_table = avail_capacity_m0.T
        avail_capacity_table.columns = [x.strftime('%Y-%b') for x in avail_capacity_table.columns]
        avail_capacity_table.index.name = 'Region'
        html_capacity = table.html_format(df=avail_capacity_table.reset_index(), header="Available capacity (mmb/d)",
            footer="World=EU+US+Asia+Middle East, Other=FSU+Africa+ANZ+Canada+Latin America", precision=1)
        avail_capacity_yoy_table = avail_capacity_yoy.T
        avail_capacity_yoy_table.columns = [x.strftime('%Y-%b') for x in avail_capacity_yoy_table.columns]
        avail_capacity_yoy_table.index.name = 'Region'
        html_capacity_yoy = table.html_format(df=avail_capacity_yoy_table.reset_index(),
            header="Available capacity yoy change (mmb/d)", precision=1)
        sub_figs.append("<b>CDU Total turnarounds (kbd)</b>")
        sub_figs.append(html_table)
        sub_figs.append("<br><b>CDU Planned turnarounds (kbd)</b>")
        sub_figs.append(html_table_plan)
        sub_figs.append("<br><b>CDU Unplanned turnarounds (kbd)</b>")
        sub_figs.append(html_table_unplan)
        if key == "World":
            total_fcc = all_regions_fcc_df[val]
            plan_fcc = all_regions_fcc_plan_df[val]
            unplan_fcc = all_regions_fcc_unplan_df[val]
            html_table_fcc, html_chart_fcc, html_chart_unified_fcc, data_adj_total_fcc = create_table(
                total_fcc / 1000, sub_title="total FCC", unplan=unplan_fcc / 1000, start_date=dt.datetime(2022, 1, 1))
            html_table_plan_fcc, html_chart_plan_fcc, _, data_adj_plan_fcc = create_table(
                plan_fcc / 1000, sub_title="planned FCC", start_date=dt.datetime(2022, 1, 1))
            html_table_unplan_fcc, html_chart_unplan_fcc, _, data_adj_unplan_fcc = create_table(
                unplan_fcc / 1000, sub_title="unplanned FCC", unplan=unplan_fcc / 1000,
                start_date=dt.datetime(2022, 1, 1), replace=True)
            sub_figs.append("<b>FCC Total turnarounds (kbd)</b>")
            sub_figs.append(html_table_fcc)
            sub_figs.append("<br><b>FCC Planned turnarounds (kbd)</b>")
            sub_figs.append(html_table_plan_fcc)
            sub_figs.append("<br><b>FCC Unplanned turnarounds (kbd)</b>")
            sub_figs.append(html_table_unplan_fcc)
            total_hyc = all_regions_hyc_df[val]
            plan_hyc = all_regions_hyc_plan_df[val]
            unplan_hyc = all_regions_hyc_unplan_df[val]
            html_table_hyc, html_chart_hyc, html_chart_unified_hyc, data_adj_total_hyc = create_table(
                total_hyc / 1000, sub_title="total Hydrocracking", unplan=unplan_hyc / 1000, start_date=dt.datetime(2022, 1, 1))
            html_table_plan_hyc, html_chart_plan_hyc, _, data_adj_plan_hyc = create_table(
                plan_hyc / 1000, sub_title="planned Hydrocracking", start_date=dt.datetime(2022, 1, 1))
            html_table_unplan_hyc, html_chart_unplan_hyc, _, data_adj_unplan_hyc = create_table(
                unplan_hyc / 1000, sub_title="unplanned Hydrocracking", unplan=unplan_hyc / 1000,
                start_date=dt.datetime(2022, 1, 1), replace=True)
            sub_figs.append("<b>Hydrocracking Total turnarounds (kbd)</b>")
            sub_figs.append(html_table_hyc)
            sub_figs.append("<br><b>Hydrocracking Planned turnarounds (kbd)</b>")
            sub_figs.append(html_table_plan_hyc)
            sub_figs.append("<br><b>Hydrocracking Unplanned turnarounds (kbd)</b>")
            sub_figs.append(html_table_unplan_hyc)
        if key == "World":
            for idx, region_name in enumerate(val):
                sub_figs_charts = []
                sub_figs_charts.append([html_chart[idx], html_chart_plan[idx], html_chart_unplan[idx]])
                sub_figs_charts.append([html_chart_fcc[idx], html_chart_plan_fcc[idx], html_chart_unplan_fcc[idx]])
                sub_figs_charts.append([html_chart_hyc[idx], html_chart_plan_hyc[idx], html_chart_unplan_hyc[idx]])
                link_path_dict[region_name] = f"{html_path}\\oil\\iir\\World_{region_name}_sub_chart.html"
                table.to_html(sub_figs + sub_figs_charts, path=link_path_dict[region_name])
                html_table = html_table.replace(region_name, f'<a href="{link_path_dict[region_name]}">{region_name}</a>')
        else:
            for idx, _ in enumerate(val):
                sub_figs.append([html_chart[idx], html_chart_plan[idx], html_chart_unplan[idx]])
            link_path = f"{html_path}\\oil\\iir\\{key}_sub_chart.html"
            table.to_html(sub_figs, path=link_path)
            html_table = html_table.replace(key, f'<a href="{link_path}">{key}</a>')
        if key == "World":
            figs.append("<b>CDU Available Capacity (Platts capacity - IIR outages, mbd)</b>")
            figs.append(html_capacity)
            figs.append(html_capacity_yoy)
            figs.append("<b><b>CDU Total turnarounds (kbd)</b>")
            figs.append(html_table)
            with open(convert_path_to_linux(f"{html_path}\\oil\\world_total_turnaround.html"), "w") as f:
                f.write(html_table)
            html_chart[0].write_json(convert_path_to_linux(_unrecovered('IIR outages 517: clipped world_total_turnaround JSON filename')))
            latest_table, latest_chart = iir_outages_latest_change()
            figs.append("<b>FCC Total turnarounds (kbd)</b>")
            figs.append(html_table_fcc)
            figs.append("<b>Hydrocracking Total turnarounds (kbd)</b>")
            figs.append(html_table_hyc)
            figs.append(latest_table)
            figs.append(html_chart_unified[0])
            figs.append(html_chart_unified[1])
            figs.append(html_chart_unified[2])
            figs.append(html_chart_unified[3])
            figs.append(html_chart_unified[4])
        elif key == "Asia":
            figs.append(html_chart_unified[0])
            figs.append(html_chart_unified[1])
        _unrecovered('IIR outages 532–536: unphotographed iir_outages report ending')


def iir_outages_latest_change():
    data_2d = sql.read_sql(
        (f"Select * from {table_name} where releaseDate >= '{(today() - dt.timedelta(28)).strftime('%Y-%m-%d')}' "
         f"and [offlineCapacity.capacityOffline] > 150000 "
         f"and eventStartDate <= '{(today() + dt.timedelta(7 * 12)).strftime('%Y-%m-%d')}' "
         f"and eventEndDate > '{today().strftime('%Y-%m-%d')}' order by releaseDate, As_of_Date"))
    figs = []
    figs.append("<div style='font-family:Calibri;' >")
    latest_release = data_2d[["eventId", "eventType", "eventStartDate", "eventEndDate", "eventDuration", "plantName",
                             "plantPhysicalAddress.countryName", "tradingRegionName", "releaseDate", "offlineCapacity.capacityOffline"]]
    latest_release.columns = ["ID", "Type", "Start", "End", "Duration", "Plant", "Country", "Region", "Release", "Capacity (kbd)"]
    latest_release["Capacity (kbd)"] = latest_release["Capacity (kbd)"] / 1000
    for idx, row in latest_release.iterrows():
        latest_release.loc[idx, "ID"] = str(latest_release.loc[idx, "ID"])
        if row["Country"] == "Republic of Korea - South Korea":
            latest_release.loc[idx, "Country"] = "Korea"
    latest_table = table.html_format(df=latest_release, precision=0,
        header="Latest releases of CDU turnarounds for next 12 weeks (last 4w, capacity > 150kbd)",
        format_column={
            "ID": {"width": "80px", "text-align": "center"},
            "Type": {"width": "80px", "text-align": "center"},
            "Start": {"width": "120px", "text-align": "center"},
            "End": {"width": "120px", "text-align": "center"},
            "Duration": {"width": "80px", "text-align": "center"},
            "Plant": {"width": "160px", "text-align": "center"},
            "Country": {"width": "80px", "text-align": "center"},
            "Region": {"width": "100px", "text-align": "center"},
            "Release": {"width": "80px", "text-align": "center"},
            "Capacity (kbd)": {"width": "120px", "text-align": "center"}}, format_row=None)
    figs.append(latest_table)
    release_date_list = pd.date_range(today()-dt.timedelta(7), today())
    all_event_data_range = pd.DataFrame()
    for i in release_date_list:
        _temp_data = iir_outages_change(release_date=i, range_in_weeks=12)
        all_event_data_range = pd.concat([all_event_data_range, _temp_data.to_frame(i)], axis=1)
    all_event_data_range_1 = all_event_data_range.iloc[:, -2:].sum(axis=1)
    all_event_data_range_2 = all_event_data_range.sum(axis=1)
    recent_events = all_event_data_range_2.to_frame("Last 7d")
    recent_events = _unrecovered('IIR outages 587: clipped recent event date-window upper bound', recent_events)
    latest_chart = chart.line_chart(df=recent_events, title="Last 2d and 7d change of next 12w turnarounds (kbd)", tickformat=False)
    latest_chart.add_vline(x=today(), line_width=2, line_dash="dashdot", line_color="green")
    _unrecovered('IIR outages 594–600: unphotographed chart additions before visible opacity=0.25, line_width=0')
    figs.append(latest_chart)
    return latest_table, latest_chart


def iir_outages_change(release_date, range_in_weeks=12):
    data = sql.read_sql(f"Select * from {table_name} order by releaseDate, As_of_Date")
    data_1d = sql.read_sql(
        (f"Select * from {table_name} where releaseDate = '{release_date.strftime('%Y-%m-%d')}' "
         f"and eventStartDate <= '{(release_date + dt.timedelta(7 * range_in_weeks)).strftime('%Y-%m-%d')}' "
         f"and eventEndDate > '{release_date.strftime('%Y-%m-%d')}' order by releaseDate, As_of_Date"))
    if len(data_1d) > 0:
        all_event_1d = pd.DataFrame()
        for idx, row in data_1d.iterrows():
            event = data.loc[(data["eventId"] == row["eventId"]) & (data["releaseDate"] <= row["releaseDate"]), :]
            event = event.iloc[-2:, :]
            one_event = pd.DataFrame()
            for idx, row in event.iterrows():
                dts = pd.date_range(row["eventStartDate"], row["eventEndDate"])
                event_1 = pd.DataFrame(0, index=dts, columns=[row["releaseDate"]])
                if row["eventStatusDesc"] != "Cancelled":
                    event_1.loc[:, :] = row["offlineCapacity.capacityOffline"]
                try:
                    one_event = pd.concat([one_event, event_1], axis=1)
                except:
                    print("error")
            one_event.fillna(0, inplace=True)
            if len(event) == 1:
                all_event_1d = pd.concat([all_event_1d, one_event.iloc[:, -1].to_frame(row["eventId"])], axis=1)
            else:
                all_event_1d = pd.concat([all_event_1d, one_event.diff(axis=1).iloc[:, -1].to_frame(row["eventId"])], axis=1)
        all_event_1d.fillna(0, inplace=True)
        all_event_1d = all_event_1d.sum(axis=1)
        return all_event_1d / 1000
    else:
        return pd.Series(dtype='float64')


def create_table(data_ori, sub_title, data_7d_ori=None, unplan=None, replace=False, start_date=None):
    data = data_ori.copy()
    if data_7d_ori is not None:
        data_7d = data_7d_ori.copy()
    if start_date is None:
        start_date = dt.datetime(2018, 1, 1)
    if today().month > 10:
        end_date = dt.datetime(today().year + 1, 12, 31)
    else:
        end_date = dt.datetime(today().year, 12, 31)
    if unplan is not None:
        unplan_ = unplan.loc[(unplan.index >= start_date) & (unplan.index <= end_date), :]
        for col in unplan_.columns:
            _unrecovered('IIR outages 655–659: unphotographed annual unplanned-outage conversion and index preparation')
            dby.set_index('date', inplace=True)
            if 2020 in dby.columns:
                dby = dby.drop(2020, axis=1)
            if 2021 in dby.columns:
                dby = dby.drop(2021, axis=1)
            if 2022 in dby.columns:
                dby = dby.drop(2022, axis=1)
            dby_ = dby.iloc[:, :-1].mean(axis=1)
            if today().month > 10:
                dby1 = ts.data_by_year(df=unplan_[col], freq="D")
                dts1 = pd.date_range(start=dt.datetime(dby1.columns[-2], 1, 1),
                    end=_unrecovered('IIR outages 671: clipped dts1 end datetime'))
                dby1 = dby1.iloc[:len(dts1), :]
                dby1['date'] = dts1
                dby1.set_index('date', inplace=True)
                if 2020 in dby1.columns:
                    dby1 = dby1.drop(2020, axis=1)
                if 2021 in dby1.columns:
                    dby1 = dby1.drop(2021, axis=1)
                if 2022 in dby1.columns:
                    dby1 = dby1.drop(2022, axis=1)
                dby_1 = dby1.iloc[:, :-2].mean(axis=1)
                dby_ = pd.concat([dby_1.loc[dby_1.index > today()], dby_], axis=0)
            if data_7d_ori is None:
                if replace:
                    _unrecovered('IIR outages 685: clipped current-data future-outage replacement', data, col, dby_)
                else:
                    data[col] = data[col] + dby_.loc[dby_.index > today()].reindex(data.index).fillna(0)
            else:
                if replace:
                    _unrecovered('IIR outages 690–691: clipped current and historical outage replacement', data, data_7d, col, dby_)
                else:
                    data[col] = data[col] + dby_.loc[dby_.index > today()].reindex(data.index).fillna(0)
                    data_7d[col] = data_7d[col] + dby_.loc[dby_.index > today()].reindex(data_7d.index).fillna(0)
    table_data = pd.DataFrame(0, index=data.columns, columns=["Current", "Week 1 chg", "Week 2 chg", "Week 3 chg", "Week 4 chg",
        "Next 4w chg", "Next 4-8w chg", "Avg of next 4w", "Avg of next 4-8w"])
    data_4wm = data.rolling(7*4).mean().shift(-7*4)
    data_4wd = data.diff(7*4).shift(-7*4)
    data_wd = data.diff(7).shift(-7)
    table_data.loc[:, "Current"] = data.loc[data.index == today(), :].iloc[-1]
    table_data.loc[:, "Week 1 chg"] = data_wd.loc[data_wd.index == today(), :].iloc[-1]
    table_data.loc[:, "Week 2 chg"] = data_wd.loc[data_wd.index == today() + dt.timedelta(7), :].iloc[-1]
    table_data.loc[:, "Week 3 chg"] = data_wd.loc[data_wd.index == today() + dt.timedelta(14), :].iloc[-1]
    table_data.loc[:, "Week 4 chg"] = data_wd.loc[data_wd.index == today() + dt.timedelta(21), :].iloc[-1]
    table_data.loc[:, "Next 4w chg"] = data_4wd.loc[data_4wd.index == today(), :].iloc[-1]
    table_data.loc[:, "Next 4-8w chg"] = data_4wd.shift(-28).loc[data_4wd.index == today(), :].iloc[-1]
    table_data.loc[:, "Avg of next 4w"] = data_4wm.loc[data_4wm.index == today(), :].iloc[-1]
    table_data.loc[:, "Avg of next 4-8w"] = data_4wm.shift(-28).loc[data_4wm.index == today(), :].iloc[-1]
    df_mean_std_cur = ts.historical_mean_std(
        data.loc[(data.index >= start_date) & (data.index <= today() + dt.timedelta(56))],
        seasonal=5,
        rank_date=today(), drop_years=[2020, 2021])
    table_data.loc[:, 'mean_cur'] = df_mean_std_cur.loc[:, 'mean']
    table_data.loc[:, 'std_cur'] = df_mean_std_cur.loc[:, 'std']
    df_mean_std_cur = ts.historical_mean_std(
        data_4wm.loc[(data_4wm.index >= start_date) & (data_4wm.index <= today() + dt.timedelta(56))], seasonal=5,
        rank_date=today(), drop_years=[2020, 2021])
    table_data.loc[:, 'mean_4wm'] = df_mean_std_cur.loc[:, 'mean']
    table_data.loc[:, 'std_4wm'] = df_mean_std_cur.loc[:, 'std']
    df_mean_std_cur = ts.historical_mean_std(
        data_4wm.shift(-28).loc[(data_4wm.index >= start_date) & (data_4wm.index <= today() + dt.timedelta(56))], seasonal=5,
        rank_date=today(), drop_years=[2020, 2021])
    table_data.loc[:, 'mean_48wm'] = df_mean_std_cur.loc[:, 'mean']
    table_data.loc[:, 'std_48wm'] = df_mean_std_cur.loc[:, 'std']
    df_mean_std_cur = ts.historical_mean_std(
        data_4wd.loc[(data_4wd.index >= start_date) & (data_4wd.index <= today() + dt.timedelta(56))], seasonal=5,
        rank_date=today(), drop_years=[2020, 2021])
    table_data.loc[:, 'mean_4wd'] = df_mean_std_cur.loc[:, 'mean']
    table_data.loc[:, 'std_4wd'] = df_mean_std_cur.loc[:, 'std']
    df_mean_std_cur = ts.historical_mean_std(
        data_4wd.shift(-28).loc[(data_4wd.index >= start_date) & (data_4wd.index <= today() + dt.timedelta(56))],
        seasonal=5, rank_date=today(), drop_years=[2020, 2021])
    table_data.loc[:, 'mean_48wd'] = df_mean_std_cur.loc[:, 'mean']
    table_data.loc[:, 'std_48wd'] = df_mean_std_cur.loc[:, 'std']
    table_data.index.name = "Region"
    table_data.reset_index(inplace=True, drop=False)
    html_table = table.html_format(df=table_data, precision=0,
        hide_cols=["mean_cur", "std_cur", "mean_4wm", "std_4wm", "mean_48wm", "std_48wm", "mean_4wd", "std_4wd", "mean_48wd", "std_48wd"],
        format_column={
            "Region": {"width": "100px", "text-align": "center"},
            "Week 1 chg": {"width": "100px", "text-align": "center"},
            "Week 2 chg": {"width": "100px", "text-align": "center"},
            "Week 3 chg": {"width": "100px", "text-align": "center"},
            "Week 4 chg": {"width": "100px", "text-align": "center"},
            "Current": {"width": "80px", "text-align": "center", 'highlight_z': ['Current', 'mean_cur', 'std_cur']},
            "Avg of next 4w": {"width": "120px", "text-align": "center", 'highlight_z': ['Avg of next 4w', 'mean_4wm', 'std_4wm']},
            "Avg of next 4-8w": {"width": "120px", "text-align": "center", 'highlight_z': ['Avg of next 4-8w', 'mean_48wm', 'std_48wm']},
            "Next 4w chg": {"width": "120px", "text-align": "center", 'highlight_z': ['Next 4w chg', 'mean_4wd', 'std_4wd']},
            "Next 4-8w chg": {"width": "120px", "text-align": "center", 'highlight_z': ['Next 4-8w chg', 'mean_48wd', 'std_48wd']}},
        format_row=None)
    data_ = data.copy()
    data_ = data_.loc[(data_.index >= start_date) & (data_.index <= end_date)]
    data_.drop(_unrecovered('IIR outages 760: clipped removal date range beginning January 1 2020', data_), axis=0, inplace=True)
    html_chart = []
    if "World" in data_.columns:
        ea_refinery_world = ea_plots(dataset_id="5239", title="Global Refinery Runs (kbd)")
        ea_refinery_us = ea_plots(dataset_id="1679", title="US Refinery Runs (kbd)")
        ea_refinery_eu = ea_plots(dataset_id="9072,9051", title="EU Refinery Runs (kbd)")
        ea_refinery_asia = ea_plots(dataset_id="1671", title="Asia Refinery Runs (kbd)")
        if data_7d_ori is None:
            outage_chart_new_world = gen_unified_plots(data_[["World"]], sub_title=sub_title)
            outage_chart_new_eu = gen_unified_plots(data_[["EU"]], sub_title=sub_title)
            outage_chart_new_us = gen_unified_plots(data_[["US"]], sub_title=sub_title)
            outage_chart_new_asia = gen_unified_plots(data_[["Asia"]], sub_title=sub_title)
            outage_chart_new_me = gen_unified_plots(data_[["Middle East"]], sub_title=sub_title)
        else:
            outage_chart_new_world = gen_unified_plots(data_[["World"]], data_7d[["World"]], sub_title)
            outage_chart_new_eu = gen_unified_plots(data_[["EU"]], data_7d[["EU"]], sub_title)
            outage_chart_new_us = gen_unified_plots(data_[["US"]], data_7d[["US"]], sub_title)
            outage_chart_new_asia = gen_unified_plots(data_[["Asia"]], data_7d[["Asia"]], sub_title)
            outage_chart_new_me = gen_unified_plots(data_[["Middle East"]], data_7d[["Middle East"]], sub_title)
        outage_chart_new = [[ea_refinery_world, outage_chart_new_world], [ea_refinery_eu, outage_chart_new_eu],
                            [ea_refinery_us, outage_chart_new_us], [ea_refinery_asia, outage_chart_new_asia], ["", outage_chart_new_me]]
    elif "China" in data_.columns:
        if data_7d_ori is None:
            outage_chart_new_ac = gen_unified_plots(data_[["Asia", "China"]], sub_title=sub_title)
            outage_chart_new_ij = gen_unified_plots(data_[["India", "Japan"]], sub_title=sub_title)
        else:
            outage_chart_new_ac = gen_unified_plots(data_[["Asia", "China"]], data_7d[["Asia", "China"]], sub_title)
            outage_chart_new_ij = gen_unified_plots(data_[["India", "Japan"]], data_7d[["India", "Japan"]], sub_title)
        outage_chart_new = [outage_chart_new_ac, outage_chart_new_ij]
    else:
        if data_7d_ori is None:
            outage_chart_new = gen_unified_plots(data_, sub_title=sub_title)
        else:
            outage_chart_new = gen_unified_plots(data_, data_7d, sub_title)
    for col in data_.columns:
        outage_chart = chart.seasonal(df=data_.loc[:, [col]], title=f"{col} daily {sub_title} turnarounds (kdb)",
            drop_years=[2020, 2021], dash_from=today() + relativedelta(days=1), over_year=True, width=750, height=500)
        if data_7d_ori is not None:
            outage_chart.add_trace(go.Scatter(
                x=_unrecovered('IIR outages 814: clipped prior-week chart x date selection', data_7d),
                y=_unrecovered('IIR outages 815: clipped prior-week chart y selection', data_7d, col),
                showlegend=True, name="7d ago", mode="lines", line={"color": "black", "width": 2, "dash": "dash"},
                hovertemplate="%{x|%b/%d} %{y}"), secondary_y=False)
        outage_chart.add_vline(x=dt.datetime(today().year, today().month, today().day), line_width=2,
            **_unrecovered('IIR outages 823: clipped today marker style'))
        outage_chart.add_vrect(x0=dt.datetime(today().year, today().month, today().day),
            x1=dt.datetime(today().year, today().month, today().day) + dt.timedelta(28),
            annotation_text="0-4w", annotation_position="top left", fillcolor="pink", opacity=0.25, line_width=0)
        outage_chart.add_vline(x=dt.datetime(today().year, today().month, today().day) + dt.timedelta(28),
            **_unrecovered('IIR outages 827: clipped four-week marker style'))
        outage_chart.add_vrect(x0=dt.datetime(today().year, today().month, today().day) + dt.timedelta(28),
            x1=dt.datetime(today().year, today().month, today().day) + dt.timedelta(56),
            annotation_text="4-8w", annotation_position="top left", fillcolor="orange", opacity=0.25, line_width=0)
        html_chart.append(outage_chart)
    return html_table, html_chart, outage_chart_new, data


def ea_plots(dataset_id, title):
    runs = dv.energy_aspects(dataset_id=dataset_id, start="2018-01-01")
    runs.set_index("Date", inplace=True)
    runs.index = pd.to_datetime(runs.index)
    if runs.index[-1] < today():
        return chart.seasonal_chart(df=runs.sum(axis=1).to_frame("runs"), title=title, freq="M", height=500, width=750)
    else:
        return chart.seasonal_chart(df=runs.sum(axis=1).to_frame("runs"), title=title, freq="M",
            dash_from=today() + relativedelta(day=1), over_year=True, height=500, width=750)


def gen_unified_plots(data, data_7d=None, sub_title=None):
    plt_columns = data.columns
    plt_data_cols = [data.loc[:, [col]] for col in plt_columns]
    titles = [f"{col} daily {sub_title} turnarounds (kdb)" for col in plt_columns]
    if len(plt_data_cols) == 1:
        width = 750
    else:
        width = 750 + (350 * len(plt_data_cols))
    fig = chart.seasonal_chart_new(df=plt_data_cols, title=titles, drop_years=[2020, 2021],
        dash_from=today() + relativedelta(days=1), over_year=True, width=width, height=500, horizontal_spacing=0.1)
    for i, col in enumerate(plt_columns):
        if data_7d is not None:
            fig.add_trace(go.Scatter(
                x=_unrecovered('IIR outages 883: clipped unified plot historical x date selection', data_7d),
                y=_unrecovered('IIR outages 884: clipped unified plot historical y selection', data_7d, col),
                showlegend=True, name="7d ago", mode="lines", line={"color": "blue", "width": 2, "dash": "dot"},
                hovertemplate="%{x|%b/%d} %{y}"), col=i+1, row=1)
        fig.add_vline(x=dt.datetime(today().year, today().month, today().day), line_width=2,
            **_unrecovered('IIR outages 891: clipped unified current marker style'))
        fig.add_vrect(x0=dt.datetime(today().year, today().month, today().day),
            x1=dt.datetime(today().year, today().month, today().day) + dt.timedelta(28),
            annotation_text="0-4w", annotation_position="top left", fillcolor="pink", opacity=0.25, line_width=0, row=1, col=i+1)
        _unrecovered('IIR outages 895–898: unphotographed unified four/eight-week chart decorations')
    return fig


def iir_outages_old(send_to=None):
    val_date = today()
    if val_date.weekday() > 0:
        send_to = None
    query = [
        "select * from dbo.IIR_CDU_Latest where [plantPhysicalAddress.countryName] = 'U.S.A.' and eventEndDate > '2018-01-01' and eventStatusDesc not in ('Cancelled')",
        "select * from dbo.IIR_CDU_Latest where [plantPhysicalAddress.countryName] = 'U.S.A.' and eventEndDate > '2018-01-01' and eventStatusDesc not in ('Cancelled') and eventType = 'Planned'",
        "select * from dbo.IIR_CDU_Latest where [plantPhysicalAddress.countryName] = 'U.S.A.' and eventEndDate > '2018-01-01' and eventStatusDesc not in ('Cancelled') and tradingRegionName in (" + _unrecovered("IIR outages 912: clipped legacy current US region SQL suffix"),
        "select * from dbo.IIR_CDU_Latest where [plantPhysicalAddress.countryName] = 'U.S.A.' and eventEndDate > '2018-01-01' and eventStatusDesc not in ('Cancelled') and tradingRegionName in (" + _unrecovered("IIR outages 914: clipped legacy current US region SQL suffix"),
        "select * from dbo.IIR_CDU_Latest where [plantPhysicalAddress.countryName] = 'U.S.A.' and eventEndDate > '2018-01-01' and eventStatusDesc not in ('Cancelled') and tradingRegionName in (" + _unrecovered("IIR outages 916: clipped legacy current US region SQL suffix"),
        "select * from dbo.IIR_CDU_Latest where [plantPhysicalAddress.countryName] = 'U.S.A.' and eventEndDate > '2018-01-01' and eventStatusDesc not in ('Cancelled') and tradingRegionName in (" + _unrecovered("IIR outages 918: clipped legacy current US region SQL suffix"),
        "select * from dbo.IIR_CDU_Latest where [plantPhysicalAddress.countryName] = 'India' and eventEndDate > '2018-01-01' and eventStatusDesc not in ('Cancelled')",
        "select * from dbo.IIR_CDU_Latest where [plantPhysicalAddress.countryName] = 'China' and eventEndDate > '2018-01-01' and eventStatusDesc not in ('Cancelled')",
        "select * from dbo.IIR_CDU_Latest where [tradingRegionName] in ('Southeast Asia', 'South Asia', 'North Asia') and eventEndDate > '2018-01-01' and eventStatusDesc not in ('Cancelled')",
        "select * from dbo.IIR_CDU_Latest where eventEndDate > '2018-01-01' and eventStatusDesc not in ('Cancelled')",
        "select * from dbo.IIR_CDU_NWE where eventEndDate > '2018-01-01' and eventStatusDesc not in ('Cancelled')",
        "select * from dbo.IIR_CDU_Med where eventEndDate > '2018-01-01' and eventStatusDesc not in ('Cancelled')",
        "select * from dbo.IIR_CDU_EU_Trading where eventEndDate > '2018-01-01' and eventStatusDesc not in ('Cancelled')",
    ]
    query_1w = [
        "Select * from IIR_CDU tb1 JOIN (Select As_of_date, ROW_NUMBER() OVER (order by As_of_date desc) as RowNumber from IIR_CDU group by As_of_date) tb2 ON tb1.As_of_date = tb2.As_of_date and tb2.RowNumber=7 and tb1.[plantPhysicalAddress.countryName] = 'U.S.A.' and tb1.eventEndDate > '2018-01-01' and tb1.eventStatusDesc not in ('Cancelled')",
        "Select * from IIR_CDU tb1 JOIN (Select As_of_date, ROW_NUMBER() OVER (order by As_of_date desc) as RowNumber from IIR_CDU group by As_of_date) tb2 ON tb1.As_of_date = tb2.As_of_date and tb2.RowNumber=7 and tb1.[plantPhysicalAddress.countryName] = 'U.S.A.' and tb1.eventEndDate > '2018-01-01' and tb1.eventStatusDesc not in ('Cancelled') and tb1.eventType = 'Planned'",
        "Select * from IIR_CDU tb1 JOIN (Select As_of_date, ROW_NUMBER() OVER (order by As_of_date desc) as RowNumber from IIR_CDU group by As_of_date) tb2 ON tb1.As_of_date = tb2.As_of_date and tb2.RowNumber=7 and tb1.[plantPhysicalAddress.countryName] = 'U.S.A.' and tb1.eventEndDate > '2018-01-01' and tb1.eventStatusDesc not in ('Cancelled') and tb1.tradingRegionName in ('III','II')",
        "Select * from IIR_CDU tb1 JOIN (Select As_of_date, ROW_NUMBER() OVER (order by As_of_date desc) as RowNumber from IIR_CDU group by As_of_date) tb2 ON tb1.As_of_date = tb2.As_of_date and tb2.RowNumber=7 and tb1.[plantPhysicalAddress.countryName] = 'U.S.A.' and tb1.eventEndDate > '2018-01-01' and tb1.eventStatusDesc not in ('Cancelled') and tb1.tradingRegionName in ('III')",
        "Select * from IIR_CDU tb1 JOIN (Select As_of_date, ROW_NUMBER() OVER (order by As_of_date desc) as RowNumber from IIR_CDU group by As_of_date) tb2 ON tb1.As_of_date = tb2.As_of_date and tb2.RowNumber=7 and tb1.[plantPhysicalAddress.countryName] = 'U.S.A.' and tb1.eventEndDate > '2018-01-01' and tb1.eventStatusDesc not in ('Cancelled') and tb1.tradingRegionName in ('II')",
        "Select * from IIR_CDU tb1 JOIN (Select As_of_date, ROW_NUMBER() OVER (order by As_of_date desc) as RowNumber from IIR_CDU group by As_of_date) tb2 ON tb1.As_of_date = tb2.As_of_date and tb2.RowNumber=7 and tb1.[plantPhysicalAddress.countryName] = 'U.S.A.' and tb1.eventEndDate > '2018-01-01' and tb1.eventStatusDesc not in ('Cancelled') and tb1.tradingRegionName in ('I')",
        "Select * from IIR_CDU tb1 JOIN (Select As_of_date, ROW_NUMBER() OVER (order by As_of_date desc) as RowNumber from IIR_CDU group by As_of_date) tb2 ON tb1.As_of_date = tb2.As_of_date and tb2.RowNumber=7 and tb1.[plantPhysicalAddress.countryName] = 'India' and tb1.eventEndDate > '2018-01-01' and tb1.eventStatusDesc not in ('Cancelled')",
        "Select * from IIR_CDU tb1 JOIN (Select As_of_date, ROW_NUMBER() OVER (order by As_of_date desc) as RowNumber from IIR_CDU group by As_of_date) tb2 ON tb1.As_of_date = tb2.As_of_date and tb2.RowNumber=7 and tb1.[plantPhysicalAddress.countryName] = 'China' and tb1.eventEndDate > '2018-01-01' and tb1.eventStatusDesc not in ('Cancelled')",
        "Select * from IIR_CDU tb1 JOIN (Select As_of_date, ROW_NUMBER() OVER (order by As_of_date desc) as RowNumber from IIR_CDU group by As_of_date) tb2 ON tb1.As_of_date = tb2.As_of_date and tb2.RowNumber=7 and tb1.tradingRegionName in ('Southeast Asia', 'South Asia', 'North Asia') and tb1.eventEndDate > '2018-01-01' and tb1.eventStatusDesc not in ('Cancelled')",
        "Select * from IIR_CDU tb1 JOIN (Select As_of_date, ROW_NUMBER() OVER (order by As_of_date desc) as RowNumber from IIR_CDU group by As_of_date) tb2 ON tb1.As_of_date = tb2.As_of_date and tb2.RowNumber=7 and tb1.eventEndDate > '2018-01-01' and tb1.eventStatusDesc not in ('Cancelled')",
        ("Select * from IIR_CDU tb1 JOIN (Select As_of_date, ROW_NUMBER() OVER (order by As_of_date desc) as RowNumber from IIR_CDU group by As_of_date) tb2 ON tb1.As_of_date = tb2.As_of_date and tb2.RowNumber=7 and tb1.eventEndDate > '2018-01-01' and tb1.eventStatusDesc not in ('Cancelled') and ((tb1.[plantPhysicalAddress.countryName] IN ('Poland', 'Ireland', 'United Kingdom', 'Sweden', 'Norway', 'Denmark', 'Finland', 'Netherlands', "
         + _unrecovered('IIR outages 981–982: clipped NWE country-list ending and boolean continuation')
         + "or (tb1.[plantPhysicalAddress.countryName] = 'France' AND tradingRegionName = 'Northwest Europe') or (tb1.plantName IN ('Gelsenkirchen Horst Refinery', 'Gelsenkirchen Scholven Refinery', 'Hamburg-Harburg Base Oil Refinery', 'Holborn Refinery', 'Rheinland Godorf Refinery (North)', 'Rheinland Wesseling Refinery (South)', 'Lingen Emsland Refinery', 'Schwedt Refinery', 'Heide Refinery', 'Leuna Refinery')))"),
        "Select * from IIR_CDU tb1 JOIN (Select As_of_date, ROW_NUMBER() OVER (order by As_of_date desc) as RowNumber from IIR_CDU group by As_of_date) tb2 ON tb1.As_of_date = tb2.As_of_date and tb2.RowNumber=7 and tb1.eventEndDate > '2018-01-01' and tb1.eventStatusDesc not in ('Cancelled') and ((tb1.[plantPhysicalAddress.countryName] IN ('Italy', 'Greece', 'Spain', 'Portugal', 'Turkey', 'Switzerland', 'Croatia', 'Austria', 'Belgium', 'Bulgaria')) or (tb1.[plantPhysicalAddress.countryName] = 'France' AND tradingRegionName = 'Mediterranean') or (tb1.plantName IN ('Bayernoil Neustadt Refinery', 'Bayernoil Vohburg Refinery', 'Burghausen Refinery', 'Ingolstadt Refinery', 'MiRO Refinery Karlsruhe')))",
    ]
    pages = ['Total_USA', 'Planned_Only', 'P3_P2', 'P3', 'P1', 'P2', 'India', 'China', 'Asia', 'World', 'NWE', 'Med', 'EU']
    countries = ['USA Total(kb/d)', 'USA Planned Only(kb/d)', 'P3 and P2 (kb/d)', 'P3 Only (kb/d)', 'P1 Only (kb/d)',
                 'P2 Only (kb/d)', 'India', 'China', 'Asia', 'Asia(ex PG)+ EU + US', 'NWE', 'Med', 'EU']
    figcountries = ['USA Total(kb/d)', 'USA Planned Only(kb/d)', 'P3 Only (kb/d)', 'China', 'Asia',
                    'Asia(ex PG)+ EU + US', 'NWE', 'Med', 'EU']
    tbltoemail = pd.DataFrame(columns=['Country', 'Week 1 change', 'Week 2 change', 'Week 3 change', 'Week 4 change',
        '4 week change', 'average 4 week change (2018-2022)', '4-8 week change', 'average 4-8 week change (2018-2022)'])
    weeklyemailcharts = {}
    for i in range(0, len(query)):
        print(i)
        print(pages[i])
        total_USA = sql.read_sql(query[i])
        test = pd.date_range(start='2018-01-01', end='2026-01-01')
        newdata = pd.Series(0, index=test)
        for idx, row in total_USA.iterrows():
            test = pd.date_range(start=row.eventStartDate, end=row.eventEndDate)
            tbl = pd.Series(row['offlineCapacity.capacityOffline'], index=test)
            newdata = newdata.add(tbl, fill_value=0)
        newdata = newdata.to_frame('Cap_offline')
        if i == 0:
            us_outage = newdata.copy()
        newdata['day'] = newdata.index.dayofyear
        newdata['day_of_month'] = newdata.index.day
        newdata['month'] = newdata.index.month
        newdata['year'] = newdata.index.year
        newdata['week'] = newdata.index.isocalendar().week
        newdata_ = newdata.copy()
        newdata_mean = newdata_.groupby(["year", "week"])["Cap_offline"].mean() / 1000
        if today().month < 11:
            newdata = _unrecovered('IIR outages 1033: clipped annual plot lower date filter', newdata)
        else:
            newdata = _unrecovered('IIR outages 1035: clipped extended annual plot lower date filter', newdata)
        daily_pivot = pd.pivot_table(newdata, values='Cap_offline', index='day', columns='year')
        fig = daily_pivot.plot()
        fig.add_vline(x=dt.datetime.now().timetuple().tm_yday, line_width=2, line_dash="dashdot",
            **_unrecovered('IIR outages 1038: clipped daily marker line color'))
        fig.update_layout(title='Daily Turnarounds for {}'.format(countries[i]), width=900,
            height=_unrecovered('IIR outages 1039: clipped daily chart height beginning 70'))
        weekly_pivot = pd.pivot_table(newdata, values='Cap_offline', index='week', columns='year',
            aggfunc='mean')
        z = val_date.isocalendar()[1]
        sloc = newdata_mean.index.get_loc((val_date.year, z))
        maint = newdata_mean.iloc[sloc]
        maint2 = newdata_mean.iloc[sloc + 4]
        maint3 = newdata_mean.iloc[sloc + 8]
        w1chg = newdata_mean.iloc[sloc + 1] - newdata_mean.iloc[sloc]
        w2chg = newdata_mean.iloc[sloc + 2] - newdata_mean.iloc[sloc + 1]
        w3chg = newdata_mean.iloc[sloc + 3] - newdata_mean.iloc[sloc + 2]
        w4chg = newdata_mean.iloc[sloc + 4] - newdata_mean.iloc[sloc + 3]
        maint_change = maint2 - maint
        maint_change2 = maint3 - maint2
        slocs = [newdata_mean.index.get_loc((x, z)) for x in [2018, 2019, 2022]]
        avg1 = newdata_mean.iloc[slocs].mean()
        avg2 = newdata_mean.iloc[[x + 4 for x in slocs]].mean()
        avg3 = newdata_mean.iloc[[x + 8 for x in slocs]].mean()
        average_hist = avg2 - avg1
        average_hist3 = avg3 - avg2
        tblemail = {'Country': [countries[i]], 'Week 1 change': [w1chg], 'Week 2 change': [w2chg],
            'Week 3 change': [w3chg], 'Week 4 change': [w4chg], '4 week change': [maint_change],
            'average 4 week change (2018-2022)': [average_hist], '4-8 week change': [maint_change2],
            'average 4-8 week change (2018-2022)': [average_hist3]}
        df = pd.DataFrame(data=tblemail)
        tbltoemail = pd.concat([tbltoemail, df], axis=0)
        if 2020 in weekly_pivot.columns:
            weekly_pivot.drop([2020], axis=1, inplace=True)
        if 2021 in weekly_pivot.columns:
            weekly_pivot.drop([2021], axis=1, inplace=True)
        figweekly = _unrecovered('IIR outages 1075–1078: unphotographed weekly chart initialization and current-year trace; only final line styling is visible', weekly_pivot, dict(width=3, color='black'))
        if i < 12:
            data_1w = sql.read_sql(query_1w[i])
        else:
            data_1w = pd.concat([data_1w_nwe, data_1w_med], axis=0)
        if i == 10:
            data_1w_nwe = data_1w.copy()
        if i == 11:
            data_1w_med = data_1w.copy()
        new_data_1w = pd.Series(0, index=test)
        for idx, row in data_1w.iterrows():
            test = pd.date_range(start=row.eventStartDate, end=row.eventEndDate)
            tbl = pd.Series(row['offlineCapacity.capacityOffline'], index=test)
            new_data_1w = new_data_1w.add(tbl, fill_value=0)
        new_data_1w = new_data_1w.to_frame('Cap_offline')
        new_data_1w['day'] = new_data_1w.index.dayofyear
        new_data_1w['day_of_month'] = new_data_1w.index.day
        new_data_1w['month'] = new_data_1w.index.month
        new_data_1w['year'] = new_data_1w.index.year
        new_data_1w['week'] = new_data_1w.index.isocalendar().week
        if today().month < 11:
            new_data_1w = new_data_1w.loc[new_data_1w.index < dt.datetime(today().year + 1, 1, 1)]
        else:
            new_data_1w = new_data_1w.loc[new_data_1w.index < dt.datetime(today().year + 2, 1, 1)]
        weekly_pivot_1w = pd.pivot_table(new_data_1w, values='Cap_offline', index='week', columns='year',
                                       aggfunc='mean')
        figweekly.add_trace(go.Scatter(x=weekly_pivot.index, y=weekly_pivot_1w.iloc[:, -1],
            showlegend=_unrecovered('IIR outages 1110: clipped prior-week trace legend flag'),
            name=str(weekly_pivot.columns[-1]) + ' 1w ago', mode='lines',
            line=dict(width=2, color='black', dash='dash')))
        figweekly.add_vline(x=val_date.isocalendar()[1], line_width=2, line_dash='dashdot',
            line_color=_unrecovered('IIR outages 1114: clipped weekly date marker color'))
        figweekly.add_vrect(x0=val_date.isocalendar()[1], x1=val_date.isocalendar()[1] + 4,
            annotation_text='next 4 weeks', annotation_position='top left',
            fillcolor=_unrecovered('IIR outages 1116: clipped four-week shading color'),
            opacity=0.25, line_width=0)
        figweekly.update_layout(title='Weekly Turnarounds for {}'.format(countries[i]), width=900,
            height=_unrecovered('IIR outages 1118: clipped weekly chart height'))
        if (countries[i] in (figcountries)):
            weeklyemailcharts[i] = figweekly
        tblemail = val_date.isocalendar()[1]
        monthly_pivot = pd.pivot_table(newdata, values='Cap_offline', index='month', columns='year',
            aggfunc=_unrecovered('IIR outages 1122: clipped monthly aggregation value'))
        figmonthly = monthly_pivot.plot()
        figmonthly.update_layout(title='Monthly Turnarounds for {}'.format(countries[i]), width=900,
            height=_unrecovered('IIR outages 1124: clipped monthly chart height'))
        with open(convert_path_to_linux('{}/oil/iir/{}.html'.format(html_path, pages[i])), 'w') as f:
            f.write(fig.to_html(full_html=False, include_plotlyjs='cdn'))
            f.write(figweekly.to_html(full_html=False, include_plotlyjs='cdn'))
            f.write(figmonthly.to_html(full_html=False, include_plotlyjs='cdn'))
    tbs = []
    tbs.append(table.html_text(f"Updated at {dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}<br>"))
    worldtbl = tbltoemail.loc[tbltoemail['Country'].isin(
        ['Asia(ex PG)+ EU + US', 'USA Total(kb/d)',
         *_unrecovered('IIR outages 1133: clipped remaining world-table country selection')])]
    worldtbl.replace('Asia(ex PG)+ EU + US', 'World', inplace=True)
    worldtbl.reset_index(inplace=True, drop=True)
    worldtbl_html = table.html_table(worldtbl, precision=0,
        format_column={'Country': {'width': '140px', 'text-align': 'center'},
                       tuple(worldtbl.columns[1:]): {'width': '140px', 'text-align': 'center'}})
    worldtbl_html = worldtbl_html.replace('USA Total(kb/d)',
        f'<a href="{html_path}\\oil\\iir\\Total_USA.html">USA Total(kb/d)</a>')
    worldtbl_html = worldtbl_html.replace('Asia', f'<a href="{html_path}\\oil\\iir\\Asia.html">Asia</a>')
    worldtbl_html = worldtbl_html.replace('World', f'<a href="{html_path}\\oil\\iir\\World.html">World</a>')
    worldtbl_html = worldtbl_html.replace('EU', f'<a href="{html_path}\\oil\\iir\\EU.html">EU</a>')
    tbs.append(worldtbl_html)
    tbs.append(weeklyemailcharts[9])
    USAtbl = tbltoemail.loc[tbltoemail['Country'].isin(
        ['USA Total(kb/d)', 'USA Planned Only(kb/d)', 'P3 and P2 (kb/d)', 'P3 Only (kb/d)', 'P1 Only (kb/d)',
         'P2 Only (kb/d)'])]
    USAtbl.reset_index(inplace=True, drop=True)
    USAtbl_html = table.html_table(USAtbl, precision=0,
        format_column={'Country': {'width': '140px', 'text-align': 'center'},
                       tuple(USAtbl.columns[1:]): {'width': '140px', 'text-align': 'center'}})
    USAtbl_html = USAtbl_html.replace('USA Total(kb/d)',
        f'<a href="{html_path}\\oil\\iir\\Total_USA.html">USA Total(kb/d)</a>')
    USAtbl_html = USAtbl_html.replace('USA Planned Only(kb/d)',
        f'<a href="{html_path}\\oil\\iir\\Planned_Only.html">USA Planned Only(kb/d)</a>')
    USAtbl_html = USAtbl_html.replace('P3 and P2 (kb/d)',
        f'<a href="{html_path}\\oil\\iir\\P3_P2.html">P3 and P2 (kb/d)</a>')
    USAtbl_html = USAtbl_html.replace('P3 Only (kb/d)', f'<a href="{html_path}\\oil\\iir\\P3.html">P3 Only (kb/d)</a>')
    USAtbl_html = USAtbl_html.replace('P1 Only (kb/d)', f'<a href="{html_path}\\oil\\iir\\P1.html">P1 Only (kb/d)</a>')
    USAtbl_html = USAtbl_html.replace('P2 Only (kb/d)', f'<a href="{html_path}\\oil\\iir\\P2.html">P2 Only (kb/d)</a>')
    tbs.append(USAtbl_html)
    tbs.append(weeklyemailcharts[0])
    actual_runs = bbg.bdh('DOEPCRIN Index', ['PX_LAST'], sdate=today() - relativedelta(years=1),
        edate=_unrecovered('IIR outages 1170: clipped US actual-runs end date'))
    us_outage = us_outage.reindex(actual_runs.index) / 1000
    forecast_runs = 17400 - us_outage
    us_runs = pd.concat([actual_runs, forecast_runs], axis=1)
    us_runs.columns = ['Actual runs', 'IIR runs']
    tbs.append(chart.line_chart(us_runs, title='US actual vs IIR runs'))
    EUtbl = tbltoemail.loc[tbltoemail['Country'].isin(['EU', 'NWE', 'Med'])]
    EUtbl.reset_index(inplace=True, drop=True)
    EUtbl_html = table.html_table(EUtbl, precision=0,
        format_column={'Country': {'width': '140px', 'text-align': 'center'},
                       tuple(EUtbl.columns[1:]): {'width': '140px', 'text-align': 'center'}})
    EUtbl_html = EUtbl_html.replace('NWE', f'<a href="{html_path}\\oil\\iir\\NWE.html">NWE</a>')
    EUtbl_html = EUtbl_html.replace('Med', f'<a href="{html_path}\\oil\\iir\\Med.html">Med</a>')
    EUtbl_html = EUtbl_html.replace('EU', f'<a href="{html_path}\\oil\\iir\\EU.html">EU</a>')
    tbs.append(EUtbl_html)
    tbs.append(weeklyemailcharts[12])
    asiatbl = tbltoemail.loc[tbltoemail['Country'].isin(['Asia', 'China', 'India'])]
    asiatbl.reset_index(inplace=True, drop=True)
    asiatbl_html = table.html_table(asiatbl, precision=0,
        format_column={'Country': {'width': '140px', 'text-align': 'center'},
                       tuple(asiatbl.columns[1:]): {'width': '140px', 'text-align': 'center'}})
    _unrecovered('IIR outages 1195–1199: unphotographed Asia table links and email assembly', asiatbl_html)
    china_state = bbg.bdh('CRCRSOER Index', ['PX_LAST'], sdate=dt.datetime(2021, 1, 1), edate=today())
    dts1 = pd.bdate_range(dt.datetime(2021, 1, 1), today(), freq='W-THU')
    china_state = china_state.reindex(dts1)
    china_state.fillna(method='ffill', inplace=True)
    tbs.append(chart.seasonal(df=china_state, title='China State Owned Refineries Run Rates', freq='W'))
    shandong = bbg.bdh('CRCRSDIR Index', ['PX_LAST'], sdate=dt.datetime(2018, 1, 1), edate=today())
    dts2 = pd.bdate_range(dt.datetime(2018, 1, 1), today(), freq='W-FRI')
    shandong = shandong.reindex(dts2)
    shandong.fillna(method='ffill', inplace=True)
    tbs.append(chart.seasonal(df=shandong, title='China Shandong Independent Refineries Run Rates', freq='W'))
    table.figures_to_html(
        [table.html_text(report_name, style='font-family:Calibri;', tag='h1')] + tbs,
        f'{html_path}\\oil\\{file_name}.html', task_name=report_name)
    if send_to is not None:
        if today().weekday() in [1, 3]:
            send_email(send_to=send_to, subject=report_name, body=tbs, html_path=f'{html_path}\\oil\\{file_name}.html')


def refinery_capacity():
    all_events = ts.read_csv(f"{data_path}\\IIR_capacity\\all_events_{today().strftime('%Y%m%d')}.csv",
        **_unrecovered('IIR outages 1223: clipped CSV arguments beginning index'))
    ref_plants = sql.read_sql("Select Distinct associatedPlantId from IIR_CDU_new where unitTypeGroup = 'C"
        + _unrecovered('IIR outages 1225: clipped crude-unit SQL suffix'))
    global_capacity = pd.DataFrame()
    pd.options.mode.chained_assignment = None
    for plant in ref_plants.iloc[:, 0].to_list():
        print(plant)
        one_plant = sql.read_sql("Select distinct * from IIR_CDU_new where unitTypeGroup = 'Crude' and as"
            + _unrecovered('IIR outages 1231: clipped per-plant SQL predicate', plant))
        plant_capacity = pd.DataFrame()
        for i in one_plant['unitId'].unique():
            one_unit = one_plant.loc[one_plant['unitId'] == i, :].sort_values(
                ['associatedEntityStartDate',
                 *_unrecovered('IIR outages 1235: clipped remaining sort columns or arguments')])
            events = all_events[[str(x) for x in one_unit['eventId'].unique()]]
            events.replace(0, np.nan, inplace=True)
            unit_capacity = events.sum(axis=1) / events.count(axis=1)
            unit_capacity.fillna(method='ffill', inplace=True)
            unit_capacity.fillna(method='bfill', inplace=True)
            plant_capacity = pd.concat([plant_capacity, unit_capacity], axis=1)
        plant_capacity.columns = one_plant['unitId'].unique()
        global_capacity = pd.concat([global_capacity, plant_capacity.sum(axis=1).to_frame(plant)], axis=1)
    pd.options.mode.chained_assignment = 'warn'
    global_capacity.to_csv(f"{data_path}\\IIR_capacity\\global_capacity_{today().strftime('%Y%m%d')}.csv")
    global_capacity.to_csv(f'{data_path}\\IIR_capacity\\global_capacity.csv')


def refinery_capacity_platts():
    POSTGRES_DB = os.environ['PLATTS_POSTGRES_URL']
    engine = create_engine(POSTGRES_DB)
    refinery_info = pd.read_sql_query('select * from public.refinery', con=engine)
    refinery_data = pd.read_sql_query('select * from public.capacity', con=engine)
    capacity = refinery_data.pivot_table(index='date', columns='refinery_id', values='capacity')
    capacity.index = pd.to_datetime(capacity.index)
    region_dict = {
        'EU': {'region_name': ('East Europe', 'NWE', 'MED')},
        'US': {'region_name': ('U.S.',)},
        'Asia': {'region_name': ('East Asia', 'South Asia', 'China', 'Japan')},
        'Middle East': {'region_name': ('Middle East',)},
        'NWE': {'region_name': ('NWE',)},
        'MED': {'region_name': ('MED',)},
        'P2 and P3': {'padd': ('PADD III', 'PADD II')},
        'P2': {'padd': ('PADD II',)},
        'China': {'country_name': ('China',)},
        'India': {'country_name': ('India',)},
        'Japan': {'country_name': ('Japan',)},
        'Africa': {'region_name': ('Africa',)},
        'ANZ': {'region_name': ('ANZ',)},
        'Canada': {'region_name': ('Canada',)},
        'FSU': {'region_name': ('FSU',)},
        'Latin America': {'region_name': ('Latin America',)},
        'World': {},
    }
    total_capacity = pd.DataFrame()
    for k, v in region_dict.items():
        if k == 'World':
            ref_cap = total_capacity[['EU', 'US', 'Asia', 'Middle East']].sum(axis=1)
        else:
            ref_id = refinery_info.loc[refinery_info[next(iter(v))].isin(v[next(iter(v))]), 'refinery_id']
            ref_id_filter = list(set(ref_id) & set(capacity.columns))
            ref_cap = capacity[ref_id_filter].sum(axis=1)
        total_capacity = pd.concat([total_capacity, ref_cap.to_frame(k)], axis=1)
    total_capacity['Other'] = capacity.sum(axis=1) - total_capacity['World']
    return total_capacity


def update():
    download_iir(unitTypeGroup='Crude')
    download_iir(unitTypeGroup='Cat Cracker')
    download_iir(unitTypeGroup='Hydrocracking')
    process_eventid()
    process_eventid(capacity=True)
    refinery_capacity()
    iir_outages(send_to=send_to)


if __name__ == '__main__':
    update()
