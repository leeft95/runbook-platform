import pandas as pd
import numpy as np
import datetime as dt
import sys
import statsmodels.api as sm
import plotly.graph_objects as go
from dateutil.relativedelta import relativedelta
import ecm.cmds.table as table
import ecm.cmds.pyg as pyg
from ecm.cmds.config import root_path, html_path, output_path, oil_group
from ecm.cmds.cdr import today
import ecm.cmds.bbg as bbg
import ecm.cmds.sql as sql
from ecm.atom.wintask.scheduler import ECMWinTask
from ecm.atom.wintask.utils import Days

send_to = ["rzhao@elementcapital.com"]
report_name = "Product Weekly Balance"
file_name = "product_weekly_balance"  # without .py
file_path = f"{root_path}\\autoreports\\reports\\oil\\{file_name}.py"


def _missing_photo_text(lines):
    raise NotImplementedError(f"Transcription gap in stocks_vs_price.py, photographed lines {lines}")


def add_schedule():
    """
    # schedule to run the report - only need to run once
    """
    sys.path.append(f"{root_path}\\autoreports\\schedule")
    from tasks import WinTaskPoC
    win_task = ECMWinTask(
        days=Days.MONDAY | Days.TUESDAY | Days.WEDNESDAY | Days.THURSDAY | Days.FRIDAY,
        start_datetime=dt.datetime(2023, 7, 1, 8, 20), timezone="Europe/London",
        task_name=report_name,
        task=WinTaskPoC(name=f'"{report_name}"', filepath=f'"{file_path}"'),
        background_task=True,
        python_executable=r"C:\local\python\miniconda\envs\ecm_cmds\pythonw.exe")
    win_task.create_task()


def rbob_regress(active='XBA Comdty'):
    sdate = dt.datetime(2010, 1, 1)
    edate = today()
    month_list = list(range(1, 13))
    year_list = list(range(sdate.year, edate.year + 1))
    if active == 'XBA Comdty':
        storage = bbg.bdh('DOESGAS1 Index', ['PX_LAST'], sdate, edate)
    elif active == 'HOA Comdty':
        storage = bbg.bdh('DOESDIS1 Index', ['PX_LAST'], sdate, edate)
    contracts = pyg.get_data("spreads", active=active, item="sprd_chain")
    contracts.rename(columns={"t3": "t"}, inplace=True)
    flat = pyg.get_data("contracts", active=active, item="fut_chain")
    flat.rename(columns={"t3": "t"}, inplace=True)
    flat['ticker_far'] = flat['ticker'].shift(-1)
    contracts = pd.merge(contracts, flat[['t', 'ticker', 'ticker_far']], how='left', left_on='t', right_on='t')
    contracts.rename(columns={'ticker_x': 'ticker'}, inplace=True)
    contracts.rename(columns={'ticker_y': 'ticker_under'}, inplace=True)
    contracts = contracts.loc[(contracts['last_t'] >= sdate) &
                             (contracts['last_t'] <= edate + dt.timedelta(**_missing_photo_text("63")))]
    reg_df = pd.DataFrame(np.nan, index=contracts['last_t'], columns=['ticker', 'month', 'price', 'stocks'])
    price_dict = {}
    for idx, row in contracts.iterrows():
        price = pyg.get_data("spreads PX_LAST", active=active, m=row['m'], y=row['y'], far_m=row['far_m'], far_y=row['far_y'])
        last_price = price['PX_LAST'].iloc[-5]
        stock_month = row['last_t'] + relativedelta(months=1) + relativedelta(day=31)
        stocks = storage.loc[storage.index <= stock_month, 'PX_LAST'][-1]
        reg_df.loc[row['last_t'], 'ticker'] = row['ticker']
        reg_df.loc[row['last_t'], 'month'] = row['last_t']
        reg_df.loc[row['last_t'], 'price'] = last_price
        reg_df.loc[row['last_t'], 'stocks'] = stocks
        reg_df.loc[row['last_t'], 'stocks_month'] = stock_month
        reg_df.loc[row['last_t'], 'm'] = row['m']
        reg_df.loc[row['last_t'], 'far_m'] = row['far_m']
        price_dict[row['ticker']] = price
    reg_df['month'] = [x + relativedelta(day=31) + relativedelta(days=1) for x in reg_df['month']]
    figs = []
    reg_param = pd.DataFrame(np.nan, index=range(1, 13), columns=['a', 'b', 'e'])
    if active == 'XBA Comdty':
        for m in range(1, 13):
            reg_month = reg_df.loc[reg_df['month'].dt.month == m, :]
            reg_pre_year = reg_month.loc[reg_month['month'].dt.year < today().year, :]
            reg_this_year = reg_month.loc[reg_month['month'].dt.year >= today().year, :]
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=reg_pre_year.loc[:, 'stocks'], y=reg_pre_year.loc[:, 'price'],
                                    text=reg_pre_year.loc[:, 'month'].dt.strftime('%Y-%b'),
                                    opacity=0.8, showlegend=True, mode='markers', name=m))
            if len(reg_this_year) > 0:
                fig.add_trace(go.Scatter(x=reg_this_year.loc[:, 'stocks'], y=reg_this_year.loc[:, 'price'],
                                        text=reg_this_year.loc[:, 'month'].dt.strftime('%Y-%b'),
                                        opacity=0.8, showlegend=True, mode='markers', name='latest points',
                                        marker=dict(color='black', size=12)))
            x = sm.add_constant(reg_pre_year.loc[:, 'stocks'].values)
            lm = sm.OLS(reg_pre_year.loc[:, 'price'].values, x).fit()
            reg_param.loc[m, ['a', 'b']] = lm.params
            reg_param.loc[m, 'e'] = lm.scale ** 0.5
            y_fit = x.dot(lm.params)
            fig.add_trace(go.Scatter(x=reg_pre_year.loc[:, 'stocks'], y=y_fit,
                                    opacity=0.8, showlegend=True, mode='lines', name='fit',
                                    marker=dict(color='grey', size=2)))
            fig.add_trace(go.Scatter(x=reg_pre_year.loc[:, 'stocks'], y=y_fit + 2 * lm.scale ** 0.5,
                                    mode='lines', name='+2sd', line=dict(color='grey', width=2, dash='dash')))
            fig.add_trace(go.Scatter(x=reg_pre_year.loc[:, 'stocks'], y=y_fit - 2 * lm.scale ** 0.5,
                                    mode='lines', name='-2sd', line=dict(color='grey', width=2, dash='dash')))
            fig.update_traces(hovertemplate='date: %{text} <br>x: %{x} <br>y: %{y}')
            fig.update_layout(title={
                'text': (f"{active} price ({reg_month['m'].iloc[-1]}-{reg_month['far_m'].iloc[-1]}) "
                         f"vs stocks ({dt.datetime.strftime(reg_month['stocks_month'].iloc[-1], '%b')}), "
                         f"rsqr:{lm.rsquared: .2f}"),
                'x': 0.5, 'xanchor': 'center'}, xaxis_title='stocks', yaxis_title='price', width=900, height=600)
            figs.append(fig)
    elif active == 'HOA Comdty':
        reg_df = reg_df.loc[reg_df['month'].dt.year > 2013, :]
        reg_df = reg_df.loc[~reg_df['month'].isin([dt.datetime(2014, 2, 1), dt.datetime(2015, 3, 1)]), :]
        reg_pre_year = reg_df.loc[reg_df['month'].dt.year < today().year, :]
        reg_this_year = reg_df.loc[reg_df['month'].dt.year >= today().year, :]
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=reg_pre_year.loc[:, 'stocks'], y=reg_pre_year.loc[:, 'price'],
                                text=reg_pre_year.loc[:, 'month'].dt.strftime('%Y-%b'),
                                opacity=0.8, showlegend=True, mode='markers', name=active))
        if len(reg_this_year) > 0:
            fig.add_trace(go.Scatter(x=reg_this_year.loc[:, 'stocks'], y=reg_this_year.loc[:, 'price'],
                                    text=reg_this_year.loc[:, 'month'].dt.strftime('%Y-%b'),
                                    opacity=0.8, showlegend=True, mode='markers', name='latest points',
                                    marker=dict(color='black', size=12)))
        x = sm.add_constant(reg_pre_year.loc[:, 'stocks'].values)
        lm = sm.OLS(reg_pre_year.loc[:, 'price'].values, x).fit()
        y_fit = x.dot(lm.params)
        reg_param.loc[:, ['a', 'b']] = lm.params
        reg_param.loc[:, 'e'] = lm.scale ** 0.5
        fig.add_trace(go.Scatter(x=reg_pre_year.loc[:, 'stocks'], y=y_fit,
                                opacity=0.8, showlegend=True, mode='lines', name='fit', marker=dict(color='grey', size=2)))
        fig.add_trace(go.Scatter(x=reg_pre_year.loc[:, 'stocks'], y=y_fit + 2 * lm.scale ** 0.5,
                                mode='lines', name='+2sd', line=dict(color='black', width=2, dash='dash')))
        fig.add_trace(go.Scatter(x=reg_pre_year.loc[:, 'stocks'], y=y_fit - 2 * lm.scale ** 0.5,
                                mode='lines', name='-2sd', line=dict(color='black', width=2, dash='dash')))
        fig.update_traces(hovertemplate='date: %{text} <br>x: %{x} <br>y: %{y}')
        fig.update_layout(title={'text': f"{active} price vs stocks, rsqr:{lm.rsquared: .2f}",
                                 'x': 0.5, 'xanchor': 'center'},
                          xaxis_title='stocks', yaxis_title='price', width=900, height=600)
        figs.append(fig)
    table.figures_to_html(figs, f"{html_path}\\oil\\{active}_regress.html", task_name=report_name)
    return reg_param, price_dict, contracts


def actual_vs_forecast_price(active='XBA Comdty'):
    reg_param, price_dict, contracts = rbob_regress(active=active)
    if active == 'XBA Comdty':
        stock_fcast = sql.read_sql("Select * from P1_Gasoline_Balances where fcast_type='stock_fcast' order by As_of_date desc, "
                                  + _missing_photo_text("187: Sto..."))
    elif active == 'HOA Comdty':
        stock_fcast = sql.read_sql("Select * from P1_Disty_Balances where fcast_type='stock_fcast' order by As_of_date desc, "
                                  + _missing_photo_text("190: Stock_..."))
    contracts = contracts.loc[contracts['last_t'] > today()]
    figs = []
    for idx, row in contracts.iterrows():
        print(row['ticker'])
        month = (row['last_t'] + relativedelta(day=31) + relativedelta(days=1)).month
        year = row['last_t'].year
        stock_fcast_m = stock_fcast.loc[
            stock_fcast['Stock_Month'] == dt.datetime(year, month, 1), ['Value', 'As_of_date', 'Stock_Month']].sort_values('As_of_date')
        stock_fcast_m.set_index('As_of_date', inplace=True)
        price_fcast = stock_fcast_m['Value'].astype(float) * reg_param.loc[month, 'b'] + reg_param.loc[month, 'a']
        price_actual = price_dict[row['ticker']]['PX_LAST']
        vol = price_actual.rolling(30).std()
        price_chart = pd.concat([price_actual, price_fcast, vol], axis=1)
        price_chart.columns = ['Actual', 'Forecast', 'Vol']
        price_chart.fillna(method='ffill', inplace=True)
        price_chart['upper_band'] = price_chart['Forecast'] + 2 * reg_param.loc[month, 'e']
        price_chart['lower_band'] = price_chart['Forecast'] - 2 * reg_param.loc[month, 'e']
        price_chart = price_chart.loc[price_chart.index >= today() - dt.timedelta(days=91)]
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=price_chart.index, y=price_chart.upper_band,
                                fill=None, mode=None, line_color='lightgray', showlegend=False))
        fig.add_trace(go.Scatter(x=price_chart.index, y=price_chart.lower_band,
                                fill='tonexty',  # fill area between trace0 and trace1
                                mode=None, line_color='lightgray', showlegend=False))
        fig.add_trace(go.Scatter(x=price_chart.index, y=price_chart['Forecast'], name='Forecast price',
                                line=dict(color='black', width=2)))
        fig.add_trace(go.Scatter(x=price_chart.index, y=price_chart['Actual'], name='Actual price',
                                line=dict(color='red', width=2)))
        fig.update_layout(title={'text': f"{row['ticker']} actual vs forecast price", 'x': 0.5, 'xanchor': 'center'},
                          xaxis_title='price', yaxis_title='stocks', width=900, height=600)
        figs.append(fig)
    table.figures_to_html(figs, f"{html_path}\\oil\\{active}_price.html", task_name=report_name)


def update():
    actual_vs_forecast_price(active='XBA Comdty')
    actual_vs_forecast_price(active='HOA Comdty')


if __name__ == '__main__':
    update()
