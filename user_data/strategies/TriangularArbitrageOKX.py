from freqtrade.strategy import IStrategy
from pandas import DataFrame
import numpy as np
import talib.abstract as ta
import freqtrade.vendor.qtpylib.indicators as qtpylib


class TriangularArbitrageOKX(IStrategy):
    """
    Triangular Arbitrage for OKX (Statistical)
    Main pair: ETH/USDT
    """

    # ========= 基本 =========
    timeframe = "1m"
    can_short = False

    startup_candle_count = 200
    process_only_new_candles = True

    # ========= 风控 =========
    stoploss = -0.012

    minimal_roi = {
        "0": 0.006,
        "5": 0.003,
        "15": 0.001
    }

    # ========= OKX 调参 =========
    triangle_threshold = 0.005  # 微调阈值到 0.5%
    z_score_threshold = 1.3  # 微调 Z-score 阈值
    volume_filter_ratio = 0.4  # 降低成交量过滤比例，允许更多交易
    window_size = 40  # 调整移动窗口大小
    ema_short = 20  # 短期 EMA
    ema_long = 50  # 长期 EMA

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

        # 使用移动平均绝对偏差（MAD）替代标准差，更稳健
        window = self.window_size
        mean = dataframe["triangle_dev"].rolling(window).mean()
        mad = dataframe["triangle_dev"].rolling(window).apply(lambda x: (x - x.mean()).abs().mean())
        
        # 使用 MAD 进行标准化，添加平滑项避免除以零
        dataframe["triangle_z"] = (dataframe["triangle_dev"] - mean) / (mad + 0.0001)
        
        # 添加趋势过滤指标
        dataframe[f"ema{self.ema_short}"] = ta.EMA(dataframe, timeperiod=self.ema_short)
        dataframe[f"ema{self.ema_long}"] = ta.EMA(dataframe, timeperiod=self.ema_long)
        dataframe["trend_up"] = dataframe[f"ema{self.ema_short}"] > dataframe[f"ema{self.ema_long}"]
        
        # 添加成交量指标
        dataframe["volume_mean20"] = dataframe["volume"].rolling(20).mean()
        dataframe["volume_filter"] = dataframe["volume"] > dataframe["volume_mean20"] * self.volume_filter_ratio

        return dataframe

    # ========= 进场 =========
    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:

        dataframe.loc[
            (
                # 三角套利条件
                (dataframe["triangle_dev"] > self.triangle_threshold)
                & (dataframe["triangle_z"] > self.z_score_threshold)
                
                # 添加过滤条件
                & (dataframe["volume_filter"])
                & (dataframe["trend_up"])
                
                # 确保数据有效
                & (dataframe["volume"] > 0)
                & (dataframe["btc_usdt"].notnull())
                & (dataframe["eth_btc"].notnull())
            ),
            "enter_long"
        ] = 1

        return dataframe

    # ========= 出场 =========
    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:

        dataframe.loc[
            (
                # 套利机会消失
                (dataframe["triangle_dev"] < 0.0015)
                | 
                # Z-score 反转
                (dataframe["triangle_z"] < 0.3)
                |
                # 趋势反转
                (qtpylib.crossed_below(dataframe["close"], dataframe[f"ema{self.ema_short}"]))
                |
                # 快速止损
                (dataframe["close"] < dataframe["open"] * (1 - self.stoploss * 0.5))
            ),
            "exit_long"
        ] = 1

        return dataframe
