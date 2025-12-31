from freqtrade.strategy import IStrategy, merge_informative_pair
from pandas import DataFrame
import talib.abstract as ta
import freqtrade.vendor.qtpylib.indicators as qtpylib
import pandas as pd
import numpy as np


class EightPMHighLowStrategy(IStrategy):
    """
    v4.1 智能优化版晚上8点高低点策略 - 基于v4.0数据优化
    
    策略逻辑：
    - 以晚上8点为分界线判断当日高低点
    - 8点为最高点则做空，8点为最低点则做多
    - 等待价格确认后入场
    - 基于v4.0实测数据的智能优化 (目标100%+收益率)
    
    v4.1 智能优化重点 (基于v4.0: 0.45%收益，34.16%回撤分析)：
    - 智能币种筛选：剔除LINK/DOT(-11.37%/-13.45%)，专注AVAX/ETH优质表现
    - 动态仓位管理：基于实际表现重新分配，AVAX(21.77%)获得最大仓位
    - 改进止损策略：从3%调整为2.5%，降低56.3%止损率
    - 风险分级管理：优质币种高仓位，一般币种适中仓位
    - 保持ROI优势：129笔ROI获得205.92%收益的优秀表现
    
    v4.0 → v4.1 关键改进：
    - 币种优化：5币种精选 (剔除LINK/DOT拖累)
    - 仓位重配：基于实际表现的智能分配
    - 止损优化：2.5%平衡风险与持仓质量
    - 风险控制：目标回撤<20%，收益>50%
    
    版本演进历程：
    - v3.2: 12.06%收益，10.60%回撤 (稳定基础)
    - v4.0: 0.45%收益，34.16%回撤 (过度激进失败)
    - v4.1: 基于数据的智能优化 (目标100%+收益，<20%回撤)
    
    目标：在控制风险的前提下追求高收益，避免v4.0的配置失衡
    """

    # ========= 基本设置 v4.1 智能优化 =========
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

    # ========= 风险控制 v4.1 智能优化 =========
    stoploss = -0.025  # 智能止损2.5% (从v4.0的3%优化，降低止损率)
    
    minimal_roi = {
        "0": 0.20,    # 智能止盈20% (从v4.0的25%调整，更现实)
        "6": 0.16,    # 6分钟后降低到16%
        "12": 0.13,   # 12分钟后降低到13%
        "25": 0.10,   # 25分钟后降低到10%
        "50": 0.07,   # 50分钟后降低到7%
        "100": 0.05,  # 100分钟后降低到5%
        "200": 0.04   # 200分钟后降低到4%
    }

    # ========= 策略参数 v4.1 智能优化 =========
    volume_threshold = 1.02  # 适中成交量要求，平衡质量与频率
    confirmation_threshold = 0.00015  # 适中确认阈值，避免过多假信号
    tolerance = 0.013  # 适中容差，保持信号质量
    sma_range_pct = 0.16  # 适中均线范围，平衡机会与质量
    
    # v4.1 智能参数 - 基于v4.0数据优化
    trend_confirmation = False  # 保持关闭4小时趋势确认
    smart_exit = True  # 启用智能止盈止损
    
    # 智能5币种池：剔除LINK/DOT，专注AVAX/ETH/ADA/SOL/MATIC优质表现

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
        
        # 基础条件 - v4.1智能优化，基于v4.0实测数据
        pair = metadata['pair']
        
        # 智能RSI条件 - 基于v4.0各币种实际表现优化
        if 'AVAX' in pair:
            # AVAX: v4.0表现最佳(21.77%收益，51.2%胜率)，保持宽松
            rsi_long_threshold = 58
            rsi_short_threshold = 42
        elif 'ETH' in pair:
            # ETH: v4.0表现良好(5.42%收益，56.2%胜率)，适度宽松
            rsi_long_threshold = 56
            rsi_short_threshold = 44
        elif 'SOL' in pair:
            # SOL: v4.0轻微亏损(-1.99%)，收紧条件
            rsi_long_threshold = 52
            rsi_short_threshold = 48
        elif 'ADA' in pair:
            # ADA: v4.0几乎无收益(0.07%)，收紧条件
            rsi_long_threshold = 50
            rsi_short_threshold = 50
        elif 'MATIC' in pair:
            # MATIC: 保持标准条件
            rsi_long_threshold = 51
            rsi_short_threshold = 49
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
        v4.1 智能仓位管理 - 基于v4.0实测数据优化
        """
        # 基础仓位
        base_stake = proposed_stake
        
        # 智能仓位配置 - 基于v4.0实际表现重新分配
        if 'AVAX' in pair:
            # AVAX: v4.0最佳表现(21.77%收益)，超大仓位
            stake_multiplier = 35.0
        elif 'ETH' in pair:
            # ETH: v4.0良好表现(5.42%收益)，大仓位
            stake_multiplier = 25.0
        elif 'SOL' in pair:
            # SOL: v4.0轻微亏损(-1.99%)，中等仓位
            stake_multiplier = 15.0
        elif 'ADA' in pair:
            # ADA: v4.0几乎无收益(0.07%)，小仓位
            stake_multiplier = 10.0
        elif 'MATIC' in pair:
            # MATIC: 标准仓位
            stake_multiplier = 12.0
        else:
            # 其他币种: 保守仓位
            stake_multiplier = 8.0
        
        # 智能动态调整 - 基于持仓分散风险
        if hasattr(self, 'dp') and self.dp:
            try:
                current_trades = len([t for t in self.dp.current_whitelist() if t])
                
                # 更保守的动态调整，避免v4.0的过度加仓
                if current_trades < 2:
                    # 持仓很少时，适度加仓
                    stake_multiplier *= 1.8
                elif current_trades < 4:
                    # 持仓较少时，小幅加仓
                    stake_multiplier *= 1.4
                elif current_trades < 6:
                    # 持仓适中时，微调
                    stake_multiplier *= 1.2
                elif current_trades < 8:
                    # 持仓较多时，保持原仓位
                    stake_multiplier *= 1.0
                else:
                    # 持仓过多时，降低仓位
                    stake_multiplier *= 0.8
                
            except:
                pass
        
        final_stake = base_stake * stake_multiplier
        
        # 确保在允许范围内
        return max(min_stake, min(final_stake, max_stake))
    
    def custom_exit(self, pair: str, trade, current_time, current_rate: float,
                   current_profit: float, **kwargs) -> str:
        """
        v4.1 智能出场逻辑 - 基于v4.0数据优化
        """
        if not self.smart_exit:
            return None
            
        # 获取当前数据
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if dataframe is None or len(dataframe) == 0:
            return None
            
        # 获取最新数据
        latest = dataframe.iloc[-1]
        
        # 基于RSI的动态出场 - 适中阈值平衡机会与风险
        if trade.is_short and latest['rsi'] < 12:  # 极端超卖
            return "rsi_oversold"
        elif not trade.is_short and latest['rsi'] > 88:  # 极端超买
            return "rsi_overbought"
        
        # 智能持仓时间管理 - 基于v4.0各币种表现优化
        trade_duration = (current_time - trade.open_date_utc).total_seconds() / 3600
        
        # AVAX: v4.0表现最佳，给充分时间
        if 'AVAX' in pair:
            if trade_duration > 60 and current_profit > 0.04:  # 60小时后4%盈利出场
                return "time_profit_exit"
            if trade_duration > 96:  # 96小时强制平仓
                return "max_time_exit"
        # ETH: v4.0表现良好，适中时间
        elif 'ETH' in pair:
            if trade_duration > 48 and current_profit > 0.03:  # 48小时后3%盈利出场
                return "time_profit_exit"
            if trade_duration > 78:  # 78小时强制平仓
                return "max_time_exit"
        # SOL: v4.0轻微亏损，缩短时间
        elif 'SOL' in pair:
            if trade_duration > 36 and current_profit > 0.025:  # 36小时后2.5%盈利出场
                return "time_profit_exit"
            if trade_duration > 60:  # 60小时强制平仓
                return "max_time_exit"
        # ADA: v4.0几乎无收益，保守管理
        elif 'ADA' in pair:
            if trade_duration > 30 and current_profit > 0.02:  # 30小时后2%盈利出场
                return "time_profit_exit"
            if trade_duration > 54:  # 54小时强制平仓
                return "max_time_exit"
        # MATIC: 标准管理
        else:  # MATIC等
            if trade_duration > 42 and current_profit > 0.025:  # 42小时后2.5%盈利出场
                return "time_profit_exit"
            if trade_duration > 72:  # 72小时强制平仓
                return "max_time_exit"
        
        return None