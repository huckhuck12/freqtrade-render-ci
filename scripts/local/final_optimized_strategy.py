#!/usr/bin/env python3
"""
最终优化版晚上8点高低点策略
基于前面的分析，重新设计策略逻辑：
1. 简化过滤条件，提高信号数量
2. 改进入场时机选择
3. 优化止损止盈比例
4. 加入趋势跟随元素
5. 更好的资金管理
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')


class FinalOptimizedStrategy:
    def __init__(self, initial_balance=10000, base_position_size=100):
        self.initial_balance = initial_balance
        self.base_position_size = base_position_size
        self.leverage = 100
        
        # 优化后的参数
        self.stop_loss = 0.015  # 1.5%止损
        self.take_profit = 0.03  # 3%止盈
        self.volume_threshold = 1.1  # 降低成交量要求
        self.confirmation_candles = 1  # 减少确认时间
        
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
        
        for i, timestamp in enumerate(date_range):
            hour = timestamp.hour
            
            # 简化的波动模式
            if 18 <= hour <= 22:
                volatility = 0.02
                volume_base = 12000
            else:
                volatility = 0.012
                volume_base = 8000
            
            # 添加一些趋势性
            if i > 0 and i % (24*30) == 0:  # 每月调整趋势
                trend_change = np.random.choice([-0.0005, 0, 0.0005], p=[0.3, 0.4, 0.3])
            else:
                trend_change = 0
            
            change = np.random.normal(trend_change, volatility)
            current_price = current_price * (1 + change)
            
            current_price = max(current_price, 800)
            current_price = min(current_price, 6000)
            
            volume = int(volume_base * (1 + abs(change) * 10) * np.random.uniform(0.5, 2.0))
            
            prices.append(current_price)
            volumes.append(volume)
        
        # 创建OHLC数据
        data = []
        for i, (timestamp, close_price, volume) in enumerate(zip(date_range, prices, volumes)):
            if i == 0:
                open_price = close_price
            else:
                open_price = prices[i-1]
            
            intraday_range = abs(np.random.normal(0, 0.008)) * close_price
            high = max(open_price, close_price) + intraday_range * 0.5
            low = min(open_price, close_price) - intraday_range * 0.5
            
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
        """简化但有效的数据分析"""
        df = data.copy()
        
        # 基础信息
        df['hour'] = df.index.hour
        df['date'] = df.index.date
        df['is_8pm'] = (df['hour'] == 20)
        
        # 每日统计
        daily_stats = df.groupby('date').agg({
            'High': 'max',
            'Low': 'min',
            'Volume': 'mean'
        }).rename(columns={'High': 'daily_high', 'Low': 'daily_low', 'Volume': 'daily_avg_volume'})
        
        df = df.join(daily_stats, on='date')
        
        # 简化的技术指标
        df['sma_20'] = df['Close'].rolling(20).mean()
        df['volume_ratio'] = df['Volume'] / df['Volume'].rolling(20).mean()
        df['price_change_1h'] = df['Close'].pct_change(1)
        df['price_change_3h'] = df['Close'].pct_change(3)
        
        # 8点极值判断
        tolerance = 0.005  # 放宽容差到0.5%
        df['is_daily_high_at_8pm'] = (
            df['is_8pm'] & 
            (df['High'] >= df['daily_high'] * (1 - tolerance))
        )
        
        df['is_daily_low_at_8pm'] = (
            df['is_8pm'] & 
            (df['Low'] <= df['daily_low'] * (1 + tolerance))
        )
        
        # 简化的信号生成
        # 基础条件：8点极值 + 成交量确认
        base_long = (
            df['is_daily_low_at_8pm'] &
            (df['volume_ratio'] > self.volume_threshold)
        )
        
        base_short = (
            df['is_daily_high_at_8pm'] &
            (df['volume_ratio'] > self.volume_threshold)
        )
        
        # 价格确认：等待下一个小时的价格确认
        df['confirmed_long'] = False
        df['confirmed_short'] = False
        
        for i in range(1, len(df)):
            # 做多确认：价格开始反弹
            if base_long.iloc[i-1]:
                if df['price_change_1h'].iloc[i] > 0.001:  # 0.1%反弹确认
                    df.iloc[i, df.columns.get_loc('confirmed_long')] = True
            
            # 做空确认：价格开始下跌
            if base_short.iloc[i-1]:
                if df['price_change_1h'].iloc[i] < -0.001:  # 0.1%下跌确认
                    df.iloc[i, df.columns.get_loc('confirmed_short')] = True
        
        # 趋势过滤：只在价格接近均线时交易（减少逆势交易）
        df['near_sma'] = abs(df['Close'] - df['sma_20']) / df['sma_20'] < 0.05  # 5%范围内
        
        # 最终信号
        df['long_signal'] = df['confirmed_long'] & df['near_sma']
        df['short_signal'] = df['confirmed_short'] & df['near_sma']
        
        # 生成数值信号
        df['signal'] = 0
        df.loc[df['long_signal'], 'signal'] = 1
        df.loc[df['short_signal'], 'signal'] = -1
        
        return df
    
    def backtest(self, df):
        """简化的回测逻辑"""
        print("\n=== 开始最终优化策略回测 ===")
        
        current_position = 0
        entry_price = 0
        entry_time = None
        
        for i, (timestamp, row) in enumerate(df.iterrows()):
            current_price = row['Close']
            signal = row['signal']
            
            # 检查止损止盈
            if current_position != 0:
                if current_position == 1:  # 多头
                    pnl_pct = (current_price - entry_price) / entry_price
                    if pnl_pct <= -self.stop_loss:
                        self.close_position(timestamp, current_price, entry_price, 
                                          current_position, entry_time, "止损")
                        current_position = 0
                    elif pnl_pct >= self.take_profit:
                        self.close_position(timestamp, current_price, entry_price, 
                                          current_position, entry_time, "止盈")
                        current_position = 0
                        
                elif current_position == -1:  # 空头
                    pnl_pct = (entry_price - current_price) / entry_price
                    if pnl_pct <= -self.stop_loss:
                        self.close_position(timestamp, current_price, entry_price, 
                                          current_position, entry_time, "止损")
                        current_position = 0
                    elif pnl_pct >= self.take_profit:
                        self.close_position(timestamp, current_price, entry_price, 
                                          current_position, entry_time, "止盈")
                        current_position = 0
            
            # 新信号
            if signal != 0 and current_position == 0:
                current_position = signal
                entry_price = current_price
                entry_time = timestamp
                
                direction = "做多" if signal > 0 else "做空"
                print(f"{timestamp.strftime('%Y-%m-%d %H:%M')}: {direction} 入场，价格: ${current_price:.2f}")
            
            elif signal != 0 and current_position != 0 and signal != current_position:
                # 反向信号
                self.close_position(timestamp, current_price, entry_price, 
                                  current_position, entry_time, "反向信号")
                
                current_position = signal
                entry_price = current_price
                entry_time = timestamp
                
                direction = "做多" if signal > 0 else "做空"
                print(f"{timestamp.strftime('%Y-%m-%d %H:%M')}: 转向{direction}，价格: ${current_price:.2f}")
        
        # 最后平仓
        if current_position != 0:
            final_price = df['Close'].iloc[-1]
            final_time = df.index[-1]
            self.close_position(final_time, final_price, entry_price, 
                              current_position, entry_time, "回测结束")
    
    def close_position(self, exit_time, exit_price, entry_price, position, entry_time, reason):
        """平仓处理"""
        if position == 1:
            pnl_pct = (exit_price - entry_price) / entry_price
        else:
            pnl_pct = (entry_price - exit_price) / entry_price
        
        leveraged_pnl_pct = pnl_pct * self.leverage
        leveraged_pnl_pct = max(leveraged_pnl_pct, -100)
        leveraged_pnl_pct = min(leveraged_pnl_pct, 300)
        
        pnl_amount = self.base_position_size * leveraged_pnl_pct / 100
        self.balance += pnl_amount
        
        trade = {
            'entry_time': entry_time,
            'exit_time': exit_time,
            'entry_price': entry_price,
            'exit_price': exit_price,
            'position': '多头' if position == 1 else '空头',
            'pnl_pct': pnl_pct,
            'leveraged_pnl_pct': leveraged_pnl_pct,
            'pnl_amount': pnl_amount,
            'balance': self.balance,
            'reason': reason,
            'duration_hours': (exit_time - entry_time).total_seconds() / 3600
        }
        
        self.trades.append(trade)
        
        direction = "多头" if position == 1 else "空头"
        print(f"{exit_time.strftime('%Y-%m-%d %H:%M')}: {direction}平仓 ({reason})，"
              f"收益: {leveraged_pnl_pct:.2%}, 余额: ${self.balance:.2f}")
    
    def print_results(self):
        """结果分析"""
        if not self.trades:
            print("没有交易记录")
            return
        
        df_trades = pd.DataFrame(self.trades)
        
        total_return = (self.balance - self.initial_balance) / self.initial_balance
        win_trades = df_trades[df_trades['pnl_amount'] > 0]
        lose_trades = df_trades[df_trades['pnl_amount'] <= 0]
        
        win_rate = len(win_trades) / len(df_trades) if len(df_trades) > 0 else 0
        
        # 按原因分类
        stop_loss_trades = df_trades[df_trades['reason'] == '止损']
        take_profit_trades = df_trades[df_trades['reason'] == '止盈']
        
        print(f"\n=== 最终优化策略结果 ===")
        print(f"初始资金: ${self.initial_balance:,.2f}")
        print(f"最终资金: ${self.balance:,.2f}")
        print(f"总收益率: {total_return:.2%}")
        print(f"年化收益率: {(total_return / 5):.2%}")
        print(f"总交易次数: {len(df_trades)}")
        print(f"胜率: {win_rate:.2%}")
        
        print(f"\n=== 交易分析 ===")
        print(f"止损次数: {len(stop_loss_trades)}")
        print(f"止盈次数: {len(take_profit_trades)}")
        print(f"止盈率: {len(take_profit_trades)/len(df_trades):.2%}")
        
        if len(win_trades) > 0:
            avg_win = win_trades['leveraged_pnl_pct'].mean()
            print(f"平均盈利: {avg_win:.2%}")
        
        if len(lose_trades) > 0:
            avg_loss = lose_trades['leveraged_pnl_pct'].mean()
            print(f"平均亏损: {avg_loss:.2%}")
        
        if len(lose_trades) > 0 and len(win_trades) > 0:
            profit_loss_ratio = abs(avg_win / avg_loss)
            print(f"盈亏比: {profit_loss_ratio:.2f}")
        
        # 显示所有交易
        print(f"\n=== 所有交易记录 ===")
        for i, trade in enumerate(self.trades, 1):
            duration = trade['duration_hours']
            print(f"{i}. {trade['entry_time'].strftime('%Y-%m-%d %H:%M')} - "
                  f"{trade['exit_time'].strftime('%m-%d %H:%M')} ({duration:.1f}h)")
            print(f"   {trade['position']} ${trade['entry_price']:.2f} -> ${trade['exit_price']:.2f}")
            print(f"   收益: {trade['leveraged_pnl_pct']:.2%} (${trade['pnl_amount']:.2f}) - {trade['reason']}")
            print()
    
    def show_signals(self, df):
        """信号统计"""
        eightpm_extremes = df[df['is_8pm'] & ((df['is_daily_high_at_8pm']) | (df['is_daily_low_at_8pm']))]
        confirmed_signals = df[df['signal'] != 0]
        
        print(f"\n=== 最终策略信号分析 ===")
        print(f"8点极值出现: {len(eightpm_extremes)} 次")
        print(f"确认交易信号: {len(confirmed_signals)} 个")
        print(f"信号转化率: {len(confirmed_signals)/max(len(eightpm_extremes), 1):.1%}")
        print(f"做多信号: {len(confirmed_signals[confirmed_signals['signal'] == 1])} 个")
        print(f"做空信号: {len(confirmed_signals[confirmed_signals['signal'] == -1])} 个")


def main():
    print("=== 最终优化版晚上8点高低点策略 ===")
    print("最终优化重点：")
    print("- 简化过滤条件，提高信号数量")
    print("- 优化止损止盈比例 (1.5% : 3%)")
    print("- 快速价格确认机制")
    print("- 趋势过滤：只在价格接近均线时交易")
    print("- 平衡的风险收益比")
    
    strategy = FinalOptimizedStrategy(initial_balance=10000, base_position_size=100)
    
    data = strategy.generate_eth_data(days=1825)
    print(f"生成了 {len(data)} 个小时的数据 (约{len(data)//24}天，{len(data)//24//365:.1f}年)")
    
    analyzed_data = strategy.analyze_data(data)
    strategy.show_signals(analyzed_data)
    strategy.backtest(analyzed_data)
    strategy.print_results()


if __name__ == "__main__":
    main()