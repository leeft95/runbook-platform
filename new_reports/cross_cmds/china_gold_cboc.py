from ecm.atom.services import fetch_series
import ecm.cmds.table as table
import ecm.cmds.chart as chart
import ecm.cmds.bbg as bbg
from ecm.cmds.cdr import today
import datetime as dt
import pandas as pd
from ecm.cmds.config import output_path


def get_row(raw_data, row_name):
    china_holding_36m_data = raw_data.iloc[-24:].std()
    china_holding_chg_1m = raw_data.iloc[-1] - raw_data.iloc[-2]
    china_holding_chg_3m = raw_data.iloc[-1] - raw_data.iloc[-3]
    china_holding_chg_6m = raw_data.iloc[-1] - raw_data.iloc[-6]
    china_holding_chg_ytd = raw_data.iloc[-1] - raw_data.iloc[-(dt.datetime.now().month)]
    china_holding_chg_yoy = raw_data.iloc[-1] - raw_data.iloc[-12]
    china_holding_chg_1m_z = china_holding_chg_1m / china_holding_36m_data
    china_holding_chg_3m_z = china_holding_chg_3m / china_holding_36m_data
    china_holding_chg_data = pd.DataFrame(
        {
            row_name: [
                raw_data.iloc[-1],
                china_holding_chg_1m,
                china_holding_chg_3m,
                china_holding_chg_6m,
                china_holding_chg_ytd,
                china_holding_chg_yoy,
                china_holding_chg_1m_z,
                china_holding_chg_3m_z,
                1.5,
                -1.5,
                raw_data.index[-1],
            ],
        },
        index=[
            "Holdings($M)",
            "1M",
            "3M",
            "6M",
            "YTD",
            "YoY",
            "Z-score 1M",
            "Z-score 3M",
            "_max",
            "_min",
            "_last_update",
        ],
    ).T
    china_holding_chg_data.index.name = ""
    china_holding_chg_data.reset_index(inplace=True)
    return china_holding_chg_data


def update(data_only=False):
    save_path = f"{output_path}\\htmls\\cross_cmds\\central_bank_gold_holdings.html"
    ticker_ccy = "XAU Curncy"
    start_date = dt.datetime(2015, 1, 1)
    end_date = today()
    px_metal = bbg.bdh(ticker=[ticker_ccy], fields=["PX_LAST"], sdate=start_date, edate=end_date)
    china_holding_bbg = bbg.bdh(
        "CNGFGOLD Index", ["PX_LAST"], sdate=start_date, edate=today()
    )  # in millions troy oz
    china_holding_bbg = (
        china_holding_bbg * px_metal.iloc[-1].values[-1]
    )  # in millions $ per troy oz
    bbg_start = china_holding_bbg.index[0]
    new_idx = pd.date_range(
        start=dt.datetime(bbg_start.year, 1, 1), periods=len(china_holding_bbg), freq="MS"
    )
    china_holding_bbg.index = new_idx
    china_holding = fetch_series("UKTI CN", "GOLD", start=start_date, end=today()).cumsum()  # in kg of gold
    china_holding = china_holding.reindex(china_holding_bbg.index)
    troy_oz_to_kg = 32.1507
    china_holding = china_holding * troy_oz_to_kg  # convert to troy oz
    china_holding = china_holding * px_metal.iloc[-1].values[-1] * 1e-6  # millions $ per troy oz
    china_holding_chg = china_holding.diff()
    china_holding_chg = china_holding_chg.to_frame("UKTI CN|GOLD Monthly Delta")
    total = china_holding.reindex(china_holding_bbg.index) + china_holding_bbg["PX_LAST"]
    row_ukti = get_row(china_holding, "UKTI\u00b9")
    row_bbg = get_row(china_holding_bbg["PX_LAST"], "PBOC Offical BBG")
    row_total = get_row(total, "Total")
    china_holding_chg_data = pd.concat([row_ukti, row_bbg, row_total], axis=0, ignore_index=True)
    if data_only:
        return total
    column_format = {
        "Holdings($M)": {"width": "100px", "text-align": "center", "format": "{:,.0f}"},
        "1M": {
            "width": "100px",
            "text-align": "center",
        },
        "3M": {"width": "100px", "text-align": "center"},
        "6M": {"width": "100px", "text-align": "center"},
        "YTD": {"width": "100px", "text-align": "center"},
        "YoY": {"width": "100px", "text-align": "center"},
        "Z-score 1M": {
            "width": "100px",
            "text-align": "center",
            "highlight": ["Z-score 1M", "_max", "_min"],
        },
        "Z-score 3M": {
            "width": "100px",
            "text-align": "center",
            "highlight": ["Z-score 3M", "_max", "_min"],
        },
    }
    html_table = table.html_format(
        china_holding_chg_data,
        header="Central Bank Gold Holdings",
        format_column=column_format,
        hide_cols=["_max", "_min", "_last_update"],
        precision=2,
        show_date=True,
    )
    fig_china_total = chart.line_chart(
        df=total.to_frame("BBG+UKTI"),
        data_p1y2=total.diff().to_frame("BBG+UKTI Monthly Delta"),
        secondary_y=True,
        title="PBOC Gold Holdings",
        y_axis_title="Gold Holdings (M$/troy oz)",
        p1y2_axis_title="Monthly Change (M$/troy oz)",
        x_axis_title="Date",
        tickformat=None,
        highlight_dict={
            "BBG+UKTI": {"color": "black", "width": 2},
            "BBG+UKTI Monthly Delta": {"mode": "bars"},
        },
        height=500,
    )
    fig_china_total.update_traces(opacity=0.6, selector=dict(type="bar"))
    fig_china_total.update_yaxes(
        range=total.diff()
        .quantile([0.01, 0.99])
        .values,  # china repoted a lot of gold at once in 2015
        secondary_y=True,
    )
    fig_china = chart.line_chart(
        df=china_holding.to_frame(),
        data_p1y2=china_holding_chg,
        secondary_y=True,
        title="UKTI China Gold Holdings\u00b9",
        y_axis_title="Gold Holdings (M$/troy oz)",
        p1y2_axis_title="Monthly Change (M$/troy oz)",
        x_axis_title="Date",
        tickformat=None,
        highlight_dict={
            "UKTI CN|GOLD": {"color": "black", "width": 2},
            "UKTI CN|GOLD Monthly Delta": {"mode": "bars"},
        },
        height=500,
    )
    fig_china.update_traces(opacity=0.6, selector=dict(type="bar"))
    fig_china_list = [
        [fig_china_total, fig_china],
        "<p style='font-family:Calibri;font-size:10pt'>\u00b9Comes from UK export data of a certain size of [photo clipped]",
    ]
    figs_out = [html_table] + fig_china_list
    table.to_html(figs_out, save_path, task_name="Central Bank Gold Holdings")


if __name__ == "__main__":
    update()
    print("China Gold CBoC data updated successfully.")
