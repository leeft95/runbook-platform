import typing as tp
from enum import Enum

import numpy as np
import pandas as pd
from ecm.cmds.core.schema.alerts import OpEnum
from pydantic.v1 import BaseModel


def _normalize_operator(operator: tp.Union[OpEnum, str]) -> OpEnum:
    """Normalize operator input to an OpEnum.

    Accepts an OpEnum member, a member name like 'GT', or a value like '>' and returns the OpEnum.
    """
    if isinstance(operator, OpEnum):
        return operator
    if operator is None:
        return OpEnum.GT
    try:
        if pd.isna(operator):
            return OpEnum.GT
    except Exception:
        pass
    if isinstance(operator, str):
        s = operator.strip()
        if s == "<NA>" or s.lower() in ("nan", "none", "null", ""):
            return OpEnum.GT
        if s in OpEnum.__members__:
            return OpEnum[s]
        try:
            return OpEnum(s)
        except Exception:
            raise ValueError(f"Invalid OpEnum: {operator}")
    raise ValueError(f"Invalid OpEnum: {operator}")


def _validate_threshold(val: tp.Any, name: str = "threshold", non_negative: bool = False) -> float:
    """
    Ensure threshold is a finite number. Convert to float when possible and
    raise ValueError for None/NaN or non-numeric values. If non_negative is
    True, also require the threshold to be >= 0.
    """
    try:
        if val is None:
            raise ValueError(f"{name} must be provided and numeric")
        f = float(val)
    except Exception:
        raise ValueError(f"{name} must be a numeric value, got: {val!r}")
    if np.isnan(f) or np.isinf(f):
        raise ValueError(f"{name} must be a finite number, got: {val!r}")
    if non_negative and f < 0:
        raise ValueError(f"{name} must be non-negative for this alert function, got {f}")
    return f


def threshold_alert(data: pd.Series | tp.List[float] | float | int, threshold: float, operator: tp.Union[OpEnum, str] = OpEnum.GT) -> pd.DataFrame:
    """
    Function to generate alerts based on a threshold value.
    :param data: Series, list, or scalar value to check against the threshold.
    :param threshold: Threshold value for the alert.
    :return: DataFrame with alerts.
    """
    if isinstance(data, (float, int, np.floating, np.integer)):
        data = pd.DataFrame([data], columns=["value"], index=[0])
    elif isinstance(data, pd.Series):
        data = data.to_frame(name="value")
    elif isinstance(data, list):
        data = pd.DataFrame(data, columns=["value"])
    threshold = _validate_threshold(threshold, "threshold")
    operator = _normalize_operator(operator)

    if operator == OpEnum.GT:
        mask = data["value"] > threshold
    elif operator == OpEnum.GTE:
        mask = data["value"] >= threshold
    elif operator == OpEnum.LT:
        mask = data["value"] < threshold
    elif operator == OpEnum.LTE:
        mask = data["value"] <= threshold
    elif operator == OpEnum.EQ:
        mask = data["value"] == threshold
    elif operator == OpEnum.NEQ:
        mask = data["value"] != threshold
    else:
        raise ValueError(f"Unsupported operation: {operator}")

    data["alert"] = mask.astype(int)
    return data


def percentage_change_alert(data: pd.Series | tp.List[float], threshold: float, n_back: int = 1, operator: tp.Union[OpEnum, str] = OpEnum.GT) -> pd.DataFrame:
    """
    Function to generate alerts based on the n to m day percentage change decimal threshold
    :param data: Series or list of float values to check against the threshold.
    :param threshold: Threshold value for the alert.
    :param n_back: Number of periods to look back for percentage change.
    """
    if isinstance(data, (float, int, np.floating, np.integer)):
        raise ValueError("percentage_change_alert does not support scalar input. Use a list or Series.")
    elif isinstance(data, pd.Series):
        data = data.to_frame(name="value")
    elif isinstance(data, list):
        data = pd.DataFrame(data, columns=["value"])

    data["pct_change"] = data["value"].pct_change(periods=n_back)
    threshold = _validate_threshold(threshold, "threshold")
    operator = _normalize_operator(operator)

    data["pct_change"] = pd.to_numeric(data["pct_change"], errors="coerce")

    match operator:
        case OpEnum.GT:
            comp = data["pct_change"] > threshold
        case OpEnum.GTE:
            comp = data["pct_change"] >= threshold
        case OpEnum.LT:
            comp = data["pct_change"] < threshold
        case OpEnum.LTE:
            comp = data["pct_change"] <= threshold
        case OpEnum.EQ:
            comp = data["pct_change"] == threshold
        case OpEnum.NEQ:
            comp = data["pct_change"] != threshold
        case _:
            raise ValueError(f"Unsupported operation: {operator}")

    comp = comp.fillna(False)
    data["alert"] = comp.astype(int)

    last_row = data.iloc[[-1]].copy()
    return last_row


def z_score_alert_rolling(data: pd.Series | tp.List[float], threshold: float, window: int = 5) -> pd.DataFrame:
    """
    Function to generate alerts based on z-score threshold.
    :param data: Series or list of float values to check against the threshold.
    :param threshold: Z-score threshold value for the alert.
    :param window: Rolling window size for mean and std deviation calculation.
    :return: DataFrame with alerts.
    """
    if isinstance(data, (float, int, np.floating, np.integer)):
        raise ValueError("z_score_alert_rolling does not support scalar input. Use a list or Series.")
    elif isinstance(data, pd.Series):
        data = data.to_frame(name="value")
    elif isinstance(data, list):
        data = pd.DataFrame(data, columns=["value"])

    threshold = _validate_threshold(threshold, "threshold", non_negative=True)
    data["rolling_mean"] = data["value"].rolling(window=window).mean()
    data["rolling_std"] = data["value"].rolling(window=window).std()
    data["z_score"] = (data["value"] - data["rolling_mean"]) / data["rolling_std"]
    data["alert"] = np.where(data["z_score"].abs() > threshold, 1, 0)
    data = data.drop(columns=["rolling_mean", "rolling_std"])
    last_row = data.iloc[[-1]].copy()
    return last_row


def z_score_alert_change(data: pd.Series | tp.List[float], threshold: float, days_over: int = 5, lookback=..., cumsum=...) -> pd.DataFrame:
    """
    [TRANSCRIPTION GAP: first description line not photographed.]
    Takes the day_over as the test period and the lookback as the diff. ie 13d lookback will calculate [clipped]
    :param data: Series or list of float values to check against the threshold.
    :param threshold: Z-score threshold value for the alert.
    :param days_over: Number of days to consider for the alert.
    :param lookback: number of days to look back for the z-score calculation. ie 13d lookback will calculate [clipped]
        (n-1 - n-13) = value to test get the z-score of
    """
    if lookback is ... or cumsum is ...:
        raise NotImplementedError("Unphotographed lookback/cumsum defaults; provide both explicitly")
    threshold = _validate_threshold(threshold, "threshold", non_negative=True)
    if isinstance(data, (float, int, np.floating, np.integer)):
        raise ValueError("z_score_alert_change does not support scalar input. Use a list or Series.")
    elif isinstance(data, pd.Series):
        data = data.to_frame(name="value")
    elif isinstance(data, list):
        data = pd.DataFrame(data, columns=["value"])
    elif isinstance(data, pd.DataFrame):
        if "value" in data.columns:
            data = data[["value"]]

    if len(data) > days_over:
        test_data = data.iloc[-days_over:, :]
    elif len(data) < days_over:
        test_data = data[["value"]]
    else:
        test_data = data[["value"]]

    _n = lookback if lookback != 1 else 2
    if len(test_data) < _n:
        change = 0
        std = 1
    else:
        if cumsum:
            cum_data = test_data["value"].cumsum()
            change = cum_data.iloc[-1] - cum_data.iloc[-_n]
            alert_value = cum_data.iloc[-lookback]
        else:
            change = test_data.iloc[-1]["value"] - test_data.iloc[-_n]["value"]
            alert_value = test_data.iloc[-lookback]["value"]
        std = test_data["value"].std()
    z_score = (change / std) if std != 0 else 0
    alert = 1 if abs(z_score) > threshold else 0
    last_row = test_data.iloc[[-1]].copy()
    last_row["value"] = alert_value
    last_row["alert"] = alert
    last_row["z_score"] = z_score
    return last_row


class AlertFunctionsEnum(Enum):
    THRESHOLD = "THRESHOLD"
    PERCENTAGE = "PERCENTAGE"
    ZSCORE_ROLLING = "ZSCORE_ROLLING"
    ZSCORE_CHANGE = "ZSCORE_CHANGE"


ALERT_FUNCTIONS_MAP = {
    AlertFunctionsEnum.THRESHOLD: threshold_alert,
    AlertFunctionsEnum.PERCENTAGE: percentage_change_alert,
    AlertFunctionsEnum.ZSCORE_ROLLING: z_score_alert_rolling,
    AlertFunctionsEnum.ZSCORE_CHANGE: z_score_alert_change,
}


class AlertFuncs(BaseModel):
    alert_type: str
    description: str
    function_name: str = "default"

    def _default_function(self):
        """
        Default function to be called when the alert type is triggered.
        This can be overridden by the user.
        """
        return AlertFunctionsEnum.THRESHOLD.value

    def get_function(self):
        """
        Returns the function to be called when the alert type is triggered.
        If no function is set, returns the raises an error function.
        """
        if self.function_name == "default":
            return ALERT_FUNCTIONS_MAP[AlertFunctionsEnum.THRESHOLD]
        else:
            try:
                func_enum = AlertFunctionsEnum[self.function_name]
                return ALERT_FUNCTIONS_MAP[func_enum]
            except KeyError:
                raise ValueError(f"Function {self.function_name} not found in AlertFunctionsEnum")


if __name__ == "__main__":
    data = pd.Series([100, 110, 120, 130, 140, 200, 250, 10000], index=pd.date_range(start="2023-01-01", periods=8))
    threshold = 115
    alert_type = AlertFuncs(alert_type="THRESHOLD", description="Threshold alert", function_name="THRESHOLD")
    func = alert_type.get_function()
    result = func(data, threshold, operator=OpEnum.GT)
    print(result)
    n_back = 2
    threshold = 0.1
    alert_type_pct = AlertFuncs(alert_type="PERCENTAGE", description="Percentage change alert", function_name="PERCENTAGE")
    func_pct = alert_type_pct.get_function()
    result_pct = func_pct(data, threshold, n_back, operator=OpEnum.LT)
    print(result_pct)
    z_threshold = 1.5
    alert_type_z = AlertFuncs(alert_type="ZSCORE", description="Z-score alert", function_name="ZSCORE_ROLLING")
    func_z = alert_type_z.get_function()
    result_z = func_z(data, z_threshold, window=3)
    print(result_z)

    print("\n=== Negative threshold sanity checks ===")

    d_neg = pd.Series([-5, -3, 0, 2])
    res_neg_gt = threshold_alert(d_neg, -2, operator=OpEnum.GT)
    print("threshold_alert with threshold>-2 ->")
    print(res_neg_gt)
    res_neg_lt = threshold_alert(d_neg, -4, operator=OpEnum.LT)
    print("threshold_alert with threshold<-4 ->")
    print(res_neg_lt)

    assert res_neg_gt["alert"].tolist() == [0, 0, 1, 1], "threshold_alert negative threshold failed"
    assert res_neg_lt["alert"].tolist() == [1, 0, 0, 0], "threshold_alert negative threshold (LT) failed"

    d_pct = pd.Series([100.0, 90.0])  # pct_change = -0.10
    res_pct = percentage_change_alert(d_pct, -0.05, n_back=1, operator=OpEnum.LT)
    print("percentage_change_alert with threshold=-0.05 ->")
    print(res_pct)
    assert int(res_pct["alert"].iloc[0]) == 1, "percentage_change_alert negative threshold failed"

    try:
        _ = z_score_alert_rolling([1, 2, 3, 4, 5], -1.0, window=3)
        raise SystemExit("z_score_alert_rolling unexpectedly accepted a negative threshold")
    except ValueError as e:
        print("z_score_alert_rolling correctly raised for negative threshold:", e)

    try:
        _ = z_score_alert_change([1, 2, 3, 4, 5], -0.5, days_over=3, lookback=2)
        raise SystemExit("z_score_alert_change unexpectedly accepted a negative threshold")
    except ValueError as e:
        print("z_score_alert_change correctly raised for negative threshold:", e)

    print("\nAll quick checks passed.")
