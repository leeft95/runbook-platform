# Processing Utils Testing Guide

## Overview
This guide explains how to validate that the refactored `process_ticker_data()` function produces identical outputs to the original `process_data()` function.

## Test Methods

### Method 1: Standalone Test Script (Recommended)
Run the comprehensive test script that compares all 15 CSV outputs:

```cmd
cd s:\Michel Kikano\CODE\autoreports\reports\cross_cmds
python test_processing_utils.py
```

**What it does:**
- Generates baseline outputs using original `process_data()`
- Generates test outputs using new `process_ticker_data()`
- Compares all 15 CSV files for differences
- Reports detailed comparison results

**Output locations:**
- Baseline: `{folder_path}\test_baseline\baseline_*.csv`
- Test: `{folder_path}\test_new\test_*.csv`

**Expected result:**
```
✅ ✅ ✅ ALL TESTS PASSED! ✅ ✅ ✅
The refactored code produces IDENTICAL outputs to the original!
```

### Method 2: Inline Quick Test
Run quick comparison within market_scan:

```python
from range_vol_am_dev import market_scan

# Run with test mode enabled
market_scan(run_test=True)
```

**What it does:**
- Runs both versions side-by-side
- Quick comparison of main DataFrame
- Shows first differences if any found
- Continues with normal execution

### Method 3: Manual Comparison
For manual validation:

```python
import pandas as pd
from range_vol_am_dev import get_tickers, get_basic_info, process_data
from market_scan_helpers.processing_utils import process_ticker_data

# Step 1: Generate baseline
ticker_dict = get_tickers()
baseline = get_basic_info(ticker_dict, use_bbg=False)
baseline[0].to_csv("baseline_trend_signal.csv")

# Step 2: Monkey-patch and generate test
import range_vol_am_dev as main
original = main.process_data
main.process_data = process_ticker_data
test = get_basic_info(ticker_dict, use_bbg=False)
test[0].to_csv("test_trend_signal.csv")
main.process_data = original

# Step 3: Compare
baseline_df = pd.read_csv("baseline_trend_signal.csv", index_col=0)
test_df = pd.read_csv("test_trend_signal.csv", index_col=0)
diff = baseline_df.compare(test_df)
print("Differences:", len(diff) if not diff.empty else "None")
```

## Files Being Compared

The test compares these 15 output files:

1. `trend_signal.csv` - Main signals DataFrame
2. `trend_alert_all.csv` - All historical alerts
3. `trend_alert_oil.csv` - Oil alerts
4. `trend_alert_ng.csv` - Natural gas alerts
5. `trend_alert_macro.csv` - Macro alerts
6. `trend_alert_all_today.csv` - All today alerts
7. `trend_alert_oil_today.csv` - Oil today alerts
8. `trend_alert_ng_today.csv` - NG today alerts
9. `trend_alert_macro_today.csv` - Macro today alerts
10. `weekly_high.csv` - Weekly high alerts
11. `weekly_low.csv` - Weekly low alerts
12. `intraday_cum_vol.csv` - Intraday volume alerts
13. `bm_alert_am.csv` - Base metal AM alerts
14. `bm_alert_pm.csv` - Base metal PM alerts
15. `sharpe_ratio.csv` - Sharpe ratio tracking

## Troubleshooting

### If tests fail:

1. **Check the error type:**
   - Shape mismatch: Different number of rows/columns
   - Value differences: Calculation discrepancies
   - Type differences: Data type mismatches

2. **Review the detailed diff:**
   The test script shows the first 5 differences for debugging

3. **Common issues:**
   - Floating point precision: Should use `np.isclose()` (already handled)
   - NaN handling: Should treat NaN == NaN as True (already handled)
   - Index/column ordering: Should be identical
   - String case sensitivity: Should match exactly

4. **Debug specific ticker:**
   ```python
   # Test single ticker
   from range_vol_am_dev import process_data, get_tickers
   from market_scan_helpers.processing_utils import process_ticker_data

   ticker_dict = get_tickers()
   key = list(ticker_dict.keys())[0]  # First ticker
   val = ticker_dict[key]

   # Get data_dict (you'll need to load cached data)
   # ... then compare outputs
   ```

## Notes

- Both tests use `use_bbg=False` to ensure consistent cached data
- Tests are non-destructive - they write to separate test folders
- Original CSV outputs in `folder_path` are NOT overwritten during testing
- Tests use monkey-patching to temporarily swap functions without code changes

## Success Criteria

✅ All 15 CSV files match exactly (allowing for floating point precision)
✅ No shape mismatches
✅ No missing/extra rows or columns
✅ All alert lists contain same items in same order
✅ All numeric values within tolerance (1e-9 relative, 1e-12 absolute)


