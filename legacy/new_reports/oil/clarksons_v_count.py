from ecm.cmds.sql import engine, read_sql
from itertools import product
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
import plotly.express as px
import ecm.cmds.table as table
from ecm.cmds.config import html_path


def _missing_photo_text(lines):
    raise NotImplementedError(f"Transcription gap in clarksons_v_count.py, photographed lines {lines}")


def chart_grid_by_decade(df, x_axis, col_values, cols=4):
    metrics = col_values
    decades = ["1st", "2nd", "3rd"]
    df[x_axis] = pd.to_datetime(df[x_axis])
    df["decade_of_month"] = pd.Categorical(
        df["decade_of_month"], categories=decades, ordered=True)
    df = df.sort_values([x_axis, "decade_of_month"])
    rows = (len(metrics) + cols - 1) // cols
    fig = make_subplots(rows=rows, cols=cols, shared_xaxes=False, subplot_titles=metrics)
    palette = px.colors.qualitative.Set1
    decades = ["1st", "2nd", "3rd"]
    color_map = dict(zip(decades, palette[:len(decades)]))
    for i, metric in enumerate(metrics):
        r = i // cols + 1
        c = i % cols + 1
        for decade in ["1st", "2nd", "3rd"]:
            d = df[df["decade_of_month"] == decade]
            fig.add_trace(
                go.Bar(x=d[x_axis], y=d[metric], name=decade, legendgroup=decade,
                       showlegend=(i == 0), marker_color=color_map[decade]), row=r, col=c)
    fig.update_layout(barmode="stack", height=350 * rows, width=400 * cols,
                      title="Clarksons V-count by decade", template="simple_white")
    fig.update_xaxes(tickformat="%b-%y", matches="x"  # 🔑 explicitly force sync (robust)
                     )
    return fig


def chart_grid(df, order_level_row, order_level_cols):
    lvl1 = order_level_row  # col_level_1
    lvl2 = order_level_cols  # col_level_2
    lvl3 = df.columns.get_level_values(2).unique()  # col_level_3
    fig = make_subplots(
        cols=len(lvl1), rows=len(lvl2),
        subplot_titles=[" - ".join(sub_list) for sub_list in list(product(lvl2, lvl1))])
    palette = px.colors.qualitative.Set1
    color_map = dict(zip(lvl3[::-1], palette[:len(lvl3)]))
    seen = set()  # which level_2 have already shown a legend item
    for i, geo in enumerate(lvl1, start=1):
        df_g = df.xs(geo, axis=1)  # columns now indexed only by level_2
        for j, decade in enumerate(lvl2, start=1):
            df_g_d = df_g.xs(decade, axis=1)  # columns now indexed only by level_2
            for sub in lvl3:
                fig.add_trace(
                    go.Scatter(x=df.index, y=df_g_d[sub], name=str(sub), mode="lines",
                               marker_color=color_map[sub], showlegend=sub not in seen,
                               legendgroup=str(sub)),  # optional: toggle all subplots together
                    row=j, col=i)
                seen.add(sub)
    fig.update_layout(height=150 * len(lvl1), width=400 * len(lvl2), showlegend=True,
                      title="Clarksons V-count by decade", template="simple_white")
    fig.update_xaxes(tickformat="%b-%y", **_missing_photo_text("118"))
    return fig


def generate_report():
    query = """
    SELECT [report_date]
        ,[month_period]
        ,[decade_of_month]
        ,[MEG]
        ,[WAF]
        ,[USG]
        ,[EC SOUTH AMERICA]
        ,[CARIBS/ECMEX]
        ,[WC SOUTH AMERICA]
        ,[UKC]
        ,[MED]
        ,[ATL TOTAL]
        ,[TOTAL]
    FROM [LO25].[dbo].[clarksons_fixt] where (report_date = (select max(report_date) from [LO25].[dbo].[clarksons_fixt]))
    """
    data = read_sql(query)
    latest_report_date = read_sql('select max(report_date) from [LO25].[dbo].[clarksons_fixt]')
    regions = ["MEG", "WAF", "USG", "EC SOUTH AMERICA", "CARIBS/ECMEX", "WC SOUTH AMERICA", "UKC", "MED", "ATL TOTAL", "TOTAL"]
    regions_focus = ["MEG", "WAF", "USG", "EC SOUTH AMERICA", "ATL TOTAL", "TOTAL"]
    query = """
    SELECT [report_date]
        ,[month_period]
        ,[decade_of_month]
        ,[MEG]
        ,[WAF]
        ,[USG]
        ,[EC SOUTH AMERICA]
        ,[CARIBS/ECMEX]
        ,[WC SOUTH AMERICA]
        ,[UKC]
        ,[MED]
        ,[ATL TOTAL]
        ,[TOTAL]
    FROM [LO25].[dbo].[clarksons_fixt]
    """
    evolution_data = read_sql(query).sort_values(by=['report_date', 'month_period', 'decade_of_month'])
    evolution_data['timing'] = (evolution_data.report_date - evolution_data.month_period).dt.days
    evolution_data['month_name'] = evolution_data.month_period.dt.strftime('%b-%y')
    evolution_data = evolution_data[(evolution_data.timing > -50) & (evolution_data.timing < 150)]
    evolution_df = _missing_photo_text("187")
    evolution_data
    metrics = data.columns[3:]
    cols = 4
    df = data.copy()
    chart_decade = chart_grid_by_decade(df=df, x_axis="month_period", col_values=regions, cols=cols)
    grid_evolution = chart_grid(evolution_df, regions_focus, ['ttl', '1st', '2nd', '3rd'])
    figs = [
        [table.html_text("Clarksons V-Count", style="font-family:Calibri;", tag='h1')],
        [table.html_text(f"Clarksons latest update: {latest_report_date.iloc[0, 0]}",
                         style=_missing_photo_text("198: font-family:Ca..."))],
        [chart_decade], [grid_evolution]]
    table.to_html(figs, f"{html_path}\\oil\\clarksons_v_count.html", task_name="Clarksons V-Count")


if __name__ == '__main__':
    generate_report()
