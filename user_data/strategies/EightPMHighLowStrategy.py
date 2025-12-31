from freqtrade.strategy import IStrategy, merge_informative_pair
from pandas import DataFrame
import talib.abstract as ta
import freqtrade.vendor.qtpylib.indicators as qtpylib
import pandas as pd
import numpy as np


class EightPMHighLowStrategy(IStrategy):
    """
    v2.4 进阶收益率优化版晚上8点高低点策略
    
    策略逻辑：
    - 以晚上8点为分界线判断当日高低点
    - 8点为最高点则做空，8点为最低点则做多
    - 等待价格确认后入场
    - 优化的止损止盈比例 (2.0% : 6.0%)
    - 专注高表现币种，移除低效币种
    
    v2.4 进阶优化重点：
    - 币种优化：移除BTC/SOL，新增AVAX/DOT/LINK
    - 参数统一：简化逻辑，移除复杂的币种差异化
    - 止损放宽：从1.5%放宽至2%，减少不必要止损
    - 止盈提升：初始止盈提升至6%，更积极的盈利目标
    - 仓位优化：ADA 2倍仓位，ETH 1.8倍仓位
    
    基于v2.3回测结果的针对性优化：
    - ADA表现最佳(81.8%胜率) → 最大仓位配置
    - ETH表现良好(70%胜率) → 较大仓位配置  
    - BTC表现差(-0.01%收益) → 移除
    - SOL收益低(0.02%收益) → 移除
    - 止损过多(12笔) → 放宽止损条件
    
    目标：在v2.3基础上进一步提升收益率至0.4%+
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

    # ========= 风险控制 v2.4 - 动态止损优化 =========
    stoploss = -0.02  # 放宽止损到2% (从1.5%放宽)
    
    minimal_roi = {
        "0": 0.06,    # 进一步提高初始止盈到6%
        "15": 0.045,  # 15分钟后降低到4.5%
        "30": 0.035,  # 30分钟后降低到3.5%
        "60": 0.025,  # 1小时后降低到2.5%
        "120": 0.02,  # 2小时后降低到2%
        "240": 0.015  # 4小时后降低到1.5%
    }

    # ========= 策略参数 v2.4 - 进阶收益率优化 =========
    volume_threshold = 1.02  # 进一步降低成交量要求 (从1.03改为1.02)
    confirmation_threshold = 0.0002  # 进一步降低价格确认阈值 (从0.0003改为0.0002)
    tolerance = 0.012  # 大幅放宽8点极值容差 (从0.01改为0.012)
    sma_range_pct = 0.12  # 大幅放宽均线范围 (从0.1改为0.12)
    
    # v2.4 新增参数 - 专注高收益优化
    trend_confirmation = False  # 保持关闭4小时趋势确认
    smart_exit = True  # 启用智能止盈止损
    
    # 移除BTC专用参数，统一使用优化参数
    # 专注于表现好的币种：ETH, ADA, AVAX, DOT, LINK

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
        
        # 8点极值判断 - 统一参数，专注高表现币种
        dataframe['is_daily_high_at_8pm'] = (
            dataframe['is_8pm'] & 
            (dataframe['high'] >= dataframe['daily_high'] * (1 - self.tolerance))
        )
        
        dataframe['is_daily_low_at_8pm'] = (
            dataframe['is_8pm'] & 
            (dataframe['low'] <= dataframe['daily_low'] * (1 + self.tolerance))
        )
        
        # 基础条件 - 统一优化参数
        base_long_conditions = [
            dataframe['is_daily_low_at_8pm'],
            (dataframe['volume_ratio'] > self.volume_threshold),
            (dataframe['rsi'] < 45)  # 放宽RSI条件
        ]
        
        base_short_conditions = [
            dataframe['is_daily_high_at_8pm'],
            (dataframe['volume_ratio'] > self.volume_threshold),
            (dataframe['rsi'] > 55)  # 放宽RSI条件
        ]
        
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
        入场信号 - v2.4 简化优化
        """
        # 统一使用放宽的均线过滤
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
    
    def custom_stake_amount(self, pair: str, current_time, current_rate: float,
                           proposed_stake: float, min_stake: float, max_stake: float,
                           leverage: float, entry_tag: str, side: str, **kwargs) -> float:
        """
        v2.4 优化仓位管理 - 专注高表现币种
        """
        # 基础仓位
        base_stake = proposed_stake
        
        # 根据币种历史表现调整仓位
        if 'ADA' in pair:
            # ADA表现最佳 (81.8%胜率) - 最大仓位
            stake_multiplier = 2.0
        elif 'ETH' in pair:
            # ETH表现良好 (70%胜率) - 较大仓位
            stake_multiplier = 1.8
        elif pair in ['AVAX/USDT:USDT', 'DOT/USDT:USDT', 'LINK/USDT:USDT']:
            # 新增币种 - 标准仓位
            stake_multiplier = 1.5
        else:
            # 其他币种 - 标准仓位
            stake_multiplier = 1.0
        
        # 根据当前持仓数量调整
        if hasattr(self, 'dp') and self.dp:
            try:
                current_trades = len([t for t in self.dp.current_whitelist() if t])
                if current_trades < 3:
                    # 持仓少时增加仓位
                    stake_multiplier *= 1.3
            except:
                pass
        
        final_stake = base_stake * stake_multiplier
        
        # 确保在允许范围内
        return max(min_stake, min(final_stake, max_stake))
    
    def custom_exit(self, pair: str, trade, current_time, current_rate: float,
                   current_profit: float, **kwargs) -> str:
        """
        v2.4 简化智能出场逻辑
        """
        if not self.smart_exit:
            return None
            
        # 获取当前数据
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if dataframe is None or len(dataframe) == 0:
            return None
            
        # 获取最新数据
        latest = dataframe.iloc[-1]
        
        # 基于RSI的动态出场 - 统一阈值
        if trade.is_short and latest['rsi'] < 25:
            return "rsi_oversold"
        elif not trade.is_short and latest['rsi'] > 75:
            return "rsi_overbought"
        
        # 基于持仓时间的出场 - 统一逻辑
        trade_duration = (current_time - trade.open_date_utc).total_seconds() / 3600
        
        # 统一时间管理
        if trade_duration > 20 and current_profit > 0.008:  # 20小时后0.8%盈利就出场
            return "time_profit_exit"
        if trade_duration > 40:  # 40小时强制平仓
            return "max_time_exit"
        
        return None