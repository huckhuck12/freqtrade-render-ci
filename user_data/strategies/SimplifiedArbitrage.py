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

    # 降低风险参数
    stoploss = -0.02
    minimal_roi = {
        "0": 0.01,
        "30": 0.005,
        "60": 0
    }

    # 简化的参数设置
    arbitrage_threshold = 0.001  # 进一步降低阈值到 0.1%
    volume_filter = 0.1  # 极低的成交量过滤

    def informative_pairs(self):
        return [("BTC/USDT", self.timeframe)]

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # 获取BTC/USDT数据
        try:
            btc = self.dp.get_pair_dataframe("BTC/USDT", self.timeframe)
            dataframe["btc_price"] = btc["close"]
            
            # 模拟ETH/BTC比率（使用固定值或简单计算）
            # 假设ETH约为BTC的0.06倍
            dataframe["eth_btc_ratio"] = 0.06
            
            # 计算理论ETH价格
            dataframe["theoretical_eth"] = dataframe["btc_price"] * dataframe["eth_btc_ratio"]
            
            # 计算价格差异百分比
            dataframe["price_diff_pct"] = (dataframe["theoretical_eth"] - dataframe["close"]) / dataframe["close"]
            
            # 添加简单的趋势指标
            dataframe["sma_short"] = ta.SMA(dataframe, timeperiod=10)
            dataframe["sma_long"] = ta.SMA(dataframe, timeperiod=30)
            dataframe["trend"] = dataframe["sma_short"] > dataframe["sma_long"]
            
            # 成交量过滤
            dataframe["volume_mean"] = dataframe["volume"].rolling(20).mean()
            dataframe["volume_ok"] = dataframe["volume"] > dataframe["volume_mean"] * self.volume_filter
            
        except Exception as e:
            # 如果获取数据失败，创建基础指标
            dataframe["price_diff_pct"] = 0.0
            dataframe["trend"] = True
            dataframe["volume_ok"] = True

        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (
                # 套利机会：理论价格高于实际价格
                (dataframe["price_diff_pct"] > self.arbitrage_threshold)
                & (dataframe["volume_ok"])
                & (dataframe["trend"])
                & (dataframe["volume"] > 0)
            ),
            "enter_long"
        ] = 1

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (
                # 套利机会消失
                (dataframe["price_diff_pct"] < 0)
                |
                # 趋势反转
                (dataframe["sma_short"] < dataframe["sma_long"])
            ),
            "exit_long"
        ] = 1

        return dataframe