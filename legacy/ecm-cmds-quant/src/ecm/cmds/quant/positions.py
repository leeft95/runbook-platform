import datetime as dt
import json
from pathlib import Path

import pandas as pd
from ecm.cmds.core.cdr import today
from ecm.cmds.core.pyg import get_data
from ecm.cmds.core.ticker import as_active
from ecm.cmds.core.ticker import convert_spread_ticker
from ecm.cmds.core.ticker import decompose_ticker

from .blotter_utils import convert_trades_to_blotter
from .ced import sys_position


def get_positions(substrategy=None, strategy="SYS", trade_date: str | None | dt.datetime = None):
    positions = sys_position(substrategy=substrategy, dt=trade_date)
    return positions


def get_actual_positions(
    sub_strategy="IROLL",
    spread=True,
    fut_gen_month="FGHJKMNQUVXZ",
    hms=0,
    trade_date: str | None | dt.datetime = None,
):
    total_pos_dict = {}
    positions = get_positions(substrategy=sub_strategy, strategy="SYS", trade_date=trade_date)
    if positions.empty:
        print(f"No Positions found for {sub_strategy} on {trade_date or today()}")
        return {"EMPTY": pd.DataFrame()}
    if hms == 0:
        positions["date"] = [x.replace(hour=0, minute=0, second=0, microsecond=0) for x in positions["date"]]
    positions = positions.sort_values("description")
    positions["description"] = [x.rpartition(" ")[0] for x in positions["description"].values]
    if len(positions) > 0:
        positions["tradedate"] = positions["date"].dt.normalize()
    ins_list = positions["mkt"].unique()
    for ins in ins_list:
        ins_df = positions.loc[positions["mkt"] == ins, :].sort_values("expiryDate")
        ins_df.reset_index(drop=True, inplace=True)
        if spread:
            pos_df = to_spread_positions(ins_df, fut_gen_month=fut_gen_month)
        else:
            pos_df = pd.DataFrame(
                ins_df["value"].values.reshape(1, len(ins_df["value"].values)),
                index=[ins_df["date"].iloc[0]],
                columns=ins_df["description"].values + " Comdty",
            )
        total_pos_dict[f"{ins}A Comdty"] = pos_df
    return total_pos_dict


def to_spread_positions(ins_df, fut_gen_month="FGHJKMNQUVXZ"):
    pos_df = pd.DataFrame()
    if ins_df.shape[0] == 2:
        if ins_df["value"].iloc[0] == -ins_df["value"].iloc[1]:
            flat_ticker0 = f"{ins_df.loc[0, 'description']} Comdty"
            flat_ticker1 = f"{ins_df.loc[1, 'description']} Comdty"
            ticker0_dict = decompose_ticker(flat_ticker0)
            ticker1_dict = decompose_ticker(flat_ticker1)
            mon0 = ticker0_dict["m"]
            mon1 = ticker1_dict["m"]
            mon0_idx = fut_gen_month.index(mon0)
            mon1_idx = fut_gen_month.index(mon1)
            days_expiry = (ins_df.loc[1, "expiryDate"] - ins_df.loc[0, "expiryDate"]).days
            if mon1_idx - mon0_idx > 1:
                raise NotImplementedError("Missing intermediate ticker/date expressions: IMG_5525 lines 73, 78")
                for idx_i, i in enumerate(tickers_middle):
                    row = ins_df.loc[0, :].copy()
                    row["description"] = i
                    row["value"] = 0
                    ins_df = ins_df.append(row, ignore_index=True)
                ins_df.sort_values("expiryDate", inplace=True)
                ins_df.reset_index(drop=True, inplace=True)
                for idx, _ in ins_df.iterrows():
                    if idx > 0:
                        ticker = f"{''.join(ins_df['description'].iloc[idx - 1: idx + 1])} Comdty"  # noqa: E203
                        ticker = convert_spread_ticker(ticker, long_to_short=False)
                        df = pd.DataFrame(
                            ins_df["value"].iloc[idx - 1 : idx].values,  # noqa: E203
                            index=[ins_df["tradedate"].iloc[idx]],
                            columns=[ticker],
                        )
                        ins_df.loc[idx, "value"] = ins_df.loc[idx, "value"] + ins_df.loc[idx - 1, "value"]
                        pos_df = pd.concat([pos_df, df], axis=1)
            else:
                ticker = f"{''.join(ins_df['description'].values)} Comdty"
                ticker = convert_spread_ticker(ticker, long_to_short=False)
                pos_df = pd.DataFrame(
                    ins_df["value"].values[0],
                    index=[ins_df["tradedate"].iloc[0]],
                    columns=[ticker],
                )
        else:
            raise Exception("sizes are not equal on two legs of spread")
    else:
        for idx, _ in ins_df.iterrows():
            if idx > 0:
                ticker = f"{''.join(ins_df['description'].iloc[idx - 1: idx + 1])} Comdty"
                ticker = convert_spread_ticker(ticker, long_to_short=False)
                df = pd.DataFrame(
                    ins_df["value"].iloc[idx - 1 : idx].values,  # noqa: E203
                    index=[ins_df["date"].iloc[idx]],
                    columns=[ticker],
                )
                ins_df.loc[idx, "value"] = ins_df.loc[idx, "value"] + ins_df.loc[idx - 1, "value"]
                pos_df = pd.concat([pos_df, df], axis=1)
    return pos_df


def create_order(substrategy: list, is_spread: bool = False, test_date=None, thr=0):
    base_dir = Path(r"\\elementcapital.corp\ecns01\TFR\PM_TF\L025")
    if test_date is None:
        test_date = today()

    trade_dir = base_dir / test_date.strftime("%Y%m%d")

    all = False
    keys = substrategy
    file_data = {}
    for file in trade_dir.iterdir():
        if file.suffix.endswith(".txt") and file.stem.startswith("L025-SYS"):
            if not all and file.stem.replace(f"-NYC-{test_date.strftime('%Y%m%d')}", "").replace("L025-SYS-", "") not in keys:
                continue
            else:
                print(f"reading {file.stem}")
                with open(file, "r") as f:
                    lines = f.readlines()
                    if len(lines) > 1:
                        raise ValueError(f"{file} has multiple lines")
                    elif len(lines) == 1:
                        file_data[file.stem[:-9]] = json.loads(lines[-1].strip())
                    else:
                        raise EOFError(f"No data in {file} to read")
    frames = []
    for key, raw_data in file_data.items():
        df_raw = pd.DataFrame([x for x in raw_data["Portfolio"]["Positions"]])
        if is_spread:
            df_ = df_raw.copy()
            df_["mkt"] = [decompose_ticker(x["Ticker"])["base_ticker"] for idx, x in df_.iterrows()]
            df_["description"] = [x["Ticker"].rpartition(" ")[0] for idx, x in df_.iterrows()]
            df_["active"] = [as_active(x["Ticker"]) for idx, x in df_.iterrows()]
            df_.rename(columns={"Amount": "value", "PositionDate": "tradedate"}, inplace=True)
            df_["date"] = df_["tradedate"]
            total_pos_dict = {}
            ins_list = df_["active"].unique()
            for ins in ins_list:
                ins_df = df_.loc[df_["active"] == ins, :].sort_values("Ticker")
                contracts = get_data("contracts", active=ins, item="fut_chain")
                raise NotImplementedError("Missing expiry lookup expression: IMG_5526 line 161")
                ins_df.sort_values("expiryDate", inplace=True)
                ins_df.reset_index(drop=True, inplace=True)
                pos_df = to_spread_positions(
                    ins_df,
                    fut_gen_month=get_data("contracts", active=ins, item="ref")["FUT_GEN_MONTH"],
                )
                total_pos_dict[ins] = pos_df
            df = pd.concat([v for v in total_pos_dict.values()], axis=1).T
            df.reset_index(inplace=True)
            df.columns = ["Ticker", "Amount"]
            df["StrategyName"] = df_raw["StrategyName"].iloc[0]
            df["PositionDate"] = df_raw["PositionDate"].iloc[0]
        else:
            df = df_raw.copy()
        df.Ticker = df.Ticker.str.upper()
        df["Model"] = [x[-1] for x in df.StrategyName.str.split(",")]
        df["FileName"] = key
        if len(df.Model.unique()) == 1:
            positions = get_actual_positions(df.Model.unique()[-1], trade_date=test_date, spread=is_spread)
            if len(positions) == 1 and positions.get("EMPTY") is not None:
                df["ExistingPositions"] = 0
            else:
                raise NotImplementedError("Missing existing-position rename key: IMG_5527 line 188")
                curr_positions["PositionDate"] = df["PositionDate"].iloc[0]
                curr_positions["StrategyName"] = df["StrategyName"].iloc[0]
                curr_positions["Model"] = df["Model"].iloc[0]
                curr_positions["FileName"] = df["FileName"].iloc[0]
                curr_positions.index = curr_positions.index.str.upper()
                curr_positions.index.name = "Ticker"
                df = df.set_index("Ticker").join(curr_positions[["ExistingPositions"]], how="outer").fillna(0)
        else:
            raise Exception(f"Multiple Models for File {key} {test_date}")
        frames.append(df)
    all_strats = pd.concat(frames)
    all_strats["Net"] = all_strats["Amount"] - all_strats["ExistingPositions"]
    all_strats.loc[all_strats["Net"].abs() < thr, "Net"] = 0
    num_by_ticker = all_strats.groupby("Ticker").sum().rename(columns={"Net": "TickerTotal"})
    pivoted_data = all_strats.pivot(values=["Net"], columns=["Model"], index=["PositionDate", "Ticker", "StrategyName"])
    pivoted_data.columns = [x[-1] if x[-1] != "" else x[0] for x in pivoted_data.columns]
    joined = pivoted_data.join(num_by_ticker)
    joined["StratTotal"] = joined.drop(columns=["TickerTotal", "ExistingPositions", "Amount"]).fillna(0).sum(axis=1)
    send_to_trade = (
        joined[joined.StratTotal != 0]
        .reset_index()
        .drop(columns=["StrategyName", "ExistingPositions", "StratTotal", "Amount"])
        .fillna(0)
        .groupby(["Ticker", "TickerTotal", "PositionDate"])
        .sum()
        .reset_index()
        .rename(columns={"TickerTotal": "Num", "Ticker": "Contract"})
    )
    send_to_trade["BS"] = send_to_trade.Num.apply(lambda x: "BUY" if x > 0 else "SELL")
    send_to_trade_req_columns = ["BS", "Num", "Contract"]
    models = [x for x in send_to_trade.columns if x not in send_to_trade_req_columns]
    send_to_trade = send_to_trade[send_to_trade_req_columns + models]
    send_to_trade["Num"] = send_to_trade["Num"].abs().astype("int32")
    if is_spread:
        send_to_trade["Contract"] = [convert_spread_ticker(x) for x in send_to_trade["Contract"]]
    return send_to_trade


if __name__ == "__main__":
    send_to_trade = create_order(substrategy=["PLATTS-SG", "SPRD26", "DOE-FP"], is_spread=False)
    send_to_trade = create_order(substrategy=["POV-RV", "DFL-RV", "FISHLT-RV"], is_spread=True)
    send_to_blotter = convert_trades_to_blotter(send_to_trade, spread=True, env="dev", counterparty="PVM")
    print(send_to_blotter)
    pos = create_order(substrategy=["POV-GO"], is_spread=True)
    print(pos)
