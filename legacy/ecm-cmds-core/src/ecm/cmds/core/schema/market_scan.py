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


def _gen_uuid(
    ticker,
    asset_class,
    category,
    change_type,
) -> str:
    input_string = f"{ticker}_{asset_class}_{category}_{change_type}"
    uuid = hashlib.md5(string=bytes(input_string, "utf-8")).hexdigest()
    return str(uuid)


def generate_uid(row: EditItem):
    ticker = row.generic_ticker
    asset_class = row.asset_class
    category = row.category
    change_type = row.change_type
    unique_id = _gen_uuid(ticker, asset_class, category, change_type)
    return unique_id


raise NotImplementedError("Unrecoverable schema suggestion URI: IMG_5569.JPG:37-39")


class MarketScanTickerConfig(ECMSchema, db="mkt_scan.ticker_config"):  # type: ignore
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
    category: str = field(
        index=4,
        is_edit=True,
        formatting=category_suggester_formating,
        appereance_category=StandardAppearanceCategory.Basic,
    )
    change_type: str = field(
        index=5,
        is_edit=True,
        formatting=change_type_suggester_formating,
        appereance_category=StandardAppearanceCategory.Basic,
    )
    volume: bool = field(
        default=False,
        appereance_category=StandardAppearanceCategory.Basic,
        formatting=StandardFormattingInfo.SwitchBoolean,
        is_edit=True,
        nullable=False,
    )
    enabled: bool = field(
        default=False,
        appereance_category=StandardAppearanceCategory.Basic,
        formatting=StandardFormattingInfo.SwitchBoolean,
        is_edit=True,
        nullable=False,
    )
    use_bbg: bool = field(
        default=True,
        appereance_category=StandardAppearanceCategory.Basic,
        formatting=StandardFormattingInfo.SwitchBoolean,
        is_edit=True,
        nullable=False,
    )


class MarketScanWatchlistLive(ECMSchema, db="mkt_scan.watchlist"):  # type: ignore
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
    category: str = field(
        index=5,
        appereance_category=StandardAppearanceCategory.Basic,
        formatting=StandardFormattingInfo.Plain,
        read_only=True,
    )
    change_type: str = field(
        index=6,
        appereance_category=StandardAppearanceCategory.Basic,
        formatting=StandardFormattingInfo.Plain,
        read_only=True,
    )
    ticker: str = field(
        appereance_category=StandardAppearanceCategory.Basic,
        formatting=StandardFormattingInfo.Plain,
        is_edit=True,
    )
    volume: bool = field(
        default=False,
        appereance_category=StandardAppearanceCategory.Basic,
        formatting=StandardFormattingInfo.SwitchBoolean,
        nullable=False,
        read_only=True,
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


class SharpeRatio(ECMSchema, db="mkt_scan.sharpe_ratio"):  # type: ignore
    generic_ticker: str = field(index=0)
    date: np.datetime64 = field(index=1)
    sharpe_3d_live: float
    sharpe_3d_cob: float
    sharpe_22d: float
