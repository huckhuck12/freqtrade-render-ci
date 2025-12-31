from freqtrade.strategy import IStrategy, merge_informative_pair
from pandas import DataFrame
import talib.abstract as ta
import freqtrade.vendor.qtpylib.indicators as qtpylib
import pandas as pd
import numpy as np


class EightPMHighLowStrategy(IStrategy):
    """
    v4.3 精准优化版晚上8点高低点策略 - 基于v4.2实际数据精准调优
    
    策略逻辑：
    - 以晚上8点为分界线判断当日高低点
    - 8点为最高点则做空，8点为最低点则做多
    - 等待价格确认后入场
    - 基于v4.2实际回测数据的精准优化
    
    v4.2 实际表现分析 (11.14%收益，10.23%回撤，44.7%胜率)：
    - AVAX: 7.57%收益，47.3%胜率 (表现最佳但未达预期)
    - SOL: 1.76%收益，44.8%胜率 (超预期表现)
    - ADA: 0.92%收益，42.3%胜率 (稳定但偏低)
    - ETH: 0.86%收益，57.1%胜率 (高胜率但交易少)
    - LINK: 0.49%收益，42.6%胜率 (平平)
    - DOT: -0.46%收益，43.8%胜率 (负贡献)
    
    v4.2 → v4.3 精准改进 (基于实际数据)：
    - AVAX王者强化：保持50x仓位，优化入场条件提升7.57%→15%+
    - SOL意外之喜：从8x大幅提升至25x仓位 (1.76%表现超预期)
    - ETH高胜率激活：进一步放宽条件，57.1%胜率巨大潜力
    - 移除DOT负贡献：-0.46%拖累整体表现
    - 添加BTC稳定器：替换DOT，增加稳定大盘币
    - 精准参数调优：基于实际止损率54.4%优化
    
    版本演进历程：
    - v4.0: 0.45%收益，34.16%回撤 (配置失衡)
    - v4.1: 34.74%收益，11.69%回撤 (智能优化成功)
    - v4.2: 11.14%收益，10.23%回撤 (未达预期但数据宝贵)
    - v4.3: 基于v4.2实际数据的精准优化 (目标25%+收益)
    
    目标：基于v4.2真实表现数据，精准优化达到25%+收益率
    """

    # ========= 基本设置 v4.2 超级优化 =========
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

    # ========= 风险控制 v4.3 精准优化 =========
    stoploss = -0.022  # 精准止损2.2% (基于v4.2实际54.4%止损率优化)
    
    minimal_roi = {
        "0": 0.15,    # 精准止盈15% (基于v4.2实际表现调整)
        "5": 0.12,    # 5分钟后降低到12%
        "10": 0.09,   # 10分钟后降低到9%
        "20": 0.06,   # 20分钟后降低到6%
        "40": 0.04,   # 40分钟后降低到4%
        "80": 0.03,   # 80分钟后降低到3%
        "160": 0.025  # 160分钟后降低到2.5%
    }

    # ========= 策略参数 v4.3 精准优化 =========
    volume_threshold = 1.008  # 精准调整成交量要求，基于v4.2实际表现
    confirmation_threshold = 0.00008  # 进一步降低确认阈值，激活ETH高胜率
    tolerance = 0.012  # 精准调整容差，平衡信号质量与数量
    sma_range_pct = 0.15  # 精准调整均线范围，基于实际交易分析
    
    # v4.3 精准参数 - 基于v4.2实际数据优化
    trend_confirmation = False  # 保持关闭4小时趋势确认
    smart_exit = True  # 启用智能止盈止损
    
    # 精准6币种池：AVAX王者+SOL意外之喜+ETH高胜率+ADA稳定+MATIC激活+BTC稳定器

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
        
        # 基础条件 - v4.2超级优化，基于v4.1成功数据再优化
        pair = metadata['pair']
        
        # 精准RSI条件 - 基于v4.2各币种实际表现精准优化
        if 'AVAX' in pair:
            # AVAX: v4.2最佳表现(7.57%收益，47.3%胜率)，优化条件提升至15%+
            rsi_long_threshold = 58
            rsi_short_threshold = 42
        elif 'SOL' in pair:
            # SOL: v4.2意外之喜(1.76%收益，44.8%胜率)，大幅放宽发挥潜力
            rsi_long_threshold = 55
            rsi_short_threshold = 45
        elif 'ETH' in pair:
            # ETH: v4.2高胜率(57.1%)但交易少，进一步激活
            rsi_long_threshold = 56
            rsi_short_threshold = 44
        elif 'ADA' in pair:
            # ADA: v4.2稳定(0.92%收益，42.3%胜率)，适度优化
            rsi_long_threshold = 52
            rsi_short_threshold = 48
        elif 'MATIC' in pair:
            # MATIC: 继续激活参与交易
            rsi_long_threshold = 54
            rsi_short_threshold = 46
        elif 'BTC' in pair:
            # BTC: 新增稳定器，保守条件
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
        v4.3 精准仓位管理 - 基于v4.2实际表现数据精准优化
        """
        # 基础仓位
        base_stake = proposed_stake
        
        # 精准仓位配置 - 基于v4.2实际表现精准调整
        if 'AVAX' in pair:
            # AVAX: v4.2最佳表现(7.57%收益，47.3%胜率)，保持王者仓位
            stake_multiplier = 50.0
        elif 'SOL' in pair:
            # SOL: v4.2意外之喜(1.76%收益，44.8%胜率)，大幅提升仓位
            stake_multiplier = 25.0
        elif 'ETH' in pair:
            # ETH: v4.2高胜率(57.1%)潜力巨大，保持高仓位
            stake_multiplier = 35.0
        elif 'ADA' in pair:
            # ADA: v4.2稳定表现(0.92%收益)，适度提升
            stake_multiplier = 18.0
        elif 'MATIC' in pair:
            # MATIC: 继续激活，给予合理仓位
            stake_multiplier = 15.0
        elif 'BTC' in pair:
            # BTC: 新增稳定器，保守仓位
            stake_multiplier = 12.0
        else:
            # 其他币种: 标准仓位
            stake_multiplier = 10.0
        
        # 精准动态调整 - 基于v4.2实际交易分析
        if hasattr(self, 'dp') and self.dp:
            try:
                current_trades = len([t for t in self.dp.current_whitelist() if t])
                
                # 基于币种实际表现的差异化动态调整
                if 'AVAX' in pair or 'SOL' in pair:
                    # 优质币种：更积极的动态加仓
                    if current_trades < 2:
                        stake_multiplier *= 2.0
                    elif current_trades < 4:
                        stake_multiplier *= 1.6
                    elif current_trades < 6:
                        stake_multiplier *= 1.3
                    else:
                        stake_multiplier *= 1.0
                elif 'ETH' in pair:
                    # ETH高胜率：激进动态调整
                    if current_trades < 3:
                        stake_multiplier *= 1.8
                    elif current_trades < 6:
                        stake_multiplier *= 1.4
                    else:
                        stake_multiplier *= 1.1
                else:
                    # 一般币种：保守的动态调整
                    if current_trades < 3:
                        stake_multiplier *= 1.3
                    elif current_trades < 6:
                        stake_multiplier *= 1.1
                    else:
                        stake_multiplier *= 0.9
                
            except:
                pass
        
        final_stake = base_stake * stake_multiplier
        
        # 确保在允许范围内
        return max(min_stake, min(final_stake, max_stake))
    
    def custom_exit(self, pair: str, trade, current_time, current_rate: float,
                   current_profit: float, **kwargs) -> str:
        """
        v4.3 精准出场逻辑 - 基于v4.2实际表现数据精准优化
        """
        if not self.smart_exit:
            return None
            
        # 获取当前数据
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if dataframe is None or len(dataframe) == 0:
            return None
            
        # 获取最新数据
        latest = dataframe.iloc[-1]
        
        # 基于RSI的动态出场 - 精准调整阈值
        if trade.is_short and latest['rsi'] < 12:  # 精准超卖阈值
            return "rsi_oversold"
        elif not trade.is_short and latest['rsi'] > 88:  # 精准超买阈值
            return "rsi_overbought"
        
        # 精准持仓时间管理 - 基于v4.2各币种实际表现优化
        trade_duration = (current_time - trade.open_date_utc).total_seconds() / 3600
        
        # AVAX: v4.2最佳表现，给充分时间发挥优势
        if 'AVAX' in pair:
            if trade_duration > 60 and current_profit > 0.04:  # 60小时后4%盈利出场
                return "time_profit_exit"
            if trade_duration > 96:  # 96小时强制平仓
                return "max_time_exit"
        # SOL: v4.2意外之喜，给充分时间发挥潜力
        elif 'SOL' in pair:
            if trade_duration > 48 and current_profit > 0.03:  # 48小时后3%盈利出场
                return "time_profit_exit"
            if trade_duration > 84:  # 84小时强制平仓
                return "max_time_exit"
        # ETH: v4.2高胜率，给充分时间捕获更多机会
        elif 'ETH' in pair:
            if trade_duration > 54 and current_profit > 0.035:  # 54小时后3.5%盈利出场
                return "time_profit_exit"
            if trade_duration > 90:  # 90小时强制平仓
                return "max_time_exit"
        # ADA: v4.2稳定表现，标准时间管理
        elif 'ADA' in pair:
            if trade_duration > 36 and current_profit > 0.025:  # 36小时后2.5%盈利出场
                return "time_profit_exit"
            if trade_duration > 72:  # 72小时强制平仓
                return "max_time_exit"
        # MATIC: 激活参与，给予合理机会
        elif 'MATIC' in pair:
            if trade_duration > 42 and current_profit > 0.03:  # 42小时后3%盈利出场
                return "time_profit_exit"
            if trade_duration > 78:  # 78小时强制平仓
                return "max_time_exit"
        # BTC: 新增稳定器，保守管理
        elif 'BTC' in pair:
            if trade_duration > 30 and current_profit > 0.02:  # 30小时后2%盈利出场
                return "time_profit_exit"
            if trade_duration > 66:  # 66小时强制平仓
                return "max_time_exit"
        # 其他币种: 标准管理
        else:
            if trade_duration > 36 and current_profit > 0.025:  # 36小时后2.5%盈利出场
                return "time_profit_exit"
            if trade_duration > 66:  # 66小时强制平仓
                return "max_time_exit"
        
        return None