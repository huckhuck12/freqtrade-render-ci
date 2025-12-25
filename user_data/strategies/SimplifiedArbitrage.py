from freqtrade.strategy import IStrategy
from pandas import DataFrame
import talib.abstract as ta
import freqtrade.vendor.qtpylib.indicators as qtpylib


class SimplifiedArbitrage(IStrategy):
    """
    Simplified triangular arbitrage strategy
    """
    timeframe = "1m"
    can_short = False
    startup_candle_count = 100
    process_only_new_candles = True

    # 优化风险参数
    stoploss = -0.015  # 更严格的止损
    minimal_roi = {
        "0": 0.008,  # 降低盈利目标
        "20": 0.004,
        "40": 0
    }

    # 优化的参数设置
    arbitrage_threshold = 0.003  # 提高阈值到 0.3%，减少无效信号
    volume_filter = 0.5  # 提高成交量过滤，确保流动性
    win_rate_target = 0.4  # 胜率目标

    def informative_pairs(self):
        return [("BTC/USDT", self.timeframe)]

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # 改进的指标计算，移除固定比率假设
        # 使用价格动量和趋势指标替代套利逻辑
        
        # 添加技术指标
        dataframe["sma_20"] = ta.SMA(dataframe, timeperiod=20)
        dataframe["sma_50"] = ta.SMA(dataframe, timeperiod=50)
        dataframe["ema_10"] = ta.EMA(dataframe, timeperiod=10)
        dataframe["ema_20"] = ta.EMA(dataframe, timeperiod=20)
        
        # 计算RSI指标
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        
        # 计算MACD指标
        macd = ta.MACD(dataframe)
        dataframe["macd"] = macd["macd"]
        dataframe["macdsignal"] = macd["macdsignal"]
        dataframe["macdhist"] = macd["macdhist"]
        
        # 计算ATR指标
        dataframe["atr"] = ta.ATR(dataframe, timeperiod=14)
        
        # 趋势判断
        dataframe["trend_up"] = (
            (dataframe["ema_10"] > dataframe["ema_20"])
            & (dataframe["sma_20"] > dataframe["sma_50"])
        )
        
        # 成交量过滤
        dataframe["volume_mean"] = dataframe["volume"].rolling(20).mean()
        dataframe["volume_ok"] = dataframe["volume"] > dataframe["volume_mean"] * self.volume_filter
        
        # 价格动量
        dataframe["price_change_pct"] = dataframe["close"].pct_change(5) * 100
        
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (
                # 趋势向上
                (dataframe["trend_up"])
                & (dataframe["volume_ok"])
                & (dataframe["volume"] > 0)
                # RSI在正常范围内
                & (dataframe["rsi"] > 40)
                & (dataframe["rsi"] < 70)
                # MACD信号
                & (dataframe["macd"] > dataframe["macdsignal"])
                & (dataframe["macdhist"] > 0)
                # 价格有正动量
                & (dataframe["price_change_pct"] > 0)
            ),
            "enter_long"
        ] = 1

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (
                # 趋势反转
                (dataframe["ema_10"] < dataframe["ema_20"])
                |
                # RSI超买
                (dataframe["rsi"] > 75)
                |
                # MACD信号反转
                (dataframe["macd"] < dataframe["macdsignal"])
                |
                # 价格动量转为负
                (dataframe["price_change_pct"] < -0.5)
            ),
            "exit_long"
        ] = 1

        return dataframe