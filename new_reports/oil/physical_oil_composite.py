import pandas as pd
import datetime as dt
import plotly as py
import sys

import ecm.cmds.time_series as ts
import ecm.cmds.table as table
import ecm.cmds.chart as chart
from ecm.cmds.cdr import today
from ecm.cmds.utils import convert_path_to_linux
from functools import partial
from pyg_mongo import *
from ecm.cmds.config import url, root_path, html_path

db = partial(mongo_table, db='data', table='platts', url=url, pk=['name', 'ticker', 'platts_ticker'])
outputs_csv_oil = f"{root_path}\\outputs\\csvs\\oil"
outputs_json_oil = f"{root_path}\\outputs\\json\\oil"
outputs_html_oil_link = f"{root_path}\\outputs\\htmls\\oil\\links"
report_name = "Physical Oil Page"
file_name = "physical_oil_composite"  # without .py
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
        days=Days.MONDAY | Days.TUESDAY | Days.WEDNESDAY | Days.THURSDAY | Days.FRIDAY | Days.SATURDAY,
        start_datetime=dt.datetime(2023, 7, 1, 5, 30), timezone="Europe/London",
        task_name=report_name,
        task=WinTaskPoC(name=f'"{report_name}"', filepath=f'"{file_path}"'),
        background_task=True,
        python_executable=r"C:\local\python\miniconda\envs\ecm_cmds\pythonw.exe")
    win_task.create_task()



def update():
    sdate = today() - dt.timedelta(364)
    figs = []
    figs.append("Physical oil index = (2 * Physical Crude + Physical Gasoil + Physical Gasoline) / 4 <br>")
    figs.append("Blend front spread = (2 * Crude Blend + Gasoil Blend $bbl + Gasoline Blend $bbl) / 4 <br>")
    figs.append("Unit: $/bbl")
    crude = ts.read_csv(f"{outputs_csv_oil}\\global_physical_crude_detail.csv", index_name='date')
    gasoil = ts.read_csv(f"{outputs_csv_oil}\\global_physical_gasoil_detail.csv", index_name='Unnamed: 0')
    gasoline = ts.read_csv(f"{outputs_csv_oil}\\global_physical_gasoline_detail.csv", index_name='Unnamed: 0')
    eu_crude = ts.read_csv(f"{outputs_csv_oil}\\physical_crude_detail_eu.csv", index_name='date')
    us_crude = ts.read_csv(f"{outputs_csv_oil}\\physical_crude_detail_us.csv", index_name='date')
    asia_crude = ts.read_csv(f"{outputs_csv_oil}\\physical_crude_detail_asia.csv", index_name='date')
    eu_gasoil = ts.read_csv(f"{outputs_csv_oil}\\eu_physical_gasoil_detail.csv", index_name='date')
    us_gasoil = ts.read_csv(f"{outputs_csv_oil}\\us_physical_gasoil_detail.csv", index_name='date')
    asia_gasoil = ts.read_csv(f"{outputs_csv_oil}\\asia_physical_gasoil_detail.csv", index_name='Unnamed: 0')
    eu_gasoline = ts.read_csv(f"{outputs_csv_oil}\\eu_physical_gasoline_detail.csv", index_name='Unnamed: 0')
    us_gasoline = ts.read_csv(f"{outputs_csv_oil}\\us_physical_gasoline_detail.csv", index_name='date')
    asia_gasoline = ts.read_csv(f"{outputs_csv_oil}\\asia_physical_gasoline_detail.csv", index_name='Unnamed: 0')
    crude.columns = ["Physical Index", "Blend Front Spread", "EU", "US", "Asia"]
    gasoil.columns = ["Physical Index", "Blend Front Spread", "EU", "US", "Asia"]
    gasoline.columns = ["Physical Index", "Blend Front Spread", "EU", "US", "Asia"]

    def legend_position(fig):
        return fig.update_layout(legend=dict(
            orientation="h", yanchor="bottom", y=-0.2, xanchor="center", x=0.5))

    total = (2 * crude + gasoil + gasoline) / 4
    total.fillna(method="ffill", inplace=True)
    total.to_csv(convert_path_to_linux(f"{outputs_csv_oil}\\global_physical_liquids.csv"))
    global_table = table.table_with_link(
        data=total, header="Global Physical Price Table", name='Global Phys Oil',
        folder=outputs_html_oil_link, inline=False, width1=100, width2=100,
        chart_columns={tuple(total.columns): 'seasonal'})
    df_chart = total[["Physical Index", "Blend Front Spread"]]
    df_chart.dropna(inplace=True)
    df_chart = df_chart.loc[df_chart.index >= sdate, :]
    global_chart = chart.line_chart(
        df=df_chart[["Physical Index"]], data_ply2=df_chart[["Blend Front Spread"]],
        secondary_y=True, title='Global Physical Oil vs Blend Front Spread',
        y_axis_title='Index', ply2_axis_title='Spread', width=750, height=500)
    global_chart.write_json(convert_path_to_linux(f"{outputs_json_oil}\\global_physical_liquids_fig.json"))

    eu_spread = (2 * eu_crude.iloc[:, 1] + eu_gasoil.iloc[:, 1] / 7.45 + eu_gasoline.iloc[:, 1] * 0.42) / 4
    eu_total = pd.concat([total["EU"], eu_spread, crude["EU"], gasoil["EU"], gasoline["EU"]], axis=1)
    eu_total.columns = ["Physical Index", "Blend Front Spread", eu_crude.columns[0], eu_gasoil.columns[0],
                        eu_gasoline.columns[0]]
    eu_total.fillna(method="ffill", inplace=True)
    eu_table = table.table_with_link(
        data=eu_total, name='EU Phys Oil', folder=outputs_html_oil_link,
        inline=False, width1=100, width2=100, chart_columns={tuple(eu_total.columns): 'seasonal'})
    df_chart = eu_total[["Physical Index", "Blend Front Spread"]]
    df_chart.dropna(inplace=True)
    df_chart = df_chart.loc[df_chart.index >= sdate, :]
    eu_chart = chart.line_chart(
        df=df_chart[["Physical Index"]], data_ply2=df_chart[["Blend Front Spread"]],
        secondary_y=True, title='EU Physical Oil vs Blend Front Spread',
        y_axis_title='Index', ply2_axis_title='Spread', width=750, height=500)

    us_spread = (2 * us_crude.iloc[:, 1] + us_gasoil.iloc[:, 1] * 0.42 + us_gasoline.iloc[:, 1] * 0.42) / 4
    us_total = pd.concat([total["US"], us_spread, crude["US"], gasoil["US"], gasoline["US"]], axis=1)
    us_total.columns = ["Physical Index", "Blend Front Spread", us_crude.columns[0], us_gasoil.columns[0],
                        us_gasoline.columns[0]]
    us_total.fillna(method="ffill", inplace=True)
    us_table = table.table_with_link(
        data=us_total, name='US Phys Oil', folder=outputs_html_oil_link,
        inline=False, width1=100, width2=100)
    df_chart = us_total[["Physical Index", "Blend Front Spread"]]
    df_chart.dropna(inplace=True)
    df_chart = df_chart.loc[df_chart.index >= sdate, :]
    us_chart = chart.line_chart(
        df=df_chart[["Physical Index"]], data_ply2=df_chart[["Blend Front Spread"]],
        secondary_y=True, title='US Physical Oil vs Blend Front Spread',
        y_axis_title='Index', ply2_axis_title='Spread', width=750, height=500)

    asia_spread = (2 * asia_crude.iloc[:, 1] + asia_gasoil.iloc[:, 1] + asia_gasoline.iloc[:, 1]) / 4
    asia_total = pd.concat([total["Asia"], asia_spread, crude["Asia"], gasoil["Asia"], gasoline["Asia"]], axis=1)
    asia_total.columns = ["Physical Index", "Blend Front Spread", asia_crude.columns[0], asia_gasoil.columns[0],
                        asia_gasoline.columns[0]]
    asia_total.fillna(method="ffill", inplace=True)
    asia_table = table.table_with_link(
        data=asia_total, name='Asia Phys Oil', folder=outputs_html_oil_link,
        inline=False, width1=100, width2=100)
    df_chart = asia_total[["Physical Index", "Blend Front Spread"]]
    df_chart.dropna(inplace=True)
    df_chart = df_chart.loc[df_chart.index >= sdate, :]
    asia_chart = chart.line_chart(
        df=df_chart[["Physical Index"]], data_ply2=df_chart[["Blend Front Spread"]],
        secondary_y=True, title='Asia Physical Oil vs Blend Front Spread',
        y_axis_title='Index', ply2_axis_title='Spread', width=750, height=500)

    figs.append(global_table)
    figs.append(global_chart)
    table_row = [eu_table, us_table, asia_table]
    fig_charts = [legend_position(eu_chart), legend_position(us_chart), legend_position(asia_chart)]
    figs.append(table.figs_to_grid(table_row + fig_charts, columns=3))
    figs.append("<br>")

    figs_table = []
    figs_charts = []
    crude = crude.loc[crude.index >= sdate, :]
    figs_table.append(table.table_with_link(
        data=crude, name='Global Phys Crude', folder=outputs_html_oil_link,
        inline=False, width1=100, width2=100))
    figs_charts.append(py.io.read_json(convert_path_to_linux(f"{outputs_json_oil}\\global_physical_crude_fig.json")))

    gasoil = gasoil.loc[gasoil.index >= sdate, :]
    figs_table.append(table.table_with_link(
        data=gasoil, name='Global Phys Gasoil', folder=outputs_html_oil_link,
        inline=False, width1=100, width2=100))
    figs_charts.append(py.io.read_json(convert_path_to_linux(f"{outputs_json_oil}\\global_physical_gasoil_fig.json")))

    gasoline = gasoline.loc[gasoline.index >= sdate, :]
    figs_table.append(table.table_with_link(
        data=gasoline, name='Global Phys Gasoline', folder=outputs_html_oil_link,
        inline=False, width1=100, width2=100))
    figs_charts.append(py.io.read_json(convert_path_to_linux(f"{outputs_json_oil}\\global_physical_gasoline_fig.json")))

    figs.append(table.figs_to_grid(figs_table + figs_charts, columns=3))
    figs.append('<br>')
    figs.append('<br> Highlight colors: <br>')
    figs.append('Last 10 days (daily change vs last 3m): green > +2sd; lightgreen > +1sd; red < -2sd; orange < -1sd. <br>')
    figs.append('20d ma (price vs 20d ma): green > +2sd; lightgreen > +1sd; red < -2sd; orange < -1sd. <br>')
    figs.append(table.html_text(f"Updated at {dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"))
    table.to_html(
        [table.html_text("Composite Physical Oil Page", style="font-family:Calibri;", tag='h1')] + figs,
        f"{html_path}\\oil\\physical_oil_page.html", task_name=report_name)


if __name__ == "__main__":
    update()
