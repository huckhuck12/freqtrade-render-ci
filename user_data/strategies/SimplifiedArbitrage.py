from freqtrade.strategy import IStrategy
from pandas import DataFrame
import talib.abstract as ta
import freqtrade.vendor.qtpylib.indicators as qtpylib


class SimplifiedArbitrage(IStrategy):
    """
    Optimized trend breakout strategy with improved filtering
    """
    timeframe = "1m"  # 与配置文件保持一致
    can_short = False
    startup_candle_count = 100
    process_only_new_candles = True

    # 优化的风险参数
    stoploss = -0.01  # 保持严格止损
    minimal_roi = {
        "0": 0.015,  # 调整盈利目标
        "45": 0.01,
        "90": 0.005
    }

    # 优化突破策略参数
    breakout_period = 15  # 缩短突破周期
    volume_multiplier = 1.2  # 降低成交量乘数
    rsi_oversold = 40  # RSI超卖阈值

    def informative_pairs(self):
        return [("BTC/USDT", self.timeframe)]

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # 计算关键指标
        dataframe["sma_15"] = ta.SMA(dataframe, timeperiod=15)
        dataframe["sma_45"] = ta.SMA(dataframe, timeperiod=45)
        
        # RSI指标用于过滤
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        
        # 计算高低点突破
        dataframe["highest_high"] = dataframe["high"].rolling(self.breakout_period).max()
        dataframe["lowest_low"] = dataframe["low"].rolling(self.breakout_period).min()
        
        # 成交量平均
        dataframe["volume_mean"] = dataframe["volume"].rolling(20).mean()
        
        # 趋势判断
        dataframe["trend_up"] = dataframe["sma_15"] > dataframe["sma_45"]
        
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # 优化突破策略入场条件
        dataframe.loc[
            (
                # 价格突破15日高点
                (dataframe["close"] > dataframe["highest_high"].shift(1))
                # 成交量放大
                & (dataframe["volume"] > dataframe["volume_mean"] * self.volume_multiplier)
                # 上升趋势
                & (dataframe["trend_up"])
                # RSI不在超卖区域
                & (dataframe["rsi"] > self.rsi_oversold)
                # 确保有成交量
                & (dataframe["volume"] > 0)
            ),
            "enter_long"
        ] = 1

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # 优化退出条件
        dataframe.loc[
            (
                # 价格跌破15日低点
                (dataframe["close"] < dataframe["lowest_low"].shift(1))
                |
                # 价格跌破短期均线
                (dataframe["close"] < dataframe["sma_15"])
                |
                # RSI超买
                (dataframe["rsi"] > 75)
            ),
            "exit_long"
        ] = 1

        return dataframe