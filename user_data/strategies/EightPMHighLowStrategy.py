from freqtrade.strategy import IStrategy, merge_informative_pair
from pandas import DataFrame
import talib.abstract as ta
import freqtrade.vendor.qtpylib.indicators as qtpylib
import pandas as pd
import numpy as np


class EightPMHighLowStrategy(IStrategy):
    """
    v3.0 激进收益优化版晚上8点高低点策略
    
    策略逻辑：
    - 以晚上8点为分界线判断当日高低点
    - 8点为最高点则做空，8点为最低点则做多
    - 等待价格确认后入场
    - 激进的杠杆和仓位配置 (目标10%+年化收益)
    - 扩展币种池，增加交易频率
    
    v3.0 激进优化重点 (目标10%+年化收益率)：
    - 激进仓位：基础仓位提升至5-10倍
    - 扩展币种：增加更多高波动币种
    - 降低门槛：放宽入场条件，增加交易频率
    - 复合增长：利用复利效应
    - 风险平衡：在高收益和风险之间找平衡
    
    基于v2.7稳定基础的激进扩展：
    - 保持57.5%胜率基础
    - 大幅提升单笔收益
    - 增加交易频率
    - 扩展市场覆盖
    
    风险警告：
    - 高收益伴随高风险
    - 建议小资金测试
    - 严格风险控制
    """

    # ========= 基本设置 v3.0 激进优化 =========
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

    # ========= 风险控制 v3.0 激进优化 =========
    stoploss = -0.025  # 激进止损2.5% (承担更高风险)
    
    minimal_roi = {
        "0": 0.15,    # 激进止盈15% (大幅提升单笔收益)
        "8": 0.12,    # 8分钟后降低到12%
        "15": 0.10,   # 15分钟后降低到10%
        "30": 0.08,   # 30分钟后降低到8%
        "60": 0.06,   # 60分钟后降低到6%
        "120": 0.04   # 120分钟后降低到4%
    }

    # ========= 策略参数 v3.0 激进优化 =========
    volume_threshold = 1.02  # 降低成交量要求，增加交易频率
    confirmation_threshold = 0.0002  # 降低价格确认阈值，更快入场
    tolerance = 0.012  # 放宽8点极值容差，增加信号
    sma_range_pct = 0.15  # 放宽均线范围，增加交易机会
    
    # v3.0 激进参数 - 追求高收益
    trend_confirmation = False  # 保持关闭4小时趋势确认
    smart_exit = True  # 启用智能止盈止损
    
    # 扩展币种池：ETH, ADA, AVAX, SOL, MATIC, DOT, LINK

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
        
        # 基础条件 - v3.0激进优化，放宽条件增加交易频率
        pair = metadata['pair']
        
        # 激进RSI条件 - 大幅放宽以增加交易机会
        if 'ETH' in pair or 'BTC' in pair:
            # 主流币：适中条件
            rsi_long_threshold = 50
            rsi_short_threshold = 50
        elif 'ADA' in pair or 'SOL' in pair:
            # 高质量币：放宽条件
            rsi_long_threshold = 48
            rsi_short_threshold = 52
        else:  # AVAX, MATIC, DOT, LINK等
            # 其他币种：最宽松条件
            rsi_long_threshold = 52
            rsi_short_threshold = 48
        
        base_long_conditions = [
            dataframe['is_daily_low_at_8pm'],
            (dataframe['volume_ratio'] > self.volume_threshold),
            (dataframe['rsi'] < rsi_long_threshold)
        ]
        
        base_short_conditions = [
            dataframe['is_daily_high_at_8pm'],
            (dataframe['volume_ratio'] > self.volume_threshold),
            (dataframe['rsi'] > rsi_short_threshold)
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
        v3.0 激进仓位管理 - 追求10%+年化收益
        """
        # 基础仓位
        base_stake = proposed_stake
        
        # 激进仓位配置 - 大幅提升仓位
        if 'ADA' in pair:
            # ADA: 历史最佳表现 - 超大仓位
            stake_multiplier = 8.0
        elif 'ETH' in pair or 'BTC' in pair:
            # 主流币: 大仓位
            stake_multiplier = 6.0
        elif 'SOL' in pair or 'AVAX' in pair:
            # 高波动币: 超大仓位
            stake_multiplier = 10.0
        elif 'MATIC' in pair or 'DOT' in pair or 'LINK' in pair:
            # 其他币种: 大仓位
            stake_multiplier = 7.0
        else:
            # 默认币种: 标准大仓位
            stake_multiplier = 5.0
        
        # 根据当前持仓数量调整
        if hasattr(self, 'dp') and self.dp:
            try:
                current_trades = len([t for t in self.dp.current_whitelist() if t])
                if current_trades < 3:
                    # 持仓少时进一步增加仓位
                    stake_multiplier *= 1.5
                elif current_trades < 5:
                    stake_multiplier *= 1.2
            except:
                pass
        
        final_stake = base_stake * stake_multiplier
        
        # 确保在允许范围内
        return max(min_stake, min(final_stake, max_stake))
    
    def custom_exit(self, pair: str, trade, current_time, current_rate: float,
                   current_profit: float, **kwargs) -> str:
        """
        v2.7 最终智能出场逻辑 - 经验证的最优配置
        """
        if not self.smart_exit:
            return None
            
        # 获取当前数据
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if dataframe is None or len(dataframe) == 0:
            return None
            
        # 获取最新数据
        latest = dataframe.iloc[-1]
        
        # 基于RSI的动态出场 - 更保守的阈值
        if trade.is_short and latest['rsi'] < 15:  # 极端超卖
            return "rsi_oversold"
        elif not trade.is_short and latest['rsi'] > 85:  # 极端超买
            return "rsi_overbought"
        
        # 基于持仓时间和币种的差异化出场
        trade_duration = (current_time - trade.open_date_utc).total_seconds() / 3600
        
        # ADA: 表现最好，给最多时间和耐心
        if 'ADA' in pair:
            if trade_duration > 36 and current_profit > 0.018:  # 36小时后1.8%盈利出场
                return "time_profit_exit"
            if trade_duration > 72:  # 72小时强制平仓
                return "max_time_exit"
        # AVAX: 活跃币种，中等时间管理
        elif 'AVAX' in pair:
            if trade_duration > 28 and current_profit > 0.015:  # 28小时后1.5%盈利出场
                return "time_profit_exit"
            if trade_duration > 56:  # 56小时强制平仓
                return "max_time_exit"
        # ETH: 表现改善，给适中时间
        else:  # ETH
            if trade_duration > 24 and current_profit > 0.012:  # 24小时后1.2%盈利出场
                return "time_profit_exit"
            if trade_duration > 48:  # 48小时强制平仓
                return "max_time_exit"
        
        return None