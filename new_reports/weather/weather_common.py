
import ecm.cmds.stormvista as sv
import ecm.cmds.sql as sql
from ecm.cmds.cdr import today
import pandas as pd
import numpy as np
import datetime as dt
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import plotly as py


def _get_model_sfx(model=None):
    if model == 'EC46':
        tbl_sfx = '_EC46'
    elif model == 'GFS':
        tbl_sfx = '_GFS'
    else:
        tbl_sfx = ''
    return tbl_sfx


def get_forecast_hdd_global(area, cycle='00', model=None):
    """
    Last 3 forecasts from Stormvista
    """
    tbl_sfx = _get_model_sfx(model)
    cycle_where = f"and cycle='{cycle}'" if model != "EC46" else ''
    sql_str = f"""select t1.* from CWG_StormVista_Global_fcast{tbl_sfx} t1 INNER JOIN
                    (select Top (3) AS_OF_DATE as dt from CWG_StormVista_Global_fcast{tbl_sfx} group by As_of_date
                    order by As_of_date desc) t2 on t1.AS_OF_DATE = t2.dt
                    where region='{area}' {cycle_where} and Field='pw_hdd' order by AS_OF_DATE desc, Dates"""
    data_f = sql.read_sql(sql_str)
    data_f['Dates'] = pd.to_datetime(data_f['Dates'])
    data_f['As_of_date'] = pd.to_datetime(data_f['As_of_date'])
    df = pd.DataFrame()
    dates = data_f['As_of_date'].unique()
    for i in dates:
        df_temp = data_f.loc[data_f['As_of_date'] == i, ['Dates', 'Value']]
        df_temp.set_index('Dates', inplace=True)
        df_temp.columns = [i]
        df = pd.concat([df, df_temp], axis=1)
    df.columns = [dt.datetime.strftime(x, '%Y-%m-%d') for x in df.columns]
    return df


def get_forecast_cdd_global(area, cycle='00', model=None):
    """
    Last 3 forecasts from Stormvista
    """
    tbl_sfx = _get_model_sfx(model)
    cycle_where = f"and cycle='{cycle}'" if model != "EC46" else ''
    sql_str = f"""select t1.* from CWG_StormVista_Global_fcast{tbl_sfx} t1 INNER JOIN
                    (select Top (3) AS_OF_DATE as dt from CWG_StormVista_Global_fcast{tbl_sfx} group by As_of_date
                    order by As_of_date desc) t2 on t1.AS_OF_DATE = t2.dt
                    where region='{area}' {cycle_where} and Field='pw_cdd' order by AS_OF_DATE desc, Dates"""
    data_f = sql.read_sql(sql_str)
    data_f['Dates'] = pd.to_datetime(data_f['Dates'])
    data_f['As_of_date'] = pd.to_datetime(data_f['As_of_date'])
    df = pd.DataFrame()
    dates = data_f['As_of_date'].unique()
    for i in dates:
        df_temp = data_f.loc[data_f['As_of_date'] == i, ['Dates', 'Value']]
        df_temp.set_index('Dates', inplace=True)
        df_temp.columns = [i]
        df = pd.concat([df, df_temp], axis=1)
    df.columns = [dt.datetime.strftime(x, '%Y-%m-%d') for x in df.columns]
    return df


def get_cwg_global_data_actuals(area, field=None):
    if field == "pw_cdd":
        query_model = "POP_CDD"
    elif field == "pw_hdd":
        query_model = "POP_HDD"
    else:
        raise ValueError(f"model {field} is unknown")
    if area in ["europe", "ttf", "italy", "uk"]:
        if area == "uk":
            area = "United Kingdom"
        elif area in ["italy", "uk"]:
            area = area.capitalize()
        table = "EUROPE"
    elif area in ["asia", "china", "japan", "skorea", "india"]:
        table = "ASIA"
        if area in ["china", "japan", "skorea", "india"]:
            area = area.capitalize()
    sql_str = f"""
        SELECT distinct * from (SELECT DATES as Date, REGION_NAME, {query_model}, AS_OF_DATE
        FROM [LO25].[dbo].[CWG_{table}] Where IS_FORECAST = 0 and REGION_NAME = '{area}'
        and DATES between '{(today() - dt.timedelta(days=28)).strftime('%Y-%m-%d')}' and '[RECOVERY: clipped today().strftime tail]'
    """
    raise NotImplementedError("Photographed weather_common.py SQL line89 is clipped")
    cwg_data = sql.read_sql(sql_str)
    cwg_data = cwg_data.drop_duplicates(subset=["Date"], keep="first")
    cwg_data = cwg_data.replace({pd.NA: np.nan})
    cwg_data["REGION_NAME"] = area
    return cwg_data[["Date", query_model]]


def get_cwg_us_data_actuals(area, field=None, region=None):
    if field == "ew_cdd":
        query_model = "POP_CDD"
    elif field == "gw_hdd":
        query_model = "NG_HDD"
    else:
        raise ValueError(f"model {field} is unknown")
    if region is not None:
        table = "US_5region"
        region_where = f" and REGION_NAME = '{area}'"
        region_field = "REGION_NAME,"
    else:
        table = "US_national"
        region_where = ""
        region_field = ""

    sql_str = f"""
        SELECT distinct * from (SELECT DATES as Date, {region_field} {query_model}, AS_OF_DATE
        FROM [LO25].[dbo].[CWG_{table}] Where IS_FORECAST = 0 {region_where}
        and DATES between '{(today() - dt.timedelta(days=28)).strftime('%Y-%m-%d')}' and '[RECOVERY: clipped today().strftime tail]'
    """
    raise NotImplementedError("Photographed weather_common.py SQL line118 is clipped")
    cwg_data = sql.read_sql(sql_str)
    cwg_data = cwg_data.drop_duplicates(subset=["Date"], keep="first")
    cwg_data = cwg_data.replace({pd.NA: np.nan})
    cwg_data = cwg_data.rename(columns={f"{query_model}": area})
    return cwg_data[["Date", area]]


def combine_actual_forecast_normal_global_cdd(area='asia', cycle='00', model=None):
    asia_f_cdd = get_forecast_cdd_global(area=area, cycle=cycle, model=model)
    asia_f = asia_f_cdd
    asia_a_cdd = sv.global_wdd_actual(field='pw_cdd', area=area, two_week=True)
    if pd.to_datetime(min(asia_a_cdd.Date)) > today() - dt.timedelta(days=14):
        asia_a_cdd = get_cwg_global_data_actuals(area=area, field="pw_cdd")
        if asia_a_cdd.empty:
            asia_a_cdd = sv.global_wdd_actual(field='pw_cdd', area=area, two_week=True)
    asia_a_cdd.set_index("Date", inplace=True)
    asia_a_cdd.index = pd.to_datetime(asia_a_cdd.index)
    asia_a_cdd.columns = ["Actual"]
    asia_a = asia_a_cdd
    asia_c = pd.concat([asia_f, asia_a], axis=1)
    asia_c['month'] = asia_c.index.month
    asia_c['day'] = asia_c.index.day
    asia_c.reset_index(drop=False, inplace=True)
    asia_n_cdd = sv.global_wdd_climo(field='pw_cdd', area=area)
    asia_n = asia_n_cdd.set_index('Date')
    asia_n.reset_index(inplace=True)
    asia_n.columns = ['Date', 'Normal']
    asia_n['month'] = [int(x[:2]) for x in asia_n['Date']]
    asia_n['day'] = [int(x[-2:]) for x in asia_n['Date']]
    asia = asia_c.merge(asia_n, on=['month', 'day'])
    asia.set_index('index', inplace=True)
    asia.drop(['month', 'day', 'Date'], axis=1, inplace=True)
    return asia


def combine_actual_forecast_normal_global_hdd(area='asia', cycle='00', model=None):
    asia_f_hdd = get_forecast_hdd_global(area=area, cycle=cycle, model=model)
    asia_f = asia_f_hdd
    asia_a_hdd = sv.global_wdd_actual(field='pw_hdd', area=area, two_week=True)
    if pd.to_datetime(min(asia_a_hdd.Date)) >= today() - dt.timedelta(days=14):
        asia_a_hdd = get_cwg_global_data_actuals(area=area, field="pw_hdd")
        if asia_a_hdd.empty:
            asia_a_hdd = sv.global_wdd_actual(field='pw_cdd', area=area, two_week=True)
    asia_a_hdd.set_index("Date", inplace=True)
    asia_a_hdd.index = pd.to_datetime(asia_a_hdd.index)
    asia_a_hdd.columns = ["Actual"]
    asia_a = asia_a_hdd
    asia_c = pd.concat([asia_f, asia_a], axis=1)
    asia_c['month'] = asia_c.index.month
    asia_c['day'] = asia_c.index.day
    asia_c.reset_index(drop=False, inplace=True)
    asia_n_hdd = sv.global_wdd_climo(field='pw_hdd', area=area)
    asia_n = asia_n_hdd.set_index('Date')
    asia_n.reset_index(inplace=True)
    asia_n.columns = ['Date', 'Normal']
    asia_n['month'] = [int(x[:2]) for x in asia_n['Date']]
    asia_n['day'] = [int(x[-2:]) for x in asia_n['Date']]
    asia = asia_c.merge(asia_n, on=['month', 'day'])
    asia.set_index('index', inplace=True)
    asia.drop(['month', 'day', 'Date'], axis=1, inplace=True)
    return asia


def combine_actual_forecast_normal_global_tdd(area='asia', cycle='00', model=None):
    asia_f_hdd = get_forecast_hdd_global(area=area, cycle=cycle, model=model)
    asia_f_cdd = get_forecast_cdd_global(area=area, cycle=cycle, model=model)
    asia_f = asia_f_hdd + asia_f_cdd
    asia_a_hdd = sv.global_wdd_actual(field='pw_hdd', area=area, two_week=True)
    if pd.to_datetime(min(asia_a_hdd.Date)) > today() - dt.timedelta(days=14):
        asia_a_hdd = get_cwg_global_data_actuals(area=area, field="pw_hdd")
    asia_a_hdd.set_index("Date", inplace=True)
    asia_a_hdd.index = pd.to_datetime(asia_a_hdd.index)
    asia_a_hdd.columns = ["Actual"]
    asia_a_cdd = sv.global_wdd_actual(field='pw_cdd', area=area, two_week=True)
    if pd.to_datetime(min(asia_a_cdd.Date)) > today() - dt.timedelta(days=14):
        asia_a_cdd = get_cwg_global_data_actuals(area=area, field="pw_cdd")
    asia_a_cdd.set_index("Date", inplace=True)
    asia_a_cdd.index = pd.to_datetime(asia_a_cdd.index)
    asia_a_cdd.columns = ["Actual"]
    asia_a = asia_a_hdd + asia_a_cdd
    asia_c = pd.concat([asia_f, asia_a], axis=1)
    asia_c['month'] = asia_c.index.month
    asia_c['day'] = asia_c.index.day
    asia_c.reset_index(drop=False, inplace=True)
    asia_n_hdd = sv.global_wdd_climo(field='pw_hdd', area=area)
    asia_n_cdd = sv.global_wdd_climo(field='pw_cdd', area=area)
    asia_n = asia_n_hdd.set_index('Date') + asia_n_cdd.set_index('Date')
    asia_n.reset_index(inplace=True)
    asia_n.columns = ['Date', 'Normal']
    asia_n['month'] = [int(x[:2]) for x in asia_n['Date']]
    asia_n['day'] = [int(x[-2:]) for x in asia_n['Date']]
    asia = asia_c.merge(asia_n, on=['month', 'day'])
    asia.set_index('index', inplace=True)
    asia.drop(['month', 'day', 'Date'], axis=1, inplace=True)
    return asia


def get_national_us(flag=1, cycle='00', field='ew_cdd', model=None):
    tbl_sfx = _get_model_sfx(model)
    cycle_where = f"and cycle='{cycle}'" if model != "EC46" else ''
    flag_where = f"and flag='{flag}'" if model != "EC46" else ''
    sql_str = f"""select t1.* from [LO25].[dbo].[CWG_StormVista_US_National{tbl_sfx}] t1 INNER JOIN
                    (select Top (3) AS_OF_DATE as dt from [LO25].[dbo].[CWG_StormVista_US_National{tbl_sfx}] group by As_of_date
                    order by As_of_date desc) t2 on t1.AS_OF_DATE = t2.dt
                    where Field='{field}' {cycle_where} {flag_where} order by AS_OF_DATE desc, Dates"""
    data_f = sql.read_sql(sql_str)
    data_f['Dates'] = pd.to_datetime(data_f['Dates'])
    data_f['As_of_date'] = pd.to_datetime(data_f['As_of_date'])
    df = pd.DataFrame()
    dates = data_f['As_of_date'].unique()
    for i in dates:
        df_temp = data_f.loc[data_f['As_of_date'] == i, ['Dates', 'Value']]
        df_temp.set_index('Dates', inplace=True)
        df_temp.columns = [i]
        df = pd.concat([df, df_temp], axis=1)
    df.columns = [dt.datetime.strftime(x, '%Y-%m-%d') for x in df.columns]
    return df


def get_regional_us(cycle='00', area='East', field='ew_cdd', model=None):
    tbl_sfx = _get_model_sfx(model)
    cycle_where = f"and cycle='{cycle}'" if model != "EC46" else ''
    sql_str = f"""select t1.* from [LO25].[dbo].[CWG_StormVista_US_Regional{tbl_sfx}] t1 INNER JOIN
                    (select Top (3) AS_OF_DATE as dt from [LO25].[dbo].[CWG_StormVista_US_Regional{tbl_sfx}] group by As_of_date
                    order by As_of_date desc) t2 on t1.AS_OF_DATE = t2.dt
                    where Region = '{area}' {cycle_where} and Field='{field}' order by AS_OF_DATE desc, Dates"""
    data_f = sql.read_sql(sql_str)
    data_f['Dates'] = pd.to_datetime(data_f['Dates'])
    data_f['As_of_date'] = pd.to_datetime(data_f['As_of_date'])
    df = pd.DataFrame()
    dates = data_f['As_of_date'].unique()
    for i in dates:
        df_temp = data_f.loc[data_f['As_of_date'] == i, ['Dates', 'Value']]
        df_temp.set_index('Dates', inplace=True)
        df_temp.columns = [i]
        df = pd.concat([df, df_temp], axis=1)
    df.columns = [dt.datetime.strftime(x, '%Y-%m-%d') for x in df.columns]
    return df


def combine_actual_forecast_normal_us_tdd(cycle='00', area='national', model=None):
    if area == 'national':
        f_cdd = get_national_us(1, cycle=cycle, field='ew_cdd', model=model)
        f_hdd = get_national_us(1, cycle=cycle, field='gw_hdd', model=model)
        us_f = f_cdd + f_hdd
        asia_a_cdd = sv.us_wdd_national_actual(field='ew_cdd')
        if pd.to_datetime(min(asia_a_cdd.Date)) > today() - dt.timedelta(days=14):
            asia_a_cdd = get_cwg_us_data_actuals(area=area, field='ew_cdd')
        asia_a_cdd.set_index("Date", inplace=True)
        asia_a_cdd.index = pd.to_datetime(asia_a_cdd.index)
        asia_a_cdd.columns = ["Actual"]
        asia_a_hdd = sv.us_wdd_national_actual(field='gw_hdd')
        if pd.to_datetime(min(asia_a_hdd.Date)) > today() - dt.timedelta(days=14):
            asia_a_hdd = get_cwg_us_data_actuals(area=area, field='gw_hdd')
        asia_a_hdd.set_index("Date", inplace=True)
        asia_a_hdd.index = pd.to_datetime(asia_a_hdd.index)
        asia_a_hdd.columns = ["Actual"]
        asia_a = asia_a_cdd + asia_a_hdd
        asia_c = pd.concat([us_f, asia_a], axis=1)
        asia_c['month'] = asia_c.index.month
        asia_c['day'] = asia_c.index.day
        asia_c.reset_index(drop=False, inplace=True)
        asia_n_cdd = sv.us_wdd_national_climo(field='ew_cdd')
        asia_n_cdd = asia_n_cdd.set_index('Date')
        asia_n_hdd = sv.us_wdd_national_climo(field='gw_hdd')
        asia_n_hdd = asia_n_hdd.set_index('Date')
        asia_n = asia_n_hdd + asia_n_cdd
        asia_n.reset_index(inplace=True)
        asia_n.columns = ['Date', 'Normal']
        asia_n['month'] = [int(x[:2]) for x in asia_n['Date']]
        asia_n['day'] = [int(x[-2:]) for x in asia_n['Date']]
        asia = asia_c.merge(asia_n, on=['month', 'day'])
        asia.set_index('index', inplace=True)
        asia.drop(['month', 'day', 'Date'], axis=1, inplace=True)
        return asia

    else:
        f_cdd = get_regional_us(cycle=cycle, area=area, field='ew_cdd', model=model)
        f_hdd = get_regional_us(cycle=cycle, area=area, field='gw_hdd', model=model)
        us_f = f_cdd + f_hdd
        asia_a_cdd = sv.us_wdd_regional_actual(field='ew_cdd')
        if pd.to_datetime(min(asia_a_cdd.Date)) > today() - dt.timedelta(days=14):
            asia_a_cdd = get_cwg_us_data_actuals(area=area, field='ew_cdd', region=area)
        asia_a_cdd.set_index("Date", inplace=True)
        asia_a_cdd = asia_a_cdd[[area]]
        asia_a_cdd.index = pd.to_datetime(asia_a_cdd.index)
        asia_a_cdd.columns = ["Actual"]
        asia_a_hdd = sv.us_wdd_regional_actual(field='gw_hdd')
        if pd.to_datetime(min(asia_a_hdd.Date)) > today() - dt.timedelta(days=14):
            asia_a_hdd = get_cwg_us_data_actuals(area=area, field='gw_hdd', region=area)
        asia_a_hdd.set_index("Date", inplace=True)
        asia_a_hdd = asia_a_hdd[[area]]
        asia_a_hdd.index = pd.to_datetime(asia_a_cdd.index)
        asia_a_hdd.columns = ["Actual"]
        asia_a = asia_a_cdd + asia_a_hdd
        asia_c = pd.concat([us_f, asia_a], axis=1)
        asia_c['month'] = asia_c.index.month
        asia_c['day'] = asia_c.index.day
        asia_c.reset_index(drop=False, inplace=True)
        asia_n_cdd = sv.us_wdd_regional_climo(field='ew_cdd')
        asia_n_cdd = asia_n_cdd.set_index('Date')
        asia_n_cdd = asia_n_cdd[[area]]
        asia_n_hdd = sv.us_wdd_regional_climo(field='gw_hdd')
        asia_n_hdd = asia_n_hdd.set_index('Date')
        asia_n_hdd = asia_n_hdd[[area]]
        asia_n = asia_n_hdd + asia_n_cdd
        asia_n.reset_index(inplace=True)
        asia_n.columns = ['Date', 'Normal']
        asia_n['month'] = [int(x[:2]) for x in asia_n['Date']]
        asia_n['day'] = [int(x[-2:]) for x in asia_n['Date']]
        asia = asia_c.merge(asia_n, on=['month', 'day'])
        asia.set_index('index', inplace=True)
        asia.drop(['month', 'day', 'Date'], axis=1, inplace=True)
        return asia


def combine_actual_forecast_normal_us(cycle='00', area='national', is_cdd=True, model=None):
    field = 'ew_cdd' if is_cdd else 'gw_hdd'
    if area == 'national':
        f_cdd = get_national_us(1, cycle=cycle, field=field, model=model)
        us_f = f_cdd
        asia_a_cdd = sv.us_wdd_national_actual(field=field)
        if pd.to_datetime(min(asia_a_cdd.Date)) > today() - dt.timedelta(days=14):
            asia_a_cdd = get_cwg_us_data_actuals(area=area, field=field)
        asia_a_cdd.set_index("Date", inplace=True)
        asia_a_cdd.index = pd.to_datetime(asia_a_cdd.index)
        asia_a_cdd.columns = ["Actual"]
        asia_a = asia_a_cdd
        asia_c = pd.concat([us_f, asia_a], axis=1)
        asia_c['month'] = asia_c.index.month
        asia_c['day'] = asia_c.index.day
        asia_c.reset_index(drop=False, inplace=True)
        asia_n_cdd = sv.us_wdd_national_climo(field=field)
        asia_n = asia_n_cdd.set_index('Date')
        asia_n.reset_index(inplace=True)
        asia_n.columns = ['Date', 'Normal']
        asia_n['month'] = [int(x[:2]) for x in asia_n['Date']]
        asia_n['day'] = [int(x[-2:]) for x in asia_n['Date']]
        asia = asia_c.merge(asia_n, on=['month', 'day'])
        asia.set_index('index', inplace=True)
        asia.drop(['month', 'day', 'Date'], axis=1, inplace=True)
        return asia

    else:
        f_cdd = get_regional_us(cycle=cycle, area=area, field=field, model=model)
        us_f = f_cdd
        asia_a_cdd = sv.us_wdd_regional_actual(field=field)
        if pd.to_datetime(min(asia_a_cdd.Date)) > today() - dt.timedelta(days=14):
            asia_a_cdd = get_cwg_us_data_actuals(area=area, field=field, region=area)
        asia_a_cdd.set_index("Date", inplace=True)
        asia_a_cdd = asia_a_cdd[[area]]
        asia_a_cdd.index = pd.to_datetime(asia_a_cdd.index)
        asia_a_cdd.columns = ["Actual"]
        asia_a = asia_a_cdd
        asia_c = pd.concat([us_f, asia_a], axis=1)
        asia_c['month'] = asia_c.index.month
        asia_c['day'] = asia_c.index.day
        asia_c.reset_index(drop=False, inplace=True)
        asia_n_cdd = sv.us_wdd_regional_climo(field=field)
        asia_n = asia_n_cdd.set_index('Date')
        asia_n = asia_n[[area]]
        asia_n.reset_index(inplace=True)
        asia_n.columns = ['Date', 'Normal']
        asia_n['month'] = [int(x[:2]) for x in asia_n['Date']]
        asia_n['day'] = [int(x[-2:]) for x in asia_n['Date']]
        asia = asia_c.merge(asia_n, on=['month', 'day'])
        asia.set_index('index', inplace=True)
        asia.drop(['month', 'day', 'Date'], axis=1, inplace=True)
        return asia


def get_chart(data, title=None, **kwargs):
    y_axis_title = kwargs.get('y_axis_title', None)
    x_axis_title = kwargs.get('x_axis_title', None)
    file_path = kwargs.get('file_path', None)
    data1 = kwargs.get('data1', None)
    data2 = kwargs.get('data2', None)

    if data1 is None and data2 is None:
        fig = go.Figure()
        for idx, col in enumerate(list(data.columns)):
            if idx == 0:
                raise NotImplementedError("Photographed weather_common.py first-series Scatter style is clipped")
            elif idx == 1:
                fig.add_trace(go.Scatter(x=data.index, y=data[col], showlegend=True, name=col,
                                        line=dict(width=2, color='red', dash='dash')))
            elif idx == 2:
                fig.add_trace(go.Scatter(x=data.index, y=data[col], showlegend=True, name=col,
                                        line=dict(width=1, color='orange', dash='dash')))
            else:
                raise NotImplementedError("Photographed weather_common.py remaining-series Scatter style is clipped")
        fig.update_layout(
            title={'text': title,
                   'x': 0.5,
                   'xanchor': 'center'},
            xaxis_title=x_axis_title,
            yaxis_title=y_axis_title,
            width=900, height=600)
    elif data1 is not None and data2 is None:
        fig = make_subplots(rows=2, cols=1, row_heights=[0.7, 0.3], shared_xaxes=True, vertical_spacing=0.02,
                            specs=[[{"secondary_y": False}], [{"secondary_y": False}]])
        for idx, col in enumerate(list(data.columns)):
            if idx == 0:
                raise NotImplementedError("Photographed weather_common.py first-series Scatter style is clipped")
            elif idx == 1:
                fig.add_trace(go.Scatter(x=data.index, y=data[col], showlegend=True, name=col,
                                        line=dict(width=2, color='red', dash='dash')))
            elif idx == 2:
                fig.add_trace(go.Scatter(x=data.index, y=data[col], showlegend=True, name=col,
                                        line=dict(width=1, color='orange', dash='dash')))
            else:
                raise NotImplementedError("Photographed weather_common.py remaining-series Scatter style is clipped")
        if len(data1.columns) == 1:
            fig.add_trace(go.Scatter(x=data1.index, y=data1.iloc[:, 0], showlegend=True, name=data1.columns[0],
                                    line=dict(width=2)), row=2, col=1)
        else:
            for j in range(len(data1.columns)):
                fig.add_trace(go.Scatter(x=data1.index, y=data1.iloc[:, j], showlegend=True, name=data1.columns[j],
                                        line=dict(width=2)), row=2, col=1)

        fig.update_layout(
            title={'text': title,
                   'x': 0.5,
                   'xanchor': 'center'},
            xaxis_title=x_axis_title,
            yaxis_title=y_axis_title,
            width=900, height=600)
    else:
        fig = make_subplots(rows=3, cols=1, row_heights=[0.5, 0.25, 0.25], shared_xaxes=True, vertical_spacing=0.02,
                            specs=[[{"secondary_y": False}], [{"secondary_y": False}], [{"secondary_y": False}]])
        for idx, col in enumerate(list(data.columns)):
            if idx == 0:
                raise NotImplementedError("Photographed weather_common.py first-series Scatter style is clipped")
            elif idx == 1:
                fig.add_trace(go.Scatter(x=data.index, y=data[col], showlegend=True, name=col,
                                        line=dict(width=2, color='red', dash='dash')))
            elif idx == 2:
                fig.add_trace(go.Scatter(x=data.index, y=data[col], showlegend=True, name=col,
                                        line=dict(width=1, color='orange', dash='dash')))
            else:
                raise NotImplementedError("Photographed weather_common.py remaining-series Scatter style is clipped")
        if len(data1.columns) == 1:
            fig.add_trace(go.Scatter(x=data1.index, y=data1.iloc[:, 0], showlegend=True, name=data1.columns[0],
                                    line=dict(width=2)), row=2, col=1)
        else:
            for j in range(len(data1.columns)):
                fig.add_trace(go.Scatter(x=data1.index, y=data1.iloc[:, j], showlegend=True, name=data1.columns[j],
                                        line=dict(width=2)), row=2, col=1)

        if len(data2.columns) == 1:
            fig.add_trace(go.Scatter(x=data2.index, y=data2.iloc[:, 0], showlegend=True, name=data2.columns[0],
                                    line=dict(width=2)), row=3, col=1)
        else:
            for j in range(len(data2.columns)):
                fig.add_trace(go.Scatter(x=data2.index, y=data2.iloc[:, j], showlegend=True, name=data2.columns[j],
                                        line=dict(width=2)), row=3, col=1)

        fig.update_layout(
            title={'text': title,
                   'x': 0.5,
                   'xanchor': 'center'},
            xaxis_title=x_axis_title,
            yaxis_title=y_axis_title,
            width=900, height=800)

    if file_path is not None:
        py.offline.plot(fig, auto_open=False, filename=file_path)
    return fig


def demand_forecast_chart(fcast_df, title, bbg_tdd=None, bbg_tdd1=None, type="cdd", ):
    fcast_df = fcast_df.loc[fcast_df.index >= fcast_df.index[-1] - dt.timedelta(days=55), :]
    if bbg_tdd is not None and bbg_tdd1 is None:
        bbg_tdd = pd.concat(
            [bbg_tdd, fcast_df.loc[fcast_df.index > bbg_tdd.index[-1], 'Actual'].to_frame(bbg_tdd.columns[0])], axis=0)
        return get_chart(fcast_df, title=title, y_axis_title=type, data1=bbg_tdd.reindex(fcast_df.index))
    elif bbg_tdd is not None and bbg_tdd1 is not None:
        bbg_tdd = pd.concat(
            [bbg_tdd, fcast_df.loc[fcast_df.index > bbg_tdd.index[-1], 'Actual'].to_frame(bbg_tdd.columns[0])], axis=0)
        bbg_tdd1 = pd.concat(
            [bbg_tdd1, fcast_df.loc[fcast_df.index > bbg_tdd1.index[-1], 'Actual'].to_frame(bbg_tdd1.columns[0])],
            axis=0)
        return get_chart(fcast_df, title=title, y_axis_title=type, data1=bbg_tdd.reindex(fcast_df.index),
                         data2=bbg_tdd1.reindex(fcast_df.index))
    else:
        return get_chart(fcast_df, title=title, y_axis_title=type)


def get_seasonal_forecast(region, month_season):
    data = sql.read_sql(f"Select * from CWG_Seasonal_Forecast where Region='{region}' and Month_Season='{month_season}'")
    data.drop_duplicates(inplace=True)
    data.set_index("Issued_Date", inplace=True)
    data.index = pd.to_datetime(data.index)
    return data


if __name__ == '__main__':
    x = combine_actual_forecast_normal_us(cycle='00', area='national', is_cdd=False)
    print(x)
