import pandas as pd
import numpy as np
import datetime as dt
import sys
import os
from dateutil.relativedelta import relativedelta
from plotly.subplots import make_subplots
import plotly.graph_objs as go
import plotly.express as px
import ecm.cmds.data as dv
import ecm.cmds.sql as sql
import ecm.cmds.kpler as kpler
import ecm.cmds.time_series as ts
import ecm.cmds.table as table
import ecm.cmds.chart as chart
from ecm.cmds.config import root_path
from ecm.cmds._email import send_email
from ecm.cmds.config import html_path, oil_group
from ecm.cmds.cdr import today

send_to = oil_group
report_name = "Kpler Imports Exports"
file_name = "kpler_imports_exports"  # without .py
file_path = f"{root_path}\\autoreports\\reports\\oil\\{file_name}.py"


def _missing_photo_text(lines, *visible_fragments):
    raise NotImplementedError(f"Unrecoverable photographed text at source lines {lines}")


def add_schedule():
    """
    # schedule to run the report - only need to run once
    """
    sys.path.append(f"{root_path}\\autoreports\\schedule")
    from tasks import WinTaskPoC
    from ecm.atom.wintask.scheduler import ECMWinTask
    from ecm.atom.wintask.utils import Days

    win_task = ECMWinTask(
        days=Days.MONDAY | Days.TUESDAY | Days.WEDNESDAY | Days.THURSDAY | Days.FRIDAY,
        start_datetime=dt.datetime(2022, 7, 1, 9, 34),
        timezone="Europe/London",
        task_name=report_name,
        task=WinTaskPoC(name=f'"{report_name}"', filepath=f'"{file_path}"'),
        background_task=True,
        python_excecutable=r"C:\local\python\miniconda\envs\ecm_cmds\pythonw.exe"
    )
    win_task.create_task()


def get_table_old(data, index_name):
    """
    covnert the last row in data to standard table
    """
    if 'Period End Date' in data.columns:
        data = data.drop(columns=['Period End Date'])
    data.index = pd.to_datetime(data.index)
    df_table = pd.DataFrame(0, index=data.columns, columns=['10day MA', '20day MA', '3month MA', 'Y-1 20d Avg', '5yr 20d Avg'])
    df_table.loc[:, '10day MA'] = data.rolling(10).mean().iloc[-1]
    df_table.loc[:, '20day MA'] = data.rolling(20).mean().iloc[-1]
    df_table.loc[:, '3month MA'] = data.rolling(90).mean().iloc[-1]
    df_table.loc[:, 'Y-1 20d Avg'] = _missing_photo_text(61, 'ts.historical_data_on_date', data.rolling(20).mean(), data.index[-1])
    df_table.loc[:, '5yr 20d Avg'] = ts.historical_data_on_date(data.rolling(20).mean(), date=data.index[-1]).iloc[-6:-1].mean()
    df_mean_std = ts.historical_mean_std(data, window=20, seasonal=None)
    df_table.loc[:, 'mean'] = df_mean_std.loc[:, 'mean']
    df_table.loc[:, 'std'] = df_mean_std.loc[:, 'std']
    df_mean_std_5d = ts.historical_mean_std(data.rolling(10).mean(), window=91, seasonal=None)
    df_table.loc[:, 'mean_10d'] = df_mean_std_5d.loc[:, 'mean']
    df_table.loc[:, 'std_10d'] = df_mean_std_5d.loc[:, 'std']
    df_mean_std_20d = ts.historical_mean_std(data.rolling(20).mean(), window=91, seasonal=None)
    df_table.loc[:, 'mean_20d'] = df_mean_std_20d.loc[:, 'mean']
    df_table.loc[:, 'std_20d'] = df_mean_std_20d.loc[:, 'std']
    df_mean_std_5d = ts.historical_mean_std(data.rolling(10).mean(), window=None, seasonal=20)
    df_table.loc[:, 'mean_10d_sea'] = df_mean_std_5d.loc[:, 'mean']
    df_table.loc[:, 'std_10d_sea'] = df_mean_std_5d.loc[:, 'std']
    df_mean_std_20d = ts.historical_mean_std(data.rolling(20).mean(), window=None, seasonal=20)
    df_table.loc[:, 'mean_20d_sea'] = df_mean_std_20d.loc[:, 'mean']
    df_table.loc[:, 'std_20d_sea'] = df_mean_std_20d.loc[:, 'std']
    df_table.loc[:, '_last_update'] = data.index[-1].strftime('%Y-%m-%d')
    df_table.index.name = index_name
    df_table.reset_index(inplace=True)
    return df_table


def get_table(data, index_name):
    """
    covnert the last row in data to standard table
    """
    if 'Period End Date' in data.columns:
        data = data.drop(columns=['Period End Date'])
    data.index = pd.to_datetime(data.index)
    df_table = pd.DataFrame(0, index=data.columns, columns=['10day MA', '20day MA'])
    df_table.loc[:, '10day MA'] = data.rolling(10).mean().iloc[-1]
    df_table.loc[:, '20day MA'] = data.rolling(20).mean().iloc[-1]
    monthly = data.resample("M").mean()
    last_3_month = monthly.iloc[-4:-1, :].sort_index(ascending=False).T
    last_3_month.columns = [x.strftime("%Y-%m") for x in last_3_month.columns]
    df_table = pd.concat([df_table, last_3_month], axis=1)
    quarterly = data.resample("Q").mean()
    last_3_quarter = quarterly.iloc[-4:-1, :].sort_index(ascending=False).T
    last_3_quarter.columns = last_3_quarter.columns.to_period("Q")
    df_table = pd.concat([df_table, last_3_quarter], axis=1)
    df_table.loc[:, 'Y-1 20d Avg'] = _missing_photo_text(108, 'ts.historical_data_on_date', data.rolling(20).mean(), data.index[-1])
    df_table.loc[:, '5yr 20d Avg'] = ts.historical_data_on_date(data.rolling(20).mean(), date=data.index[-1]).iloc[-6:-1].mean()
    df_mean_std = ts.historical_mean_std(data, window=20, seasonal=None)
    df_table.loc[:, 'mean'] = df_mean_std.loc[:, 'mean']
    df_table.loc[:, 'std'] = df_mean_std.loc[:, 'std']
    df_mean_std_5d = ts.historical_mean_std(data.rolling(10).mean(), window=91, seasonal=None)
    df_table.loc[:, 'mean_10d'] = df_mean_std_5d.loc[:, 'mean']
    df_table.loc[:, 'std_10d'] = df_mean_std_5d.loc[:, 'std']
    df_mean_std_20d = ts.historical_mean_std(data.rolling(20).mean(), window=91, seasonal=None)
    df_table.loc[:, 'mean_20d'] = df_mean_std_20d.loc[:, 'mean']
    df_table.loc[:, 'std_20d'] = df_mean_std_20d.loc[:, 'std']
    df_mean_std_5d = ts.historical_mean_std(data.rolling(10).mean(), window=None, seasonal=20)
    df_table.loc[:, 'mean_10d_sea'] = df_mean_std_5d.loc[:, 'mean']
    df_table.loc[:, 'std_10d_sea'] = df_mean_std_5d.loc[:, 'std']
    df_mean_std_20d = ts.historical_mean_std(data.rolling(20).mean(), window=None, seasonal=20)
    df_table.loc[:, 'mean_20d_sea'] = df_mean_std_20d.loc[:, 'mean']
    df_table.loc[:, 'std_20d_sea'] = df_mean_std_20d.loc[:, 'std']
    df_table.loc[:, '_last_update'] = data.index[-1].strftime('%Y-%m-%d')
    df_table.index.name = index_name
    df_table.reset_index(inplace=True)
    return df_table


def alert_table(data, alert, val_d):
    df_alert = pd.DataFrame(columns=['Alert', 'As_of_date'])
    cnt = 0
    for i in data.index:
        if (np.abs((data.loc[i, '10day MA'] - data.loc[i, 'mean_10d']) / data.loc[i, 'std_10d']) > 2 or
                np.abs((data.loc[i, '20day MA'] - data.loc[i, 'mean_20d']) / data.loc[i, 'std_20d']) > 2):
            df_alert.loc[cnt, 'Alert'] = alert
            df_alert.loc[cnt, 'As_of_date'] = val_d
            cnt += 1
    return (df_alert)


def alert_table_seasonal(data, alert, val_d):
    df_alert = pd.DataFrame(columns=['Alert', 'As_of_date'])
    cnt = 0
    for i in data.index:
        if (np.abs((data.loc[i, '10day MA'] - data.loc[i, 'mean_10d_sea']) / data.loc[i, 'std_10d_sea']) > 2 or
                np.abs((data.loc[i, '20day MA'] - data.loc[i, 'mean_20d_sea']) / data.loc[i, 'std_20d_sea']) > 2):
            df_alert.loc[cnt, 'Alert'] = alert
            df_alert.loc[cnt, 'As_of_date'] = val_d
            cnt += 1
    return (df_alert)


def alert_table_countries(data, val_d, region):
    datapanda = []
    for i in range(0, len(data)):
        x = data.iloc[[0]]
        m = 'Check {} Imports within {} imports'.format(data.iloc[i][0], region)
        tableofalerts = alert_table(x, m, val_d)
        datapanda.append(tableofalerts)
    return datapanda


def alert_table_countries_seasonal(data, val_d, region):
    datapanda = []
    for i in range(0, len(data)):
        x = data.iloc[[0]]
        m = 'Check Seasonal {} Imports within {} imports'.format(data.iloc[i][0], region)
        tableofalerts = alert_table_seasonal(x, m, val_d)
        datapanda.append(tableofalerts)
    return datapanda


def clean_table(data, index_name):
    data = data.drop(columns=['mean', 'std', 'mean_10d', 'std_10d', 'mean_20d', 'std_20d',
                              'mean_10d_sea', 'std_10d_sea', 'mean_20d_sea', 'std_20d_sea'])
    data = data.set_index(index_name)
    data = data[(data.T != 0).any()]
    data = data.round()
    data = data.astype(int)
    data = data.reset_index()
    return (data)


def line_figure(data, namettl):
    datarolled = data.rolling(10).mean()
    datagraph = datarolled.iloc[datarolled.index > '2020-01-01']
    fig4 = make_subplots(rows=1, cols=1)
    fig4.add_trace(go.Scatter(x=datagraph.index, y=datagraph['Total'], connectgaps=True, name=namettl,
                              **_missing_photo_text(197, 'mo')), row=1, col=1)
    fig4.update_layout(title=namettl)
    return fig4


def monthly_season(data, namettl):
    data.index = pd.to_datetime(data.index)
    totalpvt = pd.pivot_table(data, values='Total', index=data.index.month, columns=data.index.year,
                              **_missing_photo_text(205, 'aggf'))
    dataPanda = []
    for m in range(0, len(totalpvt.columns)):
        if (m == len(totalpvt.columns) - 1):
            trace = go.Scatter(x=totalpvt.index, y=totalpvt.iloc[:, m], connectgaps=True, name=int(totalpvt.columns[m]),
                               mode='lines+markers', line=dict(width=2, color='black'),
                               marker=dict(size=10, color='white', line=dict(width=2, color='black')))
        else:
            trace = go.Scatter(x=totalpvt.index, y=totalpvt.iloc[:, m], connectgaps=True, name=int(totalpvt.columns[m]),
                               mode='lines')
        dataPanda.append(trace)
    layout2 = go.Layout(title=namettl)
    fig2 = go.Figure(data=dataPanda, layout=layout2)
    fig2.update_layout(coloraxis={'colorscale': 'viridis'})
    return fig2


def get_ea(Country):
    api_key = os.environ["ENERGY_ASPECTS_API_KEY"]
    timeseries_url_csv = _missing_photo_text(226, f'https://api.energyaspects.com/data/timeseries/csv?api_key={api_key}&date_from=')
    Country_refruns = ['UAE', 'Saudi']
    Country_refruns_alias = ['United Arab Emirates', 'Saudi Arabia']
    Country_refmain = ['Saudi']
    Country_refmain_alias = ['Saudi_Arabia']
    country_prod = ['Saudi']
    country_pord_alias = ['Saudi Arabia']
    non_opec_crude_supplies = (
        '1064,1065,1066,1067,1068,1069,1070,1071,1072,1073,1074,1075,'
        '1076,1077,1078,1079,1080,1081,1082,1083,1084,1085,1086,1087,'
        '1088,1089,1090,1091,1092,1093,1094,1095,1096,1097,1098,1099,'
        '1100,1101,1102,1103,1104,1105,1106,1107,1108,1109,1110,1111,'
        '1112,1113,1114,1115,1116,1117,1118,1119,1120,1121,1122,1123,'
        '1124,1125,1126,1127,1128,1129,1130,1131,1132,1133,1134,1135,'
        '1136,1137,1138,1139,1140,1141,1142,1143,1144,1145,1146,1147,'
        '1148,1149,1150,1151,1152,1153,1154,1155,1156,1157,1158,1159,'
        '1160,1161,1162,1163,1164,1165,1166,1167,1168,1169,1170,1171,'
        '1172,1173,1174,1175,1176,1177,1178,1179,1180,1181,1182,1183,'
        '1184,1185,1186,1187,1188,1189,1190,1191,1192,1193,1194,1195,'
        '1196,1197,1198,1199,1200,1201,1202,1203,1204,1205,1206,1207,'
        '1208,1209,1210,1211,1212,1213,1214,1215,1216,1217,1218,1219,'
        '1220,1221,1222,1223,1224,1225,1226,1227,1228,1229,1230,1231,'
        '1232,1233,1234,1235,1236,1237,1238,1239,1240,1241,1242,1243,'
        '1244,1245,1246,1247,1248,1249,1250,1251,1252,1253,1254,1255,'
        '1256,1257,1258,1259,1260,1261,1262,1263,1264,1265,1266,1267,'
        '1268,1269,1270,1271,1272,1273,1274'
    )
    ref_runs = (
        '5269,5241,5240,5239,1575,1576,1577,1578,1579,1580,1581,1582,1583,1584,1585,'
        '1586,1587,1588,1589,1590,1591,1592,1593,1594,1595,1596,1597,1598,1599,1600,'
        '1601,1602,1603,1604,1605,1606,1607,1608,1609,1610,1611,1612,1613,1614,1615,'
        '1616,1617,1618,1619,1620,1634,1635,1573,1636,1637,1638,1639,1640,1641,1642,'
        '1643,1644,1645,1646,1647,1648,1649,1650,1651,1652,1653,1654,1655,1656,1657,'
        '1658,1659,1660,1661,1662,1663,1664,1665,1666,1667,1668,1669,1670,1623,1624,'
        '1625,1626,1627,1629,1630,1631,1632,1677,1678,1679,1673,1674,1675,1676,1628,'
        '1672,1562,1563,1564,1565,1566,1567,1568,1569,1570,1571,1572,1574,1633,1671,'
        '7162,7163,7164,7165,7166,7167,1621,1622,6490'
    )
    maintstr = (
        '6770,6771,6772,6773,6774,6775,6776,6777,6778,6779,6780,6781,6782,6783,6784,6785,'
        '6786,6787,6788,6789,6790,6791,6792,6793,6794,6795,6796,6797,6798,6799,6800,6801,'
        '6802,6803,6804,6805,6806,6807,6808,6809,6810,6811,6812,6813,6814,6815,6816,6817,'
        '6818,6819,6820,6821,6822,6823,6824,6825,6826,6827,6828,6829,6830,6831,6832,6833,'
        '6834,6835,6836,6837,6838,6839,6840,6841,6842,6843,6844,6845,6846,6847,6848,6849,'
        '6850,6851,7045,6852,6853,6854,6855,6856,6857,6858,6859,6860,6861,6862,6863,6864,'
        '6865,6866,6867,6868,6869,6870,6871,6872,6873,6874,6875,6876,6877,6878,6879,6880,'
        '6881,6882,6883,6884,6885,6886,6887,6888,6889,6890,6891,6892,6893,6894,6895,6896,'
        '6897,6898,6899,6900,6901,6902,6903,6904,6905,6906,6907,6908,6909,6910,6911,6912,'
        '6913,6914,6915,6916,6917,6918,6919,6920,6921,6922,6923,6924,6925,6926,6927,6928,'
        '6929,6930,6931,6932,6933,6934,6935,6936,6937,6938,6939,6940,6941,6942,6943,6944,'
        '6945,6946,6947,6948,6949,6950,6951,6952,6953,6954,6955,6956,6957,6958,6959,6960,'
        '6961,6962,6963,6964,6970,6985,6965,6966,6967,6968,6969,6971,6972,6973,6974,6975,'
        '6976,6977,6978,6979,6980,6981,6982,6983,6984,6986,6987,6988,6989,6990,6991,6992,'
        '6993,6994,6995,6996,6997,6998,6999,7000,7001,7002,7003,7004,7005,7006,7007,7008,'
        '7009,7010,7011,7012,7013,7014,7015,7016,7017,7018,7019,7020,7021,7022,7023,7024,'
        '7025,7026,7027,7028,7029,7030,7031,7032,7033,7034,7035,7036,7037,7038,7039,7040,'
        '7041,7042,7043,7044,7046,7047,7048,7049,7050,7051,7052,7053,7054,7055,7056,7057,'
        '7058,7059,7060,7061,7062,7063,7064,7065,7066,7067,7068,7069,7070,7071,7072,7073,'
        '7074,7075,7076,7077,7078,7079,7080,7081,7082,7083,7084,7085,7086,7087,7088,7089,'
        '7090,7091,7092,7093,7094,7095,7096,7097,7098,7099,7100,7101,7102,7103,7104,7105,'
        '7106,7107,7108,7109,7110,7111,7112,7113,7114,7115,7116,7117,7118,7119,7120,7121,'
        '7122,7123,7124,7125,7126,7127,7128,7129,7130,7131,7132,7133,7134,7135,7136,7137,'
        '7138,7139,7140,7141,7142,7143,7144,7145,7146,7147,7148,7149,7150,7151,7152,7153,'
        '7154,7155,7156,7157,7158,7169,7170,7171,7172,7173,7174,7175,7176,7177,7178,7179,'
        '7180,7181,7182,7183,7184,7185,7186,7187,7188,7189,7190,7191,7192,7193,7194,7195,'
        '7196,7197,7198,7199,7200,7201,7202,7203,7204,7205,7206,7207,7208,7209,7210,7211,'
        '7212,7213,7214,7215,7216,7217,7218,7219,7220,7221,7222,7223,7224,7225,7226,7227,'
        '7228,7229,7230,7231,7232,7233,7234,7235,7236,7237,7238,7239,7240,7241,7242,7243,'
        '7244,7245,7246,7247'
    )
    latest_request_string = timeseries_url_csv + '&dataset_id=' + maintstr
    maintenance = pd.read_csv(latest_request_string)
    latest_request_string = timeseries_url_csv + '&dataset_id=' + ref_runs
    runs = pd.read_csv(latest_request_string)
    latest_request_string = timeseries_url_csv + '&dataset_id=' + non_opec_crude_supplies
    crude_supply = pd.read_csv(latest_request_string)
    maint = pd.DataFrame()
    maint['Date'] = maintenance['Date']
    if (Country in Country_refmain):
        z = Country_refmain.index(Country)
        maint_country = Country_refmain_alias[z]
        maint[f'Monthly {Country} Refinery Total Outages aggregation for CDU units in kbd'] = maintenance.loc[
            :, maintenance.columns.str.contains(f"Monthly {maint_country} Refinery Total Outages aggregation for CDU units in kbd")]
    else:
        maint[f'Monthly {Country} Refinery Total Outages aggregation for CDU units in kbd'] = maintenance.loc[
            :, maintenance.columns.str.contains(f"{Country} Refinery Total Outages aggregation for CDU units in kbd")]
    maint = maint.set_index('Date')
    maint.index = pd.to_datetime(maint.index)
    if (Country in Country_refruns):
        x = Country_refruns.index(Country)
        new_country = Country_refruns_alias[x]
        Refinery_runs = runs[['Date', 'Monthly refinery runs for {} in kb/d'.format(new_country)]]
    else:
        Refinery_runs = runs[['Date', 'Monthly refinery runs for {} in kb/d'.format(Country)]]
    Refinery_runs = Refinery_runs.set_index('Date')
    Refinery_runs.index = pd.to_datetime(Refinery_runs.index)
    prod = pd.DataFrame()
    prod['Date'] = crude_supply['Date']
    if 'Monthly {} crude production in kb/d (includes field condensate)'.format(Country) in crude_supply.columns:
        prod['Monthly {} crude production in kb/d (includes field condensate)'.format(Country)] = crude_supply[
            'Monthly {} crude production in kb/d (includes field condensate)'.format(Country)]
    else:
        prod['Monthly {} crude production in kb/d (includes field condensate)'.format(Country)] = 0
    prod = prod.set_index('Date')
    prod.index = pd.to_datetime(prod.index)
    return (maint, Refinery_runs, prod)


def get_ea_countries(listofCountries):
    datapanda = []
    for i in range(0, len(listofCountries)):
        x = listofCountries[i]
        m, r, p = get_ea(x)
        list2 = [m, r, p]
        merged = pd.concat(list2, axis=1)
        datapanda.append(merged)
    return datapanda


def imports_figure(data, Country, maintenance, runs, production, val_d):
    data.index = pd.to_datetime(data.index)
    monthlyimp = pd.DataFrame(data['Total'].resample('MS').mean())
    runs.index = pd.to_datetime(runs.index)
    production.index = pd.to_datetime(production.index)
    test = pd.concat([runs, production, monthlyimp], axis=1)
    test['OilNeeded'] = test['Monthly refinery runs for {} in kb/d'.format(Country)] - test[
        'Monthly {} crude production in kb/d (includes field condensate)'.format(Country)]
    test['Stocks'] = test['Total'] - test['OilNeeded']
    test['Stocks_2ma'] = test['Stocks'].rolling(2).mean()
    test['Month'] = test.index.month
    a = ts.data_by_year(test['Stocks'], freq='M')
    newdata = a.rolling(5, axis=1).mean()
    newdata = newdata[2019]
    newdata.index = range(1, 13)
    test = test.reset_index()
    m = test.merge(newdata, how='right', left_on='Month', right_on=newdata.index)
    m = m.set_index('Date').sort_index()
    test = m.iloc[(m.index > '2021-01-01') & (m.index <= val_d)]
    fig = make_subplots(rows=2, cols=1)
    fig.add_trace(go.Scatter(x=test.index, y=test['Total'], name='Imports'), row=1, col=1)
    fig.add_trace(go.Bar(x=test.index, y=test['OilNeeded'], name='Oil Needed'), row=1, col=1)
    fig.add_trace(
        go.Scatter(x=test.index, y=test['Stocks'], name='Implied builds', line=dict(color='black'),
                   mode=_missing_photo_text(376, 'mode=')), row=2, col=1)
    fig.add_trace(go.Scatter(x=test.index, y=test['Stocks_2ma'], name='2Ma_builds',
                             line=dict(color='grey', dash='dash', width=0.5)), row=2, col=1)
    fig.add_trace(go.Scatter(x=test.index, y=test[2019], name='5yr', line=dict(color='blue', dash='dot')),
                  row=2, col=1)
    return fig


def imports_figure_countries(data, Country, data2, val_d):
    data.index = pd.to_datetime(data.index)
    monthlyimp = pd.DataFrame(data['Total'].resample('MS').mean())
    data2.index = pd.to_datetime(data2.index)
    data3 = data2.merge(monthlyimp['Total'], left_on=data2.index, right_on=monthlyimp.index, how='left',
                        right_index=True)
    data3['OilNeeded'] = data3['Runs'] - data3['Production']
    data3['Stocks'] = data3['Total'] - data3['OilNeeded']
    data3['Stocks_2ma'] = data3['Stocks'].rolling(2).mean()
    data3['Month'] = data3.index.month
    a = ts.data_by_year(data3['Stocks'], freq='M')
    newdata = a.rolling(5, axis=1).mean()
    newdata = newdata[2019]
    newdata.index = range(1, 13)
    data3 = data3.reset_index()
    m = data3.merge(newdata, how='right', left_on='Month', right_on=newdata.index)
    m = m.set_index('Date').sort_index()
    test = m.iloc[(m.index > '2021-01-01') & (m.index <= val_d)]
    fig = make_subplots(rows=2, cols=1)
    fig.add_trace(go.Scatter(x=test.index, y=test['Total'], name='Imports'), row=1, col=1)
    fig.add_trace(go.Bar(x=test.index, y=test['OilNeeded'], name='Oil Needed'), row=1, col=1)
    fig.add_trace(
        go.Scatter(x=test.index, y=test['Stocks'], name='Implied builds', line=dict(color='black'),
                   mode=_missing_photo_text(406, 'mode=')), row=2, col=1)
    fig.add_trace(go.Scatter(x=test.index, y=test['Stocks_2ma'], name='2Ma_builds',
                             line=dict(color='grey', dash='dash', width=0.5)), row=2, col=1)
    fig.add_trace(go.Scatter(x=test.index, y=test[2019], name='5yr', line=dict(color='blue', dash='dot')),
                  row=2, col=1)
    return fig


def imports_figure_with_inv(data, Country, maintenance, runs, production, val_d, inventory):
    data.index = pd.to_datetime(data.index)
    monthlyimp = pd.DataFrame(data['Total'].resample('MS').mean())
    runs.index = pd.to_datetime(runs.index)
    production.index = pd.to_datetime(production.index)
    test = pd.concat([runs, production, monthlyimp, inventory], axis=1)
    test['OilNeeded'] = test['Monthly refinery runs for {} in kb/d'.format(Country)] - test[
        'Monthly {} crude production in kb/d (includes field condensate)'.format(Country)]
    test['Stocks'] = test['Total'] - test['OilNeeded']
    test['Stocks_2ma'] = test['Stocks'].rolling(2).mean()
    test['Month'] = test.index.month
    a = ts.data_by_year(test['Stocks'], freq='M')
    newdata = a.rolling(5, axis=1).mean()
    newdata = newdata[2019]
    newdata.index = range(1, 13)
    test = test.reset_index()
    m = test.merge(newdata, how='right', left_on='Month', right_on=newdata.index)
    m = m.set_index('Date').sort_index()
    test = m.iloc[(m.index > '2021-01-01') & (m.index <= val_d)]
    fig = make_subplots(rows=2, cols=1)
    fig.add_trace(go.Scatter(x=test.index, y=test['Total'], name='Imports'), row=1, col=1)
    fig.add_trace(go.Bar(x=test.index, y=test['OilNeeded'], name='Oil Needed'), row=1, col=1)
    fig.add_trace(
        go.Scatter(x=test.index, y=test['Stocks'], name='Implied builds', line=dict(color='black'),
                   mode=_missing_photo_text(437, 'mode=')), row=2, col=1)
    fig.add_trace(go.Bar(x=test.index, y=test['Change_kbd'], name='Kpler Data', marker_color='lightgrey'),
                  row=2, col=1)
    fig.add_trace(go.Scatter(x=test.index, y=test[2019], name='5yr (2015-2019)',
                             line=dict(color='blue', **_missing_photo_text(440, 'd'))),
                  row=2, col=1)
    return fig


def imports_figure_with_inv_countries(data, Country, data2, val_d, inventory):
    data.index = pd.to_datetime(data.index)
    monthlyimp = pd.DataFrame(data['Total'].resample('MS').mean())
    data2.index = pd.to_datetime(data2.index)
    data3 = data2.merge(monthlyimp['Total'], left_on=data2.index, right_on=monthlyimp.index, how='left',
                        right_index=True)
    data3 = pd.concat([data3, inventory], axis=1)
    data3['OilNeeded'] = data3['Runs'] - data3['Production']
    data3['Stocks'] = data3['Total'] - data3['OilNeeded']
    data3['Stocks_2ma'] = data3['Stocks'].rolling(2).mean()
    data3['Month'] = data3.index.month
    a = ts.data_by_year(data3['Stocks'], freq='M')
    newdata = a.rolling(5, axis=1).mean()
    newdata = newdata[2019]
    newdata.index = range(1, 13)
    data3 = data3.reset_index()
    m = data3.merge(newdata, how='right', left_on='Month', right_on=newdata.index)
    m = m.set_index('Date').sort_index()
    test = m.iloc[(m.index > '2021-01-01') & (m.index <= val_d)]
    fig = make_subplots(rows=2, cols=1)
    fig.add_trace(go.Scatter(x=test.index, y=test['Total'], name='Imports'), row=1, col=1)
    fig.add_trace(go.Bar(x=test.index, y=test['OilNeeded'], name='Oil Needed'), row=1, col=1)
    fig.add_trace(
        go.Scatter(x=test.index, y=test['Stocks'], name='Implied builds', line=dict(color='black'),
                   mode=_missing_photo_text(468, 'mode=')), row=2, col=1)
    fig.add_trace(go.Bar(x=test.index, y=test['Change_kbd'], name='Kpler Data', marker_color='lightgrey'),
                  row=2, col=1)
    fig.add_trace(go.Scatter(x=test.index, y=test[2019], name='5yr (2015-2019)',
                             line=dict(color='blue', **_missing_photo_text(471, 'd'))),
                  row=2, col=1)
    return fig


def go_get_bar(fxlist, FromRegion, ToRegion):
    figbar_lt = _missing_photo_text('477-478', fxlist,
        'Fixtures out of {} to {} by load month'.format(FromRegion, ToRegion))
    figbar_lt.update_traces(xbins_size="M1")
    figbar_lt.update_xaxes(showgrid=True, ticklabelmode="period", dtick="M1", tickformat="%b\n%Y",
                           title=_missing_photo_text(480, 'title='), tickwidth=130)
    figbar_lt.update_yaxes(title="dwt")
    figbar_lt.update_layout(bargap=0.3)
    newcheck = pd.DataFrame(fxlist.groupby(by='Laycan end')['Deadweight (t)'].sum())
    if not newcheck.empty:
        newcheck.index = pd.to_datetime(newcheck.index)
        newcheck['datamtd'] = _missing_photo_text(487,
            newcheck.groupby([newcheck.index.year, newcheck.index.month])['Deadweight (t)'])
        figbar_lt.update_layout(height=600, width=900)
        figbar_lt.update_layout(font=dict(size=10))
        return (figbar_lt)
    else:
        return "Error Data for Fixtures out of {} to {} by load month is None".format(FromRegion, ToRegion)


def go_get_trend(fxlist, FromRegion, ToRegion):
    table = pd.pivot_table(fxlist, values='Deadweight (t)',
                           columns=[pd.to_datetime(fxlist['Reported date']).dt.year,
                                    pd.to_datetime(fxlist['Reported date']).dt.month],
                           index=pd.to_datetime(fxlist['Reported date']).dt.day, aggfunc=np.sum)
    newtablepivot = table.cumsum()
    newtablepivot = newtablepivot.iloc[:, -14:]
    dataPandafix = []
    for j in range(0, len(newtablepivot.columns)):
        if (j == len(newtablepivot.columns) - 1):
            trace = go.Scatter(x=newtablepivot.index, y=newtablepivot.iloc[:, j], connectgaps=True,
                               name=str(newtablepivot.columns[j]), mode='lines+markers',
                               line=dict(width=2, color='black'),
                               marker=dict(size=10, color='white', line=dict(width=2, color='black')))
        else:
            trace = go.Scatter(x=newtablepivot.index, y=newtablepivot.iloc[:, j], connectgaps=True,
                               name=str(newtablepivot.columns[j]), mode='lines')
        dataPandafix.append(trace)
    layoutfix = go.Layout(title='Fixtures in mnt out of {} to {} by Reporting Month'.format(FromRegion, ToRegion))
    figfix = go.Figure(data=dataPandafix, layout=layoutfix)
    figfix.update_layout(height=600, width=900)
    return (figfix)


def combine_html_table_chart(table_path, fig_path, fixtures_path, combine_name):
    f1 = open(table_path, 'r').read()
    f2 = open(fig_path, 'r').read()
    f3 = open(fixtures_path, 'r').read()
    table.figures_to_html([f1, f2, f3], filename=combine_name, task_name=report_name)


def prod_imports(data, Country, data2, val_d):
    data.index = pd.to_datetime(data.index)
    monthlyimp = pd.DataFrame(data['Total'].resample('MS').mean())
    data2.index = pd.to_datetime(data2.index)
    data3 = data2.merge(monthlyimp['Total'], left_on=data2.index, right_on=monthlyimp.index, how='left',
                       right_index=True)
    data3['Month'] = data3.index.month
    a = ts.data_by_year(data3['Total'], freq='M')
    newdata = a.rolling(3, axis=1).mean()
    newdata = newdata[2019]
    newdata.index = range(1, 13)
    data3 = data3.reset_index()
    m = data3.merge(newdata, how='right', left_on='Month', right_on=newdata.index)
    m = m.set_index('Date').sort_index()
    test = m.iloc[(m.index > '2021-01-01') & (m.index <= val_d)]
    fig = make_subplots(rows=2, cols=1,
                        specs=[[{"secondary_y": True}], [{"secondary_y": False}]])
    fig.add_trace(go.Scatter(x=test.index, y=test['Total'], name='Imports'), secondary_y=True, row=1, col=1)
    fig.add_trace(go.Bar(x=test.index, y=test['Runs'], name='Runs', yaxis='y1'), row=1, col=1)
    fig.add_trace(go.Scatter(x=test.index, y=test['Total'], name='Imports', line=dict(color='black'),
                             mode=_missing_photo_text(547, 'mode=')), row=2, col=1)
    fig.add_trace(go.Scatter(x=test.index, y=test[2019], name='3yr (2017-2019)',
                             line=dict(color='blue', **_missing_photo_text(549, 'd'))), row=2, col=1)
    return fig


def prod_exports(data, Country, data2, val_d):
    data.index = pd.to_datetime(data.index)
    monthlyimp = pd.DataFrame(data['Total'].resample('MS').mean())
    data2.index = pd.to_datetime(data2.index)
    data3 = data2.merge(monthlyimp['Total'], left_on=data2.index, right_on=monthlyimp.index, how='left',
                       right_index=True)
    data3['Month'] = data3.index.month
    a = ts.data_by_year(data3['Total'], freq='M')
    newdata = a.rolling(3, axis=1).mean()
    newdata = newdata[2019]
    newdata.index = range(1, 13)
    data3 = data3.reset_index()
    m = data3.merge(newdata, how='right', left_on='Month', right_on=newdata.index)
    m = m.set_index('Date').sort_index()
    test = m.iloc[(m.index > '2021-01-01') & (m.index <= val_d)]
    fig = make_subplots(rows=2, cols=1,
                        specs=[[{"secondary_y": True}], [{"secondary_y": False}]])
    fig.add_trace(go.Scatter(x=test.index, y=test['Total'], name='Exports'), secondary_y=True, row=1, col=1)
    fig.add_trace(go.Bar(x=test.index, y=test['Runs'], name='Runs', yaxis='y1'), row=1, col=1)
    fig.add_trace(go.Scatter(x=test.index, y=test['Total'], name='Exports', line=dict(color='black'),
                             mode=_missing_photo_text(574, 'mode=')), row=2, col=1)
    fig.add_trace(go.Scatter(x=test.index, y=test[2019], name='3yr (2017-2019)',
                             line=dict(color='blue', **_missing_photo_text(576, 'd'))), row=2, col=1)
    return fig


def add_alert(df_alert, table_name="Oil_Kpler_Alerts"):
    df_alert.reset_index(drop=True, inplace=True)
    alert_dates = list(pd.to_datetime(df_alert['As_of_date'].unique()).strftime("%Y-%m-%d"))
    alert_dates_str = "','".join(alert_dates)
    df = sql.read_sql(f"Select * from {table_name} where As_Of_Date in ('{alert_dates_str}')")
    if len(df) > 0:
        df['alert_string'] = df['Alert'] + df['As_Of_Date'].dt.strftime('%Y-%m-%d')
        real_alert = pd.DataFrame()
        for idx, row in df_alert.iterrows():
            if row['Alert'] + dt.datetime.strftime(row['As_of_date'], '%Y-%m-%d') not in list(df['alert_string']):
                real_alert = pd.concat([real_alert, df_alert.loc[[idx], :]], ignore_index=True, axis=0)
    else:
        real_alert = df_alert
    if len(real_alert) > 0:
        sql.to_sql(real_alert, table_name, index=False)


def format_table(z, footer=None, format_row=True):
    if format_row:
        return table.html_format(
            df=z,
            precision=0,
            show_date=False,
            footer=footer,
            hide_cols=['mean', 'std', 'mean_10d', 'std_10d', 'mean_20d',
                       'std_20d', 'mean_10d_sea', 'std_10d_sea', 'mean_20d_sea',
                       'std_20d_sea', '_last_update'],
            format_column={
                "0": {'width': '120px', 'text-align': 'left'},
                "1": {'width': '80px', 'text-align': 'center', 'highlight_z': ['10day MA', 'mean_10d', 'std_10d']},
                "2": {'width': '80px', 'text-align': 'center', 'highlight_z': ['20day MA', 'mean_20d', 'std_20d']},
                "3": {'width': '80px', 'text-align': 'center'},
                "4": {'width': '80px', 'text-align': 'center'},
                "5": {'width': '80px', 'text-align': 'center'},
                "6": {'width': '80px', 'text-align': 'center'},
                "7": {'width': '80px', 'text-align': 'center'},
                "8": {'width': '80px', 'text-align': 'center'},
                "9": {'width': '80px', 'text-align': 'center'},
                "10": {'width': '80px', 'text-align': 'center'},
            },
            format_row={0: {"bold": True, "bottom_border": True}}
        )
    else:
        return table.html_format(
            df=z,
            precision=0,
            show_date=False,
            footer=footer,
            hide_cols=['mean', 'std', 'mean_10d', 'std_10d', 'mean_20d',
                       'std_20d', 'mean_10d_sea', 'std_10d_sea', 'mean_20d_sea',
                       'std_20d_sea', '_last_update'],
            format_column={
                "0": {'width': '120px', 'text-align': 'left'},
                "1": {'width': '80px', 'text-align': 'center', 'highlight_z': ['10day MA', 'mean_10d', 'std_10d']},
                "2": {'width': '80px', 'text-align': 'center', 'highlight_z': ['20day MA', 'mean_20d', 'std_20d']},
                "3": {'width': '80px', 'text-align': 'center'},
                "4": {'width': '80px', 'text-align': 'center'},
                "5": {'width': '80px', 'text-align': 'center'},
                "6": {'width': '80px', 'text-align': 'center'},
                "7": {'width': '80px', 'text-align': 'center'},
                "8": {'width': '80px', 'text-align': 'center'},
                "9": {'width': '80px', 'text-align': 'center'},
                "10": {'width': '80px', 'text-align': 'center'},
            }
        )


def china_imports():
    val_d = (today() - dt.timedelta(1)).strftime("%Y-%m-%d")
    Country = 'China'
    namettl = Country + ' Crude Imports'
    fixture_complete = ['Fully Fixed', 'In Progress', 'Finished']
    crude = ['crude/co', 'crude', 'Crude', 'Crude/Co']
    Fzones = ['PG', 'WAF', 'Latam', 'US', 'Nsea', 'Med']
    figs = []
    for i in range(0, len(Fzones)):
        fixturelist = dv.kpler(
            '/v1/fixtures?fromZones={}&toZones={}&layCanStartAfter=2018-01-01&products=crude%2fco'.format(
                Fzones[i], Country))
        fixturelist = fixturelist.loc[(fixturelist['Product'].isin(crude))]
        fxlist = fixturelist[
            ['Reported date', 'Vessel', 'Charterer', 'Laycan start', 'Laycan end', 'Origin',
             'Destination', *_missing_photo_text(664, 'fixture column list tail'),
             'Rates ($ price)', 'Status', 'Deadweight (t)']]
        fxlist = fxlist.loc[(fxlist['Status'].isin(fixture_complete))]
        fxlist = fxlist.drop_duplicates()
        figs.append(go_get_bar(fxlist, Fzones[i], Country))
        figs.append(go_get_trend(fxlist, Fzones[i], Country))

    US = dv.kpler(
        ('/v1/flows?flowDirection=Import&granularity=daily&startDate=2015-01-01&endDate={}&'
         'toZones={}&unit=kbd&withForecast=false&split=Destination%20Ports&products=crude%2fco').format(
            val_d, Country))
    US = US.set_index('Date')
    x = get_table(US, namettl)

    USt = dv.kpler(
        ('/v1/flows?flowDirection=Import&granularity=daily&startDate=2015-01-01&endDate={}&'
         'toZones={}&unit=kbd&withForecast=false&split=Total&products=crude%2fco').format(
            val_d, Country))
    USt = kpler.convert_to_ts(USt)
    x_total = get_table(USt, namettl)

    df_alert = alert_table(x_total, 'Check {} Imports'.format(Country), val_d)
    df_alert['As_of_date'] = pd.to_datetime(df_alert['As_of_date'])
    seasonal_alert = alert_table_seasonal(x_total, 'Check Seasonal {} Imports'.format(Country), val_d)
    seasonal_alert['As_of_date'] = pd.to_datetime(seasonal_alert['As_of_date'])
    if not df_alert.empty:
        add_alert(df_alert, table_name="Oil_Kpler_Alerts")
    if not seasonal_alert.empty:
        add_alert(seasonal_alert, table_name="Oil_Kpler_Alerts")

    z = pd.concat([x_total, x], axis=0, ignore_index=True)
    fig4 = chart.line_chart(df=(USt.rolling(10).mean()).iloc[-365 * 5:], title=namettl, y_axis_title="kbd",
                            tickformat=None)
    fig2 = chart.seasonal_chart(df=USt.rolling(10).mean(), title=namettl, y_axis_title="kbd")
    output = format_table(z)
    combined_loc = f"{html_path}\\oil\\kpler_imports_exports\\{Country}_combined.html"
    run_time = [f"Latest data is on {US.index[-1]} <br>"]
    table.figures_to_html(run_time + [output] + [fig2, fig4] + figs, combined_loc, task_name=report_name)
    out_table = x_total.copy()
    out_table.rename(columns={namettl: "Name"}, inplace=True)
    out_table["Name"] = namettl
    return out_table, fig2


def china_prod_exports():
    val_d = (today() - dt.timedelta(1)).strftime("%Y-%m-%d")
    Country = 'China'
    namettl = Country + ' Clean Product Exports'
    fixture_complete = ['Fully Fixed', 'In Progress', 'Finished']
    Tzones = ['Asia', 'Europe', 'US', 'Latam']
    figs = []
    for i in range(0, len(Tzones)):
        fixturelist = dv.kpler(
            '/v1/fixtures?toZones={}&fromZones={}&layCanStartAfter=2018-01-01&products= Clean%20Products'.format(
                Tzones[i], Country))
        fxlist = fixturelist[
            ['Reported date', 'Vessel', 'Charterer', 'Laycan start', 'Laycan end', 'Origin',
             'Destination', *_missing_photo_text(723, 'fixture column list tail'),
             'Rates ($ price)', 'Status', 'Deadweight (t)']]
        fxlist = fxlist.loc[(fxlist['Status'].isin(fixture_complete))]
        fxlist = fxlist.drop_duplicates()
        figs.append(go_get_bar(fxlist, Country, Tzones[i]))
        figs.append(go_get_trend(fxlist, Country, Tzones[i]))

    US = dv.kpler(
        ('/v1/flows?flowDirection=Export&granularity=daily&startDate=2017-01-01&endDate={}&'
         'fromZones={}&unit=kbd&withForecast=false&split=Origin%20Ports&products= Clean%20Products').format(
            val_d, Country))
    US = US.set_index('Date')
    x = get_table(US, namettl)

    USt = dv.kpler(
        ('/v1/flows?flowDirection=Export&granularity=daily&startDate=2017-01-01&endDate={}&'
         'fromZones={}&unit=kbd&withForecast=false&split=Total&products= Clean%20Products').format(
            val_d, Country))
    USt = kpler.convert_to_ts(USt)
    x_total = get_table(USt, namettl)

    df_alert = alert_table_countries(x, val_d, Country)
    df_alertnew = pd.concat(df_alert)
    df_alertnew['As_of_date'] = pd.to_datetime(df_alertnew['As_of_date'])
    seasonal_alert = alert_table_countries_seasonal(x, val_d, Country)
    seasonal_alertnew = pd.concat(seasonal_alert)
    seasonal_alertnew['As_of_date'] = pd.to_datetime(seasonal_alertnew['As_of_date'])
    if not df_alertnew.empty:
        add_alert(df_alertnew, table_name="Oil_Kpler_Alerts")
    if not seasonal_alertnew.empty:
        add_alert(seasonal_alertnew, table_name="Oil_Kpler_Alerts")

    z = pd.concat([x_total, x], axis=0, ignore_index=True)
    fig4 = chart.line_chart(df=(USt.rolling(10).mean()).iloc[-365 * 5:], title=namettl, y_axis_title="kbd",
                            tickformat=None)
    fig2 = chart.seasonal_chart(df=USt.rolling(10).mean(), title=namettl, y_axis_title="kbd")
    output = format_table(z)
    combined_loc = f"{html_path}\\oil\\kpler_imports_exports\\{Country}_prod_combined.html"
    run_time = [f"Latest data is on {US.index[-1]} <br>"]
    table.figures_to_html(run_time + [output] + [fig2, fig4] + figs, combined_loc, task_name=report_name)
    out_table = x_total.copy()
    out_table.rename(columns={namettl: "Name"}, inplace=True)
    out_table["Name"] = namettl
    return out_table, fig2


def india_imports():
    val_d = (today() - dt.timedelta(1)).strftime("%Y-%m-%d")
    Country = 'India'
    namettl = Country + ' Crude Imports'
    fixture_complete = ['Fully Fixed', 'In Progress', 'Finished']
    crude = ['crude/co', 'crude', 'Crude', 'Crude/Co']
    Fzones = ['PG', 'WAF', 'Latam', 'US', 'Nsea', 'Med']
    figs = []
    for i in range(0, len(Fzones)):
        fixturelist = dv.kpler(
            '/v1/fixtures?fromZones={}&toZones={}&layCanStartAfter=2018-01-01&products=crude%2fco'.format(
                Fzones[i], Country))
        fixturelist = fixturelist.loc[(fixturelist['Product'].isin(crude))]
        fxlist = fixturelist[
            ['Reported date', 'Vessel', 'Charterer', 'Laycan start', 'Laycan end', 'Origin',
             'Destination', *_missing_photo_text(786, 'fixture column list tail'),
             'Rates ($ price)', 'Status', 'Deadweight (t)']]
        fxlist = fxlist.loc[(fxlist['Status'].isin(fixture_complete))]
        fxlist = fxlist.drop_duplicates()
        figs.append(go_get_bar(fxlist, Fzones[i], Country))
        figs.append(go_get_trend(fxlist, Fzones[i], Country))

    US = dv.kpler(
        ('/v1/flows?flowDirection=Import&granularity=daily&startDate=2015-01-01&endDate={}&'
         'toZones={}&unit=kbd&withForecast=false&split=Destination%20Ports&products=crude%2fco').format(
            val_d, Country))
    US = US.set_index('Date')
    x = get_table(US, namettl)

    USt = dv.kpler(
        ('/v1/flows?flowDirection=Import&granularity=daily&startDate=2015-01-01&endDate={}&'
         'toZones={}&unit=kbd&withForecast=false&split=Total&products=crude%2fco').format(
            val_d, Country))
    USt = kpler.convert_to_ts(USt)
    x_total = get_table(USt, namettl)

    df_alert = alert_table(x_total, 'Check {} Imports'.format(Country), val_d)
    df_alert['As_of_date'] = pd.to_datetime(df_alert['As_of_date'])
    seasonal_alert = alert_table_seasonal(x_total, 'Check Seasonal {} Imports'.format(Country), val_d)
    seasonal_alert['As_of_date'] = pd.to_datetime(seasonal_alert['As_of_date'])
    if not df_alert.empty:
        add_alert(df_alert, table_name="Oil_Kpler_Alerts")
    if not seasonal_alert.empty:
        add_alert(seasonal_alert, table_name="Oil_Kpler_Alerts")

    z = pd.concat([x_total, x], axis=0, ignore_index=True)
    fig4 = chart.line_chart(df=(USt.rolling(10).mean()).iloc[-365 * 5:], title=namettl, y_axis_title="kbd",
                            tickformat=None)
    fig2 = chart.seasonal_chart(df=USt.rolling(10).mean(), title=namettl, y_axis_title="kbd")
    output = format_table(z)
    combined_loc = f"{html_path}\\oil\\kpler_imports_exports\\{Country}_combined.html"
    run_time = [f"Latest data is on {US.index[-1]} <br>"]
    table.figures_to_html(run_time + [output] + [fig2, fig4] + figs, combined_loc)
    out_table = x_total.copy()
    out_table.rename(columns={namettl: "Name"}, inplace=True)
    out_table["Name"] = namettl
    return out_table, fig2


def india_prod_exports():
    val_d = (today() - dt.timedelta(1)).strftime("%Y-%m-%d")
    Country = 'India'
    namettl = Country + ' Clean Product Exports'
    fixture_complete = ['Fully Fixed', 'In Progress', 'Finished']
    Tzones = ['Asia', 'Europe', 'US', 'Latam']
    figs = []
    for i in range(0, len(Tzones)):
        fixturelist = dv.kpler(
            '/v1/fixtures?toZones={}&fromZones={}&layCanStartAfter=2018-01-01&products= Clean%20Products'.format(
                Tzones[i], Country))
        fxlist = fixturelist[
            ['Reported date', 'Vessel', 'Charterer', 'Laycan start', 'Laycan end', 'Origin',
             'Destination', *_missing_photo_text(846, 'fixture column list tail'),
             'Rates ($ price)', 'Status', 'Deadweight (t)']]
        fxlist = fxlist.loc[(fxlist['Status'].isin(fixture_complete))]
        fxlist = fxlist.drop_duplicates()
        figs.append(go_get_bar(fxlist, Country, Tzones[i]))
        figs.append(go_get_trend(fxlist, Country, Tzones[i]))

    US = dv.kpler(
        ('/v1/flows?flowDirection=Export&granularity=daily&startDate=2017-01-01&endDate={}&'
         'fromZones={}&unit=kbd&withForecast=false&split=Origin%20Ports&products= Clean%20Products').format(
            val_d, Country))
    US = US.set_index('Date')
    x = get_table(US, namettl)

    USt = dv.kpler(
        ('/v1/flows?flowDirection=Export&granularity=daily&startDate=2017-01-01&endDate={}&'
         'fromZones={}&unit=kbd&withForecast=false&split=Total&products= Clean%20Products').format(
            val_d, Country))
    USt = kpler.convert_to_ts(USt)
    x_total = get_table(USt, namettl)

    df_alert = alert_table_countries(x, val_d, Country)
    df_alertnew = pd.concat(df_alert)
    df_alertnew['As_of_date'] = pd.to_datetime(df_alertnew['As_of_date'])
    seasonal_alert = alert_table_countries_seasonal(x, val_d, Country)
    seasonal_alertnew = pd.concat(seasonal_alert)
    seasonal_alertnew['As_of_date'] = pd.to_datetime(seasonal_alertnew['As_of_date'])
    if not df_alertnew.empty:
        add_alert(df_alertnew, table_name="Oil_Kpler_Alerts")
    if not seasonal_alertnew.empty:
        add_alert(seasonal_alertnew, table_name="Oil_Kpler_Alerts")

    z = pd.concat([x_total, x], axis=0, ignore_index=True)
    fig4 = chart.line_chart(df=(USt.rolling(10).mean()).iloc[-365 * 5:], title=namettl, y_axis_title="kbd",
                            tickformat=None)
    fig2 = chart.seasonal_chart(df=USt.rolling(10).mean(), title=namettl, y_axis_title="kbd")
    output = format_table(z)
    combined_loc = f"{html_path}\\oil\\kpler_imports_exports\\{Country}_prod_combined.html"
    run_time = [f"Latest data is on {US.index[-1]} <br>"]
    table.figures_to_html(run_time + [output] + [fig2, fig4] + figs, combined_loc)
    out_table = x_total.copy()
    out_table.rename(columns={namettl: "Name"}, inplace=True)
    out_table["Name"] = namettl
    return out_table, fig2


def jkt_imports():
    val_d = (today() - dt.timedelta(1)).strftime("%Y-%m-%d")
    Country = _missing_photo_text(897, 'JKT: Japan, Korea, Thailand and Taiwan')
    Country_list = _missing_photo_text(898, 'Country_list')
    CNT = 'JKT'
    namettl = CNT + ' Crude Imports'
    fixture_complete = ['Fully Fixed', 'In Progress', 'Finished']
    crude = ['crude/co', 'crude', 'Crude', 'Crude/Co']
    Fzones = ['PG', 'WAF', 'Latam', 'US', 'Nsea', 'Med']
    figs = []
    for i in range(0, len(Fzones)):
        fixturelist = dv.kpler(
            '/v1/fixtures?fromZones={}&toZones={}&layCanStartAfter=2018-01-01&products=crude%2fco'.format(
                Fzones[i], Country))
        fixturelist = fixturelist.loc[(fixturelist['Product'].isin(crude))]
        fxlist = fixturelist[
            ['Reported date', 'Vessel', 'Charterer', 'Laycan start', 'Laycan end', 'Origin',
             'Destination', *_missing_photo_text(910, 'fixture column list tail'),
             'Rates ($ price)', 'Status', 'Deadweight (t)']]
        fxlist = fxlist.loc[(fxlist['Status'].isin(fixture_complete))]
        fxlist = fxlist.drop_duplicates()
        figs.append(go_get_bar(fxlist, Fzones[i], Country))
        figs.append(go_get_trend(fxlist, Fzones[i], Country))

    US = dv.kpler(
        ('/v1/flows?flowDirection=Import&granularity=daily&startDate=2015-01-01&endDate={}&'
         'toZones={}&unit=kbd&withForecast=false&split=Destination%20Countries&products=crude%2fco').format(
            val_d, Country))
    US = US.set_index('Date')
    x = get_table(US, namettl)

    USt = dv.kpler(
        ('/v1/flows?flowDirection=Import&granularity=daily&startDate=2015-01-01&endDate={}&'
         'toZones={}&unit=kbd&withForecast=false&split=Total&products=crude%2fco').format(
            val_d, Country))
    USt = kpler.convert_to_ts(USt)
    x_total = get_table(USt, namettl)

    df_alert = alert_table_countries(x, val_d, CNT)
    df_alertnew = pd.concat(df_alert)
    df_alertnew['As_of_date'] = pd.to_datetime(df_alertnew['As_of_date'])
    seasonal_alert = alert_table_countries_seasonal(x, val_d, CNT)
    seasonal_alertnew = pd.concat(seasonal_alert)
    seasonal_alertnew['As_of_date'] = pd.to_datetime(seasonal_alertnew['As_of_date'])
    if not df_alertnew.empty:
        add_alert(df_alertnew, table_name="Oil_Kpler_Alerts")
    if not seasonal_alertnew.empty:
        add_alert(seasonal_alertnew, table_name="Oil_Kpler_Alerts")

    z = pd.concat([x_total, x], axis=0, ignore_index=True)
    fig4 = chart.line_chart(df=(USt.rolling(10).mean()).iloc[-365 * 5:], title=namettl, y_axis_title="kbd",
                            tickformat=None)
    fig2 = chart.seasonal_chart(df=USt.rolling(10).mean(), title=namettl, y_axis_title="kbd")
    output = format_table(z)
    combined_loc = f"{html_path}\\oil\\kpler_imports_exports\\{CNT}_combined.html"
    run_time = [f"Latest data is on {US.index[-1]} <br>"]
    table.figures_to_html(run_time + [output] + [fig2, fig4] + figs, combined_loc)
    out_table = x_total.copy()
    out_table.rename(columns={namettl: "Name"}, inplace=True)
    out_table["Name"] = namettl
    return out_table, fig2


def latam_imports():
    val_d = (today() - dt.timedelta(1)).strftime("%Y-%m-%d")
    Country = 'Mexico, Brazil, Chile, Colombia, Argentina'
    Country_list = ['Mexico', 'Brazil', 'Chile', 'Colombia', 'Argentina']
    CNT = 'Latam'
    namettl = CNT + ' Clean Product Imports'
    fixture_complete = ['Fully Fixed', 'In Progress', 'Finished']
    Fzones = ['Asia', 'China', 'Europe', 'US', 'India']
    figs = []
    for i in range(0, len(Fzones)):
        fixturelist = dv.kpler(
            '/v1/fixtures?fromZones={}&toZones={}&layCanStartAfter=2018-01-01&products= Clean%20Products'.format(
                Fzones[i], Country))
        fxlist = fixturelist[
            ['Reported date', 'Vessel', 'Charterer', 'Laycan start', 'Laycan end', 'Origin',
             'Destination', *_missing_photo_text(973, 'fixture column list tail'),
             'Rates ($ price)', 'Status', 'Deadweight (t)']]
        fxlist = fxlist.loc[(fxlist['Status'].isin(fixture_complete))]
        fxlist = fxlist.drop_duplicates()
        figs.append(go_get_bar(fxlist, Fzones[i], Country))
        figs.append(go_get_trend(fxlist, Fzones[i], Country))

    US = dv.kpler(
        ('/v1/flows?flowDirection=Import&granularity=daily&startDate=2017-01-01&endDate={}&'
         'toZones={}&unit=kbd&withForecast=false&split=Destination%20Countries&products=Clean%20Products').format(
            val_d, Country))
    US = US.set_index('Date')
    x = get_table(US, namettl)

    USt = dv.kpler(
        ('/v1/flows?flowDirection=Import&granularity=daily&startDate=2017-01-01&endDate={}&'
         'toZones={}&unit=kbd&withForecast=false&split=Total&products=Clean%20Products').format(
            val_d, Country))
    USt = kpler.convert_to_ts(USt)
    x_total = get_table(USt, namettl)

    df_alert = alert_table_countries(x, val_d, CNT)
    df_alertnew = pd.concat(df_alert)
    df_alertnew['As_of_date'] = pd.to_datetime(df_alertnew['As_of_date'])
    seasonal_alert = alert_table_countries_seasonal(x, val_d, CNT)
    seasonal_alertnew = pd.concat(seasonal_alert)
    seasonal_alertnew['As_of_date'] = pd.to_datetime(seasonal_alertnew['As_of_date'])
    if not df_alertnew.empty:
        add_alert(df_alertnew, table_name="Oil_Kpler_Alerts")
    if not seasonal_alertnew.empty:
        add_alert(seasonal_alertnew, table_name="Oil_Kpler_Alerts")

    z = pd.concat([x_total, x], axis=0, ignore_index=True)
    fig4 = chart.line_chart(df=(USt.rolling(10).mean()).iloc[-365 * 5:], title=namettl, y_axis_title="kbd",
                            tickformat=None)
    fig2 = chart.seasonal_chart(df=USt.rolling(10).mean(), title=namettl, y_axis_title="kbd")
    output = format_table(z)
    combined_loc = f"{html_path}\\oil\\kpler_imports_exports\\{CNT}_prod_combined.html"
    run_time = [f"Latest data is on {US.index[-1]} <br>"]
    table.figures_to_html(run_time + [output] + [fig2, fig4] + figs, combined_loc)
    out_table = x_total.copy()
    out_table.rename(columns={namettl: "Name"}, inplace=True)
    out_table["Name"] = namettl
    return out_table, fig2


def pg_prod_exports():
    val_d = (today() - dt.timedelta(1)).strftime("%Y-%m-%d")
    Country = 'United Arab Emirates, Saudi Arabia, Qatar, Kuwait, Bahrain, Oman'
    Country_list = ['UAE', 'Saudi', 'Qatar', 'Kuwait', 'Bahrain', 'Oman']
    CNT = 'PG'
    namettl = CNT + ' Clean Product Exports'
    fixture_complete = ['Fully Fixed', 'In Progress', 'Finished']
    Tzones = ['Asia', 'Europe', 'US', 'Latam']
    figs = []
    for i in range(0, len(Tzones)):
        fixturelist = dv.kpler(
            '/v1/fixtures?toZones={}&fromZones={}&layCanStartAfter=2018-01-01&products= Clean%20Products'.format(
                Country, Tzones[i]))
        fxlist = fixturelist[
            ['Reported date', 'Vessel', 'Charterer', 'Laycan start', 'Laycan end', 'Origin',
             'Destination', *_missing_photo_text(1036, 'fixture column list tail'),
             'Rates ($ price)', 'Status', 'Deadweight (t)']]
        fxlist = fxlist.loc[(fxlist['Status'].isin(fixture_complete))]
        fxlist = fxlist.drop_duplicates()
        if len(fxlist) > 0:
            figs.append(go_get_bar(fxlist, Country, Tzones[i]))
            figs.append(go_get_trend(fxlist, Country, Tzones[i]))

    US = dv.kpler(
        ('/v1/flows?flowDirection=Export&granularity=daily&startDate=2017-01-01&endDate={}&'
         'fromZones={}&unit=kbd&withForecast=false&split=Origin%20Countries&products=Clean%20Products').format(
            val_d, Country))
    US = US.set_index('Date')
    x = get_table(US, namettl)

    USt = dv.kpler(
        ('/v1/flows?flowDirection=Export&granularity=daily&startDate=2017-01-01&endDate={}&'
         'fromZones={}&unit=kbd&withForecast=false&split=Total&products=Clean%20Products').format(
            val_d, Country))
    USt = kpler.convert_to_ts(USt)
    x_total = get_table(USt, namettl)

    df_alert = alert_table_countries(x, val_d, CNT)
    df_alertnew = pd.concat(df_alert)
    df_alertnew['As_of_date'] = pd.to_datetime(df_alertnew['As_of_date'])
    seasonal_alert = alert_table_countries_seasonal(x, val_d, CNT)
    seasonal_alertnew = pd.concat(seasonal_alert)
    seasonal_alertnew['As_of_date'] = pd.to_datetime(seasonal_alertnew['As_of_date'])
    if not df_alertnew.empty:
        add_alert(df_alertnew, table_name="Oil_Kpler_Alerts")
    if not seasonal_alertnew.empty:
        add_alert(seasonal_alertnew, table_name="Oil_Kpler_Alerts")

    z = pd.concat([x_total, x], axis=0, ignore_index=True)
    fig4 = chart.line_chart(df=(USt.rolling(10).mean()).iloc[-365 * 5:], title=namettl, y_axis_title="kbd",
                            tickformat=None)
    fig2 = chart.seasonal_chart(df=USt.rolling(10).mean(), title=namettl, y_axis_title="kbd")
    output = format_table(z)
    combined_loc = f"{html_path}\\oil\\kpler_imports_exports\\{CNT}_prod_combined.html"
    run_time = [f"Latest data is on {US.index[-1]} <br>"]
    table.figures_to_html(run_time + [output] + [fig2, fig4] + figs, combined_loc)
    out_table = x_total.copy()
    out_table.rename(columns={namettl: "Name"}, inplace=True)
    out_table["Name"] = namettl
    return out_table, fig2


def update(send_to):
    tb1, fig1 = china_imports()
    tb2, fig2 = china_prod_exports()
    tb3, fig3 = india_imports()
    tb4, fig4 = india_prod_exports()
    tb5, fig5 = jkt_imports()
    tb6, fig6 = latam_imports()
    tb7, fig7 = pg_prod_exports()
    figs = []
    figs.append("<div style='font-family:Calibri;' >")
    df = pd.concat([tb1, tb2, tb3, tb4, tb5, tb6, tb7], axis=0, ignore_index=True)
    figs.append(format_table(df, format_row=False, footer="JKT: Japan, Korea, Thailand and Taiwan"))
    figs.append(fig1)
    figs.append(fig2)
    figs.append(fig3)
    figs.append(fig4)
    figs.append(fig5)
    figs.append(fig6)
    figs.append(fig7)
    figs.append('Please follow the link for details: <br>')
    figs.append(
        u'<a href=f"{}\\oil\\kpler_imports_exports\\China_combined.html">China Imports</a><br>'.format(
            _missing_photo_text(1108, 'html')))
    figs.append(
        u'<a href=f"{}\\oil\\kpler_imports_exports\\China_prod_combined.html">China Exports</a><br>'.format(
            _missing_photo_text(1110, 'html')))
    figs.append(
        u'<a href=f"{}\\oil\\kpler_imports_exports\\India_combined.html">India Imports</a><br>'.format(
            _missing_photo_text(1112, 'html')))
    figs.append(
        u'<a href=f"{}\\oil\\kpler_imports_exports\\India_prod_combined.html">India Exports</a><br>'.format(
            _missing_photo_text(1114, 'html')))
    figs.append(
        u'<a href=f"{}\\oil\\kpler_imports_exports\\JKT_combined.html">JKT Imports</a><br>'.format(
            _missing_photo_text(1115, 'html')))
    figs.append(
        u'<a href=f"{}\\oil\\kpler_imports_exports\\Latam_prod_combined.html">Latam Imports</a><br>'.format(
            _missing_photo_text(1117, 'html')))
    figs.append(
        u'<a href=f"{}\\oil\\kpler_imports_exports\\PG_prod_combined.html">PG Exports</a><br>'.format(
            _missing_photo_text(1119, 'html')))
    figs.append(table.html_text(f"<br>Updated at {dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"))
    table.figures_to_html(
        [table.html_text(report_name, style="font-family:Calibri;", tag='h1')] + figs,
        f"{html_path}\\oil\\kpler_imports_exports\\total.html")
    val_d = today() - dt.timedelta(1)
    df = sql.read_sql(f"Select * from Oil_Kpler_Alerts where As_Of_Date = '{dt.datetime.strftime(val_d, '%Y-%m-%d')}'")
    if len(df) > 0:
        df['As_Of_Date'] = df['As_Of_Date'].dt.strftime('%Y-%m-%d')
        df_html = table.html_format(
            df=df,
            format_column={df.columns[0]: {'width': '400px', 'text-align': 'left'},
                           df.columns[1]: {'width': '80px', 'text-align': 'left'},
                           })


if __name__ == '__main__':
    update(send_to=send_to)
