#!/usr/bin/env python3
"""
进阶优化版晚上8点高低点策略
在原有优化基础上进一步改进：
1. 改进入场确认机制 - 等待价格确认反转
2. 添加动态止盈策略
3. 市场状态判断 - 趋势市vs震荡市
4. 多重确认信号
5. 资金管理优化
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')


class AdvancedEightPMStrategy:
    def __init__(self, initial_balance=10000, base_position_size=100):
        self.initial_balance = initial_balance
        self.base_position_size = base_position_size
        self.leverage = 100
        self.stop_loss = 0.01  # 基础止损1%
        
        # 进阶优化参数
        self.volume_threshold = 1.3  # 成交量阈值
        self.momentum_threshold = 0.0015  # 动量阈值
        self.confirmation_hours = 2  # 确认时间（小时）
        self.take_profit_ratio = 2.0  # 止盈比例（相对于止损）
        self.max_position_ratio = 0.15  # 最大仓位比例
        
        # 市场状态参数
        self.trend_period = 48  # 趋势判断周期
        self.volatility_period = 24  # 波动率计算周期
        
        self.balance = initial_balance
        self.trades = []
        
    def generate_eth_data(self, days=1825):
        """生成模拟ETH数据"""
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        print(f"生成模拟ETH数据，时间范围: {start_date.date()} 到 {end_date.date()}")
        
        date_range = pd.date_range(start=start_date, end=end_date, freq='H')
        np.random.seed(42)
        
        initial_price = 2400
        prices = []
        volumes = []
        current_price = initial_price
        
        # 添加更真实的市场周期
        cycle_length = 365 * 24  # 一年周期
        
        for i, timestamp in enumerate(date_range):
            hour = timestamp.hour
            day_of_year = timestamp.dayofyear
            
            # 季节性波动
            seasonal_factor = 1 + 0.3 * np.sin(2 * np.pi * day_of_year / 365)
            
            # 日内波动模式
            if 18 <= hour <= 22:
                volatility = 0.025 * seasonal_factor
                volume_base = 15000
            else:
                volatility = 0.015 * seasonal_factor
                volume_base = 8000
            
            # 添加趋势成分
            trend_component = 0.0001 * np.sin(2 * np.pi * i / cycle_length)
            
            # 随机游走 + 趋势
            change = np.random.normal(trend_component, volatility)
            current_price = current_price * (1 + change)
            
            current_price = max(current_price, 800)
            current_price = min(current_price, 6000)
            
            # 成交量与波动性相关
            volume_multiplier = 1 + abs(change) * 15
            volume = int(volume_base * volume_multiplier * np.random.uniform(0.3, 2.5))
            
            prices.append(current_price)
            volumes.append(volume)
        
        # 创建OHLC数据
        data = []
        for i, (timestamp, close_price, volume) in enumerate(zip(date_range, prices, volumes)):
            if i == 0:
                open_price = close_price
            else:
                open_price = prices[i-1]
            
            intraday_range = abs(np.random.normal(0, 0.012)) * close_price
            high = max(open_price, close_price) + intraday_range * 0.6
            low = min(open_price, close_price) - intraday_range * 0.6
            
            data.append({
                'Open': round(open_price, 2),
                'High': round(high, 2),
                'Low': round(low, 2),
                'Close': round(close_price, 2),
                'Volume': volume
            })
        
        df = pd.DataFrame(data, index=date_range)
        return df
    
    def analyze_data(self, data):
        """进阶数据分析"""
        df = data.copy()
        
        # 基础时间信息
        df['hour'] = df.index.hour
        df['date'] = df.index.date
        df['is_8pm'] = (df['hour'] == 20)
        
        # 每日高低点
        daily_stats = df.groupby('date').agg({
            'High': 'max',
            'Low': 'min',
            'Volume': 'mean'
        }).rename(columns={'High': 'daily_high', 'Low': 'daily_low', 'Volume': 'daily_avg_volume'})
        
        df = df.join(daily_stats, on='date')
        
        # === 技术指标 ===
        
        # 1. 移动平均线系统
        df['sma_12'] = df['Close'].rolling(12).mean()
        df['sma_24'] = df['Close'].rolling(24).mean()
        df['sma_48'] = df['Close'].rolling(48).mean()
        
        # 2. 成交量分析
        df['volume_sma'] = df['Volume'].rolling(24).mean()
        df['volume_ratio'] = df['Volume'] / df['volume_sma']
        df['volume_surge'] = df['volume_ratio'] > self.volume_threshold
        
        # 3. 动量指标
        df['momentum_1h'] = df['Close'].pct_change(1)
        df['momentum_3h'] = df['Close'].pct_change(3)
        df['momentum_6h'] = df['Close'].pct_change(6)
        
        # 4. 波动率指标
        df['volatility'] = df['Close'].rolling(self.volatility_period).std() / df['Close'].rolling(self.volatility_period).mean()
        df['high_volatility'] = df['volatility'] > df['volatility'].rolling(48).mean()
        
        # 5. 市场状态判断
        df['trend_slope'] = (df['sma_24'] - df['sma_24'].shift(12)) / df['sma_24'].shift(12)
        df['is_trending'] = abs(df['trend_slope']) > 0.02  # 2%以上视为趋势市
        df['trend_direction'] = np.where(df['trend_slope'] > 0, 1, -1)
        
        # 6. 价格位置指标
        df['daily_range'] = df['daily_high'] - df['daily_low']
        df['price_position'] = (df['Close'] - df['daily_low']) / df['daily_range']
        
        # 7. RSI类似指标
        price_change = df['Close'].diff()
        gain = price_change.where(price_change > 0, 0)
        loss = -price_change.where(price_change < 0, 0)
        avg_gain = gain.rolling(14).mean()
        avg_loss = loss.rolling(14).mean()
        rs = avg_gain / avg_loss
        df['rsi'] = 100 - (100 / (1 + rs))
        
        # === 8点极值判断 ===
        tolerance = 0.003
        df['is_daily_high_at_8pm'] = (
            df['is_8pm'] & 
            (df['High'] >= df['daily_high'] * (1 - tolerance))
        )
        
        df['is_daily_low_at_8pm'] = (
            df['is_8pm'] & 
            (df['Low'] <= df['daily_low'] * (1 + tolerance))
        )
        
        # === 进阶信号生成 ===
        
        # 基础条件
        base_long_condition = (
            df['is_daily_low_at_8pm'] &
            df['volume_surge'] &
            df['high_volatility']
        )
        
        base_short_condition = (
            df['is_daily_high_at_8pm'] &
            df['volume_surge'] &
            df['high_volatility']
        )
        
        # 确认条件（需要在后续几小时内确认）
        df['price_confirm_long'] = False
        df['price_confirm_short'] = False
        
        # 计算确认信号
        for i in range(len(df)):
            if i < self.confirmation_hours:
                continue
                
            # 做多确认：价格在确认期内开始上涨
            if base_long_condition.iloc[i-self.confirmation_hours]:
                entry_price = df['Close'].iloc[i-self.confirmation_hours]
                current_price = df['Close'].iloc[i]
                momentum_confirm = df['momentum_3h'].iloc[i] > self.momentum_threshold
                price_confirm = current_price > entry_price * 1.002  # 0.2%确认
                
                if momentum_confirm and price_confirm:
                    df.iloc[i, df.columns.get_loc('price_confirm_long')] = True
            
            # 做空确认：价格在确认期内开始下跌
            if base_short_condition.iloc[i-self.confirmation_hours]:
                entry_price = df['Close'].iloc[i-self.confirmation_hours]
                current_price = df['Close'].iloc[i]
                momentum_confirm = df['momentum_3h'].iloc[i] < -self.momentum_threshold
                price_confirm = current_price < entry_price * 0.998  # 0.2%确认
                
                if momentum_confirm and price_confirm:
                    df.iloc[i, df.columns.get_loc('price_confirm_short')] = True
        
        # 市场状态过滤
        market_suitable_for_reversal = (
            (~df['is_trending']) |  # 震荡市更适合反转
            (df['is_trending'] & (df['volatility'] > df['volatility'].rolling(72).mean()))  # 或高波动趋势市
        )
        
        # 最终信号
        df['long_signal'] = (
            df['price_confirm_long'] &
            market_suitable_for_reversal &
            (df['rsi'] < 40) &  # 超卖
            (df['price_position'] < 0.3)  # 价格在日内低位
        )
        
        df['short_signal'] = (
            df['price_confirm_short'] &
            market_suitable_for_reversal &
            (df['rsi'] > 60) &  # 超买
            (df['price_position'] > 0.7)  # 价格在日内高位
        )
        
        # 高置信度信号
        df['high_conf_long'] = (
            df['long_signal'] &
            (df['momentum_6h'] > self.momentum_threshold * 2) &
            (df['volume_ratio'] > self.volume_threshold * 1.5) &
            (df['rsi'] < 30)
        )
        
        df['high_conf_short'] = (
            df['short_signal'] &
            (df['momentum_6h'] < -self.momentum_threshold * 2) &
            (df['volume_ratio'] > self.volume_threshold * 1.5) &
            (df['rsi'] > 70)
        )
        
        # 生成最终信号
        df['signal'] = 0
        df.loc[df['long_signal'], 'signal'] = 1
        df.loc[df['short_signal'], 'signal'] = -1
        df.loc[df['high_conf_long'], 'signal'] = 2
        df.loc[df['high_conf_short'], 'signal'] = -2
        
        return df
    
    def calculate_position_size(self, signal, current_balance, volatility):
        """动态仓位计算"""
        # 基础仓位
        base_size = min(self.base_position_size, current_balance * 0.1)
        
        # 根据信号强度调整
        if abs(signal) == 2:  # 高置信度
            size_multiplier = 1.8
        else:
            size_multiplier = 1.0
        
        # 根据波动率调整（波动率高时减少仓位）
        volatility_adjustment = max(0.5, 1 - volatility * 10)
        
        final_size = base_size * size_multiplier * volatility_adjustment
        
        # 限制最大仓位
        max_size = current_balance * self.max_position_ratio
        return min(final_size, max_size)
    
    def calculate_stop_loss(self, volatility):
        """动态止损计算"""
        base_stop = self.stop_loss
        volatility_adjustment = min(volatility * 3, 0.01)  # 最多增加1%
        return base_stop + volatility_adjustment
    
    def calculate_take_profit(self, stop_loss):
        """动态止盈计算"""
        return stop_loss * self.take_profit_ratio
    
    def backtest(self, df):
        """执行进阶回测"""
        print("\n=== 开始进阶策略回测 ===")
        
        current_position = 0
        entry_price = 0
        entry_time = None
        position_size = 0
        stop_loss_level = 0
        take_profit_level = 0
        
        for i, (timestamp, row) in enumerate(df.iterrows()):
            current_price = row['Close']
            signal = row['signal']
            volatility = row.get('volatility', 0.02)
            
            # 检查止损和止盈
            if current_position != 0:
                pnl_pct = 0
                if current_position == 1:  # 多头
                    pnl_pct = (current_price - entry_price) / entry_price
                    # 止损检查
                    if pnl_pct <= -stop_loss_level:
                        self.close_position(timestamp, current_price, entry_price, 
                                          current_position, entry_time, position_size, "止损")
                        current_position = 0
                    # 止盈检查
                    elif pnl_pct >= take_profit_level:
                        self.close_position(timestamp, current_price, entry_price, 
                                          current_position, entry_time, position_size, "止盈")
                        current_position = 0
                        
                elif current_position == -1:  # 空头
                    pnl_pct = (entry_price - current_price) / entry_price
                    # 止损检查
                    if pnl_pct <= -stop_loss_level:
                        self.close_position(timestamp, current_price, entry_price, 
                                          current_position, entry_time, position_size, "止损")
                        current_position = 0
                    # 止盈检查
                    elif pnl_pct >= take_profit_level:
                        self.close_position(timestamp, current_price, entry_price, 
                                          current_position, entry_time, position_size, "止盈")
                        current_position = 0
            
            # 新信号处理
            if signal != 0 and current_position == 0:
                # 计算仓位和风控参数
                position_size = self.calculate_position_size(signal, self.balance, volatility)
                stop_loss_level = self.calculate_stop_loss(volatility)
                take_profit_level = self.calculate_take_profit(stop_loss_level)
                
                # 开仓
                current_position = 1 if signal > 0 else -1
                entry_price = current_price
                entry_time = timestamp
                
                confidence = "高置信度" if abs(signal) == 2 else "普通"
                direction = "做多" if signal > 0 else "做空"
                print(f"{timestamp.strftime('%Y-%m-%d %H:%M')}: {confidence}{direction} 入场")
                print(f"  价格: ${current_price:.2f}, 仓位: ${position_size:.2f}")
                print(f"  止损: {stop_loss_level:.2%}, 止盈: {take_profit_level:.2%}")
            
            elif signal != 0 and current_position != 0 and np.sign(signal) != current_position:
                # 反向信号，平仓后开新仓
                self.close_position(timestamp, current_price, entry_price, 
                                  current_position, entry_time, position_size, "反向信号")
                
                # 开新仓
                position_size = self.calculate_position_size(signal, self.balance, volatility)
                stop_loss_level = self.calculate_stop_loss(volatility)
                take_profit_level = self.calculate_take_profit(stop_loss_level)
                
                current_position = 1 if signal > 0 else -1
                entry_price = current_price
                entry_time = timestamp
                
                confidence = "高置信度" if abs(signal) == 2 else "普通"
                direction = "做多" if signal > 0 else "做空"
                print(f"{timestamp.strftime('%Y-%m-%d %H:%M')}: 转向{confidence}{direction}")
                print(f"  价格: ${current_price:.2f}, 仓位: ${position_size:.2f}")
        
        # 最后平仓
        if current_position != 0:
            final_price = df['Close'].iloc[-1]
            final_time = df.index[-1]
            self.close_position(final_time, final_price, entry_price, 
                              current_position, entry_time, position_size, "回测结束")
    
    def close_position(self, exit_time, exit_price, entry_price, position, entry_time, position_size, reason):
        """平仓处理"""
        if position == 1:
            pnl_pct = (exit_price - entry_price) / entry_price
        else:
            pnl_pct = (entry_price - exit_price) / entry_price
        
        leveraged_pnl_pct = pnl_pct * self.leverage
        leveraged_pnl_pct = max(leveraged_pnl_pct, -100)
        leveraged_pnl_pct = min(leveraged_pnl_pct, 500)
        
        pnl_amount = position_size * leveraged_pnl_pct / 100
        self.balance += pnl_amount
        
        trade = {
            'entry_time': entry_time,
            'exit_time': exit_time,
            'entry_price': entry_price,
            'exit_price': exit_price,
            'position': '多头' if position == 1 else '空头',
            'position_size': position_size,
            'pnl_pct': pnl_pct,
            'leveraged_pnl_pct': leveraged_pnl_pct,
            'pnl_amount': pnl_amount,
            'balance': self.balance,
            'reason': reason,
            'duration_hours': (exit_time - entry_time).total_seconds() / 3600
        }
        
        self.trades.append(trade)
        
        direction = "多头" if position == 1 else "空头"
        print(f"{exit_time.strftime('%Y-%m-%d %H:%M')}: {direction}平仓 ({reason})")
        print(f"  价格: ${exit_price:.2f}, 收益: {leveraged_pnl_pct:.2%}, 余额: ${self.balance:.2f}")
    
    def print_results(self):
        """打印详细结果"""
        if not self.trades:
            print("没有交易记录")
            return
        
        df_trades = pd.DataFrame(self.trades)
        
        total_return = (self.balance - self.initial_balance) / self.initial_balance
        win_trades = df_trades[df_trades['pnl_amount'] > 0]
        lose_trades = df_trades[df_trades['pnl_amount'] <= 0]
        
        win_rate = len(win_trades) / len(df_trades) if len(df_trades) > 0 else 0
        
        # 按平仓原因分类
        stop_loss_trades = df_trades[df_trades['reason'] == '止损']
        take_profit_trades = df_trades[df_trades['reason'] == '止盈']
        signal_trades = df_trades[df_trades['reason'] == '反向信号']
        
        print(f"\n=== 进阶策略回测结果 ===")
        print(f"初始资金: ${self.initial_balance:,.2f}")
        print(f"最终资金: ${self.balance:,.2f}")
        print(f"总收益率: {total_return:.2%}")
        print(f"年化收益率: {(total_return / 5):.2%}")
        print(f"总交易次数: {len(df_trades)}")
        print(f"胜率: {win_rate:.2%}")
        
        print(f"\n=== 平仓原因分析 ===")
        print(f"止损平仓: {len(stop_loss_trades)} 次")
        print(f"止盈平仓: {len(take_profit_trades)} 次")
        print(f"信号平仓: {len(signal_trades)} 次")
        
        if len(take_profit_trades) > 0:
            tp_rate = len(take_profit_trades) / len(df_trades)
            print(f"止盈率: {tp_rate:.2%}")
        
        if len(win_trades) > 0:
            avg_win = win_trades['leveraged_pnl_pct'].mean()
            max_win = win_trades['leveraged_pnl_pct'].max()
            avg_duration_win = win_trades['duration_hours'].mean()
            print(f"平均盈利: {avg_win:.2%}")
            print(f"最大盈利: {max_win:.2%}")
            print(f"盈利交易平均持仓时间: {avg_duration_win:.1f}小时")
        
        if len(lose_trades) > 0:
            avg_loss = lose_trades['leveraged_pnl_pct'].mean()
            max_loss = lose_trades['leveraged_pnl_pct'].min()
            avg_duration_loss = lose_trades['duration_hours'].mean()
            print(f"平均亏损: {avg_loss:.2%}")
            print(f"最大亏损: {max_loss:.2%}")
            print(f"亏损交易平均持仓时间: {avg_duration_loss:.1f}小时")
        
        # 盈亏比
        if len(lose_trades) > 0 and len(win_trades) > 0:
            profit_loss_ratio = abs(win_trades['leveraged_pnl_pct'].mean() / lose_trades['leveraged_pnl_pct'].mean())
            print(f"盈亏比: {profit_loss_ratio:.2f}")
        
        # 最近交易
        print(f"\n=== 最近5笔交易 ===")
        recent_trades = self.trades[-5:] if len(self.trades) >= 5 else self.trades
        for i, trade in enumerate(recent_trades, len(self.trades)-len(recent_trades)+1):
            print(f"{i}. {trade['entry_time'].strftime('%m-%d %H:%M')} - "
                  f"{trade['exit_time'].strftime('%m-%d %H:%M')} ({trade['duration_hours']:.1f}h)")
            print(f"   {trade['position']} ${trade['entry_price']:.2f} -> ${trade['exit_price']:.2f}")
            print(f"   收益: {trade['leveraged_pnl_pct']:.2%} - {trade['reason']}")
    
    def show_signals(self, df):
        """信号统计"""
        eightpm_signals = df[df['is_8pm'] & ((df['is_daily_high_at_8pm']) | (df['is_daily_low_at_8pm']))]
        confirmed_signals = df[df['signal'] != 0]
        high_conf_signals = df[abs(df['signal']) == 2]
        
        print(f"\n=== 进阶信号分析 ===")
        print(f"原始8点极值: {len(eightpm_signals)} 次")
        print(f"确认后信号: {len(confirmed_signals)} 个")
        print(f"信号确认率: {len(confirmed_signals)/max(len(eightpm_signals), 1):.1%}")
        print(f"高置信度信号: {len(high_conf_signals)} 个")


def main():
    print("=== 进阶优化版晚上8点高低点策略 ===")
    print("新增优化：")
    print("- 价格确认机制：等待反转确认后入场")
    print("- 动态止盈策略：根据止损比例设置止盈")
    print("- 市场状态判断：区分趋势市和震荡市")
    print("- RSI过滤：避免在极端超买超卖时反向操作")
    print("- 改进的仓位管理和风控")
    
    strategy = AdvancedEightPMStrategy(initial_balance=10000, base_position_size=100)
    
    data = strategy.generate_eth_data(days=1825)
    print(f"生成了 {len(data)} 个小时的数据 (约{len(data)//24}天，{len(data)//24//365:.1f}年)")
    
    analyzed_data = strategy.analyze_data(data)
    strategy.show_signals(analyzed_data)
    strategy.backtest(analyzed_data)
    strategy.print_results()


if __name__ == "__main__":
    main()