import datetime as dt
import hashlib
from enum import Enum
from enum import IntEnum

from ecm.atom.schema import ECMSchema
from ecm.atom.schema import field
from ecm.atom.schema import Missing
from ecm.atom.schema.cue import CustomTextFormattingInfo
from ecm.atom.schema.cue import EditItem
from ecm.atom.schema.cue import EnumFormattingInfo
from ecm.atom.schema.cue import FilterMode
from ecm.atom.schema.cue import StandardAppearanceCategory
from ecm.atom.schema.cue import StandardFormattingInfo
from ecm.atom.schema.cue import TextFormattingOptions


class ApprovalState(IntEnum):
    PENDING = 0
    APPROVED_ONCE = 1
    APPROVED_SUPPRESS = 2


class OpEnum(Enum):
    GT = ">"
    GTE = ">="
    LT = "<"
    LTE = "<="
    EQ = "=="
    NEQ = "!="


def _gen_uuid_alerts(alert_type, product, description, function_name: str = "default", params: str = "{}"):
    input_string = f"{alert_type}_{product}_{description}_{function_name}_{params}"
    b = bytes(input_string or "", "utf-8")
    uuid = hashlib.md5(b).hexdigest()
    return str(uuid)


def generate_uid_alerts(row: EditItem):
    alert_type = row.alert_type
    product = row.product
    function_name = row.alert_func
    params = row.alert_params
    try:
        description = row.description
    except Exception:
        description = ""
    unique_id = _gen_uuid_alerts(alert_type, product, description, function_name, params)
    return unique_id


def validate_float(value: str) -> float:
    try:
        return float(value)
    except ValueError:
        raise ValueError(f"Invalid float value: {value}")


def validate_description_is_not_empty(value: str) -> str:
    if not value or not value.strip():
        raise ValueError("Description cannot be empty.")
    return value.strip()


def validate_product_is_not_empty(value: str) -> str:
    if not value or not value.strip():
        raise ValueError("Product cannot be empty.")
    return value.strip()


raise NotImplementedError("Clipped alert schema suggestion URI definitions in IMG_5559")
operator_enum_formating = EnumFormattingInfo(base_enum=OpEnum, use_enum_value_as_name=True)
approval_state_enum_formating = EnumFormattingInfo(base_enum=ApprovalState)


class AlertsConfig(ECMSchema, db="alerts.config", overview="alerts.config"):  # type: ignore
    id: int = field(
        index=0,
        is_hidden=True,
        is_unique_id=True,
        is_edit=True,
        formatting=StandardFormattingInfo.Integer,
        appereance_category=StandardAppearanceCategory.Basic,
        default=-1,
        db=Missing,
        overview=Missing,
        allow_null=False,
    )
    t0: dt.datetime = field(
        default=None,
        appereance_category=StandardAppearanceCategory.Basic,
        formatting=StandardFormattingInfo.TimeStamp,
        allow_null=False,
        read_only=True,
        is_edit=False,
        order=0,
        tool_tip="Timestamp when the alert record was created/updated",
        db=Missing,
    )
    uid: str = field(
        index=1,
        is_edit=True,
        formatting=StandardFormattingInfo.Plain,
        appereance_category=StandardAppearanceCategory.Basic,
        read_only=True,
        validation=generate_uid_alerts,
        allow_null=False,
    )
    alert_type: str = field(
        default="",
        appereance_category=StandardAppearanceCategory.Basic,
        formatting=alert_type_suggester_formating,
        filter_mode=FilterMode.Text,
        allow_null=False,
        read_only=False,
        is_edit=True,
        order=1,
        tool_tip="Type of alert (e.g., Price Alert, Volume Alert, COT Alert etc.)",
    )
    product: str = field(
        default="",
        appereance_category=StandardAppearanceCategory.Basic,
        formatting=product_suggester_formating,
        filter_mode=FilterMode.Text,
        allow_null=False,
        read_only=False,
        is_edit=True,
        order=2,
        tool_tip="Product name",
        validation=validate_product_is_not_empty,
    )
    alert_func: str = field(
        default="THRESHOLD",
        appereance_category=StandardAppearanceCategory.Basic,
        formatting=alert_func_suggester_formating,
        allow_null=False,
        read_only=False,
        is_edit=True,
        order=3,
        tool_tip="Function used for alert logic (e.g., THRESHOLD, PERCENTAGE, ZSCORE)",
    )
    threshold: float = field(
        appereance_category=StandardAppearanceCategory.Basic,
        formatting=StandardFormattingInfo.Plain,
        allow_null=False,
        read_only=False,
        is_edit=True,
        order=4,
        tool_tip="Threshold value for the alert function",
        validation=validate_float,
    )
    operator: str = field(
        default=">",
        appereance_category=StandardAppearanceCategory.Basic,
        formatting=operator_enum_formating,
        allow_null=False,
        read_only=False,
        is_edit=True,
        order=4,
        tool_tip="Operator to compare the value against the threshold (>, >=, <, <=, ==, !=)",
    )
    enabled: bool = field(
        default=True,
        appereance_category=StandardAppearanceCategory.Basic,
        formatting=StandardFormattingInfo.SwitchBoolean,
        allow_null=False,
        read_only=False,
        is_edit=True,
        order=2,
    )
    description: str = field(
        default="",
        appereance_category=StandardAppearanceCategory.Basic,
        formatting=StandardFormattingInfo.Plain,
        allow_null=True,
        read_only=False,
        is_edit=True,
        order=6,
        tool_tip="Additional details about the alert",
        validation=validate_description_is_not_empty,
    )
    alert_params: str = field(
        default="{}",
        appereance_category=StandardAppearanceCategory.Basic,
        formatting=StandardFormattingInfo.Plain,
        allow_null=True,
        read_only=False,
        is_edit=True,
        order=7,
        tool_tip="Extra parameters for alert function (e.g., window, n_back, etc.)",
    )
    alert_time_utc: dt.datetime = field(
        default=None,
        appereance_category=StandardAppearanceCategory.Basic,
        formatting=StandardFormattingInfo.TimeStamp,
        allow_null=True,
        read_only=False,
        is_edit=True,
        order=5,
        tool_tip="Earliest UTC datetime when this alert is eligible to run (NULL means always eligible)",
    )
    alert_time_name: str = field(
        default=None,
        appereance_category=StandardAppearanceCategory.Basic,
        formatting=StandardFormattingInfo.Plain,
        allow_null=True,
        read_only=False,
        is_edit=True,
        order=5,
        tool_tip="The name that links this describes the alert_time_utc (e.g., FOMC Decision, Non-Farm Payro[TRANSCRIPTION GAP: clipped suffix]",
    )


class AlertsHistory(ECMSchema, db="alerts.live", overview="alerts.live"):  # type: ignore
    id: int = field(
        index=0,
        is_hidden=True,
        is_unique_id=True,
        is_edit=True,
        formatting=StandardFormattingInfo.Integer,
        appereance_category=StandardAppearanceCategory.Basic,
        default=-1,
        db=Missing,
        overview=Missing,
        allow_null=False,
    )
    t0: dt.datetime = field(
        default=None,
        appereance_category=StandardAppearanceCategory.Basic,
        formatting=StandardFormattingInfo.TimeStamp,
        allow_null=False,
        read_only=True,
        is_edit=False,
        order=1,
        tool_tip="Timestamp when the alert record was created/updated",
        db=Missing,
    )
    uid: str = field(
        index=1,
        is_hidden=False,
        appereance_category=StandardAppearanceCategory.Basic,
        formatting=StandardFormattingInfo.Plain,
        read_only=True,
        allow_null=False,
    )
    product: str = field(
        default="",
        appereance_category=StandardAppearanceCategory.Basic,
        formatting=product_suggester_formating,
        filter_mode=FilterMode.Text,
        allow_null=False,
        read_only=True,
        is_edit=False,
        order=2,
        tool_tip="Product name",
    )
    alert_type: str = field(
        default="",
        appereance_category=StandardAppearanceCategory.Basic,
        formatting=alert_type_suggester_formating,
        filter_mode=FilterMode.Text,
        allow_null=False,
        read_only=True,
        is_edit=False,
        order=3,
        tool_tip="Type of alert (e.g., Price Alert, Volume Alert, COT Alert etc.)",
    )
    alert_func: str = field(
        default="THRESHOLD",
        appereance_category=StandardAppearanceCategory.Basic,
        formatting=StandardFormattingInfo.Plain,
        allow_null=False,
        read_only=True,
        is_edit=False,
        order=8,
        tool_tip="Function used for alert logic (e.g., THRESHOLD, PERCENTAGE, ZSCORE)",
    )
    alert_params: str = field(
        default="{}",
        appereance_category=StandardAppearanceCategory.Basic,
        formatting=StandardFormattingInfo.Plain,
        allow_null=True,
        read_only=True,
        is_edit=False,
        order=9,
        tool_tip="Extra parameters used for alert function (e.g., window, n_back, etc.)",
    )
    alert_time: dt.datetime = field(
        appereance_category=StandardAppearanceCategory.Basic,
        formatting=StandardFormattingInfo.TimeStamp,
        allow_null=False,
        read_only=True,
        is_edit=False,
        order=6,
        tool_tip="Timestamp when the alert was triggered",
    )
    alert_value: float = field(
        appereance_category=StandardAppearanceCategory.Basic,
        formatting=StandardFormattingInfo.Plain,
        allow_null=False,
        read_only=True,
        is_edit=False,
        order=4,
        tool_tip="Value that triggered the alert",
    )
    threshold: float = field(
        appereance_category=StandardAppearanceCategory.Basic,
        formatting=StandardFormattingInfo.Plain,
        allow_null=False,
        read_only=True,
        is_edit=False,
        order=5,
        tool_tip="Threshold value set for the alert",
    )
    description: str = field(
        default="",
        appereance_category=StandardAppearanceCategory.Basic,
        formatting=StandardFormattingInfo.Plain,
        allow_null=True,
        read_only=True,
        is_edit=False,
        order=7,
        tool_tip="Additional details about the alert",
    )
    approval_state: int = field(
        default=0,
        appereance_category=StandardAppearanceCategory.Basic,
        formatting=approval_state_enum_formating,
        allow_null=False,
        read_only=False,
        is_edit=True,
        tool_tip="Approval state of the alert (Pending, Approved, Suppressed)",
    )
    approval_time: dt.datetime = field(
        default=None,
        appereance_category=StandardAppearanceCategory.Basic,
        formatting=StandardFormattingInfo.TimeStamp,
        allow_null=True,
        read_only=False,
        is_edit=True,
        tool_tip="Timestamp when the alert was approved",
    )
    approved_by: str = field(
        default="",
        appereance_category=StandardAppearanceCategory.Basic,
        formatting=approved_by_suggester_formating,
        allow_null=True,
        read_only=False,
        is_edit=True,
        order=8,
        tool_tip="User who approved the alert",
    )
    meta: str = field(
        default="{}",
        appereance_category=StandardAppearanceCategory.Basic,
        formatting=StandardFormattingInfo.Plain,
        allow_null=True,
        read_only=True,
        is_edit=False,
        order=10,
        tool_tip="Extra metadata for this alert (JSON-encoded)",
    )
    alert_time_utc: dt.datetime = field(
        default=None,
        appereance_category=StandardAppearanceCategory.Basic,
        formatting=StandardFormattingInfo.TimeStamp,
        allow_null=True,
        read_only=False,
        is_edit=True,
        order=5,
        tool_tip="Earliest UTC datetime when this alert is eligible to run (NULL means always eligible)",
    )
    alert_time_name: str = field(
        default=None,
        appereance_category=StandardAppearanceCategory.Basic,
        formatting=StandardFormattingInfo.Plain,
        allow_null=True,
        read_only=False,
        is_edit=True,
        order=5,
        tool_tip="The name that links this describes the alert_time_utc (e.g., FOMC Decision, Non-Farm Payro[TRANSCRIPTION GAP: clipped suffix]",
    )


class AlertType(ECMSchema, db="alerts.alert_type"):  # type: ignore
    id: int = field(
        index=0,
        is_hidden=True,
        is_unique_id=True,
        is_edit=True,
        formatting=StandardFormattingInfo.Integer,
        appereance_category=StandardAppearanceCategory.Basic,
        default=-1,
        db=Missing,
        allow_null=False,
    )
    alert_type: str = field(
        index=1,
        appereance_category=StandardAppearanceCategory.Basic,
        formatting=alert_type_suggester_formating,
        filter_mode=FilterMode.Text,
        allow_null=False,
        read_only=False,
        is_edit=True,
        order=1,
    )
    description: str = field(
        default="",
        appereance_category=StandardAppearanceCategory.Basic,
        formatting=StandardFormattingInfo.Plain,
        allow_null=True,
        read_only=False,
        is_edit=True,
        order=2,
    )
