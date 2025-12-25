from freqtrade.strategy import IStrategy
from pandas import DataFrame
import talib.abstract as ta
import freqtrade.vendor.qtpylib.indicators as qtpylib


class SimplifiedArbitrage(IStrategy):
    """
    Simplified trend-following strategy with optimized parameters
    """
    timeframe = "1m"  # 与配置文件保持一致
    can_short = False
    startup_candle_count = 100
    process_only_new_candles = True

    # 平衡的风险参数
    stoploss = -0.015  # 适当的止损
    minimal_roi = {
        "0": 0.01,  # 合理的盈利目标
        "30": 0.005,
        "60": 0
    }

    # 降低过滤条件，允许更多交易
    volume_filter = 0.3  # 降低成交量过滤

    def informative_pairs(self):
        return [("BTC/USDT", self.timeframe)]

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # 简化指标计算，只保留核心指标
        
        # 短期趋势指标
        dataframe["ema_10"] = ta.EMA(dataframe, timeperiod=10)
        dataframe["ema_20"] = ta.EMA(dataframe, timeperiod=20)
        dataframe["sma_20"] = ta.SMA(dataframe, timeperiod=20)
        
        # 基础RSI指标
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        
        # 基础MACD指标
        macd = ta.MACD(dataframe)
        dataframe["macd"] = macd["macd"]
        dataframe["macdsignal"] = macd["macdsignal"]
        dataframe["macdhist"] = macd["macdhist"]
        
        # 简单趋势判断
        dataframe["trend_up"] = (
            (dataframe["ema_10"] > dataframe["ema_20"])
            & (dataframe["close"] > dataframe["sma_20"])
        )
        
        # 基础成交量过滤
        dataframe["volume_mean"] = dataframe["volume"].rolling(20).mean()
        dataframe["volume_ok"] = dataframe["volume"] > dataframe["volume_mean"] * self.volume_filter
        
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # 简化入场条件，降低门槛
        dataframe.loc[
            (
                # 趋势向上
                (dataframe["trend_up"])
                # 适当的成交量
                & (dataframe["volume_ok"])
                # RSI在合理范围内
                & (dataframe["rsi"] > 40)
                & (dataframe["rsi"] < 75)
                # MACD金叉
                & (dataframe["macd"] > dataframe["macdsignal"])
                # 确保有成交量
                & (dataframe["volume"] > 0)
            ),
            "enter_long"
        ] = 1

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # 合理的退出条件
        dataframe.loc[
            (
                # 趋势反转
                (dataframe["ema_10"] < dataframe["ema_20"])
                |
                # RSI超买
                (dataframe["rsi"] > 80)
                |
                # MACD死叉
                (dataframe["macd"] < dataframe["macdsignal"])
            ),
            "exit_long"
        ] = 1

        return dataframe