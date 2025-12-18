from freqtrade.strategy import IStrategy
from pandas import DataFrame
import talib.abstract as ta
import freqtrade.vendor.qtpylib.indicators as qtpylib


class OneFiveTrendHTF(IStrategy):
    """
    OneFiveTrendHTF
    - 主周期：5m
    - HTF：15m
    - 仅做多
    - HTF 趋势过滤 + LTF 回调进场
    """

    # ========= 基本参数 =========
    timeframe = "5m"
    informative_timeframe = "15m"

    startup_candle_count = 100
    process_only_new_candles = True

    # ========= 风控 =========
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

    # ========= 只做多 =========
    can_short = False

    # ========= HTF =========
    def informative_pairs(self):
        return [
            (pair, self.informative_timeframe)
            for pair in self.dp.current_whitelist()
        ]

    # ========= 指标 =========
    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:

        # --- LTF (5m) ---
        dataframe["ema20"] = ta.EMA(dataframe, timeperiod=20)
        dataframe["ema50"] = ta.EMA(dataframe, timeperiod=50)
        dataframe["adx"] = ta.ADX(dataframe, timeperiod=14)

        # --- HTF (15m) ---
        inf = self.dp.get_pair_dataframe(
            pair=metadata["pair"],
            timeframe=self.informative_timeframe
        )

        inf["ema50"] = ta.EMA(inf, timeperiod=50)
        inf["ema200"] = ta.EMA(inf, timeperiod=200)
        inf["adx"] = ta.ADX(inf, timeperiod=14)

        dataframe = dataframe.merge(
            inf[["ema50", "ema200", "adx"]],
            how="left",
            left_on="date",
            right_on="date",
            suffixes=("", "_15m")
        )

        dataframe.fillna(method="ffill", inplace=True)
        return dataframe

    # ========= 进场逻辑 =========
    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:

        dataframe.loc[
            (
                # --- HTF 多头趋势 ---
                (dataframe["ema50_15m"] > dataframe["ema200_15m"]) &
                (dataframe["adx_15m"] > 20)

                &

                # --- LTF 回调 ---
                (dataframe["ema20"] > dataframe["ema50"]) &
                (qtpylib.crossed_above(dataframe["close"], dataframe["ema20"])) &
                (dataframe["adx"] > 20)
            ),
            "enter_long"
        ] = 1

        return dataframe

    # ========= 出场逻辑 =========
    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:

        dataframe.loc[
            (
                # LTF 趋势走弱
                (qtpylib.crossed_below(dataframe["close"], dataframe["ema50"])) |
                (dataframe["adx"] < 15)
            ),
            "exit_long"
        ] = 1

        return dataframe
