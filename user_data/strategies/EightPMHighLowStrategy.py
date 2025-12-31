from freqtrade.strategy import IStrategy, merge_informative_pair
from pandas import DataFrame
import talib.abstract as ta
import freqtrade.vendor.qtpylib.indicators as qtpylib
import pandas as pd
import numpy as np


class EightPMHighLowStrategy(IStrategy):
    """
    v3.2 回归优化版晚上8点高低点策略
    
    策略逻辑：
    - 以晚上8点为分界线判断当日高低点
    - 8点为最高点则做空，8点为最低点则做多
    - 等待价格确认后入场
    - 基于v3.0/v3.1对比的回归优化 (v3.0: 11.14%收益 vs v3.1: 4.55%收益)
    
    v3.2 回归优化重点 (基于v3.0成功 + v3.1教训)：
    - 回归v3.0激进基础：恢复宽松RSI条件和高仓位配置
    - 重新加入DOT：DOT(-0.46%)比v3.1中ADA/SOL亏损(-0.64%/-0.73%)更小
    - 温和微调：止损2.3%，在v3.0(2.5%)和v3.1(2.2%)间平衡
    - 仓位重配：基于v3.0实际表现优化，避免v3.1过度调整
    - 保持交易频率：避免v3.1中交易数从358降至239的问题
    
    v3.0 → v3.1 → v3.2 演进：
    - v3.0: 11.14%收益, 44.7%胜率, 358笔交易 (激进成功)
    - v3.1: 4.55%收益, 44.8%胜率, 239笔交易 (过度收紧失败)
    - v3.2: 回归激进基础 + 温和微调 (目标: 保持10%+收益，微提胜率)
    
    目标：在v3.0高收益基础上温和优化，避免v3.1的过度调整
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

    # ========= 风险控制 v3.2 回归优化 =========
    stoploss = -0.023  # 温和止损2.3% (在v3.0的2.5%和v3.1的2.2%间平衡)
    
    minimal_roi = {
        "0": 0.14,    # 回归激进止盈14% (接近v3.0的15%)
        "7": 0.11,    # 7分钟后降低到11%
        "14": 0.09,   # 14分钟后降低到9%
        "28": 0.07,   # 28分钟后降低到7%
        "55": 0.05,   # 55分钟后降低到5%
        "110": 0.04   # 110分钟后降低到4%
    }

    # ========= 策略参数 v3.2 回归优化 =========
    volume_threshold = 1.03  # 回归适中成交量要求 (v3.0: 1.02, v3.1: 1.05)
    confirmation_threshold = 0.00025  # 回归适中确认阈值 (v3.0: 0.0002, v3.1: 0.0003)
    tolerance = 0.011  # 回归适中容差 (v3.0: 0.012, v3.1: 0.010)
    sma_range_pct = 0.13  # 回归适中均线范围 (v3.0: 0.15, v3.1: 0.12)
    
    # v3.2 回归参数 - 在激进与保守间平衡
    trend_confirmation = False  # 保持关闭4小时趋势确认
    smart_exit = True  # 启用智能止盈止损
    
    # 回归7币种池：重新加入DOT，避免v3.1中ADA/SOL转亏问题

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
        
        # 基础条件 - v3.2回归优化，恢复v3.0宽松基础
        pair = metadata['pair']
        
        # 回归RSI条件 - 基于v3.0成功经验，避免v3.1过度收紧
        if 'AVAX' in pair:
            # AVAX: 表现最佳，保持宽松条件 (v3.0风格)
            rsi_long_threshold = 52
            rsi_short_threshold = 48
        elif 'ETH' in pair:
            # ETH: 胜率高，进一步放宽激活交易 (比v3.1更宽松)
            rsi_long_threshold = 53
            rsi_short_threshold = 47
        elif 'SOL' in pair:
            # SOL: 回归v3.0宽松条件，避免v3.1转亏
            rsi_long_threshold = 50
            rsi_short_threshold = 50
        elif 'ADA' in pair:
            # ADA: 回归v3.0条件，避免v3.1转亏
            rsi_long_threshold = 49
            rsi_short_threshold = 51
        elif 'DOT' in pair:
            # DOT: 重新加入，使用标准条件
            rsi_long_threshold = 48
            rsi_short_threshold = 52
        elif 'LINK' in pair or 'MATIC' in pair:
            # LINK/MATIC: 回归v3.0宽松条件
            rsi_long_threshold = 50
            rsi_short_threshold = 50
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
        v3.2 回归仓位管理 - 基于v3.0成功经验优化
        """
        # 基础仓位
        base_stake = proposed_stake
        
        # 回归仓位配置 - 基于v3.0实际表现，避免v3.1过度调整
        if 'AVAX' in pair:
            # AVAX: 表现最佳，保持超大仓位 (v3.0: 10x, v3.1: 12x)
            stake_multiplier = 11.0
        elif 'ETH' in pair:
            # ETH: 胜率高，大仓位激活 (回归v3.0风格)
            stake_multiplier = 7.0
        elif 'SOL' in pair:
            # SOL: 回归v3.0大仓位，避免v3.1转亏
            stake_multiplier = 9.0
        elif 'ADA' in pair:
            # ADA: 回归v3.0大仓位，避免v3.1转亏
            stake_multiplier = 7.5
        elif 'DOT' in pair:
            # DOT: 重新加入，保守仓位
            stake_multiplier = 5.0
        elif 'MATIC' in pair or 'LINK' in pair:
            # MATIC/LINK: 回归v3.0配置
            stake_multiplier = 6.5
        else:
            # 其他币种: 标准仓位
            stake_multiplier = 6.0
        
        # 根据当前持仓数量调整 (回归v3.0风格)
        if hasattr(self, 'dp') and self.dp:
            try:
                current_trades = len([t for t in self.dp.current_whitelist() if t])
                if current_trades < 3:
                    # 持仓少时增加仓位 (v3.0风格)
                    stake_multiplier *= 1.4
                elif current_trades < 5:
                    stake_multiplier *= 1.2
                elif current_trades < 7:
                    stake_multiplier *= 1.1
            except:
                pass
        
        final_stake = base_stake * stake_multiplier
        
        # 确保在允许范围内
        return max(min_stake, min(final_stake, max_stake))
    
    def custom_exit(self, pair: str, trade, current_time, current_rate: float,
                   current_profit: float, **kwargs) -> str:
        """
        v3.2 回归出场逻辑 - 基于v3.0成功经验优化
        """
        if not self.smart_exit:
            return None
            
        # 获取当前数据
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if dataframe is None or len(dataframe) == 0:
            return None
            
        # 获取最新数据
        latest = dataframe.iloc[-1]
        
        # 基于RSI的动态出场 - 回归v3.0适中阈值
        if trade.is_short and latest['rsi'] < 13:  # 极端超卖
            return "rsi_oversold"
        elif not trade.is_short and latest['rsi'] > 87:  # 极端超买
            return "rsi_overbought"
        
        # 基于持仓时间和币种的差异化出场 - 回归v3.0风格
        trade_duration = (current_time - trade.open_date_utc).total_seconds() / 3600
        
        # AVAX: 表现最佳，给充分时间 (回归v3.0风格)
        if 'AVAX' in pair:
            if trade_duration > 42 and current_profit > 0.022:  # 42小时后2.2%盈利出场
                return "time_profit_exit"
            if trade_duration > 78:  # 78小时强制平仓
                return "max_time_exit"
        # ETH: 胜率高，给充分时间
        elif 'ETH' in pair:
            if trade_duration > 36 and current_profit > 0.018:  # 36小时后1.8%盈利出场
                return "time_profit_exit"
            if trade_duration > 66:  # 66小时强制平仓
                return "max_time_exit"
        # SOL: 回归v3.0时间管理
        elif 'SOL' in pair:
            if trade_duration > 30 and current_profit > 0.016:  # 30小时后1.6%盈利出场
                return "time_profit_exit"
            if trade_duration > 54:  # 54小时强制平仓
                return "max_time_exit"
        # ADA: 回归v3.0时间管理
        elif 'ADA' in pair:
            if trade_duration > 32 and current_profit > 0.017:  # 32小时后1.7%盈利出场
                return "time_profit_exit"
            if trade_duration > 60:  # 60小时强制平仓
                return "max_time_exit"
        # DOT: 重新加入，保守管理
        elif 'DOT' in pair:
            if trade_duration > 24 and current_profit > 0.014:  # 24小时后1.4%盈利出场
                return "time_profit_exit"
            if trade_duration > 42:  # 42小时强制平仓
                return "max_time_exit"
        # LINK/MATIC: 回归v3.0管理
        else:  # LINK, MATIC等
            if trade_duration > 28 and current_profit > 0.015:  # 28小时后1.5%盈利出场
                return "time_profit_exit"
            if trade_duration > 48:  # 48小时强制平仓
                return "max_time_exit"
        
        return None