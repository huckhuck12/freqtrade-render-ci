from freqtrade.strategy import IStrategy
from pandas import DataFrame
import talib.abstract as ta
import freqtrade.vendor.qtpylib.indicators as qtpylib


class SimplifiedArbitrage(IStrategy):
    """
    Simplified triangular arbitrage strategy - Optimized for lower risk
    """
    timeframe = "5m"  # 切换到5分钟周期，减少噪音
    can_short = False
    startup_candle_count = 200
    process_only_new_candles = True

    # 更保守的风险参数
    stoploss = -0.01  # 更严格的止损
    minimal_roi = {
        "0": 0.015,  # 提高盈利目标，只做高概率交易
        "60": 0.01,
        "120": 0.005
    }

    # 优化的参数设置
    volume_filter = 1.0  # 更高的成交量过滤，确保足够流动性
    volatility_threshold = 0.005  # 波动率阈值

    def informative_pairs(self):
        return [("BTC/USDT", self.timeframe)]

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # 只保留最有效的指标
        
        # 长期趋势指标（更稳定）
        dataframe["sma_50"] = ta.SMA(dataframe, timeperiod=50)
        dataframe["sma_100"] = ta.SMA(dataframe, timeperiod=100)
        dataframe["ema_20"] = ta.EMA(dataframe, timeperiod=20)
        dataframe["ema_50"] = ta.EMA(dataframe, timeperiod=50)
        
        # RSI指标 - 更稳定的周期
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=21)
        
        # MACD指标 - 标准参数
        macd = ta.MACD(dataframe, fastperiod=12, slowperiod=26, signalperiod=9)
        dataframe["macd"] = macd["macd"]
        dataframe["macdsignal"] = macd["macdsignal"]
        dataframe["macdhist"] = macd["macdhist"]
        
        # ATR指标用于波动率过滤
        dataframe["atr"] = ta.ATR(dataframe, timeperiod=14)
        dataframe["atr_pct"] = dataframe["atr"] / dataframe["close"] * 100
        
        # 严格的趋势判断
        dataframe["strong_trend_up"] = (
            (dataframe["ema_20"] > dataframe["ema_50"])
            & (dataframe["sma_50"] > dataframe["sma_100"])
            & (dataframe["close"] > dataframe["sma_50"])
        )
        
        # 成交量过滤 - 更严格
        dataframe["volume_mean_20"] = dataframe["volume"].rolling(20).mean()
        dataframe["volume_mean_50"] = dataframe["volume"].rolling(50).mean()
        dataframe["high_volume"] = (
            (dataframe["volume"] > dataframe["volume_mean_20"] * self.volume_filter)
            & (dataframe["volume"] > dataframe["volume_mean_50"] * 0.8)
        )
        
        # 波动率过滤
        dataframe["low_volatility"] = dataframe["atr_pct"] < self.volatility_threshold
        
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # 非常严格的入场条件，只做高概率交易
        dataframe.loc[
            (
                # 强烈的上升趋势
                (dataframe["strong_trend_up"])
                # 高成交量
                & (dataframe["high_volume"])
                # 低波动率环境
                & (dataframe["low_volatility"])
                # 健康的RSI范围（避免超买）
                & (dataframe["rsi"] > 50)
                & (dataframe["rsi"] < 70)
                # MACD金叉且柱状图为正
                & (dataframe["macd"] > dataframe["macdsignal"])
                & (dataframe["macdhist"] > 0)
                # MACD线为正
                & (dataframe["macd"] > 0)
                # 确保有实际成交量
                & (dataframe["volume"] > 0)
            ),
            "enter_long"
        ] = 1

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # 严格的退出条件，保护利润
        dataframe.loc[
            (
                # 趋势反转
                (dataframe["ema_20"] < dataframe["ema_50"])
                |
                # RSI超买
                (dataframe["rsi"] > 80)
                |
                # MACD死叉
                (dataframe["macd"] < dataframe["macdsignal"])
                |
                # MACD柱状图变负
                (dataframe["macdhist"] < 0)
                |
                # 价格跌破短期均线
                (dataframe["close"] < dataframe["ema_20"])
            ),
            "exit_long"
        ] = 1

        return dataframe