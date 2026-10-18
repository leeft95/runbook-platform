"""Offline checks of selected photographed logic; package imports never execute."""
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest


SOURCE = Path(__file__).resolve().parents[1] / "src/ecm/cmds/quant"


def recovered_function(module, name, *, owner=None, namespace=None):
    tree = ast.parse((SOURCE / module).read_text())
    body = tree.body
    if owner is not None:
        body = next(node for node in body if isinstance(node, ast.ClassDef) and node.name == owner).body
    node = next(node for node in body if isinstance(node, ast.FunctionDef) and node.name == name)
    scope = dict(namespace or {})
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(SOURCE / module), "exec"), scope)
    return scope[name]


class RecoveredLogicTests(unittest.TestCase):
    def test_explicit_stop_long_and_short(self):
        cal_stop = recovered_function("custom.py", "cal_stop", owner="Trade", namespace={"np": SimpleNamespace(abs=abs)})
        trade = SimpleNamespace(ref_date=None, entry_price=100, direction=1)
        self.assertEqual(cal_stop(trade, ref_price=95, reward_to_risk=3), (95, 115, 105))
        self.assertEqual(cal_stop(trade, ref_price=95, reward_to_risk=3, take_profit=112), (95, 112, 105))
        trade.direction = -1
        self.assertEqual(cal_stop(trade, ref_price=105, reward_to_risk=3), (105, 85, 95))
        self.assertEqual(cal_stop(trade, ref_price=105, take_profit=88), (105, 88, 95))

    def test_risk_size_uses_absolute_stop_distance(self):
        cal_size = recovered_function("custom.py", "cal_size", owner="Trade", namespace={"np": SimpleNamespace(abs=abs)})
        trade = SimpleNamespace(entry_price=100, stop_lvl=95, fut_val_pt=1000, risk=25000)
        self.assertEqual(cal_size(trade), 5)
        trade.stop_lvl = 105
        self.assertEqual(cal_size(trade), 5)

    def test_order_direction_and_format(self):
        create_order = recovered_function("custom.py", "create_order", owner="Trade")
        trade = SimpleNamespace(direction=1, num_contracts=5, contract="CLZ5 Comdty", stop_lvl=95, tp_lvl=115)
        self.assertEqual(create_order(trade), "Please buy 5 CLZ5 Comdty TWAP in next 10 mins. Stop: 95.00, target: 115.00, OCO, GTC")
        trade.direction = -1
        self.assertEqual(create_order(trade, "VWAP", 20), "Please sell 5 CLZ5 Comdty VWAP in next 20 mins. Stop: 95.00, target: 115.00, OCO, GTC")

    def test_fixed_contracts_need_no_bloomberg_lookup(self):
        static = {"LMCADS03 Comdty", "LMAHDS03 Comdty", "LMZSDS03 Comdty", "LMNIDS03 Comdty"}
        get_ticker = recovered_function("intraday_vol.py", "get_ticker", namespace={"NO_ROLL_TICKERS": static})
        for ticker in static:
            self.assertEqual(get_ticker(ticker), (ticker, None, None))

    def test_photographed_generic_month_overrides(self):
        tk = SimpleNamespace(decompose_ticker=lambda ticker: {"active": ticker})
        get_gen_month = recovered_function("intraday_vol.py", "get_gen_month", namespace={"tk": tk})
        for ticker, expected in {"SMA Comdty": "FHKNZ", "BOA Comdty": "FHKNZ", "S A Comdty": "FHKNX", "GCA Comdty": "GJMQZ", "SIA Comdty": "HKNUZ"}.items():
            self.assertEqual(get_gen_month(ticker), expected)


if __name__ == "__main__":
    unittest.main()
