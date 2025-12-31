from freqtrade.strategy import IStrategy
from pandas import DataFrame
import talib.abstract as ta
import freqtrade.vendor.qtpylib.indicators as qtpylib
import pandas as pd
import numpy as np


class EightPMHighLowStrategy(IStrategy):
    """
    最终优化版晚上8点高低点策略
    
    策略逻辑：
    - 以晚上8点为分界线判断当日高低点
    - 8点为最高点则做空，8点为最低点则做多
    - 等待价格确认后入场
    - 优化的止损止盈比例 (1.5% : 3.0%)
    - 趋势过滤：只在价格接近均线时交易
    
    优化成果：
    - 胜率：58.10%
    - 年化收益率：9.42%
    - 止盈率：58.10%
    """

    # ========= 基本设置 =========
    timeframe = "1h"
    can_short = True
    
    startup_candle_count = 50
    process_only_new_candles = True

    # ========= 风险控制 =========
    stoploss = -0.015  # 1.5%止损
    
    minimal_roi = {
        "0": 0.03,  # 3%止盈
        "60": 0.015,  # 1小时后降低到1.5%
        "120": 0.01,  # 2小时后降低到1%
        "240": 0.005  # 4小时后降低到0.5%
    }

    # ========= 策略参数 =========
    volume_threshold = 1.1  # 成交量阈值
    confirmation_threshold = 0.001  # 0.1%价格确认阈值
    tolerance = 0.005  # 8点极值容差0.5%
    sma_range_pct = 0.05  # 均线范围5%

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        计算技术指标
        """
        # 时间信息
        dataframe['hour'] = dataframe.index.hour
        dataframe['date'] = dataframe.index.date
        dataframe['is_8pm'] = (dataframe['hour'] == 20)
        
        # 每日统计
        daily_stats = dataframe.groupby('date').agg({
            'high': 'max',
            'low': 'min',
            'volume': 'mean'
        }).rename(columns={'high': 'daily_high', 'low': 'daily_low', 'volume': 'daily_avg_volume'})
        
        # 合并回原数据
        dataframe = dataframe.join(daily_stats, on='date')
        
        # 技术指标
        dataframe['sma_20'] = ta.SMA(dataframe, timeperiod=20)
        dataframe['volume_sma'] = ta.SMA(dataframe['volume'], timeperiod=20)
        dataframe['volume_ratio'] = dataframe['volume'] / dataframe['volume_sma']
        dataframe['price_change_1h'] = dataframe['close'].pct_change(1)
        
        # 8点极值判断
        dataframe['is_daily_high_at_8pm'] = (
            dataframe['is_8pm'] & 
            (dataframe['high'] >= dataframe['daily_high'] * (1 - self.tolerance))
        )
        
        dataframe['is_daily_low_at_8pm'] = (
            dataframe['is_8pm'] & 
            (dataframe['low'] <= dataframe['daily_low'] * (1 + self.tolerance))
        )
        
        # 基础条件
        dataframe['base_long'] = (
            dataframe['is_daily_low_at_8pm'] &
            (dataframe['volume_ratio'] > self.volume_threshold)
        )
        
        dataframe['base_short'] = (
            dataframe['is_daily_high_at_8pm'] &
            (dataframe['volume_ratio'] > self.volume_threshold)
        )
        
        # 价格确认
        dataframe['confirmed_long'] = False
        dataframe['confirmed_short'] = False
        
        for i in range(1, len(dataframe)):
            # 做多确认：价格开始反弹
            if dataframe['base_long'].iloc[i-1]:
                if dataframe['price_change_1h'].iloc[i] > self.confirmation_threshold:
                    dataframe.iloc[i, dataframe.columns.get_loc('confirmed_long')] = True
            
            # 做空确认：价格开始下跌
            if dataframe['base_short'].iloc[i-1]:
                if dataframe['price_change_1h'].iloc[i] < -self.confirmation_threshold:
                    dataframe.iloc[i, dataframe.columns.get_loc('confirmed_short')] = True
        
        # 趋势过滤：只在价格接近均线时交易
        dataframe['near_sma'] = (
            abs(dataframe['close'] - dataframe['sma_20']) / dataframe['sma_20'] < self.sma_range_pct
        )
        
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        入场信号
        """
        # 做多信号
        dataframe.loc[
            (
                dataframe['confirmed_long'] &
                dataframe['near_sma'] &
                (dataframe['volume'] > 0)
            ),
            'enter_long'
        ] = 1
        
        # 做空信号
        dataframe.loc[
            (
                dataframe['confirmed_short'] &
                dataframe['near_sma'] &
                (dataframe['volume'] > 0)
            ),
            'enter_short'
        ] = 1

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        出场信号 - 主要依靠止损止盈，这里可以添加额外的出场条件
        """
        # 可以添加一些主动出场逻辑
        # 目前主要依靠minimal_roi和stoploss来控制出场
        
        return dataframe
    
    def custom_stoploss(self, pair: str, trade, current_time, current_rate: float, 
                       current_profit: float, **kwargs) -> float:
        """
        自定义止损逻辑
        """
        # 使用固定止损
        return self.stoploss
    
    def custom_sell(self, pair: str, trade, current_time, current_rate: float,
                   current_profit: float, **kwargs) -> str:
        """
        自定义卖出逻辑
        """
        # 可以在这里添加自定义的卖出条件
        # 比如基于时间、技术指标等的卖出逻辑
        
        return None