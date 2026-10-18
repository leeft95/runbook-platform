from __future__ import annotations

import typing as tp
from enum import Enum

import pandas as pd
from ecm.cmds.core.alerting.alerts import AlertsAPI


class ApprovalState(Enum):
    PENDING = 0
    APPROVED = 1
    APPROVED_SUPPRESSED = 2


class DataTestsAPI(AlertsAPI):
    """
    A thin wrapper over AlertsAPI specialized for data tests.
    Uses `test_name` instead of `product` and provides convenience helpers.
    """

    DEFAULT_ALERT_TYPE = "DATA_TESTS"
    DEFAULT_DESCRIPTION = "Data quality and validation tests"

    def __init__(self, alert_type: str | None = None, description: str | None = None, env: str = "dev"):
        super().__init__(
            alert_type=alert_type or self.DEFAULT_ALERT_TYPE,
            description=description or self.DEFAULT_DESCRIPTION,
            env=env,
        )

    def add_test_config(
        self,
        test_name: str,
        threshold: float | int | None,
        alert_func: str = "THRESHOLD",
        enabled: bool = True,
        **params: tp.Any,
    ):
        return super().add_config(product=test_name, alert_func=alert_func, threshold=threshold, enabled=enabled, **params)

    def add_tests_bulk(self, configs: tp.List[tp.Dict[str, tp.Any]]):
        normalized: list[dict[str, tp.Any]] = []
        for c in configs or []:
            d = dict(c)
            if "test_name" in d and "product" not in d:
                d["product"] = d.pop("test_name")
            normalized.append(d)
        return super().add_configs_bulk(normalized)

    def log_test(self, test_name: str, value: float | int | pd.Series, alert_func: str | None = None, meta: dict | None = None):
        return super().log_alert(product=test_name, value=value, alert_func=alert_func, meta=meta)

    def log_tests(self, values: dict[str, float] | pd.Series, alert_func: str | None = None, meta: dict | None = None):
        return super().log_alerts_bulk(alert_data=values, alert_func=alert_func, meta=meta)

    def log_test_series(self, test_name: str, series: pd.Series, alert_func: str | None = None, meta: dict | None = None):
        return super().log_timeseries_alert(product=test_name, series=series, alert_func=alert_func, meta=meta)

    def latest(self, test_name: str | None = None, limit: int = 100):
        return super().get_latest_alerts(product=test_name, limit=limit)

    def history(self, test_name: str | None = None, limit: int = 100):
        return super().get_alert_history(product=test_name, limit=limit)

    def approve(self, *args, **kwargs):  # thin passthrough to keep import surface simple
        return super().approve_alerts(*args, **kwargs)

    def unapprove(self, *args, **kwargs):
        return super().unapprove_alerts(*args, **kwargs)
