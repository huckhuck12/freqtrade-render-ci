from freqtrade.strategy import IStrategy
from pandas import DataFrame
import talib.abstract as ta
import freqtrade.vendor.qtpylib.indicators as qtpylib


class SimplifiedArbitrage(IStrategy):
    """
    Optimized mean reversion strategy with improved parameters
    """
    timeframe = "1m"
    can_short = False
    startup_candle_count = 100
    process_only_new_candles = True

    # 优化的风险参数
    stoploss = -0.02  # 放宽止损，减少止损触发
    minimal_roi = {
        "0": 0.008,  # 降低盈利目标，提高胜率
        "25": 0.004,
        "50": 0
    }

    # 优化均值回归参数
    ma_period = 40  # 缩短移动平均线周期，提高灵敏度
    std_dev = 1.8  # 降低标准差倍数，增加交易机会
    rsi_overbought = 65  # 调整超买阈值
    rsi_oversold = 35  # 调整超卖阈值，减少极端信号

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
        # 优化入场条件
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
        # 优化退出条件
        dataframe.loc[
            (
                (dataframe["close"] > dataframe["ma"])
                |
                (dataframe["rsi"] > self.rsi_overbought)
            ),
            "exit_long"
        ] = 1

        return dataframe