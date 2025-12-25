from freqtrade.strategy import IStrategy
from pandas import DataFrame
import talib.abstract as ta
import freqtrade.vendor.qtpylib.indicators as qtpylib


class SimplifiedArbitrage(IStrategy):
    """
    Optimized mean reversion strategy with improved filtering and exit conditions
    """
    timeframe = "1m"
    can_short = False
    startup_candle_count = 100
    process_only_new_candles = True

    # 优化风险参数
    stoploss = -0.015  # 收紧止损，控制单次亏损
    minimal_roi = {
        "0": 0.01,  # 提高盈利目标，过滤微利交易
        "30": 0.005,
        "60": 0
    }

    # 优化均值回归参数
    ma_period = 60  # 增加移动平均线周期，减少噪声
    std_dev = 2.0  # 增加标准差倍数，减少交易频率
    rsi_overbought = 70  # 恢复标准超买阈值
    rsi_oversold = 30  # 恢复标准超卖阈值
    rsi_period = 14
    # 新增参数
    atr_period = 14
    atr_multiplier = 1.5
    volume_threshold = 1.5  # 成交量倍数阈值

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
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=self.rsi_period)
        
        # ATR指标，用于动态过滤
        dataframe["atr"] = ta.ATR(dataframe, timeperiod=self.atr_period)
        
        # 成交量指标
        dataframe["volume_ma"] = ta.SMA(dataframe["volume"], timeperiod=20)
        dataframe["volume_ratio"] = dataframe["volume"] / dataframe["volume_ma"]
        
        # 价格动量
        dataframe["momentum"] = ta.MOM(dataframe, timeperiod=5)
        
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # 严格的入场条件，减少交易次数
        dataframe.loc[
            (
                # 价格触及布林带下轨
                (dataframe["close"] < dataframe["lower_band"])
                # RSI超卖
                & (dataframe["rsi"] < self.rsi_oversold)
                # 成交量放大，确保市场参与度
                & (dataframe["volume_ratio"] > self.volume_threshold)
                # 动量反转，确保价格开始回升
                & (dataframe["momentum"] > dataframe["momentum"].shift(1))
                # 确保有成交量
                & (dataframe["volume"] > 0)
            ),
            "enter_long"
        ] = 1

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # 改进的退出条件
        dataframe.loc[
            (
                # 价格回到均线之上
                (dataframe["close"] > dataframe["ma"])
                # 或者RSI超买
                | (dataframe["rsi"] > self.rsi_overbought)
                # 或者价格触及布林带上轨
                | (dataframe["close"] > dataframe["upper_band"])
            ),
            "exit_long"
        ] = 1

        return dataframe