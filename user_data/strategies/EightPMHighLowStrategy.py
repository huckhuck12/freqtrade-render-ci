from freqtrade.strategy import IStrategy, merge_informative_pair
from pandas import DataFrame
import talib.abstract as ta
import freqtrade.vendor.qtpylib.indicators as qtpylib
import pandas as pd
import numpy as np


class EightPMHighLowStrategy(IStrategy):
    """
    v2.8 最终优化版晚上8点高低点策略
    
    策略逻辑：
    - 以晚上8点为分界线判断当日高低点
    - 8点为最高点则做空，8点为最低点则做多
    - 等待价格确认后入场
    - 最终优化的止损止盈比例 (1.75% : 6.0%)
    - 精选3个高质量币种，最终平衡优化
    
    v2.8 最终优化重点 (基于v2.7回测结果)：
    - 止损精调：1.75%止损，目标减少17笔止损至<15笔
    - ADA参数恢复：微调ADA RSI，恢复63.6%胜率
    - ETH仓位提升：基于58.3%胜率改善，提升至1.9x
    - 收益率优化：通过更快止盈和更好仓位配置提升收益
    
    基于v2.7回测数据的最终优化：
    - ETH: 58.3%胜率, 0.10%收益 → 表现改善，提升仓位至1.9x
    - ADA: 60.0%胜率, 0.12%收益 → 微调RSI恢复至63%+胜率
    - AVAX: 55.6%胜率, 0.09%收益 → 保持1.6x配置
    
    v2.7 → v2.8 最终目标：
    - 胜率：保持57.5%+
    - 收益率：从0.30%提升至0.35%+
    - 止损数：从17笔减少至<15笔
    - 止损率：从42.5%降至<37.5%
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

    # ========= 风险控制 v2.8 - 最终优化 =========
    stoploss = -0.0175  # 精调止损至1.75% (减少v2.7中的17笔止损)
    
    minimal_roi = {
        "0": 0.06,    # 保持初始止盈6%
        "10": 0.048,  # 10分钟后降低到4.8% (更快获利)
        "20": 0.038,  # 20分钟后降低到3.8%
        "40": 0.030,  # 40分钟后降低到3.0%
        "80": 0.024,  # 80分钟后降低到2.4%
        "160": 0.020  # 160分钟后降低到2.0%
    }

    # ========= 策略参数 v2.8 - 最终优化 =========
    volume_threshold = 1.028  # 微调成交量要求
    confirmation_threshold = 0.00026  # 微调价格确认阈值
    tolerance = 0.0098  # 微调8点极值容差
    sma_range_pct = 0.110  # 微调均线范围
    
    # v2.8 最终参数 - 平衡所有币种表现
    trend_confirmation = False  # 保持关闭4小时趋势确认
    smart_exit = True  # 启用智能止盈止损
    
    # 专注3个精选币种：ETH(改善), ADA(恢复), AVAX(稳定)

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
        
        # 基础条件 - v2.8最终优化，平衡各币种表现
        pair = metadata['pair']
        
        # 根据v2.7结果微调RSI条件
        if 'ETH' in pair:
            # ETH: 58.3%胜率表现良好，保持当前条件
            rsi_long_threshold = 45
            rsi_short_threshold = 55
        elif 'ADA' in pair:
            # ADA: 胜率从63.6%降至60%，微调恢复
            rsi_long_threshold = 40
            rsi_short_threshold = 60
        else:  # AVAX
            # AVAX: 55.6%胜率稳定，保持条件
            rsi_long_threshold = 42
            rsi_short_threshold = 58
        
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
        v2.8 最终仓位管理 - 基于v2.7回测结果优化
        """
        # 基础仓位
        base_stake = proposed_stake
        
        # 根据v2.7实际表现最终调整仓位
        if 'ADA' in pair:
            # ADA: 60.0%胜率, 0.12%收益 - 保持最大仓位
            stake_multiplier = 2.5
        elif 'ETH' in pair:
            # ETH: 58.3%胜率, 0.10%收益 - 表现改善，提升仓位
            stake_multiplier = 1.9
        elif 'AVAX' in pair:
            # AVAX: 55.6%胜率, 0.09%收益 - 保持当前配置
            stake_multiplier = 1.6
        else:
            # 其他币种 - 标准仓位
            stake_multiplier = 1.0
        
        # 根据当前持仓数量调整 (最多3个持仓)
        if hasattr(self, 'dp') and self.dp:
            try:
                current_trades = len([t for t in self.dp.current_whitelist() if t])
                if current_trades < 2:
                    # 持仓少时适度增加仓位
                    stake_multiplier *= 1.08
            except:
                pass
        
        final_stake = base_stake * stake_multiplier
        
        # 确保在允许范围内
        return max(min_stake, min(final_stake, max_stake))
    
    def custom_exit(self, pair: str, trade, current_time, current_rate: float,
                   current_profit: float, **kwargs) -> str:
        """
        v2.8 最终智能出场逻辑 - 优化收益率和减少止损
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
        if trade.is_short and latest['rsi'] < 12:  # 极端超卖
            return "rsi_oversold"
        elif not trade.is_short and latest['rsi'] > 88:  # 极端超买
            return "rsi_overbought"
        
        # 基于持仓时间和币种的最终优化出场
        trade_duration = (current_time - trade.open_date_utc).total_seconds() / 3600
        
        # ADA: 保持最优配置，给充分时间
        if 'ADA' in pair:
            if trade_duration > 32 and current_profit > 0.016:  # 32小时后1.6%盈利出场
                return "time_profit_exit"
            if trade_duration > 64:  # 64小时强制平仓
                return "max_time_exit"
        # ETH: 表现改善，给更多信心
        elif 'ETH' in pair:
            if trade_duration > 30 and current_profit > 0.015:  # 30小时后1.5%盈利出场
                return "time_profit_exit"
            if trade_duration > 60:  # 60小时强制平仓
                return "max_time_exit"
        # AVAX: 保持活跃管理
        else:  # AVAX
            if trade_duration > 26 and current_profit > 0.014:  # 26小时后1.4%盈利出场
                return "time_profit_exit"
            if trade_duration > 52:  # 52小时强制平仓
                return "max_time_exit"
        
        return None