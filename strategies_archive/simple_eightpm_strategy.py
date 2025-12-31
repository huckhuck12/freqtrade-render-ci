#!/usr/bin/env python3
"""
晚上8点高低点策略 - 简化版（不依赖yfinance）
大道至简：
- 以晚上8点为分界线
- 判断8点是否为当天最高点或最低点  
- 最高点则做空，最低点则做多
- 100倍杠杆，1%止损（相当于爆仓）
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')


class EightPMStrategy:
    def __init__(self, initial_balance=10000, position_size=100):
        self.initial_balance = initial_balance
        self.position_size = position_size  # 固定仓位大小
        self.leverage = 100  # 100倍杠杆
        self.stop_loss = 0.01  # 1%止损
        
        self.balance = initial_balance
        self.positions = []
        self.trades = []
        
    def generate_eth_data(self, days=1825):  # 5年 = 365 * 5
        """生成模拟的ETH价格数据（基于真实走势特征）"""
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        print(f"生成模拟ETH数据，时间范围: {start_date.date()} 到 {end_date.date()}")
        
        # 创建小时级时间序列
        date_range = pd.date_range(start=start_date, end=end_date, freq='H')
        
        # 模拟ETH价格走势
        np.random.seed(42)  # 固定随机种子以便复现结果
        
        initial_price = 2400  # ETH初始价格
        
        # 生成价格序列
        prices = []
        current_price = initial_price
        
        for i, timestamp in enumerate(date_range):
            # 模拟日内波动模式
            hour = timestamp.hour
            
            # 晚上8点前后增加波动性
            if 18 <= hour <= 22:
                volatility = 0.025  # 2.5%波动率
            else:
                volatility = 0.015  # 1.5%波动率
            
            # 随机游走
            change = np.random.normal(0, volatility)
            current_price = current_price * (1 + change)
            
            # 确保价格在合理范围内
            current_price = max(current_price, 1000)
            current_price = min(current_price, 5000)
            
            prices.append(current_price)
        
        # 创建OHLC数据
        data = []
        for i, (timestamp, close_price) in enumerate(zip(date_range, prices)):
            if i == 0:
                open_price = close_price
            else:
                open_price = prices[i-1]
            
            # 模拟日内高低点
            intraday_range = abs(np.random.normal(0, 0.01)) * close_price
            high = max(open_price, close_price) + intraday_range * 0.5
            low = min(open_price, close_price) - intraday_range * 0.5
            
            volume = np.random.randint(5000, 20000)
            
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
        """分析数据，找出8点高低点信号"""
        df = data.copy()
        
        # 获取小时和日期
        df['hour'] = df.index.hour
        df['date'] = df.index.date
        
        # 标记晚上8点（20点）
        df['is_8pm'] = (df['hour'] == 20)
        
        # 计算每日最高价和最低价
        daily_stats = df.groupby('date').agg({
            'High': 'max',
            'Low': 'min'
        }).rename(columns={'High': 'daily_high', 'Low': 'daily_low'})
        
        # 合并回原数据
        df = df.join(daily_stats, on='date')
        
        # 判断8点是否为当日极值点
        tolerance = 0.002  # 0.2%容差
        df['is_daily_high_at_8pm'] = (
            df['is_8pm'] & 
            (df['High'] >= df['daily_high'] * (1 - tolerance))
        )
        
        df['is_daily_low_at_8pm'] = (
            df['is_8pm'] & 
            (df['Low'] <= df['daily_low'] * (1 + tolerance))
        )
        
        # 生成交易信号
        df['signal'] = 0
        df.loc[df['is_daily_high_at_8pm'], 'signal'] = -1  # 做空信号
        df.loc[df['is_daily_low_at_8pm'], 'signal'] = 1   # 做多信号
        
        # 将信号延迟到下一个小时执行（避免未来数据）
        df['signal'] = df['signal'].shift(1)
        
        return df
    
    def backtest(self, df):
        """执行回测"""
        print("\n=== 开始回测 ===")
        
        current_position = 0  # 当前仓位：1=多头，-1=空头，0=无仓位
        entry_price = 0
        entry_time = None
        
        for i, (timestamp, row) in enumerate(df.iterrows()):
            current_price = row['Close']
            signal = row['signal']
            
            # 检查止损
            if current_position != 0:
                pnl_pct = 0  # 初始化
                if current_position == 1:  # 多头仓位
                    pnl_pct = (current_price - entry_price) / entry_price
                elif current_position == -1:  # 空头仓位
                    pnl_pct = (entry_price - current_price) / entry_price
                
                # 止损检查
                if pnl_pct <= -self.stop_loss:
                    self.close_position(timestamp, current_price, entry_price, 
                                      current_position, entry_time, "止损")
                    current_position = 0
            
            # 新信号处理
            if signal != 0 and current_position == 0:
                # 开新仓
                current_position = signal
                entry_price = current_price
                entry_time = timestamp
                
                direction = "做多" if signal == 1 else "做空"
                print(f"{timestamp.strftime('%Y-%m-%d %H:%M')}: {direction} 入场，价格: ${current_price:.2f}")
            
            elif signal != 0 and current_position != 0 and signal != current_position:
                # 平仓并开反向仓位
                self.close_position(timestamp, current_price, entry_price, 
                                  current_position, entry_time, "反向信号")
                
                current_position = signal
                entry_price = current_price
                entry_time = timestamp
                
                direction = "做多" if signal == 1 else "做空"
                print(f"{timestamp.strftime('%Y-%m-%d %H:%M')}: 转向{direction}，价格: ${current_price:.2f}")
        
        # 如果最后还有持仓，平掉
        if current_position != 0:
            final_price = df['Close'].iloc[-1]
            final_time = df.index[-1]
            self.close_position(final_time, final_price, entry_price, 
                              current_position, entry_time, "回测结束")
    
    def close_position(self, exit_time, exit_price, entry_price, position, entry_time, reason):
        """平仓"""
        if position == 1:  # 多头
            pnl_pct = (exit_price - entry_price) / entry_price
        else:  # 空头
            pnl_pct = (entry_price - exit_price) / entry_price
        
        # 考虑杠杆效应 - 限制最大收益/亏损
        leveraged_pnl_pct = pnl_pct * self.leverage
        
        # 限制单笔交易的最大盈亏（防止过度杠杆化）
        leveraged_pnl_pct = max(leveraged_pnl_pct, -100)  # 最大亏损100%（爆仓）
        leveraged_pnl_pct = min(leveraged_pnl_pct, 500)   # 最大盈利500%
        
        pnl_amount = self.position_size * leveraged_pnl_pct / 100
        
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
            'reason': reason
        }
        
        self.trades.append(trade)
        
        direction = "多头" if position == 1 else "空头"
        print(f"{exit_time.strftime('%Y-%m-%d %H:%M')}: {direction}平仓 ({reason})，"
              f"价格: ${exit_price:.2f}, 收益: {leveraged_pnl_pct:.2%}, 余额: ${self.balance:.2f}")
    
    def print_results(self):
        """打印回测结果"""
        if not self.trades:
            print("没有交易记录")
            return
        
        df_trades = pd.DataFrame(self.trades)
        
        total_return = (self.balance - self.initial_balance) / self.initial_balance
        win_trades = df_trades[df_trades['pnl_amount'] > 0]
        lose_trades = df_trades[df_trades['pnl_amount'] <= 0]
        
        win_rate = len(win_trades) / len(df_trades) if len(df_trades) > 0 else 0
        
        print(f"\n=== 回测结果汇总 ===")
        print(f"初始资金: ${self.initial_balance:,.2f}")
        print(f"最终资金: ${self.balance:,.2f}")
        print(f"总收益率: {total_return:.2%}")
        print(f"总交易次数: {len(df_trades)}")
        print(f"盈利交易: {len(win_trades)} 次")
        print(f"亏损交易: {len(lose_trades)} 次")
        print(f"胜率: {win_rate:.2%}")
        
        if len(win_trades) > 0:
            avg_win = win_trades['leveraged_pnl_pct'].mean()
            max_win = win_trades['leveraged_pnl_pct'].max()
            print(f"平均盈利: {avg_win:.2%}")
            print(f"最大盈利: {max_win:.2%}")
        
        if len(lose_trades) > 0:
            avg_loss = lose_trades['leveraged_pnl_pct'].mean()
            max_loss = lose_trades['leveraged_pnl_pct'].min()
            print(f"平均亏损: {avg_loss:.2%}")
            print(f"最大亏损: {max_loss:.2%}")
        
        print(f"\n=== 详细交易记录 ===")
        for i, trade in enumerate(self.trades, 1):
            print(f"{i}. {trade['entry_time'].strftime('%m-%d %H:%M')} - "
                  f"{trade['exit_time'].strftime('%m-%d %H:%M')}")
            print(f"   {trade['position']} ${trade['entry_price']:.2f} -> ${trade['exit_price']:.2f}")
            print(f"   收益: {trade['leveraged_pnl_pct']:.2%} (${trade['pnl_amount']:.2f}) - {trade['reason']}")
            print()
    
    def show_signals(self, df):
        """显示信号统计"""
        signals = df[df['signal'] != 0]
        eightpm_signals = df[df['is_8pm'] & ((df['is_daily_high_at_8pm']) | (df['is_daily_low_at_8pm']))]
        
        print(f"\n=== 信号分析 ===")
        print(f"8点高低点出现次数: {len(eightpm_signals)}")
        print(f"8点为最高点: {len(eightpm_signals[eightpm_signals['is_daily_high_at_8pm']])} 次")
        print(f"8点为最低点: {len(eightpm_signals[eightpm_signals['is_daily_low_at_8pm']])} 次")
        print(f"实际交易信号: {len(signals)} 个")
        print(f"做多信号: {len(signals[signals['signal'] == 1])} 个")
        print(f"做空信号: {len(signals[signals['signal'] == -1])} 个")
        
        if len(eightpm_signals) > 0:
            print(f"\n8点极值点详情:")
            for _, row in eightpm_signals.iterrows():
                date_str = row.name.strftime('%Y-%m-%d')
                if row['is_daily_high_at_8pm']:
                    print(f"  {date_str}: 8点最高点 ${row['High']:.2f} (日高${row['daily_high']:.2f}) -> 做空信号")
                if row['is_daily_low_at_8pm']:
                    print(f"  {date_str}: 8点最低点 ${row['Low']:.2f} (日低${row['daily_low']:.2f}) -> 做多信号")


def main():
    print("=== 晚上8点高低点策略回测 ===")
    print("策略说明：")
    print("- 以晚上8点为分界线判断当日高低点")
    print("- 8点为最高点则做空，8点为最低点则做多")
    print("- 100倍杠杆，1%止损（相当于爆仓）")
    print("- 固定仓位大小: $100")
    print("- 使用模拟ETH数据演示 (5年期)")
    print("- 注意：这是模拟数据，实际市场可能有所不同")
    
    # 创建策略实例
    strategy = EightPMStrategy(initial_balance=10000, position_size=100)
    
    # 生成模拟数据
    data = strategy.generate_eth_data(days=1825)  # 5年数据
    print(f"生成了 {len(data)} 个小时的数据 (约{len(data)//24}天，{len(data)//24//365:.1f}年)")
    
    # 分析数据
    analyzed_data = strategy.analyze_data(data)
    
    # 显示信号统计
    strategy.show_signals(analyzed_data)
    
    # 执行回测
    strategy.backtest(analyzed_data)
    
    # 打印结果
    strategy.print_results()


if __name__ == "__main__":
    main()