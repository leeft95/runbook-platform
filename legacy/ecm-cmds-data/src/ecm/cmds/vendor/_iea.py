import os

import pandas as pd
from ecm.cmds.config import data_path
from ecm.cmds.utils import convert_path_to_linux


class IEAClient:
    """
    Client for accessing EA data.
    """

    def __init__(self):
        self.folder = convert_path_to_linux(f"{data_path}\\IEA")
        self.iea_dict = {
            "CRUDEDAT": {
                "columns": ["Country", "Product", "Item", "Date", "Value"],
                "freq": ["M"],
            },
            "EXPORDAT": {
                "columns": ["Country", "Product", "To Country", "Date", "Value"],
                "freq": ["M"],
            },
            "IMPORDAT": {
                "columns": ["Country", "Product", "From Country", "Date", "Value"],
                "freq": ["M"],
            },
            "NOECDDE": {
                "columns": ["Country", "Date", "Value"],
                "freq": ["Q", "A"],
            },
            "OECDDE": {
                "columns": ["Country", "Product", "Date", "Value"],
                "freq": ["M", "Q", "A"],
            },
            "PRODDAT": {
                "columns": ["Product", "Country", "Item", "Date", "Value"],
                "freq": ["M"],
            },
            "SPLITDAT": {
                "columns": ["Product", "Country", "Item", "Date", "Value"],
                "freq": ["M"],
            },
            "STOCKDAT": {
                "columns": ["Category", "Country", "Product", "Date", "Value"],
                "freq": ["M"],
            },
            "SUMMARY": {
                "columns": ["Country", "State", "Date", "Value"],
                "freq": ["Q", "A"],
            },
            "SUPPLY": {
                "columns": ["Country", "Product", "Date", "Value"],
                "freq": ["M", "Q", "A"],
            },
        }

    def _release_folders(self):
        all_folders = [
            x[0] for x in os.walk(convert_path_to_linux(self.folder)) if x[0][-2:].isdigit()
        ]
        all_folders.sort()
        return all_folders

    def release_dates(self):
        all_folders = self._release_folders()
        return [x.split("\\")[-1] for x in all_folders]

    def get_meta(self, file):
        pass

    def get_data(self, release_date, file, country, frequency, **kwargs):
        """
        Get time series data from an IEA file
        """
        product = kwargs.get("product", None)
        item = kwargs.get("item", None)
        from_country = kwargs.get("from_country", None)
        to_country = kwargs.get("to_country", None)
        if isinstance(release_date, str) and len(release_date) == 6:
            release_list = [release_date]
        elif isinstance(release_date, int):
            release_list = self.release_dates()[-release_date:]
        elif isinstance(release_date, list):
            release_list = release_date
        out_df = pd.DataFrame()
        for i in release_list:
            file_path = convert_path_to_linux(f"{self.folder}\\{i}\\{file}.TXT")
            df = pd.read_csv(file_path, header=None, sep=r"\s+")
            df.columns = self.iea_dict[file]["columns"]
            if frequency.lower() == "q":
                df_ = df.loc[
                    (df["Country"] == country)
                    & (df["Date"].str[0].str.isdigit())
                    & (df["Date"].str[1] == "Q"),
                    :,
                ]
            elif frequency.lower() in ["a", "y"]:
                df_ = df.loc[(df["Country"] == country) & (df["Date"].str.isdigit()), :]
            elif frequency.lower() == "m":
                df_ = df.loc[(df["Country"] == country) & (df["Date"].str.len()), :]
            if product is not None:
                df_ = df_.loc[df_["Product"] == product, :]
            if item is not None:
                df_ = df_.loc[df_["Item"] == item, :]
            if from_country is not None:
                df_ = df_.loc[df_["From Country"] == from_country, :]
            if to_country is not None:
                df_ = df_.loc[df_["To Country"] == to_country, :]
            df_ = df_[["Date", "Value"]].set_index("Date")
            df_.index = pd.to_datetime(df_.index)
            df_.sort_index(inplace=True)
            df_.columns = [i]
            out_df = pd.concat([out_df, df_], axis=1)
        return out_df


def get_summary(release_date, name, frequency):
    file_path = convert_path_to_linux(f"{data_path}\\IEA\\{release_date}\\SUMMARY.TXT")
    df = pd.read_csv(file_path, header=None, sep=r"\s+")
    df.columns = ["Name", "State", "Date", "Value"]
    if frequency.lower() == "q":
        df_ = df.loc[(df["Name"] == name) & (df["Date"].str.contains("Q")), :]
    elif frequency.lower() in ["a", "y"]:
        df_ = df.loc[(df["Name"] == name) & (~df["Date"].str.contains("Q")), :]
    df_ = df_[["Date", "Value"]].set_index("Date")
    df_.index = pd.to_datetime(df_.index)
    return df_.sort_index()


def get_supply(release_date, name, category, frequency):
    file_path = convert_path_to_linux(f"{data_path}\\IEA\\{release_date}\\SUPPLY.TXT")
    df = pd.read_csv(file_path, header=None, sep=r"\s+")
    df.columns = ["Name", "Category", "Date", "Value"]
    if frequency.lower() == "q":
        df_ = df.loc[
            (df["Name"] == name)
            & (df["Category"] == category)
            & (df["Date"].str[0].str.isdigit())
            & (df["Date"].str[1] == "Q"),
            :,
        ]
    elif frequency.lower() in ["a", "y"]:
        df_ = df.loc[
            (df["Name"] == name) & (df["Category"] == category) & (df["Date"].str.isdigit()), :
        ]
    elif frequency.lower() == "m":
        df_ = df.loc[
            (df["Name"] == name) & (df["Category"] == category) & (df["Date"].str.len()), :
        ]
    df_ = df_[["Date", "Value"]].set_index("Date")
    df_.index = pd.to_datetime(df_.index)
    return df_.sort_index()


def get_oecdde(release_date, name, category, frequency):
    file_path = convert_path_to_linux(f"{data_path}\\IEA\\{release_date}\\OECDDE.TXT")
    df = pd.read_csv(file_path, header=None, sep=r"\s+")
    df.columns = ["Name", "Category", "Date", "Value"]
    if frequency.lower() == "q":
        df_ = df.loc[
            (df["Name"] == name)
            & (df["Category"] == category)
            & (df["Date"].str[0].str.isdigit())
            & (df["Date"].str[1] == "Q"),
            :,
        ]
    elif frequency.lower() in ["a", "y"]:
        df_ = df.loc[
            (df["Name"] == name) & (df["Category"] == category) & (df["Date"].str.isdigit()), :
        ]
    elif frequency.lower() == "m":
        df_ = df.loc[
            (df["Name"] == name) & (df["Category"] == category) & (df["Date"].str.len()), :
        ]
    df_ = df_[["Date", "Value"]].set_index("Date")
    df_.index = pd.to_datetime(df_.index)
    return df_.sort_index()


if __name__ == "__main__":
    client = IEAClient()
    print(client.release_dates())
