import datetime as dt
import inspect
import json
import os
import typing as tp
from getpass import getuser

import pandas as pd
from ecm.cmds.core.alerting.alert_func import _normalize_operator
from ecm.cmds.core.alerting.alert_func import AlertFuncs
from ecm.cmds.core.alerting.alert_func import AlertFunctionsEnum
from ecm.cmds.core.schema.alerts import _gen_uuid_alerts
from ecm.cmds.core.schema.alerts import AlertsConfig
from ecm.cmds.core.schema.alerts import AlertsHistory
from ecm.cmds.core.schema.alerts import AlertType
from ecm.cmds.core.schema.alerts import ApprovalState
from ecm.cmds.core.schema.alerts import OpEnum
from ecm.cmds.core.sql import LO25DB
from ecm.cmds.core.utils import get_rows_to_upsert
from loguru import logger as log

try:
    current_user = os.getlogin()
except OSError:
    current_user = getuser()


class AlertsAPI:
    def __init__(self, alert_type: str = None, description: str = None, env: str = "dev"):
        self.config_schema = AlertsConfig
        self.history_schema = AlertsHistory
        self.generate_uid = _gen_uuid_alerts
        self.env = env
        self.db = LO25DB(env)
        self.description = description if description is not None else "Created by AlertsAPI. Please update the description."
        if alert_type is not None:
            is_valid = self._check_alert_type_is_exists(alert_type, description)
            if not is_valid:
                log.warning(f"Alert type {alert_type} does not exist in the database. Creating a new one.")
                if description is None:
                    description = "Created by AlertsAPI. Please update the description."
                new_alert_type_df = pd.DataFrame(
                    {"alert_type": [alert_type], "description": [description]}, index=[0],
                )
                new_alert_type = AlertType(new_alert_type_df, nullable=False)
                new_alert_type.dump_sql(self.db, form="db", mode="insert_first")
            self.alert_type = alert_type
        else:
            raise ValueError("alert_type must be provided")

    def _log(self, message: str):
        if self.env == "dev":
            log.debug(f"[{self.alert_type}] {message}")

    def _get_description(self) -> str:
        """
        Returns the description of the alert type
        :return: str
        """
        alert_type_df = AlertType.load_sql(self.db, form="db", nullable=False, transform=[f"alert_type = '{self.alert_type}'"])
        if alert_type_df.empty:
            raise ValueError(f"Alert type {self.alert_type} does not exist in the database.")
        return alert_type_df.description.dropna().astype(str).unique().tolist()

    def _history_has_column(self, col: str) -> bool:
        """Check if the alerts history table has a given column."""
        try:
            df = self.history_schema.load_sql(self.db, form="db", nullable=False, transform=[f"alert_type = '{self.alert_type}'"])
        except Exception:
            return False
        return col in df.columns

    def _check_alert_type_is_exists(self, alert_type: str, description) -> bool:
        """
        Checks if the alert type exists in the database
        :return: True if exists, False otherwise
        """
        transform = [f"alert_type='{alert_type}'", f"description='{description}'"]
        alert_types = AlertType.load_sql(self.db, form="db", nullable=False, transform=transform).reset_index()
        return alert_type in alert_types["alert_type"].values and description in alert_types["description"].values

    def _current_config(self, enabled=True) -> AlertsConfig:
        descriptions = self._get_description()
        escaped = [d.replace("'", "''") for d in descriptions]
        in_list = ",".join(f"'{d}'" for d in escaped) if escaped else "''"
        transform_clause = f"alert_type = '{self.alert_type}' and description in ({in_list})"
        current_config = self.config_schema.load_sql(
            source=self.db, form="db", nullable=False, transform=[transform_clause],
        )
        if current_config.empty:
            return current_config
        if enabled:
            current_config = current_config[current_config.enabled == True]  # noqa: E712
        current_config.alert_params = current_config.alert_params.apply(self.safe_json_loads)
        return current_config

    def _update_config(self, new_config) -> AlertsConfig:
        if "alert_params" in new_config.columns:
            new_config["alert_params"] = new_config["alert_params"].apply(lambda x: json.dumps(x) if isinstance(x, dict) else x)
        raise NotImplementedError("Photographed alerts.py line111 upsert key columns are clipped")
        if not upsert_df.empty:
            to_upsert = upsert_df.drop(columns=["update_type"])
            if "alert_params" in to_upsert.columns:
                to_upsert["alert_params"] = to_upsert["alert_params"].apply(lambda x: json.dumps(x) if isinstance(x, dict) else x)
            self.config_schema(to_upsert).dump_sql(self.db, form="db", mode="update_first")
            self._log(f"Upserted {len(to_upsert)} rows to alerts.config")
        else:
            self._log("No new rows to upsert to alerts.config")
        latest_config = self._current_config()
        return latest_config

    def add_config(
        self, product: str, alert_func: str = "THRESHOLD", threshold: float = None,
        enabled: bool = True, operator: tp.Optional[tp.Union[OpEnum, str]] = OpEnum.GT,
        alert_time_utc: tp.Optional[dt.datetime] = None, alert_time_name: tp.Optional[str] = None,
        **alert_params,
    ) -> AlertsConfig:
        if alert_func not in AlertFunctionsEnum.__members__:
            raise ValueError(f"Alert function {alert_func} is not valid. Valid functions are: {list(AlertFunctionsEnum.__members__)}")
        self._validate_alert_func_params(alert_func, alert_params)
        description = self.description
        if threshold is None:
            raise ValueError("Threshold must be provided for alert config.")
        try:
            op_enum = _normalize_operator(operator)
        except Exception:
            op_enum = OpEnum.GT
        uid = self.generate_uid(
            self.alert_type, product, description, alert_func,
            json.dumps(alert_params) if alert_params else "{}",
        )
        op_symbol = op_enum.value
        new_row = {
            "uid": uid, "alert_type": self.alert_type, "product": product,
            "description": description, "alert_func": alert_func, "threshold": threshold,
            "operator": op_symbol, "enabled": enabled,
            "alert_params": json.dumps(alert_params) if alert_params else "{}",
            "alert_time_utc": alert_time_utc, "alert_time_name": alert_time_name,
        }
        new_config = self.config_schema(pd.DataFrame([new_row], index=[0]))
        latest_config = self._update_config(new_config)
        return latest_config

    def add_configs_bulk(self, configs: tp.List[tp.Dict[str, tp.Any]]) -> AlertsConfig:
        """
        Adds multiple alert configurations for the alert type in bulk. Each config must include:
            - alert_type: str
            - product: str
            - description: str
            - alert_func: str
            - threshold: float
            - enabled: bool (optional, default True)
            - operator: str (optional, one of 'GT', 'GTE', 'LT', 'LTE', 'EQ', 'NEQ')
            - alert_time_utc: datetime (optional)
            - alert_time_name: str (optional)
        """
        if not configs:
            self._log("No configs provided. Nothing to add.")
            return self._current_config()
        for config in configs:
            if "alert_params" not in config or config["alert_params"] is None or (isinstance(config["alert_params"], float) and pd.isna(config["alert_params"])):
                config["alert_params"] = {}
        new_configs = pd.DataFrame(configs)
        if "alert_func" not in new_configs.columns:
            new_configs["alert_func"] = "THRESHOLD"
        if "threshold" not in new_configs.columns:
            raise ValueError("All configs must include a threshold value.")
        if "alert_params" not in new_configs.columns:
            new_configs["alert_params"] = ["{}" for _ in range(len(new_configs))]
        if "alert_time_utc" not in new_configs.columns:
            new_configs["alert_time_utc"] = None
        if "alert_time_name" not in new_configs.columns:
            new_configs["alert_time_name"] = None
        for _, row in new_configs.iterrows():
            alert_func_name = row["alert_func"]
            alert_params = row["alert_params"]
            if isinstance(alert_params, str):
                try:
                    alert_params = json.loads(alert_params)
                except Exception:
                    alert_params = {}
            self._validate_alert_func_params(alert_func_name, alert_params)
        if "alert_params" in new_configs.columns:
            new_configs["alert_params"] = new_configs["alert_params"].apply(lambda x: json.dumps(x) if isinstance(x, dict) else x)
        if "operator" in new_configs.columns:
            def _normalize_op_cell(x):
                try:
                    return _normalize_operator(x).value
                except Exception:
                    return OpEnum.GT.value
            new_configs["operator"] = new_configs["operator"].apply(_normalize_op_cell)
        else:
            new_configs["operator"] = OpEnum.GT.value

        def _row_desc_uid(row):
            desc = row["description"] if ("description" in row and pd.notna(row["description"])) else self.description
            return self.generate_uid(self.alert_type, row["product"], desc, row["alert_func"], row["alert_params"])

        new_configs["uid"] = new_configs.apply(_row_desc_uid, axis=1)
        new_configs["alert_type"] = self.alert_type
        new_configs["description"] = self.description
        config_schema = self.config_schema(new_configs)
        latest_config = self._update_config(config_schema)
        return latest_config

    def _check_config_params(self, func, params: dict) -> tp.Tuple[tp.List[str], tp.List[str]]:
        """
        Returns (missing, extra) parameter lists for a given function and params dict.
        Only parameters beyond 'data' and 'threshold' are checked.
        """
        if params is None or (isinstance(params, float) and pd.isna(params)):
            params = {}
        sig = inspect.signature(func)
        required_params = [k for k, v in sig.parameters.items() if k not in ("data", "threshold") and v.default == inspect.Parameter.empty]
        optional_params = [k for k, v in sig.parameters.items() if k not in ("data", "threshold") and v.default != inspect.Parameter.empty]
        missing = [p for p in required_params if p not in params]
        extra = [p for p in params if p not in required_params + optional_params]
        return missing, extra

    def _validate_alert_func_params(self, alert_func_name: str, alert_params: dict):
        """
        Validates that alert_params match the required parameters of the alert function.
        Raises ValueError if required parameters are missing or extra parameters are provided.
        Warns if optional parameters are not provided and will use defaults (shows default values).
        """
        alert_func_obj = AlertFuncs(alert_type=alert_func_name, description=self.description, function_name=alert_func_name)
        func = alert_func_obj.get_function()
        missing, extra = self._check_config_params(func, alert_params)
        if missing:
            raise ValueError(f"Missing required alert_params for function '{alert_func_name}': {missing}")
        if extra:
            raise ValueError(f"Extra alert_params for function '{alert_func_name}': {extra}")
        sig = inspect.signature(func)
        optional_params = [k for k, v in sig.parameters.items() if k not in ("data", "threshold") and v.default != inspect.Parameter.empty]
        missing_optional = [p for p in optional_params if p not in alert_params]
        if missing_optional:
            defaults = {p: sig.parameters[p].default for p in missing_optional}
            log.warning(f"Optional alert_params {missing_optional} not provided for function '{alert_func_name}' [photographed message clipped]")

    def _match_config_to_func(self, config):
        """
        Returns True if config's alert_params match the function signature.
        """
        alert_func_name = config.alert_func if "alert_func" in config else "THRESHOLD"
        alert_func_obj = AlertFuncs(alert_type=alert_func_name, description=self.description, function_name=alert_func_name)
        func = alert_func_obj.get_function()
        params = config.alert_params if hasattr(config, "alert_params") else {}
        missing, extra = self._check_config_params(func, params)
        return not missing and not extra

    def get_config(self, product: str = None) -> AlertsConfig:
        current_config = self._current_config()
        if product is not None:
            current_config = current_config[current_config["product"] == product]
        def safe_json_loads(x):
            if isinstance(x, dict):
                return x
            if isinstance(x, str) and x.strip().startswith("{"):
                try:
                    return json.loads(x)
                except Exception:
                    log.warning(f"Malformed alert_params JSON: {x}. Defaulting to empty dict.")
                    return {}
            if x is None:
                return {}
            return x
        if "alert_params" in current_config.columns:
            current_config["alert_params"] = current_config["alert_params"].apply(safe_json_loads)
        return current_config

    def _get_utc_now(self) -> dt.datetime:
        """
        Returns the current local time
        :return: dt.datetime
        """
        return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)

    def safe_json_loads(self, x):
        if isinstance(x, dict):
            return x
        if isinstance(x, str) and x.strip().startswith("{"):
            try:
                return json.loads(x)
            except Exception:
                log.warning(f"Malformed alert_params JSON: {x}. Defaulting to empty dict.")
                return {}
        if x is None:
            return {}
        return x

    def _is_alert_triggered(self, alert_triggered_df) -> bool:
        """
        Centralized check for whether an alert is triggered based on DataFrame output from alert functions.
        Returns True if any value in the 'alert' column is True/1.
        """
        return isinstance(alert_triggered_df, pd.DataFrame) and "alert" in alert_triggered_df.columns and alert_triggered_df["alert"].any()

    def _is_suppressed_uid(self, uid: str) -> bool:
        """
        Returns True if any prior alert with same UID has approval_state=APPROVED_SUPPRESS (2).
        If column doesn't exist, do not suppress.
        """
        try:
            df = self.history_schema.load_sql(self.db, form="db", nullable=False, transform=[f"uid = '{uid}'"])
            df = df.reset_index()
        except Exception:
            return False
        if df.empty or "approval_state" not in df.columns:
            return False
        current_date = self._get_utc_now().date()

        try:
            at_dates = pd.to_datetime(df["alert_time"], utc=True).dt.date
        except Exception:
            try:
                at_dates = pd.to_datetime(df["alert_time"]).dt.date
            except Exception:
                at_dates = None
        df_config = self.config_schema.load_sql(self.db, form="db", nullable=False, transform=[f"uid = '{uid}'"])
        if df_config.empty:
            return True
        uid_config_threshold = df_config.iloc[0].get("threshold", None)
        if uid_config_threshold is None:
            raise ValueError(f"Config for uid '{uid}' does not have a threshold. Cannot determine suppression.")
        df = df[df["threshold"] == uid_config_threshold]

        if at_dates is not None:
            approved_once_today = ((at_dates == current_date) & (df["approval_state"] == int(ApprovalState.APPROVED_ONCE))).any()
            if bool(approved_once_today):
                return True
        return bool((df["approval_state"] == int(ApprovalState.APPROVED_SUPPRESS)).any())

    def log_alert(self, product: str, value: float | pd.Series, alert_func: str = None, meta: tp.Optional[dict] = None):
        """
        Log one alert for a given product, or multiple alerts if value is a Series (non-timeseries)
        :param product: Product name
        :param value: Value(s) to check against threshold
        :param alert_func: (Optional) Only use configs with this alert_func
        :return: None
        """
        if isinstance(value, pd.Series):
            if isinstance(value.index, pd.DatetimeIndex):
                raise ValueError("Timeseries input detected. Use log_timeseries_alert(product, series, alert_func).")
            for v in value:
                self.log_alert(product, v, alert_func=alert_func)
            return
        self._log_alert_with_time(product, value, alert_func=alert_func, meta=meta)

    def _log_alert_with_time(self, product: str, value: float, alert_time: dt.datetime = None, alert_func: str = None, meta: tp.Optional[dict] = None):
        current_config = self.get_config(product)
        if current_config.description.unique().size > 1:
            log.warning(f"Multiple descriptions found for product '{product}'. Using the initialised description [photographed message clipped]")
            current_config = current_config[current_config["description"] == self.description]
        if alert_func is not None:
            current_config = current_config[current_config["alert_func"] == alert_func]
            if len(current_config) > 1:
                raise ValueError(f"Multiple configs found for product '{product}' and alert_func '{alert_func}' [photographed message clipped]")
            if current_config.empty:
                log.warning(f"No config found for product '{product}' and alert_func '{alert_func}'. Skipping.")
                return
        if current_config.empty:
            self._log(f"No config found for product {product}. Skipping.")
            return
        found_scalar = False
        for _, config in current_config.iterrows():
            alert_func_name = config.alert_func if "alert_func" in config else "THRESHOLD"
            try:
                alert_func_obj = AlertFuncs(alert_type=alert_func_name, description=self.description, function_name=alert_func_name)
                alert_func_obj_func = alert_func_obj.get_function()
            except KeyError:
                raise KeyError(f"Alert function '{alert_func_name}' referenced in config for product '{product}' [photographed message clipped]")
            if not self._match_config_to_func(config):
                log.warning(f"Config for product {product} and function {alert_func_name} does not match function signature [photographed message clipped]")
                continue
            found_scalar = True
            if not config.enabled:
                self._log(f"Alert for product {product} is disabled. Not logging alert.")
                continue
            if alert_time is None:
                alert_time = self._get_utc_now()
            description = self.description
            threshold = config.threshold if "threshold" in config else None
            base_alert_params = config.alert_params if "alert_params" in config else {}
            invoke_params = base_alert_params if isinstance(base_alert_params, dict) else ({} if base_alert_params is None else base_alert_params)
            if not isinstance(invoke_params, dict):
                try:
                    invoke_params = json.loads(str(invoke_params)) if str(invoke_params).strip().startswith("{") else {}
                except Exception:
                    invoke_params = {}
            if ("operator" not in invoke_params or invoke_params.get("operator") in (None, "")) and "operator" in config:
                try:
                    sig = inspect.signature(alert_func_obj_func)
                    if "operator" in sig.parameters:
                        op_val = config.operator
                        if pd.isna(op_val):
                            op_val = OpEnum.GT.value
                        try:
                            invoke_params = {**invoke_params, "operator": _normalize_operator(op_val).name}
                        except Exception:
                            invoke_params = {**invoke_params, "operator": OpEnum.GT.name}
                except Exception:
                    pass
            self._log(f"Calling alert function '{alert_func_name}' for product '{product}' with value={value} [photographed message clipped]")
            try:
                alert_triggered_df = alert_func_obj_func(value, threshold, **invoke_params)
            except Exception as e:
                log.error(f"Error running alert function {alert_func_name} for product {product}: {e}")
                continue
            should_log = self._is_alert_triggered(alert_triggered_df)
            if not should_log:
                continue
            if base_alert_params in (None, {}, "{}"):
                alert_params_str = "{}"
            elif isinstance(base_alert_params, dict):
                alert_params_str = json.dumps(base_alert_params)
            else:
                alert_params_str = str(base_alert_params)
            if "alert_params" in config:
                cap = config.alert_params
                if isinstance(cap, dict):
                    params_for_uid = json.dumps(cap)
                elif isinstance(cap, str) and cap.strip().startswith("{"):
                    params_for_uid = cap
                else:
                    params_for_uid = "{}"
            else:
                params_for_uid = "{}"
            uid = self.generate_uid(self.alert_type, product, description, config.alert_func, params_for_uid)
            if self._is_suppressed_uid(uid):
                self._log(f"Suppressed alert (lifetime) product={product} func={config.alert_func}")
            else:
                new_alert = {
                    "uid": uid, "alert_type": self.alert_type, "product": product,
                    "alert_value": value, "threshold": threshold, "alert_time": alert_time,
                    "description": description, "alert_func": config.alert_func,
                    "alert_params": alert_params_str,
                    "meta": json.dumps(meta) if meta is not None else "{}",
                    "alert_time_utc": getattr(config, "alert_time_utc", None),
                    "alert_time_name": getattr(config, "alert_time_name", None),
                }
                if self._history_has_column("approval_state"):
                    new_alert["approval_state"] = int(ApprovalState.PENDING)
                new_alert_df = self.history_schema(pd.DataFrame([new_alert], index=[0]), nullable=False)
                new_alert_df.dump_sql(self.db, form="db", mode="update_first")
                self._log(f"Logged alert for product {product} with value {value} using {config.alert_func}")
                self._log(
                    f"Alert logged details - Product: {product}, Value: {value}, "
                    f"Threshold: {threshold}, Alert Time: {alert_time}, Description: {description}, Alert F[photographed message clipped]"
                )
        if not found_scalar:
            log.error(f"No scalar-compatible configs found for product {product} and alert_type {self.alert_type}")

    def log_alerts_bulk(self, alert_data: tp.Dict[str, float] | pd.Series, alert_func: str = None, meta: tp.Optional[dict] = None):
        """
        Logs multiple alerts of the same alert_type
        :param alert_data: Dictionary of product names and their alert values, or Series with index=product
        :param alert_func: (Optional) Only use configs with this alert_func
        :return: None
        """
        if isinstance(alert_data, pd.Series):
            if isinstance(alert_data.index, pd.DatetimeIndex):
                raise ValueError("Bulk mode expects product names as index. For timeseries, use log_timeseries_alert [photographed message clipped]")
            alert_data = alert_data.to_dict()
        if not alert_data:
            self._log("No alert data provided. Nothing to log.")
            return
        current_config = self._current_config().copy()
        alerts_to_log = []
        for product, value in alert_data.items():
            product_rows = current_config[current_config["product"] == product]
            if product_rows.empty:
                self._log(f"No config found for product {product}. Skipping.")
                continue
            try:
                desc_count = product_rows["description"].nunique()
            except Exception:
                desc_count = 1
            if desc_count > 1:
                filtered = product_rows[product_rows["description"] == self.description]
                if filtered.empty:
                    log.warning(f"Multiple descriptions found for product '{product}' but none match initialised [photographed message clipped]")
                    config_rows = product_rows
                else:
                    config_rows = filtered
            else:
                config_rows = product_rows
            if alert_func is not None:
                config_rows = config_rows[config_rows["alert_func"] == alert_func]
                if len(config_rows) > 1:
                    raise ValueError(f"Multiple configs found for product '{product}' and alert_func '{alert_func}' [photographed message clipped]")
                if config_rows.empty:
                    log.warning(f"No config found for product '{product}' and alert_func '{alert_func}'. Skipping.")
                    continue
            if config_rows.empty:
                self._log(f"No config found for product {product}. Skipping.")
                continue
            for _, config in config_rows.iterrows():
                if not config.enabled:
                    self._log(f"Alert for product {product} is disabled. Skipping.")
                    continue
                alert_func_name = config.alert_func if "alert_func" in config else "THRESHOLD"
                description = config.description if "description" in config else self.description
                try:
                    alert_func_obj = AlertFuncs(alert_type=alert_func_name, description=description, function_name=alert_func_name)
                    alert_func_obj_func = alert_func_obj.get_function()
                except KeyError:
                    self._log(f"Alert function {alert_func_name} not found. Skipping {product}.")
                    continue
                if not self._match_config_to_func(config):
                    log.warning(f"Config for product {product} and function {alert_func_name} does not match function signature [photographed message clipped]")
                    continue
                threshold = config.threshold if "threshold" in config else None
                base_alert_params = config.alert_params if "alert_params" in config else {}
                invoke_params = base_alert_params if isinstance(base_alert_params, dict) else ({} if base_alert_params is None else base_alert_params)
                if not isinstance(invoke_params, dict):
                    try:
                        invoke_params = json.loads(str(invoke_params)) if str(invoke_params).strip().startswith("{") else {}
                    except Exception:
                        invoke_params = {}
                if ("operator" not in invoke_params or invoke_params.get("operator") in (None, "")) and "operator" in config:
                    try:
                        sig = inspect.signature(alert_func_obj_func)
                        if "operator" in sig.parameters:
                            op_val = config.operator
                            if pd.isna(op_val):
                                op_val = OpEnum.GT.value
                            try:
                                invoke_params = {**invoke_params, "operator": _normalize_operator(op_val).name}
                            except Exception:
                                invoke_params = {**invoke_params, "operator": OpEnum.GT.name}
                    except Exception:
                        pass
                self._log(f"Calling alert function '{alert_func_name}' for product '{product}' with value={value} [photographed message clipped]")
                try:
                    alert_triggered_df = alert_func_obj_func(value, threshold, **invoke_params)
                except Exception as e:
                    log.error(f"Error running alert function {alert_func_name} for product {product}: {e}")
                    continue
                should_log = self._is_alert_triggered(alert_triggered_df)
                if not should_log:
                    continue
                if base_alert_params in (None, {}, "{}"):
                    alert_params_str = "{}"
                elif isinstance(base_alert_params, dict):
                    alert_params_str = json.dumps(base_alert_params)
                else:
                    alert_params_str = str(base_alert_params)
                if "alert_params" in config:
                    cap = config.alert_params
                    if isinstance(cap, dict):
                        params_for_uid = json.dumps(cap)
                    elif isinstance(cap, str) and cap.strip().startswith("{"):
                        params_for_uid = cap
                    else:
                        params_for_uid = "{}"
                else:
                    params_for_uid = "{}"
                uid = self.generate_uid(self.alert_type, product, description, config.alert_func, params_for_uid)
                if self._is_suppressed_uid(uid):
                    self._log(f"Suppressed alert (lifetime) product={product} func={alert_func_name}")
                    continue
                alert_time = self._get_utc_now()
                new_alert = {
                    "uid": uid, "alert_type": self.alert_type, "product": product,
                    "alert_value": value, "threshold": threshold, "alert_time": alert_time,
                    "description": description, "alert_func": alert_func_name,
                    "alert_params": alert_params_str,
                    "meta": json.dumps(meta) if meta is not None else "{}",
                    "alert_time_utc": getattr(config, "alert_time_utc", None),
                    "alert_time_name": getattr(config, "alert_time_name", None),
                }
                if self._history_has_column("approval_state"):
                    new_alert["approval_state"] = int(ApprovalState.PENDING)
                alerts_to_log.append(new_alert)
        if alerts_to_log:
            new_alerts_df = self.history_schema(pd.DataFrame(alerts_to_log), nullable=False)
            if "alert_params" in new_alerts_df.columns:
                new_alerts_df["alert_params"] = new_alerts_df["alert_params"].apply(lambda x: json.dumps(x) if isinstance(x, dict) else x)
            new_alerts_df.dump_sql(self.db, form="db", mode="update_first")
            self._log(f"Logged {len(alerts_to_log)} alerts to history. For alert type {self.alert_type}")
        else:
            self._log("No alerts breached threshold. Nothing to log.")
        return

    def log_timeseries_alert(self, product: str, series: pd.Series, alert_func: str = None, meta: tp.Optional[dict] = None):
        """
        Log timeseries-based alerts for a single product using all matching configs for that product.
        :param product: Product name
        :param series: pandas Series (index = timestamps)
        """
        if not isinstance(series, pd.Series) or not isinstance(series.index, pd.DatetimeIndex):
            raise ValueError("Input to log_timeseries_alert must be a pandas Series with a DatetimeIndex.")
        configs = self.get_config(product)
        if configs.empty:
            raise ValueError(f"No config found for product {product} and alert_type {self.alert_type}")
        if alert_func is not None:
            configs = configs[configs["alert_func"] == alert_func]
            if len(configs) > 1:
                raise ValueError(f"Multiple configs found for product '{product}' and alert_func '{alert_func}' [photographed message clipped]")
            if configs.empty:
                log.warning(f"No config found for product '{product}' and alert_func '{alert_func}'. Skipping.")
                return
        for _, config in configs.iterrows():
            if not config.enabled:
                self._log(f"Alert for product {product} is disabled. Not logging alert.")
                continue
            description = self.description
            alert_func_name = config.alert_func if "alert_func" in config else "THRESHOLD"
            alert_func_obj = AlertFuncs(alert_type=alert_func_name, description=description, function_name=alert_func_name)
            func = alert_func_obj.get_function()
            threshold = config.threshold
            base_alert_params = config.alert_params
            if base_alert_params is None:
                base_alert_params = {}
            invoke_params = base_alert_params if isinstance(base_alert_params, dict) else ({} if base_alert_params is None else base_alert_params)
            if not isinstance(invoke_params, dict):
                try:
                    invoke_params = json.loads(str(invoke_params)) if str(invoke_params).strip().startswith("{") else {}
                except Exception:
                    invoke_params = {}
            if ("operator" not in invoke_params or invoke_params.get("operator") in (None, "")) and "operator" in config:
                try:
                    sig = inspect.signature(func)
                    if "operator" in sig.parameters:
                        op_val = config.operator
                        if pd.isna(op_val):
                            op_val = OpEnum.GT.value
                        try:
                            invoke_params = {**invoke_params, "operator": _normalize_operator(op_val).name}
                        except Exception:
                            invoke_params = {**invoke_params, "operator": OpEnum.GT.name}
                except Exception:
                    pass
            missing, extra = self._check_config_params(func, invoke_params)
            if missing or extra:
                log.warning(f"Config for product {product} and function {alert_func_name} does not match function signature [photographed message clipped]")
                continue
            self._log(f"Calling alert function '{alert_func_name}' for product '{product}' (timeseries) with [photographed message clipped]")
            result_df = func(series, threshold, **invoke_params)
            for idx, row in result_df.iterrows():
                if "alert" in row and row["alert"]:
                    base_alert_params = config.alert_params
                    if base_alert_params is None or base_alert_params == {}:
                        alert_params_str = "{}"
                    elif isinstance(base_alert_params, dict):
                        alert_params_str = json.dumps(base_alert_params)
                    else:
                        alert_params_str = str(base_alert_params)
                    if "alert_params" in config:
                        cap = config.alert_params
                        if isinstance(cap, dict):
                            params_for_uid = json.dumps(cap)
                        elif isinstance(cap, str) and cap.strip().startswith("{"):
                            params_for_uid = cap
                        else:
                            params_for_uid = "{}"
                    else:
                        params_for_uid = "{}"
                    uid = self.generate_uid(self.alert_type, product, description, config.alert_func, params_for_uid)
                    if self._is_suppressed_uid(uid):
                        self._log(f"Suppressed alert (lifetime) product={product} func={config.alert_func}")
                        continue
                    new_alert = {
                        "uid": uid, "alert_type": self.alert_type, "product": product,
                        "alert_value": row["value"], "threshold": threshold, "alert_time": idx,
                        "description": description, "alert_func": config.alert_func,
                        "alert_params": alert_params_str,
                        "meta": json.dumps(meta) if meta is not None else "{}",
                        "alert_time_utc": getattr(config, "alert_time_utc", None),
                        "alert_time_name": getattr(config, "alert_time_name", None),
                    }
                    if self._history_has_column("approval_state"):
                        new_alert["approval_state"] = int(ApprovalState.PENDING)
                    new_alert_df = self.history_schema(pd.DataFrame([new_alert], index=[0]), nullable=False)
                    new_alert_df.dump_sql(self.db, form="db", mode="update_first")
            self._log(f"Timeseries alerts logged for product {product} using {alert_func_name} and params [photographed message clipped]")

    def get_alert_history(self, product: str = None, limit: int = 100, alert_type: str = None,
                          latest: bool = ..., include_approved: bool = ..., is_overview: bool = ...):
        """
        Gets the full alert history order by time newest to oldest for the given product or all products if [clipped]
        for the current alert_type
        :param product: Product name to filter alerts
        :param limit: Maximum number of alerts to return
        :param optional alert_type: Filter by specific alert type, if None uses the current alert_type
        :param latest: If True, returns only the latest alerts
        return: DataFrame of alerts
        """
        if latest is ... or include_approved is ... or is_overview is ...:
            raise NotImplementedError("Photographed alerts.py get_alert_history defaults unavailable")
        alert_type_filter = alert_type if alert_type is not None else self.alert_type
        product_filter = product if product is not None else ""
        transform = [f"alert_type = '{alert_type_filter}'"]
        if product is not None:
            transform.append(f"product = '{product_filter}'")
        latest_history = self.history_schema.load_sql(self.db, form="db" if not is_overview else "overview", nullable=False, transform=transform)
        if product is not None:
            latest_history = latest_history[latest_history["product"] == product]
        if "approval_state" in latest_history.columns and not include_approved:
            latest_history = latest_history[(latest_history["approval_state"].isna()) | (latest_history["approval_state"] == int(ApprovalState.PENDING))]
        latest_history = latest_history.sort_values(by="alert_time", ascending=False)
        latest_history = latest_history.reset_index().drop(columns=["id"])
        if "alert_params" in latest_history.columns:
            latest_history["alert_params"] = latest_history["alert_params"].apply(self.safe_json_loads)
        if latest:
            return latest_history.head(limit) if limit is not None else latest_history
        historical_alerts = self.history_schema.load_sql(
            self.db, form="db", nullable=False, table_override="alerts.live_history", transform=transform,
        )
        if "approval_state" in historical_alerts.columns and not include_approved:
            historical_alerts = historical_alerts[(historical_alerts["approval_state"].isna()) | (historical_alerts["approval_state"] == int(ApprovalState.PENDING))]
        historical_alerts = historical_alerts.sort_values(by="alert_time", ascending=False)
        historical_alerts = historical_alerts.reset_index().drop(columns=["id"])
        if "alert_params" in historical_alerts.columns:
            historical_alerts["alert_params"] = historical_alerts["alert_params"].apply(self.safe_json_loads)
        if product is not None:
            historical_alerts = historical_alerts[historical_alerts["product"] == product]
        all_alerts = pd.concat([latest_history, historical_alerts])
        all_alerts = all_alerts.sort_values(by=["product", "alert_time"], ascending=False).head(limit) if limit is not None else all_alerts
        all_alerts = all_alerts.drop_duplicates(subset=["alert_type", "product", "alert_time"])
        return all_alerts

    def get_latest_alerts(self, product: str = None, limit: int = 100, include_approved: bool = False) -> AlertsHistory:
        """
        Gets the latest alerts for the given product or all products if no product is specified
        :param product: Product name to filter alerts Optional, if None uses all products
        :param limit: Maximum number of alerts to return Optional, if None returns all alerts
        return: DataFrame of latest alerts
        """
        return self.get_alert_history(product=product, limit=limit, alert_type=self.alert_type, latest=True, include_approved=include_approved)

    def get_latest_alerts_for_day(self, run_date: tp.Optional[dt.datetime] = None, product: str = None,
                                  limit: int = ..., include_approved: bool = ...):
        """
        Gets the latest alerts for the given product or all products if no product is specified for a speci[clipped]
        :param run_date: Date to filter alerts Optional, if None uses the current date
        :param product: Product name to filter alerts Optional, if None uses all products
        :param limit: Maximum number of alerts to return, if None returns all alerts for the day
        return: DataFrame of latest alerts for the day
        """
        if limit is ... or include_approved is ...:
            raise NotImplementedError("Photographed alerts.py get_latest_alerts_for_day defaults unavailable")
        if run_date is None:
            run_date = self._get_utc_now()
        elif isinstance(run_date, pd.Timestamp):
            run_date = run_date.to_pydatetime()
        elif isinstance(run_date, dt.datetime):
            if run_date.tzinfo is not None:
                run_date = run_date.astimezone(dt.timezone.utc).replace(tzinfo=None)
        if isinstance(run_date, dt.datetime):
            start_of_day = run_date.replace(hour=0, minute=0, second=0, microsecond=0)
            end_of_day = run_date.replace(hour=23, minute=59, second=59, microsecond=999999)
            alert_history = self.get_alert_history(product=product, limit=limit, include_approved=include_approved)
            alert_times = pd.to_datetime(alert_history["alert_time"], errors="coerce")
            daily_alerts = alert_history[(alert_times >= start_of_day) & (alert_times <= end_of_day)]
            daily_alerts = daily_alerts.sort_values(by=["product", "alert_time"], ascending=False)
            if limit is not None:
                daily_alerts = daily_alerts.head(limit)
            return daily_alerts.drop_duplicates(subset=["alert_type", "product", "alert_time"])
        else:
            raise ValueError("run_date must be a datetime or pandas Timestamp")

    def approve_alerts(
        self, uids: tp.Optional[tp.Sequence[str]] = None, product: tp.Optional[str] = None,
        since: tp.Optional[dt.datetime] = None, until: tp.Optional[dt.datetime] = None,
        alert_func: tp.Optional[str] = None, mode: str = "once",  # "once" or "suppress"
    ) -> pd.DataFrame:
        """
        Approve alerts. mode='once' (1) hides row; mode='suppress' (2) also suppresses future logs for same [clipped]
        :param uids: List of alert UIDs to approve. If None, approves all alerts matching other filters.
        :param product: (Optional) Product name to filter alerts
        :param since: (Optional) Start datetime to filter alerts
        :param until: (Optional) End datetime to filter alerts
        :param alert_func: (Optional) Alert function name to filter alerts
        :param mode: "once" to approve once (1), "suppress" to approve and suppress future (2)
        :return: DataFrame of approved alerts
        """
        filters = [f"alert_type = '{self.alert_type}'"] + [f"description = '{self.description}'"]
        if uids:
            uid_list = ",".join(f"'{u}'" for u in uids)
            filters.append(f"uid in ({uid_list})")
        if product:
            filters.append(f"product = '{product}'")
        if alert_func:
            filters.append(f"alert_func = '{alert_func}'")
        if since:
            filters.append(f"alert_time >= '{since}'")
        if until:
            filters.append(f"alert_time <= '{until}'")
        df = self.history_schema.load_sql(self.db, form="db", nullable=False, transform=filters)
        if df.empty:
            self._log("No alerts matched for approval.")
            return 0
        df = df.reset_index().drop(columns=["id"]).set_index("uid")
        if "approval_state" not in df.columns:
            raise ValueError("Column 'approval_state' not found in alerts history schema. Add it to the DB/[photographed message clipped]")
        target = int(ApprovalState.APPROVED_ONCE) if mode == "once" else int(ApprovalState.APPROVED_SUPPRESS)
        if not uids:
            uids = df["uid"].tolist() if "uid" in df.columns else list(df.index)
        approved_count = 0
        approved_alerts = pd.DataFrame()
        for uid in uids:
            if self._is_suppressed_uid(uid):
                continue
            if "uid" in df.columns:
                mask = df["uid"] == uid
            else:
                mask = df.index == uid
            df.loc[mask, "approval_state"] = target
            df.loc[mask, "approval_time"] = self._get_utc_now()
            df.loc[mask, "approved_by"] = current_user
            approved_count += 1
            df_ = df.loc[mask]
            approved_alerts = pd.concat([approved_alerts, df_])
        if "uid" not in df.columns and df.index.name == "uid":
            df = df.reset_index()
        self.history_schema(df, nullable=False).dump_sql(self.db, form="db", mode="update_first")
        self._log(f"Approved {approved_count} alerts with mode={mode}.")
        return approved_alerts

    def unapprove_alerts(self, uids: tp.Sequence[str]) -> int:
        """
        Revert approval for specific alerts by uid (sets approval_state back to 0).
        """
        if not uids:
            return 0
        uid_list = ",".join(f"'{u}'" for u in uids)
        raise NotImplementedError("Photographed alerts.py unapprove_alerts query filters unavailable")
        if df.empty:
            return 0
        if "approval_state" not in df.columns:
            raise ValueError("Column 'approval_state' not found in alerts history schema. Add it to the DB/[photographed message clipped]")
        df["approval_state"] = int(ApprovalState.PENDING)
        df["approval_time"] = None
        df["approved_by"] = None
        self.history_schema(df, nullable=False).dump_sql(self.db, form="db", mode="update_first")
        return len(df)


if __name__ == "__main__":
    import pandas as pd
    import datetime as dt

    print("--- Initializing AlertsAPI for 'Price Alert' ---")


















    print("\n--- Test ui configs can run---")
    ui_api = AlertsAPI(alert_type="Alert US Gas", description="TEST", env="dev")

    ui_api.log_alert(product="NG1 Comdty", value=10.0)
