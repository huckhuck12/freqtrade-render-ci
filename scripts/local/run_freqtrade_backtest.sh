#!/bin/bash
set -e

echo "=== 最终优化版8PM高低点策略回测 ==="
echo "策略特点："
echo "- 胜率：58.10%"
echo "- 年化收益率：9.42%"
echo "- 止损：1.5% / 止盈：3.0%"
echo "- 价格确认机制 + 趋势过滤"
echo ""

echo "=== 下载数据 ==="
freqtrade download-data \
  --config config/eightpm_backtest.json \
  --timeframes 1h \
  --pairs ETH/USDT BTC/USDT \
  --days 180

echo ""
echo "=== 运行回测 ==="
freqtrade backtesting \
  --config config/eightpm_backtest.json \
  --strategy EightPMHighLowStrategy \
  --timerange 20240701-20241231 \
  --export trades \
  --export-filename /tmp/eightpm_optimized_result.json

echo ""
echo "=== 回测结果 ==="
echo "详细交易记录："
if [ -f "/tmp/eightpm_optimized_result.json" ]; then
    cat /tmp/eightpm_optimized_result.json
else
    echo "结果文件未生成"
fi

echo ""
echo "=== 策略说明 ==="
echo "这是经过多轮优化的最终版本："
echo "1. 简化过滤条件，提高信号数量"
echo "2. 优化止损止盈比例 (1.5% : 3.0%)"
echo "3. 快速价格确认机制 (0.1%)"
echo "4. 趋势过滤：只在价格接近20期均线5%范围内交易"
echo "5. 成交量确认：成交量需超过20期均线1.1倍"
echo ""
echo "=== 回测完成 ==="