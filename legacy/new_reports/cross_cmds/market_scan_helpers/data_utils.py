import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Union, Tuple
from loguru import logger as log
import ecm.cmds.market_scan as ms
import ecm.cmds.ticker as tk
import ecm.cmds.bbg as bbg
from pathlib import Path
from ecm.data.api import RTHQueryClient
from ecm.atom.clients import ECMHttpError
import ecm.cmds.time_series as ts
from ecm.cmds.cdr import today
from dateutil.relativedelta import relativedelta, FR
from ecm.cmds.utils import convert_path_to_linux
from pytz import timezone

class MarketDataLoader:
    """Unified data loader for market scanning operations"""

    def __init__(self, cache_dir: Optional[str] = None, use_cache: bool = True):
        self.use_cache = use_cache
        self.cache_dir = Path(cache_dir) if cache_dir else None
        self._ticker_cache = {}
        self._price_cache = {}

        self._period_configs = {
            "D": None,
            "W": [("periodicitySelection", "WEEKLY")],
            "M": [("periodicitySelection", "MONTHLY")],
        }

    def get_tickers(self, name_dict: Optional[Dict] = None, force_update: bool = False) -> Dict:
        """Get ticker dictionary from market scan"""
        cache_key = str(name_dict) if name_dict else "default"

        if not force_update and cache_key in self._ticker_cache:
            return self._ticker_cache[cache_key]

        ticker_dict = ms.get_ticker_dict(name_dict, force_update=force_update)
        self._ticker_cache[cache_key] = ticker_dict
        return ticker_dict

    def get_gen_month(self, ticker: str) -> str:
        """Get generic month for futures ticker"""
        ticker_dict = tk.decompose_ticker(ticker)

        if ticker_dict["active"] in ["SMA Comdty", "BOA Comdty"]:
            return "FHKNZ"
        elif ticker_dict["active"] in ["S A Comdty"]:
            return "FHKNX"
        elif ticker_dict["active"] in ["GCA Comdty"]:
            return "GJMQZ"
        elif ticker_dict["active"] in ["SIA Comdty"]:
            return "HKNUZ"

        try:
            ret = bbg.bref(ticker, ["FUT_GEN_MONTH"], use_bpipe=False)
            if isinstance(ret.columns, pd.MultiIndex):
                return ret.iloc[0, 1]
            else:
                return ret.iloc[0, 0]
        except Exception as e:
            log.warning(f"Could not get generic month for {ticker}: {e}")
            return "FGHJKMNQUVXZ"  # Default all months

    def get_bloomberg_data(
        self,
        ticker: Union[str, List[str]],
        fields: Union[str, List[str]],
        start_date: datetime,
        end_date: datetime,
        period: str = "D",
        use_cache: bool = None,
        extract_single_ticker: bool = True
    ) -> pd.DataFrame:
        """
        Enhanced Bloomberg data fetcher matching refresh_data patterns

        Args:
            ticker: Single ticker or list of tickers
            fields: Bloomberg fields to fetch
            start_date: Start date
            end_date: End date
            period: 'D' (daily), 'W' (weekly), 'M' (monthly)
            use_cache: Override instance cache setting
            extract_single_ticker: If True and single ticker, extract from MultiIndex
        """
        use_cache = use_cache if use_cache is not None else self.use_cache

        cache_key = self._create_cache_key(ticker, fields, start_date, end_date, period)

        if use_cache and cache_key in self._price_cache:
            log.debug(f"Using cached data for {ticker}")
            return self._price_cache[cache_key].copy()

        try:
            elms = self._period_configs.get(period, None)
            data = bbg.bdh(ticker, fields, sdate=start_date, edate=end_date, elms=elms, use_bpipe=False)

            if extract_single_ticker and isinstance(ticker, str) and isinstance(data.columns, pd.MultiIndex):
                data = data[ticker]

            if use_cache:
                self._price_cache[cache_key] = data.copy()

            return data

        except (TypeError, ValueError, ECMHttpError) as e:
            log.error(f"Could not fetch Bloomberg data for {ticker}: {e}")
            return pd.DataFrame()
        except Exception as e:
            log.error(f"Unexpected error fetching data for {ticker}: {e}")
            return pd.DataFrame()

    def get_csv_data(self, ticker: str, folder_path: str,
                    data_type: str = "price_daily", index_col: str = "date") -> pd.DataFrame:
        """Load CSV data with error handling matching refresh_data patterns"""
        try:
            if data_type == "price_daily":
                file_path = f"{folder_path}price_daily\\{ticker}.csv"
            elif data_type == "price_intraday":
                file_path = f"{folder_path}price_intraday\\{ticker}.csv"
            else:
                file_path = f"{folder_path}{data_type}\\{ticker}.csv"

            if data_type == "price_daily" and not index_col == "date":
                raise ValueError("For price_daily, index_col must be 'date'")
            elif data_type == "price_intraday" and not index_col == "time":
                raise ValueError("For price_intraday, index_col must be 'time'")
            if index_col == "date":
                return ts.read_csv(file_path, index_name="date")
            else:
                return ts.read_csv(file_path, index_name=index_col)

        except Exception as e:
            log.warning(f"Could not load CSV {file_path}: {e}")
            return pd.DataFrame()

    def get_rth_bvol_data(self, ticker: str, start_date: datetime,
                         end_date: datetime, call_type: str = "0.5C") -> pd.DataFrame:
        """Get RTH BVOL data matching refresh_data patterns"""
        try:
            if ticker.split(" ")[-2] == "BVOL":
                base_ticker = ticker.split(" ")[0]
                if base_ticker == "FJS":
                    base_ticker = "TZT"

                flat_ticker = bbg.bref(base_ticker + "A Comdty", ["TICKER"], use_bpipe=False)
                if isinstance(flat_ticker.columns, pd.MultiIndex):
                    flat_ticker = flat_ticker.iloc[0, 1] + " Comdty"
                else:
                    flat_ticker = flat_ticker.iloc[0, 0] + " Comdty"

                gen_month = self.get_gen_month(flat_ticker)
                flat_ticker = tk.next_ticker(flat_ticker, gen_month)

                data = RTHQueryClient.get_bvol(
                    ops_codes=ms.convert_ticker(flat_ticker),
                    start_date=start_date,
                    end_date=end_date,
                    specific_call=call_type,
                )

                if len(data) > 0:
                    data = data.reset_index(level=["ric", "ticker", "option_expiry", "underlying_settle_price"], drop=True)
                    data = data[[call_type]] if not call_type == "0.5C" else data[["0.5D"]]
                    data.columns = ["PX_LAST"]
                    data.index = pd.to_datetime(data.index)
                    if data.index.name != "date":
                        data.index.name = "date"
                    data = data * 100  # Convert to percentage
                    return data

            return pd.DataFrame()

        except Exception as e:
            log.error(f"RTH Data not available for {ticker}: {e}")
            return pd.DataFrame()

    def get_rth_risk_reversal_data(self, ticker: str, start_date: datetime, end_date: datetime) -> pd.DataFrame:
        """Get RTH risk reversal data (put - call)"""
        try:
            put_data = pd.DataFrame()
            call_data = pd.DataFrame()

            try:
                put_data = self.get_rth_bvol_data(ticker, start_date, end_date, "0.25P")
            except Exception as e:
                log.error(f"RTH Put Data not available for {ticker}: {e}")

            try:
                call_data = self.get_rth_bvol_data(ticker, start_date, end_date, "0.25C")
            except Exception as e:
                log.error(f"RTH Call Data not available for {ticker}: {e}")

            if len(put_data) > 0 and len(call_data) > 0:
                return put_data - call_data.reindex(put_data.index)

            return pd.DataFrame()

        except Exception as e:
            log.error(f"Could not calculate risk reversal for {ticker}: {e}")
            return pd.DataFrame()

    def get_intraday_data(self, ticker: str, start_date: datetime,
                         end_date: datetime, interval: int = 10) -> pd.DataFrame:
        """Get Bloomberg intraday data"""
        try:
            return bbg.bdib(ticker, sdate=start_date, edate=end_date, interval=interval)
        except (TypeError, ValueError, ECMHttpError) as e:
            log.error(f"Unable to get intraday data for {ticker}: {e}")
            return pd.DataFrame()

    def get_vol_adjusted_forex_data(self, ticker: str, start_date: datetime, end_date: datetime,
                                   folder_path: Optional[str] = None, save_vol_ticker: bool = True) -> pd.DataFrame:
        """
        Get forex data with 3M vol adjustment (matches refresh_data pattern)

        Args:
            ticker: Forex ticker
            start_date: Start date
            end_date: End date
            folder_path: Path to save vol ticker CSV (required if save_vol_ticker=True)
            save_vol_ticker: Whether to save the vol ticker CSV separately

        Returns:
            DataFrame with vol adjustment applied, or original data if not forex
        """
        base_data = self.get_bloomberg_data(ticker, ["PX_LAST"], start_date, end_date)

        if ticker.split(" ")[0] in ["EURUSD", "USDJPY", "AUDUSD", "USDCAD", "USDCNH", "USDINR", "USDBRL", "USDRUB"]:
            vol_ticker = ticker.split(" ")[0] + "V3M" + ticker.split(" ")[1]

            if folder_path and save_vol_ticker:
                existing_vol = self.get_csv_data(vol_ticker, folder_path, "price_daily")
                if not existing_vol.empty:
                    last_vol_date = existing_vol.index[-2]
                    new_vol = self.get_bloomberg_data(vol_ticker, ["PX_LAST"], last_vol_date, end_date)
                    vol_data = self.merge_with_existing_data(new_vol, vol_ticker, folder_path, "price_daily")
                else:
                    extended_start = start_date - timedelta(days=182)
                    vol_data = self.get_bloomberg_data(vol_ticker, ["PX_LAST"], extended_start, end_date)

                if not vol_data.empty:
                    self.save_csv_data(vol_data, vol_ticker, folder_path, "price_daily")
            else:
                vol_data = self.get_bloomberg_data(vol_ticker, ["PX_LAST"], start_date, end_date)

            if not vol_data.empty and not base_data.empty:
                base_data["3MTH_IMPVOL_100.0%MNY_DF"] = vol_data["PX_LAST"]

        return base_data

    def save_csv_data(self, data: pd.DataFrame, ticker: str, folder_path: str, data_type: str = "price_daily"):
        """Save DataFrame to CSV with error handling"""
        try:
            if data_type == "price_daily":
                file_path = f"{folder_path}price_daily\\{ticker}.csv"
            elif data_type == "price_intraday":
                file_path = f"{folder_path}price_intraday\\{ticker}.csv"
            else:
                file_path = f"{folder_path}{data_type}\\{ticker}.csv"

            data.to_csv(convert_path_to_linux(file_path))
            log.debug(f"Saved {data_type} data for {ticker}")

        except Exception as e:
            log.error(f"Could not save {file_path}: {e}")

    def merge_with_existing_data(self, new_data: pd.DataFrame, ticker: str,
                                folder_path: str, data_type: str = "price_daily", index_col: str = "date") -> pd.DataFrame:
        """Merge new data with existing CSV data"""
        existing_data = self.get_csv_data(ticker, folder_path, data_type, index_col)

        if not existing_data.empty and not new_data.empty:
            merged_data = pd.concat([existing_data.iloc[:-2, :], new_data], axis=0)
            return merged_data
        elif not new_data.empty:
            return new_data
        else:
            return existing_data

    def refresh_ticker_data(self, ticker: str, start_date: datetime, end_date: datetime,
                           folder_path: str, use_bbg: bool = True) -> Dict[str, pd.DataFrame]:
        """
        Comprehensive data refresh matching refresh_data function patterns

        Returns:
            Dict with keys: 'daily', 'weekly', 'monthly', 'intraday'
        """
        result = {
            'daily': pd.DataFrame(),
            'weekly': pd.DataFrame(),
            'monthly': pd.DataFrame(),
            'intraday': pd.DataFrame()
        }
        next_friday = today() + relativedelta(weekday=FR(1))
        next_monthend = today() + relativedelta(day=31)

        if not use_bbg:
            result['daily'] = self.get_csv_data(ticker, folder_path, "price_daily", index_col="date")
            result['intraday'] = self.get_csv_data(ticker, folder_path, "price_intraday", index_col="time")
            if not result['daily'].empty or not result['intraday'].empty:
                result['weekly'] = result['daily'].resample("W-FRI").last() if not result['daily'].empty else pd.DataFrame()
                result['monthly'] = result['daily'].resample("M").last() if not result['daily'].empty else pd.DataFrame()
                return result

        if ticker in ["LPARB", "LAARB", "LXARB", "LLARB"]:
            result['daily'] = self._get_arb_data(ticker)
        elif ticker.split(" ")[-2] == "BVOL" and not ticker.split(" ")[-1] == "Curncy":
            result['daily'] = self.get_rth_bvol_data(ticker, start_date, end_date)
        elif ticker.split(" ")[0] in [".CL1MRR", ".CO1MRR", ".NG1MRR", ".S1MRR", ".C1MRR", ".W1MRR", ".FJS1MRR"]:
            result['daily'] = self.get_rth_risk_reversal_data(ticker, start_date, end_date)
        else:
            fields = ["PX_OPEN", "PX_HIGH", "PX_LOW", "PX_LAST", "PX_SETTLE", "FUT_PX", "VOLUME", "3MTH_IMPVOL_100.0%MNY_DF"]

            existing_daily = self.get_csv_data(ticker, folder_path, "price_daily")
            if not existing_daily.empty:
                last_date = existing_daily.index[-2]  # Use -2 like refresh_data
                new_daily = self.get_bloomberg_data(ticker, fields, last_date, end_date)
                result['daily'] = self.merge_with_existing_data(new_daily, ticker, folder_path, "price_daily")
            else:
                extended_start = start_date - timedelta(days=182)
                result['daily'] = self.get_bloomberg_data(ticker, fields, extended_start, end_date)

            if ticker.split(" ")[0] in ["EURUSD", "USDJPY", "AUDUSD", "USDCAD", "USDCNH", "USDINR", "USDBRL", "USDRUB"]:
                vol_adjusted_data = self.get_vol_adjusted_forex_data(ticker, start_date, end_date, folder_path)
                if not vol_adjusted_data.empty and not result['daily'].empty:
                    result['daily']["3MTH_IMPVOL_100.0%MNY_DF"] = vol_adjusted_data["3MTH_IMPVOL_100.0%MNY_DF"]

            weekly_fields = ["PX_OPEN", "PX_HIGH", "PX_LOW", "PX_LAST", "PX_SETTLE", "FUT_PX", "VOLUME"]
            result['weekly'] = self.get_bloomberg_data(ticker, weekly_fields, start_date, next_friday, period="W")
            result['monthly'] = self.get_bloomberg_data(ticker, weekly_fields, start_date - timedelta(days=365), next_monthend, period="M")

            existing_intraday = self.get_csv_data(ticker, folder_path, "price_intraday", "time")
            if not existing_intraday.empty:
                if len(existing_intraday) > 1:
                    last_date = existing_intraday.index[-2]
                else:
                    last_date = existing_intraday.index[-1]
                if last_date > datetime.now().astimezone(timezone("Europe/London")).replace(tzinfo=None):
                    result['intraday'] = existing_intraday
                    log.info(f"Intraday data for {ticker} is already up to date.")
                    return result
                new_intraday = self.get_intraday_data(ticker, last_date, end_date + timedelta(days=1))
                result['intraday'] = self.merge_with_existing_data(new_intraday, ticker, folder_path, "price_intraday", "time")
            else:
                result['intraday'] = self.get_intraday_data(ticker, start_date, end_date)

        if not result['daily'].empty:
            if result['weekly'].empty:
                try:
                    result['weekly'] = result['daily'].resample("W-FRI").last()
                except:
                    pass
            if result['monthly'].empty:
                try:
                    result['monthly'] = result['daily'].resample("M").last()
                except:
                    pass

        if not result['daily'].empty:
            self.save_csv_data(result['daily'], ticker, folder_path, "price_daily")
        if not result['intraday'].empty:
            self.save_csv_data(result['intraday'], ticker, folder_path, "price_intraday")

        log.info(f"Loaded data for {ticker}")
        return result

    def _get_arb_data(self, ticker: str) -> pd.DataFrame:
        """Handle special ARB tickers"""
        try:
            base_path = f"\\\\elementcapital.corp\\ecns01\\PM\\Michel Kikano\\Data\\model\\{ticker[:2]}A Comdty.csv"
            try:
                data = ts.read_csv(base_path, index_name="date")
            except:
                data = ts.read_csv(base_path, index_name="Unnamed: 0")

            data.ffill(inplace=True)
            return data
        except Exception as e:
            log.error(f"Could not load ARB data for {ticker}: {e}")
            return pd.DataFrame()

    def _create_cache_key(self, ticker, fields, start_date, end_date, period):
        """Create cache key for price data"""
        ticker_str = str(ticker) if isinstance(ticker, str) else "_".join(sorted(ticker))
        fields_str = str(fields) if isinstance(fields, str) else "_".join(sorted(fields))
        return f"{ticker_str}_{fields_str}_{start_date}_{end_date}_{period}"

    def clear_cache(self):
        """Clear all cached data"""
        self._ticker_cache.clear()
        self._price_cache.clear()
        log.info("Cache cleared")

    def get_cache_stats(self) -> Dict[str, int]:
        """Get cache statistics"""
        return {
            "ticker_cache_size": len(self._ticker_cache),
            "price_cache_size": len(self._price_cache),
        }

    @staticmethod
    def merge_dataframes(current_data: pd.DataFrame, new_data: pd.DataFrame) -> pd.DataFrame:
        """Merge two DataFrames with upsert behavior"""
        latest_new_data = new_data[~new_data.index.isin(current_data.index)]

        if latest_new_data.empty:
            current_data.loc[new_data.index] = None
            updated_data = current_data.combine_first(new_data)
        else:
            updated_data = pd.concat([current_data, latest_new_data])

        return updated_data


def get_tickers(name_dict=None):
    """Backward compatibility wrapper"""
    loader = MarketDataLoader()
    return loader.get_tickers(name_dict)


def get_gen_month(ticker):
    """Backward compatibility wrapper"""
    loader = MarketDataLoader()
    return loader.get_gen_month(ticker)


def merge_dfs(current_data: pd.DataFrame, new_data: pd.DataFrame) -> pd.DataFrame:
    """Backward compatibility wrapper"""
    return MarketDataLoader.merge_dataframes(current_data, new_data)

def _get_daily_price(ticker, fields, sdate, edate):
    """Backward compatibility for existing code"""
    loader = MarketDataLoader()
    return loader.get_bloomberg_data(ticker, fields, sdate, edate, period="D")

def _get_weekly_price(ticker, fields, sdate, edate):
    """Backward compatibility for existing code"""
    loader = MarketDataLoader()
    return loader.get_bloomberg_data(ticker, fields, sdate, edate, period="W")

def _get_monthly_price(ticker, fields, sdate, edate):
    """Backward compatibility for existing code"""
    loader = MarketDataLoader()
    return loader.get_bloomberg_data(ticker, fields, sdate, edate, period="M")
