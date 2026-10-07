import pandas as pd
import numpy as np
import datetime as dt
import sys
import os
import getpass
import PyPDF2
import re
from pandas.tseries.offsets import BDay
import ecm.cmds.data as dv
from ecm.cmds.cdr import today
import ecm.cmds.pyg as pyg
import ecm.cmds.time_series as ts
import ecm.cmds.utils as ut
from functools import partial
import ecm.cmds.bbg as bbg
from ecm.cmds.utils import convert_path_to_linux
from pyg_mongo import *
from pyg_cell import *
from ecm.cmds.config import url, root_path

report_name = "Save Platts and BBG oil price"
file_name = "save_platts_bbg"  # without .py
file_path = f"{root_path}\\autoreports\\reports\\oil\\{file_name}.py"
if sys.platform.startswith("win"):
    os.environ["GRPC_DEFAULT_SSL_ROOTS_FILE_PATH"] = r"C:\local\certs\root.crt"
    os.environ["REQUESTS_CA_BUNDLE"] = r"C:\local\certs\root.crt"
    os.environ["SSL_CERT_FILE"] = r"C:\local\certs\root.crt"
try:
    current_user = os.getlogin()
except OSError:
    current_user = getpass.getuser()


def _missing_photo_text(lines, *visible_fragments):
    raise NotImplementedError(f"Transcription gap in save_platts_bbg.py, photographed lines {lines}")


def add_schedule():
    """
    # schedule to run the report - only need to run once
    """
    sys.path.append(f"{root_path}\\autoreports\\schedule")
    from tasks import WinTaskPoC
    from ecm.atom.wintask.scheduler import ECMWinTask
    from ecm.atom.wintask.utils import Days
    win_task = ECMWinTask(
        days=Days.MONDAY | Days.TUESDAY | Days.WEDNESDAY | Days.THURSDAY | Days.FRIDAY | Days.SATURDAY,
        start_datetime=dt.datetime(2023, 7, 1, 4, 0), timezone="Europe/London",
        task_name=report_name,
        task=WinTaskPoC(name=f'"{report_name}"', filepath=f'"{file_path}"'),
        background_task=True,
        python_executable=r"C:\local\python\miniconda\envs\ecm_cmds\pythonw.exe")
    win_task.create_task()


platts_dict = {
    'Forties': ['PCRUFRT2 Index', 'AAGWZ00'],
    'Eko': ['PCRUEKO2 PLDP Index', 'AAGXB00'],
    'Urals': ['PCRUURD1 PLDP Index', 'AAGXJ00'],
    'CPC': ['PCRUTENG PLDP Index', 'AAHPL00'],
    'Saharan': ['PCRUSHBA PLDP Index', 'AAHPN00'],
    'Azeri': ['PCRUAZCF PLDP Index', 'AAHPM00'],
    'WTI Dlvd': ['NARI00EF PLDP Index', 'WMCRB00'],
    'Brent': ['PCRUBNBD PLDP Index', 'AAVJB00'],
    'Cash MEH': ['NARU000E PLDP Index', 'AAYRH00'],
    'WCS Ned': ['NARU001E PLDP Index', 'AAYAX00'],
    'WCS Cush': ['PCUC1002 PLDP Index', 'AAWTZ00'],
    'WTI USGC FOB': ['NARU0022 PLDP Index', 'AAYAZ00'],
    'Bonny': ['PCRUBLT2 PLDP Index', 'AAGXL00'],
    'Forcs': ['PCRUFOR2 PLDP Index', 'AAGXP00'],
    'Egina': ['NARI0114 PLDP Index', 'AFONB00'],
    'Hungo': ['PCRUHUNG PLDP Index', 'AASJF00'],
    'Dalia': ['PCRU1145 PLDP Index', 'AAQYY00'],
    'USGC Gasoline': ['NAUG006C PLDP Index', 'AANYX79'],
    'Group 3 Gasoline': ['NAUG00AE PLDP Index', 'AANYX02'],
    'NYH Gasoline': ['NAPN005C PLDP Index', 'AANYX15'],
    'ULSD_Pipe': ['NAUG0074 PLDP Index', 'ADIQA00'],
    'Group 3 disty': ['NAPI0006 Index', 'ADLAB00'],
    'NYH ULSD Barges': ['NAPN006E PLDP Index', 'ADIZA00'],
    'AlShaheen': ['PCRUAHDS Index', 'AAPEW00'],
    'Murban Dub': ['NARP0049 PLDP Index', 'AARBZ00'],
    'Sokol': ['PCRUSCDO PLDP Index', 'AASCK00'],
    'Tupi DES Qingdao': ['NARP0059 PLDP Index', 'LUQDD00'],
    'WTI DES Singapore': ['NARP005F PLDP Index', 'WTMSD00'],
    'Sing_gasoil': ['PASOGOSM PLDP Index', 'POAIC00'],
    'MOPJ Naphtha': ['PASONMOP PLDP Index', 'PAADI00'],
    '0.5 Marine': ['NACX0011 Index', 'FOFSB00'],
    '380 FO': ['PASOVMFO Index', 'PPXDL00'],
    'Jet FOB': ['PASOJKSM PLDP Index', 'PJACU00'],
    'VGO 0.5-0.6%': ['INFSVGOC Index', 'AAHMX00'],
    'VGO 2%': ['INFSVGOD Index', 'AAHNB00'],
    'Reformate': ['PLFUFS12 Index', 'AAXBC00'],
    'Reformate diff': ['INFSREFH Index', 'AAJMV00'],
    'Alkylate': ['PLFUFS10 Index', 'AAXBA00'],
    'Alkylata diff': ['PUSPGCAB Index', 'AAFIE00'],
    'Line space': ['NAUG004B Index', 'AAXTD00'],
    'Johan Sverdrup': ['NARI0118 Index', 'AJSVB00'],
    'Barge FP': ['PEURGONW Index', 'AAJUS00'],
    'CIF N.WE': ['PEURBG00 PLDP Index', 'AAVBG00'],
    'MED CIF': ['PEURM10C Index', 'AAWYZ00'],
    '50ppm': ['PEURG50B PLDP Index', 'AAUQC00'],
    'Jet CIF': ['PEURJKCC Index', 'PJAAU00'],
    '0.1 Barge': ['PEURG1FA PLDP Index', 'AAYWT00'],
    'NYH Jet diff': ['NAPN006A PLDP Index', 'ADIGA00'],
    'Sing Jet': ['PASOJKSG PLDP Index', 'PJABF00'],
    '10ppm Gasoil': ['PASOG10S PLDP Index', 'AAOVC00'],
    'MOPAG': ['LHAG0006 PLDP Index', 'AAIDU00'],
    'WCI': ['PASO1004 Index', 'AAQWN00'],
    'EBOB barges': ['PEUREBOB PLDP Index', 'AAQZV00'],
    'E10': ['LHEB001B PLDP Index', 'AGEFA00'],
    'EU MED CIF': ['PEURF10M Index', 'AAWZA00'],
    'Nap': ['PEURNPHY PLDP Index', 'PAAAL00'],
    'EU Reformate': ['NAEB0001 Index', 'AAXPM00'],
    'Cycle 2': ['PUSPRGBP PLDP Index', 'AAELD00'],
    'Cycle 3': ['PUSPNFGU PLDP Index', 'AAELE00'],
    **_missing_photo_text("117-119: dictionary entries absent between photographs"),
    '95 ron': ['PASOMGCS PLDP Index', 'PGAEZ00'],
    'Platts WTI delivered': ['NARI0125 Index', 'WMCRB00'],
    'Oman': ['NARP0073 Index', 'DBDOC00'],
    'Dubai Cash': ['NARP0079 Index', 'DBDDC00'],
    'Upper Zakum': ['NARP0077 Index', 'DBDUZ00'],
    'Mars': ['PCUCMRD1 Index', 'AAGWH00'],
    'WTI FOB': ['NARI0148 PLDP Index', 'ALNDB00'],
    'CFD 1wk': ['PCRUBCD1 PLRT Index', 'PCAKA00'],
    'CFD 2wk': ['PCRUBCD2 PLRT Index', 'PCAKC00'],
    'CFD 3wk': ['PCRUBCD3 PLRT Index', 'PCAKE00'],
    'CFD 4wk': ['PCRUBCD4 PLRT Index', 'PCAKG00'],
    'CFD 5wk': ['PCRUBCD5 PLRT Index', 'AAGLU00'],
    'CFD 6wk': ['PCRUBCD6 PLRT Index', 'AAGLV00'],
    'CFD 7wk': ['PCRUBCD7 PLRT Index', 'AALCZ00'],
    'CFD 8wk': ['PCRUBCD8 PLRT Index', 'AALDA00'],
    'NWE 3.5% Fuel Oil': ['PEUR35RF PLRT Index', 'PUABC00'],
    'NWE 1% Fuel Oil': ['PEURN6FR PLRT Index', 'PUAAP00'],
    'Spot Dated Brent': ['PCRUDTB1 PLRT Index', 'PCAAS00'],
    'USGC 3% Fuel Oil': ['PLRDG630 PLRT Index', 'PUAFZ00'],
    'USGC ULSD': ['PUSOPIPE PLRT Index', 'AATGY00'],
    'Ent Mt Belvieu Gasoline': ['LHLG0011 PLRT Index', 'AAWUG00'],
    'USGC Jet': ['PUSP54AF PLRT Index', 'AAELU00'],
    'Mt Belvieu Propane': ['PLLGPRMB PLRT Index', 'PMAAY00'],
    'LLS': ['PCUCLSJ1 PLRT Index', 'PCABN00'],
    'Mars Blend': ['PCUCMC1M PLRT Index', 'AAPYU00'],
    'Sing 3.5% FO': ['PASOSPFO PLRT Index', 'PPXDK00'],
    'Sing Naphtha': ['PASONAPS PLRT Index', 'PAAAP00'],
    'Sing 92 Ron': ['PASORO15 PLRT Index', 'AAXEQ00'],
    'Sing 50ppm': ['PASOCPGO PLRT Index', 'AAPPF00'],
    'Dubai 1st month': ['PCRUDUB1 PLRT Index', 'PCAAT00'],
    'NYH ULSD': ['PUSONYHB PLDP Index', 'AATGX00'],
    'Group 3 ULSD': ['PUSPUL3P PLDP Index', 'AATHB00'],
    'NYH Jet': ['PUSPJKNB PLDP Index', 'PJAAW00'],
    'USGC RBOB 83.7': ['PUSRHOPP PLDP Index', 'AAMFB00'],
    'NY Unl RBOB': ['PUSRNYUB PLDP Index', 'AAMGV00'],
    'Group 3 Prem Unl': ['PUSPG3PR PLDP Index', 'PGABD00'],
    'Linden outright': ['NAPN004D PLDP Index', 'ACXPW00'],
    'Marine NWE': ['NAEB0011 PLDP Index', 'PUMFD00'],
    'Marine USGC': ['NAUZ0001 PLDP Index', 'AUGMA00'],
    'Marine Sing': ['NACX0005 PLDP Index', 'AMFSA00'],
}

bbg_dict = {
    'Paper Midland': 'FFA1 Comdty',
    'paper MEH': 'HRT1 Comdty',
    'Mars': 'USCSMARS Index',
    'BLS Link': 'BKCUM1 LINK Index',
    'Bakken USGC Link': 'BKGCM1 LINK Index',
    'Nio Link': 'NBCCM1 LINK Index',
    'MEH Link': 'WMEHSPOT LINK Index',
    'Middy Link': 'PWTMSPOT LINK Index',
    'MEH BBG': 'USCSMEHC Index',
    'Midland BBG': 'USCSWTIM Index',
    'DJ WhiteCliffs Link': 'WCCDM1 LINK Index',
    'Spot VLCC': 'D27WAGJP GALB Index',
    'Spot AFRA': 'D08WCRUK GALB Index',
    'Bakken': 'BKCUSPOT LINK Index',
    'SaddleHorn': 'PSHCM1 LINK Index',
    'MEH': 'WMEHM1 LINK Index',
    'WCS Cush': 'WC1DM1 LINK Index',
    'WTI Cash Link': 'LNKSCASH LINK Index',
    'WTI Ex-Basin Link': 'LNKSWTXB LINK Index',
    'WTI Midland Link': 'LNKSMDSW LINK Index',
    'WTI MEH Link': 'LNKSMEHS LINK Index',
    'WTI Bakken Link': 'LNKSBGUL LINK Index',
    'WTI Corpus Link': 'LNKSWTCC LINK Index',
    'Bakken Light Link': 'LNKSBCUS LINK Index',
    'Niobrara Link': 'LNKSNIOB LINK Index',
    'Saddlehorn Link': 'PSHLBOM LINK Index',
    'White Cliffs Link': 'LNKSWCLF LINK Index',
    'Mars Link': 'LNKSMARS LINK Index',
    'WCS Link': 'LNKSWCSG LINK Index',
}


def get_platts_price(file_name="OPR_20220425.pdf"):
    platts_list = []
    dt_str = dt.datetime.strptime(file_name.split(".")[0][-8:], "%Y%m%d").strftime("%b %#d")
    for key, val in platts_dict.items():
        if val[1] not in platts_list:
            platts_list.append(val[1])
        if val[1] == 'AAXER00':
            platts_list.append('PAAAQ00')
    platts_file = f"{root_path}\\data\\platts\\files"
    file = open(convert_path_to_linux(platts_file + "\\" + file_name), 'rb')
    fileReader = PyPDF2.PdfFileReader(file)
    n = fileReader.numPages
    df = pd.Series(np.nan, index=platts_list)
    for i in range(n):
        s = fileReader.getPage(i).extractText()
        for key in platts_list:
            try:
                loc = re.search(key, s).span()[1]
            except:
                loc = 0
            if loc > 0 and s[loc] not in [')'] and re.search("Five-Day Rolling Averages", s) is None and \
                    re.search(dt_str, s) is not None:
                if key == 'AAJUS00':
                    print(key)
                raw = s[loc + 1:loc + 17]
                raw_list = raw.split(' ')
                for idx, j in enumerate(raw_list):
                    if len(j) > 2:
                        if '/' in j:
                            if j[:2] == 'NA':
                                df[key] = np.nan
                                break
                            else:
                                try:
                                    df[key] = (float(j.split('/')[0]) + float(j.split('/')[1])) / 2
                                    break
                                except:
                                    df[key] = np.nan
                        elif 'Œ' in j:
                            if j.split('Œ')[0] == 'NA':
                                df[key] = np.nan
                            else:
                                df[key] = (float(j.split('Œ')[0]) + float(j.split('Œ')[1])) / 2
                            break
                        elif '-' in j:
                            try:
                                df[key] = (float(j.split('-')[0]) + float(j.split('-')[-1])) / 2
                                break
                            except:
                                if j[-1] == '-':
                                    try:
                                        df[key] = (float(j.split('-')[0]) + float(raw_list[idx + 1])) / 2
                                    except:
                                        df[key] = float(j.split('-')[0])
                                    break
                        else:
                            if 'NA' in j:
                                df[key] = np.nan
                                break
                            else:
                                try:
                                    df[key] = float(re.sub("[^\d\.\-]", "", j))
                                    break
                                except:
                                    print(j)
                                    pass
    return df


def get_price_from_pdf():
    platts_folder = f"{root_path}\\data\\platts"
    pdf_folder = f"{root_path}\\data\\platts\\files"
    sdate_pdf = ut.find_latest_file_date(pdf_folder, date_format="%Y%m%d")
    if os.path.exists(convert_path_to_linux(f"{platts_folder}\\platts_price.csv")):
        df = ts.read_csv(f"{platts_folder}\\platts_price.csv", index_name="date")
        sdate = df.index[-1]
    else:
        df = pd.DataFrame()
        sdate = dt.datetime(2022, 3, 27)
    if sdate < sdate_pdf:
        run_dates = pd.bdate_range(sdate + BDay(1), today() - BDay(1))
        cols = list(set([x[1] for x in platts_dict.values()]))
        df1 = pd.DataFrame(0.0, index=run_dates, columns=cols)
        for j in run_dates:
            print(j)
            try:
                price = get_platts_price(file_name=f"OPR_{dt.datetime.strftime(j, '%Y%m%d')}.pdf")
            except:
                price = pd.Series(np.nan, index=cols)
            if isinstance(price, pd.Series):
                for idx, p in price.items():
                    df1.loc[j, idx] = p
            elif isinstance(price, pd.DataFrame):
                for idx, p in price.iterrows():
                    df1.loc[:, idx] = p
        try:
            df1['AAXER00'] = df1['PAAAP00'] - df1['PAAAQ00']
        except:
            return 0
        df = pd.concat([df.loc[:sdate, :], df1], axis=0)
        df.index.name = 'date'
        df.to_csv(f"{platts_folder}\\platts_price.csv")


def get_price_from_pdf_new():
    platts_folder = f"{root_path}\\data\\platts"
    pdf_folder = f"{root_path}\\data\\platts\\files"
    sdate_pdf = ut.find_latest_file_date(pdf_folder, date_format="%Y%m%d")
    if os.path.exists(convert_path_to_linux(f"{platts_folder}\\platts_price_new.csv")):
        df = ts.read_csv(f"{platts_folder}\\platts_price_new.csv", index_name="date")
        sdate = df.index[-1]
    else:
        df = pd.DataFrame()
        sdate = dt.datetime(2022, 3, 27)
    if sdate < sdate_pdf:
        run_dates = pd.bdate_range(sdate + BDay(1), today() - BDay(1))
        cols = list(set([x[1] for x in platts_dict.values()]))
        df1 = pd.DataFrame(0.0, index=run_dates, columns=cols)
        for j in run_dates:
            print(j)
            try:
                price = get_platts_price(file_name=f"OPR_{dt.datetime.strftime(j, '%Y%m%d')}.pdf")
            except:
                price = pd.Series(np.nan, index=cols)
            if isinstance(price, pd.Series):
                for idx, p in price.items():
                    df1.loc[j, idx] = p
            elif isinstance(price, pd.DataFrame):
                for idx, p in price.iterrows():
                    df1.loc[:, idx] = p
        df = pd.concat([df.loc[:sdate, :], df1], axis=0)
        df.index.name = 'date'
        df.to_csv(f"{platts_folder}\\platts_price_new.csv")


def update_platts_price():
    db = partial(mongo_table, db='data', table='platts', url=url, pk=['name', 'ticker', 'platts_ticker'])
    for k, v in platts_dict.items():
        try:
            c = pyg.get_cell(db, ticker=v[0], platts_ticker=v[1])
        except:
            try:
                data = pd.read_csv(convert_path_to_linux(_missing_photo_text("344: path/template suffix", '\\\\elementcapital.corp\\ecns01\\PM\\Michel Kikano\\Data\\market_', v[0])))
            except:
                data = pd.read_csv(convert_path_to_linux(_missing_photo_text("348: path/template suffix", '\\\\elementcapital.corp\\ecns01\\PM\\Michel Kikano\\Data\\market_', v[1])))
            data = data.set_index("date")
            data.index = pd.to_datetime(data.index)
            data.columns = ["PX_LAST"]
            c = periodic_cell(function=bbg.get_platts, ticker=v[0], platts_ticker=v[1],
                              sdate=data.index[0], edate=None, data=data,
                              csv_file=convert_path_to_linux(f"{root_path}\\data\\platts\\platts_price.csv"),
                              name=k, db=db, period='3n')
        c.go()


def replace_platts_price(platts_dict):
    db = partial(mongo_table, db='data', table='platts', url=url, pk=['name', 'ticker', 'platts_ticker'])
    for k, v in platts_dict.items():
        try:
            c = pyg.get_cell(db, ticker=v[0], platts_ticker=v[1])
            db().inc(_id=c._id).drop()
        except:
            pass
        try:
            data = pd.read_csv(convert_path_to_linux(_missing_photo_text("376: path/template suffix", '\\\\elementcapital.corp\\ecns01\\PM\\Michel Kikano\\Data\\market_scan', v[0])))
        except:
            data = pd.read_csv(convert_path_to_linux(_missing_photo_text("380: path/template suffix", '\\\\elementcapital.corp\\ecns01\\PM\\Michel Kikano\\Data\\market_scan', v[1])))
        data = data.set_index("date")
        data.index = pd.to_datetime(data.index)
        data.columns = ["PX_LAST"]
        c = periodic_cell(function=bbg.get_platts, ticker=v[0], platts_ticker=v[1],
                          sdate=data.index[0], edate=None, data=data,
                          csv_file=convert_path_to_linux(f"{root_path}\\data\\platts\\platts_price.csv"),
                          name=k, db=db, period='3n')
        c.go()


def update_bbg_price():
    db = partial(mongo_table, db='data', table='platts', url=url, pk=['name', 'ticker', 'platts_ticker'])
    for k, v in bbg_dict.items():
        try:
            c = pyg.get_cell(db, name=k, ticker=v, platts_ticker=None)
        except:
            try:
                data = pd.read_csv(convert_path_to_linux(_missing_photo_text("406: path/template suffix", '\\\\elementcapital.corp\\ecns01\\PM\\Michel Kikano\\Data\\market_', v)))
                data = data.set_index("date")
                data.index = pd.to_datetime(data.index)
                data.columns = ["PX_LAST"]
                sdate = data.index[0]
            except:
                data = None
                sdate = dt.datetime(2010, 1, 1)
            c = periodic_cell(function=bbg.bdh_update, ticker=v, platts_ticker=None,
                              fields=["PX_LAST"], sdate=sdate, edate=None, data=data,
                              name=k, db=db, period='3n')
        c.go()


def update():
    get_price_from_pdf()
    update_platts_price()
    update_bbg_price()


def get_bbg_ticker():
    ticker_list = []
    for k, v in platts_dict.items():
        ticker_list.append(v[0])
    for k, v in bbg_dict.items():
        ticker_list.append(v)
    ticker_df = pd.Series(ticker_list)


if __name__ == "__main__":
    update()
