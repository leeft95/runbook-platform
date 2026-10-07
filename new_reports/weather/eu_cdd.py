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
from ecm.cmds.config import output_path, html_path, root_path, gas_group
from ecm.cmds._email import send_email
from ecm.cmds.cdr import today
from weather_common import combine_actual_forecast_normal_global_cdd as combine_actual_forecast_normal
from ecm.cmds.utils import convert_path_to_linux

send_to = ['rzhao@elementcapital.com']
report_name = "Weather - Europe CWG CDD Update"
file_name = "eu_cdd"  # without .py
file_path = f"{root_path}\\autoreports\\reports\\weather\\{file_name}.py"
weather_csv = f"{output_path}\\csvs\\weather"


def _unrecovered(location):
    raise NotImplementedError(f"eu_cdd photographed source: {location}")


def add_schedule():
    """
    """
    sys.path.append(f"{root_path}\\autoreports\\schedule")
    from tasks import WinTaskPoC
    from ecm.atom.wintask.scheduler import ECMWinTask
    from ecm.atom.wintask.utils import Days

    win_task = ECMWinTask(
        days=Days.MONDAY | Days.TUESDAY | Days.WEDNESDAY | Days.THURSDAY | Days.FRIDAY | Days.SUNDAY,
        start_datetime=dt.datetime(2023, 7, 1, 11, 5),
        timezone="Europe/London",
        task_name=report_name,
        task=WinTaskPoC(name=f'"{report_name}"', filepath=f'"{file_path}"'),
        background_task=True,
        python_excecutable=r"C:\local\python\miniconda\envs\ecm_cmds\pythonw.exe"
    )
    win_task.create_task()


def get_forecast_hdd(area, cycle='00', model=None):
    """
    Last 3 forecasts from Stormvista
    """
    if model == 'EC46':
        tbl_sfx = '_EC46'
    elif model == 'GFS':
        tbl_sfx = '_GFS'
    else:
        tbl_sfx = ''
    sql_str = f"""select t1.* from CWG_StormVista_Global_fcast t1 INNER JOIN
                    (select Top (3) AS_OF_DATE as dt from CWG_StormVista_Global_fcast{tbl_sfx} group by As_of_date
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


def demand_forecast_chart(fcast_df, title, bbg_tdd=None, bbg_tdd1=None):
    if not isinstance(bbg_tdd, pd.DataFrame):
        bbg_tdd = pd.DataFrame()
    if not isinstance(bbg_tdd1, pd.DataFrame):
        bbg_tdd1 = pd.DataFrame()
    fcast_df = fcast_df.loc[fcast_df.index >= fcast_df.index[-1] - dt.timedelta(days=35), :]
    if bbg_tdd is not None and bbg_tdd1 is None:
        bbg_tdd = pd.concat(
            [bbg_tdd, fcast_df.loc[fcast_df.index > bbg_tdd.index[-1], 'Actual'].to_frame(bbg_tdd.columns[0])], axis=0)
        return get_chart(fcast_df, title=title, y_axis_title='cdd', data1=bbg_tdd)
    elif not bbg_tdd.empty and not bbg_tdd1.empty:
        bbg_tdd = pd.concat(
            [bbg_tdd, fcast_df.loc[fcast_df.index > bbg_tdd.index[-1], 'Actual'].to_frame(bbg_tdd.columns[0])], axis=0)
        bbg_tdd1 = pd.concat(
            [bbg_tdd1, fcast_df.loc[fcast_df.index > bbg_tdd1.index[-1], 'Actual'].to_frame(bbg_tdd1.columns[0])], axis=0)
        return get_chart(fcast_df, title=title, y_axis_title='cdd', data1=bbg_tdd,
                         data2=bbg_tdd1)
    else:
        return get_chart(fcast_df, title=title, y_axis_title='cdd')


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
                               line=dict(width=2, **_unrecovered('get_chart original line 113: clipped line color/style'))))
            elif idx == 1:
                fig.add_trace(go.Scatter(x=data.index, y=data[col], showlegend=True, name=col,
                                         line=dict(width=2, color='red', dash='dash')))
            elif idx == 2:
                fig.add_trace(go.Scatter(x=data.index, y=data[col], showlegend=True, name=col,
                                         line=dict(width=1, color='orange', dash='dash')))
            else:
                fig.add_trace(go.Scatter(x=data.index, y=data[col], showlegend=True, name=col,
                                         line=_unrecovered('get_chart original line 121: clipped line style')))
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
                               line=dict(width=2, **_unrecovered('get_chart original line 134: clipped line color/style'))))
            elif idx == 1:
                fig.add_trace(go.Scatter(x=data.index, y=data[col], showlegend=True, name=col,
                                         line=dict(width=2, color='red', dash='dash')))
            elif idx == 2:
                fig.add_trace(go.Scatter(x=data.index, y=data[col], showlegend=True, name=col,
                                         line=dict(width=1, color='orange', dash='dash')))
            else:
                fig.add_trace(go.Scatter(x=data.index, y=data[col], showlegend=True, name=col,
                                         line=_unrecovered('get_chart original line 142: clipped line style')))
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
                               line=dict(width=2, **_unrecovered('get_chart original line 164: clipped line color/style'))))
            elif idx == 1:
                fig.add_trace(go.Scatter(x=data.index, y=data[col], showlegend=True, name=col,
                                         line=dict(width=2, color='red', dash='dash')))
            elif idx == 2:
                fig.add_trace(go.Scatter(x=data.index, y=data[col], showlegend=True, name=col,
                                         line=dict(width=1, color='orange', dash='dash')))
            else:
                fig.add_trace(go.Scatter(x=data.index, y=data[col], showlegend=True, name=col,
                                         line=_unrecovered('get_chart original line 172: clipped line style')))
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
    season = season.drop_duplicates(keep="last")

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


def cumulative_hdd_chart(winter, hdd_df, title='Cumulative TDDs vs 10Y normal'):

    winterpvt2 = pd.pivot_table(winter, columns=['Season_year'], index=['day_count'],
                                values='Cumulative of Actual_vs_Normal per season')
    winterpvt2_email = winterpvt2[winterpvt2.columns[-6:]]

    lvi = winterpvt2_email.iloc[:, -1].last_valid_index()
    if lvi < len(winterpvt2_email):
        last_col = winterpvt2_email.columns[-1]
        winterpvt2_email['Latest forecast'] = winterpvt2_email.loc[lvi - len(hdd_df) + 1: lvi, last_col]
        winterpvt2_email.loc[lvi - len(hdd_df) + 1: lvi, last_col] = np.nan

    base_date = hdd_df.index[0] - dt.timedelta(days=1)
    if base_date.month >= 10:
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
                               line=dict(width=3, color=_unrecovered('original line 289: clipped color beginning b')))
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


def cumulative_cdd_chart(winter, hdd_df, title='Cumulative CDDs vs 10Y normal'):

    winterpvt2 = pd.pivot_table(winter, columns=['Season_year'], index=['day_count'],
                                values='Cumulative of Actual_vs_Normal per season')
    winterpvt2_email = winterpvt2[winterpvt2.columns[-6:]]

    lvi = winterpvt2_email.iloc[:, -1].last_valid_index()
    if lvi < len(winterpvt2_email):
        last_col = winterpvt2_email.columns[-1]
        winterpvt2_email['Latest forecast'] = winterpvt2_email.loc[lvi - len(hdd_df) + 1: lvi, last_col]
        winterpvt2_email.loc[lvi - len(hdd_df) + 1: lvi, last_col] = np.nan

    base_date = hdd_df.index[0] - dt.timedelta(days=1)
    date_idx = pd.date_range(dt.datetime(base_date.year, 5, 1), dt.datetime(base_date.year, 9, 30))
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
                               line=dict(width=3, color=_unrecovered('original line 338: clipped color beginning b')))
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
            f"Select distinct * from CWG_Fcast_Europe where AS_OF_DATE='{j.strftime('%Y-%m-%d')}' and REGION='Europe' order by DATES")
        hist_fcst.set_index("DATES", inplace=True)
        hist_fcst.index = pd.to_datetime(hist_fcst.index)
        cur_d_fcst = hist_fcst["POP_CDD"]
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
        asia.to_excel(convert_path_to_linux(f"{weather_csv}\\cdd_forecast_europe.xlsx"))
    except:
        pass
    try:
        china.to_excel(convert_path_to_linux(f"{weather_csv}\\cdd_forecast_ttf.xlsx"))
    except:
        pass
    try:
        japan.to_excel(convert_path_to_linux(f"{weather_csv}\\cdd_forecast_italy.xlsx"))
    except:
        pass
    try:
        sk.to_excel(convert_path_to_linux(f"{weather_csv}\\cdd_forecast_uk.xlsx"))
    except:
        pass
    tbs.append('StormVista table (ECMWF-EPS):')
    sv_hdd = pd.read_csv(convert_path_to_linux(f"{weather_csv}\\eu_cdd_stormvista.csv"))
    tbs.append(table.html_format(
        sv_hdd, precision=1,
        format_column={tuple(sv_hdd.columns): {'width': '100px', 'text-align': 'center'},
                       sv_hdd.columns[-3]: {'width': '100px', 'text-align': 'center', 'format': '{:.1%}'},
                       sv_hdd.columns[-2]: {'width': '100px', 'text-align': 'center', 'format': '{:.1%}'},
                       sv_hdd.columns[-1]: {'width': '100px', 'text-align': 'center', 'format': '{:.1%}'}}
    ))
    tbs.append('<br>')
    h_df, a_df = get_hdd_cdd(region="Europe")
    eu_actual = a_df.copy()
    cur_m_sdate = today() + relativedelta(day=1)
    cur_m_tdd = monthly_tdd_evolution(cur_m_sdate, eu_actual)
    if (today() + relativedelta(days=15)).month != today().month:
        next_m_sdate = today() + relativedelta(day=31) + relativedelta(days=1)
        next_m_tdd = monthly_tdd_evolution(next_m_sdate, eu_actual)
    else:
        next_m_tdd = pd.Series()
    fig1 = demand_forecast_chart(asia, title='1-15 CDD forecasts charts for Europe',
        bbg_tdd=cur_m_tdd.to_frame("this month"), bbg_tdd1=next_m_tdd.to_frame("next month"))
    fig2 = demand_forecast_chart(china, title='1-15 CDD forecasts charts for TTF')
    fig3 = demand_forecast_chart(japan, title='1-15 CDD forecasts charts for Italy')
    fig4 = demand_forecast_chart(sk, title='1-15 CDD forecasts charts for UK')
    figs_link = []
    tbs.append(fig1)
    figs_link.append(fig2)
    figs_link.append(fig3)
    figs_link.append(fig4)
    table.figures_to_html(figs_link, filename=f"{html_path}\\weather\\links\\eu_weather_other_charts_cdd.html")
    tbs.append(u'<a href="{}\\weather\\links\\eu_weather_other_charts_cdd.html">Link to other charts</a>'.format(html_path))
    tbs.append('<br>')
    region_list = ['Europe', 'TTF', 'Italy', 'Iberian Peninsula', 'United Kingdom']
    tbs_link = []
    tbs_link.append("<div style='font-family:Calibri;' >")
    for i in region_list:
        print(i)
        h_df, a_df = get_hdd_cdd(region=i)
        df2_fcast = sql.read_sql(
            (f"select t1.* from CWG_Fcast_Europe t1 INNER JOIN (select max(AS_OF_DATE) as dt from "
             f"CWG_Fcast_Europe) t2 on t1.AS_OF_DATE = t2.dt where REGION='{i}' order by DATES"))
        df2_fcast = df2_fcast[['DATES', 'POP_HDD', 'POP_HDD_10Y', 'POP_CDD', 'POP_CDD_10Y']]
        df2_fcast.set_index('DATES', inplace=True)
        df2_fcast['NG_HDD'] = df2_fcast['POP_CDD']
        df2_fcast['10Y_NG_HDD'] = df2_fcast['POP_CDD_10Y']
        df2_fcast = df2_fcast[['NG_HDD', '10Y_NG_HDD']]
        if len(df2_fcast) > 0:
            a_df = a_df.append(df2_fcast)
        a_df = a_df[~a_df.index.duplicated(keep='first')]
        if today().month in [5, 6, 7, 8, 9]:
            summer = winter_hdd(a_df, winsum='W')
            summer_table = witer_month_table(summer, winsum='W')
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
            winter = winter_hdd(a_df, winsum='S')
            winter_table = witer_month_table(winter, winsum='S')
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
        else:
            summer = winter_hdd(a_df, winsum='S')
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
            tbs.append(f'{i} HDD vs 10Y Normal - current and next month include CDD forecasts: ')
            tbs.append(winter_table_html)
            tbs.append('<br>')
        else:
            tbs_link.append(f'{i} BCM change vs 10Y Normal - Last season: ')
            tbs_link.append(summer_table_html)
            tbs_link.append('<br>')
            tbs_link.append(f'{i} HDD vs 10Y Normal - current and next month include CDD forecasts: ')
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
            tbs.append(f'{i} BCM change vs 10Y Normal - current and next month include CDD forecasts: ')
            tbs.append(winter_table_bcf_html)
            tbs.append('<br>')
        else:
            tbs_link.append(f'{i} BCM change vs 10Y Normal - current and next month include CDD forecasts: ')
            tbs_link.append(winter_table_bcf_html)
            tbs_link.append('<br>')
        if i == "Europe":
            if today().month in [5, 6, 7, 8, 9]:
                tbs.append(cumulative_cdd_chart(winter, df2_fcast))
            else:
                tbs.append(cumulative_hdd_chart(winter, df2_fcast))
        else:
            if today().month in [5, 6, 7, 8, 9]:
                tbs_link.append(cumulative_cdd_chart(winter, df2_fcast))
            else:
                tbs_link.append(cumulative_hdd_chart(winter, df2_fcast))
    table.figures_to_html(tbs_link, filename=f"{html_path}\\weather\\links\\eu_weather_other_charts_1_cdd.html")
    tbs.append(u'<a href="{}\\weather\\links\\eu_weather_other_charts_1_cdd.html">Link to other charts</a>'.format(html_path))
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
