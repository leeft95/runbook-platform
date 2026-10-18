import ecm.cmds.table as table
from tqdm.contrib.concurrent import thread_map
import pandas as pd
from tshistory.api import timeseries
import ecm.cmds.chart as chart
from ecm.cmds.config import html_path
import sys
import os
import plotly.graph_objects as go
import plotly.express as px

if sys.platform.startswith("win"):
    os.environ["GRPC_DEFAULT_SSL_ROOTS_FILE_PATH"] = r"C:\local\certs\root.crt"
    os.environ["REQUESTS_CA_BUNDLE"] = r"C:\local\certs\root.crt"
    os.environ["SSL_CERT_FILE"] = r"C:\local\certs\root.crt"

tsa = timeseries('https://lo25.wagyu.elementcapital.corp/tsh/api')


def _missing_photo_text(lines, *visible_fragments):
    raise NotImplementedError(f"Transcription gap in crude_balance_forecast.py, photographed lines {lines}")


def history_weekly(tsa, name, from_insertion_date=None, to_insertion_date=None):
    insertion_dates = tsa.insertion_dates(name)
    default_insertion_date = max(pd.Timestamp.now(tz='UTC') - pd.DateOffset(days=100), insertion_dates[0])
    from_insertion_date = from_insertion_date or default_insertion_date
    to_insertion_date = insertion_dates[-1]
    a_range = pd.date_range(from_insertion_date, to_insertion_date + pd.DateOffset(days=7), freq='W-FRI').floor('D')
    def try_get(name, i):
        try:
            return tsa.get(name, revision_date=i)
        except:
            return pd.Series(pd.NA, tsa.get(name).index)
    return pd.concat(list(map(lambda i: try_get(name, i).rename(i), a_range)), axis=1).dropna(axis=1, how='all')


def plot_value_by_vintage_plotly(df: pd.DataFrame, title='', freq_value: str='Q', freq_value_agg='mean', freq_vintage=None):
    palette = px.colors.qualitative.Dark24
    fig = go.Figure().update_layout(colorway=palette)
    freqs = {'D': '%d-%m', 'W-FRI': '%d-%m', 'M': '%b-%y', 'Q': 'Q%q-%y', 'Y': '%y'}
    df_plot = df.copy()
    df_plot.index = pd.to_datetime(df_plot.index).to_period(freq_value).strftime(freqs[freq_value])
    df_plot.columns = pd.to_datetime(df_plot.columns).to_period(freq_vintage if freq_vintage is not None else _missing_photo_text('36: freq_vintage default')).end_time
    df_plot = df_plot.groupby(level=0, axis=1, sort=False).last().groupby(level=0, axis=0, sort=False).agg(freq_value_agg)
    df_transposed = df_plot.T
    fig = go.Figure()
    for i, col in enumerate(df_transposed.columns):
        color = palette[i % len(palette)]
        fig.add_trace(go.Scatter(x=df_transposed.index, y=df_transposed[col], mode='lines+markers',
                                 name=str(col.date()) if hasattr(col, 'date') else str(col),
                                 line=dict(color=color), marker=dict(color='white', line=dict(color=color, width=2), size=8)))
    fig.update_layout(title_xanchor="left", title_x=0.06, plot_bgcolor="white",
                      title=f'{title} - forecast evolution'.replace("&nbsp;", ""),
                      xaxis_title="forecast date", legend_title="value date", yaxis_title='',
                      template='plotly_white', margin=dict(l=5, r=5, t=30, b=20))
    fig.update_yaxes(mirror=True, ticks="outside", showline=True, linecolor="black", zerolinecolor="black",
                     zerolinewidth=0.5, gridcolor="lightgrey")
    fig.update_xaxes(mirror=True, ticks="outside", showline=True, linecolor="black", gridcolor="lightgrey")
    return fig


def plot_value_by_year(series: pd.DataFrame, title='', freq_value: str='Q', freq_value_agg='mean'):
    palette = px.colors.qualitative.Dark24
    fig = go.Figure().update_layout(colorway=palette)
    if freq_value == 'Q':
        df_plot = _missing_photo_text('96: aggregation tail', series.groupby([series.index.year, [f'Q{p:01}' for p in series.index.quarter]]).agg(freq_value_agg))
    if freq_value == 'H':
        df_plot = _missing_photo_text('98: aggregation tail', series.groupby([series.index.year, [f'H{((p % 2) + 1):01}' for p in series.index.quarter]]))
    if freq_value == 'Y':
        df_plot = series.groupby(series.index.year).agg(freq_value_agg).rename('CAL').to_frame()
    if freq_value == 'M':
        df_plot = _missing_photo_text('102: aggregation tail', series.groupby([series.index.year, [f'M{p:02}' for p in series.index.month]]).agg(freq_value_agg))
    df_transposed = df_plot
    fig = go.Figure()
    for i, col in enumerate(df_transposed.columns):
        color = palette[i % len(palette)]
        fig.add_trace(go.Scatter(x=df_transposed.index, y=df_transposed[col], mode='lines+markers',
                                 name=str(col.date()) if hasattr(col, 'date') else str(col),
                                 line=dict(color=color), marker=dict(color='white', line=dict(color=color, width=2), size=8)))
    fig.update_layout(title=f'{title}'.replace("&nbsp;", ""), xaxis_title="year", legend_title="maturity",
                      yaxis_title='', template='plotly_white', plot_bgcolor="white", margin=dict(l=5, r=5, t=30, b=20))
    fig.update_yaxes(mirror=True, ticks="outside", showline=True, linecolor="black", zerolinecolor="black",
                     zerolinewidth=0.5, gridcolor="lightgrey")
    fig.update_xaxes(mirror=True, ticks="outside", showline=True, linecolor="black", gridcolor="lightgrey")
    return fig


def crude_bal(data, line_items_dict, freq='M', start_date=None, end_date=None, format_row=None, agg_dict=None, curr=None, yy=False, header=None):
    if agg_dict is None:
        _data = data.asfreq('D').ffill(limit=30).resample(freq).mean()
    else:
        _data = data.asfreq('D').ffill().resample(freq).agg(agg_dict)
    if yy:
        offset = {'M': 12, 'Q': 4, 'A': 1}
        _data = _data.diff(offset[freq])
    last_update = tsa.insertion_dates(line_items_dict[list(line_items_dict.keys())[0]])[-1]
    start_date = start_date or pd.Timestamp.now() - pd.DateOffset(days=365)
    a_range = pd.date_range(start_date, end_date or pd.Timestamp('2026-01-01'), freq='D').floor('D')
    resampled_data = _data.copy()[a_range[0]:a_range[-1]]
    freq_dict = {'M': '%b-%y', 'Q': 'Q%q-%y', 'A': 'C%y'}
    resampled_data.index = resampled_data.index.to_period(freq).strftime(freq_dict[freq])
    filtered_resampled_data = resampled_data.T.reset_index()
    filtered_resampled_data.rename(columns={"index": "kb/d"}, inplace=True)
    curr = pd.Period(pd.Timestamp.now() or curr, freq=freq).strftime(freq_dict[freq])
    column_format = {'kb/d': {"right_border": True, 'text-align': 'left', 'width': '200px'},
                     **{k: {'width': '60px'} for k in filtered_resampled_data.columns if k not in ('kb/d', curr)},
                     curr: {"left_border": True, "right_border": True, 'width': '50px'}}
    _format_row = format_row or {}
    html_table = table.html_format(filtered_resampled_data, header=header or f"ECM crude balance, kb/d",
                                   footer=f"Last updated {last_update:%d-%m %H:%m}", format_column=column_format,
                                   format_row=_format_row, precision=0, show_date=True)
    return html_table


line_items = {
    'World crude/condensate production': 'element.crude_condensate.world.supply.kbd.monthly.forecast',
    '&nbsp;&nbsp;US crude/cond': 'element.crude_condensate.united_states.supply.kbd.monthly.forecast',
    '&nbsp;&nbsp;Russia crude': 'element.crude.russia.supply.kbd.monthly.forecast',
    '&nbsp;&nbsp;Kaz': 'element.crude.kazakhstan.supply.kbd.monthly.forecast',
    '&nbsp;&nbsp;OPEC V8 crude': 'element.crude.opec_plus.opec_8.voluntary_crew.supply.kbd.monthly.forecast',
    '&nbsp;&nbsp;Saudi crude': 'element.crude.opec.saudi_arabia.supply.kbd.monthly.forecast',
    '&nbsp;&nbsp;Venz crude': 'element.crude.opec.venezuela.supply.kbd.monthly.forecast',
    '&nbsp;&nbsp;Iran crude': 'element.crude.opec.iran.supply.kbd.monthly.forecast',
    'World runs': 'element.crude_oil.world.refinery_runs.monthly.forecast',
    '&nbsp;&nbsp;US runs': 'element.crude_oil.united_states.refinery_runs.monthly.forecast',
    '&nbsp;&nbsp;China runs': 'element.crude_oil.china.refinery_runs.monthly.forecast',
    '&nbsp;&nbsp;OECD Europe runs': 'element.crude_oil.oecd_europe.refinery_runs.kbd.monthly.forecast',
    '&nbsp;&nbsp;Russian runs': 'energy_aspects.crude_oil.fsu.russia.refinery_runs_in_russia_in_kb_d.kbbl_d.month' + _missing_photo_text("197: ticker suffix"),
    'Burns': 'element.crude_oil.world.burn.kbd.monthly',
    'Balance': 'element.crude_oil.world.implied_balance.kbd.monthly.forecast',
    '&nbsp;&nbsp;US balance': 'energy_aspects.crude_oil.na.us.implied_balance.kbbl_d.monthly.forecast',
    'Kpler observed': 'kpler.crude_oil.world.balance.kbd.monthly',
    'Implied onshore builds ex. China': 'element.crude_oil.world.onshore_ex_china.kbd.monthly.forecast',
    'China stockbuilds': 'kpler.crude_oil.china.stock_change.kbd.daily.forecast',
    'Benchmark on water': 'kpler.crude_oil.benchmark.on_the_water.kbd.monthly',
    'Sanctioned on water': 'kpler.crude_oil.sanctioned.on_the_water.kbd.monthly',
    '&nbsp;&nbsp;Venezuela': 'kpler.crude_oil.venezuela.on_the_water.kbd.monthly',
    '&nbsp;&nbsp;Iran': 'kpler.crude_oil.iran.on_the_water.kbd.monthly',
    '&nbsp;&nbsp;Russia': 'kpler.crude_oil.russia.on_the_water.kbd.monthly',
    'Inventories world ex China forecast': 'element.crude_oil.world_ex_china.onshore_ending_stocks.kb.monthly.forecast',
    'Sanctioned on water forecast': 'kpler.crude.sanctioned.oil_on_water.kb.monthly.forecast',
}


def generate_report():
    data = pd.concat(thread_map(tsa.get, line_items.values(), max_workers=10), axis=1).rename(columns={v: k for k, v in line_items.items()})
    format_row = {
        0: {"bottom_border": True, "top_border": True, "bold": True},
        8: {"bottom_border": True, "top_border": True, "bold": True},
        14: {"bottom_border": True, "top_border": True, "bold": True},
        16: {"bottom_border": True, "top_border": True, "bold": True},
        17: {"bottom_border": True, "top_border": True, "bold": True},
        19: {"bottom_border": True, "top_border": True, "bold": True},
        20: {"bottom_border": True, "top_border": True, "bold": True},
    }
    format_rowyy = {
        0: {"bottom_border": True, "top_border": True, "bold": True},
        8: {"bottom_border": True, "top_border": True, "bold": True},
    }
    start_date = pd.Timestamp.now().floor('D').replace(day=1) - pd.DateOffset(days=45)
    start_date_quarter = start_date.to_period('Q').start_time
    monthly = crude_bal(data.iloc[:, :-1], line_items, 'M', start_date=start_date - pd.DateOffset(months=2), end_date=_missing_photo_text("233: pd.Timestamp... call suffix"))
    quarterly = crude_bal(data.iloc[:, :-1], line_items, 'Q', start_date=start_date - pd.DateOffset(months=2), end_date=_missing_photo_text("235: pd.Timestamp... call suffix"))
    annual = crude_bal(data.iloc[:, :-1], line_items, 'A', start_date=pd.Timestamp('20180101'), end_date=_missing_photo_text("237: pd.Timestamp... call suffix"))
    monthlyyy = crude_bal(data.iloc[:, :-10], line_items, 'M', start_date=start_date - pd.DateOffset(months=2), end_date=_missing_photo_text("240: pd.Timestamp... call suffix"))
    quarterlyyy = crude_bal(data.iloc[:, :-10], line_items, 'Q', start_date=start_date - pd.DateOffset(months=3), end_date=_missing_photo_text("242: pd.Timestamp... call suffix"))
    annualyy = crude_bal(data.iloc[:, :-10], line_items, 'A', start_date=pd.Timestamp('20180101'), end_date=_missing_photo_text("244: pd.Timestamp... call suffix"))
    date_range = (data.index >= pd.Timestamp.now() - pd.DateOffset(months=48)) & (data.index <= _missing_photo_text('246: pd.Timestamp... date bound'))
    col_range = {
        'Balance': 'element.crude_oil.world.implied_balance.kbd.monthly.forecast',
        'Kpler observed': 'kpler.crude_oil.world.balance.kbd.monthly',
        'Implied onshore builds ex. China': 'element.crude_oil.world.onshore_ex_china.kbd.monthly.forecast',
        'China stockbuilds': 'kpler.crude_oil.china.stock_change.kbd.daily.forecast',
        'Benchmark on water': 'kpler.crude_oil.benchmark.on_the_water.kbd.monthly',
        'Sanctioned on water': 'kpler.crude_oil.sanctioned.on_the_water.kbd.monthly',
    }
    onshore = tsa.get('element.crude_oil.world_ex_china.onshore_ending_stocks.kb.daily.forecast')['2022':]
    sanctioned = tsa.get('kpler.crude.sanctioned.oil_on_water.kb.daily.forecast')['2022':]
    oow = tsa.get('kpler.crude.world.oil_on_water.kb.daily.forecast')['2019':]
    chinese_stocks = tsa.get('kpler.crude_oil.china.ending_stocks.kb.daily.forecast')['2020':]
    us_stocks = tsa.get('element.crude_oil.united_states.doe_commercial_stocks.kb.weekly.forecast')['2022':]
    ex_china_us_stocks = _missing_photo_text('261: ticker/call/date slice tail', 'element.crude_oil.world_ex_china_ex_us.onshore_ending_stocks.kb.daily.fore')
    width = 700
    dash_from = pd.Timestamp.today().floor('D') + pd.DateOffset(days=1)
    fig_onshore = chart.seasonal_chart(onshore.to_frame(), start=onshore.index[0], end=onshore.index[-1],
                                          dash_name='forecast', dash_from=dash_from, title='Onshore crude inventories world ex-China, mb', width=width,
                                          theme='simple_white')
    fig_sanctioned = chart.seasonal_chart(sanctioned.to_frame(), start=sanctioned.index[0], end=sanctioned.index[-1],
                                          dash_name='forecast', dash_from=dash_from, title='Sanctioned crude on water, mb', width=width,
                                          theme='simple_white')
    fig_oow = chart.seasonal_chart(oow.to_frame(), start=oow.index[0], end=oow.index[-1],
                                          dash_name='forecast', dash_from=dash_from, title='Crude on water, mb', width=width,
                                          theme='simple_white', ex2020=False)
    fig_china = chart.seasonal_chart(chinese_stocks.to_frame(), start=chinese_stocks.index[0], end=chinese_stocks.index[-1],
                                          dash_name='forecast', dash_from=dash_from, title='Chinese crude inventories, mb', width=width,
                                          theme='simple_white', ex2020=False)
    fig_us = chart.seasonal_chart(us_stocks.to_frame(), start=us_stocks.index[0], end=us_stocks.index[-1],
                                          dash_name='forecast', dash_from=dash_from, title='US crude inventories, mb', width=width,
                                          theme='simple_white', ex2020=False)
    fig_ex_us_ex_china = chart.seasonal_chart(ex_china_us_stocks.to_frame(), start=ex_china_us_stocks.index[0], end=ex_china_us_stocks.index[-1],
                                          dash_name='forecast', dash_from=dash_from, title='Ex-China & Ex-US crude inventories, mb', width=width,
                                          theme='simple_white', ex2020=False)
    df = monthly
    bar_cols = list(col_range.keys())[-4:]
    line_cols = list(col_range.keys())[:2]

    def generate_chart_stacked_with_lines(df, bar_cols, line_cols):
        fig = go.Figure()
        palette = px.colors.qualitative.Set1  # list of rgb strings
        palette2 = px.colors.qualitative.Dark24[5:]  # list of rgb strings
        for i, col in enumerate(bar_cols):
            fig.add_trace(go.Bar(x=df.index, y=df[col], name=col,
                                 marker=dict(color=palette[i], line=dict(color="black", width=1))))
        for j, col in enumerate(line_cols):
            color = palette2[j]
            fig.add_trace(go.Scatter(x=df.index, y=df[col], name=col, mode="lines+markers",
                                     line=dict(color=color, width=4),
                                     marker=dict(color="white",  # fill
                                                 line=dict(color=color, width=2),  # contour same as line
                                                 size=8)))
        fig.update_layout(title='Crude balance onshore/offshore + benchmark/sanctioned, kb/d',
                          barmode="relative", xaxis_title="Date", template="simple_white", width=1400)
        fig.update_yaxes(title_text="kb/d", zeroline=True, zerolinewidth=1)
        return fig
    fig_balance = generate_chart_stacked_with_lines(data[date_range], bar_cols, line_cols)
    refineries = [
        "iir.crude.turkey.aegean_aliaga_star_ege_refinery.total_outage.kbd.daily",
        "iir.crude.turkey.izmir_refinery.total_outage.kbd.daily",
        "iir.crude.turkey.izmit_refinery.total_outage.kbd.daily",
        "iir.crude.poland.plock_refinery.total_outage.kbd.daily",
        "iir.crude.belgium.antwerp_refinery.total_outage.kbd.daily",
        "iir.crude.belgium.antwerpen_refinery.total_outage.kbd.daily",
        "iir.crude.norway.mongstad_refinery.total_outage.kbd.daily",
        "iir.crude.sweden.preemraff_lysekil_refinery.total_outage.kbd.daily",
        "iir.crude.spain.bilbao_refinery.total_outage.kbd.daily",
        "iir.crude.greece.corinth_refinery.total_outage.kbd.daily",
        "iir.crude.france.donges_refinery.total_outage.kbd.daily",
        "iir.crude.france.gonfreville_refinery_normandie.total_outage.kbd.daily",
        "iir.crude.france.notredamedegravenchon_refinery.total_outage.kbd.daily",
        "iir.crude.france.petroineos_lavera_refinery.total_outage.kbd.daily",
        "iir.crude.italy.saras_refinery.total_outage.kbd.daily",
        "iir.crude.italy.milazzo_refinery.total_outage.kbd.daily",
        "iir.crude.italy.augusta_refinery.total_outage.kbd.daily",
        "iir.crude.netherlands.bp_rotterdam_refinery.total_outage.kbd.daily",
        "iir.crude.netherlands.pernis_refinery.total_outage.kbd.daily",
        "iir.crude.finland.porvoo_refinery.total_outage.kbd.daily",
        "iir.crude.portugal.sines_refinery.total_outage.kbd.daily",
        "iir.crude.germany.leuna_refinery.total_outage.kbd.daily",
        "iir.crude.germany.miro_refinery_karlsruhe.total_outage.kbd.daily",
        "iir.crude.germany.schwedt_refinery.total_outage.kbd.daily",
        "iir.crude.united_kingdom.fawley_refinery.total_outage.kbd.daily",
        "iir.crude.united_kingdom.pembroke_refinery.total_outage.kbd.daily",
        "iir.crude.united_states.bayway_refinery.total_outage.kbd.daily",
        "iir.crude.united_states.paulsboro_refinery_pbf.total_outage.kbd.daily",
        "iir.crude.united_states.trainer_refinery.total_outage.kbd.daily",
        "iir.crude.united_states.baton_rouge_refinery.total_outage.kbd.daily",
        "iir.crude.united_states.baytown_refinery.total_outage.kbd.daily",
        "iir.crude.united_states.beaumont_refinery.total_outage.kbd.daily",
        "iir.crude.united_states.corpus_christi_refinery_east_flint_hills.total_outage.kbd.daily",
        "iir.crude.united_states.corpus_christi_refineryeast.total_outage.kbd.daily",
        "iir.crude.united_states.corpus_christi_refinery_west_flint_hills.total_outage.kbd.daily",
        "iir.crude.united_states.deer_park_refinery.total_outage.kbd.daily",
        "iir.crude.united_states.galveston_bay_refinery_gbr.total_outage.kbd.daily",
        "iir.crude.united_states.galveston_crude_refinery.total_outage.kbd.daily",
        "iir.crude.united_states.garyville_refinery.total_outage.kbd.daily",
        "iir.crude.united_states.houston_refinery_houston_refining.total_outage.kbd.daily",
        "iir.crude.united_states.houston_refinery_valero.total_outage.kbd.daily",
        "iir.crude.united_states.lake_charles_refinery_calcasieu.total_outage.kbd.daily",
        "iir.crude.united_states.lake_charles_refinery_citgo.total_outage.kbd.daily",
        "iir.crude.united_states.lake_charles_refinery_phillips.total_outage.kbd.daily",
        "iir.crude.united_states.norco_refinery.total_outage.kbd.daily",
        "iir.crude.united_states.port_arthur_refinery_motiva.total_outage.kbd.daily",
        "iir.crude.united_states.port_arthur_refinery_totalenergies.total_outage.kbd.daily",
        "iir.crude.united_states.port_arthur_refinery_valero.total_outage.kbd.daily",
        "iir.crude.united_states.sweeny_refinery.total_outage.kbd.daily",
        "iir.crude.united_states.texas_city_refinery_bay_plant.total_outage.kbd.daily",
        "iir.crude.united_states.texas_city_refinery.total_outage.kbd.daily",
        "iir.crude.kuwait.mina_alahmadi_refinery.total_outage.kbd.daily",
        "iir.crude.kuwait.mina_abdulla_refinery.total_outage.kbd.daily",
        "iir.crude.kuwait.mina_al_zour_refinery.total_outage.kbd.daily",
        "iir.crude.saudi_arabia.yanbu_yasref_refinery.total_outage.kbd.daily",
        "iir.crude.saudi_arabia.al_jubail_satorp_refinery.total_outage.kbd.daily",
        "energy_aspects.oil_products.afr.nigeria.monthly_refinery_total_outages_for_cdu_units_in_nigeria_in" + _missing_photo_text('442: ticker tail'),
    ]

    def get_leaf_nodes(data):
        """
        Recursively extracts all leaf nodes from a nested list or dictionary.

        A leaf node is any element that is not a dictionary, list, or tuple.
        """
        leaf_nodes = []
        if isinstance(data, dict):
            for value in data.values():
                leaf_nodes.extend(get_leaf_nodes(value))
        elif isinstance(data, (list, tuple)):
            for item in data:
                leaf_nodes.extend(get_leaf_nodes(item))
        else:
            if data is not None:  # Optionally exclude None if not considered a "value"
                leaf_nodes.append(data)
        return leaf_nodes

    refineries = refineries  # get_leaf_nodes(TSA.formula_components(name, expanded=True)[name])
    metas = {x: tsa.metadata(x) for x in refineries[:-1]}
    dict_metas = pd.DataFrame.from_records(metas)
    data = pd.concat(map(tsa.get, refineries), axis=1).ffill()
    data.columns = [f"{dict_metas[name]['tradingRegionName']} | {dict_metas[name]['plantname']}" for name in _missing_photo_text('474: column comprehension iterator/call tail')]
    freq_format = {'M': '%b-%y', 'Q': 'Q%q-%y', 'Y': '%y', 'W-FRI': '%d-%b', 'D': '%d-%b'}
    freq = 'M'
    resampled_data = data.copy()
    resampled_data['Sum'] = data.sum(axis=1)
    resampled_data.index = resampled_data.index.to_period(freq).strftime(freq_format[freq])
    resampled_data = resampled_data.groupby(axis=0, level=0, sort=False).mean()
    today = pd.Period(pd.Timestamp.now(), freq=freq).strftime(freq_format[freq])
    slice_view = slice((resampled_data.index.get_loc(today) - 6), (resampled_data.index.get_loc(today) + 16))
    format_row = {0: {"bottom_border": True, "top_border": True, 'bold': True, 'height': '10px'}}
    resampled_data_t = resampled_data.iloc[slice_view].T.sort_values([today], ascending=False).reset_index()
    column_format = {
        'index': {"left_border": True, "right_border": True, 'text-align': 'left', 'width': '500px'},
        **{k: {'width': '50px', 'highlight_on_range': {'columns': [k], 'min': 0, 'max': 200}} for k in _missing_photo_text('502: resampled... iterator suffix')},
        today: {"left_border": True, "right_border": True, 'width': '50px', 'highlight_on_range': _missing_photo_text('503: columns mapping suffix')},
    }
    html_table = table.html_format(resampled_data_t, header=f"IIR Atlantic Basin outages at key refineries, kb/d",
                                   format_column=column_format, format_row=format_row, precision=0, show_date=True)
    figs = [
        [table.html_text("ECM Crude balance", style="font-family:Calibri;", tag='h1')],
        [fig_balance],
        [fig_onshore, fig_sanctioned, fig_oow],
        [fig_us, fig_ex_us_ex_china, fig_china],
        [monthly, quarterly, annual],
        [table.html_text("ECM Crude balance, y/y", style="font-family:Calibri;", tag='h1')],
        [monthlyyy, quarterlyyy, annualyy],
    ]
    charts = []
    width = 550
    height = 500
    revisions = [
        'Balance', 'Sanctioned on water', 'Implied onshore builds ex. China', '&nbsp;&nbsp;US balance',
        'World crude/condensate production', '&nbsp;&nbsp;US crude/cond', '&nbsp;&nbsp;Russia crude',
        '&nbsp;&nbsp;OPEC V8 crude', 'World runs', '&nbsp;&nbsp;US runs', '&nbsp;&nbsp;China runs',
        '&nbsp;&nbsp;OECD Europe runs',
    ]
    for title in revisions:
        print(title)
        df = history_weekly(tsa, line_items[title], from_insertion_date=pd.Timestamp('20251008', tz='UTC'))
        vintage_plot_m = plot_value_by_vintage_plotly(df=df[start_date:start_date + pd.DateOffset(months=4)],
                                                     freq_vintage='B', freq_value='M', title=title).update_layout(
                                                         autosize=False, width=width, height=height)
        vintage_plot_q = plot_value_by_vintage_plotly(df=df[start_date_quarter:start_date_quarter + pd.DateOffset(months=12)],
                                                     freq_vintage='B', freq_value='Q', title=title).update_layout(
                                                         autosize=False, width=width, height=height)
        series = df.iloc[:, -1]
        yearly_plot = plot_value_by_year(series['2018':], freq_value='Q', title=title).update_layout(
            autosize=False, width=width, height=height)
        header = [table.html_text(title, style="font-family:Calibri;", tag='h2')]
        _charts = [vintage_plot_m, vintage_plot_q, yearly_plot]
        charts.append(header)
        charts.append(_charts)
    table.to_html(figs + charts + [[table.html_text("IIR outage, kb/d", style="font-family:Calibri;", tag='h1')], [html_table]],
                  f"{html_path}\\oil\\ecm_crude_balance.html", task_name="ECM Crude balance")


if __name__ == '__main__':
    generate_report()
