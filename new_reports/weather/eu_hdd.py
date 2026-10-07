import pandas as pd
import numpy as np
import datetime as dt
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import plotly as py
import sys
from dateutil.relativedelta import relativedelta
import ecm.cmds.stormvista as sv
import ecm.cmds.sql as sql
import ecm.cmds.table as table
import ecm.cmds.chart as chart
import ecm.cmds.bbg as bbg
import ecm.cmds.time_series as ts
from ecm.cmds.config import output_path, html_path, root_path, gas_group
from ecm.cmds._email import send_email
from ecm.cmds.cdr import today
from weather_common import combine_actual_forecast_normal_global_hdd as combine_actual_forecast_normal
from ecm.cmds.utils import convert_path_to_linux
from weather_common import get_seasonal_forecast

send_to = gas_group
report_name = "Weather - Europe CWG HDD Update"
file_name = "eu_tdd"  # without .py
file_path = f"{root_path}\\autoreports\\reports\\weather\\{file_name}.py"
weather_csv = f"{output_path}\\csvs\\weather"


def _unrecovered(location):
    raise NotImplementedError(f"eu_hdd photographed source: {location}")


def get_forecast_hdd(area, cycle='00'):
    """
    Last 3 forecasts from Stormvista
    """
    sql_str = f"""select t1.* from CWG_StormVista_Global_fcast t1 INNER JOIN
                    (select Top (3) AS_OF_DATE as dt from CWG_StormVista_Global_fcast group by As_of_date
                    order by As_of_date desc) t2 on t1.AS_OF_DATE = t2.dt
                    where region='{area}' and cycle='{cycle}' and Field='pw_hdd' order by AS_OF_DATE desc, Dates"""
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


def get_forecast_cdd(area, cycle='00'):
    """
    Last 3 forecasts from Stormvista
    """
    sql_str = f"""select t1.* from CWG_StormVista_Global_fcast t1 INNER JOIN
                    (select Top (3) AS_OF_DATE as dt from CWG_StormVista_Global_fcast group by As_of_date
                    order by As_of_date desc) t2 on t1.AS_OF_DATE = t2.dt
                    where region='{area}' and cycle='{cycle}' and Field='pw_cdd' order by AS_OF_DATE desc, Dates"""
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


def demand_forecast_chart(fcast_df, title, bbg_tdd=None, bbg_tdd1=None):
    fcast_df = fcast_df.loc[fcast_df.index >= fcast_df.index[-1] - dt.timedelta(days=35), :]
    if bbg_tdd is not None and bbg_tdd1 is None:
        bbg_tdd = pd.concat(
            [bbg_tdd, fcast_df.loc[fcast_df.index > bbg_tdd.index[-1], 'Actual'].to_frame(bbg_tdd.columns[0])], axis=0)
        return get_chart(fcast_df, title=title, y_axis_title='hdd', data1=bbg_tdd)
    elif bbg_tdd is not None and bbg_tdd1 is not None:
        bbg_tdd = pd.concat(
            [bbg_tdd, fcast_df.loc[fcast_df.index > bbg_tdd.index[-1], 'Actual'].to_frame(bbg_tdd.columns[0])], axis=0)
        bbg_tdd1 = pd.concat(
            [bbg_tdd1, fcast_df.loc[fcast_df.index > bbg_tdd1.index[-1], 'Actual'].to_frame(bbg_tdd1.columns[0])], axis=0)
        return get_chart(fcast_df, title=title, y_axis_title='hdd', data1=bbg_tdd,
                         data2=bbg_tdd1)
    else:
        return get_chart(fcast_df, title=title, y_axis_title='hdd')


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
                fig.add_trace(
                    go.Scatter(x=data.index, y=data[col], showlegend=True, name=col,
                               line=dict(width=2, **_unrecovered('get_chart original line 104: clipped line color/style'))))
            elif idx == 1:
                fig.add_trace(go.Scatter(x=data.index, y=data[col], showlegend=True, name=col,
                                         line=dict(width=2, color='red', dash='dash')))
            elif idx == 2:
                fig.add_trace(go.Scatter(x=data.index, y=data[col], showlegend=True, name=col,
                                         line=dict(width=1, color='orange', dash='dash')))
            else:
                fig.add_trace(go.Scatter(x=data.index, y=data[col], showlegend=True, name=col,
                                         line=_unrecovered('get_chart original line 112: clipped line style')))
        fig.update_layout(
            title={'text': title,
                   'x': 0.5,
                   'xanchor': 'center'},
            xaxis_title=x_axis_title,
            yaxis_title=y_axis_title,
            width=900, height=600)
    elif data1 is not None and data2 is None:
        fig = make_subplots(rows=3, cols=1, row_heights=[0.67, 0.33], shared_xaxes=True,
                            vertical_spacing=0.02,
                            specs=[[{"secondary_y": False}], [{"secondary_y": False}]])
        for idx, col in enumerate(list(data.columns)):
            if idx == 0:
                fig.add_trace(
                    go.Scatter(x=data.index, y=data[col], showlegend=True, name=col,
                               line=dict(width=2, **_unrecovered('get_chart original line 126: clipped line color/style'))))
            elif idx == 1:
                fig.add_trace(go.Scatter(x=data.index, y=data[col], showlegend=True, name=col,
                                         line=dict(width=2, color='red', dash='dash')))
            elif idx == 2:
                fig.add_trace(go.Scatter(x=data.index, y=data[col], showlegend=True, name=col,
                                         line=dict(width=1, color='orange', dash='dash')))
            else:
                fig.add_trace(go.Scatter(x=data.index, y=data[col], showlegend=True, name=col,
                                         line=_unrecovered('get_chart original line 134: clipped line style')))
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
        fig = make_subplots(rows=3, cols=1, row_heights=[0.5, 0.25, 0.25], shared_xaxes=True,
                            vertical_spacing=_unrecovered('original line 151: clipped subplot spacing'),
                            specs=[[{"secondary_y": False}], [{"secondary_y": False}], [{"secondary_y": False}]])
        for idx, col in enumerate(list(data.columns)):
            if idx == 0:
                fig.add_trace(
                    go.Scatter(x=data.index, y=data[col], showlegend=True, name=col,
                               line=dict(width=2, **_unrecovered('get_chart original line 156: clipped line color/style'))))
            elif idx == 1:
                fig.add_trace(go.Scatter(x=data.index, y=data[col], showlegend=True, name=col,
                                         line=dict(width=2, color='red', dash='dash')))
            elif idx == 2:
                fig.add_trace(go.Scatter(x=data.index, y=data[col], showlegend=True, name=col,
                                         line=dict(width=1, color='orange', dash='dash')))
            else:
                fig.add_trace(go.Scatter(x=data.index, y=data[col], showlegend=True, name=col,
                                         line=_unrecovered('get_chart original line 164: clipped line style')))
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


def winter_hdd(a_df, winsum='W'):
    """
    historical and 10Y normal daily HDDs from CWG
    """

    season = a_df.copy()

    season['month'] = season.index.month
    season['year'] = season.index.year
    season['day'] = season.index.day


    season.loc[(season['month'] >= 5), 'Season'] = 'S'
    season.loc[(season['month'] >= 10) | (season['month'] <= 4), 'Season'] = 'W'


    season.loc[(season['month'] >= 5), 'Syr'] = (season['year']).astype(str)
    season.loc[(season['month'] < 5), 'Syr'] = (season['year'] - 1).astype(str)
    season['Season_year'] = season['Season'] + season['Syr'].astype(str)

    season['Month_year'] = season['month'].astype(str) + "-" + season['year'].astype(str)

    season['Actuals_vs_Normal'] = season['NG_HDD'] - season['10Y_NG_HDD']

    season['Cumulative'] = season.groupby('Season_year')['NG_HDD'].cumsum()

    season['Cumulative of Actual_vs_Normal per season'] = season.groupby('Season_year')['Actuals_vs_Normal'].cumsum()

    season['day_count'] = season.groupby('Season_year').cumcount() + 1

    season['Cumulative of Actual_vs_Normal per month'] = season.groupby(['year', 'month'])['Actuals_vs_Normal'].cumsum()

    season['Cumulative_monthly'] = season.groupby(['year', 'month'])['NG_HDD'].cumsum()

    winter = season.loc[(season['Season'] == winsum) & (season.index >= '2010-10-01')]
    return winter


def cumulative_hdd_chart(winter, hdd_df, title='Cumulative winter HDDs vs 10Y normal'):

    winterpvt2 = pd.pivot_table(winter, columns=['Season_year'], index=['day_count'],
                                values='Cumulative of Actual_vs_Normal per season')
    winterpvt2_email = winterpvt2[winterpvt2.columns[-6:]]

    lvi = winterpvt2_email.iloc[:, -1].last_valid_index()
    if lvi < len(winterpvt2_email):
        last_col = winterpvt2_email.columns[-1]
        winterpvt2_email['Latest forecast'] = winterpvt2_email.loc[lvi - len(hdd_df) + 1: lvi, last_col]
        winterpvt2_email.loc[lvi - len(hdd_df) + 1: lvi, last_col] = np.nan

    base_date = hdd_df.index[0] - dt.timedelta(days=1)
    if base_date.month >= 9:
        date_idx = pd.date_range(dt.datetime(base_date.year, 10, 1), dt.datetime(base_date.year + 1, 4, 30))
    elif base_date.month < 5:
        date_idx = pd.date_range(dt.datetime(base_date.year - 1, 10, 1), dt.datetime(base_date.year, 4, 30))
    else:
        date_idx = pd.date_range(dt.datetime(base_date.year - 1, 10, 1), dt.datetime(base_date.year, 4, 30))
    if len(date_idx) < len(winterpvt2_email):
        winterpvt2_email = winterpvt2_email.iloc[:len(date_idx), :]
    elif len(date_idx) > len(winterpvt2_email):
        date_idx = date_idx[:len(winterpvt2_email)]
    winterpvt2_email['dates'] = date_idx
    winterpvt2_email.set_index('dates', inplace=True)

    dataPanda6 = []

    for j in range(0, len(winterpvt2_email.columns)):
        if j == len(winterpvt2_email.columns) - 2:
            trace = go.Scatter(x=winterpvt2_email.index, y=winterpvt2_email.iloc[:, j], connectgaps=True,
                               name=(winterpvt2_email.columns[j]), mode='lines',
                               line=dict(width=3, color=_unrecovered('original line 280: clipped color beginning b')))
            dataPanda6.append(trace)
        elif j == len(winterpvt2_email.columns) - 1:
            trace = go.Scatter(x=winterpvt2_email.index, y=winterpvt2_email.iloc[:, j], connectgaps=True,
                               name=(winterpvt2_email.columns[j]), mode='lines',
                               line=dict(width=3, color='black', dash='dash'))
            dataPanda6.append(trace)
        else:
            trace = go.Scatter(x=winterpvt2_email.index, y=winterpvt2_email.iloc[:, j], connectgaps=True,
                               name=(winterpvt2_email.columns[j]), mode='lines')
            dataPanda6.append(trace)

    layout6 = go.Layout(title=title, width=900, height=600)
    fig6 = go.Figure(data=dataPanda6, layout=layout6)
    return fig6


def cumulative_cdd_chart(winter, hdd_df, title='Cumulative summer CDDs vs 10Y normal', lookback: bool=False, winsum=...):

    winterpvt2 = pd.pivot_table(winter, columns=['Season_year'], index=['day_count'],
                                values='Cumulative of Actual_vs_Normal per season')
    winterpvt2_email = winterpvt2[winterpvt2.columns[-6:]]

    lvi = winterpvt2_email.iloc[:, -1].last_valid_index()
    if lvi < len(winterpvt2_email):
        last_col = winterpvt2_email.columns[-1]
        winterpvt2_email['Latest forecast'] = winterpvt2_email.loc[lvi - len(hdd_df) + 1: lvi, last_col]
        winterpvt2_email.loc[lvi - len(hdd_df) + 1: lvi, last_col] = np.nan

    if not lookback:
        base_date = hdd_df.index[0]
        if base_date.month >= 9:
            date_idx = pd.date_range(dt.datetime(base_date.year, 10, 1), dt.datetime(base_date.year + 1, 4, 30))
        elif base_date.month < 5:
            date_idx = pd.date_range(dt.datetime(base_date.year - 1, 10, 1), dt.datetime(base_date.year, 4, 30))
        else:
            date_idx = pd.date_range(dt.datetime(base_date.year, 5, 1), dt.datetime(base_date.year, 9, 30))
        if len(date_idx) < len(winterpvt2_email):
            winterpvt2_email = winterpvt2_email.iloc[:-1, :]
        winterpvt2_email['dates'] = date_idx
        winterpvt2_email.set_index('dates', inplace=True)
    else:
        base_date = hdd_df.index[0]
        base_date = dt.datetime(base_date.year, 6, 1) if winsum == "S" else dt.datetime(base_date.year, 10, 1)
        if base_date.month >= 9:
            date_idx = pd.date_range(dt.datetime(base_date.year, 10, 1), dt.datetime(base_date.year + 1, 4, 30))
        elif base_date.month < 5:
            date_idx = pd.date_range(dt.datetime(base_date.year - 1, 10, 1), dt.datetime(base_date.year, 4, 30))
        else:
            date_idx = pd.date_range(dt.datetime(base_date.year, 5, 1), dt.datetime(base_date.year, 9, 30))
        if len(date_idx) < len(winterpvt2_email):
            winterpvt2_email = winterpvt2_email.iloc[:-1, :]
        winterpvt2_email['dates'] = date_idx
        winterpvt2_email.set_index('dates', inplace=True)

    dataPanda6 = []

    for j in range(0, len(winterpvt2_email.columns)):
        if j == len(winterpvt2_email.columns) - 2:
            trace = go.Scatter(x=winterpvt2_email.index, y=winterpvt2_email.iloc[:, j], connectgaps=True,
                               name=(winterpvt2_email.columns[j]), mode='lines',
                               line=dict(width=3, color=_unrecovered('original line 347: clipped color beginning b')))
            dataPanda6.append(trace)
        elif j == len(winterpvt2_email.columns) - 1:
            trace = go.Scatter(x=winterpvt2_email.index, y=winterpvt2_email.iloc[:, j], connectgaps=True,
                               name=(winterpvt2_email.columns[j]), mode='lines',
                               line=dict(width=3, color='black', dash='dash'))
            dataPanda6.append(trace)
        else:
            trace = go.Scatter(x=winterpvt2_email.index, y=winterpvt2_email.iloc[:, j], connectgaps=True,
                               name=(winterpvt2_email.columns[j]), mode='lines')
            dataPanda6.append(trace)

    layout6 = go.Layout(title=title, width=900, height=600)
    fig6 = go.Figure(data=dataPanda6, layout=layout6)
    return fig6


def witer_month_table(winter, winsum='W'):
    'HDD vs 10Y normal by month for each winter'
    df_eom2 = winter[['Actuals_vs_Normal']]

    df_eom2 = df_eom2.resample("MS").sum()
    df_eom2['month'] = df_eom2.index.month
    df_eom2['year'] = df_eom2.index.year


    df_eom2.loc[(df_eom2['month'] >= 5), 'Season'] = 'S'
    df_eom2.loc[(df_eom2['month'] >= 10) | (df_eom2['month'] <= 4), 'Season'] = 'W'
    df_eom2.loc[(df_eom2['month'] >= 5), 'Syr'] = (df_eom2['year']).astype(str)
    df_eom2.loc[(df_eom2['month'] < 5), 'Syr'] = (df_eom2['year'] - 1).astype(str)
    df_eom2['Season_year'] = df_eom2['Season'] + df_eom2['Syr'].astype(str)

    df_eom2_winter = df_eom2.loc[(df_eom2['Season'] == winsum) & (df_eom2.index >= '2016-10-01')]

    df_eom2_winter['Actuals_vs_Normal'] = df_eom2_winter['Actuals_vs_Normal'].astype('float')

    df_eom2_winterpvt = pd.pivot_table(df_eom2_winter, columns=['Season_year'], index=['month'],
                                      values='Actuals_vs_Normal')

    if winsum == 'W':
        df_eom2_winterpvt = df_eom2_winterpvt.reindex([10, 11, 12, 1, 2, 3, 4])
        df_eom2_winterpvt.loc['Total', :] = df_eom2_winterpvt.sum(axis=0)
        df_eom2_winterpvt.insert(loc=0, column='month', value=['Oct', 'Nov', 'Dec', 'Jan', 'Feb', 'Mar', 'Apr', 'Total'])
    elif winsum == 'S':
        df_eom2_winterpvt = df_eom2_winterpvt.reindex([5, 6, 7, 8, 9])
        df_eom2_winterpvt.loc['Total', :] = df_eom2_winterpvt.sum(axis=0)
        df_eom2_winterpvt.insert(loc=0, column='month', value=['May', 'Jun', 'Jul', 'Aug', 'Sep', 'Total'])

    df_eom2_winterpvt.index.name = None
    df_eom2_winterpvt.columns.name = None
    df_eom2_winterpvt.reset_index(drop=True, inplace=True)
    return df_eom2_winterpvt


def monthly_tdd_evolution(cur_m_sdate, eu_actual):
    cur_m_actual = eu_actual.loc[eu_actual.index >= cur_m_sdate, "NG_HDD"]
    cur_m_dts = pd.date_range(cur_m_sdate, cur_m_sdate + relativedelta(day=31))
    cur_m_norm = eu_actual.loc[(eu_actual.index >= cur_m_dts[0] - relativedelta(years=1)) & (
        eu_actual.index <= cur_m_dts[-1] - relativedelta(years=1)), "10Y_NG_HDD"]
    cur_m_norm.index = [x + relativedelta(years=1) for x in cur_m_norm.index]
    loop_list = pd.date_range(cur_m_sdate - dt.timedelta(15), today())
    cur_m_tdd = pd.Series(0, index=loop_list)
    for j in loop_list:
        hist_fcst = sql.read_sql(
            f"Select * from CWG_Fcast_Europe where AS_OF_DATE='{j.strftime('%Y-%m-%d')}' and REGION='Europe' order by DATES")
        hist_fcst.set_index("DATES", inplace=True)
        hist_fcst.index = pd.to_datetime(hist_fcst.index)
        cur_d_fcst = hist_fcst["POP_HDD"]
        if len(cur_d_fcst) > 0:
            cur_d = pd.Series(0, index=cur_m_dts)
            if cur_d_fcst.index[-1] < cur_m_dts[0]:
                cur_d = cur_m_norm.copy()
            elif cur_d_fcst.index[0] <= cur_m_dts[0]:
                cur_d = cur_m_norm.copy()
                cur_d[:cur_d_fcst.index[-1]] = cur_d_fcst[cur_m_dts[0]:]
            elif cur_d_fcst.index[-1] >= cur_m_dts[-1]:
                cur_d[:cur_d_fcst.index[0] - dt.timedelta(1)] = cur_m_actual[:cur_d_fcst.index[0] - dt.timedelta(1)]
                cur_d[cur_d_fcst.index[0]:] = cur_d_fcst[:cur_m_dts[-1]]
            else:
                cur_d = cur_m_norm.copy()
                cur_d[:cur_d_fcst.index[0] - dt.timedelta(1)] = cur_m_actual[:cur_d_fcst.index[0] - dt.timedelta(1)]
                cur_d[cur_d_fcst.index] = cur_d_fcst
            cur_m_tdd[j] = cur_d.sum()
        else:
            cur_m_tdd[j] = np.nan
    return cur_m_tdd.fillna(method="ffill")


def get_hdd_cdd(region):
    df2 = sql.read_sql(
        (f"select DATES as dt, POP_HDD, POP_HDD_10Y, POP_CDD, POP_CDD_10Y from "
         f"[L025].[dbo].[CWG_Actual_Europe] where REGION='{region}' order by dt"))
    a_df = df2.drop_duplicates(subset=['dt'])
    a_df = a_df.rename(columns={"dt": "Date"})
    a_df['Date'] = pd.to_datetime(a_df['Date'])
    a_df.set_index('Date', inplace=True)
    a_df['NG_HDD'] = a_df['POP_HDD']
    a_df['10Y_NG_HDD'] = a_df['POP_HDD_10Y']
    a_df = a_df[['NG_HDD', '10Y_NG_HDD']]
    a_df.dropna(inplace=True)
    c_df = df2.drop_duplicates(subset=['dt'])
    c_df = c_df.rename(columns={"dt": "Date"})
    c_df['Date'] = pd.to_datetime(c_df['Date'])
    c_df.set_index('Date', inplace=True)
    c_df['NG_HDD'] = c_df['POP_CDD']
    c_df['10Y_NG_HDD'] = c_df['POP_CDD_10Y']
    c_df = c_df[['NG_HDD', '10Y_NG_HDD']]
    c_df.dropna(inplace=True)
    return a_df, c_df


def update(send_to=send_to):
    figs = []
    figs1 = []
    tbs = []
    tbs1 = []
    asia = combine_actual_forecast_normal(area='europe')
    china = combine_actual_forecast_normal(area='ttf')
    japan = combine_actual_forecast_normal(area='italy')
    sk = combine_actual_forecast_normal(area='uk')
    try:
        asia.to_excel(convert_path_to_linux(f"{weather_csv}\\hdd_forecast_europe.xlsx"))
    except:
        pass
    try:
        china.to_excel(convert_path_to_linux(f"{weather_csv}\\hdd_forecast_ttf.xlsx"))
    except:
        pass
    try:
        japan.to_excel(convert_path_to_linux(f"{weather_csv}\\hdd_forecast_italy.xlsx"))
    except:
        pass
    try:
        sk.to_excel(convert_path_to_linux(f"{weather_csv}\\hdd_forecast_uk.xlsx"))
    except:
        pass
    tbs.append('StormVista table (ECMWF-EPS):')
    sv_hdd = pd.read_csv(convert_path_to_linux(f"{weather_csv}\\eu_hdd_stormvista.csv"))
    tbs.append(table.html_format(sv_hdd, precision=1,
        format_column={tuple(sv_hdd.columns): {'width': '100px', 'text-align': 'center'},
                       sv_hdd.columns[-5]: {'width': '100px', 'text-align': 'center', **_unrecovered('original line 498: clipped column formatting')},
                       sv_hdd.columns[-4]: {'width': '100px', 'text-align': 'center', **_unrecovered('original line 499: clipped column formatting')},
                       sv_hdd.columns[-2]: {'width': '100px', 'text-align': 'center', **_unrecovered('original line 500: clipped column formatting')},
                       sv_hdd.columns[-1]: {'width': '100px', 'text-align': 'center', **_unrecovered('original line 501: clipped column formatting')}}))
    tbs.append('<br>')
    a_df, c_df = get_hdd_cdd(region="Europe")
    eu_actual = a_df.copy()
    cur_m_sdate = today() + relativedelta(day=1)
    cur_m_tdd = monthly_tdd_evolution(cur_m_sdate, eu_actual)
    current_date_ = today()
    next_month_ = (current_date_ + relativedelta(day=31) + relativedelta(days=1)).month
    next_year_ = (current_date_ + relativedelta(day=31) + relativedelta(days=1)).year
    if (today() + relativedelta(days=15)).month != today().month:
        next_m_sdate = today() + relativedelta(day=31) + relativedelta(days=1)
        next_m_tdd = monthly_tdd_evolution(next_m_sdate, eu_actual)
        next_m_tdd = next_m_tdd.to_frame("next month")
        next_m_tdd = next_m_tdd.reindex(cur_m_tdd.index)
        cwg2 = get_seasonal_forecast(region='europe', month_season=dt.datetime(next_year_, next_month_, 1).strftime(_unrecovered('original line 520: month-season format')))
        cwg2 = cwg2[["Month_Season", "HDD", "HDD_norm10"]]
        cwg2 = cwg2[~cwg2.index.duplicated(keep='last')]
        if len(cwg2) == 1:
            next_m_tdd.loc[(next_m_tdd.index >= cwg2.index[-1]) & (next_m_tdd.index < next_m_tdd.first_valid_index()), :] = _unrecovered('original line 524: clipped assignment tail')
            next_m_tdd.loc[next_m_tdd.index < cwg2.index[-1], :] = cwg2["HDD_norm10"].iloc[-1]
        elif len(cwg2) > 0:
            cwg2_ = cwg2.reindex(next_m_tdd.index).fillna(method='ffill')
            next_m_tdd.loc[(next_m_tdd.index >= cwg2_.first_valid_index()) & (next_m_tdd.index < next_m_tdd.first_valid_index()), :] = _unrecovered('original line 528: clipped assignment tail')
            next_m_tdd.loc[(next_m_tdd.index < cwg2_.first_valid_index()), :] = cwg2["HDD_norm10"].iloc[-1]
        elif len(cwg2) == 0:
            next_m_sdate = today() + relativedelta(day=31) + relativedelta(days=1)
            next_m_dts = pd.date_range(next_m_sdate, next_m_sdate + relativedelta(day=31))
            next_m_norm = eu_actual.loc[(eu_actual.index >= next_m_dts[0] - relativedelta(years=1)) & (eu_actual.index <= next_m_dts[-1] - relativedelta(years=1)), "10Y_NG_HDD"]
            next_m_norm.index = [x + relativedelta(years=1) for x in next_m_norm.index]
            next_m_tdd.loc[next_m_tdd.index < next_m_tdd.first_valid_index(), :] = next_m_norm.sum()
    else:
        cwg2 = get_seasonal_forecast(region='europe', month_season=dt.datetime(next_year_, next_month_, 1).strftime(_unrecovered('original line 538: month-season format')))
        if len(cwg2) > 0:
            cwg2 = cwg2[cwg2["As_of_date"] == cwg2["As_of_date"].max()]
            cwg_tdd1 = cwg2[["HDD", "HDD_norm10"]].reindex(cur_m_tdd.index).fillna(method="ffill").fillna(method="bfill")
            cwg_tdd1.columns = ["CWG " + cwg2["Month_Season"].iloc[0].split(" ")[0], "CWG Norm"]
            next_m_tdd = cwg_tdd1
        else:
            next_m_sdate = today() + relativedelta(day=31) + relativedelta(days=1)
            next_m_dts = pd.date_range(next_m_sdate, next_m_sdate + relativedelta(day=31))
            next_m_tdd = eu_actual.loc[(eu_actual.index >= next_m_dts[0] - relativedelta(years=1)) & (eu_actual.index <= next_m_dts[-1] - relativedelta(years=1)), "10Y_NG_HDD"]
            next_m_tdd.index = [x + relativedelta(years=1) for x in next_m_tdd.index]
            next_m_tdd = pd.DataFrame(next_m_tdd.sum(), index=cur_m_tdd.index, columns=["next month"])
    fig1 = demand_forecast_chart(asia, title='1-15 HDD forecasts charts for Europe',
        bbg_tdd=cur_m_tdd.to_frame("this month"), bbg_tdd1=next_m_tdd)
    fig2 = demand_forecast_chart(china, title='1-15 HDD forecasts charts for TTF')
    fig3 = demand_forecast_chart(japan, title='1-15 HDD forecasts charts for Italy')
    fig4 = demand_forecast_chart(sk, title='1-15 HDD forecasts charts for UK')
    figs_link = []
    tbs.append(fig1)
    figs_link.append(fig2)
    figs_link.append(fig3)
    figs_link.append(fig4)
    table.figures_to_html(figs_link, filename=f"{html_path}\\weather\\links\\eu_weather_other_charts_hdd.html")
    tbs.append(u'<a href="{}\\weather\\links\\eu_weather_other_charts_hdd.html">Link to other charts</a>'.format(html_path))
    tbs.append('<br>')
    dfnew_hdd = sql.read_sql("select * from [dbo].[CWG_BALANCE_OF_MONTH_Global] where Region='Europe' and " + _unrecovered('original line 568: SQL condition beginning M'))
    dfnew_hdd = dfnew_hdd.drop_duplicates()
    dfnew_hdd = dfnew_hdd.sort_values("AS_OF_DATE")
    dfnew_hdd.set_index("AS_OF_DATE", inplace=True)
    dfnew_hdd.index = pd.to_datetime(dfnew_hdd.index)
    front_ticker = (bbg.live_contract(active="TZTA Comdty"))["ticker"]
    front_price = bbg.bdh(front_ticker, ['PX_LAST'],
                          sdate=cur_m_tdd.index[0],
                          edate=cur_m_tdd.index[-1],
                          elms=[('nonTradingDayFillOption', 'ALL_CALENDAR_DAYS'),
                                ('nonTradingDayFillMethod', 'PREVIOUS_VALUE')])
    front_price = front_price.reindex(cur_m_tdd.index)
    this_month_hdd_forecast = pd.concat([front_price, cur_m_tdd, dfnew_hdd[["10Y", "Last Year", "FCAST_MONTH"]]], axis=1)
    this_month_hdd_forecast.reset_index(inplace=True)
    this_month_hdd_forecast.columns = ["AS_OF_DATE", "Price", "CWG Fcast", "CWG Normal", "Last Year", "FCAST_MONTH"]
    this_month_hdd_forecast = this_month_hdd_forecast.fillna(method="bfill").fillna(method="ffill")
    this_month_hdd_forecast.sort_values("AS_OF_DATE", ascending=False, inplace=True)
    this_month_hdd_forecast["AS_OF_DATE"] = this_month_hdd_forecast["AS_OF_DATE"].dt.strftime("%Y-%m-%d")
    this_month_hdd_forecast_html = table.html_format(this_month_hdd_forecast, background_color='lightyellow',
        precision=0,
        format_column={
            'AS_OF_DATE': {'width': '100px', 'text-align': 'center'},
            'Price': {'width': '100px', 'text-align': 'center', 'format': '{:.3f}'},
            'CWG Fcast': {'width': '80px', 'text-align': 'center'},
            'Last Year': {'width': '80px', 'text-align': 'center'},
            'CWG Normal': {'width': '80px', 'text-align': 'center'},
            'FCAST_MONTH': {'width': '100px', 'text-align': 'center'},
        })
    tbs.append('Current Month - Total HDD forecast')
    tbs.append(this_month_hdd_forecast_html)
    tbs.append('<br>')
    if (today() + relativedelta(days=15)).month != today().month:
        cur_m_norm = eu_actual.loc[(eu_actual.index >= next_m_sdate - relativedelta(years=1)) & (
            eu_actual.index <= next_m_sdate + relativedelta(day=31) - relativedelta(years=1)), "10Y_NG_HDD"]
        cur_m_norm.index = [x + relativedelta(years=1) for x in cur_m_norm.index]
        cur_m_1y = eu_actual.loc[(eu_actual.index >= next_m_sdate - relativedelta(years=1)) & (
            eu_actual.index <= next_m_sdate + relativedelta(day=31) - relativedelta(years=1)), "NG_HDD"]
        cur_m_1y.index = [x + relativedelta(years=1) for x in cur_m_1y.index]
        second_ticker = (bbg.live_contract(active="TZTA Comdty", seq=1))["ticker"]
        second_price = bbg.bdh(second_ticker, ['PX_LAST'],
                              sdate=next_m_tdd.index[0],
                              edate=next_m_tdd.index[-1],
                              elms=[('nonTradingDayFillOption', 'ALL_CALENDAR_DAYS'),
                                    ('nonTradingDayFillMethod', 'PREVIOUS_VALUE')])
        second_price = second_price.reindex(next_m_tdd.index)
        next_month_hdd_forecast = pd.concat([second_price, next_m_tdd], axis=1)
        next_month_hdd_forecast.reset_index(inplace=True)
        next_month_hdd_forecast.columns = ["AS_OF_DATE", "Price", "CWG Fcast"]
        next_month_hdd_forecast["CWG Normal"] = cur_m_norm.sum()
        next_month_hdd_forecast["Last Year"] = cur_m_1y.sum()
        next_month_hdd_forecast["FCAST_MONTH"] = next_m_sdate.strftime("%Y-%m-%d")
        next_month_hdd_forecast.sort_values("AS_OF_DATE", ascending=False, inplace=True)
        next_month_hdd_forecast["AS_OF_DATE"] = next_month_hdd_forecast["AS_OF_DATE"].dt.strftime("%Y-%m-%d")
        next_month_hdd_forecast_html = table.html_format(next_month_hdd_forecast, background_color='lightgreen',
            precision=0,
            format_column={
                'AS_OF_DATE': {'width': '100px', 'text-align': 'center'},
                'Price': {'width': '100px', 'text-align': 'center', 'format': '{:.3f}'},
                'CWG Fcast': {'width': '80px', 'text-align': 'center'},
                'Last Year': {'width': '80px', 'text-align': 'center'},
                'CWG Normal': {'width': '80px', 'text-align': 'center'},
                'FCAST_MONTH': {'width': '100px', 'text-align': 'center'},
            })
        tbs.append('Next Month - Total HDD forecast')
        tbs.append(next_month_hdd_forecast_html)
        tbs.append('<br>')
    region_list = ['Europe', 'TTF', 'Italy', 'Iberian Peninsula', 'United Kingdom']
    tbs_link = []
    tbs_link.append("<div style='font-family:Calibri;' >")
    for i in region_list:
        a_df, c_df = get_hdd_cdd(region=i)
        df2_fcast = sql.read_sql(
            (f"select t1.* from CWG_Fcast_Europe t1 INNER JOIN (select max(AS_OF_DATE) as dt from "
             f"CWG_Fcast_Europe) t2 on t1.AS_OF_DATE = t2.dt where REGION='{i}' order by DATES"))
        df2_fcast = df2_fcast[['DATES', 'POP_HDD', 'POP_HDD_10Y', 'POP_CDD', 'POP_CDD_10Y']]
        df2_fcast.set_index('DATES', inplace=True)
        df2_fcast['NG_HDD'] = df2_fcast['POP_HDD']
        df2_fcast['10Y_NG_HDD'] = df2_fcast['POP_HDD_10Y']
        df2_fcast = df2_fcast[['NG_HDD', '10Y_NG_HDD']]
        if len(df2_fcast) > 0:
            a_df = a_df.append(df2_fcast)
        a_df = a_df[~a_df.index.duplicated(keep='first')]
        summer = winter_hdd(c_df, winsum='S')
        summer_table = witer_month_table(summer, winsum='S')
        summer_table.loc[:, summer_table.columns[1:]] = summer_table.iloc[:, 1:] * 36 / 1000 #* -1
        summer_table_html = table.html_format(summer_table, precision=1, format_column={
            summer_table.columns[0]: {'width': '80px', 'text-align': 'center'},
            summer_table.columns[1]: {'width': '80px', 'text-align': 'center'},
            summer_table.columns[2]: {'width': '80px', 'text-align': 'center'},
            summer_table.columns[3]: {'width': '80px', 'text-align': 'center'},
            summer_table.columns[4]: {'width': '80px', 'text-align': 'center'},
            summer_table.columns[5]: {'width': '80px', 'text-align': 'center'},
            summer_table.columns[6]: {'width': '80px', 'text-align': 'center'},
            summer_table.columns[7]: {'width': '80px', 'text-align': 'center'},
            summer_table.columns[8]: {'width': '80px', 'text-align': 'center'},
        })
        winter = winter_hdd(a_df, winsum='W')
        winter_table = witer_month_table(winter, winsum='W')
        winter_table_html = table.html_format(winter_table, precision=0, format_column={
            winter_table.columns[0]: {'width': '80px', 'text-align': 'center'},
            winter_table.columns[1]: {'width': '80px', 'text-align': 'center'},
            winter_table.columns[2]: {'width': '80px', 'text-align': 'center'},
            winter_table.columns[3]: {'width': '80px', 'text-align': 'center'},
            winter_table.columns[4]: {'width': '80px', 'text-align': 'center'},
            winter_table.columns[5]: {'width': '80px', 'text-align': 'center'},
            winter_table.columns[6]: {'width': '80px', 'text-align': 'center'},
            winter_table.columns[7]: {'width': '80px', 'text-align': 'center'},
            winter_table.columns[8]: {'width': '80px', 'text-align': 'center'},
        })
        if i == "Europe":
            tbs.append(f'{i} BCM change vs 10Y Normal - Last season: ')
            tbs.append(summer_table_html)
            tbs.append('<br>')
            tbs.append(f'{i} HDD vs 10Y Normal - current and next month include HDD forecasts: ')
            tbs.append(winter_table_html)
            tbs.append('<br>')
        else:
            tbs_link.append(f'{i} BCM change vs 10Y Normal - Last season: ')
            tbs_link.append(summer_table_html)
            tbs_link.append('<br>')
            tbs_link.append(f'{i} HDD vs 10Y Normal - current and next month include HDD forecasts: ')
            tbs_link.append(winter_table_html)
            tbs_link.append('<br>')
        winter_table_bcf = winter_table.copy()
        winter_table_bcf.loc[:, winter_table_bcf.columns[1:]] = winter_table_bcf.iloc[:, 1:] * 36 / 1000 #* -1
        winter_table_bcf_html = table.html_format(winter_table_bcf, precision=1, format_column={
            winter_table.columns[0]: {'width': '80px', 'text-align': 'center'},
            winter_table.columns[1]: {'width': '80px', 'text-align': 'center'},
            winter_table.columns[2]: {'width': '80px', 'text-align': 'center'},
            winter_table.columns[3]: {'width': '80px', 'text-align': 'center'},
            winter_table.columns[4]: {'width': '80px', 'text-align': 'center'},
            winter_table.columns[5]: {'width': '80px', 'text-align': 'center'},
            winter_table.columns[6]: {'width': '80px', 'text-align': 'center'},
            winter_table.columns[7]: {'width': '80px', 'text-align': 'center'},
            winter_table.columns[8]: {'width': '80px', 'text-align': 'center'},
        })
        if i == "Europe":
            tbs.append(f'{i} BCM change vs 10Y Normal - current and next month include HDD forecasts: ')
            tbs.append(winter_table_bcf_html)
            tbs.append('<br>')
        else:
            tbs_link.append(f'{i} BCM change vs 10Y Normal - current and next month include HDD forecasts: ')
            tbs_link.append(winter_table_bcf_html)
            tbs_link.append('<br>')
        if i == "Europe":
            tbs.append(cumulative_cdd_chart(summer, df2_fcast, lookback=True, winsum="S"))
            tbs.append(cumulative_hdd_chart(winter, df2_fcast))
        else:
            tbs_link.append(cumulative_hdd_chart(winter, df2_fcast))

    inv_draw = pd.read_excel(convert_path_to_linux("\\\\elementcapital.corp\\ecns01\\PM\\Michel Kikano\\" + _unrecovered('original line 737: workbook path beginning Jose')))
    inv_draw.set_index("Unnamed: 0", inplace=True)
    inv_draw.index = pd.to_datetime(inv_draw.index)
    inv_draw.loc[inv_draw.index[0] - dt.timedelta(1), :] = 0
    inv_draw.sort_index(inplace=True)
    if today().month > 4:
        yr_chg = today().year - inv_draw.index[0].year
    else:
        yr_chg = today().year - 1 - inv_draw.index[0].year
    inv_draw.index = [x + relativedelta(years=yr_chg) for x in inv_draw.index]
    tbs.append(chart.line_chart(
        df=inv_draw,
        title="TTF stock cumulative change",
        highlight_dict={
            inv_draw.columns[-1]: {"color": "black", "width": 2},
            inv_draw.columns[-2]: {"color": "blue", "width": 1},
        },
    ))
    price_vol = ts.read_csv("\\\\elementcapital.corp\\ecns01\\PM\\Michel Kikano\\Data\\backtest\\CORV\\TZTA" + _unrecovered('original line 757: CSV path tail'))
    yr_list = price_vol.index.year.unique().to_list()
    if today().month < 4:
        yr_list = yr_list[:-1]
    df_price_chg = pd.DataFrame(np.nan, index=range(132), columns=yr_list)
    for idx, i in enumerate(yr_list):
        sdate = dt.datetime(i, 10, 1)
        edate = dt.datetime(i + 1, 3, 31)
        new_idx = pd.bdate_range(sdate, edate)
        if idx == len(yr_list) - 1:
            new_idx = pd.bdate_range(sdate, price_vol.index[-1])
            val = price_vol.loc[(price_vol.index >= sdate) & (price_vol.index <= edate), "price chg"].reindex(new_idx)
            val1 = price_vol.loc[(price_vol.index >= sdate) & (price_vol.index <= edate), "tdd chg"].reindex(new_idx)
            df_price_chg.loc[:len(val) - 1, i] = val / 100
            df_price_chg.loc[:len(new_idx) - 1, "Dates"] = new_idx
            df_price_chg.loc[:len(val) - 1, "Exp chg"] = val1 * 0.0017
            df_price_chg = df_price_chg.iloc[:len(new_idx), :]
        else:
            val = price_vol.loc[(price_vol.index >= sdate) & (price_vol.index <= edate), "price chg"].reindex(new_idx)
            df_price_chg.loc[:len(val) - 1, i] = val / 100
    df_price_chg.set_index("Dates", inplace=True)
    df_price_chg["Avg since 2022"] = df_price_chg.iloc[:, :-3].mean(axis=1)
    df_price_chg = df_price_chg.cumsum(axis=0)
    df_price_chg.loc[df_price_chg.index[0] - dt.timedelta(1), :] = 0
    df_price_chg.sort_index(inplace=True)
    tbs.append(chart.line_chart(
        df=df_price_chg.iloc[:, -3:],
        title="TZT winter cumulative price change",
        highlight_dict={
            df_price_chg.columns[-3]: {"color": "black", "width": 2},
            df_price_chg.columns[-2]: {"color": "blue", "width": 1},
            df_price_chg.columns[-1]: {"color": "red", "width": 1},
        },
    ))
    table.figures_to_html(tbs_link, filename=f"{html_path}\\weather\\links\\eu_weather_other_charts_1_hdd.html")
    tbs.append(u'<a href="{}\\weather\\links\\eu_weather_other_charts_1_hdd.html">Link to other charts</a>'.format(html_path))
    tbs.append('<br>')
    tbs.append(u'<a href="{}\\weather\\eu_tdd.html">Link to EU TDD</a>'.format(html_path))
    tbs.append('<br>')
    tbs.append(table.html_text(f"Updated at {dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"))
    table.figures_to_html(
        [table.html_text(report_name, style="font-family:Calibri;", tag='h1')] + tbs,
        f"{html_path}\\weather\\eu_cdd_hdd.html", task_name="Weather - Global TDD")
    send_email(send_to=send_to, subject=report_name, body=tbs, html_path=f"{html_path}\\weather\\eu_cdd_hdd.html")


if __name__ == '__main__':
    update()
