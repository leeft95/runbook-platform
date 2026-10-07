import pandas as pd
import datetime as dt
import ecm.cmds.sql as sql
from ecm.cmds.cdr import today
from ecm.cmds.config import data_path
from ecm.cmds.utils import convert_path_to_linux


def save_to_db(df, table_name, run_date):
    val_d = dt.datetime(run_date.year, run_date.month, 1)
    df['As_of_date'] = val_d
    last_date = sql.read_sql(f"Select MAX(As_of_date) from {table_name}")
    if len(df) > 0 and last_date.iloc[0, 0] < val_d:
        sql.to_sql(df, table_name, index=False)


def read_txt(file_name, run_date):
    return pd.read_csv(convert_path_to_linux(f"{data_path}\\IEA\\{run_date.strftime('%Y%m')}\\{file_name}.txt"), header=None, sep=r'\s+')


def update(run_date):
    print("Summary")
    df = read_txt("SUMMARY", run_date=run_date)
    df.columns = ['Region', 'Observation', 'Period', 'Obs_value']
    save_to_db(df, "IEA_Summary", run_date=run_date)
    print("Stocks")
    df = read_txt("stockdat", run_date=run_date)
    df.columns = ['Govt_Industrial', 'Country', 'Product', 'Date', 'Obs_value']
    save_to_db(df, "IEA_Stocks", run_date=run_date)
    print("Crude")
    df = read_txt("CRUDEDAT", run_date=run_date)
    df.columns = ['Country', 'Product', 'Flow_Breakdown', 'Date', 'Obs_value']
    save_to_db(df, "IEA_Crude", run_date=run_date)
    print("Exports")
    df = read_txt("Expordat", run_date=run_date)
    df.columns = ['Country_Exporting', 'Product', 'Country_Importing', 'Date', 'Obs_Value']
    save_to_db(df, "IEA_Exports", run_date=run_date)
    print("Imports")
    df = read_txt("Impordat", run_date=run_date)
    df.columns = ['Country_Importing', 'Product', 'Country_Exporting', 'Date', 'Obs_Value']
    save_to_db(df, "IEA_Imports", run_date=run_date)
    print("Non OECD")
    df = read_txt("NOECDDE", run_date=run_date)
    df.columns = ['Country', 'Date', 'Obs_Value']
    save_to_db(df, "IEA_Non_OECD_Demand", run_date=run_date)
    print("OECD")
    df = read_txt("OECDDE", run_date=run_date)
    df.columns = ['Country', 'Product', 'Date', 'Obs_value']
    save_to_db(df, "IEA_OECD_Demand", run_date=run_date)
    print("Production")
    df = read_txt("PRODDAT", run_date=run_date)
    df.columns = ['Product', 'Country', 'Flow_Breakdown', 'Date', 'Obs_value']
    save_to_db(df, "IEA_Prod", run_date=run_date)
    print("SPLITDAT")
    df = read_txt("SPLITDAT", run_date=run_date)
    df.columns = ['Product', 'Country', 'Flow_Breakdown', 'Date', 'Obs_value']
    save_to_db(df, "IEA_Prod_Split", run_date=run_date)
    print("Field by Field")
    raise NotImplementedError("Missing photographed CSV filename/arguments: iea_data.py line 67")
    monthlydata = df.loc[df['FREQUENCY'] == 'monthly']
    save_to_db(monthlydata, "IEA_FBF", run_date=run_date)


if __name__ == '__main__':
    dt_list = [
        dt.datetime(2025, 8, 13),
    ]
    for i in dt_list:
        update(run_date=i)
