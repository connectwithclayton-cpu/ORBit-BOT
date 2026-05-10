"""Historical OHLCV + VIX loading (Polygon or yfinance)."""

from __future__ import annotations

import time

import pandas as pd

from .settings import FabioBacktestSettings


class FabioDataLoader:
    def __init__(self, settings: FabioBacktestSettings):
        self.cfg = settings

    def load(self) -> tuple[dict, pd.DataFrame]:
        if self.cfg.data_source == "polygon" and len(self.cfg.polygon_api_key) > 10:
            return self._load_polygon()
        if self.cfg.data_source == "polygon":
            print("⚠  POLYGON_API_KEY not set — falling back to yfinance.\n")
        return self._load_yfinance()

    def _load_polygon(self) -> tuple[dict, pd.DataFrame]:
        try:
            import requests
        except ImportError:
            raise SystemExit("requests not found. Run: pip install requests")
        import yfinance as yf

        api_key = self.cfg.polygon_api_key
        symbols = self.cfg.symbols
        start, end = self.cfg.start_date, self.cfg.end_date
        sleep_sec = 13
        base = "https://api.polygon.io"

        def _get(url, params=None):
            params = params or {}
            params["apiKey"] = api_key
            r = requests.get(url, params=params, timeout=30)
            r.raise_for_status()
            return r.json()

        def _fetch_aggs(ticker, multiplier, timespan, from_date, to_date, label=""):
            url = f"{base}/v2/aggs/ticker/{ticker}/range/{multiplier}/{timespan}/{from_date}/{to_date}"
            params = {"adjusted": "true", "sort": "asc", "limit": 50000}
            rows = []
            page = 0
            while url:
                page += 1
                if label:
                    print(f"\r    {label} page {page}...", end="", flush=True)
                data = _get(url, params if page == 1 else {})
                rows.extend(data.get("results", []))
                url = data.get("next_url")
                if url:
                    time.sleep(sleep_sec)
            if label:
                print(f" {len(rows)} bars")
            return rows

        def _to_df(rows, tz="America/New_York"):
            if not rows:
                return pd.DataFrame()
            df = pd.DataFrame(rows)
            df["t"] = pd.to_datetime(df["t"], unit="ms", utc=True).dt.tz_convert(tz).dt.tz_localize(None)
            df = df.rename(
                columns={
                    "o": "Open",
                    "h": "High",
                    "l": "Low",
                    "c": "Close",
                    "v": "Volume",
                    "t": "Datetime",
                }
            )
            df = df[["Datetime", "Open", "High", "Low", "Close", "Volume"]].set_index("Datetime")
            return df.sort_index()

        print("Fetching data from Polygon.io...")
        data = {}
        for sym in symbols:
            print(f"  [{sym}] daily bars...", end=" ")
            daily_rows = _fetch_aggs(sym, 1, "day", start, end, label=f"{sym} daily")
            daily = _to_df(daily_rows)
            daily.index = daily.index.normalize()
            time.sleep(sleep_sec)

            print(f"  [{sym}] 5-min bars...")
            intra_rows = _fetch_aggs(sym, 5, "minute", start, end, label=f"{sym} 5m")
            intraday = _to_df(intra_rows)
            time.sleep(sleep_sec)

            print(f"  [{sym}] 3-min bars...")
            intra3m_rows = _fetch_aggs(sym, 3, "minute", start, end, label=f"{sym} 3m")
            intraday_3m = _to_df(intra3m_rows)
            time.sleep(sleep_sec)

            data[sym] = {"daily": daily, "intraday": intraday, "intraday_3m": intraday_3m}

        print("  VIX daily (yfinance)...", end=" ")
        vix = yf.download("^VIX", start=start, end=end, interval="1d", auto_adjust=True, progress=False)
        if isinstance(vix.columns, pd.MultiIndex):
            vix.columns = vix.columns.get_level_values(0)
        if vix.index.tz is not None:
            vix.index = vix.index.tz_convert("America/New_York").tz_localize(None)
        vix.index = vix.index.normalize()
        print("done.\n")
        return data, vix

    def _load_yfinance(self) -> tuple[dict, pd.DataFrame]:
        import yfinance as yf

        symbols = self.cfg.symbols
        start, end = self.cfg.start_date, self.cfg.end_date
        print("Downloading data via yfinance...")
        data = {}
        for sym in symbols:
            print(f"  {sym} daily...", end=" ")
            daily = yf.download(sym, start=start, end=end, interval="1d", auto_adjust=True, progress=False)
            print(f"intraday 5m...", end=" ")
            try:
                intraday = yf.download(sym, start=start, end=end, interval="5m", auto_adjust=True, progress=False)
                if intraday.index.tz is not None:
                    intraday.index = intraday.index.tz_convert("America/New_York").tz_localize(None)
            except Exception:
                intraday = pd.DataFrame()
            data[sym] = {"daily": daily, "intraday": intraday}
            print("done.")

        print("  VIX daily...", end=" ")
        vix = yf.download("^VIX", start=start, end=end, interval="1d", auto_adjust=True, progress=False)
        print("done.\n")
        return data, vix
