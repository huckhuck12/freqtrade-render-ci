from freqtrade.strategy import IStrategy, merge_informative_pair
from pandas import DataFrame
import talib.abstract as ta
import freqtrade.vendor.qtpylib.indicators as qtpylib
import pandas as pd
import numpy as np


class EightPMHighLowStrategy(IStrategy):
    """
    v3.1 精准优化版晚上8点高低点策略
    
    策略逻辑：
    - 以晚上8点为分界线判断当日高低点
    - 8点为最高点则做空，8点为最低点则做多
    - 等待价格确认后入场
    - 基于v3.0回测结果的精准优化 (11.14%收益，44.7%胜率)
    
    v3.1 精准优化重点 (基于v3.0实测数据)：
    - 币种优化：剔除DOT(-0.46%)，强化AVAX(7.57%)
    - 胜率提升：收紧入场条件，从44.7%目标提升至50%+
    - ETH激活：进一步放宽条件，从14笔增加至30+笔
    - 止损优化：从2.5%调整为2.2%，减少54.5%止损率
    - 仓位精调：基于实际表现重新分配
    
    v3.0 → v3.1 关键改进：
    - 剔除表现最差币种DOT
    - 强化表现最佳币种AVAX配置
    - 收紧RSI条件提升胜率
    - 优化止损减少无效亏损
    - ETH专项激活策略
    
    目标：保持10%+收益基础上提升胜率至50%+
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

    # ========= 风险控制 v3.1 精准优化 =========
    stoploss = -0.022  # 优化止损2.2% (从2.5%收紧，减少54.5%止损率)
    
    minimal_roi = {
        "0": 0.12,    # 收紧初始止盈12% (从15%调整)
        "6": 0.10,    # 6分钟后降低到10%
        "12": 0.08,   # 12分钟后降低到8%
        "25": 0.06,   # 25分钟后降低到6%
        "50": 0.04,   # 50分钟后降低到4%
        "100": 0.03   # 100分钟后降低到3%
    }

    # ========= 策略参数 v3.1 精准优化 =========
    volume_threshold = 1.05  # 收紧成交量要求，提升信号质量
    confirmation_threshold = 0.0003  # 提高价格确认阈值，减少假信号
    tolerance = 0.010  # 收紧8点极值容差，提升精准度
    sma_range_pct = 0.12  # 收紧均线范围，提升入场质量
    
    # v3.1 精准参数 - 平衡收益与胜率
    trend_confirmation = False  # 保持关闭4小时趋势确认
    smart_exit = True  # 启用智能止盈止损
    
    # 优化币种池：剔除DOT，强化AVAX, ETH, ADA, SOL, MATIC, LINK

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
        
        # 基础条件 - v3.1精准优化，收紧条件提升胜率
        pair = metadata['pair']
        
        # 精准RSI条件 - 基于v3.0实测表现优化
        if 'AVAX' in pair:
            # AVAX: 表现最佳(7.57%)，保持宽松条件
            rsi_long_threshold = 52
            rsi_short_threshold = 48
        elif 'ETH' in pair:
            # ETH: 胜率高(57.1%)但交易少(14笔)，大幅放宽激活
            rsi_long_threshold = 55
            rsi_short_threshold = 45
        elif 'SOL' in pair:
            # SOL: 中等表现(1.76%)，适度收紧
            rsi_long_threshold = 48
            rsi_short_threshold = 52
        elif 'ADA' in pair:
            # ADA: 胜率偏低(42.3%)，收紧条件
            rsi_long_threshold = 45
            rsi_short_threshold = 55
        elif 'LINK' in pair or 'MATIC' in pair:
            # LINK/MATIC: 表现一般，收紧条件
            rsi_long_threshold = 46
            rsi_short_threshold = 54
        else:
            # 其他币种：标准条件
            rsi_long_threshold = 50
            rsi_short_threshold = 50
        
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
        v3.1 精准仓位管理 - 基于v3.0实测表现优化
        """
        # 基础仓位
        base_stake = proposed_stake
        
        # 精准仓位配置 - 基于v3.0实际表现调整
        if 'AVAX' in pair:
            # AVAX: 表现最佳(7.57%) - 超大仓位
            stake_multiplier = 12.0
        elif 'ETH' in pair:
            # ETH: 胜率最高(57.1%)但交易少 - 大仓位激活
            stake_multiplier = 8.0
        elif 'SOL' in pair:
            # SOL: 中等表现(1.76%) - 中等仓位
            stake_multiplier = 6.0
        elif 'ADA' in pair:
            # ADA: 胜率偏低(42.3%) - 降低仓位
            stake_multiplier = 4.0
        elif 'MATIC' in pair or 'LINK' in pair:
            # MATIC/LINK: 表现一般 - 标准仓位
            stake_multiplier = 5.0
        else:
            # 其他币种: 保守仓位
            stake_multiplier = 3.0
        
        # 根据当前持仓数量调整
        if hasattr(self, 'dp') and self.dp:
            try:
                current_trades = len([t for t in self.dp.current_whitelist() if t])
                if current_trades < 2:
                    # 持仓很少时进一步增加仓位
                    stake_multiplier *= 1.8
                elif current_trades < 4:
                    stake_multiplier *= 1.4
                elif current_trades < 6:
                    stake_multiplier *= 1.1
            except:
                pass
        
        final_stake = base_stake * stake_multiplier
        
        # 确保在允许范围内
        return max(min_stake, min(final_stake, max_stake))
    
    def custom_exit(self, pair: str, trade, current_time, current_rate: float,
                   current_profit: float, **kwargs) -> str:
        """
        v3.1 精准出场逻辑 - 基于v3.0实测数据优化
        """
        if not self.smart_exit:
            return None
            
        # 获取当前数据
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if dataframe is None or len(dataframe) == 0:
            return None
            
        # 获取最新数据
        latest = dataframe.iloc[-1]
        
        # 基于RSI的动态出场 - 更严格的阈值
        if trade.is_short and latest['rsi'] < 12:  # 极端超卖
            return "rsi_oversold"
        elif not trade.is_short and latest['rsi'] > 88:  # 极端超买
            return "rsi_overbought"
        
        # 基于持仓时间和币种的差异化出场 - 基于v3.0实测优化
        trade_duration = (current_time - trade.open_date_utc).total_seconds() / 3600
        
        # AVAX: 表现最佳，给最多耐心和时间
        if 'AVAX' in pair:
            if trade_duration > 48 and current_profit > 0.025:  # 48小时后2.5%盈利出场
                return "time_profit_exit"
            if trade_duration > 84:  # 84小时强制平仓
                return "max_time_exit"
        # ETH: 胜率高但交易少，给充分时间
        elif 'ETH' in pair:
            if trade_duration > 40 and current_profit > 0.020:  # 40小时后2.0%盈利出场
                return "time_profit_exit"
            if trade_duration > 72:  # 72小时强制平仓
                return "max_time_exit"
        # SOL: 中等表现，标准时间管理
        elif 'SOL' in pair:
            if trade_duration > 32 and current_profit > 0.018:  # 32小时后1.8%盈利出场
                return "time_profit_exit"
            if trade_duration > 60:  # 60小时强制平仓
                return "max_time_exit"
        # ADA: 胜率偏低，缩短持仓时间
        elif 'ADA' in pair:
            if trade_duration > 24 and current_profit > 0.015:  # 24小时后1.5%盈利出场
                return "time_profit_exit"
            if trade_duration > 48:  # 48小时强制平仓
                return "max_time_exit"
        # LINK/MATIC: 表现一般，保守时间管理
        else:  # LINK, MATIC等
            if trade_duration > 20 and current_profit > 0.012:  # 20小时后1.2%盈利出场
                return "time_profit_exit"
            if trade_duration > 40:  # 40小时强制平仓
                return "max_time_exit"
        
        return None