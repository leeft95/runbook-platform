import pandas as pd
import datetime as dt
import sys
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import ecm.cmds.data as dv
import ecm.cmds.kpler as kpler
import ecm.cmds.time_series as ts
import ecm.cmds.table as table
import ecm.cmds.chart as chart
from ecm.cmds.config import root_path
from ecm.cmds._email import send_email
from ecm.cmds.cdr import today
from ecm.cmds.config import html_path, oil_group

send_to = ["rzhao@elementcapital.com", "ltrindade@elementcapital.com"]
report_name = "Crude on Water"
file_name = "oil_on_water"  # without .py
file_path = f"{root_path}\\autoreports\\reports\\oil\\{file_name}.py"


def _missing_photo_text(lines):
    raise NotImplementedError(f"Transcription gap in oil_on_water.py, photographed lines {lines}")


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
        start_datetime=dt.datetime(2023, 7, 1, 9, 30), timezone="Europe/London",
        task_name=report_name,
        task=WinTaskPoC(name=f'"{report_name}"', filepath=f'"{file_path}"'),
        background_task=True,
        python_executable=r"C:\local\python\miniconda\envs\ecm_cmds\pythonw.exe")
    win_task.create_task()



def subplots(df):
    plot_rows = 2
    plot_cols = 4
    fig = make_subplots(rows=plot_rows, cols=plot_cols, vertical_spacing=0.1)
    x = 0
    for i in range(1, plot_rows + 1):
        for j in range(1, plot_cols + 1):
            fig.add_trace(go.Scatter(x=df.index, y=df[df.columns[x]].values,
                                     name=df.columns[x], mode='lines'), row=i, col=j)
            x = x + 1
    fig.update_layout(
        margin=dict(l=10, r=20, t=30, b=0),
        legend=dict(orientation="h", yanchor="top", xanchor="center", y=-0.1, x=0.5,
                    font=dict(family="Arial", size=12, color="black")), width=1000, height=600)
    fig.for_each_yaxis(lambda axis: axis.update(dict(tickfont=dict(size=10))))
    fig.for_each_xaxis(lambda axis: axis.update(dict(tickfont=dict(size=10))))
    fig.update_layout(title="Oil on Water by Loading Region", title_x=0.5)
    return fig


def oil_on_water_old(send_to):
    fleet = dv.kpler('/v1/fleet-metrics?metric=loaded_vessels&zones=world&period=daily&unit=mmbbl&pr' + _missing_photo_text("78"))
    fleet = kpler.convert_to_ts(fleet)
    fig1 = chart.seasonal_chart(df=fleet, title="Total Oil On Water (mb)", freq='D')
    water = dv.kpler(link=("/v1/fleet-metrics?metric=loaded_vessels&period=daily&startDate=2017-01-01&unit=kb&"
                           "split=Origin%20Trading%20Regions&products=crude%2fco"))
    water = kpler.convert_to_ts(kpler_links=water, end_dt="-1d")
    water["Total"] = water.sum(axis=1)
    required_regions = ['Latin America', 'USGC (US Gulf Coast)', 'MED Zone (MED Sea+Black Sea)',
                        'Mideast Gulf', 'West African Gulf', 'South-East Asia', 'Unknown', 'Total']
    available_columns = [x for x in required_regions if x in water.columns]
    water = water[available_columns]
    water = water / 1000
    water["Total MTD Chg"] = water["Total"].copy()
    table_data = table.table_format1(
        df=water, rows=None, highlight={"window": 92}, agg_by="mean",
        agg_by_column={"Total MTD Chg": "diff"}, window=20, ex2020=True, show_quarter=3,
        table_head="Region", qtd=True)
    html_table = table.html_format(**_missing_photo_text("115-118"),
        show_date=False,
        format_column={'0': {'width': '120px', 'text-align': 'left'}, '1': {'width': '80px', 'text-align': 'center', 'highlight_z': [1, '_mean', '_std']}, '2': {'width': '80px', 'text-align': 'center'}, '3': {'width': '80px', 'text-align': 'center'}, '4': {'width': '80px', 'text-align': 'center'}, '5': {'width': '80px', 'text-align': 'center'}, '6': {'width': '80px', 'text-align': 'center'}, '7': {'width': '80px', 'text-align': 'center'}, '8': {'width': '80px', 'text-align': 'center'}, '9': {'width': '80px', 'text-align': 'center'}, '10': {'width': '80px', 'text-align': 'center'}},
        format_row={"5": {"bottom_border": True}, "6": {"bold": True}, "7": {"bold": True}},
        precision=0, hide_cols=["_last_update", "_mean", "_std"])
    figs = []
    figs.append(html_table)
    figs.append(fig1)
    figs.append(subplots(water.tail(252)))
    figs.append(table.html_text(f"Updated at {dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"))
    table.figures_to_html([table.html_text(report_name, style="font-family:Calibri;", tag='h1')] + figs,
                          f"{html_path}\\oil\\{file_name}.html", task_name=report_name)
    send_email(send_to=send_to, subject=report_name, body=figs, html_path=f"{html_path}\\oil\\{file_name}.html")


def oil_on_water_data(above_7d=False):
    if above_7d:
        water = dv.kpler(
            (f'/v1/fleet-metrics?metric=floating_storage&zones=world&floatingStorageDurationMin=7&'
             f'floatingStorageDurationMax=Inf&period=daily&startDate=2017-03-01&unit=mmbbl&split=Origin'
             + _missing_photo_text("156")))
    else:
        water = dv.kpler(link=("/v1/fleet-metrics?metric=loaded_vessels&period=daily&startDate=2017-01-01&unit=mmbbl&"
                               "split=Origin%20Countries&products=crude%2fco"))
    water = kpler.convert_to_ts(kpler_links=water, end_dt="-1d")
    water["Total"] = water.sum(axis=1)
    water["Sanctioned"] = water[['Russian Federation', 'Iran', 'Venezuela']].sum(axis=1)
    water["Non-Sanctioned"] = water["Total"] - water["Sanctioned"]
    water = water[["Sanctioned", 'Russian Federation', 'Iran', 'Venezuela', "Non-Sanctioned", 'Saudi Arabia', 'United States',
                   'Brazil', 'Total']]
    water = water.rename(columns={
        'Russian Federation': "&emsp;Russian", 'Iran': "&emsp;Iran", 'Venezuela': "&emsp;Venezuela",
        'Saudi Arabia': "&emsp;Saudi Arabia", 'United States': "&emsp;United States", 'Brazil': "&emsp;Brazil"})
    water["Total MTD Chg"] = water["Total"].copy()
    return water


def oil_on_water(water, above_7d=False):
    if above_7d:
        header = 'Floating above 7d'
    else:
        header = 'Oil on Water'
    table_data = table.table_format1(
        df=water, rows=None, highlight={"window": 92}, agg_by="mean",
        agg_by_column={"Total MTD Chg": "diff"}, window=20, ex2020=True, show_quarter=3,
        table_head="Region", qtd=True)
    html_table = table.html_format(
        df=table_data, header=f"{header} (mb)", footer=None, show_date=False,
        format_column={'0': {'width': '120px', 'text-align': 'left'}, '1': {'width': '80px', 'text-align': 'center', 'highlight_z': [1, '_mean', '_std']}, '2': {'width': '80px', 'text-align': 'center'}, '3': {'width': '80px', 'text-align': 'center'}, '4': {'width': '80px', 'text-align': 'center'}, '5': {'width': '80px', 'text-align': 'center'}, '6': {'width': '80px', 'text-align': 'center'}, '7': {'width': '80px', 'text-align': 'center'}, '8': {'width': '80px', 'text-align': 'center'}, '9': {'width': '80px', 'text-align': 'center'}, '10': {'width': '80px', 'text-align': 'center'}},
        format_row={"7": {"bottom_border": True}, "8": {"bold": True}, "9": {"bold": True}},
        precision=0, hide_cols=["_last_update", "_mean", "_std"])
    figs = []
    figs.append("<div style='font-family:Calibri; '>")
    figs.append(html_table)
    fig1 = chart.seasonal_chart(df=water['Total'], title=f"Total Crude {header} (mb)", freq='D')
    figs.append(fig1)
    fig2 = chart.seasonal_chart(df=water["Sanctioned"], title=f"Sanctioned {header} (mb)", freq='D')
    fig3 = chart.seasonal_chart(df=water["Non-Sanctioned"], title=f"Non-Sanctioned {header} (mb)", freq='D')
    figs.append(fig2)
    figs.append(fig3)
    return figs


def update(send_to=send_to):
    water = oil_on_water_data()
    figs0 = oil_on_water(water)
    water1 = oil_on_water_data(above_7d=True)
    figs1 = oil_on_water(water1, above_7d=True)
    figs = list(zip(figs0, figs1))
    table.to_html([table.html_text(report_name, style="font-family:Calibri;", tag='h1')] + figs,
                  f"{html_path}\\oil\\{file_name}.html", task_name=report_name)


def create_table(fleet, header=None):
    fleet.rename(columns={"Total": "Stocks"}, inplace=True)
    fleet['Date'] = pd.to_datetime(fleet['Date'])
    fleet['year'] = (fleet['Date']).dt.year
    fleet['month'] = (fleet['Date']).dt.month
    fleet['delta'] = fleet['Stocks'].diff()
    fleet['MTD'] = fleet.groupby(['year', 'month'])['delta'].cumsum()
    fleet['YTD'] = fleet.groupby('year')['delta'].cumsum()
    fleet['4W MA (delta)'] = fleet['delta'].rolling(window=28).mean()
    fleet['7D MA (delta)'] = fleet['delta'].rolling(window=7).mean()
    fleet_table = fleet[-15:].copy()
    fleet_table.reset_index(drop=True, inplace=True)
    fleet_table = fleet_table[['Date', 'Stocks', '7D MA (delta)', '4W MA (delta)', 'MTD', 'YTD']]
    fleet_table['Date'] = fleet_table['Date'].dt.strftime('%Y-%m-%d')
    return table.html_format(df=fleet_table, precision=1, header=header)


def floating_storage():
    figs = []
    fs = dv.kpler(
        (f'/v1/fleet-metrics?metric=floating_storage&zones=world&floatingStorageDurationMin=7&'
         f'floatingStorageDurationMax=Inf&period=daily&startDate=2017-03-01&unit=mmbbl&products=crude/co'))
    fs15 = dv.kpler(
        (f'/v1/fleet-metrics?metric=floating_storage&zones=world&floatingStorageDurationMin=15&'
         f'floatingStorageDurationMax=Inf&period=daily&startDate=2017-03-01&unit=mmbbl&products=crude/co'))
    figs.append(create_table(fs.copy(), header="Floating Storage above 7d (mb)"))
    fs = kpler.convert_to_ts(fs)
    fs15 = kpler.convert_to_ts(fs15)
    fs_chart = pd.concat([fs, fs15], axis=1)
    fs_chart.columns = [">7d", ">15d"]
    figs.append(chart.line_chart(df=fs_chart.iloc[-365:, :], tickformat=None,
                                  title=_missing_photo_text("279: Floating Storage above 7d a...")))
    sg = dv.kpler(
        ('/v1/fleet-metrics?metric=floating_storage&zones=Singapore%20Strait&floatingStorageDurationMin=7&'
         'floatingStorageDurationMax=Inf&period=daily&startDate=2017-03-01&unit=kb&products=crude/co'))
    ms = dv.kpler(
        ('/v1/fleet-metrics?metric=floating_storage&zones=Malacca%20Strait&floatingStorageDurationMin=7&'
         'floatingStorageDurationMax=Inf&period=daily&startDate=2017-03-01&unit=kb&products=crude/co'))
    ns = dv.kpler(
        ('/v1/fleet-metrics?metric=floating_storage&zones=North%20Sea&floatingStorageDurationMin=7&'
         'floatingStorageDurationMax=Inf&period=daily&startDate=2017-03-01&unit=kb&products=crude/co'))
    ara = dv.kpler(
        ('/v1/fleet-metrics?metric=floating_storage&zones=ARA&floatingStorageDurationMin=7&'
         'floatingStorageDurationMax=Inf&period=daily&startDate=2017-03-01&unit=kb&products=crude/co'))
    ch = dv.kpler(
        ('/v1/fleet-metrics?metric=floating_storage&zones=China&floatingStorageDurationMin=7&'
         'floatingStorageDurationMax=Inf&period=daily&startDate=2017-03-01&unit=kb&products=crude/co'))
    med = dv.kpler(
        ('/v1/fleet-metrics?metric=floating_storage&zones=Med&floatingStorageDurationMin=7&'
         'floatingStorageDurationMax=Inf&period=daily&startDate=2017-03-01&unit=kb&products=crude/co'))
    sg = kpler.convert_to_ts(sg)
    ms = kpler.convert_to_ts(ms)
    ns = kpler.convert_to_ts(ns)
    ara = kpler.convert_to_ts(ara)
    ch = kpler.convert_to_ts(ch)
    med = kpler.convert_to_ts(med)
    nwe = ara + ns
    sg_malacca = ms + sg
    float_region = pd.concat([nwe, sg_malacca, ch, med], axis=1)
    float_region.columns = ['NWE', 'Sing and Malacca', 'China', 'Med']
    figs.append(chart.line_chart(df=float_region.iloc[-365:, :], tickformat=None,
                                  title=_missing_photo_text("310: Floating Storage by Regio...")))
    return figs


if __name__ == "__main__":
    update(send_to=send_to)
