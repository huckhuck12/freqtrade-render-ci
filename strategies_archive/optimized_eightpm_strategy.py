#!/usr/bin/env python3
"""
优化版晚上8点高低点策略
基于原始"大道至简"理念，增加过滤条件和优化措施：
1. 增加成交量确认
2. 添加价格动量过滤
3. 优化仓位管理
4. 改进止损机制
5. 添加趋势过滤
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')


class OptimizedEightPMStrategy:
    def __init__(self, initial_balance=10000, base_position_size=100):
        self.initial_balance = initial_balance
        self.base_position_size = base_position_size  # 基础仓位大小
        self.leverage = 100  # 100倍杠杆
        self.stop_loss = 0.01  # 1%止损
        
        # 优化参数 - 调整为更宽松的条件
        self.volume_threshold = 1.2  # 降低成交量阈值
        self.momentum_threshold = 0.001  # 降低动量阈值
        self.trend_filter_period = 12  # 缩短趋势过滤周期
        self.confidence_multiplier = 1.5  # 降低高置信度仓位倍数
        
        self.balance = initial_balance
        self.positions = []
        self.trades = []
        
    def generate_eth_data(self, days=1825):  # 5年数据
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
        volumes = []
        current_price = initial_price
        
        for i, timestamp in enumerate(date_range):
            # 模拟日内波动模式
            hour = timestamp.hour
            
            # 晚上8点前后增加波动性
            if 18 <= hour <= 22:
                volatility = 0.025  # 2.5%波动率
                volume_base = 15000
            else:
                volatility = 0.015  # 1.5%波动率
                volume_base = 8000
            
            # 随机游走
            change = np.random.normal(0, volatility)
            current_price = current_price * (1 + change)
            
            # 确保价格在合理范围内
            current_price = max(current_price, 1000)
            current_price = min(current_price, 5000)
            
            # 生成成交量（与波动性相关）
            volume_multiplier = 1 + abs(change) * 10  # 波动越大成交量越大
            volume = int(volume_base * volume_multiplier * np.random.uniform(0.5, 2.0))
            
            prices.append(current_price)
            volumes.append(volume)
        
        # 创建OHLC数据
        data = []
        for i, (timestamp, close_price, volume) in enumerate(zip(date_range, prices, volumes)):
            if i == 0:
                open_price = close_price
            else:
                open_price = prices[i-1]
            
            # 模拟日内高低点
            intraday_range = abs(np.random.normal(0, 0.01)) * close_price
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
        """分析数据，添加优化指标"""
        df = data.copy()
        
        # 基础时间信息
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
        
        # === 优化指标 ===
        
        # 1. 成交量过滤
        df['volume_ma'] = df['Volume'].rolling(window=24).mean()  # 24小时成交量均线
        df['volume_ratio'] = df['Volume'] / df['volume_ma']
        df['volume_filter'] = df['volume_ratio'] > self.volume_threshold
        
        # 2. 价格动量
        df['price_change'] = df['Close'].pct_change()
        df['momentum_1h'] = df['Close'].pct_change(1)  # 1小时动量
        df['momentum_3h'] = df['Close'].pct_change(3)  # 3小时动量
        
        # 3. 趋势过滤
        df['trend_ma'] = df['Close'].rolling(window=self.trend_filter_period).mean()
        df['above_trend'] = df['Close'] > df['trend_ma']
        
        # 4. 波动率指标
        df['volatility'] = df['Close'].rolling(window=12).std() / df['Close'].rolling(window=12).mean()
        
        # 5. 价格位置指标（当前价格在日内区间的位置）
        df['daily_range'] = df['daily_high'] - df['daily_low']
        df['price_position'] = (df['Close'] - df['daily_low']) / df['daily_range']
        
        # === 原始8点极值判断 ===
        tolerance = 0.002  # 0.2%容差
        df['is_daily_high_at_8pm'] = (
            df['is_8pm'] & 
            (df['High'] >= df['daily_high'] * (1 - tolerance))
        )
        
        df['is_daily_low_at_8pm'] = (
            df['is_8pm'] & 
            (df['Low'] <= df['daily_low'] * (1 + tolerance))
        )
        
        # === 优化后的信号生成 ===
        
        # 做空信号（8点最高点 + 过滤条件）
        df['short_signal'] = (
            df['is_daily_high_at_8pm'] &
            df['volume_filter'] &  # 成交量确认
            (df['momentum_1h'] < 0) &  # 动量转负（放宽条件）
            (df['price_position'] > 0.7)  # 价格在日内较高位置
        )
        
        # 做多信号（8点最低点 + 过滤条件）
        df['long_signal'] = (
            df['is_daily_low_at_8pm'] &
            df['volume_filter'] &  # 成交量确认
            (df['momentum_1h'] > 0) &  # 动量转正（放宽条件）
            (df['price_position'] < 0.3)  # 价格在日内较低位置
        )
        
        # 高置信度信号（适度严格的条件）
        df['high_confidence_short'] = (
            df['short_signal'] &
            (df['momentum_3h'] < -self.momentum_threshold) &  # 3小时动量转负
            (df['volume_ratio'] > self.volume_threshold * 1.2)  # 成交量适度放大
        )
        
        df['high_confidence_long'] = (
            df['long_signal'] &
            (df['momentum_3h'] > self.momentum_threshold) &  # 3小时动量转正
            (df['volume_ratio'] > self.volume_threshold * 1.2)  # 成交量适度放大
        )
        
        # 生成最终交易信号
        df['signal'] = 0
        df.loc[df['long_signal'], 'signal'] = 1  # 普通做多
        df.loc[df['short_signal'], 'signal'] = -1  # 普通做空
        df.loc[df['high_confidence_long'], 'signal'] = 2  # 高置信度做多
        df.loc[df['high_confidence_short'], 'signal'] = -2  # 高置信度做空
        
        # 将信号延迟到下一个小时执行（避免未来数据）
        df['signal'] = df['signal'].shift(1)
        
        return df
    
    def calculate_position_size(self, signal, current_balance):
        """动态计算仓位大小"""
        if abs(signal) == 2:  # 高置信度信号
            return min(self.base_position_size * self.confidence_multiplier, current_balance * 0.2)
        else:  # 普通信号
            return min(self.base_position_size, current_balance * 0.1)
    
    def calculate_dynamic_stop_loss(self, volatility):
        """根据波动率动态调整止损"""
        # 基础止损1%，根据波动率调整
        base_stop = 0.01
        volatility_adjustment = min(volatility * 2, 0.005)  # 最多增加0.5%
        return base_stop + volatility_adjustment
    
    def backtest(self, df):
        """执行优化后的回测"""
        print("\n=== 开始优化策略回测 ===")
        
        current_position = 0  # 当前仓位：1=多头，-1=空头，0=无仓位
        entry_price = 0
        entry_time = None
        position_size = 0
        dynamic_stop_loss = self.stop_loss
        
        for i, (timestamp, row) in enumerate(df.iterrows()):
            current_price = row['Close']
            signal = row['signal']
            volatility = row.get('volatility', 0.02)
            
            # 检查止损
            if current_position != 0:
                pnl_pct = 0
                if current_position == 1:  # 多头仓位
                    pnl_pct = (current_price - entry_price) / entry_price
                elif current_position == -1:  # 空头仓位
                    pnl_pct = (entry_price - current_price) / entry_price
                
                # 动态止损检查
                if pnl_pct <= -dynamic_stop_loss:
                    self.close_position(timestamp, current_price, entry_price, 
                                      current_position, entry_time, position_size, "动态止损")
                    current_position = 0
            
            # 新信号处理
            if signal != 0 and current_position == 0:
                # 计算仓位大小
                position_size = self.calculate_position_size(signal, self.balance)
                
                # 计算动态止损
                dynamic_stop_loss = self.calculate_dynamic_stop_loss(volatility)
                
                # 开新仓
                current_position = 1 if signal > 0 else -1
                entry_price = current_price
                entry_time = timestamp
                
                confidence = "高置信度" if abs(signal) == 2 else "普通"
                direction = "做多" if signal > 0 else "做空"
                print(f"{timestamp.strftime('%Y-%m-%d %H:%M')}: {confidence}{direction} 入场，"
                      f"价格: ${current_price:.2f}, 仓位: ${position_size:.2f}, 止损: {dynamic_stop_loss:.2%}")
            
            elif signal != 0 and current_position != 0 and np.sign(signal) != current_position:
                # 平仓并开反向仓位
                self.close_position(timestamp, current_price, entry_price, 
                                  current_position, entry_time, position_size, "反向信号")
                
                # 开新仓
                position_size = self.calculate_position_size(signal, self.balance)
                dynamic_stop_loss = self.calculate_dynamic_stop_loss(volatility)
                current_position = 1 if signal > 0 else -1
                entry_price = current_price
                entry_time = timestamp
                
                confidence = "高置信度" if abs(signal) == 2 else "普通"
                direction = "做多" if signal > 0 else "做空"
                print(f"{timestamp.strftime('%Y-%m-%d %H:%M')}: 转向{confidence}{direction}，"
                      f"价格: ${current_price:.2f}, 仓位: ${position_size:.2f}")
        
        # 如果最后还有持仓，平掉
        if current_position != 0:
            final_price = df['Close'].iloc[-1]
            final_time = df.index[-1]
            self.close_position(final_time, final_price, entry_price, 
                              current_position, entry_time, position_size, "回测结束")
    
    def close_position(self, exit_time, exit_price, entry_price, position, entry_time, position_size, reason):
        """平仓"""
        if position == 1:  # 多头
            pnl_pct = (exit_price - entry_price) / entry_price
        else:  # 空头
            pnl_pct = (entry_price - exit_price) / entry_price
        
        # 考虑杠杆效应和动态仓位
        leveraged_pnl_pct = pnl_pct * self.leverage
        
        # 限制单笔交易的最大盈亏
        leveraged_pnl_pct = max(leveraged_pnl_pct, -100)  # 最大亏损100%
        leveraged_pnl_pct = min(leveraged_pnl_pct, 500)   # 最大盈利500%
        
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
            'reason': reason
        }
        
        self.trades.append(trade)
        
        direction = "多头" if position == 1 else "空头"
        print(f"{exit_time.strftime('%Y-%m-%d %H:%M')}: {direction}平仓 ({reason})，"
              f"价格: ${exit_price:.2f}, 收益: {leveraged_pnl_pct:.2%}, 余额: ${self.balance:.2f}")
    
    def print_results(self):
        """打印优化后的回测结果"""
        if not self.trades:
            print("没有交易记录")
            return
        
        df_trades = pd.DataFrame(self.trades)
        
        total_return = (self.balance - self.initial_balance) / self.initial_balance
        win_trades = df_trades[df_trades['pnl_amount'] > 0]
        lose_trades = df_trades[df_trades['pnl_amount'] <= 0]
        
        win_rate = len(win_trades) / len(df_trades) if len(df_trades) > 0 else 0
        
        # 按仓位大小分类统计
        normal_trades = df_trades[df_trades['position_size'] <= self.base_position_size * 1.5]
        high_conf_trades = df_trades[df_trades['position_size'] > self.base_position_size * 1.5]
        
        print(f"\n=== 优化策略回测结果汇总 ===")
        print(f"初始资金: ${self.initial_balance:,.2f}")
        print(f"最终资金: ${self.balance:,.2f}")
        print(f"总收益率: {total_return:.2%}")
        print(f"年化收益率: {(total_return / 5):.2%}")
        print(f"总交易次数: {len(df_trades)}")
        print(f"盈利交易: {len(win_trades)} 次")
        print(f"亏损交易: {len(lose_trades)} 次")
        print(f"胜率: {win_rate:.2%}")
        
        print(f"\n=== 交易分类统计 ===")
        print(f"普通信号交易: {len(normal_trades)} 次")
        print(f"高置信度交易: {len(high_conf_trades)} 次")
        
        if len(high_conf_trades) > 0:
            hc_win_rate = len(high_conf_trades[high_conf_trades['pnl_amount'] > 0]) / len(high_conf_trades)
            print(f"高置信度胜率: {hc_win_rate:.2%}")
        
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
        
        # 显示最近10笔交易
        print(f"\n=== 最近10笔交易记录 ===")
        recent_trades = self.trades[-10:] if len(self.trades) >= 10 else self.trades
        for i, trade in enumerate(recent_trades, len(self.trades)-len(recent_trades)+1):
            print(f"{i}. {trade['entry_time'].strftime('%m-%d %H:%M')} - "
                  f"{trade['exit_time'].strftime('%m-%d %H:%M')}")
            print(f"   {trade['position']} ${trade['entry_price']:.2f} -> ${trade['exit_price']:.2f}")
            print(f"   仓位: ${trade['position_size']:.2f}, 收益: {trade['leveraged_pnl_pct']:.2%} "
                  f"(${trade['pnl_amount']:.2f}) - {trade['reason']}")
            print()
    
    def show_signals(self, df):
        """显示优化后的信号统计"""
        signals = df[df['signal'] != 0]
        eightpm_signals = df[df['is_8pm'] & ((df['is_daily_high_at_8pm']) | (df['is_daily_low_at_8pm']))]
        
        # 过滤后的信号
        filtered_signals = df[df['signal'] != 0]
        high_conf_signals = df[abs(df['signal']) == 2]
        
        print(f"\n=== 优化信号分析 ===")
        print(f"原始8点极值点: {len(eightpm_signals)} 次")
        print(f"过滤后交易信号: {len(filtered_signals)} 个")
        print(f"信号过滤率: {(1 - len(filtered_signals)/max(len(eightpm_signals), 1)):.1%}")
        print(f"高置信度信号: {len(high_conf_signals)} 个")
        print(f"普通做多信号: {len(filtered_signals[filtered_signals['signal'] == 1])} 个")
        print(f"普通做空信号: {len(filtered_signals[filtered_signals['signal'] == -1])} 个")
        print(f"高置信度做多: {len(filtered_signals[filtered_signals['signal'] == 2])} 个")
        print(f"高置信度做空: {len(filtered_signals[filtered_signals['signal'] == -2])} 个")


def main():
    print("=== 优化版晚上8点高低点策略回测 ===")
    print("优化措施：")
    print("- 增加成交量确认过滤")
    print("- 添加价格动量指标")
    print("- 动态仓位管理")
    print("- 根据波动率调整止损")
    print("- 高置信度信号识别")
    print("- 使用模拟ETH数据演示 (5年期)")
    
    # 创建优化策略实例
    strategy = OptimizedEightPMStrategy(initial_balance=10000, base_position_size=100)
    
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