import pandas as pd
import numpy as np
import datetime as dt
import sys
import os

if sys.platform.startswith('win'):
    os.environ['GRPC_DEFAULT_SSL_ROOTS_FILE_PATH'] = 'C:\local\certs\root.crt'
    os.environ['REQUESTS_CA_BUNDLE'] = 'C:\local\certs\root.crt'
    os.environ['SSL_CERT_FILE'] = 'C:\local\certs\root.crt'

from dateutil.relativedelta import relativedelta
import ecm.cmds.data as dv
import ecm.cmds.kpler as kpler
import ecm.cmds.time_series as ts
import ecm.cmds.table as table
import ecm.cmds.chart as chart
import ecm.cmds.bbg as bbg
from ecm.cmds.config import root_path, csv_path, data_path
from ecm.cmds._email import send_email
from ecm.cmds.config import html_path
from ecm.cmds.cdr import today
from ecm.cmds.utils import convert_path_to_linux
from pyg_base import dt as pygdt
import ecm.cmds.vendor._platts as platts

send_to = ['mkikano@elementcapital.com', 'rzhao@elementcapital.com', 'ltrindade@elementcapital.com', 'lballand@elementcapital.com']
report_name = 'Global Product Inventory'
file_name = 'product_inventory'  # without .py
file_path = f'{root_path}\\autoreports\\reports\\oil\\{file_name}.py'


def _missing_photo_text(lines, *visible_fragments):
    raise NotImplementedError(f'Unrecoverable photograph text at source lines {lines}; see TRANSCRIPTION_NOTES.md')


def add_schedule():
    """
    # schedule to run the report - only need to run once
    """
    sys.path.append(f'{root_path}\\autoreports\\schedule')
    from tasks import WinTaskPoC
    from ecm.atom.wintask.scheduler import ECMWinTask
    from ecm.atom.wintask.utils import Days
    win_task = ECMWinTask(days=Days.THURSDAY, start_datetime=dt.datetime(2022, 7, 1, 17, 0), timezone='Europe/London',
                          task_name=report_name, task=WinTaskPoC(name=f'"{report_name}"', filepath=f'"{file_path}"'),
                          background_task=True, python_excecutable=r'C:\local\python\miniconda\envs\ecm_cmds\pythonw.exe')
    win_task.create_task()


ea_bbg_map = {
    '1530': 'ARASGSLN Index', '1531': 'ARASGO Index', '1532': 'ARASKERO Index', '1533': 'ARASNPHT Index',
    '1534': 'ARASFO Index', '1535': 'CUAAST Index', '1536': 'SPIVLDIS Index', '1537': 'SPIVMDIS Index',
    '1538': 'SPIVRESD Index', '1545': 'AALNX00', '1546': 'AAVPL00', '1547': 'AALQU00', '1548': 'AALNZ00',
    '1549': 'AALQU00', '1550': 'AALOF00', '1551': 'AAVQZ00', '1552': 'FUJLD04', '1553': 'FUJMD04', '1554': 'FUJHD04',
    '1555': '', '1556': 'DOESTMGS Index', '1557': 'DOESDIST Index', '1558': 'DOESJETK Index', '1559': 'DOESRESD Index',
    '1560': 'DOESESPR Index', '1561': 'DOESCRUD Index'}
base_link = f'{html_path}\\oil\\links\\stocks_change.html'
base_link_main = f'{html_path}\\oil\\{file_name}.html'
name_to_stock_chg_chart_link = {
    'Land': f"<a href='{base_link}#liquid_land'>Land</a>",
    'Water': f"<a href='{base_link}#liquid_water'>Water</a>",
    'Land+Water': f"<a href='{base_link_main}#liquids'>Land+Water</a>",
    'Crude On Land': f"<a href='{base_link}#crude_land'>Crude On Land</a>",
    'Crude On Water': f"<a href='{base_link}#crude_water'>Crude On Water</a>",
    'United States': f"<a href='{base_link}#nam_level'>United States</a>",
    'Europe': f"<a href='{base_link}#eu_level'>Europe</a>",
    'Atlantic Basin (US+EU)': f"<a href='{base_link}#ab_level'>Atlantic Basin (US+EU)</a>",
    'SA,Egypt,Caribbean': f"<a href='{base_link}#other_level'>SA,Egypt,Caribbean</a>",
    'Asia': f"<a href='{base_link}#asia_level'>Asia</a>",
    'China': f"<a href='{base_link}#china_level'>China</a>"}


def crude_inventory():
    spr = dv.kpler(link='/v1/inventories?zones=US&startDate=2017-01-01&split=byTankType')
    crude_on_water = dv.kpler(link=('/v1/fleet-metrics?metric=loaded_vessels&zones=world&period=daily&'
                                    'startDate=2017-01-01&unit=kb&products=crude%2fco'))
    global_land = dv.kpler(link='/v1/inventories?zones=World&startDate=2017-01-01&period=daily&split=total')
    asian_stocks = dv.kpler(link=('/v1/inventories?zones=China,India,Korea,Japan,Indonesia,Taiwan,Thailand&'
                                 'startDate=2017-01-01&period=daily&split=byCountry'))
    eu_stocks = dv.kpler(link=('/v1/inventories?zones=Netherlands,France,Germany,Italy,Spain,United%20Kingdom&'
                              'startDate=2017-01-01&period=daily&split=byCountry'))
    nam_stocks = dv.kpler(link='/v1/inventories?zones=United%20States,Canada&startDate=2017-01-01&period=daily&split=byCountry')
    other_ab_stocks = dv.kpler(link=('/v1/inventories?zones=South%20Africa,Egypt,Caribbean%20Islands&'
                                    'startDate=2017-01-01&period=daily&split=byCountry'))
    spr.to_csv(convert_path_to_linux(f"{data_path}\\kpler\\spr_{dt.datetime.now().strftime('%Y%m%d%H%M%S')}.csv"))
    global_land.to_csv(convert_path_to_linux(f"{data_path}\\kpler\\global_land_{dt.datetime.now().strftime('%Y%m%d%H%M%S')}.csv"))
    spr = kpler.convert_to_ts(kpler_links=spr, columns=['SPR'], end_dt='-1d')
    global_land = kpler.convert_to_ts(kpler_links=global_land, columns=['Crude On Land'],
                                      rename={'Level (kb)': 'Crude On Land'}, end_dt='-1d')
    crude_on_water = kpler.convert_to_ts(kpler_links=crude_on_water, columns=['Crude On Water'],
                                         rename={'Total': 'Crude On Water'}, end_dt='-1d')
    crude_on_water.to_csv(convert_path_to_linux(f"{csv_path}\\oil\\kpler\\crude_on_water_{dt.datetime.now().strftime('%Y%m%d%H%M%S')}.csv"))
    global_crude = ts.sum_dfs(dfs=[spr, global_land, crude_on_water])
    global_crude['Crude On Land'] = global_crude['Crude On Land'] - global_crude['SPR']
    global_crude['Total'] = global_crude['Crude On Land'] + global_crude['Crude On Water']
    global_crude['Total (kbd)'] = global_crude['Total'].diff()
    global_crude.drop(['SPR'], axis=1, inplace=True)
    asian_stocks = kpler.convert_to_ts(asian_stocks, rename={'Level (kb)': 'Asia'}, end_dt='-1d',
                                       drop_column=['Zone', 'Installation', 'Local Supply (kbd)', 'Local Demand (kbd)',
                                                    'Cargoes (kbd)', 'Capacity (kb)', 'Relative Fill Level', 'Country',
                                                    'Continent', 'Revisit Rate', 'Last Image'])
    asian_stocks['Asia (kbd)'] = asian_stocks['Asia'].diff()
    asian_stocks = asian_stocks[['China', 'India', 'Indonesia', 'Japan', 'South Korea', 'Taiwan', 'Thailand', 'Asia', 'Asia (kbd)']]
    global_crude_exch = ts.sum_dfs(dfs=[spr, global_land, crude_on_water, asian_stocks[['China']]])
    global_crude_exch['Crude On Land'] = global_crude_exch['Crude On Land'] - global_crude_exch['SPR'] - global_crude_exch['China']
    global_crude_exch['Total'] = global_crude_exch['Crude On Land'] + global_crude_exch['Crude On Water']
    global_crude_exch['Total (kbd)'] = global_crude_exch['Total'].diff()
    global_crude_exch.drop(['SPR', 'China'], axis=1, inplace=True)
    eu_stocks = kpler.convert_to_ts(eu_stocks, rename={'Level (kb)': 'Europe'}, end_dt='-1d',
                                    drop_column=['Zone', 'Installation', 'Local Supply (kbd)', 'Local Demand (kbd)',
                                                 'Cargoes (kbd)', 'Capacity (kb)', 'Relative Fill Level', 'Country',
                                                 'Continent', 'Revisit Rate', 'Last Image'])
    eu_stocks['Europe (kbd)'] = eu_stocks['Europe'].diff()
    eu_stocks = eu_stocks[['France', 'Germany', 'Italy', 'Netherlands', 'Spain', 'United Kingdom', 'Europe', 'Europe (kbd)']]
    nam_stocks = kpler.convert_to_ts(nam_stocks, rename={'Level (kb)': 'Americas'}, end_dt='-1d',
                                     drop_column=['Zone', 'Installation', 'Local Supply (kbd)', 'Local Demand (kbd)',
                                                  'Cargoes (kbd)', 'Capacity (kb)', 'Relative Fill Level', 'Country',
                                                  'Continent', 'Revisit Rate', 'Last Image'])
    nam_stocks['United States'] = nam_stocks['United States'] - spr['SPR']
    nam_stocks['Americas'] = nam_stocks['Americas'] - spr['SPR']
    nam_stocks['Americas (kbd)'] = nam_stocks['Americas'].diff()
    nam_stocks = nam_stocks[['Canada', 'United States', 'Americas', 'Americas (kbd)']]
    other_ab_stocks = kpler.convert_to_ts(other_ab_stocks, rename={'Level (kb)': 'SA,Egypt,Caribbean'}, end_dt='-1d',
                                          drop_column=['Zone', 'Installation', 'Local Supply (kbd)', 'Local Demand (kbd)',
                                                       'Cargoes (kbd)', 'Capacity (kb)', 'Relative Fill Level', 'Country',
                                                       'Continent', 'Revisit Rate', 'Last Image'])
    ab_stocks = pd.concat([nam_stocks['United States'], eu_stocks['Europe'], other_ab_stocks['SA,Egypt,Caribbean']], axis=1)
    ab_stocks.columns = ['United States', 'Europe', 'SA,Egypt,Caribbean']
    ab_stocks['Atlantic Basin (US+EU)'] = ab_stocks[['United States', 'Europe']].sum(axis=1)
    ab_stocks['Atlantic Basin (kbd)'] = ab_stocks['Atlantic Basin (US+EU)'].diff()
    return global_crude, global_crude_exch, eu_stocks, nam_stocks, asian_stocks, ab_stocks


def product_on_water():
    clean_on_water = dv.kpler(link='/v1/fleet-metrics?metric=loaded_vessels&products=Clean%20Products&period=daily&unit=kb')
    clean_on_water = kpler.convert_to_ts(kpler_links=clean_on_water, columns=['Clean Oil On Water'],
                                         end_dt=_missing_photo_text('192'), rename={'Total': 'Clean Oil On Water'})
    clean_on_water.to_csv(convert_path_to_linux(f"{csv_path}\\oil\\kpler\\clean_on_water_{dt.datetime.now().strftime('%Y%m%d%H%M%S')}.csv"))
    return clean_on_water


def product_inventory_old_old():
    product_stocks = dv.energy_aspects(
        dataset_id=('1530,1531,1532,1533,1534,1535,1536,1537,1538,1539,1540,1541,1542,1543,1544,'
                    '1545,1546,1547,1548,1549,1550,1551,1552,1553,1554,1555,1556,1557,1558,1559,1560,1561'), start='2017-01-01')
    product_stocks = kpler.convert_to_ts(kpler_links=product_stocks, columns=None, rename=None,
                                         drop_column=['Weekly Mexico diesel inventories in kbbl',
                                                      'Weekly Mexico fuel oil inventories in kbbl',
                                                      'Weekly Mexico gasoline inventories in kbbl',
                                                      'Weekly Mexico jet fuel inventories in kbbl',
                                                      'Weekly Mexico total diesel storage in kbbl',
                                                      'Weekly Mexico total gasoline storage in kbbl'])
    product_stocks.rename(columns={'Weekly total product inventories for Fujairah in Mbbl': 'Fujairah'}, inplace=True)
    product_stocks['Weekly gasoline inventories for ARA in kt'] = product_stocks['Weekly gasoline inventories for ARA in kt'] * 8.33
    product_stocks['Weekly jet fuel inventories for ARA in kt'] = product_stocks['Weekly jet fuel inventories for ARA in kt'] * 7.878
    product_stocks['Weekly middle distillate inventories for ARA in kt'] = product_stocks['Weekly middle distillate inventories for ARA in kt'] * 7.45
    product_stocks['Weekly fuel oil inventories for ARA in kt'] = product_stocks['Weekly fuel oil inventories for ARA in kt'] * 7.45
    product_stocks['ARA'] = (product_stocks['Weekly gasoline inventories for ARA in kt'] +
        product_stocks['Weekly jet fuel inventories for ARA in kt'] +
        product_stocks['Weekly middle distillate inventories for ARA in kt'] +
        product_stocks['Weekly fuel oil inventories for ARA in kt'])
    product_stocks['Weekly fuel oil inventories in Singapore in Mbbl'] = product_stocks['Weekly fuel oil inventories in Singapore in Mbbl'] * 1000
    product_stocks['Weekly light distillates inventories in Singapore in Mbbl'] = product_stocks['Weekly light distillates inventories in Singapore in Mbbl'] * 1000
    product_stocks['Weekly middle distillates inventories in Singapore in Mbbl'] = product_stocks['Weekly middle distillates inventories in Singapore in Mbbl'] * 1000
    product_stocks['Singapore'] = (product_stocks['Weekly fuel oil inventories in Singapore in Mbbl'] +
        product_stocks['Weekly light distillates inventories in Singapore in Mbbl'] +
        product_stocks['Weekly middle distillates inventories in Singapore in Mbbl'])
    product_stocks['Weekly jet fuel inventories for Japan in kl'] = product_stocks['Weekly jet fuel inventories for Japan in kl'] / 158.987567172247
    try:
        product_stocks['Weekly kerosene inventories for Japan in kl'] = product_stocks['Weekly kerosene inventories for Japan in kl'] / 158.987567172247
    except:
        product_stocks['Weekly kerosene inventories for Japan in kl'] = product_stocks['Weekly kerosene stock level in Japan in kl '] / 158.987567172247
    try:
        product_stocks['Weekly naphtha inventories for Japan in kl'] = product_stocks['Weekly naphtha inventories for Japan in kl'] / 158.987567172247
    except:
        product_stocks['Weekly naphtha inventories for Japan in kl'] = product_stocks['Weekly naphtha stock level in Japan in kl '] / 158.987567172247
    try:
        product_stocks['Weekly gasoline inventories for Japan in kl'] = product_stocks['Weekly gasoline inventories for Japan in kl'] / 158.987567172247
    except:
        product_stocks['Weekly gasoline inventories for Japan in kl'] = product_stocks['Weekly gasoline stock level in Japan in kl '] / 158.987567172247
    product_stocks['Weekly diesel inventories for Japan in kl'] = product_stocks['Weekly diesel inventories for Japan in kl'] / 158.987567172247
    product_stocks['Weekly fuel oil inventories for Japan in Mbbl'] = product_stocks['Weekly fuel oil inventories for Japan in Mbbl'] * 1000
    product_stocks['Japan'] = (product_stocks['Weekly jet fuel inventories for Japan in kl'] +
        product_stocks['Weekly kerosene inventories for Japan in kl'] +
        product_stocks['Weekly naphtha inventories for Japan in kl'] +
        product_stocks['Weekly gasoline inventories for Japan in kl'] +
        product_stocks['Weekly diesel inventories for Japan in kl'] +
        product_stocks['Weekly fuel oil inventories for Japan in Mbbl'])
    product_stocks['Fujairah'] = product_stocks['Fujairah'] * 1000
    product_stocks['US'] = (product_stocks['Weekly diesel inventories for US in kbbl'] +
        product_stocks['Weekly gasoline inventories for US in kbbl'] +
        product_stocks['Weekly jet fuel inventories for US in kbbl'] +
        product_stocks['Weekly residual fuel oil inventories for US in kbbl'])
    product_stocks['US Other'] = product_stocks['Weekly total product inventories for US in kbbl'] - product_stocks['Weekly crude inventories for US in kbbl'] - product_stocks['US']
    product_by_loc = product_stocks[['US', 'US Other', 'ARA', 'Japan', 'Singapore', 'Fujairah']]
    product_stocks_fill = product_stocks.copy()
    product_stocks_fill = product_stocks_fill.reindex(pd.date_range(product_stocks_fill.index[0], product_stocks_fill.index[-1]))
    product_stocks_fill.fillna(method='ffill', inplace=True)
    product_stocks_fill['Distillate'] = (product_stocks_fill['Weekly middle distillate inventories for ARA in kt'] +
        product_stocks_fill['Weekly jet fuel inventories for ARA in kt'] +
        product_stocks_fill['Weekly middle distillates inventories in Singapore in Mbbl'] +
        product_stocks_fill['Weekly jet fuel inventories for Japan in kl'] +
        product_stocks_fill['Weekly kerosene inventories for Japan in kl'] +
        product_stocks_fill['Weekly diesel inventories for Japan in kl'] +
        product_stocks_fill['Weekly middle distillate inventories for Fujairah in Mbbl'] * 1000 +
        product_stocks_fill['Weekly diesel inventories for US in kbbl'] +
        product_stocks_fill['Weekly jet fuel inventories for US in kbbl'])
    product_stocks_fill['Light Ends'] = (product_stocks_fill['Weekly naphtha inventories for ARA in kt'] +
        product_stocks_fill['Weekly gasoline inventories for ARA in kt'] +
        product_stocks_fill['Weekly naphtha inventories for Japan in kl'] +
        product_stocks_fill['Weekly gasoline inventories for Japan in kl'] +
        product_stocks_fill['Weekly light distillates inventories in Singapore in Mbbl'] +
        product_stocks_fill['Weekly light distillates inventories for Fujairah in Mbbl'] * 1000 +
        product_stocks_fill['Weekly gasoline inventories for US in kbbl'])
    product_stocks_fill['Fuel Oil'] = (product_stocks_fill['Weekly fuel oil inventories for ARA in kt'] +
        product_stocks_fill['Weekly fuel oil inventories in Singapore in Mbbl'] +
        product_stocks_fill['Weekly fuel oil inventories for Japan in Mbbl'] +
        product_stocks_fill['Weekly residual and heavy distillates inventories for Fujairah in Mbbl'] * 1000 +
        product_stocks_fill['Weekly residual fuel oil inventories for US in kbbl'])
    return product_by_loc, product_stocks_fill[['Distillate', 'Light Ends', 'Fuel Oil']]


def product_inventory_old():
    product_stocks = dv.energy_aspects(
        dataset_id=('1530,1531,1532,1533,1534,1535,1536,1537,1538,1539,1540,1541,1542,1543,1544,'
                    '1545,1546,1547,1548,1549,1550,1551,1552,1553,1554,1555,1556,1557,1558,1559,1560,1561'), start='2017-01-01')
    product_stocks = kpler.convert_to_ts(kpler_links=product_stocks, columns=None, rename=None,
                                         drop_column=['Weekly diesel inventories in Mexico in kb',
                                                      'Weekly fuel oil inventories in Mexico in kb',
                                                      'Weekly gasoline inventories in Mexico in kb',
                                                      'Weekly jet/kero inventories in Mexico in kb'])
    product_stocks.rename(columns={'Weekly total product inventories for Fujairah in Mbbl': 'Fujairah'}, inplace=True)
    product_stocks['Weekly gasoline inventories in ARA in kt'] = product_stocks['Weekly gasoline inventories in ARA in kt'] * 8.33
    product_stocks['Weekly jet/kero inventories for ARA in kt'] = product_stocks['Weekly jet/kero inventories in ARA in kt'] * 7.878
    product_stocks['Weekly middle distillate inventories in ARA in kt'] = product_stocks['Weekly middle distillate inventories in ARA in kt'] * 7.45
    product_stocks['Weekly fuel oil inventories in ARA in kt'] = product_stocks['Weekly fuel oil inventories in ARA in kt'] * 7.45
    product_stocks['ARA'] = (product_stocks['Weekly gasoline inventories in ARA in kt'] +
        product_stocks['Weekly jet/kero inventories in ARA in kt'] +
        product_stocks['Weekly middle distillate inventories in ARA in kt'] +
        product_stocks['Weekly fuel oil inventories in ARA in kt'])
    product_stocks['Weekly fuel oil inventories in Singapore in Mb'] = product_stocks['Weekly fuel oil inventories in Singapore in Mb'] * 1000
    product_stocks['Weekly light distillate inventories in Singapore in Mb'] = product_stocks['Weekly light distillate inventories in Singapore in Mb'] * 1000
    product_stocks['Weekly middle distillates inventories in Singapore in Mb'] = product_stocks['Weekly middle distillates inventories in Singapore in Mb'] * 1000
    product_stocks['Singapore'] = (product_stocks['Weekly fuel oil inventories in Singapore in Mb'] +
        product_stocks['Weekly light distillate inventories in Singapore in Mb'] +
        product_stocks['Weekly middle distillates inventories in Singapore in Mb'])
    product_stocks['Weekly jet/kero inventories in Japan in kl'] = product_stocks['Weekly jet/kero inventories in Japan in kl'] / 158.987567172247
    product_stocks['Weekly kerosene inventories in Japan in kl'] = product_stocks['Weekly kerosene inventories in Japan in kl '] / 158.987567172247
    product_stocks['Weekly naphtha inventories in Japan in kl'] = product_stocks['Weekly naphtha inventories in Japan in kl '] / 158.987567172247
    product_stocks['Weekly gasoline inventories in Japan in kl'] = product_stocks['Weekly gasoline inventories in Japan in kl '] / 158.987567172247
    product_stocks['Weekly diesel inventories in Japan in kl'] = product_stocks['Weekly diesel inventories in Japan in kl'] / 158.987567172247
    product_stocks['Weekly fuel oil inventories in Japan in mb'] = product_stocks['Weekly fuel oil inventories in Japan in mb'] * 1000
    product_stocks['Japan'] = (product_stocks['Weekly jet/kero inventories in Japan in kl'] +
        product_stocks['Weekly kerosene inventories in Japan in kl'] +
        product_stocks['Weekly naphtha inventories in Japan in kl'] +
        product_stocks['Weekly gasoline inventories in Japan in kl'] +
        product_stocks['Weekly diesel inventories in Japan in kl'] +
        product_stocks['Weekly fuel oil inventories in Japan in mb'])
    product_stocks['Fujairah'] = product_stocks['Weekly total product inventories in Fujairah in Mb'] * 1000
    product_stocks['US'] = (product_stocks['Weekly diesel inventories in United States in kb'] +
        product_stocks['Weekly gasoline inventories in United States in kb'] +
        product_stocks['Weekly jet/kero inventories in United States in kb'] +
        product_stocks['Weekly residual fuel oil inventories in United States in kb'])
    product_stocks['US Other'] = product_stocks['Weekly total product inventories in United States in kb'] - product_stocks['Weekly crude oil inventories in United States in kb'] - product_stocks['US']
    product_by_loc = product_stocks[['US', 'US Other', 'ARA', 'Japan', 'Singapore', 'Fujairah']]
    product_stocks_fill = product_stocks.copy()
    product_stocks_fill = product_stocks_fill.reindex(pd.date_range(product_stocks_fill.index[0], product_stocks_fill.index[-1]))
    product_stocks_fill.fillna(method='ffill', inplace=True)
    product_stocks_fill['Distillate'] = (product_stocks_fill['Weekly middle distillate inventories in ARA in kt'] +
        product_stocks_fill['Weekly jet/kero inventories in ARA in kt'] +
        product_stocks_fill['Weekly middle distillates inventories in Singapore in Mb'] +
        product_stocks_fill['Weekly jet/kero inventories in Japan in kl'] +
        product_stocks_fill['Weekly kerosene inventories in Japan in kl'] +
        product_stocks_fill['Weekly diesel inventories in Japan in kl'] +
        product_stocks_fill['Weekly middle distillate inventories in Fujairah in Mb'] * 1000 +
        product_stocks_fill['Weekly diesel inventories in United States in kb'] +
        product_stocks_fill['Weekly jet/kero inventories in United States in kb'])
    product_stocks_fill['Light Ends'] = (product_stocks_fill['Weekly naphtha inventories in ARA in kt'] +
        product_stocks_fill['Weekly gasoline inventories in ARA in kt'] +
        product_stocks_fill['Weekly naphtha inventories in Japan in kl'] +
        product_stocks_fill['Weekly gasoline inventories in Japan in kl'] +
        product_stocks_fill['Weekly light distillate inventories in Singapore in Mb'] +
        product_stocks_fill['Weekly light distillates inventories in Fujairah in Mb'] * 1000 +
        product_stocks_fill['Weekly gasoline inventories in United States in kb'])
    product_stocks_fill['Fuel Oil'] = (product_stocks_fill['Weekly fuel oil inventories in ARA in kt'] +
        product_stocks_fill['Weekly fuel oil inventories in Singapore in Mb'] +
        product_stocks_fill['Weekly fuel oil inventories in Japan in mb'] +
        product_stocks_fill['Weekly residual and heavy distillates inventories in Fujairah in Mb'] * 1000 +
        product_stocks_fill['Weekly residual fuel oil inventories in United States in kb'])
    return product_by_loc, product_stocks_fill[['Distillate', 'Light Ends', 'Fuel Oil']]


def get_platts(ticker, sdate, edate):
    df = platts.get_market_data(ticker, start_date=sdate, end_date=edate)
    df = df[['assessDate', 'value']]
    df.set_index('assessDate', inplace=True)
    df.index = pd.to_datetime(df.index)
    df.columns = ['PX_LAST']
    return df


def product_inventory():
    product_stocks_ara = bbg.bdh(['ARASGO Index', 'ARASKERO Index', 'ARASGSLN Index', 'ARASNPHT Index', 'ARASFO Index'],
                                ['PX_LAST'], sdate=dt.datetime(2017, 1, 1), edate=today())
    ara_out = product_stocks_ara.copy()
    ara_out.columns = ['Gasoil', 'Jet', 'Gasoline', 'Naphtha', 'Fuel Oil']
    product_stocks_sing = bbg.bdh(['SPIVLDIS Index', 'SPIVMDIS Index', 'SPIVRESD Index'], ['PX_LAST'],
                                 sdate=dt.datetime(2017, 1, 1), edate=today())
    product_stocks_us = bbg.bdh(['DOESTMGS Index', 'DOESDIST Index', 'DOESJETK Index', 'DOESRESD Index',
                                'DOESESPR Index', 'DOESCRUD Index'], ['PX_LAST'], sdate=dt.datetime(2017, 1, 1), edate=today())
    jp_gasoline = get_platts('AALNX00', sdate=dt.datetime(2017, 1, 1), edate=today())
    jp_naphtha = pd.DataFrame(0.0, index=jp_gasoline.index, columns=['PX_LAST'])
    jp_jet = get_platts('AALQU00', sdate=dt.datetime(2017, 1, 1), edate=today())
    jp_diesel = get_platts('AALNZ00', sdate=dt.datetime(2017, 1, 1), edate=today())
    jp_kero = get_platts('AALQU00', sdate=dt.datetime(2017, 1, 1), edate=today())
    jp_fo = get_platts('AALOF00', sdate=dt.datetime(2017, 1, 1), edate=today())
    fuj_light = get_platts('FUJLD04', sdate=dt.datetime(2017, 1, 1), edate=today())
    fuj_middle = get_platts('FUJMD04', sdate=dt.datetime(2017, 1, 1), edate=today())
    fuj_res = get_platts('FUJHD04', sdate=dt.datetime(2017, 1, 1), edate=today())
    product_stocks_ara['ARASNPHT Index'] = product_stocks_ara['ARASNPHT Index'] * 8.9
    product_stocks_ara['ARASGSLN Index'] = product_stocks_ara['ARASGSLN Index'] * 8.33
    product_stocks_ara['ARASKERO Index'] = product_stocks_ara['ARASKERO Index'] * 7.878
    product_stocks_ara['ARASGO Index'] = product_stocks_ara['ARASGO Index'] * 7.45
    product_stocks_ara['ARASFO Index'] = product_stocks_ara['ARASFO Index'] * 7.45
    jp_gasoline /= 1000
    jp_naphtha /= 1000
    jp_jet /= 1000
    jp_diesel /= 1000
    jp_kero /= 1000
    jp_fo /= 1000
    product_ara = product_stocks_ara[['ARASGSLN Index', 'ARASGO Index', 'ARASKERO Index', 'ARASFO Index']].sum(axis=1)
    product_sing = product_stocks_sing.sum(axis=1)
    product_fuj = fuj_light + fuj_middle + fuj_res
    product_jp = jp_gasoline + jp_naphtha + jp_jet + jp_diesel + jp_kero + jp_fo
    product_us = product_stocks_us[['DOESTMGS Index', 'DOESDIST Index', 'DOESJETK Index', 'DOESRESD Index']].sum(axis=1)
    product_us_other = product_stocks_us['DOESESPR Index'] - product_stocks_us['DOESCRUD Index'] - product_us
    product_by_loc = pd.concat([product_us, product_us_other, product_ara, product_jp, product_sing, product_fuj], axis=1)
    product_by_loc.columns = ['US', 'US Other', 'ARA', 'Japan', 'Singapore', 'Fujairah']
    dts = pd.date_range(dt.datetime(2017, 1, 1), today() - dt.timedelta(1))
    product_light = pd.concat([product_stocks_ara[['ARASGSLN Index', 'ARASNPHT Index']].sum(axis=1),
                               jp_gasoline, jp_naphtha, fuj_light, product_stocks_sing['SPIVLDIS Index'],
                               product_stocks_us['DOESTMGS Index']], axis=1)
    product_light = product_light.reindex(dts).fillna(method='ffill').sum(axis=1)
    product_middle = pd.concat([product_stocks_ara[['ARASGO Index', 'ARASKERO Index']].sum(axis=1),
                                jp_diesel, jp_jet, jp_kero, fuj_middle, product_stocks_sing['SPIVMDIS Index'],
                                product_stocks_us[['DOESDIST Index', 'DOESJETK Index']].sum(axis=1)], axis=1)
    product_middle = product_middle.reindex(dts).fillna(method='ffill').sum(axis=1)
    product_fo = pd.concat([product_stocks_ara['ARASFO Index'], jp_fo, fuj_res, product_stocks_sing['SPIVRESD Index'],
                            product_stocks_us['DOESRESD Index']], axis=1)
    product_fo = product_fo.reindex(dts).fillna(method='ffill').sum(axis=1)
    product_by_type = pd.concat([product_middle, product_light, product_fo], axis=1)
    product_by_type.columns = ['Distillate', 'Light Ends', 'Fuel Oil']
    return product_by_loc.reindex(dts), product_by_type, ara_out


def update(send_to):
    product_water = product_on_water()
    product_land, product_by_type, ara = product_inventory()
    ara_daily = ara.reindex(pd.date_range(dt.datetime(2017, 1, 1), today())).fillna(method='ffill')
    product_last_update = ts.last_valid_index(product_land, index_name='Product Land', column_name='Last Update', dt2str='%Y-%m-%d')
    product_stocks = pd.concat([product_land, product_water], axis=1)
    product_stocks.fillna(method='ffill', inplace=True)
    product_by_type = product_by_type.reindex(product_stocks.index)
    product_by_type.fillna(method='ffill', inplace=True)
    product_stocks['Land Stocks'] = product_stocks[['ARA', 'US', 'US Other', 'Japan', 'Singapore', 'Fujairah']].sum(axis=1)
    product_stocks['Land Stocks ex US Other'] = product_stocks[['ARA', 'US', 'Japan', 'Singapore', 'Fujairah']].sum(axis=1)
    product_stocks['Total Prods'] = product_stocks['Land Stocks ex US Other'] + product_stocks['Clean Oil On Water']
    product_stocks['Total Prods (kbd)'] = product_stocks['Total Prods'].diff()
    product_land_fill = product_stocks[['US', 'US Other', 'ARA', 'Japan', 'Singapore', 'Fujairah']]
    product_land_fill['Total ex US'] = product_land_fill[['ARA', 'Japan', 'Singapore', 'Fujairah']].sum(axis=1)
    product_stocks = product_stocks[['Land Stocks', 'Land Stocks ex US Other', 'Clean Oil On Water', 'Total Prods', 'Total Prods (kbd)']]
    product_stocks_table = product_stocks.copy()
    product_stocks_table = product_stocks_table.rolling(5).mean()
    table_product = table.table_format1(df=product_stocks_table,
                                        rows=['Land Stocks ex US Other', 'Clean Oil On Water', 'Total Prods', 'Total Prods (kbd)'],
                                        highlight={'seasonal': 5}, agg_by='diff', agg_by_column={'Total Prods (kbd)': 'mean'},
                                        window=20, show_quarter=4, ex2020=True, table_head='Product Stocks', qtd=True)
    table_product_by_type = table.table_format1(df=product_by_type, rows=None, highlight={'seasonal': 5},
                                                agg_by='diff', agg_by_column=None, window=20, show_quarter=4,
                                                ex2020=True, table_head='Product Stocks', qtd=True)
    table_product_by_type.to_csv(convert_path_to_linux(f'{csv_path}\\oil\\global_product_by_type_table.csv'))
    product_by_type.to_csv(convert_path_to_linux(f'{csv_path}\\oil\\global_product_by_type.csv'))
    table_product_detail = table.table_format1(df=product_land_fill, rows=None, highlight={'seasonal': 5},
                                               agg_by='diff', agg_by_column=None, window=20, show_quarter=4,
                                               ex2020=True, table_head='Product Stocks', qtd=True)
    table_product_detail = pd.concat([table_product_detail, product_last_update], axis=1)
    table_product_detail.drop(['Product Land'], axis=1, inplace=True)
    table_product_detail.loc[0, 'Product Stocks'] = 'US/Main'
    table_product_detail.loc[1, 'Product Stocks'] = 'US/Other'
    table_ara_detail = table.table_format1(df=ara_daily, rows=None, highlight={'seasonal': 5},
                                          agg_by='diff', agg_by_column=None, window=20, show_quarter=4,
                                          ex2020=True, table_head='Product Stocks', qtd=True)
    mo_ea, _last_update = dv.ea_us_oil_weekly(sheet_name='Fig 5 US gasoline balance')
    mo_ea = mo_ea.iloc[:, -1] * 1000
    disty_ea, _last_update = dv.ea_us_oil_weekly(sheet_name='Fig 9 US distillate balance')
    disty_ea = disty_ea.iloc[:, -1] * 1000
    prod_ea = mo_ea + disty_ea
    prod_ea = prod_ea.to_frame('US Prod Consensus')
    prod_ea['_last_update'] = _last_update
    prod_ea = prod_ea.loc[prod_ea.index < today(), :]
    table_consensus_us_prod = table.table_format1(df=prod_ea, freq='M', lable='Change',
                                                  rows=['US Prod Consensus', '_last_update'], agg_by=None,
                                                  window=20, show_quarter=3, table_head='Product Stocks', qtd=True)
    table_consensus_us_prod['Last Update'] = _last_update.strftime('%Y-%m-%d')
    table_product_detail = pd.concat([table_product_detail.loc[[0], :], table_consensus_us_prod,
                                      table_product_detail.loc[1:, :]], axis=0, ignore_index=True)
    format_column = {
        '0': {'width': '120px', 'text-align': 'left'},
        '1': {'width': '80px', 'text-align': 'center', 'highlight_z': [1, '_mean', '_std'], 'right_border': True},
        '2': {'width': '80px', 'text-align': 'center'},
        '3': {'width': '80px', 'text-align': 'center'},
        '4': {'width': '80px', 'text-align': 'center', 'right_border': True},
        '5': {'width': '80px', 'text-align': 'center'},
        '6': {'width': '80px', 'text-align': 'center'},
        '7': {'width': '80px', 'text-align': 'center'},
        '8': {'width': '80px', 'text-align': 'center', 'right_border': True},
        '9': {'width': '80px', 'text-align': 'center'},
        '10': {'width': '80px', 'text-align': 'center'},
        '11': {'width': '80px', 'text-align': 'center'}}
    html_product = table.html_format(df=table_product, header='Global Product Stocks Change (kb) - 20d Change on 5d MA',
                                     footer=None, show_date=False, format_column=format_column,
                                     format_row={'1': {'bottom_border': True}, '3': {'bold': True}}, precision=0,
                                     hide_cols=['_mean', '_std', '_last_update'], inline=False, background_color='lightblue')
    html_product_by_type = table.html_format(df=table_product_by_type, header='Detailed Product Stocks Change by Type (kb)',
                                              footer=None, show_date=False, format_column=format_column, format_row=None,
                                              precision=0, hide_cols=['_mean', '_std', '_last_update'],
                                              inline=False, background_color='lightblue')
    html_product_details = table.html_format(df=table_product_detail, header='Detailed Product Stocks Change by Region (kb)',
                                             footer=None, show_date=False, format_column=format_column,
                                             format_row={'2': {'bottom_border': True}, '7': {'bold': True}}, precision=0,
                                             hide_cols=['_mean', '_std', '_last_update'], inline=False, background_color='lightblue')
    html_ara_details = table.html_format(df=table_ara_detail, header='Detailed ARA Stocks Change (kt)',
                                         footer=None, show_date=False, format_column=format_column, format_row=None,
                                         precision=0, hide_cols=['_mean', '_std', '_last_update'], inline=False, background_color='lightblue')

    def seasonal_chart_2col(df, column, title, freq='D', column1=None, roll=10):
        df_2y = (df.rolling(10).mean()).loc[pygdt('-2y'):, [column]]
        if column1 is None:
            column1 = [f'{column} 10{freq} ma']
        if roll is None:
            df_ = df.copy()
        else:
            df_ = df.rolling(10).mean()
        return chart.seasonal_chart_2col_new(
            df=df_, df1=pd.concat([df_2y, df_2y.loc[pygdt('-2y'):].iloc[:, 0].to_frame(f'{column} 10{freq} ma')], axis=1),
            start=chart_sdate, column=column, column1=column1, title=title, vs_avg=True, ytd=False, freq=freq,
            x_axis_title='Date', y_axis_title='kb', y1_axis_title='kb', y2_axis_title=None,
            highlight_dict={column: {'color': 'black'}}, highlight_dict_c2={f'{column} 10{freq} ma': {'color': 'black'}})
    chart_sdate = dt.datetime(2018, 1, 1)
    product_level = seasonal_chart_2col(df=product_stocks, column='Total Prods', title='Total Products Stocks ex US other - level')
    product_land_level = seasonal_chart_2col(df=product_stocks, column='Land Stocks ex US Other',
                                             title='Products Land Stocks ex US Other - level')
    product_water_level = seasonal_chart_2col(df=product_stocks, column='Clean Oil On Water', title='Products Water Stocks - level')
    distillate_level = seasonal_chart_2col(df=product_by_type[['Distillate']], column='Distillate', title='Agency Distillate Product Stocks - level')
    lightends_level = seasonal_chart_2col(df=product_by_type[['Light Ends']], column='Light Ends', title='Agency Light Ends Product Stocks - level')
    fueloil_level = seasonal_chart_2col(df=product_by_type[['Fuel Oil']], column='Fuel Oil', title='Agency Fuel Oil Product Stocks - level')
    us_level = seasonal_chart_2col(df=product_land_fill[['US']], column='US', title='DOE US Product Stocks - level')
    usother_level = seasonal_chart_2col(df=product_land_fill[['US Other']], column='US Other', title='DOE US Other Product Stocks - level')
    ara_level_dict = {}
    for col in ara.columns:
        ara_season = chart.seasonal_chart(df=ara, column=col, title=f'ARA {col} Stocks - level', freq='W',
                                          **_missing_photo_text('741', 'h'))
        ara_2y = chart.line_chart(df=ara[[col]].iloc[-100:, :], title=f'ARA {col} Stocks - last 2Y',
                                  **_missing_photo_text('742', 'tickfor'))
        ara_level_dict[col] = [ara_season, ara_2y]
    product_chg = ts.rolling(product_stocks, method='diff', window=20, start=chart_sdate)
    distillate_chg = ts.rolling(product_by_type[['Distillate']], method='diff', window=20, start=chart_sdate)
    lightends_chg = ts.rolling(product_by_type[['Light Ends']], method='diff', window=20, start=chart_sdate)
    fueloil_chg = ts.rolling(product_by_type[['Fuel Oil']], method='diff', window=20, start=chart_sdate)
    us_chg = ts.rolling(product_land_fill[['US']], method='diff', window=20, start=chart_sdate)
    usother_chg = ts.rolling(product_land_fill[['US Other']], method='diff', window=20, start=chart_sdate)
    ara_chg = ts.rolling(ara, method='diff', window=4, start=chart_sdate)

    def format_ytd(df, freq=None):
        if 2020 in df.columns:
            df = df.drop([2020], axis=1)
        df = df.iloc[:, -6:]
        if freq is None:
            dts = pd.date_range(dt.datetime(df.columns[-1], 1, 1), dt.datetime(df.columns[-1], 12, 31))
        else:
            dts = pd.date_range(dt.datetime(df.columns[-1], 1, 1), dt.datetime(df.columns[-1], 12, 31), freq=freq)
        if len(dts) < df.shape[0]:
            df = df.iloc[:len(dts), :]
        df['Date'] = dts
        df = df.set_index('Date')
        return df

    product_ytd = format_ytd(ts.data_by_year(product_stocks['Total Prods'], freq='D', ytd=True))
    product_land_ytd = format_ytd(ts.data_by_year(product_stocks['Land Stocks ex US Other'], freq='D', ytd=True))
    product_water_ytd = format_ytd(ts.data_by_year(product_stocks['Clean Oil On Water'], freq='D', ytd=True))
    distillate_ytd = format_ytd(ts.data_by_year(product_by_type['Distillate'], freq='D', ytd=True))
    lightends_ytd = format_ytd(ts.data_by_year(product_by_type['Light Ends'], freq='D', ytd=True))
    fueloil_ytd = format_ytd(ts.data_by_year(product_by_type['Fuel Oil'], freq='D', ytd=True))
    us_ytd = format_ytd(ts.data_by_year(product_land_fill['US'], freq='D', ytd=True))
    usother_ytd = format_ytd(ts.data_by_year(product_land_fill['US Other'], freq='D', ytd=True))
    ara_ytd_dict = {}
    for col in ara.columns:
        ara_ytd_dict[col] = format_ytd(ts.data_by_year(ara[col], freq='W', ytd=True), freq='W-THU')

    def seasonal_chart(df, column, df1, title, freq='D'):
        return chart.seasonal_chart_2col_new(df=df, column=column, df1=df1, title=title,
                                             column_titles=['20d Change', 'YTD Change'], vs_avg=True, ytd=False,
                                             freq=freq, x_axis_title='Date', y_axis_title='kb', y1_axis_title='kb', y2_axis_title=None)

    chart_product_chg = seasonal_chart(df=product_chg, column='Total Prods', df1=product_ytd,
                                        title='Total Products Stocks ex US other - Change')
    chart_product_land_chg = seasonal_chart(df=product_chg, column='Land Stocks ex US Other', df1=product_land_ytd,
                                             title='Products Land Stocks ex US Other - Change')
    chart_product_water_chg = seasonal_chart(df=product_chg, column='Clean Oil On Water', df1=product_water_ytd,
                                              title='Products Water Stocks - Change')
    chart_distillate_chg = seasonal_chart(df=distillate_chg, column='Distillate', df1=distillate_ytd,
                                           title='Agency Distillate Product Stocks - Change')
    chart_lightends_chg = seasonal_chart(df=lightends_chg, column='Light Ends', df1=lightends_ytd,
                                          title='Agency Light Ends Product Stocks - Change')
    chart_fueloil_chg = seasonal_chart(df=fueloil_chg, column='Fuel Oil', df1=fueloil_ytd,
                                        title='Agency Fuel Oil Product Stocks - Change')
    chart_us_chg = seasonal_chart(df=us_chg, column='US', df1=us_ytd, title='DOE US Product Stocks')
    chart_usother_chg = seasonal_chart(df=usother_chg, column='US Other', df1=usother_ytd,
                                        title='DOE US Other Product Stocks - Change')
    ara_chg_dict = {}
    for col in ara.columns:
        chart_ara_chg = chart.seasonal_chart(df=ara_chg, column=col, title=f'ARA {col} Stocks - 4w Change',
                                            **_missing_photo_text('814'))
        chart_ara_ytd = chart.line_chart(df=ara_ytd_dict[col], title=f'ARA {col} Stocks - YTD Change',
                                          highlight_dict={ara_ytd_dict[col].columns[-1]: {'color': 'black', 'width': 2}},
                                          tickformat=None, height=500, width=750)
        ara_chg_dict[col] = [chart_ara_chg, chart_ara_ytd]
    figs_lvl = []
    for col in ara.columns:
        figs_lvl.append(ara_level_dict[col])
        figs_lvl.append(ara_chg_dict[col])
    table.to_html(figs_lvl, f'{html_path}\\oil\\links\\product_stocks_level.html', task_name=report_name)
    figs = []
    figs.append(table.html_text(f"Updated at {dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"))
    figs.append(_missing_photo_text('837', '<a href="https://elementcapital.atlassian.net/wiki/spaces/LO25/pages/1774687371/Global+Liquids+Inv'))
    figs.append(html_product)
    figs.append(html_product_by_type)
    figs.append(html_product_details)
    figs.append(html_ara_details)
    figs.append(u'<a href="{:s}\\oil\\links\\product_stocks_level.html">ARA Detailed Stocks Charts</a><br>'.format(html_path))
    figs.append(product_level)
    figs.append(chart_product_chg)
    figs.append(product_land_level)
    figs.append(chart_product_land_chg)
    figs.append(product_water_level)
    figs.append(chart_product_water_chg)
    figs.append(distillate_level)
    figs.append(chart_distillate_chg)
    figs.append(lightends_level)
    figs.append(chart_lightends_chg)
    figs.append(fueloil_level)
    figs.append(chart_fueloil_chg)
    table.to_html([table.html_text(report_name, style='font-family:Calibri;', tag='h1')] + figs,
                   f'{html_path}\\oil\\{file_name}.html', task_name=report_name)
    if today().weekday() in [2]:
        send_email(send_to=send_to, subject=report_name, body=figs, html_path=f'{html_path}\\oil\\{file_name}.html')


if __name__ == '__main__':
    update(send_to=send_to)
