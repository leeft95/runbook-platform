import pandas as pd
import numpy as np
import datetime as dt
import sys
import os

os.environ['CMDSTAN'] = "C:\\local\\python\\miniconda\\envs\\ecm_cmds\\Library\\bin\\cmdstan"
from prophet import Prophet
import holidays
import requests
import plotly.graph_objects as go
import plotly.express as px
import plotly as py
from dateutil.relativedelta import relativedelta
import ecm.cmds.data as dv
import ecm.cmds.kpler as kpler
import ecm.cmds.time_series as ts
import ecm.cmds.table as table
import ecm.cmds.pyg as pyg
from ecm.cmds.config import root_path, html_path, output_path, oil_group
from ecm.cmds.cdr import today
from ecm.cmds._email import send_email
from ecm.cmds.data import ea_api_key
import ecm.cmds.bbg as bbg
import ecm.cmds.sql as sql
from ecm.atom.wintask.scheduler import ECMWinTask
from ecm.atom.wintask.utils import Days

send_to = ["rzhao@elementcapital.com", "ltrindade@elementcapital.com"]
report_name = "Product Weekly Balance"
file_name = "product_weekly_balance"  # without .py
file_path = f"{root_path}\\autoreports\\reports\\oil\\{file_name}.py"


def _missing_photo_text(lines, *visible_fragments):
    raise NotImplementedError(f"Unrecoverable photographed text at source lines {lines}")


def add_schedule():
    """
    # schedule to run the report - only need to run once
    """
    sys.path.append(f"{root_path}\\autoreports\\schedule")
    from tasks import WinTaskPoC

    win_task = ECMWinTask(
        days=Days.MONDAY | Days.TUESDAY | Days.WEDNESDAY | Days.THURSDAY | Days.FRIDAY,
        start_datetime=dt.datetime(2023, 7, 1, 8, 5),
        timezone="Europe/London",
        task_name=report_name,
        task=WinTaskPoC(name=f'"{report_name}"', filepath=f'"{file_path}"'),
        background_task=True,
        python_excecutable=r"C:\local\python\miniconda\envs\ecm_cmds\pythonw.exe"
    )
    win_task.create_task()


def update_gasoline(send_to):
    sdate = dt.datetime(2010, 1, 1)
    edate = today()
    padd1 = dv.kpler(
        ('/v1/flows?toZones=padd%201&flowDirection=Import&split=Products&startDate=2019-01-01&'
         'granularity=eia-weekly&unit=kbd&products= Clean%20Products'))
    padd1 = kpler.convert_to_ts(padd1)
    p1_mogas = padd1[['Gasoline/Naphtha', 'Gasoline', 'Blending Comps', 'Naphtha']]
    p1_mogas['Total'] = p1_mogas.sum(axis=1)
    countries = dv.kpler(
        ('/v1/flows?toZones=padd%201&products=Gasoline/Naphtha,Gasoline,Blending Comps,Naphtha&'
         'flowDirection=Import&split=Origin%20Countries&startDate=2019-01-01&granularity=eia-weekly&unit=kbd'))
    countries = kpler.convert_to_ts(countries)
    countries['Total'] = countries.sum(axis=1)
    countries['Europe'] = countries[
        ['Netherlands', 'United Kingdom', 'Belgium', 'Portugal', 'France', 'Spain', 'Turkey', 'Finland',
         'Sweden', 'Norway']].sum(axis=1)
    countries['FSU'] = countries[['Lithuania', 'Latvia', 'Russian Federation']].sum(axis=1)
    countries_clean = dv.kpler(
        ('/v1/flows?toZones=padd%201&fromZones=Europe,Russia,Canada,Asia&flowDirection=Import&'
         'split=Origin%20Countries&startDate=2019-01-01&granularity=eia-weekly&unit=kbd&products= Clean%20Products'))
    countries_clean = kpler.convert_to_ts(countries_clean)
    countries_clean['Total'] = countries_clean.sum(axis=1)
    data = bbg.bdh(['DOEPFEP1 Index'], ['PX_LAST'], sdate, edate, elms=[("periodicityAdjustment", "ACTUAL")])
    data.index.names = ['ds']
    data.columns = ['y']
    data.index = pd.to_datetime(data.index)
    data = data.reset_index()
    hol = holidays.CountryHoliday('US', years=range(2000, 2031))['2000-01-01':'2030-12-31']
    df_holidays = pd.DataFrame({'holiday': 'US', 'ds': hol})
    m = Prophet(holidays=df_holidays)
    m.fit(data)
    future = m.make_future_dataframe(periods=24, freq='W-FRI')
    future.tail()
    forecast = m.predict(future)
    forecast.tail()
    fig1 = m.plot(forecast)
    fig2 = m.plot_components(forecast)
    forecast.set_index('ds', inplace=True)
    data.set_index('ds', inplace=True)
    demand_fcast = data.join(forecast[['yhat', 'yhat_lower', 'yhat_upper']], how='outer')
    test = demand_fcast[['y', 'yhat']]
    df1 = test.resample('M').mean()
    df1.index = [dt.datetime(x.year, x.month, 1) for x in df1.index]
    trace = go.Scatter(
        name='Actual Demand', mode='markers', x=list(data.index), y=list(data['y']),
        marker=dict(color='black', line=dict(width=1), size=3))
    trace1 = go.Scatter(
        name='Forecast', mode='lines', x=list(forecast.index), y=list(forecast['yhat']),
        marker=dict(color='#3bbed7', line=dict(width=3)))
    upperband = go.Scatter(
        x=forecast.index, y=forecast['yhat_upper'], fill='tonexty',
        fillcolor='rgb(175,238,238,0.1)', name='Confidence', hoverinfo='none', mode='none')
    lowerband = go.Scatter(
        x=forecast.index, y=forecast['yhat_lower'], marker={'color': 'rgba(0,0,0,0)'},
        showlegend=False, hoverinfo='none')
    datag = [lowerband, upperband, trace1, trace]
    figure = go.Figure(data=datag)
    EIA = dv.eia_api_key
    EIA_web = _missing_photo_text(156,
        f'https://api.eia.gov/v2/petroleum/sum/snd/data/?api_key={EIA}&frequency=monthly&'
        f'data[0]=value&sort[0][column]=period&sort[0][direction]=desc&offset=0&length=5000&facets[s')
    """
    Donwload data from EIA API
    """
    STEO = 'MGFUPP12'
    commercial = requests.get(EIA_web + STEO, verify=False)
    if commercial.status_code != 200:
        raise Exception(f"Request for {EIA_web} failed with {json_data.get('error')}")
    json_data = commercial.json()
    db = pd.DataFrame(json_data['response']['data'])
    df = db[['period', 'value']]
    df.columns = ['Date', 'EIA_Prod_Supp']
    df.set_index('Date', drop=True, inplace=True)
    df = df.astype(int)
    df['Year'] = df.index.astype(str).str[:4]
    df['Month'] = df.index.astype(str).str[5:]
    df['Day'] = 1
    df['Date'] = pd.to_datetime(df[['Year', 'Month', 'Day']])
    df.set_index('Date', drop=True, inplace=True)
    df = df.drop(columns=['Year', 'Month', 'Day'])
    EIA_web = _missing_photo_text(183,
        f'https://api.eia.gov/v2/petroleum/pnp/pct/data/?api_key={EIA}&frequency=monthly&'
        f'data[0]=value&sort[0][column]=period&sort[0][direction]=desc&offset=0&length=5000&facets[se')
    STEO_yield = 'MGFRYP13'
    commercial = requests.get(EIA_web + STEO_yield, verify=False)
    json_data = commercial.json()
    db = pd.DataFrame(json_data['response']['data'])
    df_yield = db[['period', 'value']]
    df_yield.columns = ['Date', 'Yield']
    df_yield.set_index('Date', drop=True, inplace=True)
    df_yield['Year'] = df_yield.index.astype(str).str[:4]
    df_yield['Month'] = df_yield.index.astype(str).str[5:]
    df_yield['Day'] = 1
    df_yield['Date'] = pd.to_datetime(df_yield[['Year', 'Month', 'Day']])
    df_yield.set_index('Date', drop=True, inplace=True)
    df_yield = df_yield.drop(columns=['Year', 'Month', 'Day'])
    comp = pd.concat([df1, df], axis=1)
    comp['EIA_Prod_Supp'] = comp['EIA_Prod_Supp'].astype(float) / 10
    comp = comp.loc[comp.index > '2010-01-01']
    ovldata = bbg.bdh(
        ['DOEIGAS1 Index', 'DOEPBCP1 Index', 'DOETMGP1 Index', 'DOESGAS1 Index', 'DOEPFEP1 Index', 'DOEPCRP1 Index'],
        ['PX_LAST'], sdate, edate, elms=[("periodicityAdjustment", "ACTUAL")])
    ovldata.columns = ['Imports', 'MGBC', 'Total Production', 'Stocks', 'Demand', 'Runs']
    ovldata['Ref_Prod'] = ovldata['Total Production'] - ovldata['MGBC'] - ovldata['Demand']
    ovldata['Yield'] = ovldata['Ref_Prod'] / ovldata['Runs']
    datayield = ovldata['Yield']
    datayield = datayield.resample('M').mean()
    datayield.index = [dt.datetime(x.year, x.month, 1) for x in datayield.index.tolist()]
    ovldata['Demand'] = ovldata['Demand'] * 10
    ovldata['Total_Demand'] = ovldata['Demand'] + ovldata['MGBC']
    ovldata['Stock_change'] = ovldata['Stocks'].diff() / 7
    ovldata['Net_Receipts'] = ovldata['Stock_change'] - (
        ovldata['Total Production'] - ovldata['MGBC'] - ovldata['Demand']) - ovldata['Imports']
    weeklychange = ovldata.diff()
    fourweek = ovldata.rolling(4).mean()
    tbl = pd.DataFrame()
    tbl = ovldata.tail(4)
    tbl_loc = f'{html_path}\\oil\\mogas_weekly_balance\\Mogas_Balance.html'
    tbl_loc_td = _missing_photo_text(228, f'{html_path}\\oil\\mogas_weekly_balance\\Mogas_Balance_', edate, '%Y-%m')
    combined_loc = f'{html_path}\\oil\\mogas_weekly_combined.html'
    total_loc = f'{html_path}\\oil\\mogas_weekly_prior_tables.html'
    newdata = pd.read_csv(
        (f'https://api.energyaspects.com/data/timeseries/csv?api_key={os.environ["ENERGY_ASPECTS_API_KEY"]}&'
         'geography=US&frequency=weekly&category=crude_oil&aspect=runs'), sep=',')
    newdata = newdata.set_index('Date')
    newdata.index = pd.to_datetime(newdata.index)
    z = pd.merge(ovldata, newdata['US PADD_1 refinery weekly runs in kbbl_d'], left_on=ovldata.index,
                 right_index=True, how='outer', **_missing_photo_text(238, 'left_i'))
    z = z.set_index('key_0')
    z = pd.merge(z, demand_fcast['yhat'], left_on=z.index, right_on=demand_fcast.index, how='inner')
    z = z.set_index('key_0')
    z['Kpler_imports'] = p1_mogas['Total']
    z[['Canada', 'Europe', 'India', 'Brazil', 'Saudi Arabia']] = countries[
        ['Canada', 'Europe', 'India', 'Brazil', 'Saudi Arabia']]
    zavg = z.rolling(4).mean()
    zavgneed = zavg.loc[zavg.index == ovldata.index[-1]]
    z['Net_receipts_fcast'] = np.where(z.index > ovldata.index[-1], zavgneed['Net_Receipts'],
                                      z['Net_Receipts'].rolling(4).mean().shift(1))
    z['Canada_adj'] = np.where(z.index > ovldata.index[-1] + dt.timedelta(days=7), zavgneed.Canada, 0)
    z['EU_adj_2'] = np.where(z.index > ovldata.index[-1] + dt.timedelta(days=14), zavgneed.Europe, 0)
    z['EU_adj'] = z['EU_adj_2'] - z['Europe']
    z['EU_adj'] = np.where(z['EU_adj_2'] > 0, z['EU_adj_2'] - z['Europe'], 0)
    z['Kpler_Imports_adjusted'] = z['Kpler_imports'] + z['Canada_adj'] + z['EU_adj']
    z.rename(columns={'yhat': 'Demand_fcast', 'US PADD_1 refinery weekly runs in kbbl_d': 'Runs Fcast'}, inplace=True)
    z['Demand_fcast'] = z['Demand_fcast'] * 10
    z['MGBC_fcast'] = np.where(z.index > ovldata.index[-1], zavgneed['MGBC'], z['MGBC'].rolling(4).mean().shift(1))
    z['Total Production Fcast'] = np.where(z.index > ovldata.index[-1], zavgneed['Total Production'],
                                          z['Total Production'].rolling(4).mean().shift(1))
    z['Stock_change_fcast'] = z['Net_receipts_fcast'] + z['Kpler_Imports_adjusted'] + z['Total Production Fcast'] - (
        z['Demand_fcast'] + z['MGBC_fcast'])
    z['Stock_test'] = z['Stocks'].ffill()
    z['stock_adj'] = np.where(z['Stocks'].isnull(), z['Stock_change_fcast'] * 7, 0)
    z['stock_adj'] = z['stock_adj'].cumsum()
    z['Stock_fcast'] = z['Stock_test'] + z['stock_adj']
    displaydf = z.loc[ovldata.index[-1] - dt.timedelta(28):ovldata.index[-1] + dt.timedelta(28)]
    maindf = displaydf[
        ['Runs', 'Demand', 'Imports', 'Net_Receipts', 'Stocks', 'Stock_change', 'Runs Fcast', 'Demand_fcast',
         'Kpler_imports', 'Kpler_Imports_adjusted', 'Net_receipts_fcast', 'Stock_change_fcast', 'Stock_fcast']]
    maindf.index = maindf.index.strftime('%b-%d')
    maindf['Stocks'] = maindf['Stocks'] / 1000
    maindf['Stock_fcast'] = maindf['Stock_fcast'] / 1000
    maindf = maindf.reset_index()
    maindf = maindf.T
    new_header = maindf.iloc[0]
    maindf = maindf[1:]
    maindf.columns = new_header
    maindf = maindf.reset_index()
    maindf = maindf.fillna(value=np.nan)
    maindf_html = table.html_format(maindf, precision=0,
        format_column={
            'index': {'width': '120px', 'text-align': 'center'},
            tuple(maindf.columns[1:5]): {'width': '80px', 'text-align': 'center'},
            tuple(maindf.columns[7:]): {'width': '80px', 'text-align': 'center'},
            tuple(maindf.columns[5:7]): {'width': '80px', 'text-align': 'center', 'right_border': True},
        }, format_row={
            8: {'color': 'green', 'bold': True},
            (4, 5, 11, 12): {'format': '{:.2f}', 'columns': maindf.columns[1:]},
        })
    grphdata = z.loc[z.index > '01-01-2021']
    newdata = z.loc[z.index > '01-01-2022']
    figq = px.line(grphdata, x=grphdata.index, y=['Imports', 'Kpler_imports', 'Kpler_Imports_adjusted'],
                   title='Imports Kpler vs EIA')
    figq.update_traces(patch={'line': {'color': 'orange', 'width': 2, 'dash': 'dash'}},
                       selector={'legendgroup': 'Kpler_Imports_adjusted'})
    figs = px.line(grphdata, x=grphdata.index, y=['Stock_change', 'Stock_change_fcast'], title='Stock Change')
    figs.update_traces(patch={'line': {'color': 'orange', 'width': 2, 'dash': 'dot'}},
                       selector={'legendgroup': 'Stock_change_fcast'})
    figs2 = px.line(newdata, x=newdata.index, y=['Stocks', 'Stock_fcast'], title='Stocks')
    figs2.update_traces(patch={'line': {'color': 'red', 'width': 2}})
    figs2.update_traces(patch={'line': {'color': 'red', 'width': 2, 'dash': 'dot'}},
                        selector={'legendgroup': 'Stock_fcast'})
    errord = z.loc[z.index > '01-01-2022']
    errord = errord.cumsum()
    fige = px.line(errord, x=errord.index, y=['Stock_change', 'Stock_change_fcast'],
                   title='Cumulative v/s Stock Change')
    EIA_web = _missing_photo_text(316,
        f'https://api.eia.gov/v2/petroleum/move/ptb/data/?api_key={EIA}&frequency=monthly&'
        f'data[0]=value&sort[0][column]=period&sort[0][direction]=desc&offset=0&length=5000&facets[se')
    MGBC = 'MBCMXP1P31'
    commercial = requests.get(EIA_web + MGBC, verify=False)
    json_data = commercial.json()
    db = pd.DataFrame(json_data['response']['data'])
    mgbc = db[['period', 'value']]
    mgbc.columns = ['Date', 'p3_BC']
    mgbc.set_index('Date', drop=True, inplace=True)
    mgbc['Year'] = mgbc.index.astype(str).str[:4]
    mgbc['Month'] = mgbc.index.astype(str).str[5:]
    mgbc['Day'] = 1
    mgbc['Date'] = pd.to_datetime(mgbc[['Year', 'Month', 'Day']])
    mgbc.set_index('Date', drop=True, inplace=True)
    mgbc = mgbc.drop(columns=['Year', 'Month', 'Day'])
    FM = 'MGFMXP1P31'
    commercial = requests.get(EIA_web + FM, verify=False)
    json_data = commercial.json()
    db = pd.DataFrame(json_data['response']['data'])
    fm = db[['period', 'value']]
    fm.columns = ['Date', 'p3_FM']
    fm.set_index('Date', drop=True, inplace=True)
    fm['Year'] = fm.index.astype(str).str[:4]
    fm['Month'] = fm.index.astype(str).str[5:]
    fm['Day'] = 1
    fm['Date'] = pd.to_datetime(fm[['Year', 'Month', 'Day']])
    fm.set_index('Date', drop=True, inplace=True)
    fm = fm.drop(columns=['Year', 'Month', 'Day'])
    P2 = 'MBCMXP2P11'
    commercial = requests.get(EIA_web + P2, verify=False)
    json_data = commercial.json()
    db = pd.DataFrame(json_data['response']['data'])
    p2 = db[['period', 'value']]
    p2.columns = ['Date', 'p2_exp']
    p2.set_index('Date', drop=True, inplace=True)
    p2['Year'] = p2.index.astype(str).str[:4]
    p2['Month'] = p2.index.astype(str).str[5:]
    p2['Day'] = 1
    p2['Date'] = pd.to_datetime(p2[['Year', 'Month', 'Day']])
    p2.set_index('Date', drop=True, inplace=True)
    p2 = p2.drop(columns=['Year', 'Month', 'Day'])
    NR = pd.concat([fm, mgbc, p2], axis=1).astype(float)
    NR['Net_receipts'] = NR['p3_FM'] + NR['p3_BC'] - NR['p2_exp']
    NR['Net_receipts_kbd'] = NR['Net_receipts'] / NR.index.days_in_month
    NR['weekly'] = z['Net_Receipts'].resample('MS').mean()
    NRM = NR.Net_receipts_kbd.max()
    NRMin = NR.Net_receipts_kbd.min()
    NR = NR.loc[NR.index > '01-01-2019']
    Prodsup = df.loc[df.index >= '01-01-2019']
    Prodsup.index = Prodsup.index.to_period('M').to_timestamp('M')
    avg2019 = Prodsup.loc[Prodsup.index.year == 2019].mean()
    netr = ovldata.loc[ovldata.index > '01-01-2019']
    NR.index = NR.index.to_period('M').to_timestamp('M')
    test = px.line(netr, x=netr.index, y=['Net_Receipts'], title='Monthly v/s weekly Net Receipts')
    test.update_traces(line_color='rgb(251,180,174)', line_width=2)
    test.add_trace(go.Scatter(x=NR.index, y=NR['Net_receipts_kbd'], line_shape='hv', name='Monthly Data',
                              line=dict(color='black', width=3)))
    test.add_hline(y=NRM, line_width=1, line_color='grey')
    test.add_hline(y=NRMin, line_width=1, line_color='grey')
    test2 = px.line(netr, x=netr.index, y=['Demand'],
                    title=_missing_photo_text(387, 'Monthly (prod supp) v/s weekly (eth input) Dema'))
    test2.update_traces(line_color='purple', line_width=2)
    test2.add_trace(go.Scatter(x=Prodsup.index, y=Prodsup['EIA_Prod_Supp'], line_shape='hv', name='Monthly Data',
                               line=dict(color='red', width=3)))
    test2.add_hline(y=avg2019['EIA_Prod_Supp'], line_width=1, line_color='grey', name='2019 average demand')
    EIA_web = _missing_photo_text(394,
        f'https://api.eia.gov/v2/petroleum/sum/snd/data/?api_key={EIA}&frequency=monthly&'
        f'data[0]=value&sort[0][column]=period&sort[0][direction]=desc&offset=0&length=5000&facets[se')
    dem = 'MGFUPUS2'
    commercial = requests.get(EIA_web + dem, verify=False)
    json_data = commercial.json()
    db = pd.DataFrame(json_data['response']['data'])
    totdem = db[['period', 'value']]
    totdem.columns = ['Date', 'Total_Dem']
    totdem.set_index('Date', drop=True, inplace=True)
    totdem = totdem.astype(int)
    totdem['Year'] = totdem.index.astype(str).str[:4]
    totdem['Month'] = totdem.index.astype(str).str[5:]
    totdem['Day'] = 1
    totdem['Date'] = pd.to_datetime(totdem[['Year', 'Month', 'Day']])
    totdem.set_index('Date', drop=True, inplace=True)
    totdem = totdem.drop(columns=['Year', 'Month', 'Day'])
    totdem = totdem.loc[totdem.index > '2018-12-01']
    Demgas = bbg.bdh(['DOEPFETH Index', 'DOEDMGAS Index'], ['PX_LAST'], sdate, edate,
                     elms=[("periodicityAdjustment", "ACTUAL")])
    Demgas.columns = ['Weekly Ethanol implied demand', 'Weekly product supplied']
    Demgas['Weekly Ethanol implied demand'] = Demgas['Weekly Ethanol implied demand'] * 10
    Demgas = Demgas.resample('MS').mean()
    Demgas = Demgas.loc[Demgas.index > '2018-12-01']
    tot2019 = totdem.loc[totdem.index.year == 2019].mean()
    test3 = px.line(totdem, x=totdem.index, y=['Total_Dem'],
                    title='Monthly (prod supp) v/s weekly (eth input) Demand and Demand for total US')
    test3.update_traces(line_color='green', line_width=2)
    test3.add_trace(go.Scatter(x=Demgas.index, y=Demgas['Weekly Ethanol implied demand'],
                               name='Weekly Ethanol implied demand', line=dict(color='red', width=1)))
    test3.add_trace(go.Scatter(x=Demgas.index, y=Demgas['Weekly product supplied'],
                               name='Weekly product supplied', line=dict(color='orange', width=2)))
    test3.add_hline(y=tot2019['Total_Dem'], line_width=1, line_color='grey', name='2019 average demand')
    p2new = pd.DataFrame()
    p2new['y'] = p2['p2_exp'].astype(float) / p2.index.days_in_month
    p2new = p2new.loc[p2new.index > '2009-08-01']
    p2new.index.names = ['ds']
    p2new.index = pd.to_datetime(p2new.index)
    p2new = p2new.reset_index()
    hol = holidays.CountryHoliday('US', years=range(2000, 2031))['2000-01-01':'2030-12-31']
    df_holidays = pd.DataFrame({'holiday': 'US', 'ds': hol})
    m = Prophet(holidays=df_holidays)
    m.fit(p2new)
    future = m.make_future_dataframe(periods=12, freq='MS')
    future.tail()
    forecastp2 = m.predict(future)
    forecastp2.tail()
    fig1 = m.plot(forecastp2)
    fig2 = m.plot_components(forecastp2)
    forecastp2.set_index('ds', inplace=True)
    p2new.set_index('ds', inplace=True)
    p2_fcast = p2new.join(forecastp2[['yhat', 'yhat_lower', 'yhat_upper']], how='outer')
    table.figures_to_html([maindf_html], tbl_loc, task_name=report_name)
    table.figures_to_html([maindf_html, figure, figq, figs, figs2, test, test2, test3], combined_loc, task_name=report_name)
    table.figures_to_html([maindf_html, figure, figq, figs, figs2, test, test2, test3], tbl_loc_td, task_name=report_name)
    file_list = os.listdir(f"{html_path}\\oil\\mogas_weekly_balance")
    files = pd.DataFrame([file_list]).T
    files.columns = ['List of Prior files']
    files['List of Prior files'] = f'{html_path}\\oil\\mogas_weekly_balance\\' + files['List of Prior files'].astype(str)

    def make_clickable(val):
        return '<a href="{}">{}</a>'.format(val, val)

    testfiles = files.style.format(make_clickable)
    with open(total_loc, 'w') as f:
        f.write(testfiles.to_html())
    if send_to is not None and today().weekday() == 1:
        send_email(send_to=send_to, subject="Mogas Weekly Balance",
                   body=[maindf_html, fig1, figq, figs, figs2, test, test2, test3])


def update_disty():
    padd1 = dv.kpler(_missing_photo_text(477,
        '/v1/flows?toZones=padd%201&flowDirection=Import&split=Products&startDate=2019-01-01&granularity=eia'))
    padd1 = kpler.convert_to_ts(padd1)
    p1_disty = padd1[['Diesel', 'Gasoil', 'Gasoil/Diesel', 'Middle Distillates', 'LCO']]
    p1_disty['Total'] = p1_disty.sum(axis=1)
    EU = ['Netherlands', 'Belgium', 'France', 'Spain', 'UK', 'Italy']
    countries = dv.kpler(
        ('/v1/flows?toZones=padd%201&products=Diesel,Gasoil,Gasoil/Diesel,Middle Distillates,LCO&'
         'flowDirection=Import&split=Origin%20Countries&startDate=2019-01-01&granularity=eia-weekly&unit=kbd'))
    countries = kpler.convert_to_ts(countries)
    countries['Total'] = countries.sum(axis=1)
    try:
        countries['PG'] = countries[['Saudi Arabia', 'Kuwait', 'United Arab Emirates', 'Qatar', ]].sum(axis=1)
    except:
        countries['PG'] = countries[['Saudi Arabia', 'Kuwait', 'Qatar', ]].sum(axis=1)
    countries['Asia'] = countries[['South Korea', 'India']].sum(axis=1)
    countries['Europe'] = countries.isin(EU).sum(axis=1)
    countries_clean = dv.kpler(
        ('/v1/flows?toZones=padd%201&fromZones=Europe,Russia,Canada,Asia&flowDirection=Import&'
         'split=Origin%20Countries&startDate=2019-01-01&granularity=eia-weekly&unit=kbd&products=Clean%20Products'))
    countries_clean = kpler.convert_to_ts(countries_clean)
    countries_clean['Total'] = countries_clean.sum(axis=1)
    data = bbg.bdh(['PSM1PSFO Index'], ['PX_LAST'], dt.datetime(2010, 1, 1), today(),
                   elms=[("periodicityAdjustment", "ACTUAL")])
    data.index.names = ['ds']
    data.columns = ['y']
    data.index = pd.to_datetime(data.index)
    data = data.reset_index()
    hol = holidays.CountryHoliday('US', years=range(2000, 2031))['2000-01-01':'2030-12-31']
    df_holidays = pd.DataFrame({'holiday': 'US', 'ds': hol})
    m = Prophet(holidays=df_holidays)
    m.fit(data)
    future = m.make_future_dataframe(periods=24, freq='m')
    future.tail()
    forecast = m.predict(future)
    forecast.tail()
    fig1 = m.plot(forecast)
    fig2 = m.plot_components(forecast)
    forecast.set_index('ds', inplace=True)
    data.set_index('ds', inplace=True)
    demand_fcast = data.join(forecast[['yhat', 'yhat_lower', 'yhat_upper']], how='outer')
    test = demand_fcast[['y', 'yhat']]
    df1 = test.resample('M').mean()
    df1.index = [dt.datetime(x.year, x.month, 1) for x in df1.index.tolist()]
    copydata = df1.copy()
    copydata = copydata.resample('W-FRI')
    trace = go.Scatter(
        name='Actual Demand', mode='markers', x=list(data.index), y=list(data['y']),
        marker=dict(color='black', line=dict(width=1), size=3))
    trace1 = go.Scatter(
        name='Forecast', mode='lines', x=list(forecast.index), y=list(forecast['yhat']),
        marker=dict(color='#3bbed7', line=dict(width=3)))
    upperband = go.Scatter(
        x=forecast.index, y=forecast['yhat_upper'], fill='tonexty',
        fillcolor='rgb(175,238,238,0.1)', name='Confidence', hoverinfo='none', mode='none')
    lowerband = go.Scatter(
        x=forecast.index, y=forecast['yhat_lower'], marker={'color': 'rgba(0,0,0,0)'},
        showlegend=False, hoverinfo='none')
    datag = [lowerband, upperband, trace1, trace]
    figure = go.Figure(data=datag)
    py.offline.plot(figure, auto_open=False, filename="H:\\temp\\temp.html")
    EIA = dv.eia_api_key
    EIA_web = _missing_photo_text(579,
        f'https://api.eia.gov/v2/petroleum/sum/snd/data/?api_key={EIA}&frequency=monthly&'
        f'data[0]=value&sort[0][column]=period&sort[0][direction]=desc&offset=0&length=5000&facets')
    """
    Donwload data from EIA API
    """
    STEO_US = 'MDIUPUS2'
    STEO_P1 = 'MDIUPP12'
    STEO_P2 = 'MDIUPP22'
    STEO_P3 = 'MDIUPP32'
    STEO_P4 = 'MDIUPP42'
    STEO_P5 = 'MDIUPP52'
    commercial = requests.get(EIA_web + STEO_US, verify=False)
    commercial_p1 = requests.get(EIA_web + STEO_P1, verify=False)
    commercial_p2 = requests.get(EIA_web + STEO_P2, verify=False)
    commercial_p3 = requests.get(EIA_web + STEO_P3, verify=False)
    commercial_p4 = requests.get(EIA_web + STEO_P4, verify=False)
    commercial_p5 = requests.get(EIA_web + STEO_P5, verify=False)
    json_data = commercial.json()
    db = pd.DataFrame(json_data['response']['data'])
    json_data = db[['period', 'value']]
    json_data_p1 = commercial_p1.json()
    db = pd.DataFrame(json_data_p1['response']['data'])
    json_data_p1 = db[['period', 'value']]
    json_data_p2 = commercial_p2.json()
    db = pd.DataFrame(json_data_p2['response']['data'])
    json_data_p2 = db[['period', 'value']]
    json_data_p3 = commercial_p3.json()
    db = pd.DataFrame(json_data_p3['response']['data'])
    json_data_p3 = db[['period', 'value']]
    json_data_p4 = commercial_p4.json()
    db = pd.DataFrame(json_data_p4['response']['data'])
    json_data_p4 = db[['period', 'value']]
    json_data_p5 = commercial_p5.json()
    db = pd.DataFrame(json_data_p5['response']['data'])
    json_data_p5 = db[['period', 'value']]
    lst = [json_data, json_data_p1, json_data_p2, json_data_p3, json_data_p4, json_data_p5]
    data = ['US Prod Supplied', 'P1 Prod Supplied', 'P2 Prod Supplied', 'P3 Prod Supplied', 'P4 Prod Supplied',
            'P5 Prod Supplied', 'P5 Prod Supplied']
    df = pd.DataFrame()
    df_p1 = pd.DataFrame()
    df_p2 = pd.DataFrame()
    df_p3 = pd.DataFrame()
    df_p4 = pd.DataFrame()
    df_p5 = pd.DataFrame()
    df_t = {}
    for i in range(0, len(lst)):
        df_t[i] = lst[i]
        df_t[i].columns = ['Date', '{}'.format(data[i])]
        df_t[i].set_index('Date', drop=True, inplace=True)
        df_t[i]['Year'] = df_t[i].index.astype(str).str[:4]
        df_t[i]['Month'] = df_t[i].index.astype(str).str[5:]
        df_t[i]['Day'] = 1
        df_t[i]['Date'] = pd.to_datetime(df_t[i][['Year', 'Month', 'Day']])
        df_t[i].set_index('Date', drop=True, inplace=True)
        df_t[i] = df_t[i].drop(columns=['Year', 'Month', 'Day'])
    newdf = pd.concat(df_t, axis=1).astype(float)
    newdf = newdf.loc[newdf.index > '12-01-2009']
    newdf.columns = newdf.columns.droplevel()
    newdf['P1_ratio'] = newdf['P1 Prod Supplied'] / newdf['US Prod Supplied']
    p1_ratio = newdf['P1_ratio'].groupby(newdf.index.month).mean()
    EIA_web = _missing_photo_text(646,
        f'https://api.eia.gov/v2/petroleum/pnp/pct/data/?api_key={EIA}&frequency=monthly&'
        f'data[0]=value&sort[0][column]=period&sort[0][direction]=desc&offset=0&length=5000&facets')
    STEO_yield = 'MDIRYUS3'
    commercial = requests.get(EIA_web + STEO_yield, verify=False)
    json_data = commercial.json()
    db = pd.DataFrame(json_data['response']['data'])
    df_yield = db[['period', 'value']]
    df_yield.columns = ['Date', 'Yield']
    df_yield.set_index('Date', drop=True, inplace=True)
    df_yield['Year'] = df_yield.index.astype(str).str[:4]
    df_yield['Month'] = df_yield.index.astype(str).str[5:]
    df_yield['Day'] = 1
    df_yield['Date'] = pd.to_datetime(df_yield[['Year', 'Month', 'Day']])
    df_yield.set_index('Date', drop=True, inplace=True)
    df_yield = df_yield.drop(columns=['Year', 'Month', 'Day'])
    ovldata = bbg.bdh(['DOEIDIS1 Index', 'DOETDIP1 Index', 'DOESDIS1 Index', 'DOEDDIST Index', 'DOEPCRP1 Index'],
                     ['PX_LAST'], dt.datetime(2010, 1, 1), today(), elms=[("periodicityAdjustment", "ACTUAL")])
    ovldata.columns = ['Imports', 'Total Production', 'Stocks', 'Demand', 'Runs']
    ovldata['Yield'] = ovldata['Total Production'] / ovldata['Runs']
    ovldatanew = ovldata.reset_index().merge(p1_ratio, how='outer', left_on=ovldata.index.month,
                                            right_on=p1_ratio.index).set_index('date')
    ovldatanew = ovldatanew.drop(columns='key_0')
    ovldatanew['P1_demand'] = ovldatanew['Demand'] * ovldatanew['P1_ratio']
    ovldatanew = ovldatanew.sort_index()
    datayield = ovldata['Yield']
    datayield = datayield.resample('M').mean()
    datayield.index = [dt.datetime(x.year, x.month, 1) for x in datayield.index.tolist()]
    ovldatanew['Stock_change'] = ovldatanew['Stocks'].diff() / 7
    ovldatanew['Net_Receipts'] = ovldatanew['Stock_change'] - (
        ovldatanew['Total Production'] - ovldatanew['P1_demand']) - ovldata['Imports']
    weeklychange = ovldatanew.diff()
    fourweek = ovldatanew.rolling(4).mean()
    tbl = pd.DataFrame()
    tbl = ovldatanew.tail(4)
    tbl_loc = f'{html_path}\\oil\\disty_weekly_balance\\Disty_Balance.html'
    tbl_loc_td = _missing_photo_text(691, f'{html_path}\\oil\\disty_weekly_balance\\Disty_Balance', today(), '%Y-%')
    combined_loc = f'{html_path}\\oil\\disty_weekly_combined.html'
    total_loc = f'{html_path}\\oil\\disty_weekly_prior_tables.html'
    newdata = pd.read_csv(
        (f'https://api.energyaspects.com/data/timeseries/csv?api_key={ea_api_key}&geography=US&'
         'frequency=weekly&category=crude_oil&aspect=runs'), sep=',')
    newdata = newdata.set_index('Date')
    newdata.index = pd.to_datetime(newdata.index)
    z = pd.merge(ovldatanew, newdata['US PADD_1 refinery weekly runs in kbbl_d'], right_on=newdata.index,
                 left_index=True, right_index=False, how='outer')
    z = z.set_index('key_0')
    z.index = z.index.rename('Date')
    z['month'] = z.index.month
    z['year'] = z.index.year
    demand_fcast['month'] = demand_fcast.index.month
    demand_fcast['year'] = demand_fcast.index.year
    mergeddf = z.reset_index().merge(demand_fcast, on=['month', 'year'], how='left').set_index('Date')
    test = mergeddf.merge(p1_disty, left_index=True, right_index=True)
    test[['Canada', 'Europe', 'Asia', 'PG']] = countries[['Canada', 'Europe', 'Asia', 'PG']]
    zavg = test.rolling(4).mean()
    zavgneed = zavg.loc[zavg.index == ovldatanew.index[-1]]
    test['Net_receipts_fcast'] = np.where(test.index > ovldatanew.index[-1], zavgneed['Net_Receipts'],
                                         test['Net_Receipts'].rolling(4).mean().shift(1))
    test['Canada_adj'] = np.where(test.index > ovldatanew.index[-1] + dt.timedelta(days=7), zavgneed.Canada, 0)
    test['EU_adj_2'] = np.where(test.index > ovldatanew.index[-1] + dt.timedelta(days=14), zavgneed.Europe, 0)
    test['EU_adj'] = test['EU_adj_2'] - test['Europe']
    test['EU_adj'] = np.where(test['EU_adj_2'] > 0, test['EU_adj_2'] - test['Europe'], 0)
    test['Kpler_Imports_adjusted'] = test['Total'] + test['Canada_adj'] + test['EU_adj']
    test.rename(columns={'yhat': 'Demand_fcast', 'US PADD_1 refinery weekly runs in kbbl_d': 'Runs Fcast',
                         'Total': 'Kpler_Imports'}, inplace=True)
    test['Yield Fcast'] = np.where(test.index > ovldatanew.index[-1], zavgneed['Yield'],
                                  test['Yield'].rolling(4).mean().shift(1))
    test['Total Production Fcast'] = np.where(test.index > ovldatanew.index[-1],
                                             test['Yield Fcast'] * test['Runs Fcast'],
                                             test['Total Production'])
    test['Stock_change_fcast'] = test['Net_receipts_fcast'] + test['Kpler_Imports_adjusted'] + test[
        'Total Production Fcast'] - (test['Demand_fcast'])
    test['Stock_test'] = test['Stocks'].ffill()
    test['stock_adj'] = np.where(test['Stocks'].isnull(), test['Stock_change_fcast'] * 7, 0)
    test['stock_adj'] = test['stock_adj'].cumsum()
    test['Stock_fcast'] = test['Stock_test'] + test['stock_adj']
    displaydf = test.loc[ovldata.index[-1] - dt.timedelta(28):ovldata.index[-1] + dt.timedelta(28)]
    maindf = displaydf[
        ['Runs', 'Demand', 'Imports', 'Net_Receipts', 'Stocks', 'Stock_change', 'Runs Fcast', 'Demand_fcast',
         'Kpler_Imports', 'Kpler_Imports_adjusted', 'Net_receipts_fcast', 'Stock_change_fcast', 'Stock_fcast']]
    maindf.index = maindf.index.strftime('%b-%d')
    maindf = maindf.T
    maindf.index.name = 'Disty'
    maindf = maindf.reset_index()
    maindf_html = table.html_format(maindf, precision=0,
        format_column={
            'Disty': {'width': '100px', 'text-align': 'center'},
            tuple(maindf.columns[1:5]): {'width': '80px', 'text-align': 'center'},
            tuple(maindf.columns[7:]): {'width': '80px', 'text-align': 'center'},
            tuple(maindf.columns[5:7]): {'width': '80px', 'text-align': 'center', 'right_border': True},
        }, format_row={8: {'color': 'green', 'bold': True}})
    grphdata = test.loc[test.index > '01-01-2021']
    newdata = test.loc[test.index > '01-01-2022']
    figq = px.line(grphdata, x=grphdata.index, y=['Imports', 'Kpler_Imports', 'Kpler_Imports_adjusted'],
                   title='Imports Kpler vs EIA')
    figq.update_traces(patch={'line': {'color': 'orange', 'width': 2, 'dash': 'dash'}},
                       selector={'legendgroup': 'Kpler_Imports_adjusted'})
    figs = px.line(grphdata, x=grphdata.index, y=['Stock_change', 'Stock_change_fcast'], title='Stock Change')
    figs.update_traces(patch={'line': {'color': 'orange', 'width': 2, 'dash': 'dot'}},
                       selector={'legendgroup': 'Stock_change_fcast'})
    figs2 = px.line(newdata, x=newdata.index, y=['Stocks', 'Stock_fcast'], title='Stocks')
    figs2.update_traces(patch={'line': {'color': 'red', 'width': 2}})
    figs2.update_traces(patch={'line': {'color': 'red', 'width': 2, 'dash': 'dot'}},
                        selector={'legendgroup': 'Stock_fcast'})
    errord = test.loc[test.index > '01-01-2022']
    errord = errord.cumsum()
    fige = px.line(errord, x=errord.index, y=['Stock_change', 'Stock_change_fcast'],
                   title='Cumulative v/s Stock Change')
    table.figures_to_html([maindf_html], tbl_loc)
    table.figures_to_html([maindf_html], tbl_loc_td)
    EIA_web = _missing_photo_text(780,
        f'https://api.eia.gov/v2/petroleum/move/ptb/data/?api_key={EIA}&frequency=monthly&'
        f'data[0]=value&sort[0][column]=period&sort[0][direction]=desc&offset=0&length=5000&facets[s')
    MGBC = 'MDIMXP1P31'
    commercial = requests.get(EIA_web + MGBC, verify=False)
    json_data = commercial.json()
    db = pd.DataFrame(json_data['response']['data'])
    mgbc = db[['period', 'value']]
    mgbc.columns = ['Date', 'p3_BC']
    mgbc.set_index('Date', drop=True, inplace=True)
    mgbc['Year'] = mgbc.index.astype(str).str[:4]
    mgbc['Month'] = mgbc.index.astype(str).str[5:]
    mgbc['Day'] = 1
    mgbc['Date'] = pd.to_datetime(mgbc[['Year', 'Month', 'Day']])
    mgbc.set_index('Date', drop=True, inplace=True)
    mgbc = mgbc.drop(columns=['Year', 'Month', 'Day'])
    P2 = 'MDIMXP1P21'
    commercial = requests.get(EIA_web + P2, verify=False)
    json_data = commercial.json()
    db = pd.DataFrame(json_data['response']['data'])
    p2 = db[['period', 'value']]
    p2.columns = ['Date', 'p2_imp']
    p2.set_index('Date', drop=True, inplace=True)
    p2['Year'] = p2.index.astype(str).str[:4]
    p2['Month'] = p2.index.astype(str).str[5:]
    p2['Day'] = 1
    p2['Date'] = pd.to_datetime(p2[['Year', 'Month', 'Day']])
    p2.set_index('Date', drop=True, inplace=True)
    p2 = p2.drop(columns=['Year', 'Month', 'Day'])
    NR = pd.concat([mgbc, p2], axis=1).astype(float)
    NR['Net_receipts'] = NR['p3_BC'] + NR['p2_imp']
    NR['Net_receipts_kbd'] = NR['Net_receipts'] / NR.index.days_in_month
    NR['weekly'] = test['Net_Receipts'].resample('MS').mean()
    NRM = NR.Net_receipts_kbd.max()
    NRMin = NR.Net_receipts_kbd.min()
    NR = NR.loc[NR.index > '01-01-2019']
    Prodsup = newdf.loc[newdf.index >= '01-01-2019']
    Prodsup.index = Prodsup.index.to_period('M').to_timestamp('M')
    avg2019 = Prodsup.loc[Prodsup.index.year == 2019].mean()
    netr = test.loc[test.index > '01-01-2019']
    NR.index = NR.index.to_period('M').to_timestamp('M')
    testgr = px.line(netr, x=netr.index, y=['Net_Receipts'], title='Monthly v/s weekly Net Receipts')
    testgr.update_traces(line_color='rgb(251,180,174)', line_width=2)
    testgr.add_trace(go.Scatter(x=NR.index, y=NR['Net_receipts_kbd'], line_shape='hv', name='Monthly Data',
                                line=dict(color='black', width=3)))
    testgr.add_hline(y=NRM, line_width=1, line_color='grey')
    testgr.add_hline(y=NRMin, line_width=1, line_color='grey')
    testgr2 = px.line(netr, x=netr.index, y=['Demand_fcast'],
                      title=_missing_photo_text(834, 'Monthly (prod supp) v/s weekly Demand F'))
    testgr2.update_traces(line_color='purple', line_width=2)
    testgr2.add_trace(go.Scatter(x=Prodsup.index, y=Prodsup['P1 Prod Supplied'], line_shape='hv', name='Monthly Data',
                                 line=dict(color='red', width=3)))
    testgr2.add_hline(y=avg2019['P1 Prod Supplied'], line_width=1, line_color='grey', name='2019 average demand')
    table.figures_to_html([maindf_html, figure, figq, fige, figs2, testgr, testgr2], combined_loc)
    file_list = os.listdir(f"{html_path}\\oil\\disty_weekly_balance")
    files = pd.DataFrame([file_list]).T
    files.columns = ['List of Prior files']
    files['List of Prior files'] = f'{html_path}\\oil\\disty_weekly_balance\\' + files['List of Prior files'].astype(str)

    def make_clickable(val):
        return '<a href="{}">{}</a>'.format(val, val)

    testfiles = files.style.format(make_clickable)
    with open(total_loc, 'w') as f:
        f.write(testfiles.to_html())


def update(send_to):
    update_gasoline(send_to=send_to)
    update_disty()


if __name__ == '__main__':
    update(send_to=send_to)
