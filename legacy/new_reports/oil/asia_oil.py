import pandas as pd
import datetime as dt
import sys
import ecm.cmds.data as dv
import ecm.cmds.kpler as kpler
import ecm.cmds.time_series as ts
import ecm.cmds.table as table
import ecm.cmds.chart as chart
from ecm.cmds.config import root_path, html_path
from ecm.cmds.cdr import today
import ecm.cmds.custom as custom

report_name = "Asia Oil Flow"
file_name = "asia_oil"  # without.py
file_path = f"{root_path}\\autoreports\\reports\\oil\\{file_name}.py"


def _missing_photo_text(lines):
    raise NotImplementedError(f"Transcription gap in asia_oil.py, photographed lines {lines}")


def add_schedule():
    """# schedule to run the report - only need to run once"""
    sys.path.append(f"{root_path}\\autoreports\\schedule")
    from tasks import WinTaskPoC
    from ecm.atom.wintask.scheduler import ECMWinTask
    from ecm.atom.wintask.utils import Days
    win_task = ECMWinTask(
        days=Days.MONDAY | Days.TUESDAY | Days.WEDNESDAY | Days.THURSDAY | Days.FRIDAY,
        start_datetime=dt.datetime(2023, 7, 1, 9, 25),
        timezone="Europe/London", task_name=report_name,
        task=WinTaskPoC(name=f'"{report_name}"', filepath=f'"{file_path}"'),
        background_task=True,
        python_executable=r"C:\local\python\miniconda\envs\ecm_cmds\pythonw.exe")
    win_task.create_task()


def update():
    figs = []
    figs.append("<div style='font-family:Calibri; '>")
    country_list = ["China", "India", "Japan", "South Korea", "Taiwan", "Thailand", ]
    top = 10
    country_str = ",".join(country_list)
    country_str = country_str.replace(" ", "%20")
    type_list = ["crude", ]
    dir_list = ["import", ]
    for i in type_list:
        for j in dir_list:
            if j == "import":
                d = "destination"
            elif j == "export":
                d = "origin"
            total = custom.Oil.kpler_flow(country=country_str, direction=j, product=i, split=d, sdate="2018-01-01", )
            total_html = custom.Oil.table_format2_vs_month(
                data=total[["Total"] + total.columns[:-1].to_list()], table_head="Destination Country",
                header=f"Crude exports to Asia by destination",
                file_path=f"{html_path}\\oil\\analysis\\asia_{i}_{j}.html", ma=10)
            total_imp = custom.Oil.kpler_flow(country=country_str, direction=j, product=i, split=d,
                                            flow_direction="Import", sdate="2018-01-01", )
            total_imp_html = custom.Oil.table_format2_vs_month(
                data=total_imp[["Total"] + total_imp.columns[:-1].to_list()], table_head="Destination Country",
                header=f"Asia crude imports by destination",
                file_path=f"{html_path}\\oil\\analysis\\asia_{i}_{j}_imp.html", ma=10)
            figs.append([total_html, total_imp_html])
    obj_total = custom.Oil(country_str)
    crude_imports_total, crude_grade_total = obj_total.crude_imports()
    imp_country = obj_total.summary_table(
        data=crude_imports_total, top=top, name="Origin Country",
        header="Crude exports to Asia by origin countries",
        file_path=f"{obj_total.folder}\\asia_total_crude_imports_by_exports.html")
    imp_grade = obj_total.summary_table(
        data=crude_grade_total, top=top, name="Total Grades", header="Crude exports to Asia by grades",
        file_path=f"{obj_total.folder}\\asia_total_crude_imports_grades_by_exports.html")
    crude_imports_total_imp, crude_grade_total_imp = obj_total.crude_imports(flow_direction="Import")
    imp_country_imp = obj_total.summary_table(
        data=crude_imports_total_imp, top=top, name="Origin Country", header="Asia crude imports by origin countries",
        file_path=f"{obj_total.folder}\\asia_total_crude_imports_by_imports.html")
    imp_grade_imp = obj_total.summary_table(**_missing_photo_text("117-177"))
    for i in country_list:
        obj = custom.Oil(i)
        figs_crude_imports = []
        figs_crude_imports.append("<div style='font-family:Calibri; '>")
        crude_imports_country, crude_imports_grade = obj.crude_imports()
        crude_imports_country_imp, crude_imports_grade_imp = obj.crude_imports(flow_direction="Import")
        if i in ["China"]:
            crude_imports_country["Iran"] = _missing_photo_text("185: Iran + Unknown...")
            crude_imports_country.drop("Unknown", axis=1, inplace=True)
            crude_imports_country.drop("Malaysia", axis=1, inplace=True)
            crude_imports_country.rename(columns={"Iran": "Iran+Malaysia"}, inplace=True)
            crude_imports_grade["Iran"] = crude_imports_grade["Iran"] + crude_imports_grade["EOPL"]
            crude_imports_grade.drop("EOPL", axis=1, inplace=True)
            crude_imports_country_imp["Iran"] = crude_imports_country_imp["Iran"] + _missing_photo_text("191")
            crude_imports_country_imp.drop("Unknown", axis=1, inplace=True)
            crude_imports_country_imp.drop("Malaysia", axis=1, inplace=True)
            crude_imports_grade_imp["Iran"] = crude_imports_grade_imp["Iran"] + crude_imports_grade_imp["EOPL"]
            crude_imports_grade_imp.drop("EOPL", axis=1, inplace=True)
        imp_country = obj.summary_table(
            data=crude_imports_country, top=top, name="From Country",
            header=f"Crude exports to {i} by origin countries",
            file_path=f"{obj_total.folder}\\{i}_crude_imports_by_exports.html")
        imp_grade = obj.summary_table(
            data=crude_imports_grade, top=top, name="Import Grades", header=f"Crude exports to {i} by grades",
            file_path=f"{obj_total.folder}\\{i}_grade_imports_by_exports.html")
        imp_country_imp = obj.summary_table(
            data=crude_imports_country_imp, top=top, name="From Country",
            header=f"{i} crude import by origin countries",
            file_path=f"{obj_total.folder}\\{i}_crude_imports_by_imports.html")
        imp_grade_imp = obj.summary_table(
            data=crude_imports_grade_imp, top=top, name="Import Grades", header=f"{i} crude import by grades",
            file_path=f"{obj_total.folder}\\{i}_grade_imports_by_imports.html")
        figs_crude_imports.append([imp_country, imp_country_imp])
        figs_crude_imports.append([imp_grade, imp_grade_imp])
        if i in ["China", "India"]:
            import_from_me = crude_imports_country[
                ['Iraq', 'Saudi Arabia', 'United Arab Emirates', 'Kuwait', 'Oman', 'Qatar']].sum(axis=1).rolling(10).mean()
            import_from_me_chart = chart.seasonal_chart(df=import_from_me,
                title=_missing_photo_text('230: Middle East crude export...'))
            import_from_me_imp = crude_imports_country_imp[
                ['Iraq', 'Saudi Arabia', 'United Arab Emirates', 'Kuwait', 'Oman', 'Qatar']].sum(axis=1).rolling(10).mean()
            import_from_me_chart_imp = chart.seasonal_chart(df=import_from_me_imp,
                title=_missing_photo_text('233: {i} crude import...'))
            figs_crude_imports.append([import_from_me_chart, import_from_me_chart_imp])
            import_from_waf = crude_imports_country[
                ['Nigeria', 'Cameroon', 'Gabon', 'Angola', 'Equatorial Guinea']].sum(axis=1).rolling(10).mean()
            import_from_waf_chart = chart.seasonal_chart(df=import_from_waf,
                title=_missing_photo_text('238: WAF crude export to {i}...'))
            import_from_waf_imp = crude_imports_country_imp[
                ['Nigeria', 'Cameroon', 'Gabon', 'Angola', 'Equatorial Guinea']].sum(axis=1).rolling(10).mean()
            import_from_waf_chart_imp = chart.seasonal_chart(df=import_from_waf_imp,
                title=_missing_photo_text('241: {i} crude import...'))
            figs_crude_imports.append([import_from_waf_chart, import_from_waf_chart_imp])
            import_from_latem = crude_imports_country[
                ['Brazil', 'Colombia', 'Guyana', 'Mexico', 'Venezuela']].sum(axis=1).rolling(10).mean()
            import_from_latem_chart = chart.seasonal_chart(df=import_from_latem,
                title=_missing_photo_text('246: Latem crude export...'))
            import_from_latem_imp = crude_imports_country_imp[
                ['Brazil', 'Colombia', 'Guyana', 'Mexico', 'Venezuela']].sum(axis=1).rolling(10).mean()
            import_from_latem_chart_imp = chart.seasonal_chart(df=import_from_latem_imp,
                title=_missing_photo_text('249: {i} crude i...'))
            figs_crude_imports.append([import_from_latem_chart, import_from_latem_chart_imp])
        table.to_html(
            [table.html_text(f"{i} Oil Flow", style="font-family:Calibri;", tag="h1")] + figs_crude_imports,
            f"{obj.folder}\\{i}_crude_imports.html")
    table.to_html(
        [table.html_text("Asia Oil Flow", style="font-family:Calibri;", tag='h1')] + figs,
        f"{html_path}\\oil\\analysis\\asia_oil_flow.html")


if __name__ == "__main__":
    update()
