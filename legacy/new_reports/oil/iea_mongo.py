import pandas as pd
import datetime as dt
import os
from functools import partial
from pyg_mongo import *
from pyg_cell import *
from ecm.cmds.config import data_path
import ecm.cmds.pyg as pyg
import ecm.cmds.vendor._iea as func_iea
from ecm.cmds.utils import convert_path_to_linux


def _missing_photo_kwargs(line):
    """Transcription marker for arguments clipped from the available photographs."""
    raise NotImplementedError(f"Missing photographed keyword arguments: iea_mongo.py line {line}")


def create_db_table():
    raise NotImplementedError("Missing photographed database connection: iea_mongo.py line 13")


def save_summary(release_date="202509"):
    file_path = convert_path_to_linux(f"{data_path}\\IEA\\{release_date}\\SUMMARY.TXT")
    df = pd.read_csv(file_path, header=None, sep=r"\s+")
    df.columns = ["Name", "State", "Date", "Value"]
    db = partial(mongo_table, table="summary", pk=["release_date", "name", "frequency"], db="iea", url=pyg.url)
    unique_names = df["Name"].unique()
    freqs = ["Q", "A"]
    for i in unique_names:
        for j in freqs:
            try:
                c = pyg.get_cell(db, release_date=release_date, name=i, frequency=j)
                print(c.data)
            except:
                c = periodic_cell(function=func_iea.get_summary, db=db, release_date=release_date, name=i,
                                  **_missing_photo_kwargs(31))
            c.go()


def save_supply(release_date="202509"):
    file_path = convert_path_to_linux(f"{data_path}\\IEA\\{release_date}\\SUPPLY.TXT")
    df = pd.read_csv(file_path, header=None, sep=r"\s+")
    df.columns = ["Name", "Category", "Date", "Value"]
    db = partial(mongo_table, table="supply", pk=["release_date", "name", "category", "frequency"], db="iea",
                 **_missing_photo_kwargs(39))
    unique_names = df["Name"].unique()
    cats = df["Category"].unique()
    freqs = ["Q", "A", "M"]
    for i in unique_names:
        for j in freqs:
            for k in cats:
                try:
                    c = pyg.get_cell(db, release_date=release_date, name=i, category=k, frequency=j)
                    print(c.data)
                except:
                    c = periodic_cell(function=func_iea.get_supply, db=db, release_date=release_date, name=i,
                                      **_missing_photo_kwargs(52))
                c.go()


def save_oecdde(release_date="202509"):
    file_path = convert_path_to_linux(f"{data_path}\\IEA\\{release_date}\\OECDDE.TXT")
    df = pd.read_csv(file_path, header=None, sep=r"\s+")
    df.columns = ["Name", "Category", "Date", "Value"]
    db = partial(mongo_table, table="oecdde", pk=["release_date", "name", "category", "frequency"], db="iea",
                 **_missing_photo_kwargs(60))
    unique_names = df["Name"].unique()
    cats = df["Category"].unique()
    freqs = ["Q", "A", "M"]
    for i in unique_names:
        for j in freqs:
            for k in cats:
                try:
                    c = pyg.get_cell(db, release_date=release_date, name=i, category=k, frequency=j)
                    print(c.data)
                except:
                    c = periodic_cell(function=func_iea.get_oecdde, db=db, release_date=release_date, name=i,
                                      **_missing_photo_kwargs(73))
                c.go()


def save_hist_data():
    all_folders = [x[0] for x in os.walk(convert_path_to_linux(f"{data_path}\\IEA")) if x[0][-2:].isdigit()]
    all_folders.sort()
    for i in all_folders[-21:]:
        print(i[-6:])
        save_oecdde(release_date=i[-6:])


if __name__ == '__main__':
    save_hist_data()
