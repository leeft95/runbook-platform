import pandas as pd
import numpy as np
import datetime as dt
import sys
import os
if sys.platform.startswith("win"):
    os.environ["GRPC_DEFAULT_SSL_ROOTS_FILE_PATH"] = "C:\local\certs\root.crt"
    os.environ["REQUESTS_CA_BUNDLE"] = "C:\local\certs\root.crt"
    os.environ["SSL_CERT_FILE"] = "C:\local\certs\root.crt"
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


def _unrecovered(message, *visible_arguments):
    raise NotImplementedError(message)


send_to = ['mkikano@elementcapital.com', 'rzhao@elementcapital.com', 'ltrindade@elementcapital.com',
           *_unrecovered('Kpler inventory 26: clipped recipient list tail beginning lba')]
report_name = "Global Liquids Inventory"
file_name = "kpler_inventory"  # without .py
file_path = f"{root_path}\\autoreports\\reports\\oil\\{file_name}.py"


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
        start_datetime=dt.datetime(2022, 7, 1, 9, 35), timezone="Europe/London", task_name=report_name,
        task=WinTaskPoC(name=f'"{report_name}"', filepath=f'"{file_path}"'), background_task=True,
        python_excecutable=r"C:\local\python\miniconda\envs\ecm_cmds\pythonw.exe")
    win_task.create_task()


ea_bbg_map = {
    "1530": "ARASGSLN Index", "1531": "ARASGO Index", "1532": "ARASKERO Index", "1533": "ARASNPHT Index",
    "1534": "ARASFO Index", "1535": "CUAAST Index", "1536": "SPIVLDIS Index", "1537": "SPIVMDIS Index",
    "1538": "SPIVRESD Index", "1545": "AALNX00", "1546": "AAVPL00", "1547": "AALQU00",
    "1548": "AALNZ00", "1549": "AALQU00", "1550": "AALOF00", "1551": "AAVQZ00", "1552": "FUJLD04",
    "1553": "FUJMD04", "1554": "FUJHD04", "1555": "", "1556": "DOESTMGS Index", "1557": "DOESDIST Index",
    "1558": "DOESJETK Index", "1559": "DOESRESD Index", "1560": "DOESESPR Index", "1561": "DOESCRUD Index",
}
base_link = f"{html_path}\\oil\\links\\stocks_change.html"
base_link_main = f"{html_path}\\oil\\{file_name}.html"
name_to_stock_chg_chart_link = {
    "Land": f'<a href="{html_path}\\oil\\links\\stocks_level.html">Land</a>',
    "Water": f'<a href="{html_path}\\oil\\oil_on_water.html">Water</a>',
}


def crude_inventory():
    spr = dv.kpler(link="/v1/inventories?zones=US&startDate=2017-01-01&split=byTankType")
    crude_on_water = dv.kpler(link=("/v1/fleet-metrics?metric=loaded_vessels&zones=world&period=daily&"
                                    "startDate=2017-01-01&unit=kb&products=crude%2fco"))
    global_land = dv.kpler(link="/v1/inventories?zones=World&startDate=2017-01-01&period=daily&split=total")
    asian_stocks = dv.kpler(link=("/v1/inventories?zones=China,India,Korea,Japan,Indonesia,Taiwan,Thailand&"
                                  "startDate=2017-01-01&period=daily&split=byCountry"))
    eu_stocks = dv.kpler(link=("/v1/inventories?zones=Netherlands,France,Germany,Italy,Spain,United%20Kingdom&"
                               "startDate=2017-01-01&period=daily&split=byCountry"))
    nam_stocks = dv.kpler(link="/v1/inventories?zones=United%20States,Canada&startDate=2017-01-01&period=daily&split=byCountry")
    other_ab_stocks = dv.kpler(link=("/v1/inventories?zones=South%20Africa,Egypt,Caribbean%20Islands&"
                                     "startDate=2017-01-01&period=daily&split=byCountry"))
    spr.to_csv(convert_path_to_linux(_unrecovered('Kpler inventory 109: clipped dated SPR filename tail', f"{data_path}\\kpler\\spr_")))
    global_land.to_csv(convert_path_to_linux(_unrecovered('Kpler inventory 110: clipped dated land filename tail', f"{data_path}\\kpler\\global_land_")))
    spr = kpler.convert_to_ts(kpler_links=spr, columns=["SPR"], end_dt="-1d")
    global_land = kpler.convert_to_ts(kpler_links=global_land, columns=["Crude On Land"],
                                      rename={"Level (kb)": "Crude On Land"}, end_dt="-1d")
    crude_on_water = kpler.convert_to_ts(kpler_links=crude_on_water, columns=["Crude On Water"],
                                         rename={"Total": "Crude On Water"}, end_dt="-1d")
    global_crude = ts.sum_dfs(dfs=[spr, global_land, crude_on_water])
    global_crude["Crude On Land"] = global_crude["Crude On Land"] - global_crude["SPR"]
    global_crude["Total"] = global_crude["Crude On Land"] + global_crude["Crude On Water"]
    global_crude["Total (kbd)"] = global_crude["Total"].diff()
    global_crude.drop(["SPR"], axis=1, inplace=True)
    asian_stocks = kpler.convert_to_ts(asian_stocks, rename={"Level (kb)": "Asia"}, end_dt="-1d",
                                       drop_column=['Zone', 'Installation', 'Local Supply (kbd)', 'Local Demand (kbd)',
                                                    'Cargoes (kbd)', 'Capacity (kb)', 'Relative Fill Level', 'Country',
                                                    'Continent', 'Revisit Rate', 'Last Image'])
    asian_stocks["Asia (kbd)"] = asian_stocks["Asia"].diff()
    asian_stocks = asian_stocks[['China', 'India', 'Indonesia', 'Japan', 'South Korea', 'Taiwan', 'Thailand', 'Asia', 'Asia (kbd)']]
    global_crude_exch = ts.sum_dfs(dfs=[spr, global_land, crude_on_water, asian_stocks[["China"]]])
    global_crude_exch["Crude On Land"] = global_crude_exch["Crude On Land"] - global_crude_exch["SPR"] - global_crude_exch["China"]
    global_crude_exch["Total"] = global_crude_exch["Crude On Land"] + global_crude_exch["Crude On Water"]
    global_crude_exch["Total (kbd)"] = global_crude_exch["Total"].diff()
    global_crude_exch.drop(["SPR", "China"], axis=1, inplace=True)
    eu_stocks = kpler.convert_to_ts(eu_stocks, rename={"Level (kb)": "Europe"}, end_dt="-1d",
                                    drop_column=['Zone', 'Installation', 'Local Supply (kbd)', 'Local Demand (kbd)',
                                                 'Cargoes (kbd)', 'Capacity (kb)', 'Relative Fill Level', 'Country',
                                                 'Continent', 'Revisit Rate', 'Last Image'])
    eu_stocks['Europe (kbd)'] = eu_stocks['Europe'].diff()
    eu_stocks = eu_stocks[['France', 'Germany', 'Italy', 'Netherlands', 'Spain', 'United Kingdom', 'Europe', 'Europe (kbd)']]
    nam_stocks = kpler.convert_to_ts(nam_stocks, rename={"Level (kb)": "Americas"}, end_dt="-1d",
                                     drop_column=['Zone', 'Installation', 'Local Supply (kbd)', 'Local Demand (kbd)',
                                                  'Cargoes (kbd)', 'Capacity (kb)', 'Relative Fill Level', 'Country',
                                                  'Continent', 'Revisit Rate', 'Last Image'])
    nam_stocks["United States"] = nam_stocks["United States"] - spr["SPR"]
    nam_stocks["Americas"] = nam_stocks["Americas"] - spr["SPR"]
    nam_stocks['Americas (kbd)'] = nam_stocks['Americas'].diff()
    nam_stocks = nam_stocks[['Canada', 'United States', 'Americas', 'Americas (kbd)']]
    other_ab_stocks = kpler.convert_to_ts(other_ab_stocks, rename={"Level (kb)": "SA,Egypt,Caribbean"}, end_dt="-1d",
                                          drop_column=['Zone', 'Installation', 'Local Supply (kbd)', 'Local Demand (kbd)',
                                                       'Cargoes (kbd)', 'Capacity (kb)', 'Relative Fill Level', 'Country',
                                                       'Continent', 'Revisit Rate', 'Last Image'])
    ab_stocks = pd.concat([nam_stocks["United States"], eu_stocks["Europe"], other_ab_stocks["SA,Egypt,Caribbean"]], axis=1)
    ab_stocks.columns = ["United States", "Europe", "SA,Egypt,Caribbean"]
    ab_stocks["Atlantic Basin (US+EU)"] = ab_stocks[["United States", "Europe"]].sum(axis=1)
    ab_stocks["Atlantic Basin (kbd)"] = ab_stocks["Atlantic Basin (US+EU)"].diff()
    return global_crude, global_crude_exch, eu_stocks, nam_stocks, asian_stocks, ab_stocks


def product_on_water():
    clean_on_water = dv.kpler(link="/v1/fleet-metrics?metric=loaded_vessels&products=Clean%20Products&period=daily&unit=kb")
    clean_on_water = kpler.convert_to_ts(kpler_links=clean_on_water, columns=["Clean Oil On Water"], end_dt="-1d")
    return clean_on_water


def product_inventory_old_old():
    product_stocks = dv.energy_aspects(
        dataset_id=("1530,1531,1532,1533,1534,1535,1536,1537,1538,1539,1540,1541,1542,1543,1544,"
                    "1545,1546,1547,1548,1549,1550,1551,1552,1553,1554,1555,1556,1557,1558,1559,1560,1561"),
        start="2017-01-01")
    product_stocks = kpler.convert_to_ts(kpler_links=product_stocks, columns=None, rename=None,
        drop_column=['Weekly Mexico diesel inventories in kbbl', 'Weekly Mexico fuel oil inventories in kbbl',
                     'Weekly Mexico gasoline inventories in kbbl', 'Weekly Mexico jet fuel inventories in kbbl',
                     'Weekly Mexico total diesel storage in kbbl', 'Weekly Mexico total gasoline storage in kbbl'])
    product_stocks.rename(columns={'Weekly total product inventories for Fujairah in Mbbl': 'Fujairah'}, inplace=True)
    product_stocks['Weekly gasoline inventories for ARA in kt'] = product_stocks['Weekly gasoline inventories for ARA in kt'] * 8.33
    product_stocks['Weekly jet fuel inventories for ARA in kt'] = product_stocks['Weekly jet fuel inventories for ARA in kt'] * 7.878
    product_stocks['Weekly middle distillate inventories for ARA in kt'] = product_stocks['Weekly middle distillate inventories for ARA in kt'] * 7.45
    product_stocks['Weekly fuel oil inventories for ARA in kt'] = product_stocks['Weekly fuel oil inventories for ARA in kt'] * 7.45
    product_stocks['ARA'] = product_stocks['Weekly gasoline inventories for ARA in kt'] + product_stocks['Weekly jet fuel inventories for ARA in kt'] + product_stocks['Weekly middle distillate inventories for ARA in kt'] + product_stocks['Weekly fuel oil inventories for ARA in kt']
    product_stocks['Weekly fuel oil inventories in Singapore in Mbbl'] = product_stocks['Weekly fuel oil inventories in Singapore in Mbbl'] * 1000
    product_stocks['Weekly light distillates inventories in Singapore in Mbbl'] = product_stocks['Weekly light distillates inventories in Singapore in Mbbl'] * 1000
    product_stocks['Weekly middle distillates inventories in Singapore in Mbbl'] = product_stocks['Weekly middle distillates inventories in Singapore in Mbbl'] * 1000
    product_stocks['Singapore'] = product_stocks['Weekly fuel oil inventories in Singapore in Mbbl'] + product_stocks['Weekly light distillates inventories in Singapore in Mbbl'] + product_stocks['Weekly middle distillates inventories in Singapore in Mbbl']
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
    product_stocks['Japan'] = product_stocks['Weekly jet fuel inventories for Japan in kl'] + product_stocks['Weekly kerosene inventories for Japan in kl'] + product_stocks['Weekly naphtha inventories for Japan in kl'] + product_stocks['Weekly gasoline inventories for Japan in kl'] + product_stocks['Weekly diesel inventories for Japan in kl'] + product_stocks['Weekly fuel oil inventories for Japan in Mbbl']
    product_stocks['Fujairah'] = product_stocks['Fujairah'] * 1000
    product_stocks['US'] = product_stocks['Weekly diesel inventories for US in kbbl'] + product_stocks['Weekly gasoline inventories for US in kbbl'] + product_stocks['Weekly jet fuel inventories for US in kbbl'] + product_stocks['Weekly residual fuel oil inventories for US in kbbl']
    product_stocks['US Other'] = product_stocks['Weekly total product inventories for US in kbbl'] - product_stocks['Weekly crude inventories for US in kbbl'] - product_stocks['US']
    product_by_loc = product_stocks[['US', 'US Other', 'ARA', 'Japan', 'Singapore', 'Fujairah']]
    product_stocks_fill = product_stocks.copy()
    product_stocks_fill = product_stocks_fill.reindex(pd.date_range(product_stocks_fill.index[0], product_stocks_fill.index[-1]))
    product_stocks_fill.fillna(method="ffill", inplace=True)
    product_stocks_fill['Distillate'] = (product_stocks_fill['Weekly middle distillate inventories for ARA in kt'] + product_stocks_fill['Weekly jet fuel inventories for ARA in kt'] + product_stocks_fill['Weekly middle distillates inventories in Singapore in Mbbl'] + product_stocks_fill['Weekly jet fuel inventories for Japan in kl'] + product_stocks_fill['Weekly kerosene inventories for Japan in kl'] + product_stocks_fill['Weekly diesel inventories for Japan in kl'] + product_stocks_fill['Weekly middle distillate inventories for Fujairah in Mbbl'] * 1000 + product_stocks_fill['Weekly diesel inventories for US in kbbl'] + product_stocks_fill['Weekly jet fuel inventories for US in kbbl'])
    product_stocks_fill['Light Ends'] = (product_stocks_fill['Weekly naphtha inventories for ARA in kt'] + product_stocks_fill['Weekly gasoline inventories for ARA in kt'] + product_stocks_fill['Weekly naphtha inventories for Japan in kl'] + product_stocks_fill['Weekly gasoline inventories for Japan in kl'] + product_stocks_fill['Weekly light distillates inventories in Singapore in Mbbl'] + product_stocks_fill['Weekly light distillates inventories for Fujairah in Mbbl'] * 1000 + product_stocks_fill['Weekly gasoline inventories for US in kbbl'])
    product_stocks_fill['Fuel Oil'] = (product_stocks_fill['Weekly fuel oil inventories for ARA in kt'] + product_stocks_fill['Weekly fuel oil inventories in Singapore in Mbbl'] + product_stocks_fill['Weekly fuel oil inventories for Japan in Mbbl'] + product_stocks_fill['Weekly residual and heavy distillates inventories for Fujairah in Mbbl'] * 1000 + product_stocks_fill['Weekly residual fuel oil inventories for US in kbbl'])
    return product_by_loc, product_stocks_fill[["Distillate", "Light Ends", "Fuel Oil"]]


def product_inventory_old():
    product_stocks = dv.energy_aspects(dataset_id="1530,1531,1532,1533,1534,1535,1536,1537,1538,1539,1540,1541,1542,1543,1544,1545,1546,1547,1548,1549,1550,1551,1552,1553,1554,1555,1556,1557,1558,1559,1560,1561", start="2017-01-01")
    product_stocks = kpler.convert_to_ts(kpler_links=product_stocks, columns=None, rename=None, drop_column=['Weekly diesel inventories in Mexico in kb', 'Weekly fuel oil inventories in Mexico in kb', 'Weekly gasoline inventories in Mexico in kb', 'Weekly jet/kero inventories in Mexico in kb'])
    product_stocks.rename(columns={'Weekly total product inventories for Fujairah in Mbbl': 'Fujairah'}, inplace=True)
    product_stocks['Weekly gasoline inventories in ARA in kt'] = product_stocks['Weekly gasoline inventories in ARA in kt'] * 8.33
    product_stocks['Weekly jet/kero inventories for ARA in kt'] = product_stocks['Weekly jet/kero inventories in ARA in kt'] * 7.878
    product_stocks['Weekly middle distillate inventories in ARA in kt'] = product_stocks['Weekly middle distillate inventories in ARA in kt'] * 7.45
    product_stocks['Weekly fuel oil inventories in ARA in kt'] = product_stocks['Weekly fuel oil inventories in ARA in kt'] * 7.45
    product_stocks['ARA'] = product_stocks['Weekly gasoline inventories in ARA in kt'] + product_stocks['Weekly jet/kero inventories in ARA in kt'] + product_stocks['Weekly middle distillate inventories in ARA in kt'] + product_stocks['Weekly fuel oil inventories in ARA in kt']
    product_stocks['Weekly fuel oil inventories in Singapore in Mb'] = product_stocks['Weekly fuel oil inventories in Singapore in Mb'] * 1000
    product_stocks['Weekly light distillates inventories in Singapore in Mb'] = product_stocks['Weekly light distillates inventories in Singapore in Mb'] * 1000
    product_stocks['Weekly middle distillates inventories in Singapore in Mb'] = product_stocks['Weekly middle distillates inventories in Singapore in Mb'] * 1000
    product_stocks['Singapore'] = product_stocks['Weekly fuel oil inventories in Singapore in Mb'] + product_stocks['Weekly light distillates inventories in Singapore in Mb'] + product_stocks['Weekly middle distillates inventories in Singapore in Mb']
    product_stocks['Weekly jet/kero inventories in Japan in kl'] = product_stocks['Weekly jet/kero inventories in Japan in kl'] / 158.987567172247
    product_stocks['Weekly kerosene inventories in Japan in kl'] = product_stocks['Weekly kerosene inventories in Japan in kl '] / 158.987567172247
    product_stocks['Weekly naphtha inventories in Japan in kl'] = product_stocks['Weekly naphtha inventories in Japan in kl '] / 158.987567172247
    product_stocks['Weekly gasoline inventories in Japan in kl'] = product_stocks['Weekly gasoline inventories in Japan in kl '] / 158.987567172247
    product_stocks['Weekly diesel inventories in Japan in kl'] = product_stocks['Weekly diesel inventories in Japan in kl'] / 158.987567172247
    product_stocks['Weekly fuel oil inventories in Japan in mb'] = product_stocks['Weekly fuel oil inventories in Japan in mb'] * 1000
    product_stocks['Japan'] = product_stocks['Weekly jet/kero inventories in Japan in kl'] + product_stocks['Weekly kerosene inventories in Japan in kl'] + product_stocks['Weekly naphtha inventories in Japan in kl'] + product_stocks['Weekly gasoline inventories in Japan in kl'] + product_stocks['Weekly diesel inventories in Japan in kl'] + product_stocks['Weekly fuel oil inventories in Japan in mb']
    product_stocks['Fujairah'] = product_stocks['Weekly total product inventories in Fujairah in Mb'] * 1000
    product_stocks['US'] = product_stocks['Weekly diesel inventories in United States in kb'] + product_stocks['Weekly gasoline inventories in United States in kb'] + product_stocks['Weekly jet/kero inventories in United States in kb'] + product_stocks['Weekly residual fuel oil inventories in United States in kb']
    product_stocks['US Other'] = product_stocks['Weekly total product inventories in United States in kb'] - product_stocks['Weekly crude oil inventories in United States in kb'] - product_stocks['US']
    product_by_loc = product_stocks[['US', 'US Other', 'ARA', 'Japan', 'Singapore', 'Fujairah']]
    product_stocks_fill = product_stocks.copy()
    product_stocks_fill = product_stocks_fill.reindex(pd.date_range(product_stocks_fill.index[0], product_stocks_fill.index[-1]))
    product_stocks_fill.fillna(method="ffill", inplace=True)
    product_stocks_fill['Distillate'] = (product_stocks_fill['Weekly middle distillate inventories in ARA in kt'] + product_stocks_fill['Weekly jet/kero inventories in ARA in kt'] + product_stocks_fill['Weekly middle distillates inventories in Singapore in Mb'] + product_stocks_fill['Weekly jet/kero inventories in Japan in kl'] + product_stocks_fill['Weekly kerosene inventories in Japan in kl'] + product_stocks_fill['Weekly diesel inventories in Japan in kl'] + product_stocks_fill['Weekly middle distillate inventories in Fujairah in Mb'] * 1000 + product_stocks_fill['Weekly diesel inventories in United States in kb'] + product_stocks_fill['Weekly jet/kero inventories in United States in kb'])
    product_stocks_fill['Light Ends'] = (product_stocks_fill['Weekly naphtha inventories in ARA in kt'] + product_stocks_fill['Weekly gasoline inventories in ARA in kt'] + product_stocks_fill['Weekly naphtha inventories in Japan in kl'] + product_stocks_fill['Weekly gasoline inventories in Japan in kl'] + product_stocks_fill['Weekly light distillates inventories in Singapore in Mb'] + product_stocks_fill['Weekly light distillates inventories in Fujairah in Mb'] * 1000 + product_stocks_fill['Weekly gasoline inventories in United States in kb'])
    product_stocks_fill['Fuel Oil'] = (product_stocks_fill['Weekly fuel oil inventories in ARA in kt'] + product_stocks_fill['Weekly fuel oil inventories in Singapore in mb'] + product_stocks_fill['Weekly fuel oil inventories in Japan in mb'] + product_stocks_fill['Weekly residual and heavy distillates inventories in Fujairah in Mb'] * 1000 + product_stocks_fill['Weekly residual fuel oil inventories in United States in kb'])
    return product_by_loc, product_stocks_fill[["Distillate", "Light Ends", "Fuel Oil"]]


def get_platts(ticker, sdate, edate):
    df = platts.get_market_data(ticker, start_date=sdate, end_date=edate)
    df = df[["assessDate", "value"]]
    df.set_index("assessDate", inplace=True)
    df.index = pd.to_datetime(df.index)
    df.columns = ["PX_LAST"]
    return df


def product_inventory():
    product_stocks_ara = bbg.bdh(["ARASGSLN Index", "ARASGO Index", "ARASKERO Index", "ARASNPHT Index", "ARASFO Index"],
                                **_unrecovered('Kpler inventory 434: clipped Bloomberg history arguments'))
    product_stocks_sing = bbg.bdh(["SPIVLDIS Index", "SPIVMDIS Index", "SPIVRESD Index"], ["PX_LAST"],
                                 **_unrecovered('Kpler inventory 435: clipped Bloomberg date arguments'))
    product_stocks_us = bbg.bdh(["DOESTMGS Index", "DOESDIST Index", "DOESJETK Index", "DOESRESD Index",
                                "DOESESPR Index", "DOESCRUD Index"],
                               **_unrecovered('Kpler inventory 436: clipped Bloomberg history arguments'))
    jp_gasoline = get_platts("AALNX00", sdate=dt.datetime(2017, 1, 1), edate=today())
    jp_naphtha = pd.DataFrame(0.0, index=jp_gasoline.index, columns=["PX_LAST"])
    jp_jet = get_platts("AALQU00", sdate=dt.datetime(2017, 1, 1), edate=today())
    jp_diesel = get_platts("AALNZ00", sdate=dt.datetime(2017, 1, 1), edate=today())
    jp_kero = get_platts("AALQU00", sdate=dt.datetime(2017, 1, 1), edate=today())
    jp_fo = get_platts("AALOF00", sdate=dt.datetime(2017, 1, 1), edate=today())
    fuj_light = get_platts("FUJLD04", sdate=dt.datetime(2017, 1, 1), edate=today())
    fuj_middle = get_platts("FUJMD04", sdate=dt.datetime(2017, 1, 1), edate=today())
    fuj_res = get_platts("FUJHD04", sdate=dt.datetime(2017, 1, 1), edate=today())
    product_stocks_ara["ARASNPHT Index"] = product_stocks_ara["ARASNPHT Index"] * 8.9
    product_stocks_ara["ARASGSLN Index"] = product_stocks_ara["ARASGSLN Index"] * 8.33
    product_stocks_ara["ARASKERO Index"] = product_stocks_ara["ARASKERO Index"] * 7.878
    product_stocks_ara["ARASGO Index"] = product_stocks_ara["ARASGO Index"] * 7.45
    product_stocks_ara["ARASFO Index"] = product_stocks_ara["ARASFO Index"] * 7.45
    jp_gasoline /= 1000
    jp_naphtha /= 1000
    jp_jet /= 1000
    jp_diesel /= 1000
    jp_kero /= 1000
    jp_fo /= 1000
    product_ara = product_stocks_ara[["ARASGSLN Index", "ARASGO Index", "ARASKERO Index", "ARASFO Index"]].sum(axis=1)
    product_sing = product_stocks_sing.sum(axis=1)
    product_fuj = fuj_light + fuj_middle + fuj_res
    product_jp = jp_gasoline + jp_naphtha + jp_jet + jp_diesel + jp_kero + jp_fo
    product_us = product_stocks_us[["DOESTMGS Index", "DOESDIST Index", "DOESJETK Index", "DOESRESD Index"]].sum(axis=1)
    product_us_other = product_stocks_us["DOESESPR Index"] - product_stocks_us["DOESCRUD Index"] - product_us
    product_by_loc = pd.concat([product_us, product_us_other, product_ara, product_jp, product_sing, product_fuj], axis=1)
    product_by_loc.columns = ['US', 'US Other', 'ARA', 'Japan', 'Singapore', 'Fujairah']
    dts = pd.date_range(dt.datetime(2017, 1, 1), today() - dt.timedelta(1))
    product_light = pd.concat([product_stocks_ara[["ARASGSLN Index", "ARASNPHT Index"]].sum(axis=1),
                               *_unrecovered('Kpler inventory 470: clipped light product concat terms', jp_gasoline)], axis=1)
    product_light = product_light.reindex(dts).fillna(method="ffill").sum(axis=1)
    product_middle = pd.concat([product_stocks_ara[["ARASGO Index", "ARASKERO Index"]].sum(axis=1),
                                *_unrecovered('Kpler inventory 472: clipped middle product concat terms', jp_diesel)], axis=1)
    product_middle = product_middle.reindex(dts).fillna(method="ffill").sum(axis=1)
    product_fo = pd.concat([product_stocks_ara["ARASFO Index"], jp_fo, fuj_res, product_stocks_sing["SPIVRESD Index"],
                            *_unrecovered('Kpler inventory 474: clipped fuel oil concat tail')], axis=1)
    product_fo = product_fo.reindex(dts).fillna(method="ffill").sum(axis=1)
    product_by_type = pd.concat([product_middle, product_light, product_fo], axis=1)
    product_by_type.columns = ["Distillate", "Light Ends", "Fuel Oil"]
    return product_by_loc.reindex(dts), product_by_type


def update(send_to):
    global_crude, global_crude_exch, eu_stocks, nam_stocks, asian_stocks, ab_stocks = crude_inventory()
    product_water = product_on_water()
    product_land, product_by_type = product_inventory()
    product_last_update = ts.last_valid_index(product_land, index_name="Product Land", column_name="Last Update", dt2str="%Y-%m-%d")
    product_stocks = pd.concat([product_land, product_water], axis=1)
    product_stocks.fillna(method="ffill", inplace=True)
    product_by_type = product_by_type.reindex(product_stocks.index)
    product_by_type.fillna(method='ffill', inplace=True)
    product_stocks["Land Stocks"] = product_stocks[['ARA', 'US', 'US Other', 'Japan', 'Singapore', 'Fujairah']].sum(axis=1)
    product_stocks["Land Stocks ex US Other"] = product_stocks[['ARA', 'US', 'Japan', 'Singapore', 'Fujairah']].sum(axis=1)
    product_stocks["Total Prods"] = product_stocks["Land Stocks ex US Other"] + product_stocks["Clean Oil On Water"]
    product_stocks["Total Prods (kbd)"] = product_stocks["Total Prods"].diff()
    product_land_fill = product_stocks[["US", "US Other", "ARA", "Japan", "Singapore", "Fujairah"]]
    product_stocks = product_stocks[["Land Stocks", "Land Stocks ex US Other", "Clean Oil On Water", "Total Prods", "Total Prods (kbd)"]]
    liquids_stocks = pd.concat([global_crude, product_stocks], axis=1)
    liquids_stocks["Land"] = liquids_stocks["Crude On Land"] + liquids_stocks["Land Stocks"]
    liquids_stocks["Water"] = liquids_stocks["Crude On Water"] + liquids_stocks["Clean Oil On Water"]
    liquids_stocks["Land+Water"] = liquids_stocks["Land"] + liquids_stocks["Water"]
    liquids_stocks["Land+Water (kbd)"] = liquids_stocks["Land+Water"].diff()
    liquids_stocks = liquids_stocks[["Land", "Water", "Land+Water", "Land+Water (kbd)"]]
    liquids_stocks_table = liquids_stocks.rolling(5).mean()
    liquids_stocks_exch = pd.concat([global_crude_exch, product_stocks], axis=1)
    liquids_stocks_exch["Land"] = liquids_stocks_exch["Crude On Land"] + liquids_stocks_exch["Land Stocks"]
    liquids_stocks_exch["Water"] = liquids_stocks_exch["Crude On Water"] + liquids_stocks_exch["Clean Oil On Water"]
    liquids_stocks_exch["Land+Water"] = liquids_stocks_exch["Land"] + liquids_stocks_exch["Water"]
    liquids_stocks_exch["Land+Water (kbd)"] = liquids_stocks_exch["Land+Water"].diff()
    liquids_stocks_exch = liquids_stocks_exch[["Land", "Water", "Land+Water", "Land+Water (kbd)"]]
    liquids_stocks_table_exch = liquids_stocks_exch.rolling(5).mean()
    global_crude_table = global_crude.rolling(5).mean()
    global_crude_table_exch = global_crude_exch.rolling(5).mean()
    product_stocks_table = product_stocks.copy()
    product_stocks_table = product_stocks_table.rolling(5).mean()
    ab_liquids = (ab_stocks["Atlantic Basin (US+EU)"] + product_land_fill["US"] + product_land_fill["ARA"])
    table_liquids = table.table_format1(df=liquids_stocks_table,
        rows=["Land", "Water", "Land+Water", "Land+Water (kbd)"], highlight={"seasonal": 5}, agg_by="diff",
        agg_by_column={"Land+Water (kbd)": "mean"}, window=20, show_quarter=4, ex2020=True,
        table_head="Liquids Stocks", smooth=None, qtd=True)
    table_liquids.columns = [str(x) for x in table_liquids.columns]
    ea_liquids_m = dv.energy_aspects(dataset_id="6471", start="2024-01-01")
    ea_liquids_m.set_index("Date", inplace=True)
    ea_liquids_m.index = pd.to_datetime(ea_liquids_m.index)
    ea_liquids_m.columns = ["month"]
    ea_liquids_q = ea_liquids_m.resample("Q").mean()
    ea_liquids_q.index = [x + relativedelta(day=1) for x in ea_liquids_q.index]
    ea_liquids_m["quarter"] = ea_liquids_q
    ea_liquids_m["quarter"].fillna(method="bfill", inplace=True)
    ea_liquids_m["ratio"] = ea_liquids_m["month"] / ea_liquids_m["quarter"]
    consensus_liquids_raw = pd.read_csv(convert_path_to_linux(_unrecovered('Kpler inventory 550: clipped monthly consensus CSV name', f"{root_path}\\outputs\\csvs\\oil\\consens")))
    consensus_liquids_raw.set_index("Unnamed: 0", inplace=True)
    consensus_liquids_raw.set_index("Source", inplace=True)
    consensus_liquids_raw.drop("Date", axis=1, inplace=True)
    consensus_liquids_raw_q = pd.read_csv(convert_path_to_linux(_unrecovered('Kpler inventory 555: clipped quarterly consensus CSV name', f"{root_path}\\outputs\\csvs\\oil\\conse")))
    consensus_liquids_raw_q.set_index("Unnamed: 0", inplace=True)
    consensus_liquids_raw_q.set_index("Source", inplace=True)
    consensus_liquids_raw_q.drop("Date", axis=1, inplace=True)
    consensus_liquids_m = consensus_liquids_raw.iloc[-2, :-4].T
    consensus_liquids_m.index = pd.to_datetime(consensus_liquids_m.index)
    ea_liquids_m["Consensus"] = consensus_liquids_m
    anchor_liquids_m = consensus_liquids_raw.iloc[-1, :-4].T
    anchor_liquids_m.index = pd.to_datetime(anchor_liquids_m.index)
    ea_liquids_m["Anchor"] = anchor_liquids_m
    ea_liquids_m["Anchor"].fillna(method="ffill", inplace=True)
    kpler_real = liquids_stocks_table.iloc[:, -1].resample("M").mean()
    kpler_real.index = [x + relativedelta(day=1) for x in kpler_real.index]
    ea_liquids_m["Actual"] = kpler_real
    real_vs_exp = ea_liquids_m[["Actual", "Consensus", "Anchor"]]
    real_vs_exp_liquid_fig = chart.line_chart(
        df=real_vs_exp.loc[(real_vs_exp.index >= today() - relativedelta(months=12)) & (real_vs_exp.index <= today() + relativedelta(months=3)), :],
        title="Global monthly liquids balance (kbd) - realized vs expected",
        highlight_dict={"Actual": {"mode": "bars"},
                        "Consensus": {"color": "black", "width": 2, "mode": "lines+markers"},
                        "Anchor": {"color": "red", "width": 2, "mode": "lines+markers", "dash": "dash"}}, width=750, height=500)
    if consensus_liquids_raw.columns[0][1] == "Q":
        consensus_liquids_raw.columns = [f"{x.split('Q')[1]}Q{x.split('Q')[0]}" for x in consensus_liquids_raw.columns]
    consensus_liquids = pd.DataFrame(np.nan, index=[0], columns=["Liquids Stocks"] + list(table_liquids.columns[1:]))
    consensus_liquids.loc[:, "Liquids Stocks"] = "Consensus"
    for i in range(1, len(consensus_liquids.columns) - 2):
        if "Q" in consensus_liquids.columns[i] and consensus_liquids.columns[i] != "QTD":
            consensus_liquids.loc[:, consensus_liquids.columns[i]] = consensus_liquids_raw_q[consensus_liquids.columns[i]].iloc[-2]
        else:
            if consensus_liquids.columns[i] in ["20d Change"]:
                q = dt.datetime(today().year, today().month, 1).strftime("%Y-%m-%d %H:%M:%S")
                consensus_liquids.loc[:, consensus_liquids.columns[i]] = consensus_liquids_raw[q].iloc[-2]
            elif _unrecovered('Kpler inventory 596: missing consensus branch condition'):
                q = _unrecovered('Kpler inventory 597: missing quarter selection')
                consensus_liquids.loc[:, consensus_liquids.columns[i]] = consensus_liquids_raw_q[q].iloc[-2]
            else:
                q = dt.datetime.strptime(consensus_liquids.columns[i], '%Y-%m').strftime("%Y-%m-%d %H:%M:%S")
                consensus_liquids.loc[:, consensus_liquids.columns[i]] = consensus_liquids_raw[q].iloc[-2]
    table_liquids = pd.concat([table_liquids, consensus_liquids], axis=0, ignore_index=True)
    table_liquids.to_csv(convert_path_to_linux(f"{csv_path}\\oil\\global_liquids_stocks_table.csv"))
    table_liquids["Liquids Stocks"] = table_liquids["Liquids Stocks"].replace(name_to_stock_chg_chart_link)
    table_liquids_exch = table.table_format1(df=liquids_stocks_table_exch,
        rows=["Land", "Water", "Land+Water", "Land+Water (kbd)"], highlight={"seasonal": 5}, agg_by="diff",
        agg_by_column={"Land+Water (kbd)": "mean"}, window=20, show_quarter=4, ex2020=True,
        table_head="Liquids Stocks", smooth=None, qtd=True)
    table_liquids_exch.columns = consensus_liquids.columns.to_list() + table_liquids_exch.columns[12:].to_list()
    table_liquids_exch.rename(columns={"Liquids Stocks": "Liquids ex China"}, inplace=True)
    table_crude = table.table_format1(df=global_crude_table,
        rows=['Crude On Land', 'Crude On Water', 'Total', 'Total (kbd)'], highlight={"seasonal": 5}, agg_by="diff",
        agg_by_column={"Total (kbd)": "mean"}, window=20, show_quarter=4, ex2020=True, table_head="Crude Stocks", qtd=True)
    cur_q = int((today().month - 1) / 3 + 1)
    last_day = dt.datetime(today().year, 3 * cur_q - 2, 1) - dt.timedelta(1)
    ea_last_update = dv.ea_release_dates(dataset_id="6470")
    for i in range(len(ea_last_update) - 1, 0, -1):
        if dt.datetime.strptime(ea_last_update[i][:10], "%Y-%m-%d") < last_day:
            crude_ea_latest_release = ea_last_update[i]
            break
    consensus_crude = dv.energy_aspects(dataset_id="6470", release_date=crude_ea_latest_release, start="2023-01-01")
    consensus_crude.set_index("Date", inplace=True)
    consensus_crude.index = pd.to_datetime(consensus_crude.index)
    consensus_crude = consensus_crude * 1000
    consensus_crude.columns = ["Consensus"]
    anchor_crude = dv.energy_aspects(dataset_id="6470", **_unrecovered('Kpler inventory 656–658: missing anchor request arguments'))
    anchor_crude.set_index("Date", inplace=True)
    anchor_crude.index = pd.to_datetime(anchor_crude.index)
    anchor_crude = anchor_crude * 1000
    anchor_crude.columns = ["Anchor"]
    ea_crude_m = consensus_crude.copy()
    ea_crude_m["Anchor"] = anchor_crude
    kpler_real_crude = global_crude_table.iloc[:, -1].resample("M").mean()
    kpler_real_crude.index = [x + relativedelta(day=1) for x in kpler_real_crude.index]
    ea_crude_m["Actual"] = kpler_real_crude
    real_vs_exp_crude = ea_crude_m[["Actual", "Consensus", "Anchor"]]
    real_vs_exp_crude_fig = chart.line_chart(
        df=real_vs_exp_crude.loc[(real_vs_exp_crude.index >= today() - relativedelta(months=12)) & (real_vs_exp_crude.index <= today() + relativedelta(months=3)), :],
        title="Global monthly Crude balance (kbd) - realized vs expected",
        highlight_dict={"Actual": {"mode": "bars"}, "Consensus": {"color": "black", "width": 2, "mode": "lines+markers"},
                        "Anchor": {"color": "red", "width": 2, "mode": "lines+markers", "dash": "dash"}}, width=750, height=500)
    consensus_crude = consensus_crude.loc[consensus_crude.index <= today(), :]
    consensus_crude_q = consensus_crude.resample("QS").mean()
    consensus_crude_m = consensus_crude_q.reindex(consensus_crude.index)
    consensus_crude_m.fillna(method='ffill', inplace=True)
    consensus_crude_m['_last_update'] = ea_last_update[-1]
    consensus_crude['_last_update'] = ea_last_update[-1]
    table_consensus = table.table_format1(df=consensus_crude, freq="M", lable="Change", rows=['Consensus', '_last_update'],
                                          agg_by="mean", window=20, show_quarter=3, table_head="Crude Stocks", qtd=True)
    table_crude_consensus = pd.concat([table_crude, table_consensus], axis=0, ignore_index=True)
    table_crude_consensus.to_csv(convert_path_to_linux(f"{csv_path}\\oil\\global_crude_stocks_table.csv"))
    table_crude_consensus["Crude Stocks"] = table_crude_consensus["Crude Stocks"].replace(name_to_stock_chg_chart_link)
    table_crude_exch = table.table_format1(df=global_crude_table_exch,
        rows=['Crude On Land', 'Crude On Water', 'Total', 'Total (kbd)'], highlight={"seasonal": 5}, agg_by="diff",
        agg_by_column={"Total (kbd)": "mean"}, window=20, show_quarter=4, ex2020=True, table_head="Crude Stocks", qtd=True)
    _unrecovered('Kpler inventory 717–719: unphotographed crude ex-China table postprocessing')
    table_product = table.table_format1(df=product_stocks_table,
        rows=["Land Stocks ex US Other", "Clean Oil On Water", "Total Prods", "Total Prods (kbd)"],
        highlight={"seasonal": 5}, agg_by="diff", agg_by_column={"Total Prods (kbd)": "mean"}, window=20,
        show_quarter=4, ex2020=True, table_head="Product Stocks", qtd=True)
    table_product_by_type = table.table_format1(df=product_by_type, rows=None, highlight={"seasonal": 5},
        agg_by="diff", agg_by_column=None, window=20, show_quarter=4, ex2020=True, table_head="Product Stocks", qtd=True)
    table_product_by_type.to_csv(convert_path_to_linux(f"{csv_path}\\oil\\global_product_by_type_table.csv"))
    product_by_type.to_csv(convert_path_to_linux(f"{csv_path}\\oil\\global_product_by_type.csv"))
    table_product_detail = table.table_format1(df=product_land_fill, rows=None, highlight={"seasonal": 5},
        agg_by="diff", agg_by_column=None, window=20, show_quarter=4, ex2020=True, table_head="Product Stocks", qtd=True)
    table_product_detail = pd.concat([table_product_detail, product_last_update], axis=1)
    table_product_detail.drop(["Product Land"], axis=1, inplace=True)
    table_product_detail.loc[0, 'Product Stocks'] = "US/Main"
    table_product_detail.loc[1, 'Product Stocks'] = "US/Other"
    mo_ea, _last_update = dv.ea_us_oil_weekly(sheet_name="Fig 5 US gasoline balance")
    mo_ea = mo_ea.iloc[:, -1] * 1000
    disty_ea, _last_update = dv.ea_us_oil_weekly(sheet_name="Fig 9 US distillate balance")
    disty_ea = disty_ea.iloc[:, -1] * 1000
    prod_ea = mo_ea + disty_ea
    prod_ea = prod_ea.to_frame("US Prod Consensus")
    prod_ea["_last_update"] = _last_update
    prod_ea = prod_ea.loc[prod_ea.index < today(), :]
    table_consensus_us_prod = table.table_format1(df=prod_ea, freq="M", lable="Change", rows=['US Prod Consensus', '_last_update'],
        agg_by=None, window=20, show_quarter=3, table_head="Product Stocks", qtd=True)
    table_consensus_us_prod["Last Update"] = _last_update.strftime('%Y-%m-%d')
    table_product_detail = pd.concat([table_product_detail.loc[[0], :], table_consensus_us_prod, table_product_detail.loc[1:, :]],
                                     axis=0, ignore_index=True)
    ea_us_crude = dv.energy_aspects(dataset_id="313", start="2018-01-01")
    ea_us_crude.set_index("Date", inplace=True)
    ea_us_crude.index = pd.to_datetime(ea_us_crude.index)
    ea_us_crude = ea_us_crude * 1000
    ea_us_crude.columns = ["US Crude Consensus"]
    ea_us_crude['_last_update'] = ea_last_update[-1]
    ea_us_crude = ea_us_crude.loc[ea_us_crude.index < today(), :]
    table_consensus_us_crude = table.table_format1(df=ea_us_crude, freq="M", lable="Change", rows=['US Crude Consensus', '_last_update'],
        agg_by="diff", window=20, show_quarter=3, table_head="Crude Stocks", qtd=True)
    table_ab = table.table_format1(df=ab_stocks, rows=None, highlight={"seasonal": 5}, agg_by="diff",
        agg_by_column={"Atlantic Basin (kbd)": "mean"}, window=20, show_quarter=4, ex2020=True, table_head="Crude Stocks", qtd=True)
    table_ab = pd.concat([table_ab.loc[[0], :], table_consensus_us_crude, table_ab.loc[1:, :]], axis=0, ignore_index=True)
    table_ab["Crude Stocks"] = table_ab["Crude Stocks"].replace(name_to_stock_chg_chart_link)
    table_eu = table.table_format1(df=eu_stocks, rows=None, highlight={"seasonal": 5}, agg_by="diff",
        agg_by_column={"Europe (kbd)": "mean"}, window=20, show_quarter=4, ex2020=True, table_head="Crude Stocks", qtd=True)
    table_eu["Crude Stocks"] = table_eu["Crude Stocks"].replace(name_to_stock_chg_chart_link)
    table_asian = table.table_format1(df=asian_stocks, rows=None, highlight={"seasonal": 5}, agg_by="diff",
        agg_by_column={"Asia (kbd)": "mean"}, window=20, show_quarter=4, ex2020=True, table_head="Crude Stocks", qtd=True)
    table_asian["Crude Stocks"] = table_asian["Crude Stocks"].replace(name_to_stock_chg_chart_link)
    format_column = {"0": {"width": "120px", "text-align": "left"},
                     "1": {"width": "80px", "text-align": "center", "highlight_z": [1, "_mean", "_std"], "right_border": True},
                     "2": {"width": "80px", "text-align": "center"},
                     "3": {"width": "80px", "text-align": "center"},
                     "4": {"width": "80px", "text-align": "center", "right_border": True},
                     "5": {"width": "80px", "text-align": "center"},
                     "6": {"width": "80px", "text-align": "center"},
                     "7": {"width": "80px", "text-align": "center"},
                     "8": {"width": "80px", "text-align": "center", "right_border": True},
                     "9": {"width": "80px", "text-align": "center"},
                     "10": {"width": "80px", "text-align": "center"},
                     "11": {"width": "80px", "text-align": "center"}}
    html_liquids = table.html_format(df=table_liquids,
        header="Global Liquids Stocks Change (kb) - 20d Change on 5d MA",
        footer="Consensus is the latest average sell side quarterly SND", show_date=False, format_column=format_column,
        format_row={"2": {"bottom_border": True}, "3": {"bold": True}}, precision=0,
        hide_cols=["_mean", "_std", "_last_update"], inline=False, background_color="lightblue")
    html_liquids_exch = table.html_format(df=table_liquids_exch, header='Global Liquids Stocks ex China Change (kb) - 20d Change on 5d MA',
        footer='Consensus is the latest average sell side quarterly SND', show_date=False, format_column=format_column, format_row={'2': {'bottom_border': True}, '3': {'bold': True}},
        precision=0, hide_cols=["_mean", "_std", "_last_update"], inline=False, background_color="lightblue")
    html_crude = table.html_format(df=table_crude_consensus, header='Global Crude Stocks Change (kb) - 20d Change on 5d MA',
        footer='Consensus is quarterly average of EA monthly forecast (Commercial+SPR, last update in previous quarter)', show_date=True, format_column=format_column, format_row={'1': {'bottom_border': True}, '3': {'bold': True}},
        precision=0, hide_cols=["_mean", "_std", "_last_update"], inline=False, background_color="lightblue")
    html_crude_exch = table.html_format(df=table_crude_consensus_exch, header='Global Crude Stocks ex China Change (kb) - 20d Change on 5d MA',
        footer='Consensus is quarterly average of EA monthly forecast (Commercial+SPR, last update in previous quarter)', show_date=True, format_column=format_column, format_row={'1': {'bottom_border': True}, '3': {'bold': True}},
        precision=0, hide_cols=["_mean", "_std", "_last_update"], inline=False, background_color="lightblue")
    html_product = table.html_format(df=table_product, header='Global Product Stocks Change (kb) - 20d Change on 5d MA',
        footer=None, show_date=False, format_column=format_column, format_row={'1': {'bottom_border': True}, '3': {'bold': True}},
        precision=0, hide_cols=["_mean", "_std", "_last_update"], inline=False, background_color="lightblue")
    html_product_by_type = table.html_format(df=table_product_by_type, header='Detailed Product Stocks Change by Type (kb)',
        footer=None, show_date=False, format_column=format_column, format_row=None,
        precision=0, hide_cols=["_mean", "_std", "_last_update"], inline=False, background_color="lightblue")
    html_product_details = table.html_format(df=table_product_detail, header='Detailed Product Stocks Change by Region (kb)',
        footer=None, show_date=False, format_column=format_column, format_row=None,
        precision=0, hide_cols=["_mean", "_std", "_last_update"], inline=False, background_color="lightblue")
    html_ab = table.html_format(df=table_ab, header='Atlantic Basin Crude Stocks Change (kb)',
        footer=None, show_date=False, format_column=format_column, format_row={'3': {'bottom_border': True}, '5': {'bold': True}},
        precision=0, hide_cols=["_mean", "_std", "_last_update"], inline=False, background_color="lightblue")
    html_eu = table.html_format(df=table_eu, header='European Crude Stocks Change (kb)',
        footer=None, show_date=False, format_column=format_column, format_row={'5': {'bottom_border': True}, '7': {'bold': True}},
        precision=0, hide_cols=["_mean", "_std", "_last_update"], inline=False, background_color="lightblue")
    html_asian = table.html_format(df=table_asian, header='Asian Crude Stocks Change (kb)',
        footer=None, show_date=False, format_column=format_column, format_row={'6': {'bottom_border': True}, '8': {'bold': True}},
        precision=0, hide_cols=["_mean", "_std", "_last_update"], inline=False, background_color="lightblue")
    def seasonal_chart_2col_old(df, column, title):
        df_2y = df.loc[pygdt("-2y"):, [column]]
        return chart.seasonal_chart_2col(
            df=df,
            df1=pd.concat([df_2y, (df_2y.rolling(10)).mean().loc[pygdt("-2y"):].iloc[:, 0].to_frame(f"{column} 10d ma")], axis=1),
            start=chart_sdate, column=column, column1=[f"{column} 10d ma"], title=title,
            vs_avg=True, ytd=False, freq="D", x_axis_title="Date", y_axis_title="kb", y1_axis_title="kb", y2_axis_title=None,
            highlight_dict={column: {"color": "black"}, f"{column} 10d ma": {"color": "black", "width": 2}})
    def seasonal_chart_2col(df, column, title):
        df_2y = (df.rolling(10).mean()).loc[pygdt("-2y"):, [column]]
        return chart.seasonal_chart_2col_new(
            df=df.rolling(10).mean(),
            df1=pd.concat([df_2y, df_2y.loc[pygdt("-2y"):].iloc[:, 0].to_frame(f"{column} 10d ma")], axis=1),
            start=chart_sdate, column=column, column1=[f"{column} 10d ma"], title=title,
            vs_avg=True, ytd=False, freq="D", x_axis_title="Date", y_axis_title="kb", y1_axis_title="kb", y2_axis_title=None,
            highlight_dict={column: {"color": "black"}}, highlight_dict_c2={f"{column} 10d ma": {"color": "black"}})
    chart_sdate = dt.datetime(2018, 1, 1)
    liquid_level = seasonal_chart_2col(df=liquids_stocks, column='Land+Water', title='Total Liquids Stocks - level')
    liquid_exch_level = seasonal_chart_2col(df=liquids_stocks_exch, column='Land+Water', title='Total Liquids Stocks ex China - level')
    liquid_land_level = seasonal_chart_2col(df=liquids_stocks, column='Land', title='Liquids Land Stocks - level')
    liquid_water_level = seasonal_chart_2col(df=liquids_stocks, column='Water', title='Liquids Water Stocks - level')
    liquids_stocks.to_csv(convert_path_to_linux(f"{csv_path}\\oil\\global_liquids_stocks.csv"))
    crude_level = seasonal_chart_2col(df=global_crude, column='Total', title='Total Crude Stocks - level')
    crude_exch_level = seasonal_chart_2col(df=global_crude_exch, column='Total', title='Total Crude Stocks ex China - level')
    crude_land_level = seasonal_chart_2col(df=global_crude, column='Crude On Land', title='Crude Land Stocks - level')
    crude_water_level = seasonal_chart_2col(df=global_crude, column='Crude On Water', title='Crude Water Stocks - level')
    global_crude.to_csv(convert_path_to_linux(f"{csv_path}\\oil\\global_crude_stocks.csv"))
    ab_liquids_level = seasonal_chart_2col(df=ab_liquids, column='AB Liquids', title='Atlantic Basin (US+EU) Liquids Stocks ex US other - level')
    product_level = seasonal_chart_2col(df=product_stocks, column='Total Prods', title='Total Products Stocks ex US other - level')
    product_land_level = seasonal_chart_2col(df=product_stocks, column='Land Stocks ex US Other', title='Products Land Stocks ex US Other - level')
    product_water_level = seasonal_chart_2col(df=product_stocks, column='Clean Oil On Water', title='Products Water Stocks - level')
    ab_level = seasonal_chart_2col(df=ab_stocks, column='Atlantic Basin (US+EU)', title='Atlantic Basin (US+EU) Crude Stocks - level')
    nam_level = seasonal_chart_2col(df=nam_stocks, column='United States', title='US Crude Stocks - level')
    nam_stocks.to_csv(convert_path_to_linux(f"{csv_path}\\oil\\nam_crude_stocks.csv"))
    eu_level = seasonal_chart_2col(df=eu_stocks, column='Europe', title='European Crude Stocks - level')
    other_level = seasonal_chart_2col(df=ab_stocks, column='SA,Egypt,Caribbean', title='SA,Egypt,Caribbean Crude Stocks - level')
    asia_level = seasonal_chart_2col(df=asian_stocks, column='Asia', title='Asia Crude Stocks - level')
    china_level = seasonal_chart_2col(df=asian_stocks, column='China', title='China Crude Stocks - level')
    distillate_level = seasonal_chart_2col(df=product_by_type[["Distillate"]], column='Distillate', title='Agency Distillate Product Stocks - level')
    lightends_level = seasonal_chart_2col(df=product_by_type[["Light Ends"]], column='Light Ends', title='Agency Light Ends Product Stocks - level')
    fueloil_level = seasonal_chart_2col(df=product_by_type[["Fuel Oil"]], column='Fuel Oil', title='Agency Fuel Oil Product Stocks - level')
    us_level = seasonal_chart_2col(df=product_land_fill[["US"]], column='US', title='DOE US Product Stocks - level')
    usother_level = seasonal_chart_2col(df=product_land_fill[["US Other"]], column='US Other', title='DOE US Other Product Stocks - level')
    liquid_chg = ts.rolling(liquids_stocks, method="diff", window=20, start=chart_sdate)
    liquid_exch_chg = ts.rolling(liquids_stocks_exch, method="diff", window=20, start=chart_sdate)
    crude_chg = ts.rolling(global_crude, method="diff", window=20, start=chart_sdate)
    crude_exch_chg = ts.rolling(global_crude_exch, method="diff", window=20, start=chart_sdate)
    product_chg = ts.rolling(product_stocks, method="diff", window=20, start=chart_sdate)
    ab_chg = ts.rolling(ab_stocks, method="diff", window=20, start=chart_sdate)
    nam_chg = ts.rolling(nam_stocks, method="diff", window=20, start=chart_sdate)
    eu_chg = ts.rolling(eu_stocks, method="diff", window=20, start=chart_sdate)
    other_chg = ts.rolling(ab_stocks[["SA,Egypt,Caribbean"]], method="diff", window=20, start=chart_sdate)
    asia_chg = ts.rolling(asian_stocks, method="diff", window=20, start=chart_sdate)
    distillate_chg = ts.rolling(product_by_type[["Distillate"]], method="diff", window=20, start=chart_sdate)
    lightends_chg = ts.rolling(product_by_type[["Light Ends"]], method="diff", window=20, start=chart_sdate)
    fueloil_chg = ts.rolling(product_by_type[["Fuel Oil"]], method="diff", window=20, start=chart_sdate)
    us_chg = ts.rolling(product_land_fill[["US"]], method="diff", window=20, start=chart_sdate)
    usother_chg = ts.rolling(product_land_fill[["US Other"]], method="diff", window=20, start=chart_sdate)
    def format_ytd(df):
        if 2020 in df.columns:
            df = df.drop([2020], axis=1)
        df = df.iloc[:, -5:]
        dts = pd.date_range(dt.datetime(df.columns[-1], 1, 1), dt.datetime(df.columns[-1], 12, 31))
        if len(dts) < df.shape[0]:
            df = df.iloc[:len(dts), :]
        df["Date"] = dts
        df = df.set_index("Date")
        return df
    liquid_ytd = format_ytd(ts.data_by_year(liquids_stocks['Land+Water'], freq="D", ytd=True))
    liquid_exch_ytd = format_ytd(ts.data_by_year(liquids_stocks_exch['Land+Water'], freq="D", ytd=True))
    liquid_land_ytd = format_ytd(ts.data_by_year(liquids_stocks['Land'], freq="D", ytd=True))
    liquid_water_ytd = format_ytd(ts.data_by_year(liquids_stocks['Water'], freq="D", ytd=True))
    crude_ytd = format_ytd(ts.data_by_year(global_crude['Total'], freq="D", ytd=True))
    crude_exch_ytd = format_ytd(ts.data_by_year(global_crude_exch['Total'], freq="D", ytd=True))
    crude_land_ytd = format_ytd(ts.data_by_year(global_crude['Crude On Land'], freq="D", ytd=True))
    crude_water_ytd = format_ytd(ts.data_by_year(global_crude['Crude On Water'], freq="D", ytd=True))
    product_ytd = format_ytd(ts.data_by_year(product_stocks['Total Prods'], freq="D", ytd=True))
    product_land_ytd = format_ytd(ts.data_by_year(product_stocks['Land Stocks ex US Other'], freq="D", ytd=True))
    product_water_ytd = format_ytd(ts.data_by_year(product_stocks['Clean Oil On Water'], freq="D", ytd=True))
    ab_ytd = format_ytd(ts.data_by_year(ab_stocks['Atlantic Basin (US+EU)'], freq="D", ytd=True))
    nam_ytd = format_ytd(ts.data_by_year(nam_stocks['Americas'], freq="D", ytd=True))
    eu_ytd = format_ytd(ts.data_by_year(eu_stocks['Europe'], freq="D", ytd=True))
    other_ytd = format_ytd(ts.data_by_year(ab_stocks['SA,Egypt,Caribbean'], freq="D", ytd=True))
    asia_ytd = format_ytd(ts.data_by_year(asian_stocks['Asia'], freq="D", ytd=True))
    china_ytd = format_ytd(ts.data_by_year(asian_stocks['China'], freq="D", ytd=True))
    distillate_ytd = format_ytd(ts.data_by_year(product_by_type['Distillate'], freq="D", ytd=True))
    lightends_ytd = format_ytd(ts.data_by_year(product_by_type['Light Ends'], freq="D", ytd=True))
    fueloil_ytd = format_ytd(ts.data_by_year(product_by_type['Fuel Oil'], freq="D", ytd=True))
    us_ytd = format_ytd(ts.data_by_year(product_land_fill['US'], freq="D", ytd=True))
    usother_ytd = format_ytd(ts.data_by_year(product_land_fill['US Other'], freq="D", ytd=True))
    def seasonal_chart(df, column, df1, title):
        return chart.seasonal_chart_2col_new(df=df, column=column, df1=df1, title=title,
            column_titles=["20d Change", "YTD Change"], vs_avg=True, ytd=False, freq="D",
            x_axis_title="Date", y_axis_title="kb", y1_axis_title="kb", y2_axis_title=None)
    chart_liquid_chg = seasonal_chart(df=liquid_chg, column='Land+Water', df1=liquid_ytd, title='Total Liquids Stocks')
    chart_liquid_exch_chg = seasonal_chart(df=liquid_exch_chg, column='Land+Water', df1=liquid_exch_ytd, title='Total Liquids Stocks ex China')
    chart_liquid_land_chg = seasonal_chart(df=liquid_chg, column='Land', df1=liquid_land_ytd, title='Liquids Land Stocks')
    chart_liquid_water_chg = seasonal_chart(df=liquid_chg, column='Water', df1=liquid_water_ytd, title='Liquids Water Stocks')
    chart_crude_chg = seasonal_chart(df=crude_chg, column='Total', df1=crude_ytd, title='Total Crude Stocks')
    chart_crude_exch_chg = seasonal_chart(df=crude_exch_chg, column='Total', df1=crude_exch_ytd, title='Total Crude Stocks ex China')
    chart_crude_land_chg = seasonal_chart(df=crude_chg, column='Crude On Land', df1=crude_land_ytd, title='Crude Land Stocks')
    chart_crude_water_chg = seasonal_chart(df=crude_chg, column='Crude On Water', df1=crude_water_ytd, title='Crude Water Stocks')
    chart_product_chg = seasonal_chart(df=product_chg, column='Total Prods', df1=product_ytd, title='Total Products Stocks ex US Other')
    chart_product_land_chg = seasonal_chart(df=product_chg, column='Land Stocks ex US Other', df1=product_land_ytd, title='Products Land Stocks ex US Other')
    chart_product_water_chg = seasonal_chart(df=product_chg, column='Clean Oil On Water', df1=product_water_ytd, title='Products Water Stocks')
    chart_ab_chg = seasonal_chart(df=ab_chg, column='Atlantic Basin (US+EU)', df1=ab_ytd, title='Atlantic Basin (US+EU) Crude Stocks')
    chart_nam_chg = seasonal_chart(df=nam_chg, column='United States', df1=nam_ytd, title='US Crude Stocks')
    chart_eu_chg = seasonal_chart(df=eu_chg, column='Europe', df1=eu_ytd, title='European Crude Stocks')
    chart_other_chg = seasonal_chart(df=other_chg, column='SA,Egypt,Caribbean', df1=other_ytd, title='Other AB Crude Stocks')
    chart_asia_chg = seasonal_chart(df=asia_chg, column='Asia', df1=asia_ytd, title='Asia Crude Stocks')
    chart_china_chg = seasonal_chart(df=asia_chg, column='China', df1=china_ytd, title='China Crude Stocks')
    figs_lvl = []
    figs_lvl.append('<a id="liquid_land"></a>')
    figs_lvl.append(liquid_land_level)
    figs_lvl.append('<a id="liquid_water"></a>')
    figs_lvl.append(liquid_water_level)
    figs_lvl.append('<a id="crude_land"></a>')
    figs_lvl.append(crude_land_level)
    figs_lvl.append('<a id="crude_water"></a>')
    figs_lvl.append(crude_water_level)
    figs_lvl.append('<a id="product_land"></a>')
    figs_lvl.append(product_land_level)
    figs_lvl.append('<a id="product_water"></a>')
    figs_lvl.append(product_water_level)
    figs_lvl.append('<a id="ab_liquids"></a>')
    figs_lvl.append(ab_liquids_level)
    figs_lvl.append('<a id="ab_level"></a>')
    figs_lvl.append(ab_level)
    figs_lvl.append('<a id="nam_level"></a>')
    figs_lvl.append(nam_level)
    figs_lvl.append('<a id="eu_level"></a>')
    figs_lvl.append(eu_level)
    figs_lvl.append('<a id="other_level"></a>')
    figs_lvl.append(other_level)
    figs_lvl.append('<a id="asia_level"></a>')
    figs_lvl.append(asia_level)
    figs_lvl.append('<a id="china_level"></a>')
    figs_lvl.append(china_level)
    figs_lvl.append('<a id="distillate_level"></a>')
    figs_lvl.append(distillate_level)
    figs_lvl.append('<a id="lightends_level"></a>')
    figs_lvl.append(lightends_level)
    figs_lvl.append('<a id="fueloil_level"></a>')
    figs_lvl.append(fueloil_level)
    figs_lvl.append('<a id="us_level"></a>')
    figs_lvl.append(us_level)
    figs_lvl.append('<a id="usother_level"></a>')
    figs_lvl.append(usother_level)
    table.figures_to_html(figs_lvl, f"{html_path}\\oil\\links\\stocks_level.html", task_name=report_name)
    figs_chg = []
    figs_chg.append('<a id="liquid_land"></a>')
    figs_chg.append(chart_liquid_land_chg)
    figs_chg.append('<a id="liquid_water"></a>')
    figs_chg.append(chart_liquid_water_chg)
    figs_chg.append('<a id="crude_land"></a>')
    figs_chg.append(chart_crude_land_chg)
    figs_chg.append('<a id="crude_water"></a>')
    figs_chg.append(chart_crude_water_chg)
    figs_chg.append('<a id="product_land"></a>')
    figs_chg.append(chart_product_land_chg)
    figs_chg.append('<a id="product_water"></a>')
    figs_chg.append(chart_product_water_chg)
    figs_chg.append('<a id="ab_level"></a>')
    figs_chg.append(chart_ab_chg)
    figs_chg.append('<a id="nam_level"></a>')
    figs_chg.append(chart_nam_chg)
    figs_chg.append('<a id="eu_level"></a>')
    figs_chg.append(chart_eu_chg)
    figs_chg.append('<a id="other_level"></a>')
    figs_chg.append(chart_other_chg)
    figs_chg.append('<a id="asia_level"></a>')
    figs_chg.append(chart_asia_chg)
    figs_chg.append('<a id="china_level"></a>')
    figs_chg.append(chart_china_chg)
    table.figures_to_html(figs_chg, f"{html_path}\\oil\\links\\stocks_change.html", task_name=report_name)
    figs = []
    figs.append(table.html_text(f"Updated at {dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"))
    figs.append(_unrecovered('Kpler inventory 1253: clipped wiki link after /1774687371/Global+Liquids+In'))
    figs.append(html_liquids)
    figs.append(html_liquids_exch)
    figs.append(html_crude)
    figs.append(html_crude_exch)
    figs.append(html_product)
    figs.append(html_product_by_type)
    figs.append(html_product_details)
    figs.append(html_ab)
    figs.append(html_eu)
    figs.append(html_asian)
    figs.append([real_vs_exp_liquid_fig, real_vs_exp_crude_fig])
    figs.append('<a id="liquids"></a>')
    figs.append(liquid_level)
    figs.append(chart_liquid_chg)
    figs.append(liquid_exch_level)
    figs.append(chart_liquid_exch_chg)
    figs.append('<a id="crude"></a>')
    figs.append(crude_level)
    figs.append(chart_crude_chg)
    figs.append(crude_exch_level)
    figs.append(chart_crude_exch_chg)
    figs.append(product_level)
    figs.append(chart_product_chg)
    figs.append(_unrecovered('Kpler inventory 1278: clipped links HTML after stocks_change.html and Detailed Stocks Change Charts'))
    table.to_html([table.html_text(report_name, style="font-family:Calibri;", tag='h1')] + figs,
        f"{html_path}\\oil\\{file_name}.html", task_name=report_name)

def update_exprod(send_to):
    global_crude, eu_stocks, nam_stocks, asian_stocks, ab_stocks = crude_inventory()
    product_water = product_on_water()
    liquids_stocks = global_crude.copy()
    liquids_stocks["Land"] = liquids_stocks["Crude On Land"] #+ liquids_stocks["Land Stocks"]
    liquids_stocks["Water"] = liquids_stocks["Crude On Water"] #+ liquids_stocks["Clean Oil On Water"]
    liquids_stocks["Land+Water"] = liquids_stocks["Land"] + liquids_stocks["Water"]
    liquids_stocks["Land+Water (kbd)"] = liquids_stocks["Land+Water"].diff()
    liquids_stocks = liquids_stocks[["Land", "Water", "Land+Water", "Land+Water (kbd)"]]
    liquids_stocks_table = liquids_stocks.rolling(5).mean()
    global_crude_table = global_crude.rolling(5).mean()
    ab_liquids = ab_stocks["Atlantic Basin (US+EU)"].to_frame("AB Liquids")
    table_liquids = table.table_format1(df=liquids_stocks_table,
        rows=["Land", "Water", "Land+Water", "Land+Water (kbd)"], highlight={"seasonal": 5},
        agg_by="diff", agg_by_column={"Land+Water (kbd)": "mean"}, window=20, show_quarter=4,
        ex2020=True, table_head="Liquids Stocks", smooth=None, qtd=True)
    table_liquids.columns = [str(x) for x in table_liquids.columns]
    consensus_liquids_raw = pd.read_csv(convert_path_to_linux(_unrecovered('Kpler inventory 1317: clipped consensus CSV path')))
    consensus_liquids_raw.set_index("Unnamed: 0", inplace=True)
    _unrecovered('Kpler inventory 1319: unphotographed consensus preparation line')
    consensus_liquids_raw.drop("Date", axis=1, inplace=True)
    if consensus_liquids_raw.columns[0][1] == "Q":
        consensus_liquids_raw.columns = [f"{x.split('Q')[1]}Q{x.split('Q')[0]}" for x in consensus_liquids_raw.columns]
    consensus_liquids = pd.DataFrame(np.nan, index=[0], columns=["Liquids Stocks"] + list(table_liquids.columns[1:]))
    consensus_liquids.loc[:, "Liquids Stocks"] = "Consensus"
    for i in range(1, len(consensus_liquids.columns) - 2):
        if "Q" in consensus_liquids.columns[i] and consensus_liquids.columns[i] != "QTD":
            consensus_liquids.loc[:, consensus_liquids.columns[i]] = consensus_liquids_raw[consensus_liquids.columns[i]].iloc[-2]
        else:
            if consensus_liquids.columns[i] in ["20d Change", "QTD"]:
                q = f"{today().year}Q{pd.Timestamp(today()).quarter}"
            else:
                q = (f"{dt.datetime.strptime(consensus_liquids.columns[i], '%Y-%m').year}Q"
                     f"{pd.Timestamp(dt.datetime.strptime(consensus_liquids.columns[i], '%Y-%m')).quarter}")
            consensus_liquids.loc[:, consensus_liquids.columns[i]] = consensus_liquids_raw[q].iloc[-2]
    table_liquids = pd.concat([table_liquids, consensus_liquids], axis=0, ignore_index=True)
    table_liquids.to_csv(convert_path_to_linux(f"{csv_path}\\oil\\global_liquids_stocks_table.csv"))
    table_liquids["Liquids Stocks"] = table_liquids["Liquids Stocks"].replace(name_to_stock_chg_chart_link)
    table_crude = table.table_format1(df=global_crude_table,
        rows=['Crude On Land', 'Crude On Water', 'Total', 'Total (kbd)'], highlight={"seasonal": 5},
        agg_by="diff", agg_by_column={"Total (kbd)": "mean"}, window=20, show_quarter=4,
        ex2020=True, table_head="Crude Stocks", qtd=True)
    cur_q = int((today().month - 1) / 3 + 1)
    last_day = dt.datetime(today().year, 3 * cur_q - 2, 1) - dt.timedelta(1)
    ea_last_update = dv.ea_release_dates(dataset_id="6470")
    for i in range(len(ea_last_update) - 1, 0, -1):
        if dt.datetime.strptime(ea_last_update[i][:10], "%Y-%m-%d") < last_day:
            crude_ea_latest_release = ea_last_update[i]
            break
    consensus_crude = dv.energy_aspects(dataset_id="6470", release_date=crude_ea_latest_release, start="2023-01-01")
    consensus_crude.set_index("Date", inplace=True)
    consensus_crude.index = pd.to_datetime(consensus_crude.index)
    consensus_crude = consensus_crude * 1000
    consensus_crude.columns = ["Consensus"]
    consensus_crude = consensus_crude.loc[consensus_crude.index < today(), :]
    consensus_crude_q = consensus_crude.resample("QS").mean()
    consensus_crude_m = consensus_crude_q.reindex(consensus_crude.index)
    consensus_crude_m.fillna(method="ffill", inplace=True)
    consensus_crude_m['_last_update'] = ea_last_update[-1]
    table_consensus = table.table_format1(df=consensus_crude, freq="M", lable="Change", rows=['Consensus', '_last_update'],
        agg_by="mean", window=20, show_quarter=3, table_head="Crude Stocks", qtd=True)
    table_crude_consensus = pd.concat([table_crude, table_consensus], axis=0, ignore_index=True)
    table_crude_consensus.to_csv(convert_path_to_linux(f"{csv_path}\\oil\\global_crude_stocks_table.csv"))
    table_crude_consensus["Crude Stocks"] = table_crude_consensus["Crude Stocks"].replace(name_to_stock_chg_chart_link)
    mo_ea, _last_update = dv.ea_us_oil_weekly(sheet_name="Fig 5 US gasoline balance")
    mo_ea = mo_ea.iloc[:, -1] * 1000
    disty_ea, _last_update = dv.ea_us_oil_weekly(sheet_name="Fig 9 US distillate balance")
    disty_ea = disty_ea.iloc[:, -1] * 1000
    prod_ea = mo_ea + disty_ea
    prod_ea = prod_ea.to_frame("US Prod Consensus")
    prod_ea['_last_update'] = _last_update
    prod_ea = prod_ea.loc[prod_ea.index < today(), :]
    table_consensus_us_prod = table.table_format1(df=prod_ea, freq="M", lable="Change", rows=['US Prod Consensus', '_last_update'],
        agg_by=None, window=20, show_quarter=3, table_head="Product Stocks", qtd=True)
    table_consensus_us_prod["Last Update"] = _last_update
    ea_us_crude = dv.energy_aspects(dataset_id="313", start="2018-01-01")
    ea_us_crude.set_index("Date", inplace=True)
    ea_us_crude.index = pd.to_datetime(ea_us_crude.index)
    ea_us_crude = ea_us_crude * 1000
    ea_us_crude.columns = ["US Crude Consensus"]
    ea_us_crude['_last_update'] = ea_last_update[-1]
    ea_us_crude = ea_us_crude.loc[ea_us_crude.index < today(), :]
    table_consensus_us_crude = table.table_format1(df=ea_us_crude, freq="M", lable="Change", rows=['US Crude Consensus', '_last_update'],
        agg_by="diff", window=20, show_quarter=3, table_head="Crude Stocks", qtd=True)
    table_ab = table.table_format1(df=ab_stocks, rows=None, highlight={"seasonal": 5}, agg_by="diff",
        agg_by_column={"Atlantic Basin (kbd)": "mean"}, window=20, show_quarter=4, ex2020=True, table_head="Crude Stocks", qtd=True)
    table_ab = pd.concat([table_ab.loc[[0], :], table_consensus_us_crude, table_ab.loc[1:, :]], axis=0, ignore_index=True)
    table_ab["Crude Stocks"] = table_ab["Crude Stocks"].replace(name_to_stock_chg_chart_link)
    table_eu = table.table_format1(df=eu_stocks, rows=None, highlight={"seasonal": 5}, agg_by="diff",
        agg_by_column={"Europe (kbd)": "mean"}, window=20, show_quarter=4, ex2020=True, table_head="Crude Stocks", qtd=True)
    table_eu["Crude Stocks"] = table_eu["Crude Stocks"].replace(name_to_stock_chg_chart_link)
    table_asian = table.table_format1(df=asian_stocks, rows=None, highlight={"seasonal": 5}, agg_by="diff",
        agg_by_column={"Asia (kbd)": "mean"}, window=20, show_quarter=4, ex2020=True, table_head="Crude Stocks", qtd=True)
    table_asian["Crude Stocks"] = table_asian["Crude Stocks"].replace(name_to_stock_chg_chart_link)
    format_column = {"0": {"width": "120px", "text-align": "left"},
                     "1": {"width": "80px", "text-align": "center", "highlight_z": [1, "_mean", "_std"], "right_border": True},
                     "2": {"width": "80px", "text-align": "center"},
                     "3": {"width": "80px", "text-align": "center"},
                     "4": {"width": "80px", "text-align": "center", "right_border": True},
                     "5": {"width": "80px", "text-align": "center"},
                     "6": {"width": "80px", "text-align": "center"},
                     "7": {"width": "80px", "text-align": "center"},
                     "8": {"width": "80px", "text-align": "center", "right_border": True},
                     "9": {"width": "80px", "text-align": "center"},
                     "10": {"width": "80px", "text-align": "center"},
                     "11": {"width": "80px", "text-align": "center"}}
    html_liquids = table.html_format(df=table_liquids,
        header="Global Liquids Stocks Change (kb) - 20d Change on 5d MA",
        footer="Consensus is the latest average sell side quarterly SND", show_date=False, format_column=format_column,
        format_row={"2": {"bottom_border": True}, "3": {"bold": True}}, precision=0,
        hide_cols=["_mean", "_std", "_last_update"], inline=False, background_color="lightblue")
    html_crude = table.html_format(df=table_crude_consensus, header='Global Crude Stocks Change (kb) - 20d Change on 5d MA',
        footer='Consensus is quarterly average of EA monthly forecast (last update in previous quarter)', show_date=True, format_column=format_column, format_row={'1': {'bottom_border': True}, '3': {'bold': True}},
        precision=0, hide_cols=["_mean", "_std", "_last_update"], inline=False, background_color="lightblue")
    html_ab = table.html_format(df=table_ab, header='Atlantic Basin Crude Stocks Change (kb)',
        footer=None, show_date=False, format_column=format_column, format_row={'3': {'bottom_border': True}, '5': {'bold': True}},
        precision=0, hide_cols=["_mean", "_std", "_last_update"], inline=False, background_color="lightblue")
    html_eu = table.html_format(df=table_eu, header='European Crude Stocks Change (kb)',
        footer=None, show_date=False, format_column=format_column, format_row={'5': {'bottom_border': True}, '7': {'bold': True}},
        precision=0, hide_cols=["_mean", "_std", "_last_update"], inline=False, background_color="lightblue")
    html_asian = table.html_format(df=table_asian, header='Asian Crude Stocks Change (kb)',
        footer=None, show_date=False, format_column=format_column, format_row={'6': {'bottom_border': True}, '8': {'bold': True}},
        precision=0, hide_cols=["_mean", "_std", "_last_update"], inline=False, background_color="lightblue")
    def seasonal_chart_2col_old(df, column, title):
        df_2y = df.loc[pygdt("-2y"):, [column]]
        return chart.seasonal_chart_2col(
            df=df,
            df1=pd.concat([df_2y, (df_2y.rolling(10)).mean().loc[pygdt("-2y"):].iloc[:, 0].to_frame(f"{column} 10d ma")], axis=1),
            start=chart_sdate, column=column, column1=[f"{column} 10d ma"], title=title,
            vs_avg=True, ytd=False, freq="D", x_axis_title="Date", y_axis_title="kb", y1_axis_title="kb", y2_axis_title=None,
            highlight_dict={column: {"color": "black"}, f"{column} 10d ma": {"color": "black", "width": 2}})
    def seasonal_chart_2col(df, column, title):
        df_2y = (df.rolling(10).mean()).loc[pygdt("-2y"):, [column]]
        return chart.seasonal_chart_2col_new(
            df=df.rolling(10).mean(),
            df1=pd.concat([df_2y, df_2y.loc[pygdt("-2y"):].iloc[:, 0].to_frame(f"{column} 10d ma")], axis=1),
            start=chart_sdate, column=column, column1=[f"{column} 10d ma"], title=title,
            vs_avg=True, ytd=False, freq="D", x_axis_title="Date", y_axis_title="kb", y1_axis_title="kb", y2_axis_title=None,
            highlight_dict={column: {"color": "black"}}, highlight_dict_c2={f"{column} 10d ma": {"color": "black"}})
    chart_sdate = dt.datetime(2018, 1, 1)
    liquid_level = seasonal_chart_2col(df=liquids_stocks, column='Land+Water', title='Total Liquids Stocks - level')
    liquid_land_level = seasonal_chart_2col(df=liquids_stocks, column='Land', title='Liquids Land Stocks - level')
    liquid_water_level = seasonal_chart_2col(df=liquids_stocks, column='Water', title='Liquids Water Stocks - level')
    liquids_stocks.to_csv(convert_path_to_linux(f"{csv_path}\\oil\\global_liquids_stocks.csv"))
    crude_level = seasonal_chart_2col(df=global_crude, column='Total', title='Total Crude Stocks - level')
    crude_land_level = seasonal_chart_2col(df=global_crude, column='Crude On Land', title='Crude Land Stocks - level')
    crude_water_level = seasonal_chart_2col(df=global_crude, column='Crude On Water', title='Crude Water Stocks - level')
    global_crude.to_csv(convert_path_to_linux(f"{csv_path}\\oil\\global_crude_stocks.csv"))
    ab_liquids_level = seasonal_chart_2col(df=ab_liquids, column='AB Liquids', title='Atlantic Basin (US+EU) Liquids Stocks ex US other - level')
    ab_level = seasonal_chart_2col(df=ab_stocks, column='Atlantic Basin (US+EU)', title='Atlantic Basin (US+EU) Crude Stocks - level')
    nam_level = seasonal_chart_2col(df=nam_stocks, column='United States', title='US Crude Stocks - level')
    eu_level = seasonal_chart_2col(df=eu_stocks, column='Europe', title='European Crude Stocks - level')
    other_level = seasonal_chart_2col(df=ab_stocks, column='SA,Egypt,Caribbean', title='SA,Egypt,Caribbean Crude Stocks - level')
    asia_level = seasonal_chart_2col(df=asian_stocks, column='Asia', title='Asia Crude Stocks - level')
    china_level = seasonal_chart_2col(df=asian_stocks, column='China', title='China Crude Stocks - level')
    liquid_chg = ts.rolling(liquids_stocks, method="diff", window=20, start=chart_sdate)
    crude_chg = ts.rolling(global_crude, method="diff", window=20, start=chart_sdate)
    ab_chg = ts.rolling(ab_stocks, method="diff", window=20, start=chart_sdate)
    nam_chg = ts.rolling(nam_stocks, method="diff", window=20, start=chart_sdate)
    eu_chg = ts.rolling(eu_stocks, method="diff", window=20, start=chart_sdate)
    other_chg = ts.rolling(ab_stocks[["SA,Egypt,Caribbean"]], method="diff", window=20, start=chart_sdate)
    asia_chg = ts.rolling(asian_stocks, method="diff", window=20, start=chart_sdate)
    def format_ytd(df):
        if 2020 in df.columns:
            df = df.drop([2020], axis=1)
        df = df.iloc[:, -5:]
        dts = pd.date_range(dt.datetime(df.columns[-1], 1, 1), dt.datetime(df.columns[-1], 12, 31))
        if len(dts) < df.shape[0]:
            df = df.iloc[:len(dts), :]
        df["Date"] = dts
        df = df.set_index("Date")
        return df
    liquid_ytd = format_ytd(ts.data_by_year(liquids_stocks['Land+Water'], freq="D", ytd=True))
    liquid_land_ytd = format_ytd(ts.data_by_year(liquids_stocks['Land'], freq="D", ytd=True))
    liquid_water_ytd = format_ytd(ts.data_by_year(liquids_stocks['Water'], freq="D", ytd=True))
    crude_ytd = format_ytd(ts.data_by_year(global_crude['Total'], freq="D", ytd=True))
    crude_land_ytd = format_ytd(ts.data_by_year(global_crude['Crude On Land'], freq="D", ytd=True))
    crude_water_ytd = format_ytd(ts.data_by_year(global_crude['Crude On Water'], freq="D", ytd=True))
    ab_ytd = format_ytd(ts.data_by_year(ab_stocks['Atlantic Basin (US+EU)'], freq="D", ytd=True))
    nam_ytd = format_ytd(ts.data_by_year(nam_stocks['Americas'], freq="D", ytd=True))
    eu_ytd = format_ytd(ts.data_by_year(eu_stocks['Europe'], freq="D", ytd=True))
    other_ytd = format_ytd(ts.data_by_year(ab_stocks['SA,Egypt,Caribbean'], freq="D", ytd=True))
    asia_ytd = format_ytd(ts.data_by_year(asian_stocks['Asia'], freq="D", ytd=True))
    china_ytd = format_ytd(ts.data_by_year(asian_stocks['China'], freq="D", ytd=True))
    def seasonal_chart(df, column, df1, title):
        return chart.seasonal_chart_2col_new(df=df, column=column, df1=df1, title=title,
            column_titles=["20d Change", "YTD Change"], vs_avg=True, ytd=False, freq="D",
            x_axis_title="Date", y_axis_title="kb", y1_axis_title="kb", y2_axis_title=None)
    chart_liquid_chg = seasonal_chart(df=liquid_chg, column='Land+Water', df1=liquid_ytd, title='Total Liquids Stocks')
    chart_liquid_land_chg = seasonal_chart(df=liquid_chg, column='Land', df1=liquid_land_ytd, title='Liquids Land Stocks')
    chart_liquid_water_chg = seasonal_chart(df=liquid_chg, column='Water', df1=liquid_water_ytd, title='Liquids Water Stocks')
    chart_crude_chg = seasonal_chart(df=crude_chg, column='Total', df1=crude_ytd, title='Total Crude Stocks')
    chart_crude_land_chg = seasonal_chart(df=crude_chg, column='Crude On Land', df1=crude_land_ytd, title='Crude Land Stocks')
    chart_crude_water_chg = seasonal_chart(df=crude_chg, column='Crude On Water', df1=crude_water_ytd, title='Crude Water Stocks')
    chart_ab_chg = seasonal_chart(df=ab_chg, column='Atlantic Basin (US+EU)', df1=ab_ytd, title='Atlantic Basin (US+EU) Crude Stocks')
    chart_nam_chg = seasonal_chart(df=nam_chg, column='United States', df1=nam_ytd, title='US Crude Stocks')
    chart_eu_chg = seasonal_chart(df=eu_chg, column='Europe', df1=eu_ytd, title='European Crude Stocks')
    chart_other_chg = seasonal_chart(df=other_chg, column='SA,Egypt,Caribbean', df1=other_ytd, title='Other AB Crude Stocks')
    chart_asia_chg = seasonal_chart(df=asia_chg, column='Asia', df1=asia_ytd, title='Asia Crude Stocks')
    chart_china_chg = seasonal_chart(df=asia_chg, column='China', df1=china_ytd, title='China Crude Stocks')
    figs_lvl = []
    figs_lvl.append('<a id="liquid_land"></a>')
    figs_lvl.append(liquid_land_level)
    figs_lvl.append('<a id="liquid_water"></a>')
    figs_lvl.append(liquid_water_level)
    figs_lvl.append('<a id="crude_land"></a>')
    figs_lvl.append(liquid_level)
    figs_lvl.append(crude_land_level)
    figs_lvl.append('<a id="crude_water"></a>')
    figs_lvl.append(crude_water_level)
    figs_lvl.append('<a id="ab_liquids"></a>')
    figs_lvl.append(ab_liquids_level)
    figs_lvl.append('<a id="ab_level"></a>')
    figs_lvl.append(ab_level)
    figs_lvl.append('<a id="nam_level"></a>')
    figs_lvl.append(nam_level)
    figs_lvl.append('<a id="eu_level"></a>')
    figs_lvl.append(eu_level)
    figs_lvl.append('<a id="other_level"></a>')
    figs_lvl.append(other_level)
    figs_lvl.append('<a id="asia_level"></a>')
    figs_lvl.append(asia_level)
    figs_lvl.append('<a id="china_level"></a>')
    figs_lvl.append(china_level)
    table.figures_to_html(figs_lvl, f"{html_path}\\oil\\links\\stocks_level.html", task_name=report_name)
    figs_chg = []
    figs_chg.append('<a id="liquid_land"></a>')
    figs_chg.append(chart_liquid_land_chg)
    figs_chg.append('<a id="liquid_water"></a>')
    figs_chg.append(chart_liquid_water_chg)
    figs_chg.append('<a id="crude_land"></a>')
    figs_chg.append(chart_crude_land_chg)
    figs_chg.append('<a id="crude_water"></a>')
    figs_chg.append(chart_crude_water_chg)
    figs_chg.append('<a id="ab_level"></a>')
    figs_chg.append(chart_ab_chg)
    figs_chg.append('<a id="nam_level"></a>')
    figs_chg.append(chart_nam_chg)
    figs_chg.append('<a id="eu_level"></a>')
    figs_chg.append(chart_eu_chg)
    figs_chg.append('<a id="other_level"></a>')
    figs_chg.append(chart_other_chg)
    figs_chg.append('<a id="asia_level"></a>')
    figs_chg.append(chart_asia_chg)
    figs_chg.append('<a id="china_level"></a>')
    figs_chg.append(chart_china_chg)
    table.figures_to_html(figs_chg, f"{html_path}\\oil\\links\\stocks_change.html", task_name=report_name)
    figs = []
    figs.append(table.html_text(f"Updated at {dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"))
    figs.append(_unrecovered('Kpler inventory 1757: clipped wiki hyperlink'))
    figs.append(html_liquids)
    figs.append(html_crude)
    figs.append(html_ab)
    figs.append(html_eu)
    figs.append(html_asian)
    figs.append('<a id="liquids"></a>')
    figs.append(liquid_level)
    figs.append('<a id="crude"></a>')
    figs.append(crude_level)
    figs.append(chart_liquid_chg)
    figs.append(chart_crude_chg)
    figs.append(u'<a href="{:s}\\oil\\links\\stocks_level.html">Detailed Stocks Level Charts</a><br>'.format(html_path))
    figs.append(u'<a href="{:s}\\oil\\links\\stocks_change.html">Detailed Stocks Change Charts</a><br>'.format(html_path))
    figs.append(u'<a href="{:s}\\oil\\oil_on_water.html">Oil On Water</a><br>'.format(html_path))
    figs.append(u'<a href="{:s}\\oil\\floating_storage.html">Floating Storage</a><br>'.format(html_path))
    table.figures_to_html([table.html_text(report_name, style="font-family:Calibri;", tag='h1')] + figs,
        f"{html_path}\\oil\\{file_name}.html", task_name=report_name)

if __name__ == "__main__":
    update(send_to=send_to)
