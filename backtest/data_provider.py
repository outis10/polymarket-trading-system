"""Data providers for historical price data"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List, Optional
import asyncio
import logging

import pandas as pd

try:
    import aiohttp
except ImportError:
    aiohttp = None

try:
    import requests
except ImportError:
    requests = None


@dataclass
class PriceBar:
    """OHLCV price bar"""
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


class BaseDataProvider(ABC):
    """Base interface for data providers"""

    @abstractmethod
    async def fetch_historical_data(
        self,
        symbol: str,
        start_date: datetime,
        end_date: datetime,
        timeframe: str = "1m"
    ) -> pd.DataFrame:
        """
        Fetch historical OHLCV data

        Args:
            symbol: Trading pair (e.g., "SOLUSDT")
            start_date: Start date
            end_date: End date
            timeframe: "1m", "5m", "15m", "1h", etc.

        Returns:
            DataFrame with columns: timestamp, open, high, low, close, volume
        """
        pass

    @abstractmethod
    def get_supported_symbols(self) -> List[str]:
        """Get list of supported symbols"""
        pass


class BinanceDataProvider(BaseDataProvider):
    """Data provider using Binance public API"""

    BASE_URL = "https://api.binance.com/api/v3"

    # Timeframe to milliseconds mapping (all Binance supported intervals)
    TIMEFRAME_MS = {
        "1m": 60 * 1000,
        "3m": 3 * 60 * 1000,
        "5m": 5 * 60 * 1000,
        "15m": 15 * 60 * 1000,
        "30m": 30 * 60 * 1000,
        "1h": 60 * 60 * 1000,
        "2h": 2 * 60 * 60 * 1000,
        "4h": 4 * 60 * 60 * 1000,
        "6h": 6 * 60 * 60 * 1000,
        "8h": 8 * 60 * 60 * 1000,
        "12h": 12 * 60 * 60 * 1000,
        "1d": 24 * 60 * 60 * 1000,
        "3d": 3 * 24 * 60 * 60 * 1000,
        "1w": 7 * 24 * 60 * 60 * 1000,
    }

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    async def fetch_historical_data(
        self,
        symbol: str,
        start_date: datetime,
        end_date: datetime,
        timeframe: str = "1m"
    ) -> pd.DataFrame:
        """
        Fetch klines from Binance API

        Binance allows up to 1000 klines per request, so we paginate for longer periods.
        """
        if timeframe not in self.TIMEFRAME_MS:
            raise ValueError(f"Unsupported timeframe: {timeframe}")

        start_ms = int(start_date.timestamp() * 1000)
        end_ms = int(end_date.timestamp() * 1000)

        all_klines = []
        current_start = start_ms

        self.logger.info(f"Fetching {symbol} data from {start_date} to {end_date}")

        while current_start < end_ms:
            klines = await self._fetch_klines(
                symbol=symbol,
                interval=timeframe,
                start_time=current_start,
                end_time=end_ms,
                limit=1000
            )

            if not klines:
                break

            all_klines.extend(klines)

            # Move to next batch
            last_timestamp = klines[-1][0]
            current_start = last_timestamp + self.TIMEFRAME_MS[timeframe]

            # Rate limiting
            await asyncio.sleep(0.1)

        if not all_klines:
            self.logger.warning(f"No data received for {symbol}")
            return pd.DataFrame(columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])

        # Convert to DataFrame
        df = pd.DataFrame(all_klines, columns=[
            'timestamp', 'open', 'high', 'low', 'close', 'volume',
            'close_time', 'quote_volume', 'trades', 'taker_buy_base',
            'taker_buy_quote', 'ignore'
        ])

        # Process columns
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df['open'] = df['open'].astype(float)
        df['high'] = df['high'].astype(float)
        df['low'] = df['low'].astype(float)
        df['close'] = df['close'].astype(float)
        df['volume'] = df['volume'].astype(float)

        # Keep only needed columns
        df = df[['timestamp', 'open', 'high', 'low', 'close', 'volume']]

        # Note: Binance already filters by the timestamps we provide,
        # so no additional filtering is needed here.
        # The timestamps in df are UTC.

        self.logger.info(f"Fetched {len(df)} bars for {symbol}")

        return df

    async def _fetch_klines(
        self,
        symbol: str,
        interval: str,
        start_time: int,
        end_time: int,
        limit: int = 1000
    ) -> List:
        """Fetch klines from Binance"""
        url = f"{self.BASE_URL}/klines"
        params = {
            "symbol": symbol,
            "interval": interval,
            "startTime": start_time,
            "endTime": end_time,
            "limit": limit
        }

        if aiohttp:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params) as response:
                    if response.status == 200:
                        return await response.json()
                    else:
                        self.logger.error(f"Binance API error: {response.status}")
                        return []
        elif requests:
            # Fallback to sync requests
            response = requests.get(url, params=params, timeout=30)
            if response.status_code == 200:
                return response.json()
            else:
                self.logger.error(f"Binance API error: {response.status_code}")
                return []
        else:
            raise ImportError("Either aiohttp or requests is required")

    def get_supported_symbols(self) -> List[str]:
        """Get common crypto symbols"""
        return [
            "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT",
            "XRPUSDT", "ADAUSDT", "DOGEUSDT", "MATICUSDT"
        ]


class CoinGeckoDataProvider(BaseDataProvider):
    """Data provider using CoinGecko API (free, lower granularity)"""

    BASE_URL = "https://api.coingecko.com/api/v3"

    # CoinGecko ID mapping
    SYMBOL_MAP = {
        "SOLUSDT": "solana",
        "BTCUSDT": "bitcoin",
        "ETHUSDT": "ethereum",
        "BNBUSDT": "binancecoin",
    }

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    async def fetch_historical_data(
        self,
        symbol: str,
        start_date: datetime,
        end_date: datetime,
        timeframe: str = "1h"
    ) -> pd.DataFrame:
        """
        Fetch data from CoinGecko

        Note: CoinGecko granularity depends on date range:
        - 1-2 days: 5 min
        - 2-90 days: hourly
        - >90 days: daily
        """
        coin_id = self.SYMBOL_MAP.get(symbol)
        if not coin_id:
            raise ValueError(f"Symbol {symbol} not supported by CoinGecko provider")

        start_ts = int(start_date.timestamp())
        end_ts = int(end_date.timestamp())

        url = f"{self.BASE_URL}/coins/{coin_id}/market_chart/range"
        params = {
            "vs_currency": "usd",
            "from": start_ts,
            "to": end_ts
        }

        if requests:
            response = requests.get(url, params=params, timeout=30)
            if response.status_code != 200:
                self.logger.error(f"CoinGecko API error: {response.status_code}")
                return pd.DataFrame(columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])

            data = response.json()
        else:
            raise ImportError("requests library is required for CoinGecko provider")

        # CoinGecko returns prices, not OHLC
        prices = data.get('prices', [])

        if not prices:
            return pd.DataFrame(columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])

        df = pd.DataFrame(prices, columns=['timestamp', 'close'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df['open'] = df['close']
        df['high'] = df['close']
        df['low'] = df['close']
        df['volume'] = 0.0  # CoinGecko doesn't provide volume in this endpoint

        df = df[['timestamp', 'open', 'high', 'low', 'close', 'volume']]

        self.logger.info(f"Fetched {len(df)} bars for {symbol} from CoinGecko")

        return df

    def get_supported_symbols(self) -> List[str]:
        """Get supported symbols"""
        return list(self.SYMBOL_MAP.keys())


class DataProviderFactory:
    """Factory for creating data providers"""

    @staticmethod
    def create(provider_name: str) -> BaseDataProvider:
        """
        Create a data provider

        Args:
            provider_name: "binance" or "coingecko"

        Returns:
            Data provider instance
        """
        providers = {
            "binance": BinanceDataProvider,
            "coingecko": CoinGeckoDataProvider,
        }

        if provider_name not in providers:
            raise ValueError(f"Provider {provider_name} not supported. Use: {list(providers.keys())}")

        return providers[provider_name]()
