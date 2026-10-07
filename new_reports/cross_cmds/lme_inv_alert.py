import ecm.cmds.bbg as bbg
import ecm.cmds.table as table
from ecm.cmds._email import send_email
from ecm.cmds.cdr import today
from ecm.cmds.config import macro_group
from ecm.cmds.core.alerting.alert_func import z_score_alert_change
import pandas as pd
from dateutil.relativedelta import relativedelta

lme_canceled_warents_tickes = {
    "Copper": "LFCA Index",
    "Alluminium": "LFAH Index",
    "Nickel": "LNFNI Index",
    "Zinc": "NLFSN Index",
    "Lead": "NLFPB Index",
    "Tin": "LFTA Index"
}
send_to = macro_group


def get_data(ticker):
    """ get enough data for a 3 month lookback z-score calculation """
    sdate = today() - relativedelta(days=200)
    edate = today()
    data = bbg.bdh(ticker, "PX_LAST", sdate, edate)
    data = data.rename(columns={"PX_LAST": "value"})
    data.columns.name = None
    return data


def get_alert_email_table(df):
    df = df.rename(columns={"Value": "Last Px"})
    df = df[["Metal", "Ticker", "Last Px", "Change", "z_score", "alert", "z_high", "z_low"]]
    html_table = table.html_format(df, hide_cols=["alert", "z_high", "z_low", "z_score"], format_column={
        "Metal": {"width": "150px", "text-align": "center"},
        "Ticker": {"width": "100px", "text-align": "center"},
        "Last Px": {"format": "{:.2f}", "width": "100px", "text-align": "center"},
        "Change": {"width": "100px", "text-align": "center", "highlight": ["Change", "z_score", "z_high", "z_low"]},
    }, footer="Change in LME Canceled Warrants exceeding 2sd on a 3 month lookback")
    return html_table


def lme_inv_alert():
    alerts = pd.DataFrame()
    for metal, ticker in lme_canceled_warents_tickes.items():
        data = get_data(ticker)
        data = data.dropna()
        if len(data) < 30:
            continue
        alert_row = z_score_alert_change(data, threshold=2.0, days_over=180)
        alert_row = alert_row.rename(columns={"value": "Value"})
        alert_row["Change"] = data["value"].iloc[-1] - data["value"].iloc[-2]
        alert_row['Metal'] = metal
        alert_row['Ticker'] = ticker
        alert_row["z_high"] = 2.0
        alert_row["z_low"] = -2.0
        alerts = pd.concat([alerts, alert_row], ignore_index=True)
    if not alerts.empty:
        triggered_alerts = alerts[alerts['alert'] == 1].reset_index(drop=True)
        if not triggered_alerts.empty:
            email = ["LME Canceled Warrants Alerts Triggered"]
            email_table = get_alert_email_table(triggered_alerts)
            email.append(email_table)
            raise NotImplementedError("Missing mail arguments: IMG_5225 line 61")
        else:
            print("No alerts triggered.")


if __name__ == "__main__":
    lme_inv_alert()
