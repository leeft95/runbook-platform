import pandas as pd
import numpy as np
import datetime as dt
import time
import plotly.graph_objects as go
import plotly as py
import sys
import os
os.environ['CMDSTAN'] = "C:\\local\\python\\miniconda\\envs\\ecm_cmds\\Library\\bin\\cmdstan"
import holidays
from pandas.tseries.offsets import BDay
from dateutil.relativedelta import relativedelta, FR
from scipy.interpolate import UnivariateSpline
import ecm.cmds.chart as chart
import ecm.cmds.sql as sql
import ecm.cmds.table as table
import ecm.cmds.data as dv
import ecm.cmds.bbg as bbg
import ecm.cmds.talib as talib
import ecm.cmds.time_series as ts
from ecm.cmds.config import output_path, html_path, root_path, gas_group, csv_path
from ecm.cmds._email import send_email
from ecm.cmds.cdr import today
from ecm.cmds.utils import convert_path_to_linux

def _unrecovered(message, *visible_arguments):
    raise NotImplementedError(message)


send_to = ['rzhao@elementcapital.com', 'ltrindade@elementcapital.com']
report_name = "Weather - European temperature and LDZ"
file_name = "eu_weather"
file_path = f"{root_path}\\autoreports\\reports\\weather\\{file_name}.py"
weather_csv_path = f"{csv_path}\\weather"
weather_json_folder = f"{output_path}\\json\\weather"
weather_pdf_folder = f"{output_path}\\pdf\\weather"
weather_html_folder = f"{html_path}\\weather"


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
        start_datetime=dt.datetime(2023, 7, 1, 8, 55), timezone="Europe/London",
        repetition_interval=dt.timedelta(hours=12, minutes=20),
        repetition_duration=dt.timedelta(hours=12, minutes=20),
        task_name=report_name, task=WinTaskPoC(name=f'"{report_name}"', filepath=f'"{file_path}"'),
        background_task=True, python_excecutable=r"C:\local\python\miniconda\envs\ecm_cmds\pythonw.exe",
    )
    win_task.create_task()


def get_eu_gas_demand(sdate='01_Jan_2009'):
    demand = dv.ce_eugasopdata(
        assets=('1836,185,188,192,54,83,103,1801,1802,1803,2068,665,668,671,685,1734,1737,'
                '1740,1743,1746,1749,1752,1755,2405,209,210,2097,2458,1765,2520,1862,2371,'
                '1877,2481,2965,2967,2966,2968'),
        variable='netFlow,withdrawal', dateFrom=sdate, unit='mcm')
    demand = demand[:today()]
    demand = demand.fillna(method='ffill')
    demand.rename(columns={
        'DE, PowGen.Gas.GasBurnEq': 'DE - G2P', 'AT, PowGen.Gas.GasBurnEq': 'AT - G2P',
        'CZ, PowGen.Gas.GasBurnEq': 'CZ - G2P', 'NL, PowGen.Gas.GasBurnEq': 'NL - G2P',
        'SK, PowGen.Gas.GasBurnEq': 'SK - G2P'}, inplace=True)
    demand['AT - LDZ'] = demand['AT, Demand'] - demand['AT - G2P']
    demand['CZ - LDZ'] = demand['CZ, Demand'] - demand['CZ - G2P']
    demand['SK - LDZ'] = demand['SK, Demand'] - demand['SK - G2P']
    demand['NL, Demand - Ind'] = demand['NL, Demand - NonLDC'] - demand['NL - G2P']
    demand['DE - LDZ1'] = (demand['DE, Dem, H, Ldc, GPL'] + demand['DE, Dem, H, Ldc, NCG'] +
                           demand['DE, Dem, L, Ldc, GPL'] + demand['DE, Dem, L, Ldc, NCG'])
    demand['DE - IND1'] = ((demand['DE, Dem, H, NonLdc, GPL'] + demand['DE, Dem, H, NonLdc, NCG'] +
                           demand['DE, Dem, L, NonLdc, GPL'] + demand['DE, Dem, L, NonLdc, NCG']) - demand[_unrecovered('EU weather 85: clipped demand column')])
    demand['DE - LDZ2'] = demand['DE, Dem, H, Ldc'] + demand['DE, Dem, L, Ldc']
    demand['DE - IND2'] = demand['DE, Dem, H, NonLdc'] + demand['DE, Dem, L, NonLdc']
    demand['DE - LDZ'] = pd.concat([
        demand.loc[:dt.datetime(2016, 10, 1), 'DE - LDZ1'], demand.loc[dt.datetime(2016, 10, 2):, 'DE - LDZ2']], axis=0)
    demand['DE - IND'] = pd.concat([
        demand.loc[:dt.datetime(2016, 10, 1), 'DE - IND1'], demand.loc[dt.datetime(2016, 10, 2):, 'DE - IND2']], axis=0)
    demand['LDZ'] = (demand['DE - LDZ'] + demand['SK - LDZ'] + demand['CZ - LDZ'] + demand['AT - LDZ'] + demand[
        'BE, Demand - Ldc'] + demand['FR, Demand - Ldc'] + demand['GB, Demand - LDC'] + demand['IT, Demand, Ldc'] + demand[
        'NL, Demand - LDC'] + demand['CH, Demand'])
    demand['G2P'] = (demand['DE - G2P'] + demand['AT - G2P'] + demand['CZ - G2P'] + demand['NL - G2P'] + demand['SK - G2P'] +
                     demand['FR, Demand - Pow'] + demand['GB, Demand - Power'] + demand['IT, Demand, Pow'] + demand['BE, Demand - Pow'])
    demand['IND'] = (demand['BE, Demand - Ind'] + demand['FR, Demand - Ind'] + demand['IT, Demand, Ind'] +
                     demand['GB, Demand - Industrial'] + demand['DE - IND'] + demand['NL, Demand - Ind'])
    demand_ldc = demand[['DE - LDZ', 'SK - LDZ', 'CZ - LDZ', 'AT - LDZ', 'BE, Demand - Ldc', 'FR, Demand - Ldc', 'GB, Demand - LDC',
                         'IT, Demand, Ldc', 'NL, Demand - LDC', 'CH, Demand']]
    demand_ldc.columns = ['DE', 'SK', 'CZ', 'AT', 'BE', 'FR', 'GB', 'IT', 'NL', 'CH']
    return demand_ldc

country_list = ['DE', 'SK', 'CZ', 'AT', 'BE', 'FR', 'GB', 'IT', 'NL', 'CH']
cdr_dict = {'DE': 'GE', 'SK': 'SO', 'CZ': 'CZ', 'AT': 'AS', 'BE': 'BE',
            'FR': 'FR', 'GB': 'GB', 'IT': 'IT', 'NL': 'NE', 'CH': 'SZ'}


def plotly_chart(data, title, **kwargs):
    """
    draw plotly chart from data
    if format_dict is None, draw line chart is mode is None, x asix is index,
    otherwise draw scatter chart, x asix is first colume
    """
    mode = kwargs.get('mode', None)
    file_path = kwargs.get('file_path', None)
    data1 = kwargs.get('data1', None)
    color_col = kwargs.get('color_col', None)
    y_axis_title = kwargs.get('y_axis_title', None)
    x_axis_title = kwargs.get('x_axis_title', None)
    format_dict = kwargs.get('format_dict', None)
    fig = go.Figure()
    if format_dict is None:
        if mode is None:
            if color_col is None:
                if isinstance(data, pd.DataFrame):
                    for col in data.columns:
                        fig.add_trace(go.Scatter(x=data.index, y=data[col], opacity=0.8, showlegend=True,
                                                **_unrecovered('EU weather 143: clipped trace name argument'), line=dict(width=1)))
                elif isinstance(data, pd.Series):
                    fig.add_trace(go.Scatter(x=data.index, y=data, opacity=0.8, showlegend=False))
            else:
                category = data[color_col].unique()
                for i in category:
                    fig.add_trace(go.Scatter(x=data.loc[data[color_col] == i, :].iloc[:, 0],
                                             y=data.loc[data[color_col] == i, :].iloc[:, 1], opacity=0.8, showlegend=True, name=str(i)))
        else:
            if color_col is None:
                for i in range(1, len(data.columns)):
                    fig.add_trace(go.Scatter(x=data.iloc[:, 0], y=data.iloc[:, i], opacity=0.8, showlegend=True,
                                             mode=_unrecovered('EU weather 158: clipped scatter mode'), name=str(data.columns[i])))
            else:
                category = data[color_col].unique()
                for i in category:
                    fig.add_trace(go.Scatter(x=data.loc[data[color_col] == i, :].iloc[:, 0],
                                             y=data.loc[data[color_col] == i, :].iloc[:, 1], opacity=0.8, showlegend=True, mode='markers', name=str(i)))
    else:
        for key, val in format_dict.items():
            fig.add_trace(go.Scatter(
                x=val['x'] if 'x' in val.keys() else data.index, y=data[key],
                text=val['text'] if 'text' in val.keys() else data.index,
                textposition=val['textposition'] if 'textposition' in val.keys() else _unrecovered('EU weather 171: clipped textposition default'),
                mode=val['mode'] if 'mode' in val.keys() else 'lines+markers+text',
                opacity=val['opacity'] if 'opacity' in val.keys() else 0.8,
                showlegend=val['showlegend'] if 'showlegend' in val.keys() else True,
                name=val['name'] if 'name' in val.keys() else key,
                line=dict(width=val['width'] if 'width' in val.keys() else 1,
                          color=val['color'] if 'color' in val.keys() else None,
                          dash=val['dash'] if 'dash' in val.keys() else None)))
    if data1 is not None:
        if mode is None:
            fig.add_trace(go.Scatter(x=data1.iloc[:, 0], y=data1.iloc[:, 1], opacity=0.8, showlegend=True, name=str(data1.columns[1])))
        else:
            for i in range(1, len(data.columns)):
                fig.add_trace(go.Scatter(x=data1.iloc[:, 0], y=data1.iloc[:, i], opacity=0.8, showlegend=True,
                                         mode=_unrecovered('EU weather 187: clipped scatter mode'), name=str(data1.columns[i])))
    fig.update_layout(title={'text': title, 'x': 0.5, 'xanchor': 'center'}, xaxis_title=x_axis_title, yaxis_title=y_axis_title, width=900, height=600)
    if file_path is not None:
        py.offline.plot(fig, auto_open=False, filename=convert_path_to_linux(file_path))
    return fig


def fit_demand_forecast(df, start=-1, hol=None, forecast_periods=0, forecast_x=None):
    data = df.copy()
    data.columns = ['x', 'y']
    data.index.name = 'ds'
    data.reset_index(inplace=True)
    forecast = talib.ts_regression(data, hol=hol, start=start, forecast_periods=forecast_periods, forecast_x=forecast_x)
    return forecast['yhat']


def format_temperature(temperature_fore0):
    temperature_fore0.columns = ['Date', 'Temperature']
    temperature_fore0.set_index('Date', inplace=True)
    temperature_fore0.index = pd.to_datetime(temperature_fore0.index)
    temperature_fore0.index = temperature_fore0.index.date
    return temperature_fore0


def ldz_change_vs_history():
    country_list_1 = ['GB', 'DE', 'IT', 'FR', 'NL', 'CZ', 'BE', 'AT', 'SK', 'CH']
    gas = ts.read_csv(f"{weather_csv_path}\\eu_gas_demand_live.csv", index_name='Date')
    temperature = ts.read_csv(f"{weather_csv_path}\\eu_temperature_live.csv", index_name='Unnamed: 0')
    gas = gas[gas.index.year >= 2015]
    temperature = temperature[temperature.index.year >= 2015]
    d1_run_date = today() - BDay(1)
    norm = pd.read_csv(convert_path_to_linux(f"{weather_csv_path}\\eu_gas_normal.csv"))
    norm.set_index('ds', inplace=True)
    norm.index = pd.to_datetime(norm.index)
    norm_2021 = norm[norm.index >= dt.datetime(2021, 10, 1)]
    norm_2021['Total'] = norm_2021.sum(axis=1)
    figs = []
    total_df = pd.DataFrame(0, index=temperature.index, columns=['gas demand', 'forecast'])
    forecast_df = pd.DataFrame()
    for i in country_list_1:
        print(i)
        temp_data = sql.read_sql(
            ("Select * from ECMWF_Europe_fcast where Run = 0 and ForecastOnDate = '{:s}' and Country = '{:s}" + _unrecovered('EU weather 239: clipped SQL suffix')).format(
                dt.datetime.strftime(d1_run_date, '%Y-%m-%d'), i))
        temp_data.set_index("Date", inplace=True)
        temp_data.index = pd.to_datetime(temp_data.index)
        lvd = temperature[i].last_valid_index()
        lvd_loc = temperature.index.get_loc(lvd)
        temperature_ = pd.concat([temperature.loc[:lvd, i], temp_data.loc[temperature.index[lvd_loc + 1]:gas.index[-1], "Temperature"]], axis=0)
        df = pd.concat([temperature_, gas[i]], axis=1)
        df.columns = ['temperature', 'gas demand']
        start = df['gas demand'].first_valid_index()
        df = df.loc[start:, :]
        i_holidays = holidays.CountryHoliday(i, years=range(2000, 2031))['2000-01-01':'2030-12-31']
        df_holidays = pd.DataFrame({'holiday': i, 'ds': i_holidays})
        if i == 'GB':
            df.drop(df[df['temperature'].isnull()].index, axis=0, inplace=True)
        df['forecast'] = fit_demand_forecast(df, start=None, hol=df_holidays)
        df.loc[df['forecast'] == 0, 'forecast'] = np.nan
        df.loc[df['forecast'] < 0, 'forecast'] = 0
        total_df['gas demand'] = total_df['gas demand'] + df['gas demand']
        total_df['forecast'] = total_df['forecast'] + df['forecast']
        forecast_df['{:s}_gas demand'.format(i)] = df['gas demand']
        forecast_df['{:s}_forecast'.format(i)] = df['forecast']
    total_df = total_df.loc[dt.datetime(2014, 12, 31):]
    total_df.to_csv(convert_path_to_linux(f"{weather_csv_path}\\total_ldz_0.csv"))
    forecast_by_country = pd.DataFrame()
    for i in country_list:
        forecast_by_country[i] = forecast_df[f"{i}_forecast"]
    forecast_by_country["total"] = forecast_by_country.sum(axis=1)
    current_forecast = pd.read_excel(convert_path_to_linux(f"{weather_csv_path}\\eu_ldz_forecast_latest_by" + _unrecovered('EU weather 280: clipped workbook suffix/arguments')))
    current_forecast.set_index("Unnamed: 0", inplace=True)
    current_forecast.index = pd.to_datetime(current_forecast.index)
    current_forecast.columns = [x.split("_")[0] for x in current_forecast.columns]
    gas_normal = ts.read_csv(f"{weather_csv_path}\\eu_gas_normal.csv", index_name='ds')
    gas_normal['total'] = gas_normal.sum(axis=1)
    combined_forecast = pd.concat([forecast_by_country.iloc[:-1, :], current_forecast,
                                  gas_normal.loc[gas_normal.index > current_forecast.index[-1]]], axis=0)
    combined_forecast.to_excel(convert_path_to_linux(
        "\\\\elementcapital.corp\\ECNS01\\PM\\Michel Kikano\\Joseph\\EU_Gas\\Modelle" + _unrecovered('EU weather 290: clipped Excel destination')))
    total_df_2021 = total_df[total_df.index >= dt.datetime(2021, 10, 1)]
    df_err_2021 = (total_df_2021['gas demand'] - total_df_2021['forecast'])
    df_err_ratio_2021 = df_err_2021 / total_df_2021['forecast']
    df_err_ratio_2021_7d = df_err_ratio_2021.rolling(7).mean()
    df_err_2021_norm = (total_df_2021['gas demand'] - norm_2021['Total'])
    df_err_ratio_2021_norm = df_err_2021_norm / norm_2021['Total']
    data_for_table = pd.concat([norm_2021['Total'], total_df_2021, df_err_2021_norm, df_err_ratio_2021_norm, df_err_2021,
                                df_err_ratio_2021, df_err_ratio_2021_7d], axis=1)
    data_for_table.columns = ['Normal', 'Actual', 'Forecast', 'Actual-Normal Non weather adj',
                              'Actual-Normal % Non weather adj', 'Actual-Forecast weather adj',
                              'Actual-Forecast % weather adj', '7d MA of Actual-Forecast % weather adj']
    data_for_table = data_for_table.loc[data_for_table.index <= today(), :].iloc[-20:, :]
    data_for_table.index.name = 'EU'
    data_for_table.reset_index(inplace=True)
    data_for_table['EU'] = data_for_table['EU'].dt.strftime('%Y-%m-%d')
    html_tb = table.html_format(
        df=data_for_table, precision=1,
        format_column={
            'EU': {'width': '80px', 'text-align': 'center'},
            'Normal': {'width': '80px', 'text-align': 'center', 'format': '{:.0f}'},
            'Actual': {'width': '80px', 'text-align': 'center', 'format': '{:.0f}'},
            'Forecast': {'width': '80px', 'text-align': 'center', 'format': '{:.0f}'},
            'Actual-Normal Non weather adj': {'width': '100px', 'text-align': 'center'},
            'Actual-Normal % Non weather adj': {'width': '100px', 'text-align': 'center', 'format': '{:.1%}'},
            'Actual-Forecast weather adj': {'width': '100px', 'text-align': 'center'},
            'Actual-Forecast % weather adj': {'width': '100px', 'text-align': 'center', 'format': '{:.1%}'},
            '7d MA of Actual-Forecast % weather adj': {'width': '100px', 'text-align': 'center', 'format': '{:.1%}'},
        })
    figs.append(html_tb)
    f = open(convert_path_to_linux(f"{weather_html_folder}\\eu_ldz_destruction_table.html"), 'w')
    f.write(html_tb)
    f.close()
    eu_chart = chart.line_chart(
        df=total_df_2021.iloc[-60:, :],
        data_p2y1=df_err_2021.rolling(7).mean().to_frame('Actual-Fitted 7d mean').iloc[-60:, :],
        data_p3y1=(df_err_ratio_2021 * 100).rolling(7).mean().to_frame('Actual-Fitted ratio 7d mean').iloc[-60:, :],
        title='EU Actual vs Fitted LDZ', y_axis_title='mcm/d', p2y1_axis_title='mcm/d', p3y1_axis_title='error (%)', subplots=[0.5, 0.25, 0.25])
    figs.append(eu_chart)
    eu_chart.write_json(convert_path_to_linux(f"{weather_json_folder}\\eu_ldz_chart.json"))
    cum_dd = total_df_2021['forecast'] - total_df_2021['gas demand']
    cum_dd = cum_dd[cum_dd.index >= dt.datetime(2022, 9, 1)]
    cum_dd = cum_dd.cumsum() / 1000
    eu_ldz_dd_chart = chart.line_chart(df=cum_dd.to_frame('EU'), title='EU cumulative demand destruction since 2022-09-01', y_axis_title='bcm')
    figs.append(eu_ldz_dd_chart)
    eu_ldz_dd_chart.write_json(convert_path_to_linux(f"{weather_json_folder}\\eu_ldz_dd_chart.json"))
    for i in country_list_1:
        total_df = pd.concat([forecast_df[f'{i}_gas demand'], forecast_df[f'{i}_forecast']], axis=1)
        total_df.columns = ['gas demand', 'forecast']
        total_df_2021 = total_df[total_df.index >= dt.datetime(2021, 10, 1)]
        df_err_2021 = (total_df_2021['gas demand'] - total_df_2021['forecast'])
        df_err_ratio_2021 = df_err_2021 / total_df_2021['forecast']
        df_err_ratio_2021_7d = df_err_ratio_2021.rolling(7).mean()
        df_err_2021_norm = (total_df_2021['gas demand'] - norm_2021[i])
        df_err_ratio_2021_norm = df_err_2021_norm / norm_2021[i]
        data_for_table = pd.concat([norm_2021[i], total_df_2021, df_err_2021_norm, df_err_ratio_2021_norm, df_err_2021,
                                    df_err_ratio_2021, df_err_ratio_2021_7d], axis=1)
        data_for_table.columns = ['Normal', 'Actual', 'Forecast', 'Actual-Normal Non weather adj',
                                  'Actual-Normal % Non weather adj', 'Actual-Forecast weather adj',
                                  'Actual-Forecast % weather adj', '7d MA of Actual-Forecast % weather adj']
        data_for_table = data_for_table.loc[data_for_table.index <= today(), :].iloc[-20:, :]
        data_for_table.index.name = i
        data_for_table.reset_index(inplace=True)
        data_for_table[i] = data_for_table[i].dt.strftime('%Y-%m-%d')
        html_tb = table.html_format(
            df=data_for_table, precision=1,
            format_column={
                i: {'width': '80px', 'text-align': 'center'},
                'Normal': {'width': '80px', 'text-align': 'center', 'format': '{:.0f}'},
                'Actual': {'width': '80px', 'text-align': 'center', 'format': '{:.0f}'},
                'Forecast': {'width': '80px', 'text-align': 'center', 'format': '{:.0f}'},
                'Actual-Normal Non weather adj': {'width': '100px', 'text-align': 'center'},
                'Actual-Normal % Non weather adj': {'width': '100px', 'text-align': 'center', 'format': '{:.1%}'},
                'Actual-Forecast weather adj': {'width': '100px', 'text-align': 'center'},
                'Actual-Forecast % weather adj': {'width': '100px', 'text-align': 'center', 'format': '{:.1%}'},
                '7d MA of Actual-Forecast % weather adj': {'width': '100px', 'text-align': 'center', 'format': '{:.1%}'},
            })
        figs.append(html_tb)
        figs.append(chart.line_chart(
            df=total_df_2021.iloc[-60:, :],
            data_p2y1=df_err_2021.rolling(7).mean().to_frame('Actual-Fitted 7d mean').iloc[-60:, :],
            data_p3y1=(df_err_ratio_2021 * 100).rolling(7).mean().to_frame('Actual-Fitted ratio 7d mean').iloc[-60:, :],
            title=f'{i} Actual vs Fitted LDZ', y_axis_title='mcm/d', p2y1_axis_title='mcm/d', p3y1_axis_title='error (%)', subplots=[0.5, 0.25, 0.25]))
        cum_dd = total_df_2021['forecast'] - total_df_2021['gas demand']
        cum_dd = cum_dd[cum_dd.index >= dt.datetime(2022, 9, 1)]
        cum_dd = cum_dd.cumsum() / 1000
        figs.append(chart.line_chart(df=cum_dd.to_frame(i), title=f'{i} cumulative demand destruction since 2022-09-01', y_axis_title='bcm'))
    table.figures_to_html(figs, filename=f"{weather_html_folder}\\actual_fitted_ldz.html")


def get_gas_demand(real_time=True):
    """
    load historical data from file, update latest data from source
    """
    gas = ts.read_csv(f"{weather_csv_path}\\eu_gas_demand.csv", index_name='Date')
    if real_time:
        gas_new = get_eu_gas_demand(sdate=dt.datetime.strftime(gas.index[-7], '%d_%b_%Y'))
        gas = pd.concat([gas.iloc[:-7, :], gas_new], axis=0)
        gas.iloc[:-7, :].to_csv(convert_path_to_linux(f"{weather_csv_path}\\eu_gas_demand.csv"))
    return gas


def get_temperature_forecast(forecast_date, location, run=0):
    """get 2w forecast on forecast date"""
    temperature_fore = bbg.get_weather_forecast(location=location, publication_date=forecast_date, run=run)
    if not temperature_fore.empty:
        temperature_fore = format_temperature(temperature_fore)
        temperature_fore_agg = temperature_fore.groupby(temperature_fore.index)['Temperature'].mean()
        return temperature_fore_agg.iloc[:-1]
    return None


def get_temperature(real_time=True):
    """
    load historical data from file, update latest data from bbg
    """
    temperature_hist = ts.read_csv(f"{weather_csv_path}\\eu_temperature.csv", index_name='Unnamed: 0')
    alldays = pd.date_range(start=temperature_hist.index[-7], end=dt.datetime.now())
    if real_time:
        temperature = pd.DataFrame()
        for i in country_list:
            temperature_new = bbg.get_historical_weather(location=i, sdate=temperature_hist.index[-7], edate=dt.datetime.now())
            temperature_new = format_temperature(temperature_new)
            temperature_new = temperature_new[~temperature_new.index.duplicated(keep='last')]
            temperature_new = temperature_new.reindex(alldays)
            temperature[i] = temperature_new['Temperature']
        temperature = pd.concat([temperature_hist.iloc[:-7, :], temperature], axis=0)
        temperature.iloc[:-7, :].to_csv(convert_path_to_linux(f"{weather_csv_path}\\eu_temperature.csv"))
    else:
        temperature = temperature_hist
    return temperature


def get_weighted_temperature(df_demand, df_temperature, window=0):
    """demand weighted temperature"""
    if window == 0:
        df_demand_smooth = df_demand
    else:
        df_demand_smooth = df_demand.rolling(window).mean()
    weights = df_demand_smooth.div(df_demand_smooth.sum(axis=1), axis=0)
    weighted_mean = (df_temperature * weights).sum(axis=1)
    if window != 0:
        weighted_mean.iloc[:window - 1] = np.nan
    return weighted_mean


def dict_df_mean_std(dict):
    """calculate the mean from dictionary of dataframes"""
    cols = dict[list(dict.keys())[0]].columns
    df_mean = pd.DataFrame()
    df_std = pd.DataFrame()
    for col in cols:
        df_temp = pd.DataFrame(np.nan, index=range(len(dict[list(dict.keys())[0]])), columns=list(dict.keys()))
        for key, val in dict.items():
            df_temp[key] = val[col].values
        df_mean[col] = df_temp.mean(axis=1)
        df_std[col] = df_temp.std(axis=1)
    return df_mean, df_std


def get_demand_forecast(gas, temperature, forecast_day=today()):
    gas_fcast = gas.copy()
    if forecast_day not in gas_fcast.index:
        gas_fcast_new = pd.DataFrame(np.nan, index=[forecast_day], columns=gas.columns)
        gas_fcast = pd.concat([gas_fcast, gas_fcast_new], axis=0)
    total_df = pd.DataFrame(0, index=temperature.index, columns=['gas demand', 'forecast'])
    forecast_df = pd.DataFrame()
    for i in country_list:
        print(i)
        df = pd.concat([temperature[i], gas_fcast[i]], axis=1)
        df.columns = ['temperature', 'gas demand']
        start = df['gas demand'].first_valid_index()
        df = df.loc[start:, :]
        i_holidays = holidays.CountryHoliday(i, years=range(2000, 2031))['2000-01-01':'2030-12-31']
        df_holidays = pd.DataFrame({'holiday': i, 'ds': i_holidays})
        if i == 'GB':
            df.drop(df[df['temperature'].isnull()].index, axis=0, inplace=True)
        df['forecast'] = fit_demand_forecast(
            df, df.index.get_loc(df['gas demand'].last_valid_index()) - _unrecovered('EU weather 517: clipped forecast start offset'),
            hol=df_holidays, forecast_periods=abs(_unrecovered('EU weather 519: clipped forecast period expression', df.index.get_loc(df['gas demand'].last_valid_index()))))
        total_df['forecast'] = total_df['forecast'] + df['forecast']
        forecast_df['{:s}_demand'.format(i)] = df.loc[forecast_day:, 'forecast']
    forecast_df['total_demand'] = total_df.loc[forecast_day:, 'forecast']
    return forecast_df


def get_normal_data(data, holiday=False):
    normal = pd.DataFrame()
    for i in data.columns:
        if holiday:
            i_holidays = holidays.CountryHoliday(i, years=range(2000, 2031))['2000-01-01':'2030-12-31']
            df_holidays = pd.DataFrame({'holiday': i, 'ds': i_holidays})
            fitted = talib.ts_forecast(data[i], hol=df_holidays)
        else:
            fitted = talib.ts_forecast(data[i])
        normal[i] = fitted['yhat']
    return normal


def temperature_to_TDD_cel(temperature, weights):
    actual_cdd = temperature - 15.5
    actual_cdd[actual_cdd < 0] = 0
    agg_actual_cdd = (actual_cdd * weights).sum(axis=1)
    actual_hdd = 15.5 - temperature
    actual_hdd[actual_hdd < 0] = 0
    agg_actual_hdd = (actual_hdd * weights).sum(axis=1)
    df = pd.concat([agg_actual_cdd, agg_actual_hdd], axis=1)
    df.columns = ['CDD', 'HDD']
    return df


def update_eu_tdd_forecast(run=0):
    save_file = convert_path_to_linux(f"{weather_csv_path}\\eu_fcast_tdd_{run}.csv")
    if os.path.exists(save_file):
        exist_data = pd.read_csv(save_file)
        sdate = pd.to_datetime(exist_data["ForecastOnDate"]).iloc[-1]
    else:
        exist_data = pd.DataFrame()
        sdate = dt.datetime(2019, 5, 29)
    sdate_str = sdate.strftime('%Y-%m-%d')
    country_list = ['AT', 'BE', 'CH', 'CZ', 'DE', 'FR', 'GB', 'IT', 'NL', 'SK']
    country_coef = [1.26, 2.56, 0.82, 1.54, 11.69, 10.85, 14.24, 16.79, 5.15, 0.86]
    total_coef = np.array(country_coef).sum()
    country_w = country_coef / total_coef
    dates = sql.read_sql(f"Select Distinct ForecastOnDate from ECMWF_Europe_fcast where ForecastOnDate > '" + _unrecovered('EU weather 568: clipped forecast-date SQL suffix'))
    if len(dates) > 0:
        eu_fcast = pd.DataFrame()
        for d in dates['ForecastOnDate']:
            print(d)
            df = pd.DataFrame()
            fcast = sql.read_sql(f"Select * from ECMWF_Europe_fcast where Run={run} and ForecastOnDate='{d}" + _unrecovered('EU weather 574: clipped SQL suffix'))
            for country in country_list:
                one_country = fcast.loc[fcast['Country'] == country, ['Date', 'Temperature']]
                one_country.set_index('Date', inplace=True)
                one_country.index = pd.to_datetime(one_country.index)
                df[country] = one_country['Temperature']
            weights_ = pd.DataFrame([country_w]*len(df), index=df.index, columns=country_list)
            tdd = temperature_to_TDD_cel(df, weights_)
            tdd['ForecastOnDate'] = d
            eu_fcast = pd.concat([eu_fcast, tdd], axis=0)
        eu_fcast.index.name = "Date"
        eu_fcast.index = eu_fcast.index.strftime("%m/%d/%Y")
        if len(exist_data) > 0:
            eu_fcast = pd.concat([exist_data.set_index("Date"), eu_fcast], axis=0)
        eu_fcast.to_csv(save_file)


def update_eu_tdd_norm():
    norm_temper = ts.read_csv(convert_path_to_linux(f"{weather_csv_path}\\eu_temperature_normal.csv"), **_unrecovered('EU weather 592: clipped index argument'))
    country_list = ['AT', 'BE', 'CH', 'CZ', 'DE', 'FR', 'GB', 'IT', 'NL', 'SK']
    country_coef = [1.26, 2.56, 0.82, 1.54, 11.69, 10.85, 14.24, 16.79, 5.15, 0.86]
    total_coef = np.array(country_coef).sum()
    country_w = country_coef / total_coef
    weights_ = pd.DataFrame([country_w] * len(norm_temper), index=norm_temper.index, columns=country_list)
    norm_tdd = temperature_to_TDD_cel(norm_temper, weights_)
    norm_tdd.to_csv(convert_path_to_linux(f"{weather_csv_path}\\eu_tdd_normal.csv"))


def update_eu_tdd_norm_spline():
    actual_tdd = ts.read_csv(convert_path_to_linux(f"{weather_csv_path}\\eu_tdd_live.csv"), index_name="Unnamed: 0")
    norm_tdd = pd.DataFrame(0, index=range(0, 366), columns=actual_tdd.columns)
    for col in actual_tdd.columns:
        data = actual_tdd[col]
        norm_by_year = ts.data_by_year(data, freq='D')
        norm_by_year_mean = norm_by_year.iloc[:, -11:-1].mean(axis=1)
        cs = UnivariateSpline(norm_by_year_mean.index, norm_by_year_mean)
        norm_tdd[col] = cs(norm_by_year_mean.index)
    norm_tdd.to_csv(convert_path_to_linux(f"{weather_csv_path}\\eu_tdd_normal_spline.csv"))


def update_eu_tdd_live():
    norm_temper = ts.read_csv(convert_path_to_linux(f"{weather_csv_path}\\eu_temperature_live.csv"), index_name="Unnamed: 0")
    country_list = ['AT', 'BE', 'CH', 'CZ', 'DE', 'FR', 'GB', 'IT', 'NL', 'SK']
    country_coef = [1.26, 2.56, 0.82, 1.54, 11.69, 10.85, 14.24, 16.79, 5.15, 0.86]
    total_coef = np.array(country_coef).sum()
    country_w = country_coef / total_coef
    weights_ = pd.DataFrame([country_w] * len(norm_temper), index=norm_temper.index, columns=country_list)
    norm_tdd = temperature_to_TDD_cel(norm_temper, weights_)
    norm_tdd.iloc[:-2, :].to_csv(convert_path_to_linux(f"{weather_csv_path}\\eu_tdd_live.csv"))


def gas_weather_forecast(send_to):
    get_hist_weather_forecast(run=0)
    get_hist_weather_forecast(run=12)
    gas = get_gas_demand(real_time=True)
    gas.to_csv(convert_path_to_linux(f"{weather_csv_path}\\eu_gas_demand_live.csv"))
    gas_normal = get_normal_data(gas, holiday=True)
    gas_normal.to_csv(convert_path_to_linux(f"{weather_csv_path}\\eu_gas_normal.csv"))
    temperature = get_temperature(real_time=True)
    temperature.to_csv(convert_path_to_linux(f"{weather_csv_path}\\eu_temperature_live.csv"))
    temperature_normal = get_normal_data(temperature, holiday=True)
    temperature_normal.to_csv(convert_path_to_linux(f"{weather_csv_path}\\eu_temperature_normal.csv"))
    gas = gas[gas.index.year >= 2015]
    gas_normal = gas_normal[gas_normal.index.year >= 2015]
    gas_total_normal = gas_normal.sum(axis=1)
    temperature = temperature[temperature.index.year >= 2015]
    temperature_normal = temperature_normal[temperature_normal.index.year >= 2015]
    temperature_total_normal = get_weighted_temperature(gas_normal, temperature_normal, window=0)
    figs = []
    tbs = []
    this_month = today().month
    this_year = today().year
    next_month = this_month + 1 if this_month < 12 else 1
    next_year = this_year if this_month < 12 else this_year + 1
    start_yr = gas.index[0].year
    end_yr = gas.index[-1].year
    hist_gas_demand = {}
    hist_total_demand = {}
    hist_temperature = {}
    hist_weighted_temperature = {}
    for yr in range(start_yr, end_yr):
        start_loc_gas = np.where(gas.index >= dt.datetime(yr, today().month, today().day))[0][0]
        start_loc_tem = np.where(temperature.index >= dt.datetime(yr, today().month, today().day))[0][0]
        hist_gas_demand[yr] = gas.iloc[start_loc_gas - 42:start_loc_gas + 78, :]
        hist_total_demand[yr] = hist_gas_demand[yr].sum(axis=1).reset_index(drop=True)
        hist_temperature[yr] = temperature.iloc[start_loc_tem - 42:start_loc_tem + 78, :]
        hist_weighted_temperature[yr] = get_weighted_temperature(hist_gas_demand[yr], hist_temperature[yr], window=14).values
    alldays = pd.date_range(start=today() - dt.timedelta(days=42), end=today() + dt.timedelta(days=77))
    hist_gas_demand_mean = dict_df_mean_std(hist_gas_demand)[0]
    hist_gas_demand_std = pd.DataFrame(hist_total_demand).std(axis=1)
    hist_gas_demand_mean.index = alldays
    hist_gas_demand_std.index = alldays
    if len(hist_weighted_temperature[2015]) == 0:
        del hist_weighted_temperature[2015]
    hist_weighted_temperature_mean = pd.DataFrame(hist_weighted_temperature).mean(axis=1)
    hist_weighted_temperature_mean.index = alldays
    hist_weighted_temperature_std = pd.DataFrame(hist_weighted_temperature).std(axis=1)
    hist_weighted_temperature_std.index = alldays
    hist_tempe_this_month_mean = temperature_total_normal.loc[(temperature_total_normal.index.month == this_month) & (temperature_total_normal.index.year == this_year)]
    hist_tempe_next_month_mean = temperature_total_normal.loc[(temperature_total_normal.index.month == next_month) & (temperature_total_normal.index.year == next_year)]
    tempe_by_yr = pd.DataFrame(hist_weighted_temperature)
    tempe_by_yr.index = alldays
    hist_tempe_this_month_std = tempe_by_yr.loc[tempe_by_yr.index.month == this_month].mean(axis=0).std()
    hist_tempe_next_month_std = tempe_by_yr.loc[tempe_by_yr.index.month == next_month].mean(axis=0).std()
    this_y1_tempe = get_weighted_temperature(hist_gas_demand[this_year - 1], hist_temperature[this_year - 1], **_unrecovered('EU weather 688: clipped weighting arguments'))
    hist_tempe_this_month_mean_y1 = this_y1_tempe.loc[this_y1_tempe.index.month == this_month].mean()
    try:
        next_y1_temp = get_weighted_temperature(hist_gas_demand[next_year - 1], hist_temperature[next_year - 1], window=14)
    except:
        next_y1_temp = get_weighted_temperature(hist_gas_demand[next_year - 2], hist_temperature[next_year - 2], window=14)
    hist_tempe_next_month_mean_y1 = next_y1_temp.loc[next_y1_temp.index.month == next_month].mean()
    hist_gas_this_month_mean = gas_total_normal.loc[(gas_total_normal.index.month == this_month) & (gas_total_normal.index.year == this_year)]
    hist_gas_next_month_mean = gas_total_normal.loc[(gas_total_normal.index.month == next_month) & (gas_total_normal.index.year == next_year)]
    gas_by_yr = pd.DataFrame(hist_total_demand)
    gas_by_yr.index = alldays
    hist_gas_this_month_std = gas_by_yr.loc[gas_by_yr.index.month == this_month].sum(axis=0).std() / 1000
    hist_gas_next_month_std = gas_by_yr.loc[gas_by_yr.index.month == next_month].sum(axis=0).std() / 1000
    this_y1_gas = hist_gas_demand[this_year - 1]
    hist_gas_this_month_mean_y1 = this_y1_gas.loc[this_y1_gas.index.month == this_month].sum(axis=1).mean()
    try:
        next_y1_gas = hist_gas_demand[next_year - 1]
    except:
        next_y1_gas = hist_gas_demand[next_year - 2]
    hist_gas_next_month_mean_y1 = next_y1_gas.loc[next_y1_gas.index.month == next_month].sum(axis=1).mean()
    if dt.datetime.now().hour < 18:
        cur_run = 0
        prev_run = 12
        cur_run_date = today()
        prev_run_date = today() - BDay(1)
        d1_run_date = today() - BDay(1)
    else:
        if today().weekday() < 5:
            cur_run = 12
            prev_run = 0
            cur_run_date = prev_run_date = today()
            d1_run_date = today() - BDay(1)
        else:
            cur_run = prev_run = 12
            cur_run_date = today()
            prev_run_date = today() - BDay(1)
            d1_run_date = today() - BDay(2)
    prev_forecast = pd.DataFrame()
    for i in country_list:
        _fcst = sql.read_sql((f"Select * from ECMWF_Europe_fcast where country='{i}' and run={prev_run} and "
                             f"ForecastOnDate = '{prev_run_date.strftime('%Y-%m-%d')}' order by Date"))
        _fcst['Date'] = pd.to_datetime(_fcst['Date'])
        prev_forecast[i] = _fcst[['Date', 'Temperature']].set_index('Date')
    prev_weighted_forecast = get_weighted_temperature(hist_gas_demand_mean, prev_forecast, window=0)
    prev_weighted_forecast = prev_weighted_forecast.reindex(prev_forecast.index)
    d1_forecast = pd.DataFrame()
    for i in country_list:
        temp_data = sql.read_sql(("Select * from ECMWF_Europe_fcast where Run = 0 and ForecastOnDate = '{:s}' and Country = '{:s}" + _unrecovered('EU weather 750: clipped SQL suffix')).format(dt.datetime.strftime(d1_run_date, '%Y-%m-%d'), i))
        temp_data.set_index('Date', inplace=True)
        temp_data.index = pd.to_datetime(temp_data.index)
        d1_forecast[i] = temp_data['Temperature']
    d1_weighted_forecast = get_weighted_temperature(hist_gas_demand_mean, d1_forecast, window=0)
    d1_weighted_forecast = d1_weighted_forecast.reindex(d1_forecast.index)
    prev_forecast_1w = pd.DataFrame()
    for i in country_list:
        _fcst = sql.read_sql((f"Select * from ECMWF_Europe_fcast where country='{i}' and run=0 and "
                             f"ForecastOnDate = '{(today() - dt.timedelta(days=1)).strftime('%Y-%m-%d')}' order by Date"))
        _fcst['Date'] = pd.to_datetime(_fcst['Date'])
        prev_forecast_1w[i] = _fcst[['Date', 'Temperature']].set_index('Date')
    prev_weighted_forecast_1w = get_weighted_temperature(hist_gas_demand_mean, prev_forecast_1w, window=0)
    prev_weighted_forecast_1w = prev_weighted_forecast_1w.reindex(prev_forecast_1w.index)
    cur_forecast = pd.DataFrame()
    for i in country_list:
        _fcst = sql.read_sql((f"Select * from ECMWF_Europe_fcast where country='{i}' and run={cur_run} and "
                             f"ForecastOnDate = '{cur_run_date.strftime('%Y-%m-%d')}' order by Date"))
        _fcst['Date'] = pd.to_datetime(_fcst['Date'])
        cur_forecast[i] = _fcst[['Date', 'Temperature']].set_index('Date')
    cur_weighted_forecast = get_weighted_temperature(hist_gas_demand_mean, cur_forecast, window=0)
    cur_weighted_forecast = cur_weighted_forecast.reindex(cur_forecast.index)
    if temperature['DE'].last_valid_index() != temperature['GB'].last_valid_index():
        temperature.loc[temperature['DE'].last_valid_index(), 'GB'] = temperature.loc[temperature['GB'].last_valid_index(), 'GB']
        temperature.loc[temperature['GB'].last_valid_index(), 'GB'] = np.nan
    last_loc = temperature.index.get_loc(temperature.last_valid_index()) - len(temperature.index) + 1
    cur_temperature = get_weighted_temperature(gas.iloc[-56:last_loc, :], temperature.iloc[-56:last_loc, :], window=14)
    actual_temperature = ts.read_csv(f"{weather_csv_path}\\eu_temperature_live.csv", index_name='Unnamed: 0')
    yd_actual = pd.DataFrame(0, index=[today() - dt.timedelta(1)], columns=country_list)
    for k in country_list:
        yd_actual[k] = sql.read_sql((f"Select Temperature from ECMWF_Europe_fcast where Date="
                                    f"'{(today() - dt.timedelta(1)).strftime('%Y-%m-%d')}' and "
                                    f"run=12 and country='{k}' order by ForecastOnDate desc")).values[0][0]
    combined_temp = pd.concat([actual_temperature.iloc[:-2, :], yd_actual, cur_forecast,
                              temperature_normal.loc[temperature_normal.index > cur_forecast.index[-1], :]], axis=0)
    combined_temp.to_excel(convert_path_to_linux(
        "\\\\elementcapital.corp\\ECNS01\\PM\\Michel Kikano\\Joseph\\EU_Gas\\Proces" + _unrecovered('EU weather 803: clipped folder name') +
        f"EU_Full_Wx_prophet\\{today().strftime('%Y%m%d')}_EC{cur_run}.xlsx"))
    if cur_run_date.weekday() in [0, 6]:
        fri_forecast = pd.DataFrame()
        fri_run_date = cur_run_date + relativedelta(weekday=FR(-1))
        for i in country_list:
            temp_data = sql.read_sql(("Select * from ECMWF_Europe_fcast where Run = 0 and ForecastOnDate = '{:s}' and "
                                      "Country = '{:s}' order by Date").format(dt.datetime.strftime(fri_run_date, '%Y-%m-%d'), i))
            temp_data.set_index('Date', inplace=True)
            temp_data.index = pd.to_datetime(temp_data.index)
            fri_forecast[i] = temp_data['Temperature']
        fri_weighted_forecast = get_weighted_temperature(hist_gas_demand_mean, fri_forecast, window=0)
        fri_weighted_forecast = fri_weighted_forecast.reindex(fri_forecast.index)
        output_df = pd.DataFrame(np.nan, index=alldays, columns=['current temperature', 'average temperature', 'current forecast', 'Last Friday EC00 ENS'])
        output_df['current temperature'] = cur_temperature
        output_df['average temperature'] = temperature_total_normal
        output_df['current forecast'] = cur_weighted_forecast
        output_df['Last Friday EC00 ENS'] = fri_weighted_forecast
        output_df['previous forecast'] = prev_weighted_forecast
        output_df['D-1 forecast (run00)'] = d1_weighted_forecast
        output_df = output_df.iloc[28:-63, :]
        output_df.to_csv(convert_path_to_linux(f"{weather_csv_path}\\eu_forecast\\eu_temperature_forecast_" + _unrecovered('EU weather 834: clipped date-formatted CSV suffix')))
        output_df.to_excel(convert_path_to_linux(f"{weather_csv_path}\\eu_temperature_forecast_latest.xlsx"))
        chart1 = plotly_chart(output_df[['current temperature', 'average temperature', 'current forecast', 'Last Friday EC00 ENS']],
                              title='Europe temperature forecast - gas demand weighted',
                              file_path=f"{weather_html_folder}\\links\\eu_temperature_forecast.html", y_axis_title='Temperature', x_axis_title='Date',
                              format_dict={
                                  'current temperature': {'mode': 'lines', 'width': 1, 'color': 'purple'},
                                  'average temperature': {'mode': 'lines', 'width': 1, 'color': 'orange'},
                                  'current forecast': {'mode': 'lines', 'width': 2, 'color': 'black'},
                                  'Last Friday EC00 ENS': {'mode': 'lines', 'width': 2, 'color': 'red', 'dash': 'dash'},
                              })
    else:
        output_df = pd.DataFrame(np.nan, index=alldays, columns=['current temperature', 'average temperature', 'current forecast', 'previous forecast', 'D-1 forecast (run00)'])
        output_df['current temperature'] = cur_temperature
        output_df['average temperature'] = temperature_total_normal
        output_df['current forecast'] = cur_weighted_forecast
        output_df['previous forecast'] = prev_weighted_forecast
        output_df['D-1 forecast (run00)'] = d1_weighted_forecast
        output_df = output_df.iloc[28:-63, :]
        output_df.to_csv(convert_path_to_linux(f"{weather_csv_path}\\eu_forecast\\eu_temperature_forecast_" + _unrecovered('EU weather 860: clipped date-formatted CSV suffix')))
        output_df.to_excel(convert_path_to_linux(f"{weather_csv_path}\\eu_temperature_forecast_latest.xlsx"))
        chart1 = plotly_chart(output_df, title='Europe temperature forecast - gas demand weighted',
                              file_path=f"{weather_html_folder}\\links\\eu_temperature_forecast.html", y_axis_title='Temperature', x_axis_title='Date',
                              format_dict={
                                  'current temperature': {'mode': 'lines', 'width': 1, 'color': 'purple'},
                                  'average temperature': {'mode': 'lines', 'width': 1, 'color': 'orange'},
                                  'current forecast': {'mode': 'lines', 'width': 2, 'color': 'black'},
                                  'previous forecast': {'mode': 'lines', 'width': 2, 'color': 'red', 'dash': 'dash'},
                                  'D-1 forecast (run00)': {'mode': 'lines', 'width': 1, 'color': 'orange', 'dash': 'dash'},
                              })
    figs.append(chart1)


    if cur_run == 0:
        temperature_full = pd.concat([temperature.iloc[:last_loc], prev_forecast_1w.loc[temperature.index[last_loc]:cur_run_date - dt.timedelta(days=1)], cur_forecast], axis=0)
        gas_full = gas.reindex(temperature_full.index)
        cur_demand_forecast = get_demand_forecast(gas_full, temperature_full, cur_run_date)
        cur_demand_forecast.to_excel(convert_path_to_linux((f"{weather_csv_path}\\eu_ldz_forecast_latest_by" + _unrecovered('EU weather 885: clipped Excel destination/template')).format(dt.datetime.strftime(cur_run_date, '%Y%m%d'), cur_run)))
        temperature_prev = pd.concat([temperature.iloc[:last_loc], prev_forecast.loc[temperature.index[last_loc]:]], axis=0)
        gas_prev = gas.iloc[:-1].reindex(temperature_prev.index)
        prev_demand_forecast = get_demand_forecast(gas_prev, temperature_prev, cur_run_date - dt.timedelta(days=1))
        d1_demand_forecast = sql.read_sql("Select * from ECMWF_Europe_Calculate where Calculate_date = '{:s}' order by Date".format(dt.datetime.strftime(cur_run_date - dt.timedelta(days=1), '%Y-%m-%d'), i))
        if len(d1_demand_forecast) == 0:
            temperature_d1 = pd.concat([temperature.iloc[:last_loc], d1_forecast.loc[temperature.index[last_loc]:]], axis=0)
            gas_d1 = gas.iloc[:-1].reindex(temperature_d1.index)
            d1_demand_forecast = get_demand_forecast(gas_d1, temperature_d1, cur_run_date - dt.timedelta(days=1))
        else:
            d1_demand_forecast.set_index('Date', inplace=True)
            d1_demand_forecast.index = pd.to_datetime(d1_demand_forecast.index)
    else:
        temperature_full = pd.concat([temperature.iloc[:last_loc], prev_forecast_1w.loc[temperature.index[last_loc]:cur_run_date - dt.timedelta(days=1)], cur_forecast], axis=0)
        gas_full = gas.reindex(temperature_full.index)
        cur_demand_forecast = get_demand_forecast(gas_full, temperature_full)
        if prev_forecast.index[0] > temperature.index[last_loc]:
            temperature_prev = pd.concat([temperature.iloc[:last_loc], prev_forecast_1w.loc[temperature.index[last_loc]:cur_run_date - dt.timedelta(days=1)], prev_forecast], axis=0)
        else:
            temperature_prev = pd.concat([temperature.iloc[:last_loc], prev_forecast.loc[prev_forecast.index >= temperature.index[last_loc], :]], axis=0)
        gas_prev = gas.iloc[:-1].reindex(temperature_prev.index)
        prev_demand_forecast = get_demand_forecast(gas_prev, temperature_prev, cur_run_date)
        d1_demand_forecast = sql.read_sql("Select * from ECMWF_Europe_Calculate where Calculate_date = '{:s}' order by Date".format(dt.datetime.strftime(cur_run_date - dt.timedelta(days=1), '%Y-%m-%d'), i))
        if len(d1_demand_forecast) == 0:
            temperature_d1 = pd.concat([temperature.iloc[:last_loc], d1_forecast.loc[temperature.index[last_loc]:]], axis=0)
            gas_d1 = gas.iloc[:-1].reindex(temperature_d1.index)
            d1_demand_forecast = get_demand_forecast(gas_d1, temperature_d1, cur_run_date - dt.timedelta(days=1))
        else:
            d1_demand_forecast.set_index('Date', inplace=True)
            d1_demand_forecast.index = pd.to_datetime(d1_demand_forecast.index)
    ldz_df = pd.DataFrame(np.nan, index=alldays, columns=['current LDZ', 'average LDZ', 'current forecast', 'previous forecast', 'D-1 forecast (run00)'])
    ldz_df['current LDZ'] = gas.iloc[-28:, :].sum(axis=1)
    ldz_df['average LDZ'] = gas_total_normal
    ldz_df['current forecast'] = cur_demand_forecast['total_demand']
    ldz_df['previous forecast'] = prev_demand_forecast['total_demand']
    ldz_df['D-1 forecast (run00)'] = d1_demand_forecast['total_demand']
    ldz_df = ldz_df.iloc[28:-63, :]
    ldz_df.to_csv(convert_path_to_linux(f"{weather_csv_path}\\eu_forecast\\eu_ldz_forecast_" + _unrecovered('EU weather 949: clipped date-formatted CSV suffix')))
    ldz_df.to_excel(convert_path_to_linux(f"{weather_csv_path}\\eu_ldz_forecast_latest.xlsx"))
    chart2 = plotly_chart(ldz_df, title='Europe LDZ forecast', file_path=f"{weather_html_folder}\\links\\eu_ldz_forecast.html", y_axis_title='mcm/d', x_axis_title='Date',
                          format_dict={
                              'current LDZ': {'mode': 'lines', 'width': 1, 'color': 'purple'},
                              'average LDZ': {'mode': 'lines', 'width': 1, 'color': 'orange'},
                              'current forecast': {'mode': 'lines', 'width': 2, 'color': 'black'},
                              'previous forecast': {'mode': 'lines', 'width': 2, 'color': 'red', 'dash': 'dash'},
                              'D-1 forecast (run00)': {'mode': 'lines', 'width': 1, 'color': 'orange', 'dash': 'dash'},
                          })
    figs.append(chart2)
    date_list = [cur_run_date - dt.timedelta(days=x) for x in range(1, 6)]
    date_strs = "','".join([dt.datetime.strftime(x, '%Y-%m-%d') for x in date_list])
    temp_data = sql.read_sql(f"Select * from ECMWF_Europe_fcast where ForecastOnDate in ('{date_strs}') order by ForecastOnDate," + _unrecovered('EU weather 970: clipped SQL ordering suffix'))
    temp_data['ForecastOnDate'] = pd.to_datetime(temp_data['ForecastOnDate'])
    temp_data['Date'] = pd.to_datetime(temp_data['Date'])
    agg_fcast_temp = pd.DataFrame(np.nan, index=cur_weighted_forecast.index, columns=date_list)
    gas_fcast_temp = pd.DataFrame(np.nan, index=cur_weighted_forecast.index, columns=date_list)
    for j in date_list:
        fcast_on_date = pd.DataFrame()
        fcast_on_date_ = pd.DataFrame()
        for i in country_list:
            country_fcast = temp_data.loc[(temp_data['Country'] == i) & (temp_data['ForecastOnDate'] == j) & (temp_data['Run'] == cur_run), ['Date', 'Temperature']]
            country_fcast.set_index('Date', inplace=True)
            country_fcast = country_fcast['Temperature']
            fcast_on_date_[i] = country_fcast.copy()
            country_fcast = pd.concat([country_fcast, temperature_normal.loc[temperature_normal.index > country_fcast.index[-1], i]])
            fcast_on_date[i] = country_fcast
        fcast_on_date_weighted = get_weighted_temperature(hist_gas_demand_mean, fcast_on_date, window=0)
        agg_fcast_temp[j] = fcast_on_date_weighted.reindex(cur_weighted_forecast.index)
        temperature_full = pd.concat([temperature.loc[temperature.index < fcast_on_date_.index[0], :], fcast_on_date_], axis=0)
        gas_full = gas.reindex(temperature_full.index)
        cur_demand_forecast_hist = get_demand_forecast(gas_full, temperature_full, j)
        cur_demand_forecast_total = pd.concat([cur_demand_forecast_hist['total_demand'], gas_normal.loc[gas_normal.index > cur_demand_forecast_hist.index[-1], :].sum(axis=1)])
        gas_fcast_temp[j] = cur_demand_forecast_total.reindex(cur_demand_forecast.index)
    if cur_run == 0:
        prev_forecast_with_norm = pd.DataFrame()
        prev_forecast_with_norm_gas = pd.concat([prev_demand_forecast['total_demand'], gas_normal.loc[gas_normal.index > prev_demand_forecast.index[-1], :].sum(axis=1)])
        for i in country_list:
            prev_forecast_with_norm[i] = pd.concat([prev_forecast[i], temperature_normal.loc[temperature_normal.index > prev_forecast.index[-1], i]], axis=0)
    else:
        prev_forecast_with_norm = prev_forecast
        prev_forecast_with_norm_gas = prev_demand_forecast['total_demand']
    fcast_on_date_weighted = get_weighted_temperature(hist_gas_demand_mean, prev_forecast_with_norm, window=0)
    prev_weighted_forecast_with_normal = fcast_on_date_weighted.reindex(cur_weighted_forecast.index)
    prev_forecast_with_norm_gas = prev_forecast_with_norm_gas.reindex(cur_demand_forecast.index)
    table_temperature = pd.DataFrame(0, index=['12H', '24H', '3D', '5D'], columns=['NW Europe'])
    table_temperature.loc['12H', 'NW Europe'] = (cur_weighted_forecast - prev_weighted_forecast_with_normal).sum()
    table_temperature.loc['24H', 'NW Europe'] = (cur_weighted_forecast - agg_fcast_temp.iloc[:, 0]).sum()
    table_temperature.loc['3D', 'NW Europe'] = (cur_weighted_forecast - agg_fcast_temp.iloc[:, 2]).sum()
    table_temperature.loc['5D', 'NW Europe'] = (cur_weighted_forecast - agg_fcast_temp.iloc[:, 4]).sum()
    table_temperature.index.name = 'Change'
    table_temperature.reset_index(inplace=True)
    table1 = table.html_format(df=table_temperature, format_column={'Change': {'width': '100px', 'text-align': 'center'}, 'NW Europe': {'width': '100px', 'text-align': 'center'}})
    table_gas = pd.DataFrame(0, index=['12H', '24H', '3D', '5D'], columns=['NW Europe'])
    table_gas.loc['12H', 'NW Europe'] = (cur_demand_forecast['total_demand'] - prev_forecast_with_norm_gas).sum()
    table_gas.loc['24H', 'NW Europe'] = (cur_demand_forecast['total_demand'] - gas_fcast_temp.iloc[:, 0]).sum()
    table_gas.loc['3D', 'NW Europe'] = (cur_demand_forecast['total_demand'] - gas_fcast_temp.iloc[:, 2]).sum()
    table_gas.loc['5D', 'NW Europe'] = (cur_demand_forecast['total_demand'] - gas_fcast_temp.iloc[:, 4]).sum()
    table_gas.index.name = 'Change'
    table_gas.reset_index(inplace=True)
    table2 = table.html_format(df=table_gas, format_column={'Change': {'width': '100px', 'text-align': 'center'}, 'NW Europe': {'width': '100px', 'text-align': 'center'}})
    tbs.append('Temperature forecast: (Unit: degree celsius)')
    tbs.append(table1)
    tbs.append('<br>')
    tbs.append('Gas demand - LDZ forecast: ')
    tbs.append(table2)
    tbs.append('<br>')
    tbs.append(chart1)
    tbs.append(chart2)
    tbs.append('<br>')


    if cur_run == 0:
        figs1 = []
        this_month_temperature, this_month_gas = monthly_temperature_gas_demand(
            cur_forecast, cur_weighted_forecast, cur_temperature, hist_gas_demand_mean, this_year, this_month,
            hist_tempe_this_month_mean, hist_tempe_this_month_std, hist_gas_this_month_mean, hist_gas_this_month_std, temperature, gas)
        this_month_temperature['Normal +1 sd'] = this_month_temperature['Normal'] + this_month_temperature['std']
        this_month_temperature['Normal -1 sd'] = this_month_temperature['Normal'] - this_month_temperature['std']
        this_month_temperature['Y-1'] = hist_tempe_this_month_mean_y1
        this_month_temperature_todb = this_month_temperature.copy()
        this_month_temperature.drop(['std'], axis=1, inplace=True)
        chart3 = plotly_chart(this_month_temperature, title='Europe current month temperature',
                              file_path=f"{weather_html_folder}\\links\\eu_current_month_temperature.html", y_axis_title='Temperature', x_axis_title='Date',
                              format_dict={
                                  'Temperature': {'mode': 'lines+markers', 'width': 2, 'color': 'blue'},
                                  'Normal': {'mode': 'lines', 'width': 1, 'color': 'black'},
                                  'Normal +1 sd': {'mode': 'lines', 'width': 1, 'color': 'grey', 'dash': _unrecovered('EU weather 1084: clipped normal dash style')},
                                  'Normal -1 sd': {'mode': 'lines', 'width': 1, 'color': 'grey', 'dash': _unrecovered('EU weather 1085: clipped normal dash style')},
                                  'Y-1': {'mode': 'lines', 'width': 1, 'color': 'green'},
                              })
        figs1.append(chart3)
        this_month_gas['Normal +1 sd'] = this_month_gas['Normal'] + this_month_gas['std']
        this_month_gas['Normal -1 sd'] = this_month_gas['Normal'] - this_month_gas['std']
        this_month_gas['Y-1'] = hist_gas_this_month_mean_y1 * len(hist_gas_this_month_mean) / 1000
        this_month_gas_todb = this_month_gas.copy()
        this_month_gas.drop(['std'], axis=1, inplace=True)
        chart4 = plotly_chart(this_month_gas, title='Europe current month LDZ',
                              file_path=f"{weather_html_folder}\\links\\eu_current_month_ldz.html", y_axis_title='bcm/m', x_axis_title='Date',
                              format_dict={
                                  'LDZ': {'mode': 'lines+markers', 'width': 2, 'color': 'blue'},
                                  'Normal': {'mode': 'lines', 'width': 1, 'color': 'black'},
                                  'Normal +1 sd': {'mode': 'lines', 'width': 1, 'color': 'grey', 'dash': _unrecovered('EU weather 1101: clipped normal dash style')},
                                  'Normal -1 sd': {'mode': 'lines', 'width': 1, 'color': 'grey', 'dash': _unrecovered('EU weather 1102: clipped normal dash style')},
                                  'Y-1': {'mode': 'lines', 'width': 1, 'color': 'green'},
                              })
        figs1.append(chart4)
        this_month_temperature_todb.drop(['Normal +1 sd', 'Normal -1 sd'], axis=1, inplace=True)
        this_month_temperature_todb.columns = ['Forecast', 'Normal', 'Stddev', 'LastYear']
        this_month_temperature_todb['Type'] = 'Temperature'
        this_month_temperature_todb['FcastMonth'] = dt.datetime(this_year, this_month, 1)
        this_month_temperature_todb = this_month_temperature_todb.loc[:this_month_temperature_todb['Forecast'].last_valid_index(), :]
        this_month_gas_todb.drop(['Normal +1 sd', 'Normal -1 sd'], axis=1, inplace=True)
        this_month_gas_todb.columns = ['Forecast', 'Normal', 'Stddev', 'LastYear']
        this_month_gas_todb['Type'] = 'LDZ'
        this_month_gas_todb['FcastMonth'] = dt.datetime(this_year, this_month, 1)
        this_month_gas_todb = this_month_gas_todb.loc[:this_month_gas_todb['Forecast'].last_valid_index(), :]
        todb_df = pd.concat([this_month_temperature_todb, this_month_gas_todb], axis=0)
        todb_df = todb_df.reset_index()
        todb_df.rename(columns={'index': 'Date'}, inplace=True)
        sql_str = "Delete from ECMWF_Europe_Balance where FcastMonth = '{:s}' and Date >= '{:s}'".format(
            dt.datetime.strftime(dt.datetime(this_year, this_month, 1), '%Y-%m-%d'), dt.datetime.strftime(todb_df['Date'].iloc[0], '%Y-%m-%d'))
        sql.sql_execute(sql_str)
        sql.to_sql(todb_df, 'ECMWF_Europe_Balance', index=False)
        if output_df.index[-2].month == next_month:
            next_month_temperature, next_month_gas = monthly_temperature_gas_demand(
                cur_forecast, cur_weighted_forecast, cur_temperature, hist_gas_demand_mean, next_year, next_month,
                hist_tempe_next_month_mean, hist_tempe_next_month_std, hist_gas_next_month_mean, hist_gas_next_month_std, temperature, gas)
            next_month_temperature['Normal +1 sd'] = next_month_temperature['Normal'] + next_month_temperature['std']
            next_month_temperature['Normal -1 sd'] = next_month_temperature['Normal'] - next_month_temperature['std']
            next_month_temperature['Y-1'] = hist_tempe_next_month_mean_y1
            next_month_temperature_todb = next_month_temperature.copy()
            next_month_temperature.drop(['std'], axis=1, inplace=True)
            chart5 = plotly_chart(next_month_temperature, title='Europe next month temperature',
                                  file_path=f"{weather_html_folder}\\links\\eu_next_month_temperature.html", y_axis_title='Temperature', x_axis_title='Date',
                                  format_dict={
                                      'Temperature': {'mode': 'lines+markers', 'width': 2, 'color': 'blue'},
                                      'Normal': {'mode': 'lines', 'width': 1, 'color': 'black'},
                                      'Normal +1 sd': {'mode': 'lines', 'width': 1, 'color': 'grey', 'dash': _unrecovered('EU weather 1150: clipped normal dash style')},
                                      'Normal -1 sd': {'mode': 'lines', 'width': 1, 'color': 'grey', 'dash': _unrecovered('EU weather 1151: clipped normal dash style')},
                                      'Y-1': {'mode': 'lines', 'width': 1, 'color': 'green'},
                                  })
            figs1.append(chart5)
            next_month_gas['Normal +1 sd'] = next_month_gas['Normal'] + next_month_gas['std']
            next_month_gas['Normal -1 sd'] = next_month_gas['Normal'] - next_month_gas['std']
            next_month_gas['Y-1'] = hist_gas_next_month_mean_y1 * len(hist_gas_next_month_mean) / 1000
            next_month_gas_todb = next_month_gas.copy()
            next_month_gas.drop(['std'], axis=1, inplace=True)
            chart6 = plotly_chart(next_month_gas, title='Europe next month LDZ',
                                  file_path=f"{weather_html_folder}\\links\\eu_next_month_ldz.html", y_axis_title='bcm/m', x_axis_title='Date',
                                  format_dict={
                                      'LDZ': {'mode': 'lines+markers', 'width': 2, 'color': 'blue'},
                                      'Normal': {'mode': 'lines', 'width': 1, 'color': 'black'},
                                      'Normal +1 sd': {'mode': 'lines', 'width': 1, 'color': 'grey', 'dash': _unrecovered('EU weather 1166: clipped normal dash style')},
                                      'Normal -1 sd': {'mode': 'lines', 'width': 1, 'color': 'grey', 'dash': _unrecovered('EU weather 1167: clipped normal dash style')},
                                      'Y-1': {'mode': 'lines', 'width': 1, 'color': 'green'},
                                  })
            figs1.append(chart6)
            next_month_temperature_todb.drop(['Normal +1 sd', 'Normal -1 sd'], axis=1, inplace=True)
            next_month_temperature_todb.columns = ['Forecast', 'Normal', 'Stddev', 'LastYear']
            next_month_temperature_todb['Type'] = 'Temperature'
            next_month_temperature_todb['FcastMonth'] = dt.datetime(next_year, next_month, 1)
            next_month_temperature_todb = next_month_temperature_todb.loc[:next_month_temperature_todb['Forecast'].last_valid_index(), :]
            next_month_gas_todb.drop(['Normal +1 sd', 'Normal -1 sd'], axis=1, inplace=True)
            next_month_gas_todb.columns = ['Forecast', 'Normal', 'Stddev', 'LastYear']
            next_month_gas_todb['Type'] = 'LDZ'
            next_month_gas_todb['FcastMonth'] = dt.datetime(next_year, next_month, 1)
            next_month_gas_todb = next_month_gas_todb.loc[:next_month_gas_todb['Forecast'].last_valid_index(), :]
            todb_df = pd.concat([next_month_temperature_todb, next_month_gas_todb], axis=0)
            todb_df = todb_df.reset_index()
            todb_df.rename(columns={'index': 'Date'}, inplace=True)
            sql_str = "Delete from ECMWF_Europe_Balance where FcastMonth = '{:s}' and Date >= '{:s}'".format(
                dt.datetime.strftime(dt.datetime(next_year, next_month, 1), '%Y-%m-%d'), dt.datetime.strftime(todb_df['Date'].iloc[0], '%Y-%m-%d'))
            sql.sql_execute(sql_str)
            sql.to_sql(todb_df, 'ECMWF_Europe_Balance', index=False)
        table.figures_to_html(figs1, filename=f"{weather_html_folder}\\links\\eu_weather_balance_forecast_c" + _unrecovered('EU weather 1192: clipped HTML suffix'))
    pdf_path = f"{weather_pdf_folder}\\eu_forecast.pdf"
    try:
        table.figures_to_pdf(figs1, pdf_path=pdf_path, landscape=True, width=600, height=600)
    except:
        f2 = open(convert_path_to_linux(f"{weather_html_folder}\\links\\eu_weather_balance_forecast_charts." + _unrecovered('EU weather 1200: clipped fallback read suffix/arguments')))
        f1 = open(convert_path_to_linux(f"{weather_html_folder}\\links\\eu_weather_forecast_charts.html"), _unrecovered('EU weather 1201: clipped fallback write mode'))
        f1.write(f2)
        f1.close()
    tbs.append(u'<a href="{}\\links\\eu_weather_forecast_charts.html">Link to demand forecast evolution</a>'.format(weather_html_folder))
    tbs.append('<br>')
    tbs.append('<br>')
    sql_str = ("Select Date, Forecast, LastYear, Normal, FcastMonth from ECMWF_Europe_Balance where "
               "FcastMonth = '{:s}' and Type = 'Temperature' order by Date desc").format(dt.datetime.strftime(dt.datetime(this_year, this_month, 1), '%Y-%m-%d'))
    this_month_tempe_forecast = sql.read_sql(sql_str)
    this_month_tempe_forecast.columns = ['AS_OF_DATE', 'Fcast', 'Last Year', 'Normal', 'FCAST_MONTH']
    try:
        this_month_tempe_forecast.to_csv(convert_path_to_linux(f'{weather_csv_path}\\this_month_temperature' + _unrecovered('EU weather 1217: clipped CSV suffix')))
    except:
        pass
    this_month_tempe_forecast_html = table.html_format(df=this_month_tempe_forecast, background_color='lightyellow', format_column={'AS_OF_DATE': {'width': '100px', 'text-align': 'center'},
             'Fcast': {'width': '80px', 'text-align': 'center'},
             'Last Year': {'width': '80px', 'text-align': 'center'},
             'Normal': {'width': '80px', 'text-align': 'center'},
             'FCAST_MONTH': {'width': '100px', 'text-align': 'center'}})
    tbs.append('Current Month - Temperature forecast')
    tbs.append(this_month_tempe_forecast_html)
    tbs.append('<br>')
    sql_str = ("Select Date, Forecast, LastYear, Normal, FcastMonth from ECMWF_Europe_Balance where "
               "FcastMonth = '{:s}' and Type = 'LDZ' order by Date desc").format(dt.datetime.strftime(dt.datetime(this_year, this_month, 1), '%Y-%m-%d'))
    this_month_gas_forecast = sql.read_sql(sql_str)
    this_month_gas_forecast.columns = ['AS_OF_DATE', 'Fcast', 'Last Year', 'Normal', 'FCAST_MONTH']
    try:
        this_month_gas_forecast.to_csv(convert_path_to_linux(f'{weather_csv_path}\\this_month_LDZ' + _unrecovered('EU weather 1241: clipped CSV suffix')))
    except:
        pass
    this_month_gas_forecast_html = table.html_format(df=this_month_gas_forecast, background_color='lightyellow', format_column={'AS_OF_DATE': {'width': '100px', 'text-align': 'center'},
             'Fcast': {'width': '80px', 'text-align': 'center'},
             'Last Year': {'width': '80px', 'text-align': 'center'},
             'Normal': {'width': '80px', 'text-align': 'center'},
             'FCAST_MONTH': {'width': '100px', 'text-align': 'center'}})
    tbs.append('Current Month - LDZ forecast')
    tbs.append(this_month_gas_forecast_html)
    tbs.append('<br>')
    sql_str = ("Select Date, Forecast, LastYear, Normal, FcastMonth from ECMWF_Europe_Balance where "
               "FcastMonth = '{:s}' and Type = 'Temperature' order by Date desc").format(dt.datetime.strftime(dt.datetime(next_year, next_month, 1), '%Y-%m-%d'))
    next_month_tempe_forecast = sql.read_sql(sql_str)
    show_next_month = False
    if len(next_month_tempe_forecast) > 0:
        show_next_month = True
        next_month_tempe_forecast.columns = ['AS_OF_DATE', 'Fcast', 'Last Year', 'Normal', 'FCAST_MONTH']
        next_month_tempe_forecast.to_csv(convert_path_to_linux(f"{weather_csv_path}\\next_month_temperature" + _unrecovered('EU weather 1268: clipped CSV suffix')))
        next_month_tempe_forecast_html = table.html_table(next_month_tempe_forecast, background_color=_unrecovered('EU weather 1269: clipped light-prefixed color'), table_format_column={'AS_OF_DATE': {'width': '100px', 'text-align': 'center'},
             'Fcast': {'width': '80px', 'text-align': 'center'},
             'Last Year': {'width': '80px', 'text-align': 'center'},
             'Normal': {'width': '80px', 'text-align': 'center'},
             'FCAST_MONTH': {'width': '100px', 'text-align': 'center'}})
        tbs.append('Next Month - Temperature forecast')
        tbs.append(next_month_tempe_forecast_html)
        tbs.append('<br>')
        sql_str = ("Select Date, Forecast, LastYear, Normal, FcastMonth from ECMWF_Europe_Balance where "
                   "FcastMonth = '{:s}' and Type = 'LDZ' order by Date desc").format(dt.datetime.strftime(dt.datetime(next_year, next_month, 1), '%Y-%m-%d'))
        next_month_gas_forecast = sql.read_sql(sql_str)
        next_month_gas_forecast.columns = ['AS_OF_DATE', 'Fcast', 'Last Year', 'Normal', 'FCAST_MONTH']
        next_month_gas_forecast.to_csv(convert_path_to_linux(f'{weather_csv_path}\\next_month_LDZ_forecast.' + _unrecovered('EU weather 1286: clipped CSV suffix')))
        next_month_gas_forecast_html = table.html_table(next_month_gas_forecast, background_color='lightgreen', table_format_column={'AS_OF_DATE': {'width': '100px', 'text-align': 'center'},
             'Fcast': {'width': '80px', 'text-align': 'center'},
             'Last Year': {'width': '80px', 'text-align': 'center'},
             'Normal': {'width': '80px', 'text-align': 'center'},
             'FCAST_MONTH': {'width': '100px', 'text-align': 'center'}})
        tbs.append('Next Month - LDZ forecast')
        tbs.append(next_month_gas_forecast_html)
        tbs.append('<br>')


    gas_total = gas.sum(axis=1)
    temperature_total = get_weighted_temperature(gas_normal, temperature, window=0)
    a_df = pd.DataFrame()
    a_df['NG_HDD'] = temperature_total
    del_loc = temperature.index.get_loc(temperature.last_valid_index()) + 1
    a_df.loc[temperature.index[del_loc]:, 'NG_HDD'] = np.nan
    a_df['10Y_NG_HDD'] = temperature_total_normal
    a_df.dropna(inplace=True)
    latest_hdd = output_df['current forecast']
    latest_hdd.dropna(inplace=True)
    latest_hdd = latest_hdd.to_frame('NG_HDD')
    latest_hdd['10Y_NG_HDD'] = temperature_total_normal
    if (latest_hdd.index[0] - a_df.index[-1]).days > 1:
        previous_hdd = output_df['D-1 forecast (run00)']
        previous_hdd.dropna(inplace=True)
        previous_hdd = previous_hdd.to_frame('NG_HDD')
        previous_hdd['10Y_NG_HDD'] = temperature_total_normal
        first_fcast_loc = previous_hdd.index.get_loc(latest_hdd.index[0])
        if previous_hdd.index[0] > a_df.index[-1]:
            last_actual_loc = 0
            hdd_fcast = pd.concat([previous_hdd[['NG_HDD', '10Y_NG_HDD']].iloc[last_actual_loc:first_fcast_loc], latest_hdd[['NG_HDD', '10Y_NG_HDD']]], axis=0)
        else:
            last_actual_loc = previous_hdd.index.get_loc(a_df.index[-1])
            hdd_fcast = pd.concat([previous_hdd[['NG_HDD', '10Y_NG_HDD']].iloc[last_actual_loc + 1:first_fcast_loc], latest_hdd[['NG_HDD', '10Y_NG_HDD']]], axis=0)
        hdd_fcast = hdd_fcast[(hdd_fcast.index.month >= 10) | (hdd_fcast.index.month < 7)]
        if len(hdd_fcast) > 0:
            a_df = a_df.append(hdd_fcast)
    else:
        a_df = a_df.append(latest_hdd)
    if today().month in [10, 11, 12, 1, 2, 3, 4] or (today().month == 9 and today().day > 25):
        winter = winter_hdd(a_df)
        winter_table = witer_month_table(winter)
    else:
        winter = summer_hdd(a_df)
        winter_table = summer_month_table(winter)
    winter_table_html = table.html_table(winter_table, precision=1, format_column={
        winter_table.columns[0]: {'width': '80px', 'text-align': 'center'},
        winter_table.columns[1]: {'width': '80px', 'text-align': 'center'},
        winter_table.columns[2]: {'width': '80px', 'text-align': 'center'},
        winter_table.columns[3]: {'width': '80px', 'text-align': 'center'},
        winter_table.columns[4]: {'width': '80px', 'text-align': 'center'},
        winter_table.columns[5]: {'width': '80px', 'text-align': 'center'},
        winter_table.columns[6]: {'width': '80px', 'text-align': 'center'},
    })
    demand_df = pd.DataFrame()
    demand_df['NG_HDD'] = gas_total
    demand_df['10Y_NG_HDD'] = gas_total_normal
    demand_df.dropna(inplace=True)
    latest_demand = ldz_df['current forecast']
    latest_demand.dropna(inplace=True)
    latest_demand = latest_demand.to_frame('NG_HDD')
    latest_demand['10Y_NG_HDD'] = gas_total_normal
    if len(latest_demand) > 0:
        if demand_df.index[-1] >= latest_demand.index[0]:
            demand_df = pd.concat([demand_df.iloc[:-1, :], latest_demand], axis=0)
        else:
            demand_df = demand_df.append(latest_demand)
    if today().month in [10, 11, 12, 1, 2, 3, 4] or (today().month == 9 and today().day > 25):
        winter_demand = winter_hdd(demand_df)
        winter_demand_table = witer_month_table(winter_demand)
    else:
        winter_demand = summer_hdd(demand_df)
        winter_demand_table = summer_month_table(winter_demand)
    winter_demand_table_html = table.html_format(winter_demand_table, precision=0, format_column={
        winter_demand_table.columns[0]: {'width': '80px', 'text-align': 'center'},
        winter_demand_table.columns[1]: {'width': '80px', 'text-align': 'center'},
        winter_demand_table.columns[2]: {'width': '80px', 'text-align': 'center'},
        winter_demand_table.columns[3]: {'width': '80px', 'text-align': 'center'},
        winter_demand_table.columns[4]: {'width': '80px', 'text-align': 'center'},
        winter_demand_table.columns[5]: {'width': '80px', 'text-align': 'center'},
        winter_demand_table.columns[6]: {'width': '80px', 'text-align': 'center'},
    })
    tbs.append('LDS vs Normal - current and next month include LDS forecasts: ')
    tbs.append(winter_demand_table_html)
    tbs.append('<br>')
    if today().month in [10, 11, 12, 1, 2, 3, 4] or (today().month == 9 and today().day > 25):
        tbs.append(cumulative_winter_hdd_chart(winter_demand, latest_demand, title='Cumulative winter LDZ vs normal'))
    else:
        tbs.append(cumulative_summer_hdd_chart(winter_demand, latest_demand, title='Cumulative summer LDZ vs normal'))
    table.figures_to_html(tbs, filename=f"{weather_html_folder}\\eu_weather_forecast_tables.html")
    send_email(send_to, subject="Weather - EU", body=[
        'Latest update from source is {:s}'.format(dt.datetime.strftime(gas.index[-1], '%Y-%m-%d')),
        tbs, '<br><br>This is automated email sent at {:s}. <br><br>'.format(time.strftime('%Y-%m-%d %H:%M'))],
        html_path=f"{weather_html_folder}\\eu_weather_forecast_tables.html", attachments=pdf_path)


def monthly_temperature_gas_demand(lastest_fcast_country, lastest_fcast, real_data, w, y, m, avg, stddev, avg_gas, stddev_gas, temperature, gas):
    fdom = dt.datetime(y, m, 1)
    data = sql.read_sql(("Select distinct(ForecastOnDate) from ECMWF_Europe_fcast where Date >= '{:s}' and Country='DE' orde" + _unrecovered('EU weather 1416: clipped SQL ordering suffix')).format(dt.datetime.strftime(fdom, '%Y-%m-%d')))
    data_list = pd.to_datetime(data['ForecastOnDate']).to_list()
    data_list.insert(0, data_list[0] - dt.timedelta(days=1))
    data_list.append(lastest_fcast.index[0])
    dts = pd.date_range(start=fdom, end=fdom + relativedelta(day=31))
    out_data = {}
    out_data_gas = {}
    yestday_fcast = pd.DataFrame()
    yestday_europe_fcast = pd.DataFrame()
    for d in data_list:
        print(d)
        europe_fcast = pd.DataFrame(np.nan, index=pd.date_range(start=d, end=d + dt.timedelta(days=14)), columns=country_list)
        if d < lastest_fcast.index[0]:
            for i in country_list:
                hist_fcast = sql.read_sql(("Select * from ECMWF_Europe_fcast where ForecastOnDate = '{:s}' and Run=0 and Country='" + _unrecovered('EU weather 1437: clipped country SQL suffix')).format(dt.datetime.strftime(d, '%Y-%m-%d'), i))
                hist_fcast.set_index('Date', inplace=True)
                hist_fcast.index = pd.to_datetime(hist_fcast.index)
                europe_fcast[i] = hist_fcast['Temperature']
            weighted_fcast = get_weighted_temperature(w, europe_fcast, window=0).loc[europe_fcast.index]
        else:
            weighted_fcast = lastest_fcast
            europe_fcast = lastest_fcast_country
        cur_demand_forecast = sql.read_sql("Select * from ECMWF_Europe_Calculate where Calculate_date = '{:s}' order by Date".format(dt.datetime.strftime(d, '%Y-%m-%d'), i))
        if len(cur_demand_forecast) == 0:
            gas_temp = gas.copy()
            gas_temp[d + dt.timedelta(days=1):] = np.nan
            if data_list.index(d) == 0:
                temperature_full = pd.concat([temperature.loc[:d - dt.timedelta(days=1), :], europe_fcast], axis=0)
            else:
                temperature_full = pd.concat([temperature.loc[:d - dt.timedelta(days=2), :], yestday_europe_fcast.loc[d - dt.timedelta(days=1):d - dt.timedelta(days=1)], europe_fcast], axis=0)
            if europe_fcast.isna().values.all():
                cur_demand_forecast = pd.Series(np.nan, index=europe_fcast.index)
                weighted_fcast = pd.Series(np.nan, index=weighted_fcast.index)
            else:
                temperature_full.fillna(method='ffill', inplace=True)
                gas_full = gas_temp.reindex(temperature_full.index)
                cur_demand_forecast = get_demand_forecast(gas_full, temperature_full, forecast_day=d)
                cur_demand_forecast_todb = cur_demand_forecast.copy()
                cur_demand_forecast_todb.index.name = 'Date'
                cur_demand_forecast_todb.reset_index(inplace=True)
                cur_demand_forecast_todb['Calculate_date'] = d
                sql.to_sql(cur_demand_forecast_todb, 'ECMWF_Europe_Calculate', index=False)
                cur_demand_forecast = cur_demand_forecast['total_demand']
        else:
            cur_demand_forecast.set_index('Date', inplace=True)
            cur_demand_forecast.index = pd.to_datetime(cur_demand_forecast.index)
            cur_demand_forecast = cur_demand_forecast['total_demand']
        monthly_data = pd.Series(np.nan, index=dts)
        monthly_gas = pd.Series(np.nan, index=dts)
        if d <= fdom:
            monthly_data[monthly_data.index <= weighted_fcast.index[-1]] = weighted_fcast[weighted_fcast.index >= dts[0]]
            monthly_data[monthly_data.index > weighted_fcast.index[-1]] = avg[monthly_data.index > weighted_fcast.index[-1]]
            monthly_gas[monthly_gas.index <= cur_demand_forecast.index[-1]] = cur_demand_forecast[cur_demand_forecast.index >= dts[0]]
            monthly_gas[monthly_gas.index > cur_demand_forecast.index[-1]] = avg_gas[monthly_gas.index > cur_demand_forecast.index[-1]]
        elif weighted_fcast.index[-1] >= fdom + relativedelta(day=31):
            monthly_data[monthly_data.index >= weighted_fcast.index[0]] = weighted_fcast[weighted_fcast.index <= dts[-1]]
            try:
                monthly_data[d - dt.timedelta(days=1)] = yestday_fcast.iloc[0]
            except:
                monthly_data[d - dt.timedelta(days=1)] = real_data[d - dt.timedelta(days=1)]
            monthly_data[:d - dt.timedelta(days=2)] = real_data[monthly_data.index[0]:d - dt.timedelta(days=2)]
            monthly_gas[monthly_gas.index >= cur_demand_forecast.index[0]] = cur_demand_forecast[cur_demand_forecast.index <= dts[-1]]
            monthly_gas[:d] = gas[monthly_gas.index[0]:d].sum(axis=1)
        else:
            monthly_data[(monthly_data.index >= weighted_fcast.index[0]) & (monthly_data.index <= weighted_fcast.index[-1])] = weighted_fcast
            monthly_data[weighted_fcast.index[-1] + dt.timedelta(days=1):] = avg[weighted_fcast.index[-1] + dt.timedelta(days=1):]
            try:
                monthly_data[d - dt.timedelta(days=1)] = yestday_fcast.iloc[0]
            except:
                monthly_data[d - dt.timedelta(days=1)] = real_data[d - dt.timedelta(days=1)]
            monthly_data[:d - dt.timedelta(days=2)] = real_data[monthly_data.index[0]:d - dt.timedelta(days=2)]
            monthly_gas[(monthly_gas.index >= cur_demand_forecast.index[0]) & (monthly_gas.index <= cur_demand_forecast.index[-1])] = cur_demand_forecast
            monthly_gas[cur_demand_forecast.index[-1] + dt.timedelta(days=1):] = avg_gas[cur_demand_forecast.index[-1] + dt.timedelta(days=1):]
            monthly_gas[:d] = gas[monthly_gas.index[0]:d].sum(axis=1)
        out_data[d] = monthly_data.mean()
        out_data_gas[d] = monthly_gas.sum() / 1000
        yestday_fcast = weighted_fcast.copy()
        yestday_europe_fcast = europe_fcast.copy()
    out_df = pd.DataFrame.from_dict(out_data, orient='index')
    out_df.columns = ['Temperature']
    if d + relativedelta(day=31) < dts[0]:
        out_df = pd.concat([out_df, pd.DataFrame(np.nan, index=pd.date_range(start=d + dt.timedelta(days=1), end=d + relativedelta(day=31)), columns=['Temperature']),
                            pd.DataFrame(np.nan, index=dts, columns=['Temperature'])], axis=0)
    else:
        out_df = pd.concat([out_df, pd.DataFrame(np.nan, index=dts[dts.get_loc(d) + 1:], columns=['Temperature'])], axis=0)
    out_df['Normal'] = avg.mean()
    out_df['std'] = stddev
    out_gas = pd.DataFrame.from_dict(out_data_gas, orient='index')
    out_gas.columns = ['LDZ']
    if d + relativedelta(day=31) < dts[0]:
        out_gas = pd.concat([out_gas, pd.DataFrame(np.nan, index=pd.date_range(start=d + dt.timedelta(days=1), end=d + relativedelta(day=31)), columns=['LDZ']),
                             pd.DataFrame(np.nan, index=dts, columns=['LDZ'])], axis=0)
    else:
        out_gas = pd.concat([out_gas, pd.DataFrame(np.nan, index=dts[dts.get_loc(d) + 1:], columns=['LDZ'])], axis=0)
    out_gas['Normal'] = avg_gas.sum() / 1000
    out_gas['std'] = stddev_gas
    return out_df, out_gas


def get_hist_weather_forecast(run):
    for i in country_list:
        print(i)
        df2 = sql.read_sql("select MAX(ForecastOnDate) from ECMWF_Europe_fcast where Run='{:d}' and Country='{:s}'".format(run, i))
        if df2.iloc[0, 0] is None:
            sdate = dt.datetime(2018, 10, 15)
        else:
            if isinstance(df2.iloc[0, 0], str):
                sdate = dt.datetime.strptime(df2.iloc[0, 0], '%Y-%m-%d') + dt.timedelta(days=1)
            else:
                sdate = df2.iloc[0, 0] + dt.timedelta(days=1)
        alldays = pd.date_range(start=sdate, end=today())
        if len(alldays) > 0:
            for d in alldays:
                print(d)
                forecast_by_d = pd.DataFrame()
                for cur_run in [run]:
                    try:
                        cur_forecast = get_temperature_forecast(forecast_date=d, location=i, run=cur_run)
                        if cur_forecast is None:
                            raise IndexError
                        cur_forecast = cur_forecast.reset_index()
                        cur_forecast.rename(columns={'index': 'Date'}, inplace=True)
                        cur_forecast['Run'] = cur_run
                        cur_forecast['Country'] = i
                        cur_forecast['ForecastOnDate'] = d
                        forecast_by_d = pd.concat([forecast_by_d, cur_forecast], axis=0)
                    except IndexError:
                        pass
                sql.to_sql(forecast_by_d, 'ECMWF_Europe_fcast', index=False)


def winter_hdd(a_df):
    """historical and 10Y normal daily HDDs from CWG"""
    season = a_df.copy()
    season['month'] = season.index.month
    season['year'] = season.index.year
    season['day'] = season.index.day
    season.loc[(season['month'] >= 7), 'Season'] = 'S'
    season.loc[(season['month'] >= 10) | (season['month'] <= 6), 'Season'] = 'W'
    season.loc[(season['month'] >= 7), 'Syr'] = (season['year']).astype(str)
    season.loc[(season['month'] < 7), 'Syr'] = (season['year'] - 1).astype(str)
    season['Season_year'] = season['Season'] + season['Syr'].astype(str)
    season['Month_year'] = season['month'].astype(str) + "-" + season['year'].astype(str)
    season['Actuals_vs_Normal'] = season['NG_HDD'] - season['10Y_NG_HDD']
    season['Cumulative'] = season.groupby('Season_year')['NG_HDD'].cumsum()
    season['Cumulative of Actual_vs_Normal per season'] = season.groupby('Season_year')['Actuals_vs_Normal'].cumsum()
    season['day_count'] = season.groupby('Season_year').cumcount() + 1
    season['Cumulative of Actual_vs_Normal per month'] = season.groupby(['year', 'month'])['Actuals_vs_Normal'].cumsum()
    season['Cumulative_monthly'] = season.groupby(['year', 'month'])['NG_HDD'].cumsum()
    winter = season.loc[(season['Season'] == 'W') & (season.index >= '2010-10-01')]
    return winter


def summer_hdd(a_df):
    """historical and 10Y normal daily HDDs from CWG"""
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
    winter = season.loc[(season['Season'] == 'S') & (season.index >= '2010-10-01')]
    return winter


def cumulative_winter_hdd_chart(winter, hdd_df, title='Cumulative winter temperature vs normal'):
    winterpvt2 = pd.pivot_table(winter, columns=['Season_year'], index=['day_count'], values='Cumulative of Actual_vs_Normal per season')
    winterpvt2_email = winterpvt2[winterpvt2.columns[-6:]]
    lvi = winterpvt2_email.iloc[:, -1].last_valid_index()
    last_col = winterpvt2_email.columns[-1]
    winterpvt2_email['Latest forecast'] = winterpvt2_email.loc[lvi - len(hdd_df) + 1:lvi, last_col]
    winterpvt2_email.loc[lvi - len(hdd_df) + 1:lvi, last_col] = np.nan
    base_date = hdd_df.index[0] - dt.timedelta(days=1)
    if base_date.month >= 9:
        date_idx = pd.date_range(dt.datetime(base_date.year, 10, 1), dt.datetime(base_date.year + 1, 6, 30))
    elif base_date.month < 7:
        date_idx = pd.date_range(dt.datetime(base_date.year - 1, 10, 1), dt.datetime(base_date.year, 6, 30))
    if len(date_idx) < len(winterpvt2_email):
        winterpvt2_email = winterpvt2_email.iloc[:-1, :]
    winterpvt2_email['dates'] = date_idx
    winterpvt2_email.set_index('dates', inplace=True)
    dataPanda6 = []
    for j in range(0, len(winterpvt2_email.columns)):
        if j == len(winterpvt2_email.columns) - 2:
            trace = go.Scatter(x=winterpvt2_email.index, y=winterpvt2_email.iloc[:, j], connectgaps=True,
                               name=(winterpvt2_email.columns[j]), mode='lines', line=dict(width=3, color=_unrecovered('EU weather 1727: clipped actual trace color')))
            dataPanda6.append(trace)
        elif j == len(winterpvt2_email.columns) - 1:
            trace = go.Scatter(x=winterpvt2_email.index, y=winterpvt2_email.iloc[:, j], connectgaps=True,
                               name=(winterpvt2_email.columns[j]), mode='lines', line=dict(width=3, color='black', dash='dash'))
            dataPanda6.append(trace)
        else:
            trace = go.Scatter(x=winterpvt2_email.index, y=winterpvt2_email.iloc[:, j], connectgaps=True,
                               name=(winterpvt2_email.columns[j]), mode='lines')
            dataPanda6.append(trace)
    layout6 = go.Layout(title=title)
    fig6 = go.Figure(data=dataPanda6, layout=layout6)
    fig6.update_layout(title={'text': title, 'x': 0.5, 'xanchor': 'center'}, width=900, height=600)
    return fig6


def cumulative_summer_hdd_chart(winter, hdd_df, title='Cumulative winter temperature vs normal'):
    winterpvt2 = pd.pivot_table(winter, columns=['Season_year'], index=['day_count'], values='Cumulative of Actual_vs_Normal per season')
    winterpvt2_email = winterpvt2[winterpvt2.columns[-6:]]
    lvi = winterpvt2_email.iloc[:, -1].last_valid_index()
    last_col = winterpvt2_email.columns[-1]
    winterpvt2_email['Latest forecast'] = winterpvt2_email.loc[lvi - len(hdd_df) + 1:lvi, last_col]
    winterpvt2_email.loc[lvi - len(hdd_df) + 1:lvi, last_col] = np.nan
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
                               name=(winterpvt2_email.columns[j]), mode='lines', line=dict(width=3, color=_unrecovered('EU weather 1779: clipped actual trace color')))
            dataPanda6.append(trace)
        elif j == len(winterpvt2_email.columns) - 1:
            trace = go.Scatter(x=winterpvt2_email.index, y=winterpvt2_email.iloc[:, j], connectgaps=True,
                               name=(winterpvt2_email.columns[j]), mode='lines', line=dict(width=3, color='black', dash='dash'))
            dataPanda6.append(trace)
        else:
            trace = go.Scatter(x=winterpvt2_email.index, y=winterpvt2_email.iloc[:, j], connectgaps=True,
                               name=(winterpvt2_email.columns[j]), mode='lines')
            dataPanda6.append(trace)
    layout6 = go.Layout(title=title)
    fig6 = go.Figure(data=dataPanda6, layout=layout6)
    fig6.update_layout(title={'text': title, 'x': 0.5, 'xanchor': 'center'}, width=900, height=600)
    return fig6


def witer_month_table(winter):
    'HDD vs 10Y normal by month for each winter'
    df_eom2 = winter[['Actuals_vs_Normal']]
    df_eom2 = df_eom2.resample("MS").sum()
    df_eom2['month'] = df_eom2.index.month
    df_eom2['year'] = df_eom2.index.year
    df_eom2.loc[(df_eom2['month'] >= 7), 'Season'] = 'S'
    df_eom2.loc[(df_eom2['month'] >= 10) | (df_eom2['month'] <= 6), 'Season'] = 'W'
    df_eom2.loc[(df_eom2['month'] >= 7), 'Syr'] = (df_eom2['year']).astype(str)
    df_eom2.loc[(df_eom2['month'] < 7), 'Syr'] = (df_eom2['year'] - 1).astype(str)
    df_eom2['Season_year'] = df_eom2['Season'] + df_eom2['Syr'].astype(str)
    df_eom2_winter = df_eom2.loc[(df_eom2['Season'] == 'W') & (df_eom2.index >= '2016-09-01')]
    df_eom2_winter['Actuals_vs_Normal'] = df_eom2_winter['Actuals_vs_Normal']
    df_eom2_winterpvt = pd.pivot_table(df_eom2_winter, columns=['Season_year'], index=['month'], values='Actuals_vs_Normal')
    df_eom2_winterpvt = df_eom2_winterpvt.reindex([10, 11, 12, 1, 2, 3, 4, 5, 6])
    df_eom2_winterpvt.loc['Total', :] = df_eom2_winterpvt.sum(axis=0)
    df_eom2_winterpvt.insert(loc=0, column='month', value=['Oct', 'Nov', 'Dec', 'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Total'])
    df_eom2_winterpvt.index.name = None
    df_eom2_winterpvt.columns.name = None
    df_eom2_winterpvt.reset_index(drop=True, inplace=True)
    return df_eom2_winterpvt


def summer_month_table(summer):
    'HDD vs 10Y normal by month for each winter'
    df_eom2 = summer[['Actuals_vs_Normal']]
    df_eom2 = df_eom2.resample("MS").sum()
    df_eom2['month'] = df_eom2.index.month
    df_eom2['year'] = df_eom2.index.year
    df_eom2.loc[(df_eom2['month'] >= 4), 'Season'] = 'S'
    df_eom2.loc[(df_eom2['month'] >= 11) | (df_eom2['month'] <= 3), 'Season'] = 'W'
    df_eom2.loc[(df_eom2['month'] >= 4), 'Syr'] = (df_eom2['year']).astype(str)
    df_eom2.loc[(df_eom2['month'] < 4), 'Syr'] = (df_eom2['year'] - 1).astype(str)
    df_eom2['Season_year'] = df_eom2['Season'] + df_eom2['Syr'].astype(str)
    df_eom2_winter = df_eom2.loc[(df_eom2['Season'] == 'S') & (df_eom2.index >= '2017-04-01')]
    df_eom2_winter['Actuals_vs_Normal'] = df_eom2_winter['Actuals_vs_Normal']
    df_eom2_winterpvt = pd.pivot_table(df_eom2_winter, columns=['Season_year'], index=['month'], values='Actuals_vs_Normal')
    df_eom2_winterpvt = df_eom2_winterpvt.reindex([4, 5, 6, 7, 8, 9, 10])
    df_eom2_winterpvt.loc['Total', :] = df_eom2_winterpvt.sum(axis=0)
    df_eom2_winterpvt.insert(loc=0, column='month', value=['Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Total'])
    df_eom2_winterpvt.index.name = None
    df_eom2_winterpvt.columns.name = None
    df_eom2_winterpvt.reset_index(drop=True, inplace=True)
    return df_eom2_winterpvt


def update():
    gas_weather_forecast(send_to=send_to)
    update_eu_tdd_forecast(run=0)
    update_eu_tdd_forecast(run=12)
    update_eu_tdd_norm()
    update_eu_tdd_live()
    update_eu_tdd_norm_spline()
    ldz_change_vs_history()


if __name__ == '__main__':
    update()

