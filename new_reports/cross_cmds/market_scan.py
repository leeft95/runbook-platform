import range_vol_am
from ecm.cmds.config import oil_group, gas_group
send_to = list(set(oil_group + gas_group))


def update():
    range_vol_am.market_scan()
    range_vol_am.send_sharpe_ratio_rank()


if __name__ == "__main__":
    update()
