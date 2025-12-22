from freqtrade.strategy import IStrategy
from pandas import DataFrame
import talib.abstract as ta
import freqtrade.vendor.qtpylib.indicators as qtpylib


class OneFiveTrendHTF(IStrategy):

    timeframe = "5m"
    informative_timeframe = "15m"

    startup_candle_count = 200
    process_only_new_candles = True
    can_short = False

    # ===== 风控 =====
    stoploss = -0.12

    minimal_roi = {
        "0": 0.06,
        "30": 0.03,
        "90": 0
    }

    trailing_stop = True
    trailing_stop_positive = 0.02
    trailing_stop_positive_offset = 0.04
    trailing_only_offset_is_reached = True

    # ===== HTF =====
    def informative_pairs(self):
        return [(pair, self.informative_timeframe)
                for pair in self.dp.current_whitelist()]

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:

        # === LTF ===
        dataframe["ema20"] = ta.EMA(dataframe, 20)
        dataframe["ema50"] = ta.EMA(dataframe, 50)
        dataframe["adx"] = ta.ADX(dataframe, 14)
        dataframe["atr"] = ta.ATR(dataframe, 14)
        dataframe["atr_pct"] = dataframe["atr"] / dataframe["close"]

        # === HTF ===
        inf = self.dp.get_pair_dataframe(
            metadata["pair"], self.informative_timeframe
        )

        inf["ema50"] = ta.EMA(inf, 50)
        inf["ema100"] = ta.EMA(inf, 100)
        inf["ema200"] = ta.EMA(inf, 200)
        inf["adx"] = ta.ADX(inf, 14)

        dataframe = dataframe.merge(
            inf[["ema50", "ema100", "ema200", "adx"]],
            left_on="date",
            right_on="date",
            how="left",
            suffixes=("", "_15m")
        )

        dataframe.ffill(inplace=True)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:

        dataframe.loc[
            (
                # ===== HTF 强趋势 =====
                (dataframe["ema50_15m"] > dataframe["ema100_15m"]) &
                (dataframe["ema100_15m"] > dataframe["ema200_15m"]) &
                (dataframe["adx_15m"] > 30)

                &

                # ===== LTF 回调 =====
                (dataframe["close"] > dataframe["ema50"]) &
                (dataframe["low"] < dataframe["ema20"]) &
                (dataframe["close"] > dataframe["ema20"]) &
                (dataframe["adx"] > 25)

                &

                # ===== 排除低波动震荡 =====
                (dataframe["atr_pct"] > 0.002)
            ),
            "enter_long"
        ] = 1

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:

        dataframe.loc[
            (
                qtpylib.crossed_below(dataframe["close"], dataframe["ema50"]) |
                (dataframe["adx"] < 20)
            ),
            "exit_long"
        ] = 1

        return dataframe
