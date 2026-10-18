"""Offline checks of extracted oil helpers; report imports are never executed."""
import ast
from pathlib import Path
import statistics
from types import SimpleNamespace
import unittest

SOURCE = Path(__file__).resolve().parents[1]


def recovered_function(module, name, namespace):
    path = SOURCE / module
    tree = ast.parse(path.read_text(), filename=str(path))
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
    scope = dict(namespace)
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), 'exec'), scope)
    return scope[name]


class Sample(list):
    """Numeric sample with the Series operations used by these two helpers."""
    @property
    def empty(self):
        return not self

    @property
    def iloc(self):
        return self

    @property
    def values(self):
        return list(self)

    def copy(self):
        return Sample(self)

    def __getitem__(self, key):
        result = super().__getitem__(key)
        return Sample(result) if isinstance(key, slice) else result

    def mean(self):
        return statistics.mean(self)

    def std(self):
        return statistics.stdev(self)


class OilLogicTests(unittest.TestCase):
    def test_window_zscore_uses_prior_observations_only(self):
        windows = []

        def ewma(sample, window):
            windows.append(window)
            return window * 10

        get_stats = recovered_function('window_pattern.py', 'get_stats', {
            'pd': SimpleNamespace(DataFrame=lambda columns, index: dict.fromkeys(columns)),
            'get_ewma': ewma,
        })
        for latest in (100, -100):
            sample = Sample([1, 2, 3, 4, latest])
            result = get_stats(sample, 'TEST', True)
            self.assertAlmostEqual(result['_zscore'], (latest - 2.5) / statistics.stdev([1, 2, 3, 4]))
            self.assertEqual([result['D-2'], result['D-1'], result['D']], [3, 4, latest])
            self.assertEqual((result['_thr1'], result['_thr2']), (1.5, -1.5))
            self.assertEqual((result['13D (EWMA)'], result['5D (EWMA)']), (130, 50))
            self.assertEqual(sample, [1, 2, 3, 4, latest])
        self.assertEqual(windows, [13, 5, 13, 5])

    def test_ewma_receives_latest_window_in_reverse_order(self):
        received = []

        def exp_avg(values):
            received.append(values)
            return 123

        get_ewma = recovered_function('window_pattern.py', 'get_ewma', {
            'np': SimpleNamespace(array=list),
            'talib': SimpleNamespace(exp_avg=exp_avg),
        })
        sample = Sample(range(1, 21))
        self.assertEqual(get_ewma(sample, window=5), 123)
        self.assertEqual(received, [[20, 19, 18, 17, 16]])
        self.assertEqual(sample, list(range(1, 21)))


if __name__ == '__main__':
    unittest.main()
