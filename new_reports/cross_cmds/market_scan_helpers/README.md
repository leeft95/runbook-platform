# Market Scan Helpers Module

## Status: ✅ Production Ready

**Migration completed January 2026**

This module provides the refactored, modular implementation of the market scan processing logic, replacing the monolithic `range_vol_am.py` (6,900 lines) with a cleaner architecture (~4,590 lines in `range_vol_am_dev.py`).

## Overview

The `market_scan_helpers` module breaks down the monolithic `process_data` function into smaller, focused, testable components. This makes the code:

- ✅ **Easier to maintain** - Each function has a single responsibility
- ✅ **Easier to test** - Unit test individual calculations
- ✅ **Easier to debug** - Isolate issues to specific functions
- ✅ **Easier to understand** - Clear function names and documentation
- ✅ **Reusable** - Functions can be used in other reports
- ✅ **~33% code reduction** - From 6,900 to 4,590 lines

## Module Structure

### Data Preparation
- `prepare_price_data()` - Clean and prepare OHLC price data
- `calculate_price_changes()` - Calculate price changes and returns
- `calculate_post_close()` - Calculate post-close price movement

### FOM (First of Month) Metrics
- `parse_fom_date()` - Parse FOM date strings
- `calculate_fom_metrics()` - Calculate FOM flags and z-scores
- `calculate_fom_vwap()` - Calculate FOM VWAP

### Technical Indicators
- `calculate_stochastic()` - Stochastic oscillator
- `calculate_sharpe_ratios()` - 3D, 22D, COB sharpe ratios
- `calculate_sharpe_3d_cob()` - Helper for COB sharpe
- `calculate_range_metrics()` - True range and spikes
- `calculate_three_day_trend()` - 3-day price trend
- `calculate_current_price_range()` - HIGH/LOW range position

### Fisher Transform
- `calculate_fisher_indicators()` - Daily/weekly/monthly Fisher
- `determine_fisher_signals()` - BUY/SELL signals from Fisher
- `get_simple_fisher_signals()` - Simple Fisher signals

### Moving Averages
- `calculate_moving_average_signals()` - Momentum and hybrid signals

### KPI & Trend
- `calculate_kpi()` - Key performance indicator
- `calculate_trend_index()` - Composite trend index
- `determine_combined_signals()` - Combined trading signals
- `calculate_signal_flag()` - Signal flag determination

### Volume Analysis
- `calculate_volume_spikes()` - Intraday volume spikes
- `adjust_volume_for_roll()` - Contract roll adjustment

### Alert Generation
- `generate_alerts()` - Range/volume based alerts
- `generate_base_metal_alerts()` - Base metal z-score alerts
- `generate_volume_alert()` - Intraday volume alerts
- `check_weekly_high_low()` - Weekly extremes detection
- `generate_sharpe_ratio_row()` - Sharpe tracking data

### Utilities
- `get_expiry_info()` - Expiry date and days remaining
- `check_iroll_tag()` - IROLL tag identification
- `empty_return_tuple()` - Empty return structure
- `datetime_range()` - Datetime range generator

## Usage Example

```python
from market_scan_helpers.processing_utils import (
    prepare_price_data,
    calculate_price_changes,
    calculate_stochastic,
    calculate_sharpe_ratios,
    calculate_fisher_indicators,
    determine_fisher_signals,
    calculate_moving_average_signals,
    calculate_kpi,
    calculate_trend_index,
    determine_combined_signals,
    generate_alerts
)

def process_data_refactored(key, val, data_dict, fom_comments, fom_dict, week_sdate, folder_path):
    """Refactored process_data using modular functions"""

    # Extract data
    daily_price = data_dict.get("daily", pd.DataFrame())
    weekly_price = data_dict.get("weekly", pd.DataFrame())
    monthly_price = data_dict.get("monthly", pd.DataFrame())
    intraday_price = data_dict.get("intraday", pd.DataFrame())

    # 1. Prepare price data
    price_data = prepare_price_data(daily_price, weekly_price, monthly_price)
    if price_data is None:
        return empty_return_tuple()

    # 2. Calculate price changes
    price_changes = calculate_price_changes(
        price_data['closep'], chg_type, intraday_price
    )

    # 3. Calculate technical indicators
    sto_ind = calculate_stochastic(
        price_data['highp'], price_data['lowp'], price_data['closep']
    )

    sharpe_metrics = calculate_sharpe_ratios(
        price_changes['daily_price_chg'],
        price_changes['intraday_price_chg'],
        instr, chg_type
    )

    range_metrics = calculate_range_metrics(
        price_data['highp'], price_data['lowp'],
        price_data['closep'], daily_price
    )

    # 4. Calculate Fisher indicators
    fisher = calculate_fisher_indicators(
        price_data['highp'], price_data['lowp'], price_data['closep'],
        price_data['highp_w'], price_data['lowp_w'], price_data['closep_w'],
        price_data['highp_m'], price_data['lowp_m'], price_data['closep_m'],
        daily_price
    )

    fish, fish1, fishlt, fishlt1, counter, counter1 = determine_fisher_signals(
        fisher, price_data['closep']
    )

    # 5. Calculate moving averages
    ma_signals = calculate_moving_average_signals(price_data['closep'])

    # 6. Calculate KPI
    kpi_metrics = calculate_kpi(
        price_data['closep'], price_data['imp_vol'],
        price_changes['daily_price_chg'], chg_type,
        key[1], intraday_price
    )

    # 7. Calculate trend index
    three_day = calculate_three_day_trend(price_data['closep'])
    current_price_range = calculate_current_price_range(
        price_data['closep'], price_data['highp'], price_data['lowp']
    )
    post_close = calculate_post_close(daily_price)

    trend_index = calculate_trend_index(
        price_changes['price_change'],
        range_metrics['range_spike'],
        volume_metrics['volume_spike_5d'],
        three_day,
        sharpe_metrics['sharpe_3d'],
        sharpe_metrics['sharpe_22d'],
        current_price_range,
        post_close,
        range_metrics['avg_true_range']
    )

    # 8. Determine signals
    combined_signals = determine_combined_signals(
        trend_index, price_changes['price_change'],
        ma_signals['mom'], ma_signals['mom1'],
        ma_signals['hybrid'], ma_signals['hybrid1'],
        fish, fish1, fishlt, fishlt1, counter, counter1
    )

    # 9. Generate alerts
    alerts = generate_alerts(
        instr, ticker, chg_type,
        price_changes['price_change_pct'], price_changes['price_change_pct1'],
        range_metrics['range_spike'], range_metrics['range_spike1'],
        volume_metrics['volume_spike_5d'], volume_metrics['volume_spike_5d_1'],
        sharpe_metrics['sharpe_3d_cob'], daily_price
    )

    # Build output list...
    # (combine all metrics into output structure)

    return (output_list, alerts, ...)
```

## Migration Status

### Phase 1: Create Processing Utils ✅
- [x] Extract calculation functions
- [x] Add documentation
- [x] Create usage examples

### Phase 2: Update range_vol_am_dev.py ✅
- [x] Import processing_utils functions
- [x] Replace inline calculations with function calls
- [x] Integrate MarketDataLoader for data fetching
- [x] Remove redundant/dead code (5 functions removed)

### Phase 3: Testing & Validation ✅
- [x] Validate outputs match original implementation
- [x] Verify all email functions (sharpe ratio, risk index, alerts) are identical
- [x] Syntax validation passed
- [x] Production configuration verified

### Phase 4: Production Deployment ✅
- [x] `send_to` uses production email list
- [x] `output_path` uses config default
- [x] `use_bbg=True` for live Bloomberg data
- [x] `nan_inf_to_errors=True` in Excel exports
- [x] All dead code removed
- [x] Helpers module has complete `get_gen_month` implementation

## Files

| File | Purpose |
|------|---------|
| `__init__.py` | Module exports and MarketDataLoader |
| `config_dicts.py` | Ticker dictionaries, FOM keys, option configs |
| `data_utils.py` | MarketDataLoader class for Bloomberg/cache data |
| `processing_utils.py` | 32+ calculation functions |
| `README.md` | This documentation |

## Key Components

### MarketDataLoader (`data_utils.py`)
Central class for data fetching with caching support:
- `get_tickers()` - Get ticker dictionary
- `get_gen_month()` - Get generic month for futures (includes GCA, SIA special cases)
- `refresh_ticker_data()` - Fetch daily/weekly/monthly/intraday data
- `get_bloomberg_data()` - Bloomberg API wrapper with caching

## Benefits

### Before (Monolithic)
```python
def process_data(...):
    # 900+ lines of code
    # Multiple responsibilities
    # Hard to test
    # Hard to debug
    # Duplicated logic
```

### After (Modular)
```python
def process_data(...):
    price_data = prepare_price_data(...)
    price_changes = calculate_price_changes(...)
    sharpe_metrics = calculate_sharpe_ratios(...)
    fisher = calculate_fisher_indicators(...)
    # ... etc
    # Clear, readable, testable
```

## Function Categories

| Category | Functions | Purpose |
|----------|-----------|---------|
| Data Prep | 3 | Clean and prepare input data |
| FOM Metrics | 3 | First-of-month calculations |
| Technical | 7 | Technical indicators (stochs, range, etc) |
| Fisher | 3 | Fisher transform signals |
| Moving Avg | 1 | EMA-based signals |
| KPI/Trend | 4 | Composite metrics |
| Volume | 2 | Volume spike detection |
| Alerts | 5 | Alert generation |
| Utilities | 4 | Helper functions |

**Total: 32 focused functions** replacing 1 monolithic function

## Production vs Dev File Comparison

| Aspect | range_vol_am.py (old) | range_vol_am_dev.py (new) |
|--------|----------------------|--------------------------|
| Lines of code | ~6,900 | ~4,590 |
| Architecture | Monolithic | Modular (uses helpers) |
| Data fetching | Inline Bloomberg calls | MarketDataLoader class |
| Config | Hardcoded dicts | Imported from config_dicts.py |
| Processing | Single 900+ line function | 32 focused functions |

## Validated Email Functions

All email-generating functions verified **byte-for-byte identical**:

| Function | Status |
|----------|--------|
| `send_sharpe_ratio_rank` | ✅ Identical |
| `get_risk_index_html` | ✅ Identical |
| `send_alert_email_am` | ✅ Identical |
| `send_alert_email_pm` | ✅ Identical |
| `send_alert_email_gas` | ✅ Identical |
| `risk_sharpe_ticker_weights` | ✅ Identical |

## Testing

Each function can now be unit tested:

```python
def test_calculate_stochastic():
    highp = pd.Series([10, 12, 15, 13, 11])
    lowp = pd.Series([8, 9, 11, 10, 9])
    closep = pd.Series([9, 11, 14, 12, 10])

    result = calculate_stochastic(highp, lowp, closep)
    assert result in ["OB", "OS", "OB CROSS", "OS CROSS", None]

def test_calculate_price_changes_flat():
    closep = pd.Series([100, 102, 105, 103])
    result = calculate_price_changes(closep, "FLAT")

    assert result['price_change'] == 103 - 105
    assert abs(result['price_change_pct'] - ((103 - 105) / 105)) < 0.001
```

## Notes

- Import errors for `ecm.cmds.tickers` are handled gracefully
- Functions use type hints where appropriate
- All functions have docstrings
- Error handling included in complex calculations
- Logging via `loguru` for debugging
- pandas 2.0+ compatible (explicit dtype for empty Series)

## Removed Dead Code

The following redundant functions were removed from `range_vol_am_dev.py`:

| Function | Reason |
|----------|--------|
| `get_gen_month` (wrapper at line 106) | Replaced by helpers module |
| `datetime_range` | Replaced by helpers module |
| `get_volume_list` | Unused, broken (no return) |
| `get_platts_ticker` | Unused, broken (no return) |
| `get_ticker` | Unused |

## Future Improvements

- [ ] Add comprehensive unit test suite
- [ ] Performance benchmarking
- [ ] Consider async data fetching for parallelization


