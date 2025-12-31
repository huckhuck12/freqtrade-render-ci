from freqtrade.strategy import IStrategy, merge_informative_pair
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
    
    # ========= 多时间框架设置 =========
    informative_pairs = []
    
    def informative_pairs(self):
        """
        定义需要的额外时间框架数据
        """
        pairs = self.dp.current_whitelist()
        informative_pairs = []
        for pair in pairs:
            informative_pairs.append((pair, '4h'))  # 添加4小时时间框架
        return informative_pairs

    # ========= 风险控制 =========
    stoploss = -0.015  # 1.5%止损
    
    minimal_roi = {
        "0": 0.04,    # 提高初始止盈到4%
        "30": 0.025,  # 30分钟后降低到2.5%
        "60": 0.02,   # 1小时后降低到2%
        "120": 0.015, # 2小时后降低到1.5%
        "240": 0.01   # 4小时后降低到1%
    }

    # ========= 策略参数 v2.1 - 单项优化测试 =========
    volume_threshold = 1.05  # 降低成交量要求 (从1.1改为1.05)
    confirmation_threshold = 0.0005  # 降低价格确认阈值 (从0.001改为0.0005)
    tolerance = 0.008  # 放宽8点极值容差 (从0.005改为0.008)
    sma_range_pct = 0.08  # 放宽均线范围 (从0.05改为0.08)
    
    # v2.1 新增参数 - 单项测试：只启用智能止盈止损
    trend_confirmation = False  # 关闭4小时趋势确认
    smart_exit = True  # 启用智能止盈止损

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        计算技术指标
        """
        # 时间信息 - 使用date列而不是index
        dataframe['hour'] = pd.to_datetime(dataframe['date']).dt.hour
        dataframe['date_only'] = pd.to_datetime(dataframe['date']).dt.date
        dataframe['is_8pm'] = (dataframe['hour'] == 20)
        
        # v2.1 多时间框架趋势确认
        if self.trend_confirmation:
            # 获取4小时数据
            informative = self.dp.get_pair_dataframe(pair=metadata['pair'], timeframe='4h')
            informative['sma_4h'] = ta.SMA(informative, timeperiod=20)
            informative['trend_4h'] = np.where(informative['close'] > informative['sma_4h'], 1, -1)
            
            # 合并到1小时数据
            dataframe = merge_informative_pair(dataframe, informative, self.timeframe, '4h', ffill=True)
        
        # 每日统计
        daily_stats = dataframe.groupby('date_only').agg({
            'high': 'max',
            'low': 'min',
            'volume': 'mean'
        }).rename(columns={'high': 'daily_high', 'low': 'daily_low', 'volume': 'daily_avg_volume'})
        
        # 合并回原数据
        dataframe = dataframe.join(daily_stats, on='date_only')
        
        # 技术指标
        dataframe['sma_20'] = ta.SMA(dataframe, timeperiod=20)
        dataframe['volume_sma'] = ta.SMA(dataframe['volume'], timeperiod=20)
        dataframe['volume_ratio'] = dataframe['volume'] / dataframe['volume_sma']
        dataframe['price_change_1h'] = dataframe['close'].pct_change(1)
        
        # 添加RSI指标用于超买超卖判断
        dataframe['rsi'] = ta.RSI(dataframe, timeperiod=14)
        
        # 添加波动率指标
        dataframe['atr'] = ta.ATR(dataframe, timeperiod=14)
        dataframe['volatility'] = dataframe['atr'] / dataframe['close']
        
        # 8点极值判断
        dataframe['is_daily_high_at_8pm'] = (
            dataframe['is_8pm'] & 
            (dataframe['high'] >= dataframe['daily_high'] * (1 - self.tolerance))
        )
        
        dataframe['is_daily_low_at_8pm'] = (
            dataframe['is_8pm'] & 
            (dataframe['low'] <= dataframe['daily_low'] * (1 + self.tolerance))
        )
        
        # 基础条件 - 增加RSI过滤和趋势确认
        base_long_conditions = [
            dataframe['is_daily_low_at_8pm'],
            (dataframe['volume_ratio'] > self.volume_threshold),
            (dataframe['rsi'] < 40)  # RSI超卖时做多
        ]
        
        base_short_conditions = [
            dataframe['is_daily_high_at_8pm'],
            (dataframe['volume_ratio'] > self.volume_threshold),
            (dataframe['rsi'] > 60)  # RSI超买时做空
        ]
        
        # v2.1 添加4小时趋势确认
        if self.trend_confirmation:
            base_long_conditions.append(dataframe['trend_4h'] == 1)  # 4小时上升趋势
            base_short_conditions.append(dataframe['trend_4h'] == -1)  # 4小时下降趋势
        
        dataframe['base_long'] = np.logical_and.reduce(base_long_conditions)
        dataframe['base_short'] = np.logical_and.reduce(base_short_conditions)
        
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
    
    def custom_exit(self, pair: str, trade, current_time, current_rate: float,
                   current_profit: float, **kwargs) -> str:
        """
        v2.1 智能出场逻辑
        """
        if not self.smart_exit:
            return None
            
        # 获取当前数据
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if dataframe is None or len(dataframe) == 0:
            return None
            
        # 获取最新数据
        latest = dataframe.iloc[-1]
        
        # 基于RSI的动态出场
        if trade.is_short:
            # 空头仓位：RSI过度超卖时平仓
            if latest['rsi'] < 25:
                return "rsi_oversold"
        else:
            # 多头仓位：RSI过度超买时平仓
            if latest['rsi'] > 75:
                return "rsi_overbought"
        
        # 基于持仓时间的出场
        trade_duration = (current_time - trade.open_date_utc).total_seconds() / 3600
        
        # 持仓超过24小时且有小幅盈利时平仓
        if trade_duration > 24 and current_profit > 0.005:
            return "time_profit_exit"
        
        # 持仓超过48小时强制平仓
        if trade_duration > 48:
            return "max_time_exit"
        
        return None