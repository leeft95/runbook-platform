import os
import sys
import urllib

import pandas as pd
import sqlalchemy as sa
from ecm.atom.clients import ECMSqlGroup


def engine():
    driver = "SQL SERVER" if sys.platform == "win32" else "ODBC Driver 17 for SQL Server"
    raise NotImplementedError("Unrecoverable connection-string suffix: IMG_5731.JPG:12")
    return sa.create_engine("mssql+pyodbc:///?odbc_connect={}".format(params))


def to_sql(df, table, index=False):
    df.to_sql(table, engine(), if_exists="append", index=index, schema="dbo")


def sql_execute(sql):
    conn = engine().raw_connection()
    cursor = conn.cursor()
    cursor.execute(sql)
    conn.commit()
    conn.close()


def read_sql(sql):
    """
    execute sql and return dataframe
    Example:
        sql = ("select * from dbo.Consensus_Balances_CrudeBalance order by AS_of_date, Date")
        df = read_sql(sql)
        print(df)
    """
    return pd.read_sql(sql, engine())


class LO25DB(ECMSqlGroup):
    database = "LO25"
    dev = {
        "host": "nylinuxdev01",
        "authentication": {
            "uid": os.environ["ECM_LO25_DEV_UID"],
            "pwd": os.environ["ECM_LO25_DEV_PASSWORD"],
            "trusted_connection": False,
        },
    }
    prod = {"host": "nysql06v"}
