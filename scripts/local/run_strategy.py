#!/usr/bin/env python3
"""
简化版运行脚本
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

try:
    from final_optimized_strategy import FinalOptimizedStrategy
    
    def main():
        strategy = FinalOptimizedStrategy()
        
        # 生成数据
        data = strategy.generate_eth_data(days=365)
        analyzed_data = strategy.analyze_data(data)
        
        # 显示信号统计
        strategy.show_signals(analyzed_data)
        
        # 执行回测
        strategy.backtest(analyzed_data)
        
        # 打印结果
        strategy.print_results()
    
    main()
    
except ImportError as e:
    print("缺少依赖包，请先安装:")
    print("pip install pandas numpy")
    print(f"错误详情: {e}")
except Exception as e:
    print(f"运行出错: {e}")
    print("请检查策略文件是否存在")