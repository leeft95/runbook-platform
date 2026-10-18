"""Offline checks of photographed functions, with all service access replaced."""
import ast
import math
import statistics
import re
from pathlib import Path
from types import SimpleNamespace
import unittest

SOURCE = Path(__file__).resolve().parents[1]


def recovered_function(module, name, namespace):
    tree = ast.parse((SOURCE / module).read_text())
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
    scope = dict(namespace)
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(SOURCE / module), 'exec'), scope)
    return scope[name]


class Price:
    def __init__(self, value):
        self.value = value
        self.loc = self

    def __sub__(self, other):
        return Price(self.value - other.value)

    def __truediv__(self, other):
        return Price(self.value / other.value)

    def __getitem__(self, key):
        return self


class IntradaySample:
    """Small timestamped sample used without importing the report's dependencies."""
    def __init__(self, values, index=None):
        self.values = values
        self.index = list(range(len(values))) if index is None else index
        self.loc = self

    def __len__(self):
        return len(self.values)

    def __getitem__(self, bounds):
        selected = [(i, value) for i, value in zip(self.index, self.values) if bounds.start <= i <= bounds.stop]
        return IntradaySample([value for _, value in selected], [i for i, _ in selected])

    def __mul__(self, weight):
        return IntradaySample([value * weight for value in self.values], self.index)

    def drop(self, index):
        return IntradaySample([value for i, value in zip(self.index, self.values) if i != index],
                              [i for i in self.index if i != index])

    def mean(self):
        return statistics.mean(self.values)

    def std(self):
        return statistics.stdev(self.values)


class RecoveredReportLogicTests(unittest.TestCase):
    def test_synthetic_spread_switches_each_leg_at_2019_cutoff(self):
        calls = []

        def get_data(table, **kwargs):
            calls.append(kwargs)
            return Price(110 if len(calls) == 1 else 100)

        spread = recovered_function('oil_price_range.py', 'synthetic_spread', {'pyg': SimpleNamespace(get_data=get_data)})
        result = spread('DATA Comdty', 2019, 'H', far_y=2019, far_m='J', pct=True)
        self.assertAlmostEqual(result.value, 0.1)
        self.assertEqual(result.columns, ['PX_LAST'])
        self.assertEqual([c['active'] for c in calls], ['TOA Comdty', 'DATA Comdty'])
        calls.clear()
        self.assertEqual(spread('CLA Comdty', 2024, 'F', far_y=2024, far_m='G').value, 10)
        self.assertEqual([c['active'] for c in calls], ['CLA Comdty', 'CLA Comdty'])

    def test_open_interest_raw_and_zscore_formats_keep_distinct_inputs(self):
        format_table = recovered_function('open_interest.py', 'format_table_signal', {'table': SimpleNamespace(html_format=lambda **kwargs: kwargs)})
        raw = format_table(object(), full=True)
        standardized = format_table(object(), z=True, gas_only=True)
        self.assertIn('1d chg zscore', raw['hide_cols'])
        self.assertIn('1d chg', standardized['hide_cols'])
        self.assertEqual(raw['format_column']['1d chg']['highlight_z'], ['1d chg', '1d_mean', '1d_std'])
        self.assertEqual(standardized['format_column']['1d chg zscore']['highlight_z'], ['1d chg zscore', '1d chg', '1d_mean', '1d_std'])
        self.assertEqual(standardized['format_row'], {0: {'bold': True}})
        self.assertEqual(raw['format_column']['1y percentile']['highlight'], ['1y percentile', 'thr1', 'thr2'])

    def test_options_ticker_year_and_carbon_month_conversion(self):
        convert = recovered_function('options_volume.py', 'convert_ticker', {'re': re})
        self.assertEqual(convert('GKZ6 Comdty'), 'NGZ26 Comdty')
        self.assertEqual(convert('MZBM6 Comdty'), 'MZBZ26 Comdty')
        self.assertEqual(convert('MOH26 Comdty'), 'MOZ26 Comdty')
        self.assertEqual(convert('CLZ26 Comdty'), 'CLZ26 Comdty')

    def test_gas_sharpe_drops_first_observation_and_preserves_spread_weights(self):
        sharpe = recovered_function('range_vol_gas.py', 'sr_3d_cob',
                                     {'np': SimpleNamespace(sqrt=math.sqrt, nan=math.nan)})
        sample = IntradaySample([999] + list(range(1, 11)))
        expected = statistics.mean(range(1, 11)) / statistics.stdev(range(1, 11)) * math.sqrt(10)
        self.assertAlmostEqual(sharpe(sample, 0, 10, 'EU_GAS', 'FLAT'), expected)
        self.assertAlmostEqual(sharpe(sample, 0, 10, 'EU_GAS', 'SPRD'), expected * 0.3)
        self.assertAlmostEqual(sharpe(sample, 0, 10, 'FI', 'SPRD'), -expected)
        self.assertTrue(math.isnan(sharpe(sample, 1, 10, 'EU_GAS', 'FLAT')))


if __name__ == '__main__':
    unittest.main()
