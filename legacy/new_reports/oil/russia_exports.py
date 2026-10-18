import pandas as pd
import datetime as dt
import sys
import ecm.cmds.data as dv
import ecm.cmds.kpler as kpler
import ecm.cmds.time_series as ts
import ecm.cmds.table as table
import ecm.cmds.chart as chart
from ecm.cmds.config import root_path
from ecm.cmds.cdr import today
from ecm.cmds._email import send_email
from ecm.cmds.config import html_path

send_to = None
report_name = "Russia Exports"
file_name = "russia_exports"  # without .py
file_path = f"{root_path}\\autoreports\\reports\\oil\\{file_name}.py"
outputs_html_oil_link = f"{root_path}\\outputs\\htmls\\oil\\links"


def _missing_photo_text(lines):
    raise NotImplementedError(f"Transcription gap in russia_exports.py, photographed lines {lines}")


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
        start_datetime=dt.datetime(2022, 7, 1, 9, 32), timezone="Europe/London",
        task_name=report_name,
        task=WinTaskPoC(name=f'"{report_name}"', filepath=f'"{file_path}"'),
        background_task=True,
        python_executable=r"C:\local\python\miniconda\envs\ecm_cmds\pythonw.exe")
    win_task.create_task()



def seasonal_chart(df, column, title):
    chart_sdate = dt.datetime(2018, 1, 1)
    df_ma = ts.rolling(df, method="mean", window=20, start=chart_sdate)
    return chart.seasonal_chart(df=df_ma, column=column, title=title, vs_avg=True,
                                ytd=False, freq="D", x_axis_title="Date",
                                y_axis_title="kbd", y1_axis_title="kbd", y2_axis_title=None)


def html_format(df, header):
    return table.html_format(
        df=df, header=header, footer=None, show_date=False,
        format_column={
            "0": {"width": "120px", "text-align": "left"},
            "1": {"width": "80px", "text-align": "center", "highlight_z": [1, "_mean", "_std"]},
            "2": {"width": "80px", "text-align": "center", "highlight_z": [2, "_mean1", "_std1"]},
            "3": {"width": "80px", "text-align": "center"},
            "4": {"width": "80px", "text-align": "center"},
            "5": {"width": "80px", "text-align": "center"},
            "6": {"width": "80px", "text-align": "center"},
            "7": {"width": "80px", "text-align": "center"},
            "8": {"width": "80px", "text-align": "center"},
            "9": {"width": "80px", "text-align": "center"},

        }, format_row={"0": {"bottom_border": True, "bold": True}}, precision=0,
        hide_cols=["_last_update", "_mean", "_std", "_mean1", "_std1"])


def update(send_to):
    crude = dv.kpler(link=("/v1/flows?flowDirection=Export&granularity=daily&startDate=2015-01-01&"
                           "fromZones=Russian%20Federation&unit=kbd&withForecast=true&"
                           "split=Origin%20Installations&onlyRealized=true&products=crude%2fco"))
    crude_seller = dv.kpler(link=("/v1/flows?flowDirection=Export&granularity=daily&startDate=2015-01-01&"
                                  "fromZones=Russian%20Federation&unit=kbd&withForecast=true&"
                                  "split=Seller&onlyRealized=true&products=crude%2fco"))
    clean_seller = dv.kpler(link=("/v1/flows?flowDirection=Export&granularity=daily&startDate=2015-01-01&"
                                  "fromZones=Russian%20Federation&unit=kbd&withForecast=true&"
                                  "split=Seller&onlyRealized=true&products=Clean%20Products"))
    clean = dv.kpler(link=("/v1/flows?flowDirection=Export&granularity=daily&startDate=2017-01-01&"
                           "fromInstallations=Novatek%20Ust%20Luga,Novorossiysk%20Product,"
                           "Ust%20Luga%20Oil%20Terminal,Sibur%20Ust%20Luga,Primorsk%20Product,Primorsk%20Mix,"
                           "Sheskharis,Tuapse&unit=kbd&withForecast=true&onlyRealized=true&split=Origin%20Installatio"
                           + _missing_photo_text("106: URL tail")))
    distillate = dv.kpler(link=("/v1/flows?flowDirection=Export&granularity=daily&startDate=2017-01-01&"
                                "products=diesel,gasoil&unit=kbd&withForecast=true&split=Total&onlyRealized=true&"
                                "withIntraCountry=false&fromZones=Russian%20Federation"))
    crude_on_water = dv.kpler(link=("/v1/fleet-metrics?metric=loaded_vessels&period=daily&"
                                    "products=eastern%20russia%20crude,western%20russia%20crude&unit=kb"))
    crude_on_water_east = dv.kpler(link=("/v1/fleet-metrics?metric=loaded_vessels&period=daily&"
                                         "products=eastern%20russia%20crude&unit=kb"))
    clean_on_water = dv.kpler(link=(_missing_photo_text("117-118: URL prefix") +
                                    "products=Clean%20Products&split=Origin%20Countries&unit=kb&startDate=2017-01-01"))
    crude_exports = dv.kpler(link=("/v1/flows?toZones=China,India&products=crude%2fco&flowDirection=Export&fromZones=Russi"
                                    + _missing_photo_text("121") +
                                    "split=Destination%20Countries&granularity=daily&withForecast=true&onlyRealized=true&st"
                                    + _missing_photo_text("122")))
    crude_exports_ch = dv.kpler(link=("/v1/flows?toZones=China&products=crude%2fco&flowDirection=Export&fromZones=Russian%20F"
                                       + _missing_photo_text("124") +
                                       "split=Grades&granularity=daily&withForecast=true&onlyRealized=true&startDate=2017-01-0"
                                       + _missing_photo_text("125")))
    crude_exports_in = dv.kpler(link=("/v1/flows?toZones=India&products=crude%2fco&flowDirection=Export&fromZones=Russian%20F"
                                       + _missing_photo_text("127") +
                                       "split=Grades&granularity=daily&withForecast=true&onlyRealized=true&startDate=2017-01-0"
                                       + _missing_photo_text("128")))
    crude_imports = dv.kpler(link=("/v1/flows?products=crude%2fco&flowDirection=Import&fromZones=Russian%20Federation&"
                                    "split=Destination%20Countries&granularity=daily&withForecast=true&onlyRealized=true&st"
                                    + _missing_photo_text("131")))
    cpc_imports = dv.kpler(link=("/v1/flows?products=crude%2fco&flowDirection=Import&fromInstallations=CPC%20Terminal&"
                                  "split=Destination%20Countries&granularity=daily&withForecast=true&onlyRealized=true&st"
                                  + _missing_photo_text("134")))
    clean_imports = dv.kpler(link=("/v1/flows?products=Clean%20Products&flowDirection=Import&fromZones=Russian%20Federatio"
                                    + _missing_photo_text("136") +
                                    "split=Destination%20Countries&granularity=daily&withForecast=true&onlyRealized=true&st"
                                    + _missing_photo_text("137")))
    crude = kpler.convert_to_ts(kpler_links=crude, end_dt="-1d")
    clean = kpler.convert_to_ts(kpler_links=clean, end_dt="-1d")
    crude_seller = kpler.convert_to_ts(kpler_links=crude_seller, end_dt="-1d")
    clean_seller = kpler.convert_to_ts(kpler_links=clean_seller, end_dt="-1d")
    distillate = kpler.convert_to_ts(kpler_links=distillate, end_dt="-1d")
    crude_on_water = kpler.convert_to_ts(kpler_links=crude_on_water, end_dt="-1d")
    crude_on_water_east = kpler.convert_to_ts(kpler_links=crude_on_water_east, end_dt="-1d")
    clean_on_water = kpler.convert_to_ts(kpler_links=clean_on_water, end_dt="-1d")
    crude_exports = kpler.convert_to_ts(kpler_links=crude_exports, end_dt="-1d")
    crude_exports_ch = kpler.convert_to_ts(kpler_links=crude_exports_ch, end_dt="-1d")
    crude_exports_in = kpler.convert_to_ts(kpler_links=crude_exports_in, end_dt="-1d")
    crude_imports = kpler.convert_to_ts(kpler_links=crude_imports, end_dt="-1d")
    cpc_imports = kpler.convert_to_ts(kpler_links=cpc_imports, end_dt="-1d")
    clean_imports = kpler.convert_to_ts(kpler_links=clean_imports, end_dt="-1d")

    crude.rename(columns={"Sheskharis": "Novo", "CPC Terminal": "CPC"}, inplace=True)
    crude["Primorsk"] = crude["Primorsk"] + crude["Primorsk Mix"]
    murmansk_cols = ['FSO Rosneft Umba', 'FSO Kola', 'Murmansk Crude', 'FSO Yuri Korchagin',
                     'Prirazlomn' + _missing_photo_text("158: remaining column list")]
    avail_murmansk_cols = [x for x in crude.columns if x in murmansk_cols]
    crude['Murmansk'] = crude[avail_murmansk_cols].sum(axis=1)
    try:
        crude['Ust Luga'] = crude['Novatek Ust Luga'] + crude['Ust Luga Oil Terminal'] + crude['TNTK C' + _missing_photo_text("162")]
    except KeyError:
        crude['Ust Luga'] = crude[[x for x in crude.columns if "Ust Luga" in x]].sum(axis=1)
    baltic_cols = ['Primorsk', 'Ust Luga', 'Murmansk Crude', 'Murmansk Products', 'Yamal',
                   'St Petersbu' + _missing_photo_text("165: remaining column list")]
    avail_baltic_cols = [x for x in crude.columns if x in baltic_cols]
    crude['Baltic'] = crude[avail_baltic_cols].sum(axis=1)
    crude['Far East'] = crude['Sakhalin I'] + crude['Sakhalin II'] + crude['Kozmino']
    crude['Total'] = crude['Baltic'] + crude['Novo'] + crude['Far East'] + crude['Unknown'] + crude['Mu' + _missing_photo_text("169")]
    crude = crude[['Total', 'Baltic', 'Primorsk', 'Ust Luga', 'Murmansk', 'Novo', 'Far East', 'CPC', 'Unknown']]
    crude.rename(columns={"Primorsk": "&emsp;Primorsk", "Ust Luga": "&emsp;Ust Luga",
                          "Murmansk": "&ems" + _missing_photo_text("171: rename mapping suffix")}, inplace=True)
    clean['Primorsk'] = clean['Primorsk Mix'] + clean['Primorsk Product']
    _missing_photo_text("174-177: clean aggregation assignments absent between photos")
    clean['Black sea'] = clean['Novo'] + clean['Tuapse']
    clean = clean[['Total', 'Baltic', 'Primorsk', 'Ust Luga', 'Black sea', 'Novo', 'Tuapse']]
    clean.rename(columns={"Primorsk": "&emsp;Primorsk", "Novo": "&emsp;Novo", "Ust Luga": "&emsp;Ust Luga",
                          "Tuapse": "&emsp;Tuapse"}, inplace=True)
    total = pd.DataFrame()
    total["Total"] = crude["Total"] + clean["Total"]
    total['Crude'] = crude['Total']
    total['Clean'] = clean['Total']
    total['Distillate'] = distillate['Total']
    total_seller = pd.DataFrame()
    total_seller["Total"] = crude_seller["Rosneft"] + crude_seller["Lukoil"] + clean_seller["Rosneft"] + clean_seller["Lukoil"]
    total_seller['Crude'] = crude_seller["Rosneft"] + crude_seller["Lukoil"]
    total_seller['Clean'] = clean_seller["Rosneft"] + clean_seller["Lukoil"]
    clean_on_water = clean_on_water["Russian Federation"].to_frame("Total")
    liquids_on_water = crude_on_water + clean_on_water
    crude_exports["Total"] = crude_exports.sum(axis=1)
    crude_exports_ch = crude_exports_ch[["ESPO", "Sokol"]]
    crude_exports_ch.columns = ["&emsp;ESPO", "&emsp;Sokol"]
    crude_exports_in = crude_exports_in[["Urals", "CPC Russia"]]
    crude_exports_in.columns = ["&emsp;Urals", "&emsp;CPC RU"]
    crude_exports = pd.concat([crude_exports, crude_exports_ch, crude_exports_in], axis=1)
    crude_exports = crude_exports[["Total", "China", "&emsp;ESPO", "&emsp;Sokol", "India", "&emsp;Urals", "&emsp;CPC RU"]]
    crude_imports["Total"] = crude_imports.sum(axis=1)
    crude_imports["Other"] = crude_imports["Total"] - crude_imports[["China", "India", "Turkey"]].sum(axis=1)
    crude_imports_ = crude_imports.copy()
    crude_imports_ = crude_imports_[["Total", "China", "India", "Turkey", "Other"]]
    cpc_imports["Total"] = cpc_imports.sum(axis=1)
    cpc_imports["Other"] = cpc_imports["Total"] - cpc_imports[["China", "India", "Turkey"]].sum(axis=1)
    cpc_imports_ = cpc_imports.copy()
    cpc_imports_ = cpc_imports_[["Total", "China", "India", "Turkey", "Other"]]
    clean_imports["Total"] = clean_imports.sum(axis=1)
    clean_imports["Other"] = clean_imports["Total"] - clean_imports[["China", "India", "Turkey", "Brazil"]].sum(axis=1)
    clean_imports_ = clean_imports.copy()
    clean_imports_ = clean_imports_[["Total", "China", "India", "Turkey", "Brazil", "Other"]]
    crude_imports_ = crude_imports_ - cpc_imports_
    liquid_imports = crude_imports_ + clean_imports_
    liquid_imports["Crude"] = crude_imports_["Total"]
    liquid_imports["Clean"] = clean_imports_["Total"]
    crude_imports_ = crude_imports_[["China", "India", "Turkey", "Other"]]
    crude_imports_.columns = ["&emsp;China Crude", "&emsp;India Crude", "&emsp;Turkey Crude", "&emsp;Other Crude"]
    clean_imports_ = clean_imports_[["China", "India", "Turkey", "Brazil", "Other"]]
    clean_imports_.columns = ["&emsp;China Clean", "&emsp;India Clean", "&emsp;Turkey Clean", "&emsp;Brazil Clean", "&emsp;Other Clean"]
    liquid_imports = pd.concat([liquid_imports[["Total", "Crude", "Clean"]], crude_imports_, clean_imports_], axis=1)
    liquid_imports = liquid_imports[[
        "Total", "Crude", "&emsp;China Crude", "&emsp;India Crude", "&emsp;Turkey Crude", "&emsp;Other Crude",
        "Clean", "&emsp;China Clean", "&emsp;India Clean", "&emsp;Turkey Clean", "&emsp;Brazil Clean", "&emsp;Other Clean"]]
    def table_format2_vs_month(df, table_head, header):
        figs = []
        file_path = f"{outputs_html_oil_link}\\russia_{table_head.replace('/', '_')}.html"
        for i in df.columns:
            figs.append(seasonal_chart(df=df, column=i, title=f"{table_head} - {i} - 20d mva"))
        chart_link = _missing_photo_text("236-238: chart output/link and table call beginning")
        tb = table.table_format2_vs_month(df=df, rows=None, highlight={"window": 92}, agg_by="mean",
                                         agg_by_column=None, window=10, window1=20,
                                         benchmark_quarter=f"{today().year - 1}-Q4", table_head=table_head)
        html_tb = html_format(df=tb, header=header)
        return html_tb.replace(table_head, chart_link)

    html_total = table_format2_vs_month(total, table_head="Total Export", header="Total export (kbd)")
    html_total_seller = table_format2_vs_month(total_seller, table_head="Rosneft+Lukoil Export", header="Ros" + _missing_photo_text("253: header"))
    html_crude = table_format2_vs_month(crude, table_head="Crude Export", header="Crude export (kbd)")
    html_clean = table_format2_vs_month(clean, table_head="Clean Export", header="Clean export (kbd)")
    html_export = table_format2_vs_month(crude_exports, table_head="Export Des", header="Export to China, In" + _missing_photo_text("256: header"))
    html_import = table_format2_vs_month(liquid_imports, table_head="Liquids import from RU", header="Liquid" + _missing_photo_text("257: header"))
    chart_total = seasonal_chart(df=total, column='Total', title='Total liquid exports - 20d mva')
    chart_crude = seasonal_chart(df=total, column='Crude', title='Total crude exports - 20d mva')
    chart_baltic_crude = seasonal_chart(df=crude, column='Baltic', title='Baltic crude exports - 20d mva')
    chart_clean = seasonal_chart(df=total, column='Clean', title='Total clean exports - 20d mva')
    chart_baltic_clean = seasonal_chart(df=clean, column='Baltic', title='Baltic clean exports - 20d mva')
    chart_blacksea_clean = seasonal_chart(df=clean, column='Black sea', title='Black sea clean exports - 20d mva')
    chart_crude_on_water = seasonal_chart(df=crude_on_water, column='Total', title='Russian crude on water - 20d mva')
    chart_crude_on_water_east = seasonal_chart(df=crude_on_water_east, column='Total', title='Russian crude to East on water - 20d mva')
    chart_clean_on_water = seasonal_chart(df=clean_on_water, column='Total', title='Russian clean on water - 20d mva')
    chart_liquids_on_water = seasonal_chart(df=liquids_on_water, column='Total', title='Russian liquids on water - 20d mva')
    chart_export = seasonal_chart(df=crude_exports, column='Total', title='Crude to China and India - 20d mva')
    figs = []
    figs.append(table.html_text(f"Updated at {dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"))
    figs.append(html_total)
    figs.append(html_total_seller)
    figs.append(html_crude)
    figs.append(html_clean)
    figs.append(html_export)
    figs.append(html_import)
    figs.append(chart_total)
    figs.append(chart_crude)
    figs.append(chart_baltic_crude)
    figs.append(chart_clean)
    figs.append(chart_baltic_clean)
    figs.append(chart_blacksea_clean)
    figs.append(chart_crude_on_water)
    figs.append(chart_clean_on_water)
    figs.append(chart_liquids_on_water)
    figs.append(chart_export)
    figs.append(chart_crude_on_water_east)
    table.figures_to_html([table.html_text(report_name, style="font-family:Calibri;", tag='h1')] + figs,
                          f"{html_path}\\oil\\{file_name}.html", task_name=report_name)


if __name__ == "__main__":
    update(send_to=send_to)
