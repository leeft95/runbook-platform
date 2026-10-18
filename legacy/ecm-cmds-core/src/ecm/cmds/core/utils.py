import datetime as dt
import os
import sys
import time
import typing as tp
from pathlib import Path

import numpy as np
import pandas as pd
from ecm.atom.clients import retry
from loguru import logger as log


def _capitalize(text):
    if isinstance(text, dict):
        return type(text)({key: _capitalize(value) for key, value in text.items()})
    return text.capitalize() if isinstance(text, str) else text


def bbgcase(text):
    """
    convert to BBG-case, all upper except last one

    >>> assert bbgcase('EDZ9 COMDTY GIP') == 'EDZ9 Comdty GIP'
    >>> assert bbgcase('abc corporation') == 'ABC CORPORATION'
    """
    if isinstance(text, dict):
        return type(text)({key: _capitalize(value) for key, value in text.items()})
    if not isinstance(text, str):
        return text
    text = " ".join([x for x in text.upper().split(" ") if len(x)])
    for k in ["Comdty", "Index", "Curncy", "Corp", "Pfd", "Equity", "Govt", "Mtge"]:
        kup = " " + k.upper()
        if text.endswith(kup):
            return text.replace(kup, " " + k)
        elif kup + " " in text:
            return text.replace(" " + kup + " ", " " + k + " ")
    return text


def find_latest_file_date(folder, date_format, reverse=False):
    if len(os.listdir(convert_path_to_linux(folder))) == 0:
        return None
    else:
        exist_dates = []
        date_length = len(dt.datetime(2023, 1, 1).strftime(date_format))
        for filename in os.listdir(convert_path_to_linux(folder)):
            if os.path.isfile(convert_path_to_linux((folder + "\\" + filename))):
                if not reverse:
                    edt = dt.datetime.strptime(filename.split(".")[0][-date_length:], date_format)
                else:
                    edt = dt.datetime.strptime(filename.split(".")[0][:date_length], date_format)
                exist_dates.append(edt)
        if len(exist_dates) > 0:
            return np.max(exist_dates)
        else:
            return None


def tic():
    global startTime_for_tictoc
    startTime_for_tictoc = time.time()


def toc():
    if "startTime_for_tictoc" in globals():
        print("Elapsed time is " + str(time.time() - startTime_for_tictoc) + " seconds.")
    else:
        print("Toc: start time not set")


@retry(6, exceptions=[FileNotFoundError], before_retry=lambda x: time.sleep(60 * 10))
def retry_till_file_available(path: str) -> bool:
    """
    Checks if a file is available 6 times with a 10 min wait inbetween each try
    other wise will raise the FileNotFoundError
    """
    pth = Path(path)
    if not pth.exists():
        raise FileNotFoundError(f"File {pth} not available")
    else:
        return True


def convert_path_to_linux(path: tp.Union[str, Path]) -> tp.Union[str, Path]:
    if isinstance(path, Path):
        path = str(path)
        is_path = True
    else:
        is_path = False
    if sys.platform.startswith("win"):
        return path if not is_path else Path(path)
    elif sys.platform.startswith("linux"):
        path = (
            path.lower()
            .replace(r"\\elementcapital.corp\ecns01\pm\michel kikano", "/mnt/h")
            .replace("\\\\elementcapital.corp\\ecns01\\pm\\\\michel kikano", "/mnt/h")
            .replace("\\\\elementcapital.corp\\ecns01\\pm\\\michel kikano", "/mnt/h")  # noqa: W605
            .replace("\\\\elementcapital.corp\\ecns01\\pm\\michel kikano", "/mnt/h")
            .replace(r"s:\michel kikano", "/mnt/h")
            .replace("\\", "/")
        )
        return path if not is_path else Path(path)
    else:
        log.error(f"Path not converted {sys.platform} is not known")
        return path if not is_path else Path(path)


def get_rows_to_upsert(df_new: pd.DataFrame, df_existing: pd.DataFrame, key_cols: list, only_new=False) -> pd.DataFrame:
    df_new = df_new.reset_index()
    df_existing = df_existing.reset_index()

    df_new_idx = df_new.set_index(key_cols)
    df_existing_idx = df_existing.set_index(key_cols)

    common_cols = df_new_idx.columns.intersection(df_existing_idx.columns)
    df_new_idx = df_new_idx[common_cols]
    df_existing_idx = df_existing_idx[common_cols]

    new_idx = df_new_idx.index.difference(df_existing_idx.index)
    df_new_only = df_new_idx.loc[new_idx].reset_index()
    df_new_only["update_type"] = "new"

    if not only_new:
        common_idx = df_new_idx.index.intersection(df_existing_idx.index)

        df1 = df_new_idx.loc[common_idx]
        df2 = df_existing_idx.loc[common_idx]

        df1_aligned, df2_aligned = df1.align(df2)

        diff_mask = ~((df1_aligned == df2_aligned) | (df1_aligned.isna() & df2_aligned.isna()))
        changed_mask = diff_mask.any(axis=1)
        updated_idx = changed_mask[changed_mask].index

        df_merged = pd.merge(
            df1.loc[updated_idx].reset_index(),
            df2.loc[updated_idx].reset_index(),
            on=key_cols,
            suffixes=("_new", "_old"),
        )

        keep_cols = [col for col in df_merged.columns if col.endswith("_new")] + key_cols
        df_updated = df_merged[keep_cols].copy()

        df_updated.columns = [col.replace("_new", "") if col.endswith("_new") else col for col in df_updated.columns]
        df_updated["update_type"] = "updated"

        df_upsert = pd.concat([df_new_only, df_updated], ignore_index=True)
    else:
        df_upsert = df_new_only

    return df_upsert
