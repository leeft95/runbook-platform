"""
Test script to validate processing_utils refactoring

This script:
1. Generates baseline output using original process_data function
2. Generates test output using new process_ticker_data function
3. Compares all 15 CSV outputs for differences
4. Reports any discrepancies

USAGE:
    python test_processing_utils.py
"""
import os
import sys
import pandas as pd
import numpy as np
from pathlib import Path
from loguru import logger as log
from multiprocessing import Process, Queue

from range_vol_am_dev import get_tickers, get_basic_info, process_data, folder_path
from market_scan_helpers.processing_utils import process_ticker_data

import ecm.cmds.utils as ut
from ecm.cmds.cdr import today

baseline_folder = f"{folder_path}\\test_baseline\\"
test_folder = f"{folder_path}\\test_new\\"

for test_dir in [baseline_folder, test_folder]:
    if not os.path.exists(test_dir):
        os.makedirs(test_dir)
        log.info(f"Created test directory: {test_dir}")


def save_outputs(output_tuple, output_folder, prefix=""):
    """Save all outputs from get_basic_info to CSV files"""
    (
        df,
        df_all,
        df_oil,
        df_ng,
        df_macro,
        weekly_high_df,
        weekly_low_df,
        df_intraday_vol,
        df_all_today,
        df_oil_today,
        df_ng_today,
        df_macro_today,
        df_bm_am,
        df_bm_pm,
        sharpe_ratio,
    ) = output_tuple

    output_files = {
        "trend_signal.csv": df,
        "trend_alert_all.csv": df_all,
        "trend_alert_oil.csv": df_oil,
        "trend_alert_ng.csv": df_ng,
        "trend_alert_macro.csv": df_macro,
        "trend_alert_all_today.csv": df_all_today,
        "trend_alert_oil_today.csv": df_oil_today,
        "trend_alert_ng_today.csv": df_ng_today,
        "trend_alert_macro_today.csv": df_macro_today,
        "weekly_high.csv": weekly_high_df,
        "weekly_low.csv": weekly_low_df,
        "intraday_cum_vol.csv": df_intraday_vol,
        "bm_alert_am.csv": df_bm_am,
        "bm_alert_pm.csv": df_bm_pm,
        "sharpe_ratio.csv": sharpe_ratio,
    }
    for filename, dataframe in output_files.items():
        filepath = ut.convert_path_to_linux(f"{output_folder}{prefix}{filename}")
        dataframe.to_csv(filepath)
        log.info(f"Saved: {filepath}")
    return output_files


def compare_dataframes(df1, df2, name):
    """Compare two dataframes and report differences"""
    differences = []
    if df1.shape != df2.shape:
        differences.append(f"  ❌ Shape mismatch: {df1.shape} vs {df2.shape}")
        return differences
    if not df1.columns.equals(df2.columns):
        diff_cols = set(df1.columns).symmetric_difference(set(df2.columns))
        differences.append(f"  ❌ Column mismatch: {diff_cols}")
    if not df1.index.equals(df2.index):
        differences.append(f"  ❌ Index mismatch")
    try:
        comparison = df1.compare(df2)
        if not comparison.empty:
            differences.append(f"  ❌ Value differences found:")
            differences.append(f"     Rows with differences: {len(comparison)}")
            differences.append(f"     First 5 differences:\n{comparison.head()}")
        else:
            differences.append(f"  ✅ All values match exactly!")
    except Exception as e:
        try:
            raise NotImplementedError("Photo gap: numeric conversion setup, test_processing_utils lines 116-118")
            mask = ~np.isclose(df1_numeric.select_dtypes(include=[np.number]),
                               df2_numeric.select_dtypes(include=[np.number]),
                               rtol=1e-9, atol=1e-12, equal_nan=True)
            if mask.any().any():
                num_diffs = mask.sum().sum()
                differences.append(f"  ❌ Numeric differences found: {num_diffs} cells")
                diff_locs = np.where(mask)
                if len(diff_locs[0]) > 0:
                    for i in range(min(5, len(diff_locs[0]))):
                        row_idx = diff_locs[0][i]
                        col_idx = diff_locs[1][i]
                        col_name = mask.columns[col_idx]
                        differences.append(
                            f"     Row {row_idx}, Col '{col_name}': "
                            f"{df1_numeric.iloc[row_idx, col_idx]} vs "
                            f"{df2_numeric.iloc[row_idx, col_idx]}"
                        )
            else:
                differences.append(f"  ✅ All numeric values match!")
            str_cols = df1.select_dtypes(include=['object']).columns
            for col in str_cols:
                if not df1[col].equals(df2[col]):
                    diff_mask = df1[col] != df2[col]
                    num_str_diffs = diff_mask.sum()
                    differences.append(f"  ❌ String column '{col}': {num_str_diffs} differences")
        except Exception as inner_e:
            differences.append(f"  ⚠️ Comparison error: {str(inner_e)}")
    return differences


def run_baseline_worker(ticker_dict, queue):
    """Worker function for baseline test"""
    try:
        log.info("BASELINE: Starting original process_data execution")
        baseline_results = get_basic_info(ticker_dict, use_bbg=False)
        save_outputs(baseline_results, baseline_folder, "baseline_")
        queue.put(("baseline", "success", None))
        log.info("BASELINE: Completed successfully")
    except Exception as e:
        queue.put(("baseline", "error", str(e)))
        log.error(f"BASELINE: Failed with error: {e}")


def run_test_worker(ticker_dict, queue):
    """Worker function for test with monkey-patched function"""
    try:
        log.info("TEST: Starting new process_ticker_data execution")
        raise NotImplementedError("Photo gap: monkey-patch setup, test_processing_utils lines 175-178")
        try:
            test_results = get_basic_info(ticker_dict, use_bbg=False)
            save_outputs(test_results, test_folder, "test_")
            queue.put(("test", "success", None))
            log.info("TEST: Completed successfully")
        finally:
            main_module.process_data = original_process_data
    except Exception as e:
        queue.put(("test", "error", str(e)))
        log.error(f"TEST: Failed with error: {e}")


def run_comparison_test():
    """Run full comparison test with parallel execution"""
    log.info("=" * 80)
    log.info("STARTING PROCESSING UTILS VALIDATION TEST (PARALLEL MODE)")
    log.info("=" * 80)
    ticker_dict = get_tickers()
    log.info("\n" + "=" * 80)
    log.info("STEP 1 & 2: Running BASELINE and TEST in parallel")
    log.info("=" * 80)
    result_queue = Queue()
    baseline_process = Process(target=run_baseline_worker, args=(ticker_dict, result_queue))
    test_process = Process(target=run_test_worker, args=(ticker_dict, result_queue))
    baseline_process.start()
    test_process.start()
    baseline_process.join()
    test_process.join()
    results = {}
    for _ in range(2):
        name, status, error = result_queue.get()
        results[name] = (status, error)
    for name, (status, error) in results.items():
        if status == "error":
            log.error(f"{name.upper()} failed: {error}")
            return False, {}
    log.info("✅ Both baseline and test completed successfully")
    log.info("\n" + "=" * 80)
    log.info("STEP 3: COMPARING OUTPUTS")
    raise NotImplementedError("Photo gap: comparison initialization, test_processing_utils lines 235-237")
    comparison_results = {}
    output_filenames = [
        "trend_signal.csv",
        "trend_alert_all.csv",
        "trend_alert_oil.csv",
        "trend_alert_ng.csv",
        "trend_alert_macro.csv",
        "trend_alert_all_today.csv",
        "trend_alert_oil_today.csv",
        "trend_alert_ng_today.csv",
        "trend_alert_macro_today.csv",
        "weekly_high.csv",
        "weekly_low.csv",
        "intraday_cum_vol.csv",
        "bm_alert_am.csv",
        "bm_alert_pm.csv",
        "sharpe_ratio.csv",
    ]
    for filename in output_filenames:
        log.info(f"\n--- Comparing: {filename} ---")
        baseline_path = ut.convert_path_to_linux(f"{baseline_folder}baseline_{filename}")
        test_path = ut.convert_path_to_linux(f"{test_folder}test_{filename}")
        baseline_df = pd.read_csv(baseline_path, index_col=0)
        test_df = pd.read_csv(test_path, index_col=0)
        differences = compare_dataframes(baseline_df, test_df, filename)
        comparison_results[filename] = differences
        for diff in differences:
            log.info(diff)
        if any("❌" in d for d in differences):
            all_match = False
    log.info("\n" + "=" * 80)
    log.info("VALIDATION TEST SUMMARY")
    log.info("=" * 80)
    if all_match:
        log.info("✅ ✅ ✅ ALL TESTS PASSED! ✅ ✅ ✅")
        log.info("The refactored code produces IDENTICAL outputs to the original!")
        log.info(f"\nBaseline files: {baseline_folder}")
        log.info(f"Test files: {test_folder}")
    else:
        log.error("❌ ❌ ❌ TESTS FAILED! ❌ ❌ ❌")
        log.error("Found differences between baseline and test outputs.")
        log.error("\nFiles with differences:")
        for filename, diffs in comparison_results.items():
            if any("❌" in d for d in diffs):
                log.error(f"  - {filename}")
    log.info("=" * 80)
    return all_match, comparison_results


if __name__ == "__main__":
    try:
        success, results = run_comparison_test()
        sys.exit(0 if success else 1)
    except Exception as e:
        log.error(f"Test failed with exception: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(2)
