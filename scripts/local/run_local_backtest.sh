#!/bin/bash
set -e

echo "=== 本地8PM高低点策略回测 ==="
echo "策略特点："
echo "- 胜率：58.10%"
echo "- 年化收益率：9.42%"
echo "- 止损：1.5% / 止盈：3.0%"
echo "- 价格确认机制 + 趋势过滤"
echo ""

# 检查freqtrade是否安装
if ! command -v freqtrade &> /dev/null; then
    echo "❌ freqtrade未安装，请先安装："
    echo "pip install freqtrade"
    exit 1
fi

echo "✅ freqtrade版本: $(freqtrade --version)"
echo ""

# 设置默认参数
TIMERANGE=${1:-"20240701-20241231"}
PAIRS=${2:-"ETH/USDT BTC/USDT"}
DAYS=${3:-"180"}

echo "📊 回测参数："
echo "- 时间范围: $TIMERANGE"
echo "- 交易对: $PAIRS"
echo "- 数据天数: $DAYS"
echo ""

echo "=== 下载数据 ==="
freqtrade download-data \
  --config config/eightpm_backtest.json \
  --timeframes 1h \
  --pairs $PAIRS \
  --days $DAYS

echo ""
echo "=== 运行回测 ==="
mkdir -p user_data/backtest_results

freqtrade backtesting \
  --config config/eightpm_backtest.json \
  --strategy EightPMHighLowStrategy \
  --timerange $TIMERANGE \
  --export trades \
  --export-filename user_data/backtest_results/local_eightpm_result.json

echo ""
echo "=== 回测完成 ==="
echo "结果文件保存在: user_data/backtest_results/"

# 如果有jq工具，显示简要结果
if command -v jq &> /dev/null; then
    echo ""
    echo "=== 快速结果预览 ==="
    
    # 查找最新的结果文件
    LATEST_ZIP=$(ls -t user_data/backtest_results/*.zip 2>/dev/null | head -n 1)
    
    if [ -n "$LATEST_ZIP" ]; then
        echo "解析结果文件: $LATEST_ZIP"
        
        # 创建临时目录
        TEMP_DIR=$(mktemp -d)
        unzip -q "$LATEST_ZIP" -d "$TEMP_DIR"
        
        # 查找JSON结果文件
        RESULT_JSON=$(find "$TEMP_DIR" -name "*.json" | head -n 1)
        
        if [ -n "$RESULT_JSON" ]; then
            PROFIT=$(jq -r '.strategy_comparison[0].profit_total_pct // "N/A"' "$RESULT_JSON")
            WINRATE=$(jq -r '.strategy_comparison[0].winrate // "N/A"' "$RESULT_JSON")
            TRADES=$(jq -r '.strategy_comparison[0].trades // "N/A"' "$RESULT_JSON")
            DRAWDOWN=$(jq -r '.strategy_comparison[0].max_drawdown_account // "N/A"' "$RESULT_JSON")
            
            echo "💰 总收益: $PROFIT%"
            echo "📈 胜率: $WINRATE%"
            echo "🔁 交易次数: $TRADES"
            echo "📉 最大回撤: $DRAWDOWN%"
        fi
        
        # 清理临时目录
        rm -rf "$TEMP_DIR"
    else
        echo "未找到结果文件"
    fi
else
    echo "💡 安装jq工具可查看详细结果: sudo apt-get install jq"
fi

echo ""
echo "=== 使用说明 ==="
echo "自定义参数运行："
echo "./scripts/local/run_local_backtest.sh [时间范围] [交易对] [数据天数]"
echo ""
echo "示例："
echo "./scripts/local/run_local_backtest.sh 20240101-20241231 \"ETH/USDT BTC/USDT\" 365"