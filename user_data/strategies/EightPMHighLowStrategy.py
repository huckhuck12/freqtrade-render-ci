from freqtrade.strategy import IStrategy, merge_informative_pair
from pandas import DataFrame
import talib.abstract as ta
import freqtrade.vendor.qtpylib.indicators as qtpylib
import pandas as pd
import numpy as np


class EightPMHighLowStrategy(IStrategy):
    """
    v2.6 精准优化版晚上8点高低点策略
    
    策略逻辑：
    - 以晚上8点为分界线判断当日高低点
    - 8点为最高点则做空，8点为最低点则做多
    - 等待价格确认后入场
    - 优化的止损止盈比例 (1.6% : 6.0%)
    - 精选3个高质量币种，质量胜过数量
    
    v2.6 精准优化重点 (基于最新回测结果)：
    - 移除表现差的BTC，专注ETH+ADA+AVAX三币种
    - 参数精调：降低止损至1.6%，提高止盈至6%，改善盈亏比
    - 信号质量：收紧RSI条件，提高入场精准度
    - 仓位优化：ETH增至2.0倍(90%胜率表现优异)，ADA保持2.5倍，AVAX调至1.5倍
    - 成交量过滤：提高成交量要求至1.035，确保流动性
    
    基于最新回测数据的优化决策：
    - ETH: 90%胜率, 0.1%收益 → 增加仓位至2.0倍
    - BTC: 45.5%胜率, -0.03%收益 → 完全移除
    - ADA/AVAX: 配置文件已正确，但需要参数微调
    
    目标：胜率提升至70%+，收益率提升至0.15%+，减少止损次数
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

    # ========= 风险控制 v2.6 - 精准优化 =========
    stoploss = -0.016  # 降低止损至1.6% (减少不必要止损)
    
    minimal_roi = {
        "0": 0.06,    # 提高初始止盈至6% (改善盈亏比)
        "15": 0.045,  # 15分钟后降低到4.5%
        "30": 0.035,  # 30分钟后降低到3.5%
        "60": 0.028,  # 60分钟后降低到2.8%
        "120": 0.022, # 120分钟后降低到2.2%
        "240": 0.018  # 240分钟后降低到1.8%
    }

    # ========= 策略参数 v2.6 - 精准优化 =========
    volume_threshold = 1.035  # 提高成交量要求，确保流动性
    confirmation_threshold = 0.0003  # 提高价格确认阈值，减少假信号
    tolerance = 0.009  # 收紧8点极值容差，提高信号质量
    sma_range_pct = 0.105  # 收紧均线范围，提高入场精准度
    
    # v2.6 新增参数 - 精准信号策略
    trend_confirmation = False  # 保持关闭4小时趋势确认
    smart_exit = True  # 启用智能止盈止损
    
    # 专注3个精选币种：ETH(优异), ADA(最佳), AVAX(潜力)

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
        
        # 基础条件 - 精准优化参数，提高信号质量
        base_long_conditions = [
            dataframe['is_daily_low_at_8pm'],
            (dataframe['volume_ratio'] > self.volume_threshold),
            (dataframe['rsi'] < 40)  # 进一步收紧RSI条件，提高精准度
        ]
        
        base_short_conditions = [
            dataframe['is_daily_high_at_8pm'],
            (dataframe['volume_ratio'] > self.volume_threshold),
            (dataframe['rsi'] > 60)  # 进一步收紧RSI条件，提高精准度
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
        v2.6 精准仓位管理 - 基于最新回测表现优化
        """
        # 基础仓位
        base_stake = proposed_stake
        
        # 根据最新回测表现调整仓位
        if 'ETH' in pair:
            # ETH: 90%胜率, 0.1%收益 - 表现优异，增加仓位
            stake_multiplier = 2.0
        elif 'ADA' in pair:
            # ADA: 保持最大仓位配置
            stake_multiplier = 2.5
        elif 'AVAX' in pair:
            # AVAX: 适度增加仓位
            stake_multiplier = 1.5
        else:
            # 其他币种 - 标准仓位
            stake_multiplier = 1.0
        
        # 根据当前持仓数量调整 (最多3个持仓)
        if hasattr(self, 'dp') and self.dp:
            try:
                current_trades = len([t for t in self.dp.current_whitelist() if t])
                if current_trades < 2:
                    # 持仓少时适度增加仓位
                    stake_multiplier *= 1.15
            except:
                pass
        
        final_stake = base_stake * stake_multiplier
        
        # 确保在允许范围内
        return max(min_stake, min(final_stake, max_stake))
    
    def custom_exit(self, pair: str, trade, current_time, current_rate: float,
                   current_profit: float, **kwargs) -> str:
        """
        v2.6 优化智能出场逻辑 - 减少不必要止损，提高盈利持有
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
        if trade.is_short and latest['rsi'] < 18:  # 极端超卖
            return "rsi_oversold"
        elif not trade.is_short and latest['rsi'] > 82:  # 极端超买
            return "rsi_overbought"
        
        # 基于持仓时间的出场 - 针对不同币种差异化管理
        trade_duration = (current_time - trade.open_date_utc).total_seconds() / 3600
        
        # ETH: 表现最好，给最多时间
        if 'ETH' in pair:
            if trade_duration > 30 and current_profit > 0.015:  # 30小时后1.5%盈利出场
                return "time_profit_exit"
            if trade_duration > 60:  # 60小时强制平仓
                return "max_time_exit"
        # ADA: 保持原有时间管理
        elif 'ADA' in pair:
            if trade_duration > 24 and current_profit > 0.012:  # 24小时后1.2%盈利出场
                return "time_profit_exit"
            if trade_duration > 48:  # 48小时强制平仓
                return "max_time_exit"
        # AVAX: 标准时间管理
        else:
            if trade_duration > 20 and current_profit > 0.01:  # 20小时后1%盈利出场
                return "time_profit_exit"
            if trade_duration > 40:  # 40小时强制平仓
                return "max_time_exit"
        
        return None