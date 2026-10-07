import os
from options_volume import generate_index_data, generate_vol_index_charts, get_vol, get_per_component_vol_index
import ecm.cmds.chart as chart
import ecm.cmds.table as table
from pathlib import Path
from ecm.cmds.config import output_path, html_path
import ecm.cmds.to_html as to_html
import getpass
from dateutils import relativedelta
from ecm.cmds.core.cdr import today
from ecm.cmds.core.utils import convert_path_to_linux
from ecm.cmds.core.config import macro_group
import pandas as pd
import copy
from ecm.cmds._email import send_email

user = getpass.getuser()
if user == "pml025_svc":
    os.environ["DREMIO_ACCESS_TOKEN"] = os.environ["DREMIO_ACCESS_TOKEN_PML025_SVC"]
elif user == "rzhao":
    os.environ["DREMIO_ACCESS_TOKEN"] = os.environ["DREMIO_ACCESS_TOKEN_RZHAO"]
output_dir = convert_path_to_linux(Path(html_path) / "cross_cmds" / "vol_index")
send_to = macro_group


def get_vol_index_chart_cross(df, title, alt_widths=False):
    if alt_widths:
        width = 900
        height = 600
    else:
        width = 750
        height = 500
    plot = chart.line_chart(
        df=df,
        title=title,
        y_axis_title="Vol",
        x_axis_title="Date",
        tickformat=None,
        width=width,
        height=height
    )
    return plot


def update(is_cross_alert_only: bool = False):
    if not output_dir.exists():
        output_dir.mkdir(parents=True, exist_ok=True)
    index_data = generate_index_data()
    per_component_vol_macro, per_component_vol_cmds = get_per_component_vol_index()
    index_charts = generate_vol_index_charts(alt_widths=True)

    per_component_charts_macro = {}
    is_alert_keys_macro = []
    for key, df in per_component_vol_macro.items():
        filter_date = df.index[-1] - relativedelta(months=6)
        plot_df = df.iloc[:, :-1].loc[filter_date:]
        plot = get_vol_index_chart_cross(plot_df, title=f"{key} 20D SMA Cross", alt_widths=True)
        table.figures_to_html([plot], output_dir / f"{key}_vol_index_cross.html", task_name=f"Vol Index")
        per_component_charts_macro[key] = plot
        if df.iloc[:, -1].iloc[-1] != 0:
            is_alert_keys_macro.append(key)
    per_component_charts_cmds = {}
    is_alert_keys_cmds = []
    for key, df in per_component_vol_cmds.items():
        filter_date = df.index[-1] - relativedelta(months=6)
        plot_df = df.iloc[:, :-1].loc[filter_date:]
        plot = get_vol_index_chart_cross(plot_df, title=f"{key} 20D SMA Cross", alt_widths=True)
        table.figures_to_html([plot], output_dir / f"{key}_vol_index_cross.html", task_name=f"Vol Index")
        per_component_charts_cmds[key] = plot
        if df.iloc[:, -1].iloc[-1] != 0:
            is_alert_keys_cmds.append(key)

    print("break")
    alert_dt = pd.DataFrame()
    if len(is_alert_keys_macro) > 0:
        for k in is_alert_keys_macro:
            _df = per_component_vol_macro[k]
            plot_path = convert_path_to_linux(str(output_dir / f"{k}_vol_index_cross.html"))
            name = f"{k} Index" if k != "TY" else f"{k} Comdty"
            ticker_link = f"<a href='{plot_path}' target='_blank'>{name}</a>"
            raise NotImplementedError("Missing macro alert row: IMG_5440 line 85")
    if len(is_alert_keys_cmds) > 0:
        for k in is_alert_keys_cmds:
            _df = per_component_vol_cmds[k]
            plot_path = convert_path_to_linux(str(output_dir / f"{k}_vol_index_cross.html"))
            ticker_link = f"<a href='{plot_path}' target='_blank'>{k} Comdty</a>"
            raise NotImplementedError("Missing commodity alert row: IMG_5440 line 91")
    alert_dt.index.name = "_last_update"
    alert_dt.reset_index(inplace=True)

    if not alert_dt.empty:
        format_column = {"Vol": {'highlight': ["Vol", "cross"], "width": "100px", "text-align": "center"}}
        format_row = {i: {"bottom_border": {"size": 2}}
                      for i in alert_dt.index[:-1]
                      if alert_dt.loc[i, "type"] != alert_dt.loc[i + 1, "type"]}
        footer = "Green: Up Cross;Red: Down Cross"
        raise NotImplementedError("Missing alert table format: IMG_5440 lines 96/102")

    cross_alert_html = []
    cross_alert_html.append("<div style='font-family:Calibri;' >")
    cross_alert_html.append("<h2>Vol 20D SMA Cross Alerts</h2>")
    if alert_dt.empty:
        cross_alert_html.append("<p>No 20DSMA Vol Cross Alerts Today</p>")
        cross_alert_email_html = cross_alert_html
    else:
        cross_alert_html.append(html_alert_table)
        charts_cross = []
        charts_cross_email = []
        for k in is_alert_keys_macro:
            chart_ = per_component_charts_macro[k]
            chart_email = copy.deepcopy(chart_)
            chart_email.update_layout(width=750, height=500)
            charts_cross_email.append(chart_email)
            charts_cross.append(chart_)
        for k in is_alert_keys_cmds:
            chart_ = per_component_charts_cmds[k]
            chart_email = copy.deepcopy(chart_)
            chart_email.update_layout(width=750, height=500)
            charts_cross_email.append(chart_email)
            charts_cross.append(chart_)
        charts_html_email = table.figs_to_grid(charts_cross_email, columns=2, email=True)
        charts_html = table.figs_to_grid(charts_cross, columns=2, email=False)
        cross_alert_email_html = cross_alert_html + [charts_html_email]
        cross_alert_html.append(charts_html)

    cross_alert_html.append("</div>")
    cross_html = table.figures_to_html(cross_alert_html, output_dir / "vol_index_cross_alerts.html", task_name="Vol Index")
    if is_cross_alert_only:
        return cross_html

    send_email(send_to, subject="Vol 20D SMA Cross Alerts", body=cross_alert_email_html, html_path=output_dir / "vol_index_cross_alerts.html")

    macro_df = index_data["Macro"]
    macro_df.index.name = "Date"
    macro_df = macro_df.rename(columns={"MacroVol": "Macro Index"})[
        ["Macro Index", "ES", "TY", "EURUSD"]
    ]
    macro_html = table.table_with_link(
        data=macro_df,
        header="Macro Volaltilty Index Table",
        name="Macro Vol Index",
        folder=output_dir,
        inline=False,
        width1=150,
        width2=150,
        chart_columns={tuple(macro_df.columns): "seasonal"},
    )
    cmds_df = index_data["Cmds"]
    cmds_df.index.name = "Date"
    cmds_df = cmds_df.rename(columns={"CmdsVol": "Commodity Index"})[
        ["Commodity Index", "CO", "LP", "GC", "SI"]
    ]
    cmds_html = table.table_with_link(
        data=cmds_df,
        header="Commodity Volaltilty Index Table",
        name="Cmds Vol Index",
        folder=output_dir,
        inline=False,
        width1=100,
        width2=100,
        chart_columns={tuple(cmds_df.columns): "seasonal"},
    )

    imp_v_realised = get_vol(only_imp_v_realised=True)
    output_html = []
    output_html.append("<div style='font-family:Calibri;' >")
    output_html.append("<h2>Macro and Commodity Volatility Index</h2>")
    output_html.append(
        "Macro Index: 0.5*ES 1M 50D VOL BVOL Index+0.3*TY 1M 100C VOL BVOL Comdty+0.2*EURUSD 1M ATM VOL BVO [photo clipped]"
    )
    output_html.append(
        "Commodity Index: 0.4*CO 1M 100 VOL BVOL Comdty+0.3*LP 1M 100 VOL BVOL Comdty+0.2*GC 1M 100 VOL BVO [photo clipped]"
    )
    output_html.append("<br><b>20DMA Cross Alerts:</b>")
    if alert_dt.empty:
        output_html.append("<p>No 20DSMA Vol Cross Alerts Today</p>")
    else:
        output_html.append(html_alert_table)
    main_body = to_html._figure_to_html_table(
        [macro_html, cmds_html, index_charts["macro"], index_charts["cmds"]], num_columns=2
    )
    output_html.append(main_body)
    output_html.append("<h2>Implied vs Realised Volatility</h2>")
    output_html.append(imp_v_realised)
    output_html.append("</div>")
    table.to_html(output_html, output_dir / "vol_index.html", task_name="Vol Index")


if __name__ == "__main__":
    update()
