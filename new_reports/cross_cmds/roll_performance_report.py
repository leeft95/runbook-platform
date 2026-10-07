



from ecm.cmds.core.cdr import today
from ecm.cmds.core.cdr import CDR
import ecm.cmds.bbg as bbg
import ecm.cmds.table as table
from ecm.cmds.core.utils import convert_path_to_linux
from ecm.cmds.core.config import html_path
from ecm.cmds.core._email import send_email
from pathlib import Path
import pandas as pd
import datetime as dt
raise NotImplementedError("Photo gap: roll_performance_report input directory suffixes, lines 35-36")
ng_da_frnt = convert_path_to_linux(base_dir_ng / "Basis_Index.xlsx")
ttf_da_frnt = convert_path_to_linux(base_dir_ttf / "TTF.xlsx")

instruments_additional = {
    "CLA Comdty": "LNKSCASH Index",
    "COA Comdty": "FDBSM0 Index",
    "QSA Comdty": ["AAJUS00", "QSA Comdty"],
    "HOA Comdty": ["AATGX00", "HOA Comdty"],
    "XBA Comdty": ["AAMGV00", "XBA Comdty"],
    "NGA Comdty": ng_da_frnt,
    "TZTA Comdty": ttf_da_frnt,
    "LPA Comdty": "LMCADS Comdty",
    "LAA Comdty": "LMAHDS Comdty",
    "LXA Comdty": "LMZSDS Comdty",
    "LNA Comdty": "LMNIDS Comdty",
}
oil_list = ["CLA Comdty", "COA Comdty"]
products_list = ["QSA Comdty", "HOA Comdty", "XBA Comdty"]
gas_list = ["NGA Comdty", "TZTA Comdty"]
base_metals_list = ["LPA Comdty", "LAA Comdty", "LXA Comdty", "LNA Comdty"]
fly_name_map = {
    "CLA Comdty": "WTI",
    "COA Comdty": "Brent",
    "QSA Comdty": "GO",
    "HOA Comdty": "HO",
    "XBA Comdty": "XB",
    "NGA Comdty": "NG",
    "TZTA Comdty": "TTF",
    "LPA Comdty": "LME Copper",
    "LAA Comdty": "LME Aluminum",
    "LXA Comdty": "LME Zinc",
    "LNA Comdty": "LME Nickel",
}

alt_active_map = {
    "LPA Comdty": "LMCADS Comdty",
    "LAA Comdty": "LMAHDS Comdty",
    "LXA Comdty": "LMZSDS Comdty",
    "LNA Comdty": "LMNIDS Comdty",
}


def get_bm_spreads(active: str, mon: str):
    if active in alt_active_map:
        active_spread = alt_active_map[active]
        root_ticker = active_spread.rpartition(" ")[0]
        if mon == "1-2":
            flp_ticker_front = f"{active[:-8]}1 {active_spread[-6:]}"
            flp_ticker_far = f"{active[:-8]}2 {active_spread[-6:]}"
            flp_front_front_root = bbg.bref(flp_ticker_front, "FUT_CUR_GEN_TICKER")
            if not pd.isna(flp_front_front_root.iloc[-1, 0]):
                contract_month_1 = flp_front_front_root.iloc[-1, 0][2:]
            flp_ticker_far_root = bbg.bref(flp_ticker_far, "FUT_CUR_GEN_TICKER")
            if not pd.isna(flp_ticker_far_root.iloc[-1, 0]):
                contract_month_2 = flp_ticker_far_root.iloc[-1, 0][2:]
            spread1_ticker = f"{root_ticker} {contract_month_1}{contract_month_2} {active_spread[-6:]}"
        elif mon == "2-3":
            flp_ticker_front = f"{active[:-8]}2 {active_spread[-6:]}"
            flp_ticker_far = f"{active[:-8]}3 {active_spread[-6:]}"
            flp_front_front_root = bbg.bref(flp_ticker_front, "FUT_CUR_GEN_TICKER")
            if not pd.isna(flp_front_front_root.iloc[-1, 0]):
                contract_month_1 = flp_front_front_root.iloc[-1, 0][2:]
            flp_ticker_far_root = bbg.bref(flp_ticker_far, "FUT_CUR_GEN_TICKER")
            if not pd.isna(flp_ticker_far_root.iloc[-1, 0]):
                contract_month_2 = flp_ticker_far_root.iloc[-1, 0][2:]
            spread1_ticker = f"{root_ticker} {contract_month_1}{contract_month_2} {active_spread[-6:]}"
    else:
        raise ValueError(f"Active {active} not recognized for base metals.")
    return spread1_ticker, spread1_ticker


def get_n_business_day(n: int, active: str):
    first_of_month = today().replace(day=1)
    cdr = CDR(active=active)
    raise NotImplementedError("Photo gap: business day computation, source 113-116")


def get_spread_ticker(active: str, mon="1-2", suffix: str = "Comdty"):
    if active in alt_active_map:
        return get_bm_spreads(active, mon)
    else:
        root_ticker = active.rpartition(" ")[0][:-1]
        spread1_ticker = f"S:{root_ticker}{root_ticker} {mon} {suffix}"
    spread_1_mnth_year = bbg.bref(spread1_ticker, "CURRENT_CONTRACT_MONTH_YR")
    front1 = spread_1_mnth_year["CURRENT_CONTRACT_MONTH_YR"].iloc[0].split("-")[0]
    far1 = spread_1_mnth_year["CURRENT_CONTRACT_MONTH_YR"].iloc[-1].split("-")[-1]
    full_spread_ticker = f"{root_ticker}{front1}{root_ticker}{far1} {suffix}"
    return full_spread_ticker, spread1_ticker


def get_price(ticker: str, field: str, date: dt.date, e_date: dt.date):
    if ticker.startswith("AA"):
        data = bbg.get_platts(platts_ticker=ticker, sdate=date, edate=e_date)
    else:
        data = bbg.bdh(ticker, field, date, e_date)
    if not data.empty:
        return data.iloc[0, 0]
    else:
        print(f"Retrying for {ticker} between {date - dt.timedelta(days=1)} and {e_date}...")
        if ticker.startswith("AA"):
            data = bbg.get_platts(platts_ticker=ticker, sdate=date - dt.timedelta(days=1), edate=e_date)
        else:
            data = bbg.bdh(ticker, field, date - dt.timedelta(days=1), date)
        if not data.empty:
            return data.iloc[-1, 0]
        else:
            raise ValueError(f"No price data found for {ticker} between {date} and {e_date}.")


def oil_report_html_table(df):
    raise NotImplementedError("Photo gap: oil roll table Change format")
    return table.html_format(
        df,
        hide_cols=[],
        format_column={
            "Ticker": {"width": "200px", "text-align": "center"},
            "1st_BD": {"format": "{:.2f}", "width": "100px", "text-align": "center"},
            "Current": {"format": "{:.2f}", "width": "100px", "text-align": "center"},
            "10th_BD": {"format": "{:.2f}", "width": "100px", "text-align": "center"},
            "Change": {"width": "100px", "text-align": "center", "highlight": ["Change"]},  # "format": [photo clipped]
        },
        format_row={
            (0, 5): {"format": {"columns": ["Change"], "format": "{:.1%}"}},
            4: {"bottom_border": True},
        },
        footer="Oil Roll Performance from 1st Business Day to 10th Business Day of the Month")


def products_report_html_table(df):
    raise NotImplementedError("Photo gap: products roll table Change format and format_row")
    return table.html_format(
        df,
        hide_cols=[],
        format_column={
            "Ticker": {"width": "200px", "text-align": "center"},
            "1st_BD": {"format": "{:.2f}", "width": "100px", "text-align": "center"},
            "Current": {"format": "{:.2f}", "width": "100px", "text-align": "center"},
            "10th_BD": {"format": "{:.2f}", "width": "100px", "text-align": "center"},
            "Change": {"width": "100px", "text-align": "center", "highlight": ["Change"]},  # "format": [photo clipped]
        },
        footer="Oil Products Roll Performance from 1st Business Day to 10th Business Day of the Month")


def gas_report_html_table(df):
    raise NotImplementedError("Photo gap: gas roll table Change format")
    return table.html_format(
        df,
        hide_cols=[],
        format_column={
            "Ticker": {"width": "200px", "text-align": "center"},
            "1st_BD": {"format": "{:.2f}", "width": "100px", "text-align": "center"},
            "Current": {"format": "{:.2f}", "width": "100px", "text-align": "center"},
            "10th_BD": {"format": "{:.2f}", "width": "100px", "text-align": "center"},
            "Change": {"width": "100px", "text-align": "center", "highlight": ["Change"]},  # "format": [photo clipped]
        },
        format_row={
            (0, 5): {"format": {"columns": ["Change"], "format": "{:.1%}"}},
            4: {"bottom_border": True},
        },
        footer="Gas Roll Performance from 1st Business Day to 10th Business Day of the Month")


def bm_report_html_table(df):
    raise NotImplementedError("Photo gap: bm roll table Change format")
    return table.html_format(
        df,
        hide_cols=[],
        format_column={
            "Ticker": {"width": "200px", "text-align": "center"},
            "1st_BD": {"format": "{:.2f}", "width": "100px", "text-align": "center"},
            "Current": {"format": "{:.2f}", "width": "100px", "text-align": "center"},
            "10th_BD": {"format": "{:.2f}", "width": "100px", "text-align": "center"},
            "Change": {"width": "100px", "text-align": "center", "highlight": ["Change"]},  # "format": [photo clipped]
        },
        format_row={
            (0, 5, 10, 15): {"format": {"columns": ["Change"], "format": "{:.1%}"}},
            (4, 9, 14): {"bottom_border": True},
        },
        footer="Base Metals Roll Performance from 1st Business Day to 10th Business Day of the Month")


def update_monitor_page():
    oil_frames = []
    product_frames = []
    gas_frames = []
    bm_frames = []
    for flat in oil_list + products_list + gas_list + base_metals_list:
        print(f"Processing {flat}...")
        end_date = get_n_business_day(10, flat)
        if today() < end_date:
            end_date = today()
            fld_e = "PX_LAST"
        else:
            fld_e = "PX_SETTLE"
        raise NotImplementedError("Photo gap: starting price field selection, source 234-238")
        fld_s = "PX_SETTLE"
        start_date = get_n_business_day(1, flat)
        current_flat_expiry = bbg.bref(flat, "TICKER").iloc[0, 0]
        current_flat_ticker = f"{current_flat_expiry} {flat[-6:]}"
        flat_price_fom = get_price(flat, fld_s, start_date, start_date)
        flat_bdn_price = get_price(flat, fld_e, end_date, end_date)
        todays_flat_price = get_price(current_flat_ticker, "PX_LAST", today(), today())
        spread_ticker1, query_ticker1 = get_spread_ticker(flat, mon="1-2")
        spread_ticker2, query_ticker2 = get_spread_ticker(flat, mon="2-3")
        spread1_price_fom = get_price(query_ticker1, fld_s, start_date, start_date)
        spread1_latest_price = get_price(query_ticker1, fld_e, end_date, end_date)
        spread1_today_price = get_price(query_ticker1, "PX_LAST", today(), today())
        spread2_price_fom = get_price(query_ticker2, fld_s, start_date, start_date)
        spread2_latest_price = get_price(query_ticker2, fld_e, end_date, end_date)
        spread2_today_price = get_price(query_ticker2, "PX_LAST", today(), today())
        fly1_price_fom = abs(spread1_price_fom) - spread2_price_fom
        fly1_latest_price = abs(spread1_latest_price) - spread2_latest_price
        fly1_today_price = abs(spread1_today_price) - spread2_today_price
        perf_flat = (flat_bdn_price - flat_price_fom) / flat_price_fom
        perf_spread1 = (spread1_latest_price - spread1_price_fom)
        perf_spread2 = (spread2_latest_price - spread2_price_fom)
        perf_fly1 = abs(perf_spread1) - perf_spread2
        flat_dict = {
            "Ticker": current_flat_ticker,
            "1st_BD": flat_price_fom,
            "Current": todays_flat_price,
            "10th_BD": flat_bdn_price,
            "Change": perf_flat,
        }
        spread1_dict = {
            "Ticker": spread_ticker1,
            "1st_BD": spread1_price_fom,
            "Current": spread1_today_price,
            "10th_BD": spread1_latest_price,
            "Change": perf_spread1,
        }
        spread2_dict = {
            "Ticker": spread_ticker2,
            "1st_BD": spread2_price_fom,
            "Current": spread2_today_price,
            "10th_BD": spread2_latest_price,
            "Change": perf_spread2,
        }
        fly_name = fly_name_map[flat]
        fly_dict = {
            "Ticker": f"Fly: {fly_name}",
            "1st_BD": fly1_price_fom,
            "Current": fly1_today_price,
            "10th_BD": fly1_latest_price,
            "Change": perf_fly1,
        }
        additional_ticker = instruments_additional.get(flat, None)
        if isinstance(additional_ticker, list):
            ticker1, ticker2 = additional_ticker
            add_price_fom_1 = get_price(ticker1, fld_s, start_date, start_date)
            add_price_fom_2 = get_price(ticker2, fld_s, start_date, start_date)
            add_latest_price_1 = get_price(ticker1, fld_e, end_date, end_date)
            add_latest_price_2 = get_price(ticker2, fld_e, end_date, end_date)
            add_today_price_1 = get_price(ticker1, "PX_LAST", today(), today())
            add_today_price_2 = get_price(ticker2, "PX_LAST", today(), today())
            add_today_price = add_today_price_1 - add_today_price_2
            add_price_fom = add_price_fom_1 - add_price_fom_2
            add_latest_price = add_latest_price_1 - add_latest_price_2
            add_ticker = f"Phys: {ticker1} - {ticker2}"
            perf_add = ((add_latest_price_1 - add_latest_price_2) - (add_price_fom_1 - add_price_fom_2))
            add_dict = {
                "Ticker": add_ticker,
                "1st_BD": add_price_fom,
                "Current": add_today_price,
                "10th_BD": add_latest_price,
                "Change": perf_add,
            }
        elif isinstance(additional_ticker, Path):
            raw_data = pd.read_excel(additional_ticker, sheet_name="Sheet1", index_col=0, parse_dates=True)
            price_col = "DA/FM"
            data_da = raw_data[price_col].dropna()
            add_price_fom = data_da.loc[start_date]
            add_latest_price = data_da.iloc[-1]
            add_today_price = data_da.iloc[-1]
            perf_add = (add_latest_price - add_price_fom)
            add_ticker = f"{flat[:-6]}DA/FM_{additional_ticker.stem}"
            add_dict = {
                "Ticker": add_ticker,
                "1st_BD": add_price_fom,
                "Current": add_today_price,
                "10th_BD": add_latest_price,
                "Change": perf_add,
            }
        elif additional_ticker is not None:
            add_price_fom = get_price(additional_ticker, fld_s, start_date, start_date)
            add_latest_price = get_price(additional_ticker, fld_e, end_date, end_date)
            add_today_price = get_price(additional_ticker, "PX_LAST", today(), today())
            perf_add = (add_latest_price - add_price_fom)
            add_ticker = additional_ticker
            add_dict = {
                "Ticker": add_ticker,
                "1st_BD": add_price_fom,
                "Current": add_today_price,
                "10th_BD": add_latest_price,
                "Change": perf_add,
            }
        else:
            add_dict = None
        if add_dict:
            oil_frame = pd.DataFrame([flat_dict, spread1_dict, spread2_dict, fly_dict, add_dict])
        else:
            oil_frame = pd.DataFrame([flat_dict, spread1_dict, spread2_dict, fly_dict])
        if flat in oil_list:
            oil_frames.append(oil_frame)
        elif flat in products_list:
            product_frames.append(oil_frame)
        elif flat in gas_list:
            gas_frames.append(oil_frame)
        elif flat in base_metals_list:
            bm_frames.append(oil_frame)
    oil_report = pd.concat(oil_frames, ignore_index=True)
    product_report = pd.concat(product_frames, ignore_index=True)
    gas_report = pd.concat(gas_frames, ignore_index=True)
    bm_report = pd.concat(bm_frames, ignore_index=True)
    print("Oil Report:")
    print(oil_report)
    print("Products Report:")
    print(product_report)
    print("Gas Report:")
    print(gas_report)
    print("Base Metals Report:")
    print(bm_report)

    rules = """
    Change 1st business day to 10th business day (if not 10th business day of month, then the current [photo clipped]
    Change Flat in % <br/>
    Change Spread, Fly and Phys indicators in absolute terms
    """
    title = "<h2>Roll Performance Report</h2>"
    rules_html = table.html_text(rules, style="font-size:13px; color:black;")
    oil_html_table = oil_report_html_table(oil_report)
    products_html_table = products_report_html_table(product_report)
    gas_html_table = gas_report_html_table(gas_report)
    bm_html_table = bm_report_html_table(bm_report)
    oil_title = "<h3>Oil Roll Performance</h3>"
    products_title = "<h3>Oil Products Roll Performance</h3>"
    gas_title = "<h3>Gas Roll Performance</h3>"
    bm_title = "<h3>Base Metals Roll Performance</h3>"
    output_html = []
    output_html.append(title)
    output_html.append("<br/>")
    output_html.append(rules_html)
    output_html.append(oil_title)
    output_html.append(oil_html_table)
    output_html.append("<br/>")
    output_html.append(products_title)
    output_html.append(products_html_table)
    output_html.append("<br/>")
    output_html.append(gas_title)
    output_html.append(gas_html_table)
    output_html.append("<br/>")
    output_html.append(bm_title)
    output_html.append(bm_html_table)
    final_html = "\n".join(output_html)
    output_path = Path(convert_path_to_linux(rf"{html_path}\cross_cmds\roll_performance_report.html"))
    table.to_html([final_html], output_path, task_name="Roll Performance Report")
    print(f"Roll Performance Report saved to {output_path}")
    send_email(send_to=["ltrindade"], subject="Roll Performance Report", body=[final_html])


if __name__ == "__main__":
    update_monitor_page()
