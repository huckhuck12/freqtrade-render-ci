from freqtrade.strategy import IStrategy

class OneFiveTrendHTF(IStrategy):
    timeframe = "5m"

    minimal_roi = {
        "0": 0.1
    }

    stoploss = -0.15

    def populate_indicators(self, dataframe, metadata):
        return dataframe

    def populate_entry_trend(self, dataframe, metadata):
        dataframe["enter_long"] = 0
        return dataframe

    def populate_exit_trend(self, dataframe, metadata):
        dataframe["exit_long"] = 0
        return dataframe
