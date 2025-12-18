from freqtrade.strategy import IStrategy, merge_informative_pair
from pandas import DataFrame
import talib.abstract as ta
import freqtrade.vendor.qtpylib.indicators as qtpylib


class OneFiveTrendHTF(IStrategy):
    """
    OneFiveTrendHTF
    主周期: 5m
    HTF: 15m
    逻辑:
    - 15m EMA50 > EMA200 + ADX > 20 作为大趋势过滤
    - 5m 回调后再次上穿 EMA20 进场
    - 只做多
    """

    # ========= 基本设置 =========
    timeframe = "5m"
    informative_timeframe = "15m"

    startup_candle_count = 240
    process_only_new_candles = True

    # ========= 资金 & 风控 =========
    can_short = False
    stoploss = -0.15

    minimal_roi = {
        "0": 0.08,
        "30": 0.04,
        "60": 0
    }

    trailing_stop = True
    trailing_stop_positive = 0.015
    trailing_stop_positive_offset = 0.03
    trailing_only_offset_is_reached = True

    # ========= HTF pairs =========
    def informative_pairs(self):
        return [
            (pair, self.informative_timeframe)
            for pair in self.dp.current_whitelist()
        ]

    # ========= 指标 =========
    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # ===== LTF 5m =====
        dataframe["ema20"] = ta.EMA(dataframe, timeperiod=20)
        dataframe["ema50"] = ta.EMA(dataframe, timeperiod=50)
        dataframe["adx"] = ta.ADX(dataframe)

        # ===== HTF 15m =====
        informative = self.dp.get_pair_dataframe(
            pair=metadata["pair"],
            timeframe=self.informative_timeframe
        )

        informative["ema50"] = ta.EMA(informative, timeperiod=50)
        informative["ema200"] = ta.EMA(informative, timeperiod=200)
        informative["adx"] = ta.ADX(informative)

        # 合并 HTF 到 LTF
        dataframe = merge_informative_pair(
            dataframe,
            informative,
            self.timeframe,
            self.informative_timeframe,
            ffill=True
        )

        return dataframe

    # ========= 进场 =========
    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (
                # ===== HTF 多头趋势 =====
                (dataframe["ema50_15m"] > dataframe["ema200_15m"]) &
                (dataframe["adx_15m"] > 20)

                &

                # ===== LTF 回调后启动 =====
                (dataframe["ema20"] > dataframe["ema50"]) &
                (qtpylib.crossed_above(dataframe["close"], dataframe["ema20"])) &
                (dataframe["adx"] > 20)
            ),
            "enter_long"
        ] = 1

        return dataframe

    # ========= 出场 =========
    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (
                (qtpylib.crossed_below(dataframe["close"], dataframe["ema50"])) |
                (dataframe["adx"] < 15)
            ),
            "exit_long"
        ] = 1

        return dataframe
