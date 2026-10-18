import datetime as dt
import math
import re
import typing as tp

import ecm.cmds.core.bbg_blp as bbg
import pandas as pd
from dateutil.relativedelta import relativedelta
from dateutil.rrule import MONTHLY
from dateutil.rrule import rrule
from dateutil.rrule import WE
from ecm.cmds.core.cdr import CDR
from ecm.cmds.core.cdr import month_str2int
from ecm.cmds.core.cdr import now_ldn
from ecm.cmds.core.cdr import today
from ecm.cmds.core.schema import _gen_uuid
from ecm.cmds.core.schema import MarketScanTickerConfig
from ecm.cmds.core.schema import MarketScanWatchlistLive
from ecm.cmds.core.schema import SharpeRatio
from ecm.cmds.core.sql import L025DB
from ecm.cmds.core.utils import get_rows_to_upsert
from loguru import logger as log

default_name_dict = {
    "ESA Index": ("EQT", "TICKER", "FLAT", 1, 1),
    "NQA Index": ("EQT", "TICKER", "FLAT", 1, 1),
    "RTYA Index": ("EQT", "TICKER", "FLAT", 1, 1),
    "GXA Index": ("EQT", "TICKER", "FLAT", 1, 1),
    "VGA Index": ("EQT", "TICKER", "FLAT", 1, 1),
    "NKA Index": ("EQT", "TICKER", "FLAT", 1, 1),
    "MESA Index": ("EQT", "TICKER", "FLAT", 1, 1),
    "IFBA Index": ("EQT", "TICKER", "FLAT", 1, 1),
    "XUA Index": ("EQT", "TICKER", "FLAT", 1, 1),
    "MSZZCYDE Index": ("EQT", "TICKER", "FLAT", 1, 0),
    "MSEECYDE Index": ("EQT", "TICKER", "FLAT", 1, 0),
    "UXA Index": ("EQT", "TICKER", "FLAT", 1, 1),
    "ECA Curncy": ("CCY", "TICKER", "FLAT", 1, 1),
    "ADA Curncy": ("CCY", "TICKER", "FLAT", 1, 1),
    "JYA Curncy": ("CCY", "TICKER", "FLAT", 1, 1),
    "CDA Curncy": ("CCY", "TICKER", "FLAT", 1, 1),
    "DXA Curncy": ("CCY", "TICKER", "FLAT", 1, 1),
    "USDCNH Curncy": ("CCY", "COPY", "FLAT", 1, 0),
    "USDINR Curncy": ("CCY", "COPY", "FLAT", 1, 0),
    "USDBRL Curncy": ("CCY", "COPY", "FLAT", 1, 0),
    "USDRUB Curncy": ("CCY", "COPY", "FLAT", 1, 0),
    "FXJPEMCS Index": ("CCY", "COPY", "FLAT", 1, 0),
    "BTCA Curncy": ("CCY", "TICKER", "FLAT", 1, 1),
    "DCRA Curncy": ("CCY", "TICKER", "FLAT", 1, 1),
    "TUA Comdty": ("FI", "TICKER", "FLAT", 1, 1),
    "TYA Comdty": ("FI", "TICKER", "FLAT", 1, 1),
    "RXA Comdty": ("FI", "TICKER", "FLAT", 1, 1),
    "USGG2YR Index": ("FI", "COPY", "SPRD", 1, 0),
    "USGG5YR Index": ("FI", "COPY", "SPRD", 1, 0),
    "USGG10YR Index": ("FI", "COPY", "SPRD", 1, 0),
    "USGG5Y5Y Index": ("FI", "COPY", "SPRD", 1, 0),
    "USYC2Y10 Index": ("FI", "COPY", "SPRD", 1, 0),
    "USYC5Y30 Index": ("FI", "COPY", "SPRD", 1, 0),
    "USSWIT1 Curncy": ("FI", "COPY", "SPRD", 1, 0),
    "USSWIT2 Curncy": ("FI", "COPY", "SPRD", 1, 0),
    "USSWIT5 Curncy": ("FI", "COPY", "SPRD", 1, 0),
    "USSWIT10 Curncy": ("FI", "COPY", "SPRD", 1, 0),
    "FWISUS55 Index": ("FI", "COPY", "SPRD", 1, 0),
    ".USGGT1 Index": ("FI", "COPY", "SPRD", 1, 0),
    ".USGGT2 Index": ("FI", "COPY", "SPRD", 1, 0),
    ".USGGT5 Index": ("FI", "COPY", "SPRD", 1, 0),
    ".USGGT10 Index": ("FI", "COPY", "SPRD", 1, 0),
    "SFRA Comdty": ("FI", "TICKER", "FLAT", 1, 1),
    "SFR2 Comdty": ("FI", "CONTRACT", "FLAT", 1, 1),
    "SFR3 Comdty": ("FI", "CONTRACT", "FLAT", 1, 1),
    "SFR4 Comdty": ("FI", "CONTRACT", "FLAT", 1, 1),
    "GCA Comdty": ("PM", "TICKER", "FLAT", 1, 1),
    "SIA Comdty": ("PM", "TICKER", "FLAT", 1, 1),
    "PLA Comdty": ("PM", "TICKER", "FLAT", 1, 1),
    "PAA Comdty": ("PM", "TICKER", "FLAT", 1, 1),
    "GC 3M 100 VOL BVOL Comdty": ("PM", "COPY", "SPRD", 1, 0),
    "XAUUSD25R3M BGN Curncy": ("PM", "COPY", "SPRD", 1, 0),
    "AUAA Comdty": ("PM", "TICKER", "FLAT", 1, 1),
    "SAIA Comdty": ("PM", "TICKER", "FLAT", 1, 1),
    "GDX US Equity": ("PM", "COPY", "FLAT", 1, 1),
    "GDXJ US Equity": ("PM", "COPY", "FLAT", 1, 1),
    "COA Comdty": ("BRT", "TICKER", "FLAT", 1, 1),
    "CO2 Comdty": ("BRT", "CONTRACT", "FLAT", 1, 1),
    "CO3 Comdty": ("BRT", "CONTRACT", "FLAT", 1, 1),
    "CO4 Comdty": ("BRT", "CONTRACT", "FLAT", 0, 1),
    "CO6 Comdty": ("BRT", "CONTRACT", "FLAT", 0, 1),
    "CO12 Comdty": ("BRT", "CONTRACT", "FLAT", 0, 1),
    "CODEC1 Comdty": ("BRT", "FUT_CUR_GEN_TICKER", "FLAT", 1, 1),
    "CODEC2 Comdty": ("BRT", "FUT_CUR_GEN_TICKER", "FLAT", 1, 1),
    "COJUN1 Comdty": ("BRT", "FUT_CUR_GEN_TICKER", "FLAT", 0, 1),
    "S:COCO 2-6 Comdty": ("BRT", "CALSPRD", "SPRD", 1, 1),
    "CO 1st Spread": ("BRT", "CALCULATE", "SPRD", 1, 1),
    "CO 2nd Spread": ("BRT", "CALCULATE", "SPRD", 1, 1),
    "CO 3rd Spread": ("BRT", "CALCULATE", "SPRD", 1, 1),
    "CO Jun-Dec Spread": ("BRT", "CALCULATE", "SPRD", 1, 1),
    "CO Dec-Dec Spread": ("BRT", "CALCULATE", "SPRD", 1, 1),
    "CO 1M 100 VOL BVOL Comdty": ("BRT", "COPY", "SPRD", 1, 0),
    ".CO1MRR Index": ("BRT", "COPY", "SPRD", 1, 0),
    "SXEP Index": ("BRT", "COPY", "FLAT", 1, 0),
    "BWCHEM Index": ("BRT", "COPY", "FLAT", 1, 0),
    "SABIC AB Equity": ("BRT", "COPY", "FLAT", 1, 1),
    "SH000908 Index": ("BRT", "COPY", "FLAT", 1, 0),
    "DATA Comdty": ("BRT", "TICKER", "FLAT", 0, 1),
    "DAT2 Comdty": ("BRT", "CONTRACT", "FLAT", 1, 1),
    "DAT3 Comdty": ("BRT", "CONTRACT", "FLAT", 1, 1),
    "DAT4 Comdty": ("BRT", "CONTRACT", "FLAT", 1, 1),
    "DAT 1st Spread": ("BRT", "CALCULATE", "SPRD", 0, 1),
    "DAT 2nd Spread": ("BRT", "CALCULATE", "SPRD", 1, 1),
    "DAT 3rd Spread": ("BRT", "CALCULATE", "SPRD", 1, 1),
    "FDBSM1 Index": ("BRT", "COPY", "SPRD", 1, 0),
    "FDBSM2 Index": ("BRT", "COPY", "SPRD", 1, 0),
    "FDBSM3 Index": ("BRT", "COPY", "SPRD", 1, 0),
    "FNNSQ 1Q1 Index": ("BRT", "COPY", "SPRD", 1, 0),
    "FNOSQ 1Q1 Index": ("BRT", "COPY", "SPRD", 1, 0),
    "FSQCQ 1Q1 Index": ("BRT", "COPY", "SPRD", 1, 0),
    "FWJSQ 1Q1 Index": ("BRT", "COPY", "SPRD", 1, 0),
    "FROSQ 1Q1 Index": ("BRT", "COPY", "SPRD", 1, 0),
    "FDBDM1 Index": ("BRT", "COPY", "SPRD", 1, 0),
    "FDBDM2 Index": ("BRT", "COPY", "SPRD", 1, 0),
    "FDBDM3 Index": ("BRT", "COPY", "SPRD", 1, 0),
    "FDUSM1 Index": ("BRT", "COPY", "SPRD", 1, 0),
    "FDUSM2 Index": ("BRT", "COPY", "SPRD", 1, 0),
    "FDUSQ 1Q1 Index": ("BRT", "COPY", "SPRD", 1, 0),
    "MUCDAT Comdty": ("BRT", "COPY", "SPRD", 1, 0),
    "MUCDAT 2 Comdty": ("BRT", "OILSPRD", "SPRD", 1, 0),
    "MUCDAT 3 Comdty": ("BRT", "OILSPRD", "SPRD", 1, 0),
    "HWTCO Comdty": ("BRT", "COPY", "SPRD", 1, 0),
    "FJWHM1 Index": ("BRT", "COPY", "SPRD", 1, 0),
    "FJWHM2 Index": ("BRT", "COPY", "SPRD", 1, 0),
    "FSMCM1 Index": ("BRT", "COPY", "SPRD", 1, 0),
    "FSMCM2 Index": ("BRT", "COPY", "SPRD", 1, 0),
    "FSCDM1 Index": ("GASOLINE", "COPY", "SPRD", 1, 0),
    "FSCDM2 Index": ("GASOLINE", "COPY", "SPRD", 1, 0),
    "FSNOM1 Index": ("GASOLINE", "COPY", "SPRD", 1, 0),
    "FSNOM2 Index": ("GASOLINE", "COPY", "SPRD", 1, 0),
    "FSGAM1 Index": ("GASOLINE", "COPY", "SPRD", 1, 0),
    "FSGAM2 Index": ("GASOLINE", "COPY", "SPRD", 1, 0),
    "FSGCM1 Index": ("DIST", "COPY", "SPRD", 1, 0),
    "FSGCM2 Index": ("DIST", "COPY", "SPRD", 1, 0),
    "FSEUM1 Index": ("DIST", "COPY", "SPRD", 1, 0),
    "FSEUM2 Index": ("DIST", "COPY", "SPRD", 1, 0),
    "FSG1M1 Index": ("DIST", "COPY", "SPRD", 1, 0),
    "FSG1M2 Index": ("DIST", "COPY", "SPRD", 1, 0),
    "CLA Comdty": ("WTI", "TICKER", "FLAT", 1, 1),
    "CL2 Comdty": ("WTI", "CONTRACT", "FLAT", 1, 1),
    "CL3 Comdty": ("WTI", "CONTRACT", "FLAT", 1, 1),
    "CL4 Comdty": ("WTI", "CONTRACT", "FLAT", 0, 1),
    "CL6 Comdty": ("WTI", "CONTRACT", "FLAT", 0, 1),
    "CLDEC1 Comdty": ("WTI", "FUT_CUR_GEN_TICKER", "FLAT", 1, 1),
    "CLDEC2 Comdty": ("WTI", "FUT_CUR_GEN_TICKER", "FLAT", 1, 1),
    "CLJUN1 Comdty": ("WTI", "FUT_CUR_GEN_TICKER", "FLAT", 0, 1),
    "S:CLCL 2-6 Comdty": ("WTI", "CALSPRD", "SPRD", 1, 1),
    "CL 1st Spread": ("WTI", "CALCULATE", "SPRD", 1, 1),
    "CL 2nd Spread": ("WTI", "CALCULATE", "SPRD", 1, 1),
    "CL 3rd Spread": ("WTI", "CALCULATE", "SPRD", 1, 1),
    "CL Jun-Dec Spread": ("WTI", "CALCULATE", "SPRD", 1, 1),
    "CL Dec-Dec Spread": ("WTI", "CALCULATE", "SPRD", 1, 1),
    "CL 1M 100 VOL BVOL Comdty": ("WTI", "COPY", "SPRD", 1, 0),
    ".CL1MRR Index": ("WTI", "COPY", "SPRD", 1, 0),
    "ENCO 1st Spread": ("WTI", "CALCULATE", "SPRD", 1, 1),
    "ENCO 2nd Spread": ("WTI", "CALCULATE", "SPRD", 1, 1),
    "ENCO 3rd Spread": ("WTI", "CALCULATE", "SPRD", 1, 1),
    "ENCO Dec-Dec Spread": ("WTI", "CALCULATE", "SPRD", 1, 1),
    "XOP US Equity": ("WTI", "COPY", "FLAT", 1, 1),
    "XLE US Equity": ("WTI", "COPY", "FLAT", 1, 1),
    "OSX Index": ("WTI", "COPY", "FLAT", 1, 0),
    "CVX US Equity": ("WTI", "COPY", "FLAT", 1, 1),
    "VLO US Equity": ("WTI", "COPY", "FLAT", 1, 1),
    "PBF US Equity": ("WTI", "COPY", "FLAT", 1, 1),
    "PAA US Equity": ("WTI", "COPY", "FLAT", 1, 1),
    "ENB CN Equity": ("WTI", "COPY", "FLAT", 1, 1),
    "QSA Comdty": ("DIST", "TICKER", "FLAT", 1, 1),
    "QS2 Comdty": ("DIST", "CONTRACT", "FLAT", 1, 1),
    "QS3 Comdty": ("DIST", "CONTRACT", "FLAT", 0, 1),
    "QS4 Comdty": ("DIST", "CONTRACT", "FLAT", 0, 1),
    "QS6 Comdty": ("DIST", "CONTRACT", "FLAT", 0, 1),
    "QSDEC1 Comdty": ("DIST", "FUT_CUR_GEN_TICKER", "FLAT", 1, 1),
    "QSDEC2 Comdty": ("DIST", "FUT_CUR_GEN_TICKER", "FLAT", 1, 1),
    "S:QSQS 2-6 Comdty": ("DIST", "CALSPRD", "SPRD", 1, 1),
    "QS 1st Spread": ("DIST", "CALCULATE", "SPRD", 1, 1),
    "QS 2nd Spread": ("DIST", "CALCULATE", "SPRD", 1, 1),
    "QS 3rd Spread": ("DIST", "CALCULATE", "SPRD", 1, 1),
    "QS Quarter Spread": ("DIST", "CALCULATE", "SPRD", 1, 1),
    "QS Dec-Dec Spread": ("DIST", "CALCULATE", "SPRD", 1, 1),
    "HOA Comdty": ("DIST", "TICKER", "FLAT", 1, 1),
    "HO2 Comdty": ("DIST", "CONTRACT", "FLAT", 1, 1),
    "HO3 Comdty": ("DIST", "CONTRACT", "FLAT", 0, 1),
    "HO4 Comdty": ("DIST", "CONTRACT", "FLAT", 0, 1),
    "HO6 Comdty": ("DIST", "CONTRACT", "FLAT", 0, 1),
    "HODEC1 Comdty": ("DIST", "FUT_CUR_GEN_TICKER", "FLAT", 1, 1),
    "HODEC2 Comdty": ("DIST", "FUT_CUR_GEN_TICKER", "FLAT", 1, 1),
    "S:HOHO 2-6 Comdty": ("DIST", "CALSPRD", "SPRD", 1, 1),
    "HO 1st Spread": ("DIST", "CALCULATE", "SPRD", 1, 1),
    "HO 2nd Spread": ("DIST", "CALCULATE", "SPRD", 1, 1),
    "HO 3rd Spread": ("DIST", "CALCULATE", "SPRD", 1, 1),
    "HO Quarter Spread": ("DIST", "CALCULATE", "SPRD", 1, 1),
    "HO Dec-Dec Spread": ("DIST", "CALCULATE", "SPRD", 1, 1),
    "HOCL 1st Spread": ("DIST", "CALCULATE", "SPRD", 1, 1),
    "HOCL 2nd Spread": ("DIST", "CALCULATE", "SPRD", 1, 1),
    "FVHRM 1st Spread": ("DIST", "COSPREAD", "SPRD", 1, 1),
    "FVHRM 6th Spread": ("DIST", "COSPREAD", "SPRD", 1, 1),
    "FVHRM 12th Spread": ("DIST", "COSPREAD", "SPRD", 1, 1),
    "XBA Comdty": ("GASOLINE", "TICKER", "FLAT", 1, 1),
    "XB2 Comdty": ("GASOLINE", "CONTRACT", "FLAT", 1, 1),
    "XB3 Comdty": ("GASOLINE", "CONTRACT", "FLAT", 0, 1),
    "XB4 Comdty": ("GASOLINE", "CONTRACT", "FLAT", 0, 1),
    "XB5 Comdty": ("GASOLINE", "CONTRACT", "FLAT", 0, 1),
    "XB6 Comdty": ("GASOLINE", "CONTRACT", "FLAT", 0, 1),
    "S:XBXB 2-6 Comdty": ("GASOLINE", "CALSPRD", "SPRD", 1, 1),
    "XB 1st Spread": ("GASOLINE", "CALCULATE", "SPRD", 1, 1),
    "XB 2nd Spread": ("GASOLINE", "CALCULATE", "SPRD", 1, 1),
    "XB 3rd Spread": ("GASOLINE", "CALCULATE", "SPRD", 1, 1),
    "XB 4th Spread": ("GASOLINE", "CALCULATE", "SPRD", 1, 1),
    "XB 5th Spread": ("GASOLINE", "CALCULATE", "SPRD", 1, 1),
    "XBCL 1st Spread": ("GASOLINE", "CALCULATE", "SPRD", 1, 1),
    "XBCL 2nd Spread": ("GASOLINE", "CALCULATE", "SPRD", 1, 1),
    "FVXRM 1st Spread": ("GASOLINE", "COSPREAD", "SPRD", 1, 1),
    "FVXRM 6th Spread": ("GASOLINE", "COSPREAD", "SPRD", 1, 1),
    "XBHO 1st Spread": ("GASOLINE", "CALCULATE", "SPRD", 1, 1),
    "XBHO 2nd Spread": ("GASOLINE", "CALCULATE", "SPRD", 1, 1),
    "XBHO 3rd Spread": ("GASOLINE", "CALCULATE", "SPRD", 1, 1),
    "IHWA Comdty": ("GASOLINE", "TICKER", "FLAT", 0, 1),
    "IHW2 Comdty": ("GASOLINE", "CONTRACT", "FLAT", 1, 1),
    "IHW3 Comdty": ("GASOLINE", "CONTRACT", "FLAT", 1, 1),
    "IHW4 Comdty": ("GASOLINE", "CONTRACT", "FLAT", 0, 1),
    "IHW 1st Spread": ("GASOLINE", "CALCULATE", "SPRD", 0, 1),
    "IHW 2nd Spread": ("GASOLINE", "CALCULATE", "SPRD", 1, 1),
    "IHW 3rd Spread": ("GASOLINE", "CALCULATE", "SPRD", 1, 1),
    "NGA Comdty": ("HH", "TICKER", "FLAT", 1, 1),
    "NG2 Comdty": ("HH", "CONTRACT", "FLAT", 1, 1),
    "NG3 Comdty": ("HH", "CONTRACT", "FLAT", 1, 1),
    "NG4 Comdty": ("HH", "CONTRACT", "FLAT", 1, 1),
    "NG5 Comdty": ("HH", "CONTRACT", "FLAT", 0, 1),
    "NG6 Comdty": ("HH", "CONTRACT", "FLAT", 0, 1),
    "S:NGNG 2-6 Comdty": ("HH", "CALSPRD", "SPRD", 1, 1),
    "NG 1st Spread": ("HH", "CALCULATE", "SPRD", 1, 1),
    "NG 2nd Spread": ("HH", "CALCULATE", "SPRD", 1, 1),
    "NG 3rd Spread": ("HH", "CALCULATE", "SPRD", 1, 1),
    "NGOCT1 Comdty": ("HH", "FUT_CUR_GEN_TICKER", "FLAT", 0, 1),
    "NG Oct-Jan Spread": ("HH", "CALCULATE", "SPRD", 1, 1),
    "NG 1M 100 VOL BVOL Comdty": ("HH", "COPY", "SPRD", 1, 0),
    ".NG1MRR Index": ("HH", "COPY", "SPRD", 1, 0),
    "FSNGY 23 Index": ("HH", "ROLLYEAR", "FLAT", 1, 0),
    "FSNGY 24 Index": ("HH", "ROLLYEAR+1", "FLAT", 1, 0),
    "FSNGY 25 Index": ("HH", "ROLLYEAR+2", "FLAT", 1, 0),
    "FSNGY 26 Index": ("HH", "ROLLYEAR+3", "FLAT", 1, 0),
    "FSNGS SU23 Index": ("HH", "ROLLYEAR", "FLAT", 1, 0),
    "FSNGS SU24 Index": ("HH", "ROLLYEAR+1", "FLAT", 1, 0),
    "FSNGS SU25 Index": ("HH", "ROLLYEAR+2", "FLAT", 1, 0),
    "FSNGS WI2223 Index": ("HH", "ROLLYEAR", "FLAT", 1, 0),
    "FSNGS WI2324 Index": ("HH", "ROLLYEAR+1", "FLAT", 1, 0),
    "FSNGS WI2425 Index": ("HH", "ROLLYEAR+2", "FLAT", 1, 0),
    "CTIA Comdty": ("HH", "TICKER", "FLAT", 1, 1),
    "XNG Index": ("HH", "COPY", "FLAT", 1, 0),
    "LNG US Equity": ("HH", "COPY", "FLAT", 1, 1),
    ".DRY_E&P Index": ("HH", "COPY", "FLAT", 1, 0),
    "FN3PM1 Index": ("HH", "COPY", "FLAT", 1, 0),
    "FN3PM2 Index": ("HH", "COPY", "FLAT", 1, 0),
    "FN3PM3 Index": ("HH", "COPY", "FLAT", 1, 0),
    "FN3PQ1 Index": ("HH", "COPY", "FLAT", 1, 0),
    "FN3PQ2 Index": ("HH", "COPY", "FLAT", 1, 0),
    "FN3PQ3 Index": ("HH", "COPY", "FLAT", 1, 0),
    "FN3PY1 Index": ("HH", "COPY", "FLAT", 1, 0),
    "FN3PY2 Index": ("HH", "COPY", "FLAT", 1, 0),
    "FN3PY3 Index": ("HH", "COPY", "FLAT", 1, 0),
    "FN3PY4 Index": ("HH", "COPY", "FLAT", 1, 0),
    "PJMF1MON Index": ("HH", "COPY", "FLAT", 1, 0),
    "PJMF2MON Index": ("HH", "COPY", "FLAT", 1, 0),
    "PJMF3MON Index": ("HH", "COPY", "FLAT", 1, 0),
    "PJMFQ1 Index": ("HH", "COPY", "FLAT", 1, 0),
    "PJMFQ2 Index": ("HH", "COPY", "FLAT", 1, 0),
    "PJMFQ3 Index": ("HH", "COPY", "FLAT", 1, 0),
    "PJMFY 24 Index": ("HH", "ROLLYEAR", "FLAT", 1, 0),
    "PJMFY 25 Index": ("HH", "ROLLYEAR+1", "FLAT", 1, 0),
    "PJMFY 26 Index": ("HH", "ROLLYEAR+2", "FLAT", 1, 0),
    "TZTA Comdty": ("TTF", "TICKER", "FLAT", 1, 1),
    "TZT2 Comdty": ("TTF", "CONTRACT", "FLAT", 1, 1),
    "TZT3 Comdty": ("TTF", "CONTRACT", "FLAT", 0, 1),
    "TZT4 Comdty": ("TTF", "CONTRACT", "FLAT", 0, 1),
    "TZT 1st spread": ("TTF", "CALCULATE", "SPRD", 1, 1),
    "TZT 2nd spread": ("TTF", "CALCULATE", "SPRD", 1, 1),
    "TZT 3rd spread": ("TTF", "CALCULATE", "SPRD", 1, 1),
    "QZTA Comdty": ("TTF", "TICKER", "FLAT", 1, 1),
    "QZT2 Comdty": ("TTF", "CONTRACT", "FLAT", 1, 1),
    "QZT3 Comdty": ("TTF", "CONTRACT", "FLAT", 0, 1),
    "QZT 1st spread": ("TTF", "CALCULATE", "SPRD", 1, 1),
    "QZT 2nd spread": ("TTF", "CALCULATE", "SPRD", 1, 1),
    "QQTA Comdty": ("TTF", "TICKER", "FLAT", 1, 1),
    "QQT2 Comdty": ("TTF", "CONTRACT", "FLAT", 0, 1),
    "QQT3 Comdty": ("TTF", "CONTRACT", "FLAT", 0, 1),
    "QQT 1st spread": ("TTF", "CALCULATE", "SPRD", 1, 1),
    "QQT 2nd spread": ("TTF", "CALCULATE", "SPRD", 1, 1),
    "QTTA Comdty": ("TTF", "TICKER", "FLAT", 1, 1),
    "QTT2 Comdty": ("TTF", "CONTRACT", "FLAT", 1, 1),
    "QTT3 Comdty": ("TTF", "CONTRACT", "FLAT", 1, 1),
    "QTT4 Comdty": ("TTF", "CONTRACT", "FLAT", 1, 1),
    "QTT 1st spread": ("TTF", "CALCULATE", "SPRD", 1, 1),
    "FJS 1M 100 VOL BVOL Comdty": ("TTF", "COPY", "SPRD", 1, 0),
    ".FJS1MRR Index": ("TTF", "COPY", "SPRD", 1, 0),
    "MOA Comdty": ("TTF", "TICKER", "FLAT", 1, 1),
    "XAA Comdty": ("TTF", "TICKER", "FLAT", 1, 1),
    "XEA Comdty": ("TTF", "TICKER", "FLAT", 1, 1),
    "TMA Comdty": ("TTF", "TICKER", "FLAT", 1, 1),
    "EQNR NO Equity": ("TTF", "COPY", "FLAT", 1, 1),
    "GAZP RM Equity": ("TTF", "COPY", "FLAT", 1, 1),
    "GERW1WYY Comdty": ("TTF", "WEEKLY", "FLAT", 1, 1),
    "GERW2WYY Comdty": ("TTF", "WEEKLY", "FLAT", 1, 1),
    "GER1W Comdty": ("TTF", "COPY", "FLAT", 1, 1),
    "GER2W Comdty": ("TTF", "COPY", "FLAT", 1, 1),
    "GER3W Comdty": ("TTF", "COPY", "FLAT", 1, 1),
    "GER4W Comdty": ("TTF", "COPY", "FLAT", 1, 1),
    "GER5W Comdty": ("TTF", "COPY", "FLAT", 1, 1),
    "DETA Comdty": ("TTF", "TICKER", "FLAT", 1, 1),
    "DET2 Comdty": ("TTF", "CONTRACT", "FLAT", 1, 1),
    "JXTA Comdty": ("TTF", "TICKER", "FLAT", 1, 1),
    "JXT2 Comdty": ("TTF", "CONTRACT", "FLAT", 1, 1),
    "JXT 1st spread": ("TTF", "CALCULATE", "SPRD", 1, 1),
    "JXYA Comdty": ("TTF", "TICKER", "FLAT", 1, 1),
    "JXY2 Comdty": ("TTF", "CONTRACT", "FLAT", 1, 1),
    "JXY3 Comdty": ("TTF", "CONTRACT", "FLAT", 1, 1),
    "JXY 1st spread": ("TTF", "CALCULATE", "SPRD", 1, 1),
    "ELFBDAHD Index": ("TTF", "COPY", "FLAT", 1, 0),
    "FIB2W Comdty": ("TTF", "COPY", "FLAT", 1, 0),
    "FIB3W Comdty": ("TTF", "COPY", "FLAT", 1, 0),
    "FACA Comdty": ("TTF", "TICKER", "FLAT", 1, 1),
    "FAC2 Comdty": ("TTF", "CONTRACT", "FLAT", 1, 1),
    "FAC3 Comdty": ("TTF", "CONTRACT", "FLAT", 1, 1),
    "FABA Comdty": ("TTF", "TICKER", "FLAT", 1, 1),
    "FAB2 Comdty": ("TTF", "CONTRACT", "FLAT", 1, 1),
    "FAB3 Comdty": ("TTF", "CONTRACT", "FLAT", 1, 1),
    "FAB4 Comdty": ("TTF", "CONTRACT", "FLAT", 1, 1),
    "FAAA Comdty": ("TTF", "TICKER", "FLAT", 1, 1),
    "FAA2 Comdty": ("TTF", "CONTRACT", "FLAT", 1, 1),
    "FAA3 Comdty": ("TTF", "CONTRACT", "FLAT", 1, 1),
    "HGA Comdty": ("BM", "TICKER", "FLAT", 1, 1),
    "HG2 Comdty": ("BM", "CONTRACT", "FLAT", 0, 1),
    "HG3 Comdty": ("BM", "CONTRACT", "FLAT", 0, 1),
    "HG 1st Spread": ("BM", "CALCULATE", "SPRD", 1, 1),
    "HG 2nd Spread": ("BM", "CALCULATE", "SPRD", 1, 1),
    "LMCADS03 Comdty": ("BM", "TICKER", "FLAT", 1, 1),
    "LMAHDS03 Comdty": ("BM", "TICKER", "FLAT", 1, 1),
    "LMNIDS03 Comdty": ("BM", "TICKER", "FLAT", 1, 1),
    "LMZSDS03 Comdty": ("BM", "TICKER", "FLAT", 1, 1),
    "LMSNDS03 Comdty": ("BM", "TICKER", "FLAT", 1, 1),
    "LMPBDS03 Comdty": ("BM", "TICKER", "FLAT", 1, 1),
    "LMCADS Comdty": ("BM", "TICKER", "FLAT", 1, 1),
    "LMAHDS Comdty": ("BM", "TICKER", "FLAT", 1, 1),
    "LMZSDS Comdty": ("BM", "TICKER", "FLAT", 1, 1),
    "LMNIDS Comdty": ("BM", "TICKER", "FLAT", 1, 1),
    "LMCADS 03Z24 Comdty": ("BM", "COPY", "SPRD", 1, 1),
    "LMCADS Z24Z25 Comdty": ("BM", "COPY", "SPRD", 1, 1),
    "LMCADS 1st Spread": ("BM", "LMESPREAD", "SPRD", 1, 1),
    "LMCADS 2nd Spread": ("BM", "LMESPREAD", "SPRD", 1, 1),
    "LMCADS 3rd Spread": ("BM", "LMESPREAD", "SPRD", 1, 1),
    "LMAHDS 03Z24 Comdty": ("BM", "COPY", "SPRD", 1, 1),
    "LMAHDS Z24Z24 Comdty": ("BM", "COPY", "SPRD", 1, 1),
    "LMAHDS 1st Spread": ("BM", "LMESPREAD", "SPRD", 1, 1),
    "LMAHDS 2nd Spread": ("BM", "LMESPREAD", "SPRD", 1, 1),
    "LMAHDS 3rd Spread": ("BM", "LMESPREAD", "SPRD", 1, 1),
    "LMZSDS 03Z24 Comdty": ("BM", "COPY", "SPRD", 1, 1),
    "LMZSDS Z24Z25 Comdty": ("BM", "COPY", "SPRD", 1, 1),
    "LMZSDS 1st Spread": ("BM", "LMESPREAD", "SPRD", 1, 1),
    "LMZSDS 2nd Spread": ("BM", "LMESPREAD", "SPRD", 1, 1),
    "LMZSDS 3rd Spread": ("BM", "LMESPREAD", "SPRD", 1, 1),
    "LMNIDS 03Z24 Comdty": ("BM", "COPY", "SPRD", 1, 1),
    "LMNIDS Z24Z25 Comdty": ("BM", "COPY", "SPRD", 1, 1),
    "LMNIDS 1st Spread": ("BM", "LMESPREAD", "SPRD", 1, 1),
    "LMNIDS 2nd Spread": ("BM", "LMESPREAD", "SPRD", 1, 1),
    "LMNIDS 3rd Spread": ("BM", "LMESPREAD", "SPRD", 1, 1),
    "CUA Comdty": ("BM", "TICKER", "FLAT", 1, 1),
    ".CUCH12US Index": ("BM", "COPY", "SPRD", 1, 0),
    ".CUCH23US Index": ("BM", "COPY", "SPRD", 1, 0),
    ".CUCH34US Index": ("BM", "COPY", "SPRD", 1, 0),
    "CU2 Comdty": ("BM", "CONTRACT", "FLAT", 0, 1),
    "CU3 Comdty": ("BM", "CONTRACT", "FLAT", 0, 1),
    "CU 1st Spread": ("BM", "CALCULATE", "SPRD", 1, 1),
    "CU 2nd Spread": ("BM", "CALCULATE", "SPRD", 1, 1),
    "CECN00CU Index": ("BM", "COPY", "SPRD", 1, 0),
    "LPARB": ("BM", "CUSTOM", "SPRD", 1, 0),
    "AAA Comdty": ("BM", "TICKER", "FLAT", 1, 1),
    ".CHAL12US Index": ("BM", "COPY", "SPRD", 1, 0),
    ".CHAL23US Index": ("BM", "COPY", "SPRD", 1, 0),
    ".CHAL34US Index": ("BM", "COPY", "SPRD", 1, 0),
    "AA2 Comdty": ("BM", "CONTRACT", "FLAT", 0, 1),
    "AA3 Comdty": ("BM", "CONTRACT", "FLAT", 0, 1),
    "AA 1st Spread": ("BM", "CALCULATE", "SPRD", 1, 1),
    "AA 2nd Spread": ("BM", "CALCULATE", "SPRD", 1, 1),
    "LAARB": ("BM", "CUSTOM", "SPRD", 1, 0),
    "XIIA Comdty": ("BM", "TICKER", "FLAT", 1, 1),
    ".CHNI12 Index": ("BM", "COPY", "SPRD", 1, 0),
    ".CHNI23 Index": ("BM", "COPY", "SPRD", 1, 0),
    ".CHNI34 Index": ("BM", "COPY", "SPRD", 1, 0),
    "XII2 Comdty": ("BM", "CONTRACT", "FLAT", 0, 1),
    "XII3 Comdty": ("BM", "CONTRACT", "FLAT", 0, 1),
    "XII 1st Spread": ("BM", "CALCULATE", "SPRD", 1, 1),
    "XII 2nd Spread": ("BM", "CALCULATE", "SPRD", 1, 1),
    "ZNAA Comdty": ("BM", "TICKER", "FLAT", 1, 1),
    ".CHZN12US Index": ("BM", "COPY", "SPRD", 1, 0),
    ".CHZN23US Index": ("BM", "COPY", "SPRD", 1, 0),
    ".CHZN34US Index": ("BM", "COPY", "SPRD", 1, 0),
    "ZNA2 Comdty": ("BM", "CONTRACT", "FLAT", 0, 1),
    "ZNA3 Comdty": ("BM", "CONTRACT", "FLAT", 0, 1),
    "ZNA 1st Spread": ("BM", "CALCULATE", "SPRD", 1, 1),
    "ZNA 2nd Spread": ("BM", "CALCULATE", "SPRD", 1, 1),
    "LXARB": ("BM", "CUSTOM", "SPRD", 1, 0),
    "LLARB": ("BM", "CUSTOM", "SPRD", 1, 0),
    "SXPP Index": ("BM", "COPY", "FLAT", 1, 0),
    "XME US Equity": ("BM", "COPY", "FLAT", 1, 1),
    "GLEN LN Equity": ("BM", "COPY", "FLAT", 1, 0),
    "AA US Equity": ("BM", "COPY", "FLAT", 1, 0),
    "NUE US Equity": ("BM", "COPY", "FLAT", 1, 0),
    "BHP LN Equity": ("BM", "COPY", "FLAT", 1, 0),
    "SH000909 Index": ("BM", "COPY", "FLAT", 1, 0),
    "COPX US Equity": ("BM", "COPY", "FLAT", 1, 0),
    "IOEA Comdty": ("Bulks", "TICKER", "FLAT", 1, 1),
    "RBTA Comdty": ("Bulks", "TICKER", "FLAT", 1, 1),
    "SCOA Comdty": ("Bulks", "TICKER", "FLAT", 1, 1),
    "C A Comdty": ("GR", "TICKER", "FLAT", 1, 1),
    "C 2 Comdty": ("GR", "CONTRACT", "FLAT", 1, 1),
    "C 3 Comdty": ("GR", "CONTRACT", "FLAT", 0, 1),
    "C DEC1 Comdty": ("GR", "FUT_CUR_GEN_TICKER", "FLAT", 0, 1),
    "C DEC2 Comdty": ("GR", "FUT_CUR_GEN_TICKER", "FLAT", 0, 1),
    "C  1st Spread": ("GR", "CALCULATE", "SPRD", 1, 1),
    "C  2nd Spread": ("GR", "CALCULATE", "SPRD", 1, 1),
    "C  Dec-Dec Spread": ("GR", "CALCULATE", "SPRD", 1, 1),
    "S A Comdty": ("GR", "TICKER", "FLAT", 1, 1),
    "S 2 Comdty": ("GR", "CONTRACT", "FLAT", 1, 1),
    "S 3 Comdty": ("GR", "CONTRACT", "FLAT", 0, 1),
    "S NOV1 Comdty": ("GR", "FUT_CUR_GEN_TICKER", "FLAT", 0, 1),
    "S NOV2 Comdty": ("GR", "FUT_CUR_GEN_TICKER", "FLAT", 0, 1),
    "S  1st Spread": ("GR", "CALCULATE", "SPRD", 1, 1),
    "S  2nd Spread": ("GR", "CALCULATE", "SPRD", 1, 1),
    "S  Nov-Nov Spread": ("GR", "CALCULATE", "SPRD", 1, 1),
    "W A Comdty": ("GR", "TICKER", "FLAT", 1, 1),
    "W 2 Comdty": ("GR", "CONTRACT", "FLAT", 1, 1),
    "W 3 Comdty": ("GR", "CONTRACT", "FLAT", 0, 1),
    "W DEC1 Comdty": ("GR", "FUT_CUR_GEN_TICKER", "FLAT", 0, 1),
    "W DEC2 Comdty": ("GR", "FUT_CUR_GEN_TICKER", "FLAT", 0, 1),
    "W  1st Spread": ("GR", "CALCULATE", "SPRD", 1, 1),
    "W  2nd Spread": ("GR", "CALCULATE", "SPRD", 1, 1),
    "W  Dec-Dec Spread": ("GR", "CALCULATE", "SPRD", 1, 1),
    "SMA Comdty": ("GR", "TICKER", "FLAT", 1, 1),
    "SM2 Comdty": ("GR", "CONTRACT", "FLAT", 0, 1),
    "SM 1st Spread": ("GR", "CALCULATE", "SPRD", 1, 1),
    "BOA Comdty": ("GR", "TICKER", "FLAT", 1, 1),
    "BO2 Comdty": ("GR", "CONTRACT", "FLAT", 0, 1),
    "BO 1st Spread": ("GR", "CALCULATE", "SPRD", 1, 1),
    ".SOYCORN Index": ("GR", "COPY", "SPRD", 1, 0),
    ".WCORN Index": ("GR", "COPY", "SPRD", 1, 0),
    ".SOYWHEAT Index": ("GR", "COPY", "SPRD", 1, 0),
    "KWA Comdty": ("GR", "TICKER", "FLAT", 1, 1),
    "CAA Comdty": ("GR", "TICKER", "FLAT", 1, 1),
    "AKA Comdty": ("GR", "TICKER", "FLAT", 1, 1),
    "AEA Comdty": ("GR", "TICKER", "FLAT", 1, 1),
    "ACA Comdty": ("GR", "TICKER", "FLAT", 1, 1),
    "SBA Comdty": ("SFT", "TICKER", "FLAT", 1, 1),
    "SB2 Comdty": ("SFT", "CONTRACT", "FLAT", 1, 1),
    "SB3 Comdty": ("SFT", "CONTRACT", "FLAT", 0, 1),
    "SB4 Comdty": ("SFT", "CONTRACT", "FLAT", 0, 1),
    "SB 1st Spread": ("SFT", "CALCULATE", "SPRD", 1, 1),
    "SB 2nd Spread": ("SFT", "CALCULATE", "SPRD", 1, 1),
    "QWA Comdty": ("SFT", "TICKER", "FLAT", 1, 1),
    "QW2 Comdty": ("SFT", "CONTRACT", "FLAT", 1, 1),
    "QW 1st Spread": ("SFT", "CALCULATE", "SPRD", 1, 1),
    ".QWOCT S 92051579 Index": ("SFT", "COPY", "SPRD", 1, 0),
    "CCA Comdty": ("SFT", "TICKER", "FLAT", 1, 1),
    "CC2 Comdty": ("SFT", "CONTRACT", "FLAT", 0, 1),
    "CC 1st Spread": ("SFT", "CALCULATE", "SPRD", 1, 1),
    "QCA Comdty": ("SFT", "TICKER", "FLAT", 1, 1),
    "QC2 Comdty": ("SFT", "CONTRACT", "FLAT", 0, 1),
    "QC 1st Spread": ("SFT", "CALCULATE", "SPRD", 1, 1),
    "KCA Comdty": ("SFT", "TICKER", "FLAT", 1, 1),
    "KC2 Comdty": ("SFT", "CONTRACT", "FLAT", 0, 1),
    "KC 1st Spread": ("SFT", "CALCULATE", "SPRD", 1, 1),
}

gas_name_dict = {
    "NGA Comdty": ("US_GAS", "TICKER", "FLAT", 1, 1, False),
    "NG2 Comdty": ("US_GAS", "CONTRACT", "FLAT", 1, 1, False),
    "NG3 Comdty": ("US_GAS", "CONTRACT", "FLAT", 1, 1, False),
    "NG4 Comdty": ("US_GAS", "CONTRACT", "FLAT", 1, 1, False),
    "NG5 Comdty": ("US_GAS", "CONTRACT", "FLAT", 0, 1, False),
    "NG6 Comdty": ("US_GAS", "CONTRACT", "FLAT", 0, 1, False),
    "S:NGNG 2-6 Comdty": ("US_GAS", "CALSPRD", "SPRD", 1, 1, False),
    "NG 1st Spread": ("US_GAS", "CALCULATE", "SPRD", 1, 1, False),
    "NG 2nd Spread": ("US_GAS", "CALCULATE", "SPRD", 1, 1, False),
    "NG 3rd Spread": ("US_GAS", "CALCULATE", "SPRD", 1, 1, False),
    "NGMAR1 Comdty": ("US_GAS", "FUT_CUR_GEN_TICKER", "FLAT", 0, 1, False),
    "NGOCT1 Comdty": ("US_GAS", "FUT_CUR_GEN_TICKER", "FLAT", 0, 1, False),
    "NG Mar-Apr Spread": ("US_GAS", "CALCULATE", "SPRD", 1, 1, False),
    "NG Oct-Jan Spread": ("US_GAS", "CALCULATE", "SPRD", 1, 1, False),
    "NGH4NGJ4 Comdty": ("US_GAS", "COPY", "SPRD", 1, 1, False),
    "NGV4NGF5 Comdty": ("US_GAS", "COPY", "SPRD", 0, 1, False),
    "NG 1M 100 VOL BVOL Comdty": ("US_GAS", "COPY", "SPRD", 1, 0, False),
    "NG 3M 100 VOL BVOL Comdty": ("US_GAS", "COPY", "SPRD", 1, 0, False),
    "NG 6M 100 VOL BVOL Comdty": ("US_GAS", "COPY", "SPRD", 1, 0, False),
    ".NG1M Index": ("US_GAS", "COPY", "SPRD", 1, 0, False),
    ".NG3M Index": ("US_GAS", "COPY", "SPRD", 0, 0, False),
    ".NG6M Index": ("US_GAS", "COPY", "SPRD", 0, 0, False),
    "TZTA Comdty": ("EU_GAS", "TICKER", "FLAT", 1, 1, False),
    "TZT2 Comdty": ("EU_GAS", "CONTRACT", "FLAT", 1, 1, False),
    "TZT3 Comdty": ("EU_GAS", "CONTRACT", "FLAT", 0, 1, False),
    "TZT 1st spread": ("EU_GAS", "CALCULATE", "SPRD", 1, 1, False),
    "TZT 2nd spread": ("EU_GAS", "CALCULATE", "SPRD", 1, 1, False),
    "TZTH4J4 Comdty": ("EU_GAS", "COPY", "SPRD", 1, 1, False),
    "QZTA Comdty": ("EU_GAS", "TICKER", "FLAT", 1, 1, False),
    "QZT2 Comdty": ("EU_GAS", "CONTRACT", "FLAT", 1, 1, False),
    "QZT3 Comdty": ("EU_GAS", "CONTRACT", "FLAT", 0, 1, False),
    "QZT 1st spread": ("EU_GAS", "CALCULATE", "SPRD", 1, 1, False),
    "QZT 2nd spread": ("EU_GAS", "CALCULATE", "SPRD", 1, 1, False),
    "QQTA Comdty": ("EU_GAS", "TICKER", "FLAT", 1, 1, False),
    "QQT2 Comdty": ("EU_GAS", "CONTRACT", "FLAT", 0, 1, False),
    "QQT3 Comdty": ("EU_GAS", "CONTRACT", "FLAT", 0, 1, False),
    "QQT 1st spread": ("EU_GAS", "CALCULATE", "SPRD", 1, 1, False),
    "QQT 2nd spread": ("EU_GAS", "CALCULATE", "SPRD", 1, 1, False),
    "QTTA Comdty": ("EU_GAS", "TICKER", "FLAT", 1, 1, False),
    "QTT2 Comdty": ("EU_GAS", "CONTRACT", "FLAT", 1, 1, False),
    "QTT3 Comdty": ("EU_GAS", "CONTRACT", "FLAT", 1, 1, False),
    "QTT4 Comdty": ("EU_GAS", "CONTRACT", "FLAT", 1, 1, False),
    "QTT 1st spread": ("EU_GAS", "CALCULATE", "SPRD", 1, 1, False),
    "FJS 1M 100 VOL BVOL Comdty": ("EU_GAS", "COPY", "SPRD", 1, 0, False),
    "FJS 3M 100 VOL BVOL Comdty": ("EU_GAS", "COPY", "SPRD", 1, 0, False),
    "FJS 6M 100 VOL BVOL Comdty": ("EU_GAS", "COPY", "SPRD", 1, 0, False),
    ".FJS1MRR Index": ("EU_GAS", "COPY", "SPRD", 1, 0, False),
    "GERW1WYY Comdty": ("EU_POWER", "WEEKLY", "FLAT", 1, 1, False),
    "GERW2WYY Comdty": ("EU_POWER", "WEEKLY", "FLAT", 1, 1, False),
    "DETA Comdty": ("EU_POWER", "TICKER", "FLAT", 1, 1, False),
    "DET2 Comdty": ("EU_POWER", "CONTRACT", "FLAT", 0, 1, False),
    "DET 1st spread": ("EU_POWER", "CALCULATE", "SPRD", 0, 1, False),
    "JXTA Comdty": ("EU_POWER", "TICKER", "FLAT", 1, 1, False),
    "JXT2 Comdty": ("EU_POWER", "CONTRACT", "FLAT", 0, 1, False),
    "JXT 1st spread": ("EU_POWER", "CALCULATE", "SPRD", 0, 1, False),
    "JXYA Comdty": ("EU_POWER", "TICKER", "FLAT", 1, 1, False),
    "JXY2 Comdty": ("EU_POWER", "CONTRACT", "FLAT", 1, 1, False),
    "JXY3 Comdty": ("EU_POWER", "CONTRACT", "FLAT", 1, 1, False),
    "JXY 1st spread": ("EU_POWER", "CALCULATE", "SPRD", 0, 1, False),
    "DET 1M 100 VOL BVOL Comdty": ("EU_POWER", "COPY", "SPRD", 1, 0, False),
    "DET 3M 100 VOL BVOL Comdty": ("EU_POWER", "COPY", "SPRD", 1, 0, False),
    "FACA Comdty": ("EU_POWER", "TICKER", "FLAT", 1, 1, False),
    "FABA Comdty": ("EU_POWER", "TICKER", "FLAT", 1, 1, False),
    "FAAA Comdty": ("EU_POWER", "TICKER", "FLAT", 1, 1, False),
    "FAA2 Comdty": ("EU_POWER", "TICKER", "FLAT", 1, 1, False),
    "FAA3 Comdty": ("EU_POWER", "TICKER", "FLAT", 1, 1, False),
    "FAC 1M 100 VOL BVOL Comdty": ("EU_POWER", "COPY", "SPRD", 1, 0, False),
    "FAC 3M 100 VOL BVOL Comdty": ("EU_POWER", "COPY", "SPRD", 1, 0, False),
    "ELGBY 22 OECM Index": ("EU_POWER", "ROLLYEAR", "FLAT", 1, 0, False),
    "FSNGY 23 Index": ("US_GAS", "ROLLYEAR", "FLAT", 1, 0, False),
    "FSNGY 24 Index": ("US_GAS", "ROLLYEAR+1", "FLAT", 1, 0, False),
    "FSNGY 25 Index": ("US_GAS", "ROLLYEAR+2", "FLAT", 1, 0, False),
    "FSNGY 26 Index": ("US_GAS", "ROLLYEAR+3", "FLAT", 1, 0, False),
    "FSNGS SU23 Index": ("US_GAS", "ROLLYEAR", "FLAT", 1, 0, False),
    "FSNGS SU24 Index": ("US_GAS", "ROLLYEAR+1", "FLAT", 1, 0, False),
    "FSNGS SU25 Index": ("US_GAS", "ROLLYEAR+2", "FLAT", 1, 0, False),
    "FSNGS WI2223 Index": ("US_GAS", "ROLLYEAR", "FLAT", 1, 0, False),
    "FSNGS WI2324 Index": ("US_GAS", "ROLLYEAR+1", "FLAT", 1, 0, False),
    "FSNGS WI2425 Index": ("US_GAS", "ROLLYEAR+2", "FLAT", 1, 0, False),
    "MOA Comdty": ("EU_POWER", "TICKER", "FLAT", 1, 1, False),
    "CTIA Comdty": ("US_GAS", "TICKER", "FLAT", 1, 1, False),
    "XAA Comdty": ("COAL", "TICKER", "FLAT", 1, 1, False),
    "XEA Comdty": ("COAL", "TICKER", "FLAT", 1, 1, False),
    "TMA Comdty": ("COAL", "TICKER", "FLAT", 1, 1, False),
    "XNG Index": ("NG_STOCKS", "COPY", "FLAT", 1, 0, False),
    "EQNR NO Equity": ("NG_STOCKS", "COPY", "FLAT", 1, 1, False),
    "GAZP RM Equity": ("NG_STOCKS", "COPY", "FLAT", 1, 1, False),
    "LNG US Equity": ("NG_STOCKS", "COPY", "FLAT", 1, 1, False),
    ".DRY_E&P Index": ("NG_STOCKS", "COPY", "FLAT", 1, 1, False),
    "FNA Comdty": ("EU_GAS", "TICKER", "FLAT", 1, 1, True),
    "FN2 Comdty": ("EU_GAS", "CONTRACT", "FLAT", 1, 1, True),
    "FN3 Comdty": ("EU_GAS", "CONTRACT", "FLAT", 0, 1, True),
    "FN 1st spread": ("EU_GAS", "CALCULATE", "SPRD", 1, 1, True),
    "FN 2nd spread": ("EU_GAS", "CALCULATE", "SPRD", 1, 1, True),
    "FNMAR1 Comdty": ("EU_GAS", "FUT_CUR_GEN_TICKER", "FLAT", 1, 1, True),
    "FN Mar-Apr Spread": ("EU_GAS", "CALCULATE", "SPRD", 1, 1, True),
    "QRA Comdty": ("EU_GAS", "TICKER", "FLAT", 1, 1, True),
    "QR2 Comdty": ("EU_GAS", "CONTRACT", "FLAT", 1, 1, True),
    "QR3 Comdty": ("EU_GAS", "CONTRACT", "FLAT", 0, 1, True),
    "QR 1st spread": ("EU_GAS", "CALCULATE", "SPRD", 1, 1, True),
    "QR 2nd spread": ("EU_GAS", "CALCULATE", "SPRD", 1, 1, True),
    "SAA Comdty": ("EU_GAS", "TICKER", "FLAT", 1, 1, True),
    "SA2 Comdty": ("EU_GAS", "CONTRACT", "FLAT", 0, 1, True),
    "SA 1st spread": ("EU_GAS", "CALCULATE", "SPRD", 1, 1, True),
    "EEDATTF1 Index": ("EU_GAS", "COPY", "FLAT", 1, 1, True),
    "NBPGDAHD Index": ("EU_GAS", "COPY", "FLAT", 1, 1, True),
    "EGTHDAHD Index": ("EU_GAS", "COPY", "FLAT", 1, 1, True),
    "NCG1M Comdty": ("EU_GAS", "TICKER", "FLAT", 1, 1, True),
    "NCG1Q Comdty": ("EU_GAS", "TICKER", "FLAT", 1, 1, True),
    "NCG1S Comdty": ("EU_GAS", "TICKER", "FLAT", 1, 1, True),
    "NCG2S Comdty": ("EU_GAS", "TICKER", "FLAT", 1, 1, True),
    "NCG1Y Comdty": ("EU_GAS", "TICKER", "FLAT", 1, 1, True),
    "NCG2Y Comdty": ("EU_GAS", "TICKER", "FLAT", 1, 1, True),
    "COA Comdty": ("OIL", "TICKER", "FLAT", 1, 1, False),
    "CODEC1 Comdty": ("OIL", "FUT_CUR_GEN_TICKER", "FLAT", 1, 1, False),
    "CODEC2 Comdty": ("OIL", "FUT_CUR_GEN_TICKER", "FLAT", 1, 1, False),
    "CLA Comdty": ("OIL", "TICKER", "FLAT", 1, 1, False),
    "CLDEC1 Comdty": ("OIL", "FUT_CUR_GEN_TICKER", "FLAT", 1, 1, False),
    "CLDEC2 Comdty": ("OIL", "FUT_CUR_GEN_TICKER", "FLAT", 1, 1, False),
}
month_ticker_dict = {
    "JAN": "F",
    "FEB": "G",
    "MAR": "H",
    "APR": "J",
    "MAY": "K",
    "JUN": "M",
    "JUL": "N",
    "AUG": "Q",
    "SEP": "U",
    "OCT": "V",
    "NOV": "X",
    "DEC": "Z",
}
month_ticker_dict1 = {
    1: "F",
    2: "G",
    3: "H",
    4: "J",
    5: "K",
    6: "M",
    7: "N",
    8: "Q",
    9: "U",
    10: "V",
    11: "X",
    12: "Z",
}


def convert_ticker(ticker):
    if ticker[:2] == "GK":
        ticker_ = f"NG{ticker[2:]}"
    else:
        ticker_ = ticker
    m = re.search(r"[\d].$", ticker_.partition(" ")[0])
    if m is None:
        return f"{ticker_.partition(' ')[0][:-1]}2{ticker_.partition(' ')[0][-1]}" f" {ticker_.partition(' ')[-1]}"
    else:
        return ticker_


def ticker_split(ticker="NGV21 Comdty"):
    """
    Return ticker for instrument, month symbol, year, and asset class
    """
    ticker_parts = ticker.split(" ")
    if len(ticker_parts) > 2:
        instrument = ticker_parts[0] + " "
        month_symbol = ticker_parts[1][0]
        year = ticker_parts[1][1:]
        asset_class = ticker_parts[-1]
    else:
        i = -1
        tick = ticker.rpartition(" ")[0]
        while abs(i) < len(tick):
            if not tick[i].isdigit():
                month_symbol = tick[i]
                year = tick[i + 1 :]  # noqa: E203
                instrument = tick[:i]
                break
            else:
                i -= 1
        asset_class = ticker_parts[-1]
    return instrument, month_symbol, year, asset_class


def ticker_split_gen(ticker="C 2 Comdty"):
    """
    Return ticker for instrument, number of contract, and asset class
    """
    ticker_parts = ticker.split(" ")
    if len(ticker_parts) > 2:
        instrument = ticker_parts[0] + " "
        num_contract = ticker_parts[1]
        asset_class = ticker_parts[-1]
    else:
        if ticker_parts[0][-1] == "A":
            instrument = ticker_parts[:-1]
            num_contract = "A"
        else:
            i = -1
            tick = ticker.rpartition(" ")[0]
            while abs(i) < len(tick):
                if not tick[i].isdigit():
                    instrument = tick[: i + 1]
                    num_contract = tick[i + 1 :]  # noqa: E203
                    break
                else:
                    i -= 1
        asset_class = ticker_parts[-1]
    return instrument, num_contract, asset_class


def get_bbg_ticker(name, ticker_type, **kwargs):
    log.debug(f"Getting Ticker {name}")
    cur_ticker = kwargs.get("cur_ticker", None)
    next = kwargs.get("next", None)
    name1 = kwargs.get("name1", None)
    name2 = kwargs.get("name2", None)

    if ticker_type in ["TICKER", "FUT_CUR_GEN_TICKER"]:
        try:
            ticker = bbg.bref(name, [ticker_type])
        except Exception:
            ticker = None
        if ticker is not None and isinstance(ticker.columns, pd.MultiIndex):
            ticker.columns = [x[0] for x in ticker.columns]
        if ticker is not None:
            if name.split(" ")[-2] == "US":
                ticker = ticker[ticker_type][0] + " US Equity"
            else:
                ticker = ticker[ticker_type][0] + " " + name.split(" ")[-1]
                if name == "CTIA Comdty":
                    ticker = f"{ticker[:3]}Z{ticker[-9:]}"
    elif ticker_type == "COPY":
        ticker = name
    elif ticker_type == "CONTRACT":
        month_symbol_list = bbg.bref(cur_ticker, ["FUT_GEN_MONTH"])
        if isinstance(month_symbol_list.columns, pd.MultiIndex):
            month_symbol_list = month_symbol_list.values[0][1]
        else:
            month_symbol_list = month_symbol_list.values[0][0]
        month_symbol_list = [x for x in month_symbol_list]
        instrument, month_symbol, yr, asset_class = ticker_split(cur_ticker)
        next_ticker_loc = month_symbol_list.index(month_symbol) + next - 1
        if next_ticker_loc > len(month_symbol_list) - 1:
            next_ticker_symbol = month_symbol_list[next_ticker_loc % len(month_symbol_list)]
            yr = str(int(yr) + math.floor(next_ticker_loc / len(month_symbol_list)))
        else:
            next_ticker_symbol = month_symbol_list[next_ticker_loc]
        ticker = name.rpartition(" ")[0][:-1] + next_ticker_symbol + yr + " " + name.rpartition(" ")[-1]

    elif ticker_type == "CALCULATE":
        instrument, month_symbol, yr, asset_class = ticker_split(name1)
        if instrument[-1] == " ":
            if len(yr) == 1:
                ticker = name1.split(" ")[0] + "_" + name1.split(" ")[1] + name2.split(" ")[0] + "_" + name2.split(" ")[1] + " " + name1.split(" ")[-1]
            elif len(yr) == 2:
                ticker = (
                    name1.split(" ")[0]
                    + "_"
                    + name1.split(" ")[1][0]
                    + name1.split(" ")[1][-1]
                    + name2.split(" ")[0]
                    + "_"
                    + name2.split(" ")[1][0]
                    + name2.split(" ")[1][-1]
                    + " "
                    + name1.split(" ")[-1]
                )
        elif len(instrument) > 2:
            if len(yr) == 1:
                ticker = name1.split(" ")[0] + name2.split(" ")[0][-2:] + " " + name2.split(" ")[1]
            elif len(yr) == 2:
                ticker = name1.split(" ")[0][:-2] + name1.split(" ")[0][-1] + name2.split(" ")[0][-3] + name2.split(" ")[0][-1] + " " + name2.split(" ")[1]
        else:
            if len(yr) == 1:
                ticker = name1.split(" ")[0] + name2.split(" ")[0] + " " + name2.split(" ")[1]
            elif len(yr) == 2:
                ticker = name1.split(" ")[0][:-2] + name1.split(" ")[0][-1] + name2.split(" ")[0][:-2] + name2.split(" ")[0][-1] + " " + name2.split(" ")[1]

    elif ticker_type[:8] == "ROLLYEAR":
        if "+" in ticker_type:
            year_str = str(dt.datetime.now().year + 1 + int(ticker_type[-1]))[-2:]
            year_str0 = str(dt.datetime.now().year + int(ticker_type[-1]))[-2:]
        else:
            year_str = str(dt.datetime.now().year + 1)[-2:]
            year_str0 = str(dt.datetime.now().year)[-2:]
        ticker_parts = name.split(" ")
        if ticker_parts[1].isdecimal():
            if len(ticker_parts[1]) > 2:
                ticker_parts = [x if idx != 1 else year_str0 + year_str for idx, x in enumerate(ticker_parts)]
            else:
                ticker_parts = [x if idx != 1 else year_str for idx, x in enumerate(ticker_parts)]
        else:
            if len(ticker_parts[1]) > 4:
                ticker_parts = [x if idx != 1 else x[:2] + year_str0 + year_str for idx, x in enumerate(ticker_parts)]
            else:
                ticker_parts = [x if idx != 1 else x[:2] + year_str for idx, x in enumerate(ticker_parts)]
        ticker = " ".join(ticker_parts)

    elif ticker_type == "OILSPRD":
        ticker_list = name.split(" ")
        front_ticker = bbg.bref(ticker_list[0] + " " + ticker_list[-1], ["TICKER"])  # .iloc[0, 0]
        if isinstance(front_ticker.columns, pd.MultiIndex):
            front_ticker = front_ticker.iloc[0, 1]
        else:
            front_ticker = front_ticker.iloc[0, 0]
        next_ticker_loc = list(month_str2int.keys()).index(front_ticker[-2]) + int(ticker_list[1]) - 1
        if next_ticker_loc > len(list(month_str2int.keys())) - 1:
            next_ticker_symbol = list(month_str2int.keys())[next_ticker_loc % len(list(month_str2int.keys()))]
            yr = str(int(front_ticker[-1]) + math.floor(next_ticker_loc / len(list(month_str2int.keys()))))
        else:
            next_ticker_symbol = list(month_str2int.keys())[next_ticker_loc]
            yr = str(int(front_ticker[-1]))
        ticker = front_ticker[:-2] + next_ticker_symbol + yr + " Comdty"

    elif ticker_type == "CUSTOM":
        ticker = name

    elif ticker_type == "WEEKLY":
        add_week = int(name[4])
        week_num = "{0}{1:02}".format(*(today() + dt.timedelta(7 * add_week)).isocalendar())
        ticker = name[:3] + week_num[-2:] + name[5] + week_num[2:4] + " " + name.split(" ")[-1]

    return ticker


def _get_ticker_contract(key, val, ticker_dict):
    log.debug(f"Getting Ticker {key}")
    instrument, num_contract, asset_class = ticker_split_gen(key)
    try:
        ticker = get_bbg_ticker(
            key,
            val[1],
            cur_ticker=ticker_dict[instrument + "A " + asset_class][0],
            next=int(num_contract),
        )
    except Exception:
        ticker = None
    return ticker


def _get_ticker_co_spread(key, ticker_dict):
    log.debug(f"Getting Ticker {key}")
    if key.split(" ")[1].lower() == "1st":
        ticker = key.split(" ")[0] + " " + ticker_dict["COA Comdty"][0].split(" ")[0][-2] + "2" + ticker_dict["COA Comdty"][0].split(" ")[0][-1] + " Index"
    elif key.split(" ")[1].lower() == "2nd":
        ticker = key.split(" ")[0] + " " + ticker_dict["CO2 Comdty"][0].split(" ")[0][-2] + "2" + ticker_dict["CO2 Comdty"][0].split(" ")[0][-1] + " Index"
    elif key.split(" ")[1].lower() == "3rd":
        ticker = key.split(" ")[0] + " " + ticker_dict["CO3 Comdty"][0].split(" ")[0][-2] + "2" + ticker_dict["CO3 Comdty"][0].split(" ")[0][-1] + " Index"
    elif key.split(" ")[1].lower() == "6th":
        ticker = key.split(" ")[0] + " " + ticker_dict["CO6 Comdty"][0].split(" ")[0][-2] + "2" + ticker_dict["CO6 Comdty"][0].split(" ")[0][-1] + " Index"
    elif key.split(" ")[1].lower() == "12th":
        ticker = key.split(" ")[0] + " " + ticker_dict["CO12 Comdty"][0].split(" ")[0][-2] + "2" + ticker_dict["CO12 Comdty"][0].split(" ")[0][-1] + " Index"
    return ticker


def _get_cal_spread(key, ticker_dict):
    log.debug(f"Getting Ticker {key}")
    partial_ticker2 = key.split(" ")[0][2:]
    partial_ticker = partial_ticker2[: int(len(partial_ticker2) / 2)]
    cal_sprd1 = key.split(" ")[1][0]
    cal_sprd2 = key.split(" ")[1][-1]
    name1 = ticker_dict[partial_ticker + cal_sprd1 + " Comdty"][0]
    name2 = ticker_dict[partial_ticker + cal_sprd2 + " Comdty"][0]
    if partial_ticker == "NG":
        ticker = name1.split(" ")[0][:3] + name1.split(" ")[0][-1] + name2.split(" ")[0][:3] + name2.split(" ")[0][-1] + " Comdty"
    else:
        ticker = name1.split(" ")[0] + name2.split(" ")[0] + " Comdty"
    return ticker


def _get_lme_spread(key):
    log.debug(f"Getting Ticker {key}")
    parts = key.split(" ")
    current_month_roll_day = list(
        rrule(
            freq=MONTHLY,
            dtstart=dt.datetime(today().year, today().month, 1),
            count=1,
            byweekday=WE(+3),
        )
    )[0]
    current_month_roll_day = CDR("GB").bday_adj(date=current_month_roll_day, t=-2)
    if today() > current_month_roll_day:
        relative_day = today() + relativedelta(months=1)
    else:
        relative_day = today()
    if parts[1] == "1st":
        this_contract_day = relative_day
        this_month = this_contract_day.month
        this_year = this_contract_day.year
        next_contract_day = relative_day + relativedelta(months=1)
        next_month = next_contract_day.month
        next_year = next_contract_day.year
        ticker = f"{parts[0]} {month_ticker_dict1[this_month]}{str(this_year)[-2:]}" f"{month_ticker_dict1[next_month]}{str(next_year)[-2:]} Comdty"
    elif parts[1] == "2nd":
        this_contract_day = relative_day + relativedelta(months=1)
        this_month = this_contract_day.month
        this_year = this_contract_day.year
        next_contract_day = relative_day + relativedelta(months=2)
        next_month = next_contract_day.month
        next_year = next_contract_day.year
        ticker = f"{parts[0]} {month_ticker_dict1[this_month]}{str(this_year)[-2:]}" f"{month_ticker_dict1[next_month]}{str(next_year)[-2:]} Comdty"
    elif parts[1] == "3rd":
        this_contract_day = relative_day + relativedelta(months=2)
        this_month = this_contract_day.month
        this_year = this_contract_day.year
        next_contract_day = relative_day + relativedelta(months=3)
        next_month = next_contract_day.month
        next_year = next_contract_day.year
        ticker = f"{parts[0]} {month_ticker_dict1[this_month]}{str(this_year)[-2:]}" f"{month_ticker_dict1[next_month]}{str(next_year)[-2:]} Comdty"
    return ticker


def _get_ticker_calculate(key, val, ticker_dict):
    log.debug(f"Getting Ticker {key}")
    key_parts = key.split(" ")
    if key.split(" ")[1] == "":
        key_parts[:2] = [" ".join(key_parts[:2])]
    if key_parts[1].lower() == "1st":
        try:
            if len(key_parts[0]) == 4:
                name2 = ticker_dict[key_parts[0][-2:] + "A Comdty"][0]
                instrument, month_symbol, yr, asset_class = ticker_split(name2)
                name1 = key_parts[0][:2] + month_symbol + yr + " " + asset_class
            else:
                name1 = ticker_dict[key_parts[0] + "A Comdty"][0]
                name2 = ticker_dict[key_parts[0] + "2 Comdty"][0]
            ticker = get_bbg_ticker(key, val[1], name1=name1, name2=name2)
        except Exception:
            ticker = None
    elif key_parts[1].lower() == "2nd":
        try:
            if len(key_parts[0]) == 4:
                name2 = ticker_dict[key_parts[0][-2:] + "2 Comdty"][0]
                instrument, month_symbol, yr, asset_class = ticker_split(name2)
                name1 = key_parts[0][:2] + month_symbol + yr + " " + asset_class
            else:
                name1 = ticker_dict[key_parts[0] + "2 Comdty"][0]
                name2 = ticker_dict[key_parts[0] + "3 Comdty"][0]
            ticker = get_bbg_ticker(key, val[1], name1=name1, name2=name2)
        except Exception:
            ticker = None
    elif key_parts[1].lower() == "3rd":
        try:
            if len(key_parts[0]) == 4:
                name2 = ticker_dict[key_parts[0][-2:] + "3 Comdty"][0]
                instrument, month_symbol, yr, asset_class = ticker_split(name2)
                name1 = key_parts[0][:2] + month_symbol + yr + " " + asset_class
            else:
                name1 = ticker_dict[key_parts[0] + "3 Comdty"][0]
                name2 = ticker_dict[key_parts[0] + "4 Comdty"][0]
            ticker = get_bbg_ticker(key, val[1], name1=name1, name2=name2)
        except Exception:
            ticker = None
    elif key_parts[1].lower() == "4th":
        if len(key_parts[0]) == 4:
            name2 = ticker_dict[key_parts[0][-2:] + "4 Comdty"][0]
            instrument, month_symbol, yr, asset_class = ticker_split(name2)
            name1 = key_parts[0][:2] + month_symbol + yr + " " + asset_class
        else:
            name1 = ticker_dict[key_parts[0] + "4 Comdty"][0]
            name2 = ticker_dict[key_parts[0] + "5 Comdty"][0]
        ticker = get_bbg_ticker(key, val[1], name1=name1, name2=name2)
    elif key_parts[1].lower() == "5th":
        if len(key_parts[0]) == 4:
            name2 = ticker_dict[key_parts[0][-2:] + "5 Comdty"][0]
            instrument, month_symbol, yr, asset_class = ticker_split(name2)
            name1 = key_parts[0][:2] + month_symbol + yr + " " + asset_class
        else:
            name1 = ticker_dict[key_parts[0] + "5 Comdty"][0]
            name2 = ticker_dict[key_parts[0] + "6 Comdty"][0]
        ticker = get_bbg_ticker(key, val[1], name1=name1, name2=name2)
    elif key_parts[1].lower() == "dec-dec":
        if len(key_parts[0]) == 4:
            name2 = ticker_dict[key_parts[0][-2:] + "DEC1 Comdty"][0]
            instrument, month_symbol, yr, asset_class = ticker_split(name2)
            name1 = key_parts[0][:2] + month_symbol + yr + " " + asset_class
        else:
            name1 = ticker_dict[key_parts[0] + "DEC1 Comdty"][0]
            name2 = ticker_dict[key_parts[0] + "DEC2 Comdty"][0]
        ticker = get_bbg_ticker(key, val[1], name1=name1, name2=name2)
    elif key_parts[1].lower() == "dec2-dec3":
        ticker = get_bbg_ticker(
            key,
            val[1],
            name1=ticker_dict[key_parts[0] + "DEC2 Comdty"][0],
            name2=ticker_dict[key_parts[0] + "DEC3 Comdty"][0],
        )
    elif key_parts[1].lower() == "nov-nov":
        ticker = get_bbg_ticker(
            key,
            val[1],
            name1=ticker_dict[key_parts[0] + "NOV1 Comdty"][0],
            name2=ticker_dict[key_parts[0] + "NOV2 Comdty"][0],
        )
    elif key_parts[1].lower() == "oct-jan":
        name1 = ticker_dict[key_parts[0] + "OCT1 Comdty"][0]
        instrument, month_symbol, yr, asset_class = ticker_split(name1)
        name2 = instrument + "F" + str(int(yr) + 1) + " " + asset_class
        ticker = get_bbg_ticker(key, val[1], name1=name1, name2=name2)
    elif key_parts[1].lower() == "mar-apr":
        name1 = ticker_dict[key_parts[0] + "MAR1 Comdty"][0]
        instrument, month_symbol, yr, asset_class = ticker_split(name1)
        name2 = instrument + "J" + str(int(yr)) + " " + asset_class
        ticker = get_bbg_ticker(key, val[1], name1=name1, name2=name2)
    elif key_parts[1].lower() == "jun-dec":
        name_jun = ticker_dict[key_parts[0] + "JUN1 Comdty"][0]
        name_dec = ticker_dict[key_parts[0] + "DEC1 Comdty"][0]
        lst_trd_jun = bbg.bref(name_jun, ["LAST_TRADEABLE_DT"])
        lst_trd_dec = bbg.bref(name_dec, ["LAST_TRADEABLE_DT"])
        if isinstance(lst_trd_jun.columns, pd.MultiIndex):
            lst_trd_jun = pd.to_datetime(lst_trd_jun.values[0][1])
            lst_trd_dec = pd.to_datetime(lst_trd_dec.values[0][1])
        else:
            lst_trd_jun = lst_trd_jun.values[0][0]
            lst_trd_dec = lst_trd_dec.values[0][0]
        if lst_trd_jun < lst_trd_dec:
            ticker = get_bbg_ticker(key, val[1], name1=name_jun, name2=name_dec)
        else:
            ticker = get_bbg_ticker(key, val[1], name1=name_dec, name2=name_jun)
    elif key_parts[1].lower() == "quarter":
        quarter_dict = {3: "H", 6: "M", 9: "U", 12: "Z"}
        cur_month_symbol = quarter_dict[[x for x in list(quarter_dict.keys()) if x >= dt.datetime.now().month][0]]
        if key_parts[0] == "NG":
            cur_yr = str(dt.datetime.now().year)[-2:]
        else:
            cur_yr = str(dt.datetime.now().year)[-1]
        if cur_month_symbol == "Z":
            next_month_symbol = "H"
            next_month_symbol1 = "M"
            if key_parts[0] == "NG":
                next_yr = next_yr1 = str(dt.datetime.now().year + 1)[-2:]
            else:
                next_yr = next_yr1 = str(dt.datetime.now().year + 1)[-1]
        else:
            next_month_symbol = quarter_dict[[x for x in list(quarter_dict.keys()) if x >= dt.datetime.now().month][1]]
            if key_parts[0] == "NG":
                next_yr = str(dt.datetime.now().year)[-2:]
            else:
                next_yr = str(dt.datetime.now().year)[-1]
            if next_month_symbol == "Z":
                next_month_symbol1 = "H"
                if key_parts[0] == "NG":
                    next_yr1 = str(dt.datetime.now().year + 1)[-2:]
                else:
                    next_yr1 = str(dt.datetime.now().year + 1)[-1]
            else:
                next_month_symbol1 = quarter_dict[[x for x in list(quarter_dict.keys()) if x >= dt.datetime.now().month][2]]
                if key_parts[0] == "NG":
                    next_yr1 = str(dt.datetime.now().year)[-2:]
                else:
                    next_yr1 = str(dt.datetime.now().year)[-1]

        first_quarter_ticker = key_parts[0] + cur_month_symbol + cur_yr + " Comdty"
        second_quarter_ticker = key_parts[0] + next_month_symbol + next_yr + " Comdty"
        third_quarter_ticker = key_parts[0] + next_month_symbol1 + next_yr1 + " Comdty"
        lst_trd_fq1t = bbg.bref(first_quarter_ticker, ["LAST_TRADEABLE_DT"])
        if isinstance(lst_trd_fq1t.columns, pd.MultiIndex):
            lst_trd_fq1t = lst_trd_fq1t.values[0][1]
        else:
            lst_trd_fq1t = lst_trd_fq1t.values[0][0]
        if dt.datetime.now().date() >= pd.to_datetime(lst_trd_fq1t).date():
            name1 = second_quarter_ticker
            name2 = third_quarter_ticker
        else:
            name1 = first_quarter_ticker
            name2 = second_quarter_ticker
        ticker = get_bbg_ticker(key, val[1], name1=name1, name2=name2)
    else:
        raise ValueError("No more spreads!")
    return ticker


def load_name_dict(name_dict: dict = None, env="prod", update: bool = False, gas_mode: bool = False):
    rows = []
    if name_dict is None:
        name_dict = default_name_dict if not gas_mode else gas_name_dict
    for k, v in name_dict.items():
        if len(v) == 6:
            asset_class, category, change_type, enabled, volume, use_bbg = v  # type: ignore
        elif len(v) == 5:
            asset_class, category, change_type, enabled, volume = v  # type: ignore
            use_bbg = True
        else:
            raise ValueError("Expected a config of 5 items for general cross comds and 6 for gas")
        uuid = _gen_uuid(k, asset_class, category, change_type)
        formatted_dict = dict(
            uid=uuid,
            generic_ticker=k,
            asset_class=asset_class,
            category=category,
            change_type=change_type,
            volume=volume,
            enabled=enabled,
            use_bbg=use_bbg,
        )
        rows.append(formatted_dict)
    df = pd.DataFrame(rows)
    df = df.set_index(["uid", "generic_ticker", "asset_class", "category", "change_type"])
    ret_frame = MarketScanTickerConfig(df)
    return ret_frame


_gas_categories = ["US_GAS", "EU_GAS", "EU_POWER", "COAL", "NG_STOCKS", "OIL"]


def get_latest_config(ticker_config=None, env="prod", update: bool = False, gas_mode=False) -> dict:
    schema = MarketScanTickerConfig
    if not ticker_config:
        data = schema.load_sql(L025DB(env), form="db")
        if data.empty:
            data = load_name_dict(gas_mode)
        index_cols = data.index.names
        data = data.reset_index()
        if gas_mode:
            raw_data = data[data.asset_class.isin(_gas_categories)]
        else:
            data = data.drop(columns=["use_bbg"])
            raw_data = data[~data.asset_class.isin(_gas_categories)]
        raw_data = raw_data.set_index(index_cols)
        raw_dict = raw_data.reset_index().set_index(["asset_class", "generic_ticker"]).to_dict(orient="index")
        formated_dict = {}
        for k, v in raw_dict.items():
            x = list(v.values())
            x.insert(2, k[1])
            formated_dict[k] = tuple(x)
        return formated_dict
    else:
        data = load_name_dict(ticker_config, env=env, update=update)
        log.info("Updating the config db")
        data.dump_sql(db=L025DB(env), form="db", mode="update_only")
        data = schema.load_sql(L025DB(env), form="db")
        index_cols = data.index.names
        data = data.reset_index()
        if gas_mode:
            raw_data = data[data.asset_class.isin(_gas_categories)]
        else:
            data = data.drop(columns=["use_bbg"])
            raw_data = data[~data.asset_class.isin(_gas_categories)]
        raw_data = raw_data.set_index(index_cols)
        raw_dict = raw_data.reset_index().set_index(["asset_class", "generic_ticker"]).to_dict(orient="index")
        formated_dict = {}
        for k, v in raw_dict.items():
            x = list(v.values())
            x.insert(2, k[1])
            formated_dict[k] = tuple(x)
        return formated_dict


def get_latest_watchlist(env="prod") -> pd.DataFrame:
    schema = MarketScanWatchlistLive
    data = schema.load_sql(L025DB(env), form="db")
    if not data.empty:
        data = data.drop_duplicates()
        data = data.reset_index().set_index("uid")
    return data


def update_latest_watchlist(df, env="prod", is_update=True) -> pd.DataFrame:
    schema = MarketScanWatchlistLive
    to_update = schema(df)
    if is_update:
        to_update.dump_sql(L025DB(env), form="db", mode="update_only")
    else:
        to_update.dump_sql(L025DB(env), form="db", mode="insert_first")


def get_ticker_dict(ticker_config=None, force_update=False, env="prod", gas_mode: bool = False) -> dict:
    latest_config = get_latest_config(ticker_config, env=env, update=force_update, gas_mode=gas_mode)
    latest_watchlist = get_latest_watchlist(env=env)
    if gas_mode:
        latest_watchlist = latest_watchlist[latest_watchlist.asset_class.isin(_gas_categories)]
    else:
        latest_watchlist = latest_watchlist[~latest_watchlist.asset_class.isin(_gas_categories)]
    ticker_dict: tp.Dict[tp.Tuple, tp.Tuple] = {}
    ticker_dict_rec: tp.Dict[tp.Tuple, tp.Tuple] = {}
    log.info("Loading Tickers")
    watchlist_rows = []
    run_update = True
    for (asset_class, key), vals in latest_config.items():
        if not gas_mode:
            use_bbg = True
            uid = vals[1]
            category = vals[3]
            change_type = vals[4]
            volume = vals[5]
            enabled = vals[6]
        else:
            uid = vals[1]
            category = vals[3]
            change_type = vals[4]
            volume = vals[5]
            enabled = vals[6]
            use_bbg = vals[7]
        if not latest_watchlist.empty:
            index_cols = latest_watchlist.index.names
            latest_watchlist = latest_watchlist.reset_index()
            if gas_mode:
                latest_watchlist = latest_watchlist[latest_watchlist.asset_class.isin(_gas_categories)]
            else:
                latest_watchlist = latest_watchlist[~latest_watchlist.asset_class.isin(_gas_categories)]
            latest_watchlist = latest_watchlist.set_index(index_cols)
            try:
                db_vals = latest_watchlist.loc[uid]
            except KeyError as ke:
                log.error(f"{ke} missing for {key}")
                db_vals = pd.Series()
                run_update = True
            if not db_vals.empty:
                val = (
                    db_vals.asset_class,
                    db_vals.category,
                    db_vals.change_type,
                    db_vals.enabled,
                    db_vals.volume,
                    use_bbg,
                )
                ticker = db_vals.ticker
                try:
                    last_update = pd.to_datetime(db_vals.update_time.unique()[0]).date()
                except Exception:
                    last_update = pd.to_datetime(db_vals.update_time).date()
                if force_update or last_update < now_ldn().date():
                    run_update = True
                else:
                    run_update = False
            else:
                val = (asset_class, category, change_type, enabled, volume, use_bbg)  # type: ignore
        else:
            val = (asset_class, category, change_type, enabled, volume, use_bbg)  # type: ignore
        if run_update:
            if category in [
                "TICKER",
                "FUT_CUR_GEN_TICKER",
                "COPY",
                "ROLLYEAR",
                "ROLLYEAR+1",
                "ROLLYEAR+2",
                "ROLLYEAR+3",
                "ROLLYEAR+4",
                "OILSPRD",
                "CUSTOM",
                "WEEKLY",
            ]:
                ticker = get_bbg_ticker(key, category)
            elif category == "CONTRACT":
                if gas_mode:
                    instrument, num_contract, _asset_class = ticker_split_gen(key)
                    ticker = get_bbg_ticker(
                        key,
                        category,
                        cur_ticker=ticker_dict_rec[instrument + "A " + _asset_class][0],
                        next=int(num_contract),
                    )
                else:
                    ticker = _get_ticker_contract(key, val, ticker_dict_rec)
            elif category == "COSPREAD":
                ticker = _get_ticker_co_spread(key, ticker_dict_rec)
            elif category == "CALSPRD":
                ticker = _get_cal_spread(key, ticker_dict_rec)
            elif category == "LMESPREAD":
                ticker = _get_lme_spread(key)
            elif category == "CALCULATE":
                ticker = _get_ticker_calculate(key, val, ticker_dict_rec)
            else:
                raise NotImplementedError(f"{category} is not implemented")
            if ticker is not None:
                formatted_dict = dict(
                    uid=uid,
                    generic_ticker=key,
                    asset_class=asset_class,
                    category=category,
                    change_type=change_type,
                    ticker=ticker,
                    volume=volume,
                    enabled=enabled,
                    update_time=now_ldn(),
                )
                watchlist_rows.append(formatted_dict)
            else:
                log.error(f"Ticker not found for {key}")
        if gas_mode:
            ticker_dict[(asset_class, key)] = (ticker, asset_class, change_type, enabled, volume, use_bbg)
            ticker_dict_rec[key] = (ticker, val[0], val[2], val[3], val[4], val[5])  # type: ignore

        else:
            ticker_dict[(asset_class, key)] = (ticker, asset_class, change_type, enabled, volume)  # type: ignore
            ticker_dict_rec[key] = (ticker, val[0], val[2], val[3], val[4])

    if len(watchlist_rows) > 0:
        pk_cols = [
            "uid",
            "generic_ticker",
            "asset_class",
            "category",
            "change_type",
        ]
        watchlist_df = pd.DataFrame(watchlist_rows).set_index(pk_cols)
        new_df = MarketScanWatchlistLive(watchlist_df)
        update_time = new_df.data["update_time"].max()
        new_df = new_df.drop(columns=["update_time"])
        existing_watchlist = MarketScanWatchlistLive(latest_watchlist)
        existing_watchlist = existing_watchlist.drop(columns=["update_time"])
        upsert_df = get_rows_to_upsert(new_df, existing_watchlist, key_cols=pk_cols)
        if not upsert_df.empty:
            upsert_df["update_time"] = update_time
            update_df = upsert_df[upsert_df.update_type == "updated"]
            insert_df = upsert_df[upsert_df.update_type == "new"]
            if not update_df.empty:
                log.info(f"Updating {len(update_df)} rows")
                update_df_to_insert = update_df.drop(columns="update_type")
                update_latest_watchlist(update_df_to_insert, env=env, is_update=True)
            if not insert_df.empty:
                log.info(f"Inserting {len(insert_df)} rows")
                insert_df_to_insert = insert_df.drop(columns="update_type")
                update_latest_watchlist(insert_df_to_insert, env=env, is_update=False)
            log.info("Watchlist updated")
        else:
            log.info("No updates to watchlist")
    return ticker_dict


def save_sharpe_ratio(gen_ticker, s_3d, s_3d_cob, s_22d, date, env: str = "dev"):
    df = (
        pd.Series(
            dict(
                generic_ticker=gen_ticker,
                sharpe_3d_live=s_3d,
                sharpe_3d_cob=s_3d_cob,
                sharpe_22d=s_22d,
                date=date,
            )
        )
        .to_frame()
        .T.set_index(["generic_ticker", "date"])
    )
    schema = SharpeRatio
    schema_df = schema(df)
    schema_df.dump_sql(L025DB(env), form="db", mode="update_first")


def get_sharpe_ratio_history(gen_ticker, env: str = "dev"):
    schema = SharpeRatio
    data = schema.load_sql(L025DB(env), form="db", transform=[f"generic_ticker = '{gen_ticker}'"])
    data = data.reset_index().set_index("date")
    return data


if __name__ == "__main__":
    ticker_dict = get_ticker_dict(env="prod", gas_mode=False)
    print("break")
