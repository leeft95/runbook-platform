import pandas as pd
import numpy as np
import datetime as dt
import sys
import os
from prophet import Prophet
import holidays
import requests
import plotly.graph_objects as go
import plotly as py
from dateutil.relativedelta import relativedelta
import ecm.cmds.data as dv
import ecm.cmds.kpler as kpler
import ecm.cmds.time_series as ts
import ecm.cmds.table as table
import ecm.cmds.pyg as pyg
from ecm.cmds.config import root_path, html_path, output_path
from ecm.cmds.cdr import today
from ecm.cmds._email import send_email
import ecm.cmds.bbg as bbg
import ecm.cmds.sql as sql
from ecm.atom.wintask.scheduler import ECMWinTask
from ecm.atom.wintask.utils import Days

report_name = 'Product Monthly Balance'
file_name = 'product_monthly_balance'  # without .py
file_path = f"{root_path}\\autoreports\\reports\\oil\\{file_name}.py"
EIA = dv.eia_api_key


def _missing_photo_text(lines, *visible_fragments):
    raise NotImplementedError(f'Unrecoverable photograph text at source lines {lines}; see TRANSCRIPTION_NOTES.md')


def add_schedule():
    """
    # schedule to run the report - only need to run once
    """
    sys.path.append(f"{root_path}\\autoreports\\schedule")
    from tasks import WinTaskPoC
    win_task = ECMWinTask(
        days=Days.MONDAY | Days.TUESDAY | Days.WEDNESDAY | Days.THURSDAY | Days.FRIDAY,
        start_datetime=dt.datetime(2023, 7, 1, 8, 0), timezone='Europe/London', task_name=report_name,
        task=WinTaskPoC(name=f'"{report_name}"', filepath=f'"{file_path}"'), background_task=True,
        python_excecutable=r'C:\local\python\miniconda\envs\ecm_cmds\pythonw.exe')
    win_task.create_task()


def seasonal_chart(data, data1=None, title=None, **kwargs):
    file_path = kwargs.get('file_path', None)
    y_axis_title = kwargs.get('y_axis_title', None)
    x_axis_title = kwargs.get('x_axis_title', None)
    y_axis_min = kwargs.get('y_axis_min', None)
    freq = kwargs.get('freq', 'm')
    seasonal_data = ts.data_by_year(data, freq=freq)
    seasonal_data['Max'] = seasonal_data.iloc[:, :5].max(axis=1)
    seasonal_data['Min'] = seasonal_data.iloc[:, :5].min(axis=1)
    seasonal_data['5 Year Avg'] = seasonal_data.iloc[:, :5].mean(axis=1)
    if freq in ['m', 'w']:
        seasonal_data.index = seasonal_data.index + 1
    elif freq == 'd':
        seasonal_data.index = pd.date_range(dt.datetime(seasonal_data.columns[-1], 1, 1),
                                            dt.datetime(seasonal_data.columns[-1], 12, 31))
    elif freq == 'wd':
        seasonal_data.index = pd.bdate_range(dt.datetime(seasonal_data.columns[-1], 1, 1),
                                             dt.datetime(seasonal_data.columns[-1], 12, 31))
    colors = ['#17becf', '#e377c2', '#ff7f0e', '#2ca02c', 'darkblue', 'firebrick']
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=seasonal_data.index, y=seasonal_data['Max'], fill=None, mode=None,
                             line_color='lightgray', showlegend=False))
    fig.add_trace(go.Scatter(x=seasonal_data.index, y=seasonal_data['Min'], fill='tonexty',  # fill area between trace0 and trace1
                             mode=None, line_color='lightgray', showlegend=False))
    fig.add_trace(go.Scatter(x=seasonal_data.index, y=seasonal_data['5 Year Avg'], name='5 Year Avg',
                             line=dict(color='black', width=4, dash='dot')))
    for i in [-6, -5, -4]:
        fig.add_trace(go.Scatter(x=seasonal_data.index, y=seasonal_data.iloc[:, i], name=seasonal_data.columns[i],
                                 line=dict(color=colors[i], width=2)))
    if data1 is not None:
        for col in data1.columns:
            fig.add_trace(go.Scatter(x=seasonal_data.index,
                                     y=data1.loc[data1.index >= dt.datetime(seasonal_data.columns[-4], 1, 1), col],
                                     name=col, line=dict(color='blue', width=2, dash='dash')))
    fig.update_layout(title=title, xaxis_title=x_axis_title, yaxis_title=y_axis_title,
                      template='plotly_white', width=640, height=480)
    if y_axis_min is not None:
        fig.update_yaxes(range=[y_axis_min, data.max()])
    if file_path is not None:
        py.offline.plot(fig, auto_open=False, filename=file_path)
    return fig


def mogas_monthly_balance():
    val_date = today()
    val_date2 = today() + dt.timedelta(28)
    nxt_mnth = val_date2.replace(day=28) + dt.timedelta(days=4)
    res = nxt_mnth - dt.timedelta(days=nxt_mnth.day)
    dataneeded_EIA = ['M_EPCO_YIY_R10_2', 'MGFRYP13', 'M_NA_YDR_R10_MBBLD', 'MCRCCP12', 'M_EPOOXE_YIY_R10_2',
                      'MFERIP12', 'M_EPOBG_YIY_R10_2', 'M_EPOBG_YIB_R10_2', 'MGFRPP11', 'MBCIMP11', 'MGFIMP11',
                      'MGFUPP12', 'MGFMXP2P11', 'MBCMXP2P11', 'MBCSTP11', 'MGFSTP11', 'MBCNRP11', 'MGFNRP11',
                      'MBCMXP1P31', 'MGFMXP1P31']
    dataneeded_columns = ['P1 Runs kbd', 'yields reported', 'Reported reformate feeds', 'Reported FCC feeds',
                          'Ethanol i/p Refs', 'Total Ethanol i/p', 'MGBC i/p Ref', 'MGBC i/p Blender',
                          'Finished Mogas prod', 'Imports from ex-US MGBC kb/d', 'Imports from ex-US FM kb/d',
                          'P1 demand kb/d', 'Exports ex US FM kb/d to p2', 'Exports of MGBC to p2',
                          'Total Stocks MGBC', 'Total Stocks FM', 'Net Receipts MGBC', 'Net Receipts FM',
                          'P3 Imports', 'P3MGBC']
    monthlydata = pd.DataFrame()
    """
    Donwload data from EIA API
    """
    for i in range(0, len(dataneeded_EIA)):
        if i in (0, 4, 6):
            EIA_web = (f'https://api.eia.gov/v2/petroleum/pnp/inpt2/data/?api_key={EIA}&'
                       f'frequency=monthly&data[1]=value&facets[series][]={dataneeded_EIA[i]}&'
                       f'sort[0][column]=period&sort[0][direction]=desc&offset=0&length=5000')
        elif i == 1:
            EIA_web = (f'https://api.eia.gov/v2/petroleum/pnp/pct/data/?api_key={EIA}&'
                       f'frequency=monthly&data[0]=value&facets[series][]={dataneeded_EIA[i]}&'
                       f'sort[0][column]=period&sort[0][direction]=desc&offset=0&length=5000')
        elif i in (2, 3, 4):
            EIA_web = (f'https://api.eia.gov/v2/petroleum/pnp/dwns/data/?api_key={EIA}&'
                       f'frequency=monthly&data[0]=value&facets[series][]={dataneeded_EIA[i]}&'
                       f'sort[0][column]=period&sort[0][direction]=desc&offset=0&length=5000')
        elif i == 7:
            EIA_web = (f'https://api.eia.gov/v2/petroleum/pnp/inpt3/data/?api_key={EIA}&'
                       f'frequency=monthly&data[0]=value&facets[series][]={dataneeded_EIA[i]}&'
                       f'sort[0][column]=period&sort[0][direction]=desc&offset=0&length=5000')
        elif i in (9, 10):
            EIA_web = (f'https://api.eia.gov/v2/petroleum/move/imp/data/?api_key={EIA}&'
                       f'frequency=monthly&data[0]=value&facets[series][]={dataneeded_EIA[i]}&'
                       f'sort[0][column]=period&sort[0][direction]=desc&offset=0&length=5000')
        elif i in (12, 13, 18, 19):
            EIA_web = (f'https://api.eia.gov/v2/petroleum/move/ptb/data/?api_key={EIA}&'
                       f'frequency=monthly&data[0]=value&facets[series][]={dataneeded_EIA[i]}&'
                       f'sort[0][column]=period&sort[0][direction]=desc&offset=0&length=5000')
        elif i == 13:
            EIA_web = (f'https://api.eia.gov/v2/petroleum/move/pipe/data/?api_key={EIA}&'
                       f'frequency=monthly&data[0]=value&facets[series][]={dataneeded_EIA[i]}&'
                       f'sort[0][column]=period&sort[0][direction]=desc&offset=0&length=5000')
        else:
            EIA_web = (f'https://api.eia.gov/v2/petroleum/sum/snd/data/?api_key={EIA}&'
                       f'frequency=monthly&data[0]=value&facets[series][]={dataneeded_EIA[i]}&'
                       f'sort[0][column]=period&sort[0][direction]=desc&offset=0&length=5000')
        commercial = requests.get(EIA_web, verify=False)
        json_data = commercial.json()
        db = pd.DataFrame(json_data['response']['data'])
        df = db[['period', 'value']]
        df.columns = ['Date', '{}'.format(dataneeded_columns[i])]
        df.set_index('Date', drop=True, inplace=True)
        df.loc[:, 'Year'] = df.index.astype(str).str[:4]
        df.loc[:, 'Month'] = df.index.astype(str).str[5:]
        df.loc[:, 'Day'] = 1
        df.loc[:, 'Date'] = pd.to_datetime(df[['Year', 'Month', 'Day']])
        df.set_index('Date', drop=True, inplace=True)
        df = df.drop(columns=['Year', 'Month', 'Day'])
        monthlydata = pd.concat([monthlydata, df], axis=1)
    bblstokbd = ['Imports from ex-US MGBC kb/d', 'Imports from ex-US FM kb/d', 'Exports ex US FM kb/d to p2',
                 'Exports of MGBC to p2', 'Net Receipts MGBC', 'Net Receipts FM', 'P3 Imports', 'P3MGBC',
                 'Finished Mogas prod']
    for j in range(0, len(bblstokbd)):
        monthlydata['{}'.format(bblstokbd[j])] = monthlydata['{}'.format(bblstokbd[j])] / monthlydata.index.days_in_month
    monthlydata['MGBC i/p Net'] = monthlydata[['MGBC i/p Ref', 'MGBC i/p Blender']].sum(axis=1)
    monthlydata['Yields'] = (monthlydata['Finished Mogas prod'] - monthlydata['Total Ethanol i/p'] - monthlydata[
        'MGBC i/p Net']) / monthlydata['P1 Runs kbd']
    monthlydata['Total Exports'] = monthlydata[['Exports ex US FM kb/d to p2', 'Exports of MGBC to p2']].sum(axis=1)
    monthlydata['Total Stocks'] = monthlydata[['Total Stocks MGBC', 'Total Stocks FM']].sum(axis=1)
    monthlydata['Change in Total stocks'] = monthlydata['Total Stocks'].diff()
    monthlydata['Change in stocks in kb/d'] = monthlydata['Change in Total stocks'] / monthlydata.index.days_in_month
    monthlydata['Ethanol i/p Blender'] = monthlydata['Total Ethanol i/p'] - monthlydata['Ethanol i/p Refs']
    monthlydata['P3 Imports'] = monthlydata[['P3 Imports', 'P3MGBC']].sum(axis=1)
    monthlydata['Imports from ex-US kb/d'] = monthlydata[['Imports from ex-US MGBC kb/d', 'Imports from ex-US FM kb/d']].sum(axis=1)
    monthlydata['total imp kb/d'] = monthlydata[['Imports from ex-US kb/d', 'P3 Imports']].sum(axis=1)
    monthlydata['Total Supply from Calc'] = monthlydata['total imp kb/d'] + monthlydata['Finished Mogas prod']
    monthlydata['Total Demand'] = monthlydata['P1 demand kb/d'] + monthlydata['MGBC i/p Net'] + monthlydata['Total Exports']
    monthlydata['Implied stock change'] = monthlydata['Total Supply from Calc'] - monthlydata['Total Demand']
    monthlydata['Monthly_Ref_Prod'] = monthlydata['Yields'] * monthlydata['P1 Runs kbd']
    monthlydata['Adjustment'] = monthlydata['Implied stock change'] - monthlydata['Change in stocks in kb/d']
    hist = monthlydata.copy()
    padd1 = dv.kpler(('/v1/flows?toZones=padd%201&flowDirection=Import&split=Products&startDate=2017-01-01&'
                      'granularity=monthly&unit=kbd&withForecast=false&products= Clean%20Products'))
    padd1 = kpler.convert_to_ts(padd1)
    p1_mogas = padd1[['Gasoline/Naphtha', 'Gasoline', 'Blending Comps', 'Naphtha']]
    p1_mogas['Total'] = p1_mogas.sum(axis=1)
    countries = dv.kpler((f'/v1/flows?toZones=padd%201&products=Gasoline/Naphtha, Gasoline, Blending Comps, Naphtha&'
                          f'flowDirection=Import&split=Origin%20Countries&startDate=2019-01-01&granularity=eia-weekly&'
                          f'unit=kbd&endDate={dt.datetime.strftime(res, "%Y-%m-%d")}'))
    countries = kpler.convert_to_ts(countries)
    countries['Total'] = countries.sum(axis=1)
    countries['Europe'] = countries[['Netherlands', 'United Kingdom', 'Belgium', 'Portugal', 'France', 'Spain', 'Turkey',
                                     'Finland', *_missing_photo_text('250', 'It'), 'Sweden', 'Norway']].sum(axis=1)
    countries['FSU'] = countries[['Lithuania', 'Latvia', 'Russian Federation']].sum(axis=1)
    datatofcast = ['Yields', 'Total Exports', 'Imports from ex-US kb/d', 'P3 Imports', 'Ethanol i/p Blender',
                   'P1 demand kb/d', 'Change in stocks in kb/d', 'Adjustment']
    fcastdataframe = pd.DataFrame()
    for counter in range(0, len(datatofcast)):
        data = pd.DataFrame()
        data['y'] = monthlydata['{}'.format(datatofcast[counter])]
        data.index.names = ['ds']
        data.index = pd.to_datetime(data.index)
        data = data.reset_index()
        hol = holidays.CountryHoliday('US', years=range(2000, 2031))['2000-01-01':'2030-12-31']
        df_holidays = pd.DataFrame({'holiday': 'US', 'ds': hol})
        m = Prophet(holidays=df_holidays)
        m.fit(data)
        future = m.make_future_dataframe(periods=12, freq='MS')
        future.tail()
        forecast = m.predict(future)
        forecast.set_index('ds', inplace=True)
        data.set_index('ds', inplace=True)
        demand_fcast = data.join(forecast[['yhat']], how='outer')
        test = demand_fcast[['y', 'yhat']]
        test.columns = ['{}'.format(datatofcast[counter]), '{}_Fcast'.format(datatofcast[counter])]
        fcastdataframe = pd.concat([fcastdataframe, test], axis=1)
    monthlydata = monthlydata.join(fcastdataframe[['Yields_Fcast', 'Total Exports_Fcast', 'Imports from ex-US kb/d_Fcast',
                                                  'P3 Imports_Fcast', 'Ethanol i/p Blender_Fcast', 'P1 demand kb/d_Fcast',
                                                  'Change in stocks in kb/d_Fcast', 'Adjustment_Fcast']], how='outer')
    monthlydata = monthlydata.loc[monthlydata.index > '01-01-2010']
    monthlydata = monthlydata.rename(columns={'Change in stocks in kb/d_Fcast': 'FB Prophet Change in Stocks kbd'})
    weeklydata = bbg.bdh(['DOEIGAS1 Index', 'DOEPBCP1 Index', 'DOETMGP1 Index', 'DOESGAS1 Index', 'DOEPFEP1 Index',
                          'DOEPCRP1 Index'], ['PX_LAST'], dt.datetime(2010, 1, 1), today(),
                         elms=[('periodicityAdjustment', 'ACTUAL')])
    weeklydata.columns = ['Weekly Imports', 'Weekly MGBC', 'Weekly Total Production', 'Weekly Stocks',
                          'Weekly Demand', 'Weekly Runs']
    weeklydata['Weekly_Ref_Prod'] = weeklydata['Weekly Total Production'] - weeklydata['Weekly MGBC'] - weeklydata['Weekly Demand']
    weeklydata['Weekly_Yield'] = weeklydata['Weekly_Ref_Prod'] / weeklydata['Weekly Runs']
    lastweeklydate = weeklydata.index[-1]
    first = lastweeklydate.replace(day=1)
    lastMonth = (first - dt.timedelta(days=1)).replace(day=1)
    weeklydata2 = weeklydata.copy()
    weeklydata2 = weeklydata2.sort_index().resample('MS').apply(lambda ser: ser.iloc[-1,])
    weeklydata = weeklydata.resample('MS').mean()
    monthlydata = monthlydata.join(weeklydata[['Weekly Imports', 'Weekly MGBC', 'Weekly Total Production', 'Weekly Demand',
                                              'Weekly Runs', 'Weekly_Ref_Prod', 'Weekly_Yield']], how='outer')
    monthlydata = monthlydata.join(weeklydata2['Weekly Stocks'], how='outer')
    finalstocks = weeklydata2.loc[weeklydata.index == lastMonth]['Weekly Stocks']
    zavg = countries.rolling(4).mean()
    zavgneed = zavg.loc[zavg.index == lastweeklydate]
    countries['Canada_adj'] = np.where(countries.index > lastweeklydate + dt.timedelta(days=7),
                                       *_missing_photo_text('311', 'zavgneed.Can'))
    countries['EU_adj_2'] = np.where(countries.index > lastweeklydate + dt.timedelta(days=14),
                                     *_missing_photo_text('312', 'zavgneed.Euro'))
    countries['EU_adj'] = countries['EU_adj_2'] - countries['Europe']
    countries['EU_adj'] = np.where(countries['EU_adj_2'] > 0, countries['EU_adj_2'] - countries['Europe'], 0)
    countries['Kpler_Imports_adjusted'] = countries['Total'] + countries['Canada_adj'] + countries['EU_adj']
    countries['Europe'] = countries['Europe'] + countries['EU_adj']
    countries['Canada'] = countries['Europe'] + countries['EU_adj']
    countries = countries.resample('MS').mean()
    newdata = pd.read_csv((f'https://api.energyaspects.com/data/timeseries/csv?api_key={os.environ["ENERGY_ASPECTS_API_KEY"]}&'
                           'geography=US&frequency=monthly&category=crude_oil&aspect=runs'), sep=',')
    newdata = newdata.set_index('Date')
    newdata.index = pd.to_datetime(newdata.index)
    newdata = pd.DataFrame(newdata['Monthly refinery runs for US PADD 1 in kb/d'])
    monthlydata['EA_Runs'] = newdata['Monthly refinery runs for US PADD 1 in kb/d']
    monthlydata['Prod_From_refinery_Fcast'] = monthlydata['EA_Runs'] * monthlydata['Yields_Fcast']
    monthlydata['Kpler_imports'] = countries['Kpler_Imports_adjusted']
    monthlydata['Kpler_EU'] = countries['Europe']
    monthlydata['Dem2'] = monthlydata['Ethanol i/p Blender_Fcast'] * 10
    monthlydata['P1 demand kb/d_Fcast'] = (monthlydata['P1 demand kb/d_Fcast'] + monthlydata['Dem2']) / 2
    monthlydata['p1 Imports'] = np.where(monthlydata['Kpler_imports'].isnull(), monthlydata['Imports from ex-US kb/d_Fcast'],
                                        monthlydata['Kpler_imports'])
    monthlydata['Total_Supply_Fcast'] = np.where(monthlydata.index > hist.index[-1],
                                                monthlydata[['p1 Imports', 'P3 Imports_Fcast', 'Ethanol i/p Blender_Fcast',
                                                              'Prod_From_refinery_Fcast']].sum(axis=1),
                                                monthlydata[['Imports from ex-US kb/d', 'P3 Imports', 'Ethanol i/p Blender',
                                                              'Monthly_Ref_Prod']].sum(axis=1))
    monthlydata['Total_Demand_Fcast'] = np.where(monthlydata.index > hist.index[-1],
                                                monthlydata[['P1 demand kb/d_Fcast', 'Total Exports_Fcast']].sum(axis=1),
                                                monthlydata[['P1 demand kb/d', 'Total Exports']].sum(axis=1))
    monthlydata['Stock_change_Fcast'] = _missing_photo_text('344-346',
        monthlydata['Total_Supply_Fcast'] - monthlydata['Total_Demand_Fcast'], monthlydata['Adjustment_Fcast'])
    monthlydata['Stock_test'] = np.where(monthlydata.index > lastMonth, finalstocks, monthlydata['Total Stocks'].ffill())
    monthlydata['stock_adj'] = np.where(monthlydata.index > lastMonth,
                                       monthlydata['Stock_change_Fcast'] * monthlydata.index.days_in_month,
                                       _missing_photo_text('350'))
    monthlydata['stock_adj'] = monthlydata['stock_adj'].cumsum()
    monthlydata['Stock_fcast'] = np.where(monthlydata.index > lastMonth,
                                         monthlydata['Stock_test'] + monthlydata['stock_adj'], monthlydata['Weekly Stocks'])
    monthlydata['Weekly_change_in_Stocks'] = monthlydata['Weekly Stocks'].diff()
    monthlydata['Weekly_change_in_Stocks_in_kbd'] = monthlydata['Weekly_change_in_Stocks'] / monthlydata.index.days_in_month
    monthlydata['stock_adj'] = np.where(monthlydata['Total Stocks'].isnull(),
                                       monthlydata['FB Prophet Change in Stocks kbd'] * monthlydata.index.days_in_month,
                                       _missing_photo_text('360'))
    monthlydata['stock_adj'] = monthlydata['stock_adj'].cumsum()
    monthlydata['FB_Stock_fcast'] = monthlydata['Stock_test'] + monthlydata['stock_adj']
    monthlydata = monthlydata.drop(columns=['Stock_test', 'stock_adj'])
    monthlydata.to_csv(_missing_photo_text('365', f"{output_path}\\csvs\\oil\\mogas_monthly_balance\\monthlydata_", '%Y%m%'))
    z = monthlydata.loc[monthlydata.index > '01-01-2020']
    stocks = z[['Weekly Stocks', 'FB_Stock_fcast', 'Total Stocks', 'Stock_fcast']]
    test = pd.DataFrame(stocks.unstack())
    test.columns = ['Value']
    test['As_Of_Date'] = pd.to_datetime(val_date)
    test = test.reset_index()
    test = test.rename(columns={'level_0': 'Fcast_Type', 'level_1': 'Stock Month'})
    exist_dates = sql.read_sql(f'Select Distinct As_of_date from P1_Gasoline_Balances order by As_of_date')
    if val_date not in list(exist_dates['As_of_date']):
        sql.to_sql(test, 'P1_Gasoline_Balances', index=False)
    figs = []
    monthlydata_ = monthlydata.copy()
    monthlydata_ = monthlydata_.loc[(monthlydata_.index >= dt.datetime(2015, 1, 1)) &
                                   (monthlydata_.index <= _missing_photo_text('382', 'dt.datetime(today().year, 1'))]
    p1_import = monthlydata_['Imports from ex-US MGBC kb/d'] + monthlydata_['Imports from ex-US FM kb/d']
    figs.append(seasonal_chart(monthlydata_['P1 demand kb/d'],
                               data1=monthlydata_['P1 demand kb/d_Fcast'].to_frame('P1 demand fcst'),
                               title='PADD1 demand', x_axis_title='month', y_axis_title='kbd'))
    figs.append(seasonal_chart(monthlydata_['P1 Runs kbd'], data1=monthlydata_['EA_Runs'].to_frame('P1 runs fcst'),
                               title='PADD1 runs', x_axis_title='month', y_axis_title='kbd'))
    figs.append(seasonal_chart(p1_import, data1=monthlydata_['p1 Imports'].to_frame('P1 imports fcst'),
                               title='PADD1 imports', x_axis_title='month', y_axis_title='kbd'))
    figs.append(seasonal_chart(monthlydata_['Total Stocks'],
                               data1=monthlydata_['Stock_fcast'].to_frame('Stocks fcst'),
                               title='Total stocks', x_axis_title='month', y_axis_title='kb'))
    maindf = monthlydata[['P1 Runs kbd', 'EA_Runs', 'P1 demand kb/d', 'P1 demand kb/d_Fcast', 'Exports of MGBC to p2',
                          *_missing_photo_text('395', 'P3 Im'), 'Imports from ex-US kb/d', 'p1 Imports', 'Total Stocks',
                          'Change in Total stocks', *_missing_photo_text('396', 'Change in stock'),
                          'Weekly Stocks', 'Weekly_change_in_Stocks_in_kbd', 'Stock_fcast', 'Stock_change_Fcast',
                          *_missing_photo_text('397', 'FB_Stock_f')]]
    maindf = maindf.loc[maindf.index >= '2021-01-01']
    maindf.index = maindf.index.strftime('%b-%y')
    maindf.index.name = 'Dates'
    maindf.reset_index(inplace=True)
    last_row_idx = maindf.loc[maindf['Dates'] == dt.datetime.strftime(today(), '%b-%y')].index[0]
    maindf_html = table.html_format(maindf, precision=0,
                                    format_column={maindf.columns[0]: {'width': '80px', 'text-align': 'center'},
                                                   tuple(maindf.columns[1:]): {'width': '80px', 'text-align': 'center'}},
                                    format_row={last_row_idx + 1: {'bottom_border': True, 'bold': True},
                                                last_row_idx: {'bold': True}, last_row_idx - 1: {'bold': True},
                                                last_row_idx - 2: {'bottom_border': True}})
    figs.insert(0, maindf_html)
    table.figures_to_html(figs, f"{html_path}\\oil\\mogas_monthly_balance.html", task_name=report_name)
    table.figures_to_html(figs, _missing_photo_text('416', f"{html_path}\\oil\\mogas_monthly_balance\\mogas_monthly_balance_", '%Y%'))
    file_list = os.listdir(f"{html_path}\\oil\\mogas_monthly_balance")
    files = pd.DataFrame([file_list]).T
    files.columns = ['List of Prior files']
    files['List of Prior files'] = f"{html_path}\\oil\\mogas_monthly_balance\\" + files['List of Prior files'].astype(str)

    def make_clickable(val):
        return '<a href="{}">{}</a>'.format(val, val)

    testfiles = files.style.format(make_clickable)
    total_loc = f'{html_path}\\oil\\mogas_monthly_balance_prior_tables.html'
    with open(total_loc, 'w') as f:
        f.write(testfiles.render())


def disty_monthly_balance():
    val_date = today()
    val_date2 = today() + dt.timedelta(28)
    nxt_mnth = val_date2.replace(day=28) + dt.timedelta(days=4)
    res = nxt_mnth - dt.timedelta(days=nxt_mnth.day)
    dataneeded_EIA = ['M_EPCO_YIY_R10_2', 'MDIRPP12', 'MDIIMP12', 'MDIMXP1P31', 'MDIUPP12', 'MDIEXP12',
                      'MDIMXP2P11', 'MDISTP11', 'MDIUPUS2', 'MDIUPP22', 'MDIUPP32', 'MDIUPP42', 'MDIUPP52', 'MDIMPP1P31']
    dataneeded_columns = ['P1 Runs kbd', 'Disty Production', 'Imports from ex-US kb/d', 'Imports from P3 kb/d',
                          'P1 demand kb/d', 'Exports Ex-US', 'Exports to P2 kb/d', 'Total Stocks', 'STEO_US',
                          'STEO_P2', 'STEO_P3', 'STEO_P4', 'STEO_P5', 'P3_P1_pipe']
    monthlydata = pd.DataFrame()
    EIA_web = 'https://api.eia.gov/series/?api_key={}&series_id='.format(EIA)
    """Donwload data from EIA API"""
    for i in range(0, len(dataneeded_EIA)):
        if i == 0:
            EIA_web = (f'https://api.eia.gov/v2/petroleum/pnp/inpt2/data/?api_key={EIA}&frequency=monthly&'
                       f'data[1]=value&facets[series][]={dataneeded_EIA[i]}&sort[0][column]=period&'
                       f'sort[0][direction]=desc&offset=0&length=5000')
        elif i in (3, 6):
            EIA_web = (f'https://api.eia.gov/v2/petroleum/move/ptb/data/?api_key={EIA}&frequency=monthly&'
                       f'data[0]=value&facets[series][]={dataneeded_EIA[i]}&sort[0][column]=period&'
                       f'sort[0][direction]=desc&offset=0&length=5000')
        elif i == 13:
            EIA_web = (f'https://api.eia.gov/v2/petroleum/move/pipe/data/?api_key={EIA}&frequency=monthly&'
                       f'data[0]=value&facets[series][]={dataneeded_EIA[i]}&sort[0][column]=period&'
                       f'sort[0][direction]=desc&offset=0&length=5000')
        else:
            EIA_web = (f'https://api.eia.gov/v2/petroleum/sum/snd/data/?api_key={EIA}&frequency=monthly&'
                       f'data[0]=value&facets[series][]={dataneeded_EIA[i]}&sort[0][column]=period&'
                       f'sort[0][direction]=desc&offset=0&length=5000')
        commercial = requests.get(EIA_web, verify=False)
        json_data = commercial.json()
        db = pd.DataFrame(json_data['response']['data'])
        df = db[['period', 'value']]
        df.columns = ['Date', '{}'.format(dataneeded_columns[i])]
        df.set_index('Date', drop=True, inplace=True)
        df.loc[:, 'Year'] = df.index.astype(str).str[:4]
        df.loc[:, 'Month'] = df.index.astype(str).str[5:]
        df.loc[:, 'Day'] = 1
        df.loc[:, 'Date'] = pd.to_datetime(df[['Year', 'Month', 'Day']])
        df.set_index('Date', drop=True, inplace=True)
        df = df.drop(columns=['Year', 'Month', 'Day'])
        monthlydata = pd.concat([monthlydata, df], axis=1)
    bblstokbd = ['Imports from P3 kb/d', 'Exports to P2 kb/d', 'P3_P1_pipe']
    for j in range(0, len(bblstokbd)):
        monthlydata['{}'.format(bblstokbd[j])] = monthlydata['{}'.format(bblstokbd[j])] / monthlydata.index.days_in_month
    monthlydata['Yields'] = (monthlydata['Disty Production']) / monthlydata['P1 Runs kbd']
    monthlydata['Total Exports'] = monthlydata[['Exports to P2 kb/d', 'Exports Ex-US']].sum(axis=1)
    monthlydata['Change in Total stocks'] = monthlydata['Total Stocks'].diff()
    monthlydata['Change in stocks in kb/d'] = monthlydata['Change in Total stocks'] / monthlydata.index.days_in_month
    monthlydata['total imp kb/d'] = monthlydata[['Imports from ex-US kb/d', 'Imports from P3 kb/d']].sum(axis=1)
    monthlydata['Total Supply from Calc'] = monthlydata['total imp kb/d'] + monthlydata['Disty Production']
    monthlydata['Total Demand'] = monthlydata['P1 demand kb/d'] + monthlydata['Total Exports']
    monthlydata['Implied stock change'] = monthlydata['Total Supply from Calc'] - monthlydata['Total Demand']
    monthlydata['Adjustment'] = monthlydata['Implied stock change'] - monthlydata['Change in stocks in kb/d']
    monthlydata['P1_ratio'] = monthlydata['P1 demand kb/d'] / monthlydata['STEO_US']
    p1_ratio = monthlydata['P1_ratio'].groupby(monthlydata.index.month).mean()
    hist = monthlydata.copy()
    cleanurl = 'https://api.kpler.com'
    credentials = {'email': os.environ['KPLER_EMAIL'], 'password': os.environ['KPLER_PASSWORD']}
    headers_login = {'Content-Type': 'application/json'}
    response = requests.post(cleanurl + '/v1/login', data=json.dumps(credentials), headers=headers_login,
                              **_missing_photo_text('537', 've'))
    if response.status_code != 200:
        raise Exception('Failed to authenticate !')
    else:
        token = response.json()['token']
        headers = {'Authorization': token}

    def style_negative(v, props=''):
        return props if v < 0 else None

    test9 = requests.get(cleanurl + ('/v1/flows?toZones=padd%201&flowDirection=Import&split=Products&'
                                     'startDate=2017-01-01&granularity=monthly&unit=kbd&withForecast=false'),
                          headers=headers, stream=True, verify=False)
    t = test9.content
    s2 = str(t, 'utf-8')
    dt_kpler = StringIO(s2)
    padd1 = pd.read_csv(dt_kpler, sep=';')
    p1_mogas = padd1[['Date', 'Diesel', 'Gasoil/Diesel', 'Gasoil', 'LCO']]
    p1_mogas['Total'] = p1_mogas.sum(axis=1)
    p1_mogas['Date'] = pd.to_datetime(p1_mogas['Date'])
    p1_mogas.set_index('Date', drop=True, inplace=True)
    EU = ['Netherlands', 'Belgium', 'Spain', 'Italy', 'Norway', 'Turkey']
    test10 = requests.get(cleanurl + (f'/v1/flows?toZones=padd%201&products=Diesel, Gasoil/Diesel, Gasoil, LCO&flowDirection=Import&'
                                      f'split=Origin%20Countries&startDate=2019-01-01&granularity=eia-weekly&'
                                      f'unit=kbd&endDate={res.strftime("%Y-%m-%d")}'),
                           headers=headers, stream=True, verify=False)
    t = test10.content
    s2 = str(t, 'utf-8')
    dt_kpler = StringIO(s2)
    countries = pd.read_csv(dt_kpler, sep=';')
    countries['Total'] = countries.sum(axis=1)
    countries['Date'] = pd.to_datetime(countries['Date'])
    countries.set_index('Date', drop=True, inplace=True)
    countries['PG'] = countries[['Saudi Arabia', 'Kuwait', 'United Arab Emirates', 'Qatar', ]].sum(axis=1)
    countries['Asia'] = countries[['South Korea', 'India']].sum(axis=1)
    countries['Europe'] = countries[[col_name for col_name in EU]].sum(axis=1)
    datatofcast = ['Yields', 'Total Exports', 'Imports from ex-US kb/d', 'Imports from P3 kb/d', 'P1 demand kb/d',
                   'Change in stocks in kb/d', 'Adjustment', 'P3_P1_pipe']
    fcastdataframe = pd.DataFrame()
    for counter in range(0, len(datatofcast)):
        data = pd.DataFrame()
        data['y'] = monthlydata['{}'.format(datatofcast[counter])]
        data.index.names = ['ds']
        data.index = pd.to_datetime(data.index)
        hol = holidays.CountryHoliday('US', years=range(2000, 2031))['2000-01-01':'2030-12-31']
        df_holidays = pd.DataFrame({'holiday': 'US', 'ds': hol})
        m = Prophet(holidays=df_holidays)
        if datatofcast[counter] in ['Imports from P3 kb/d']:
            pipe_arb = bbg.bdh('UDS1 Comdty', ['PX_LAST'], dt.datetime(2010, 1, 1), today(),
                               elms=[('periodicityAdjustment', 'ACTUAL')])
            line_space = pyg.get_data(pyg.data_db().platts, platts_ticker='AAXTD00')
            pipe_arb = pipe_arb.reindex(line_space.index)
            price_arb = _missing_photo_text('598-599', 'pipe_arb', 'line_space.iloc[:, 0] / 100')
            data['x'] = price_arb.reindex(data.index)
            data.dropna(inplace=True)
            m.add_regressor('x')
        data = data.reset_index()
        m.fit(data)
        future = m.make_future_dataframe(periods=12, freq='MS')
        if datatofcast[counter] in ['Imports from P3 kb/d']:
            future['x'] = price_arb.reindex(future.ds).reset_index(drop=True)
            future['x'].fillna(method='ffill', inplace=True)
        forecast = m.predict(future)
        if datatofcast[counter] in ['Imports from P3 kb/d']:
            for idx, row in forecast.iterrows():
                if forecast.loc[idx, 'ds'] > data['ds'].iloc[-1] and \
                        forecast.loc[idx, 'ds'].month in [4, 5, 6, 7, 8, 9, 10]:
                    previous_peak = data.loc[(pd.DatetimeIndex(data['ds']).month == forecast.loc[idx, 'ds'].month) &
                                              (pd.DatetimeIndex(data['ds']).year != 2020), 'y'].max()
                    if forecast.loc[idx, 'yhat'] > previous_peak:
                        forecast.loc[idx, 'yhat'] = previous_peak
        forecast.set_index('ds', inplace=True)
        data.set_index('ds', inplace=True)
        demand_fcast = data.join(forecast[['yhat']], how='outer')
        test = demand_fcast[['y', 'yhat']]
        test.columns = ['{}'.format(datatofcast[counter]), '{}_Fcast'.format(datatofcast[counter])]
        fcastdataframe = pd.concat([fcastdataframe, test], axis=1)
    monthlydata = monthlydata.join(fcastdataframe[['Yields_Fcast', 'Total Exports_Fcast', 'Imports from ex-US kb/d_Fcast',
                                                  'Imports from P3 kb/d_Fcast', 'P1 demand kb/d_Fcast',
                                                  'Change in stocks in kb/d_Fcast', 'Adjustment_Fcast',
                                                  'P3_P1_pipe_Fcast']], how='outer')
    monthlydata = monthlydata.loc[monthlydata.index > '01-01-2010']
    monthlydata = monthlydata.rename(columns={'Change in stocks in kb/d_Fcast': 'FB Prophet Change in Stocks kbd'})
    weeklydata = bbg.bdh(['DOEIDIS1 Index', 'DOETDIP1 Index', 'DOESDIS1 Index', 'DOEDDIST Index', 'DOEPCRP1 Index'],
                         ['PX_LAST'], dt.datetime(2010, 1, 1), today(), elms=[('periodicityAdjustment', 'ACTUAL')])
    weeklydata.columns = ['Weekly Imports', 'Weekly Total Production', 'Weekly Stocks', 'Weekly Demand', 'Weekly Runs']
    weeklydata = weeklydata.reset_index().merge(p1_ratio, how='outer', left_on=weeklydata.index.month,
                                               right_on=p1_ratio.index).set_index('date')
    weeklydata = weeklydata.drop(columns='key_0')
    weeklydata['Weekly Demand'] = weeklydata['Weekly Demand'] * weeklydata['P1_ratio']
    weeklydata = weeklydata.sort_index()
    weeklydata['Weekly_Yield'] = weeklydata['Weekly Total Production'] / weeklydata['Weekly Runs']
    lastweeklydate = weeklydata.index[-1]
    first = lastweeklydate.replace(day=1)
    lastMonth = (first - dt.timedelta(days=1)).replace(day=1)
    weeklydata2 = weeklydata.copy()
    weeklydata2 = weeklydata2.sort_index().resample('MS').apply(lambda ser: ser.iloc[-1,])
    weeklydata = weeklydata.resample('MS').mean()
    monthlydata = monthlydata.join(weeklydata[['Weekly Imports', 'Weekly Total Production', 'Weekly Demand', 'Weekly Runs',
                                              'Weekly_Yield']], how='outer')
    monthlydata = monthlydata.join(weeklydata2['Weekly Stocks'], how='outer')
    finalstocks = weeklydata2.loc[weeklydata.index == lastMonth]['Weekly Stocks']
    zavg = countries.rolling(4).mean()
    zavgneed = zavg.loc[zavg.index == lastweeklydate]
    countries['Canada_adj'] = np.where(countries.index > lastweeklydate + dt.timedelta(days=7),
                                       *_missing_photo_text('659', 'zavgneed.Can'))
    countries['Kpler_Imports_adjusted'] = countries['Total'] + countries['Canada_adj']
    countries = countries.resample('MS').mean()
    newdata = pd.read_csv((f'https://api.energyaspects.com/data/timeseries/csv?api_key={os.environ["ENERGY_ASPECTS_API_KEY"]}&'
                           'geography=US&frequency=monthly&category=crude_oil&aspect=runs'), sep=',')
    newdata = newdata.set_index('Date')
    newdata.index = pd.to_datetime(newdata.index)
    newdata = pd.DataFrame(newdata['Monthly refinery runs for US PADD 1 in kb/d'])
    monthlydata['EA_Runs'] = newdata['Monthly refinery runs for US PADD 1 in kb/d']
    monthlydata['Prod_From_refinery_Fcast'] = monthlydata['EA_Runs'] * monthlydata['Yields_Fcast']
    monthlydata['Kpler_imports'] = countries['Kpler_Imports_adjusted']
    monthlydata['Kpler_EU'] = countries['Europe']
    monthlydata['p1 Imports'] = np.where(monthlydata['Kpler_imports'].isnull(), monthlydata['Imports from ex-US kb/d_Fcast'],
                                        monthlydata['Kpler_imports'])
    monthlydata['Total_Supply_Fcast'] = np.where(monthlydata.index > hist.index[-1],
                                                monthlydata[['Imports from ex-US kb/d_Fcast', 'Imports from P3 kb/d_Fcast',
                                                              'Prod_From_refinery_Fcast']].sum(axis=1),
                                                monthlydata[['Imports from ex-US kb/d', 'Imports from P3 kb/d',
                                                              'Disty Production']].sum(axis=1))
    monthlydata['Total_Demand_Fcast'] = np.where(monthlydata.index > hist.index[-1],
                                                monthlydata[['P1 demand kb/d_Fcast', 'Total Exports_Fcast']].sum(axis=1),
                                                monthlydata[['P1 demand kb/d', 'Total Exports']].sum(axis=1))
    monthlydata['Stock_change_Fcast'] = _missing_photo_text('684-686',
        monthlydata['Total_Supply_Fcast'] - monthlydata['Total_Demand_Fcast'], monthlydata['Adjustment_Fcast'])
    monthlydata['Stock_test'] = np.where(monthlydata.index > lastMonth, finalstocks, monthlydata['Total Stocks'].ffill())
    monthlydata['stock_adj'] = np.where(monthlydata.index > lastMonth,
                                       monthlydata['Stock_change_Fcast'] * monthlydata.index.days_in_month,
                                       _missing_photo_text('690'))
    monthlydata['stock_adj'] = monthlydata['stock_adj'].cumsum()
    monthlydata['Stock_fcast'] = np.where(monthlydata.index > lastMonth,
                                         monthlydata['Stock_test'] + monthlydata['stock_adj'], monthlydata['Weekly Stocks'])
    monthlydata['Weekly_change_in_Stocks'] = monthlydata['Weekly Stocks'].diff()
    monthlydata['Weekly_change_in_Stocks_in_kbd'] = monthlydata['Weekly_change_in_Stocks'] / monthlydata.index.days_in_month
    monthlydata['stock_adj'] = np.where(monthlydata['Total Stocks'].isnull(),
                                       monthlydata['FB Prophet Change in Stocks kbd'] * monthlydata.index.days_in_month,
                                       _missing_photo_text('700'))
    monthlydata['stock_adj'] = monthlydata['stock_adj'].cumsum()
    monthlydata['FB_Stock_fcast'] = monthlydata['Stock_test'] + monthlydata['stock_adj']
    monthlydata = monthlydata.drop(columns=['Stock_test', 'stock_adj'])
    monthlydata.to_csv(_missing_photo_text('705', f"{output_path}\\csvs\\oil\\disty_monthly_balance\\monthlydata_", '%Y%m%'))
    z = monthlydata.loc[monthlydata.index > '01-01-2020']
    stocks = z[['Weekly Stocks', 'FB_Stock_fcast', 'Total Stocks', 'Stock_fcast']]
    test = pd.DataFrame(stocks.unstack())
    test.columns = ['Value']
    test['As_Of_Date'] = pd.to_datetime(val_date)
    test = test.reset_index()
    test = test.rename(columns={'level_0': 'Fcast_Type', 'level_1': 'Stock Month'})
    exist_dates = pd.read_sql(f'Select Distinct As_of_date from P1_Disty_Balances order by As_of_date', _missing_photo_text('714', 'engi'))
    if val_date not in list(exist_dates['As_of_date']):
        sql.to_sql(test, 'P1_Disty_Balances', index=False)
    figs = []
    monthlydata_ = monthlydata.copy()
    monthlydata_ = monthlydata_.loc[(monthlydata_.index >= dt.datetime(2015, 1, 1)) &
                                   (monthlydata_.index <= _missing_photo_text('721', 'dt.datetime(today().year, 1'))]
    p1_import = monthlydata_['Imports from ex-US kb/d']
    figs.append(seasonal_chart(monthlydata_['P1 demand kb/d'],
                               data1=monthlydata_['P1 demand kb/d_Fcast'].to_frame('P1 demand fcst'),
                               title='PADD1 demand', x_axis_title='month', y_axis_title='kbd'))
    figs.append(seasonal_chart(monthlydata_['P1 Runs kbd'], data1=monthlydata_['EA_Runs'].to_frame('P1 runs fcst'),
                               title='PADD1 runs', x_axis_title='month', y_axis_title='kbd'))
    figs.append(seasonal_chart(p1_import, data1=monthlydata_['p1 Imports'].to_frame('P1 imports fcst'),
                               title='PADD1 imports', x_axis_title='month', y_axis_title='kbd'))
    figs.append(seasonal_chart(monthlydata_['Total Stocks'],
                               data1=monthlydata_['Stock_fcast'].to_frame('Stocks fcst'),
                               title='Total stocks', x_axis_title='month', y_axis_title='kb'))
    maindf = monthlydata[['P1 Runs kbd', 'EA_Runs', 'P1 demand kb/d', 'P1 demand kb/d_Fcast',
                          *_missing_photo_text('734', 'Imports from'), 'Imports from P3 kb/d_Fcast',
                          'p1 Imports', 'Total Stocks', 'Change in Total stocks', 'Change in stocks in kb/d',
                          'Weekly Stocks', 'Weekly_change_in_Stocks_in_kbd', 'Stock_fcast',
                          'Stock_change_Fcast', 'FB_Stock_fcast', ]]
    maindf = maindf.loc[maindf.index >= '2021-01-01']
    maindf.index = maindf.index.strftime('%b-%y')
    maindf.index.name = 'Dates'
    maindf.reset_index(inplace=True)
    last_row_idx = maindf.loc[maindf['Dates'] == dt.datetime.strftime(today(), '%b-%y')].index[0]
    maindf_html = table.html_format(maindf, precision=0,
                                    format_column={maindf.columns[0]: {'width': '80px', 'text-align': 'center'},
                                                   tuple(maindf.columns[1:]): {'width': '80px', 'text-align': 'center'}},
                                    format_row={last_row_idx + 1: {'bottom_border': True, 'bold': True},
                                                last_row_idx: {'bold': True}, last_row_idx - 1: {'bold': True},
                                                last_row_idx - 2: {'bottom_border': True}})
    figs.insert(0, maindf_html)
    table.figures_to_html(figs, f"{html_path}\\oil\\disty_monthly_balance.html", task_name=report_name)
    table.figures_to_html(figs, _missing_photo_text('755', f"{html_path}\\oil\\disty_monthly_balance\\disty_monthly_balance_", '%Y%'))
    file_list = os.listdir(f"{html_path}\\oil\\disty_monthly_balance")
    files = pd.DataFrame([file_list]).T
    files.columns = ['List of Prior files']
    files['List of Prior files'] = f"{html_path}\\oil\\disty_monthly_balance\\" + files['List of Prior files'].astype(str)

    def make_clickable(val):
        return '<a href="{}">{}</a>'.format(val, val)

    testfiles = files.style.format(make_clickable)
    total_loc = f'{html_path}\\oil\\disty_monthly_balance_prior_tables.html'
    with open(total_loc, 'w') as f:
        f.write(testfiles.render())


def update():
    mogas_monthly_balance()
    disty_monthly_balance()


if __name__ == '__main__':
    update()
