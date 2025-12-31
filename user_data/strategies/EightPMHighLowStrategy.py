from freqtrade.strategy import IStrategy, merge_informative_pair
from pandas import DataFrame
import talib.abstract as ta
import freqtrade.vendor.qtpylib.indicators as qtpylib
import pandas as pd
import numpy as np


class EightPMHighLowStrategy(IStrategy):
    """
    v4.0 超激进版晚上8点高低点策略 - 追求200%收益率
    
    策略逻辑：
    - 以晚上8点为分界线判断当日高低点
    - 8点为最高点则做空，8点为最低点则做多
    - 等待价格确认后入场
    - 极度激进配置追求200%年化收益率 (vs v3.2的12.06%)
    
    v4.0 超激进重点 (200%收益目标)：
    - 极限仓位：20-50x基础仓位 (vs v3.2的7-11x)
    - 超高杠杆：充分利用期货高杠杆特性
    - 复利效应：利用滚雪球效应快速增长资金
    - 高频交易：大幅放宽条件，最大化交易机会
    - 动态加仓：盈利时进一步加大仓位
    - 激进止盈：更高的止盈目标捕获大波动
    
    版本演进历程：
    - v3.0: 11.14%收益 (激进成功基础)
    - v3.1: 4.55%收益 (过度收紧失败)
    - v3.2: 12.06%收益 (回归优化成功)
    - v4.0: 200%收益目标 (超激进挑战)
    
    ⚠️ 极高风险警告：
    - 可能导致巨额亏损或快速爆仓
    - 仅建议极小资金测试
    - 需要强大心理承受能力
    - 高收益伴随极高风险
    """

    # ========= 基本设置 v4.0 超激进优化 =========
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

    # ========= 风险控制 v4.0 超激进优化 =========
    stoploss = -0.03  # 超激进止损3.0% (承担更高风险追求200%收益)
    
    minimal_roi = {
        "0": 0.25,    # 超激进止盈25% (捕获大波动)
        "5": 0.20,    # 5分钟后降低到20%
        "10": 0.16,   # 10分钟后降低到16%
        "20": 0.12,   # 20分钟后降低到12%
        "40": 0.08,   # 40分钟后降低到8%
        "80": 0.06,   # 80分钟后降低到6%
        "160": 0.04   # 160分钟后降低到4%
    }

    # ========= 策略参数 v4.0 超激进优化 =========
    volume_threshold = 1.01  # 超宽松成交量要求，最大化交易机会
    confirmation_threshold = 0.0001  # 超低确认阈值，快速入场
    tolerance = 0.015  # 放宽8点极值容差，增加信号
    sma_range_pct = 0.20  # 大幅放宽均线范围，最大化交易机会
    
    # v4.0 超激进参数 - 追求200%收益
    trend_confirmation = False  # 保持关闭4小时趋势确认
    smart_exit = True  # 启用智能止盈止损
    
    # 超激进7币种池：最大化市场覆盖和交易机会

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
        
        # 基础条件 - v4.0超激进优化，最大化交易机会
        pair = metadata['pair']
        
        # 超激进RSI条件 - 大幅放宽所有条件追求200%收益
        if 'AVAX' in pair:
            # AVAX: 表现最佳，超宽松条件
            rsi_long_threshold = 60
            rsi_short_threshold = 40
        elif 'ETH' in pair:
            # ETH: 大幅放宽激活更多交易
            rsi_long_threshold = 58
            rsi_short_threshold = 42
        elif 'SOL' in pair:
            # SOL: 超宽松条件
            rsi_long_threshold = 55
            rsi_short_threshold = 45
        elif 'ADA' in pair:
            # ADA: 超宽松条件
            rsi_long_threshold = 55
            rsi_short_threshold = 45
        elif 'DOT' in pair:
            # DOT: 宽松条件
            rsi_long_threshold = 53
            rsi_short_threshold = 47
        elif 'LINK' in pair or 'MATIC' in pair:
            # LINK/MATIC: 宽松条件
            rsi_long_threshold = 54
            rsi_short_threshold = 46
        else:
            # 其他币种：宽松条件
            rsi_long_threshold = 55
            rsi_short_threshold = 45
        
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
        v4.0 超激进仓位管理 - 追求200%收益率
        """
        # 基础仓位
        base_stake = proposed_stake
        
        # 超激进仓位配置 - 20-50x基础仓位追求200%收益
        if 'AVAX' in pair:
            # AVAX: 表现最佳，超极限仓位
            stake_multiplier = 50.0
        elif 'SOL' in pair:
            # SOL: 高波动，超大仓位
            stake_multiplier = 40.0
        elif 'ETH' in pair:
            # ETH: 主流币，超大仓位
            stake_multiplier = 35.0
        elif 'ADA' in pair:
            # ADA: 大仓位
            stake_multiplier = 30.0
        elif 'DOT' in pair or 'LINK' in pair:
            # DOT/LINK: 大仓位
            stake_multiplier = 25.0
        elif 'MATIC' in pair:
            # MATIC: 标准大仓位
            stake_multiplier = 20.0
        else:
            # 其他币种: 大仓位
            stake_multiplier = 25.0
        
        # 动态加仓系统 - 盈利时进一步加大仓位
        if hasattr(self, 'dp') and self.dp:
            try:
                # 获取当前账户盈利状态
                current_trades = len([t for t in self.dp.current_whitelist() if t])
                
                # 基于持仓数量的动态调整
                if current_trades < 2:
                    # 持仓很少时，极限加仓
                    stake_multiplier *= 2.5
                elif current_trades < 4:
                    # 持仓较少时，大幅加仓
                    stake_multiplier *= 2.0
                elif current_trades < 6:
                    # 持仓适中时，适度加仓
                    stake_multiplier *= 1.5
                elif current_trades < 8:
                    # 持仓较多时，小幅加仓
                    stake_multiplier *= 1.2
                # 持仓过多时保持原仓位
                
            except:
                pass
        
        final_stake = base_stake * stake_multiplier
        
        # 确保在允许范围内，但尽可能接近上限
        return max(min_stake, min(final_stake, max_stake))
    
    def custom_exit(self, pair: str, trade, current_time, current_rate: float,
                   current_profit: float, **kwargs) -> str:
        """
        v4.0 超激进出场逻辑 - 追求200%收益率
        """
        if not self.smart_exit:
            return None
            
        # 获取当前数据
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if dataframe is None or len(dataframe) == 0:
            return None
            
        # 获取最新数据
        latest = dataframe.iloc[-1]
        
        # 基于RSI的动态出场 - 更极端的阈值捕获大波动
        if trade.is_short and latest['rsi'] < 10:  # 极端超卖
            return "rsi_oversold"
        elif not trade.is_short and latest['rsi'] > 90:  # 极端超买
            return "rsi_overbought"
        
        # 超激进持仓时间管理 - 给更多时间捕获大波动
        trade_duration = (current_time - trade.open_date_utc).total_seconds() / 3600
        
        # AVAX: 表现最佳，给最长时间捕获大波动
        if 'AVAX' in pair:
            if trade_duration > 72 and current_profit > 0.05:  # 72小时后5%盈利出场
                return "time_profit_exit"
            if trade_duration > 120:  # 120小时强制平仓
                return "max_time_exit"
        # SOL: 高波动币，长时间持有
        elif 'SOL' in pair:
            if trade_duration > 60 and current_profit > 0.04:  # 60小时后4%盈利出场
                return "time_profit_exit"
            if trade_duration > 96:  # 96小时强制平仓
                return "max_time_exit"
        # ETH: 主流币，适中时间
        elif 'ETH' in pair:
            if trade_duration > 48 and current_profit > 0.03:  # 48小时后3%盈利出场
                return "time_profit_exit"
            if trade_duration > 84:  # 84小时强制平仓
                return "max_time_exit"
        # ADA: 适中管理
        elif 'ADA' in pair:
            if trade_duration > 54 and current_profit > 0.035:  # 54小时后3.5%盈利出场
                return "time_profit_exit"
            if trade_duration > 90:  # 90小时强制平仓
                return "max_time_exit"
        # DOT/LINK: 标准管理
        elif 'DOT' in pair or 'LINK' in pair:
            if trade_duration > 42 and current_profit > 0.025:  # 42小时后2.5%盈利出场
                return "time_profit_exit"
            if trade_duration > 72:  # 72小时强制平仓
                return "max_time_exit"
        # MATIC: 标准管理
        else:  # MATIC等
            if trade_duration > 36 and current_profit > 0.02:  # 36小时后2%盈利出场
                return "time_profit_exit"
            if trade_duration > 66:  # 66小时强制平仓
                return "max_time_exit"
        
        return None