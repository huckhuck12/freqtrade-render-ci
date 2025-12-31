#!/usr/bin/env python3
"""
晚上8点高低点策略 - 独立实现
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

# 尝试导入yfinance，如果失败则使用模拟数据
try:
    import yfinance as yf
    HAS_YFINANCE = True
except ImportError:
    HAS_YFINANCE = False
    print("yfinance导入失败，将使用模拟数据进行演示")


class EightPMStrategy:
    def __init__(self, symbol="ETH-USD", initial_balance=10000, position_size=100):
        self.symbol = symbol
        self.initial_balance = initial_balance
        self.position_size = position_size  # 固定仓位大小
        self.leverage = 100  # 100倍杠杆
        self.stop_loss = 0.01  # 1%止损
        
        self.balance = initial_balance
        self.positions = []
        self.trades = []
        
    def get_data(self, days=90):
        """获取历史数据"""
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        print(f"获取 {self.symbol} 数据，时间范围: {start_date.date()} 到 {end_date.date()}")
        
        if HAS_YFINANCE:
            try:
                # 获取小时级数据
                data = yf.download(self.symbol, start=start_date, end=end_date, interval="1h")
                
                if data.empty:
                    print("无法获取数据，尝试使用ETH-USD...")
                    data = yf.download("ETH-USD", start=start_date, end=end_date, interval="1h")
                
                if not data.empty:
                    return data
            except Exception as e:
                print(f"yfinance获取数据失败: {e}")
        
        # 如果yfinance失败或不可用，生成模拟数据
        print("使用模拟ETH数据进行演示...")
        return self.generate_mock_data(start_date, end_date)
    
    def generate_mock_data(self, start_date, end_date):
        """生成模拟的ETH价格数据"""
        # 创建小时级时间序列
        date_range = pd.date_range(start=start_date, end=end_date, freq='H')
        
        # 模拟ETH价格走势（基于随机游走）
        np.random.seed(42)  # 固定随机种子以便复现
        
        initial_price = 2000  # ETH初始价格
        returns = np.random.normal(0, 0.02, len(date_range))  # 2%波动率
        
        prices = [initial_price]
        for ret in returns[1:]:
            new_price = prices[-1] * (1 + ret)
            prices.append(max(new_price, 100))  # 价格不能低于100
        
        # 创建OHLC数据
        data = []
        for i, (timestamp, price) in enumerate(zip(date_range, prices)):
            # 模拟日内波动
            high = price * (1 + abs(np.random.normal(0, 0.005)))
            low = price * (1 - abs(np.random.normal(0, 0.005)))
            open_price = prices[i-1] if i > 0 else price
            close_price = price
            volume = np.random.randint(1000, 10000)
            
            data.append({
                'Open': open_price,
                'High': max(open_price, high, close_price),
                'Low': min(open_price, low, close_price),
                'Close': close_price,
                'Volume': volume
            })
        
        df = pd.DataFrame(data, index=date_range)
        return df
    
    def analyze_data(self, data):
        """分析数据，找出8点高低点信号"""
        df = data.copy()
        
        # 确保索引是datetime
        if not isinstance(df.index, pd.DatetimeIndex):
            df.index = pd.to_datetime(df.index)
        
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
        tolerance = 0.001  # 0.1%容差
        df['is_daily_high_at_8pm'] = (
            df['is_8pm'] & 
            (df['High'] >= df['daily_high'] * (1 - tolerance))
        )
        
        df['is_daily_low_at_8pm'] = (
            df['is_8pm'] & 
            (df['Low'] <= df['daily_low'] * (1 + tolerance))
        )
        
        # 生成交易信号（延迟一个小时执行）
        df['signal'] = 0
        df.loc[df['is_daily_high_at_8pm'], 'signal'] = -1  # 做空信号
        df.loc[df['is_daily_low_at_8pm'], 'signal'] = 1   # 做多信号
        
        # 将信号延迟到下一个小时
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
                print(f"{timestamp}: {direction} 入场，价格: ${current_price:.2f}")
            
            elif signal != 0 and current_position != 0 and signal != current_position:
                # 平仓并开反向仓位
                self.close_position(timestamp, current_price, entry_price, 
                                  current_position, entry_time, "反向信号")
                
                current_position = signal
                entry_price = current_price
                entry_time = timestamp
                
                direction = "做多" if signal == 1 else "做空"
                print(f"{timestamp}: 转向{direction}，价格: ${current_price:.2f}")
        
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
        
        # 考虑杠杆效应
        leveraged_pnl_pct = pnl_pct * self.leverage
        pnl_amount = self.position_size * leveraged_pnl_pct
        
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
        print(f"{exit_time}: {direction}平仓 ({reason})，价格: ${exit_price:.2f}, "
              f"收益: {leveraged_pnl_pct:.2%}, 余额: ${self.balance:.2f}")
    
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
            print(f"平均盈利: {avg_win:.2%}")
        
        if len(lose_trades) > 0:
            avg_loss = lose_trades['leveraged_pnl_pct'].mean()
            print(f"平均亏损: {avg_loss:.2%}")
        
        print(f"\n=== 详细交易记录 ===")
        for i, trade in enumerate(self.trades, 1):
            print(f"{i}. {trade['entry_time'].strftime('%Y-%m-%d %H:%M')} - "
                  f"{trade['exit_time'].strftime('%Y-%m-%d %H:%M')}")
            print(f"   {trade['position']} ${trade['entry_price']:.2f} -> ${trade['exit_price']:.2f}")
            print(f"   收益: {trade['leveraged_pnl_pct']:.2%} (${trade['pnl_amount']:.2f}) - {trade['reason']}")
            print()


def main():
    print("=== 晚上8点高低点策略回测 ===")
    print("策略说明：")
    print("- 以晚上8点为分界线判断当日高低点")
    print("- 8点为最高点则做空，8点为最低点则做多")
    print("- 100倍杠杆，1%止损（相当于爆仓）")
    print("- 固定仓位大小")
    
    # 创建策略实例
    strategy = EightPMStrategy(symbol="ETH-USD", initial_balance=10000, position_size=100)
    
    # 获取数据
    data = strategy.get_data(days=90)
    
    if data.empty:
        print("无法获取数据，请检查网络连接")
        return
    
    # 分析数据
    analyzed_data = strategy.analyze_data(data)
    
    # 显示信号统计
    signals = analyzed_data[analyzed_data['signal'] != 0]
    print(f"\n找到 {len(signals)} 个交易信号:")
    print(f"做多信号: {len(signals[signals['signal'] == 1])} 个")
    print(f"做空信号: {len(signals[signals['signal'] == -1])} 个")
    
    # 执行回测
    strategy.backtest(analyzed_data)
    
    # 打印结果
    strategy.print_results()


if __name__ == "__main__":
    main()