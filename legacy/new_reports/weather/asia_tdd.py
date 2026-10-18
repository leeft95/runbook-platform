import pandas as pd
import numpy as np
import datetime as dt
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import plotly as py
import sys
import ecm.cmds.stormvista as sv
import ecm.cmds.sql as sql
import ecm.cmds.table as table
from ecm.cmds.config import output_path, html_path, root_path, gas_group
from ecm.cmds._email import send_email
from ecm.cmds.cdr import today
from ecm.cmds.utils import convert_path_to_linux

send_to = gas_group
report_name = "Weather - Asia CWG TDD Update"
file_name = "asia_tdd"  # without .py
file_path = f"{root_path}\\autoreports\\reports\\weather\\{file_name}.py"
weather_csv = f"{output_path}\\csvs\\weather"


def _unrecovered(location):
    raise NotImplementedError(f"asia_tdd photographed source: {location}")


def add_schedule():
    """
    """
    sys.path.append(f"{root_path}\\autoreports\\schedule")
    from tasks import WinTaskPoC
    from ecm.atom.wintask.scheduler import ECMWinTask
    from ecm.atom.wintask.utils import Days

    win_task = ECMWinTask(
        days=Days.MONDAY | Days.TUESDAY | Days.WEDNESDAY | Days.THURSDAY | Days.FRIDAY | Days.SUNDAY,
        start_datetime=dt.datetime(2023, 7, 1, 11, 10),
        timezone="Europe/London",
        task_name=report_name,
        task=WinTaskPoC(name=f'"{report_name}"', filepath=f'"{file_path}"'),
        background_task=True,
        python_excecutable=r"C:\local\python\miniconda\envs\ecm_cmds\pythonw.exe"
    )
    win_task.create_task()


def get_forecast_hdd(area):
    """
    Last 3 forecasts from Stormvista
    """
    sql_str = f"""select t1.* from CWG_StormVista_Global_fcast t1 INNER JOIN
                    (select Top (3) AS_OF_DATE as dt from CWG_StormVista_Global_fcast group by As_of_date
                    order by As_of_date desc) t2 on t1.AS_OF_DATE = t2.dt
                    where region='{area}' and cycle='00' and Field='pw_hdd' order by AS_OF_DATE desc, Dates"""
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


def get_forecast_cdd(area):
    """
    Last 3 forecasts from Stormvista
    """
    sql_str = f"""select t1.* from CWG_StormVista_Global_fcast t1 INNER JOIN
                    (select Top (3) AS_OF_DATE as dt from CWG_StormVista_Global_fcast group by As_of_date
                    order by As_of_date desc) t2 on t1.AS_OF_DATE = t2.dt
                    where region='{area}' and cycle='00' and Field='pw_cdd' order by AS_OF_DATE desc, Dates"""
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


def combine_actual_forecast_normal(area='asia'):
    asia_f_hdd = get_forecast_hdd(area=area)
    asia_f_cdd = get_forecast_cdd(area=area)
    asia_f = asia_f_hdd + asia_f_cdd
    asia_a_hdd = sv.global_wdd_actual(field='pw_hdd', area=area)
    asia_a_hdd.set_index("Date", inplace=True)
    asia_a_hdd.index = pd.to_datetime(asia_a_hdd.index)
    asia_a_hdd.columns = ["Actual"]
    asia_a_cdd = sv.global_wdd_actual(field='pw_cdd', area=area)
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


def hdd_forecast_chart():
    normals = sql.read_sql("select * from [L025].[dbo].[CWG_Normals]")
    fcasts = sql.read_sql("select * from [dbo].[CWG_fifteenday_fcast_CDD_ELEC]")

    fcasts['AS_OF_DATE'] = pd.to_datetime(fcasts['AS_OF_DATE'])
    fcasts = fcasts.drop_duplicates(['DATES', 'AS_OF_DATE'], keep='last')
    fcasts = fcasts.sort_values('AS_OF_DATE')


    x = pd.DataFrame(fcasts['AS_OF_DATE'].unique()).tail(10)
    enddate = x[0].max()
    startdate = x[0].min()
    graphingdata = fcasts
    datareq = (fcasts['AS_OF_DATE'] > startdate) & (fcasts['AS_OF_DATE'] <= enddate)


    fcasts = fcasts.loc[datareq]


    pttable = fcasts.pivot_table(values='NG_CDD', index='DATES', columns='AS_OF_DATE')
    pttable = pttable.reset_index()

    graphingtable = pttable.copy()

    pttable['vs yest'] = pttable.iloc[:, -1] - pttable.iloc[:, -2]

    pttable['vs last week'] = pttable.iloc[:, -2] - pttable.iloc[:, -8]

    pttable = pttable.merge(normals['ng_hdd_10yr'], how='inner',
                            left_on=(pttable['DATES'].dt.month, pttable['DATES'].dt.day),
                            right_on=(normals['Month'], normals['Day']))

    graphingtable = graphingtable.merge(normals['ng_hdd_10yr'], how='inner',
                                        left_on=(graphingtable['DATES'].dt.month, graphingtable['DATES'].dt.day),
                                        right_on=(normals['Month'], normals['Day']))

    pttable = pttable.drop(columns=['key_0', 'key_1'])
    graphingtable = graphingtable.drop(columns=['key_0', 'key_1'])

    graphingtable = graphingtable.set_index(graphingtable['DATES'])

    yt = graphingtable[graphingtable.columns[-4:]]

    dataPanda2 = []
    for j in range(0, len(yt.columns)):
        trace = go.Scatter(x=yt.index, y=yt.iloc[:, j], connectgaps=True, name=str((yt.columns[j])), mode='lines')
        dataPanda2.append(trace)

    layout2 = go.Layout(title='1-15 run')
    fig2 = go.Figure(data=dataPanda2, layout=layout2)
    return fig2


def demand_forecast_chart(fcast_df, title, bbg_tdd=None, bbg_tdd1=None):
    fcast_df = fcast_df.loc[fcast_df.index >= fcast_df.index[-1] - dt.timedelta(days=35), :]
    if bbg_tdd is not None and bbg_tdd1 is None:
        bbg_tdd = pd.concat(
            [bbg_tdd, fcast_df.loc[fcast_df.index > bbg_tdd.index[-1], 'Actual'].to_frame(bbg_tdd.columns[0])], axis=0)
        return get_chart(fcast_df, title=title, y_axis_title='tdd', data1=bbg_tdd.reindex(fcast_df.index))
    elif bbg_tdd is not None and bbg_tdd1 is not None:
        bbg_tdd = pd.concat(
            [bbg_tdd, fcast_df.loc[fcast_df.index > bbg_tdd.index[-1], 'Actual'].to_frame(bbg_tdd.columns[0])], axis=0)
        bbg_tdd1 = pd.concat(
            [bbg_tdd1, fcast_df.loc[fcast_df.index > bbg_tdd1.index[-1], 'Actual'].to_frame(bbg_tdd1.columns[0])], axis=0)
        return get_chart(fcast_df, title=title, y_axis_title='tdd', data1=bbg_tdd.reindex(fcast_df.index),
                         data2=bbg_tdd1.reindex(fcast_df.index))
    else:
        return get_chart(fcast_df, title=title, y_axis_title='tdd')


def daily_chg_table(hdd_df_ori):
    hdd_df1 = hdd_df_ori.iloc[:, [0, 1, 3]]
    hdd_df1.dropna(axis=0, inplace=True)
    hdd_df2 = hdd_df_ori.iloc[:, [1, 2, 3]]
    hdd_df2.dropna(axis=0, inplace=True)
    table_hdd = pd.DataFrame(0, index=[0, 1],
                             columns=['Date', 'Forecast change CDD', 'Forecast vs Normal CDD', 'CDD forecast',
                                      '10Y CDD'])
    table_hdd['Date'] = [hdd_df_ori.columns[0], hdd_df_ori.columns[1]]
    table_hdd.loc[0, '10Y CDD'] = hdd_df1['Normal'].mean()
    table_hdd.loc[1, '10Y CDD'] = hdd_df2['Normal'].mean()
    table_hdd.loc[0, 'CDD forecast'] = hdd_df1.iloc[:, 0].mean()
    table_hdd.loc[1, 'CDD forecast'] = hdd_df1.iloc[:, 1].mean()
    table_hdd.loc[0, 'Forecast change CDD'] = hdd_df1.iloc[:, 0].sum() - hdd_df1.iloc[:, 1].sum()
    table_hdd.loc[1, 'Forecast change CDD'] = hdd_df2.iloc[:, 0].sum() - hdd_df2.iloc[:, 1].sum()
    table_hdd.loc[0, 'Forecast vs Normal CDD'] = hdd_df1.iloc[:, 0].sum() - hdd_df1['Normal'].sum()
    table_hdd.loc[1, 'Forecast vs Normal CDD'] = hdd_df1.iloc[:, 1].sum() - hdd_df1['Normal'].sum()
    return table_hdd


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
                               line=dict(width=2, **_unrecovered('get_chart original line 236: clipped line color/style'))))
            elif idx == 1:
                fig.add_trace(go.Scatter(x=data.index, y=data[col], showlegend=True, name=col,
                                         line=dict(width=2, color='red', dash='dash')))
            elif idx == 2:
                fig.add_trace(go.Scatter(x=data.index, y=data[col], showlegend=True, name=col,
                                         line=dict(width=1, color='orange', dash='dash')))
            else:
                fig.add_trace(go.Scatter(x=data.index, y=data[col], showlegend=True, name=col,
                                         line=_unrecovered('get_chart original line 244: clipped line style')))
        fig.update_layout(
            title={'text': title,
                   'x': 0.5,
                   'xanchor': 'center'},
            xaxis_title=x_axis_title,
            yaxis_title=y_axis_title,
            width=900, height=600)
    elif data1 is not None and data2 is None:
        fig = make_subplots(specs=[[{"secondary_y": True}]])
        for idx, col in enumerate(list(data.columns)):
            if idx == 0:
                fig.add_trace(
                    go.Scatter(x=data.index, y=data[col], showlegend=True, name=col,
                               line=dict(width=2, **_unrecovered('get_chart original line 257: clipped line color/style'))))
            elif idx == 1:
                fig.add_trace(go.Scatter(x=data.index, y=data[col], showlegend=True, name=col,
                                         line=dict(width=2, color='red', dash='dash')))
            elif idx == 2:
                fig.add_trace(go.Scatter(x=data.index, y=data[col], showlegend=True, name=col,
                                         line=dict(width=1, color='orange', dash='dash')))
            else:
                fig.add_trace(go.Scatter(x=data.index, y=data[col], showlegend=True, name=col,
                                         line=_unrecovered('get_chart original line 265: clipped line style')))
        if len(data1.columns) == 1:
            fig.add_trace(go.Scatter(x=data1.index, y=data1.iloc[:, 0], showlegend=True, name=data1.columns[0],
                                     line=dict(width=2)), secondary_y=True)
        else:
            for j in range(len(data1.columns)):
                fig.add_trace(go.Scatter(x=data1.index, y=data1.iloc[:, j], showlegend=True, name=data1.columns[j],
                                         line=dict(width=2)), secondary_y=True)

        fig.update_layout(
            title={'text': title,
                   'x': 0.5,
                   'xanchor': 'center'},
            xaxis_title=x_axis_title,
            yaxis_title=y_axis_title,
            width=900, height=600)
    else:
        fig = make_subplots(rows=2, cols=1, row_heights=[0.7, 0.3], shared_xaxes=True,
                            vertical_spacing=0.02,
                            specs=[[{"secondary_y": True}], [{"secondary_y": True}]])
        for idx, col in enumerate(list(data.columns)):
            if idx == 0:
                fig.add_trace(
                    go.Scatter(x=data.index, y=data[col], showlegend=True, name=col,
                               line=dict(width=2, **_unrecovered('get_chart original line 287: clipped line color/style'))))
            elif idx == 1:
                fig.add_trace(go.Scatter(x=data.index, y=data[col], showlegend=True, name=col,
                                         line=dict(width=2, color='red', dash='dash')))
            elif idx == 2:
                fig.add_trace(go.Scatter(x=data.index, y=data[col], showlegend=True, name=col,
                                         line=dict(width=1, color='orange', dash='dash')))
            else:
                fig.add_trace(go.Scatter(x=data.index, y=data[col], showlegend=True, name=col,
                                         line=_unrecovered('get_chart original line 295: clipped line style')))
        if len(data1.columns) == 1:
            fig.add_trace(go.Scatter(x=data1.index, y=data1.iloc[:, 0], showlegend=True, name=data1.columns[0],
                                     line=dict(width=2)), secondary_y=True)
        else:
            for j in range(len(data1.columns)):
                fig.add_trace(go.Scatter(x=data1.index, y=data1.iloc[:, j], showlegend=True, name=data1.columns[j],
                                         line=dict(width=2)), secondary_y=True)

        if len(data2.columns) == 1:
            fig.add_trace(go.Scatter(x=data2.index, y=data2.iloc[:, 0], showlegend=True, name=data2.columns[0],
                                     line=dict(width=2)), row=2, col=1)
        else:
            for j in range(len(data2.columns)):
                fig.add_trace(go.Scatter(x=data2.index, y=data2.iloc[:, j], showlegend=True, name=data2.columns[j],
                                         line=dict(width=2)), row=2, col=1)

        fig.update_layout(
            title={'text': title,
                   'x': 0.5,
                   'xanchor': 'center'},
            xaxis_title=x_axis_title,
            yaxis_title=y_axis_title,
            width=900, height=600)

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


    season.loc[(season['month'] >= 4), 'Season'] = 'S'
    season.loc[(season['month'] >= 10) | (season['month'] <= 3), 'Season'] = 'W'


    season.loc[(season['month'] >= 4), 'Syr'] = (season['year']).astype(str)
    season.loc[(season['month'] < 4), 'Syr'] = (season['year'] - 1).astype(str)
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


def cumulative_hdd_chart(winter, hdd_df, title='Cumulative winter TDDs vs 10Y normal'):

    winterpvt2 = pd.pivot_table(winter, columns=['Season_year'], index=['day_count'],
                                values='Cumulative of Actual_vs_Normal per season')
    winterpvt2_email = winterpvt2[winterpvt2.columns[-6:]]

    lvi = winterpvt2_email.iloc[:, -1].last_valid_index()
    if lvi < len(winterpvt2_email):
        last_col = winterpvt2_email.columns[-1]
        winterpvt2_email['Latest forecast'] = winterpvt2_email.loc[lvi - len(hdd_df) + 1: lvi, last_col]
        winterpvt2_email.loc[lvi - len(hdd_df) + 1: lvi, last_col] = np.nan

    if len(hdd_df) == 0:
        base_date = today() - dt.timedelta(days=1)
    else:
        base_date = hdd_df.index[0] - dt.timedelta(days=1)
    if base_date.month >= 9:
        date_idx = pd.date_range(dt.datetime(base_date.year, 10, 1), dt.datetime(base_date.year + 1, 3, 31))
    elif base_date.month < 4:
        date_idx = pd.date_range(dt.datetime(base_date.year - 1, 10, 1), dt.datetime(base_date.year, 3, 31))
    if len(date_idx) < len(winterpvt2_email):
        winterpvt2_email = winterpvt2_email.iloc[:-1, :]
    winterpvt2_email['dates'] = date_idx
    winterpvt2_email.set_index('dates', inplace=True)

    dataPanda6 = []

    for j in range(0, len(winterpvt2_email.columns)):
        if j == len(winterpvt2_email.columns) - 2:
            trace = go.Scatter(x=winterpvt2_email.index, y=winterpvt2_email.iloc[:, j], connectgaps=True,
                               name=(winterpvt2_email.columns[j]), mode='lines',
                               line=dict(width=3, color=_unrecovered('original line 410: clipped color beginning b')))
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


def cumulative_cdd_chart(winter, hdd_df, title='Cumulative summer TDDs vs 10Y normal'):

    winterpvt2 = pd.pivot_table(winter, columns=['Season_year'], index=['day_count'],
                                values='Cumulative of Actual_vs_Normal per season')
    winterpvt2_email = winterpvt2[winterpvt2.columns[-6:]]

    lvi = winterpvt2_email.iloc[:, -1].last_valid_index()
    if lvi < len(winterpvt2_email):
        last_col = winterpvt2_email.columns[-1]
        winterpvt2_email['Latest forecast'] = winterpvt2_email.loc[lvi - len(hdd_df) + 1: lvi, last_col]
        winterpvt2_email.loc[lvi - len(hdd_df) + 1: lvi, last_col] = np.nan

    if len(hdd_df) > 0:
        base_date = hdd_df.index[0] - dt.timedelta(days=1)
        date_idx = pd.date_range(dt.datetime(base_date.year, 4, 1), dt.datetime(base_date.year, 9, 30))
        if len(date_idx) < len(winterpvt2_email):
            winterpvt2_email = winterpvt2_email.iloc[:-1, :]
        winterpvt2_email['dates'] = date_idx
        winterpvt2_email.set_index('dates', inplace=True)

    dataPanda6 = []

    for j in range(0, len(winterpvt2_email.columns)):
        if j == len(winterpvt2_email.columns) - 2:
            trace = go.Scatter(x=winterpvt2_email.index, y=winterpvt2_email.iloc[:, j], connectgaps=True,
                               name=(winterpvt2_email.columns[j]), mode='lines',
                               line=dict(width=3, color=_unrecovered('original line 458: clipped color beginning b')))
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


    df_eom2.loc[(df_eom2['month'] >= 4), 'Season'] = 'S'
    df_eom2.loc[(df_eom2['month'] >= 10) | (df_eom2['month'] <= 3), 'Season'] = 'W'
    df_eom2.loc[(df_eom2['month'] >= 4), 'Syr'] = (df_eom2['year']).astype(str)
    df_eom2.loc[(df_eom2['month'] < 4), 'Syr'] = (df_eom2['year'] - 1).astype(str)
    df_eom2['Season_year'] = df_eom2['Season'] + df_eom2['Syr'].astype(str)

    df_eom2_winter = df_eom2.loc[(df_eom2['Season'] == winsum) & (df_eom2.index >= '2016-10-01')]

    df_eom2_winter['Actuals_vs_Normal'] = df_eom2_winter['Actuals_vs_Normal'].astype('float')

    df_eom2_winterpvt = pd.pivot_table(df_eom2_winter, columns=['Season_year'], index=['month'],
                                      values='Actuals_vs_Normal')

    if winsum == 'W':
        df_eom2_winterpvt = df_eom2_winterpvt.reindex([10, 11, 12, 1, 2, 3])
        df_eom2_winterpvt.loc['Total', :] = df_eom2_winterpvt.sum(axis=0)
        df_eom2_winterpvt.insert(loc=0, column='month', value=['Oct', 'Nov', 'Dec', 'Jan', 'Feb', 'Mar', 'Total'])
    elif winsum == 'S':
        df_eom2_winterpvt = df_eom2_winterpvt.reindex([4, 5, 6, 7, 8, 9])
        df_eom2_winterpvt.loc['Total', :] = df_eom2_winterpvt.sum(axis=0)
        df_eom2_winterpvt.insert(loc=0, column='month', value=['Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Total'])

    df_eom2_winterpvt.index.name = None
    df_eom2_winterpvt.columns.name = None
    df_eom2_winterpvt.reset_index(drop=True, inplace=True)
    return df_eom2_winterpvt


def update():
    figs = []
    figs1 = []
    tbs = []
    tbs1 = []
    asia = combine_actual_forecast_normal(area='asia')
    china = combine_actual_forecast_normal(area='china')
    japan = combine_actual_forecast_normal(area='japan')
    sk = combine_actual_forecast_normal(area='skorea')
    india = combine_actual_forecast_normal(area='india')
    try:
        asia.to_excel(convert_path_to_linux(f"{weather_csv}\\tdd_forecast_asia.xlsx"))
    except:
        pass
    try:
        china.to_excel(convert_path_to_linux(f"{weather_csv}\\tdd_forecast_china.xlsx"))
    except:
        pass
    try:
        japan.to_excel(convert_path_to_linux(f"{weather_csv}\\tdd_forecast_japan.xlsx"))
    except:
        pass
    try:
        sk.to_excel(convert_path_to_linux(f"{weather_csv}\\tdd_forecast_sk.xlsx"))
    except:
        pass
    try:
        india.to_excel(convert_path_to_linux(f"{weather_csv}\\tdd_forecast_india.xlsx"))
    except:
        pass
    tbs.append('StormVista table (ECMWF-EPS):')
    sv_hdd = pd.read_csv(convert_path_to_linux(f"{weather_csv}\\asia_tdd_stormvista.csv"))
    tbs.append(table.html_format(df=sv_hdd, precision=1,
        format_column={tuple(sv_hdd.columns): {'width': '100px', 'text-align': 'center'}}))
    tbs.append('<br>')
    fig1 = demand_forecast_chart(asia, title='1-15 TDD forecasts charts for Asia')
    fig2 = demand_forecast_chart(china, title='1-15 TDD forecasts charts for China')
    fig3 = demand_forecast_chart(japan, title='1-15 TDD forecasts charts for Japan')
    fig4 = demand_forecast_chart(sk, title='1-15 TDD forecasts charts for South Korea')
    fig5 = demand_forecast_chart(india, title='1-15 TDD forecasts charts for India')
    tbs.append(fig1)
    tbs.append(fig2)
    tbs.append(fig3)
    tbs.append(fig4)
    tbs.append(fig5)
    region_list = ['Asia', 'China', 'Japan', 'South Korea', 'India']
    for i in region_list:
        df2 = sql.read_sql(
            (f"select DATES as dt, POP_HDD, POP_HDD_10Y, POP_CDD, POP_CDD_10Y from "
             f"[L025].[dbo].[CWG_Actual_Asia] where REGION='{i}' order by dt"))
        a_df = df2.drop_duplicates(subset=['dt'])
        a_df = a_df.rename(columns={"dt": "Date"})
        a_df['Date'] = pd.to_datetime(a_df['Date'])
        a_df.set_index('Date', inplace=True)
        a_df['NG_HDD'] = a_df['POP_HDD'] + a_df['POP_CDD']
        a_df['10Y_NG_HDD'] = a_df['POP_HDD_10Y'] + a_df['POP_CDD_10Y']
        a_df = a_df[['NG_HDD', '10Y_NG_HDD']]
        a_df.dropna(inplace=True)
        if i != 'India':
            df2_fcast = sql.read_sql(
                (f"select t1.* from CWG_Fcast_Asia t1 INNER JOIN (select max(AS_OF_DATE) as dt from "
                 f"CWG_Fcast_Asia) t2 on t1.AS_OF_DATE = t2.dt where REGION='{i}' order by DATES"))
            df2_fcast = df2_fcast[['DATES', 'POP_HDD', 'POP_HDD_10Y', 'POP_CDD', 'POP_CDD_10Y']]
            df2_fcast.set_index('DATES', inplace=True)
            df2_fcast['NG_HDD'] = df2_fcast['POP_HDD'] + df2_fcast['POP_CDD']
            df2_fcast['10Y_NG_HDD'] = df2_fcast['POP_HDD_10Y'] + df2_fcast['POP_CDD_10Y']
            df2_fcast = df2_fcast[['NG_HDD', '10Y_NG_HDD']]
        else:
            df2_fcast = pd.DataFrame()
        if len(df2_fcast) > 0:
            a_df = pd.concat([a_df, df2_fcast], axis=0)
        a_df = a_df[~a_df.index.duplicated(keep='first')]
        if (today() + dt.timedelta(10)).month in [4, 5, 6, 7, 8, 9]:
            winter = winter_hdd(a_df, winsum='S')
            winter_table = witer_month_table(winter, winsum='S')
            summer = winter_hdd(a_df, winsum='W')
            summer_table = witer_month_table(summer, winsum='W')
        else:
            winter = winter_hdd(a_df, winsum='W')
            winter_table = witer_month_table(winter, winsum='W')
            summer = winter_hdd(a_df, winsum='S')
            summer_table = witer_month_table(summer, winsum='S')
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
        if i == "Asia":
            winter_table_bcf = winter_table.copy()
            winter_table_bcf.loc[:, winter_table_bcf.columns[1:]] = winter_table_bcf.iloc[:, 1:] * 25 / 1000
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
            summer_table_bcf = summer_table.copy()
            summer_table_bcf.loc[:, summer_table_bcf.columns[1:]] = summer_table_bcf.iloc[:, 1:] * 25 / 1000
            summer_table_bcf_html = table.html_format(summer_table_bcf, precision=1, format_column={
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
            tbs.append(f'{i} BCM change vs 10Y Normal - last season: ')
            tbs.append(summer_table_bcf_html)
            tbs.append('<br>')
            tbs.append(f'{i} TDD vs 10Y Normal - current and next month include TDD forecasts: ')
            tbs.append(winter_table_html)
            tbs.append('<br>')
            tbs.append(f'{i} BCM change vs 10Y Normal - current and next month include TDD forecasts: ')
            tbs.append(winter_table_bcf_html)
            tbs.append('<br>')
        else:
            tbs.append(f'{i} TDD vs 10Y Normal - current and next month include TDD forecasts: ')
            tbs.append(winter_table_html)
            tbs.append('<br>')
        if (today() + dt.timedelta(10)).month in [4, 5, 6, 7, 8, 9]:
            tbs.append(cumulative_cdd_chart(winter, df2_fcast))
        else:
            tbs.append(cumulative_cdd_chart(summer, df2_fcast))
            tbs.append(cumulative_hdd_chart(winter, df2_fcast))
    tbs.append(table.html_text(f"Updated at {dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"))
    table.figures_to_html(
        [table.html_text(report_name, style="font-family:Calibri;", tag='h1')] + tbs,
        f"{html_path}\\weather\\{file_name}.html", task_name="Weather - Global TDD")




if __name__ == '__main__':
    update()
