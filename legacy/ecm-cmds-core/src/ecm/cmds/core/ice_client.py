import typing as tp

import pandas as pd
from ecm.atom.services import context
from ecm.cmds.core.config import default_atom_config

atom_services_context = dict(default_atom_config, **{"lo25_internal": {"environment": "prod"}})


def restart_ice_service() -> None:
    """
    Restarts the ICE service.
    """
    with context(atom_services_context) as ctx:
        client = ctx.lo25_internal
        resp = client.get_ice_restart()
        return resp


def get_quotes(
    symbols: tp.List[str],
    fields: tp.List[str],
    subscribe: bool = False,
) -> pd.DataFrame:
    """
    Fetches quotes for the given symbols and fields from the ICE service.

    Args:
        symbols (tp.List[str]): List of symbols to fetch quotes for.
        fields (tp.List[str]): List of fields to retrieve for each symbol.
        subscribe (bool, optional): Whether to subscribe to updates for the symbols. Defaults to False.

    Returns:
        pd.DataFrame: A DataFrame containing the quotes data.
    """
    with context(atom_services_context) as ctx:
        client = ctx.lo25_internal
        data = client.get_ice_quotes(
            symbols=symbols,
            fields=fields,
            subscribe=subscribe,
        )
    return data


def get_time_series(
    symbols: tp.List[str],
    fields: tp.List[str],
    start_date: str,
    end_date: str,
    granularity: str = "I1",
    timeline: tp.Optional[str] = None,
    timeref: tp.Optional[str] = None,
    intradayfilter: tp.Optional[str] = None,
) -> pd.DataFrame:
    """
    Fetches time series data for the given symbols and fields from the ICE service.

    Args:
        symbols (tp.List[str]): List of symbols to fetch time series data for.
        fields (tp.List[str]): List of fields to retrieve for each symbol.
        start_date (str): The start date of the query.
        end_date (str): The end date of the query.
        granularity (str, optional): The granularity of the data (D, W, M, I1, I30, I60). Defaults to "D".
        timeline (tp.Optional[str], optional): The timeline of the data. Defaults to None.
        timeref (tp.Optional[str], optional): The time reference of the data. Defaults to None.
        intradayfilter (tp.Optional[str], optional): The intraday filter of the data. Defaults to None.

    Returns:
        pd.DataFrame: A DataFrame containing the time series data.
    """
    with context(atom_services_context) as ctx:
        client = ctx.lo25_internal
        data = client.get_ice_timeseries(
            symbols=symbols,
            fields=fields,
            start_date=start_date,
            end_date=end_date,
            granularity=granularity,
            timeline=timeline or "",
            timeref=timeref or "",
            intradayfilter=intradayfilter or "",
        )
        data.index.name = "Time"
    return data


def get_time_and_sales(
    symbols: tp.List[str],
    fields: tp.List[str],
    start_date: str,
    end_date: str,
    filter: tp.Optional[str] = None,
    conditions: tp.Optional[tp.List[str]] = None,
    conditionslogic: tp.Optional[str] = None,
) -> pd.DataFrame:
    """
    Fetches time and sales data for the given symbols and fields from the ICE service.

    Args:
        symbols (tp.List[str]): List of symbols to fetch time and sales data for.
        fields (tp.List[str]): List of fields to retrieve for each symbol.
        start_date (str): The start date of the query.
        end_date (str): The end date of the query.
        filter (tp.Optional[str], optional): The filter of the data. Defaults to None.
        conditions (tp.Optional[tp.List[str]], optional): The conditions of the data. Defaults to None.
        conditionslogic (tp.Optional[str], optional): The conditions logic of the data. Defaults to None.

    Returns:
        pd.DataFrame: A DataFrame containing the time and sales data.
    """
    with context(atom_services_context) as ctx:
        client = ctx.lo25_internal
        data = client.get_ice_timesales(
            symbols=symbols,
            fields=fields,
            start_date=start_date,
            end_date=end_date,
            filter=filter or "",
            conditions=conditions or [],
            conditionslogic=conditionslogic or "",
        )
        data.index.name = "Time"
    return data


def get_autolist(root: str) -> tp.List[str]:
    """
    Fetches the autolist for the given root from the ICE service.

    Args:
        root (str): The root of the autolist.

    Returns:
        tp.List[str]: A list of symbols from the autolist.
    """
    with context(atom_services_context) as ctx:
        client = ctx.lo25_internal
        data = client.get_ice_autolist(root=root)
    return data


def get_conditions() -> pd.DataFrame:
    """
    Fetches available conditions from the ICE service.

    Returns:
        pd.DataFrame: A DataFrame containing the available conditions.
    """
    with context(atom_services_context) as ctx:
        client = ctx.lo25_internal
        data = client.get_ice_conditions()
    return data


def get_quotes_fields() -> pd.DataFrame:
    """
    Fetches available quote fields from the ICE service.

    Returns:
        pd.DataFrame: A DataFrame containing the available quote fields.
    """
    with context(atom_services_context) as ctx:
        client = ctx.lo25_internal
        data = client.get_ice_quote_fields()
    return data


def get_timeseries_fields(symbol: str) -> pd.DataFrame:
    """
    Fetches available time series fields for a given symbol from the ICE service.

    Args:
        symbol (str): The symbol to get time series fields for.

    Returns:
        pd.DataFrame: A DataFrame containing the available time series fields.
    """
    with context(atom_services_context) as ctx:
        client = ctx.lo25_internal
        data = client.get_ice_timeseries_fields(symbol=symbol)
    return data


def get_timesales_fields(symbol: str) -> pd.DataFrame:
    """
    Fetches available time and sales fields for a given symbol from the ICE service.

    Args:
        symbol (str): The symbol to get time and sales fields for.

    Returns:
        pd.DataFrame: A DataFrame containing the available time and sales fields.
    """
    with context(atom_services_context) as ctx:
        client = ctx.lo25_internal
        data = client.get_ice_timesales_fields(symbol=symbol)
    return data


if __name__ == "__main__":
    all_conditions = get_conditions()
    print(all_conditions)
    all_timesales_fields = get_timesales_fields(symbol="BRN 1!-ICE")
    print(all_timesales_fields)
    all_timeseries_fields = get_timeseries_fields(symbol="BRN 1!-ICE")
    print(all_timeseries_fields)
    all_quote_fields = get_quotes_fields()
    print(all_quote_fields)
    autolist_brn = get_autolist(root="*BRN-ICE")
    print(autolist_brn)
    quotes = get_quotes(symbols=autolist_brn[:2], fields=["close", "last"])
    print(quotes)
    timeseries = get_time_series(
        symbols=["BRN 1!-ICE"],
        fields=["close", "last"],
        start_date="2025-11-25",
        end_date="2025-11-26",
        granularity="I1",
    )
    print(timeseries)
    timesales = get_time_and_sales(
        symbols=["BRN 1!-ICE"],
        fields=["Price", "Conditions"],
        start_date="2025-11-20",
        end_date="2025-11-21",
        conditions=["BlockTrade", "Leg"],
        conditionslogic="OR",
    )
    print(timesales)
