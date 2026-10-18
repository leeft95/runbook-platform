import os
import sys

if sys.platform.startswith("win"):
    os.environ["GRPC_DEFAULT_SSL_ROOTS_FILE_PATH"] = r"C:\local\certs\root.crt"
    os.environ["REQUESTS_CA_BUNDLE"] = r"C:\local\certs\root.crt"
    os.environ["SSL_CERT_FILE"] = r"C:\local\certs\root.crt"

import datetime as dt
from ecm.cmds.core.cdr import today
from kpler.sdk import Platform, TradesStatus
from kpler.sdk.configuration import Configuration
from kpler.sdk.resources.trades import Trades
from kpler.sdk.resources.flows import Flows
from kpler.sdk.resources.vessels import Vessels
from kpler.sdk.resources.trades_snapshot import TradesSnapshot


kpler_logins = {
    "gas": {"username": os.environ["KPLER_GAS_USERNAME"], "password": os.environ["KPLER_GAS_PASSWORD"]},
    "oil": {"username": os.environ["KPLER_OIL_USERNAME"], "password": os.environ["KPLER_OIL_PASSWORD"]},
}


def get_all_platforms():
    """
    Get all available platforms
    """
    return [platform for platform in Platform]


class KplerClient:
    def __init__(self, platform: Platform, mode: str):
        try:
            user_pass_config = kpler_logins[mode]
        except KeyError:
            raise ValueError(
                f"Invalid mode: {mode}. Available modes are: {list(kpler_logins.keys())}"
            )
        self.config = Configuration(
            platform, user_pass_config["username"], user_pass_config["password"]
        )
        self.platform = platform
        self.trades = Trades(self.config)
        self.flows = Flows(self.config)
        self.vessels = Vessels(self.config)

    def get_flows(self, **kwargs):
        return self.flows.get(**kwargs)

    def get_vessels(self, **kwargs):
        return self.vessels.get(**kwargs)

    def get_trades(self, start_date: dt.datetime = None, **kwargs):
        """
        Get trades
        """
        if start_date is None:
            start_date = today()
        return self.trades.get(start_date=start_date, **kwargs)

    def get_trades_snapshot(
        self, start_date: dt.datetime = None, status: TradesStatus = None, **kwargs
    ):
        """
        Get trades snapshot
        """
        snapshot = TradesSnapshot(self.config).get(
            start_date=start_date, trade_status=status, **kwargs
        )
        snapshot_date = snapshot.headers.get("lastAvailableDate", None)
        snapshot["last_update"] = snapshot_date
        return snapshot

    def get_snapshot_columns(self):
        """
        Get snapshot columns
        """
        return TradesSnapshot(self.config).get_columns()


if __name__ == "__main__":
    client = KplerClient(Platform.LNG, "gas")
    date = dt.datetime(2018, 1, 1)
    snapshot = client.get_trades_snapshot()
    column_definitions = client.get_snapshot_columns()
    print(snapshot)
    print(column_definitions)
    print("break")
