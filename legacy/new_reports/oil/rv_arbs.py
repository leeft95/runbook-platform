import ecm.cmds.table as table
from tqdm.contrib.concurrent import thread_map
import pandas as pd
from tshistory.api import timeseries
from ecm.cmds.config import html_path
import pandas as pd
from dotenv import load_dotenv
from ecm.cmds.core.utils import convert_path_to_linux
from ecm.cmds.saturn.curve_bias.curve_bias import evaluate, env

output_dir = convert_path_to_linux(r'S:\Michel Kikano\CODE\lballand\lballand_utils\output')

tsa = timeseries()

load_dotenv()

MONTHS = ['F', 'G', 'H', 'J', 'K', 'M', 'N', 'Q', 'U', 'V', 'X', 'Z']
WIDTH = 500


def _missing_photo_text(lines):
    """Transcription marker for source absent from all available photographs."""
    raise NotImplementedError(f"Missing photographed text: rv_arbs.py source lines {lines}")


def eval(x):
    try:
        data = evaluate(x, env)
        return data
    except:
        print(x)


def multiple_curve(markets, name, precision=2):
    _data = dict(thread_map(lambda k: (k, eval(f'(curve "{k}" #:table "daily_combined" #:n 4)')), markets,
                            **_missing_photo_text("28")))
    datas = pd.concat(_data, axis=1)
    last_print = (datas.index[-1])
    _table = datas.iloc[-1].unstack(0).dropna(how='all').reset_index()
    _, _cols = _table.shape
    html_table = table.html_format(
        _table.assign(year=lambda x: x.year.astype(str)).head(12),
        header=name + "| " + f"{last_print:%d-%b}",
        precision=precision,
        show_date=True,
        custom_width=WIDTH,
        footer=f"Last updated {last_print:%d-%b}",
    )
    return html_table


def multiple_evolution(markets, name='', maturity='U', year=2025):
    _data = _missing_photo_text("46")
    datas = pd.concat(_data, axis=1)
    last_print = (datas.index[-1])
    _table = datas.xs((year, maturity), axis=1, level=(1, 2)).ffill(limit=1)
    html_table = table.table_with_link(
        _table,
        header=name + "| " + maturity + str(year - 2000),
        name=name+maturity+str(year - 2000),
        folder=output_dir,
        inline=False,
        width1=2 * WIDTH,
        **_missing_photo_text("57-58"),
        footer=f"Last updated {last_print:%d-%b}",
        chart_columns={tuple(_table.columns): 'seasonal'}
    )
    return html_table


current_year = pd.Timestamp.now().year
current_month = MONTHS[(pd.Timestamp.now().month + 1) % 12]

_tabs = {
    'Asia crude arb': [
        'Landing WTI Dubai cycle',
        'Landing Murban Dubai cycle',
        'Landing CPC Dubai cycle',
        'Landing JS Dubai cycle',
        'Landing Dtd Dubai cycle',
        'TI vs Murban Dubai cycle',
        'TI-Brent fut',
        'Brent/Dubai',
        'TD22 USGC-China',
        'TD3c PG-China',
        'WTI spreads',
        'MEH Diff Fut',
        'Marginal Sing margin',
        'Dubai spreads',
    ],

    'Sing margin set': [
        'Dubai spreads',
        'Murban Diff',
        'Landing Murban Dubai cycle',
        'Naphtha Crack Japan',
        'Sing Gasoline crack',
        'Sing Regrade',
        'Sing Gasoil crack',
        'Sing VLSFO crack',
        'Sing 380cst FO crack',
        'ICAP style Sing margin',
        'Marginal Sing margin',
    ],

    'Nsea crude set': [
        'DFL',
        'ICE WTI spreads',
        'TD25 USGC-ARA ETS',
        'MEH Diff Fut',
        'JS Diff',
        'CPC Diff',
        'WTI-Brent X-arb less TD25',
        'Landing WTI NWE vs Dtd',
        'Landing Forties NWE vs Dtd',
        'Landing WTI vs Forties',
        'NWE Marginal margin vs Dtd CIF',
        'NWE Marginal margin vs CIF WTI',
    ],

    'NWE margin set': [
        'DFL',
        'GO spreads',
        'NWE Naphtha Crack',
        'EBOB Crack',
        'JET FOB regrade',
        'GO Crack',
        'NWE VLSFO crack',
        'NWE HSFO crack',
        'TD25 USGC-ARA ETS',
        'EBOB-GO',
        'ICAP margin',
        'NWE Marginal margin vs Dtd CIF',
    ],

    'Gulf coast ULSD arb': [
        'USGC ULSD Diff',
        'RVO',
        'HOGO fut (ex-RVO)',
        'TC14 USGC-UKC',
        'USGC ULSD landing Europe',
        'NYH ULSD landing Europe',
        'ULSD USGC to NWE arb',
        '10ppm CIF MED',
        '10ppm CIF NWE',
        'GO spreads',
        'HO spreads',
    ],

    'Asian ULSD arb': [
        'MOPAG vs Sing',
        'E/W Gasoil',
        '10ppm Sing spreads',
        'GO swap spread',
        'GO spreads',
        'TC20 PG-UKC',
        'TC5 PG-Jp',
        'GO spreads',
        'ULSD Arab Gulf to Sing',
        'ULSD Arab Gulf to UKC via Suez',
        'ULSD Arab Gulf to MED via Suez',
        'ULSD Arab Gulf to NWE via Cape',
    ],

    'Gasoline': [
        'EBOB Crack',
        'NWE Naphtha Crack',
        'RBOB-Brent',
        'RVO',
        'RBOB-Brent swap (ex-RVO)',
        'TC2 UKC-USAC',
        'RBOB-EBOB',
        'RBOB (ex-RVO) vs EBOB swap - TC2',
        'Naive gasoline T/a arb',
        'NWE GasNap',
        'NWE ProNap',
        'Sing Gasoline crack',
        'E/W Gasoline',
    ],
    'Naphtha': [
        None,
        'C+F Jap Naphtha spread',
        'E/W Naphtha, bbl',
        'E/W Naphtha, T',
        'TC5 PG-Jp',
        'NWE GasNap',
        'NWE ProNap',
        'E/W Naphtha arb',
    ]
}

_offset = {
    'Asia crude arb': 2,
    'Sing margin set': 2,
    'Nsea crude set': 0,
    'NWE margin set': 1,
    'Gulf coast ULSD arb': 1,
    'Asian ULSD arb': 1,
    'Gasoline': 1,
    'Naphtha': 1,
}

bom = pd.Timestamp.today().floor('D').replace(day=1)


def generate_curve(name):
    module = multiple_curve(
        _tabs[name],
        name=name
    )
    return module


def generate_evolution(name):
    contract = bom + pd.DateOffset(months=_offset[name])

    module = multiple_evolution(
        _tabs[name],
        name=name,
        year=contract.year,
        maturity=MONTHS[contract.month - 1],
    )
    return module


def generate_arbs_report():
    figs = [
        [table.html_text("Oil RV", style="font-family:Calibri;", tag='h1')],
        [table.html_text("Crude arbs", style="font-family:Calibri;", tag='h2')],
        [generate_curve('Asia crude arb'), generate_curve('Nsea crude set')],
        [generate_evolution('Asia crude arb'), generate_evolution('Nsea crude set')],
        [table.html_text("EU/Asia Margins", style="font-family:Calibri;", tag='h2')],
        [generate_curve('Sing margin set'), generate_curve('NWE margin set')],
        [generate_evolution('Sing margin set'), generate_evolution('NWE margin set')],
        [table.html_text("Diesel arbs", style="font-family:Calibri;", tag='h2')],
        [generate_curve('Asian ULSD arb'), generate_curve('Gulf coast ULSD arb')],
        [generate_evolution('Asian ULSD arb'), generate_evolution('Gulf coast ULSD arb')],
        [table.html_text("Gasoline/Naphtha", style="font-family:Calibri;", tag='h2')],
        [generate_curve('Gasoline'), generate_curve('Naphtha')],
        [generate_evolution('Gasoline'), generate_evolution('Naphtha')],
    ]

    table.to_html(
        figs,
        f"{html_path}\\oil\\arbs.html", task_name="RV oil arbs"
    )
