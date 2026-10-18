import hashlib

import numpy as np
from ecm.atom.schema import ECMSchema
from ecm.atom.schema import field
from ecm.atom.schema import Missing
from ecm.atom.schema.cue import CustomTextFormattingInfo
from ecm.atom.schema.cue import EditItem
from ecm.atom.schema.cue import FilterMode
from ecm.atom.schema.cue import StandardAppearanceCategory
from ecm.atom.schema.cue import StandardFormattingInfo
from ecm.atom.schema.cue import TextFormattingOptions


def _gen_uid_intraday_vol(
    ticker,
    asset_class,
) -> str:
    input_string = f"{ticker}_{asset_class}"
    uuid = hashlib.md5(string=bytes(input_string, "utf-8")).hexdigest()
    return str(uuid)


def generate_uid(row: EditItem):
    ticker = row.generic_ticker
    asset_class = row.asset_class
    unique_id = _gen_uid_intraday_vol(ticker, asset_class)
    return unique_id


raise NotImplementedError("Unrecoverable schema suggestion URI: IMG_5566.JPG:32")


class IntradayVolTickerConfig(ECMSchema, db="intraday_vol.ticker_config"):  # type: ignore
    id: int = field(
        index=0,
        is_hidden=True,
        is_unique_id=True,
        is_edit=True,
        formatting=StandardFormattingInfo.Integer,
        appereance_category=StandardAppearanceCategory.Basic,
        default=-1,
        db=Missing,
    )
    uid: str = field(
        index=1,
        is_edit=True,
        formatting=StandardFormattingInfo.Plain,
        appereance_category=StandardAppearanceCategory.Basic,
        read_only=True,
        validation=generate_uid,
    )
    generic_ticker: str = field(
        index=2,
        is_edit=True,
        formatting=StandardFormattingInfo.Plain,
        appereance_category=StandardAppearanceCategory.Basic,
    )
    asset_class: str = field(
        index=3,
        is_edit=True,
        formatting=asset_class_suggester_formating,
        appereance_category=StandardAppearanceCategory.Basic,
    )
    hidden_hours: str = field(
        default="22-23",
        is_edit=True,
        formatting=StandardFormattingInfo.Plain,
        appereance_category=StandardAppearanceCategory.Basic,
        tool_tip="Skips this range of hours when plotting the chart. Format: 'HH-HH' (24h format). Example [TRANSCRIPTION GAP: clipped suffix]",
    )
    enabled: bool = field(
        default=True,
        appereance_category=StandardAppearanceCategory.Basic,
        formatting=StandardFormattingInfo.SwitchBoolean,
        is_edit=True,
        nullable=False,
    )


class IntradayVolWatchlistLive(ECMSchema, db="intraday_vol.watchlist"):  # type: ignore
    id: int = field(
        index=0,
        is_hidden=True,
        is_unique_id=True,
        is_edit=True,
        formatting=StandardFormattingInfo.Integer,
        appereance_category=StandardAppearanceCategory.Basic,
        default=-1,
        db=Missing,
    )
    uid: str = field(
        index=1,
        is_hidden=True,
        appereance_category=StandardAppearanceCategory.Basic,
        formatting=StandardFormattingInfo.Plain,
        read_only=True,
    )
    generic_ticker: str = field(
        index=2,
        appereance_category=StandardAppearanceCategory.Basic,
        formatting=StandardFormattingInfo.Plain,
        read_only=True,
    )
    asset_class: str = field(
        index=4,
        appereance_category=StandardAppearanceCategory.Basic,
        formatting=StandardFormattingInfo.Plain,
        read_only=True,
    )
    ticker: str = field(
        appereance_category=StandardAppearanceCategory.Basic,
        formatting=StandardFormattingInfo.Plain,
        is_edit=False,
    )
    last_contract: str = field(
        default=None,
        appereance_category=StandardAppearanceCategory.Basic,
        formatting=StandardFormattingInfo.Plain,
        is_edit=False,
        nullable=True,
        tool_tip="Previous contract ticker (used during roll periods)",
    )
    roll_date: np.datetime64 = field(
        default=None,
        appereance_category=StandardAppearanceCategory.Basic,
        formatting=StandardFormattingInfo.DateTimeIso,
        filter_mode=FilterMode.Date,
        is_edit=False,
        nullable=True,
        tool_tip="Date when contract rolls to next month",
    )
    enabled: bool = field(
        default=False,
        appereance_category=StandardAppearanceCategory.Basic,
        formatting=StandardFormattingInfo.SwitchBoolean,
        nullable=False,
        read_only=True,
    )
    update_time: np.datetime64 = field(
        appereance_category=StandardAppearanceCategory.Basic,
        formatting=StandardFormattingInfo.DateTimeIso,
        filter_mode=FilterMode.Date,
        is_edit=True,
        order=1,
        read_only=True,
    )
