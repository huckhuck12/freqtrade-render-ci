from freqtrade.strategy import IStrategy
from pandas import DataFrame
import numpy as np


class TriangularArbitrageOKX(IStrategy):
    """
    Triangular Arbitrage for OKX (Statistical)
    Main pair: ETH/USDT
    """

    # ========= 基本 =========
    timeframe = "1m"
    can_short = False

    startup_candle_count = 60
    process_only_new_candles = True

    # ========= 风控 =========
    stoploss = -0.015

    minimal_roi = {
        "0": 0.004,
        "5": 0.002,
        "15": 0
    }

    # ========= OKX 调参 =========
    triangle_threshold = 0.004  # 0.4%

    # ========= 信息对 =========
    def informative_pairs(self):
        return [
            ("BTC/USDT", self.timeframe),
            ("ETH/BTC", self.timeframe),
        ]

    # ========= 指标 =========
    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:

        btc = self.dp.get_pair_dataframe("BTC/USDT", self.timeframe)
        ethbtc = self.dp.get_pair_dataframe("ETH/BTC", self.timeframe)

        dataframe["btc_usdt"] = btc["close"]
        dataframe["eth_btc"] = ethbtc["close"]

        # 三角比率
        dataframe["triangle_ratio"] = (
            dataframe["btc_usdt"]
            * dataframe["eth_btc"]
            / dataframe["close"]
        )

        dataframe["triangle_dev"] = dataframe["triangle_ratio"] - 1.0

        # 标准化（更适合 OKX 噪音）
        mean = dataframe["triangle_dev"].rolling(40).mean()
        std = dataframe["triangle_dev"].rolling(40).std()

        dataframe["triangle_z"] = (dataframe["triangle_dev"] - mean) / std

        return dataframe

    # ========= 进场 =========
    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:

        dataframe.loc[
            (
                (dataframe["triangle_dev"] > self.triangle_threshold)
                & (dataframe["triangle_z"] > 1.2)
                & (dataframe["volume"] > 0)
            ),
            "enter_long"
        ] = 1

        return dataframe

    # ========= 出场 =========
    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:

        dataframe.loc[
            (
                (dataframe["triangle_dev"] < 0.001)
                | (dataframe["triangle_z"] < 0)
            ),
            "exit_long"
        ] = 1

        return dataframe
