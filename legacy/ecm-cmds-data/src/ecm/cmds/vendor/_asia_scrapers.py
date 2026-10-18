import asyncio
import datetime as dt
import json
import math
import os
import shutil
import sys
import time
from pathlib import Path

import pandas as pd
from ecm.cmds.core.config import data_path
from ecm.cmds.core.selenium import get_chrome_driver
from ecm.cmds.core.utils import convert_path_to_linux
from googletrans import Translator
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

if sys.platform.startswith("win"):
    os.environ["GRPC_DEFAULT_SSL_ROOTS_FILE_PATH"] = r"C:\local\certs\root.crt"
    os.environ["REQUESTS_CA_BUNDLE"] = r"C:\local\certs\root.crt"
    os.environ["SSL_CERT_FILE"] = r"C:\local\certs\root.crt"

_columns_dict = {
    "unit": [
        "area",
        "power_generation_company",
        "power_plant_code",
        "power_plant_name",
        "power_generation_type",
        "unit_name",
        "approved_output",
        "approved_output_after_change",
        "effective_start_date",
        "operation_start_date",
        "operation_end_date",
        "last_updated",
    ],
    "unit_string_cols": [
        "area",
        "power_generation_company",
        "power_plant_name",
        "power_generation_type",
        "unit_name",
    ],
    "outage": [
        "area",
        "power_generation_company",
        "power_plant_code",
        "power_plant_name",
        "power_generation_type",
        "unit_name",
        "approved_output",
        "outage_category",
        "type",
        "amount_of_reduction",
        "outage_start",
        "recovery_outlook",
        "expected_restoration_date",
        "cause_of_outage",
        "last_updated",
    ],
    "outage_string_cols": [
        "area",
        "power_generation_company",
        "power_plant_name",
        "power_generation_type",
        "unit_name",
        "outage_category",
        "type",
        "recovery_outlook",
        "cause_of_outage",
    ],
    "hatsuden": [
        "power_plant_code",
        "area",
        "power_plant_name",
        "unit_name",
        "power_generation_type",
        "date",
        "t00_30_kWh",
        "t01_00_kWh",
        "t01_30_kWh",
        "t02_00_kWh",
        "t02_30_kWh",
        "t03_00_kWh",
        "t03_30_kWh",
        "t04_00_kWh",
        "t04_30_kWh",
        "t05_00_kWh",
        "t05_30_kWh",
        "t06_00_kWh",
        "t06_30_kWh",
        "t07_00_kWh",
        "t07_30_kWh",
        "t08_00_kWh",
        "t08_30_kWh",
        "t09_00_kWh",
        "t09_30_kWh",
        "t10_00_kWh",
        "t10_30_kWh",
        "t11_00_kWh",
        "t11_30_kWh",
        "t12_00_kWh",
        "t12_30_kWh",
        "t13_00_kWh",
        "t13_30_kWh",
        "t14_00_kWh",
        "t14_30_kWh",
        "t15_00_kWh",
        "t15_30_kWh",
        "t16_00_kWh",
        "t16_30_kWh",
        "t17_00_kWh",
        "t17_30_kWh",
        "t18_00_kWh",
        "t18_30_kWh",
        "t19_00_kWh",
        "t19_30_kWh",
        "t20_00_kWh",
        "t20_30_kWh",
        "t21_00_kWh",
        "t21_30_kWh",
        "t22_00_kWh",
        "t22_30_kWh",
        "t23_00_kWh",
        "t23_30_kWh",
        "t24_00_kWh",
        "daily_amount_kWh",
        "last_updated",
    ],
    "hatsuden_string_cols": [
        "area",
        "power_plant_name",
        "unit_name",
        "power_generation_type",
    ],
}


async def translate_bulk(to_translate):
    output = {}
    for key, value in to_translate.items():
        n = 200
        a = value
        chunks = [a[i : i + n] for i in range(0, len(a), n)]
        values = {}
        for i, chunk in enumerate(chunks):
            print(f"Processing {key} {i+1}/{len(chunks)}")
            has_translations = False
            while not has_translations:
                try:
                    async with Translator() as translator:
                        translations = await translator.translate(chunk, src="ja", dest="en")
                        for translation in translations:
                            values[translation.origin] = translation.text
                        time.sleep(5)
                        has_translations = True
                except Exception as e:
                    print(e)
                    time.sleep(30)
        output[key] = values
    return output


def convert_df_to_english(df, source, translation_dict=None):
    if translation_dict is None:
        if source == "unit":
            translation_source = convert_path_to_linux(
                f"{data_path}\\hjks\\{source}\\hjks_unit_translations.json"
            )
            if not os.path.exists(translation_source):
                to_translate = {}
                for col in _columns_dict[f"{source}_string_cols"]:
                    to_translate[col] = list(df[col].unique())
                loop = asyncio.get_event_loop()
                translated_dict = loop.run_until_complete(translate_bulk(to_translate))
                with open(translation_source, "w", encoding="utf-8") as f:
                    json.dump(translated_dict, f, ensure_ascii=False, indent=4)
            with open(translation_source, "r", encoding="utf-8") as f:
                translation_dict = json.load(f)
        elif source == "outage":
            translation_source = convert_path_to_linux(
                f"{data_path}\\hjks\\{source}\\hjks_outage_translations.json"
            )
            if not os.path.exists(translation_source):
                to_translate = {}
                for col in _columns_dict[f"{source}_string_cols"]:
                    to_translate[col] = list(df[col].unique())
                loop = asyncio.get_event_loop()
                translated_dict = loop.run_until_complete(translate_bulk(to_translate))
                with open(translation_source, "w", encoding="utf-8") as f:
                    json.dump(translated_dict, f, ensure_ascii=False, indent=4)
            with open(translation_source, "r", encoding="utf-8") as f:
                translation_dict = json.load(f)
        elif source == "hatsuden":
            translation_source = convert_path_to_linux(
                f"{data_path}\\hatsuden\\hatsuden_translations.json"
            )
            if not os.path.exists(translation_source):
                to_translate = {}
                for col in _columns_dict["hatsuden_string_cols"]:
                    to_translate[col] = list(df[col].unique())
                loop = asyncio.get_event_loop()
                translated_dict = loop.run_until_complete(translate_bulk(to_translate))
                with open(translation_source, "w", encoding="utf-8") as f:
                    json.dump(translated_dict, f, ensure_ascii=False, indent=4)
            with open(translation_source, "r", encoding="utf-8") as f:
                translation_dict = json.load(f)
        else:
            raise ValueError("source must be either 'unit' or 'outage'")
    df = df.replace(translation_dict)
    untranslated_values = {}
    for col in _columns_dict[f"{source}_string_cols"]:
        unmatched = list(set(df[col].unique()) - set(translation_dict[col].values()))
        if len(unmatched) > 0:
            unmatched = [x for x in unmatched if isinstance(x, str) or not math.isnan(x)]
            if len(unmatched) > 0:
                untranslated_values[col] = unmatched
    if len(untranslated_values) > 0:
        print(f"Translating new values in {untranslated_values.keys()}")

        loop = asyncio.get_event_loop()
        translated_dict = loop.run_until_complete(translate_bulk(untranslated_values))
        for key in translated_dict.keys():
            old_values = translation_dict[key]
            updated_values = dict(old_values, **translated_dict[key])
            translation_dict[key] = updated_values
        with open(translation_source, "w", encoding="utf-8") as f:
            json.dump(translation_dict, f, ensure_ascii=False, indent=4)
        convert_df_to_english(df, source, translation_dict)
    return df


def download_csv_from_hjks(source):
    def _convert_downloaded_csv_to_english(path_to_downloads, source):
        downloaded_file = (
            path_to_downloads.parent
            / "raw"
            / f"{source}_{dt.datetime.today().strftime('%Y%m%d')}.csv"
        )
        if downloaded_file.exists():
            df = pd.read_csv(downloaded_file, encoding="cp932", low_memory=False)
            df = df.reset_index().drop(columns=[df.iloc[:, -1].name])
            df.columns = _columns_dict[source]
            sanitize = {r"\u3000": " "}
            df = df.replace(sanitize)
            df = convert_df_to_english(df, source)
        else:
            raise FileNotFoundError(f"{downloaded_file} does not exist")
        return df

    def _wait_for_download(path_to_downloads, source):
        seconds = 0
        dl_wait = True
        while dl_wait and seconds < 20:
            time.sleep(1)
            dl_wait = False
            for fname in path_to_downloads.iterdir():
                if fname.suffix.endswith(".crdownload"):
                    dl_wait = True
                if fname.suffix == ".csv":
                    new_name = f"{source}_{dt.datetime.today().strftime('%Y%m%d')}" + fname.suffix
                    new_path = fname.parent.parent / "raw" / new_name
                    if not new_path.parent.exists():
                        new_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(fname, new_path)
                    print(f"\nMoved {fname} to {new_path}\n")
            seconds += 1
        return seconds

    if source == "unit":
        url = "https://hjks.jepx.or.jp/hjks/unit"
        download_dir = Path(convert_path_to_linux(f"{data_path}\\hjks\\unit\\staging\\"))
        if not download_dir.exists():
            download_dir.mkdir(parents=True, exist_ok=True)

    elif source == "outage":
        url = "https://hjks.jepx.or.jp/hjks/outages"
        download_dir = Path(convert_path_to_linux(f"{data_path}\\hjks\\outage\\staging\\"))
        if not download_dir.exists():
            download_dir.mkdir(parents=True, exist_ok=True)

    else:
        raise ValueError("source must be either 'unit' or 'outage'")
    try:
        driver = get_chrome_driver(download_dir)
        driver.get(url)
        time.sleep(30)
        driver.find_element(By.XPATH, "/html/body/div[2]/div/div/form/div[3]/input[1]").click()
        time.sleep(30)
        _wait_for_download(download_dir, source)
        driver.close()
        parsed_df = _convert_downloaded_csv_to_english(download_dir, source)
        output_dir = download_dir.parent / "processed"
        if not output_dir.exists():
            output_dir.mkdir(parents=True, exist_ok=True)
        parsed_df.to_csv(
            output_dir / f"{source}_{dt.datetime.today().strftime('%Y%m%d')}.csv",
            index=False,
            encoding="utf-8",
        )
    except Exception as e:
        print(f"Error downloading {source} data: {e}")
        driver.close()
        raise e
    return parsed_df


def download_csv_from_hatsuden(start_date=None, end_date=None):
    if not start_date:
        start_date = dt.datetime.today() - dt.timedelta(days=1)
    if not end_date:
        end_date = start_date

    def _convert_downloaded_csv_to_english(path_to_downloads, source):
        downloaded_file = path_to_downloads.parent / "raw" / f"{start_date.strftime('%Y%m%d')}.csv"
        if downloaded_file.exists():
            df = pd.read_csv(downloaded_file, low_memory=False)
            df.columns = _columns_dict[source]
            sanitize = {r"\u3000": " "}
            df = df.replace(sanitize)
            df = convert_df_to_english(df, source)
        else:
            raise FileNotFoundError(f"{downloaded_file} does not exist")
        return df

    def _wait_for_download(path_to_downloads):
        seconds = 0
        dl_wait = True
        while dl_wait and seconds < 20:
            time.sleep(1)
            dl_wait = False
            for fname in path_to_downloads.iterdir():
                if fname.suffix.endswith(".crdownload"):
                    dl_wait = True
                if fname.suffix == ".csv":
                    new_name = f"{start_date.strftime('%Y%m%d')}" + fname.suffix
                    new_path = fname.parent.parent / "raw" / new_name
                    if not new_path.parent.exists():
                        new_path.parent.mkdir(parents=True, exist_ok=True)
                    try:
                        shutil.move(fname, new_path)
                    except Exception as e:
                        print(f"Error moving {fname} to {new_path}: {e}")
                        fname.unlink(missing_ok=True)
                        raise e
                    print(f"\nMoved {fname} to {new_path}\n")
            seconds += 1
        return seconds

    try:
        download_dir = Path(convert_path_to_linux(f"{data_path}\\hatsuden\\staging\\"))
        if not download_dir.exists():
            download_dir.mkdir(parents=True, exist_ok=True)
        driver = get_chrome_driver(download_dir, headless=True)
        url = "http://hatsuden-kokai.occto.or.jp/hks-web-public/info/hks"
        driver.implicitly_wait(30)
        driver.get(url)
        agree = driver.find_element(By.XPATH, "/html/body/div[2]/form/div/div/div/input[1]")
        try:
            agree.click()
        except Exception:
            driver.execute_script("arguments[0].click();", agree)
        next = driver.find_element(By.XPATH, "/html/body/div[2]/form/div/div/div/button")
        try:
            next.click()
        except Exception:
            driver.execute_script("arguments[0].click();", next)
        tab1 = driver.find_element(By.XPATH, "/html/body/nav[2]/div/div/ul/li[2]/a")
        try:
            tab1.click()
        except Exception:
            driver.execute_script("arguments[0].click();", tab1)

        tab2 = driver.find_element(By.XPATH, "/html/body/nav[2]/div/div/ul/li[2]/ul/li/a")
        try:
            tab2.click()
        except Exception:
            driver.execute_script("arguments[0].click();", tab2)
        driver.find_element(
            By.XPATH, "/html/body/form/div/div[4]/div/div[4]/div[1]/div/input"
        ).clear()
        driver.find_element(
            By.XPATH, "/html/body/form/div/div[4]/div/div[4]/div[1]/div/input"
        ).send_keys(start_date.strftime("%Y%m%d"))
        driver.find_element(
            By.XPATH, "/html/body/form/div/div[4]/div/div[4]/div[1]/div/input"
        ).send_keys(Keys.ENTER)
        driver.find_element(
            By.XPATH, "/html/body/form/div/div[4]/div/div[4]/div[3]/div/input"
        ).clear()
        driver.find_element(
            By.XPATH, "/html/body/form/div/div[4]/div/div[4]/div[3]/div/input"
        ).send_keys(end_date.strftime("%Y%m%d"))
        driver.find_element(
            By.XPATH, "/html/body/form/div/div[4]/div/div[4]/div[1]/div/input"
        ).send_keys(Keys.ENTER)
        driver.find_element(By.XPATH, "/html/body/form/div/div[4]/div/div[5]/button[1]").click()
        time.sleep(20)
        driver.find_element(By.XPATH, "/html/body/form/div/div[4]/div/div[5]/button[2]").click()
        _wait_for_download(download_dir)
        driver.close()
        parsed_df = _convert_downloaded_csv_to_english(download_dir, "hatsuden")
        output_dir = download_dir.parent / "processed"
        if not output_dir.exists():
            output_dir.mkdir(parents=True, exist_ok=True)
        parsed_df.to_csv(
            output_dir / f"{start_date.strftime('%Y%m%d')}.csv",
            index=False,
        )
        return parsed_df
    except Exception as e:
        print(f"Error downloading Hatsuden data: {e}")
        driver.close()
        raise e


if __name__ == "__main__":
    download_csv_from_hatsuden()
