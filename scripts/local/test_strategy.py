#!/usr/bin/env python3
"""
本地策略测试脚本 - 不依赖freqtrade环境
用于快速验证策略逻辑和参数
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

from final_optimized_strategy import FinalOptimizedStrategy

def main():
    print("=== 8PM高低点策略 - 本地测试 ===")
    print("这是一个独立的策略测试，不需要freqtrade环境")
    print("")
    
    # 创建策略实例
    strategy = FinalOptimizedStrategy(initial_balance=10000, base_position_size=100)
    
    # 生成测试数据
    print("📊 生成测试数据...")
    data = strategy.generate_eth_data(days=365)  # 1年数据
    print(f"✅ 生成了 {len(data)} 个小时的数据 (约{len(data)//24}天)")
    
    # 分析数据
    print("🔍 分析数据和生成信号...")
    analyzed_data = strategy.analyze_data(data)
    
    # 显示信号统计
    strategy.show_signals(analyzed_data)
    
    # 执行回测
    print("🚀 执行回测...")
    strategy.backtest(analyzed_data)
    
    # 打印结果
    strategy.print_results()
    
    print("")
    print("=== 测试完成 ===")
    print("💡 这是基于模拟数据的测试结果")
    print("📈 实际表现可能因市场环境而异")
    print("🔧 可以修改 final_optimized_strategy.py 中的参数进行调优")

if __name__ == "__main__":
    main()