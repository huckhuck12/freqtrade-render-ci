from freqtrade.strategy import IStrategy
from pandas import DataFrame
import talib.abstract as ta
import freqtrade.vendor.qtpylib.indicators as qtpylib


class SimplifiedArbitrage(IStrategy):
    """
    Mean reversion strategy with optimized parameters
    """
    timeframe = "1m"
    can_short = False
    startup_candle_count = 100
    process_only_new_candles = True

    # 均值回归策略参数
    stoploss = -0.015
    minimal_roi = {
        "0": 0.01,
        "30": 0.005,
        "60": 0
    }

    # 均值回归参数
    ma_period = 50  # 移动平均线周期
    std_dev = 2.0  # 标准差倍数
    rsi_overbought = 70
    rsi_oversold = 30

    def informative_pairs(self):
        return [("BTC/USDT", self.timeframe)]

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # 计算移动平均线和标准差
        dataframe["ma"] = ta.SMA(dataframe, timeperiod=self.ma_period)
        dataframe["std"] = ta.STDDEV(dataframe, timeperiod=self.ma_period)
        
        # 计算布林带
        dataframe["upper_band"] = dataframe["ma"] + (dataframe["std"] * self.std_dev)
        dataframe["lower_band"] = dataframe["ma"] - (dataframe["std"] * self.std_dev)
        
        # RSI指标
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        
        # 价格偏离度
        dataframe["price_deviation"] = (dataframe["close"] - dataframe["ma"]) / dataframe["ma"]
        
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # 均值回归策略入场条件 - 价格低于下轨且RSI超卖
        dataframe.loc[
            (
                (dataframe["close"] < dataframe["lower_band"])
                & (dataframe["rsi"] < self.rsi_oversold)
                & (dataframe["volume"] > 0)
            ),
            "enter_long"
        ] = 1

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # 均值回归策略退出条件 - 价格回归均线或RSI超买
        dataframe.loc[
            (
                (dataframe["close"] > dataframe["ma"])
                |
                (dataframe["rsi"] > self.rsi_overbought)
            ),
            "exit_long"
        ] = 1

        return dataframe