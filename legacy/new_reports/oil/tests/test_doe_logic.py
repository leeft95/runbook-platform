"""Check photographed DOE sizing arithmetic without importing the report."""
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock


class ClosingPrice(float):
    def diff(self):
        return 4.0

    def shift(self, periods):
        assert periods == 1
        return 80.0


class ObservedVolatility(float):
    def shift(self, periods):
        assert periods == 1
        return 20.0


class DoeSizingTests(unittest.TestCase):
    def test_usd_position_uses_selected_volatility_lag_and_contract_value(self):
        source = Path(__file__).resolve().parents[1] / 'doe_stocks_bbg.py'
        tree = ast.parse(source.read_text(), filename=str(source))
        function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'cal_size')
        realized_volatility = Mock(return_value=ObservedVolatility(10.0))
        scope = {'talib': SimpleNamespace(realizedvol=realized_volatility)}
        exec(compile(ast.Module(body=[function], type_ignores=[]), str(source), 'exec'), scope)
        size = scope['cal_size']
        quote = ClosingPrice(100.0)
        self.assertEqual(size(quote, shift=0), 20.0)
        self.assertEqual(size(quote), 10.0)
        self.assertEqual(size(quote, size_per_trade=6000000, target_vol=5, vpp=500), 30.0)
        self.assertEqual(realized_volatility.call_count, 3)
        for observed in realized_volatility.call_args_list:
            self.assertEqual(observed.args, (5.0,))
            self.assertEqual(observed.kwargs, {'rollwindow': 30, 'annualize': 260})


if __name__ == '__main__':
    unittest.main()
