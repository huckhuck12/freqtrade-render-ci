from freqtrade.strategy import IStrategy
from pandas import DataFrame
import pandas as pd

# ❌ 不再使用 TA-Lib（CI 环境不稳定）
# import talib.abstract as ta

# ✅ 使用 freqtrade 自带的 qtpylib（CI 已内置）
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
        # CI / Backtest 安全保护
        if not hasattr(self, "dp") or self.dp is None:
            return []

        return [
            (pair, self.informative_timeframe)
            for pair in self.dp.current_whitelist()
        ]

    # ========= 指标 =========
    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:

        if dataframe.empty:
            return dataframe

        # ===== LTF (5m) =====
        dataframe["ema20"] = qtpylib.ema(dataframe["close"], window=20)
        dataframe["ema50"] = qtpylib.ema(dataframe["close"], window=50)
        dataframe["adx"] = qtpylib.adx(dataframe)

        # ===== HTF (15m) =====
        if not hasattr(self, "dp") or self.dp is None:
            return dataframe

        inf = self.dp.get_pair_dataframe(
            pair=metadata["pair"],
            timeframe=self.informative_timeframe
        )

        if inf is None or inf.empty:
            return dataframe

        inf["ema50"] = qtpylib.ema(inf["close"], window=50)
        inf["ema200"] = qtpylib.ema(inf["close"], window=200)
        inf["adx"] = qtpylib.adx(inf)

        # 合并 HTF → LTF
        dataframe = dataframe.merge(
            inf[["date", "ema50", "ema200", "adx"]],
            how="left",
            on="date",
            suffixes=("", "_15m")
        )

        dataframe.fillna(method="ffill", inplace=True)
        return dataframe

    # ========= 进场逻辑 =========
    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:

        if dataframe.empty:
            return dataframe

        dataframe["enter_long"] = 0

        dataframe.loc[
            (
                # ===== HTF 多头趋势 =====
                (dataframe["ema50_15m"] > dataframe["ema200_15m"]) &
                (dataframe["adx_15m"] > 20)

                &

                # ===== LTF 回调 =====
                (dataframe["ema20"] > dataframe["ema50"]) &
                (qtpylib.crossed_above(dataframe["close"], dataframe["ema20"])) &
                (dataframe["adx"] > 20)
            ),
            "enter_long"
        ] = 1

        return dataframe

    # ========= 出场逻辑 =========
    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:

        if dataframe.empty:
            return dataframe

        dataframe["exit_long"] = 0

        dataframe.loc[
            (
                (qtpylib.crossed_below(dataframe["close"], dataframe["ema50"])) |
                (dataframe["adx"] < 15)
            ),
            "exit_long"
        ] = 1

        return dataframe
