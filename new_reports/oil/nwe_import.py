import pandas as pd
import datetime as dt
import sys
import os
from dateutil.relativedelta import relativedelta
import ecm.cmds.data as dv
import ecm.cmds.kpler as kpler
import ecm.cmds.time_series as ts
import ecm.cmds.table as table
import ecm.cmds.chart as chart
from ecm.cmds.config import root_path
from ecm.cmds.cdr import today
from ecm.cmds._email import send_email
import ecm.cmds.custom as custom
from ecm.cmds.config import html_path
from ecm.cmds.utils import convert_path_to_linux

report_name = "NWE Import"
file_name = "nwe_import"  # without .py
file_path = f"{root_path}\\autoreports\\reports\\oil\\{file_name}.py"


def _missing_photo_text(lines):
    raise NotImplementedError(f"Transcription gap in nwe_import.py, photographed lines {lines}")


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
        start_datetime=dt.datetime(2023, 7, 1, 9, 29), timezone="Europe/London",
        task_name=report_name,
        task=WinTaskPoC(name=f'"{report_name}"', filepath=f'"{file_path}"'),
        background_task=True,
        python_executable=r"C:\local\python\miniconda\envs\ecm_cmds\pythonw.exe")
    win_task.create_task()



def gasoil_table(df, index_name, csv_name, freq="W"):
    figs = []
    df["Total"] = df.sum(axis=1)
    df_chart = df.loc[df.index <= today(), "Total"].copy()
    df.rename(columns={'Russian Federation': 'Russia'}, inplace=True)
    df['PG'] = df[['Saudi Arabia', 'United Arab Emirates', 'Qatar', 'Kuwait', 'Oman', 'Bahrain']].sum(axis=1)
    df['Asia'] = df[['India', 'China', 'Malaysia', 'Singapore Republic', 'South Korea', 'Bahrain', 'Taiwan', 'Japan', 'Indonesia']].sum(axis=1)
    df['Americas'] = df[['United States', 'Bahamas']].sum(axis=1)
    df['EOS'] = df['PG'] + df['Asia']
    df = df[['Russia', 'PG', 'United Arab Emirates', 'Qatar', 'Kuwait', 'Saudi Arabia', 'Asia', 'India', 'China',
             'Malaysia', 'Singapore Republic', 'South Korea', 'United States', 'EOS', 'Total']]
    df_2019 = df.loc[(df.index >= '2019-01-01') & (df.index <= '2019-12-31')].mean()
    df_2021 = df.loc[(df.index >= '2021-01-01') & (df.index <= '2021-12-31')].mean()
    if freq == "W":
        df = df.loc[(df.index >= today() - dt.timedelta(28)) & (df.index <= today() + relativedelta(months=_missing_photo_text('60: clipped month count beginning 1')))]
    elif freq == "M":
        df = df.loc[(df.index >= today() - dt.timedelta(180)) & (df.index <= today() + relativedelta(months=_missing_photo_text('62: clipped month count')))]
    df_table = df.T
    cur_col1 = dt.datetime.strftime([x for x in df_table.columns if x < today()][-1], '%Y-%m-%d')
    cur_col = dt.datetime.strftime([x for x in df_table.columns if x >= today()][0], '%Y-%m-%d')
    df_table.columns = [dt.datetime.strftime(x, '%Y-%m-%d') for x in df_table.columns]
    df_table = df_table.merge(df_2019.rename('2019'), left_index=True, right_index=True)
    df_table = df_table.merge(df_2021.rename('2021'), left_index=True, right_index=True)
    df_table.index.name = index_name
    df_table.to_csv(convert_path_to_linux(f"{root_path}\\outputs\\csvs\\oil\\{csv_name}.csv"))
    df_table.reset_index(inplace=True)
    figs.append(table.html_table(df_table, precision=0,
        format_column={index_name: {'width': '120px', 'text-align': 'left'},
                       tuple(df_table.columns[1:]): {'width': '100px', 'text-align': 'center'},
                       cur_col: {'width': '100px', 'text-align': 'center', 'right_border': True, 'bold': True},
                       cur_col1: {'width': '100px', 'text-align': 'center', 'right_border': True},
                       df_table.columns[-3]: {'width': '100px', 'text-align': 'center', 'right_border': True},
                       df_table.columns[-2]: {'width': '100px', 'text-align': 'center', 'right_border': True}},
        format_row={(1, 6, 13, 14): {'color': 'green', 'bold': True}, (0, 5, 11, 12, 13): {'bottom_border': True}}))
    figs.append(chart.seasonal_chart(df=df_chart, freq=freq, title=index_name, vs_avg=False,
                                     y_axis_title=_missing_photo_text('84: clipped unit/call suffix'), x_axis_title="Date"))
    return figs


def crude_table(df, index_name, csv_name, freq="W"):
    figs = []
    df_chart = df.loc[df.index <= today(), "Total"].copy()
    df['Russia'] = df[['Urals', 'Novy Port', 'Varandey']].sum(axis=1)
    df['PG'] = df[['Saudi Arabia', 'United Arab Emirates', 'Kuwait', 'Iraq', 'Iran', 'Egypt']].sum(axis=1)
    df['Latam'] = df[['Brazil', 'Colombia', 'Guyana', 'Mexico', 'Venezuela']].sum(axis=1)
    df['WAF'] = df[['Nigeria', 'Cameroon', 'Gabon', 'Angola', 'Equatorial Guinea']].sum(axis=1)
    df['NAF_Med'] = df[['CPC', 'KEBCO', 'Libya']].sum(axis=1)
    df['Sweet'] = df[['United States', 'Libya', 'CPC', 'Nigeria', 'Algeria']].sum(axis=1)
    df['Sours'] = df[['PG', 'Brazil', 'Guyana', 'Angola', 'Urals', 'KEBCO']].sum(axis=1)
    df = df[['Sours', 'PG', 'Brazil', 'Guyana', 'Angola', 'Urals', 'KEBCO', 'Sweet', 'United States', 'Libya', 'CPC',
             'Nigeria', 'Algeria', 'Total']]
    df_2019 = df.loc[(df.index >= '2019-01-01') & (df.index <= '2019-12-31')].mean()
    df_2021 = df.loc[(df.index >= '2021-01-01') & (df.index <= '2021-12-31')].mean()
    if freq == "W":
        df = df.loc[(df.index >= today() - dt.timedelta(28)) & (df.index <= today() + relativedelta(months=_missing_photo_text('104: clipped month count beginning 1')))]
    elif freq == "M":
        df = df.loc[(df.index >= today() - dt.timedelta(180)) & (df.index <= today() + relativedelta(months=_missing_photo_text('106: clipped month count')))]
    df_table = df.T
    cur_col1 = dt.datetime.strftime([x for x in df_table.columns if x < today()][-1], '%Y-%m-%d')
    cur_col = dt.datetime.strftime([x for x in df_table.columns if x >= today()][0], '%Y-%m-%d')
    df_table.columns = [dt.datetime.strftime(x, '%Y-%m-%d') for x in df_table.columns]
    df_table = df_table.merge(df_2019.rename('2019'), left_index=True, right_index=True)
    df_table = df_table.merge(df_2021.rename('2021'), left_index=True, right_index=True)
    df_table.index.name = index_name
    df_table.to_csv(convert_path_to_linux(f"{root_path}\\outputs\\csvs\\oil\\{csv_name}.csv"))
    df_table.reset_index(inplace=True)
    figs.append(table.html_table(df_table, precision=0,
        format_column={index_name: {'width': '120px', 'text-align': 'left'},
                       tuple(df_table.columns[1:]): {'width': '100px', 'text-align': 'center'},
                       cur_col: {'width': '100px', 'text-align': 'center', 'right_border': True, 'bold': True},
                       cur_col1: {'width': '100px', 'text-align': 'center', 'right_border': True},
                       df_table.columns[-3]: {'width': '100px', 'text-align': 'center', 'right_border': True},
                       df_table.columns[-2]: {'width': '100px', 'text-align': 'center', 'right_border': True}},
        format_row={(0, 7, 13): {'color': 'green', 'bold': True}, (6, 12): {'bottom_border': True}}))
    figs.append(chart.seasonal_chart(df=df_chart, freq=freq, title=index_name, vs_avg=False,
                                     y_axis_title=_missing_photo_text('128: clipped unit/call suffix'), x_axis_title="Date"))
    return figs


def gasoil_monthly_plus():
    newda = pd.DataFrame()
    for i in range(1, 150):
        val_date = today() - dt.timedelta(i)
        val_d = val_date.strftime('%Y') + "-" + val_date.strftime('%m') + "-" + val_date.strftime('%d')
        next_m = (val_date + pd.DateOffset(months=1) + relativedelta(day=1)).strftime("%Y-%m-%d")
        prev_m = (val_date + pd.DateOffset(months=-1) + relativedelta(day=1)).strftime("%Y-%m-%d")
        current_m = (val_date + relativedelta(day=1)).strftime("%Y-%m-%d")
        datam = [next_m, prev_m, current_m]
        if os.path.exists(f"{root_path}\\outputs\\csvs\\oil\\nwe\\{val_date.strftime('%Y%m%d')}_gasoil.csv"):
            total_weekly_cntry = ts.read_csv(f"{root_path}\\outputs\\csvs\\oil\\nwe\\{val_date.strftime('%Y%m%d')}_gasoil.csv", index_name='Date')
        else:
            total_weekly_cntry = dv.kpler(f'/v1/flows?flowDirection=Import&granularity=daily&startDate=2022-01-01&products=Diesel,Gasoil, Gasoil/Diesel,LCO&toZones=EU&fromZones=Asia,%20Africa,%20Americas,%20Oceania,%20Russian%20Federation&unit=KT&withForecast=false&onlyRealized=true&split=Origin%20Countries&withIntraCountry=false')
            total_weekly_cntry = kpler.convert_to_ts(total_weekly_cntry, forecast=True)
            total_weekly_cntry.to_csv(convert_path_to_linux(f"{root_path}\\outputs\\csvs\\oil\\nwe\\{val_date.strftime('%Y%m%d')}_gasoil.csv"))
        if "Total" not in total_weekly_cntry.columns:
            total_weekly_cntry["Total"] = total_weekly_cntry.sum(axis=1)
        data = total_weekly_cntry.resample("MS").sum()
        data = data.loc[data.index.isin(datam)]
        data['to_date'] = (data.index - val_date).days
        newda = pd.concat([newda, data], axis=0)
    figs = []
    newda['to_date'] = newda['to_date'] * -1
    newda["US"] = newda[['United States', 'Bahamas']].sum(axis=1)
    newda["PG"] = newda[['Saudi Arabia', 'United Arab Emirates', 'Qatar', 'Kuwait', 'Oman', 'Bahrain']].sum(axis=1)
    newda["Asia"] = newda[['India', 'China', 'Malaysia', 'Singapore Republic', 'South Korea', 'Bahrain', 'Taiwan', 'Japan', 'Indonesia']].sum(axis=1)
    region_list = ["Total", "US", "PG", "Asia"]
    for i in region_list:
        chart_data = pd.pivot_table(newda, values=i, index='to_date', columns='Date')
        chart_data = chart_data.loc[chart_data.index < 20]
        chart_data = chart_data.iloc[:, -6:]
        chart_data.columns = [x.strftime('%Y-%m-%d') for x in chart_data.columns]
        figs.append(chart.line_chart(df=chart_data, highlight_dict={chart_data.columns[-1]: {"width": 2, "color": "black"}},
                                     title=i, show_grid_c1=False, y_axis_title='kt', tickformat=None))
    return figs


def crude_monthly_plus():
    newda = pd.DataFrame()
    for i in range(1, 150):
        val_date = today() - dt.timedelta(i)
        val_d = val_date.strftime('%Y') + "-" + val_date.strftime('%m') + "-" + val_date.strftime('%d')
        next_m = (val_date + pd.DateOffset(months=1) + relativedelta(day=1)).strftime("%Y-%m-%d")
        prev_m = (val_date + pd.DateOffset(months=-1) + relativedelta(day=1)).strftime("%Y-%m-%d")
        current_m = (val_date + relativedelta(day=1)).strftime("%Y-%m-%d")
        datam = [next_m, prev_m, current_m]
        if os.path.exists(f"{root_path}\\outputs\\csvs\\oil\\nwe\\{val_date.strftime('%Y%m%d')}.csv"):
            total_weekly_cntry = ts.read_csv(f"{root_path}\\outputs\\csvs\\oil\\nwe\\{val_date.strftime('%Y%m%d')}.csv", index_name='Date')
        else:
            total_weekly_cntry = dv.kpler(f'/v1/flows?flowDirection=Import&granularity=daily&startDate=2022-01-01&products=crude/co&toZones=Ireland,Antifer,Bayonne,Bordeaux,Brest,Donges,Dunkerque,La Rochelle,Le Havre,Lorient,Nantes,Rouen,Saint-Malo,united kingdom,Sweden,Netherlands,Germany,Denmark,Finland,Norway,Belgium,Poland&fromZones=Asia,%20Africa,%20Americas,%20Oceania,%20Russian%20Federation&unit=kbd&withForecast=false&onlyRealized=true&split=Origin%20Countries&withIntraCountry=false')
            total_weekly_cntry = kpler.convert_to_ts(total_weekly_cntry, forecast=True)
            total_weekly_cntry.to_csv(convert_path_to_linux(f"{root_path}\\outputs\\csvs\\oil\\nwe\\{val_date.strftime('%Y%m%d')}.csv"))
        if "Total" not in total_weekly_cntry.columns:
            total_weekly_cntry["Total"] = total_weekly_cntry.sum(axis=1)
        data = total_weekly_cntry.resample("MS").mean()
        data = data.loc[data.index.isin(datam)]
        data['to_date'] = (data.index - val_date).days
        newda = pd.concat([newda, data], axis=0)
    figs = []
    newda['to_date'] = newda['to_date'] * -1
    newda["US"] = newda['United States']
    newda["WAF"] = newda[['Nigeria', 'Republic of the Congo', 'Cameroon', 'Ghana', 'Angola', 'Gabon', 'Equatorial Guinea']].sum(axis=1)
    region_list = ["Total", "US", "WAF"]
    for i in region_list:
        chart_data = pd.pivot_table(newda, values=i, index='to_date', columns='Date')
        chart_data = chart_data.loc[chart_data.index < 20]
        chart_data = chart_data.iloc[:, -6:]
        chart_data.columns = [x.strftime('%Y-%m-%d') for x in chart_data.columns]
        figs.append(chart.line_chart(df=chart_data, highlight_dict={chart_data.columns[-1]: {"width": 2, "color": "black"}},
                                     title=i, show_grid_c1=False, y_axis_title='kbd', tickformat=None))
    return figs


def gasoil_weekly():
    nwe = dv.kpler(link='/v1/flows?flowDirection=Import&granularity=eia-weekly&startDate=2017-01-06&products=Diesel,Gasoil, Gasoil/Diesel,LCO&toZones=Ireland,Antifer,Bayonne,Bordeaux,Brest,Donges,Dunkerque,La Rochelle,Le Havre,Lorient,Nantes,Rouen,Saint-Malo,united kingdom,Sweden,Netherlands,Germany,Denmark,Finland,Norway,Belgium&fromZones=Asia,%20Africa,%20Americas,%20Oceania,%20Russian%20Federation&unit=KT&split=Origin%20Countries&onlyRealized=true&withIntraCountry=false')
    eu = dv.kpler(link='/v1/flows?flowDirection=Import&granularity=eia-weekly&startDate=2017-01-06&products=Diesel,Gasoil, Gasoil/Diesel,LCO&toZones=EU&fromZones=Asia,%20Africa,%20Americas,%20Oceania,%20Russian%20Federation&unit=KT&split=Origin%20Countries&onlyRealized=true&withIntraCountry=false')
    nwe = kpler.convert_to_ts(kpler_links=nwe, forecast=True)
    eu = kpler.convert_to_ts(kpler_links=eu, forecast=True)
    fig_nwe = gasoil_table(nwe, index_name="N.WE imports", csv_name="nwe_imports_gasoil_weekly")
    fig_eu = gasoil_table(eu, index_name="Total EU imports", csv_name="eu_imports_gasoil_weekly")
    figs = fig_nwe + fig_eu
    figs.append(table.html_text(f"Updated at {dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"))
    table.figures_to_html([table.html_text("Weekly Gasoil Imports", style="font-family:Calibri;", tag='h1')] + figs,
                          f"{html_path}\\oil\\nwe_gasoil_imports_weekly.html", task_name=report_name)


def gasoil_monthly():
    nwe = dv.kpler(link='/v1/flows?flowDirection=Import&granularity=monthly&startDate=2017-01-06&products=Diesel,Gasoil, Gasoil/Diesel,LCO&toZones=Ireland,Antifer,Bayonne,Bordeaux,Brest,Donges,Dunkerque,La Rochelle,Le Havre,Lorient,Nantes,Rouen,Saint-Malo,united kingdom,Sweden,Netherlands,Germany,Denmark,Finland,Norway,Belgium&fromZones=Asia,%20Africa,%20Americas,%20Oceania,%20Russian%20Federation&unit=KT&split=Origin%20Countries&onlyRealized=true&withIntraCountry=false')
    eu = dv.kpler(link='/v1/flows?flowDirection=Import&granularity=monthly&startDate=2017-01-06&products=Diesel,Gasoil, Gasoil/Diesel,LCO&toZones=EU&fromZones=Asia,%20Africa,%20Americas,%20Oceania,%20Russian%20Federation&unit=KT&split=Origin%20Countries&onlyRealized=true&withIntraCountry=false')
    nwe = kpler.convert_to_ts(kpler_links=nwe, forecast=True)
    eu = kpler.convert_to_ts(kpler_links=eu, forecast=True)
    fig_nwe = gasoil_table(nwe, index_name="N.WE imports", csv_name="nwe_imports_gasoil_monthly", freq="M")
    fig_eu = gasoil_table(eu, index_name="Total EU imports", csv_name="eu_imports_gasoil_monthly", freq="M")
    figs = fig_nwe + fig_eu
    figs1 = gasoil_monthly_plus()
    figs = figs + figs1
    figs.append(table.html_text(f"Updated at {dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"))
    table.figures_to_html([table.html_text("Monthly Gasoil Imports", style="font-family:Calibri;", tag='h1')] + figs,
                          f"{html_path}\\oil\\nwe_gasoil_imports_monthly.html", task_name=report_name)


def crude_weekly():
    nwe = dv.kpler(link='/v1/flows?flowDirection=Import&granularity=eia-weekly&startDate=2017-01-06&products=crude/co&toZones=Ireland,Antifer,Bayonne,Bordeaux,Brest,Donges,Dunkerque,La Rochelle,Le Havre,Lorient,Nantes,Rouen,Saint-Malo,united kingdom,Sweden,Netherlands,Germany,Denmark,Finland,Norway,Belgium,Poland&fromZones=Asia,%20Africa,%20Americas,%20Oceania,%20Russian%20Federation&unit=kbd&split=Origin%20Countries&onlyRealized=true&withIntraCountry=false')
    nwe_grade = dv.kpler(link='/v1/flows?flowDirection=Import&granularity=eia-weekly&startDate=2017-01-06&products=crude/co&toZones=Ireland,Antifer,Bayonne,Bordeaux,Brest,Donges,Dunkerque,La Rochelle,Le Havre,Lorient,Nantes,Rouen,Saint-Malo,united kingdom,Sweden,Netherlands,Germany,Denmark,Finland,Norway,Belgium,Poland&fromZones=Asia,%20Africa,%20Americas,%20Oceania,%20Russian%20Federation&unit=kbd&split=Grades&onlyRealized=true&withIntraCountry=false')
    eu = dv.kpler(link='/v1/flows?flowDirection=Import&granularity=eia-weekly&startDate=2017-01-06&products=crude/co&toZones=EU&fromZones=Asia,%20Africa,%20Americas,%20Oceania,%20Russian%20Federation&unit=kbd&split=Origin%20Countries&onlyRealized=true&withIntraCountry=false')
    eu_grade = dv.kpler(link='/v1/flows?flowDirection=Import&granularity=eia-weekly&startDate=2017-01-06&products=crude/co&toZones=EU&fromZones=Asia,%20Africa,%20Americas,%20Oceania,%20Russian%20Federation&unit=kbd&split=Grades&onlyRealized=true&withIntraCountry=false')
    nwe = kpler.convert_to_ts(kpler_links=nwe, forecast=True)
    nwe_grade = kpler.convert_to_ts(kpler_links=nwe_grade, forecast=True)
    nwe["Total"] = nwe.sum(axis=1)
    nwe_grade['CPC'] = nwe_grade['CPC'] + nwe_grade['CPC Kazakhstan']
    nwe = pd.concat([nwe, nwe_grade[['Urals', 'CPC', 'KEBCO', 'Novy Port', 'Varandey']]], axis=1)
    eu = kpler.convert_to_ts(kpler_links=eu, forecast=True)
    eu_grade = kpler.convert_to_ts(kpler_links=eu_grade, forecast=True)
    eu["Total"] = eu.sum(axis=1)
    eu_grade['CPC'] = eu_grade['CPC'] + eu_grade['CPC Kazakhstan']
    eu = pd.concat([eu, eu_grade[['Urals', 'CPC', 'KEBCO', 'Novy Port', 'Varandey']]], axis=1)
    fig_nwe = crude_table(nwe, index_name="N.WE imports", csv_name="nwe_imports_crude_weekly")
    fig_eu = crude_table(eu, index_name="Total EU imports", csv_name="eu_imports_crude_weekly")
    figs = fig_nwe + fig_eu
    figs.append(table.html_text(f"Updated at {dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"))
    table.figures_to_html([table.html_text("Weekly Crude Imports", style="font-family:Calibri;", tag='h1')] + figs,
                          f"{html_path}\\oil\\nwe_crude_imports_weekly.html", task_name=report_name)


def crude_monthly():
    nwe = dv.kpler(link='/v1/flows?flowDirection=Import&granularity=monthly&startDate=2017-01-06&products=crude/co&toZones=Ireland,Antifer,Bayonne,Bordeaux,Brest,Donges,Dunkerque,La Rochelle,Le Havre,Lorient,Nantes,Rouen,Saint-Malo,united kingdom,Sweden,Netherlands,Germany,Denmark,Finland,Norway,Belgium,Poland&fromZones=Asia,%20Africa,%20Americas,%20Oceania,%20Russian%20Federation&unit=kbd&split=Origin%20Countries&onlyRealized=true&withIntraCountry=false')
    nwe_grade = dv.kpler(link='/v1/flows?flowDirection=Import&granularity=monthly&startDate=2017-01-06&products=crude/co&toZones=Ireland,Antifer,Bayonne,Bordeaux,Brest,Donges,Dunkerque,La Rochelle,Le Havre,Lorient,Nantes,Rouen,Saint-Malo,united kingdom,Sweden,Netherlands,Germany,Denmark,Finland,Norway,Belgium,Poland&fromZones=Asia,%20Africa,%20Americas,%20Oceania,%20Russian%20Federation&unit=kbd&split=Grades&onlyRealized=true&withIntraCountry=false')
    eu = dv.kpler(link='/v1/flows?flowDirection=Import&granularity=monthly&startDate=2017-01-06&products=crude/co&toZones=EU&fromZones=Asia,%20Africa,%20Americas,%20Oceania,%20Russian%20Federation&unit=kbd&split=Origin%20Countries&onlyRealized=true&withIntraCountry=false')
    eu_grade = dv.kpler(link='/v1/flows?flowDirection=Import&granularity=monthly&startDate=2017-01-01&products=crude/co&toZones=EU&fromZones=Asia,%20Africa,%20Americas,%20Oceania,%20Russian%20Federation&unit=kbd&split=Grades&onlyRealized=true&withIntraCountry=false')
    nwe = kpler.convert_to_ts(kpler_links=nwe, forecast=True)
    nwe_grade = kpler.convert_to_ts(kpler_links=nwe_grade, forecast=True)
    nwe["Total"] = nwe.sum(axis=1)
    nwe_grade['CPC'] = nwe_grade['CPC'] + nwe_grade['CPC Kazakhstan']
    nwe = pd.concat([nwe, nwe_grade[['Urals', 'CPC', 'KEBCO', 'Novy Port', 'Varandey']]], axis=1)
    eu = kpler.convert_to_ts(kpler_links=eu, forecast=True)
    eu_grade = kpler.convert_to_ts(kpler_links=eu_grade, forecast=True)
    eu["Total"] = eu.sum(axis=1)
    eu_grade['CPC'] = eu_grade['CPC'] + eu_grade['CPC Kazakhstan']
    eu = pd.concat([eu, eu_grade[['Urals', 'CPC', 'KEBCO', 'Novy Port', 'Varandey']]], axis=1)
    fig_nwe = crude_table(nwe, index_name="N.WE imports", csv_name="nwe_imports_crude_monthly", freq="M")
    fig_eu = crude_table(eu, index_name="Total EU imports", csv_name="eu_imports_crude_monthly", freq="M")
    figs = fig_nwe + fig_eu
    figs1 = crude_monthly_plus()
    figs = figs + figs1
    figs.append(table.html_text(f"Updated at {dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"))
    table.figures_to_html([table.html_text("Monthly Crude Imports", style="font-family:Calibri;", tag='h1')] + figs,
                          f"{html_path}\\oil\\nwe_crude_imports_monthly.html", task_name=report_name)


def crude_daily():
    nwe = dv.kpler(link='/v1/flows?flowDirection=Import&granularity=daily&startDate=2017-01-06&products=crude/co&toZones=Ireland,Antifer,Bayonne,Bordeaux,Brest,Donges,Dunkerque,La Rochelle,Le Havre,Lorient,Nantes,Rouen,Saint-Malo,united kingdom,Sweden,Netherlands,Germany,Denmark,Finland,Norway,Belgium,Poland&fromZones=Asia,%20Africa,%20Americas,%20Oceania,%20Russian%20Federation&unit=kbd&split=Origin%20Countries&onlyRealized=true&withIntraCountry=false')
    nwe_grade = dv.kpler(link='/v1/flows?flowDirection=Import&granularity=daily&startDate=2017-01-06&products=crude/co&toZones=Ireland,Antifer,Bayonne,Bordeaux,Brest,Donges,Dunkerque,La Rochelle,Le Havre,Lorient,Nantes,Rouen,Saint-Malo,united kingdom,Sweden,Netherlands,Germany,Denmark,Finland,Norway,Belgium,Poland&fromZones=Asia,%20Africa,%20Americas,%20Oceania,%20Russian%20Federation&unit=kbd&split=Grades&onlyRealized=true&withIntraCountry=false')
    eu = dv.kpler(link='/v1/flows?flowDirection=Import&granularity=daily&startDate=2017-01-06&products=crude/co&toZones=EU&fromZones=Asia,%20Africa,%20Americas,%20Oceania,%20Russian%20Federation&unit=kbd&split=Origin%20Countries&onlyRealized=true&withIntraCountry=false')
    eu_grade = dv.kpler(link='/v1/flows?flowDirection=Import&granularity=daily&startDate=2017-01-01&products=crude/co&toZones=EU&fromZones=Asia,%20Africa,%20Americas,%20Oceania,%20Russian%20Federation&unit=kbd&split=Grades&onlyRealized=true&withIntraCountry=false')
    nwe = kpler.convert_to_ts(kpler_links=nwe, forecast=True)
    nwe_grade = kpler.convert_to_ts(kpler_links=nwe_grade, forecast=True)
    nwe["Total"] = nwe.sum(axis=1)
    nwe_grade['CPC'] = nwe_grade['CPC'] + nwe_grade['CPC Kazakhstan']
    nwe = pd.concat([nwe, nwe_grade[['Urals', 'CPC', 'KEBCO', 'Novy Port', 'Varandey']]], axis=1)
    eu = kpler.convert_to_ts(kpler_links=eu, forecast=True)
    eu_grade = kpler.convert_to_ts(kpler_links=eu_grade, forecast=True)
    eu["Total"] = eu.sum(axis=1)
    eu_grade['CPC'] = eu_grade['CPC'] + eu_grade['CPC Kazakhstan']
    eu = pd.concat([eu, eu_grade[['Urals', 'CPC', 'KEBCO', 'Novy Port', 'Varandey']]], axis=1)
    fig_nwe = crude_table(nwe, index_name="N.WE imports", csv_name="nwe_imports_crude_monthly", freq="M")
    fig_eu = crude_table(eu, index_name="Total EU imports", csv_name="eu_imports_crude_monthly", freq="M")
    figs = fig_nwe + fig_eu
    figs1 = crude_monthly_plus()
    figs = figs + figs1
    figs.append(table.html_text(f"Updated at {dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"))
    table.figures_to_html([table.html_text("Monthly Crude Imports", style="font-family:Calibri;", tag='h1')] + figs,
                          f"{html_path}\\oil\\nwe_crude_imports_monthly.html", task_name=report_name)


def update():
    gasoil_monthly()
    crude_monthly()


def update_eu():
    figs = []
    figs.append("<div style='font-family:Calibri;' >")
    country_list = ["EU", "North West Europe Zone", "Europe", "OECD Europe"]
    top = 10
    for i in country_list:
        print(i)
        obj = custom.Oil(i)
        figs_crude_imports = []
        figs.append("<div style='font-family:Calibri;' >")
        crude_imports_country, crude_imports_grade = obj.crude_imports()
        crude_imports_grade["CPC"] = crude_imports_grade["CPC"] + crude_imports_grade["CPC Kazakhstan"]
        crude_imports_grade.drop("CPC Kazakhstan", axis=1, inplace=True)
        imp_country = obj.summary_table(data=crude_imports_country, top=top, name="From Country", header="Cr" + _missing_photo_text('447: heading/call suffix'))
        imp_grade = obj.summary_table(data=crude_imports_grade, top=top, name="Import Grades", header="Crude" + _missing_photo_text('448: heading/call suffix'))
        figs_crude_imports.append(imp_country)
        figs_crude_imports.append(imp_grade)
        import_from_me = crude_imports_country[['Iraq', 'Saudi Arabia', 'United Arab Emirates', 'Kuwait', 'Oman', 'Qatar']].sum(axis=1).rolling(10).mean()
        import_from_me_chart = chart.seasonal_chart(df=import_from_me, title=f"{i} crude import from Middle" + _missing_photo_text('454: title/call suffix'))
        figs_crude_imports.append(import_from_me_chart)
        import_from_waf = crude_imports_country[['Nigeria', 'Cameroon', 'Gabon', 'Angola', 'Equatorial Guinea']].sum(axis=1).rolling(10).mean()
        import_from_waf_chart = chart.seasonal_chart(df=import_from_waf, title=f"{i} crude import from WAF")
        figs_crude_imports.append(import_from_waf_chart)
        import_from_latem = crude_imports_country[['Brazil', 'Colombia', 'Guyana', 'Mexico', 'Venezuela']].sum(axis=1).rolling(10).mean()
        import_from_latem_chart = chart.seasonal_chart(df=import_from_latem, title=f"{i} crude import from L" + _missing_photo_text('464: title/call suffix'))
        figs_crude_imports.append(import_from_latem_chart)
        import_from_med = crude_imports_country[['Libya']].sum(axis=1).rolling(10).mean() + _missing_photo_text('467: crude_imports_gr... remaining operand')
        import_from_med_chart = chart.seasonal_chart(df=import_from_med, title=f"{i} crude import from MED")
        figs_crude_imports.append(import_from_med_chart)
        table.figures_to_html(figs_crude_imports, f"{obj.folder}\\{i}_crude_imports.html")
        figs_crude_exports = []
        crude_exports_country, crude_exports_grade = obj.crude_exports()
        figs_crude_exports.append(obj.summary_table(crude_exports_country, top=8, name="To Country", header=_missing_photo_text('475: heading/call suffix')))
        figs_crude_exports.append(obj.summary_table(crude_exports_grade, top=8, name="Export Grades", header=_missing_photo_text('476: heading/call suffix')))
        table.figures_to_html(figs_crude_exports, f"{obj.folder}\\{i}_crude_exports.html")
        figs_prod_imports = []
        prod_imports_country, prod_imports_grade = obj.product_imports()
        figs_prod_imports.append(obj.summary_table(prod_imports_country, top=8, name="Prod from Country", header=_missing_photo_text('481: heading/call suffix')))
        figs_prod_imports.append(obj.summary_table(prod_imports_grade, top=8, name="Import Types", header="P" + _missing_photo_text('482: heading/call suffix')))
        table.figures_to_html(figs_prod_imports, f"{obj.folder}\\{i}_product_imports.html")
        figs_prod_exports = []
        prod_exports_country, prod_exports_grade = obj.product_exports()
        figs_prod_exports.append(obj.summary_table(prod_exports_country, top=8, name="Prod to Country", header=_missing_photo_text('487: heading/call suffix')))
        figs_prod_exports.append(obj.summary_table(prod_exports_grade, top=8, name="Export Types", header="P" + _missing_photo_text('488: heading/call suffix')))
        table.figures_to_html(figs_prod_exports, f"{obj.folder}\\{i}_product_exports.html")
    table.figures_to_html([table.html_text("NWE Oil Flow", style="font-family:Calibri;", tag='h1')] + figs,
                          f"{html_path}\\oil\\analysis\\nwe_oil_flow.html", task_name=report_name)


if __name__ == "__main__":
    update_eu()
