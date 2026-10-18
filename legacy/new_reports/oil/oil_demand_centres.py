import datetime as dt
import sys
import ecm.cmds.data as dv
import ecm.cmds.kpler as kpler
import ecm.cmds.time_series as ts
import ecm.cmds.table as table
import ecm.cmds.chart as chart
from ecm.cmds.cdr import today
from ecm.cmds.config import root_path, json_path, html_path
from ecm.cmds._email import send_email
from ecm.cmds.utils import convert_path_to_linux

send_to = None
report_name = "Oil Demand Centres"
file_name = "oil_demand_centres"  # without .py
file_path = f"{root_path}\\autoreports\\reports\\oil\\{file_name}.py"


def _missing_photo_text(lines):
    raise NotImplementedError(f"Transcription gap in oil_demand_centres.py, photographed lines {lines}")


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
        start_datetime=dt.datetime(2022, 7, 1, 9, 32), timezone="Europe/London",
        task_name=report_name,
        task=WinTaskPoC(name=f'"{report_name}"', filepath=f'"{file_path}"'),
        background_task=True,
        python_executable=r"C:\local\python\miniconda\envs\ecm_cmds\pythonw.exe")
    win_task.create_task()



def update(send_to):
    crude_imports = dv.kpler(link=(
        "/v1/flows?toZones=China,India,Japan,South%20Korea,Thailand,Taiwan,Vietnam,Indonesia,Brazil,C"
        + _missing_photo_text('46: remaining zones') +
        "Argentina&products=crude%2fco&flowDirection=Import&"
        "split=Destination%20Countries&granularity=daily&onlyRealized=true&startDate=2017-01-01&unit=kbd"))
    crude_imports_eu = dv.kpler(link=(
        "/v1/flows?flowDirection=Import&granularity=daily&startDate=2017-01-06&products="
        "crude/co&toZones=EU&fromZones=Asia,%20Africa,%20Americas,%20Oceania,%20Russian%20Federation&"
        "unit=kbd&split=Origin%20Countries&withIntraCountry=false"))
    clean_exports = dv.kpler(link=(
        "/v1/flows?fromZones=China,India,Japan,South%20Korea,Thailand,Taiwan,Vietnam,Indonesia,Brazil,"
        + _missing_photo_text('54: remaining zones') +
        "Argentina&products=Clean%20Products&flowDirection=Export&"
        "split=Origin%20Countries&granularity=daily&onlyRealized=true&startDate=2017-01-01&unit=kbd"))
    clean_exports_eu = dv.kpler(link=(
        "/v1/flows?fromZones=EU&products=Clean%20Products&flowDirection=Export&withIntraCountry=false&"
        "split=Origin%20Countries&granularity=daily&onlyRealized=true&startDate=2017-01-01&unit=kbd"))
    clean_imports = dv.kpler(link=(
        "/v1/flows?toZones=China,India,Japan,South%20Korea,Thailand,Taiwan,Vietnam,Indonesia,B"
        + _missing_photo_text('62: remaining zones') +
        "Argentina&products=Clean%20Products&flowDirection=Import&"
        "split=Destination%20Countries&granularity=daily&onlyRealized=true&startDate=2017-01-01&unit=kbd"))
    clean_imports_eu = dv.kpler(link=(
        "/v1/flows?toZones=EU&products=Clean%20Products&flowDirection=Import&withIntraCountry=false&"
        "split=Destination%20Countries&granularity=daily&onlyRealized=true&startDate=2017-01-01&unit=kbd"))
    clean_net_export = dv.kpler(link=(
        "/v1/flows?fromZones=China,India,Japan,South%20Korea,Thailand,Taiwan,Vietnam,Indonesia"
        + _missing_photo_text('69: remaining zones') +
        "Argentina&products=Clean%20Products&flowDirection=NetExport&"
        "split=Origin%20Countries&granularity=daily&onlyRealized=true&startDate=2017-01-01&unit=kbd"))
    clean_net_export_eu = dv.kpler(link=(
        "/v1/flows?fromZones=EU&products=Clean%20Products&flowDirection=NetExport&withIntraCountry=false&"
        "split=Origin%20Countries&granularity=daily&onlyRealized=true&startDate=2017-01-01&unit=kbd"))
    pg_clean = dv.kpler(link=(
        "/v1/flows?flowDirection=Export&granularity=daily&startDate=2017-01-01&fromZones=Unite"
        + _missing_photo_text('77: remaining zones') +
        "unit=kbd&withForecast=false&split=Origin%20Countries&products=Clean%20Products"))
    crude_stocks = dv.kpler(link=(
        "/v1/inventories?zones=China,India,Japan,South%20Korea,Thailand,Taiwan,Vietnam,Indones"
        + _missing_photo_text('80: remaining zones') +
        "Argentina&startDate=2017-01-01&period=daily&split=byCountry"))
    crude_stocks = kpler.convert_to_ts(kpler_links=crude_stocks, end_dt="-1d")
    crude_stocks = crude_stocks[['Argentina', 'Brazil', 'Chile', 'China', 'India', 'Indonesia',
                                  'Jap' + _missing_photo_text('85: remaining country selection')]]
    crude_stocks["Total"] = crude_stocks.sum(axis=1)
    crude_stocks["Other Asia"] = crude_stocks[["Japan", "South Korea", "Thailand", "Taiwan", "Vietnam", "Indonesia"]].sum(axis=1)
    crude_stocks["Latam"] = crude_stocks[["Brazil", "Chile", "Mexico", "Argentina"]].sum(axis=1)
    crude_stocks = crude_stocks[["China", "India", "Other Asia", "Latam", "Total"]]
    crude_stocks = crude_stocks / 1000

    crude_imports = kpler.convert_to_ts(kpler_links=crude_imports, end_dt="-1d")
    crude_imports_eu = kpler.convert_to_ts(kpler_links=crude_imports_eu, end_dt="-1d")
    crude_imports["Total"] = crude_imports.sum(axis=1)
    crude_imports["Other Asia"] = crude_imports[["Japan", "South Korea", "Thailand", "Taiwan", "Vietnam", "Indonesia"]].sum(axis=1)
    crude_imports["Latam"] = crude_imports[["Brazil", "Chile", "Mexico", "Argentina"]].sum(axis=1)
    crude_imports = crude_imports[["China", "India", "Other Asia", "Latam", "Total"]]

    clean_exports = kpler.convert_to_ts(kpler_links=clean_exports, end_dt="-1d")
    clean_exports_eu = kpler.convert_to_ts(kpler_links=clean_exports_eu, end_dt="-1d")
    clean_exports["Total"] = clean_exports.sum(axis=1)
    clean_exports["Other Asia"] = clean_exports[["Japan", "South Korea", "Thailand", "Taiwan", "Vietnam", "Indonesia"]].sum(axis=1)
    clean_exports["Latam"] = clean_exports[["Brazil", "Chile", "Mexico", "Argentina"]].sum(axis=1)
    clean_exports = clean_exports[["China", "India", "Other Asia", "Latam", "Total"]]

    clean_imports = kpler.convert_to_ts(kpler_links=clean_imports, end_dt="-1d")
    clean_imports_eu = kpler.convert_to_ts(kpler_links=clean_imports_eu, end_dt="-1d")
    clean_imports["Total"] = clean_imports.sum(axis=1)
    clean_imports["Other Asia"] = clean_imports[["Japan", "South Korea", "Thailand", "Taiwan", "Vietnam", "Indonesia"]].sum(axis=1)
    clean_imports["Latam"] = clean_imports[["Brazil", "Chile", "Mexico", "Argentina"]].sum(axis=1)
    clean_imports = clean_imports[["China", "India", "Other Asia", "Latam", "Total"]]

    clean_net_export = kpler.convert_to_ts(kpler_links=clean_net_export, end_dt="-1d")
    clean_net_export_eu = kpler.convert_to_ts(kpler_links=clean_net_export_eu, end_dt="-1d")
    clean_net_export["Total"] = clean_net_export.sum(axis=1)
    clean_net_export["Other Asia"] = clean_net_export[["Japan", "South Korea", "Thailand", "Taiwan", "Vietnam", "Indonesia"]].sum(axis=1)
    clean_net_export["Latam"] = clean_net_export[["Brazil", "Chile", "Mexico", "Argentina"]].sum(axis=1)
    clean_net_export = clean_net_export[["China", "India", "Other Asia", "Latam", "Total"]]

    net_clean = -1 * clean_net_export  # change to import - export
    crude_im_clean_ex = crude_imports - clean_exports
    crude_imports["Latam"] = crude_imports["Latam"] + clean_imports["Latam"]
    crude_imports.rename(columns={"Latam": "Latam crude+clean"}, inplace=True)
    pg_clean = kpler.convert_to_ts(kpler_links=pg_clean, end_dt="-1d")
    clean_exports["PG"] = pg_clean.sum(axis=1)
    clean_exports.rename(columns={"Total": "Total ex PG"}, inplace=True)
    clean_exports["Total inc PG"] = clean_exports[["Total ex PG", "PG"]].sum(axis=1)
    clean_exports = clean_exports[['China', 'India', 'Other Asia', 'Latam', 'PG', 'Total ex PG', 'Total inc PG']]

    def table_format2(df, table_head):
        return table.table_format2_vs_month(df=df, rows=None, highlight={"window": 92}, agg_by="mean",
                                            agg_by_column=None, window=10, window1=20,
                                            benchmark_quarter=f"{today().year-1}-Q4", table_head=table_head)
    table_net = table_format2(df=crude_im_clean_ex, table_head="Crude Imports - Product Exports")
    table_crude = table_format2(df=crude_imports, table_head="Crude Imports")
    table_clean_export = table_format2(df=clean_exports, table_head="Products Exports")
    table_net_clean = table_format2(df=net_clean, table_head="Net Products Imports")
    html_net = table.html_format(df=table_net, header='Crude import - product export (kbd)',
                                    footer='Other Asia: Japan, South Korea, Thailand, Taiwan, Vietnam, Indonesia',
                                    show_date=False,
                                    format_column={table_net.columns[0]: {"width": "120px", "text-align": "left"},
                                                   table_net.columns[1]: {"width": "80px", "text-align": "center", "highlight_z": [1, "_mean", "_std"]},
                                                   tuple(table_net.columns[2:]): {"width": "80px", "text-align": "center"}},
                                    format_row={3: {"bottom_border": True}, 4: {"bold": True}}, precision=0,
                                    hide_cols=["_last_update", "_mean", "_std", "_mean1", "_std1"],
                                    inline=False, background_color="lightblue", na_rep="-")
    with open(convert_path_to_linux(f"{html_path}\\oil\\crude_imp_prod_exp.html"), "w") as f:
        f.write(html_net)
    html_crude = table.html_format(df=table_crude, header='Crude import (kbd)',
                                    footer='Latam: Brazil, Chile, Mexico, Argentina',
                                    show_date=False,
                                    format_column={table_crude.columns[0]: {"width": "120px", "text-align": "left"},
                                                   table_crude.columns[1]: {"width": "80px", "text-align": "center", "highlight_z": [1, "_mean", "_std"]},
                                                   tuple(table_crude.columns[2:]): {"width": "80px", "text-align": "center"}},
                                    format_row={3: {"bottom_border": True}, 4: {"bold": True}}, precision=0,
                                    hide_cols=["_last_update", "_mean", "_std", "_mean1", "_std1"],
                                    inline=False, background_color="lightblue", na_rep="-")
    html_clean_export = table.html_format(df=table_clean_export, header='Product export (kbd)',
                                    show_date=False,
                                    format_column={table_clean_export.columns[0]: {"width": "120px", "text-align": "left"},
                                                   table_clean_export.columns[1]: {"width": "80px", "text-align": "center", "highlight_z": [1, "_mean", "_std"]},
                                                   tuple(table_clean_export.columns[2:]): {"width": "80px", "text-align": "center"}},
                                    format_row={4: {"bottom_border": True}, 5: {"bold": True}}, precision=0,
                                    hide_cols=["_last_update", "_mean", "_std", "_mean1", "_std1"],
                                    inline=False, background_color="lightblue", na_rep="-")
    html_net_clean = table.html_format(df=table_net_clean, header='Product import - export (kbd)',
                                    show_date=False,
                                    format_column={table_net_clean.columns[0]: {"width": "120px", "text-align": "left"},
                                                   table_net_clean.columns[1]: {"width": "80px", "text-align": "center", "highlight_z": [1, "_mean", "_std"]},
                                                   tuple(table_net_clean.columns[2:]): {"width": "80px", "text-align": "center"}},
                                    format_row={3: {"bottom_border": True}, 4: {"bold": True}}, precision=0,
                                    hide_cols=["_last_update", "_mean", "_std", "_mean1", "_std1"],
                                    inline=False, background_color="lightblue", na_rep="-")
    stock_ma = ts.rolling(crude_stocks, method="mean", window=10, start=dt.datetime(2018, 1, 1))
    net_ma = ts.rolling(crude_im_clean_ex, method="mean", window=20, start=dt.datetime(2018, 1, 1))
    crude_ma = ts.rolling(crude_imports, method="mean", window=20, start=dt.datetime(2018, 1, 1))
    clean_ma = ts.rolling(clean_exports, method="mean", window=20, start=dt.datetime(2018, 1, 1))
    net_clean_ma = ts.rolling(net_clean, method="mean", window=20, start=dt.datetime(2018, 1, 1))
    chart_stock = chart.seasonal_chart(df=stock_ma, column='Total', title='Total Asia+Latam crude stocks (10d MA)', vs_avg=True,
                                         ytd=False, freq="D", x_axis_title="Date", y_axis_title='mb',
                                         y1_axis_title='mb', y2_axis_title=None, width=750, height=500)
    chart_net = chart.seasonal_chart(df=net_ma, column='Total', title='Total crude import - product export (20d MA)', vs_avg=True,
                                         ytd=False, freq="D", x_axis_title="Date", y_axis_title='kbd',
                                         y1_axis_title='kbd', y2_axis_title=None, width=750, height=500)
    chart_net.write_json(convert_path_to_linux(f"{json_path}\\oil\\crude_imp_prod_exp.json"))
    chart_crude = chart.seasonal_chart(df=crude_ma, column='Total', title='Total crude import (20d MA)', vs_avg=True,
                                         ytd=False, freq="D", x_axis_title="Date", y_axis_title='kbd',
                                         y1_axis_title='kbd', y2_axis_title=None, width=750, height=500)
    chart_clean_export = chart.seasonal_chart(df=clean_ma, column='Total ex PG', title='Total product export ex PG (20d MA)', vs_avg=True,
                                         ytd=False, freq="D", x_axis_title="Date", y_axis_title='kbd',
                                         y1_axis_title='kbd', y2_axis_title=None, width=750, height=500)
    chart_net_clean = chart.seasonal_chart(df=net_clean_ma, column='Total', title='Total product import - export (20d MA)', vs_avg=True,
                                         ytd=False, freq="D", x_axis_title="Date", y_axis_title='kbd',
                                         y1_axis_title='kbd', y2_axis_title=None, width=750, height=500)
    regions_index = [0, 1, 2]
    for i in regions_index:
        figs_region = []
        figs_region.append(chart.seasonal_chart(df=stock_ma, column=stock_ma.columns[i], title=f"{stock_ma.columns[i]} crude stocks (10d MA)",
                                                vs_avg=True, ytd=False, freq="D", x_axis_title="Date",
                                                y_axis_title='mb', y1_axis_title='mb', y2_axis_title=None, width=750, height=500))
        figs_region.append(chart.seasonal_chart(df=net_ma, column=net_ma.columns[i], title=f"{net_ma.columns[i]} crude import - product export (20d MA)",
                                                vs_avg=True, ytd=False, freq="D", x_axis_title="Date",
                                                y_axis_title='kbd', y1_axis_title='kbd', y2_axis_title=None, width=750, height=500))
        figs_region.append(chart.seasonal_chart(df=crude_ma, column=crude_ma.columns[i], title=f"{crude_ma.columns[i]} crude import (20d MA)",
                                                vs_avg=True, ytd=False, freq="D", x_axis_title="Date",
                                                y_axis_title='kbd', y1_axis_title='kbd', y2_axis_title=None, width=750, height=500))
        figs_region.append(chart.seasonal_chart(df=clean_ma, column=clean_ma.columns[i], title=f"{clean_ma.columns[i]} product export (20d MA)",
                                                vs_avg=True, ytd=False, freq="D", x_axis_title="Date",
                                                y_axis_title='kbd', y1_axis_title='kbd', y2_axis_title=None, width=750, height=500))
        file_path = f"{html_path}\\oil\\links\\kpler_imp_exp_{net_ma.columns[i]}.html"
        table.figures_to_html(figs_region, filename=file_path, task_name=report_name)
        html_net = html_net.replace(net_ma.columns[i], f'<a href="{file_path}">{net_ma.columns[i]}</a>')
    figs = []
    figs.append(table.html_text(f"Updated at {dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}<br>"))
    figs.append(html_net)
    figs.append(html_crude)
    figs.append(html_clean_export)
    figs.append(chart_stock)
    figs.append(chart_net)
    figs.append(chart_crude)
    figs.append(chart_clean_export)
    table.figures_to_html([table.html_text(report_name, style="font-family:Calibri;", tag='h1')] + figs,
                          f"{html_path}\\oil\\{file_name}.html", task_name=report_name)
    if today().weekday() in [1, 3]:
        send_email(send_to=send_to, subject=report_name, body=figs, html_path=f"{html_path}\\oil\\{file_name}.html")


if __name__ == "__main__":
    update(send_to=send_to)
