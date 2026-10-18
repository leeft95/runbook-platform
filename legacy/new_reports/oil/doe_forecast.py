import ecm.cmds.table as table
from tqdm.contrib.concurrent import thread_map
import pandas as pd
from tshistory.api import timeseries
import ecm.cmds.chart as chart
from ecm.cmds.config import html_path
import sys
import os
if sys.platform.startswith("win"):
    os.environ["GRPC_DEFAULT_SSL_ROOTS_FILE_PATH"] = r"C:\local\certs\root.crt"
    os.environ["REQUESTS_CA_BUNDLE"] = r"C:\local\certs\root.crt"
    os.environ["SSL_CERT_FILE"] = r"C:\local\certs\root.crt"

tsa = timeseries('https://lo25.wagyu.elementcapital.corp/tsh/api')


def _missing_photo_text(lines):
    raise NotImplementedError(f"Transcription gap in doe_forecast.py, photographed lines {lines}")


def us_crude_bal_ea(data, line_items_dict, freq='M', end_date=None, format_row=None, agg_dict=None, curr=None):
    if agg_dict is None:
        _data = data.asfreq('D').bfill().resample(freq).mean()
    else:
        _data = data.asfreq('D').bfill().resample(freq).agg(agg_dict)
    last_update = tsa.insertion_dates(line_items_dict[list(line_items_dict.keys())[-1]])[-1]
    a_range = pd.date_range(pd.Timestamp.now() - pd.DateOffset(days=30),
                           end_date or pd.Timestamp('2026-01-0' + _missing_photo_text('25: date/call tail')))
    resampled_data = _data.copy()[a_range[0]:a_range[-1]]
    freq_dict = {'M': '%b-%y', 'W-FRI': '%d-%b', 'Q': 'Q%q-%y'}
    resampled_data.index = resampled_data.index.to_period(freq).strftime(freq_dict[freq])
    filtered_resampled_data = resampled_data.T.reset_index()
    filtered_resampled_data.rename(columns={"index": "kb/d"}, inplace=True)
    curr = pd.Period(pd.Timestamp.now() or curr, freq=freq).strftime(freq_dict[freq])
    column_format = {
        'kb/d': {"right_border": True, 'text-align': 'left', 'width': '200px'},
        **{k: {'width': '60px'} for k in filtered_resampled_data.columns if k not in ('kb/d', curr)},
        curr: {"left_border": True, "right_border": True, "width": '50px'},
    }
    _format_row = format_row or {
        0: {"bottom_border": True, "top_border": True, 'bold': True},
        6: {"bottom_border": True, "top_border": True, 'bold': True},
        4: {"bottom_border": True, "top_border": True},
        8: {'italic': True}, 9: {'italic': True}, 10: {'italic': True}, 12: {'italic': True},
        13: {"bottom_border": True, "top_border": True, 'bold': True},
        15: {"bottom_border": True, "top_border": True, 'bold': True},
        18: {'italic': True},
    }
    html_table = table.html_format(filtered_resampled_data, header=f"DOE crude balance, kb/d",
                                   footer=f"Last updated {last_update:%d-%m %H:%m}",
                                   format_column=column_format, format_row=_format_row, precision=0, show_date=True)
    return html_table


def generate_report():
    line_items = {
        'Supply': 'element.crude_oil.united_states.doe_supply.kbd.weekly.forecast',
        'Crude field production': 'element.crude_oil.united_states.doe_production.kbd.weekly',
        'Cad pipe': 'element.crude_oil.united_states.doe_pipe_crude_imports.kbd.weekly.forecast',
        'Waterborne imports': 'element.crude_oil.united_states.doe_waterborne_crude_imports.kbd.weekly.forecast',
        'Total realised imports': 'element.crude_oil.united_states.doe_crude_imports.kbd.weekly.forecast',
        'Transfers to supply': 'element.crude_oil.united_states.doe_transfers_to_crude_supply.kbd.weekly',
        'Demand': 'element.crude_oil.united_states.doe_demand.kbd.weekly.forecast',
        'Refinery runs': 'element.crude_oil.united_states.ea_runs_iir_adjusted.kbd.weekly',
        'DOE refinery runs': 'eia.crude_oil.refinery_runs.united_states.kbd.weekly',
        'IIR outages': 'iir.crude.united_states.total_outage.kbd.weekly',
        'Operating rate': 'element.crude.united_states.operating_rate.pct.weekly.forecast.100',
        'Exports': 'element.crude_oil.united_states.doe_waterborne_crude_exports.kbd.weekly.forecast',
        'DOE exports': 'eia.crude_oil.exports.united_states.kbd.weekly',
        'Balance (S-D)': 'element.crude_oil.united_states.doe_balance.kbd.weekly.forecast',
        'Adjustment factor': 'element.crude_oil.united_states.doe_adjustement.kbd.weekly',
        'Commercial stock build': 'element.crude_oil.united_states.doe_commercial_balance.kb.weekly.forecast',
        'Whisper': 'bloomberg.crude_oil.stock_change.whisper.kbd.weekly.shifted',
        'Commercial stocks': 'element.crude_oil.united_states.doe_commercial_stocks.kb.weekly.forecast',
        'Commercial stocks vs 5y': 'element.crude_oil.united_states.doe_commercial_stocks.kb.weekly.forecast.' + _missing_photo_text('86'),
    }

    weekly_to_monthly = {
        'Supply': lambda x: x.mean(),
        'Crude field production': lambda x: x.mean(),
        'Cad pipe': lambda x: x.mean(),
        'Waterborne imports': lambda x: x.mean(),
        'Total realised imports': lambda x: x.mean(),
        'Transfers to supply': lambda x: x.mean(),
        'Demand': lambda x: x.mean(),
        'Refinery runs': lambda x: x.mean(),
        'DOE refinery runs': lambda x: x.mean(),
        'IIR outages': lambda x: x.mean(),
        'Operating rate': lambda x: x.mean(),
        'Exports': lambda x: x.mean(),
        'DOE exports': lambda x: x.mean(),
        'Balance (S-D)': lambda x: x.mean(),
        'Adjustment factor': lambda x: x.mean(),
        'Commercial stock build': lambda x: x.sum() / 7,
        'Whisper': lambda x: x.sum() / 7,
        'Commercial stocks': lambda x: x.iloc[-1],
        'Commercial stocks vs 5y': lambda x: x.iloc[-1],
    }

    line_items_2 = {
        'Supply': 'element.crude_oil.united_states.doe_supply.kbd.weekly.forecast',
        'Crude field production': 'element.crude_oil.united_states.doe_production.kbd.weekly',
        'Cad pipe': 'element.crude_oil.united_states.doe_pipe_crude_imports.kbd.weekly.forecast',
        'Waterborne imports': 'element.crude_oil.united_states.doe_waterborne_crude_imports.kbd.weekly.forecast',
        'Total realised imports': 'element.crude_oil.united_states.doe_crude_imports.kbd.weekly.forecast',
        'Transfers to supply': 'element.crude_oil.united_states.doe_transfers_to_crude_supply.kbd.weekly',
        'Demand': 'element.crude_oil.united_states.doe_demand.kbd.weekly.forecast',
        'Refinery runs': 'element.crude_oil.united_states.doe_refinery_runs.kbd.weekly.forecast.adj',
        'Consensus runs': 'element.crude_oil.united_states.doe_refinery_runs.kbd.weekly.forecast',
        'Operating rate': 'element.crude.united_states.operating_rate.pct.weekly.forecast.100.adj',
        'Consensus OR': 'element.crude.united_states.operating_rate.pct.weekly.forecast.100',
        'Exports': 'element.crude_oil.united_states.doe_waterborne_crude_exports.kbd.weekly.forecast.adj',
        'Consensus exp': 'element.crude_oil.united_states.doe_waterborne_crude_exports.kbd.weekly.forecast',
        'Commercial stock build': 'element.crude_oil.united_states.doe_commercial_balance.kb.weekly.forecast.' + _missing_photo_text('125/127'),
        'Commercial stocks': 'element.crude_oil.united_states.doe_commercial_stocks.kb.weekly.forecast.adj',
        'Commercial stocks vs 5y': 'element.crude_oil.united_states.doe_commercial_stocks.kb.weekly.forecast.' + _missing_photo_text('125/127'),
    }

    weekly_to_monthly_2 = {
        'Supply': lambda x: x.mean(),
        'Crude field production': lambda x: x.mean(),
        'Cad pipe': lambda x: x.mean(),
        'Waterborne imports': lambda x: x.mean(),
        'Total realised imports': lambda x: x.mean(),
        'Transfers to supply': lambda x: x.mean(),
        'Demand': lambda x: x.mean(),
        'Refinery runs': lambda x: x.mean(),
        'Consensus runs': lambda x: x.mean(),
        'Operating rate': lambda x: x.mean(),
        'Consensus OR': lambda x: x.mean(),
        'Exports': lambda x: x.mean(),
        'Consensus exp': lambda x: x.mean(),
        'Commercial stock build': lambda x: x.sum() / 7,
        'Commercial stocks': lambda x: x.iloc[-1],
        'Commercial stocks vs 5y': lambda x: x.iloc[-1],
    }

    extra_items = {
        'WTI M+2 spread': 'platts.price.crude_oil.wti_mo02_vs_wti_mo03_intermonth_spread.usd_bbl.daily.14_30' + _missing_photo_text('150: time-zone suffix'),
        'Commercial stocks': 'element.crude_oil.united_states.doe_commercial_stocks.kb.weekly.forecast.adj',
        'Exports': 'element.crude_oil.united_states.doe_waterborne_crude_exports.kbd.weekly.forecast.adj',
        'Refinery runs': 'element.crude_oil.united_states.doe_refinery_runs.kbd.weekly.forecast',
        'doe': 'eia.crude_oil.ending_stocks.united_states.kb.weekly',
        'TD25 cash': 'platts.price.shipping.wti_meh_nwe_freight.usd_bbl.daily.14_30_us_eastern',
        'TD22 cash': 'platts.price.shipping.mars_singapore_freight.usd_bbl.daily.14_30_us_eastern',
        'M+1 MEH': 'platts.price.crude_oil.wti_meh_mo01_vs_1st_line_wti_at_london_moc.usd_bbl.daily.16_30_uk',
        'Brent/TI front x-arb': 'platts.price.crude_oil.brent_mo01_vs_wti_mo01.usd_bbl.daily.16_30_uk',
        'MEH vs Dubai cash': 'platts.price.crude_oil.cash_meh_arb_vs_dubai.usd_bbl.daily.16_30_singapore',
    }
    data = pd.concat(thread_map(tsa.get, line_items.values(), max_workers=10), axis=1).rename(columns={v: k for k, v in line_items.items()})
    data_extra = pd.concat(thread_map(tsa.get, extra_items.values(), max_workers=10), axis=1).rename(columns={v: k for k, v in extra_items.items()})
    data_risk = pd.concat(thread_map(tsa.get, line_items_2.values(), max_workers=10), axis=1).rename(columns={v: k for k, v in line_items_2.items()})
    last_print = data_extra['doe'].dropna().index[-1]
    weekly_table = us_crude_bal_ea(data, line_items, 'W-FRI', end_date=pd.Timestamp.now() + pd.DateOffset(days=50), curr=last_print)
    monthly = us_crude_bal_ea(data, line_items, 'M', end_date=pd.Timestamp.now() + pd.DateOffset(days=180), curr=last_print, agg_dict=weekly_to_monthly)
    quarterly_table = us_crude_bal_ea(data, line_items, 'Q', end_date=pd.Timestamp.now() + pd.DateOffset(days=365), curr=last_print, agg_dict=weekly_to_monthly)
    _format_row = {
        0: {"bottom_border": True, "top_border": True, 'bold': True},
        6: {"bottom_border": True, "top_border": True, 'bold': True},
        4: {"bottom_border": True, "top_border": True},
        8: {'italic': True}, 10: {'italic': True}, 12: {'italic': True},
        13: {"bottom_border": True, "top_border": True, 'bold': True},
    }
    weekly_table_risk = us_crude_bal_ea(data_risk, line_items_2, 'W-FRI', end_date=pd.Timestamp.now() + pd.DateOffset(days=50), curr=last_print, format_row=_format_row)
    monthly_table_risk = us_crude_bal_ea(data_risk, line_items_2, 'M', end_date=pd.Timestamp.now() + pd.DateOffset(days=180), format_row=_format_row, curr=last_print, agg_dict=weekly_to_monthly_2)
    quarterly_table_risk = us_crude_bal_ea(data_risk, line_items_2, 'Q', end_date=pd.Timestamp.now() + pd.DateOffset(days=365), format_row=_format_row, curr=last_print, agg_dict=weekly_to_monthly_2)
    width = 700
    height = 500
    chart_01 = chart.seasonal_chart(
        df=data['2018':'2026'], column='Commercial stocks', title=f'Commercial stocks, kb', freq='W',
        height=height, width=width,
        dash_name='forecast', dash_from=data_extra['doe'].dropna().index[-1],
        ytd=False, vs_avg=False, cur_yr=pd.Timestamp.today().year, over_year=True)

    chart_02 = chart.seasonal_chart(
        df=data['2018':'2026'], column='Commercial stocks vs 5y', title=f'Commercial stocks vs 5y, kb', freq='W',
        height=height, width=width,
        dash_name='forecast', dash_from=data_extra['doe'].dropna().index[-1],
        ytd=False, vs_avg=False, cur_yr=pd.Timestamp.today().year, over_year=True)

    chart_03 = chart.seasonal_chart(
        df=data_extra[['WTI M+2 spread']]['2018':].dropna().resample('B').ffill(), column='WTI M+2 spread', title=f'WTI M+2 spread, $/bbl', freq='B',
        height=height, width=width,
        ytd=False, vs_avg=False, cur_yr=pd.Timestamp.today().year, over_year=True)

    chart_04 = chart.seasonal_chart(
        df=data_extra[['Refinery runs']]['2018':'2026'].dropna(), column='Refinery runs', title=f'Refinery runs, kb/d', freq='W',
        height=height, width=width,
        dash_name='forecast', dash_from=data_extra['doe'].dropna().index[-1],
        ytd=False, vs_avg=False, cur_yr=pd.Timestamp.today().year, over_year=True)

    chart_05 = chart.seasonal_chart(
        df=data['2018':'2026'], column='Operating rate', title=f'Realised/Forward operating rate, %', freq='W',
        height=height, width=width,
        dash_name='forecast', dash_from=data_extra['doe'].dropna().index[-1],
        ytd=False, vs_avg=False, cur_yr=pd.Timestamp.today().year, over_year=True)

    chart_06 = chart.seasonal_chart(
        df=data['2018':'2026'], column='IIR outages', title=f'IIR outages, kb/d', freq='W',
        height=height, width=width,
        dash_name='forecast', dash_from=data_extra['doe'].dropna().index[-1],
        ytd=False, vs_avg=False, cur_yr=pd.Timestamp.today().year, over_year=True)

    chart_07 = chart.seasonal_chart(
        df=data['2020':'2026'], column='Exports', title=f'Crude exports, kb/d', freq='W',
        height=height, width=width,
        dash_name='forecast', dash_from=data_extra['doe'].dropna().index[-1],
        ytd=False, vs_avg=False, cur_yr=pd.Timestamp.today().year, over_year=True)

    chart_08 = chart.seasonal_chart(
        df=data['2020':'2026'], column='Waterborne imports', title=f'Waterborne imports, kb/d', freq='W',
        height=height, width=width,
        dash_name='forecast', dash_from=data_extra['doe'].dropna().index[-1],
        ytd=False, vs_avg=False, cur_yr=pd.Timestamp.today().year, over_year=True)

    chart_09 = chart.seasonal_chart(
        df=data['2020':'2026'], column='Cad pipe', title=f'Pipeline imports, kb/d', freq='W',
        height=height, width=width,
        dash_name='forecast', dash_from=data_extra['doe'].dropna().index[-1],
        ytd=False, vs_avg=False, cur_yr=pd.Timestamp.today().year, over_year=True)

    chart_10 = chart.seasonal_chart(
        df=data_extra[['MEH vs Dubai cash']]['2020':].dropna().resample('B').ffill(), column='MEH vs Dubai cash', title=f'MEH @ Corpus Christi vs Dubai cash, $/bbl, VLCC', freq='B',
        height=height, width=width,
        ytd=False, vs_avg=False, cur_yr=pd.Timestamp.today().year, over_year=True)

    chart_11 = chart.seasonal_chart(
        df=data_extra[['M+1 MEH']]['2020':].dropna().resample('B').ffill(), column='M+1 MEH', title=f'M+1 MEH, $/bbl', freq='B',
        height=height, width=width,
        ytd=False, vs_avg=False, cur_yr=pd.Timestamp.today().year, over_year=True)

    chart_12 = chart.seasonal_chart(
        df=data_extra[['TD22 cash']]['2020':].dropna().resample('B').ffill(), column='TD22 cash', title=f'TD22 cash, $/bbl', freq='B',
        height=height, width=width,
        ytd=False, vs_avg=False, cur_yr=pd.Timestamp.today().year, over_year=True)

    chart_13 = chart.seasonal_chart(
        df=data_extra[['TD25 cash']]['2020':].dropna().resample('B').ffill(), column='TD25 cash', title=f'TD25 cash, $/bbl', freq='B',
        height=height, width=width,
        ytd=False, vs_avg=False, cur_yr=pd.Timestamp.today().year, over_year=True)

    chart_13a = chart.seasonal_chart(
        df=data_extra[['Brent/TI front x-arb']]['2018':].dropna().resample('B').ffill(), column='Brent/TI front x-arb', title=f'Brent/TI front x-arb, $/bbl', freq='B',
        height=height, width=width,
        ytd=False, vs_avg=False, cur_yr=pd.Timestamp.today().year, over_year=True)

    figs = [
        [table.html_text("US consensus balance", style="font-family:Calibri;", tag='h1')],
        [weekly_table, monthly, quarterly_table],
        [table.html_text("Storage", style="font-family:Calibri;", tag='h1')],
        [chart_01, chart_02, chart_03],
        [table.html_text("Refinery ops", style="font-family:Calibri;", tag='h1')],
        [chart_04, chart_05, chart_06],
        [table.html_text("Trade balance", style="font-family:Calibri;", tag='h1')],
        [chart_07, chart_08, chart_09],
        [chart_10, chart_11, chart_12],
        [chart_13, chart_13a],
    ]
    table.to_html(figs, f"{html_path}\\oil\\doe_forecast2.html", task_name="US Balance")
