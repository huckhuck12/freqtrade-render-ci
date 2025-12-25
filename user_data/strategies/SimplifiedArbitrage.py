from freqtrade.strategy import IStrategy
from pandas import DataFrame
import talib.abstract as ta
import freqtrade.vendor.qtpylib.indicators as qtpylib


class SimplifiedArbitrage(IStrategy):
    """
    Trend breakout strategy with optimized parameters
    """
    timeframe = "1m"  # 与配置文件保持一致
    can_short = False
    startup_candle_count = 100
    process_only_new_candles = True

    # 保守的风险参数
    stoploss = -0.01  # 严格止损
    minimal_roi = {
        "0": 0.02,  # 更高的盈利目标
        "60": 0.01,
        "120": 0.005
    }

    # 突破策略参数
    breakout_period = 20  # 突破周期
    volume_multiplier = 1.5  # 成交量乘数

    def informative_pairs(self):
        return [("BTC/USDT", self.timeframe)]

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # 计算关键指标
        dataframe["sma_20"] = ta.SMA(dataframe, timeperiod=20)
        dataframe["sma_50"] = ta.SMA(dataframe, timeperiod=50)
        
        # 计算ATR用于止损和突破幅度
        dataframe["atr"] = ta.ATR(dataframe, timeperiod=14)
        
        # 计算高低点突破
        dataframe["highest_high"] = dataframe["high"].rolling(self.breakout_period).max()
        dataframe["lowest_low"] = dataframe["low"].rolling(self.breakout_period).min()
        
        # 成交量平均
        dataframe["volume_mean"] = dataframe["volume"].rolling(20).mean()
        
        # 趋势判断
        dataframe["trend_up"] = dataframe["sma_20"] > dataframe["sma_50"]
        
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # 突破策略入场条件
        dataframe.loc[
            (
                # 价格突破20日高点
                (dataframe["close"] > dataframe["highest_high"].shift(1))
                # 同时成交量放大
                & (dataframe["volume"] > dataframe["volume_mean"] * self.volume_multiplier)
                # 处于上升趋势中
                & (dataframe["trend_up"])
                # 确保有成交量
                & (dataframe["volume"] > 0)
            ),
            "enter_long"
        ] = 1

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # 突破策略退出条件
        dataframe.loc[
            (
                # 价格跌破20日低点
                (dataframe["close"] < dataframe["lowest_low"].shift(1))
                |
                # 价格跌破短期均线
                (dataframe["close"] < dataframe["sma_20"])
            ),
            "exit_long"
        ] = 1

        return dataframe