import base64
import inspect
import typing as tp
import webbrowser
from functools import partial
from io import BytesIO
from pathlib import Path

import kaleido  # noqa: F401
import matplotlib
import pandas as pd
import plotly
import plotly.graph_objects as go
import plotly.io as pi
from ecm.cmds.core.pyg import db_address
from matplotlib import pyplot as plt
from matplotlib.axes import SubplotBase
from matplotlib.figure import Figure as mFigure
from plotly.basedatatypes import BaseFigure
from plotly.basedatatypes import BaseTraceType
from plotly.graph_objects import Figure
from pyg_base import as_list
from pyg_base import Dict
from pyg_base import dictable
from pyg_base import dt as pygdt
from pyg_base import is_date
from pyg_base import is_float
from pyg_base import is_ts
from pyg_base import lower
from pyg_base import mkdir
from pyg_base import nona
from pyg_base import ulist
from pyg_base import zipper
from pyg_cell import cell
from pyg_cell import db_cell

from .markdown import Markdown
from .utils import convert_path_to_linux



__all__ = [
    "HTML", "HTM", "filewrite", "table", "JPG", "JPEG",
    "_create_html_table_from_figures", "_figure_to_html_table", "_fig_to_html",
]

ARGSPEC = "fullargspec"


def getargspec(function):
    """
    extends inspect.getfullargspec to perform introspection on extended functions and objects
    inspect will not necessarily respect any overrides that we wish to apply to function signature
    """
    if hasattr(function, ARGSPEC):
        return getattr(function, ARGSPEC)
    else:
        return inspect.getfullargspec(function)


class flist(object):
    def __init__(self, functions, params=None):
        if params is not None:
            assert len(params) == len(functions)
            self.functions = [partial(function, **param) if len(param) else function for function, param in zip(functions, params)]
        else:
            self.functions = functions

    def __repr__(self):
        return "\n then ".join([function.__repr__() for function in self.functions])

    __str__ = __repr__

    @property
    def __doc__(self):
        return "%s" % self

    @property
    def __name__(self):
        return ">".join([getattr(function, "__name__", str(function)) for function in self.functions])

    @property
    def __wrapped__(self):
        return self.functions[0]

    @property
    def fullargspec(self):
        return getargspec(self.functions[0])

    def __call__(self, *args, **kwargs):
        result = self.functions[0](*args, **kwargs)
        for function in self.functions[1:]:
            result = function(result)
        return result


temp_dir = "c:/temp/"


def filename(fn, ext="htm"):
    """filename generator
    >>> assert filename(True, 'csv').endswith('csv')
    >>> assert filename('test', 'git').endswith('test.git')
    """
    if isinstance(fn, str):
        if "." + ext not in fn:
            fn = fn + "." + ext
        if ":" in fn or fn.startswith("//") or fn.startswith("\\"):
            pass
        else:
            fn = temp_dir + fn
        while "//" in fn[2:]:
            fn = fn[:2] + fn[2:].replace("//", "/")
        return fn
    if fn is True:
        t = pygdt.now()
        return temp_dir + t.utcnow().strftime("%Y%m%d_%H%M%S_%f.") + ext
    else:
        raise ValueError("dont know how to convert %s to a filename" % fn)


def _as_title(title=None):
    if isinstance(title, str):
        return go.layout.Title(text=title)
    elif isinstance(title, dict):
        return go.layout.Title(**title)


def _as_xaxis(xaxis=None):
    if isinstance(xaxis, str):
        return go.layout.XAxis(title=go.layout.xaxis.Title(text=xaxis))
    elif isinstance(xaxis, dict):
        return go.layout.XAxis(**xaxis)


def _as_yaxis(yaxis=None):
    if isinstance(yaxis, str):
        return go.layout.YAxis(title=go.layout.yaxis.Title(text=yaxis))
    elif isinstance(yaxis, dict):
        return go.layout.YAxis(**yaxis)


def _as_name(row, name=None):
    if name is None:
        if "_pk" in row:
            return ("%s" % [row[k] for k in row["_pk"]])[1:-1]
        else:
            return "%s" % {k: v for k, v in row.items() if isinstance(v, str)}
    return "%s" % row[name]


def _as_mode(mode, x=None):
    if mode is None:
        mode = "ts" if (len(x) and is_date(x[0])) else "f" if isinstance(x, list) else "xy"
    mode = lower(mode)
    return dict(
        xy="markers", ts="lines", f="lines+markers", func="lines+markers",
        function="lines+markers", m="markers", l="lines", lm="lines+marker", ml="lines+markers",
    ).get(mode, mode)


def _as_values(value):
    if is_ts(value):
        return value.values
    else:
        return value


def _as_output(value, x):
    """
    value is a dict and we determine what keys are being used as output
    """
    if x is None:
        if "output" in value:
            return as_list(value["output"])
        if "data" in x:
            return ["data"]
        else:
            return [key for key, value in value.items() if isinstance(value, (pd.DataFrame, pd.Series))]
    else:
        return as_list(x)


def Fig(data, title=None, xaxis=None, yaxis=None, barmode=None):
    """
    wraps a collection of go.traces in a figure object
    """
    res = go.Figure(data)
    if barmode is not None:
        res.update_layout(barmode=barmode)
    if title is not None:
        res.update_layout(title=_as_title(title))
    if xaxis is not None:
        res.update_layout(xaxis=_as_xaxis(xaxis))
    if yaxis is not None:
        res.update_layout(yaxis=_as_yaxis(yaxis))
    return res


def Scatters(value=None, x=None, y=None, name=None, transform=None, mode=None):
    if isinstance(value, (list, dictable)):
        return sum(
            [Scatters(v, x_, y_, n, t, m)
             for v, x_, y_, n, t, m in zipper(
                 value, x or [None], y or [None], name or [None], transform or [None], mode or [None])],
            [],
        )
    if isinstance(value, pd.core.groupby.generic.DataFrameGroupBy):
        return sum(
            [Scatters(v, x=x, y=y, name=k if name is None else name, transform=transform, mode=mode) for k, v in value],
            [],
        )
    tfm = flist(as_list(transform) + [_as_values])
    if isinstance(value, pd.DataFrame):
        if x is None:
            xvals = value.index
        else:
            xvals = value[x].values
        if y is None:
            cols = [col for col in value.columns if col != x]
        else:
            cols = as_list(y)
        col_names = zip(cols, cols) if name is None else zipper(cols, name)
        mode = _as_mode(mode, xvals)
        df = {col: nona(value[col]) for col in cols}
        return [go.Scatter(x=df[col].index, y=tfm(df[col]), name="%s" % nm, mode=mode) for col, nm in col_names]
    if isinstance(value, pd.Series):
        df = nona(value)
        xvals = df.index
        mode = _as_mode(mode, xvals)
        return [go.Scatter(x=xvals, y=tfm(df), name="%s" % name, mode=mode)]
    if isinstance(value, tuple) and len(value) == 2:
        xvals = value[0]
        mode = _as_mode(mode, xvals)
        return [go.Scatter(x=xvals, y=tfm(value[1]), name="%s" % name, mode=mode)]
    if isinstance(value, dict):
        xvals = value[x]
        if isinstance(xvals, (pd.DataFrame, pd.Series)):
            return Scatters(value=xvals, x=None, y=y, name=_as_name(value, name), transform=transform, mode=mode)
        else:
            mode = _as_mode(mode, xvals)
            return [go.Scatter(x=xvals, y=tfm(value[i]), name=_as_name(value, name), mode=mode) for i in _as_output(value, y)]
    elif value is None:
        mode = _as_mode(mode, x)
        return [go.Scatter(x=x, y=tfm(y), name=name, mode=mode)]
    else:
        raise ValueError("cannot handle this value %s" % type(value))


def Scatter(value=None, x=None, y=None, name=None, transform=None, mode=None,
            title=None, xaxis=None, yaxis=None):
    """
    An all-purpose XY or timeseries scatter plot based on Plotly.
    Parameters
    ----------
    :params value:
    value can be multiple things:
        1) a list will create multiple scatters
        2) a df.groupby object will create multiple scatters named by groupby keys
        3) a df will create a multiple scatter per column.
            use y = colname(s) to restrict to specific cols
        4) a series will create a single scatter
        5) a 2-tuple will plot x vs y
    or you can use x and y as you would normally do in a normal go.Scatter

    :param x,y:
    x, y can be column names if value is a DataFrame or a dict.

    :param name:
    name overrides column name if value is DataFrame but
    can also be used as the key name if a dict is provided

    :param transform:
    A function, or a list of functions that transforms the original data.

    :param mode: you can use plotly's 'm(arkers)', 'markers+lines' or
    'l(ines)' or 'ts' vs 'xy' vs 'f/func/function' instead. If left None,
    it will usually default to lines if x are dates, otherwise will use markers

    :params title, xaxis, yaxis: These are related to Figure() object and
    are explained in Fig() function

    Examples
    --------
    import numpy as np; import pandas as pd
    from core.timeseries import *
    from core.base import *
    from core.data.out import Scatter
    from functools import partial

    df = pd.Series(np.random.normal(0,1,1000), drange(-999))
    Scatter(df)
    Scatter(df, transform = cumsum)
    Scatter([df], transform = [cumsum, [cumsum, partial(ewma, days = 30)]], name = ['raw','ewma'])

    ts = pd.DataFrame(np.random.normal(0,1,(1000,3)), index = drange(-999), columns = ['a','b','c'])
    Scatter(ts, y = ['a', 'b'])
    Scatter(ts, x = 'a', y = 'b')
    ts['contract'] = ['TYM9'] * 500 + ['TYZ9'] * 500
    Scatter(ts.groupby('contract'), y = 'a', transform = cumsum)

    xy = pd.DataFrame(np.random.normal(0,1,(1000,5)), columns = list('abcde'))
    xy['gender'] = ['male'] * 500 + ['female'] * 500
    Scatter(xy)
    Scatter(xy, x = 'a', y = ['b','c'])
    Scatter(xy.groupby('gender'), x = 'a', y = 'b')

    x = np.arange(-4,4,0.1)
    Scatter(x = x, y = x, transform = np.sin)
    Scatter(value = [None], x = [x], y = [x], transform = [np.sin, np.cos],
    name = ['sin','cos'], mode = 'function')

    """
    return Fig(Scatters(value=value, x=x, y=y, name=name, transform=transform, mode=mode),
               title=title, xaxis=xaxis, yaxis=yaxis)


class hstr(str):
    def _repr_html_(self):
        return self


def _fn(path, ext):
    if not isinstance(path, str):
        return path
    res = filename(path, ext)
    mkdir(res)
    return res


def _add(path=None, subdir=None):
    if not isinstance(path, str):
        return path
    else:
        "%s/%s" % (path, subdir)


def _depth(depth):
    return depth - 1 if isinstance(depth, int) and depth > 0 else depth


def _html(fn=None):
    return _fn(fn, "htm")


def _png(fn=None):
    return _fn(fn, "png")


IMG = '<img src="%s">'
HREF = '<a href="%(link)s">%(text)s</a>'


def _fig_to_html(fig, fmt="png", path=None, width=None):
    """
    converts a plotly or a matplotlib figure into a static html plot
    """
    if path is not None:
        if isinstance(fig, BaseTraceType):
            fig = Figure(fig)
        if isinstance(fig, SubplotBase):
            fig = fig.figure
        if isinstance(fig, matplotlib.figure.Figure):
            fn = _png(path)
            fig.savefig(fn)
            return IMG % fn
        elif isinstance(fig, (mFigure, BaseFigure)):
            fn = _png(path)
            fig.write_image(fn)
            return IMG % fn
        else:
            return fig

    if isinstance(fig, mFigure):
        tmpfile = BytesIO()
        fig.savefig(tmpfile, format=fmt)
        bits = tmpfile.getvalue()
    elif isinstance(fig, BaseFigure):
        bits = fig.to_image(format=fmt, engine="kaleido")
    elif isinstance(fig, BaseTraceType):
        bits = Figure(fig).to_image(format=fmt, width=width, engine="kaleido")
    encoded = base64.b64encode(bits).decode("utf8") if isinstance(bits, bytes) else bits
    return "<img src='data:image/{};base64,{}'>".format(fmt, encoded)


def _create_html_table_from_figures(
    figs: tp.Union[go.Figure, str, tp.List[tp.Union[str, go.Figure]]],
    num_columns: int = 2, email_mode=False, width=None,
):
    raw_html = ""
    rows = [(figs[i : i + num_columns]) for i in range(0, len(figs), num_columns)]  # noqa: E203
    raw_html += "<table style='width:auto'>\n<tbody>"
    for row in rows:
        html_figs = []
        for data in row:
            if isinstance(data, list):
                for d in data:
                    html_figs.append(_fig_to_html(d) if email_mode else d.to_html(full_html=False))
            else:
                if not isinstance(data, str):
                    html_figs.append(_fig_to_html(data) if email_mode or isinstance(data, str) else data.to_html(full_html=False))
                else:
                    html_figs.append(data)
        html_row = "<tr>" + "".join([(f"<td>{fig}</td>") for fig in html_figs]) + "</tr>\n"  # noqa: E501
        raw_html += html_row
    raw_html += "</tbody>\n</table>"
    return raw_html


def _figure_to_html_table(
    figs: tp.Union[go.Figure, str, tp.List[tp.Union[str, go.Figure]]],
    filename: str | None = None, num_columns: int = 2,
    email_mode: bool = False, width=None,
):
    """Writes a html file of figures as a table

    Args:
        figs (tp.Union[go.Figure, str, tp.List[tp.Union[str, go.Figure]]]):
            The list of plotly figures
        filename (str, optional): The output path of the html file. Defaults to "dashboard.html".
        num_columns (int, optional): Number of columns in the table. Defaults to 2.
    """
    if not isinstance(figs, list):
        figs = [figs]
    raw_html = ""
    raw_html += "<html><head></head><div><style>table {margin: 10px;}</style></div><body>" + "\n"
    raw_html += _create_html_table_from_figures(figs, num_columns, email_mode, width)
    raw_html += "</body></html>" + "\n"
    if filename:
        filename_ = convert_path_to_linux(filename)
        file_path = Path(filename_)
        Path.mkdir(file_path.parent, parents=True, exist_ok=True)
        with open(filename, "w", encoding="utf-8") as dashboard:
            dashboard.write(raw_html)
    return raw_html


def _div_row(row):
    return "<div class='row'>%s</div>" % ("\n".join(["<div class='column'>%s</div>" % v for v in row]))


def _div_col(col):
    return "<div class='col'>%s</div>" % ("\n".join(["<div class='row'>%s</div>" % v for v in col]))


def _tbl_row(row):
    return "<table><tr>%s</tr></table>" % ("\n".join(["<td>%s</td>" % v for v in row]))


def _tbl_col(col):
    return "<table>%s</table>" % ("\n".join(["<tr><td>%s</td></tr>" % v for v in col]))


def _dictable_to_div_table(value, mode="plotly", path=None, depth=1):
    n = len(value)
    keys = value.keys()
    body = {k: [_raw_html_div(v[i], mode=mode, path=_add(_add(path, k), i), depth=_depth(depth)) for i in range(n)] for k, v in value.items()}
    res = "\n".join([_div_row(keys)] + [_div_row(row) for row in zip(*body.values())])
    return res


def address2path(value):
    address = db_address(value)
    if address[0] is None:
        return "/".join(["%s/%s" % (k, v) for k, v in zip(*address[-2:])])
    else:
        return "/".join([address[0][0]] + list(address[1:-2]) + ["%s/%s" % (k, v) for k, v in zip(*address[-2:])])


def is_db_able(value):
    return isinstance(value, db_cell) and None not in db_address(value)[-1]


def is_matplot(value):
    return isinstance(value, SubplotBase)


def _db_cell_to_html(value, mode="plotly", path=None, depth=1):
    """
    value = get_cell('markets', ticker = 'TYA Comdty', item = 'z')
    """
    cols = ulist(value.get("_pk", [])) + value.get("output", [])
    d = Dict(value)[cols]
    if path is None or depth == 0:
        return _raw_html_div(d, mode=mode, path=path, depth=depth)
    else:
        subdir = address2path(db_address(value))
        inputs = value._inputs
        res = to_html(inputs, path, auto_play=False, mode=mode, path=_add(path, subdir), depth=_depth(depth))
        link = filewrite(res, fn=path, auto_play=False, ext="htm")
        return HREF % dict(text=subdir, link=link)


def _plot(value, mode=None, **kwargs):
    if mode == "plotly":
        return Scatter(value, **kwargs)
    else:
        if isinstance(mode, dict):
            kwargs.update(mode)
        plt.figure()
        return value.plot(**kwargs)


class table(pd.DataFrame):
    pass


def _raw_html_div(value, mode="plotly", path=None, depth=1, cols: int = 1):
    """
    converts values to raw html, no div or saving as a file
    We start by converting a timeseries to a plotly/matplotlib figure
    """
    if isinstance(value, table):
        return value.to_html().replace('class="dataframe"', "")
    if isinstance(value, Markdown):
        return value.to_html()
    if isinstance(value, BaseTraceType) and not isinstance(value, Figure):
        value = Figure(value)
    if is_ts(value):
        value = _plot(value, mode)
    if is_matplot(value):
        return _fig_to_html(value.figure, path=path)
    elif is_db_able(value):
        return _db_cell_to_html(value, mode=mode, path=path, depth=depth)
    elif isinstance(value, cell):
        cols = ulist(value.get("_pk", [])) + value.get("output", [])
        value = Dict(value)[cols]
        return _raw_html_div(value, mode=mode, path=path, depth=depth)
    elif isinstance(value, matplotlib.figure.Figure):
        return _fig_to_html(value, path=path)
    elif isinstance(value, pd.DataFrame):
        return value.to_html().replace('class="dataframe"', "")
    elif isinstance(value, dictable):
        return _dictable_to_div_table(value, mode=mode, path=path, depth=depth)  # converts the internals [comment clipped]
    elif isinstance(value, dict):
        return _dictable_to_div_table(dictable({k: [v] for k, v in value.items()}), mode=mode, path=path, depth=depth)
    elif isinstance(value, Figure):
        if mode in ("plotly", "plotly_table", "i", "interactive"):
            if mode == "plotly_table":
                return _figure_to_html_table(value, path, cols)
            else:
                return pi.to_html(value, auto_play=False, full_html=False)
        else:
            return _fig_to_html(value, path=path)
    elif hasattr(value, "to_html"):
        return value.to_html()
    elif hasattr(value, "_repr_html_"):
        return value._repr_html_()
    elif is_float(value):
        return "%1.4f" % value
    elif isinstance(value, list):
        return _div_col([_raw_html_div(value[i], mode, path=_add(path, i), depth=_depth(depth)) for i in range(len(value))])
    elif isinstance(value, tuple):
        return _div_row([_raw_html_div(value[i], mode, path=_add(path, i), depth=_depth(depth)) for i in range(len(value))])
    else:
        return "%s" % value


def _raw_html_tbl(value, mode: str = "plotly", path: str = None, depth: int = 1, cols: int = 1):
    """
    converts values to raw html, no div or saving as a file
    We start by converting a timeseries to a plotly/matplotlib figure
    """
    if isinstance(value, table):
        return value.to_html().replace('class="dataframe"', "")
    if isinstance(value, Markdown):
        return value.to_html()
    if isinstance(value, BaseTraceType) and not isinstance(value, Figure):
        value = Figure(value)
    if isinstance(value, cell):
        cols = ulist(value.get("_pk", [])) + value.get("output", [])
        value = Dict(value)[cols]
    if is_ts(value) and len(value):
        value = _plot(value, mode)
    if is_matplot(value):
        return _fig_to_html(value.figure, path=path)
    elif isinstance(value, matplotlib.figure.Figure):
        return _fig_to_html(value, path=path)
    elif isinstance(value, pd.DataFrame):
        return value.to_html().replace('class="dataframe"', "")
    elif isinstance(value, dictable):
        return value.do(lambda v: _raw_html_tbl(v, mode, path=path, depth=_depth(depth))).to_html()  # [comment clipped]
    elif isinstance(value, dict):
        return dictable({k: _raw_html_tbl(v, mode, path=path, depth=_depth(depth)) for k, v in value.items()}).to_html()
    elif isinstance(value, plotly.graph_objs._figure.Figure):
        if mode in ("plotly", "plotly_table", "i", "interactive"):
            if mode == "plotly_table":
                return _figure_to_html_table(value, path, cols)
            else:
                return pi.to_html(value, auto_play=False, full_html=False)
        else:
            return _fig_to_html(value, path=path)
    elif hasattr(value, "to_html"):
        return value.to_html()
    elif hasattr(value, "_repr_html_"):
        return value._repr_html_()
    elif is_float(value):
        return "%1.4f" % value
    elif isinstance(value, list):
        return _tbl_col([_raw_html_tbl(v, mode, path=path, depth=_depth(depth)) for v in value])
    elif isinstance(value, tuple):
        return _tbl_row([_raw_html_tbl(v, mode, path=path, depth=_depth(depth)) for v in value])
    else:
        return "%s" % value


def filewrite(value, fn=True, ext="htm", auto_play=False):
    _filename = _fn(fn, ext)
    _filename = convert_path_to_linux(_filename)
    with open(_filename, "w") as f:
        f.write(value)
    if auto_play:
        webbrowser.open(_filename)
    return _filename


_top = """
<html>
<style>
.page {
  margin: 15px;
}

.row {
  display: flex;
  flex-direction: row;
  flex-wrap: wrap;
  width: 100%;
}

.column {
  display: flex;
  flex-direction: column;
  flex-basis: 100%;
  flex: 1;
}
.markdown table { border-collapse: collapse; }
.markdown th, .markdown td { border: 1px solid #ddd; padding: 6px; }
.markdown pre { padding: 8px; overflow-x: auto; }
</style>
<body>"""

_bottom = """
</body>
</html>
"""


def to_html(value, fn=True, auto_play=True, mode="plotly", div=True, path=None, depth=1, cols: int = 2):
    """
    mode = 'plotly', 'plotly_table', 'static' and 'email'
    """
    if mode == "email":
        depth = 0
    body = _raw_html_div(value, mode=mode, path=path, depth=depth, cols=cols) if div else _raw_html_tbl(value, mode=mode, path=path, depth=depth, cols=cols)
    page = _top + body + _bottom
    if fn is False:
        return page if mode == "email" else hstr(page)
    else:
        return filewrite(page, fn, ext="htm", auto_play=auto_play)


HTML = to_html
HTM = partial(to_html, fn=False)
JPG = partial(to_html, mode="static", fn=False)
JPEG = partial(to_html, mode="static")
