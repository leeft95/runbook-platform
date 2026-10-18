"""Offline aggregate checks; no report imports or data-service calls."""
import ast
from functools import partial
from pathlib import Path
from types import SimpleNamespace
import unittest

SOURCE = Path(__file__).resolve().parents[1] / 'cot_cme.py'


def aggregate_function(name, values):
    calls = []
    drops = []
    results = []

    class Table:
        def inc(self, **kwargs):
            self.selected = kwargs['_id']
            return self

        def drop(self):
            drops.append(self.selected)

    def get_cell(db, active, item):
        return SimpleNamespace(active=active, item=item, value=values.get(active, 0), _id=(active, item))

    def sumproduct(dfs, w, method=None):
        result = sum(cell.value * weight for cell, weight in zip(dfs, w))
        return result / sum(w) if method == 'mean' else result

    def periodic_cell(**kwargs):
        calls.append(kwargs)

        def go():
            args = {key: kwargs[key] for key in ('dfs', 'w', 'method') if key in kwargs}
            results.append(kwargs['function'](**args))

        return SimpleNamespace(go=go)

    scope = {
        'partial': partial, 'mongo_table': lambda **kwargs: Table(), 'url': 'offline', 'cal_period': '3n',
        'pyg': SimpleNamespace(get_cell=get_cell), 'periodic_cell': periodic_cell,
        'ts': SimpleNamespace(sumproduct=sumproduct, sum_dfs=lambda dfs: sum(c.value for c in dfs)),
    }
    tree = ast.parse(SOURCE.read_text())
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(SOURCE), 'exec'), scope)
    scope[name]()
    return calls, drops, results


class RecoveredPositioningLogicTests(unittest.TestCase):
    def test_oil_aggregates_preserve_gasoil_conversion(self):
        values = {'COA Comdty': 10, 'ENA Comdty': 20, 'CLA Comdty': 30, 'NYMEX Brent': 40,
                  'QSA Comdty': 50, 'XBA Comdty': 60, 'HOA Comdty': 70}
        product, _, product_results = aggregate_function('create_total_product', values)
        oil, _, oil_results = aggregate_function('create_total_oil', values)
        self.assertEqual(len(product), 10)
        self.assertEqual(len(oil), 10)
        for result in product_results:
            self.assertAlmostEqual(result, 172.65)
        for result in oil_results:
            self.assertAlmostEqual(result, 272.65)

    def test_natgas_options_are_added_only_for_combined_managed_money(self):
        values = {'NGA Comdty': 100, 'NG NYMEX Swap': 40, 'NG NYMEX Penultimate': 80,
                  'NG ICE Henry Hub': 120, 'GKA Options': 10}
        calls, drops, results = aggregate_function('create_total_natgas', values)
        by_item = dict(zip((c['item'] for c in calls), results))
        self.assertEqual(by_item['MMLF'], 160)
        self.assertEqual(by_item['MMSF'], 160)
        self.assertEqual(by_item['OIFO'], 160)
        self.assertEqual(by_item['MMLFO'], 170)
        self.assertEqual(by_item['MMSFO'], 170)
        self.assertEqual({c['active'] for c in calls}, {'NG CME+ICE'})
        self.assertEqual({active for active, _ in drops}, {'NatGas'})

    def test_oil_vwap_uses_only_two_crude_markets_and_weighted_product_mean(self):
        values = {'COA Comdty': 80, 'CLA Comdty': 60, 'ENA Comdty': 999, 'NYMEX Brent': 999,
                  'QSA Comdty': 100, 'XBA Comdty': 110, 'HOA Comdty': 120}
        calls, _, results = aggregate_function('vwap_oil', values)
        self.assertEqual([c['active'] for c in calls], ['Crude', 'Product'])
        self.assertEqual(results[0], 70)
        self.assertAlmostEqual(results[1], (85.3 + 110 + 120) / 2.853)


if __name__ == '__main__':
    unittest.main()
