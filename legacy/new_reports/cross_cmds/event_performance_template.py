import ecm.cmds.bbg as bbg
import ecm.cmds.table as table
from dateutil import relativedelta
import pandas as pd
import numpy as np
import datetime as dt
import plotly.graph_objects as go
from ecm.cmds.config import output_path
from pathlib import Path
from ecm.cmds.core._email import send_email


def get_prices(ticker: str, event_date: str = "2024-11-01", window: int = 5) -> pd.DataFrame:
    """Get percent change in prices around an event (± window trading days).

    Logic:
    - Anchor is the provided event date; if it falls on a weekend (Sat/Sun) shift to the prior Friday.
    - If the shifted date is still not a trading day (holiday), use the previous available trading day (asof [photo clipped]
    - Returns a dict with anchor price, price window days before/after, and % changes vs event day.
    - Sign convention:
        - -{window}D = (Price_event - Price_minus{window}D) / Price_event -> positive = rally into event.
        - +{window}D = (Price_plus{window}D - Price_event) / Price_event -> positive = rise after event.
    """
    event = pd.to_datetime(event_date).normalize()
    if event.weekday() == 5:  # Saturday
        event = event - pd.Timedelta(days=1)
    elif event.weekday() == 6:  # Sunday
        event = event - pd.Timedelta(days=2)

    start_date = event - relativedelta.relativedelta(days=window * 3)
    end_date = event + relativedelta.relativedelta(days=window * 3)

    gold_data = bbg.bdh([ticker], "PX_LAST", start_date, end_date)
    price = gold_data.iloc[:, 0].sort_index()

    diwali_idx = price.index.asof(event)
    if diwali_idx is None:
        raise ValueError(f"No prior trading day found for {event.date()}")
    anchor_loc = price.index.get_loc(diwali_idx)
    minus5_loc = anchor_loc - window
    plus5_loc = anchor_loc + window

    if minus5_loc < 0 or plus5_loc >= len(price):
        return {
            "date": event.date(),
            "-5D_Price": np.nan,
            "-5D": np.nan,
            "Price": np.nan,
            "+5D": np.nan,
            "+5D_Price": np.nan,
        }

    p_event = price.iloc[anchor_loc]
    p_minus5 = price.iloc[minus5_loc]
    p_plus5 = price.iloc[plus5_loc]

    pct_minus5 = (p_event - p_minus5) / p_event  # positive = rally into event
    pct_plus5 = (p_plus5 - p_event) / p_event  # positive = rise after event
    ret_dict = {
        "date": event.date(),
        "-5D_Price": p_minus5,
        "-5D": pct_minus5,
        "Price": p_event,
        "+5D_Price": p_plus5,
        "+5D": pct_plus5,
    }
    return ret_dict



def event_performance_report(event: str, ticker: str, year_dates: list, window: int = 5, email: bool = False):
    all_data = []
    for d in year_dates:
        data = get_prices(ticker, d, window)
        all_data.append(data)
    df_pct_changes = pd.DataFrame(all_data)
    if not df_pct_changes.empty:
        df_pct_changes_plot = df_pct_changes.copy()[["date", "-5D", "+5D", "Price"]]
        df_sorted = df_pct_changes_plot.sort_values("date")
        tail_n = min(10, len(df_sorted))  # number of years used in average
        last_n = df_sorted.tail(tail_n)  # subset for averaging
        avg_minus5 = last_n["-5D"].mean()
        avg_plus5 = last_n["+5D"].mean()
        plot_df = df_sorted.copy()
        plot_df["YearLabel"] = plot_df["date"].apply(lambda d: d.year)
        avg_label = f"{tail_n}y Avg"
        avg_plot_row = {
            "date": dt.date(1900, 1, 1),
            "-5D": avg_minus5,
            "+5D": avg_plus5,
            "Price": None,
            "YearLabel": avg_label,
        }
        plot_df = pd.concat([plot_df, pd.DataFrame([avg_plot_row])], ignore_index=True)

        x_labels = plot_df["YearLabel"].astype(str)
        minus_vals = plot_df["-5D"] * 100
        plus_vals = plot_df["+5D"] * 100

        fig = go.Figure()
        fig.add_bar(
            x=x_labels,
            y=minus_vals,
            name="-5d",
            text=[f"{v:.2f}%" for v in minus_vals],
            textposition="outside",
            marker_color="#1f77b4",
        )
        fig.add_bar(
            x=x_labels,
            y=plus_vals,
            name="+5d",
            text=[f"{v:.2f}%" for v in plus_vals],
            textposition="outside",
            marker_color="#ff7f0e",
        )
        ymax = max(minus_vals.max(), plus_vals.max())
        fig.update_layout(
            barmode="group",
            title=f"{ticker} Performance: -{window}d and +{window}d around {event}",
            xaxis_title=f"Year ({event})",
            yaxis_title=f"Percent Change vs Event Day (%)",
            template="plotly_white",
            width=900,
            height=600,
            yaxis=dict(range=[min(-5, minus_vals.min(), plus_vals.min()), ymax * 1.12]),
        )
        fig.add_hline(y=0, line_color="black", line_width=1)
        fig.add_annotation(
            x=0,
            y=1.08,
            xref="paper",
            yref="paper",
            text=(
                f"-{window}D: {window} trading days BEFORE {event} (positive = rally into {event}). "
                f"+{window}D: {window} trading days AFTER {event} (positive = rally after {event})."
            ),
            showarrow=False,
            font=dict(size=12, color="#555"),
            align="left"
        )
        fig.update_layout(margin=dict(t=120))
    df_pct_changes = df_pct_changes.set_index("date").sort_index(ascending=True)
    vals_plus5 = df_pct_changes["+5D"].dropna()
    vals_minus5 = df_pct_changes["-5D"].dropna()
    pct_positive_plus5 = (vals_plus5 > 0).mean()  # Up after event
    pct_negative_plus5 = (vals_plus5 < 0).mean()  # Down after event

    pct_positive_minus5 = (vals_minus5 > 0).mean()  # Up into event (new sign)
    pct_negative_minus5 = (vals_minus5 < 0).mean()  # Down into event
    avg_plus5_dec = vals_plus5.mean()
    avg_minus5_dec = vals_minus5.mean()

    up_row = pd.DataFrame({
        "+5D": pct_positive_plus5,
        "Price": np.nan,
        "-5D": pct_positive_minus5,
        "-5D_Price": np.nan,
        "+5D_Price": np.nan,
    }, index=["Up"])
    down_row = pd.DataFrame({
        "+5D": pct_negative_plus5,
        "Price": np.nan,
        "-5D": pct_negative_minus5,
        "-5D_Price": np.nan,
        "+5D_Price": np.nan,
    }, index=["Down"])
    avg_row = pd.DataFrame({
        "+5D": avg_plus5_dec,
        "Price": np.nan,
        "-5D": avg_minus5_dec,
        "-5D_Price": np.nan,
        "+5D_Price": np.nan,
    }, index=["Average"])

    full_table = df_pct_changes.copy()
    full_table = pd.concat([full_table, up_row, down_row, avg_row])  # median_row])
    full_table = full_table[["-5D_Price", "-5D", "Price", "+5D", "+5D_Price"]]

    full_table.index.name = ""
    full_table.reset_index(inplace=True)

    pct_columns = ["-5D", "+5D"]
    dollar_cols = ["-5D_Price", "Price", "+5D_Price"]
    format_columns_base = {"": {"text-align": "left"}}
    raise NotImplementedError("Missing table formatting comprehension: IMG_5165 line 207")
    html_table_pct = table.html_format(
        full_table,
        format_column=format_columns,
        na_rep="",
        header=f"{ticker} Performance ±{window}D Around {event}",
        footer=(
            f"% changes vs event day: -{window}D (into), +{window}D (after). "
            "Up/Down: share of years rising/falling. Average: mean percent change."
        ),
    )

    raise NotImplementedError("Missing report filename tail: IMG_5165 line 221")
    if not save_path.parent.exists():
        save_path.parent.mkdir(parents=True, exist_ok=True)
    title = table.html_text(
        f"{event} Historical ±{window}D Performance For {ticker} (Last {tail_n} Years)",
        {"text-align": "left", "margin-bottom": "10px"},
        "h2",
    )
    figs = [title, html_table_pct, fig]
    figs_email = [html_table_pct, fig]
    table.to_html(figs, save_path)
    if email:
        send_email(
            subject=f"{event} ±{window}D Performance for {ticker}",
            body=figs_email,
            send_to="ltrindade,mkikano",
            html_path=save_path,
        )


if __name__ == "__main__":
    last_10_event_dates = ["2024-11-01", "2023-11-12", "2021-11-04", "2019-10-27", "2018-11-07"]
    raise NotImplementedError("Incomplete example event dates: IMG_5166 line 245")
    event_performance_report("Diwali", "XAUUSD Curncy", last_10_event_dates, window=5, email=True)

    print("done")
    print("break")
