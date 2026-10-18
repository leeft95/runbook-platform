import pandas as pd
import datetime as dt
from pathlib import Path
from ecm.cmds.config import root_path, csv_path


input_path = Path(f"{root_path}/data/Link")
output_path = Path(f"{csv_path}/oil/link")


def split_into_parts_crude(df):
    pipeline_assesments = df.iloc[:, :6]
    spread_assesments = df.iloc[:, 6:]
    raise NotImplementedError("Missing photographed predicate suffixes: save_lnk_eod.py lines 12 and 14")
    pipeline_locations = list(zip(split_position_pipeline[0:], split_position_pipeline[1:]))
    spread_locations = list(zip(split_position_spread[0:], split_position_spread[1:]))
    data_dict = dict()
    columns = ["Ticker", "Settle", "Prev", "Change", "MTD"]
    if len(pipeline_locations) == 1:
        pos = pipeline_locations[0]
        name1 = pos[0][1]
        frame1 = pipeline_assesments.iloc[pos[0][0]:pos[1][0]].iloc[2:, 1:]
        frame1.columns = columns
        data_dict[name1] = frame1
        name2 = pos[1][1]
        frame2 = pipeline_assesments.iloc[pos[1][0]:].iloc[2:, 1:]
        frame2.columns = columns
        data_dict[name2] = frame2
    else:
        for sp in pipeline_locations:
            name = sp[0][1]
            frame = pipeline_assesments.iloc[sp[0][0]:sp[1][0]].iloc[2:, 0:-1]
            frame.columns = columns
            data_dict[name] = frame
    for sp in spread_locations:
        name = sp[0][1]
        frame = spread_assesments.iloc[sp[0][0]:sp[1][0]].iloc[2:, 0:-1]
        frame.columns = columns
        data_dict[name] = frame
    return data_dict


def save_eod_crude(base_path: Path):
    for f in base_path.iterdir():
        if f.stem.startswith("LCDR") and f.suffix == ".xlsx":
            date = pd.to_datetime(f.stem.split(" ")[-1])
            data = pd.read_excel(f, skiprows=[0, 1])
            all_data = split_into_parts_crude(data)
            for name, frame in all_data.items():
                frame["date"] = date
                frame = frame.set_index("date")
                output_name = "_".join(name.lower().split(" "))
                outpath = output_path / f"{output_name}.csv"
                if Path(outpath).exists():
                    curr_data = pd.read_csv(outpath).set_index("date")
                    curr_data.index = pd.to_datetime(curr_data.index)
                else:
                    curr_data = pd.DataFrame()
                out_frame = frame.combine_first(curr_data)
                out_frame.to_csv(outpath)


if __name__ == "__main__":
    save_eod_crude(base_path=input_path)
