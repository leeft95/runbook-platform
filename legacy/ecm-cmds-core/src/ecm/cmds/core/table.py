import base64
import datetime as dt
import inspect
import json
import os
import re
from io import BytesIO
from pathlib import Path

import ecm.cmds.core.chart as chart
import ecm.cmds.core.to_html as html
import matplotlib.figure
import numpy as np
import pandas as pd
import plotly as py
from dateutil.relativedelta import relativedelta
from ecm.cmds.core.cdr import now_ldn
from ecm.cmds.core.time_series import historical_data_on_date
from ecm.cmds.core.time_series import historical_mean_std
from ecm.cmds.core.utils import convert_path_to_linux
from pyg_base import mkdir
from pytz import timezone
from xhtml2pdf import pisa


def color_negative_red(val):
    if isinstance(val, str) and "(" in val:
        color = "red" if val.startswith("(") else "black"
    elif isinstance(val, str):
        try:
            v = float(val.replace(",", ""))
            color = "red" if v < 0 else "black"
        except Exception:
            color = "black"

    elif isinstance(val, dt.datetime) or isinstance(val, dt.date):
        color = "black"
    else:
        color = "red" if val < 0 else "black"
    return "color: {:s}".format(color)


def apply_color(v, column_color):
    return f"color: {column_color}"


def style_bold(val, style="bold"):
    return f"font-weight: {style}"


def style_italic(val, style="italic"):
    return f"font-style: {style}"


def style_border_bottom(val):
    return "border-bottom: 1px solid black"


def style_border(val, direction="right", style="solid", sz=1):
    return f"border-{direction}: {sz}px {style} black"


def style_highlight_zscore(row):
    if len(row) == 3:
        if row[0] > row[1] + 2 * row[2]:
            return ['background-color: green', '', '']
        elif row[0] > row[1] + 1 * row[2]:
            return ['background-color: lightgreen', '', '']
        elif row[0] < row[1] - 2 * row[2]:
            return ['background-color: #FF8787', '', '']
        elif row[0] < row[1] - 1 * row[2]:
            return ['background-color: #FFA94D', '', '']
        else:
            return ['', '', '']
    elif len(row) == 4:
        if row[1] > row[2] + 2 * row[3]:
            return ['background-color: green', '', '', '']
        elif row[1] > row[2] + 1 * row[3]:
            return ['background-color: lightgreen', '', '', '']
        elif row[1] < row[2] - 2 * row[3]:
            return ['background-color: #FF8787', '', '', '']
        elif row[1] < row[2] - 1 * row[3]:
            return ['background-color: #FFA94D', '', '', '']
        else:
            return ['', '', '', '']


def style_highlight_by_key(row, true_key, false_key, true_colour="#C6EFCE", false_colour="#FFC7CE"):
    if not isinstance(true_key, list):
        true_key = [true_key]
    if not isinstance(false_key, list):
        false_key = [false_key]
    if row[0] in true_key:
        return [f"background-color: {true_colour}"]
    elif row[0] in false_key:
        return [f"background-color: {false_colour}"]
    else:
        return [""]


def style_highlight_on_range(row, min, max):
    if row[0] > max:
        return ["background-color: #C6EFCE"]
    elif row[0] < min:
        return ["background-color: #FFC7CE"]
    else:
        return [""]


def style_highlight(row):
    if len(row) == 1:
        if row[0] > 0:
            return ['background-color: #C6EFCE']
        elif row[0] < 0:
            return ['background-color: #FFC7CE']
        else:
            return ['']
    elif len(row) == 2:
        if row[1] > 0:
            return ['background-color: #C6EFCE', '']
        elif row[1] < 0:
            return ['background-color: #FFC7CE', '']
        else:
            return ['', '']
    elif len(row) == 3:
        if row[0] > row[1]:
            return ['background-color: #C6EFCE', '', '']
        elif row[0] < row[2]:
            return ['background-color: #FFC7CE', '', '']
        else:
            return ['', '', '']
    elif len(row) == 4:
        if row[1] > row[2]:
            return ['background-color: #C6EFCE', '', '', '']
        elif row[1] < row[3]:
            return ['background-color: #FFC7CE', '', '', '']
        else:
            return ['', '', '', '']
    elif len(row) == 5:
        if row[0] > row[1]:
            return ['background-color: green', '', '', '', '']
        elif row[1] > row[0] > row[2]:
            return ['background-color: #C6EFCE', '', '', '', '']
        elif row[3] > row[0] > row[4]:
            return ['background-color: #FFC7CE', '', '', '', '']
        elif row[0] < row[4]:
            return ['background-color: #FFA94D', '', '', '', '']
        else:
            return ['', '', '', '', '']
    elif len(row) == 6:
        if row[1] > row[2]:
            return ['background-color: green', '', '', '', '', '']
        elif row[2] > row[1] > row[3]:
            return ['background-color: #C6EFCE', '', '', '', '', '']
        elif row[4] > row[1] > row[5]:
            return ['background-color: #FFC7CE', '', '', '', '', '']
        elif row[1] < row[5]:
            return ['background-color: #FFA94D', '', '', '', '', '']
        else:
            return ['', '', '', '', '', '']


def html_table(df_table, **kwargs):
    """
    format DataFrame to html table
    Input is DataFrame. Return html table.
    """
    format_column = kwargs.get("format_column", None)
    format_row = kwargs.get("format_row", None)
    precision = kwargs.get("precision", 1)
    hide_cols = kwargs.get("hide_cols", [])
    hide_rows = kwargs.get("hide_rows", [])
    inline = kwargs.get("inline", False)
    background_color = kwargs.get("background_color", "lightblue")
    na_rep = kwargs.get("na_rep", "-")
    html = df_table.style
    one_bg_color = kwargs.get("one_bg_color", False)
    is_mdix = kwargs.get("multiindex", False)
    custom_width = kwargs.get("custom_width", None)

    html.applymap(color_negative_red)
    html.format(precision=precision, na_rep=na_rep, thousands=",")
    if one_bg_color:
        raise NotImplementedError("Photographed table background lambda187 clipped")
    else:
        raise NotImplementedError("Photographed table background lambda192 clipped")
    if custom_width is not None:
        td_props = [{"selector": "td", "props": [("width", custom_width)]}]
    else:
        td_props = []
    html.set_table_styles(
        [
            {
                "selector": "th",
                "props": [
                    ("border-bottom", "1px solid black"),
                    ("font-size", "11pt"),
                    ("font-family", "Calibri"),
                    ("text-align", "center"),
                ],
            },
            {
                "selector": "",
                "props": [
                    ("border", "2px solid black"),
                    ("font-size", "11pt"),
                    ("font-family", "Calibri"),
                    ("border-collapse", "collapse"),
                ],
            },
        ] + td_props,
        overwrite=False,
    )
    html.hide(axis="index")
    if inline:
        html.set_table_attributes('align="left"')

    if format_column is not None:
        for key, val in format_column.items():
            if isinstance(key, tuple) and not is_mdix:
                for k in key:
                    if "text-align" not in val.keys():
                        raise NotImplementedError("Photographed table text-align default235/327 clipped")
                    html.set_properties(
                        **{
                            "width": "{:s}".format(val["width"] if "width" in val.keys() else "100px"),
                            "text-align": "{:s}".format(val["text-align"] if "text-align" in val.keys() else ...),
                        },
                        subset=[k],
                    )
                    if "format" in val.keys():
                        html.format("{:s}".format(val["format"]), subset=[k], na_rep="-")
                    if "highlight" in val.keys():
                        html.apply(style_highlight, subset=(val["highlight"], k), axis=0)
                    if "highlight_z" in val.keys():
                        html.apply(style_highlight_zscore, subset=val["highlight_z"], axis=1)
                    if "highlight_on_key" in val.keys():
                        html.apply(
                            style_highlight_by_key,
                            subset=val["highlight_on_key"]["columns"],
                            true_key=val["highlight_on_key"]["true_key"],
                            false_key=val["highlight_on_key"]["false_key"],
                            true_colour=val["highlight_on_key"].get("true_colour", "#C6EFCE"),
                            false_colour=val["highlight_on_key"].get("false_colour", "#FFC7CE"),
                            axis=1,
                        )
                    if "highlight_on_range" in val.keys():
                        html.apply(
                            style_highlight_on_range,
                            subset=val["highlight_on_range"]["columns"],
                            min=val["highlight_on_range"]["min"],
                            max=val["highlight_on_range"]["max"],
                            axis=1,
                        )
                    if "hide" in val.keys() and val["hide"]:
                        hide_cols.append(k)
                    if val.get("right_border"):
                        border_options = val.get("right_border", {})
                        if isinstance(border_options, bool):
                            border_options = {}
                        html.applymap(
                            style_border,
                            subset=[k],
                            direction="right",
                            sz=border_options.get("size", 1),
                            style=border_options.get("style", "solid"),
                        )
                    if val.get("left_border"):
                        border_options = val.get("left_border", {})
                        if isinstance(border_options, bool):
                            border_options = {}
                        html.applymap(
                            style_border,
                            subset=[k],
                            direction="left",
                            sz=border_options.get("size", 1),
                            style=border_options.get("style", "solid"),
                        )
                    if "bar" in val.keys() and val["bar"]:
                        bar_options = val.get("bar", {})
                        if isinstance(bar_options, bool):
                            bar_options = {}
                        color_map = bar_options.get("color_map", None)
                        vmin = bar_options.get("vmin", None)
                        vmax = bar_options.get("vmax", None)
                        if color_map is not None:
                            extras = {"cmap": color_map}
                        else:
                            raise NotImplementedError("Photographed table bar color313 incomplete")
                            extras = {"color": [bar_options.get("low_color", "#d65f5f"), ...]}
                        if vmin is not None:
                            extras["vmin"] = vmin
                        if vmax is not None:
                            extras["vmax"] = vmax
                        html.bar(subset=[k], align=bar_options.get("align", "mid"), **extras)
                    if "bold" in val.keys() and val["bold"]:
                        html.applymap(style_bold, subset=[k])
                    if "italic" in val.keys() and val["italic"]:
                        html.applymap(style_italic, subset=[k], style="italic")
            else:
                if "text-align" not in val.keys():
                    raise NotImplementedError("Photographed table text-align default235/327 clipped")
                html.set_properties(
                    **{
                        "width": "{:s}".format(val["width"] if "width" in val.keys() else "100px"),
                        "text-align": "{:s}".format(val["text-align"] if "text-align" in val.keys() else ...),
                    },
                    subset=[key],
                )
                if "format" in val.keys():
                    html.format("{:s}".format(val["format"]), subset=[key], na_rep="-")
                if "highlight" in val.keys():
                    if isinstance(val["highlight"][0], int) and val["highlight"][0] not in df_table.columns:
                        val["highlight"][0] = df_table.columns[val["highlight"][0]]
                    html.apply(style_highlight, subset=val["highlight"], axis=1)
                if "highlight_z" in val.keys():
                    if isinstance(val["highlight_z"][0], int) and val["highlight_z"][0] not in df_table.columns:
                        val["highlight_z"][0] = df_table.columns[val["highlight_z"][0]]
                    html.apply(style_highlight_zscore, subset=val["highlight_z"], axis=1)
                if "highlight_on_key" in val.keys():
                    html.apply(
                        style_highlight_by_key,
                        subset=val["highlight_on_key"]["columns"],
                        true_key=val["highlight_on_key"]["true_key"],
                        false_key=val["highlight_on_key"]["false_key"],
                        true_colour=val["highlight_on_key"].get("true_colour", "#C6EFCE"),
                        false_colour=val["highlight_on_key"].get("false_colour", "#FFC7CE"),
                        axis=1,
                    )
                if "highlight_on_range" in val.keys():
                    html.apply(
                        style_highlight_on_range,
                        subset=val["highlight_on_range"]["columns"],
                        min=val["highlight_on_range"]["min"],
                        max=val["highlight_on_range"]["max"],
                        axis=1,
                    )
                if "hide" in val.keys() and val["hide"]:
                    hide_cols.append(key)
                if val.get("right_border"):
                    border_options = val.get("right_border", {})
                    if isinstance(border_options, bool):
                        border_options = {}
                    html.applymap(
                        style_border,
                        subset=[key],
                        direction="right",
                        sz=border_options.get("size", 1),
                        style=border_options.get("style", "solid"),
                    )
                if val.get("left_border"):
                    border_options = val.get("left_border", {})
                    if isinstance(border_options, bool):
                        border_options = {}
                    html.applymap(
                        style_border,
                        subset=[key],
                        direction="left",
                        sz=border_options.get("size", 1),
                        style=border_options.get("style", "solid"),
                    )
                if "bar" in val.keys() and val["bar"]:
                    bar_options = val.get("bar", {})
                    if isinstance(bar_options, bool):
                        bar_options = {}
                    color_map = bar_options.get("color_map", None)
                    vmin = bar_options.get("vmin", None)
                    vmax = bar_options.get("vmax", None)
                    if color_map is not None:
                        extras = {"cmap": color_map}
                    else:
                        raise NotImplementedError("Photographed table bar color401 incomplete")
                        extras = {"color": [bar_options.get("low_color", "#d65f5f"), ...]}
                    if vmin is not None:
                        extras["vmin"] = vmin
                    if vmax is not None:
                        extras["vmax"] = vmax
                    html.bar(subset=[key], align=bar_options.get("align", "mid"), **extras)
                if "bold" in val.keys() and val["bold"]:
                    html.applymap(style_bold, subset=[key])
                if "italic" in val.keys() and val["italic"]:
                    html.applymap(style_italic, subset=[key], style="italic")

        if hide_cols is not None and len(hide_cols) > 0:
            hide_cols = [x for x in hide_cols if x in df_table.columns]
            html.hide(hide_cols, axis="columns")
        if hide_rows is not None and len(hide_rows) > 0:
            html.hide(hide_rows, axis="index")

    if format_row is not None:
        for key, val in format_row.items():
            if isinstance(key, tuple):
                for k in key:
                    if isinstance(k, str):
                        k = int(k)
                    if "bold" in val.keys() and val["bold"]:
                        if "columns" in val.keys():
                            html.applymap(style_bold, subset=pd.IndexSlice[df_table.index[k], val["columns"]])
                        else:
                            html.applymap(style_bold, subset=pd.IndexSlice[df_table.index[k], :])
                    if "italic" in val.keys() and val["italic"]:
                        if "columns" in val.keys():
                            html.applymap(
                                style_italic,
                                subset=pd.IndexSlice[df_table.index[k], val["columns"]],
                                style="italic",
                            )
                        else:
                            html.applymap(
                                style_italic,
                                subset=pd.IndexSlice[df_table.index[k], :],
                                style="italic",
                            )
                    if "bottom_border" in val.keys() and val["bottom_border"]:
                        border_options = val.get("bottom_border", {})
                        if isinstance(border_options, bool):
                            border_options = {}
                        html.applymap(
                            style_border,
                            subset=pd.IndexSlice[df_table.index[k], :],
                            direction="bottom",
                            sz=border_options.get("size", 1),
                            style=border_options.get("style", "solid"),
                        )
                    if "top_border" in val.keys() and val["top_border"]:
                        border_options = val.get("top_border", {})
                        if isinstance(border_options, bool):
                            border_options = {}
                        html.applymap(
                            style_border,
                            subset=pd.IndexSlice[df_table.index[k], :],
                            direction="top",
                            sz=border_options.get("size", 1),
                            style=border_options.get("style", "solid"),
                        )
                    if "highlight" in val.keys():
                        html.apply(
                            style_highlight,
                            subset=pd.IndexSlice[df_table.index[k], val["highlight"]],
                            axis=1,
                        )
                    if "highlight_z" in val.keys():
                        html.apply(
                            style_highlight_zscore,
                            subset=pd.IndexSlice[df_table.index[k], val["highlight_z"]],
                            axis=1,
                        )
                    if "format" in val.keys():
                        if isinstance(val["format"], dict):
                            fval = val["format"]
                            if "columns" in fval.keys():
                                html.format(
                                    "{:s}".format(fval["format"]),
                                    subset=pd.IndexSlice[df_table.index[k], fval["columns"]],
                                    na_rep="-",
                                )
                        elif isinstance(val["format"], list):
                            fvals = val["format"]
                            for fval in fvals:
                                html.format(
                                    "{:s}".format(fval["format"]),
                                    subset=pd.IndexSlice[df_table.index[k], fval["columns"]],
                                    na_rep="-",
                                )
                        else:
                            fval = val
                            if "columns" in fval.keys():
                                html.format(
                                    "{:s}".format(fval["format"]),
                                    subset=pd.IndexSlice[df_table.index[k], fval["columns"]],
                                    na_rep="-",
                                )
                            else:
                                html.format(
                                    "{:s}".format(fval["format"]),
                                    subset=pd.IndexSlice[df_table.index[k], :],
                                    na_rep="-",
                                )
                    if "color" in val.keys():
                        html.applymap(
                            apply_color,
                            subset=pd.IndexSlice[df_table.index[k], :],
                            column_color=val["color"],
                        )
            else:
                if isinstance(key, str):
                    key = int(key)
                if "bold" in val.keys() and val["bold"]:
                    if "columns" in val.keys():
                        html.applymap(style_bold, subset=pd.IndexSlice[df_table.index[key], val["columns"]])
                    else:
                        html.applymap(style_bold, subset=pd.IndexSlice[df_table.index[key], :])
                if "italic" in val.keys() and val["italic"]:
                    if "columns" in val.keys():
                        html.applymap(
                            style_italic,
                            subset=pd.IndexSlice[df_table.index[key], val["columns"]],
                            style="italic",
                        )
                    else:
                        html.applymap(
                            style_italic,
                            subset=pd.IndexSlice[df_table.index[key], :],
                            style="italic",
                        )
                if "bottom_border" in val.keys() and val["bottom_border"]:
                    border_options = val.get("bottom_border", {})
                    if isinstance(border_options, bool):
                        border_options = {}
                    html.applymap(
                        style_border,
                        subset=pd.IndexSlice[df_table.index[key], :],
                        direction="bottom",
                        sz=border_options.get("size", 1),
                        style=border_options.get("style", "solid"),
                    )
                if "top_border" in val.keys() and val["top_border"]:
                    border_options = val.get("top_border", {})
                    if isinstance(border_options, bool):
                        border_options = {}
                    html.applymap(
                        style_border,
                        subset=pd.IndexSlice[df_table.index[key], :],
                        direction="top",
                        sz=border_options.get("size", 1),
                        style=border_options.get("style", "solid"),
                    )
                if "highlight" in val.keys():
                    html.apply(
                        style_highlight,
                        subset=pd.IndexSlice[df_table.index[key], val["highlight"]],
                        axis=1,
                    )
                if "highlight_z" in val.keys():
                    html.apply(
                        style_highlight_zscore,
                        subset=pd.IndexSlice[df_table.index[key], val["highlight_z"]],
                        axis=1,
                    )
                if "format" in val.keys():
                    if isinstance(val["format"], dict):
                        fval = val["format"]
                        if "columns" in fval.keys():
                            html.format(
                                "{:s}".format(fval["format"]),
                                subset=pd.IndexSlice[df_table.index[key], fval["columns"]],
                                na_rep="-",
                            )
                    elif isinstance(val["format"], list):
                        fvals = val["format"]
                        for fval in fvals:
                            html.format(
                                "{:s}".format(fval["format"]),
                                subset=pd.IndexSlice[df_table.index[key], fval["columns"]],
                                na_rep="-",
                            )
                    else:
                        fval = val
                        if "columns" in fval.keys():
                            html.format(
                                "{:s}".format(fval["format"]),
                                subset=pd.IndexSlice[df_table.index[key], fval["columns"]],
                                na_rep="-",
                            )
                        else:
                            html.format(
                                "{:s}".format(fval["format"]),
                                subset=pd.IndexSlice[df_table.index[key], :],
                                na_rep="-",
                            )
                if "color" in val.keys():
                    html.applymap(
                        apply_color,
                        subset=pd.IndexSlice[df_table.index[key], :],
                        column_color=val["color"],
                    )
    return df_table.to_html() if df_table.empty else html.to_html()


def html_format(
    df,
    header=None,
    footer=None,
    show_date=True,
    format_column=None,
    format_row=None,
    precision=1,
    hide_cols=None,
    hide_rows=None,
    inline=False,
    background_color="lightblue",
    one_bg_color=False,
    na_rep="-",
    header_raw=None,
    multiindex=False,
    custom_width=None,
):
    """
    change dataframe df to html

    Example:
        from functools import partial
        from pyg.mongo import mongo_table
        from ecm.cmds.config import url
        import ecm.cmds.pyg as pyg
        db = partial(mongo_table, table="data", pk=["name", "sector", "market", "category",
                     "region", "country", "source"],
                      db="reports", url=url)
        c1 = pyg.get_cell(db, name="kpler_implied_demand_exporter_table")
        tb = html_format(df=c1.data,
                         header="Export (kbd): Lower exports imply stronger internal demand
                                and/or Tars",
                         footer="Saudi/China/Japan are net exports",
                         show_date=True,
                         format_column={"0": {"width": "120px", "text-align": "left"},
                                        "1": {"width": "80px",
                                              "text-align": "center",
                                              "highlight_z": [1,"_mean","_std"]},
                                        ("2","3","4","5","6"): {"width": "80px",
                                                                 "text-align": "center"}
                                        },
                         format_row=None,
                         precision=0,
                         hide_cols=["_last_update", "_mean", "_std"],
                         inline=False,
                         background_color="lightblue",
                         na_rep="-")
        figs = []
        figs.append(tb)
        figures_to_html(figs, "H:\\temp\\test_table.html")
    """
    if format_column is None:
        format_column_ = {
            df.columns[0]: {"width": "120px", "text-align": "left"},
            tuple(df.columns[1:]): {"width": "80px", "text-align": "center"},
        }
    else:
        format_column_ = {}
        for key, val in format_column.items():
            if isinstance(key, tuple):
                try:
                    format_column_[tuple([df.columns[int(x)] for x in key])] = val
                except Exception:
                    format_column_[key] = val
            else:
                try:
                    format_column_[df.columns[int(key)]] = val
                except Exception:
                    format_column_[key] = val

    if hide_cols is None:
        if "_last_update" in df.columns and show_date:
            hide_cols = ["_last_update"]
        else:
            hide_cols = []

    body = html_table(
        df,
        precision=precision,
        background_color=background_color,
        one_bg_color=one_bg_color,
        inline=inline,
        hide_cols=hide_cols,
        hide_rows=hide_rows,
        na_rep=na_rep,
        format_column=format_column_,
        format_row=format_row,
        multiindex=multiindex,
        custom_width=custom_width,
    )
    if header is not None:
        head = f"""<p style='font-size: 16px; text-align:left;
                    font-family:Calibri; font-weight:bold'>{header}</p>"""
    else:
        if header_raw is not None:
            head = header_raw
        else:
            head = ""

    if footer is not None:
        foot = f"""<div style='font-size: 12px; text-align:left;
                    font-family:Calibri'>{footer}</div>"""
    else:
        foot = ""
    if show_date:
        if "_last_update" in df.columns:
            end_note = f"""<div style='font-size: 12px; text-align:left;
                        font-family:Calibri'>Latest data: {df['_last_update'].iloc[0]}
                        </div><br>"""
        else:
            end_note = ""
    else:
        end_note = ""
    return head + body + foot + end_note


def html_text(body, style="font-size: 12px; text-align:left; font-family:Calibri", tag="div"):
    """
    Format text, e.g.
    html_text(f"Updated at {dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    """
    if style is None:
        return f"<{tag} style='font-family:Calibri;'>{body}</{tag}>"
    else:
        return f"<{tag} style='{style}'>{body}</{tag}>"


def _table_format1(df, **kwargs):
    """
    Format of this table: month-1 to month-3 should be in format 2023-04
    columns: 20d change, (month-1), (month-2), (month-3), Y-1 20d change, 5yr 20d change
    df: freq must be daily
    ex2020: without 2020 if true
    table_head: index name
    rows: keep these columns in order from df
    highlight: dict, compare today with the same date in last 5yrs - {"seasonal": 5}
                    compare today with last 65d - {"window": 65}
    return dataframe
    Example:
        from functools import partial
        from pyg_mongo import mongo_table
        from ecm.cmds.config import url
        import ecm.cmds.pyg as pyg

        db = partial(
            mongo_table,
            table="data",
            pk=["name", "sector", "market", "category", "region", "country", "source"],
            db="reports",
            url=url,
        )
        c1 = pyg.get_cell(db, name="global_product_stocks_adjust")
        tb = table_format1(
            c1.data,
            agg_by="diff",
            agg_by_column={"Total Prods (kbd)": "mean"},
            window=20,
            show_quarter=3,
            ex2020=True,
            table_head="Exporter",
            rows=[
                "ARA",
                "US",
                "US Other",
                "Japan",
                "Singapore",
                "Fujairah",
                "Clean Oil On Water",
                "Total Prods",
                "Total Prods (kbd)",
            ],
            highlight={"seasonal": 5},

    """
    agg_by = kwargs.get("agg_by", "last")
    agg_by_column = kwargs.get("agg_by_column", None)
    window = kwargs.get("window", 20)
    ex2020 = kwargs.get("ex2020", True)
    table_head = kwargs.get("table_head", None)
    rows = kwargs.get("rows", None)
    highlight = kwargs.get("highlight", None)
    fill_na = kwargs.get("fill_na", None)
    lable = kwargs.get("lable", None)
    show_quarter = kwargs.get("show_quarter", None)
    smooth = kwargs.get("smooth", None)
    qtd = kwargs.get("qtd", False)
    df_ = df.copy()
    if rows is not None:
        df_ = df_[rows]
    if "_last_update" in df_.columns:
        _last_update = df["_last_update"].iloc[-1]
        df_.drop("_last_update", axis=1, inplace=True)
    else:
        _last_update = None
    if fill_na is not None:
        df_.fillna(method=fill_na, inplace=True)
    if agg_by_column is not None:
        col1 = list(set(df_.columns) - set(agg_by_column.keys()))
    else:
        col1 = df_.columns
    if agg_by is None:
        window_chg = df_[col1]
        lable = "Level"
    elif agg_by.lower() in ["change", "diff", "chg"]:
        if smooth is not None:
            window_chg = df_[col1].rolling(smooth).mean().diff(periods=window)
        else:
            window_chg = df_[col1].diff(periods=window)
        monthly = df_[col1].resample("M").last().diff()
        quarterly = df_[col1].resample("Q").last().diff()
        lable = "Change"
    elif agg_by.lower() == "sum":
        window_chg = df_[col1].rolling(window).sum()
        monthly = df_[col1].resample("M").sum()
        quarterly = df_[col1].resample("Q").sum()
        lable = "Sum"
    elif agg_by.lower() in ["ma", "mean"]:
        window_chg = df_[col1].rolling(window).mean()
        monthly = df_[col1].resample("M").mean()
        quarterly = df_[col1].resample("Q").mean()
        lable = "MA"

    if agg_by_column is not None:
        window_chg2 = pd.DataFrame()
        for k, v in agg_by_column.items():
            if v is None:
                window_chg2[k] = df_[k]
            elif v.lower() in ["change", "diff", "chg"]:
                window_chg2[k] = df_[k].diff(periods=window)
                monthly2 = df_[k].resample("M").last().diff()
                quarterly2 = df_[k].resample("Q").last().diff()
            elif v.lower() == "sum":
                window_chg2[k] = df_[k].rolling(window).sum()
                monthly2 = df_[k].resample("M").sum()
                quarterly2 = df_[k].resample("Q").sum()
            elif v.lower() in ["ma", "mean"]:
                window_chg2[k] = df_[k].rolling(window).mean()
                monthly2 = df_[k].resample("M").mean()
                quarterly2 = df_[k].resample("Q").mean()
        window_chg = pd.concat([window_chg, window_chg2], axis=1)
        window_chg = window_chg[df_.columns]
        monthly = pd.concat([monthly, monthly2], axis=1)
        monthly = monthly[df_.columns]
        quarterly = pd.concat([quarterly, quarterly2], axis=1)
        quarterly = quarterly[df_.columns]
    window_chg_by_year = historical_data_on_date(window_chg, date=window_chg.index[-1])
    if ex2020:
        new_idx = [x for x in window_chg_by_year.index if x.year != 2020]
        window_chg_by_year = window_chg_by_year.reindex(new_idx)
    window_chg_last = window_chg.iloc[-1, :].to_frame(f"{window}d {lable}")
    last_3_month = monthly.iloc[-4:-1, :].sort_index(ascending=False).T
    last_3_month.columns = [x.strftime("%Y-%m") for x in last_3_month.columns]
    window_chg_y1 = window_chg_by_year.iloc[-2, :].to_frame(f"Y-1 {window}d {lable}")
    window_chg_y5 = window_chg_by_year.iloc[-6:-1, :].mean(axis=0).to_frame(f"5Y {window}d {lable}")
    if _last_update is None:
        last_update = pd.DataFrame(
            df_.index[-1].strftime("%Y-%m-%d"),
            index=window_chg_last.index,
            columns=["_last_update"],
        )
    else:
        if isinstance(_last_update, str):
            last_update = pd.DataFrame(_last_update, index=window_chg_last.index, columns=["_last_update"])
        else:
            last_update = pd.DataFrame(
                _last_update.strftime("%Y-%m-%d"),
                index=window_chg_last.index,
                columns=["_last_update"],
            )
    if highlight is not None:
        if "seasonal" in highlight.keys():
            mean_std = historical_mean_std(window_chg, seasonal=highlight["seasonal"])
        elif "window" in highlight.keys():
            mean_std = historical_mean_std(window_chg, window=highlight["window"])
        mean_std.columns = ["_mean", "_std"]
        if show_quarter is not None:
            show_quarter_ = -show_quarter - 1
            last_n_quarter = quarterly.iloc[show_quarter_:-1, :].sort_index(ascending=False).T
            last_n_quarter.columns = last_n_quarter.columns.to_period("Q")
            if qtd:
                last_n_quarter = pd.concat([quarterly.iloc[-1, :].T.to_frame("QTD"), last_n_quarter], axis=1)
            df_table = pd.concat(
                [
                    window_chg_last,
                    last_3_month,
                    last_n_quarter,
                    window_chg_y1,
                    window_chg_y5,
                    last_update,
                    mean_std,
                ],
                axis=1,
            )
        else:
            df_table = pd.concat(
                [
                    window_chg_last,
                    last_3_month,
                    window_chg_y1,
                    window_chg_y5,
                    last_update,
                    mean_std,
                ],
                axis=1,
            )
    else:
        if show_quarter is not None:
            show_quarter_ = -show_quarter - 1
            last_n_quarter = quarterly.iloc[show_quarter_:-1, :].sort_index(ascending=False).T
            last_n_quarter.columns = last_n_quarter.columns.to_period("Q")
            if qtd:
                last_n_quarter = pd.concat([quarterly.iloc[-1, :].T.to_frame("QTD"), last_n_quarter], axis=1)
            df_table = pd.concat(
                [
                    window_chg_last,
                    last_3_month,
                    last_n_quarter,
                    window_chg_y1,
                    window_chg_y5,
                    last_update,
                ],
                axis=1,
            )
        else:
            df_table = pd.concat([window_chg_last, last_3_month, window_chg_y1, window_chg_y5, last_update], axis=1)
    if table_head is not None:
        df_table.index.name = table_head
    df_table.reset_index(inplace=True)
    return df_table


def _table_format1_monthly(df, **kwargs):
    """
    Format of this table: month-1 to month-3 should be in format 2023-04
    columns: 20d change, (month-1), (month-2), (month-3), Y-1 20d change, 5yr 20d change
        the first column - 20d change is last month
    df: freq must be monthly
    ex2020: without 2020 if true
    table_head: index name
    rows: keep these columns in order from df
    highlight: dict, compare current month with the same date in last 5yrs - {"seasonal": 5},
    return dataframe
    Example:
        from ecm.cmds.data import crude_consensus
        df = crude_consensus()
        tb = table_format1(df, freq="M", show_quarter=3, agg_by=None,
                          rows=["Consensus"], lable='Change')
        print(tb)
    """
    agg_by = kwargs.get("agg_by", "last")
    agg_by_column = kwargs.get("agg_by_column", None)
    window = kwargs.get("window", 1)
    ex2020 = kwargs.get("ex2020", True)
    table_head = kwargs.get("table_head", None)
    rows = kwargs.get("rows", None)
    highlight = kwargs.get("highlight", None)
    fill_na = kwargs.get("fill_na", None)
    lable = kwargs.get("lable", None)
    show_quarter = kwargs.get("show_quarter", None)
    qtd = kwargs.get("qtd", None)
    df_ = df.copy()
    if rows is not None:
        df_ = df_[rows]
    if "_last_update" in df_.columns:
        _last_update = df["_last_update"].iloc[-1]
        df_.drop("_last_update", axis=1, inplace=True)
    else:
        _last_update = None
    if fill_na is not None:
        df_.fillna(method=fill_na, inplace=True)
    if agg_by_column is not None:
        col1 = set(df_.columns) - set(agg_by_column.keys())
    else:
        col1 = df_.columns
    if agg_by is None:
        window_chg = df_[col1]
        quarterly = df_[col1].resample("Q").last()
    elif agg_by.lower() in ["change", "diff", "chg"]:
        window_chg = df_[col1].diff()
        quarterly = df_[col1].resample("Q").last().diff()
    elif agg_by.lower() in ["mean"]:
        window_chg = df_[col1]
        quarterly = df_[col1].resample("Q").mean()
    if agg_by_column is not None:
        window_chg2 = pd.DataFrame()
        for k, v in agg_by_column.items():
            if v is None:
                window_chg2[k] = df_[k]
                quarterly2 = df_[k].resample("Q").last()
            elif v.lower() in ["change", "diff", "chg"]:
                window_chg2[k] = df_[k].diff()
                quarterly2 = df_[k].resample("Q").last().diff()
        window_chg = pd.concat([window_chg, window_chg2], axis=1)
        window_chg = window_chg[df_.columns]
        quarterly = pd.concat([quarterly, quarterly2], axis=1)
        quarterly = quarterly[df_.columns]
    raise NotImplementedError("Photographed monthly window_chg_last1019 unavailable")
    last_3_month = window_chg.iloc[-4:-1, :].sort_index(ascending=False).T
    last_3_month.columns = [x.strftime("%Y-%m") for x in last_3_month.columns]
    if _last_update is None:
        last_update = pd.DataFrame(
            df_.index[-1].strftime("%Y-%m-%d"),
            index=window_chg_last.index,
            columns=["_last_update"],
        )
    else:
        if isinstance(_last_update, str):
            last_update = pd.DataFrame(_last_update, index=window_chg_last.index, columns=["_last_update"])
        else:
            last_update = pd.DataFrame(
                _last_update.strftime("%Y-%m-%d"),
                index=window_chg_last.index,
                columns=["_last_update"],
            )
    if highlight is not None:
        window_chg_by_year = historical_data_on_date(window_chg, date=window_chg.index[-1])
        if ex2020:
            new_idx = [x for x in window_chg_by_year.index if x.year != 2020]
            window_chg_by_year = window_chg_by_year.reindex(new_idx)
        window_chg_y1 = window_chg_by_year.iloc[-2, :].to_frame(f"Y-1 {window}d {lable}")
        window_chg_y5 = window_chg_by_year.iloc[-6:-1, :].mean(axis=0).to_frame(f"5Y {window}d {lable}")

        if "seasonal" in highlight.keys():
            mean_std = historical_mean_std(window_chg, seasonal=highlight["seasonal"])
        elif "window" in highlight.keys():
            mean_std = historical_mean_std(window_chg, window=highlight["window"])
        mean_std.columns = ["_mean", "_std"]
        if show_quarter is not None:
            show_quarter_ = -show_quarter - 1
            last_n_quarter = quarterly.iloc[show_quarter_:-1, :].sort_index(ascending=False).T
            last_n_quarter.columns = last_n_quarter.columns.to_period("Q")
            if qtd:
                last_n_quarter = pd.concat([quarterly.iloc[-1, :].T.to_frame("QTD"), last_n_quarter], axis=1)
            df_table = pd.concat(
                [
                    window_chg_last,
                    last_3_month,
                    last_n_quarter,
                    window_chg_y1,
                    window_chg_y5,
                    last_update,
                    mean_std,
                ],
                axis=1,
            )
        else:
            df_table = pd.concat(
                [
                    window_chg_last,
                    last_3_month,
                    window_chg_y1,
                    window_chg_y5,
                    last_update,
                    mean_std,
                ],
                axis=1,
            )
    else:
        if show_quarter is not None:
            show_quarter_ = -show_quarter - 1
            last_n_quarter = quarterly.iloc[show_quarter_:-1, :].sort_index(ascending=False).T
            last_n_quarter.columns = last_n_quarter.columns.to_period("Q")
            if qtd:
                last_n_quarter = pd.concat([quarterly.iloc[-1, :].T.to_frame("QTD"), last_n_quarter], axis=1)
            df_table = pd.concat([window_chg_last, last_3_month, last_n_quarter, last_update], axis=1)
        else:
            df_table = pd.concat([window_chg_last, last_3_month, last_update], axis=1)

    if table_head is not None:
        df_table.index.name = table_head
    df_table.reset_index(inplace=True)
    return df_table


def table_format1(
    df,
    agg_by="change",
    agg_by_column=None,
    window=20,
    ex2020=True,
    table_head=None,
    rows=None,
    highlight=None,
    freq="D",
    lable=None,
    show_quarter=None,
    smooth=None,
    qtd=False,
):
    if freq == "D":
        return _table_format1(
            df=df,
            agg_by=agg_by,
            agg_by_column=agg_by_column,
            window=window,
            ex2020=ex2020,
            table_head=table_head,
            rows=rows,
            highlight=highlight,
            lable=lable,
            show_quarter=show_quarter,
            smooth=smooth,
            qtd=qtd,
        )
    elif freq == "M":
        return _table_format1_monthly(
            df=df,
            agg_by=agg_by,
            agg_by_column=agg_by_column,
            window=window,
            table_head=table_head,
            rows=rows,
            highlight=highlight,
            lable=lable,
            show_quarter=show_quarter,
            qtd=qtd,
        )


def _table_format2(df, **kwargs):
    """
    Format of this table: month-1 to month-5 should be in format 2023-04
    columns: 10d MA 20d MA, (month-1), (month-2), (month-3), (month-4), (month-5)
    df: freq must be daily
    ex2020: without 2020 if true
    table_head: index name
    rows: keep these columns in order from df
    highlight: dict, compare today with the same date in last 5yrs - {"seasonal": 5},
                    compare today with last 65d - {"window": 65}
    return dataframe
    Example:
        from functools import partial
        from pyg.mongo import mongo_table
        from ecm.cmds.config import url
        import ecm.cmds.pyg as pyg

        db = partial(
            mongo_table,
            table="data",
            pk=["name", "sector", "market", "category", "region", "country", "source"],
            db="reports",
            url=url,
        )
        c1 = pyg.get_cell(db, name="kpler_opec_export_adjust")
        tb = table_format2(
            c1.data,
            agg_by="mean",
            agg_by_column=None,
            window=10,
            window1=20,
            show_quarter=None,
            table_head="OPEC",
            rows=None,
            highlight={"window": 65})
    """
    agg_by = kwargs.get("agg_by", "last")
    agg_by_column = kwargs.get("agg_by_column", None)
    window = kwargs.get("window", 10)
    window1 = kwargs.get("window1", 20)
    table_head = kwargs.get("table_head", None)
    rows = kwargs.get("rows", None)
    highlight = kwargs.get("highlight", None)
    fill_na = kwargs.get("fill_na", None)
    lable = kwargs.get("lable", None)
    show_quarter = kwargs.get("show_quarter", None)
    mtd = kwargs.get("mtd", None)
    df_ = df.copy()
    if rows is not None:
        df_ = df_[rows]
    if "_last_update" in df_.columns:
        _last_update = df_["_last_update"].iloc[-1]
        df_.drop("_last_update", axis=1, inplace=True)
    else:
        _last_update = None
    if fill_na is not None:
        df_.fillna(method=fill_na, inplace=True)
    if agg_by_column is not None:
        col1 = set(df_.columns) - set(agg_by_column.keys())
    else:
        col1 = df_.columns
    if agg_by is None:
        window_chg = df_[col1]
        window_chg1 = df_[col1]
        lable = "Level"
    elif agg_by.lower() in ["change", "diff", "chg"]:
        window_chg = df_[col1].diff(periods=window)
        window_chg1 = df_[col1].diff(periods=window1)
        monthly = df_[col1].resample("M").last().diff()
        quarterly = df_[col1].resample("Q").last().diff()
        lable = "Change"
    elif agg_by.lower() == "sum":
        window_chg = df_[col1].rolling(window).sum()
        window_chg1 = df_[col1].rolling(window1).sum()
        monthly = df_[col1].resample("M").sum()
        quarterly = df_[col1].resample("Q").sum()
        lable = "Sum"
    elif agg_by.lower() in ["ma", "mean"]:
        window_chg = df_[col1].rolling(window).mean()
        window_chg1 = df_[col1].rolling(window1).mean()
        monthly = df_[col1].resample("M").mean()
        quarterly = df_[col1].resample("Q").mean()
        lable = "MA"

    if agg_by_column is not None:
        window_chg2 = pd.DataFrame()
        window_chg3 = pd.DataFrame()
        for k, v in agg_by_column.items():
            if v is None:
                window_chg2[k] = df_[k]
                window_chg3[k] = df_[k]
            elif v.lower() in ["change", "diff", "chg"]:
                window_chg2[k] = df_[k].diff(periods=window)
                window_chg3[k] = df_[k].diff(periods=window1)
                if mtd:
                    last_m = (df_[k].resample("M").last()).iloc[-2]
                    window_chg2.loc[window_chg2.index[-1], k] = (df_[k].rolling(window).mean()).iloc[-1] - last_m
                    window_chg3.loc[window_chg3.index[-1], k] = (df_[k].rolling(window1).mean()).iloc[-1] - last_m
                monthly2 = df_[k].resample("M").last().diff()
                quarterly2 = df_[k].resample("Q").last().diff()
            elif v.lower() == "sum":
                window_chg2[k] = df_[k].rolling(window).sum()
                window_chg3[k] = df_[k].rolling(window1).sum()
                monthly2 = df_[k].resample("M").sum()
                quarterly2 = df_[k].resample("Q").sum()
            elif v.lower() in ["ma", "mean"]:
                window_chg2[k] = df_[k].rolling(window).mean()
                window_chg3[k] = df_[k].rolling(window1).mean()
                monthly2 = df_[k].resample("M").mean()
                quarterly2 = df_[k].resample("Q").mean()
        window_chg = pd.concat([window_chg, window_chg2], axis=1)
        window_chg1 = pd.concat([window_chg1, window_chg3], axis=1)
        window_chg = window_chg[df_.columns]
        window_chg1 = window_chg1[df_.columns]
        monthly = pd.concat([monthly, monthly2], axis=1)
        monthly = monthly[df_.columns]
        quarterly = pd.concat([quarterly, quarterly2], axis=1)
        quarterly = quarterly[df_.columns]

    window_chg_last = window_chg.iloc[-1, :].to_frame(f"{window}d {lable}")
    window_chg_last1 = window_chg1.iloc[-1, :].to_frame(f"{window1}d {lable}")
    last_5_month = monthly.iloc[-6:-1, :].sort_index(ascending=False).T
    last_5_month.columns = [x.strftime("%Y-%m") for x in last_5_month.columns]
    if _last_update is None:
        last_update = pd.DataFrame(
            df_.index[-1].strftime("%Y-%m-%d"),
            index=window_chg_last.index,
            columns=["_last_update"],
        )
    else:
        if isinstance(_last_update, str):
            last_update = pd.DataFrame(_last_update, index=window_chg_last.index, columns=["_last_update"])
        else:
            last_update = pd.DataFrame(
                _last_update.strftime("%Y-%m-%d"),
                index=window_chg_last.index,
                columns=["_last_update"],
            )
    if highlight is not None:
        if "seasonal" in highlight.keys():
            mean_std = historical_mean_std(window_chg, seasonal=highlight["seasonal"])
            mean_std1 = historical_mean_std(window_chg1, seasonal=highlight["seasonal"])
        elif "window" in highlight.keys():
            mean_std = historical_mean_std(window_chg, seasonal=None, window=highlight["window"])
            mean_std1 = historical_mean_std(window_chg1, seasonal=None, window=highlight["window"])
        mean_std.columns = ["_mean", "_std"]
        mean_std1.columns = ["_mean1", "_std1"]
        if show_quarter is not None:
            show_quarter_ = -show_quarter - 1
            last_n_quarter = quarterly.iloc[show_quarter_:-1, :].sort_index(ascending=False).T
            last_n_quarter.columns = last_n_quarter.columns.to_period("Q")
            df_table = pd.concat(
                [
                    window_chg_last,
                    window_chg_last1,
                    last_5_month,
                    last_n_quarter,
                    last_update,
                    mean_std,
                    mean_std1,
                ],
                axis=1,
            )
        else:
            df_table = pd.concat(
                [
                    window_chg_last,
                    window_chg_last1,
                    last_5_month,
                    last_update,
                    mean_std,
                    mean_std1,
                ],
                axis=1,
            )
    else:
        if show_quarter is not None:
            show_quarter_ = -show_quarter - 1
            last_n_quarter = quarterly.iloc[show_quarter_:-1, :].sort_index(ascending=False).T
            last_n_quarter.columns = last_n_quarter.columns.to_period("Q")
            df_table = pd.concat(
                [
                    window_chg_last,
                    window_chg_last1,
                    last_5_month,
                    last_n_quarter,
                    last_update,
                ],
                axis=1,
            )
        else:
            df_table = pd.concat([window_chg_last, window_chg_last1, last_5_month, last_update], axis=1)
    if table_head is not None:
        df_table.index.name = table_head
    df_table.reset_index(inplace=True)
    return df_table


def _table_format2_vs_month(df, **kwargs):
    """
    Format of this table: month-1 to month-5 should be in format 2023-04
    columns: 10d MA 20d MA, (month-1), (month-2), (month-3), (month-4), (month-5)
    df: freq must be daily
    ex2020: without 2020 if true
    table_head: index name
    rows: keep these columns in order from df
    highlight: dict, compare today with the same date in last 5yrs - {"seasonal": 5},
                    compare today with last 65d - {"window": 65}
    return dataframe
    Example:
        from functools import partial
        from pyg_mongo import mongo_table
        from ecm.cmds.config import url
        import ecm.cmds.pyg as pyg

        db = partial(
            mongo_table,
            table="data",
            pk=["name", "sector", "market", "category", "region", "country", "source"],
            db="reports",
            url=url,
        )
        c1 = pyg.get_cell(db, name="russia_total_export_adjust")
        tb = _table_format2_vs_month(
            c1.data,
            agg_by="mean",
            agg_by_column=None,
            window=10,
            window1=20,
            benchmark_month=dt.datetime(2022,2,1),
            table_head="Total Exports",
            rows=None,
            highlight={"window": 65})
    """
    agg_by = kwargs.get("agg_by", "last")
    agg_by_column = kwargs.get("agg_by_column", None)
    window = kwargs.get("window", 10)
    window1 = kwargs.get("window1", 20)
    table_head = kwargs.get("table_head", None)
    rows = kwargs.get("rows", None)
    highlight = kwargs.get("highlight", None)
    fill_na = kwargs.get("fill_na", None)
    lable = kwargs.get("lable", None)
    benchmark_month = kwargs.get("benchmark_month", None)
    benchmark_quarter = kwargs.get("benchmark_quarter", None)
    df_ = df.copy()
    if rows is not None:
        df_ = df_[rows]
    if "_last_update" in df_.columns:
        _last_update = df_["_last_update"].iloc[-1]
        df_.drop("_last_update", axis=1, inplace=True)
    else:
        _last_update = None
    if fill_na is not None:
        df_.fillna(method=fill_na, inplace=True)
    if agg_by_column is not None:
        col1 = set(df_.columns) - set(agg_by_column.keys())
    else:
        col1 = df_.columns
    if agg_by is None:
        window_chg = df_[col1]
        window_chg1 = df_[col1]
        lable = "Level"
    elif agg_by.lower() in ["change", "diff", "chg"]:
        window_chg = df_[col1].diff(periods=window)
        window_chg1 = df_[col1].diff(periods=window1)
        monthly = df_[col1].resample("M").last().diff()
        quarterly = df_[col1].resample("Q").last().diff()
        lable = "Change"
    elif agg_by.lower() == "sum":
        window_chg = df_[col1].rolling(window).sum()
        window_chg1 = df_[col1].rolling(window1).sum()
        monthly = df_[col1].resample("M").sum()
        quarterly = df_[col1].resample("Q").sum()
        lable = "Sum"
    elif agg_by.lower() in ["ma", "mean"]:
        window_chg = df_[col1].rolling(window).mean()
        window_chg1 = df_[col1].rolling(window1).mean()
        monthly = df_[col1].resample("M").mean()
        quarterly = df_[col1].resample("Q").mean()
        lable = "MA"

    if agg_by_column is not None:
        window_chg2 = pd.DataFrame()
        window_chg3 = pd.DataFrame()
        for k, v in agg_by_column.items():
            if v is None:
                window_chg2[k] = df_[k]
                window_chg3[k] = df_[k]
            elif v.lower() in ["change", "diff", "chg"]:
                window_chg2[k] = df_[k].diff(periods=window)
                window_chg3[k] = df_[k].diff(periods=window1)
                monthly2 = df_[k].resample("M").last().diff()
                quarterly2 = df_[k].resample("Q").last().diff()
            elif v.lower() == "sum":
                window_chg2[k] = df_[k].rolling(window).sum()
                window_chg3[k] = df_[k].rolling(window1).sum()
                monthly2 = df_[k].resample("M").sum()
                quarterly2 = df_[k].resample("Q").sum()
            elif v.lower() in ["ma", "mean"]:
                window_chg2[k] = df_[k].rolling(window).mean()
                window_chg3[k] = df_[k].rolling(window1).mean()
                monthly2 = df_[k].resample("M").mean()
                quarterly2 = df_[k].resample("Q").mean()
        window_chg = pd.concat([window_chg, window_chg2], axis=1)
        window_chg1 = pd.concat([window_chg1, window_chg3], axis=1)
        window_chg = window_chg[df_.columns]
        window_chg1 = window_chg1[df_.columns]
        monthly = pd.concat([monthly, monthly2], axis=1)
        monthly = monthly[df_.columns]
        quarterly = pd.concat([quarterly, quarterly2], axis=1)
        quarterly = quarterly[df_.columns]

    window_chg_last = window_chg.iloc[-1, :].to_frame(f"{window}d {lable}")
    window_chg_last1 = window_chg1.iloc[-1, :].to_frame(f"{window1}d {lable}")
    last_5_month = monthly.iloc[-6:-1, :].sort_index(ascending=False).T
    last_5_month.columns = [x.strftime("%Y-%m") for x in last_5_month.columns]
    if _last_update is None:
        last_update = pd.DataFrame(
            df_.index[-1].strftime("%Y-%m-%d"),
            index=window_chg_last.index,
            columns=["_last_update"],
        )
    else:
        if isinstance(_last_update, str):
            last_update = pd.DataFrame(_last_update, index=window_chg_last.index, columns=["_last_update"])
        else:
            last_update = pd.DataFrame(
                _last_update.strftime("%Y-%m-%d"),
                index=window_chg_last.index,
                columns=["_last_update"],
            )
    if highlight is not None:
        if "seasonal" in highlight.keys():
            mean_std = historical_mean_std(window_chg, seasonal=highlight["seasonal"])
            mean_std1 = historical_mean_std(window_chg1, seasonal=highlight["seasonal"])
        elif "window" in highlight.keys():
            mean_std = historical_mean_std(window_chg, window=highlight["window"])
            mean_std1 = historical_mean_std(window_chg1, window=highlight["window"])
        mean_std.columns = ["_mean", "_std"]
        mean_std1.columns = ["_mean1", "_std1"]
        if benchmark_month is not None:
            benchmark_month_ = window_chg_last.iloc[:, 0] - monthly.loc[benchmark_month + relativedelta(day=31), :]
            benchmark_month_ = benchmark_month_.to_frame(f"10dMA vs {benchmark_month.strftime('%b%y')}")
            df_table = pd.concat(
                [
                    window_chg_last,
                    window_chg_last1,
                    last_5_month,
                    benchmark_month_,
                    last_update,
                    mean_std,
                    mean_std1,
                ],
                axis=1,
            )
        elif benchmark_quarter is not None:
            benchmark_month = pd.to_datetime(benchmark_quarter)
            benchmark_months = [
                benchmark_month + relativedelta(day=31),
                benchmark_month + relativedelta(months=1) + relativedelta(day=31),
                benchmark_month + relativedelta(months=2) + relativedelta(day=31),
            ]
            benchmark_month_ = window_chg_last1.iloc[:, 0] - monthly.loc[benchmark_months, :].mean()
            benchmark_month_ = benchmark_month_.to_frame(f"20dMA vs {benchmark_quarter}")
            df_table = pd.concat(
                [
                    window_chg_last,
                    window_chg_last1,
                    last_5_month,
                    benchmark_month_,
                    last_update,
                    mean_std,
                    mean_std1,
                ],
                axis=1,
            )
        else:
            df_table = pd.concat(
                [
                    window_chg_last,
                    window_chg_last1,
                    last_5_month,
                    last_update,
                    mean_std,
                    mean_std1,
                ],
                axis=1,
            )
    else:
        if benchmark_month is not None:
            benchmark_month_ = window_chg_last.iloc[:, 0] - monthly.loc[benchmark_month + relativedelta(day=31), :]
            benchmark_month_ = benchmark_month_.to_frame(f"10dMA vs {benchmark_month.strftime('%b%y')}")
            df_table = pd.concat(
                [
                    window_chg_last,
                    window_chg_last1,
                    last_5_month,
                    benchmark_month_,
                    last_update,
                ],
                axis=1,
            )
        else:
            df_table = pd.concat([window_chg_last, window_chg_last1, last_5_month, last_update], axis=1)
    if table_head is not None:
        df_table.index.name = table_head
    df_table.reset_index(inplace=True)
    return df_table


def table_format2(
    df,
    agg_by="change",
    agg_by_column=None,
    window=10,
    window1=20,
    table_head=None,
    rows=None,
    highlight=None,
    freq="D",
    lable=None,
    show_quarter=None,
    mtd=False,
):
    if freq == "D":
        return _table_format2(
            df=df,
            agg_by=agg_by,
            agg_by_column=agg_by_column,
            window=window,
            window1=window1,
            table_head=table_head,
            rows=rows,
            highlight=highlight,
            lable=lable,
            show_quarter=show_quarter,
            mtd=mtd,
        )


def table_format2_vs_month(
    df,
    agg_by="change",
    agg_by_column=None,
    window=10,
    window1=20,
    table_head=None,
    rows=None,
    highlight=None,
    freq="D",
    lable=None,
    benchmark_month=None,
    benchmark_quarter=None,
):
    if freq == "D":
        return _table_format2_vs_month(
            df=df,
            agg_by=agg_by,
            agg_by_column=agg_by_column,
            window=window,
            window1=window1,
            table_head=table_head,
            rows=rows,
            highlight=highlight,
            lable=lable,
            benchmark_month=benchmark_month,
            benchmark_quarter=benchmark_quarter,
        )


def table_with_link(data, name, folder, inline=False, **kwargs):
    """
    Create table with link to charts
    """
    width1 = kwargs.get("width1", 80)
    width2 = kwargs.get("width2", 60)
    chart_columns = kwargs.get("chart_columns", None)
    header = kwargs.get("header", None)
    footer = kwargs.get("footer", None)
    rows = kwargs.get("rows", 10)
    drop_cols = kwargs.get("drop_cols", [2020, 2022])

    chg = data.diff()
    chg.columns = [f"{x}_chg" for x in data.columns]
    chg_mean = chg.rolling(65).mean()
    chg_mean.columns = [f"{x}_mean" for x in chg_mean.columns]
    chg_std = chg.rolling(65).std()
    chg_std.columns = [f"{x}_std" for x in chg_std.columns]
    data_ = pd.concat([data, chg, chg_mean, chg_std], axis=1)
    data_mv = data.dropna().rolling(20).mean()
    data_ori = data.copy()
    data_ori.columns = [f"{x}_chg" for x in data_ori.columns]
    data_ori_mean = data_mv.copy()
    data_ori_mean.columns = [f"{x}_mean" for x in data_ori.columns]
    data_ori_std = data.rolling(20).std()
    data_ori_std.columns = [f"{x}_std" for x in data_ori.columns]
    data_mv = pd.concat([data_mv, data_ori, data_ori_mean, data_ori_std], axis=1)
    lastest_mv = data_mv.iloc[-1:, :]
    lastest_mv.index = ["20d ma"]
    data_ = data_.iloc[-rows:, :]
    data_.index = data_.index.strftime("%d-%b-%y")
    data_ = pd.concat([data_, lastest_mv], axis=0)
    data_.index.name = name
    data_.reset_index(inplace=True)
    hide_cols = [x for x in data_.columns if "_" in x]
    format_dict = {name: {"width": "{:d}px".format(width1), "text-align": "Center"}}
    charts = []
    if chart_columns is None:
        chart_columns = {tuple(data.columns): 20}
    for col in data.columns:
        format_dict[col] = {
            "width": "{:d}px".format(width2),
            "text-align": "Center",
            "highlight_z": [col, f"{col}_chg", f"{col}_chg_mean", f"{col}_chg_std"],
        }

    for k, v in chart_columns.items():
        if isinstance(v, str) and v == "seasonal":
            if isinstance(k, tuple):
                for col in k:
                    data_chart_ = pd.Series(
                        np.nan,
                        index=pd.bdate_range(
                            dt.datetime(data[col].index[0].year, 1, 1),
                            data[col].index[0] - dt.timedelta(1),
                        ),
                    )
                    if len(data_chart_) > 0:
                        data_chart_ = pd.concat([data_chart_, data[col]], axis=0)
                    else:
                        data_chart_ = data[col]
                    charts.append(
                        chart.seasonal_chart(
                            df=data_chart_.dropna(),
                            title=f"{name}_{col}",
                            ex2020=True,
                            freq="B",
                            width=750,
                            height=500,
                            vs_avg=False,
                            exclude_years=drop_cols,
                        )
                    )
            else:
                data_chart_ = pd.Series(
                    np.nan,
                    index=pd.bdate_range(dt.datetime(data[k].index[0].year, 1, 1), data[k].index[0] - dt.timedelta(1)),
                )
                if len(data_chart_) > 0:
                    data_chart_ = pd.concat([data_chart_, data[k]], axis=0)
                else:
                    data_chart_ = data[k]
                charts.append(
                    chart.seasonal_chart(
                        df=data_chart_,
                        title=f"{name}_{k}",
                        ex2020=True,
                        freq="B",
                        width=750,
                        height=500,
                        exclude_years=drop_cols,
                        vs_avg=False,
                    )
                )
        elif isinstance(v, pd.DataFrame):
            if isinstance(k, tuple):
                for col in k:
                    data1 = v.reindex(data.index, method="ffill")
                    charts.append(
                        chart.line_chart(
                            df=data[[col]],
                            data_ply2=data1,
                            secondary_y=True,
                            title=f"{name}_{col}",
                            tickformat=None,
                            width=750,
                            height=500,
                        )
                    )
            else:
                data1 = v.reindex(data.index, method="ffill")
                charts.append(
                    chart.line_chart(
                        df=data[[k]],
                        data_ply2=data1,
                        secondary_y=True,
                        title=f"{name}_{k}",
                        tickformat=None,
                        width=750,
                        height=500,
                    )
                )
        elif isinstance(v, int):
            if isinstance(k, tuple):
                for col in k:
                    data_chart = pd.concat([data[col].dropna(), data[col].dropna().rolling(v).mean()], axis=1)
                    data_chart.columns = [col, f"{v}d ma"]
                    if data_chart.iloc[:, 0].dropna().index.min() < dt.datetime(2023, 1, 1):
                        charts.append(
                            chart.seasonal_chart(
                                df=data_chart[col],
                                title=f"{name}_{col}",
                                ex2020=True,
                                freq="B",
                                width=750,
                                height=500,
                                vs_avg=True,
                                x_axis_title="Date",
                                exclude_years=drop_cols,
                            )
                        )
                    else:
                        charts.append(
                            chart.line_chart(
                                df=data_chart,
                                title=f"{name}_{col}",
                                tickformat=None,
                                width=750,
                                height=500,
                            )
                        )
            else:
                data_chart = pd.concat([data[k].dropna(), data[k].dropna().rolling(v).mean()], axis=1)
                data_chart.columns = [k, f"{v}d ma"]
                if data_chart.iloc[:, 0].dropna().index.min() < dt.datetime(2023, 1, 1):
                    charts.append(
                        chart.seasonal_chart(
                            df=data_chart[k],
                            title=f"{name}_{k}",
                            ex2020=True,
                            freq="B",
                            width=750,
                            height=500,
                            vs_avg=True,
                            x_axis_title="Date",
                            exclude_years=drop_cols,
                        )
                    )
                else:
                    charts.append(
                        chart.line_chart(
                            df=data_chart,
                            title=f"{name}_{k}",
                            tickformat=None,
                            width=750,
                            height=500,
                        )
                    )
    file_path = f"{folder}\\{name.replace('/', '_')}.html"
    figures_to_html(charts, file_path)
    chart_link = f'<a href="{file_path}">{name}</a>'
    html = html_format(
        df=data_,
        precision=2,
        background_color="F5F5F5",
        one_bg_color=True,
        header=header,
        footer=footer,
        inline=inline,
        hide_cols=hide_cols,
        format_column=format_dict,
        format_row={len(data_) - 2: {"bottom_border": True}},
    )
    return html.replace(name, chart_link)


def figures_to_html(
    figs,
    filename="dashboard.html",
    add_home: bool = True,
    add_generation_timestamp: bool = True,
    task_name=None,
):
    filename = convert_path_to_linux(filename)
    mkdir(filename)
    dashboard = open(filename, "w", encoding="utf-8")
    dashboard.write("<html><head></head><div><style>table {margin: 10px;}</style></div><body>" + "\n")
    if add_home:
        raise NotImplementedError("Unrecoverable table.py:1832 home_link URL/HTML tail")
        home_link = ...
        if task_name:
            frame_info = inspect.stack()[1]
            filename = frame_info.filename
            caller = Path(os.path.abspath(filename))
            run_date = dt.datetime.now().strftime("%Y-%m-%d")
            task = task_name.replace("_", "-").replace(" ", "-").replace("'", "").lower()
            folder_name = caller.parent.stem.replace("_", "-").replace(" ", "-").replace("'", "")
            if folder_name == "Utility-Code":
                folder_name = "us-gas"
            elif folder_name == "EU-Code":
                folder_name = "eu-gas"
            else:
                folder_name = folder_name
            task_path = f"lo25/{folder_name}/{task}"
            rerun_link = (
                "<a href='https://prismaticprod-gfishbein.elementcapital.msappproxy.net/"
                "snaphub/LinkRunner/AskToRun"
                "?runner=Wave&action=Trigger"
                f"&activity=day/{run_date}/{task_path}'"
                " target='_blank'>Re-run Report</a>"
            )
            home_link = home_link + f"&emsp;{rerun_link}"
        dashboard.write(home_link)
    if add_generation_timestamp:
        ts = dt.datetime.now().astimezone(timezone("Europe/London")).strftime("%Y-%m-%d %H:%M:%S %Z%z")
        to_write = html_text(f"Generated on {ts}<br>")
        dashboard.write(to_write)
    for fig in figs:
        if fig is None:
            continue
        if isinstance(fig, html.Markdown):
            dashboard.write(fig.to_html())
            continue
        try:
            inner_html = fig.to_html().split("<body>")[1].split("</body>")[0]
            dashboard.write(inner_html)
        except Exception:
            dashboard.write(fig)
    dashboard.write("</body></html>" + "\n")
    dashboard.close()
    return open(filename, "r", encoding="utf-8").read()


def figures_to_imgs(figs):
    images = [base64.b64encode(py.io.to_image(figure)).decode("utf-8") for figure in figs]
    html_img = ['''<br> <img alt="Embedded Image" src="data:image/png;base64,{:s}" /><br><br>'''.format(x) for x in images]
    return html_img


def figures_to_pdf(figs, pdf_path, **kwargs):
    """
    Convert plotly go figure list to pdf
    """
    pdf_path = convert_path_to_linux(pdf_path)
    landscape = kwargs.get("landscape", False)
    width = kwargs.get("width", 600)
    height = kwargs.get("heigh", 400)
    images = []
    for _idx, val in enumerate(figs):
        try:
            images.append(base64.b64encode(py.io.to_image(val)).decode("utf-8"))
        except Exception:
            try:
                with open(val, "rb") as image_file:
                    images.append(base64.b64encode(image_file.read()).decode("utf-8"))
            except Exception:
                img = html_to_plotly(val, path=False)
                images.append(base64.b64encode(py.io.to_image(img)).decode("utf-8"))
    report_html = ""
    raise NotImplementedError("Unrecoverable table.py:1903 PDF image/caption template tail")
    template = ...
    for image in images:
        _ = template
        _ = _.format(image=image, caption="", width=width, height=height)
        report_html += _
    convert_html_to_pdf(report_html, pdf_path, landscape=landscape)


def convert_html_to_pdf(source_html, output_filename, landscape=False):
    result_file = open(output_filename, "w+b")

    if landscape:
        raise NotImplementedError("Unrecoverable table.py:1917 landscape HTML/CSS tail")
        source_html = ...
    pisa_status = pisa.CreatePDF(
        source_html,  # the HTML to convert
        dest=result_file,  # file handle to receive result
    )

    result_file.close()  # close output file

    return pisa_status.err


def html_to_plotly(html_file, path=True):
    if path:
        html_file = convert_path_to_linux(html_file)
        with open(html_file) as f:
            html = f.read()
    else:
        html = html_file
    num = -(2**16)
    call_arg_str = re.findall(r"Plotly\.newPlot\((.*)\)", html[num:])[0]
    call_args = json.loads(f"[{call_arg_str}]")
    plotly_json = {"data": call_args[1], "layout": call_args[2]}
    return py.io.from_json(json.dumps(plotly_json))


def html_style(style: dict = None):
    content = """
    body {
        font-family:Calibri;
      }
      head {
        font-family:Calibri;
      }
    """
    if style is not None:
        for k, v in style.items():
            content += f"""
            .{k} {{
            {v}
            }}
            """
    return content


def figs_to_grid_email(figs, columns=3, width=1200):
    """
    Outlook-only version.
    - Outer 100% table centers a fixed-width inner table (width attr).
    - Cells use percentage widths; images are block + width:100%; height:auto.
    """

    def _inner_body(html_str: str) -> str:
        s = str(html_str)
        low = s.lower()
        if "<body" in low and "</body>" in low:
            try:
                i = low.index("<body")
                i = low.index(">", i) + 1
                j = low.index("</body>", i)
                return s[i:j]
            except Exception:
                return s
        return s

    rows = [figs[i : i + columns] for i in range(0, len(figs), columns)]  # noqa: E203
    td_width = int(100 / columns)

    raise NotImplementedError("Unrecoverable table.py:1990 email inner-table CSS tail")
    parts = [
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" '
        'style="border-collapse:collapse; mso-table-lspace:0pt; mso-table-rspace:0pt;"><tr>'
        '<td align="left" style="padding:0;">',
        ...,
    ]

    for r in rows:
        parts.append("<tr>")
        for fig in r:
            parts.append(f'<td width="{td_width}%" valign="top" style="padding:6px;">')

            if isinstance(fig, py.graph_objs.Figure):
                png = py.io.to_image(fig, format="png", scale=1)
                encoded = base64.b64encode(png).decode("utf-8")
                parts.append('<img alt="figure" ' f'src="data:image/png;base64,{encoded}" ' 'style="display:block; width:100%; height:auto;">')
            elif isinstance(fig, matplotlib.figure.Figure):
                buf = BytesIO()
                fig.savefig(buf, format="png", bbox_inches="tight")
                encoded = base64.b64encode(buf.getvalue()).decode("utf-8")
                parts.append('<img alt="figure" ' f'src="data:image/png;base64,{encoded}" ' 'style="display:block; width:100%; height:auto;">')
            elif isinstance(fig, str) and fig.lower().endswith(".png"):
                with open(fig, "rb") as f:
                    encoded = base64.b64encode(f.read()).decode("utf-8")
                parts.append('<img alt="image" ' f'src="data:image/png;base64,{encoded}" ' 'style="display:block; width:100%; height:auto;">')
            elif isinstance(fig, html.Markdown):
                parts.append(fig.to_html())
            else:
                parts.append(_inner_body(str(fig)))

            parts.append("</td>")

        if len(r) < columns:
            for _ in range(columns - len(r)):
                parts.append(f'<td width="{td_width}%" valign="top" style="padding:6px;"></td>')
        parts.append("</tr>")

    parts.append("</table></td></tr></table>")
    return "".join(parts)


def figs_to_grid(figs, columns=3, flex=False, email: bool = False):
    """splits a list of html objects into a grid"""

    if email:
        return figs_to_grid_email(figs, columns=columns)
    rows = len([(figs[i : i + columns]) for i in range(0, len(figs), columns)])  # noqa: E203
    style_container = f"""
        display: grid;
        grid-template-columns: repeat({columns}, 0.05fr);
        grid-template-rows: repeat({rows}, 0.05fr);
        grid-gap: 10px;
        padding: 10px;
        gap: 5px;
    """
    if flex:
        style_item = """
                display: flex;
                justify-content: center;
                align-items: center;
                """
    else:
        style_item = """
        display: table-cell;
        vertical-align: middle;
        justify-content: center;
        align-items: center;
        """
    body = f"""<div style='{style_container}'>"""
    for i, fig in enumerate(figs):
        item_num = i + 1
        div = f"<div class='item{item_num}' style='{style_item}'>"
        if isinstance(fig, py.graph_objs.Figure):
            body += f"{div}{fig.to_html().split('<body>')[1].split('</body>')[0]}</div>"
        elif isinstance(fig, matplotlib.figure.Figure):
            tmpfile = BytesIO()
            fig.savefig(tmpfile, format="png")
            encoded = base64.b64encode(tmpfile.getvalue()).decode("utf-8")
            body += f"{div}<img src='data:image/png;base64,{encoded}'></div>"
        elif isinstance(fig, str) and fig[-4:] == ".png":
            encoded = base64.b64encode(open(fig, "rb").read()).decode("utf-8")
            body += f"{div}<img src='data:image/png;base64,{encoded}'></div>"
        elif isinstance(fig, html.Markdown):
            body += f"{div}{fig.to_html()}</div>"
        else:
            body += f"{div}{fig}</div>"
    return body + "</div>"


def _recur_list(figs, cnt=0, style=None):
    if cnt % 2 == 0:
        header = "<div>"
    else:
        header = f"<div class='{style}'>"
    div = "<div style='margin: 5px;'>"
    body_content = ""
    for fig in figs:
        if isinstance(fig, py.graph_objs.Figure):
            body_content += f"{div}{fig.to_html().split('<body>')[1].split('</body>')[0]}</div>"
        elif isinstance(fig, matplotlib.figure.Figure):
            tmpfile = BytesIO()
            fig.savefig(tmpfile, format="png")
            encoded = base64.b64encode(tmpfile.getvalue()).decode("utf-8")
            body_content += f"{div}<img src='data:image/png;base64,{encoded}'></div>"
        elif isinstance(fig, str) and fig[-4:] == ".png":
            encoded = base64.b64encode(open(fig, "rb").read()).decode("utf-8")
            body_content += f"{div}<img src='data:image/png;base64,{encoded}'></div>"
        elif isinstance(fig, list) or isinstance(fig, tuple):
            body_content += _recur_list(fig, cnt=cnt + 1, style=style)
        elif isinstance(fig, html.Markdown):
            body_content += f"{div}{fig.to_html()}</div>"
        else:
            body_content += f"{div}{fig}</div>"
    return header + body_content + "</div>"


def to_html(figs, path=None, title=None, add_home: bool = True, task_name=None, add_generation_timestamp: bool = True):
    """
    convert list to html. Elements in list is vertically arranged in html.
    But list in figs list is horizontally arranged.
    :param figs: list of tables and charts
    :param path: save html to path
    :param title: html title
    :return:
    """
    _style = {"horizontal": "display: flex;"}
    body_content = _recur_list(figs, style="horizontal")

    if add_generation_timestamp:
        body_content = (
            f"""
        <div style='font-size: 12px;'>
        Updated at {now_ldn().strftime('%Y-%m-%d %H:%M:%S')}
        </div><br>
        """
            + body_content
        )

    if add_home:
        raise NotImplementedError("Unrecoverable table.py:2127 home_link URL/HTML tail")
        home_link = ...
        if task_name:
            frame_info = inspect.stack()[1]
            filename = frame_info.filename
            caller = Path(os.path.abspath(filename))
            run_date = dt.datetime.now().strftime("%Y-%m-%d")
            task = task_name.replace("_", "-").replace(" ", "-").replace("'", "").lower()
            folder_name = caller.parent.stem.replace("_", "-").replace(" ", "-").replace("'", "")
            if folder_name == "Utility-Code":
                folder_name = "us-gas"
            elif folder_name == "EU-Code":
                folder_name = "eu-gas"
            else:
                folder_name = folder_name
            task_path = f"lo25/{folder_name}/{task}"
            rerun_link = (
                "<a href='https://prismaticprod-gfishbein.elementcapital.msappproxy.net/"
                "snaphub/LinkRunner/AskToRun"
                "?runner=Wave&action=Trigger"
                f"&activity=day/{run_date}/{task_path}'"
                " target='_blank'>Re-run Report</a>"
            )
            home_link = home_link + f"&emsp;{rerun_link}"
        body_content = home_link + body_content
    if title is not None:
        body_content = f"<h1>{title}</h1>" + body_content

    content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            {html_style(_style)}
        </style>
    </head>
    <body>
        {body_content}
    </body>
    </html>
    """
    if path is None:
        return content
    else:
        path = convert_path_to_linux(path)
        with open(path, "w+", encoding="utf-8") as f:
            f.write(content)


if __name__ == "__main__":
    from MD_test import MD_TEST
    from ecm.cmds.core.markdown import MD

    figs = [MD(MD_TEST)]
    to_html(figs, path=r"c:\dev\lo25\test.html", title="Test Report")


