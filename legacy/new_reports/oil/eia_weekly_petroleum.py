import pandas as pd
import datetime as dt
from functools import partial
import ecm.cmds.bbg as bbg
import ecm.cmds.pyg as pyg
import ecm.cmds.data as dv
from pyg_mongo import *
from pyg_cell import *
from ecm.cmds.config import url

ticker_dict = {
    "crude ex spr": ["DOESCRUD Index", "petroleum.stoc.wstk.WCESTUS1"],
    "cushing": ["DOESCROK Index", "petroleum.sum.sndw.W_EPC0_SAX_YCUOK_MBBL"],
    "crude p2": ["DOESCRU2 Index", "petroleum.sum.sndw.WCESTP21"],
    "crude+spr": ["DOESTCRD Index", "petroleum.sum.sndw.WCRSTUS1"],
    "crude change": ["DOEASCRD Index", "PX_LAST"],
    "crude whisper": ["WHISCRUD Index", "PX_LAST"],
    "doe schedule": ["DOEASCRD Index", "ECO_FUTURE_RELEASE_DATE_LIST"],
    "product supply": ["DOEDTPRD Index", "petroleum.sum.sndw.WRPUPUS2"],
    "product ex spr": ["DOESESPR Index", "petroleum.sum.sndw.WTESTUS1"],
    "product supply 4w average": ["DOEDTPS4 Index", "petroleum.sum.sndw.WRPUPUS2", "four-week-average"],
    "crude refinery runs": ["DOEPCRIN Index", "petroleum.sum.sndw.WCRRIUS2"],
    "distillate inventory": ["DOESDIST Index", "petroleum.sum.sndw.WDISTUS1"],
    "mogas inventory": ["DOESIMGS Index", "petroleum.sum.sndw.WGTSTUS1"],
    "crude production": ["DOETCRUD Index", "petroleum.sum.sndw.WCRFPUS2"],
    "crude imports": ["DOEICISP Index", "petroleum.move.wkly.WCRIMUS2"],
    "crude exports": ["DOEBCEXP Index", "petroleum.move.wkly.WCREXUS2"],
    "crude imports from Canada": ["DEPWIMCA Index", "petroleum.move.wimpc.W_EPC0_IM0_NUS-NCA_MBBLD"],
    "crude imports from Saudi": ["DEPWIMSA Index", "petroleum.move.wimpc.W_EPC0_IM0_NUS-NSA_MBBLD"],
    "crude imports from Mexico": ["DEPWIMMX Index", "petroleum.move.wimpc.W_EPC0_IM0_NUS-NMX_MBBLD"],
    "crude imports from Iraq": ["DEPWIMIQ Index", "petroleum.move.wimpc.W_EPC0_IM0_NUS-NIZ_MBBLD"],
    "crude imports from Colombia": ["DEPWIMCO Index", "petroleum.move.wimpc.W_EPC0_IM0_NUS-NCO_MBBLD"],
    "crude imports from Brazil": ["DEPWIMBR Index", "petroleum.move.wimpc.W_EPC0_IM0_NUS-NBR_MBBLD"],
    "crude imports from Nigeria": ["DEPWIMNG Index", "petroleum.move.wimpc.W_EPC0_IM0_NUS-NNI_MBBLD"],
    "crude p3 inventory": ["DOESCRU3 Index", "petroleum.sum.sndw.WCESTP31"],
    "mogas production": ["DOETMGLA Index", "petroleum.pnp.wprodrb.W_EPM0F_YPR_NUS_MBBLD"],
    "mogas imports": ["DOEIMGAS Index", "petroleum.move.wkly.WGTIMUS2"],
    "mogas supply": ["DOEDMGAS Index", "petroleum.sum.sndw.WGFUPUS2"],
    "mogas supply 4w average": ["DOEDFMG4 Index", "petroleum.sum.sndw.WGFUPUS2", "four-week-average"],
    "p1 mogas inventory": ["DOESGAS1 Index", "petroleum.sum.sndw.WGTSTP11"],
    "p3 mogas production": ["DOETMGP3 Index", "petroleum.pnp.wprodrb.WGFRPP32"],
    "p3 ethanol": ["DOEPFEP3 Index", "petroleum.pnp.wiup.W_EPOOXE_YIR_R30_MBBLD"],
    "p3 MGBC": ["DOEPBCP3 Index", "petroleum.pnp.wiup.WBCRI_R30_2"],
    "p3 runs": ["DOEPCRP3 Index", "petroleum.sum.sndw.WCRRIP32"],
    "p1 ethanol": ["DOEPFEP1 Index", "petroleum.pnp.wiup.W_EPOOXE_YIR_R10_MBBLD"],
    "p5 total refinery input": ["DOEPBCP5 Index", "petroleum.pnp.wiup.WBCRI_R50_2"],
    "p2 mogas inventory": ["DOESGAS2 Index", "petroleum.sum.sndw.WGTSTP21"],
    "p3 mogas inventory": ["DOESGAS3 Index", "petroleum.sum.sndw.WGTSTP31"],
    "disty production": ["DOETDIST Index", "petroleum.pnp.wprodrb.WDIRPUS2"],
    "disty export": ["DOEBDIST Index", "petroleum.move.wkly.WDIEXUS2"],
    "disty demand": ["DOEDDIST Index", "petroleum.sum.sndw.WDIUPUS2"],
    "disty supply 4w average": ["DOEDDFO4 Index", "petroleum.sum.sndw.WDIUPUS2", "four-week-average"],
    "p1 disty inventory": ["DOESDIS1 Index", "petroleum.sum.sndw.WDISTP11"],
    "p2 disty inventory": ["DOESDIS2 Index", "petroleum.sum.sndw.WDISTP21"],
    "p3 disty inventory": ["DOESDIS3 Index", "petroleum.sum.sndw.WDISTP31"],
    "p3 disty production": ["DOETDIP3 Index", "petroleum.pnp.wprodrb.WDIRPP32"],
}


def create_inventory():
    db = partial(mongo_table, db='data', table='eia_weekly', url=url, pk=['name', 'ticker', 'field'])
    for k, v in ticker_dict.items():
        print(k)
        try:
            c = pyg.get_cell(db, ticker=v[0], field=v[1])
            db().inc(_id=c._id).drop()
        except:
            pass
        if k in ["doe schedule"]:
            data = pd.read_csv(f"S:\\Michel Kikano\\Data\\inventory\\release.csv")
            data = data.set_index("Unnamed: 0")
            c = periodic_cell(function=bbg.release_schedule,
                              ticker=v[0], fields=[v[1]], data=data, name=k,
                              field=v[1], sdate=dt.datetime(2000, 1, 1), edate=None,
                              db=db, period='3n')
        elif v[1] in ["PX_LAST"]:
            data = None
            c = periodic_cell(function=bbg.bdh_update,
                              ticker=v[0], fields=[v[1]], data=data, name=k,
                              field=v[1], sdate=dt.datetime(2000, 1, 1), edate=None,
                              db=db, period='3n')
        else:
            try:
                data = None
                c = periodic_cell(function=dv.eia, ticker=v[0], freq=v[2],
                                  data=data, name=k, field=v[1],
                                  sdate=dt.datetime(2000, 1, 1), edate=None,
                                  db=db, period='3n')
            except:
                data = None
                c = periodic_cell(function=dv.eia, ticker=v[0], freq="weekly",
                                  data=data, name=k, field=v[1],
                                  sdate=dt.datetime(2000, 1, 1), edate=None,
                                  db=db, period='3n')
        c.go()


def update():
    db = partial(mongo_table, db='data', table='eia_weekly', url=url, pk=['name', 'ticker', 'field'])
    for k, v in ticker_dict.items():
        print(k)
        pyg.get_cell(db, ticker=v[0], field=v[1]).go()


if __name__ == "__main__":
    raise NotImplementedError("Missing photographed main block: eia_weekly_petroleum.py after line 129")
