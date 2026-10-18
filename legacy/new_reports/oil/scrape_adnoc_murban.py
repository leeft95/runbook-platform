import pandas as pd
import datetime as dt
import sys
import PyPDF2
from urllib.error import HTTPError
from pathlib import Path
from ecm.cmds.cdr import today
import ecm.cmds.chart as chart
import ecm.cmds.table as table
from loguru import logger as log

from tabula.io import read_pdf
import PyPDF2
import itertools
from io import BytesIO
import requests
import time
from ecm.cmds.config import root_path
from ecm.atom.clients import retry
import ecm.cmds.to_html as to_html
from ecm.cmds.utils import convert_path_to_linux

report_name = "Save Adnoc Murban Forecast Monthly"
file_name = "scrape_adnoc_murban"  # without .py
file_path = f"{root_path}\\autoreports\\reports\\oil\\{file_name}.py"

csv_base_path = f"\\\\elementcapital.corp\\ecns01\\PM\\Michel Kikano\\CODE\\outputs\\csvs\\oil\\adnoc_murban_forecast"
csv_base_path_html = convert_path_to_linux(
    f"\\\\elementcapital.corp\\ecns01\\PM\\Michel Kikano\\CODE\\outputs\\htmls\\oil\\adnoc_murban_forecast"
)
latest_file = convert_path_to_linux(f"{csv_base_path}\\all.csv")


def _missing_photo_text(lines):
    """Transcription marker for text clipped from all available photographs."""
    raise NotImplementedError(f"Missing photographed text: scrape_adnoc_murban.py source lines {lines}")


@retry(max_tries=1, exceptions=[HTTPError], before_retry=lambda **_: time.sleep(10))
def scrape_pdf(month: str, year: str):
    pdf_base_url = ("https://afdshd01.adnoc.ae/adn-prd/-/media/adnoc-v2/files/murban-report/2025-reports/murb"
                    + _missing_photo_text("37")).format(
        month=month, year=year
    )
    tables = read_pdf(pdf_base_url, pages=1, stream=True, columns=None)
    log.info(f"Scraped {pdf_base_url} tabula with {len(tables)} tables")
    months = list(itertools.chain.from_iterable(tables[0].iloc[0].str.split(" ").values))
    years = list(itertools.chain.from_iterable(tables[0].iloc[1].str.split(" ").values))
    data = list(itertools.chain.from_iterable(tables[0].iloc[2].str.split(" ").values))
    final_df = pd.DataFrame(dict(month=months, year=years, export_availability_forecast=data))
    issue_date_pfx = "Date of  Issue:"
    x = requests.get(pdf_base_url, verify=False)
    fileReader = PyPDF2.PdfFileReader(BytesIO(x.content))
    n = fileReader.numPages
    found_data = False
    for i in range(n):
        s = fileReader.getPage(i).extractText()
        lines = s.split("\n")
        for line in lines:
            if issue_date_pfx in line:
                print(line)
                issue_date = pd.to_datetime(line.split(issue_date_pfx)[-1].strip())
                found_data = True
                break
        if found_data:
            break
    final_df["release_date"] = issue_date
    final_df = final_df.set_index("release_date")
    return final_df


def update():
    hist_date = dt.datetime(2023, 1, 1)
    if Path(latest_file).exists():
        current_data = pd.read_csv(latest_file).dropna(axis=0, how="all")
        current_data["release_date"] = pd.to_datetime(current_data.release_date)
        current_data["year"] = current_data["year"].astype(int)
        current_data = current_data.set_index("release_date")
    else:
        current_data = pd.DataFrame()
    if not current_data.empty:
        last_release_date = current_data.index.max()
        if last_release_date.month == 12:
            next_release_date = dt.datetime(last_release_date.year + 1, 1, 1) + pd.DateOffset(
                days=26
            )
        else:
            next_release_date = dt.datetime(
                last_release_date.year, last_release_date.month + 1, 1
            ) + pd.DateOffset(days=26)
        if today() >= next_release_date:
            month = next_release_date.strftime("%B").lower()
            year = str(next_release_date.year)
            try:
                latest_data = scrape_pdf(month, year)
                latest_data.to_csv(f"{csv_base_path}\\{year}_{month}.csv")
                df = pd.concat([current_data, latest_data])
                df.to_csv(latest_file)
                plot_latest()
            except Exception as e:
                raise Exception(f"Could not extract data for {month}-{year}\n{e}")
        else:
            return
    else:
        dates = pd.date_range(hist_date, today(), freq="MS") + pd.DateOffset(days=26)
        data = pd.DataFrame()
        for date in dates:
            month = date.strftime("%B").lower()
            year = str(date.year)
            if date > today():
                continue
            try:
                new_data = scrape_pdf(month, year)
                new_data.to_csv(f"{csv_base_path}\\{year}_{month}.csv")
                data = pd.concat([data, new_data])
            except Exception as e:
                print(f"Could not extract data for {month}-{year}\n{e}")
        data.to_csv(latest_file)


def plot_latest():
    if Path(latest_file).exists():
        current_data = pd.read_csv(latest_file).dropna(axis=0, how="all")
        current_data["release_date"] = pd.to_datetime(current_data.release_date)
        current_data["export_availability_forecast"] = (
            current_data["export_availability_forecast"].str.replace(",", "").astype(float)
        )
        current_data["year"] = current_data["year"].astype(int)
        current_data["date"] = [
            pd.to_datetime(f"01-{y.month}-{y.year}")
            for _, y in list(current_data[["year", "month"]].astype(str).iterrows())
        ]
        current_data = current_data.drop(columns=["month", "year"])
        reformated_dfs = []
        individual_plots = []
        for rd, df in current_data.groupby("release_date"):
            if rd in current_data.release_date.unique()[-6:]:
                x = pd.DataFrame(
                    {rd.strftime("%Y-%m-%d"): df.export_availability_forecast, "date": df.date}
                ).set_index("date")
                reformated_dfs.append(x)
        all_df = pd.concat(reformated_dfs, axis=0)
        plot_df = all_df.iloc[:, -6:]
        highlight_dict = {plot_df.columns[-1]: dict(color="black")}
        plot = chart.line_chart(
            plot_df,
            title="Murban Export Availability by forecast release date",
            x_axis_title="Date",
            y_axis_title="KDB",
            tickformat="%b\n%Y",
            highlight_dict=highlight_dict,
        )
        plot.update_xaxes(dtick="M1", tickformat="%b\n%Y", ticklabelmode="period")
        table.to_html([plot], path=rf"{csv_base_path_html}\forecast.html")

    else:
        return None


if __name__ == "__main__":
    update()
