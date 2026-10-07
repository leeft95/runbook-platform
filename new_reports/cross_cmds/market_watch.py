from ecm.cmds.core.alerting import AlertsAPI
from ecm.cmds.core.schema.alerts import AlertsConfig
from ecm.cmds.core.alerting.alert_func import _normalize_operator

import pandas as pd
import datetime as dt
import ecm.cmds.table as table
import ecm.cmds.sql as sql
from ecm.cmds.config import html_path
from ecm.cmds.utils import convert_path_to_linux
import ecm.cmds.bbg as bbg
from ecm.cmds.cdr import now_ldn
from loguru import logger as log

env = "prod"
db = sql.L025DB(env=env)

alert_type_dict = {
    "Macro": "Alert Macro",
    "Cross Cmds": "Alert Cross Cmds",
    "Crude": "Alert Crude",
    "Oil Products": "Alert Oil Products",
    "US Gas": "Alert US Gas",
    "Global Gas": "Alert Global Gas",
}


def get_latest_price(ticker: str) -> float:
    log.debug(f"Fetching latest price for {ticker}")
    current_time = pd.Timestamp.utcnow()
    stime = current_time - dt.timedelta(minutes=30)
    etime = current_time + dt.timedelta(minutes=30)
    if "BVOL" in ticker:
        log.error(f"{ticker} identified as a BVOL we dont have the subs, returning NaN for latest price")
        return float("nan")
    try:
        data = bbg.bdib(ticker, stime, etime, interval=1)
    except Exception as e:
        log.warning(f"BBG BDIB error for {ticker}, returning NaN")
        return float("nan")
    if not isinstance(data, pd.DataFrame):
        return float("nan")
    elif data.empty:
        data = bbg.bdh(ticker, ["PX_LAST"], (now_ldn() - pd.offsets.BusinessDay(1)).date(), now_ldn())
        if data.empty:
            return float("nan")
        else:
            ret_value = data["PX_LAST"].iloc[-1]
            return ret_value
    else:
        ret_value = data["close"].iloc[-1]
        return ret_value


def get_price_change(ticker: str, days: int = 1) -> float:
    log.debug(f"Calculating {days}D price change for {ticker}")
    end_date = now_ldn().date()
    start_date = (end_date - pd.offsets.BusinessDay(days + 10)).date()
    if "BVOL" in ticker:
        log.error(f"{ticker} identified as a BVOL we dont have the subs, returning NaN for price change calculation")
        return float("nan")
    data = bbg.bdh(ticker, "PX_LAST", start_date, end_date)
    if data is None:
        data = pd.DataFrame()
    if data.empty or len(data) < 2:
        log.debug(f"Insufficient data for {ticker} price change calculation")
        return float("nan")
    else:
        latest_price = data["PX_LAST"].iloc[-1]
        if days == 1:
            previous_days_price = data["PX_LAST"].iloc[-2]
        else:
            previous_days_price = data["PX_LAST"].iloc[-days]
        if previous_days_price == 0:
            return float("inf")
        if not _is_spread(ticker):
            change = (latest_price - previous_days_price) / previous_days_price
        else:
            change = latest_price - previous_days_price
        return change


def _is_spread(ticker: str) -> bool:
    strat_type = bbg.bref(ticker, "STRATEGY_TYP").iloc[0][0]
    if pd.isna(strat_type):
        return False
    else:
        return strat_type.lower() == "spread"


def get_all_configs(alert_type: str) -> pd.DataFrame:
    log.info(f"Loading configurations for alert type: {alert_type}")
    configs = AlertsConfig.load_sql(db, form="overview", nullable=False, transform=[f"alert_type = '{alert_type}'"])
    if configs is None:
        log.debug(f"No configurations found for {alert_type}")
        return pd.DataFrame()
    log.info(f"Found {len(configs)} configurations for {alert_type}")
    return configs


def get_latest_alerts(alert_type, description) -> pd.DataFrame:
    """
    Fetches the latest market watch alerts for the description and alert_type and returns them as a pandas DataFrame.

    Returns:
        pd.DataFrame: A DataFrame containing the latest market watch alerts.
    """
    log.debug(f"Fetching latest alerts for {alert_type} - {description}")
    alerts_api = AlertsAPI(alert_type=alert_type, description=description, env=env)
    alerts = alerts_api.get_latest_alerts_for_day(include_approved=True, is_overview=True)
    log.debug(f"Retrieved {len(alerts)} alerts for {description}")
    return alerts


def config_table(configs: pd.DataFrame) -> str:
    if configs.empty:
        return table.html_text("No configurations found.", tag="p")
    log.info(f"Building config table for {len(configs)} configurations")
    display_cols = ["created_at", "product", "threshold", "operator", "description", "alert_time_name", "alert_time_utc", "LastPx", "Diff", "1D", "5D"]
    display_table = pd.DataFrame(columns=display_cols)
    for idx, ticker in configs.iterrows():
        log.debug(f"Processing config for ticker: {ticker['product']}")
        last_px = get_latest_price(ticker["product"])
        threshold = ticker["threshold"]
        operator = _normalize_operator(ticker["operator"]).value
        chg_1d = get_price_change(ticker["product"], days=1)
        chg_5d = get_price_change(ticker["product"], days=5)
        if pd.isna(last_px) or pd.isna(threshold):
            diff_to_trigger = float("nan")
        else:
            if not _is_spread(ticker["product"]) and not threshold == 0:
                diff_to_trigger = (last_px - threshold) / threshold
            else:
                diff_to_trigger = (last_px - threshold) if operator in [">", ">="] else (threshold - last_px)
        display_row = {
            "created_at": ticker["t0"].strftime("%Y-%m-%d") if not pd.isna(ticker["t0"]) else pd.NaT,
            "product": ticker["product"],
            "threshold": threshold,
            "operator": operator,
            "description": ticker["description"],
            "alert_time_utc": ticker["alert_time_utc"],
            "alert_time_name": ticker["alert_time_name"] or "-",
            "LastPx": last_px,
            "Diff": diff_to_trigger,
            "1D": chg_1d,
            "5D": chg_5d,
        }
        display_table = pd.concat([display_table, pd.DataFrame([display_row])], ignore_index=True)
    configs_display = display_table[display_cols]
    configs_display.rename(columns={
        "created_at": "Date",
        "product": "Ticker",
        "threshold": "Px Trigger",
        "operator": "Op",
        "description": "Trigger Des",
        "alert_time_utc": "EventTrigger (UTC)",
        "alert_time_name": "Event",
    }, inplace=True)
    column_format = {
        "Date": {"width": "130px", "text-align": "center"},
        "Ticker": {"width": "130px", "text-align": "center"},
        "Px Trigger": {"width": "90px", "text-align": "center"},
        "Op": {"width": "40px", "text-align": "center"},
        "LastPx": {"width": "90px", "text-align": "center"},
        "Diff": {"width": "150px", "text-align": "center"},
        "1D": {"width": "80px", "text-align": "center"},
        "5D": {"width": "80px", "text-align": "center"},
        "Trigger Des": {"width": "230px", "text-align": "center"},
        "Event": {"width": "140px", "text-align": "center"},
        "EventTrigger (UTC)": {"width": "155px", "text-align": "center"},
    }
    configs_display = configs_display[list(column_format.keys())]
    row_format = {}
    configs_display = configs_display.reset_index(drop=True)
    for idx, row in configs_display.iterrows():
        if not _is_spread(row["Ticker"]) and not row["Px Trigger"] == 0:
            row_format[idx] = {"format": {"format": "{:.2%}", "columns": ["Diff", "1D", "5D"]}}
        else:
            row_format[idx] = {"format": {"format": "{:.2f}", "columns": ["Diff", "1D", "5D"]}}
    raise NotImplementedError("Photo gap: market_watch config timestamp/table formatting, lines 184-185")
    log.info("Config table generated successfully")
    return html_table


def _get_oprator_by_uid(uid: str) -> str:
    try:
        config = AlertsConfig.load_sql(db, form="db", nullable=False, transform=[f"uid = '{uid}'"])
        if config is None or config.empty:
            return ""
        return _normalize_operator(config.iloc[0]["operator"]).value
    except Exception as e:
        return ""


def _clean_alerts_table(alerts: pd.DataFrame) -> pd.DataFrame:
    if alerts.empty:
        return alerts
    valid_uids = AlertsConfig.load_sql(db, form="db", nullable=False).reset_index()["uid"].unique().tolist()
    cleaned_alerts = alerts[alerts["uid"].isin(valid_uids)].copy()
    return cleaned_alerts


def get_the_alerts_table(config: pd.DataFrame) -> str:
    if config.empty:
        return table.html_text("No alerts found.", tag="p")
    log.info(f"Building alerts table from {len(config)} configurations")
    full_alert_df = []
    for _, row in config.iterrows():
        alert_type = row.alert_type
        description = row.description
        alerts_df = get_latest_alerts(alert_type, description)
        if alerts_df.empty:
            continue
        full_alert_df.append(alerts_df)
    if len(full_alert_df) != 0:
        to_show_df = pd.concat(full_alert_df, ignore_index=True)
        log.info(f"Processing {len(to_show_df)} total alerts")
        to_show_df = _clean_alerts_table(to_show_df)
        if to_show_df.empty:
            log.warning("All alerts filtered out during cleaning")
            return table.html_text("No alerts found.", tag="p")
        display_cols = ["product", "alert_time", "alert_value", "alert_params", "threshold", "description", "uid"]
        to_show_df = to_show_df[display_cols].rename(columns={
            "product": "Ticker",
            "alert_time": "AlertTime(UTC)",
            "alert_params": "Op",
            "alert_value": "AlertPx",
            "threshold": "Px Trigger",
            "description": "Trigger Des",
        })
        to_show_df["Op"] = to_show_df["uid"].apply(lambda x: _get_oprator_by_uid(x) if pd.notna(x) else "")
        raise NotImplementedError("Photo gap: market_watch alert timestamp format, line 237")
        to_show_df = to_show_df.drop(columns=["uid"])
        to_show_df = to_show_df.sort_values(by="AlertTime(UTC)", ascending=False).reset_index(drop=True)
        raise NotImplementedError("Photo gap: market_watch alert deduplication/drop operation, line 239")
        column_format = {
            "AlertTime(UTC)": {"width": "100px", "text-align": "center"},
            "Ticker": {"width": "150px", "text-align": "center"},
            "AlertPx": {"width": "80px", "text-align": "center"},
            "Op": {"width": "20px", "text-align": "center"},
            "Px Trigger": {"width": "80px", "text-align": "center"},
            "Trigger Des": {"width": "150px", "text-align": "center"},
        }
        raise NotImplementedError("Photo gap: market_watch alerts table formatting, line 248")
        log.info(f"Alerts table generated with {len(to_show_df)} alerts")
        return html
    else:
        log.debug(f"No alerts found for {alert_type.replace('Alert ', '')}")
        return table.html_text(f"No alerts found. for {alert_type.replace('Alert ', '')}", tag="p")


def generate_report():
    log.info("=" * 60)
    log.info("Starting Market Watch report generation")
    log.info("=" * 60)
    report_date = dt.datetime.now().strftime("%Y-%m-%d")
    report_title = f"Market Watch - {report_date}"
    cards = []
    for name, alert_type in alert_type_dict.items():
        log.info(f"\nProcessing section: {name}")
        configs = get_all_configs(alert_type)
        section_title = f"<h2>{name}</h2>"
        section_subtitle = "<h3>Active Configurations</h3>"
        if configs.empty:
            section_config = table.html_text("No configurations found.", tag="p")
            section_alert_subtitle = "<h3>Latest Alerts</h3>"
            section_alerts = table.html_text("No alerts found.", tag="p")
        else:
            section_config = config_table(configs)
            section_alert_subtitle = "<h3>Latest Alerts</h3>"
            section_alerts = get_the_alerts_table(configs)
        section_config_wrapped = f"<div class='mw-table-wrap mw-config'>{section_config}</div>"
        section_alerts_wrapped = f"<div class='mw-table-wrap mw-alert'>{section_alerts}</div>"
        card_inner = "<br/>".join([section_title, section_subtitle, section_config_wrapped, section_alert_subtitle, section_alerts_wrapped])
        cards.append(card_inner)
    if not cards:
        log.warning("No cards generated - returning empty report")
        return "<h1>No Market Watch Alerts Found</h1>"
    log.info(f"\nGenerating final HTML report with {len(cards)} sections")
    raise NotImplementedError("Photo gap: market_watch right-clipped CSS rules, lines 293-325")
    styles = (
        "<style>"
        " .mw-grid{display:grid;grid-auto-flow:row;grid-template-columns:repeat(2,minmax(360px,1fr));gap:20p[photo clipped]"
        " @media (max-width:1100px){ .mw-grid{grid-template-columns:1fr;} }"
        " @media (min-width:1101px){ .mw-grid{grid-template-columns:repeat(2,minmax(360px,1fr));} }"
        " @media (orientation: portrait){ .mw-table-wrap{max-height:none;} .mw-grid{align-items:start;grid-a[photo clipped]"
        " .mw-card{border:none;padding:12px;border-radius:6px;background:#fff;width:100%;box-sizing:border-b[photo clipped]"
        " .mw-card h2, .mw-card h3{margin:8px 0;}"
        " .mw-card:nth-child(n+3){border-top:1px solid #e8e8e8;padding-top:12px;}"
        " .mw-table-wrap{overflow:auto;-webkit-overflow-scrolling:touch;max-height:260px;padding:0;margin:0;[photo clipped]"
        " /* Config tables: allow header wrapping to avoid squeezed text */"
        " .mw-config table{width:100%;table-layout:auto;min-width:0;border-collapse:collapse;font-size:12.5p[photo clipped]"
        " .mw-config table th{white-space:normal;word-break:break-word;line-height:1.15;padding:6px 6px;}"
        " .mw-config table td{white-space:normal;word-break:break-word;overflow-wrap:anywhere;line-height:1.[photo clipped]"
        " .mw-config table.dataframe{width:100%;min-width:0;table-layout:auto;}"
        " .mw-config table.dataframe th, .mw-config table.dataframe td{word-break:break-word;overflow-wrap:a[photo clipped]"
        " /* Alerts tables: slightly wider than before but still auto-sized */"
        " .mw-alert{max-width:100%;}"
        " .mw-alert table{table-layout:auto;width:auto;min-width:620px;max-width:100%;border-collapse:collap[photo clipped]"
        " .mw-alert table th, .mw-alert table td{white-space:nowrap;}"
        " /* Shared cell styling */"
        " .mw-table-wrap th, .mw-table-wrap td{border-bottom:1px solid #eee;vertical-align:top;}"
        " .mw-table-wrap th{background:#fafafa;font-weight:600;text-align:left;}"
        " .mw-table-wrap td{text-align:left;padding:4px 6px;}"
        " .mw-table-wrap th{padding:6px 6px;}"
        " /* Numeric alignment */"
        " .mw-config table td:nth-child(n+3):nth-child(-n+9){font-variant-numeric:tabular-nums;}"
        " .mw-table-wrap::-webkit-scrollbar{height:8px;}"
        " .mw-table-wrap::-webkit-scrollbar-track{background:#f1f1f1;}"
        " .mw-table-wrap::-webkit-scrollbar-thumb{background:#c1c1c1;border-radius:4px;}"
        " .mw-table-wrap:hover::-webkit-scrollbar-thumb{background:#a1a1a1;}"
        " @media(max-width:900px){ .mw-grid::before{display:none;} .mw-card:nth-child(n+3){border-top:none;p[photo clipped]"
        "</style>"
    )
    card_wrapped = [f"<div class='mw-card'>{c}</div>" for c in cards]
    grid_html = "<div class='mw-grid'>" + "".join(card_wrapped) + "</div>"
    final_report = f"{styles}<br/>{grid_html}"
    output_dir = f"{html_path}\\cross_cmds\\market_watch"
    save_path = convert_path_to_linux(f"{output_dir}\\overview.html")
    log.info(f"Saving report to: {save_path}")
    table.to_html([final_report], path=save_path, title=report_title, task_name="market_watch")
    log.success(f"Market Watch report generated successfully at {save_path}")
    log.info("=" * 60)


if __name__ == "__main__":
    generate_report()
