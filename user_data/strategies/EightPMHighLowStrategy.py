from freqtrade.strategy import IStrategy, merge_informative_pair
from pandas import DataFrame
import talib.abstract as ta
import freqtrade.vendor.qtpylib.indicators as qtpylib
import pandas as pd
import numpy as np


class EightPMHighLowStrategy(IStrategy):
    """
    v2.2 优化版晚上8点高低点策略 - BTC适度优化
    
    策略逻辑：
    - 以晚上8点为分界线判断当日高低点
    - 8点为最高点则做空，8点为最低点则做多
    - 等待价格确认后入场
    - 优化的止损止盈比例 (1.5% : 4.0%)
    - 针对BTC的适度优化参数
    
    v2.2 优化重点：
    - 暂时关闭4小时趋势确认 (缺少4h数据)
    - BTC适度优化：避免过滤过严导致无信号
    - 保持ETH优秀表现的同时提升BTC胜率
    - 智能出场：BTC使用更保守的时间和RSI阈值
    
    参数调整：
    - BTC成交量阈值：1.08 (适度提高)
    - BTC RSI阈值：38/62 (适度严格)
    - BTC波动率要求：>1% (适度降低)
    - BTC均线范围：6% (适度放宽)
    
    目标：在保证信号数量的前提下提升BTC胜率
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
        if self.trend_confirmation:
            pairs = self.dp.current_whitelist()
            informative_pairs = []
            for pair in pairs:
                informative_pairs.append((pair, '4h'))  # 添加4小时时间框架
            return informative_pairs
        return []

    # ========= 风险控制 =========
    stoploss = -0.015  # 1.5%止损
    
    minimal_roi = {
        "0": 0.04,    # 提高初始止盈到4%
        "30": 0.025,  # 30分钟后降低到2.5%
        "60": 0.02,   # 1小时后降低到2%
        "120": 0.015, # 2小时后降低到1.5%
        "240": 0.01   # 4小时后降低到1%
    }

    # ========= 策略参数 v2.2 - BTC优化 + 4小时趋势确认 =========
    volume_threshold = 1.05  # 降低成交量要求 (从1.1改为1.05)
    confirmation_threshold = 0.0005  # 降低价格确认阈值 (从0.001改为0.0005)
    tolerance = 0.008  # 放宽8点极值容差 (从0.005改为0.008)
    sma_range_pct = 0.08  # 放宽均线范围 (从0.05改为0.08)
    
    # v2.2 新增参数 - 暂时关闭4小时趋势确认，专注BTC优化
    trend_confirmation = False  # 暂时关闭4小时趋势确认 (缺少4h数据)
    smart_exit = True  # 启用智能止盈止损
    
    # BTC专用参数 - 适度优化，避免过滤过严
    btc_volume_threshold = 1.08  # BTC成交量要求适度提高 (从1.15降至1.08)
    btc_tolerance = 0.007  # BTC极值容差适度严格 (从0.006放宽至0.007)
    btc_rsi_oversold = 38  # BTC RSI超卖阈值适度严格 (从35放宽至38)
    btc_rsi_overbought = 62  # BTC RSI超买阈值适度严格 (从65收紧至62)

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        计算技术指标
        """
        # 时间信息 - 使用date列而不是index
        dataframe['hour'] = pd.to_datetime(dataframe['date']).dt.hour
        dataframe['date_only'] = pd.to_datetime(dataframe['date']).dt.date
        dataframe['is_8pm'] = (dataframe['hour'] == 20)
        
        # v2.2 多时间框架趋势确认
        if self.trend_confirmation:
            # 获取4小时数据
            informative = self.dp.get_pair_dataframe(pair=metadata['pair'], timeframe='4h')
            if informative is not None and len(informative) > 0:
                informative['sma_4h'] = ta.SMA(informative, timeperiod=20)
                informative['trend_4h'] = np.where(informative['close'] > informative['sma_4h'], 1, -1)
                
                # 合并到1小时数据 - 注意列名会有后缀
                dataframe = merge_informative_pair(dataframe, informative, self.timeframe, '4h', ffill=True)
            else:
                # 如果没有4小时数据，创建默认值
                dataframe['trend_4h_4h'] = 0
        
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
        
        # 8点极值判断 - 针对BTC使用不同参数
        pair_name = metadata['pair']
        is_btc = 'BTC' in pair_name
        
        current_tolerance = self.btc_tolerance if is_btc else self.tolerance
        
        dataframe['is_daily_high_at_8pm'] = (
            dataframe['is_8pm'] & 
            (dataframe['high'] >= dataframe['daily_high'] * (1 - current_tolerance))
        )
        
        dataframe['is_daily_low_at_8pm'] = (
            dataframe['is_8pm'] & 
            (dataframe['low'] <= dataframe['daily_low'] * (1 + current_tolerance))
        )
        
        # 基础条件 - 针对BTC使用不同的RSI和成交量阈值
        current_volume_threshold = self.btc_volume_threshold if is_btc else self.volume_threshold
        rsi_oversold = self.btc_rsi_oversold if is_btc else 40
        rsi_overbought = self.btc_rsi_overbought if is_btc else 60
        
        base_long_conditions = [
            dataframe['is_daily_low_at_8pm'],
            (dataframe['volume_ratio'] > current_volume_threshold),
            (dataframe['rsi'] < rsi_oversold)  # 针对BTC使用更严格的RSI
        ]
        
        base_short_conditions = [
            dataframe['is_daily_high_at_8pm'],
            (dataframe['volume_ratio'] > current_volume_threshold),
            (dataframe['rsi'] > rsi_overbought)  # 针对BTC使用更严格的RSI
        ]
        
        # BTC额外过滤条件：适度添加波动率过滤
        if is_btc:
            # BTC需要适度的波动率才交易 (降低要求)
            base_long_conditions.append(dataframe['volatility'] > 0.01)  # 1%以上波动率 (从1.5%降至1%)
            base_short_conditions.append(dataframe['volatility'] > 0.01)
            
            # BTC使用适度严格的均线范围
            btc_sma_range = 0.06  # BTC使用6%范围 (从5%放宽至6%)
            base_long_conditions.append(
                abs(dataframe['close'] - dataframe['sma_20']) / dataframe['sma_20'] < btc_sma_range
            )
            base_short_conditions.append(
                abs(dataframe['close'] - dataframe['sma_20']) / dataframe['sma_20'] < btc_sma_range
            )
        
        # v2.2 添加4小时趋势确认 (现已启用)
        if self.trend_confirmation:
            # 使用正确的列名 (merge_informative_pair会添加后缀)
            trend_column = 'trend_4h_4h'
            if trend_column in dataframe.columns:
                base_long_conditions.append(dataframe[trend_column] == 1)  # 4小时上升趋势
                base_short_conditions.append(dataframe[trend_column] == -1)  # 4小时下降趋势
            else:
                # 如果没有趋势数据，不添加趋势过滤
                pass
        
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
        入场信号 - v2.2 针对BTC适度优化
        """
        pair_name = metadata['pair']
        is_btc = 'BTC' in pair_name
        
        # 针对BTC使用适度严格的均线过滤
        if is_btc:
            near_sma_condition = (
                abs(dataframe['close'] - dataframe['sma_20']) / dataframe['sma_20'] < 0.06  # 从5%放宽至6%
            )
        else:
            near_sma_condition = dataframe['near_sma']
        
        # 做多信号
        dataframe.loc[
            (
                dataframe['confirmed_long'] &
                near_sma_condition &
                (dataframe['volume'] > 0)
            ),
            'enter_long'
        ] = 1
        
        # 做空信号
        dataframe.loc[
            (
                dataframe['confirmed_short'] &
                near_sma_condition &
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
        v2.2 智能出场逻辑 - 针对BTC优化
        """
        if not self.smart_exit:
            return None
            
        # 获取当前数据
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if dataframe is None or len(dataframe) == 0:
            return None
            
        # 获取最新数据
        latest = dataframe.iloc[-1]
        is_btc = 'BTC' in pair
        
        # 基于RSI的动态出场 - BTC使用不同阈值
        if is_btc:
            # BTC使用更保守的RSI出场阈值
            if trade.is_short and latest['rsi'] < 30:
                return "rsi_oversold"
            elif not trade.is_short and latest['rsi'] > 70:
                return "rsi_overbought"
        else:
            # ETH使用原有阈值
            if trade.is_short and latest['rsi'] < 25:
                return "rsi_oversold"
            elif not trade.is_short and latest['rsi'] > 75:
                return "rsi_overbought"
        
        # 基于持仓时间的出场 - BTC使用更短的持仓时间
        trade_duration = (current_time - trade.open_date_utc).total_seconds() / 3600
        
        if is_btc:
            # BTC更快出场
            if trade_duration > 18 and current_profit > 0.003:  # 18小时后0.3%盈利就出场
                return "time_profit_exit"
            if trade_duration > 36:  # 36小时强制平仓
                return "max_time_exit"
        else:
            # ETH保持原有逻辑
            if trade_duration > 24 and current_profit > 0.005:
                return "time_profit_exit"
            if trade_duration > 48:
                return "max_time_exit"
        
        return None