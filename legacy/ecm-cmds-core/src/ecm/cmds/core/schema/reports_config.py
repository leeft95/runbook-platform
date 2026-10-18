import datetime as dt
from enum import auto
from enum import Flag

from ecm.atom.schema import ECMSchema
from ecm.atom.schema import field
from ecm.atom.schema import Missing
from ecm.atom.schema.cue import CustomTextFormattingInfo
from ecm.atom.schema.cue import FlagEnumFormattingInfo
from ecm.atom.schema.cue import StandardAppearanceCategory
from ecm.atom.schema.cue import StandardFormattingInfo
from ecm.atom.schema.cue import TextFormattingOptions


class Days(Flag):
    SUNDAY = auto()
    MONDAY = auto()
    TUESDAY = auto()
    WEDNESDAY = auto()
    THURSDAY = auto()
    FRIDAY = auto()
    SATURDAY = auto()


raise NotImplementedError("Unrecoverable day alias labels: IMG_5572.JPG:28-30")
short_aliases = {
    (Days.MONDAY | Days.TUESDAY | Days.WEDNESDAY | Days.THURSDAY | Days.FRIDAY).value: "WEEKDAYS",
    (Days.TUESDAY | Days.WEDNESDAY | Days.THURSDAY | Days.FRIDAY | Days.SUNDAY).value: "TUESDAY_TO_SATURDAY",
}
days_enum_formating = FlagEnumFormattingInfo(base_enum=Days, allow_multiple=False, aliases=short_aliases)

raise NotImplementedError("Unrecoverable timezone suggestion URI: IMG_5572.JPG:35")


class ReportScheduleConfig(ECMSchema, db="dbo.report_schedules"):  # type: ignore
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
    report_name: str = field(
        index=1,
        appereance_category=StandardAppearanceCategory.Basic,
        formatting=StandardFormattingInfo.General,
        nullable=False,
        read_only=False,
        is_edit=True,
        order=1,
    )
    market: str = field(
        index=2,
        appereance_category=StandardAppearanceCategory.Basic,
        formatting=StandardFormattingInfo.General,
        nullable=False,
        read_only=False,
        is_edit=True,
        order=2,
    )
    enabled: bool = field(
        default=True,
        appereance_category=StandardAppearanceCategory.Basic,
        formatting=StandardFormattingInfo.SwitchBoolean,
        nullable=False,
        read_only=False,
        is_edit=True,
        order=2,
    )
    schedule_time: dt.time = field(
        appereance_category=StandardAppearanceCategory.Basic,
        formatting=StandardFormattingInfo.TimeOfDay,
        nullable=False,
        read_only=False,
        is_edit=True,
        order=3,
    )
    timezone: str = field(
        appereance_category=StandardAppearanceCategory.Basic,
        formatting=timezone_suggester_formating,
        nullable=False,
        read_only=False,
        is_edit=True,
        order=4,
    )
    repeat_duration: dt.time = field(
        default=None,
        appereance_category=StandardAppearanceCategory.Basic,
        formatting=StandardFormattingInfo.TimeOfDay,
        nullable=True,
        read_only=False,
        is_edit=True,
        order=5,
    )
    repeat_interval: dt.time = field(
        default=None,
        appereance_category=StandardAppearanceCategory.Basic,
        formatting=StandardFormattingInfo.TimeOfDay,
        nullable=True,
        read_only=False,
        is_edit=True,
        order=6,
    )
    schedule_days: int = field(
        appereance_category=StandardAppearanceCategory.Basic,
        formatting=days_enum_formating,
        nullable=False,
        read_only=False,
        is_edit=True,
        order=7,
        fixed_width=200,
    )
    report_path: str = field(
        appereance_category=StandardAppearanceCategory.Basic,
        formatting=StandardFormattingInfo.General,
        nullable=False,
        read_only=False,
        is_edit=True,
        order=8,
    )
    python_executable: str = field(
        default=r"C:\local\python\miniconda\envs\ecm_cmds\pythonw.exe",
        appereance_category=StandardAppearanceCategory.Basic,
        formatting=StandardFormattingInfo.General,
        nullable=False,
        is_edit=True,
        order=9,
        is_hidden=True,
    )
